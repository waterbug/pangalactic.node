# -*- coding: utf-8 -*-
"""
Tests for the message bus channels a client subscribes to.

The repository publishes a cloaked object only on its owner's channel
(`vger.save()`, via `get_owner_id()`), so a client that is not subscribed to
a project's channel is never told about another user's work on that project.
Nothing fails and nothing is logged on the client:  the change simply never
appears, until the next login.

That is what happened on 2026-09-22 (reported by the author, and the second
time this symptom has been seen):  zaphod dropped a component onto a FireSat
subsystem, the repository recorded it and published

    + publishing 1 items on channel "FireSat"
      new object ids:
      - FireSat-PropSys-0001260-LatchValve-001

and the admin client, which was showing FireSat, never saw it.  Its own log
gave the reason -- of the fifteen channels it subscribed to at login,
`vger.channel.FireSat` was not one:

    channels we will subscribe to: ['vger.channel.MDL', 'vger.channel.566.0',
    ... 'vger.channel.H2G2', ... 'vger.channel.admin']

The channel set was computed once, at login, from the RoleAssignments that
happened to be in the local db at that moment -- and it is *usually* the
right set, which is why this is rare and why it comes back.  A user's own
roles arrive with `get_user_roles()`, and a project synced in any earlier
session leaves its RoleAssignments behind for every login after it.  H2G2
was in the list because it has a project administrator, whose RoleAssignment
the login sends to a global admin.  FireSat has none, admin holds no role in
it, and that client had never synced it before, so nothing put it in the set
-- its RoleAssignments arrived *with the project*, in the sync at 14:24,
after the subscriptions were made.

A client subscribes to a project's channel when it syncs that project, which
is what these tests hold it to.  Whose roles are in the local db is not the
point.

These borrow the real methods onto a stand-in `self`, the pattern used by
test_vault_file_upload.py:  a Main instance needs a QMainWindow and a message
bus, and neither is what is being tested.
"""
import pytest
from types import SimpleNamespace

from twisted.internet.defer import Deferred, succeed

# set the orb -- must precede any pangalactic.core import that pulls in "orb"
import pangalactic.core.set_uberorb

from pangalactic.core import orb, state

from pangalactic.node import pangalaxian
from pangalactic.node.pangalaxian import Main


class FakeSubscription(Deferred):
    """
    A subscription deferred.  crossbar's fires with a Subscription object
    carrying the topic; the client's callback logs `sub.topic`.
    """

    def __init__(self, topic):
        Deferred.__init__(self)
        self.topic = topic


class FakeSession:
    """
    Stands in for the WAMP session:  records what was subscribed to.

    `fail_on` names channels whose subscription is to fail, so the retry
    behaviour can be tested.
    """

    def __init__(self, fail_on=()):
        self.subscribed = []
        self.calls = []
        self.fail_on = set(fail_on)

    def subscribe(self, handler, channel):
        self.subscribed.append(channel)
        sub = FakeSubscription(channel)
        if channel in self.fail_on:
            sub.errback(RuntimeError(f'no such channel: {channel}'))
        else:
            sub.callback(sub)
        return sub

    def call(self, name, *args, **kw):
        self.calls.append((name, args, kw))
        return succeed(None)


class FakeClient:
    """A stand-in for Main carrying the real methods under test."""

    subscribe_to_mbus_channels = Main.subscribe_to_mbus_channels
    subscribe_to_project_channel = Main.subscribe_to_project_channel
    sync_current_project = Main.sync_current_project
    on_pubsub_success = Main.on_pubsub_success
    on_pubsub_failure = Main.on_pubsub_failure

    def __init__(self, fail_on=()):
        self.channels = []
        self.subscribed_channels = set()
        self.mbus = SimpleNamespace(session=FakeSession(fail_on=fail_on))
        self.statusbar = SimpleNamespace(showMessage=lambda msg: None)

    def on_pubsub_msg(self, msg):
        pass

    def set_bus_state(self):
        pass


@pytest.fixture
def client(test_orb):
    """A connected client, subscribed to nothing yet."""
    return FakeClient()


@pytest.fixture
def quiet_sync(monkeypatch):
    """
    Silence the two bits of gui that sync_current_project() drives.

    Neither is under test:  ProgressDialog needs a real QWidget parent, and
    processEvents needs a QApplication.
    """
    class FakeProgressDialog:
        def __init__(self, *args, **kw):
            pass

        def setMinimum(self, n):
            pass

        def setMaximum(self, n):
            pass

        def setMinimumDuration(self, n):
            pass

        def resize(self, w, h):
            pass

    monkeypatch.setattr(pangalaxian, 'ProgressDialog', FakeProgressDialog)
    monkeypatch.setattr(pangalaxian.QApplication, 'processEvents',
                        staticmethod(lambda *a, **kw: None))


