# -*- coding: utf-8 -*-
"""
Tests for BlockLabel, after removing its shadowing of Qt methods.

`BlockLabel` is a `QGraphicsTextItem`, so `parent`, `x` and `y` are all
*methods* on it.  Its `__init__` used to do

    self.parent = parent
    self.x = x or 0
    self.y = y or 0

each of which shadows the method on that instance, so a later `self.parent()`,
`self.x()` or `self.y()` raises `TypeError: 'X' object is not callable`.

Unlike the `.parent = None` sites fixed on 2026-08-02, these were not failed
*detaches* -- the real parent was set correctly by
`super().__init__(parent=parent)` first, and the attributes were used as data.
So it worked, and was latent rather than live: nothing called those methods on
a BlockLabel.

Found by the guard in test_widget_detach.py, which is why that guard exists.
"""
import pytest

from PyQt5.QtWidgets import QGraphicsRectItem, QGraphicsScene

from pangalactic.node.diagrams.shapes import BlockLabel


@pytest.fixture
def scene(qtbot):
    """A scene with a rectangular parent item to hang labels on."""
    sc = QGraphicsScene()
    parent = QGraphicsRectItem(0, 0, 300, 120)
    sc.addItem(parent)
    return sc, parent


def test_01_qt_methods_are_not_shadowed(scene, qtbot):
    """CASE: parent(), x() and y() are still callable on the instance"""
    sc, parent = scene
    label = BlockLabel('Widget', parent)

    # each of these raised TypeError when the attributes shadowed them
    assert callable(label.parent)
    assert callable(label.x)
    assert callable(label.y)
    label.parent()
    label.x()
    label.y()


def test_02_parent_item_is_set(scene, qtbot):
    """CASE: the label is parented to the item it was given

    Note this held before the change too -- super().__init__(parent=parent)
    did the real work, and the shadowing attribute was only a duplicate.
    """
    sc, parent = scene
    label = BlockLabel('Widget', parent)
    assert label.parentItem() is parent


def test_03_label_is_centred_on_its_parent_by_default(scene, qtbot):
    """CASE: with no explicit x/y, the label centres on the parent"""
    sc, parent = scene
    label = BlockLabel('Widget', parent)

    pr = parent.boundingRect()
    br = label.boundingRect()
    assert label.x() == pytest.approx(pr.center().x() - br.width() / 2)
    assert label.y() == pytest.approx(pr.center().y() - br.height() / 2)


def test_04_explicit_offsets_override_centring(scene, qtbot):
    """CASE: x= and y= place the label explicitly

    These are the values that used to be stored as self.x / self.y, and are
    now self.x_pos / self.y_pos.
    """
    sc, parent = scene
    label = BlockLabel('Widget', parent, x=17, y=23)
    assert label.x() == pytest.approx(17)
    assert label.y() == pytest.approx(23)


def test_05_set_text_can_be_called_again(scene, qtbot):
    """CASE: re-setting the text re-positions without a stale parent

    set_text() reads self.parentItem() rather than a stored attribute, so it
    stays correct even if the parent is changed afterwards -- which an
    attribute would not.
    """
    sc, parent = scene
    label = BlockLabel('Widget', parent, x=5, y=6)

    other = QGraphicsRectItem(0, 0, 400, 200)
    sc.addItem(other)
    label.setParentItem(other)
    label.set_text('Renamed')

    assert label.parentItem() is other
    assert label.x() == pytest.approx(5)
    assert label.y() == pytest.approx(6)
