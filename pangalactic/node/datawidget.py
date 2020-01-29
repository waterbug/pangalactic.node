"""
A DataMatrix-based collaborative data table widget.
"""
from PyQt5.QtCore import QDate, QPoint, Qt
from PyQt5.QtGui import QColor, QIcon, QKeySequence, QPainter, QPixmap
from PyQt5.QtWidgets import (QAction, QActionGroup, QApplication, QColorDialog,
        QComboBox, QDialog, QFontDialog, QGroupBox, QHBoxLayout, QLabel,
        QLineEdit, QMessageBox, QPushButton, QTableWidget,
        QTableWidgetItem, QToolBar, QVBoxLayout)
from PyQt5.QtPrintSupport import QPrinter, QPrintPreviewDialog


class DataMatrixWidget(QTableWidget):
    """
    A collaborative data table widget.
    """
    def __init__(self, datamatrix, parent=None):
        """
        Initialize.

        Args:
            datamatrix (DataMatrix): the table's DataMatrix instance
        """
        if datamatrix.schema:
            data = datamatrix.data or {list(datamatrix.schema.keys())[0]:
                                       'no data found.'}
        else:
            datamatrix.schema = {'0': {}}
            datamatrix.data = {'0': 'no schema found.'}
        rows = len(data) or 1
        cols = len(datamatrix.schema) or 20
        super(DataMatrixWidget, self).__init__(rows, cols, parent)
        # self.toolbar = QToolBar()
        # self.addToolBar(self.toolbar)
        self.setTextElideMode(Qt.ElideNone)
        self.setSelectionBehavior(self.SelectRows)
        self.setSortingEnabled(False)
        header = self.horizontalHeader()
        header.setStyleSheet(
                           'QHeaderView { font-weight: bold; '
                           'font-size: 14px; border: 1px; } '
                           'QToolTip { font-weight: normal; '
                           'font-size: 12px; border: 2px solid; };')
        labels = [col['label'] or col['name']
                  for col in datamatrix.schema.values()]
        for i, label in enumerate(labels):
            self.setHorizontalHeaderItem(i, QTableWidgetItem(label))
        for col in range(cols):
            self.resizeColumnToContents(col)

