# -*- coding: utf-8 -*-
"""
Shared pytest fixtures for the pangalactic.node gui tests.

These tests use pytest-qt, which supplies the "qtbot" fixture:  it creates the
QApplication, drives real mouse/keyboard events, and cleans widgets up
afterwards.  Run them headless with:

    QT_QPA_PLATFORM=offscreen pytest pangalactic/node/test

NOTE: gui tests are only worth writing for behaviour that actually needs a
widget.  Controller logic in pangalaxian is reachable through the dispatcher
without any gui at all, and is much cheaper to test that way.
"""
import os
import shutil
import tempfile

import pytest

# set the orb -- must precede any pangalactic.core import that pulls in "orb"
import pangalactic.core.set_uberorb

from pangalactic.core import orb, config
from pangalactic.core.serializers import deserialize
from pangalactic.core.test.utils import create_test_users, create_test_project


@pytest.fixture(scope='session')
def test_orb():
    """
    Start the orb once per session, on a scratch home with the standard test
    data loaded.

    NOTE: the home directory is created first, deliberately -- orb.start() with
    a home that does not exist writes the reference db *as a file* at that path
    and then raises.
    """
    root = tempfile.mkdtemp(prefix='node_gui_test_')
    home = os.path.join(root, 'home')
    os.makedirs(home)
    orb.start(home=home, debug=False, console=False)
    deserialize(orb, create_test_users())
    deserialize(orb, create_test_project())
    yield orb
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def no_ldap():
    """
    Remove "ldap_schema" from config for the duration of a test.

    This is the configuration an installation without an LDAP directory has,
    and the one in which the admin tool used to be unusable:  AddPersonDialog
    built its form from config['ldap_schema'] and raised TypeError when it was
    absent.  Most gui tests here should run in this state, because it is the
    one that was broken.
    """
    saved = config.pop('ldap_schema', None)
    yield
    if saved is not None:
        config['ldap_schema'] = saved


class DispatcherSpy:
    """
    Record pydispatcher signals so a test can assert what was sent, and how
    many times.

    NOTE: this exists because pydispatcher holds receivers **weakly** -- a
    bare function or lambda connected inline is garbage collected immediately
    and never fires, which silently turns "nothing was sent" into a passing
    test.  Holding the receiver on an instance keeps it alive.

    The count matters as much as the fact:  the bug that prompted these tests
    was a change that made a deletion reach the repository *twice*, which an
    "it happened" assertion would not have caught.
    """
    def __init__(self, signal):
        self.signal = signal
        self.calls = []
        from pydispatch import dispatcher
        dispatcher.connect(self.receive, signal)

    def receive(self, *args, **kw):
        self.calls.append(kw)

    @property
    def count(self):
        return len(self.calls)

    def disconnect(self):
        from pydispatch import dispatcher
        try:
            dispatcher.disconnect(self.receive, self.signal)
        except Exception:
            pass


@pytest.fixture
def spy():
    """
    Factory for DispatcherSpy, disconnected at the end of the test.
    """
    spies = []

    def _make(signal):
        s = DispatcherSpy(signal)
        spies.append(s)
        return s

    yield _make
    for s in spies:
        s.disconnect()
