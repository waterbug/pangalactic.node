# -*- coding: utf-8 -*-
"""
Dialogs for importing a STEP assembly file.

Two steps, in this order, because the mode decides what the plan means:

1. `StepImportModeDialog` -- pick the file and the mode.
2. `StepPlanDialog` -- review what the import will do, item by item, and
   confirm it.

These are presenters.  What an import *does* is decided by
`pangalactic.node.step_plan`, which has no Qt in it and is tested without a
dialog; nothing here should acquire logic about matching or creating.
"""
import os

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox,
                             QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                             QPushButton, QRadioButton, QTableWidget,
                             QTableWidgetItem, QVBoxLayout)

from pangalactic.node.dialogs import OptionNotification

from pydispatch import dispatcher

from pangalactic.core import orb, state
from pangalactic.node.step_plan import (ACU, CREATE, MATCHED, NEW, PLACE,
                                        PLACEMENT, PRODUCT, REUSED, UNMATCHED,
                                        UNPLACED, apply_creation,
                                        apply_placements, file_has_changed,
                                        get_correspondence, plan_creation,
                                        plan_placements, set_correspondence)

# how each status reads to a user, and how it is coloured.  UNMATCHED and
# UNPLACED are informational:  they say what the import will *not* cover,
# which matters as much as what it will.
STATUS_TEXT = {
    MATCHED:   'matched',
    UNMATCHED: 'no such component',
    UNPLACED:  'not in the file',
    NEW:       'create',
    REUSED:    'use existing',
    }

STATUS_COLOR = {
    MATCHED:   '#1a7f37',    # green -- will be placed
    NEW:       '#0969da',    # blue  -- will be created
    REUSED:    '#0969da',
    UNMATCHED: '#9a6700',    # amber -- nothing will happen
    UNPLACED:  '#9a6700',
    }

KIND_TEXT = {PLACEMENT: 'placement', PRODUCT: 'product', ACU: 'usage'}


class StepImportModeDialog(QDialog):
    """
    Pick the STEP file and the import mode.

    The mode is chosen before the import begins because it decides what the
    plan means:  placing an assembly that exists, or creating one that does
    not.
    """

    def __init__(self, assembly=None, parent=None):
        """
        Keyword Args:
            assembly (Product):  the assembly to place, if there is one
                selected.  Without it, placing is not offered.
            parent (QWidget):  parent widget
        """
        super().__init__(parent)
        self.setWindowTitle('Import a STEP Assembly')
        self.assembly = assembly
        self.file_path = ''
        layout = QVBoxLayout(self)

        file_row = QHBoxLayout()
        self.file_label = QLabel('[no file selected]', self)
        browse = QPushButton('Select STEP file ...', self)
        browse.clicked.connect(self.on_browse)
        file_row.addWidget(browse)
        file_row.addWidget(self.file_label, stretch=1)
        layout.addLayout(file_row)

        form = QFormLayout()
        name = getattr(assembly, 'name', None)
        self.place_button = QRadioButton(
            f'Place the components of "{name}"' if name
            else 'Place the components of an existing assembly', self)
        self.place_button.setToolTip(
            'Match the file\'s occurrences to the components this assembly '
            'already has, and record where each one sits.  No products are '
            'created.')
        self.create_button = QRadioButton(
            'Create products and assembly structure from the file', self)
        self.create_button.setToolTip(
            'Propose a product for each distinct part in the file and a '
            'usage for each occurrence of one.  For a design that exists '
            'only in CAD.')
        if assembly is None:
            self.place_button.setEnabled(False)
            self.place_button.setToolTip(
                'Select an assembly first to place its components.')
            self.create_button.setChecked(True)
        else:
            self.place_button.setChecked(True)
        form.addRow(self.place_button)
        form.addRow(self.create_button)
        layout.addLayout(form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal,
            self)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._update_ok()

    @property
    def mode(self):
        """
        The chosen mode:  PLACE or CREATE.
        """
        return PLACE if self.place_button.isChecked() else CREATE

    def _update_ok(self):
        """
        Nothing can be imported without a file, so Ok stays disabled until
        one is chosen.
        """
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(
                                                    bool(self.file_path))

    def on_browse(self):
        """
        Select the STEP file, starting where the last one was found.
        """
        start = state.get('last_step_path') or orb.home
        fpath, _ = QFileDialog.getOpenFileName(
            self, 'Select a STEP file', start,
            'STEP Files (*.stp *.step *.STP *.STEP);;All Files (*)')
        if fpath:
            self.file_path = fpath
            state['last_step_path'] = os.path.dirname(fpath)
            self.file_label.setText(os.path.basename(fpath))
        self._update_ok()


