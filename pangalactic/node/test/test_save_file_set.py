# -*- coding: utf-8 -*-
"""
Tests for saving a multi-file assembly out of the vault.

"Save a local copy" is for taking a copy *away* -- to share, or to use in
another process.  For a CAD assembly exported as a set of files, one file is
not a copy of anything usable:  s1-pe-214.stp is one of thirteen, and on its
own it refers to twelve files that are not there.

The names are the whole point.  A STEP assembly resolves its references by
name, relative to its own directory, so a set saved under any other names is
not readable -- and the vault's names are `<oid>_<name>`, which exist to keep
the vault collision-free and mean nothing outside it.

Run headless with QT_QPA_PLATFORM=offscreen.
"""
import os

import pytest

# set the orb -- must precede any pangalactic.core import that pulls in "orb"
import pangalactic.core.set_uberorb

from pangalactic.core import orb
from pangalactic.core.clone import clone

from PyQt5.QtWidgets import (QFileDialog, QMessageBox,
                             QPushButton)

from pangalactic.node.dialogs import FileInfoDialog


def rep_file(name, parent=None, in_vault=True):
    rf = clone('RepresentationFile', user_file_name=name,
               id=name.replace('.', '_'), name=name)
    if parent is not None:
        rf.component_file_of = parent
    orb.save([rf])
    if in_vault:
        with open(orb.get_vault_fpath(rf), 'w') as f:
            f.write(f'contents of {name}')
    return rf


@pytest.fixture
def answers(monkeypatch, tmp_path):
    """
    Answer the directory chooser with tmp_path and dismiss the report.
    """
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory',
                        staticmethod(lambda *a, **kw: str(tmp_path)))
    monkeypatch.setattr(QMessageBox, 'exec_', lambda self: QMessageBox.Ok)
    return str(tmp_path)


def button_labels(dlg):
    """
    The dialog's button labels.
    """
    return [b.text() for b in dlg.findChildren(QPushButton)]


def test_01_no_set_button_for_a_lone_file(qtbot, test_orb):
    """
    CASE:  a file that references nothing.  "Save Local Copy" is all that is
    wanted;  there is no set.
    """
    dlg = FileInfoDialog(rep_file('lone.stp'))
    qtbot.addWidget(dlg)
    labels = button_labels(dlg)
    assert 'Save Local Copy' in labels
    assert 'Save Whole Set' not in labels


def test_01b_the_set_button_is_offered_for_a_set(qtbot, test_orb):
    """
    CASE:  a file that references others.  Saving it alone would give the
    user a file nothing can read, so the whole set is offered too.
    """
    top = rep_file('offered_asm.stp')
    rep_file('offered_part.stp', parent=top)
    dlg = FileInfoDialog(top)
    qtbot.addWidget(dlg)
    labels = button_labels(dlg)
    assert 'Save Local Copy' in labels
    assert 'Save Whole Set' in labels


def test_01c_nothing_is_offered_for_a_file_not_in_the_vault(qtbot, test_orb):
    """
    CASE:  the file has not been downloaded.  There is nothing to save yet,
    so the dialog offers to fetch it instead.
    """
    top = rep_file('undownloaded_asm.stp', in_vault=False)
    rep_file('undownloaded_part.stp', parent=top)
    dlg = FileInfoDialog(top)
    qtbot.addWidget(dlg)
    labels = button_labels(dlg)
    assert 'Download File' in labels
    assert 'Save Whole Set' not in labels


def test_02_the_whole_set_is_saved_under_its_own_names(qtbot, test_orb,
                                                       answers):
    """
    CASE:  an assembly with subassemblies and parts.  Every file lands in
    one directory under the name its references use.
    """
    top = rep_file('save_asm.stp')
    sub = rep_file('save_sub.stp', parent=top)
    rep_file('save_part.stp', parent=sub)
    dlg = FileInfoDialog(top)
    qtbot.addWidget(dlg)
    dlg.on_save_set(None)
    for name in ('save_asm.stp', 'save_sub.stp', 'save_part.stp'):
        path = os.path.join(answers, name)
        assert os.path.exists(path), f'{name} was not saved'
    # ... with the file's content, not an empty placeholder
    with open(os.path.join(answers, 'save_part.stp')) as f:
        assert f.read() == 'contents of save_part.stp'


def test_03_the_vault_name_is_not_used(qtbot, test_orb, answers):
    """
    CASE:  the saved names are the user file names.

    The vault name carries the oid to keep the vault collision-free, and a
    reference will never match it -- saving under vault names would produce a
    directory of files that cannot read each other.
    """
    top = rep_file('names_asm.stp')
    part = rep_file('names_part.stp', parent=top)
    dlg = FileInfoDialog(top)
    qtbot.addWidget(dlg)
    dlg.on_save_set(None)
    saved = os.listdir(answers)
    assert 'names_part.stp' in saved
    assert not any(part.oid in name for name in saved)


def test_04_a_file_not_downloaded_is_reported(qtbot, test_orb, answers,
                                              monkeypatch):
    """
    CASE:  part of the set is not in the vault.

    Said rather than silently skipped:  a set missing a file is not readable,
    and the user is about to send it to somebody.
    """
    shown = []
    monkeypatch.setattr(QMessageBox, '__init__',
                        lambda self, icon, title, text, *a, **kw:
                            shown.append(text) or None)
    monkeypatch.setattr(QMessageBox, 'exec_', lambda self: QMessageBox.Ok)
    top = rep_file('partial_asm.stp')
    rep_file('partial_here.stp', parent=top)
    rep_file('partial_gone.stp', parent=top, in_vault=False)
    dlg = FileInfoDialog(top)
    qtbot.addWidget(dlg)
    dlg.on_save_set(None)
    assert os.path.exists(os.path.join(answers, 'partial_here.stp'))
    assert not os.path.exists(os.path.join(answers, 'partial_gone.stp'))
    assert shown and 'partial_gone.stp' in shown[0]


def test_05_cancelling_saves_nothing(qtbot, test_orb, tmp_path, monkeypatch):
    """
    CASE:  the user cancels the directory chooser.
    """
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory',
                        staticmethod(lambda *a, **kw: ''))
    top = rep_file('cancel_asm.stp')
    rep_file('cancel_part.stp', parent=top)
    dlg = FileInfoDialog(top)
    qtbot.addWidget(dlg)
    dlg.on_save_set(None)
    assert os.listdir(str(tmp_path)) == []
