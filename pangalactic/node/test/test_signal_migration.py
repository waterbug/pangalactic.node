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


def test_01_obj_modified_is_gone():
    """CASE: the relayed pyqtSignal is not reintroduced

    Guard rather than assertion about the past: the relay pattern is easy to
    add back one connection at a time, and each addition looks locally
    reasonable.
    """
    # matches use, not mention: a declaration, an emit, or a connect.  Prose
    # in a docstring explaining why the signal is gone is not a reintroduction.
    USE = re.compile(r'\bobj_modified\s*=\s*pyqtSignal|'
                     r'\bobj_modified\.(emit|connect)\s*\(')
    offenders = []
    for path in _python_files():
        if os.path.basename(path) == os.path.basename(__file__):
            continue
        with open(path, encoding='utf-8') as f:
            for n, line in enumerate(f, 1):
                code = line.split('#')[0]
                if USE.search(code):
                    offenders.append(
                        f'{os.path.relpath(path, PKG)}:{n}: {line.strip()}')
    assert not offenders, (
        'obj_modified reappeared -- send the "modified object" dispatcher '
        'signal instead:\n  ' + '\n  '.join(offenders))


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
