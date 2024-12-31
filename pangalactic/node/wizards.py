# -*- coding: utf-8 -*-
"""
Wizards
"""
import os, re
import pprint
from collections import OrderedDict as OD
from datetime import datetime
from textwrap import wrap

from PyQt5.QtCore import Qt, QItemSelectionModel
from PyQt5.QtGui import QPixmap, QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import (QAbstractItemView, QAction, QApplication,
                             QCheckBox, QFormLayout, QGridLayout, QGroupBox,
                             QHBoxLayout, QLabel, QMenu, QMessageBox,
                             QPushButton, QScrollArea, QSizePolicy, QTableView,
                             QVBoxLayout, QWidget, QWizard, QWizardPage)

from pydispatch import dispatcher

# pangalactic
from pangalactic.core             import orb
from pangalactic.core             import config, state
from pangalactic.core.clone       import clone
from pangalactic.core.meta        import MAIN_VIEWS, SELECTABLE_VALUES
from pangalactic.core.names       import (get_external_name_plural,
                                          PREFERRED_ALIASES, STD_ALIASES,
                                          STD_VIEWS)
from pangalactic.core.parametrics import (de_defz, parm_defz, set_dval,
                                          set_dval_from_str,
                                          set_pval_from_str)
from pangalactic.core.refdata     import trls
from pangalactic.core.utils.datetimes import dtstamp
from pangalactic.core.utils.excelreader import get_raw_excel_data
from pangalactic.core.utils.xlsxreader import get_raw_xlsx_data
from pangalactic.node.buttons     import CheckButtonLabel
from pangalactic.node.dialogs     import ProgressDialog
# from pangalactic.node.dialogs     import NotificationDialog
from pangalactic.node.filters     import FilterPanel
from pangalactic.node.libraries   import LibraryListView
from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.tablemodels import ListTableModel, MappingTableModel
from pangalactic.node.utils       import extract_mime_data
from pangalactic.node.widgets     import (AutosizingListView, ColorLabel,
                                          NameLabel, PlaceHolder, ValueLabel)
from functools import reduce

# data_wizard_state keys:
#   - file_path:         path of input data file
#   - dataset:           input data
#   - dataset_name:      name given to input data
#   - selected_dataset:  data for selected columns
#   - heading_row:       row in input data that contains column names
#   - object_type:       type of objects to be created
#   - column_names:      list containing the selected column names
#   - column_numbers:    list containing the selected column numbers
#   - col_map:           dict mapping column names to object properties
#   - dictified:         list of dicts mapping selected cols to data

data_wizard_state = {}

# new product wizard_state keys:
#   - product
#   - product_oid
#   - trl

wizard_state = {}

dtypes = {
    'str': str,
    'int': int,
    'float': float,
    'bool': bool,
    'datetime': datetime
    }


class PrintLogger:
    def info(self, txt):
        print(txt)
    def debug(self, txt):
        print(txt)


#################################
#  Data Import Wizard Pages
#################################

class DataImportWizard(QWizard):
    """
    Wizard to assist with importing data from a file.

    Keyword Args:
        object_type: class of objects to be created from the data
        file_path: path to the data file
        width: width of the widget
        height: height of the widget
        parent: parent widget
    """
    def __init__(self, object_type='', file_path='', width=1200, height=700,
                 parent=None): 
        super().__init__(parent=parent)
        if not hasattr(orb, 'log'):
            orb.log = PrintLogger()
        orb.log.info('* DataImportWizard')
        # clear the data_wizard_state; otherwise, successive invocations
        # will have state carried over, which would definitely be a bug!
        data_wizard_state.clear()
        data_wizard_state['object_type'] = object_type
        orb.log.info(f'  - object type: {object_type}')
        self.setWizardStyle(QWizard.ClassicStyle)
        # the included buttons must be specified using setButtonLayout in order
        # to get the "Back" button on Windows (it is automatically included on
        # Linux but not on Windows)
        included_buttons = [QWizard.Stretch,
                            QWizard.BackButton,
                            QWizard.NextButton,
                            QWizard.FinishButton,
                            QWizard.CancelButton]
        self.setButtonLayout(included_buttons)
        self.setOptions(QWizard.NoBackButtonOnStartPage)
        data_wizard_state['col_map'] = {}
        data_wizard_state['file_path'] = file_path
        txt = '<h2>You have selected the file<br>'
        txt += f'<font color="green"><b>&lt;{file_path}&gt;</b></font>.<br>'
        txt += 'This wizard will assist in importing data ...</h2>'
        intro_label = QLabel(txt)
        intro_label.setWordWrap(False)
        # first check to see if first row matches standard headers --
        # if so, offer short-cut to ObjectCreationPage ...
        # *********************************************
        # this section lifted from DataSheetPage's init
        fpath = data_wizard_state.get('file_path')
        datasets = {}
        if fpath:
            # import raw data from excel file
            if fpath.endswith('.xls'):
                datasets = get_raw_excel_data(fpath)
            elif fpath.endswith('.xlsx'):
                datasets = get_raw_xlsx_data(fpath, read_only=True)
        # *********************************************
        sheet_names = list(datasets.keys())
        dataset = datasets[sheet_names[0]]
        first_col_names = dataset.pop(0)
        orb.log.debug(f'  - col names: {first_col_names}')
        first_col_lowered = []
        blank_col = False
        for n in first_col_names:
            if n and isinstance(n, str):
                n = ' '.join(n.split('\n'))  # in case multi-line
                first_col_lowered.append(n.casefold())
            else:
                blank_col = True
        orb.log.debug(f'    lowered: {first_col_lowered}')
        aliases = STD_ALIASES.get(object_type, []) or []
        orb.log.debug(f'    aliases: {aliases}')
        if (not blank_col and object_type in STD_ALIASES and
            all([(a in aliases) for a in first_col_lowered])):
            # all match -- only add ObjectCreationPage ...
            data_wizard_state['dataset'] = dataset
            data_wizard_state['selected_dataset'] = dataset
            data_wizard_state['column_names'] = first_col_names
            data_wizard_state['column_numbers'] = range(len(first_col_names))
            data_wizard_state['col_map'] = {a: aliases[a.casefold()]
                                            for a in first_col_names}
            dictified = []
            for i, row in enumerate(dataset):
                dictified.append({col: dataset[i][j] for j, col
                                            in enumerate(first_col_names)})
            data_wizard_state['dictified'] = dictified
            object_creation_page = ObjectCreationPage(parent=self)
            self.addPage(object_creation_page)
        else:
            # not all match -- start from beginning
            data_intro_page = DataIntroPage(intro_label, parent=self)
            data_sheet_page = DataSheetPage(parent=self)
            data_header_page = DataHeaderPage(parent=self)
            mapping_page = MappingPage(parent=self)
            object_creation_page = ObjectCreationPage(parent=self)
            self.addPage(data_intro_page)
            self.addPage(data_sheet_page)
            self.addPage(data_header_page)
            self.addPage(mapping_page)
            self.addPage(object_creation_page)
        self.setGeometry(50, 50, width, height)
        self.setSizeGripEnabled(True)
        self.setWindowTitle("Data Import Wizard")


class DataIntroPage(QWizardPage):
    """
    Data Import Wizard intro page.
    """
    def __init__(self, intro_label, parent=None):
        super().__init__(parent=parent)
        self.setTitle("Introduction")
        layout = QHBoxLayout()
        logo_path = config.get('tall_logo')
        if logo_path:
            image_path = os.path.join(orb.image_dir, logo_path)
            layout.addWidget(PlaceHolder(image=image_path, parent=self))
        layout.addWidget(intro_label)
        self.setLayout(layout)


