# -*- coding: utf-8 -*-
"""
Qt front end for the 42 IPC socket link.

Layering, deliberately:

    ipc42.py       protocol + blocking listener   (no Qt, no orb)
    ipc42_gui.py   worker thread + monitor panel  (this module)

`Ipc42Worker` owns the socket and does all blocking work off the GUI thread.
It reports **only via pyqtSignal**, never pydispatcher: Qt marshals a
cross-thread signal onto the receiver's event loop, whereas pydispatcher
calls the receiver synchronously in the *sending* thread, which here would be
the worker — touching widgets from it is undefined behaviour. That boundary
is the one established in `pydispatcher_migration.md` §1, and this module is
the first new code on the far side of it.

**Run / pause / step are ack policy, not commands to 42.** 42 blocks on
`read(Socket, Ack, 4)` after every message, so the worker simply declines to
ack while paused. There is no command channel in 42's IPC (see
`NOTES_ON_42_IPC.md` §1), so this is the only control that needs no change to
42 itself.
"""
import errno
import socket
import threading
import time

from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtWidgets import (QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                             QPushButton, QSpinBox, QVBoxLayout, QWidget)

from pangalactic.core import orb
from pangalactic.node.ipc42 import Listener42, parse_message

# Prefixes worth subscribing to for ACS work.  Deliberately NOT "World":
# it is 94% of a default message and pushes 42's unchecked 16 KB TX buffer to
# 86% full with a single body -- see NOTES_ON_42_IPC.md §2.
DEFAULT_PREFIXES = ('SC', 'SC[0].AC')

DEFAULT_PORT = 10001

# How often the worker re-checks for a stop request while it is blocked
# waiting -- both for 42 to connect and for permission to ack.  It bounds the
# worst-case shutdown latency, so it is the number Ipc42Panel.stop_listening()
# sizes its wait against.
ACCEPT_POLL = 0.1

# Socket errors that mean "the peer went away".  42 exiting is a normal end of
# run, not a failure worth putting in front of the user -- and it does not
# always arrive as a clean EOF: if 42 closes with data still unread the kernel
# sends RST, so the same event surfaces as ECONNRESET on a read or EPIPE on
# the ack, depending purely on timing.  EBADF covers our own close() racing
# the loop during shutdown.
_DISCONNECT_ERRNOS = frozenset([errno.ECONNRESET, errno.EPIPE,
                                errno.ENOTCONN, errno.ESHUTDOWN,
                                errno.EBADF])

# How often a free-running stream is reported to the gui, in Hz.
#
# 42 outruns any gui by orders of magnitude: measured against the stock demo
# on loopback, it produces ~2000 messages/second.  Emitting every one does
# **not** throttle it, which is the trap -- a cross-thread emit only posts an
# event and returns, so the ack goes out whether or not the gui ever gets
# round to the message, and the undelivered ones pile up in Qt's event queue
# without bound.  Measured: 6426 acks against 787 deliveries in 3 s, i.e.
# 5639 messages accumulated, and climbing.
#
# (The synchronous `Listener42.messages()` generator does not have this
# problem -- there the ack genuinely cannot happen until the consumer asks
# for the next message.  The property is lost precisely at the thread
# boundary, so it is worth not assuming it carries over.)
#
# 20 Hz is well past what anyone can read and keeps memory flat.
DISPLAY_HZ = 20


