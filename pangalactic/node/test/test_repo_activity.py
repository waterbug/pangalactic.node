# -*- coding: utf-8 -*-
"""
Tests for the repository activity indicator.

A STEP import finishes locally and then hands its objects to vger.save(),
which runs on the server and answers later.  Without something on screen the
client looks finished while the import is still going.  These cover the
lifecycle of that indicator -- shown when the wait starts, taken down when
the repository has answered for everything, and not left hanging when some of
it is refused or the rpc fails.

The controller logic is reachable without building a Main window, which would
need a bus, a reactor and a login;  these drive the handlers directly, which
is what conftest recommends for anything that does not actually need a
widget.

Run headless with QT_QPA_PLATFORM=offscreen.
"""
import pytest

# set the orb -- must precede any pangalactic.core import that pulls in "orb"
import pangalactic.core.set_uberorb

from PyQt5.QtWidgets import QWidget

from pangalactic.core import state

from pangalactic.node.pangalaxian import Main


class FakeMain(QWidget):
    """
    Just enough of Main to exercise the indicator.

    The handlers under test touch only the attributes set here, plus the
    dialog they create, so binding them to this stands in for a window
    without needing a bus, a reactor or a login.  It is a real QWidget
    because the dialog is parented to it.
    """
    REPO_ACTIVITY_TIMEOUT = Main.REPO_ACTIVITY_TIMEOUT
    on_repo_save_pending = Main.on_repo_save_pending
    repo_save_returned = Main.repo_save_returned
    close_repo_activity = Main.close_repo_activity
    on_repo_activity_timeout = Main.on_repo_activity_timeout

    def __init__(self):
        super().__init__()
        self.repo_pending_oids = set()
        self.repo_activity_dlg = None
        self.messages = []
        self.statusbar = self

    def showMessage(self, msg, timeout=0):
        self.messages.append(msg)


@pytest.fixture
def main(qtbot, monkeypatch, test_orb):
    """
    A stand-in Main, with the dialog it builds registered for cleanup and
    the deferred status-bar message made immediate so it can be asserted on.

    test_orb is wanted only for orb.log, which the timeout path writes to
    and which does not exist until the orb is started.
    """
    from pangalactic.node import pangalaxian
    monkeypatch.setattr(pangalaxian.QTimer, 'singleShot',
                        staticmethod(lambda ms, fn: fn() if ms == 0 else None))
    m = FakeMain()
    qtbot.addWidget(m)
    saved = state.get('connected')
    state['connected'] = True
    yield m
    state['connected'] = saved
    if m.repo_activity_dlg is not None:
        m.repo_activity_dlg.close()


def test_01_indicator_appears_while_the_server_works(main):
    """
    CASE:  objects are handed to the repository.  The indicator is shown and
    the oids are recorded as outstanding.
    """
    main.on_repo_save_pending(oids=['a', 'b'], msg='sending 2 items ...')
    assert main.repo_activity_dlg is not None
    assert main.repo_activity_dlg.isVisible()
    assert main.repo_pending_oids == {'a', 'b'}
    # indeterminate: there is no way to know how far the server has got
    assert main.repo_activity_dlg.minimum() == 0
    assert main.repo_activity_dlg.maximum() == 0


def test_02_partial_answer_keeps_waiting(main):
    """
    CASE:  the repository answers for some of the objects.  The indicator
    stays up -- the rest are still outstanding.
    """
    main.on_repo_save_pending(oids=['a', 'b'], msg='...')
    main.repo_save_returned(['a'])
    assert main.repo_pending_oids == {'b'}
    assert main.repo_activity_dlg is not None


def test_03_full_answer_takes_it_down(main):
    """
    CASE:  the repository has answered for everything.  The indicator goes,
    and the user is told the save completed.
    """
    main.on_repo_save_pending(oids=['a', 'b'], msg='...')
    main.repo_save_returned(['a', 'b'])
    assert main.repo_pending_oids == set()
    assert main.repo_activity_dlg is None
    assert any('saved to the repository' in m for m in main.messages)


def test_04_unrelated_oids_do_not_dismiss_it(main):
    """
    CASE:  a save the indicator is not waiting on answers first.

    on_vger_save_result runs for every save the client makes, so an
    indicator that counted rpcs instead of naming oids would be dismissed by
    somebody else's save.  This is why the wait is pinned to oids.
    """
    main.on_repo_save_pending(oids=['a', 'b'], msg='...')
    main.repo_save_returned(['something-else'])
    assert main.repo_pending_oids == {'a', 'b'}
    assert main.repo_activity_dlg is not None


def test_05_refused_objects_stop_the_wait(main):
    """
    CASE:  the repository refuses part of the batch.  A refusal is an answer
    -- nothing more is coming for those -- so the indicator must not hang on
    them until the timeout.
    """
    main.on_repo_save_pending(oids=['a', 'b'], msg='...')
    # this is what on_vger_save_result passes: saved + refused
    main.repo_save_returned(['a', 'b'])
    assert main.repo_activity_dlg is None


def test_06_nothing_shown_while_disconnected(main):
    """
    CASE:  disconnected.  Nothing is pending on a server we are not talking
    to;  the objects are saved locally and go up at the next sync, so an
    indicator would be waiting for something that was never sent.
    """
    state['connected'] = False
    main.on_repo_save_pending(oids=['a'], msg='...')
    assert main.repo_activity_dlg is None
    assert main.repo_pending_oids == set()


def test_07_no_oids_shows_nothing(main):
    """
    CASE:  an import that produced no objects.  Nothing to wait for.
    """
    main.on_repo_save_pending(oids=[], msg='...')
    assert main.repo_activity_dlg is None


def test_08_timeout_gives_up_and_says_so(main):
    """
    CASE:  the server never answers.  The indicator is modeless, but one that
    never goes away is still wrong, so it gives up and leaves a message
    saying the items will sync later.
    """
    main.on_repo_save_pending(oids=['a'], msg='...')
    main.on_repo_activity_timeout()
    assert main.repo_activity_dlg is None
    assert main.repo_pending_oids == set()
    assert any('next login' in m for m in main.messages)


def test_09_timeout_after_completion_does_nothing(main):
    """
    CASE:  the save completed well before the timeout fires -- which it
    always will, since the timer is armed unconditionally.  The late timer
    must not put up a message about a wait that ended normally.
    """
    main.on_repo_save_pending(oids=['a'], msg='...')
    main.repo_save_returned(['a'])
    main.messages.clear()
    main.on_repo_activity_timeout()
    assert main.messages == []


def test_10_a_second_batch_joins_the_same_wait(main):
    """
    CASE:  an import sends "new objects" and "modified objects" separately,
    so two saves can be outstanding at once.  Both are waited for by the one
    indicator, and it goes down when the last of them answers.
    """
    main.on_repo_save_pending(oids=['a'], msg='...')
    first = main.repo_activity_dlg
    main.on_repo_save_pending(oids=['b'], msg='...')
    assert main.repo_activity_dlg is first
    assert main.repo_pending_oids == {'a', 'b'}
    main.repo_save_returned(['a'])
    assert main.repo_activity_dlg is first
    main.repo_save_returned(['b'])
    assert main.repo_activity_dlg is None
