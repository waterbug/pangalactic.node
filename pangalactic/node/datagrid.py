# -*- coding: utf-8 -*-
"""
A DataMatrix-based collaborative data table/tree widget.
"""
from PyQt5.QtCore import (Qt, QAbstractItemModel, QCoreApplication,
                          QItemSelectionModel, QMetaObject, QModelIndex, QRect)
# from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QAbstractItemView, QAction, QApplication, QLineEdit,
                             QMainWindow, QMenu, QMenuBar, QStatusBar,
                             QStyledItemDelegate, QTreeView, QVBoxLayout, QWidget)
# from PyQt5.QtWidgets import (QApplication, QStyledItemDelegate, QLineEdit,
                             # QTableWidgetItem, QTreeView)

from uuid import uuid4

from pangalactic.core                  import config
from pangalactic.core.utils.datamatrix import DataMatrix
from pangalactic.core.uberorb          import orb

from louie import dispatcher


class GridTreeItem:
    """
    Node in a DMTreeModel.

    Attributes:
        item_data (list):  list of values to be assigned to the item, in which
            the first value is the oid of the corresponding DataMatrix row
        oid (str):  defined as the first value in item_data, or ''

    Keyword Args:
        parent (GridTreeItem):  parent item of this item
    """
    def __init__(self, data, parent=None):
        """
        Initialize a GridTreeItem, which corresponds to a row in the DataMatrix
        of a DMTreeModel.

        Args:
            data (list):  list of values to be assigned to the item

        Keyword Args:
            parent (GridTreeItem):  parent item of this item
        """
        data_sum = str(data)[:30] + ' ...'
        orb.log.debug('* GridTreeItem({}) initializing ...'.format(
                                                              data_sum))
        self.parent_item = parent
        self.item_data = data[:]
        self.children = []

    @property
    def oid(self):
        if self.item_data:
            return self.item_data[0]
        else:
            return ''

    def child(self, row):
        if row < 0 or row >= len(self.children):
            return None
        return self.children[row]

    def childCount(self):
        return len(self.children)

    def childNumber(self):
        if self.parent_item != None:
            return self.parent_item.children.index(self)
        return 0

    def columnCount(self):
        return len(self.item_data)

    def data(self, column):
        if column < 0 or column >= len(self.item_data):
            return None
        return self.item_data[column]

    def insertChildren(self, position, count, columns):
        """
        Insert child items under current item.

        Args:
            position (int):  position at which to begin inserting
            count (int):  number of children to insert
            columns (int):  number of columns in each child

        Keyword Args:
            oids (list):  if a list of oids is supplied, they are the oids of
                rows the DMTreeModel's DataMatrix that are being added;
                therefore, they are not "new items" and the 'insertChildren()'
                call will not send a 'local new items' signal
        """
        orb.log.debug('  - GridTreeItem.insertChildren({}, {}, {})'.format(
                                                 position, count, columns))
        if position < 0 or position > len(self.children):
            return False
        new_items = []
        for row in range(count):
            data = [None for i in range(columns)]
            item = GridTreeItem(data, parent=self)
            self.children.insert(position, item)
            new_items.append(item)
        dispatcher.send(signal='dm new items', items=new_items)
        return True

    def insertColumns(self, position, columns):
        orb.log.debug('  - GridTreeItem.insertColumns({}, {})'.format(
                                                    position, str(columns)))
        if position < 0 or position > len(self.item_data):
            return False
        for column in range(columns):
            self.item_data.insert(position, '')
        for child in self.children:
            child.insertColumns(position, columns)
        return True

    def parent(self):
        return self.parent_item

    def removeChildren(self, position, count):
        orb.log.debug('  - GridTreeItem.removeChildren({}, {})'.format(
                                                      position, count))
        if position < 0 or position + count > len(self.children):
            return False
        for row in range(count):
            self.children.pop(position)
        return True

    def removeColumns(self, position, columns):
        orb.log.debug('  - GridTreeItem.removeColumns({}, {})'.format(
                                                    position, str(columns)))
        if position < 0 or position + columns > len(self.item_data):
            return False
        for column in range(columns):
            self.item_data.pop(position)
        for child in self.children:
            child.removeColumns(position, columns)
        return True

    def setData(self, column, value):
        if value:
            # only log if there is a non-None/non-zero value
            orb.log.debug('  - GridTreeItem.setData({}, {})'.format(
                                                     column, value))
        if column < 0 or column >= len(self.item_data):
            return False
        self.item_data[column] = value
        return True


