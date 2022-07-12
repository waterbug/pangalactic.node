# -*- coding: utf-8 -*-
"""
Wizards
"""
import os
from collections import OrderedDict as OD

from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.QtCore import Qt

# import pandas as pd

from louie import dispatcher

# pangalactic
from pangalactic.core             import config, state
from pangalactic.core.names       import get_external_name_plural
from pangalactic.core.parametrics import set_dval
from pangalactic.core.refdata     import trls
from pangalactic.core.uberorb     import orb
from pangalactic.core.utils.excelreader import get_raw_excel_data
from pangalactic.core.utils.xlsxreader import get_raw_xlsx_data
from pangalactic.node.filters     import FilterPanel
from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.tablemodels import ListTableModel, MappingTableModel
from pangalactic.node.utils       import clone
from pangalactic.node.widgets     import (AutosizingListView, NameLabel,
                                          PlaceHolder, ValueLabel)
from functools import reduce

# wizard_state keys:
#   - file_path
#   - dataset_name
#   - dataset
#   - heading_row
#   - column_names
#   - column_numbers
#   - product
#   - product_type

wizard_state = {}


class PrintLogger:
    def info(self, txt):
        print(txt)
    def debug(self, txt):
        print(txt)


#################################
#  Data Import Wizard Pages
#################################

class DataImportWizard(QtWidgets.QWizard):
    """
    Wizard to assist with importing data from a file.
    """

    def __init__(self, file_path='', width=1200, height=700, parent=None): 
        super().__init__(parent=parent)
        if not hasattr(orb, 'log'):
            orb.log = PrintLogger()
        orb.log.info('* [data import wizard]')
        self.setWizardStyle(QtWidgets.QWizard.ClassicStyle)
        # the included buttons must be specified using setButtonLayout in order
        # to get the "Back" button on Windows (it is automatically included on
        # Linux but not on Windows)
        included_buttons = [QtWidgets.QWizard.Stretch,
                            QtWidgets.QWizard.BackButton,
                            QtWidgets.QWizard.NextButton,
                            QtWidgets.QWizard.FinishButton,
                            QtWidgets.QWizard.CancelButton]
        self.setButtonLayout(included_buttons)
        self.setOptions(QtWidgets.QWizard.NoBackButtonOnStartPage)
        wizard_state['file_path'] = file_path
        txt = '<p/>You have selected the file<br>'
        txt += f'<font color="green"><b>&lt;{file_path}&gt;</b></font>.<br>'
        txt += 'This wizard will assist in importing data ...'
        intro_label = QtWidgets.QLabel(txt)
        intro_label.setWordWrap(False)
        self.addPage(DataIntroPage(intro_label, parent=self))
        self.addPage(DataSheetPage(parent=self))
        self.addPage(DataHeaderPage(parent=self))
        self.addPage(MetaDataPage(parent=self))
        self.addPage(DataImportConclusionPage(self))
        self.setGeometry(50, 50, width, height)
        self.setSizeGripEnabled(True)
        self.setWindowTitle("Data Import Wizard")


class DataIntroPage(QtWidgets.QWizardPage):
    """
    Data Import Wizard intro page.
    """
    def __init__(self, intro_label, parent=None):
        super().__init__(parent=parent)
        # TODO:  this page will identify the file type and ask the user what
        # type of data it is (semantic, numeric, etc.) and what the purpose of
        # the data is -- that will determine what type of container to use for
        # the data (db, pandas or xray dataframe, etc. ...)
        self.setTitle("Introduction")
        layout = QtWidgets.QHBoxLayout()
        logo_path = config.get('tall_logo')
        if logo_path:
            image_path = os.path.join(orb.image_dir, logo_path)
            layout.addWidget(PlaceHolder(image=image_path, parent=self))
        layout.addWidget(intro_label)
        self.setLayout(layout)


