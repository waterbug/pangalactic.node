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

from PyQt5.QtCore import QEventLoop, Qt
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                             QDialogButtonBox, QFileDialog, QFormLayout,
                             QHBoxLayout, QLabel, QPushButton, QRadioButton,
                             QTableWidget, QTableWidgetItem, QVBoxLayout)

from pangalactic.node.dialogs import OptionNotification, ProgressDialog
from pangalactic.node.threads import Worker, threadpool

from pydispatch import dispatcher

from pangalactic.core import orb, state
from pangalactic.node.step_plan import (ACU, CREATE, MATCHED, NEW, PLACE,
                                        PLACEMENT, PRODUCT, REUSED, UNMATCHED,
                                        UNPLACED, apply_creation,
                                        apply_placements, file_has_changed,
                                        get_correspondence, plan_creation,
                                        plan_placements, product_key,
                                        set_correspondence)

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


# ---------------------------------------------------------------------------
# Progress reporting.
#
# A STEP import takes long enough on a real assembly to look like a hang:
# reading the file is a single blocking call into OCC that can run for many
# seconds, and applying the plan creates a few objects per component.  So the
# work is reported in two ways, according to what can be known about it:
#
#   * reading -- a busy indicator, driven from a worker thread.  OCC gives no
#     way to ask how far through the file it is, and running it on the GUI
#     thread would freeze even an animated bar, so it goes to the threadpool
#     and a nested event loop waits for it.  This keeps run_step_import()
#     synchronous, which is what its callers expect.
#   * applying -- a real progress bar.  Here the work is a loop over known
#     items, so the fraction done is honest.  This stays on the GUI thread:
#     it creates objects, and the orb's SQLAlchemy session belongs to the
#     thread that made it.
# ---------------------------------------------------------------------------

def _busy_dialog(title, label, parent=None):
    """
    A modal dialog with an indeterminate ("busy") progress bar.

    Args:
        title (str):  window title
        label (str):  what is being waited for

    Keyword Args:
        parent (QWidget):  parent widget

    Returns:
        ProgressDialog
    """
    # NOTE: constructed with maximum=1, not 0.  ProgressDialog sets the value
    # to 0 in its constructor, and a QProgressDialog whose value has reached
    # its maximum closes itself -- so a maximum of 0 would close the dialog
    # as it was built.  The range is made indeterminate afterwards, with
    # auto-close and auto-reset off.
    dlg = ProgressDialog(title=title, label=label, maximum=1, parent=parent)
    dlg.setAutoClose(False)
    dlg.setAutoReset(False)
    dlg.setRange(0, 0)
    dlg.show()
    return dlg


def _run_busy(fn, *args, title='Working', label='working ...', parent=None):
    """
    Run `fn` on the threadpool while a busy dialog is shown, and wait for it.

    The wait is a nested event loop rather than a blocking join, so the dialog
    paints and its bar animates while the work runs.

    Args:
        fn (callable):  the function to run.  It must not touch the orb --
            the database session belongs to the GUI thread.
        args:  positional arguments for `fn`

    Keyword Args:
        title (str):  window title for the dialog
        label (str):  what is being waited for
        parent (QWidget):  parent widget

    Returns:
        tuple:  (result, error), where error is the (exctype, value,
        traceback) tuple emitted by the Worker, or None if `fn` returned.
    """
    dlg = _busy_dialog(title, label, parent=parent)
    out = {}
    loop = QEventLoop()
    worker = Worker(fn, *args)
    worker.signals.result.connect(lambda r: out.__setitem__('result', r))
    worker.signals.error.connect(lambda e: out.__setitem__('error', e))
    worker.signals.progress.connect(
                    lambda what, n: what and dlg.setLabelText(what))
    worker.signals.finished.connect(loop.quit)
    threadpool.start(worker)
    loop.exec_()
    dlg.close()
    return out.get('result'), out.get('error')