class DataSheetPage(QWizardPage):
    """
    Page for selecting the sheet to import from an Excel file.
    First, a check will be done to see if the file conforms to a standard
    format -- i.e., data is on first sheet, column names are in first row,
    column names are standard for the type of file (e.g. Requirements).  If
    so, the user will be notified and the data is imported without further ado
    ... if not, the wizard's steps will be followed.
    """
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        # only file type currently supported is 'excel' ...
        fpath = data_wizard_state.get('file_path')
        if fpath:
            fname = os.path.basename(fpath)
            self.setTitle('Sheets loaded from the file: '
                          f'<font color="blue"><code>{fname}</code></font>')
            # self.setSubTitle("Select a sheet to import...")
            # import raw data from excel file
            self.datasets = {}
            if fpath.endswith('.xls'):
                self.datasets = get_raw_excel_data(fpath)
            elif fpath.endswith('.xlsx'):
                self.datasets = get_raw_xlsx_data(fpath,
                                                  read_only=True)
        else:
            return
        # datasets_list_label = QLabel(
                                    # '<font color="green">'
                                    # "<h3>Select a sheet<br>to import:"
                                    # "</font></h3>")
        datasets_list_label = ColorLabel(
                                    "Select a sheet to import:",
                                    color="green", element='h3',
                                    border=1, margin=10)
        # sheet list widget
        self.sl_model = QStandardItemModel(parent=self)
        self.sheet_names = list(self.datasets.keys())
        if self.sheet_names:
            for name in self.sheet_names:
                self.sl_model.appendRow(QStandardItem(name))
        else:
            self.sl_model.appendRow('None')
        self.sheet_list_widget = AutosizingListView(self)
        self.sheet_list_widget.setModel(self.sl_model)
        self.sheet_list_widget.clicked.connect(self.on_select_dataset)
        self.sheet_list_widget.setSelectionMode(
                                QAbstractItemView.ExtendedSelection)
        self.selection_model = self.sheet_list_widget.selectionModel()
        self.selection_model.select(self.sl_model.createIndex(0, 0),
                                    QItemSelectionModel.ToggleCurrent)
        self.vbox = QVBoxLayout()
        self.vbox.addWidget(datasets_list_label,
                            alignment=Qt.AlignLeft|Qt.AlignTop)
        self.vbox.addWidget(self.sheet_list_widget,
                            alignment=Qt.AlignLeft|Qt.AlignTop)
        self.vbox.setStretch(1, 1)
        self.hbox = QHBoxLayout()
        self.hbox.addLayout(self.vbox)
        self.set_dataset(self.sheet_names[0])
        self.setLayout(self.hbox)

    def on_select_dataset(self, idx):
        row = idx.row()
        # create table view for selected dataset
        dataset_name = str(self.sl_model.item(row).text())
        self.set_dataset(dataset_name)

    def set_dataset(self, dataset_name):
        current = data_wizard_state.get('dataset_name')
        if current and (current == dataset_name):
            return
        else:
            data_wizard_state['dataset_name'] = str(dataset_name)
            data_wizard_state['dataset'] = self.datasets[dataset_name]
        if hasattr(self, 'tableview'):
            self.hbox.removeWidget(self.tableview)
            self.tableview.setAttribute(Qt.WA_DeleteOnClose)
            self.tableview.parent = None
            self.tableview.close()
        tablemodel = ListTableModel(self.datasets[dataset_name],
                                    parent=self)
        self.tableview = QTableView(self)
        self.tableview.setModel(tablemodel)
        self.tableview.resizeColumnsToContents()
        self.tableview.setSizeAdjustPolicy(self.tableview.AdjustToContents)
        self.hbox.addWidget(self.tableview, stretch=1,
                            alignment=Qt.AlignLeft|Qt.AlignTop)
        self.hbox.setStretch(1, 1)
        self.updateGeometry()


class DataHeaderPage(QWizardPage):
    """
    Page to select the row that contains the column names and select which
    columns are to be imported.
    """
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.candidate_column_names = [] 
        data_wizard_state['heading_row'] = 0
        data_wizard_state['column_names'] = []
        data_wizard_state['column_numbers'] = []
        self.directions = ColorLabel('Click on the row<br>'
                                     'that contains<br>'
                                     'the column names...',
                                     color="green", element='h3',
                                     border=1, margin=10)
        # set min. width so that when the column name checkboxes are added, the
        # panel is wide enough that no horizontal scroll bar appears ...
        self.directions.setMinimumWidth(200)
        self.vbox = QVBoxLayout()
        self.vbox.addWidget(self.directions,
                            alignment=Qt.AlignLeft|Qt.AlignTop)
        self.hbox = QHBoxLayout()
        self.hbox.addLayout(self.vbox)

    def initializePage(self):
        orb.log.debug('* DataHeaderPage')
        # TODO:  check self.vbox for a column listing from a previous
        # instantiation -- if one is found, remove it ...
        ds_name = data_wizard_state["dataset_name"]
        self.setTitle(
            f'Column Headings for <font color="blue">{ds_name}</font>')
        tablemodel = ListTableModel(data_wizard_state['dataset'], parent=self)
        if hasattr(self, 'tableview'):
            self.tableview.setParent(None)
        self.tableview = QTableView(self)
        self.tableview.setModel(tablemodel)
        self.tableview.resizeColumnsToContents()
        self.tableview.setSizeAdjustPolicy(self.tableview.AdjustToContents)
        self.tableview.setSelectionBehavior(self.tableview.SelectRows)
        self.tableview.setSelectionMode(self.tableview.SingleSelection)
        self.tableview.clicked.connect(self.on_row_clicked)
        row_header = self.tableview.verticalHeader()
        row_header.sectionClicked.connect(self.on_row_header_clicked)
        # self.hbox.addWidget(self.tableview, stretch=1,
        self.hbox.addWidget(self.tableview,
                            alignment=Qt.AlignLeft|Qt.AlignTop)
        self.updateGeometry()
        self.setLayout(self.hbox)

    def on_row_clicked(self, idx):
        self.get_col_names(idx.row())

    def on_row_header_clicked(self, idx):
        self.get_col_names(idx)

    def get_col_names(self, row):
        """
        Get contents of row that is specified to contain column names.
        """
        self.candidate_column_names = data_wizard_state['dataset'][row] 
        data_wizard_state['heading_row'] = row
        self.directions.set_content(
                    'Click on the labels of columns<br>to be imported:',
                    color="green", element='h3',
                    border=1, margin=10)
        # if there are checkboxes from a previous call, remove them ...
        if hasattr(self, 'cb_layout'):
            for i in reversed(list(range(self.cb_layout.count()))):
                self.cb_layout.itemAt(i).widget().setParent(None)
            self.cb_layout.setParent(None)
            self.cb_container.setParent(None)
            self.cb_scrollarea.setParent(None)
        self.cbs = []
        self.cb_labels = {}
        self.cb_scrollarea = QScrollArea()
        self.cb_scrollarea.setWidgetResizable(True)
        self.cb_container = QWidget()
        self.cb_scrollarea.setWidget(self.cb_container)
        self.cb_layout = QGridLayout(self.cb_container)
        self.cb_all = QCheckBox()
        self.cb_all.clicked.connect(self.on_check_all)
        self.cb_all.clicked.connect(self.completeChanged)
        cb_all_label = QLabel('<b>SELECT ALL</b>')
        self.cb_layout.addWidget(self.cb_all, 0, 0)
        self.cb_layout.addWidget(cb_all_label, 0, 1)
        self.cbs.append(self.cb_all)
        for i, name in enumerate(self.candidate_column_names):
            cb = QCheckBox()
            cb.clicked.connect(self.completeChanged)
            cb.clicked.connect(self.on_check_cb)
            if i in data_wizard_state['column_numbers']:
                cb.setChecked(True)
            height = 25
            label_text = name
            if not name:
                label_text = '[no name]'
            elif len(name) > 15:
                wrapped_lines = wrap(name, width=15, break_long_words=False)
                label_text = '\n'.join(wrapped_lines)
                height = len(wrapped_lines) * 25
            cb_label = CheckButtonLabel(label_text, h=height, w=300)
            cb_label.setChecked(False)
            if name in data_wizard_state['column_names']:
                cb_label.setChecked(True)
            cb_label.clicked.connect(self.on_click_label)
            cb_label.clicked.connect(self.completeChanged)
            cb_label.setFixedWidth(100)
            self.cb_labels[name] = cb_label
            # cb_label.setWordWrap(True)
            self.cbs.append(cb)
            self.cb_layout.addWidget(cb, i+1, 0)
            self.cb_layout.addWidget(cb_label, i+1, 1)
        self.vbox.addWidget(self.cb_scrollarea)
        self.vbox.setStretch(1, 1)
        self.updateGeometry()

    def on_check_all(self):
        if self.cb_all.isChecked():
            for cb in self.cbs:
                cb.setChecked(True)
        else:
            for cb in self.cbs:
                cb.setChecked(False)
        self.on_check_cb()

    def on_click_label(self):
        for i, name in enumerate(self.candidate_column_names):
            if self.cb_labels.get(name):
                if self.cb_labels[name].isChecked():
                    self.cb_labels[name].setStyleSheet(
                            'color: purple; background-color: yellow; '
                            'border: 1px solid black;')
                    self.cbs[i+1].setChecked(True)
                else:
                    self.cb_labels[name].setStyleSheet(
                            'color: purple; background-color: white; '
                            'border: 1px solid black;')
                    self.cbs[i+1].setChecked(False)
        self.on_check_cb()

    def on_check_cb(self):
        data_wizard_state['column_names'] = []
        data_wizard_state['column_numbers'] = []
        for i, name in enumerate(self.candidate_column_names):
            if self.cbs[i+1].isChecked():
                self.cb_labels[name].setChecked(True)
                self.cb_labels[name].setStyleSheet(
                        'color: purple; background-color: yellow; '
                        'border: 1px solid black;')
                data_wizard_state['column_names'].append(
                                            self.candidate_column_names[i])
                data_wizard_state['column_numbers'].append(i)
            else:
                self.cb_labels[name].setChecked(False)
                self.cb_labels[name].setStyleSheet(
                        'color: purple; background-color: white; '
                        'border: 1px solid black;')
        orb.log.debug('* wizard: selected columns:')
        for i, n in zip(data_wizard_state['column_numbers'],
                        data_wizard_state['column_names']):
            orb.log.debug('  * [{}] {}'.format(i, n))

    def isComplete(self):
        """
        Return `True` when the page is complete, which activates the `Next`
        button.
        """
        # TODO:  return True when any checkbox of the column names checkboxes
        # has been checked, False if none have been checked.
        if hasattr(self, 'cbs'):
            for cb in self.cbs:
                if cb.isChecked():
                    return True
            return False
        else:
            return False


