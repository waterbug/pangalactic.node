# -*- coding: utf-8 -*-
"""
Tests for what PrepareForOfflineDialog offers to check out.

The interesting part of the dialog is `classify()`:  what it will let a user
claim and what it will not.  Activities are the notable exclusion -- they
cannot be edited offline at all, since editing one adjusts the times of the
others in its timeline (see NOTES_ON_CHECKOUT_MODEL.md section 13) -- so
offering a claim on one would promise something access.py refuses to honour.

Run headless with QT_QPA_PLATFORM=offscreen.
"""
import pytest

# set the orb -- must precede any pangalactic.core import that pulls in "orb"
import pangalactic.core.set_uberorb

from pangalactic.core import orb, state

from pangalactic.node.dialogs import PrepareForOfflineDialog


@pytest.fixture
def project(test_orb):
    projects = [p for p in orb.get_by_type('Project')
                if p.oid != 'pgefobjects:SANDBOX']
    assert projects, 'no project in the test data'
    return projects[0]


@pytest.fixture
def as_user(test_orb):
    person = orb.get_by_type('Person')[0]
    saved = (state.get('local_user_oid'), state.get('checkouts'),
             state.get('connected'), state.get('client'))
    state['local_user_oid'] = person.oid
    state['checkouts'] = {}
    state['connected'] = True
    state['client'] = True
    yield person
    (state['local_user_oid'], state['checkouts'], state['connected'],
     state['client']) = saved


def offered(dlg):
    """
    The objects the dialog offers to check out.
    """
    return [orb.get(oid) for oid in dlg.checkboxes]


def test_01_activities_are_not_offered(qtbot, project, as_user):
    """
    CASE:  a project whose objects include activities.  None of them is
    offered -- not the Mission, not its sub-activities.
    """
    activities = [o for o in orb.get_objects_for_project(project)
                  if isinstance(o, orb.classes['Activity'])]
    assert activities, 'test data should include activities'
    dlg = PrepareForOfflineDialog(project)
    qtbot.addWidget(dlg)
    assert not any(isinstance(o, orb.classes['Activity'])
                   for o in offered(dlg))


def test_02_activities_are_not_listed_as_unavailable_either(qtbot, project,
                                                            as_user):
    """
    CASE:  the same.  They are skipped outright rather than shown in the
    "not available" list -- that list is for things the user might have
    expected to claim and could not, and gives a reason per item.  An
    activity is not a candidate at all, so listing every one of them with a
    reason would bury the items that are.
    """
    dlg = PrepareForOfflineDialog(project)
    qtbot.addWidget(dlg)
    activity_ids = {a.id for a in orb.get_objects_for_project(project)
                    if isinstance(a, orb.classes['Activity'])}
    assert activity_ids, 'test data should include activities'
    # classify() builds the "not available" entries as label strings, each
    # beginning with the object's id
    available, unavailable = dlg.classify(project)
    for label in unavailable:
        assert not any(label.startswith(f'{aid}  (')
                       for aid in activity_ids), label


def test_03_activity_controls_are_not_offered(qtbot, monkeypatch, project,
                                              as_user):
    """
    CASE:  the project's objects include a Decision and a Merge.  Neither is
    offered either -- they are not Activities, but they sequence the
    activities in a timeline, so the same reasoning covers them.

    The test data has none, so they are constructed in memory and injected:
    classify() reads the project's objects through the orb, and building them
    for real would leave them in the session for every later test in the run.
    """
    real_objects = orb.get_objects_for_project(project)
    controls = [orb.classes['Decision'](oid='test:decision-offline'),
                orb.classes['Merge'](oid='test:merge-offline')]
    for c in controls:
        c.id = c.oid
    monkeypatch.setattr(orb, 'get_objects_for_project',
                        lambda p: list(real_objects) + controls)
    dlg = PrepareForOfflineDialog(project)
    qtbot.addWidget(dlg)
    assert 'test:decision-offline' not in dlg.checkboxes
    assert 'test:merge-offline' not in dlg.checkboxes
    available, unavailable = dlg.classify(project)
    for label in unavailable:
        assert not label.startswith('test:decision-offline')
        assert not label.startswith('test:merge-offline')


def test_04_products_are_still_offered(qtbot, project, as_user):
    """
    CASE:  the exclusion is confined to activities.  The project's hardware
    is still offered, which is the ordinary case the dialog exists for.
    """
    dlg = PrepareForOfflineDialog(project)
    qtbot.addWidget(dlg)
    assert any(isinstance(o, orb.classes['Product']) for o in offered(dlg))