class DMTreeModel(QAbstractItemModel):
    """
    A DataMatrix-based tree model.

    Attributes:
        items_by_oid (dict):  a dict that maps DataMatrix row oids to their
            corresponding GridTreeItem instances in the DMTreeModel.
        cell_to_index (dict): maps a DataMatrix (row_oid, col_id) tuple to the
            model index of a cell
        index_to_cell (dict): maps the index of a cell to a (row_oid, col_id)
            tuple in the DataMatrix
    """
    def __init__(self, project=None, schema_name=None, schema=None,
                 parent=None):
        """
        Initialize.

        Keyword Args:
            project (Project): associated project (becomes the owner of the DataSet
                that is created when the DataMatrix is saved)
            schema_name (str): name of a schema for lookup in
                config['dm_schemas'] -- if found, 'schema' arg will be ignored
            schema (list): list of data element ids (column "names")
            parent (QWidget):  parent widget
        """
        arguments = 'project={}, schema_name={}, schema={}'
        orb.log.debug('* DMTreeModel({}) initializing ...'.format(
                      arguments.format(getattr(project, 'id', 'None'),
                                       schema_name,
                                       str(schema))))
        super().__init__(parent)
        self.items_by_oid = {}
        self.cell_to_index = {}
        self.index_to_cell = {}
        self.dm = None
        if isinstance(project, orb.classes['Project']) and schema_name:
            # check for a cached DataMatrix instance ...
            dm_oid = project.id + '-' + schema_name
            self.dm = orb.data.get(dm_oid)
        if not self.dm:
            # if no datamatrix found in the orb's cache, pass the args to
            # DataMatrix, which will check for a stored one or create a new
            # one based on the input:
            self.dm = DataMatrix(project=project, schema_name=schema_name,
                                 schema=schema)
        # TODO: create 'dedz' cache and look up col label/name there ...
        #       the MEL-specific stuff below is for prototyping ...
        # labels = [col['label'] or col['name'] for col in self.dm.schema]
        if config.get('deds') and config['deds'].get('mel_deds'):
            orb.log.debug('  - setting column labels from "mel_deds" ...')
            mel_deds = config['deds']['mel_deds']
            self.column_labels = [mel_deds[deid].get('label', deid)
                                  for deid in mel_deds]
        else:
            if self.dm.schema:
                orb.log.debug('  - setting column labels from schema ...')
            else:
                orb.log.debug('  - no schema; setting default label ...')
            self.column_labels = self.dm.schema or ['Data']
        self.root_item = GridTreeItem(self.column_labels)
        self.load_initial_dm_data()
        # TODO:  leaving setupModelData for now as it provides example code for
        # how to add rows and populate them ...
        # self.setupModelData(data.split("\n"), self.root_item)

        # TODO:  hook these up to the appropriate methods ...
        dispatcher.connect(self.on_local_new_items, 'dm new items')
        # dispatcher.connect(self.new_row, 'dm new row')
        # dispatcher.connect(self.on_remote_new_row,
                           # 'remote: data new row')
        # dispatcher.connect(self.on_remote_data_item_updated,
                           # 'remote: data item updated')

    def columnCount(self, parent=QModelIndex()):
        return self.root_item.columnCount()

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if role != Qt.DisplayRole and role != Qt.EditRole:
            return None
        item = self.getItem(index)
        # orb.log.debug('  - DMTreeModel.data({})'.format(index.column()))
        return item.data(index.column())

    def flags(self, index):
        if not index.isValid():
            return 0
        return Qt.ItemIsEditable | super().flags(index)

    def getItem(self, index):
        if index.isValid():
            item = index.internalPointer()
            if item:
                return item
        return self.root_item

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.root_item.data(section)
        return None

    def index(self, row, column, parent=QModelIndex()):
        # orb.log.debug('  - DMTreeModel.index({}, {})'.format(row, column))
        if parent.isValid() and parent.column() != 0:
            return QModelIndex()
        parent_item = self.getItem(parent)
        childItem = parent_item.child(row)
        if childItem:
            return self.createIndex(row, column, childItem)
        else:
            return QModelIndex()

    def insertColumns(self, position, columns, parent=QModelIndex()):
        orb.log.debug('  - DMTreeModel.insertColumns({}, {})'.format(
                                                position, str(columns)))
        self.beginInsertColumns(parent, position, position + columns - 1)
        success = self.root_item.insertColumns(position, columns)
        self.endInsertColumns()
        return success

    def insertRows(self, position, rows, parent=QModelIndex()):
        """
        Insert rows into the model.

        Args:
            position (int):  position at which to begin inserting
            rows (int):  number of rows to insert

        Keyword Args:
            parent (QModelIndex):  index of the parent item of which the new
                rows (items) will be children
        """
        orb.log.debug('  - DMTreeModel.insertRows({}, {})'.format(
                                                position, str(rows)))
        parent_item = self.getItem(parent)
        self.beginInsertRows(parent, position, position + rows - 1)
        # NOTE:  if 'from_dm' is False, insertChildren will dispatch 'local new
        # items' signal, which will create the corresponding new rows in
        # self.dm
        success = parent_item.insertChildren(position, rows,
                                             self.root_item.columnCount())
        self.endInsertRows()
        return success

    def on_local_new_items(self, items=None):
        """
        Handle "local new items" signal sent by an item's 'insertChildren()'
        method:  add corresponding rows to the DataMatrix when new items are
        added to the DMTreeModel.
        """
        orb.log.debug('  - DMTreeModel.on_local_new_items()')
        if not items:
            orb.log.debug('    + no items sent.')
            return
        orb.log.debug('    + item oids:'.format(
                                    str([i.oid for i in items])))
        for item in items:
            row_dict = {}
            if item.item_data:
                row_dict['oid'] = item.oid
                for i, name in enumerate(self.dm.schema):
                    row_dict[name] = item.item_data[i]
                self.dm[item.oid] = row_dict

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        childItem = self.getItem(index)
        parent_item = childItem.parent()
        if parent_item == self.root_item:
            return QModelIndex()
        return self.createIndex(parent_item.childNumber(), 0, parent_item)

    def removeColumns(self, position, columns, parent=QModelIndex()):
        orb.log.debug('  - DMTreeModel.removeColumns({}, {})'.format(
                                                position, str(columns)))
        self.beginRemoveColumns(parent, position, position + columns - 1)
        success = self.root_item.removeColumns(position, columns)
        self.endRemoveColumns()
        if self.root_item.columnCount() == 0:
            self.removeRows(0, self.rowCount())
        return success

    def removeRows(self, position, rows, parent=QModelIndex()):
        orb.log.debug('  - DMTreeModel.removeRows({}, {})'.format(
                                                position, str(rows)))
        parent_item = self.getItem(parent)
        self.beginRemoveRows(parent, position, position + rows - 1)
        success = parent_item.removeChildren(position, rows)
        self.endRemoveRows()
        return success

    def rowCount(self, parent=QModelIndex()):
        parent_item = self.getItem(parent)
        count = parent_item.childCount()
        # orb.log.debug('  - DMTreeModel.rowCount(): {}'.format(count))
        return count

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole:
            return False
        item = self.getItem(index)
        result = item.setData(index.column(), value)
        if result:
            orb.log.debug('  - DMTreeModel.setData({})'.format(value))
            orb.log.debug('    for item with oid: "{}"'.format(item.oid))
            orb.log.debug('    at row: {}, column: {}'.format(index.row(),
                                                              index.column()))
            self.dataChanged.emit(index, index)
        return result

    def setHeaderData(self, section, orientation, value, role=Qt.EditRole):
        if role != Qt.EditRole or orientation != Qt.Horizontal:
            return False
        result = self.root_item.setData(section, value)
        if result:
            orb.log.debug('  - DMTreeModel.setHeaderData({})'.format(section,
                                                                     value))
            self.headerDataChanged.emit(orientation, section, section)
        return result

    def load_initial_dm_data(self, parent=None):
        """
        Add initial DataMatrix data to the grid.
        """
        orb.log.debug('  - DMTreeModel.load_initial_dm_data()')
        if parent == None:
            parents = [self.root_item]
        else:
            parents = [parent]
        # TODO:  levels
        # levels = [0]
        # NOTE:  if a series of rows are on the same level, might call
        # 'insertRows()' with all of them (and their oids) ...
        row_dicts_in_order = [d for d in self.dm.values()]
        row_dicts_in_order.sort(key=lambda x: x.get('row', 0) or 0)
        for row_dict in row_dicts_in_order:
            row = int(row_dict.get('row', 0) or 0)
            orb.log.debug('  - row: {} ({})'.format(row, type(row)))
            self.insertRows(row, 1)
            self.dm[row_dict['oid']]['row'] = row
            idx = self.index(row, 0, parent=QModelIndex())
            item = self.getItem(idx)
            self.items_by_oid[row_dict['oid']] = item
            for i, de in enumerate(self.dm.schema):
                item.setData(i, row_dict.get(de))

    def setupModelData(self, lines, parent):
        """
        Add data to the grid.
        """
        parents = [parent]
        indentations = [0]
        number = 0
        while number < len(lines):
            position = 0
            while position < len(lines[number]):
                if lines[number][position] != " ":
                    break
                position += 1
            # lineData = lines[number][position:].trimmed()
            lineData = lines[number][position:].strip()
            if lineData:
                # Read the column data from the rest of the line.
                columnData = [s for s in lineData.split('\t') if s]
                if position > indentations[-1]:
                    # The last child of the current parent is now the new
                    # parent unless the current parent has no children.
                    if parents[-1].childCount() > 0:
                        parents.append(parents[-1].child(
                                            parents[-1].childCount() - 1))
                        indentations.append(position)
                else:
                    while position < indentations[-1] and len(parents) > 0:
                        parents.pop()
                        indentations.pop()
                # Append a new item to the current parent's list of children.
                parent = parents[-1]
                parent.insertChildren(parent.childCount(), 1,
                                      self.root_item.columnCount())
                for column in range(len(columnData)):
                    parent.child(parent.childCount() -1).setData(
                                                    column, columnData[column])
            number += 1


