# -*- coding: utf-8 -*-
"""
A DataMatrix-based collaborative data table/tree widget.
"""
# python std lib
import os

# PyQt
from PyQt5.QtCore import (Qt, QAbstractItemModel, QItemSelectionModel,
                          QMetaObject, QModelIndex)
from PyQt5.QtWidgets import (QAbstractItemView, QAction, QApplication,
                             QDialog, QFileDialog, QLineEdit, QMainWindow,
                             QStatusBar, QStyledItemDelegate, QTreeView,
                             QVBoxLayout, QWidget)

# pangalactic
# from pangalactic.core             import prefs
from pangalactic.core             import config, state
from pangalactic.core.utils.datetimes import dtstamp, date2str
from pangalactic.core.entity      import DataMatrix, Entity, dmz
from pangalactic.core.parametrics import de_defz, parm_defz
from pangalactic.core.uberorb     import orb
from pangalactic.node.dialogs     import CustomizeColsDialog

# Louie
from louie import dispatcher


class GridTreeItem:
    """
    A node in a DMTreeModel, roughly equivalent to a row in a table.  A
    GridTreeItem can be associated with an occurrance or a collection of
    occurrances of an entity, product, subsystem, or model in an assembled or
    integrated system.

    Attributes:
        oid (str):  unique identifier of the underlying Entity
        dm (DataMatrix):  the DataMatrix of the DMTreeModel that has this item

    Keyword Args:
        parent (GridTreeItem):  parent item of this item
    """
    def __init__(self, oid=None, dm=None, root=False, parent=None):
        """
        Initialize a GridTreeItem, which corresponds to a row in the DataMatrix
        of a DMTreeModel.

        Keyword Args:
            oid (str):  unique identifier of the underlying Entity
            dm (DataMatrix):  the DataMatrix instance of the DMTreeModel that
                has this item
            root (bool):  if True, we are the root item (i.e. header row)
            parent (GridTreeItem):  parent item of this item
        """
        argstr = f'oid={oid}'
        orb.log.debug('* GridTreeItem({}) initializing ...'.format(argstr))
        self.root = root
        self.dm = dm
        if self.root:
            # the root item will not have an entity but will have the schema
            self.entity = None
        else:
            self.entity = Entity(oid=oid)
        self.parent_item = parent
        # "children" entities in the DataMatrix in which the entity is embedded
        # are determined by how many entities that immediately follow this one
        # have a 'level' value that is exactly one higher ... but the
        # "children" attribute of GridTreeItem is determined by how many child
        # nodes have been added to the DMTreeModel.
        self.children = []

    @property
    def oid(self):
        return self.entity.oid

    @property
    def schema(self):
        return getattr(self.dm, 'schema', [])

    @property
    def name(self):
        return getattr(self.dm, 'name', '')

    @property
    def column_labels(self):
        return getattr(self.dm, 'column_labels', [])

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
        return len(self.schema)

    def data(self, column):
        if column < 0 or column >= len(self.schema):
            return None
        if self.root:
            try:
                return self.column_labels[column]
            except:
                try:
                    return self.schema[column]
                except:
                    return 'Unknown'
        col_id = self.schema[column]
        return self.entity.get(col_id, '')

    def insertChildren(self, position, count):
        """
        Insert child items (with new entities) under current item.

        Args:
            position (int):  position at which to begin inserting
            count (int):  number of children to insert
        """
        orb.log.debug('  - GridTreeItem.insertChildren({}, {})'.format(
                                                      position, count))
        if position < 0 or position > len(self.children):
            return False
        for i in range(count):
            entity = self.dm[position + i]
            item = GridTreeItem(oid=entity.oid, dm=self.dm, parent=self)
            self.children.insert(position + i, item)
        return True

    def insertPeers(self, position, count):
        """
        Insert peer items (with new entities) under current item.

        Args:
            position (int):  position at which to begin inserting
            count (int):  number of children to insert
        """
        orb.log.debug('  - GridTreeItem.insertPeer({}, {})'.format(
                                                      position, count))
        if position < 0 or position > len(self.children):
            return False
        # if self.childCount():
            # position += self.childCount()
        for i in range(count):
            entity = self.dm[position + i]
            item = GridTreeItem(oid=entity.oid, dm=self.dm, parent=self)
            self.children.insert(position + i, item)
        return True

    # FIXME:  this is OLD -- needs to be adapted to the Entity paradigm ...
    # What should this do?  Insert a data element or parameter into schema?
    # Or use it as a "show column(s)" type of function?
    def insertColumns(self, position, columns):
        orb.log.debug('  - GridTreeItem.insertColumns({}, {})'.format(
                                                    position, str(columns)))
        if position < 0 or position > len(self.schema):
            return False
        for column in range(columns):
            self.schema.insert(position, '')
        for child in self.children:
            child.insertColumns(position, columns)
        return True

    def parent(self):
        return self.parent_item

    # FIXME:  this is OLD -- needs to be adapted to the Entity paradigm ...
    def removeChildren(self, position, count):
        orb.log.debug('  - GridTreeItem.removeChildren({}, {})'.format(
                                                      position, count))
        if position < 0 or position + count > len(self.children):
            return False
        for row in range(count):
            self.children.pop(position)
        return True

    # FIXME:  this is OLD -- needs to be adapted to the Entity paradigm ...
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
        if column < 0 or column >= len(self.schema):
            return False
        col_id = self.schema[column]
        self.entity[col_id] = value
        return True