def test_01_syncing_a_project_subscribes_to_its_channel(client, quiet_sync):
    """CASE: the regression -- sync a project, be on its channel

    A project synced in a session the login of which did not know about it.
    This is the FireSat case: nothing in the client's state says "FireSat"
    until the sync, and the sync is exactly when the client starts needing
    the channel.
    """
    state['project'] = 'H2G2'
    client.sync_current_project(None)
    assert 'vger.channel.H2G2' in client.mbus.session.subscribed


def test_02_subscribed_before_the_sync_rpc_is_issued(client, quiet_sync):
    """CASE: subscribe first, ask for the data second

    Anything another user saves while the sync is in flight is published
    once.  Subscribing after the rpc would drop exactly those messages, and
    the gap is not small:  a project sync carries every object in the
    project.
    """
    state['project'] = 'H2G2'
    client.sync_current_project(None)
    session = client.mbus.session
    assert session.subscribed, 'nothing was subscribed to'
    assert session.calls, 'the sync rpc was not called'
    # both happened; the order is the point
    assert session.subscribed[0] == 'vger.channel.H2G2'
    assert session.calls[0][0] == 'vger.sync_project'


def test_03_sandbox_has_no_channel(client, quiet_sync):
    """CASE: the SANDBOX is local-only, so there is nothing to subscribe to

    Its objects are never published -- vger does not have them at all.
    """
    state['project'] = 'pgefobjects:SANDBOX'
    client.sync_current_project(None)
    assert client.mbus.session.subscribed == []


def test_04_a_channel_is_subscribed_to_only_once(client):
    """CASE: re-syncing a project does not subscribe to its channel again

    A second subscription to the same topic delivers every message on it
    twice, which would show up as duplicate objects and duplicate rpcs --
    the failure mode of the "obj_modified" duplication (test_signal_
    migration.py), arrived at from the other end.
    """
    project = orb.get('H2G2')
    client.subscribe_to_project_channel(project)
    client.subscribe_to_project_channel(project)
    client.subscribe_to_project_channel(project)
    assert client.mbus.session.subscribed == ['vger.channel.H2G2']


def test_05_login_channels_are_not_re_subscribed_by_a_sync(client,
                                                           quiet_sync):
    """CASE: a project channel already subscribed to at login is left alone

    The login-time set still exists and still carries project channels when
    the local db happens to hold the roles.  A sync of one of those projects
    must not double it.
    """
    client.channels = ['vger.channel.H2G2', 'vger.channel.public']
    client.subscribe_to_mbus_channels()
    assert client.mbus.session.subscribed == ['vger.channel.H2G2',
                                              'vger.channel.public']
    state['project'] = 'H2G2'
    client.sync_current_project(None)
    assert client.mbus.session.subscribed.count('vger.channel.H2G2') == 1


def test_06_a_failed_subscription_is_retried(test_orb):
    """CASE: a subscription that failed is not remembered as made

    The record exists to prevent duplicates, so it is written when the
    subscription is asked for, before the answer comes back -- which means
    the failure path has to take it back out again, or one lost subscription
    would last for the whole session.
    """
    client = FakeClient(fail_on=['vger.channel.H2G2'])
    project = orb.get('H2G2')
    client.subscribe_to_project_channel(project)
    assert 'vger.channel.H2G2' not in client.subscribed_channels
    client.subscribe_to_project_channel(project)
    assert client.mbus.session.subscribed == ['vger.channel.H2G2',
                                              'vger.channel.H2G2']


def test_07_a_new_session_subscribes_again(client):
    """CASE: subscriptions belong to the session that made them

    on_mbus_joined() empties the record, so a client that reconnects
    subscribes to everything again rather than believing the previous
    session's subscriptions are still live.  The reconnect path is the one
    that matters most here: a client that drops and returns is a client that
    has been missing messages.
    """
    project = orb.get('H2G2')
    client.subscribe_to_project_channel(project)
    assert client.subscribed_channels == {'vger.channel.H2G2'}
    # what on_mbus_joined() does, with a new session underneath
    client.subscribed_channels = set()
    client.mbus = SimpleNamespace(session=FakeSession())
    client.subscribe_to_project_channel(project)
    assert client.mbus.session.subscribed == ['vger.channel.H2G2']


def test_08_offline_client_subscribes_to_nothing(test_orb):
    """CASE: no message bus session, no subscriptions and no exception

    Reached when a project is synced while the transport is down; the
    subscription is made when the session is rejoined and the sync runs
    again.
    """
    client = FakeClient()
    client.mbus = None
    project = orb.get('H2G2')
    client.subscribe_to_project_channel(project)
    assert client.subscribed_channels == set()


def test_09_on_mbus_joined_clears_the_record():
    """CASE: the clearing is in on_mbus_joined, not only in __init__

    Held at source level because the handler's body is all gui and state
    that a stand-in cannot run.  If the line moves, this says so rather than
    leaving test_07 asserting a promise nothing keeps.
    """
    import inspect
    src = inspect.getsource(Main.on_mbus_joined)
    assert 'self.subscribed_channels = set()' in src