class StepPlanDialog(QDialog):
    """
    Review a STEP import, item by item, before anything is created or moved.

    Every row that would change something carries a checkbox.  Rows that
    would not -- an occurrence with no matching component, a component the
    file says nothing about -- are shown without one, because they are
    reported rather than applied.
    """

    # columns
    CONFIRM, KIND, STATUS, PATH, NOTE = range(5)
    HEADERS = ['', 'kind', 'status', 'in the assembly', 'note']

    def __init__(self, items, mode, file_name='', parent=None):
        """
        Args:
            items (list of PlanItem):  the plan, from step_plan
            mode (str):  PLACE or CREATE

        Keyword Args:
            file_name (str):  name of the file being imported, for the title
            parent (QWidget):  parent widget
        """
        super().__init__(parent)
        self.items = items
        self.mode = mode
        what = ('Place components' if mode == PLACE
                else 'Create products and structure')
        self.setWindowTitle(f'{what} from {file_name}' if file_name else what)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self._summary(), self))

        self.table = QTableWidget(len(items), len(self.HEADERS), self)
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        for row, item in enumerate(items):
            self._fill_row(row, item)
        self.table.resizeColumnsToContents()
        self.table.itemChanged.connect(self.on_item_changed)
        layout.addWidget(self.table)

        button_row = QHBoxLayout()
        accept_all = QPushButton('Accept all', self)
        accept_all.clicked.connect(lambda: self.set_all(True))
        reject_all = QPushButton('Reject all', self)
        reject_all.clicked.connect(lambda: self.set_all(False))
        button_row.addWidget(accept_all)
        button_row.addWidget(reject_all)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal,
            self)
        self.buttons.button(QDialogButtonBox.Ok).setText('Import')
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _summary(self):
        """
        One line saying what the plan amounts to, so the count is visible
        without reading the table.
        """
        actionable = [i for i in self.items if i.actionable]
        skipped = len(self.items) - len(actionable)
        if self.mode == PLACE:
            text = f'{len(actionable)} components to place'
        else:
            products = len([i for i in actionable if i.kind == PRODUCT])
            usages = len([i for i in actionable if i.kind == ACU])
            text = f'{products} products, {usages} usages'
        if skipped:
            text += f'; {skipped} item(s) this import does not cover'
        return text

    def _fill_row(self, row, item):
        confirm = QTableWidgetItem()
        if item.actionable:
            confirm.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            confirm.setCheckState(Qt.Checked if item.confirmed
                                  else Qt.Unchecked)
        else:
            # nothing to confirm:  this row is telling the user what the
            # import leaves alone
            confirm.setFlags(Qt.ItemIsEnabled)
        self.table.setItem(row, self.CONFIRM, confirm)
        for col, text in ((self.KIND, KIND_TEXT.get(item.kind, item.kind)),
                          (self.STATUS, STATUS_TEXT.get(item.status,
                                                        item.status)),
                          (self.PATH, item.path),
                          (self.NOTE, item.note)):
            cell = QTableWidgetItem(text)
            cell.setFlags(Qt.ItemIsEnabled)
            if col == self.STATUS and item.status in STATUS_COLOR:
                cell.setForeground(QBrush(QColor(STATUS_COLOR[item.status])))
            self.table.setItem(row, col, cell)

    def on_item_changed(self, cell):
        """
        Keep the plan in step with the checkboxes.  The dialog holds the
        actual PlanItem objects, so confirming here is what apply_* will act
        on.
        """
        if cell.column() != self.CONFIRM:
            return
        row = cell.row()
        if 0 <= row < len(self.items):
            self.items[row].confirmed = (cell.checkState() == Qt.Checked)

    def set_all(self, confirmed):
        """
        Accept or reject every item that can be acted on.  Items that cannot
        are untouched -- "accept all" must not appear to accept something
        that will not happen.
        """
        for row, item in enumerate(self.items):
            if not item.actionable:
                continue
            cell = self.table.item(row, self.CONFIRM)
            cell.setCheckState(Qt.Checked if confirmed else Qt.Unchecked)

    def confirmed_items(self):
        """
        The items the user accepted.
        """
        return [i for i in self.items if i.confirmed and i.actionable]


