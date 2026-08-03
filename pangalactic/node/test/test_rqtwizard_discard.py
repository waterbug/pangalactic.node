# -*- coding: utf-8 -*-
"""
Tests for discarding an unfinished requirement when the wizard is dismissed.

The wizard creates and saves its Requirement when the first page opens, and
applies everything the user enters only in RqtSummaryPage.finish().  So any
exit that is not Finish must throw the object away, or it leaves a saved
placeholder with none of its attributes.

The discard used to be wired to the Cancel *button* alone, so closing the
window with the title-bar X (or Esc) left exactly that debris behind.  It now
lives in RqtWizard.reject(), which all three exits route through.

See rqtwizard_review.md #4.
"""
import pytest

# set the orb -- must precede any pangalactic.core import that pulls in "orb"
import pangalactic.core.set_uberorb

from pangalactic.core import orb, state
from pangalactic.core.clone import clone

from PyQt5.QtWidgets import QMessageBox, QWizard

from pangalactic.node.rqtwizard import RqtWizard, rqt_wizard_state


@pytest.fixture
def wizard(qtbot, test_orb):
    """An RqtWizard with a new, unfinished requirement in play.

    NOTE: the wizard's first page builds a real PgxnObject in edit mode, which
    needs a local user with "modify" on the requirement -- without one,
    get_perms() withholds it, PgxnObject never creates its save_button, and
    the page raises AttributeError.  (That is exactly the failure the author
    hit on 2026-08-02, from the other direction: Requirement had been added to
    PgxnObject's UNEDITABLES.)
    """
    state['project'] = 'H2G2'
    state['local_user_oid'] = 'test:steve'
    state['connected'] = True
    w = RqtWizard(parent=None, performance=False)
    qtbot.addWidget(w)
    yield w
    rqt_wizard_state['rqt_oid'] = ''


def _make_pending_rqt(wizard, name='Test Rqt'):
    """Put the wizard in the state the first page leaves it in."""
    project = orb.get('H2G2')
    rqt = clone('Requirement', id='H2G2-TBD', owner=project, level=0,
                public=True)
    rqt.name = name
    orb.save([rqt])
    rqt_wizard_state['rqt_oid'] = rqt.oid
    wizard.new_req = True
    return rqt


def _answer(monkeypatch, button):
    monkeypatch.setattr(QMessageBox, 'question',
                        staticmethod(lambda *a, **kw: button))


def test_01_closing_the_window_discards_the_requirement(wizard, monkeypatch):
    """CASE: the title-bar X discards, once confirmed

    This is the case that was broken: close() goes straight to reject(),
    which the old Cancel-button-only wiring never reached.
    """
    rqt = _make_pending_rqt(wizard)
    oid = rqt.oid
    _answer(monkeypatch, QMessageBox.Yes)

    wizard.show()
    wizard.close()

    assert orb.get(oid) is None, 'unfinished requirement was left behind'
    assert rqt_wizard_state['rqt_oid'] == ''


def test_02_cancel_discards_the_requirement(wizard, monkeypatch):
    """CASE: the Cancel button still discards"""
    rqt = _make_pending_rqt(wizard)
    oid = rqt.oid
    _answer(monkeypatch, QMessageBox.Yes)

    wizard.button(QWizard.CancelButton).click()

    assert orb.get(oid) is None
    assert rqt_wizard_state['rqt_oid'] == ''


def test_03_declining_keeps_the_requirement_and_the_wizard(wizard, monkeypatch):
    """CASE: answering No leaves both the object and the wizard alone"""
    rqt = _make_pending_rqt(wizard)
    oid = rqt.oid
    _answer(monkeypatch, QMessageBox.No)

    wizard.show()
    wizard.close()

    assert orb.get(oid) is not None, 'requirement discarded despite "No"'
    assert wizard.isVisible(), 'wizard closed despite "No"'
    # and it is still discardable afterwards
    _answer(monkeypatch, QMessageBox.Yes)
    wizard.close()
    assert orb.get(oid) is None


def test_04_untouched_requirement_is_discarded_without_a_prompt(wizard,
                                                                monkeypatch):
    """CASE: nothing entered yet -> no prompt, just discard

    `name` is the required field on the first page, so a requirement without
    one has nothing worth warning about.
    """
    rqt = _make_pending_rqt(wizard, name='')
    oid = rqt.oid

    def _fail(*a, **kw):
        raise AssertionError('prompted for an untouched requirement')

    monkeypatch.setattr(QMessageBox, 'question', staticmethod(_fail))

    wizard.show()
    wizard.close()

    assert orb.get(oid) is None


def test_05_a_committed_requirement_is_not_discarded(wizard, monkeypatch):
    """CASE: after Finish, dismissing the wizard must not delete it

    finish() clears new_req precisely so that a reject() arriving afterwards
    cannot delete the requirement that was just created.
    """
    rqt = _make_pending_rqt(wizard)
    oid = rqt.oid
    wizard.new_req = False          # what finish() does on success

    def _fail(*a, **kw):
        raise AssertionError('prompted for a committed requirement')

    monkeypatch.setattr(QMessageBox, 'question', staticmethod(_fail))

    wizard.show()
    wizard.close()

    assert orb.get(oid) is not None, 'committed requirement was deleted'