class Ipc42Worker(QObject):
    """Owns the 42 socket and runs its blocking loop off the GUI thread.

    Signals are the only way state leaves this object.  All of them are
    pyqtSignal so Qt marshals them to whatever thread the receiver lives in.

    **`message` is a display feed, not a lossless one.**  While free-running
    it is rate-limited to `display_hz` (see DISPLAY_HZ for why); every message
    is still read and acked, so 42 runs at full speed and `n_messages` is the
    true step count.  While paused or stepping *every* message is emitted --
    that is when each individual step is the thing being looked at.

    A consumer that needs every message must not take it from this signal.
    Give it `display_hz=None` and accept that it must keep up, or drive
    `Listener42` directly, where the ack is genuinely gated on the consumer.
    """

    # peer address, e.g. "('127.0.0.1', 34928)"
    connected = pyqtSignal(str)
    # a parsed ipc42.Message42; `object` because it is not a Qt type
    message = pyqtSignal(object)
    disconnected = pyqtSignal()
    # human-readable failure; the worker stops after emitting it
    failed = pyqtSignal(str)
    # True while free-running, False while paused
    running_changed = pyqtSignal(bool)

    def __init__(self, port=DEFAULT_PORT, start_paused=False,
                 display_hz=DISPLAY_HZ, parent=None):
        """
        Keyword Args:
            display_hz (float):  cap on `message` emissions per second while
                free-running; None emits every message (see the class
                docstring for what that costs)
        """
        super().__init__(parent)
        self.port = port
        self._listener = None
        self._stopping = threading.Event()
        # set -> free-running; clear -> paused (42 blocks on its ack)
        self._running = threading.Event()
        if not start_paused:
            self._running.set()
        # one permit per single-step request
        self._step_permits = threading.Semaphore(0)
        self._emit_interval = (1.0 / display_hz) if display_hz else 0.0
        self._last_emit = 0.0
        # total messages read and acked -- the true step count, which the
        # rate-limited `message` signal does not convey on its own
        self.n_messages = 0
        # most recent message, whether or not it was emitted
        self.latest = None

    # ---------------------------------------------------------- control
    # These are called from the GUI thread.  threading primitives are used
    # rather than Qt ones because the waiting side is a plain blocking loop,
    # not an event loop.

    def set_running(self, running):
        if running:
            self._running.set()
        else:
            self._running.clear()
        self.running_changed.emit(bool(running))

    def step(self, n=1):
        """Permit `n` further messages, then pause again."""
        self._running.clear()
        for _ in range(max(1, int(n))):
            self._step_permits.release()
        self.running_changed.emit(False)

    def stop(self):
        self._stopping.set()
        self._running.set()          # unblock the gate so the loop can exit
        self._step_permits.release()
        listener = self._listener
        if listener is not None:
            listener.close()

    # ---------------------------------------------------------- the loop

    def _await_permission(self):
        """Block until acking is permitted, or the worker is stopping.

        Returns False if we are stopping and should not ack.
        """
        while not self._stopping.is_set():
            if self._running.is_set():
                return True
            # short timeout so a stop request is noticed promptly
            if self._step_permits.acquire(timeout=ACCEPT_POLL):
                return True
        return False

    def _should_emit(self):
        """Whether to report this message to the gui.

        Every message while paused or stepping -- there each step is the
        thing being looked at, and there are few of them.  While free-running
        the gui cannot use more than `display_hz` of them and accumulates the
        rest, so the surplus is dropped from the *display* only; it is still
        read and acked, and `n_messages` still counts it.
        """
        if not self._running.is_set() or self._emit_interval <= 0:
            return True
        now = time.monotonic()
        if now - self._last_emit >= self._emit_interval:
            self._last_emit = now
            return True
        return False

    def _accept(self):
        """Wait for 42 to dial in, returning None if stopped first.

        Polls rather than blocking because closing a listening socket from
        another thread does not reliably interrupt accept() on Linux -- the
        thread can sit there forever and Qt aborts the process when a
        still-running QThread is destroyed.  ACCEPT_POLL bounds how long a
        stop request waits; reads, once connected, still block indefinitely,
        since a simulation step may take as long as it takes.
        """
        while not self._stopping.is_set():
            try:
                return self._listener.accept()
            except socket.timeout:
                continue
        return None

    def run(self):
        """Entry point for the thread.  Blocks until stopped or 42 exits."""
        try:
            if self._stopping.is_set():
                return
            self._listener = Listener42(port=self.port, timeout=None,
                                        accept_timeout=ACCEPT_POLL)
            self._listener.open()
            peer = self._accept()
            if peer is None:            # stopped before 42 ever connected
                return
            self.connected.emit(str(peer))
            while not self._stopping.is_set():
                text = self._listener.read_message()
                if text is None:
                    break
                msg = parse_message(text)
                self.n_messages += 1
                self.latest = msg
                if self._should_emit():
                    self.message.emit(msg)
                # ack AFTER reporting: while paused, 42 stays blocked here,
                # which is precisely the pause mechanism
                if not self._await_permission():
                    break
                self._listener.send_ack()
        except OSError as e:
            # a peer that went away is a disconnect, not a failure; the
            # `finally` below reports it as one
            if (not self._stopping.is_set()
                    and e.errno not in _DISCONNECT_ERRNOS):
                self.failed.emit(f'{type(e).__name__}: {e}')
        except Exception as e:              # noqa: BLE001 - reported, not hidden
            orb.log.error(f'* ipc42 worker failed: {type(e).__name__}: {e}')
            if not self._stopping.is_set():
                self.failed.emit(f'{type(e).__name__}: {e}')
        finally:
            if self._listener is not None:
                self._listener.close()
            self.disconnected.emit()