class GridTreeView(QTreeView):
    """
    A collaborative data table/tree view.
    """
    def __init__(self, parent=None):
        """
        Initialize.
        """
        orb.log.debug('* GridTreeView initializing ...')
        super().__init__(parent)
        self.setItemDelegate(DGDelegate(self))
        self.setSelectionBehavior(self.SelectRows)
        self.setSortingEnabled(False)
        header = self.header()
        header.setStyleSheet('QHeaderView { font-weight: bold; '
                             'font-size: 14px; border: 1px; } '
                             'QToolTip { font-weight: normal; '
                             'font-size: 12px; border: 2px solid; };')
        dispatcher.connect(self.new_row, 'dm new row')

    def drawRow(self, painter, option, index):
        # orb.log.debug('* GridTreeView.drawRow()')
        QTreeView.drawRow(self, painter, option, index)
        # painter.setPen(Qt.lightGray)
        painter.setPen(Qt.darkGray)
        y = option.rect.y()
        # saving is mandatory to keep alignment throughout the row painting
        painter.save()
        painter.translate(self.visualRect(
            self.model().index(0, 0)).x() - self.indentation() - .5, -.5)
        for sectionId in range(self.header().count() - 1):
            painter.translate(self.header().sectionSize(sectionId), 0)
            painter.drawLine(0, y, 0, y + option.rect.height())
        painter.restore()
        # don't draw the line before the root index
        if index == self.model().index(0, 0):
            return
        painter.drawLine(0, y, option.rect.width(), y)

    def new_row(self, row_oid=None, local=True):
        orb.log.debug('new_row()')
        # to avoid cycles ...
        if not local:
            if row_oid in self.model().dm:
                orb.log.debug("  - we already got one, it's verra nahss!")
                return
        # appends a new blank row, with oid
        row_nbr = len(self.model().dm)
        self.model().insertRow(row_nbr)
        row_oid = self.model().dm.row(row_nbr)
        orb.log.debug(' - self.dm is now {}'.format(str(self.model().dm)))
        proj_id = self.model().dm.project.id
        if local:
            dispatcher.send('dm new row added', proj_id=proj_id,
                            dm_oid=self.model().dm.oid, row_oid=row_oid)

    # NEEDS WORK, UNTESTED!
    # NOTE:  also, probably better to use DataGrid.insertRow ...
    # def add_row(self, row):
        # new_row = len(self.dm)
        # self.model().insertRow(new_row)
        # # if row doesn't have an oid, give it one
        # if not row.get('oid'):
            # row['oid'] = str(uuid4())
        # self.dm[row['oid']] = row
        # for elem_id, val in enumerate(row.items()):
            # if elem_id in self.dm.schema:
                # # TODO: put value into appropriate cell ...
                # pass

    def set_cell_value(self, row_oid, col_id, value):
        orb.log.debug('* GridTreeView.set_cell_value("{}", "{}")'.format(
                      row_oid, col_id))
        row_oids = list(self.dm.keys())
        if row_oid in row_oids:
            row_nbr = row_oids.index(row_oid)
            # FIXME:  what to use for parent index?
            item = self.model.getItem(self.model.index(row_nbr, 0,
                                                       QModelIndex()))
            if col_id in self.dm.schema:
                col_nbr = self.dm.schema.index(col_id)
                item.setData(col_nbr, value)

    def on_remote_new_row(self, dm_oid=None, row_oid=None):
        orb.log.debug('* GridTreeView.on_remote_new_row("{}", "{}")'.format(
                      dm_oid, row_oid))
        if self.dm.oid == dm_oid:
            self.new_row(row_oid=row_oid, local=False)

    def on_remote_data_item_updated(self, dm_oid=None, row_oid=None,
                                    col_id=None, value=None):
        arguments = 'dm_oid="{}", row_oid="{}", col_id="{}", value={}'.format(
                                               dm_oid, row_oid, col_id, value)
        orb.log.debug('* GridTreeView.on_remote_data_item_updated(')
        orb.log.debug('      {})'.format(arguments))
        if self.dm.oid == dm_oid:
            self.set_cell_value(row_oid, col_id, value)