def get_prop_def(cname, property_name):
    # orb.log.debug(f'* wizard: get_prop_def("{property_name}")')
    e = orb.registry.pes.get(property_name)
    if e:
        PGANA = orb.get('pgefobjects:PGANA')
        prop_def_oid = e['oid'] + '.PropertyDefinition'
        prop_def = orb.get(prop_def_oid)
        if not prop_def:
            # orb.log.debug('  prop def not found, creating ...')
            PropDef = orb.classes['PropertyDefinition']
            label = None
            if cname in PREFERRED_ALIASES:
                label = PREFERRED_ALIASES[cname].get(e['id'])
            prop_def = PropDef(oid=prop_def_oid, id=e['id'], id_ns=e['id_ns'],
                               name=e['name'], owner=PGANA, label=label,
                               description=e['definition'],
                               range_datatype=e['range'])
        return prop_def
    else:
        return None


class PropertyDropLabel(ColorLabel):
    """
    A Label that represents a property (a DataElementDefinition or a
    ParameterDefinition), for use in the DataImportWizard.  This label accepts
    a drag/drop event: a dropped property replaces the property currently
    referenced by the label and modifies the mapping accordingly.  It also has
    a context menu with a 'delete' choice that deletes its referenced property.  
    """
    def __init__(self, idx, color=None, element=None, border=None, margin=None,
                 parent=None, **kw):
        """
        Initialize.

        Args:
            idx (int): the index of this label in the sequence of labels
                corresponding to the list of data columns to be mapped

        Keyword Args:
            color (str):  color to use for text
            element (str):  html element to use for label
            border (int):  thickness of border (default: no border)
            margin (int):  width of margin surrounding contents
            parent (QWidget):  parent widget
        """
        super().__init__('', color=color, element=element,
                         border=border, margin=margin, parent=None)
        self.color = color
        self.element = element
        self.border = border
        self.margin = margin
        self.setStyleSheet('background-color: white')
        self.setAcceptDrops(True)
        self.mime_types = ['application/x-pgef-data-element-definition',
                           'application/x-pgef-property-definition',
                           'application/x-pgef-parameter-definition']
        self.idx = idx
        self.dedef = None
        self.setup_context_menu()
        # dispatcher.connect(self.adjust_parent_size, 'dedef label resized')

    def set_content(self, name, color=None, element=None, border=None,
                    margin=None, maxwidth=0):
        self.name = name
        self.color = color or 'purple'
        self.element = getattr(self, 'element', None) or element
        self.border = getattr(self, 'border', None) or border
        self.margin = getattr(self, 'margin', None) or margin
        super().set_content(self.name, color=self.color, element=self.element,
                            border=self.border, margin=self.margin,
                            maxwidth=maxwidth)
        if self.name:
            self.setStyleSheet('background-color: yellow')

    def setup_context_menu(self):
        delete_dedef_action = QAction('Delete', self)
        delete_dedef_action.triggered.connect(self.delete_dedef)
        self.addAction(delete_dedef_action)
        # self.setContextMenuPolicy(Qt.ActionsContextMenu)
        self.menu = QMenu(self)
        self.menu.setStyleSheet(
            'QMenu::item {color: purple; background: white;} '
            'QMenu::item:selected {color: white; background: purple;}')
        self.menu.addAction(delete_dedef_action)

    def delete_dedef(self, event):
        """
        Remove a DataElementDefinition from the mapping.
        """
        if getattr(self, 'dedef', None):
            self.dedef = None
        if self.text():
            self.setText('')
            self.setStyleSheet('background-color: white')

    def mimeTypes(self):
        """
        Return MIME Types accepted for drops.
        """
        return self.mime_types

    def supportedDropActions(self):
        return Qt.CopyAction

    def dragEnterEvent(self, event):
        # orb.log.debug(f'* a drag entered label {self.idx} ...')
        if (event.mimeData().hasFormat(
                'application/x-pgef-data-element-definition')
                or event.mimeData().hasFormat(
                'application/x-pgef-parameter-definition')
                or event.mimeData().hasFormat(
                'application/x-pgef-property-definition')):
            self.setStyleSheet('background-color: yellow')
            event.accept()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        if not self.dedef:
            self.setStyleSheet('background-color: white')
        event.accept()

    def dragMoveEvent(self, event):
        if (event.mimeData().hasFormat(
                'application/x-pgef-data-element-definition')
                or event.mimeData().hasFormat(
                'application/x-pgef-parameter-definition')
                or event.mimeData().hasFormat(
                'application/x-pgef-property-definition')):
            self.setStyleSheet('background-color: yellow')
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def contextMenuEvent(self, event):
        if self.menu:
            self.menu.exec_(self.mapToGlobal(event.pos()))

    def dropEvent(self, event):
        """
        Handle drop events (map the corresponding column from the input data to
        this DataElementDefinition).  Note that this will remove the
        DataElementDefinition object currently associated with the label from
        the mapping and add the dropped one to the mapping.
        """
        # orb.log.debug(f'* label {self.idx} got a drop ...')
        if event.mimeData().hasFormat(
                                'application/x-pgef-data-element-definition'):
            data = extract_mime_data(event,
                                'application/x-pgef-data-element-definition')
            icon, dedef_oid, dedef_id, dedef_name, dedef_cname = data
            self.dedef = orb.get(dedef_oid)
            name = self.dedef.label or dedef_id
            self.set_content(name)
            self.setStyleSheet('background-color: yellow')
            self.adjustSize()
            dispatcher.send(signal='dedef drop', dedef_id=dedef_id,
                            idx=self.idx)
        elif event.mimeData().hasFormat(
                                'application/x-pgef-parameter-definition'):
            data = extract_mime_data(event,
                                'application/x-pgef-parameter-definition')
            icon, dedef_oid, dedef_id, dedef_name, dedef_cname = data
            self.dedef = orb.get(dedef_oid)
            name = self.dedef.label or dedef_id
            self.set_content(name)
            self.setStyleSheet('background-color: yellow')
            self.adjustSize()
            dispatcher.send(signal='dedef drop', dedef_id=dedef_id,
                            idx=self.idx)
        elif event.mimeData().hasFormat(
                                'application/x-pgef-property-definition'):
            data = extract_mime_data(event,
                                'application/x-pgef-property-definition')
            icon, dedef_oid, dedef_id, dedef_name, dedef_cname = data
            self.dedef = orb.get(dedef_oid)
            name = self.dedef.label or dedef_id
            self.set_content(name)
            self.setStyleSheet('background-color: yellow')
            self.adjustSize()
            dispatcher.send(signal='dedef drop', dedef_id=dedef_id,
                            idx=self.idx)
        else:
            self.setStyleSheet('background-color: white')
            event.ignore()