class DMTreeModel(QAbstractItemModel):
    """
    A DataMatrix-based tree model.  Arguments for 'project' and 'name'
    are used to intialize the underlying DataMatrix object.

    Attributes:
        oid_to_index (dict): maps an entity oid to the model index of an item
        index_to_oid (dict): maps the index of an item to an entity oid
    """
    def __init__(self, project=None, name=None, parent=None):
        """
        Initialize.

        Keyword Args:
            project (Project): associated project (effective owner of the
                DataMatrix underlying the model)
            name (str): name of an initial schema (in 'schemaz' cache)
                to be passed to the DataMatrix
            parent (QWidget):  parent widget
        """
        arguments = 'project={}, name="{}"'
        orb.log.debug('* DMTreeModel({}) initializing ...'.format(
                      arguments.format(getattr(project, 'id', 'None'),
                                       name)))
        super().__init__(parent)
        self.oid_to_index = {}
        self.index_to_oid = {}
        self.dm = None
        self.project = project
        name = name or config.get('default_schema_name')
        if isinstance(project, orb.classes['Project']) and name:
            # check for a cached DataMatrix instance ...
            dm_oid = project.id + '-' + name
            orb.log.debug(f'  looking for DataMatrix "{dm_oid}" ...')
            orb.log.debug('  dmz cache is: {}'.format(str(dmz)))
            self.dm = dmz.get(dm_oid)
        if self.dm:
            orb.log.debug('  DataMatrix found: "{}"'.format(self.dm.oid))
            orb.log.debug('  {}'.format(str(self.dm)))
        else:
            orb.log.debug('  DataMatrix not found in cache.')
            # if no parts list found in the orb's cache, pass the args to
            # DataMatrix, which will check for a stored one or create a new
            # one based on the input:
            self.project = project or orb.get('pgefobjects:SANDBOX')
            self.dm = DataMatrix(project_id=project.id, name=name)
        # self.dm.clear()
        self.dm.recompute_mel(project)
        # --------------------------------------------------------------------
        # NOTE:  'root_item' is the header row ... and this is the ONLY place
        # where the Model explicitly calls GridTreeItem() -- in all other
        # cases, new instances of GridTreeItem are created by calling methods
        # on instances of GridTreeItem, such as insertChildren() ... so for our
        # entity-based paradigm a 'dm' (DataMatrix instance) needs to be passed
        # to the GridTreeItem.  In the example code,
        # self.rootItem.columnCount() is passed in since it is just creating
        # blank cells.
        # --------------------------------------------------------------------
        self.root_item = GridTreeItem(dm=self.dm, root=True)
        self.load_dm_data()
        # TODO:  figure out if we need these ...
        # dispatcher.connect(self.new_row, 'dm new row')
        # dispatcher.connect(self.on_remote_new_row,
                           # 'remote: data new row')
        # dispatcher.connect(self.on_remote_data_item_updated,
                           # 'remote: data item updated')
        dispatcher.connect(self.on_pval_set, 'pval set')

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
        if role == Qt.ToolTipRole:
            pid = self.dm.schema[section]
            txt = de_defz.get(pid, {}).get('description')
            txt = txt or parm_defz.get(pid, {}).get('description')
            return txt or pid
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
            position (int):  position relative to parent at which to begin
                inserting
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
        if parent.isValid():
            success = parent_item.insertChildren(position, rows)
        else:
            success = parent_item.insertPeers(position, rows)
        self.endInsertRows()
        return success

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        childItem = self.getItem(index)
        parent_item = childItem.parent()
        if parent_item == self.root_item or parent_item == None:
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
        """
        Set model data on a cell.  Note:  the item's setData will update the
        Entity / DataMatrix.
        """
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

    def load_dm_data(self, parent=None):
        """
        Load DataMatrix data into the grid.
        """
        orb.log.debug('* DMTreeModel.load_dm_data()')
        # if parent == None:
            # parents = [self.root_item]
        # else:
            # parents = [parent]
        # TODO:  levels
        # levels = [0]
        # NOTE:  if a series of rows are on the same level, might call
        # 'insertRows()' with all of them (and their oids) ... self.insertRow
        # actually calls insertRows() anyway.
        n = len(self.dm)
        if n == 1:
            orb.log.debug('  - loading 1 entity ...')
        else:
            orb.log.debug('  - loading {} entities ...'.format(n))
        for row in range(n):
            entity = self.dm[row]
            orb.log.debug('    row {} (oid "{}")'.format(row, entity.oid))
            self.insertRow(row, parent=QModelIndex())
            # TESTING:
            # self.root_item.insertChildren(self.root_item.childCount(), 0,
                                          # self.root_item.columnCount())
            idx = self.index(row, 0, parent=QModelIndex())
            item = self.getItem(idx)
            self.oid_to_index[item.oid] = idx
            for j, col_id in enumerate(self.dm.schema):
                item.setData(j, entity.get(col_id, ''))

    def on_pval_set(self, oid=None, pid=None, value=None, units=None,
                    mod_datetime=None, local=True):
        orb.log.debug('DMTreeModel.on_pval_set()')
        idx = self.oid_to_index.get(oid)
        if idx:
            self.dataChanged(idx, idx)