class Ipc42Panel(QWidget):
    """Minimal monitor and pacing control for a connected 42.

    Shows the simulation clock and a few state variables, and offers
    Run / Pause / Step.  It is a monitor, not a commander: 42's IPC accepts
    state, not commands, so there is nothing here that tells 42 *what to do*
    -- only how fast to do it.

    NOTE: the panel deliberately does **not** re-emit the message stream.
    Chaining `worker.message` -> `on_message` -> a panel signal would add a
    hop with no consumers; anything that wants the raw stream should connect
    to `panel.worker.message` directly, which is also the more specific
    signal.
    """

    def __init__(self, port=DEFAULT_PORT, watch=None, parent=None):
        """
        Keyword Args:
            port (int):  port to listen on (42 dials out to it)
            watch (list of str):  variable names to display; defaults to a
                small attitude/rate set
        """
        super().__init__(parent)
        self.port = port
        self.watch = list(watch or ['SC[0].qn', 'SC[0].wn', 'SC[0].PosR'])
        self.thread = None
        self.worker = None

        self.status = QLabel('not listening')
        self.status.setStyleSheet('font-weight: bold')
        self.clock = QLabel('--')
        self.counter = QLabel('0')

        self.listen_button = QPushButton('Listen')
        self.run_button = QPushButton('Run')
        self.pause_button = QPushButton('Pause')
        self.step_button = QPushButton('Step')
        self.step_count = QSpinBox()
        self.step_count.setRange(1, 1000)
        self.step_count.setValue(1)
        self.stop_button = QPushButton('Stop')

        self.listen_button.clicked.connect(self.start_listening)
        self.run_button.clicked.connect(lambda: self._set_running(True))
        self.pause_button.clicked.connect(lambda: self._set_running(False))
        self.step_button.clicked.connect(self._on_step)
        self.stop_button.clicked.connect(self.stop_listening)

        controls = QHBoxLayout()
        for w in (self.listen_button, self.run_button, self.pause_button,
                  self.step_button, self.step_count, self.stop_button):
            controls.addWidget(w)
        controls.addStretch(1)

        info = QGridLayout()
        info.addWidget(QLabel('Status:'), 0, 0)
        info.addWidget(self.status, 0, 1)
        info.addWidget(QLabel('Sim time:'), 1, 0)
        info.addWidget(self.clock, 1, 1)
        info.addWidget(QLabel('Messages:'), 2, 0)
        info.addWidget(self.counter, 2, 1)

        self.value_labels = {}
        values_box = QGroupBox('State')
        values_layout = QGridLayout()
        for row, name in enumerate(self.watch):
            values_layout.addWidget(QLabel(name), row, 0)
            lbl = QLabel('--')
            lbl.setTextInteractionFlags(lbl.textInteractionFlags())
            self.value_labels[name] = lbl
            values_layout.addWidget(lbl, row, 1)
        values_box.setLayout(values_layout)

        layout = QVBoxLayout()
        layout.addLayout(controls)
        layout.addLayout(info)
        layout.addWidget(values_box)
        layout.addStretch(1)
        self.setLayout(layout)
        self._update_buttons(listening=False)

    # ---------------------------------------------------------- lifecycle

    def start_listening(self, start_paused=False):
        if self.thread is not None:
            return
        self.worker = Ipc42Worker(port=self.port, start_paused=start_paused)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.connected.connect(self.on_connected)
        self.worker.message.connect(self.on_message)
        self.worker.disconnected.connect(self.on_disconnected)
        self.worker.failed.connect(self.on_failed)
        self.thread.start()
        self.counter.setText('0')
        self.clock.setText('--')
        for lbl in self.value_labels.values():
            lbl.setText('--')
        self.status.setText(f'listening on port {self.port} ...')
        self._update_buttons(listening=True)

    def stop_listening(self):
        if self.worker is not None:
            self.worker.stop()
        if self.thread is not None:
            self.thread.quit()
            # bounded: the worker's gate wakes within 100 ms of a stop
            self.thread.wait(3000)
            self.thread = None
            self.worker = None
        self.status.setText('not listening')
        self._update_buttons(listening=False)

    def closeEvent(self, event):
        self.stop_listening()
        super().closeEvent(event)

    # ---------------------------------------------------------- slots
    # These run on the GUI thread because Qt marshals the worker's signals.

    def on_connected(self, peer):
        self.status.setText(f'42 connected from {peer}')

    def on_message(self, msg):
        if self.worker is None:
            # a queued message can still arrive after stop_listening() has
            # dropped the worker: Qt delivers what was already posted
            return
        # the true step count, not the number of messages displayed: while
        # free-running the worker deliberately reports only DISPLAY_HZ of
        # them, so counting arrivals here would understate what 42 has done
        self.counter.setText(str(self.worker.n_messages))
        if msg.time is not None:
            self.clock.setText(
                f'{msg.time.year}-{msg.time.doy:03d} '
                f'{msg.time.hour:02d}:{msg.time.minute:02d}:'
                f'{msg.time.second:09.6f}')
        for name, lbl in self.value_labels.items():
            value = msg.values.get(name)
            if value is None:
                continue
            if isinstance(value, list):
                lbl.setText('  '.join(f'{v: .6e}' for v in value))
            else:
                lbl.setText(str(value))

    def on_disconnected(self):
        self.status.setText('42 disconnected')
        self._update_buttons(listening=False)

    def on_failed(self, text):
        self.status.setText(f'error: {text}')
        orb.log.error(f'* ipc42 panel: {text}')
        self._update_buttons(listening=False)

    # ---------------------------------------------------------- helpers

    def _set_running(self, running):
        if self.worker is not None:
            self.worker.set_running(running)
        self.run_button.setEnabled(not running)
        self.pause_button.setEnabled(running)

    def _on_step(self):
        if self.worker is not None:
            self.worker.step(self.step_count.value())
        self.run_button.setEnabled(True)
        self.pause_button.setEnabled(False)

    def _update_buttons(self, listening):
        self.listen_button.setEnabled(not listening)
        for w in (self.run_button, self.pause_button, self.step_button,
                  self.step_count, self.stop_button):
            w.setEnabled(listening)
        if listening:
            self.run_button.setEnabled(False)   # already running