class DataSheetPage(QtWidgets.QWizardPage):
    """
    Page for selecting the sheet to import from an Excel file.
    """
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        # only file type currently supported is 'excel' ...
        fpath = wizard_state.get('file_path')
        if fpath:
            self.setTitle('Sheets loaded from the file: '
                          '<font color="blue"><code>%s</code></font>'
                          % os.path.basename(fpath))
            # self.setSubTitle("Select a sheet to import...")
            # import raw data from excel file
            self.datasets = {}
            if fpath.endswith('.xls'):
                self.datasets = get_raw_excel_data(fpath,
                                                   clear_empty_rows=False)
            elif fpath.endswith('.xlsx'):
                self.datasets = get_raw_xlsx_data(fpath,
                                                  clear_empty_rows=False,
                                                  read_only=True)
        else:
            return
        datasets_list_label = QtWidgets.QLabel(
                                    "<b>Select a sheet<br>to import:</b>")
        # sheet list widget
        self.sl_model = QtGui.QStandardItemModel(parent=self)
        sheet_names = list(self.datasets.keys())
        if sheet_names:
            for name in sheet_names:
                self.sl_model.appendRow(QtGui.QStandardItem(name))
        else:
            self.sl_model.appendRow('None')
        self.sheet_list_widget = AutosizingListView(self)
        self.sheet_list_widget.setModel(self.sl_model)
        self.sheet_list_widget.clicked.connect(self.on_select_dataset)
        self.sheet_list_widget.setSelectionMode(
                                QtWidgets.QAbstractItemView.ExtendedSelection)
        self.selection_model = self.sheet_list_widget.selectionModel()
        self.selection_model.select(self.sl_model.createIndex(0, 0),
                                QtCore.QItemSelectionModel.ToggleCurrent)
        self.vbox = QtWidgets.QVBoxLayout()
        self.vbox.addWidget(datasets_list_label,
                            alignment=Qt.AlignLeft|Qt.AlignTop)
        self.vbox.addWidget(self.sheet_list_widget,
                            alignment=Qt.AlignLeft|Qt.AlignTop)
        self.vbox.setStretch(1, 1)
        self.hbox = QtWidgets.QHBoxLayout()
        self.hbox.addLayout(self.vbox)
        self.set_dataset(sheet_names[0])
        self.setLayout(self.hbox)

    def on_select_dataset(self, idx):
        row = idx.row()
        # create table view for selected dataset
        dataset_name = str(self.sl_model.item(row).text())
        self.set_dataset(dataset_name)

    def set_dataset(self, dataset_name):
        current = wizard_state.get('dataset_name')
        if current and (current == dataset_name):
            return
        else:
            wizard_state['dataset_name'] = str(dataset_name)
            wizard_state['dataset'] = self.datasets[dataset_name]
        if hasattr(self, 'tableview'):
            self.hbox.removeWidget(self.tableview)
            self.tableview.setAttribute(Qt.WA_DeleteOnClose)
            self.tableview.parent = None
            self.tableview.close()
        tablemodel = ListTableModel(self.datasets[dataset_name],
                                    parent=self)
        self.tableview = QtWidgets.QTableView(self)
        self.tableview.setModel(tablemodel)
        self.tableview.resizeColumnsToContents()
        self.tableview.setSizeAdjustPolicy(self.tableview.AdjustToContents)
        self.hbox.addWidget(self.tableview, stretch=1,
                            alignment=Qt.AlignLeft|Qt.AlignTop)
        self.hbox.setStretch(1, 1)
        self.updateGeometry()