class MappingPage(QWizardPage):
    """
    Page to specify a mapping from the data columns to attributes into which
    the data will be imported.
    """
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.object_type = data_wizard_state.get('object_type') or ''
        self.widgets_added = False
        self.column_names = data_wizard_state.get('column_names') or []
        dispatcher.connect(self.on_dedef_drop, 'dedef drop')

    def initializePage(self):
        orb.log.debug('* MappingPage.initializePage()')
        if not self.widgets_added:
            self.add_widgets()
        # after adding all widgets, redo the mapping area for proper sizing
        # NOTE: order is important here -- remove mapping_container before
        # mapping_scrollarea
        if getattr(self, 'mapping_container', None):
            self.mapping_container.setAttribute(Qt.WA_DeleteOnClose)
            self.mapping_container.parent = None
            self.mapping_container.close()
            self.mapping_container = None
        if getattr(self, 'mapping_layout', None):
            self.vbox.removeWidget(self.mapping_scrollarea)
            self.mapping_scrollarea.setAttribute(Qt.WA_DeleteOnClose)
            self.mapping_scrollarea.parent = None
            self.mapping_scrollarea.close()
            self.mapping_scrollarea = None
        self.mapping_scrollarea = QScrollArea()
        self.mapping_scrollarea.setWidgetResizable(True)
        self.mapping_scrollarea.setMinimumWidth(300)
        self.mapping_container = QWidget()
        self.mapping_scrollarea.setWidget(self.mapping_container)
        self.mapping_scrollarea.setAlignment(Qt.AlignLeft|Qt.AlignTop)
        self.mapping_layout = QGridLayout(
                                                self.mapping_container)
        arrow_image = QPixmap(os.path.join(
                              orb.home, 'icons', 'right_arrow.png'))
        arrow_label = QLabel()
        arrow_label.setPixmap(arrow_image)
        col_map = data_wizard_state['col_map']
        col_labels_height = 0
        for i, name in enumerate(data_wizard_state['column_names']):
            col_label = QLabel(name)
            col_label.setWordWrap(True)
            col_label.setMargin(10)
            col_label.setStyleSheet('border: 1px solid black;')
            col_label.setFixedWidth(100)
            col_label.setMaximumSize(col_label.sizeHint())
            col_labels_height += col_label.height() + 10
            arrow_label = QLabel()
            arrow_label.setFixedWidth(20)
            arrow_label.setPixmap(arrow_image)
            target_label = PropertyDropLabel(i, margin=2, border=1)
            if col_map and col_map.get(name):
                target_label.set_content(col_map[name])
            self.mapping_layout.addWidget(col_label, i, 0)
            self.mapping_layout.addWidget(arrow_label, i, 1)
            self.mapping_layout.addWidget(target_label, i, 2)
        msa_height = min([self.parent().height() - 70, col_labels_height])
        # orb.log.debug(f'  - col_labels_height: {col_labels_height}')
        # orb.log.debug(f'  - mapping_scrollarea height set to: {msa_height}')
        self.mapping_scrollarea.setMinimumHeight(msa_height)
        self.vbox.addWidget(self.mapping_scrollarea,
                            alignment=Qt.AlignLeft|Qt.AlignTop)
        self.vbox.addStretch()
        self.updateGeometry()

    def add_widgets(self):
        orb.log.debug('* MappingPage.add_widgets()')
        # button to pop up instructions
        instructions_button = QPushButton('View Instructions')
        instructions_button.clicked.connect(self.instructions)
        instructions_button.setMaximumSize(150,35)
        # set min. width so that when the column name checkboxes are added, the
        # panel is wide enough that no horizontal scroll bar appears ...
        self.vbox = QVBoxLayout()
        self.vbox.setSpacing(10)
        self.vbox.addWidget(instructions_button,
                            alignment=Qt.AlignLeft|Qt.AlignTop)
        self.hbox = QHBoxLayout()
        self.hbox.setSpacing(50)
        self.hbox.addLayout(self.vbox)
        self.setTitle('Data Mapping for <font color="blue">%s</font>'
                      % data_wizard_state['dataset_name'])
        # Mapping construction, using 3 vertical columns, of which the first 2
        # columns are inside the self.vbox layout:
        # (1) selected column names
        # (2) empty labels into which the target attribute will be dropped
        self.mapping_scrollarea = QScrollArea()
        self.mapping_scrollarea.setWidgetResizable(True)
        self.mapping_scrollarea.setMinimumWidth(300)
        self.mapping_container = QWidget()
        self.mapping_scrollarea.setWidget(self.mapping_container)
        self.mapping_scrollarea.setAlignment(Qt.AlignLeft|Qt.AlignTop)
        self.mapping_layout = QGridLayout(self.mapping_container)
        arrow_image = QPixmap(os.path.join(
                              orb.home, 'icons', 'right_arrow.png'))
        arrow_label = QLabel()
        arrow_label.setPixmap(arrow_image)
        col_map = data_wizard_state['col_map']
        col_labels_height = 0
        for i, name in enumerate(data_wizard_state['column_names']):
            col_label = QLabel(name)
            col_label.setFixedWidth(100)
            col_label.setMargin(10)
            col_label.setWordWrap(True)
            col_label.setStyleSheet('border: 1px solid black;')
            col_label.setMaximumSize(col_label.sizeHint())
            col_labels_height += col_label.height() + 10
            arrow_label = QLabel()
            arrow_label.setFixedWidth(20)
            arrow_label.setPixmap(arrow_image)
            target_label = PropertyDropLabel(i, margin=10, border=1)
            if col_map and col_map.get(name):
                target_label.set_content(col_map[name], color="purple")
            self.mapping_layout.addWidget(col_label, i, 0)
            self.mapping_layout.addWidget(arrow_label, i, 1)
            self.mapping_layout.addWidget(target_label, i, 2)
        self.vbox.addWidget(self.mapping_scrollarea,
                            alignment=Qt.AlignLeft|Qt.AlignTop)
        # scroll area does not properly size itself so this is required:
        msa_height = min([self.parent().height() - 70, col_labels_height])
        # orb.log.debug(f'  - col_labels_height: {col_labels_height}')
        # orb.log.debug(f'  - mapping_scrollarea height set to: {msa_height}')
        self.mapping_scrollarea.setMinimumHeight(msa_height)
        self.vbox.addStretch()

        # ... and the 3rd column is in self.attr_vbox ...
        # (3) attributes of the target object type shown in a list from which
        # they can be dragged/dropped onto the empty labels
        self.attr_vbox = QVBoxLayout()
        self.hbox.addLayout(self.attr_vbox)
        objs = []
        std_view = None
        if self.object_type in STD_VIEWS:
            std_view = STD_VIEWS[self.object_type]
            for fname in std_view:
                objs.append(get_prop_def(self.object_type, fname))
        else:
            for fname in orb.schemas[self.object_type]['field_names']:
                # exclude object-valued properties for now ...
                if (orb.schemas[self.object_type]['fields'][fname]['range']
                    not in orb.classes):
                    objs.append(get_prop_def(self.object_type, fname))
        if self.object_type == 'HardwareProduct':
            # for HardwareProducts, can additionally map columns to parameters
            # and MEL data elements
            gsfc_dedefs = orb.search_exact(cname='DataElementDefinition',
                                           id_ns='gsfc.mel')
            if gsfc_dedefs:
                objs += gsfc_dedefs
            objs += orb.get_by_type('ParameterDefinition')
        if std_view:
            self.attr_panel = LibraryListView('PropertyDefinition', objs=objs,
                                              parent=self)
        else:
            self.attr_panel = FilterPanel(objs=objs, as_library=True,
                                       title=f'{self.object_type} Properties',
                                       sized_cols={'id': 0,
                                                   'range_datatype': 0},
                                       view=['id', 'range_datatype'],
                                       height=self.geometry().height(),
                                       width=450, parent=self)
        self.attr_vbox.addWidget(self.attr_panel)

        # *******************************************************************
        # Table displaying the selected dataset ...
        # *******************************************************************
        # remove rows above the specified heading_row ...
        data_rows = data_wizard_state['dataset'][
                                    data_wizard_state['heading_row']+1:]
        # include only the columns specified for import ...
        new_dataset = [[row[i] for i in data_wizard_state['column_numbers']]
                        for row in data_rows]
        data_wizard_state['selected_dataset'] = new_dataset

        data_wizard_state['dictified'] = []
        dictified = data_wizard_state['dictified']
        for i, row in enumerate(new_dataset):
            dictified.append({col_name : new_dataset[i][j] for j, col_name
                              in enumerate(data_wizard_state['column_names'])})
        orb.log.debug('  dictified:')
        orb.log.debug(pprint.pformat(dictified))
        # tablemodel = ListTableModel(new_dataset, parent=self)
        tablemodel = MappingTableModel(dictified, parent=self)
        if hasattr(self, 'tableview'):
            self.tableview.setParent(None)
        self.tableview = QTableView(self)
        self.tableview.setModel(tablemodel)
        self.tableview.resizeColumnsToContents()
        self.tableview.setSizeAdjustPolicy(self.tableview.AdjustToContents)
        self.tableview.setSelectionBehavior(self.tableview.SelectRows)
        self.tableview.setSelectionMode(self.tableview.SingleSelection)
        # self.tableview.clicked.connect(self.on_row_clicked)
        # row_header = self.tableview.verticalHeader()
        # row_header.sectionClicked.connect(self.on_row_header_clicked)
        self.hbox.addWidget(self.tableview, stretch=1,
                            alignment=Qt.AlignLeft|Qt.AlignTop)
        self.setLayout(self.hbox)
        self.updateGeometry()
        self.widgets_added = True

    def instructions(self):
        text =  '<h3>Map selected column names to properties by dragging and '
        text += 'dropping a property name from the <font color="purple">'
        text += f'{self.object_type}&nbsp;Properties</font> list '
        text += 'to the empty box next to a column name.</h3>'
        text += '<hr>'
        text += '<b>NOTE: to see the definition of a property, '
        text += 'hover the mouse over its name.</b>'
        QMessageBox.question(self, 'Instructions', text,
                                       QMessageBox.Ok)

    def on_dedef_drop(self, dedef_id=None, idx=None):
        col_names = data_wizard_state['column_names']
        col_map = data_wizard_state['col_map']
        # map to dedef "internal name" (id)
        col_map[col_names[idx]] = dedef_id
        self.completeChanged.emit()
        # orb.log.debug(f'column mapping is now: {col_map}')

    def isComplete(self):
        """
        Return `True` when the page is complete, which cases the **Next**
        button to be activated.
        """
        # TODO:  return True as soon as any column is mapped
        col_map = data_wizard_state.get('col_map')
        if col_map:
            orb.log.debug(f'* final column mapping is: {col_map}')
            # TODO:  validate that mapped columns are type-compatible with the
            # properties they are mapped to -- which basically means check that
            # any values mapped to int, float, or bool can be cast
            # successfully.
            return True
        else:
            return False


