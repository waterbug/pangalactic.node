# -*- coding: utf-8 -*-
"""
Tests for the STEP import dialogs.

The dialogs are presenters over the plan that `step_plan` produces, so these
tests check that they present it faithfully and that what the user does to a
checkbox reaches the plan.  Whether the import itself is right is
test_step_plan.py's business, and it settles that without any Qt.

Run headless with QT_QPA_PLATFORM=offscreen.
"""
import pytest

from PyQt5.QtCore import Qt

# set the orb
import pangalactic.core.set_uberorb

from pangalactic.core import orb
from pangalactic.core.serializers import deserialize
from pangalactic.core.test.utils import create_test_users, create_test_project

HOME = 'step_dialogs_test'
orb.start(home=HOME)
deserialize(orb, create_test_users() + create_test_project())

from pangalactic.node.step_import import Occurrence, Placement
from pangalactic.node.step_dialogs import (StepFileChangedDialog,
                                           StepImportModeDialog,
                                           StepPlanDialog)
from pangalactic.node.step_plan import CREATE, PLACE, plan_placements

ASSEMBLY_OID = 'test:spacecraft0'
ACU_OID = 'test:H2G2:acu-sc0-propsys'


def occ(ref_des, children=()):
    return Occurrence(name=ref_des, ref_des=ref_des, prototype_key='p',
                      prototype_name='Part',
                      placement=Placement((0.0, 0.0, 0.0), (0.0, 0.0, 1.0),
                                          (1.0, 0.0, 0.0)),
                      children=list(children))


@pytest.fixture
def plan():
    """
    A plan with one item that will be applied and one that will not.
    """
    acu = orb.get(ACU_OID)
    root = occ('root', children=[occ(acu.reference_designator),
                                 occ('NOT-IN-THE-ASSEMBLY')])
    return plan_placements(root, orb.get(ASSEMBLY_OID))


@pytest.fixture
def plan_dialog(qtbot, plan):
    dlg = StepPlanDialog(plan, PLACE, file_name='rover.stp')
    qtbot.addWidget(dlg)
    return dlg


# ---- mode dialog ---------------------------------------------------------

def test_01_place_needs_an_assembly(qtbot):
    """
    With no assembly selected, placing is not offered and creating is chosen.
    """
    dlg = StepImportModeDialog()
    qtbot.addWidget(dlg)
    assert not dlg.place_button.isEnabled()
    assert dlg.create_button.isChecked()
    assert dlg.mode == CREATE


def test_02_place_is_the_default_with_an_assembly(qtbot):
    """
    With an assembly selected, placing it is the default -- the commoner
    case, and the one that creates nothing.
    """
    dlg = StepImportModeDialog(assembly=orb.get(ASSEMBLY_OID))
    qtbot.addWidget(dlg)
    assert dlg.place_button.isChecked()
    assert dlg.mode == PLACE


def test_03_cannot_import_without_a_file(qtbot):
    """
    Ok stays disabled until a file has been chosen.
    """
    dlg = StepImportModeDialog(assembly=orb.get(ASSEMBLY_OID))
    qtbot.addWidget(dlg)
    ok = dlg.buttons.button(dlg.buttons.Ok)
    assert not ok.isEnabled()
    dlg.file_path = '/somewhere/assembly.stp'
    dlg._update_ok()
    assert ok.isEnabled()


# ---- plan dialog ---------------------------------------------------------

def test_04_every_item_is_shown(plan, plan_dialog):
    """
    A row per plan item, including the ones the import will not act on.
    """
    assert plan_dialog.table.rowCount() == len(plan)


def test_05_only_actionable_rows_are_checkable(plan, plan_dialog):
    """
    A row that would change nothing has no checkbox:  there is nothing to
    confirm, it is telling the user what the import leaves alone.
    """
    for row, item in enumerate(plan):
        cell = plan_dialog.table.item(row, plan_dialog.CONFIRM)
        checkable = bool(cell.flags() & Qt.ItemIsUserCheckable)
        assert checkable == item.actionable


def test_06_unchecking_a_row_unconfirms_the_item(plan, plan_dialog):
    """
    The dialog holds the actual PlanItems, so what the user does to a
    checkbox is what apply_* will act on.
    """
    row = [i for i, item in enumerate(plan) if item.actionable][0]
    plan_dialog.table.item(row, plan_dialog.CONFIRM).setCheckState(
                                                            Qt.Unchecked)
    assert plan[row].confirmed is False


def test_07_rechecking_a_row_confirms_it_again(plan, plan_dialog):
    """
    And back again -- the checkbox is the item's state, not a copy of it.
    """
    row = [i for i, item in enumerate(plan) if item.actionable][0]
    cell = plan_dialog.table.item(row, plan_dialog.CONFIRM)
    cell.setCheckState(Qt.Unchecked)
    cell.setCheckState(Qt.Checked)
    assert plan[row].confirmed is True


