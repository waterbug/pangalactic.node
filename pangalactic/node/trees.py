# -*- coding: utf-8 -*-
"""
Tree models
"""
import os
from textwrap import wrap

from PyQt5.QtCore import QAbstractItemModel, QModelIndex, QPoint, QSize, Qt
from PyQt5.QtGui import QDrag, QIcon, QPixmap
from PyQt5.QtWidgets import QAbstractItemView, QApplication, QTreeView

from pangalactic.core             import orb
from pangalactic.core             import state
from pangalactic.core.parametrics import parm_defz
from pangalactic.node.utils       import create_mime_data


class ParmDefItem:
    """
    A ParameterDefinition node in a ParmDefTreeModel.

    Attributes:
        pid (str):  unique identifier of the Parameter

    Keyword Args:
        parent (ParmDefItem):  parent item of this item
    """
    def __init__(self, pid=None, view=None, root=False, parent=None):
        """
        Initialize a ParmDefItem.

        Keyword Args:
            pid (str):  unique identifier of the Parameter
            root (bool):  if True, we are the root item (i.e. header row)
            parent (ParmDefItem):  parent item of this item
        """
        self.root = root
        if root:
            self.parent_item = None
            self.pid = None
        else:
            self.parent_item = parent
            self.pid = pid
        self.children = []
        self.view = view or ['id', 'name', 'dimensions', 'computed']

    @property
    def cell_data(self):
        return [self.pid] + [parm_defz[self.pid][col] for col in self.view[1:]]

    @property
    def tooltip(self):
        desc = parm_defz[self.pid]['description']
        return '\n'.join(wrap(desc, width=30, break_long_words=False))

    @property
    def icon(self):
        # hmmm ... need a better icon for parameters!  the "parameter" icon
        # (xy) doesn't really work for this, and the "box" is too generic
        return QIcon(QPixmap(os.path.join(
                       orb.home, 'icons', 'box' + state['icon_type'])))

    def appendChild(self, item):
        self.children.append(item)

    def child(self, row):
        return self.children[row]

    def childCount(self):
        return len(self.children)

    def columnCount(self):
        return len(self.view)

    def data(self, column):
        if self.root:
            if column < len(self.view):
                return self.view[column]
            else:
                return None
        else:
            try:
                return self.cell_data[column]
            except IndexError:
                return None

    def parent(self):
        return self.parent_item

    def row(self):
        if self.parent_item:
            return self.parent_item.children.index(self)
        return 0


class ParmDefTreeModel(QAbstractItemModel):
    def __init__(self, view=None, parent=None):
        super(ParmDefTreeModel, self).__init__(parent)
        self.view = view or ['id', 'name', 'dimensions', 'computed']
        self.root_item = ParmDefItem(root=True, view=self.view)
        self.refresh_data()

    def columnCount(self, parent):
        if parent.isValid():
            return parent.internalPointer().columnCount()
        else:
            return self.root_item.columnCount()

    def data(self, index, role):
        if not index.isValid():
            return None
        item = index.internalPointer()
        if role == Qt.DecorationRole and index.column() == 0:
            return item.icon
        if role == Qt.ToolTipRole:
            return item.tooltip
        if role == Qt.DisplayRole:
            return item.data(index.column())
        if role == Qt.UserRole:
            # return the pid and icon for that item
            return item.pid, item.icon
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def headerData(self, section, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.root_item.data(section)
        return None

    def index(self, row, column, parent):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        if not parent.isValid():
            parent_item = self.root_item
        else:
            parent_item = parent.internalPointer()
        child_item = parent_item.child(row)
        if child_item:
            return self.createIndex(row, column, child_item)
        else:
            return QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        child_item = index.internalPointer()
        parent_item = child_item.parent()
        if parent_item == self.root_item:
            return QModelIndex()

        return self.createIndex(parent_item.row(), 0, parent_item)

    def rowCount(self, parent):
        if parent.column() > 0:
            return 0
        if not parent.isValid():
            parent_item = self.root_item
        else:
            parent_item = parent.internalPointer()
        return parent_item.childCount()

    def refresh_data(self):
        current_parent = self.root_item
        # must use the case-dependent sort (which is the default sort) so that
        # (for example) "V" (voltage) and "v" (velocity) parameters are grouped
        # separately
        # NOTE:  parameters in "prescriptive" contexts are excluded, since it
        # is not appropriate to assign them to products, only to usages --
        # prescriptive parameters are used solely in defining constraints for
        # use in performance requirements.  They can be added as columns in
        # dashboards but it is not meaningful to assign them to products.
        parm_contexts = orb.search_exact(cname='ParameterContext',
                                         context_type='prescriptive')
        prescriptive_contexts = [obj.id for obj in parm_contexts]
        pids = sorted(list(parm_defz), key=lambda x: (x.split('[')[0].lower(), x))
        selectable_pids = [pid for pid in pids
                           # if not (pid.endswith('[Ctgcy]') or
                           if parm_defz[pid]['context']
                           not in prescriptive_contexts]
        for pid in selectable_pids:
            if pid == parm_defz[pid]['variable']:
                # child of the root_item and becomes the current parent
                current_parent = ParmDefItem(pid=pid, parent=self.root_item)
                self.root_item.appendChild(current_parent)
            else:
                # append new item to the current parent's list of children
                current_parent.appendChild(ParmDefItem(pid=pid,
                                                       parent=current_parent))


class ParmDefTreeView(QTreeView):
    """
    Tree view for ParameterDefinitions.
    """
    def __init__(self, view=None, parent=None):
        super(ParmDefTreeView, self).__init__(parent)
        self.view = view or ['id', 'name', 'dimensions', 'computed']
        model = ParmDefTreeModel(view=self.view)
        self.setModel(model)
        self.setUniformRowHeights(True)
        self.resize_columns()
        self.expanded.connect(self.node_expanded)
        self.setAlternatingRowColors(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)

    def node_expanded(self, index):
        self.resize_columns()

    def resize_columns(self):
        for col in self.view:
            self.resizeColumnToContents(self.view.index(col))

    def startDrag(self, event):
        try:
            index = self.indexAt(event.pos())
            if not index.isValid:
                return
            pid, icon = self.model().data(index, Qt.UserRole)
            if pid:
                drag = QDrag(self)
                drag.setHotSpot(QPoint(20, 10))
                drag.setPixmap(icon.pixmap(QSize(16, 16)))
                # create_mime_data() will ignore the icon in this case
                mime_data = create_mime_data(pid, icon)
                drag.setMimeData(mime_data)
                drag.exec_(Qt.CopyAction)
        except:
            # tried to drag in an area outside the tree
            pass

    def mouseMoveEvent(self, event):
        if self.dragEnabled():
            self.startDrag(event)


if __name__ == '__main__':
    # strictly for testing purposes
    import sys
    orb.start(home='pangalaxian_test')
    app = QApplication(sys.argv)
    model = ParmDefTreeModel()
    view = QTreeView()
    view.setModel(model)
    view.setWindowTitle("Parameter Tree Model")
    view.show()
    sys.exit(app.exec_())