class ObjectCreationPage(QWizardPage):
    """
    Page to create/update objects from the specified data.
    """
    def __init__(self, test_mode=False, parent=None):
        super().__init__(parent=parent)
        self.test_mode = test_mode
        self.objs = []
        project_oid = state.get('project')
        self.project = None
        self.object_type = data_wizard_state['object_type']
        if project_oid:
            self.project = orb.get(project_oid)
            proj_id = self.project.id
            if self.object_type == 'Requirement':
                self.title_txt = f'Project Requirements for {proj_id}'
            elif self.object_type == 'HardwareProduct':
                self.title_txt = f'Hardware owned by {proj_id}'
        else:
            if self.object_type == 'Requirement':
                self.title_txt = 'Requirements'
            elif self.object_type == 'HardwareProduct':
                self.title_txt = 'Hardware Products'
        self.setTitle(self.title_txt)

    def initializePage(self):
        orb.log.debug('* Object Creation Page')
        schema = orb.schemas[self.object_type]['fields']
        if self.objs:
            # if objs exist, it means we are re-entering; delete them
            orb.delete(self.objs)
            self.objs = []
        col_map = data_wizard_state['col_map']
        orb.log.debug(f'* column mapping: {col_map}')

        self.dataset = data_wizard_state['selected_dataset']
        text = f'Creating {self.object_type} objects from Excel data ...'
        self.progress_dialog = ProgressDialog(title='Creating Objects',
                                              label=text, parent=self)
        self.progress_dialog.setAttribute(Qt.WA_DeleteOnClose)
        self.progress_dialog.setMaximum(len(self.dataset))
        self.progress_dialog.setValue(0)
        self.progress_dialog.setMinimumDuration(2000)
        dictified = data_wizard_state['dictified']
        if self.object_type == 'Requirement':
            proj_rqts = orb.search_exact(cname='Requirement',
                                         owner=self.project)
            cur_ids = [r.id for r in proj_rqts]
        NOW = dtstamp()
        user = orb.get(state.get('local_user_oid'))
        for i, row in enumerate(dictified):
            obj = None
            kw = {}
            for name, val in row.items():
                if name in col_map:
                    a = col_map[name]
                    if a in schema:
                        if schema[a]['field_type'] == 'object':
                            # skip object-valued fields, for now ...
                            continue
                        else:
                            dtype = dtypes[schema[a]['range']]
                    elif a in parm_defz:
                        dtype_name = parm_defz[a]['range_datatype']
                        dtype = SELECTABLE_VALUES['range_datatype'].get(
                                                                dtype_name,
                                                                float)
                    elif a in de_defz:
                        dtype_name = de_defz[a]['range_datatype']
                        dtype = SELECTABLE_VALUES['range_datatype'].get(
                                                                dtype_name,
                                                                str)
                    try:
                        kw[a] = dtype(val)
                    except:
                        # could not cast value; ignore a
                        continue
            # for cleanup after test run ...
            if self.test_mode:
                kw['comment'] = "TEST TEST TEST"
            if self.object_type == 'Requirement':
                data = []
                for a in kw:
                    # ignore these values ...
                    if kw.get(a) in [None, "None", "", "TEST TEST TEST"]:
                        continue
                    else:
                        data.append(kw.get(a))
                if not data:
                    # do not create/update objects from empty rows
                    orb.log.debug(f'  - row {i} has no data, skipping ...')
                    self.progress_dialog.setValue(i+1)
                    continue
                ID = kw.get('id')
                if ID in cur_ids:
                    # update the existing rqt ...
                    orb.log.debug(f'* {ID} is existing rqt, updating it ...')
                    obj = orb.select('Requirement', id=ID)
                    for a in kw:
                        # do not update from empty or "None" str values,
                        # but allow 0 (zero) or False values to overwrite
                        # TODO: fix casting of str "False" values, which will
                        # be incorrect for bool() ...
                        if kw[a] == "" or kw[a] == "None":
                            continue
                        try:
                            setattr(obj, a, dtype(kw[a]))
                        except:
                            # if cast fails, ignore that field
                            orb.log.info(f'  - update of field "{a}" failed.')
                    obj.owner = self.project
                    obj.modifier = user
                    obj.mod_datetime = NOW
                else:
                    orb.log.debug(f'  - creating rqt for row {i} ...')
                    if 'level' not in kw:
                        kw['level'] = 1
                    if 'id' not in kw:
                        kw['owner'] = self.project
                        k = i
                        while 1:
                            next_id = f"{self.project.id}-{kw['level']}.{k}"
                            if next_id in cur_ids:
                                k += 1
                            else:
                                kw['id'] = next_id
                                cur_ids.append(next_id)
                                break
                    new_id = kw['id']
                    orb.log.debug(f'    with id {new_id}')
                    obj = clone('Requirement', **kw)
                    obj.creator = user
                    obj.modifier = user
                    obj.create_datetime = NOW
                    obj.mod_datetime = NOW
            elif self.object_type == 'HardwareProduct':
                # first check kw for parameter and data element id's that do
                # not collide with properties (i.e., are not in the
                # HardwareProduct schema)
                parms = {}
                des = {}
                p_names = set(orb.schemas['HardwareProduct']['field_names'])
                np_names = set(list(kw.keys())) - p_names
                for np_name in np_names:
                    if np_name in parm_defz:
                        parms[np_name] = kw.pop(np_name)
                    elif np_name in de_defz:
                        des[np_name] = kw.pop(np_name)
                # NOTE: save_hw=False prevents the saving of hw objects one at
                # a time -- much more efficient to save after all are cloned
                # TODO: check "id" kw for existing HW -- if found, update ...
                ID = kw.get('id')
                obj = None
                if ID:
                    obj = orb.select('HardwareProduct', id=ID)
                if obj:
                    # TODO: check that user has modify permission!
                    orb.log.debug('* {ID} is existing product, updating ...')
                    for a in kw:
                        setattr(obj, a, kw[a])
                    obj.modifier = user
                    obj.mod_datetime = NOW
                else:
                    obj = clone(self.object_type, save_hw=False, **kw)
                    if not getattr(obj, 'id', None):
                        obj.id = orb.gen_product_id(obj)
                    obj.creator = user
                    obj.modifier = user
                    obj.create_datetime = NOW
                    obj.mod_datetime = NOW
                if parms:
                    for pid, val in parms.items():
                        set_pval_from_str(obj.oid, pid, val)
                if des:
                    for deid, val in des.items():
                        set_dval_from_str(obj.oid, deid, val)
            else:
                obj = clone(self.object_type, **kw)
                obj.creator = user
                obj.modifier = user
                obj.create_datetime = NOW
                obj.mod_datetime = NOW
            if obj:
                self.objs.append(obj)
            orb.db.commit()
            self.progress_dialog.setValue(i+1)
        if self.objs:
            orb.save(self.objs)
            dispatcher.send(signal="new objects", objs=self.objs)
        self.progress_dialog.done(0)
        self.add_widgets()

    def add_widgets(self):
        if not hasattr(self, 'vbox'):
            self.vbox = QVBoxLayout(self)
        sized_cols = {'id': 0, 'name': 150}
        col_map = data_wizard_state['col_map']
        add_cols = set(col_map.values()) - set(MAIN_VIEWS[self.object_type])
        view = MAIN_VIEWS[self.object_type] + sorted(list(add_cols))
        # orb.log.debug(f'  - fpanel view: {view}')
        if getattr(self, 'fpanel', None):
            self.vbox.removeWidget(self.fpanel)
            self.fpanel.setAttribute(Qt.WA_DeleteOnClose)
            self.fpanel.parent = None
            self.fpanel.close()
            self.fpanel = None
        self.fpanel = FilterPanel(self.objs, view=view, sized_cols=sized_cols,
                                  word_wrap=True, parent=self)
        if self.object_type == "HardwareProduct":
            self.fpanel.proxy_view.addAction(self.fpanel.hw_fields_action)
        self.vbox.addWidget(self.fpanel, stretch=1)


