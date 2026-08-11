# -*- coding: utf-8 -*-
"""
Tests for the Qt front end of the 42 IPC link (`pangalactic.node.ipc42_gui`).

A `Fake42` stands in for the simulator: it dials out exactly as 42 does
(Socket Role CLIENT), sends captured messages, and — crucially — **waits for
the 4-byte ack**. That last part is what makes the pacing behaviour testable:
"paused" is observable precisely as "no ack arrived", which is the same thing
42 itself would experience as a stalled `read(Socket, Ack, 4)`.

Two properties are worth more than the rest:

* the worker's signals are delivered on the **GUI thread** (test 02) — this is
  the pydispatcher/pyqtSignal boundary from `pydispatcher_migration.md` §1,
  and this module is the first new code that depends on it;
* acking happens **after** the message is reported (tests 04-06), which is
  what makes run/pause/step possible without any change to 42.
"""
import os
import socket
import struct
import threading

import pytest

from PyQt5.QtCore import QThread

from pangalactic.node.ipc42 import ACK
from pangalactic.node.ipc42_gui import Ipc42Panel, Ipc42Worker

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURE = os.path.join(HERE, 'data', '42_ipc_message.txt')


@pytest.fixture(autouse=True)
def _orb(test_orb):
    """Start the orb for every test in this module.

    The orb cannot be used without `orb.start()` -- that is by design, not an
    accident -- and `ipc42_gui` logs through `orb.log` on its error paths.
    Without this the error path raises AttributeError inside the Qt event
    loop, replacing a real diagnosis with a bogus one.
    """


@pytest.fixture(scope='module')
def captured():
    with open(CAPTURE) as f:
        return f.read()


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Fake42:
    """A stand-in for 42: dials out, sends messages, waits for acks."""

    def __init__(self, port):
        self.port = port
        self.sock = None

    def connect(self, timeout=5.0):
        deadline = threading.Event()
        last = None
        for _ in range(int(timeout / 0.05)):
            try:
                self.sock = socket.create_connection(('127.0.0.1', self.port),
                                                     timeout=timeout)
                return self
            except OSError as e:            # listener not up yet
                last = e
                deadline.wait(0.05)
        raise AssertionError(f'could not connect to worker: {last}')

    def send(self, text):
        self.sock.sendall(text.encode())

    def wait_ack(self, timeout=2.0):
        """Return True if the 4-byte ack arrived within `timeout`."""
        self.sock.settimeout(timeout)
        try:
            data = self.sock.recv(len(ACK))
        except (socket.timeout, TimeoutError):
            return False
        return data == ACK

    def close(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None

    def abort(self):
        """Close hard, forcing an RST rather than a clean FIN.

        SO_LINGER with a zero timeout is the reliable way to reproduce what a
        peer does when it exits with data still unread -- which is what 42
        does often enough that it showed up as an intermittent test failure
        before the worker classified it as a disconnect.
        """
        if self.sock is not None:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                                 struct.pack('ii', 1, 0))
            self.sock.close()
            self.sock = None


@pytest.fixture
def worker_on_thread(qtbot):
    """An Ipc42Worker running on its own QThread, torn down after the test."""
    made = {}

    def _make(start_paused=False):
        port = _free_port()
        worker = Ipc42Worker(port=port, start_paused=start_paused)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        thread.start()
        made.update(worker=worker, thread=thread, port=port)
        return worker, port

    yield _make

    worker, thread = made.get('worker'), made.get('thread')
    if worker is not None:
        worker.stop()
    if thread is not None:
        thread.quit()
        assert thread.wait(5000), 'worker thread did not exit'


# ------------------------------------------------------------------ basics

def test_01_worker_reports_a_connection(qtbot, worker_on_thread):
    """CASE: 42 dialling in produces a `connected` signal"""
    worker, port = worker_on_thread()
    fake = Fake42(port)
    try:
        with qtbot.waitSignal(worker.connected, timeout=5000) as sig:
            fake.connect()
        assert '127.0.0.1' in sig.args[0]
    finally:
        fake.close()


def test_02_message_signal_arrives_on_the_gui_thread(qtbot, worker_on_thread,
                                                     captured):
    """CASE: the worker's signal is marshalled to the GUI thread

    This is the property the whole design rests on.  pydispatcher would have
    run the receiver on the worker thread, where touching widgets is
    undefined; Qt marshals it.  Asserting on thread identity rather than
    trusting the docs.
    """
    worker, port = worker_on_thread()
    main_thread = threading.current_thread().ident
    seen = {}

    def on_message(msg):
        seen['thread'] = threading.current_thread().ident
        seen['values'] = len(msg.values)

    worker.message.connect(on_message)
    fake = Fake42(port)
    try:
        fake.connect()
        with qtbot.waitSignal(worker.message, timeout=5000):
            fake.send(captured)
        assert seen['values'] == 176
        assert seen['thread'] == main_thread, (
            'message slot ran on a worker thread, not the GUI thread')
    finally:
        fake.close()


def test_03_parses_successive_messages(qtbot, worker_on_thread, captured):
    """CASE: several steps in a row"""
    worker, port = worker_on_thread()
    got = []
    worker.message.connect(lambda m: got.append(m))
    fake = Fake42(port)
    try:
        fake.connect()
        for _ in range(3):
            with qtbot.waitSignal(worker.message, timeout=5000):
                fake.send(captured)
            assert fake.wait_ack(), 'no ack while running'
        assert len(got) == 3
        assert all(m.time is not None for m in got)
    finally:
        fake.close()


# ----------------------------------------------------------- ack policy

