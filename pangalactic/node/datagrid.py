"""
A DataMatrix-based collaborative data table widget.
"""
from PyQt5.QtCore import QDate, QPoint, Qt
from PyQt5.QtGui import QColor, QIcon, QKeySequence, QPainter, QPixmap
from PyQt5.QtWidgets import (QAction, QActionGroup, QApplication, QColorDialog,
        QComboBox, QDateTimeEdit, QDialog, QFontDialog, QGroupBox, QHBoxLayout,
        QLabel, QStyledItemDelegate, QLineEdit, QMessageBox, QPushButton,
        QTableWidget, QTableWidgetItem, QToolBar, QVBoxLayout)
from PyQt5.QtPrintSupport import QPrinter, QPrintPreviewDialog

from pangalactic.core.uberorb import orb

from louie import dispatcher


class DataGrid(QTableWidget):
    """
    A collaborative data table widget.
    """
    def __init__(self, datamatrix, parent=None):
        """
        Initialize.

        Args:
            datamatrix (DataMatrix): the table's DataMatrix instance
        """
        self.dm = datamatrix
        rows = len(self.dm) or 0
        cols = len(self.dm.schema) or 1
        super(DataGrid, self).__init__(rows, cols, parent)
        # self.toolbar = QToolBar()
        # self.addToolBar(self.toolbar)
        self.setItemDelegate(DataGridDelegate(self))
        self.setSelectionBehavior(self.SelectRows)
        self.setSortingEnabled(False)
        header = self.horizontalHeader()
        header.setStyleSheet(
                           'QHeaderView { font-weight: bold; '
                           'font-size: 14px; border: 1px; } '
                           'QToolTip { font-weight: normal; '
                           'font-size: 12px; border: 2px solid; };')
        labels = [col['label'] or col['name']
                  for col in self.dm.schema.values()]
        for i, label in enumerate(labels):
            self.setHorizontalHeaderItem(i, QTableWidgetItem(label))
        for col in range(cols):
            self.resizeColumnToContents(col)

class DataGridItem(QTableWidgetItem):

    def __init__(self, text=None):
        if text is not None:
            super(DataGridItem, self).__init__(text)
        else:
            super(DataGridItem, self).__init__()

    def data(self, role):
        if role in (Qt.EditRole, Qt.StatusTipRole):
            return self.text()
        if role == Qt.DisplayRole:
            return self.text()
        t = str(self.text())
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
        return super(DataGridItem, self).data(role)

    def setData(self, role, value):
        super(DataGridItem, self).setData(role, value)
        if self.tableWidget():
            self.tableWidget().viewport().update()

class DataGridDelegate(QStyledItemDelegate):

    def __init__(self, parent=None):
        super(DataGridDelegate, self).__init__(parent)

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
        if isinstance(editor, QLineEdit):
            model.setData(index, editor.text())
            col = index.column()
            row = index.row()
            row_oid = self.parent().dm[row]['oid']
            colnames = list(self.parent().dm.schema)
            orb.log.debug('setModelData: ({}, {}): "{}"'.format(
                                colnames[col], row, editor.text()))
            dispatcher.send('item updated', oid=self.parent().oid,
                            row_oid=row_oid, value=editor.text())
        elif isinstance(editor, QDateTimeEdit):
            model.setData(index, editor.date().toString('yyyy/MM/dd'))