class StepFileChangedDialog(QDialog):
    """
    Ask what to do when a file differs from the one a stored correspondence
    was built against.

    A re-export may have gained, lost or renamed parts, so re-matching it
    silently could move components that were positioned deliberately.
    """

    def __init__(self, file_name='', imported='', parent=None):
        """
        Keyword Args:
            file_name (str):  the file being imported
            imported (str):  when the stored correspondence was made
            parent (QWidget):  parent widget
        """
        super().__init__(parent)
        self.setWindowTitle('This file has changed')
        msg = (f'<b>"{file_name}" is not the file that was imported')
        msg += f' on {imported}' if imported else ''
        msg += '.</b><br><br>Parts may have been added, removed or renamed '
        msg += 'since then, so the components matched last time may no '
        msg += 'longer be the right ones.<br><br>Re-match it now, and review '
        msg += 'the result before anything is moved?'
        form = QFormLayout(self)
        self.message_label = QLabel(msg, self)
        form.addRow(self.message_label)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal,
            self)
        self.buttons.button(QDialogButtonBox.Ok).setText('Re-match')
        self.buttons.button(QDialogButtonBox.Cancel).setText('Cancel import')
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)


def run_step_import(assembly=None, rep_file=None, parent=None):
    """
    Drive a STEP import from end to end:  choose the file and mode, read it,
    plan, let the user confirm, apply, save.

    Thin by intention.  Every decision it makes is a user's; every decision
    about what an import *means* belongs to `step_plan`.

    Args:
        assembly (Product):  the assembly to place, if one is selected.
            Without it, only creating is offered.
        rep_file (RepresentationFile):  the stored STEP file, if the file
            being imported is one.  Given it, the correspondence is stored
            and a changed file is noticed; without it, the import still
            works but nothing is remembered about it.
        parent (QWidget):  parent widget for the dialogs

    Returns:
        ImportResult or None:  None if the user cancelled at any point, or if
        the file could not be read.
    """
    # imported here rather than at module scope so that importing the
    # dialogs does not pull in pythonocc
    from pangalactic.node.step_import import read_assembly

    mode_dlg = StepImportModeDialog(assembly=assembly, parent=parent)
    if not mode_dlg.exec_():
        return None
    path, mode = mode_dlg.file_path, mode_dlg.mode
    file_name = os.path.basename(path)

    if rep_file is not None and file_has_changed(rep_file,
                                                 _checksum(path)):
        stored = get_correspondence(rep_file)
        changed = StepFileChangedDialog(file_name=file_name,
                                        imported=stored.get('imported', ''),
                                        parent=parent)
        if not changed.exec_():
            return None

    try:
        root = read_assembly(path)
    except Exception as e:
        orb.log.error(f'* step import: could not read "{path}": {e}')
        dlg = OptionNotification('STEP import failed',
                                 f'"{file_name}" could not be read:<br>{e}',
                                 parent=parent)
        dlg.exec_()
        return None

    if mode == PLACE:
        items = plan_placements(root, assembly)
    else:
        items = plan_creation(root)
    if not any(i.actionable for i in items):
        dlg = OptionNotification(
                'Nothing to import',
                f'Nothing in "{file_name}" matches this assembly.',
                parent=parent)
        dlg.exec_()
        return None

    plan_dlg = StepPlanDialog(items, mode, file_name=file_name, parent=parent)
    if not plan_dlg.exec_():
        return None

    if mode == PLACE:
        result = apply_placements(items)
    else:
        result = apply_creation(items, owner=getattr(assembly, 'owner', None))
    if result.objects:
        orb.save(result.objects)
    if result.created:
        dispatcher.send(signal='new objects', objs=result.created)
    if result.modified:
        dispatcher.send(signal='modified objects', objs=result.modified)
    if rep_file is not None:
        set_correspondence(rep_file, result, mode, checksum=_checksum(path))
    orb.log.info(f'* step import: {result!r}')
    return result


def _checksum(path):
    """
    Checksum a STEP file, so a later import can tell whether it is the same
    file.  Returns '' if it cannot be read, which `file_has_changed()` treats
    as "cannot compare" rather than as a change.
    """
    import hashlib
    try:
        with open(path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return ''
