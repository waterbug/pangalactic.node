# -*- coding: utf-8 -*-
"""
A DataMatrix-based collaborative data table widget.
"""
from PyQt5.QtCore import QDate, QPoint, Qt
from PyQt5.QtGui import QColor, QIcon, QKeySequence, QPainter, QPixmap
from PyQt5.QtWidgets import (QAction, QActionGroup, QApplication, QColorDialog,
        QComboBox, QDateTimeEdit, QDialog, QFontDialog, QGroupBox, QHBoxLayout,
        QLabel, QStyledItemDelegate, QLineEdit, QMessageBox, QPushButton,
        QTableWidget, QTableWidgetItem, QVBoxLayout)
from PyQt5.QtPrintSupport import QPrinter, QPrintPreviewDialog

from uuid import uuid4

from pangalactic.core                  import config
from pangalactic.core.utils.datamatrix import DataMatrix
from pangalactic.core.uberorb          import orb

from louie import dispatcher


class DataGrid(QTableWidget):
    """
    A collaborative data table widget.
    """
    def __init__(self, project, schema_name=None, parent=None):
        """
        Initialize.

        Args:
            project (Project): a Project instance

        Keyword Args:
            schema_name (str): name of a stored schema
        """
        super(QTableWidget, self).__init__(parent)
        # first check for a cached datamatrix:
        project = project or orb.get('pgefobjects:SANDBOX')
        schema_name = schema_name or "MEL"
        dm_oid = project.id + '-' + schema_name
        self.dm = orb.data.get(dm_oid)
        if not self.dm:
            # if no cached datamatrix is found, create a new one:
            self.dm = DataMatrix(project=project, schema_name=schema_name)
        rows = len(self.dm) or 0
        cols = len(self.dm.schema) or 1
        super(DataGrid, self).__init__(rows, cols, parent)
        self.setItemDelegate(DGDelegate(self))
        self.setSelectionBehavior(self.SelectRows)
        self.setSortingEnabled(False)
        header = self.horizontalHeader()
        header.setStyleSheet(
                           'QHeaderView { font-weight: bold; '
                           'font-size: 14px; border: 1px; } '
                           'QToolTip { font-weight: normal; '
                           'font-size: 12px; border: 2px solid; };')
        # TODO: create 'dedz' cache and look up col label/name there ...
        #       the stuff below is for prototyping ...
        # labels = [col['label'] or col['name'] for col in self.dm.schema]
        if config.get('deds') and config['deds'].get('mel_deds'):
            mel_deds = config['deds']['mel_deds']
            labels = [mel_deds[deid].get('label', deid)
                      for deid in mel_deds]
        else:
            labels = self.dm.schema or ['Data']
        for i, label in enumerate(labels):
            self.setHorizontalHeaderItem(i, QTableWidgetItem(label))
        for col in range(cols):
            self.resizeColumnToContents(col)
        if self.dm:
            for row in self.dm.values():
                for col_id in self.dm.schema:
                    if row.get(col_id, ''):
                        self.set_item_value(row.get('oid'), col_id,
                                            row[col_id])
        dispatcher.connect(self.new_row, 'dm new row')

    def new_row(self):
        orb.log.debug('new_row()')
        row_nbr = len(self.dm)
        self.insertRow(row_nbr)
        row_oid = str(uuid4())
        row = dict(oid=row_oid)
        self.dm[row['oid']] = row
        orb.log.debug(' - self.dm is now {}'.format(str(self.dm)))

    def add_row(self, row):
        new_row = len(self.dm)
        self.insertRow(new_row)
        # if row doesn't have an oid, give it one
        if not row.get('oid'):
            row['oid'] = str(uuid4())
        self.dm[row['oid']] = row
        for elem_id, val in enumerate(row.items()):
            if elem_id in self.dm.schema:
                # TODO: put value into appropriate cell ...
                pass

    def set_item_value(self, row_oid, col_id, value):
        row_oids = list(self.dm.keys())
        if row_oid in row_oids:
            row_nbr = row_oids.index(row_oid)
            if col_id in self.dm.schema:
                col_nbr = self.dm.schema.index(col_id)
                self.setItem(row_nbr, col_nbr,
                             QTableWidgetItem(str(value)))

class DGItem(QTableWidgetItem):

    def __init__(self, text=None):
        text = text or ''
        super(DGItem, self).__init__(text)

    def clone(self):
        return super(DGItem, self).data(Qt.DisplayRole)

    def data(self, role):
        if role in (Qt.EditRole, Qt.StatusTipRole, Qt.DisplayRole): 
            return self.text()
        if role == Qt.DisplayRole:
            return self.display()
        t = str(self.display())
        try:
            number = int(t)
        except ValueError:
            number = None
        if role == Qt.TextColorRole:
            if number is None:
                return QColor(Qt.black)
            elif number < 0:
                return QColor(Qt.red)
            return QColor(Qt.blue)
        if role == Qt.TextAlignmentRole:
            if t and (t[0].isdigit() or t[0] == '-'):
                return Qt.AlignRight | Qt.AlignVCenter
        return super(DGItem, self).data(role)

    def setData(self, role, value):
        super(DGItem, self).setData(role, value)
        if self.tableWidget():
            self.tableWidget().viewport().update()

    def display(self):
        # avoid circular dependencies
        if self.isResolving:
            return None
        self.isResolving = True
        result = self.computeFormula(self.formula(), self.tableWidget())
        self.isResolving = False
        return result


class DGDelegate(QStyledItemDelegate):

    def __init__(self, parent=None):
        super(DGDelegate, self).__init__(parent)

    def createEditor(self, parent, style, index):
        # TODO: check permission ...
        # TODO: detect column datatype ...
        if False:
            editor = QDateTimeEdit(parent)
            editor.setDisplayFormat('yyyy/MM/dd')
            editor.setCalendarPopup(True)
            return editor
        editor = QLineEdit(parent)
        editor.editingFinished.connect(self.commitAndCloseEditor)
        return editor

    def commitAndCloseEditor(self):
        editor = self.sender()
        self.commitData.emit(editor)
        self.closeEditor.emit(editor, QStyledItemDelegate.NoHint)

    def setEditorData(self, editor, index):
        if isinstance(editor, QLineEdit):
            editor.setText(index.model().data(index, Qt.EditRole))
        elif isinstance(editor, QDateTimeEdit):
            editor.setDate(QDate.fromString(
                index.model().data(index, Qt.EditRole), 'yyyy/MM/dd'))

    def setModelData(self, editor, model, index):
        orb.log.debug('setModelData()')
        if isinstance(editor, QLineEdit):
            model.setData(index, editor.text())
            colnum = index.column()
            rownum = index.row()
            dm = self.parent().dm
            col_id = dm.schema[colnum]
            row_oid = dm[list(dm.keys())[rownum]]['oid']
            # TODO: cast editor.text() to column datatype ...
            dm[row_oid][col_id] = editor.text()
            # NOTE: should not need to save() every time! dm is cached in
            # memory in the orb.data dict and will be saved at exit.
            # dm.save()
            orb.log.debug(' - ({}, {}): "{}"'.format(
                                rownum, col_id, editor.text()))
            orb.log.debug('datamatrix is now: {}'.format(str(dm)))
            dispatcher.send('item updated', oid=dm.oid,
                            row_oid=row_oid, value=editor.text())
        elif isinstance(editor, QDateTimeEdit):
            model.setData(index, editor.date().toString('yyyy/MM/dd'))