#################################
#  New Product Wizard Pages
#################################

class NewProductWizard(QWizard):
    """
    Wizard to assist in creating new components (Products) and associated Models.
    """

    def __init__(self, parent=None): 
        super().__init__(parent=parent)
        orb.log.info('* opening Product Wizard ...')
        self.setWizardStyle(QWizard.ClassicStyle)
        # the included buttons must be specified using setButtonLayout in order
        # to get the "Back" button on Windows (it is automatically included on
        # Linux but not on Windows)
        included_buttons = [QWizard.Stretch,
                            QWizard.BackButton,
                            QWizard.NextButton,
                            QWizard.FinishButton,
                            QWizard.CancelButton]
        self.setButtonLayout(included_buttons)
        self.setOptions(QWizard.NoBackButtonOnStartPage)
        wizard_state['product_oid'] = None
        intro_label = QLabel(
                "<h2>System / Component Wizard</h2>"
                "This wizard will assist you in creating or editing systems "
                "and components or subsystems!")
        project_oid = state.get('project')
        if project_oid:
            proj = orb.get(project_oid)
        else:
            proj = None
        self.project = proj
        # 0. Identify Product
        self.addPage(IdentificationPage(intro_label, parent=self))
        # 1. Select Maturity Level (TRL)
        self.addPage(MaturityLevelPage(parent=self))
        # 2. Specify Interfaces and Parameter Values
        #    * Mass
        #    * Power
        #    * Data Interface(s)
        #    * Dimensions
        #    * Image
        #    * CAD Model
        # self.addPage(ParametersPage(parent=self))
        self.addPage(NewProductWizardConclusionPage(self))
        self.setMinimumSize(800, 800)
        self.setSizeGripEnabled(True)
        self.setWindowTitle("System / Component Wizard")


instructions = """
<h3>Instructions</h3>
<p>The following fields are required:
<ul>
<li><b>id</b>: <i>(not editable)</i> a unique value is auto-generated based on
the <b>owner</b> and <b>product type</b> fields.</li>
<li><b>name</b>: a brief descriptive name, approximately 25 characters or less
(may contain spaces)</li>
<li><b>description</b>: can be verbose, no size limit</li>
<li><b>owner</b>: project or organization that has configuration control
for this system<br>or component specification
    <ul>
    <li>if a GSFC part, choose your branch, the project, or MDL</li>
    <li>if a vendor part, choose MDL but after creating the component,<br>
    bring it up in the object editor and enter the vendor name into the<br>
    <b>Vendor</b> field on the <b>data</b> tab</li>
    </ul>
</li>
<li><b>product type</b>: click the button to display a list of standard
classifiers and select one</li>
</ul>
<p><font color="red">If this <b>System / Component</b>
is competition-sensitive,
<i><b>uncheck</b></i> the <b>public</b> checkbox.
</font></p>
<p><i>NOTE:</i> you must click <b>Save</b>
to activate the <b>Next</b> button.</p>
"""