class DataHeaderPage(QtWidgets.QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.candidate_column_names = [] 
        wizard_state['heading_row'] = 0
        wizard_state['column_names'] = []
        wizard_state['column_numbers'] = []
        self.directions = QtWidgets.QLabel("<b>Click on the row<br>"
                                       "that contains<br>"
                                       "the column names...</b><br>"
                                       "<hr>")
        # set min. width so that when the column name checkboxes are added, the
        # panel is wide enough that no horizontal scroll bar appears ...
        self.directions.setMinimumWidth(200)
        self.vbox = QtWidgets.QVBoxLayout()
        self.vbox.addWidget(self.directions,
                            alignment=Qt.AlignLeft|Qt.AlignTop)
        self.hbox = QtWidgets.QHBoxLayout()
        self.hbox.addLayout(self.vbox)

    def initializePage(self):
        # TODO:  check self.vbox for a column listing from a previous
        # instantiation -- if one is found, remove it ...
        self.setTitle('Column Headings for <font color="blue">%s</font>'
                      % wizard_state['dataset_name'])
        tablemodel = ListTableModel(wizard_state['dataset'], parent=self)
        if hasattr(self, 'tableview'):
            self.tableview.setParent(None)
        self.tableview = QtWidgets.QTableView(self)
        self.tableview.setModel(tablemodel)
        self.tableview.resizeColumnsToContents()
        self.tableview.setSizeAdjustPolicy(self.tableview.AdjustToContents)
        self.tableview.setSelectionBehavior(self.tableview.SelectRows)
        self.tableview.setSelectionMode(self.tableview.SingleSelection)
        self.tableview.clicked.connect(self.on_row_clicked)
        row_header = self.tableview.verticalHeader()
        row_header.sectionClicked.connect(self.on_row_header_clicked)
        self.hbox.addWidget(self.tableview, stretch=1,
                            alignment=Qt.AlignLeft|Qt.AlignTop)
        self.updateGeometry()
        self.setLayout(self.hbox)

    def on_row_clicked(self, idx):
        self.get_col_names(idx.row())

    def on_row_header_clicked(self, idx):
        self.get_col_names(idx)

    def get_col_names(self, row):
        """
        Get data contents of row that is specified to contain column names.
        """
        self.candidate_column_names = wizard_state['dataset'][row] 
        wizard_state['heading_row'] = row
        self.directions.setText("<b>Select the columns<br>"
                                "to be imported:</b><br>"
                                "<hr>")
        # if there are checkboxes from a previous call, remove them ...
        if hasattr(self, 'cb_layout'):
            for i in reversed(list(range(self.cb_layout.count()))):
                self.cb_layout.itemAt(i).widget().setParent(None)
            self.cb_layout.setParent(None)
            self.cb_container.setParent(None)
            self.cb_scrollarea.setParent(None)
        self.cbs = []
        self.cb_scrollarea = QtWidgets.QScrollArea()
        self.cb_scrollarea.setWidgetResizable(True)
        self.cb_container = QtWidgets.QWidget()
        self.cb_scrollarea.setWidget(self.cb_container)
        self.cb_layout = QtWidgets.QGridLayout(self.cb_container)
        self.cb_all = QtWidgets.QCheckBox()
        self.cb_all.clicked.connect(self.on_check_all)
        self.cb_all.clicked.connect(self.completeChanged)
        cb_all_label = QtWidgets.QLabel('<b>SELECT ALL</b>')
        self.cb_layout.addWidget(self.cb_all, 0, 0)
        self.cb_layout.addWidget(cb_all_label, 0, 1)
        self.cbs.append(self.cb_all)
        for i, name in enumerate(self.candidate_column_names):
            cb = QtWidgets.QCheckBox()
            cb.clicked.connect(self.completeChanged)
            cb.clicked.connect(self.on_check_cb)
            cb_label = QtWidgets.QLabel(name)
            cb_label.setFixedWidth(100)
            cb_label.setWordWrap(True)
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

    def on_check_cb(self):
        wizard_state['column_names'] = []
        wizard_state['column_numbers'] = []
        for i in range(len(self.candidate_column_names)):
            if self.cbs[i+1].isChecked():
                wizard_state['column_names'].append(self.candidate_column_names[i])
                wizard_state['column_numbers'].append(i)
        orb.log.debug('* wizard: selected columns:')
        for i, n in zip(wizard_state['column_numbers'],
                        wizard_state['column_names']):
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


class MetaDataPage(QtWidgets.QWizardPage):
    """
    Page to specify the object type to map the data into and a mapping from the
    data columns to attributes into which the data will be imported.
    """
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.object_types = ['HardwareProduct', 'Requirement']
        self.widgets_added = False
        self.column_names = wizard_state.get('column_names') or []

    def initializePage(self):
        if self.widgets_added:
            if self.column_names != wizard_state.get('column_names'):
                # re-generate mapping area for the new column selections ...
                if getattr(self, 'mapping_scrollarea', None):
                    self.vbox.removeWidget(self.mapping_scrollarea)
                    self.mapping_scrollarea.setAttribute(Qt.WA_DeleteOnClose)
                    self.mapping_scrollarea.parent = None
                    self.mapping_scrollarea.close()
                    self.mapping_scrollarea = None
                self.mapping_scrollarea = QtWidgets.QScrollArea()
                self.mapping_scrollarea.setWidgetResizable(True)
                self.mapping_scrollarea.setMinimumWidth(300)
                mapping_container = QtWidgets.QWidget()
                self.mapping_scrollarea.setWidget(mapping_container)
                mapping_layout = QtWidgets.QGridLayout(mapping_container)
                arrow_image = QtGui.QPixmap(os.path.join(
                                                orb.home, 'icons', 'right_arrow.png'))
                arrow_label = QtWidgets.QLabel()
                arrow_label.setPixmap(arrow_image)
                for i, name in enumerate(wizard_state['column_names']):
                    col_label = QtWidgets.QLabel(f'<b>{name}</b>')
                    col_label.setFixedWidth(100)
                    col_label.setWordWrap(True)
                    col_label.setStyleSheet('border: 1px solid black;')
                    arrow_label = QtWidgets.QLabel()
                    arrow_label.setFixedWidth(20)
                    arrow_label.setPixmap(arrow_image)
                    target_label = QtWidgets.QLabel('<p>      </p>')
                    target_label.setFixedWidth(100)
                    target_label.setStyleSheet('border: 1px solid black;')
                    mapping_layout.addWidget(col_label, i, 0)
                    mapping_layout.addWidget(arrow_label, i, 1)
                    mapping_layout.addWidget(target_label, i, 2)
                self.vbox.addWidget(self.mapping_scrollarea)
                                    # alignment=Qt.AlignLeft|Qt.AlignTop)
                self.vbox.setStretchFactor(self.mapping_scrollarea, 1)
        else:
            self.add_widgets()

    def add_widgets(self):
        self.directions = QtWidgets.QLabel(
                                "<h3>Directions:</h3>"
                                "<ol><b>"
                                "<li>Select target object type</li>"
                                "<li>Map data columns to attributes</li>"
                                "</ol></b><hr>")
        # set min. width so that when the column name checkboxes are added, the
        # panel is wide enough that no horizontal scroll bar appears ...
        self.directions.setMinimumWidth(200)
        self.vbox = QtWidgets.QVBoxLayout()
        self.vbox.setSpacing(10)
        self.vbox.addWidget(self.directions,
                            alignment=Qt.AlignLeft|Qt.AlignTop)
        self.hbox = QtWidgets.QHBoxLayout()
        self.hbox.setSpacing(50)
        self.hbox.addLayout(self.vbox)
        self.setTitle('Data Mapping for <font color="blue">%s</font>'
                      % wizard_state['dataset_name'])
        self.vbox.addWidget(QtWidgets.QLabel(
                        "<b>Select target object type</b>"),
                        alignment=Qt.AlignLeft|Qt.AlignTop)
        self.object_type_buttons = QtWidgets.QButtonGroup()
        self.hw_button = QtWidgets.QRadioButton('HardwareProduct')
        self.reqt_button = QtWidgets.QRadioButton('Requirement')
        self.object_type_buttons.addButton(self.hw_button)
        self.object_type_buttons.addButton(self.reqt_button)
        if wizard_state.get('cname', None):
            self.object_type = wizard_state['cname']
        else:
            self.object_type = 'HardwareProduct'
        orb.log.debug(f'* object type: "{self.object_type}"')
        if self.object_type == 'HardwareProduct':
            self.hw_button.setChecked(True)
        elif self.object_type == 'Requirement':
            self.reqt_button.setChecked(True)
        self.object_type_buttons.buttonClicked.connect(
                                        self.on_set_object_type)
        radio_button_layout = QtWidgets.QVBoxLayout()
        radio_button_layout.addWidget(self.hw_button)
        radio_button_layout.addWidget(self.reqt_button)
        self.vbox.addLayout(radio_button_layout)
        self.vbox.addWidget(QtWidgets.QLabel("<hr>"))
        # mapping construction, using 3 vertical columns:
        # (1) selected column names
        # (2) empty labels into which the target attribute will be dropped
        # (3) attributes of the target object type
        self.mapping_scrollarea = QtWidgets.QScrollArea()
        self.mapping_scrollarea.setWidgetResizable(True)
        self.mapping_scrollarea.setMinimumWidth(300)
        mapping_container = QtWidgets.QWidget()
        self.mapping_scrollarea.setWidget(mapping_container)
        mapping_layout = QtWidgets.QGridLayout(mapping_container)
        arrow_image = QtGui.QPixmap(os.path.join(
                                        orb.home, 'icons', 'right_arrow.png'))
        arrow_label = QtWidgets.QLabel()
        arrow_label.setPixmap(arrow_image)
        for i, name in enumerate(wizard_state['column_names']):
            col_label = QtWidgets.QLabel(f'<b>{name}</b>')
            col_label.setFixedWidth(100)
            col_label.setWordWrap(True)
            col_label.setStyleSheet('border: 1px solid black;')
            arrow_label = QtWidgets.QLabel()
            arrow_label.setFixedWidth(20)
            arrow_label.setPixmap(arrow_image)
            target_label = QtWidgets.QLabel('<p>      </p>')
            target_label.setFixedWidth(100)
            target_label.setStyleSheet('border: 1px solid black;')
            mapping_layout.addWidget(col_label, i, 0)
            mapping_layout.addWidget(arrow_label, i, 1)
            mapping_layout.addWidget(target_label, i, 2)
        self.vbox.addWidget(self.mapping_scrollarea)
                            # alignment=Qt.AlignLeft|Qt.AlignTop)
        self.vbox.setStretchFactor(self.mapping_scrollarea, 1)
        # *******************************************************************
        # Table displaying the selected dataset ...
        # *******************************************************************
        # remove rows above the specified heading_row ...
        new_dataset = wizard_state['dataset'][wizard_state['heading_row']:]
        # include only the columns specified for import ...
        new_dataset = [[row[i] for i in wizard_state['column_numbers']]
                                             for row in new_dataset]
        tablemodel = ListTableModel(new_dataset, parent=self)
        if hasattr(self, 'tableview'):
            self.tableview.setParent(None)
        self.tableview = QtWidgets.QTableView(self)
        self.tableview.setModel(tablemodel)
        self.tableview.resizeColumnsToContents()
        self.tableview.setSizeAdjustPolicy(self.tableview.AdjustToContents)
        self.tableview.setSelectionBehavior(self.tableview.SelectRows)
        self.tableview.setSelectionMode(self.tableview.SingleSelection)
        self.tableview.clicked.connect(self.on_row_clicked)
        row_header = self.tableview.verticalHeader()
        row_header.sectionClicked.connect(self.on_row_header_clicked)
        self.hbox.addWidget(self.tableview, stretch=1,
                            alignment=Qt.AlignLeft|Qt.AlignTop)
        self.setLayout(self.hbox)
        self.updateGeometry()
        self.widgets_added = True

    def on_set_object_type(self):
        """
        Handle selection of object type.
        """
        b = self.object_type_buttons.checkedButton()
        self.object_type = b.text()
        wizard_state['cname'] = self.object_type
        orb.log.debug(f'* object type: "{self.object_type}"')

    def on_row_clicked(self, idx):
        orb.log.debug('* wizard: row {} is selected'.format(idx.row()))
        self.get_col_names(idx.row())

    def on_row_header_clicked(self, idx):
        orb.log.debug('Row header {} was clicked'.format(idx))
        self.get_col_names(idx)

    def isComplete(self):
        """
        Return `True` when the page is complete, which cases the **Next**
        button to be activated.
        """
        # TODO:  return True when all column types have been set.
        if hasattr(self, 'cbs'):
            for cb in self.cbs:
                if cb.isChecked():
                    return True
            return False
        else:
            return False


class DataImportConclusionPage(QtWidgets.QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

    def initializePage(self):
        # finishText = self.wizard().buttonText(QtWidgets.QWizard.FinishButton)
        # finishText.replace('&', '')
        new_dataset = wizard_state['dataset'][wizard_state['heading_row']:]
        # include only the columns specified for import ...
        new_dataset = [[row[i] for i in wizard_state['column_numbers']]
                                             for row in new_dataset]
        self.setTitle('Dataset <font color="blue">%s</font>'
                      % wizard_state['dataset_name'])
        self.setSubTitle("Click <b>Finish</b> to save this dataset ...")
        tablemodel = ListTableModel(new_dataset, parent=self)
        if hasattr(self, 'tableview'):
            self.tableview.setParent(None)
        self.tableview = QtWidgets.QTableView(self)
        self.tableview.setModel(tablemodel)
        self.tableview.resizeColumnsToContents()
        self.tableview.setSizeAdjustPolicy(self.tableview.AdjustToContents)
        self.tableview.setSelectionBehavior(self.tableview.SelectRows)
        self.tableview.setSelectionMode(self.tableview.SingleSelection)
        # row_header = self.tableview.verticalHeader()
        # self.vbox = QtWidgets.QVBoxLayout()
        # self.vbox.addWidget(self.tableview, stretch=1,
                            # alignment=Qt.AlignLeft|Qt.AlignTop)
        # self.addLayout(self.vbox)
        self.updateGeometry()
        self.resize(self.parent().geometry().width(),
                    self.parent().geometry().height())


#################################
#  New Product Wizard Pages
#################################

class NewProductWizard(QtWidgets.QWizard):
    """
    Wizard to assist in creating new components (Products) and associated Models.
    """

    def __init__(self, parent=None): 
        super().__init__(parent=parent)
        orb.log.info('* opening Product Wizard ...')
        self.setWizardStyle(QtWidgets.QWizard.ClassicStyle)
        # the included buttons must be specified using setButtonLayout in order
        # to get the "Back" button on Windows (it is automatically included on
        # Linux but not on Windows)
        included_buttons = [QtWidgets.QWizard.Stretch,
                            QtWidgets.QWizard.BackButton,
                            QtWidgets.QWizard.NextButton,
                            QtWidgets.QWizard.FinishButton,
                            QtWidgets.QWizard.CancelButton]
        self.setButtonLayout(included_buttons)
        self.setOptions(QtWidgets.QWizard.NoBackButtonOnStartPage)
        wizard_state['product_oid'] = None
        intro_label = QtWidgets.QLabel(
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
        # 1. Select Product Type
        ### NOTE:  now using pgxnobject to select the product type
        # self.addPage(ProductTypePage(parent=self))
        # 2. Select Maturity Level (TRL)
        self.addPage(MaturityLevelPage(parent=self))
        # 3. Specify Interfaces and Parameter Values
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

class IdentificationPage(QtWidgets.QWizardPage):
    """
    0. Identify Product
    """
    def __init__(self, intro_label, parent=None):
        super().__init__(parent=parent)
        self.setTitle("Product Identification")
        self.setSubTitle("Identify the product you are creating ...")
        layout = QtWidgets.QHBoxLayout()
        logo_path = config.get('tall_logo')
        if logo_path:
            image_path = os.path.join(orb.image_dir, logo_path)
            layout.addWidget(PlaceHolder(image=image_path, parent=self))
        self.setLayout(layout)

    def initializePage(self):
        orb.log.info('* [comp wizard] new_product()')
        # TODO:  new dialog to select Template
        proj_oid = state.get('project')
        project = orb.get(proj_oid)
        product = clone('HardwareProduct', owner=project, public=True)
        wizard_state['product_oid'] = product.oid
        # include version -- but it's allowed to be empty (blank)
        view = ['id', 'name', 'product_type', 'version', 'owner',
                'description', 'public']
        required = ['name', 'description', 'owner', 'product_type']
        panels = ['main']
        self.pgxn_obj = PgxnObject(product, embedded=True, panels=panels,
                                   view=view, required=required,
                                   edit_mode=True, new=True,
                                   enable_delete=False)
        # hide tool bar (clone etc.)
        self.pgxn_obj.toolbar.hide()
        self.pgxn_obj.save_button.clicked.connect(self.completeChanged)
        self.pgxn_obj.setAttribute(Qt.WA_DeleteOnClose)
        self.wizard().button(QtWidgets.QWizard.FinishButton).clicked.connect(
                                                         self.close_pgxn_obj)
        inst_label = QtWidgets.QLabel(instructions)
        id_panel_layout = QtWidgets.QVBoxLayout()
        id_panel_layout.addWidget(inst_label)
        id_panel_layout.addWidget(self.pgxn_obj)
        id_panel_layout.addStretch(1)
        main_layout = self.layout()
        main_layout.addLayout(id_panel_layout)

    def close_pgxn_obj(self):
        if getattr(self, 'pgxn_obj', None):
            self.pgxn_obj.close()
            self.pgxn_obj = None

    def isComplete(self):
        """
        Return `True` when the page is complete, which activates the `Next`
        button.
        """
        if self.pgxn_obj.edit_mode:
            if hasattr(self.pgxn_obj, 'save_button'):
                self.pgxn_obj.save_button.clicked.connect(self.completeChanged)
            return False
        if hasattr(self.pgxn_obj, 'edit_button'):
            self.pgxn_obj.edit_button.clicked.connect(self.completeChanged)
        return True


class ProductTypePage(QtWidgets.QWizardPage):
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
        orb.log.debug('[comp wiz] checking for project/roles/disciplines ...')
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
                orb.log.debug('[comp wiz] - no assigned roles found on '
                              'project "{}".'.format(project.id))
        else:
            orb.log.debug('[comp wiz] - either no project found or no '
                          'assigned roles found or no role map.')
        if disciplines:
            orb.log.debug('[comp wiz] - disciplines found:')
            for d in disciplines:
                orb.log.debug('             {}'.format(d.id))
        else:
            orb.log.debug('[comp wiz] - no disciplines found '
                          'related to assigned roles.')
        hbox = QtWidgets.QHBoxLayout()
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
        discipline_panel = QtWidgets.QGroupBox('Disciplines')
        vbox = QtWidgets.QVBoxLayout()
        discipline_panel.setLayout(vbox)
        self.cb_all = QtWidgets.QCheckBox('SELECT ALL / CLEAR SELECTIONS')
        self.cb_all.clicked.connect(self.on_check_all)
        vbox.addWidget(self.cb_all)
        all_disciplines = orb.get_by_type('Discipline')
        self.checkboxes = {}
        for d in all_disciplines:
            checkbox = QtWidgets.QCheckBox(d.name)
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
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addLayout(hbox)
        self.pt_label = NameLabel('Selected Product Type:')
        self.pt_label.setVisible(False)
        self.pt_value_label = ValueLabel('')
        self.pt_value_label.setVisible(False)
        pt_layout = QtWidgets.QHBoxLayout()
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
        clicked_row = clicked_index.row()
        orb.log.debug('* clicked row is "{}"'.format(clicked_row))
        mapped_row = self.product_type_panel.proxy_model.mapToSource(
                                                        clicked_index).row()
        self.pt = self.product_type_panel.objs[mapped_row]
        orb.log.debug(
            '  product type selected [mapped row] is: {}'.format(mapped_row))
        pt_name = getattr(self.pt, 'name', '[not set]')
        orb.log.debug('  ... which is "{}"'.format(pt_name))
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


class MaturityLevelPage(QtWidgets.QWizardPage):
    """
    2. Select Maturity Level (TRL)
    """
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setTitle("Maturity Level / Technology Readiness Level (TRL)")
        self.setSubTitle("Select the TRL of the product by clicking on a row "
                         "in the TRL table ...")
        ml_page_layout = QtWidgets.QVBoxLayout()
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
        self.trl_table = QtWidgets.QTableView()
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
        self.trl_table.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                     QtWidgets.QSizePolicy.Expanding)
        ml_page_layout.addWidget(self.trl_table)
        self.trl_label = NameLabel('Selected TRL:')
        self.trl_label.setVisible(False)
        self.trl_value_label = ValueLabel('')
        self.trl_value_label.setVisible(False)
        trl_layout = QtWidgets.QHBoxLayout()
        trl_layout.addWidget(self.trl_label)
        trl_layout.addWidget(self.trl_value_label)
        trl_layout.addStretch(1)
        ml_page_layout.addLayout(trl_layout)

    def initializePage(self):
        wizard_state['trl'] = None

    def trl_selected(self, clicked_index):
        clicked_row = clicked_index.row()
        orb.log.debug('* clicked row is "{}"'.format(clicked_row))
        wizard_state['trl'] = trls[clicked_row]
        orb.log.debug('  trl selected is: {}'.format(trls[clicked_row]))
        trl = wizard_state.get('trl')
        trl_nbr = trl.get('trl', '[not set]')
        orb.log.debug('  ... which is "{}"'.format(trl_nbr))
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


class ParametersPage(QtWidgets.QWizardPage):
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


class NewProductWizardConclusionPage(QtWidgets.QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        main_layout = QtWidgets.QVBoxLayout()
        form = QtWidgets.QFormLayout()
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
        orb.log.info('  - product found: {}'.format(p.id))
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

class ConceptWizard(QtWidgets.QWizard):
    """
    Wizard to assist in defining top-level requirements and parameters for a
    Mission or Instrument Concept.
    """
    def __init__(self, parent=None): 
        super().__init__(parent=parent)
        intro_label = QtWidgets.QLabel(
                "<p/>Blah blah blah."
                "<br>This wizard will assist in blah!")
        self.addPage(ConceptIntroPage(intro_label, parent=self))
        self.addPage(ConceptConclusionPage(self))
        self.setGeometry(50, 50, 800, 500)
        self.setSizeGripEnabled(True)
        self.setWindowTitle("Concept Wizard")


class ConceptIntroPage(QtWidgets.QWizardPage):
    """
    Intro page for Concept Wizard.
    """
    def __init__(self, intro_label, parent=None):
        super().__init__(parent=parent)
        self.setTitle("Introduction")
        layout = QtWidgets.QHBoxLayout()
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

    app = QtWidgets.QApplication(sys.argv)
    wizard = DataImportWizard(file_path='')
    wizard.show()
    sys.exit(app.exec_())