class DGDelegate(QStyledItemDelegate):

    def __init__(self, parent=None):
        orb.log.debug('* DGDelegate initializing ...')
        super().__init__(parent)

    def createEditor(self, parent, style, index):
        # TODO: check for edit permission ...
        # TODO: detect column datatype ...
        # TODO: select specific editors:
        # - "float editor" for floats
        # - "integer editor" for ints
        # - "text editor" for strs
        # - "checkbox editor" for bools
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

    def setModelData(self, editor, model, index):
        orb.log.debug('* setModelData()')
        if isinstance(editor, QLineEdit):
            model.setData(index, editor.text())
            colnum = index.column()
            rownum = index.row()
            dm = model.dm
            col_id = dm.schema[colnum]
            row_oid = None
            try:
                row_oid = dm[list(dm.keys())[rownum - 1]]['oid']
            except:
                dm_rows = len(dm)
                orb.log.debug('* error: dm rows = {}; row # = {}'.format(
                              dm_rows, rownum))
                orb.log.debug('         dm keys (known row oids):')
                for k in dm.keys():
                    orb.log.debug('         {}'.format(k))
                orb.log.debug('  oopsie -- dm row not found, not updated.')
                return
            # TODO: cast editor.text() to column datatype ...
            dm[row_oid][col_id] = editor.text()
            # NOTE: should not need to save() every time! dm is cached in
            # memory in the orb.data dict and will be saved at exit.
            # dm.save()
            orb.log.debug(' - ({}, "{}"): {}'.format(
                                rownum, col_id, editor.text()))
            # orb.log.debug('datamatrix is now: {}'.format(str(dm)))
            proj_id = dm.project.id
            dispatcher.send('dm item updated', proj_id=proj_id, dm_oid=dm.oid,
                            row_oid=row_oid, col_id=col_id,
                            value=editor.text())