class GridTreeView(QTreeView):
    """
    A collaborative data table/tree view.
    """
    def __init__(self, project=None, name=None, parent=None):
        """
        Initialize.

        Keyword Args:
            project (Project): associated project (effective owner of the
                DataMatrix underlying the model)
            name (str): name of an initial schema (in 'schemaz' cache)
                to be passed to the DataMatrix
        """
        orb.log.debug('* GridTreeView initializing ...')
        super().__init__(parent)
        model = DMTreeModel(project=project, name=name)
        self.setModel(model)
        self.selectionModel().selectionChanged.connect(self.update_actions)
        self.setItemDelegate(DGDelegate(self))
        # select cells (vs. rows or columns)
        self.setSelectionBehavior(self.SelectItems)
        self.setTabKeyNavigation(True)
        self.setSortingEnabled(False)
        self.setup_table()

    def setup_table(self):
        # TODO:  setup_table will need to rebuild the model using a new
        # custom schema if one is set by select_columns()
        header = self.header()
        header.setStyleSheet('QHeaderView { font-weight: bold; '
                             'font-size: 14px; border: 1px; } '
                             'QToolTip { font-weight: normal; '
                             'font-size: 12px; border: 2px solid; };')
        header.setDefaultAlignment(Qt.AlignHCenter)
        # add context menu actions
        self.insert_row_action = QAction('Insert Row (same level)', self)
        self.insert_row_action.triggered.connect(self.insert_row)
        header.addAction(self.insert_row_action)
        self.add_child_action = QAction('Add Child Row (level down)', self)
        self.add_child_action.triggered.connect(self.add_child)
        header.addAction(self.add_child_action)
        self.delete_row_action = QAction('Delete Row', self)
        self.delete_row_action.triggered.connect(self.delete_row)
        header.addAction(self.delete_row_action)
        self.select_columns_action = QAction('Select Columns', self)
        self.select_columns_action.triggered.connect(self.select_columns)
        header.addAction(self.select_columns_action)
        self.export_tsv_action = QAction('Export Table to .tsv File', self)
        self.export_tsv_action.triggered.connect(self.export_tsv)
        header.addAction(self.export_tsv_action)
        header.setContextMenuPolicy(Qt.ActionsContextMenu)

    def append_column(self, name="[No header]"):
        orb.log.debug('* GridTreeView.append_column()')
        model = self.model()
        column = model.columnCount()
        changed = model.insertColumn(column)
        if changed:
            model.setHeaderData(column + 1, Qt.Horizontal, name, Qt.EditRole)
        return changed

    def select_columns(self):
        """
        Display a dialog in response to 'select columns' context menu item.
        """
        orb.log.debug('* GridTreeView.select_columns() ...')
        schema = self.model().dm.schema
        # NOTE: current_view is a *copy* from the schema -- DO NOT modify the
        # original schema!!!
        current_schema = schema[:]
        current_schema_name = self.model().dm.name
        dlg = CustomizeColsDialog(self.model().dm.schema, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            all_cols = list(de_defz) + list(parm_defz)
            all_cols.sort()
            # rebuild schema from the selected columns
            schema.clear()
            # add any columns from current_schema first
            for col in current_schema:
                if col in dlg.checkboxes and dlg.checkboxes[col].isChecked():
                    schema.append(col)
                    all_cols.remove(col)
            # then append any newly selected columns
            for col in all_cols:
                if dlg.checkboxes[col].isChecked():
                    schema.append(col)
                    # TODO: hmmm ... does this work?
                    # self.insert_column(col)
            orb.log.debug('  new schema: {}'.format(schema))

    def drawRow(self, painter, option, index):
        # orb.log.debug('* GridTreeView.drawRow()')
        QTreeView.drawRow(self, painter, option, index)
        # painter.setPen(Qt.lightGray)
        painter.setPen(Qt.darkGray)
        y = option.rect.y()
        # saving is mandatory to keep alignment throughout the row painting
        painter.save()
        model = self.model()
        painter.translate(self.visualRect(
            model.index(0, 0)).x() - self.indentation() - .5, -.5)
        for sectionId in range(self.header().count() - 1):
            painter.translate(self.header().sectionSize(sectionId), 0)
            # draw a vertical line to separate cells
            painter.drawLine(0, y, 0, y + option.rect.height())
        painter.restore()
        # don't draw the line before the root index
        if index == model.index(0, 0):
            return
        painter.drawLine(0, y, option.rect.width(), y)

    # FIXME:  NOT IN USE -- is it even remotely correct??
    # def set_cell_value(self, row_oid, col_id, value):
        # orb.log.debug('* GridTreeView.set_cell_value("{}", "{}")'.format(
                      # row_oid, col_id))
        # model = self.model()
        # if entity:
            # # FIXME:  what to use for parent index?
            # item = model.getItem(model.index(row_nbr, 0, QModelIndex()))
            # if col_id in self.model().dm.schema:
                # col_nbr = self.model().dm.schema.index(col_id)
                # item.setData(col_nbr, value)
        # for column in range(model.columnCount()):
            # self.resizeColumnToContents(column)

    # was originally DataGrid.updateActions()
    def update_actions(self):
        orb.log.debug('* GridTreeView.update_actions()')
        # has_selection = not self.selectionModel().selection().isEmpty()
        # self.removeRowAction.setEnabled(has_selection)
        # self.removeColumnAction.setEnabled(has_selection)
        has_current = self.selectionModel().currentIndex().isValid()
        self.delete_row_action.setEnabled(has_current)
        self.add_child_action.setEnabled(has_current)
        # self.insertColumnAction.setEnabled(has_current)
        if has_current:
            self.closePersistentEditor(
                                self.selectionModel().currentIndex())
            row = self.selectionModel().currentIndex().row()
            column = self.selectionModel().currentIndex().column()
            msg = ''
            if self.selectionModel().currentIndex().parent().isValid():
                msg = "cell: ({},{})".format(row, column)
            else:
                msg = "cell: ({},{}) in top level".format(row, column)
            dispatcher.send("datagrid show msg", msg=msg)

    def insert_row(self):
        orb.log.debug('* GridTreeView.insert_row()')
        index = self.selectionModel().currentIndex()
        model = self.model()
        if index:
            model.dm.insert_new_row(index.row()+1)
            success = model.insertRow(index.row()+1, index.parent())
            if not success:
                orb.log.debug('  - failed.')
                return
        else:
            orb.log.debug('  - no current index; inserting row 0')
            model.dm.insert_new_row(0)
            model.insertRow(0, parent=QModelIndex())
        number_of_columns = model.columnCount(index.parent())
        orb.log.debug('  - calling setData() for {} columns ...'.format(
                                                        number_of_columns))
        for column in range(number_of_columns):
            child = model.index(index.row()+1, column, index.parent())
            model.setData(child, "", Qt.EditRole)
            self.resizeColumnToContents(column)
        self.update_actions()

    ### NOTE: currently, this is getting the wrong entity oid -- for it to work
    ### properly, the model.insertRows must be modified to find the correct
    ### entity ("child" of this entity, i.e. 1 level down) in the dm
    def add_child(self):
        orb.log.debug('* GridTreeView.add_child()')
        index = self.selectionModel().currentIndex()
        model = self.model()
        item = model.getItem(index)
        if not item or not item.entity:
            orb.log.debug('  - no selected item or entity, cannot add child.')
            return
        dm_oids = [e.oid for e in model.dm]
        item_dm_position = dm_oids.index(item.entity.oid)
        # NOTE:  dm.insert_new_row returns the new entity, if needed ...
        #        ... do we need it??
        entity = model.dm.insert_new_row(item_dm_position + 1,
                                         child_of=item.entity)
        # NOTE: is this needed???
        # if model.columnCount(index) == 0:
            # if not model.insertColumn(0, parent=index):
                # return
        new_child_row = item.childCount()
        # if not model.insertRow(index.row()+1, parent=index):
        if not model.insertRow(new_child_row, parent=index):
            orb.log.debug('  - model.insertRow() failed, cannot add child.')
            return
        ### NOTE: this setting blank data does not work ... and not needed???
        # set blank data for columns of new item
        # for column in range(model.columnCount(index)):
            # child_idx = model.index(new_child_row, column, index)
            ## NOTE: not clear that these are needed either ...???
            ## oid_to_index maps oid to the index of an item (row)
            # model.oid_to_index[new_entity.oid] = child_idx
            # model.index_to_oid[child_idx] = row_dict['oid']
            # model.setData(child_idx, "", Qt.EditRole)
            ## NOTE:  this probably doesn't make sense now ...???
            # if model.headerData(column, Qt.Horizontal) is None:
                # model.setHeaderData(column, Qt.Horizontal, "[No header]",
                        # Qt.EditRole)
        ## NOTE: preferable to leave selection where it is??
        self.selectionModel().setCurrentIndex(
                        model.index(new_child_row, 0, parent=index),
                        QItemSelectionModel.ClearAndSelect)
        for column in range(model.columnCount()):
            self.resizeColumnToContents(column)
        self.update_actions()

    def delete_row(self):
        orb.log.debug('* DataGrid.delete_row()')
        index = self.selectionModel().currentIndex()
        model = self.model()
        item = model.getItem(index)
        orb.log.debug('  - oid of row being deleted: "{}"'.format(item.oid))
        success = model.dm.remove_row_by_oid(item.oid)
        if success:
            if (model.removeRow(index.row(), index.parent())):
                self.update_actions()
        else:
            orb.log.debug('    unable to delete.')

    # EXPERIMENTAL!
    def on_remote_new_row(self, dm_oid=None, row_oid=None):
        orb.log.debug('* GridTreeView.on_remote_new_row("{}", "{}")'.format(
                      dm_oid, row_oid))
        if self.dm.oid == dm_oid:
            self.new_row(row_oid=row_oid, local=False)

    # EXPERIMENTAL!
    def on_remote_data_item_updated(self, dm_oid=None, row_oid=None,
                                    col_id=None, value=None):
        arguments = 'dm_oid="{}", row_oid="{}", col_id="{}", value={}'.format(
                                               dm_oid, row_oid, col_id, value)
        orb.log.debug('* GridTreeView.on_remote_data_item_updated(')
        orb.log.debug('      {})'.format(arguments))
        if self.dm.oid == dm_oid:
            self.set_cell_value(row_oid, col_id, value)

    def export_tsv(self):
        """
        Write the table content to a tsv (tab-separated-values) file.
        """
        orb.log.debug('* export_tsv()')
        dtstr = date2str(dtstamp())
        dm = self.model().dm
        fpath, filters = QFileDialog.getSaveFileName(
                                    self, 'Write to tsv File',
                                    dm.oid + '-' + dtstr + '.tsv')
        if fpath:
            orb.log.debug('  - file selected: "%s"' % fpath)
            fpath = str(fpath)    # QFileDialog fpath is unicode; UTF-8 (?)
            state['last_path'] = os.path.dirname(fpath)
            f = open(fpath, 'w')
            header = '\t'.join(dm.schema)
            rows = [header]
            orb.log.debug('  - rows to be written:')
            for entity in dm:
                row = '\t'.join([str(entity.get(col, ''))
                                 for col in dm.schema])
                orb.log.debug(f'    {row}')
                rows.append(row)
            content = '\n'.join(rows)
            f.write(content)
            f.close()
            # TODO:  add a "success" notification
            # txt = '... table exported to file: {}'.format(fpath)
        else:
            orb.log.debug('  ... export to tsv cancelled.')
            return


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
            txt = str(index.model().data(index, Qt.EditRole))
            editor.setText(txt)

    def setModelData(self, editor, model, index):
        """
        Set the model data at the specified index to the edited value, and
        update the model's associated DataMatrix.
        """
        orb.log.debug('* setModelData()')
        if isinstance(editor, QLineEdit):
            model.setData(index, editor.text())
            colnum = index.column()
            rownum = index.row()
            dm = model.dm
            col_id = dm.schema[colnum]
            # TODO: cast editor.text() to column datatype ...
            # item = model.getItem(index)
            dm[rownum][col_id] = editor.text()
            orb.log.debug(' - ({}, "{}"): {}'.format(
                                rownum, col_id, editor.text()))
            orb.log.debug('   dm row is now: {}'.format(str(dm[rownum])))


class DataGrid(QMainWindow):
    def __init__(self, project=None, name=None, parent=None):
        """
        Initialize.

        Keyword Args:
            project (Project): associated project (effective owner of the
                underlying DataMatrix)
            name (str): name of an initial schema (in 'schemaz' cache)
                to be passed to the internal DataMatrix
        """
        orb.log.debug('* DataGrid(project="{}", name="{}",'.format(
                             getattr(project, 'id', '[None]'), name))
        super().__init__(parent)
        self.centralwidget = QWidget(self)
        self.vboxlayout = QVBoxLayout(self.centralwidget)
        self.vboxlayout.setContentsMargins(0, 0, 0, 0)
        self.vboxlayout.setSpacing(0)
        self.view = GridTreeView(project=project, name=name,
                                 parent=self.centralwidget)
        self.view.setAlternatingRowColors(True)
        self.view.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.view.setAnimated(False)
        self.view.setAllColumnsShowFocus(True)
        self.view.setObjectName("view")
        self.vboxlayout.addWidget(self.view)
        self.setCentralWidget(self.centralwidget)
        self.statusbar = QStatusBar(self)
        self.setStatusBar(self.statusbar)
        QMetaObject.connectSlotsByName(self)
        self.font().setPointSize(14)
        for column in range(self.view.model().columnCount()):
            self.view.resizeColumnToContents(column)
        # self.exitAction.triggered.connect(QApplication.instance().quit)
        # self.view.selectionModel().selectionChanged.connect(self.updateActions)
        self.update()
        dispatcher.connect(self.display_status_msg, 'datagrid show msg')
        # self.updateActions()

    @property
    def row_count(self):
        return self.view.model().rowCount()

    def display_status_msg(self, msg=''):
        self.statusBar().showMessage(msg)

    # This works fine.  Triggered by the "Insert Row" action.
    # *** moved to model as "add_row"
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
        # self.updateActions()
        number_of_columns = model.columnCount(index.parent())
        orb.log.debug('  - calling setData() for {} columns ...'.format(
                                                        number_of_columns))
        for column in range(number_of_columns):
            child = model.index(index.row()+1, column, index.parent())
            model.setData(child, "[No data]", Qt.EditRole)

    def removeColumn(self):
        orb.log.debug('* DataGrid.removeColumn()')
        model = self.view.model()
        column = self.view.selectionModel().currentIndex().column()
        changed = model.removeColumn(column)
        # if changed:
            # self.updateActions()
        return changed

    # This worked fine ... was triggered by the "Remove Row" action.
    # def removeRow(self):
        # orb.log.debug('* DataGrid.removeRow()')
        # index = self.view.selectionModel().currentIndex()
        # model = self.view.model()
        # item = model.getItem(index)
        # orb.log.debug('  - oid of row item: "{}"'.format(item.oid))
        # if item.oid in model.dm:
            # model.dm.remove_oid(item.oid)
        # # if (model.removeRow(index.row(), index.parent())):
            # # self.updateActions()

    # def updateActions(self):
        # orb.log.debug('  - DataGrid.updateActions()')
        # hasSelection = not self.view.selectionModel().selection().isEmpty()
        # self.removeRowAction.setEnabled(hasSelection)
        # self.removeColumnAction.setEnabled(hasSelection)
        # hasCurrent = self.view.selectionModel().currentIndex().isValid()
        # self.insertRowAction.setEnabled(hasCurrent)
        # self.insertColumnAction.setEnabled(hasCurrent)
        # if hasCurrent:
            # self.view.closePersistentEditor(
                                # self.view.selectionModel().currentIndex())
            # row = self.view.selectionModel().currentIndex().row()
            # column = self.view.selectionModel().currentIndex().column()
            # if self.view.selectionModel().currentIndex().parent().isValid():
                # self.statusBar().showMessage(
                            # "Position: (%d,%d)" % (row, column))
            # else:
                # self.statusBar().showMessage(
                            # "Position: (%d,%d) in top level" % (row, column))


if __name__ == '__main__':

    import sys

    app = QApplication(sys.argv)
    window = DataGrid()
    window.show()
    sys.exit(app.exec_())

