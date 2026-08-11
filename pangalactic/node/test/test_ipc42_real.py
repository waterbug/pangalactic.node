# -*- coding: utf-8 -*-
"""
Drive `Ipc42Panel` against a **real running 42**, if one is installed.

Skipped unless `42` is on PATH, so an ordinary test run is unaffected.  With
the conda package installed (`conda install 42`), it runs in about ten
seconds.

The Fake42 in `test_ipc42_gui.py` proves the protocol and the ack policy.  It
cannot prove the thing that actually matters here: that withholding the ack
stalls the **simulation**, not merely the socket.  42's own clock is the
witness -- if pausing works, the sim time stops advancing because 42 is parked
in `read(Socket, Ack, 4)`, and no amount of waiting produces another step.

That is also the test that caught the display-rate defect.  Fake42 sends
messages when told to; real 42 produces them at ~1600/s, which is what
revealed that a cross-thread `emit()` does not throttle anything and the
undelivered messages accumulate in Qt's event queue without bound.
"""
import os
import shutil
import subprocess
import time

import pytest

from pangalactic.node.ipc42_gui import Ipc42Panel

FORTY_TWO = shutil.which('42')

pytestmark = pytest.mark.skipif(
    FORTY_TWO is None, reason='42 is not installed (conda install 42)')

# 42 reads InOut/ from its working directory and finds Model/ and World/
# alongside it; the conda package puts them all under share/42.
SHARE = (os.path.join(os.path.dirname(os.path.dirname(FORTY_TWO or '')),
                      'share', '42'))


@pytest.fixture
def run42(tmp_path):
    """A scratch 42 run directory: headless, TX on one socket, port assigned.

    Configured with the "SC" prefix only rather than 42's shipped
    SC/Orb/World.  That is our own advice from NOTES_ON_42_IPC.md section 2 --
    World is 94% of a default message and pushes 42's unchecked 16 KB TX
    buffer to 86% full with a single body.
    """
    if not os.path.isdir(SHARE):
        pytest.skip(f'42 support files not found at {SHARE}')
    d = tmp_path / 'run42'
    d.mkdir()
    shutil.copytree(os.path.join(SHARE, 'InOut'), d / 'InOut')
    for sub in ('Model', 'World', 'Kit'):
        src = os.path.join(SHARE, sub)
        if os.path.isdir(src):
            os.symlink(src, d / sub)

    sim = d / 'InOut' / 'Inp_Sim.txt'
    sim.write_text(sim.read_text().replace(
        'TRUE                            !  Graphics Front End?',
        'FALSE                           !  Graphics Front End?'))

    # a free port, so a stray 42 or a parallel run cannot collide
    import socket
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()

    ipc = d / 'InOut' / 'Inp_IPC.txt'
    t = ipc.read_text()
    t = t.replace('0                                       ! Number of Sockets',
                  '1                                       ! Number of Sockets', 1)
    t = t.replace(
        'OFF                                     ! IPC Mode (OFF,TX,RX,TXRX,WRITEFILE,READFILE)',
        'TX                                      ! IPC Mode (OFF,TX,RX,TXRX,WRITEFILE,READFILE)',
        1)
    t = t.replace('localhost     10001', f'localhost     {port}', 1)
    t = t.replace('''3                                       ! Number of TX prefixes
"SC"                                    ! Prefix 0
"Orb"                                   ! Prefix 1
"World"                                 ! Prefix 2''',
                  '''1                                       ! Number of TX prefixes
"SC"                                    ! Prefix 0''', 1)
    ipc.write_text(t)
    return str(d), port