class DataGrid(QMainWindow):
    def __init__(self, project=None, schema_name=None, schema=None,
                 parent=None):
        orb.log.debug('* DataGrid(project="{}", schema_name="{}",'.format(
                                                        project, schema_name))
        orb.log.debug('           schema={}'.format(str(schema)))
        super().__init__(parent)
        self.setup_ui()
        self.font().setPointSize(14)
        # ---- stuff for informal testing ------------------------------------
        # headers = ("Title", "Description")
        # file = QFile(':/default.txt')
        # f.open(QIODevice.ReadOnly)
        # model = DMTreeModel(headers, f.readAll())
        # --------------------------------------------------------------------
        # re-implementation of 3 lines above to use standard Python operations
        # instead of Qt-specific "resource" stuff in editabletreemodel_rc,
        # which is a way of embedding file-based data/icons/etc. for easier
        # distribution ... but I don't like it!  :P
        # with open('./cattens/test/data/default.txt') as f:
            # model = DMTreeModel(headers, f.read())
            # f.close()
        model = DMTreeModel(project=project, schema_name=schema_name,
                            schema=schema)
        orb.log.debug('  - setModel(DMTreeModel) ...')
        self.view.setModel(model)
        row_count = self.view.model().rowCount()
        orb.log.debug('  - self.view.model().rowCount(): {}'.format(row_count))
        for column in range(model.columnCount()):
            self.view.resizeColumnToContents(column)
        self.exitAction.triggered.connect(QApplication.instance().quit)
        self.view.selectionModel().selectionChanged.connect(self.updateActions)
        self.actionsMenu.aboutToShow.connect(self.updateActions)
        self.insertRowAction.triggered.connect(self.insertRow)
        self.insertColumnAction.triggered.connect(self.insertColumn)
        self.removeRowAction.triggered.connect(self.removeRow)
        self.removeColumnAction.triggered.connect(self.removeColumn)
        self.insertChildAction.triggered.connect(self.insertChild)
        self.updateActions()

    def insertChild(self):
        orb.log.debug('  - DataGrid.insertChild()')
        index = self.view.selectionModel().currentIndex()
        model = self.view.model()
        item = model.getItem(index)
        # TODO:  revise GridTreeItem so it updates DataMatrix & vice-versa
        new_child_row = item.childCount()
        if model.columnCount(index) == 0:
            if not model.insertColumn(0, parent=index):
                return
        if not model.insertRow(new_child_row, parent=index):
            return
        row_dict = model.dm.append_new_row()
        for column in range(model.columnCount(index)):
            child_idx = model.index(new_child_row, column, index)
            # cell_to_index maps (oid, col_id) to the index of the cell
            model.cell_to_index[(row_dict['oid'],
                                 model.dm.schema[column])] = child_idx
            model.index_to_cell[child_idx] = (row_dict['oid'],
                                              model.dm.schema[column])
            model.setData(child_idx, "[No data]", Qt.EditRole)
            if model.headerData(column, Qt.Horizontal) is None:
                model.setHeaderData(column, Qt.Horizontal, "[No header]",
                        Qt.EditRole)
        self.view.selectionModel().setCurrentIndex(
                        model.index(new_child_row, 0, parent=index),
                        QItemSelectionModel.ClearAndSelect)
        self.updateActions()

    def insertColumn(self):
        orb.log.debug('* DataGrid.insertColumn()')
        model = self.view.model()
        column = self.view.selectionModel().currentIndex().column()
        changed = model.insertColumn(column + 1)
        if changed:
            model.setHeaderData(column + 1, Qt.Horizontal, "[No header]",
                    Qt.EditRole)
        self.updateActions()
        return changed

    def insertRow(self):
        orb.log.debug('* DataGrid.insertRow()')
        index = self.view.selectionModel().currentIndex()
        model = self.view.model()
        if not index:
            orb.log.debug('  - no current index; inserting row 0')
            model.insertRow(0, index.parent())
        elif not model.insertRow(index.row()+1, index.parent()):
            orb.log.debug('  - failed.')
            return
        self.updateActions()
        number_of_columns = model.columnCount(index.parent())
        orb.log.debug('  - calling setData() for {} columns ...'.format(
                                                        number_of_columns))
        for column in range(number_of_columns):
            child = model.index(index.row()+1, column, index.parent())
            model.setData(child, "[No data]", Qt.EditRole)

    def removeColumn(self):
        orb.log.debug('  - DataGrid.removeColumn()')
        model = self.view.model()
        column = self.view.selectionModel().currentIndex().column()
        changed = model.removeColumn(column)
        if changed:
            self.updateActions()
        return changed

    def removeRow(self):
        orb.log.debug('  - DataGrid.removeRow()')
        index = self.view.selectionModel().currentIndex()
        model = self.view.model()
        if (model.removeRow(index.row(), index.parent())):
            self.updateActions()

    def updateActions(self):
        orb.log.debug('  - DataGrid.updateActions()')
        hasSelection = not self.view.selectionModel().selection().isEmpty()
        self.removeRowAction.setEnabled(hasSelection)
        self.removeColumnAction.setEnabled(hasSelection)
        hasCurrent = self.view.selectionModel().currentIndex().isValid()
        self.insertRowAction.setEnabled(hasCurrent)
        self.insertColumnAction.setEnabled(hasCurrent)
        if hasCurrent:
            self.view.closePersistentEditor(
                                self.view.selectionModel().currentIndex())
            row = self.view.selectionModel().currentIndex().row()
            column = self.view.selectionModel().currentIndex().column()
            if self.view.selectionModel().currentIndex().parent().isValid():
                self.statusBar().showMessage(
                            "Position: (%d,%d)" % (row, column))
            else:
                self.statusBar().showMessage(
                            "Position: (%d,%d) in top level" % (row, column))

    def setup_ui(self):
        orb.log.debug('  - DataGrid.setup_ui()')
        # self.setObjectName("DataGrid")
        # self.resize(573, 468)
        self.centralwidget = QWidget(self)
        self.centralwidget.setObjectName("centralwidget")
        self.vboxlayout = QVBoxLayout(self.centralwidget)
        self.vboxlayout.setContentsMargins(0, 0, 0, 0)
        self.vboxlayout.setSpacing(0)
        self.vboxlayout.setObjectName("vboxlayout")
        self.view = GridTreeView(parent=self.centralwidget)
        self.view.setAlternatingRowColors(True)
        self.view.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.view.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.view.setAnimated(False)
        self.view.setAllColumnsShowFocus(True)
        self.view.setObjectName("view")
        self.vboxlayout.addWidget(self.view)
        self.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(self)
        self.menubar.setGeometry(QRect(0, 0, 573, 31))
        self.menubar.setObjectName("menubar")
        self.fileMenu = QMenu(self.menubar)
        self.fileMenu.setObjectName("fileMenu")
        self.actionsMenu = QMenu(self.menubar)
        self.actionsMenu.setObjectName("actionsMenu")
        self.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(self)
        self.statusbar.setObjectName("statusbar")
        self.setStatusBar(self.statusbar)
        self.exitAction = QAction(self)
        self.exitAction.setObjectName("exitAction")
        self.insertRowAction = QAction(self)
        self.insertRowAction.setObjectName("insertRowAction")
        self.removeRowAction = QAction(self)
        self.removeRowAction.setObjectName("removeRowAction")
        self.insertColumnAction = QAction(self)
        self.insertColumnAction.setObjectName("insertColumnAction")
        self.removeColumnAction = QAction(self)
        self.removeColumnAction.setObjectName("removeColumnAction")
        self.insertChildAction = QAction(self)
        self.insertChildAction.setObjectName("insertChildAction")
        self.fileMenu.addAction(self.exitAction)
        self.actionsMenu.addAction(self.insertRowAction)
        self.actionsMenu.addAction(self.insertColumnAction)
        self.actionsMenu.addSeparator()
        self.actionsMenu.addAction(self.removeRowAction)
        self.actionsMenu.addAction(self.removeColumnAction)
        self.actionsMenu.addSeparator()
        self.actionsMenu.addAction(self.insertChildAction)
        self.menubar.addAction(self.fileMenu.menuAction())
        self.menubar.addAction(self.actionsMenu.menuAction())

        self.retranslate_ui(self)
        QMetaObject.connectSlotsByName(self)

    def retranslate_ui(self, DataGrid):
        orb.log.debug('  - DataGrid.retranslate_ui()')
        _translate = QCoreApplication.translate
        self.setWindowTitle(_translate("DataGrid",
                                       "Editable Tree Model"))
        self.fileMenu.setTitle(_translate("DataGrid", "&File"))
        self.actionsMenu.setTitle(_translate("DataGrid", "&Actions"))
        self.exitAction.setText(_translate("DataGrid", "E&xit"))
        self.exitAction.setShortcut(_translate("DataGrid", "Ctrl+Q"))
        self.insertRowAction.setText(_translate("DataGrid", "Insert Row"))
        self.insertRowAction.setShortcut(_translate("DataGrid", "Ctrl+I, R"))
        self.removeRowAction.setText(_translate("DataGrid", "Remove Row"))
        self.removeRowAction.setShortcut(_translate("DataGrid", "Ctrl+R, R"))
        self.insertColumnAction.setText(_translate("DataGrid",
                                                   "Insert Column"))
        self.insertColumnAction.setShortcut(_translate("DataGrid",
                                                       "Ctrl+I, C"))
        self.removeColumnAction.setText(_translate("DataGrid",
                                                   "Remove Column"))
        self.removeColumnAction.setShortcut(_translate("DataGrid",
                                                       "Ctrl+R, C"))
        self.insertChildAction.setText(_translate("DataGrid",
                                                  "Insert Child"))
        self.insertChildAction.setShortcut(_translate("DataGrid", "Ctrl+N"))


if __name__ == '__main__':

    import sys

    app = QApplication(sys.argv)
    window = DataGrid()
    window.show()
    sys.exit(app.exec_())

