# -*- coding: utf-8 -*-
"""
Tests for the pydispatcher migration of "obj_modified".

`obj_modified` was a pyqtSignal relayed up a chain -- sub-form -> PgxnObject
-> tree/library/filter panel -> Main -- because a pyqtSignal can only reach an
object holding a reference to the emitter. Every level in between carried a
handler whose whole body re-emitted it one level up.

It also duplicated the `'modified object'` dispatcher signal, which was sent
alongside it at every PgxnObject emit site, so both paths reached
`Main.on_mod_object_signal` and it ran **twice per edit** -- producing
duplicate `vger.save()` rpcs (confirmed in the running app by the author,
2026-08-03).

See `pydispatcher_migration.md`.
"""
import os
import re

import pytest

# set the orb -- must precede any pangalactic.core import that pulls in "orb"
import pangalactic.core.set_uberorb

from pangalactic.core import orb

from pangalactic.node.filters import FilterPanel

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _python_files():
    for dirpath, dirnames, filenames in os.walk(PKG):
        dirnames[:] = [d for d in dirnames if d != '__pycache__']
        for fn in filenames:
            if fn.endswith('.py'):
                yield os.path.join(dirpath, fn)


# pyqtSignals migrated to pydispatcher, with the signal name that replaced
# each.  Extend as the migration proceeds; see pydispatcher_migration.md.
MIGRATED = {
    'obj_modified': "'modified object'",
    'mod_object': 'nothing -- it was never emitted',
    'activity_edited': 'nothing -- it had no receiver',
    'toggle_library_size': "'toggle library size'",
    'hw_fields_edited': "'hw fields edited'",
    'rqt_parm_mod': "'rqt parm mod'",
    'units_set': "'units set'",
    'remote_frozen': "'remote frozen'",
    'remote_thawed': "'remote thawed'",
    'refresh_admin_tool': "'refresh admin tool'",
    }


@pytest.mark.parametrize('name', sorted(MIGRATED))
def test_01_migrated_signals_are_not_reintroduced(name):
    """CASE: a migrated pyqtSignal is not declared, emitted or connected

    Guard rather than an assertion about the past: the relay pattern is easy
    to add back one connection at a time, and each addition looks locally
    reasonable.

    Matches *use*, not mention -- prose in a docstring explaining why a signal
    is gone is not a reintroduction.
    """
    use = re.compile(r'\b' + name + r'\s*=\s*pyqtSignal|'
                     r'\b' + name + r'\.(emit|connect)\s*\(')
    offenders = []
    for path in _python_files():
        if os.path.basename(path) == os.path.basename(__file__):
            continue
        with open(path, encoding='utf-8') as f:
            for n, line in enumerate(f, 1):
                code = line.split('#')[0]
                if use.search(code):
                    offenders.append(
                        f'{os.path.relpath(path, PKG)}:{n}: {line.strip()}')
    assert not offenders, (
        f'{name} reappeared -- use {MIGRATED[name]} instead:\n  '
        + '\n  '.join(offenders))


def test_02_no_qtsignal_adapters_remain_for_modified_objects(qtbot):
    """CASE: Main no longer carries the oid->obj adapter

    `on_mod_object_qtsignal` existed only to convert a pyqtSignal's oid into
    the object the dispatcher handler wanted, then delegate to it.  With the
    pyqtSignal gone the adapter is dead weight, and leaving it would invite
    re-wiring through it.
    """
    from pangalactic.node import pangalaxian
    src = open(pangalaxian.__file__.replace('.pyc', '.py'),
               encoding='utf-8').read()
    assert 'on_mod_object_qtsignal' not in src


def test_03_filter_panel_updates_its_model_on_the_dispatcher_signal(
        qtbot, test_orb, monkeypatch):
    """CASE: FilterPanel still updates its own table model

    This is the one relay that was not pure: it did real work
    (`sourceModel().mod_object(oid)`) before re-emitting.  The work now hangs
    off the dispatcher signal instead.  ObjectTableView has an equivalent
    receiver, but it is a different class from this panel's ProxyView, so
    this is not covered by it.
    """
    from pydispatch import dispatcher

    objs = orb.get_by_type('HardwareProduct')
    if not objs:
        pytest.skip('test data has no HardwareProduct instances')
    panel = FilterPanel(objs[:3], cname='HardwareProduct')
    qtbot.addWidget(panel)

    called = []
    monkeypatch.setattr(panel.proxy_model.sourceModel(), 'mod_object',
                        lambda oid: called.append(oid))

    obj = objs[0]
    dispatcher.send(signal='modified object', obj=obj)

    assert called == [obj.oid], (
        f'FilterPanel did not update its model: {called}')


def test_04_filter_panel_ignores_a_signal_with_no_object(qtbot, test_orb):
    """CASE: a "modified object" send without an obj must not raise

    The dispatcher signal is broadcast, so this panel now sees every send in
    the process, including any that omit "obj".
    """
    from pydispatch import dispatcher

    objs = orb.get_by_type('HardwareProduct')
    if not objs:
        pytest.skip('test data has no HardwareProduct instances')
    panel = FilterPanel(objs[:3], cname='HardwareProduct')
    qtbot.addWidget(panel)

    dispatcher.send(signal='modified object')          # no obj at all
    dispatcher.send(signal='modified object', obj=None)


def test_05_filter_panel_responds_to_hw_fields_edited(qtbot, test_orb,
                                                      monkeypatch):
    """CASE: the migrated "hw fields edited" signal reaches FilterPanel

    HWFieldsDialog used to be wired to the panel that opened it.  It now
    sends a dispatcher signal, so the panel must pick it up without the
    per-dialog connection.
    """
    from pydispatch import dispatcher

    objs = orb.get_by_type('HardwareProduct')
    if not objs:
        pytest.skip('test data has no HardwareProduct instances')
    panel = FilterPanel(objs[:3], cname='HardwareProduct')
    qtbot.addWidget(panel)

    called = []
    monkeypatch.setattr(panel, 'mod_object', lambda oid: called.append(oid))

    dispatcher.send(signal='hw fields edited', oid=objs[0].oid)

    assert called == [objs[0].oid]


def test_06_pgxnobject_listens_for_freeze_and_thaw_itself(qtbot, test_orb):
    """CASE: PgxnObject connects its own freeze/thaw receivers

    Main used to wire these per instance, so it had to know about every
    PgxnObject it created.  Each instance now listens for itself.
    """
    from pangalactic.node import pgxnobject
    src = open(pgxnobject.__file__.replace('.pyc', '.py'),
               encoding='utf-8').read()
    assert "dispatcher.connect(self.on_remote_frozen, 'remote frozen')" in src
    assert "dispatcher.connect(self.on_remote_thawed, 'remote thawed')" in src


def test_07_admin_tool_refresh_is_disconnected_on_reopen(qtbot, test_orb):
    """CASE: the admin-tool teardown still disconnects the old dialog

    `refresh_admin_tool` was the one converted signal with an explicit
    teardown, added to fix the accumulation bug where every open left another
    live dialog connected (remaining-chunks review #2).  pydispatcher does not
    disconnect on destruction either, so converting it must not lose that.
    """
    from pangalactic.node import pangalaxian
    src = open(pangalaxian.__file__.replace('.pyc', '.py'),
               encoding='utf-8').read()
    assert "dispatcher.disconnect(old_dlg.refresh_roles," in src
    assert "dispatcher.connect(self.admin_dlg.refresh_roles," in src