def _read_step_file(path, progress_signal=None):
    """
    Check a STEP file's external references and read its assembly.

    Run on a worker thread by `_run_busy`, so it touches only the file and
    OCC -- no orb, no Qt widgets.  The two steps are done together because
    the first decides whether the second is worth doing.

    Args:
        path (str):  path to the STEP file

    Keyword Args:
        progress_signal (pyqtSignal):  supplied by Worker; used to say which
            step is running

    Returns:
        tuple:  (missing, root), where `missing` is the list of unresolved
        external references -- if it is non-empty, `root` is None and the
        file was not read.
    """
    # already imported by run_step_import on the GUI thread, so this is a
    # dict lookup rather than a first import of pythonocc in a worker thread
    from pangalactic.node.step_import import (missing_references,
                                              read_assembly)
    if progress_signal is not None:
        progress_signal.emit('checking for referenced files ...', 0)
    missing = missing_references(path)
    if missing:
        return missing, None
    if progress_signal is not None:
        progress_signal.emit('reading assembly ...', 0)
    return [], read_assembly(path)


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
    CONFIRM, KIND, STATUS, PATH, TYPE, NOTE = range(6)
    HEADERS = ['', 'kind', 'status', 'in the assembly', 'product type',
              'note']

    def __init__(self, items, mode, file_name='', project=None, parent=None):
        """
        Args:
            items (list of PlanItem):  the plan, from step_plan
            mode (str):  PLACE or CREATE

        Keyword Args:
            file_name (str):  name of the file being imported, for the title
            project (Project):  the current project.  In CREATE mode, offers
                to make the imported assembly a system of it.
            parent (QWidget):  parent widget
        """
        super().__init__(parent)
        self.items = items
        self.mode = mode
        # product types offered in the TYPE column, sorted for a stable menu
        self.product_types = sorted(orb.get_by_type('ProductType'),
                                    key=lambda pt: pt.name or pt.id)
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
        # rows are selected in groups so that a type can be set on many at
        # once -- see the bulk assignment row below
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        # {row: combo} for the rows that have a product type to set; only
        # new products do, so this is also the test for "is this such a row"
        self.type_combos = {}
        for row, item in enumerate(items):
            self._fill_row(row, item)
        self.table.resizeColumnsToContents()
        self.table.itemChanged.connect(self.on_item_changed)
        layout.addWidget(self.table)

        # CREATE only:  without a ProjectSystemUsage the imported assembly
        # exists but does not appear in the System Tree, which is where a
        # user looks for it first
        self.add_system_checkbox = None
        if mode == CREATE and project is not None:
            root = next((i for i in items
                         if i.kind == PRODUCT and i.is_root), None)
            if root is not None:
                self.add_system_checkbox = QCheckBox(
                    f'Add "{root.path}" to project {project.id} as a system',
                    self)
                self.add_system_checkbox.setChecked(True)
                self.add_system_checkbox.setToolTip(
                    'Creates a ProjectSystemUsage, so the assembly appears '
                    'in the System Tree.  Without it the assembly is still '
                    'created, but is reachable only through the Hardware '
                    'Library.')
                layout.addWidget(self.add_system_checkbox)

        # CREATE only:  setting the type one row at a time is unworkable on
        # a real assembly -- a file with fifty new parts means fifty trips
        # through a combo box.  STEP says nothing about product types, so
        # every new product arrives "unclassified" and the whole column has
        # to be set by hand.
        self.type_combo = None
        self.select_all_checkbox = None
        if self.type_combos:
            # Selecting rows one at a time is the same tedium the bulk
            # assignment was added to remove, so:  one checkbox to select
            # everything, then Ctrl-click the few to leave out.  Follows the
            # Disciplines panel of ProductFilterDialog -- same label, and
            # connected to "clicked" rather than "toggled" so that keeping it
            # in step with the selection below does not re-fire it.
            self.select_all_checkbox = QCheckBox(
                                    'SELECT ALL / CLEAR SELECTIONS', self)
            self.select_all_checkbox.clicked.connect(self.on_select_all)
            layout.addWidget(self.select_all_checkbox)

            type_row = QHBoxLayout()
            type_row.addWidget(QLabel('Set product type:', self))
            self.type_combo = QComboBox(self)
            for pt in self.product_types:
                self.type_combo.addItem(pt.name or pt.id, pt)
            type_row.addWidget(self.type_combo)
            self.apply_selected_button = QPushButton('Apply to selected',
                                                     self)
            self.apply_selected_button.clicked.connect(
                                            self.on_apply_type_to_selected)
            self.apply_selected_button.setEnabled(False)
            type_row.addWidget(self.apply_selected_button)
            apply_all_button = QPushButton('Apply to all', self)
            apply_all_button.setToolTip(
                'Set the type of every new product in this import.')
            apply_all_button.clicked.connect(self.on_apply_type_to_all)
            type_row.addWidget(apply_all_button)
            type_row.addStretch(1)
            layout.addLayout(type_row)
            self.table.itemSelectionChanged.connect(
                                            self.on_table_selection_changed)
            # set the button's initial enabled state and tooltip from the
            # (empty) selection, rather than duplicating them here
            self.on_table_selection_changed()

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

    # NOTE: cells are selectable but not editable.  Selectable because rows
    # are how a type is applied to more than one product at a time; the
    # values themselves are set through the checkbox and the combo box, not
    # by typing into the table, which is what NoEditTriggers enforces.
    #
    # This was worth making explicit.  Without ItemIsSelectable the only
    # selectable rows were the new products -- not by intent, but because
    # their type cell holds a combo box and therefore no item at all, and a
    # cell with no item takes the model's default flags, which include
    # selectable.  Right answer, entirely by accident, and it would have
    # stopped being right the moment anyone gave that cell an item.
    CELL_FLAGS = Qt.ItemIsSelectable | Qt.ItemIsEnabled

    def _fill_row(self, row, item):
        confirm = QTableWidgetItem()
        if item.actionable:
            confirm.setFlags(self.CELL_FLAGS | Qt.ItemIsUserCheckable)
            confirm.setCheckState(Qt.Checked if item.confirmed
                                  else Qt.Unchecked)
        else:
            # nothing to confirm:  this row is telling the user what the
            # import leaves alone
            confirm.setFlags(self.CELL_FLAGS)
        self.table.setItem(row, self.CONFIRM, confirm)
        for col, text in ((self.KIND, KIND_TEXT.get(item.kind, item.kind)),
                          (self.STATUS, STATUS_TEXT.get(item.status,
                                                        item.status)),
                          (self.PATH, item.path),
                          (self.NOTE, item.note)):
            cell = QTableWidgetItem(text)
            cell.setFlags(self.CELL_FLAGS)
            if col == self.STATUS and item.status in STATUS_COLOR:
                cell.setForeground(QBrush(QColor(STATUS_COLOR[item.status])))
            self.table.setItem(row, col, cell)
        self._fill_type_cell(row, item)

    def _fill_type_cell(self, row, item):
        """
        Give a new product a combo box to assign its type, since STEP carries
        nothing that implies one -- the plan proposes "unclassified" and this
        is where the importing user replaces it with a real one, per item.

        Every other row gets a plain, non-editable cell:  a REUSED product's
        type belongs to the product already in the repository, and importing
        must not appear to offer changing it here.
        """
        if item.kind == PRODUCT and item.status == NEW:
            combo = QComboBox(self.table)
            current = 0
            for i, pt in enumerate(self.product_types):
                combo.addItem(pt.name or pt.id, pt)
                if item.product_type is not None and pt.oid == \
                   item.product_type.oid:
                    current = i
            combo.setCurrentIndex(current)
            combo.currentIndexChanged.connect(
                lambda idx, item=item, combo=combo:
                    setattr(item, 'product_type', combo.itemData(idx)))
            self.table.setCellWidget(row, self.TYPE, combo)
            self.type_combos[row] = combo
        else:
            text = (getattr(item.product, 'product_type', None) and
                   item.product.product_type.name) or ''
            cell = QTableWidgetItem(text)
            cell.setFlags(self.CELL_FLAGS)
            self.table.setItem(row, self.TYPE, cell)

    def selected_rows(self):
        """
        The rows the user has selected, as a sorted list of row numbers.
        """
        return sorted({idx.row() for idx in self.table.selectedIndexes()})

    def on_select_all(self):
        """
        Select every row, or clear the selection.

        Selects *all* rows rather than only the ones that can take a type.
        A "select all" that quietly selected a subset would look like a bug,
        and there is no need for it to be clever:  apply_type_to_rows()
        skips the rows that have no type to set, so taking in the usages and
        placements costs nothing.
        """
        if self.select_all_checkbox is None:
            return
        if self.select_all_checkbox.isChecked():
            self.table.selectAll()
        else:
            self.table.clearSelection()

    def on_table_selection_changed(self):
        """
        Keep the two selection controls honest about what a selection will
        do:  "Apply to selected" is enabled only when the selection holds a
        row whose type can be set, and says how many of them there are --
        which is what tells a user that selecting the usages as well has no
        effect, rather than leaving them to deselect those by hand.
        """
        button = getattr(self, 'apply_selected_button', None)
        if button is None:
            return
        rows = self.selected_rows()
        settable = [row for row in rows if row in self.type_combos]
        button.setEnabled(bool(settable))
        n = len(settable)
        if n:
            s = '' if n == 1 else 's'
            button.setToolTip(f'Set the type of the {n} selected new '
                              f'product{s}.  Rows with no type to set -- '
                              'usages, placements, products that will be '
                              'reused -- are skipped, so there is no need to '
                              'leave them out of the selection.')
        else:
            button.setToolTip(
                'Select one or more new products to set their type.  Select '
                'rows by clicking, and extend the selection with Shift or '
                'Ctrl.')
        # the box reflects the selection when it is changed by other means,
        # so it never claims everything is selected when it is not
        if self.select_all_checkbox is not None:
            self.select_all_checkbox.setChecked(
                                    len(rows) == self.table.rowCount())

    def apply_type_to_rows(self, rows):
        """
        Set the product type of the given rows to the one now chosen in the
        bulk combo box.

        Rows without a type to set -- usages, placements, reused products --
        are skipped rather than refused, so that a selection dragged across
        the table does what the user means by it.

        The row combo is what is changed, not the PlanItem directly:  it is
        what the user sees, and changing it fires the signal that carries the
        value to the item, so the two cannot drift apart.

        Args:
            rows (list of int):  row numbers

        Returns:
            int:  how many rows were set
        """
        if self.type_combo is None:
            return 0
        index = self.type_combo.currentIndex()
        n = 0
        for row in rows:
            combo = self.type_combos.get(row)
            # both combos are built from self.product_types in the same
            # order, so the index carries across
            if combo is not None and 0 <= index < combo.count():
                combo.setCurrentIndex(index)
                n += 1
        return n

    def on_apply_type_to_selected(self):
        n = self.apply_type_to_rows(self.selected_rows())
        orb.log.debug(f'* step plan: type applied to {n} selected row(s).')

    def on_apply_type_to_all(self):
        n = self.apply_type_to_rows(sorted(self.type_combos))
        orb.log.debug(f'* step plan: type applied to all {n} new product(s).')

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
    # dialogs does not pull in pythonocc.  Imported for its side effect, and
    # on the GUI thread:  _read_step_file is what actually calls into it, and
    # that runs on a worker thread -- pythonocc's first import should not
    # happen there.
    from pangalactic.node import step_import       # noqa: F401

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

    # A file that names other files needs them beside it:  a STEP reader
    # resolves each reference relative to the file that makes it.  Stop
    # rather than import, because the alternative is silent -- OCC does not
    # follow the references, so the assembly would arrive with its
    # subassemblies empty and nothing would say so.
    #
    # NOTE: the user is not assumed to have exported the file -- they may
    # well have received it -- so the message says where the missing files
    # come from and what they must be called, rather than implying they
    # should already have them.  See NOTES_ON_STEP_EXTERNAL_REFS.md.
    (read_result, read_error) = _run_busy(
                        _read_step_file, path,
                        title='Reading STEP File',
                        label=f'reading "{file_name}" ...',
                        parent=parent)
    if read_error is not None:
        exctype, value, tb = read_error
        orb.log.error(f'* step import: could not read "{path}": {value}')
        orb.error_log.info(tb)
        dlg = OptionNotification('STEP import failed',
                                 f'"{file_name}" could not be read:'
                                 f'<br>{value}',
                                 parent=parent)
        dlg.exec_()
        return None
    missing, root = read_result
    if missing:
        orb.log.info(f'  - step: {len(missing)} referenced file(s) missing.')
        lines = ''.join(
            f'<br>&nbsp;&nbsp;<b>{name}</b>, referenced by '
            f'{os.path.basename(referrer)}'
            for name, referrer in missing[:10])
        more = ('<br>&nbsp;&nbsp;... and %d more'
                % (len(missing) - 10)) if len(missing) > 10 else ''
        dlg = OptionNotification(
                'Referenced files are missing',
                f'"{file_name}" is part of a set:  it refers to files '
                f'that are not beside it.{lines}{more}<br><br>The import '
                'cannot continue without them.  They come from wherever this '
                'file came from, and must be placed in the same directory '
                'under exactly these names -- that is how a STEP reader '
                'finds them.',
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

    project = orb.get(state.get('project'))
    plan_dlg = StepPlanDialog(items, mode, file_name=file_name,
                              project=project, parent=parent)
    if not plan_dlg.exec_():
        return None

    apply_progress = ProgressDialog(title='Importing',
                                    label=f'importing "{file_name}" ...',
                                    maximum=1, parent=parent)
    apply_progress.setAttribute(Qt.WA_DeleteOnClose)

    def on_progress(done, total):
        # setMaximum before setValue, and one more than the total:  a
        # QProgressDialog whose value reaches its maximum closes itself, and
        # there is still saving to do after the last item
        apply_progress.setMaximum(total + 1)
        apply_progress.setValue(done)

    # try/finally because the dialog is modal and has no cancel button:  left
    # open by an exception on the way through, it would lock the window
    try:
        if mode == PLACE:
            result = apply_placements(items, progress=on_progress)
        else:
            # NOTE: deliberately not passing an owner.  clone() defaults it
            # to the current project, which is what a newly imported
            # specification should belong to; taking it from the selected
            # assembly would put the new specs wherever that happened to
            # live -- PGANA, for a library item -- which is the opposite of
            # project-owned by default.
            add_system = (plan_dlg.add_system_checkbox is not None and
                          plan_dlg.add_system_checkbox.isChecked())
            result = apply_creation(items,
                                    project=project if add_system else None,
                                    progress=on_progress)
        apply_progress.setLabelText('saving ...')
        if result.objects:
            orb.save(result.objects)
        # The local half of the import ends here;  the repository's half is
        # only starting.  Say so before handing the objects over, because
        # dispatching them calls vger.save() synchronously from here -- the
        # indicator has to exist before the answer can arrive.
        n = len(result.objects)
        if n:
            plural = '' if n == 1 else 's'
            dispatcher.send(signal='repo save pending',
                            oids=[o.oid for o in result.objects],
                            msg=f'The import is saved on this computer.\n\n'
                                f'Sending {n} item{plural} to the repository '
                                '-- '
                                'this continues on the server, and you will '
                                'be told when it is done.')
        if result.created:
            dispatcher.send(signal='new objects', objs=result.created)
        if result.modified:
            dispatcher.send(signal='modified objects', objs=result.modified)
        if rep_file is not None:
            set_correspondence(rep_file, result, mode,
                               checksum=_checksum(path))
        elif mode == CREATE:
            apply_progress.setLabelText('storing the STEP file ...')
            _register_step_model(path, items, result, parent=parent)
    finally:
        apply_progress.close()
    orb.log.info(f'* step import: {result!r}')
    return result


# the ModelType a STEP file is a representation of
MCAD_MODEL_TYPE_OID = 'pgefobjects:ModelType.MCAD'

# STEP AP203/214/242 part 21 files
STEP_MIME_TYPE = 'application/step'


def _register_step_model(path, items, result, parent=None):
    """
    Give the imported assembly an MCAD Model of it, with a
    RepresentationFile for the STEP file, and upload the file.

    Rather than building those objects here, this sends the same
    "add update model" signal that `ModelImportDialog` sends, so an imported
    STEP model is created by exactly the path that a hand-attached one is:
    `vger.add_update_model()` makes the Model and the RepresentationFile,
    assigns the vault file name, publishes them on the owner's channel, and
    the client then uploads the file.  Duplicating that here would mean a
    second implementation of the vault naming, which belongs on the server.

    The correspondence cannot be stored yet:  it hangs off the
    RepresentationFile, which does not exist until the rpc returns.  It is
    left in `state` for `on_model_added()` to write once the object arrives.

    Args:
        path (str):  the STEP file that was imported
        items (list of PlanItem):  the plan, for finding the root assembly
        result (ImportResult):  what the import did

    Keyword Args:
        parent (QWidget):  parent widget, for any error dialog
    """
    root_items = [i for i in items
                  if i.kind == PRODUCT and getattr(i, 'is_root', False)]
    assembly = None
    for item in root_items:
        # NOTE: product entries are keyed on the prototype, not on the
        # display path -- prototype names are not unique.  See
        # step_plan.product_key().
        oid = result.mapping.get(product_key(item))
        assembly = orb.get(oid) if oid else None
        if assembly is not None:
            break
    if assembly is None:
        orb.log.debug('  - step: no root assembly; no model registered.')
        return
    if not state.get('connected'):
        # add_update_model is an rpc; offline there is nothing to call.  The
        # assembly and its placements are already saved and will sync, but
        # the STEP file itself will not be attached.
        orb.log.info('  - step: not connected; model/file not registered.')
        return
    fname = os.path.basename(path)
    try:
        fsize = os.path.getsize(path)
    except OSError:
        orb.log.error(f'  - step: cannot size "{path}"; not registering.')
        return
    parms = {'file name': fname,
             'file size': str(fsize),
             'mime_type': STEP_MIME_TYPE,
             'name': assembly.name,
             'description': f'STEP model imported from "{fname}"',
             'of_thing_oid': assembly.oid,
             'owner_oid': getattr(assembly.owner, 'oid', '') or '',
             'project_oid': state.get('project') or ''}
    # left for on_model_added(), which is where the RepresentationFile
    # first exists
    state['step_pending_correspondence'] = {
                                'fpath': path,
                                'checksum': _checksum(path),
                                'mode': CREATE,
                                'map': dict(result.mapping)}
    orb.log.info(f'  - step: registering MCAD model of "{assembly.id}"')
    dispatcher.send(signal='add update model',
                    mtype_oid=MCAD_MODEL_TYPE_OID, fpath=path, parms=parms)


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
