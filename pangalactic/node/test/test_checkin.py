# -*- coding: utf-8 -*-
"""
Tests for checking an object back in from the object editor.

A claim used to have no way of ending except by expiry or by an
administrator's force-release:  vger.check_in and pangalaxian's wrapper both
existed, but nothing in the interface called them.  These cover the two ways
a holder can now release one -- the Check In action, and the offer made after
a save -- and the visibility rules that decide when either is available.

Run headless with QT_QPA_PLATFORM=offscreen.
"""
import pytest

from pydispatch import dispatcher

from PyQt5.QtWidgets import QMessageBox

# set the orb -- must precede any pangalactic.core import that pulls in "orb"
import pangalactic.core.set_uberorb

from pangalactic.core import orb, prefs, state

from pangalactic.node.pgxnobject import PgxnObject

HOLDER = 'test:zaphod'


@pytest.fixture
def product(test_orb):
    """
    A HardwareProduct from the test data.  The check-out indicator lives in
    PgxnObject's HardwareProduct branch, so it has to be one.
    """
    hw = orb.get_by_type('HardwareProduct')
    assert hw, 'no HardwareProduct in the test data'
    return hw[0]


@pytest.fixture
def me(test_orb):
    """
    The local user, as the id that appears in a check-out record.
    """
    person = orb.get_by_type('Person')[0]
    state['local_user_oid'] = person.oid
    return person.id


@pytest.fixture
def clean_state():
    """
    Leave state and prefs as they were found:  both are module-level and
    shared across the session's tests.
    """
    saved = (state.get('checkouts'), state.get('connected'),
             state.get('local_user_oid'), prefs.get('ask_check_in_on_save'))
    yield
    (state['checkouts'], state['connected'], state['local_user_oid'],
     prefs['ask_check_in_on_save']) = saved


@pytest.fixture
def listener():
    """
    Capture the "check in" dispatcher signal.
    """
    class Listener:
        def __init__(self):
            self.calls = []
            dispatcher.connect(self.on_signal, 'check in')

        def on_signal(self, oids=None):
            self.calls.append(list(oids or []))

        def disconnect(self):
            dispatcher.disconnect(self.on_signal, 'check in')

    lis = Listener()
    yield lis
    lis.disconnect()


def editor(qtbot, obj):
    w = PgxnObject(obj)
    qtbot.addWidget(w)
    return w


def claim(oid, userid, purpose='offline work'):
    state['checkouts'] = {oid: {'userid': userid,
                                'expiry_datetime': '2099-01-01 00:00:00',
                                'purpose': purpose}}


def answer(monkeypatch, button):
    """
    Make the next QMessageBox answer with `button` instead of waiting for a
    user.
    """
    monkeypatch.setattr(QMessageBox, 'exec_', lambda self: button)


# ---------------------------------------------------------------------------
# when the Check In action is available
# ---------------------------------------------------------------------------

def test_01_no_claim_hides_both(qtbot, product, me, clean_state):
    """
    CASE:  the object is not checked out.  Neither the indicator nor the
    Check In action is shown.
    """
    state['checkouts'] = {}
    state['connected'] = True
    w = editor(qtbot, product)
    w.refresh_checkout_indicator()
    assert not w.checkout_action.isVisible()
    assert not w.checkin_action.isVisible()


def test_02_own_claim_offers_check_in(qtbot, product, me, clean_state):
    """
    CASE:  the claim is the local user's and there is a connection.  Both the
    indicator and the Check In action are shown.
    """
    claim(product.oid, me)
    state['connected'] = True
    w = editor(qtbot, product)
    w.refresh_checkout_indicator()
    assert w.checkout_action.isVisible()
    assert '(you)' in w.checkout_action.text()
    assert w.checkin_action.isVisible()
    assert w.holds_checkout()


def test_03_someone_elses_claim_does_not(qtbot, product, me, clean_state):
    """
    CASE:  the claim is somebody else's.  The indicator is shown, naming
    them, but Check In is not -- only a holder can release a claim.
    """
    claim(product.oid, 'somebody_else')
    state['connected'] = True
    w = editor(qtbot, product)
    w.refresh_checkout_indicator()
    assert w.checkout_action.isVisible()
    assert '(you)' not in w.checkout_action.text()
    assert not w.checkin_action.isVisible()
    assert not w.holds_checkout()


def test_04_disconnected_hides_check_in(qtbot, product, me, clean_state):
    """
    CASE:  the claim is the user's own but there is no connection.  The
    repository records the release, so there is nothing to release through
    and the action is hidden.
    """
    claim(product.oid, me)
    state['connected'] = False
    w = editor(qtbot, product)
    w.refresh_checkout_indicator()
    assert w.checkout_action.isVisible()
    assert not w.checkin_action.isVisible()