class IdentificationPage(QWizardPage):
    """
    0. Identify Product
    """
    def __init__(self, intro_label, parent=None):
        super().__init__(parent=parent)
        self.setTitle("Product Identification")
        self.setSubTitle("Identify the product you are creating ...")
        layout = QHBoxLayout()
        logo_path = config.get('tall_logo')
        if logo_path:
            image_path = os.path.join(orb.image_dir, logo_path)
            layout.addWidget(PlaceHolder(image=image_path, parent=self))
        self.setLayout(layout)
        self.product = None
        dispatcher.connect(self.on_new_object_signal, 'new object')

    def initializePage(self):
        orb.log.info('* [comp wizard] new_product()')
        # TODO:  new dialog to select Template
        proj_oid = state.get('project')
        project = orb.get(proj_oid)
        self.product = clone('HardwareProduct', owner=project, public=False)
        wizard_state['product_oid'] = self.product.oid
        # include version -- but it's allowed to be empty (blank)
        view = ['id', 'name', 'product_type', 'version', 'owner',
                'description', 'public']
        required = ['name', 'description', 'owner', 'product_type']
        panels = ['main']
        self.pgxn_obj = PgxnObject(self.product, embedded=True, panels=panels,
                                   view=view, required=required,
                                   edit_mode=True, new=True,
                                   enable_delete=False)
        # hide tool bar (clone etc.)
        self.pgxn_obj.toolbar.hide()
        self.pgxn_obj.setAttribute(Qt.WA_DeleteOnClose)
        self.wizard().button(QWizard.FinishButton).clicked.connect(
                                                         self.close_pgxn_obj)
        inst_label = QLabel(instructions)
        id_panel_layout = QVBoxLayout()
        id_panel_layout.addWidget(inst_label)
        id_panel_layout.addWidget(self.pgxn_obj)
        id_panel_layout.addStretch(1)
        main_layout = self.layout()
        main_layout.addLayout(id_panel_layout)

    def on_new_object_signal(self, obj=None, cname=''):
        """
        Handle "new object" dispatcher signal, emitted when PgxnObject saves.
        """
        # orb.log.info('  - "new object" signal received')
        if obj is self.product:
            self.completeChanged.emit()

    def close_pgxn_obj(self):
        if getattr(self, 'pgxn_obj', None):
            self.pgxn_obj.close()
            self.pgxn_obj = None

    def isComplete(self):
        """
        Return `True` when the product_type has been set, which activates the
        `Next` button.
        """
        # orb.log.info('* IdentificationPage.isComplete()')
        if (self.product and self.product.id and self.product.name and
            self.product.product_type):
            # orb.log.info('  - product validated successfully')
            return True
        else:
            # orb.log.info('  - product did NOT validate successfully')
            # orb.log.info('  - returning False')
            return False


class ProductTypePage(QWizardPage):
    """
    1. Select Product Type
    """
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.show_all_disciplines = False
        self.pt = None

    def initializePage(self):
        if self.title():
            # if title has already been set, we are re-entering
            # page; don't initialize
            return
        self.setTitle("Product Type")
        self.setSubTitle("Specify the type of the product")
        # if there is a current project, find user's role(s) and the related
        # discipline(s)
        proj_oid = state.get('project')
        project = orb.get(proj_oid)
        # orb.log.debug('[comp wiz] checking for project/roles/disciplines ...')
        disciplines = set()
        if project:
            # get my role assignments on the project:
            me = orb.get(state['local_user_oid'])
            ras = orb.search_exact(cname='RoleAssignment', assigned_to=me,
                                   role_assignment_context=project)
            if ras:
                roles = [ra.assigned_role for ra in ras]
                drs = reduce(lambda x,y: x.union(y),
                             [set(orb.search_exact(cname='DisciplineRole',
                                                   related_role=r))
                              for r in roles])
                disciplines = set([dr.related_to_discipline for dr in drs])
            else:
                pass
                # orb.log.debug('[comp wiz] - no assigned roles found on '
                              # 'project "{}".'.format(project.id))
        else:
            pass
            # orb.log.debug('[comp wiz] - either no project found or no '
                          # 'assigned roles found or no role map.')
        # if disciplines:
            # orb.log.debug('[comp wiz] - disciplines found:')
            # for d in disciplines:
                # orb.log.debug('             {}'.format(d.id))
        # else:
            # orb.log.debug('[comp wiz] - no disciplines found '
                          # 'related to assigned roles.')
        hbox = QHBoxLayout()
        # logo_path = config.get('tall_logo')
        # if logo_path:
            # image_path = os.path.join(orb.image_dir, logo_path)
            # hbox.addWidget(PlaceHolder(image=image_path, parent=self))
        product_types = orb.get_by_type('ProductType')
        label = get_external_name_plural('ProductType')
        self.product_type_panel = FilterPanel(product_types, label=label,
                                              parent=self)
        self.product_type_view = self.product_type_panel.proxy_view
        self.product_type_view.clicked.connect(self.product_type_selected)
        self.product_type_view.clicked.connect(self.completeChanged)
        hbox.addWidget(self.product_type_panel)
        discipline_panel = QGroupBox('Disciplines')
        vbox = QVBoxLayout()
        discipline_panel.setLayout(vbox)
        self.cb_all = QCheckBox('SELECT ALL / CLEAR SELECTIONS')
        self.cb_all.clicked.connect(self.on_check_all)
        vbox.addWidget(self.cb_all)
        all_disciplines = orb.get_by_type('Discipline')
        self.checkboxes = {}
        for d in all_disciplines:
            checkbox = QCheckBox(d.name)
            checkbox.clicked.connect(self.on_check_cb)
            vbox.addWidget(checkbox)
            self.checkboxes[d.oid] = checkbox
        if disciplines:
            for d in all_disciplines:
                if d in disciplines:
                    self.checkboxes[d.oid].setChecked(True)
        else:
            # if no roles/disciplines assigned, select all
            self.cb_all.click()
        hbox.addWidget(discipline_panel)
        main_layout = QVBoxLayout()
        main_layout.addLayout(hbox)
        self.pt_label = NameLabel('Selected Product Type:')
        self.pt_label.setVisible(False)
        self.pt_value_label = ValueLabel('')
        self.pt_value_label.setVisible(False)
        pt_layout = QHBoxLayout()
        pt_layout.addWidget(self.pt_label)
        pt_layout.addWidget(self.pt_value_label)
        pt_layout.addStretch(1)
        main_layout.addLayout(pt_layout)
        self.setLayout(main_layout)
        self.on_check_cb()

    def on_check_all(self):
        if self.cb_all.isChecked():
            self.show_all_disciplines = True
            for cb in self.checkboxes.values():
                cb.setChecked(True)
        else:
            self.show_all_disciplines = False
            for cb in self.checkboxes.values():
                cb.setChecked(False)
        self.on_check_cb()

    def on_check_cb(self):
        d_oids = []
        for d_oid, cb in self.checkboxes.items():
            if cb.isChecked():
                d_oids.append(d_oid)
        product_types = set()
        # 'Systems Engineering' is special:  show all product types ...
        if self.show_all_disciplines:
            pt_list = orb.get_by_type('ProductType')
        elif 'pgefobjects:Discipline.systems_engineering' in d_oids:
            pt_list = orb.get_by_type('ProductType')
        else:
            for d_oid in d_oids:
                discipline = orb.get(d_oid)
                if discipline:
                    pts = [dpt.relevant_product_type
                           for dpt in orb.search_exact(
                                               cname='DisciplineProductType',
                                               used_in_discipline=discipline)]
                    if pts:
                        for product_type in pts:
                            product_types.add(product_type)
            pt_list = list(product_types)
        self.product_type_panel.set_source_model(
            self.product_type_panel.create_model(objs=pt_list))

    def product_type_selected(self, clicked_index):
        # clicked_row = clicked_index.row()
        # orb.log.debug('* clicked row is "{}"'.format(clicked_row))
        mapped_row = self.product_type_panel.proxy_model.mapToSource(
                                                        clicked_index).row()
        self.pt = self.product_type_panel.objs[mapped_row]
        # orb.log.debug(
            # '  product type selected [mapped row] is: {}'.format(mapped_row))
        pt_name = getattr(self.pt, 'name', '[not set]')
        # orb.log.debug('  ... which is "{}"'.format(pt_name))
        if self.pt:
            product = orb.get(wizard_state.get('product_oid'))
            if product:
                product.product_type = self.pt
                orb.save([product])
            self.pt_label.setVisible(True)
            self.pt_value_label.setText(pt_name)
            self.pt_value_label.setVisible(True)

    def isComplete(self):
        """
        Return `True` when the page is complete, which activates the `Next`
        button.
        """
        if self.pt:
            return True
        return False


