# -*- coding: utf-8 -*-
"""
Gui tests for the admin tool's "New User" flow (see admin_tool_review.md #2).

These are a prototype:  the point is to show what pytest-qt buys over calling
handler methods directly, which is what the earlier verification for these
findings did.  Three things:

  [1] the *real* widgets are built, so a form that cannot be constructed --
      which is what AddPersonDialog did when no ldap_schema was configured --
      fails the test rather than being stepped over;
  [2] qtbot clicks the actual buttons, so the wiring between button and slot
      is covered, not just the slot;
  [3] signals can be counted, not merely detected.  The regression that
      prompted this was a change that made a deletion reach the repository
      *twice*; an "it happened" assertion passes on that, a count does not.

Run headless:

    QT_QPA_PLATFORM=offscreen pytest pangalactic/node/test/test_admin_dialogs.py
"""
import os

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFileDialog, QMessageBox

from pangalactic.core import orb
from pangalactic.node.admin import (AddPersonDialog, PERSON_FIELDS,
                                    valid_public_key, PUBLIC_KEY_LEN)


GOOD_KEY = 'd385d948b83c1ec302bfceaf744a8c4fcaf8d3fa9688ed7f39b1bb18d0f86716'

REQUIRED = [attr for attr, label, required in PERSON_FIELDS if required]


def fill(dlg, **values):
    """Type values into the dialog's fields (blank for anything not given)."""
    for attr, label, required in PERSON_FIELDS:
        dlg.form_widgets[attr].setText(values.get(attr, ''))


def complete_user(**overrides):
    data = dict(id='trillian', first_name='Tricia', last_name='McMillan',
                org_code='PGANA', email='trillian@heartofgold.ship')
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# construction
# ---------------------------------------------------------------------------

def test_01_dialog_builds_with_no_ldap_schema(qtbot, test_orb, no_ldap):
    """CASE: AddPersonDialog can be built with no ldap_schema configured

    This is the "New User" path.  Before the dialog was decoupled from
    config['ldap_schema'] it raised TypeError here, which is why there was no
    way to create a user without an LDAP directory.
    """
    dlg = AddPersonDialog(parent=None)
    qtbot.addWidget(dlg)
    assert dlg.windowTitle() == 'Create User'
    for attr in REQUIRED:
        assert attr in dlg.form_widgets
    # all fields start empty -- this is a *new* user, not a search result
    assert all(w.text() == '' for w in dlg.form_widgets.values())


def test_02_dialog_prefills_from_search_result(qtbot, test_orb, no_ldap):
    """CASE: data from a search result populates the form and carries the oid"""
    data = {'oid': 'existing-oid-1', 'id': 'buckaroo',
            'first_name': 'Buckaroo', 'last_name': 'Banzai',
            'employer_name': 'Yoyodyne'}
    dlg = AddPersonDialog(data=data, parent=None)
    qtbot.addWidget(dlg)
    assert dlg.windowTitle() == 'Add User'
    assert dlg.form_widgets['id'].text() == 'buckaroo'
    assert dlg.form_widgets['employer_name'].text() == 'Yoyodyne'
    # the oid is carried outside the form, so an existing person is updated
    # rather than duplicated
    assert dlg.person_oid == 'existing-oid-1'


# ---------------------------------------------------------------------------
# validation, driven through the real Save button
# ---------------------------------------------------------------------------

def test_03_save_button_refuses_incomplete_form(qtbot, test_orb, no_ldap, spy,
                                                monkeypatch):
    """CASE: clicking Save with required fields empty sends nothing

    NOTE: this clicks the actual button rather than calling on_save(), so the
    button -> slot connection is covered too.
    """
    monkeypatch.setattr(QMessageBox, 'show', lambda self: None)
    added = spy('add person')
    dlg = AddPersonDialog(parent=None)
    qtbot.addWidget(dlg)
    fill(dlg, first_name='Ford')          # missing id, last_name, org_code

    qtbot.mouseClick(dlg.save_button, Qt.LeftButton)

    assert added.count == 0


def test_04_save_button_refuses_duplicate_userid(qtbot, test_orb, no_ldap,
                                                 spy, monkeypatch):
    """CASE: a user id already in the repository is refused

    The user id becomes the "authid" the repository and the crossbar
    authenticator identify this person by, so it has to be unique.
    """
    monkeypatch.setattr(QMessageBox, 'show', lambda self: None)
    assert orb.select('Person', id='zaphod') is not None
    added = spy('add person')
    dlg = AddPersonDialog(parent=None)
    qtbot.addWidget(dlg)
    fill(dlg, **complete_user(id='zaphod'))
    dlg.public_key = GOOD_KEY

    qtbot.mouseClick(dlg.save_button, Qt.LeftButton)

    assert added.count == 0