def test_04_running_acks_each_message(qtbot, worker_on_thread, captured):
    """CASE: free-running -- every message is acked, so 42 keeps going"""
    worker, port = worker_on_thread()
    fake = Fake42(port)
    try:
        fake.connect()
        with qtbot.waitSignal(worker.message, timeout=5000):
            fake.send(captured)
        assert fake.wait_ack() is True
    finally:
        fake.close()


def test_05_paused_withholds_the_ack(qtbot, worker_on_thread, captured):
    """CASE: paused -- the message is reported but NOT acked

    42 would be sitting in read(Socket, Ack, 4) at this point.  That is the
    pause: no command is sent to 42 and 42 needs no support for it.
    """
    worker, port = worker_on_thread(start_paused=True)
    fake = Fake42(port)
    try:
        fake.connect()
        with qtbot.waitSignal(worker.message, timeout=5000):
            fake.send(captured)
        # reported to the GUI, but deliberately not acknowledged
        assert fake.wait_ack(timeout=0.7) is False, (
            'acked while paused -- 42 would not have stopped')
        # resuming releases it
        worker.set_running(True)
        assert fake.wait_ack(timeout=3.0) is True
    finally:
        fake.close()


def test_06_step_releases_exactly_one_message(qtbot, worker_on_thread,
                                              captured):
    """CASE: single-step -- one ack, then paused again"""
    worker, port = worker_on_thread(start_paused=True)
    fake = Fake42(port)
    try:
        fake.connect()
        with qtbot.waitSignal(worker.message, timeout=5000):
            fake.send(captured)
        assert fake.wait_ack(timeout=0.5) is False

        worker.step()                       # permit exactly one
        assert fake.wait_ack(timeout=3.0) is True

        # the next message must again be held
        with qtbot.waitSignal(worker.message, timeout=5000):
            fake.send(captured)
        assert fake.wait_ack(timeout=0.7) is False, (
            'step permitted more than one message')
    finally:
        fake.close()


def test_07_step_n_releases_n_messages(qtbot, worker_on_thread, captured):
    """CASE: step(3) advances three steps and then holds"""
    worker, port = worker_on_thread(start_paused=True)
    fake = Fake42(port)
    try:
        fake.connect()
        worker.step(3)
        for i in range(3):
            with qtbot.waitSignal(worker.message, timeout=5000):
                fake.send(captured)
            assert fake.wait_ack(timeout=3.0) is True, f'no ack for step {i}'
        with qtbot.waitSignal(worker.message, timeout=5000):
            fake.send(captured)
        assert fake.wait_ack(timeout=0.7) is False
    finally:
        fake.close()


# ------------------------------------------------------------- lifecycle

def test_08_disconnect_is_reported(qtbot, worker_on_thread, captured):
    """CASE: 42 exiting closes the socket and the worker notices"""
    worker, port = worker_on_thread()
    fake = Fake42(port)
    fake.connect()
    with qtbot.waitSignal(worker.disconnected, timeout=5000):
        fake.close()


def test_09_stop_unblocks_a_paused_worker(qtbot, worker_on_thread, captured):
    """CASE: stopping while paused must not hang

    The worker is sitting in its permission gate with 42 waiting on an ack.
    stop() has to wake it, or the thread never exits -- which is why the gate
    waits with a timeout rather than blocking forever.
    """
    worker, port = worker_on_thread(start_paused=True)
    fake = Fake42(port)
    try:
        fake.connect()
        with qtbot.waitSignal(worker.message, timeout=5000):
            fake.send(captured)
        with qtbot.waitSignal(worker.disconnected, timeout=5000):
            worker.stop()
    finally:
        fake.close()


def test_09a_abrupt_close_is_a_disconnect_not_a_failure(qtbot,
                                                        worker_on_thread,
                                                        captured):
    """CASE: an RST from 42 reports `disconnected`, never `failed`

    42 exiting is a normal end of run, but it does not always arrive as a
    clean EOF -- closing with data still unread sends RST, which surfaces as
    ECONNRESET on a read or EPIPE on the ack depending purely on timing.
    Reporting that as an error put a spurious "error: ConnectionResetError"
    in front of the user whenever the race went the wrong way.
    """
    worker, port = worker_on_thread()
    failures = []
    worker.failed.connect(lambda t: failures.append(t))
    fake = Fake42(port)
    fake.connect()
    with qtbot.waitSignal(worker.message, timeout=5000):
        fake.send(captured)
    with qtbot.waitSignal(worker.disconnected, timeout=5000):
        fake.abort()
    assert failures == [], f'42 going away was reported as a failure: {failures}'


# ----------------------------------------------------------------- panel

def test_10_panel_shows_a_message(qtbot, captured):
    """CASE: the panel updates its clock, counter and watched values"""
    port = _free_port()
    panel = Ipc42Panel(port=port, watch=['SC[0].qn', 'SC[0].wn'])
    qtbot.addWidget(panel)
    panel.start_listening()
    fake = Fake42(port)
    try:
        fake.connect()
        # the panel deliberately does not re-emit the stream, so wait on the
        # worker's own signal -- the more specific one, and the one anything
        # wanting the raw stream would connect to
        with qtbot.waitSignal(panel.worker.message, timeout=5000):
            fake.send(captured)
        assert panel.counter.text() == '1'
        assert '2024-099' in panel.clock.text()
        assert panel.value_labels['SC[0].qn'].text() != '--'
        assert 'e' in panel.value_labels['SC[0].wn'].text()
    finally:
        fake.close()
        panel.stop_listening()


def test_11_panel_stop_is_idempotent_and_leaves_no_thread(qtbot):
    """CASE: stopping twice, and stopping without a connection, are safe"""
    port = _free_port()
    panel = Ipc42Panel(port=port)
    qtbot.addWidget(panel)
    panel.start_listening()
    panel.stop_listening()
    panel.stop_listening()
    assert panel.thread is None
    assert panel.worker is None