def test_08_accept_all_leaves_unactionable_items_alone(plan, plan_dialog):
    """
    "Accept all" must not appear to accept something that will not happen.
    """
    plan_dialog.set_all(True)
    for item in plan:
        assert item.confirmed is item.actionable


def test_09_reject_all_leaves_nothing_to_import(plan, plan_dialog):
    """
    Rejecting everything leaves nothing to import.
    """
    plan_dialog.set_all(False)
    assert plan_dialog.confirmed_items() == []


def test_10_confirmed_items_excludes_unactionable(plan, plan_dialog):
    """
    confirmed_items() never offers an item that cannot be applied.
    """
    plan_dialog.set_all(True)
    assert all(i.actionable for i in plan_dialog.confirmed_items())


def test_11_summary_counts_what_is_not_covered(plan, plan_dialog):
    """
    The summary says how many items the import does not cover, so the count
    is visible without reading the table.
    """
    n_skipped = len([i for i in plan if not i.actionable])
    assert n_skipped > 0
    assert f'{n_skipped} item(s)' in plan_dialog._summary()


def test_12_the_file_name_is_in_the_title(plan_dialog):
    """
    Which file is being imported is visible while reviewing it.
    """
    assert 'rover.stp' in plan_dialog.windowTitle()


# ---- changed-file dialog -------------------------------------------------

def test_13_changed_file_dialog_names_the_file_and_date(qtbot):
    """
    The warning says which file changed and when it was last imported, so the
    user can tell whether that is expected.
    """
    dlg = StepFileChangedDialog(file_name='rover.stp', imported='2026-08-01')
    qtbot.addWidget(dlg)
    text = dlg.message_label.text()
    assert 'rover.stp' in text
    assert '2026-08-01' in text


def test_14_changed_file_dialog_offers_rematch_or_cancel(qtbot):
    """
    The choice is re-match or abandon the import -- not "proceed anyway",
    which would be the silent re-placing the stop exists to prevent.
    """
    dlg = StepFileChangedDialog(file_name='rover.stp')
    qtbot.addWidget(dlg)
    assert dlg.buttons.button(dlg.buttons.Ok).text() == 'Re-match'
    assert dlg.buttons.button(dlg.buttons.Cancel).text() == 'Cancel import'


# ---- orchestration -------------------------------------------------------

def test_15_import_returns_none_if_mode_dialog_cancelled(qtbot, monkeypatch):
    """
    Cancelling at the first dialog does nothing at all -- no file is read.
    """
    from pangalactic.node import step_dialogs as sd
    monkeypatch.setattr(sd.StepImportModeDialog, 'exec_', lambda self: 0)
    read_called = []
    monkeypatch.setattr('pangalactic.node.step_import.read_assembly',
                        lambda *a, **k: read_called.append(1))
    assert sd.run_step_import(assembly=orb.get(ASSEMBLY_OID)) is None
    assert read_called == []


def test_16_import_returns_none_if_plan_rejected(qtbot, monkeypatch, tmp_path):
    """
    Rejecting the plan applies nothing, even though the file was read and a
    plan was made.
    """
    from pangalactic.node import step_dialogs as sd
    acu = orb.get(ACU_OID)
    root = occ('root', children=[occ(acu.reference_designator)])
    step_file = tmp_path / 'x.stp'
    step_file.write_text('not really a step file')
    monkeypatch.setattr(sd.StepImportModeDialog, 'exec_', lambda self: 1)
    monkeypatch.setattr(sd.StepImportModeDialog, 'file_path',
                        str(step_file), raising=False)
    monkeypatch.setattr('pangalactic.node.step_import.read_assembly',
                        lambda *a, **k: root)
    monkeypatch.setattr(sd.StepPlanDialog, 'exec_', lambda self: 0)
    applied = []
    monkeypatch.setattr(sd, 'apply_placements',
                        lambda *a, **k: applied.append(1))
    assert sd.run_step_import(assembly=orb.get(ASSEMBLY_OID)) is None
    assert applied == []


def test_17_unreadable_file_is_reported_not_raised(qtbot, monkeypatch,
                                                   tmp_path):
    """
    A file that cannot be read gives the user a message rather than a
    traceback.
    """
    from pangalactic.node import step_dialogs as sd
    step_file = tmp_path / 'bad.stp'
    step_file.write_text('nonsense')
    monkeypatch.setattr(sd.StepImportModeDialog, 'exec_', lambda self: 1)
    monkeypatch.setattr(sd.StepImportModeDialog, 'file_path',
                        str(step_file), raising=False)
    shown = []
    monkeypatch.setattr(sd.OptionNotification, 'exec_',
                        lambda self: shown.append(self.windowTitle()))
    assert sd.run_step_import(assembly=orb.get(ASSEMBLY_OID)) is None
    assert shown == ['STEP import failed']


def test_18_checksum_of_a_missing_file_is_empty(qtbot):
    """
    An unreadable file checksums to '', which file_has_changed() treats as
    "cannot compare" rather than as a change.
    """
    from pangalactic.node.step_dialogs import _checksum
    assert _checksum('/no/such/file.stp') == ''