# ---------------------------------------------------------------------------
# what the action does
# ---------------------------------------------------------------------------

def test_05_check_in_sends_the_signal(qtbot, monkeypatch, product, me,
                                      clean_state, listener):
    """
    CASE:  the holder confirms Check In.  The object's oid goes out on the
    "check in" signal, which is what pangalaxian turns into the rpc.
    """
    claim(product.oid, me)
    state['connected'] = True
    w = editor(qtbot, product)
    answer(monkeypatch, QMessageBox.Yes)
    w.on_check_in()
    assert listener.calls == [[product.oid]]


def test_06_declining_sends_nothing(qtbot, monkeypatch, product, me,
                                    clean_state, listener):
    """
    CASE:  the holder is asked and says no.  Nothing is released.
    """
    claim(product.oid, me)
    state['connected'] = True
    w = editor(qtbot, product)
    answer(monkeypatch, QMessageBox.No)
    w.on_check_in()
    assert listener.calls == []


def test_07_check_in_of_an_unheld_claim_does_nothing(qtbot, monkeypatch,
                                                     product, me,
                                                     clean_state, listener):
    """
    CASE:  the action is triggered when the claim is not the user's -- the
    button is hidden then, but the slot guards it too, since visibility is
    refreshed on a signal and can lag the mirror.
    """
    claim(product.oid, 'somebody_else')
    state['connected'] = True
    w = editor(qtbot, product)
    answer(monkeypatch, QMessageBox.Yes)
    w.on_check_in()
    assert listener.calls == []


# ---------------------------------------------------------------------------
# the offer made after a save
# ---------------------------------------------------------------------------

def test_08_save_offers_check_in(qtbot, monkeypatch, product, me,
                                 clean_state, listener):
    """
    CASE:  the holder saves.  Saving and checking in are different things,
    but easily conflated, so the holder is asked rather than left to find the
    action.
    """
    claim(product.oid, me)
    state['connected'] = True
    prefs['ask_check_in_on_save'] = True
    w = editor(qtbot, product)
    answer(monkeypatch, QMessageBox.Yes)
    w.offer_check_in()
    assert listener.calls == [[product.oid]]


def test_09_save_offer_is_declinable(qtbot, monkeypatch, product, me,
                                     clean_state, listener):
    """
    CASE:  the holder saves and declines the offer.  The claim is kept, which
    is the point of having claimed it.
    """
    claim(product.oid, me)
    state['connected'] = True
    prefs['ask_check_in_on_save'] = True
    w = editor(qtbot, product)
    answer(monkeypatch, QMessageBox.No)
    w.offer_check_in()
    assert listener.calls == []


def test_10_save_offer_respects_the_preference(qtbot, monkeypatch, product,
                                               me, clean_state, listener):
    """
    CASE:  the user has ticked "do not ask again".  No question is asked --
    and, because the question is where the release comes from, nothing is
    released.
    """
    claim(product.oid, me)
    state['connected'] = True
    prefs['ask_check_in_on_save'] = False
    asked = []
    monkeypatch.setattr(QMessageBox, 'exec_',
                        lambda self: asked.append(1) or QMessageBox.Yes)
    w = editor(qtbot, product)
    w.offer_check_in()
    assert asked == []
    assert listener.calls == []


def test_11_no_offer_without_a_claim(qtbot, monkeypatch, product, me,
                                     clean_state, listener):
    """
    CASE:  an ordinary save of an object nobody has claimed.  The user is not
    asked about check-in at all -- this is the common case, and a question
    here would be noise on every save.
    """
    state['checkouts'] = {}
    state['connected'] = True
    prefs['ask_check_in_on_save'] = True
    asked = []
    monkeypatch.setattr(QMessageBox, 'exec_',
                        lambda self: asked.append(1) or QMessageBox.Yes)
    w = editor(qtbot, product)
    w.offer_check_in()
    assert asked == []
    assert listener.calls == []


def test_12_no_offer_while_disconnected(qtbot, monkeypatch, product, me,
                                        clean_state, listener):
    """
    CASE:  the holder saves while disconnected.  There is no way to record a
    release, so asking would be offering something that cannot be done.
    """
    claim(product.oid, me)
    state['connected'] = False
    prefs['ask_check_in_on_save'] = True
    asked = []
    monkeypatch.setattr(QMessageBox, 'exec_',
                        lambda self: asked.append(1) or QMessageBox.Yes)
    w = editor(qtbot, product)
    w.offer_check_in()
    assert asked == []
    assert listener.calls == []
