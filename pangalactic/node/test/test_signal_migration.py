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
    'hw_fields_edited': "'modified object'",
    'rqt_parm_mod': "'rqt parm mod'",
    'units_set': "'units set'",
    'remote_frozen': "'remote frozen'",
    'remote_thawed': "'remote thawed'",
    'refresh_admin_tool': "'refresh admin tool'",
    'deleted_object': "'deleted object'",
    'new_object': "'new object'",
    'delete_obj': 'nothing -- the whole chain was dead',
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


def test_05_hw_fields_dialog_sends_modified_object(qtbot, test_orb):
    """CASE: editing HW fields reaches the repository

    HWFieldsDialog saved locally and refreshed the table but sent no
    "modified object", so Main.on_mod_object_signal never ran and vger.save
    was never called -- edits to name, description, product_type and owner
    were silently never synced.  A "modified object" send here was replaced
    by a dedicated pyqtSignal in 4a4b6ec (2023-01-21).

    Asserting on the *signal* rather than on an rpc: on_mod_object_signal is
    what calls vger.save, and reaching it is the thing that was missing.
    """
    from pydispatch import dispatcher
    from pangalactic.node.dialogs import HWFieldsDialog

    objs = orb.get_by_type('HardwareProduct')
    if not objs:
        pytest.skip('test data has no HardwareProduct instances')
    hw = objs[0]

    class Spy:
        def __init__(self):
            self.calls = []

        def receive(self, obj=None, cname='', **kw):
            self.calls.append((getattr(obj, 'oid', None), cname))

    spy = Spy()
    dispatcher.connect(spy.receive, 'modified object')
    try:
        dlg = HWFieldsDialog(hw, parent=None)
        qtbot.addWidget(dlg)
        dlg.on_save()
    finally:
        dispatcher.disconnect(spy.receive, 'modified object')

    assert (hw.oid, 'HardwareProduct') in spy.calls, (
        f'no "modified object" sent for the edited product: {spy.calls}')


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


# The only modules allowed to declare pyqtSignal, and how many each may
# declare.  There is exactly one justification -- crossing a thread boundary,
# which is the one thing pydispatcher cannot do -- so every module here owns a
# worker thread.  The counts are pinned deliberately: adding a signal to one
# of these modules still trips this test and has to be justified rather than
# waved through because the file was already on the list.
CROSS_THREAD_MODULES = {
    # WorkerSignals: results from the async rpc workers
    'threads.py': 4,
    # Ipc42Worker: the 42 socket loop, reporting from its own QThread
    'ipc42_gui.py': 5,
}


def test_08_only_the_cross_thread_signals_remain(qtbot):
    """CASE: pyqtSignal survives only where a thread boundary is crossed

    Qt marshals a cross-thread signal onto the receiver's event loop;
    pydispatcher calls the receiver in whatever thread sent it, so a widget
    touched from a worker thread is undefined behaviour.  Everything else in
    the package is same-thread gui signalling and has been migrated.
    """
    import re
    from collections import Counter
    decls = []
    for path in _python_files():
        with open(path, encoding='utf-8') as f:
            for n, line in enumerate(f, 1):
                code = line.split('#')[0]
                if re.search(r'\w+\s*=\s*pyqtSignal\s*\(', code):
                    decls.append((os.path.relpath(path, PKG), n,
                                  line.strip()))
    unexpected = [d for d in decls
                  if os.path.basename(d[0]) not in CROSS_THREAD_MODULES]
    assert not unexpected, (
        'pyqtSignal declared outside the cross-thread modules '
        f'{sorted(CROSS_THREAD_MODULES)}:\n  '
        + '\n  '.join(f'{f}:{n}: {t}' for f, n, t in unexpected))
    counts = Counter(os.path.basename(d[0]) for d in decls)
    assert counts == Counter(CROSS_THREAD_MODULES), (
        f'expected {dict(CROSS_THREAD_MODULES)}, got {dict(counts)}')


def test_09_del_object_is_gone(qtbot):
    """CASE: the pyqtSignal-side deletion handler has been removed

    `del_object` was the pyqtSignal half of the deletion path and had
    diverged from `on_deleted_object_signal` in its component-mode branch
    (remaining-chunks review #4).  The correct branch was folded in and the
    method deleted; a reappearance would mean the duplication is back.
    """
    from pangalactic.node import pangalaxian
    src = open(pangalaxian.__file__.replace('.pyc', '.py'),
               encoding='utf-8').read()
    assert 'def del_object' not in src


def test_10_component_branch_does_not_refresh_after_rebuilding(qtbot):
    """CASE: the component-mode branches clear the flag, they do not refresh

    set_product_modeler_interface() constructs a new ModelWindow, so the
    diagram is already rebuilt; calling on_signal_to_refresh() after it
    regenerates what was just generated.  The "system" branches are different
    -- they build no new window -- so they legitimately still refresh.

    Resolves remaining-chunks review #4, which reported the divergence
    between del_object() and on_deleted_object_signal() without being able to
    say which was right.  del_object()'s was.
    """
    import re
    from pangalactic.node import pangalaxian
    src = open(pangalaxian.__file__.replace('.pyc', '.py'),
               encoding='utf-8').read()
    # comments are stripped first: the explanatory notes at these very sites
    # mention on_signal_to_refresh() in order to say it is deliberately absent
    code = '\n'.join(l.split('#')[0] for l in src.split('\n'))
    pattern = re.compile(
        r'self\.set_product_modeler_interface\(\)\n(.{0,600}?)'
        r'\n\s*(elif|else|orb\.log|if )', re.S)
    offenders = []
    for m in pattern.finditer(code):
        block = m.group(1)
        if 'system_model_window' in block and 'on_signal_to_refresh' in block:
            offenders.append(block.strip())
    assert not offenders, (
        'set_product_modeler_interface() is followed by on_signal_to_refresh()'
        ' -- the diagram was just rebuilt by the new ModelWindow:\n\n'
        + '\n\n'.join(offenders))