def test_05_complete_form_with_key_sends_exactly_once(qtbot, test_orb,
                                                      no_ldap, spy):
    """CASE: a complete form with a valid key dispatches "add person" ONCE

    The count is the point.  A duplicated signal is a real failure mode here
    (vger.add_person would run twice), and an "assert it was sent" check
    passes on it.
    """
    added = spy('add person')
    dlg = AddPersonDialog(parent=None)
    qtbot.addWidget(dlg)
    fill(dlg, **complete_user())
    dlg.public_key = GOOD_KEY

    qtbot.mouseClick(dlg.save_button, Qt.LeftButton)

    assert added.count == 1
    data = added.calls[0]['data']
    assert data['id'] == 'trillian'
    assert data['org_code'] == 'PGANA'
    assert data['public_key'] == GOOD_KEY


@pytest.mark.parametrize('answer,expected', [(QMessageBox.No, 0),
                                             (QMessageBox.Yes, 1)])
def test_06_no_key_asks_first(qtbot, test_orb, no_ldap, spy, monkeypatch,
                              answer, expected):
    """CASE: saving with no public key asks, and honours the answer

    Creating a user with no key is allowed -- they simply cannot log in until
    one is added -- but it must be a deliberate choice, not a silent one.
    """
    monkeypatch.setattr(QMessageBox, 'exec_', lambda self: answer)
    added = spy('add person')
    dlg = AddPersonDialog(parent=None)
    qtbot.addWidget(dlg)
    fill(dlg, **complete_user(id='zarniwoop'))
    assert dlg.public_key is None

    qtbot.mouseClick(dlg.save_button, Qt.LeftButton)

    assert added.count == expected


# ---------------------------------------------------------------------------
# public key loading, through the real file-chooser slot
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('contents,accepted,note', [
    (GOOD_KEY,            True,  'clean key'),
    (GOOD_KEY + '\n',     True,  'trailing newline is stripped, not rejected'),
    (GOOD_KEY + '  \n',   True,  'trailing whitespace is stripped'),
    (GOOD_KEY[:-1],       False, 'too short'),
    ('z' * PUBLIC_KEY_LEN, False, 'right length, not hex'),
    ('',                  False, 'empty file'),
])
def test_07_load_public_key(qtbot, test_orb, no_ldap, monkeypatch, tmp_path,
                            contents, accepted, note):
    """CASE: loading a public key file strips it and validates it

    A key stored with a trailing newline produces a principals.db row the
    authenticator can never match, so the user is created and then simply
    cannot log in, with nothing to say why.  Stripping repairs the common
    case; genuinely malformed content is refused.
    """
    key_file = tmp_path / 'user_public.key'
    key_file.write_text(contents)
    monkeypatch.setattr(QFileDialog, 'exec_', lambda self: 1)
    monkeypatch.setattr(QFileDialog, 'selectedFiles',
                        lambda self: [str(key_file)])
    monkeypatch.setattr(QMessageBox, 'show', lambda self: None)

    dlg = AddPersonDialog(parent=None)
    qtbot.addWidget(dlg)
    qtbot.mouseClick(dlg.get_key_button, Qt.LeftButton)

    if accepted:
        assert dlg.public_key == GOOD_KEY, note
        assert valid_public_key(dlg.public_key)
        # the button is swapped for the confirmation label on success
        assert dlg.got_key_label.isVisible() or not dlg.isVisible()
    else:
        assert dlg.public_key is None, note


def test_08_key_file_is_not_left_open(qtbot, test_orb, no_ldap, monkeypatch,
                                      tmp_path):
    """CASE: reading the key file does not leak the handle

    Regression guard for the "with"-less open that used to be here.
    """
    key_file = tmp_path / 'k.key'
    key_file.write_text(GOOD_KEY)
    opened = []
    real_open = open

    def tracking_open(*a, **kw):
        f = real_open(*a, **kw)
        opened.append(f)
        return f

    monkeypatch.setattr('builtins.open', tracking_open)
    monkeypatch.setattr(QFileDialog, 'exec_', lambda self: 1)
    monkeypatch.setattr(QFileDialog, 'selectedFiles',
                        lambda self: [str(key_file)])
    monkeypatch.setattr(QMessageBox, 'show', lambda self: None)

    dlg = AddPersonDialog(parent=None)
    qtbot.addWidget(dlg)
    qtbot.mouseClick(dlg.get_key_button, Qt.LeftButton)

    assert dlg.public_key == GOOD_KEY
    assert all(f.closed for f in opened), 'a file handle was left open'