class MaturityLevelPage(QWizardPage):
    """
    2. Select Maturity Level (TRL)
    """
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setTitle("Maturity Level / Technology Readiness Level (TRL)")
        self.setSubTitle("Select the TRL of the product by clicking on a row "
                         "in the TRL table ...")
        ml_page_layout = QVBoxLayout()
        self.setLayout(ml_page_layout)
        trl_cols = ['trl', 'name', 'sw_desc', 'hw_desc', 'tech_mat', 'exit']
        trl_headers = dict(trl='TRL', name='Name',
                           sw_desc='Software\nDescription',
                           hw_desc='Hardware\nDescription',
                           tech_mat='Technology\nMaturity',
                           exit='Exit\nCriteria')
        trl_ods = []
        for trl_item in trls:
            trl_od = OD()
            for col in trl_cols:
                trl_od[trl_headers[col]] = trl_item[col]
            trl_ods.append(trl_od)
        trl_model = MappingTableModel(trl_ods)
        self.trl_table = QTableView()
        self.trl_table.setModel(trl_model)
        self.trl_table.setAlternatingRowColors(True)
        self.trl_table.setShowGrid(False)
        self.trl_table.setSelectionBehavior(1)
        self.trl_table.setStyleSheet('font-size: 12px')
        self.trl_table.verticalHeader().hide()
        self.trl_table.clicked.connect(self.trl_selected)
        self.trl_table.clicked.connect(self.completeChanged)
        col_header = self.trl_table.horizontalHeader()
        col_header.setSectionResizeMode(col_header.Stretch)
        col_header.setStyleSheet('font-weight: bold')
        self.trl_table.resizeRowsToContents()
        self.trl_table.setSizePolicy(QSizePolicy.Expanding,
                                     QSizePolicy.Expanding)
        ml_page_layout.addWidget(self.trl_table)
        self.trl_label = NameLabel('Selected TRL:')
        self.trl_label.setVisible(False)
        self.trl_value_label = ValueLabel('')
        self.trl_value_label.setVisible(False)
        trl_layout = QHBoxLayout()
        trl_layout.addWidget(self.trl_label)
        trl_layout.addWidget(self.trl_value_label)
        trl_layout.addStretch(1)
        ml_page_layout.addLayout(trl_layout)

    def initializePage(self):
        wizard_state['trl'] = None

    def trl_selected(self, clicked_index):
        clicked_row = clicked_index.row()
        # orb.log.debug('* clicked row is "{}"'.format(clicked_row))
        wizard_state['trl'] = trls[clicked_row]
        # orb.log.debug('  trl selected is: {}'.format(trls[clicked_row]))
        trl = wizard_state.get('trl')
        trl_nbr = trl.get('trl', '[not set]')
        # orb.log.debug('  ... which is "{}"'.format(trl_nbr))
        if trl:
            self.trl_label.setVisible(True)
            self.trl_value_label.setText(str(trl_nbr))
            self.trl_value_label.setVisible(True)

    def resizeEvent(self, event):
        self.trl_table.resizeRowsToContents()

    def isComplete(self):
        """
        Return `True` when the page is complete, which activates the `Next`
        button.
        """
        if wizard_state.get('trl'):
            return True
        return False


class ParametersPage(QWizardPage):
    """
    3. Specify Parameter Values
       * Mass
       * Power
       * Data Interface(s)
       * Dimensions
       * Image
       * CAD Model
    """
    def __init__(self, parent=None):
        super().__init__(parent=parent)

    def initializePage(self):
        pass


class NewProductWizardConclusionPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        main_layout = QVBoxLayout()
        form = QFormLayout()
        self.id_label = NameLabel('Product ID:')
        self.id_value_label = ValueLabel('')
        form.addRow(self.id_label, self.id_value_label)
        self.name_label = NameLabel('Product Name:')
        self.name_value_label = ValueLabel('')
        form.addRow(self.name_label, self.name_value_label)
        self.desc_label = NameLabel('Product Description:')
        self.desc_value_label = ValueLabel('', wrappable=True, w=400)
        form.addRow(self.desc_label, self.desc_value_label)
        self.pt_label = NameLabel('Product Type:')
        self.pt_value_label = ValueLabel('')
        form.addRow(self.pt_label, self.pt_value_label)
        self.trl_label = NameLabel('TRL:')
        self.trl_value_label = ValueLabel('')
        form.addRow(self.trl_label, self.trl_value_label)
        main_layout.addLayout(form)
        main_layout.addStretch(1)
        self.setLayout(main_layout)
        self.updateGeometry()

    def initializePage(self):
        p = orb.get(wizard_state['product_oid'])
        # orb.log.info('  - product found: {}'.format(p.id))
        self.setTitle('New Product: <font color="blue">{}</font>'.format(
                                                                    p.name))
        self.setSubTitle("Click <b>Finish</b> to use these values<br>"
                         "or click <b>Back</b> to change them ...")
        trl = wizard_state.get('trl')
        trl_value = int(trl['trl'])
        set_dval(p.oid, 'TRL', trl_value)
        # populate value fields ...
        self.id_value_label.setText(p.id)
        self.name_value_label.setText(p.name)
        self.desc_value_label.setText(p.description)
        self.pt_value_label.setText(p.product_type.name)
        self.trl_value_label.setText(str(trl_value))
        orb.save([p])
        dispatcher.send(signal='modified object', obj=p)


#################################
#  Concept Wizard Pages
#################################

class ConceptWizard(QWizard):
    """
    Wizard to assist in defining top-level requirements and parameters for a
    Mission or Instrument Concept.
    """
    def __init__(self, parent=None): 
        super().__init__(parent=parent)
        intro_label = QLabel(
                "<p/>Blah blah blah."
                "<br>This wizard will assist in blah!")
        self.addPage(ConceptIntroPage(intro_label, parent=self))
        self.addPage(ConceptConclusionPage(self))
        self.setGeometry(50, 50, 800, 500)
        self.setSizeGripEnabled(True)
        self.setWindowTitle("Concept Wizard")


class ConceptIntroPage(QWizardPage):
    """
    Intro page for Concept Wizard.
    """
    def __init__(self, intro_label, parent=None):
        super().__init__(parent=parent)
        self.setTitle("Introduction")
        layout = QHBoxLayout()
        logo_path = config.get('tall_logo')
        if logo_path:
            image_path = os.path.join(orb.image_dir, logo_path)
            layout.addWidget(PlaceHolder(image=image_path, parent=self))
        layout.addWidget(intro_label)
        self.setLayout(layout)


class ConceptConclusionPage(object):
    pass

if __name__ == '__main__':

    import sys

    app = QApplication(sys.argv)
    wizard = DataImportWizard(file_path='')
    wizard.show()
    sys.exit(app.exec_())