@pytest.fixture
def sim(qtbot, run42, test_orb):
    """A panel with a real 42 connected to it, both torn down afterwards."""
    path, port = run42
    panel = Ipc42Panel(port=port, watch=['SC[0].qn', 'SC[0].wn'])
    qtbot.addWidget(panel)
    panel.start_listening()
    qtbot.wait(200)                     # be listening before 42 dials out
    proc = subprocess.Popen([FORTY_TWO, 'InOut'], cwd=path,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    deadline = time.time() + 20
    while time.time() < deadline and '42 connected' not in panel.status.text():
        qtbot.wait(50)
    assert '42 connected' in panel.status.text(), (
        f'42 never connected: {panel.status.text()}')
    yield panel, proc
    panel.stop_listening()
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _steps(panel):
    return int(panel.counter.text())


def test_01_real_42_streams_to_the_panel(qtbot, sim):
    """CASE: a real 42 connects and its state reaches the widgets"""
    panel, _proc = sim
    qtbot.wait(1500)
    assert _steps(panel) > 5, f'only {_steps(panel)} steps'
    assert panel.clock.text() != '--'
    assert panel.value_labels['SC[0].qn'].text() != '--'


def test_02_pause_stalls_the_actual_simulation(qtbot, sim):
    """CASE: withholding the ack stops 42 itself, not just the socket

    The sim clock is the witness: 42 is parked in read(Socket, Ack, 4), so
    its time cannot advance no matter how long we wait.
    """
    panel, proc = sim
    qtbot.wait(1000)
    panel._set_running(False)
    qtbot.wait(400)                     # let the in-flight message land
    stalled_at, clock = _steps(panel), panel.clock.text()
    qtbot.wait(2000)
    assert _steps(panel) == stalled_at, (
        f'simulation kept running while paused: {stalled_at} -> '
        f'{_steps(panel)}')
    assert panel.clock.text() == clock, 'sim clock advanced while paused'
    assert proc.poll() is None, '42 exited rather than blocking'


def test_03_step_advances_one_simulation_step(qtbot, sim):
    """CASE: one step is exactly one step, of exactly the configured size

    Inp_Sim.txt ships a 0.1 s step, so the clock must move by 0.1 s -- a
    stronger assertion than "the counter went up", and it fails if the ack
    policy ever lets an extra step slip through.
    """
    panel, _proc = sim
    qtbot.wait(800)
    panel._set_running(False)
    qtbot.wait(400)
    before, clock_before = _steps(panel), panel.clock.text()

    panel.step_count.setValue(1)
    panel._on_step()
    qtbot.wait(1000)
    assert _steps(panel) == before + 1, (
        f'step advanced {_steps(panel) - before} steps, not 1')

    def seconds(text):                  # "2024-099 00:05:08.200000"
        h, m, s = text.split()[1].split(':')
        return int(h) * 3600 + int(m) * 60 + float(s)

    delta = seconds(panel.clock.text()) - seconds(clock_before)
    assert abs(delta - 0.1) < 1e-6, f'sim advanced {delta} s, expected 0.1'


def test_04_step_n_then_holds(qtbot, sim):
    """CASE: step(5) advances five and stops"""
    panel, _proc = sim
    qtbot.wait(800)
    panel._set_running(False)
    qtbot.wait(400)
    before = _steps(panel)
    panel.step_count.setValue(5)
    panel._on_step()
    qtbot.wait(1500)
    assert _steps(panel) == before + 5, (
        f'advanced {_steps(panel) - before} steps, not 5')
    held = _steps(panel)
    qtbot.wait(1200)
    assert _steps(panel) == held, 'did not hold after stepping'


def test_05_resume_restarts_the_simulation(qtbot, sim):
    """CASE: re-acking gets 42 going again"""
    panel, _proc = sim
    qtbot.wait(800)
    panel._set_running(False)
    qtbot.wait(400)
    paused_at = _steps(panel)
    panel._set_running(True)
    qtbot.wait(1500)
    assert _steps(panel) > paused_at + 10, (
        f'did not resume: {paused_at} -> {_steps(panel)}')


def test_06_display_is_capped_while_42_runs_flat_out(qtbot, sim):
    """CASE: 42 runs at full speed; the gui is fed at DISPLAY_HZ

    Real 42 produces ~1600 messages/s on loopback.  A cross-thread emit only
    posts an event and returns, so emitting every one would neither throttle
    42 nor reach the gui -- the surplus accumulated in Qt's event queue
    (measured: 6426 acked against 787 delivered in 3 s).  42 must still get
    every ack; only the reporting is capped.
    """
    from pangalactic.node.ipc42_gui import DISPLAY_HZ
    panel, _proc = sim
    shown = []
    panel.worker.message.connect(lambda m: shown.append(m))
    start_steps = _steps(panel)
    qtbot.wait(2000)
    stepped = _steps(panel) - start_steps

    assert stepped > 200, (
        f'42 was throttled by the gui: only {stepped} steps in 2 s')
    # allow generous slack for timer granularity and event-loop jitter
    assert len(shown) < DISPLAY_HZ * 2 * 3, (
        f'display not capped: {len(shown)} emissions in 2 s')
    assert len(shown) < stepped, 'every step was emitted'
