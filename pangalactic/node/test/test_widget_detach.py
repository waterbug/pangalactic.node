# -*- coding: utf-8 -*-
"""
Tests for the widget "detach" idiom.

`parent` is a *method* on QWidget, not a writable property, so the idiom that
used to be spread across this package --

    widget.parent = None            # intended: widget.setParent(None)

-- detached nothing.  PyQt allows the assignment, which simply shadows the
bound method on that instance.  Two consequences: the widget stayed a child of
its Qt parent, and any later `widget.parent()` call raised
`TypeError: 'NoneType' object is not callable` -- a confusing way to discover
the problem, and a plausible contributor to the "C++ object got deleted" class
of failure that several bare `except:` blocks were written to swallow.

61 sites were converted to `setParent(None)` on 2026-08-02.  See
`pangalaxian_remaining_chunks_review.md` #1.

The first test is the durable one: it is a guard against the idiom coming
back, which is the real risk, since the assignment looks perfectly reasonable
and fails silently.
"""
import os
import re

import pytest
from PyQt5.QtWidgets import QWidget, QLabel, QHBoxLayout

# Modules exempt from the guard, each for a stated reason.  Add to this only
# with a reason -- an unexplained entry defeats the point of the test.
ALLOWED = {
    # Node and FakeRoot subclass plain `object`, so `self.parent` is an
    # ordinary data attribute and nothing is shadowed.
    'systemtree.py',
    # This test deliberately uses the broken idiom in order to test it.
    'test_widget_detach.py',
    # BlockLabel(QGraphicsTextItem) does `self.parent = parent` and then uses
    # `self.parent` as data in four places.  It is the same shadowing -- it
    # hides QObject.parent() -- but unlike the sites fixed on 2026-08-02 it is
    # not a failed *detach*: the real parent is set correctly by
    # super().__init__(parent=parent) first, and the attribute works as
    # intended.  Nothing calls parent() on a BlockLabel today, so it is latent.
    # Fixing it means renaming the attribute (e.g. to parent_item) across its
    # four uses in a diagram class that has no automated coverage -- a separate
    # change, deliberately not bundled with the mechanical conversion.
    'shapes.py',
    }

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDIOM = re.compile(r'\.parent\s*=\s*(?!=)')


def _python_files():
    for dirpath, dirnames, filenames in os.walk(PKG):
        dirnames[:] = [d for d in dirnames if d != '__pycache__']
        for fn in filenames:
            if fn.endswith('.py'):
                yield os.path.join(dirpath, fn)


def test_01_parent_assignment_idiom_is_not_reintroduced():
    """CASE: no QWidget in the package assigns to `.parent`

    Assigning to `.parent` shadows QWidget.parent() and silently does not
    detach.  This is the guard against it coming back; if a new legitimate
    plain-object use appears, add its module to ALLOWED with a note.
    """
    offenders = []
    for path in _python_files():
        if os.path.basename(path) in ALLOWED:
            continue
        with open(path, encoding='utf-8') as f:
            for n, line in enumerate(f, 1):
                code = line.split('#')[0]
                if IDIOM.search(code):
                    offenders.append(f'{os.path.relpath(path, PKG)}:{n}: '
                                     f'{line.strip()}')
    assert not offenders, (
        'assignment to `.parent` found -- use setParent(None):\n  '
        + '\n  '.join(offenders))


def test_02_attribute_assignment_does_not_detach(qtbot):
    """CASE: `.parent = None` leaves the widget parented (the bug)"""
    page = QWidget()
    qtbot.addWidget(page)
    box = QHBoxLayout(page)
    w = QLabel('x')
    box.addWidget(w)
    assert QWidget.parent(w) is page

    w.hide()
    box.removeWidget(w)
    w.parent = None                      # the old idiom

    # read the real parent, since `.parent` is now shadowed and cannot be
    # trusted to report on itself
    assert QWidget.parent(w) is page, 'expected the detach NOT to happen'


def test_03_setparent_none_actually_detaches(qtbot):
    """CASE: setParent(None) does what the old idiom intended"""
    page = QWidget()
    qtbot.addWidget(page)
    box = QHBoxLayout(page)
    w = QLabel('x')
    box.addWidget(w)
    assert QWidget.parent(w) is page

    w.hide()
    box.removeWidget(w)
    w.setParent(None)

    assert QWidget.parent(w) is None
    assert w.parent() is None            # and the method still works


def test_04_shadowed_parent_breaks_later_calls(qtbot):
    """CASE: the second consequence -- `widget.parent()` raises

    This is why the idiom is worse than a no-op:  it plants a TypeError in
    any code that later asks the widget who its parent is.
    """
    w = QLabel('x')
    qtbot.addWidget(w)
    assert w.parent() is None            # callable before

    w.parent = None
    with pytest.raises(TypeError):
        w.parent()                       # not callable after


def _teardown_and_rebuild(qtbot, detach, retain):
    """rqtwizard initializePage pattern: hide, removeWidget, detach, rebuild.

    `retain` models something else holding a reference to the torn-down
    widget -- a signal connection, a container, another attribute.
    """
    page = QWidget()
    qtbot.addWidget(page)
    box = QHBoxLayout(page)
    kept = []
    w = None
    for i in range(5):
        if w is not None:
            w.hide()
            box.removeWidget(w)
            detach(w)
        w = QLabel(f'v{i}')
        if retain:
            kept.append(w)
        box.addWidget(w)
    page._kept = kept                      # keep them alive for the assertion
    return len([c for c in page.children() if isinstance(c, QLabel)])


def _old(w):
    w.parent = None


def _new(w):
    w.setParent(None)


def test_05_without_another_reference_refcounting_hides_the_bug(qtbot):
    """CASE: nothing else holds a reference -- both idioms look identical

    Worth pinning, because it is why the idiom survived so long.  After
    `removeWidget` PyQt hands ownership back to Python, so rebinding the
    attribute drops the last reference and the widget is destroyed --
    whether or not the "detach" did anything.  There is no leak in this
    case, and the broken idiom is invisible.
    """
    assert _teardown_and_rebuild(qtbot, _old, retain=False) == 1
    assert _teardown_and_rebuild(qtbot, _new, retain=False) == 1


def test_06_with_another_reference_the_old_idiom_leaves_them_parented(qtbot):
    """CASE: something else holds a reference -- the idioms diverge

    This is when the detach actually has to work.  With the old idiom every
    torn-down widget stays a child of the page: invisible, but alive and
    still owned by the page.  With setParent(None) only the current one
    remains.
    """
    assert _teardown_and_rebuild(qtbot, _old, retain=True) == 5
    assert _teardown_and_rebuild(qtbot, _new, retain=True) == 1
