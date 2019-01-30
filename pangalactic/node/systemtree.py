"""
System Tree view and models
"""
from builtins import str
from builtins import range
from builtins import object
import re
# import sys
from textwrap import wrap
# louie
from louie import dispatcher

# PyQt
from PyQt5.QtGui  import QBrush, QIcon
from PyQt5.QtCore import (Qt, QAbstractItemModel, QItemSelectionModel,
                          QModelIndex, QSize, QSortFilterProxyModel, QVariant,
                          pyqtSignal)
# from PyQt5.QtCore import QRegExp
from PyQt5.QtWidgets import (QAbstractItemView, QAction, QDialog, QMessageBox,
                             QSizePolicy, QTreeView)

# pangalactic
from pangalactic.core             import prefs, state
from pangalactic.core.parametrics import get_pval, get_pval_as_str, parameterz
from pangalactic.core.uberorb     import orb
from pangalactic.core.utils.datetimes import dtstamp
from pangalactic.core.validation  import get_assembly, get_bom_oids
from pangalactic.core.units       import in_si
from pangalactic.core.utils.meta  import display_id, get_acu_id, get_acu_name
from pangalactic.node.dialogs     import AssemblyNodeDialog
from pangalactic.node.pgxnobject  import PgxnObject
# from pangalactic.node.utils      import HTMLDelegate
from pangalactic.node.utils       import (clone, create_mime_data,
                                          create_product_from_template,
                                          extract_mime_content, get_pixmap)


class Node(object):

    def __init__(self, obj, link=None, refdes=False, parent=None, *args,
                 **kwargs):
        """
        Initialize a Node.  NOTE:  a Node must be identified by an object and
        the object's relationship to the parent Node's object (here the
        relationship is referred to as the "link").  This is required because
        a given Product object may be used more than once in the assembly of
        another Product object.

        Args:
            obj (Product or Project):  the Node's object

        Keyword Args:
            link (Acu or ProjectSystemUsage):  relationship between the
                Node's object and its parent Node's object
            refdes (bool):  flag indicating whether to display the reference
                designator or the component name as the node name
            parent (Node):  the Node's parent Node
        """
        super(Node, self).__init__(*args, **kwargs)
        self._obj = obj
        self.link = link
        self.refdes = refdes
        # TODO:  make 'cname' a property
        self.parent = None
        self.children = []
        # self.is_traversed = False
        # if parent is not None:
            # parent.add_child(self)

    @property
    def cname(self):
        return self.obj.__class__.__name__

    @property
    def obj(self):
        return self._obj

    @obj.setter
    def obj(self, value):
        orb.log.info('* Node.obj.setter: set obj {}'.format(
                                            getattr(value, 'id', 'unknown')))
        self._obj = value
        if self.link:
            if self.link.__class__.__name__ == 'Acu':
                self.link.component = value
            elif self.link.__class__.__name__ == 'ProjectSystemUsage':
                self.link.system = value
            # this saves the existing link with new 'system' or 'component'
            self.link.mod_datetime = dtstamp()
            orb.save([self.link])
            # "modified object" signal is only sent when object is set by a
            # local action (e.g. a drop) -- otherwise, it was remotely modified
        else:
            orb.log.debug('  - ERROR: node has no link.')

    @property
    def name(self):
        obj_id = display_id(self.obj)
        # if self.refdes:
            # if isinstance(self.link, orb.classes['Acu']):
                # return (self.link.reference_designator or
                        # self.link.product_type_hint or
                        # obj_id)
            # elif isinstance(self.link, orb.classes['ProjectSystemUsage']):
                # return self.link.system_role or obj_id
            # else:
                # return obj_id
        # else:
        # *not* in ref designator mode -- only return ref des if node is
        # "empty" (i.e., obj_id is 'TBD')
        if obj_id == 'TBD':
            if isinstance(self.link, orb.classes['Acu']):
                if getattr(self.link, 'product_type_hint', None):
                    return 'TBD [' + self.link.product_type_hint.name + ']'
                else:
                    return 'TBD'
            elif isinstance(self.link, orb.classes['ProjectSystemUsage']):
                return self.link.system_role or obj_id
            else:
                return obj_id
        else:
            if (getattr(self.link, 'component', None) == self.obj
                and hasattr(self.link, 'quantity')):
                if self.link.quantity and self.link.quantity > 1:
                    return '{} [{}]'.format(obj_id, str(self.link.quantity))
                else:
                    return obj_id
            else:
                return obj_id

    @property
    def tooltip(self):
        if not self.refdes:
            return getattr(self.obj, 'name', None) or getattr(self.obj, 'id')
        else:
            if (self.link and
                ((getattr(self.link, 'component', None) == self.obj)
                 or (getattr(self.link, 'system', None) == self.obj))):
                if getattr(self.link, 'reference_designator', None):
                    return (self.link.reference_designator + ': '
                            + getattr(self.obj, 'name', 'TBD'))
                elif hasattr(self.link, 'system_role'):
                    return ((self.link.system_role or 'System') + ': '
                            + getattr(self.obj, 'name', 'TBD'))
                else:
                    return getattr(self.obj, 'name', 'TBD')
            else:
                return getattr(self.obj, 'name', 'TBD')

    @property
    def is_traversed(self):
        if self.cname == 'FakeRoot':
            return True
        elif issubclass(orb.classes[self.cname], orb.classes['Product']):
            return self.child_count() == len(self.obj.components)
        elif self.cname == 'Project':
            return self.child_count() == len(self.obj.systems)
        return True

    @property
    def is_branch_node(self):
        if self.cname == 'FakeRoot':
            return True
        elif issubclass(orb.classes.get(self.cname), orb.classes['Product']):
            return bool(self.obj.components)
        elif self.cname == 'Project':
            return bool(self.obj.systems)
        return False

    def add_child(self, child):
        self.children.append(child)
        child.parent = self

    def insert_child(self, position, child):
        if position < 0 or position > self.child_count():
            return False
        self.children.insert(position, child)
        child.parent = self
        return True

    def remove_children(self, position, count):
        if position < 0 or position + count > len(self.children):
            return False
        for row in range(count):
            self.children.pop(position)
        return True

    def child(self, row):
        if row < len(self.children):
            return self.children[row]
        else:
            return None

    def child_count(self):
        return len(self.children)

    def row(self):
        if self.parent is not None and self in self.parent.children:
            return self.parent.children.index(self)
        return 0


class FakeRoot(object):
    oid = ''


def get_formatted_label(node):
    return '<font color="purple">{}:</font> {}'.format(node.name,
                                                       node.obj.id)

class SystemTreeProxyModel(QSortFilterProxyModel):
    """
    Special table model that includes text filtering and sort algorithms.

        * numeric sort (for integers and floats)
        * text sort for everything else
    """
    numpat = r'[0-9][0-9]*(\.[0-9][0-9]*)'

    def __init__(self, source_model, parent=None):
        super(SystemTreeProxyModel, self).__init__(parent=parent)
        self.setSourceModel(source_model)
        self.cols = self.sourceModel().cols
        self.col_defs = self.sourceModel().col_defs

    def filterAcceptsRow(self, sourceRow, sourceParent):
        idxs = []
        for i in range(len(self.cols)):
            idxs.append(self.sourceModel().index(sourceRow, i, sourceParent))
        return any([(self.filterRegExp().indexIn(
                    str(self.sourceModel().data(idx, Qt.UserRole))) >= 0)
                    for idx in idxs])

    def is_numeric(self, s):
        try:
            m = re.match(self.numpat, str(s))
            return m.group(0) == s
        except:
            return False

    def lessThan(self, left, right):
        lvalue = str(self.sourceModel().data(left, Qt.DisplayRole)).lower()
        rvalue = str(self.sourceModel().data(right, Qt.DisplayRole)).lower()
        return lvalue < rvalue
        # text_pattern = QRegExp("([\\w\\.]*@[\\w\\.]*)")
        # if left.column() == 1 and text_pattern.indexIn(lvalue) != -1:
            # lvalue = text_pattern.cap(1)
        # if right.column() == 1 and text_pattern.indexIn(rvalue) != -1:
            # rvalue = text_pattern.cap(1)
        # if (self.is_numeric(left_data) and self.is_numeric(right_data)):
            # lvalue = float(left_data)
            # rvalue = float(right_data)
            # if lvalue and rvalue:
                # return lvalue < rvalue
            # else:
                # return QSortFilterProxyModel.lessThan(self, left, right)
        # else:


class SystemTreeModel(QAbstractItemModel):

    successful_drop = pyqtSignal()
    BRUSH = QBrush()
    RED_BRUSH = QBrush(Qt.red)
    GRAY_BRUSH = QBrush(Qt.lightGray)
    CYAN_BRUSH = QBrush(Qt.cyan)
    YELLOW_BRUSH = QBrush(Qt.yellow)

    def __init__(self, obj, refdes=True, show_allocs=False, req=None,
                 parent=None):
        """
        Args:
            obj (Project): root object of the tree

        Keyword Args:
            refdes (bool):  flag indicating whether to display the reference
                designator as part of the tooltip
            show_allocs (bool):  flag indicating whether to highlight nodes to
                which a specified requirement has been allocated
            req (Requirement):  the requirement whose allocations should be
                highlighted if 'show_allocs' is True
            parent (QWidget): parent widget of the SystemTreeModel
        """
        super(SystemTreeModel, self).__init__(parent=parent)
        self.parent = parent
        self.refdes = refdes
        self.show_allocs = show_allocs
        self.req = req
        self.cols = []
        self.col_defs = []
        dash_name = state.get('dashboard_name')
        if not dash_name:
            if prefs.get('dashboard_names'):
                dash_name = prefs['dashboard_names'][0]
                if not prefs['dashboards'].get(dash_name):
                    prefs['dashboards'][dash_name] = []
            else:
                dash_name = 'TBD'
                prefs['dashboard_names'] = [dash_name]
                prefs['dashboards'][dash_name] = []
        state['dashboard_name'] = dash_name
        self.cols = prefs['dashboards'][dash_name]
        header_labels = []
        cols = self.cols[:]
        for p_id in cols:
            pd = orb.select('ParameterDefinition', id=p_id)
            if not pd:
                # if there is no ParameterDefinition with this p_id,
                # ignoer it
                self.cols.remove(p_id)
                continue
            # no preference (i.e., is set to None) -> use base units
            units = prefs['units'].get(pd.dimensions) or in_si.get(
                                                            pd.dimensions, '')
            if units:
                units = '(' + units + ')'
            header_labels.append('   \n   '.join(wrap(
                                 pd.name, width=7,
                                 break_long_words=False) + [units]))
            self.col_defs.append('\n'.join(wrap(
                                 pd.description, width=30,
                                 break_long_words=False))) 
        self.headers = ['   {}   '.format(n) for n in header_labels]
        fake_root = FakeRoot()
        self.root = Node(fake_root)
        self.root.parent = None
        self.object_nodes = {}
        if obj is None:
            # create a "null" Project
            Project = orb.classes['Project']
            obj = Project(oid='No Project', id='No Project', name='No Project')
        self.project = obj
        top_node = self.node_for_object(obj, self.root)
        self.root.children = [top_node]
        self.successful_drop_index = None

    @property
    def req(self):
        return self._req

    @req.setter
    def req(self, r):
        self._req = r

    def node_for_object(self, obj, parent, link=None):
        """
        Return a Node instance for an object and its "parent" object.  This is
        a factory function that can be used with either a Product object or a
        Project.  Only in the case of a Product will there be a 'link' (Acu or
        ProjectSystemUsage).

        NOTE:  this function should never receive a None value for 'obj'

        Args:
            obj (Project or Product):  the object instance associated with the
                node (must be not be None)
            parent (Node):  the node's parent node
        """
        link_oid = getattr(link, 'oid', None)
        node = self.object_nodes.get((obj.oid,
                                      getattr(parent.obj, 'oid', None),
                                      link_oid))
        if not node:
            node = Node(obj, parent=parent, link=link, refdes=self.refdes)
            self.object_nodes[(obj.oid,
                               getattr(parent.obj, 'oid', None),
                               link_oid)] = node
        return node

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsEnabled
        # NOTE:  Selectable is needed for tree operations like delete node
        return (Qt.ItemIsEnabled | Qt.ItemIsDropEnabled | Qt.ItemIsSelectable)

    def supportedDropActions(self): 
        return Qt.CopyAction | Qt.MoveAction         

    def get_node(self, index):
        """
        Return the related Node for a model index.
        """
        if index.isValid():
            return index.internalPointer()
        else:
            return self.root

    def canFetchMore(self, index):
        """
        Check if the node has data that has not been loaded yet.
        """
        node = self.get_node(index)
        if node.is_branch_node and not node.is_traversed:
            return True
        return False

    def fetchMore(self, index):
        """
        Retrieve child nodes for this index (called if canFetchMore returns
        True, then dynamically inserts all nodes required for assembly
        contents).
        """
        # call this node "pnode" (parent node)
        pnode = self.get_node(index)
        nodes = []
        if hasattr(pnode.obj, 'components'):
            # -> this is a Product node
            # NOTE: "if acu.component" is needed in case Acu has been corrupted
            # (e.g. if its 'component' object is None)
            acus = [acu for acu in pnode.obj.components if acu.component]
            for acu in acus:
                comp_node = self.node_for_object(acu.component, pnode,
                                                 link=acu)
                nodes.append(comp_node)
                dispatcher.send('tree node fetched')
        elif pnode.cname == 'Project':
            # -> this is a Project node
            psus = [psu for psu in pnode.obj.systems if psu.system]
            # NOTE: "if psu.system" is needed in case psu has been corrupted
            # (e.g. if its 'system' object is None)
            if psus:
                for psu in psus:
                    sys_node = self.node_for_object(psu.system, pnode,
                                                    link=psu)
                    nodes.append(sys_node)
                    dispatcher.send('tree node fetched')
        self.add_nodes(nodes, index)

    def hasChildren(self, index):
        """
        Return True for assembly nodes so that Qt knows to check if there is
        more to load
        """
        node = self.get_node(index)
        if node.is_branch_node:
            return True
        return super(SystemTreeModel, self).hasChildren(index)

    def rowCount(self, index):
        """
        Return 0 if there is data to fetch (handled implicitly by check length
        of child list).
        """
        node = self.get_node(index)
        if not node.is_traversed:
            return 0
        else:
            return node.child_count()

    def columnCount(self, index):
        """
        Return number of columns in the tree (for an assembly tree, it is 1;
        for a dashboard tree, the number of columns depends on the number of
        parameters being displayed).

        Args:
            index (QModelIndex):  this argument is required by the
                method in QAbstractItemView, but it is ignored in this
                implementation because the number of columns is the same for
                all nodes in the tree
        """
        if self.cols:
            return len(self.cols) + 1
        else:
            return 1

    def parent(self, index):
        """
        Return the parent index of the specified index.

        Args:
            index (QModelIndex):  the index whose parent is sought
        """
        node = self.get_node(index)
        parent = node.parent
        if parent == self.root:
            return QModelIndex()
        elif parent is not None:
            return self.createIndex(parent.row(), 0, parent)
        else:
            return QModelIndex()

    def index(self, row, column, parent):
        """
        Return the index with the specified row, column and parent index.

        Args:
            row (int):  the row (within the parent's children)
            column (int):  the column (within the parent's children)
            index (QModelIndex):  the parent index of the index being sought
        """
        if parent.isValid:
            node = self.get_node(parent)
            child = node.child(row)
            if not child:
                return QModelIndex()
            return self.createIndex(row, column, child)
        else:
            return self.createIndex(0, 0, self.root)

    def data(self, index, role):
        if not index.isValid():
            return None
        node = index.internalPointer()
        if role == Qt.DecorationRole and index.column() == 0:
            return get_pixmap(node.obj)
        if role == Qt.DisplayRole:
            # MODIFIED 3/5/17:  make assembly tree & dashboard tree both
            # use Acu.reference_designator as the node's "display name"
            # MODIFIED 4/6/17:  make assembly tree display
            # Acu.reference_designator but dashboard display ref designator
            # *plus* product name (since it has more real estate)
            if self.cols:
                if node.obj.__class__.__name__ == 'Project':
                    if index.column() == 0:
                        return node.obj.id
                    else:
                        return ''
                else:
                    if index.column() == 0:
                        return node.name
                    else:
                        pid = self.cols[index.column()-1]
                        parm = parameterz.get(node.obj.oid, {}).get(pid, {})
                        units = prefs['units'].get(parm.get('dimensions'))
                        return get_pval_as_str(orb, node.obj.oid, pid,
                                               units=units)
            else:
                return node.name
        if role == Qt.ForegroundRole:
            if self.cols and index.column() > 0:
                pval = get_pval(orb, node.obj.oid,
                                self.cols[index.column()-1])
                if isinstance(pval, (int, float)) and pval <= 0:
                    return self.RED_BRUSH
                else:
                    return self.BRUSH
        if role == Qt.BackgroundRole and self.req and self.show_allocs:
            # in case node.link is an Acu:
            allocs = getattr(node.link, 'allocated_requirements', [])
            # in case node.link is a ProjectSystemUsage:
            srs = getattr(node.link, 'system_requirements', [])
            if self.req in allocs or self.req in srs:
                return self.YELLOW_BRUSH
        if role == Qt.TextAlignmentRole:
            if index.column() == 0:
                return Qt.AlignLeft
            else:
                return Qt.AlignRight
        if role == Qt.ToolTipRole:
            return node.tooltip
        if role == Qt.UserRole:
            return node.obj
        else:
            return None

    def setData(self, index, value, role=Qt.EditRole):
        """
        Set a new value for the node at the specified index.  The value is a
        Product object.

        Args:
            index (QModelIndex):  tree location at which to set the data
            value (Product):  object to be set as the node's "value"
        """
        if index.isValid():
            if role == Qt.EditRole:
                node = index.internalPointer()
                # orb.save([node.link]) is called by Node obj setter
                # ** DO NOT dispatch "modified object" because this action may
                # have been initiated by a remote event
                node.obj = value
                # signal the views that data has changed
                self.dataChanged.emit(index, index)
                return True
        return False

    def headerData(self, section, orientation, role):
        if (orientation == Qt.Horizontal and
            role == Qt.DisplayRole):
            if self.cols:
                # assert 0 <= section <= len(self.headers)
                if section == 0:
                    return QVariant('System')
                else:
                    return QVariant(self.headers[section-1])
            else:
                return self.root.name
        elif role == Qt.ToolTipRole:
            if section == 0:
                return 'System or component identifier'
            return self.col_defs[section-1]
        return QVariant()

    def mimeTypes(self):
        """
        MIME Types accepted for drops.
        """
        # TODO:  should return mime types for Product and *ALL* subclasses
        return ['application/x-pgef-hardware-product',
                'application/x-pgef-template']

    def mimeData(self, indexes):
        # according to PyQt docs, return 0 (not an empty list) if no indexes
        if not indexes:
            return 0
        mimedata = []
        for idx in indexes:
            node = self.get_node(idx)
            if node.obj:
                icon = QIcon(get_pixmap(node.obj))
                mimedata.append(create_mime_data(node.obj, icon))
        return mimedata

    def dropMimeData(self, data, action, row, column, parent):
        """
        Handle the drop event on the system tree.  This includes the following
        possible cases:

            0: dropped item would cause a cycle -> abort
            1: drop target is "TBD" -> replace it
                1.1:  drop item is Template -> create a new Product from it
                1.2:  drop item is Product -> use it
            2: drop target is a normal Product -> add a new component position
                2.1:  drop item is a Template -> create a new Product from it
                      that will be added as a component
                2.2:  drop item is a Product -> add it as a new component
            3: drop target is a Project
                3.1:  drop item is a Template
                      3.1.1 -> use it to create a new Product as a "system"
                      3.1.2 -> add it as a Template so it can be edited
                3.2:  drop item is a Product -> *if* it is not already in use
                      on the Project, use it to create a new ProjectSystemUsage
        """
        orb.log.info('* SystemTreeModel.dropMimeData()')
        # NOTE: for now, dropped item must be a HardwareProduct ... in the
        # future, may accomodate *ANY* Product subclass (including Model,
        # Document, etc.)
        drop_target = self.data(parent, Qt.UserRole)
        if not drop_target or not hasattr(drop_target, 'oid'):
            orb.log.info('  - drop ignored -- invalid drop target.')
            return False
        if (data.hasFormat("application/x-pgef-hardware-product")
            or data.hasFormat("application/x-pgef-template")):
            self.successful_drop_index = None
            if data.hasFormat("application/x-pgef-hardware-product"):
                content = extract_mime_content(data,
                                        "application/x-pgef-hardware-product")
            else:
                content = extract_mime_content(data,
                                        "application/x-pgef-template")
            icon, obj_oid, obj_id, obj_name, obj_cname = content
            dropped_item = orb.get(obj_oid)
            orb.log.info('  - item dropped: %s' % (dropped_item.name))
            if drop_target.oid == obj_oid:
                orb.log.info('    invalid: dropped item same as target.')
                popup = QMessageBox(
                            QMessageBox.Critical,
                            "Assembly same as Component",
                            "A product cannot be a component of itself.",
                            QMessageBox.Ok, self.parent)
                popup.show()
                return False
            orb.log.debug('  - action: {}'.format(action))
            orb.log.debug('  - row: {}'.format(row))
            orb.log.debug('  - column: {}'.format(column))
            orb.log.debug('  - target name: {}'.format(drop_target.name))
            target_cname = drop_target.__class__.__name__
            if issubclass(orb.classes[target_cname], orb.classes['Product']):
                orb.log.info('    + target is a subclass of Product ...')
                # first check for cycles (cycles will crash the tree)
                bom_oids = get_bom_oids(dropped_item)
                if (drop_target.oid in bom_oids and 
                    drop_target.oid != 'pgefobjects:TBD'):
                    # case 0: dropped item would cause a cycle -> abort
                    popup = QMessageBox(
                                QMessageBox.Critical,
                                "Prohibited Operation",
                                "Product cannot be used in its own assembly.",
                                QMessageBox.Ok, self.parent)
                    popup.show()
                    return False
                elif drop_target.oid == 'pgefobjects:TBD':
                    # case 1: drop target is "TBD" product -> replace it
                    node = self.get_node(parent)
                    if data.hasFormat("application/x-pgef-template"):
                        # case 1.1:  drop item is Template -> create a new
                        # product from it
                        ptype = dropped_item.product_type
                        hint = ''
                        if getattr(node.link, 'product_type_hint', None):
                            hint = getattr(node.link.product_type_hint, 'name',
                                           '')
                        if hint and ptype.name != hint:
                            # ret = QMessageBox.warning(
                            ret = QMessageBox.critical(
                                    self.parent, "Product Type Check",
                                    "The template you dropped is not for "
                                    "a {}.".format(hint), QMessageBox.Cancel)
                                    # "use it anyway?".format(hint),
                                    # QMessageBox.Yes | QMessageBox.No)
                            if ret == QMessageBox.Cancel:
                                return False
                            ### DEPRECATED:  this code enabled the
                            ### "product type hint" to be overridden ...
                            # if ret == QMessageBox.Yes:
                                # product = create_product_from_template(
                                                                # dropped_item)
                                # view = dict(id='', name='', product_type='',
                                            # description='')
                                # panels = ['main']
                                # # call new product dialog:
                                # dlg = PgxnObject(product, edit_mode=True,
                                                 # view=view, panels=panels,
                                                 # modal_mode=True,
                                                 # parent=self.parent)
                                # if dlg.exec_():
                                    # # NOTE:  setting node.obj saves the link
                                    # # (acu/psu) object
                                    # node.obj = product
                                    # self.dataChanged.emit(parent, parent)
                                    # self.successful_drop.emit()
                                    # return True
                            # elif ret == QMessageBox.No:
                                # return False
                        else:
                            product = create_product_from_template(
                                                                dropped_item)
                            # view = dict(id='', name='', product_type='',
                                        # description='')
                            # panels = ['main']
                            # # call new product dialog:
                            # dlg = PgxnObject(product, edit_mode=True,
                                             # view=view, panels=panels,
                                             # new=True, modal_mode=True,
                                             # parent=self.parent)
                            # dlg.show()
                            node.obj = product
                            if not getattr(node.link, 'product_type_hint',
                                           None):
                                pt = product.product_type
                                node.link.product_type_hint = pt
                            self.dataChanged.emit(parent, parent)
                            self.successful_drop.emit()
                            orb.log.info(
                                '   node link modified [product created '
                                'from template]: {}'.format(
                                node.link.name))
                            dispatcher.send('modified object',
                                            obj=node.link)
                            return True
                    else:
                        # case 1.2:  drop item is product -> use it
                        # is dropped item's product_type same as acu's "hint"?
                        ptname = getattr(dropped_item.product_type, 'name', '')
                        hint = ''
                        if getattr(node.link, 'product_type_hint', None):
                            hint = getattr(node.link.product_type_hint, 'name',
                                           '')
                        if hint and ptname != hint:
                            # ret = QMessageBox.warning(
                            ret = QMessageBox.critical(
                                        self.parent, "Product Type Check",
                                        "The product you dropped is not a "
                                        "{}.".format(hint),
                                        QMessageBox.Cancel)
                                        # " Add it anyway?".format(hint),
                                        # QMessageBox.Yes | QMessageBox.No)
                            if ret == QMessageBox.Cancel:
                                return False
                            # if ret == QMessageBox.Yes:
                                # node.obj = dropped_item
                                # self.dataChanged.emit(parent, parent)
                                # self.successful_drop.emit()
                                # return True
                            # elif ret == QMessageBox.No:
                                # return False
                        else:
                            # orb.save([node.link]) is called by Node obj
                            # setter
                            node.obj = dropped_item
                            if not getattr(node.link, 'product_type_hint',
                                           None):
                                pt = dropped_item.product_type
                                node.link.product_type_hint = pt
                            self.dataChanged.emit(parent, parent)
                            self.successful_drop.emit()
                            orb.log.info('   node link modified: {}'.format(
                                         node.link.name))
                            dispatcher.send('modified object', obj=node.link)
                            return True
                else:
                    # case 2: drop target is a normal product -> add new Acu
                    if data.hasFormat("application/x-pgef-template"):
                        # case 2.1:  drop item is a Template -> use it to
                        # create a new product that will be a dropped_item
                        ptype = dropped_item.product_type
                        product = create_product_from_template(dropped_item)
                        # view = dict(id='', name='', product_type='',
                                    # description='')
                        # panels = ['main']
                        # # call new product dialog:
                        # dlg = PgxnObject(product, edit_mode=True,
                                         # view=view, panels=panels,
                                         # new=True, modal_mode=True,
                                         # parent=self.parent)
                        # if dlg.exec_():
                        orb.log.info('      creating Acu ...')
                        # generate a new reference_designator
                        ref_des = orb.get_next_ref_des(drop_target,
                                                       product)
                        new_acu = clone('Acu',
                                id=get_acu_id(drop_target.id, ref_des),
                                name=get_acu_name(drop_target.name, ref_des),
                                assembly=drop_target,
                                component=product,
                                product_type_hint=dropped_item.product_type,
                                reference_designator=ref_des)
                        orb.save([new_acu])
                        orb.log.info('      Acu created: %s' % new_acu.name)
                        self.add_nodes([self.node_for_object(product,
                                        parent=self.get_node(parent),
                                        link=new_acu)], parent)
                        self.successful_drop_index = parent
                        self.successful_drop.emit()
                        dispatcher.send('new object', obj=new_acu)
                        return True
                    else:
                        # case 2.2:  drop item is a product -> add it as a new
                        # component
                        orb.log.info('      creating Acu ...')
                        # generate a new reference_designator
                        ref_des = orb.get_next_ref_des(drop_target,
                                                       dropped_item)
                        new_acu = clone('Acu',
                                id=get_acu_id(drop_target.id, ref_des),
                                name=get_acu_name(drop_target.name, ref_des),
                                assembly=drop_target,
                                component=dropped_item,
                                product_type_hint=dropped_item.product_type,
                                reference_designator=ref_des)
                        orb.save([new_acu])
                        orb.log.info('      Acu created: %s' % new_acu.name)
                        self.add_nodes([self.node_for_object(
                                        dropped_item,
                                        parent=self.get_node(parent),
                                        link=new_acu)], parent)
                        self.successful_drop_index = parent
                        self.successful_drop.emit()
                        dispatcher.send('new object', obj=new_acu)
                        return True
            elif target_cname == 'Project':
                # case 3: drop target is a project
                orb.log.info('    + target is a Project -- creating PSU ...')
                # TODO:  apply or generate system_role attr
                if data.hasFormat("application/x-pgef-template"):
                    # case 3.1:  drop item is a Template -> use it to
                    # create a new product that will be a component
                    ret = QMessageBox.warning(
                            self.parent, "Template Check",
                            "You dropped a Template -- do you want to create "
                            "a product from it?",
                            QMessageBox.Yes | QMessageBox.No)
                    if ret == QMessageBox.Yes:
                        ptype = dropped_item.product_type
                        product = create_product_from_template(dropped_item)
                        # view = dict(id='', name='', product_type='',
                                    # description='')
                        # panels = ['main']
                        # call new product dialog:
                        # dlg = PgxnObject(product, edit_mode=True,
                                         # view=view, panels=panels,
                                         # new=True, modal_mode=True,
                                         # parent=self.parent)
                        # if dlg.exec_():
                        orb.log.info('      creating ProjectSystemUsage')
                        psu_id = 'psu-' + product.id + '-' + drop_target.id
                        psu_name = ('psu: ' + product.name +
                                    ' (system used on) ' +
                                    drop_target.name)
                        psu_role = getattr(product.product_type, 'name',
                                           'System')
                        new_psu = clone('ProjectSystemUsage',
                                        id=psu_id,
                                        name=psu_name,
                                        system_role=psu_role,
                                        project=drop_target,
                                        system=product)
                        orb.save([new_psu])
                        orb.log.info('      ProjectSystemUsage created: %s'
                                      % psu_name)
                        self.add_nodes([self.node_for_object(
                                           product,
                                           parent=self.get_node(parent),
                                           link=new_psu)],
                                       parent)
                        self.successful_drop_index = parent
                        self.successful_drop.emit()
                        dispatcher.send('new object', obj=new_psu)
                        return True
                    elif ret == QMessageBox.No:
                        # check whether a PSU already exists for that Template
                        psu = orb.search_exact(cname='ProjectSystemUsage',
                                               project=drop_target,
                                               system=dropped_item)
                        if psu:
                            QMessageBox.warning(self.parent,
                                'Already exists',
                                'Template "{0}" already exists '
                                'on project {1}'.format(
                                dropped_item.name, drop_target.id))
                        else:
                            psu_id = ('psu-' + dropped_item.id + '-' +
                                      drop_target.id)
                            psu_name = ('psu: ' + dropped_item.name +
                                        ' (system used on) ' +
                                        drop_target.name)
                            psu_role = getattr(dropped_item.product_type, 'name',
                                               'System')
                            new_psu = clone('ProjectSystemUsage',
                                            id=psu_id,
                                            name=psu_name,
                                            system_role=psu_role,
                                            project=drop_target,
                                            system=dropped_item)
                            orb.save([new_psu])
                            orb.log.info('      ProjectSystemUsage created: %s'
                                          % psu_name)
                            self.add_nodes([self.node_for_object(
                                            dropped_item,
                                            parent=self.get_node(parent),
                                            link=new_psu)], parent)
                            self.successful_drop_index = parent
                            self.successful_drop.emit()
                            dispatcher.send('new object', obj=new_psu)
                            return True
                else:
                    # case 3.2:  drop item is a product -> *if* it is not
                    # already in use on the project, add a new Psu
                    psu = orb.search_exact(cname='ProjectSystemUsage',
                                           project=drop_target,
                                           system=dropped_item)
                    if psu:
                        QMessageBox.warning(self.parent,
                                        'Already exists',
                                        'System "{0}" already exists on '
                                        'project {1}'.format(
                                        dropped_item.name, drop_target.id))
                    else:
                        psu_id = 'psu-' + dropped_item.id + '-' + drop_target.id
                        psu_name = ('psu: ' + dropped_item.name +
                                    ' (system used on) ' + drop_target.name)
                        psu_role = getattr(dropped_item.product_type, 'name',
                                           'System')
                        new_psu = clone('ProjectSystemUsage',
                                        id=psu_id,
                                        name=psu_name,
                                        system_role=psu_role,
                                        project=drop_target,
                                        system=dropped_item)
                        orb.save([new_psu])
                        orb.log.info('      ProjectSystemUsage created: %s'
                                      % psu_name)
                        self.add_nodes([self.node_for_object(
                                   dropped_item, parent=self.get_node(parent),
                                   link=new_psu)], parent)
                        self.successful_drop_index = parent
                        self.successful_drop.emit()
                        dispatcher.send('new object', obj=new_psu)
            else:
                orb.log.info('    + target is not a Project or Product '
                              '-- no action taken.')
                return False
            return True
        else:
            return False

    def removeRows(self, position, count, parent=QModelIndex()):
        """
        Implementation of QAbstractItemModel method for SystemTreeModel.
        (Note that removeRow() is a convenience function that calls this.)

        Note: if a row (node) being deleted represents an Acu (Assembly
        Component Usage) instance, it is possible for there to be other nodes
        in the tree that reference that same Acu instance -- since they all
        represent the same object, which is being deleted, all such nodes must
        be located and deleted.
        """
        orb.log.info('* SystemTreeModel.removeRows()')
        orb.log.debug('  position: {}'.format(position))
        orb.log.debug('  count: {}'.format(count))
        parent_node = self.get_node(parent)
        orb.log.debug('  parent_node: {}'.format(
                                 getattr(parent_node.obj, 'id', '[no id]')))
        self.beginRemoveRows(parent, position, position + count - 1)
        links_to_delete = []
        for pos in range(position, position + count):
            i = self.index(position, 0, parent)
            node_being_removed = self.get_node(i)
            links_to_delete.append(node_being_removed.link)
        acus = [l.oid for l in links_to_delete
                if isinstance(l, orb.classes['Acu'])]
        if acus:
            orb.log.debug('  + acus to be deleted: {}'.format(
                          [l.id for l in links_to_delete
                           if isinstance(l, orb.classes['Acu'])]))
        psus = [l.oid for l in links_to_delete
                if isinstance(l, orb.classes['ProjectSystemUsage'])]
        if psus:
            orb.log.debug('  + psus to be deleted: {}'.format(
                          [l.oid for l in links_to_delete
                if isinstance(l, orb.classes['ProjectSystemUsage'])]))
        orb.delete(links_to_delete)
        success = parent_node.remove_children(position, count)
        self.endRemoveRows()
        self.dataChanged.emit(parent, parent)
        for acu_oid in acus:
            dispatcher.send(signal="deleted object", oid=acu_oid, cname='Acu')
        for psu_oid in psus:
            dispatcher.send(signal="deleted object", oid=psu_oid,
                            cname='ProjectSystemUsage')
        return success

    def add_nodes(self, nodes, parent=QModelIndex()):
        node = self.get_node(parent)
        position = node.child_count()
        self.beginInsertRows(parent, position, position + len(nodes) - 1)
        for child in nodes:
            node.add_child(child)
        self.endInsertRows()
        self.dirty = True
        return True


class SystemTreeView(QTreeView):
    def __init__(self, obj, refdes=True, show_allocs=False, req=None,
                 parent=None):
        """
        Args:
            obj (Project or Product): root object of the tree

        Keyword Args:
            refdes (bool):  flag indicating whether to display the reference
                designator or the component name as the node name
            show_allocs (bool):  flag indicating whether to highlight nodes to
                which a specified requirement has been allocated
            req (Requirement):  the requirement whose allocations should be
                highlighted if 'show_allocs' is True
        """
        super(SystemTreeView, self).__init__(parent)
        self.show_allocs = show_allocs
        tree_model = SystemTreeModel(obj, refdes=refdes,
                                     show_allocs=show_allocs,
                                     req=req, parent=self)
        self.proxy_model = SystemTreeProxyModel(tree_model, parent=self)
        self.source_model = self.proxy_model.sourceModel()
        self.proxy_model.setDynamicSortFilter(True)
        # old tree used model directly:
        # self.setModel(tree_model)
        self.setModel(self.proxy_model)
        # all rows are same height, so use this to optimize performance
        self.setUniformRowHeights(True)
        # delegate = HTMLDelegate()
        # self.setItemDelegate(delegate)
        self.setHeaderHidden(True)
        cols = self.source_model.cols
        if cols:
            for i in range(1, len(cols)+1):
                self.hideColumn(i)
        self.setSelectionMode(self.SingleSelection)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.source_model.successful_drop.connect(self.on_successful_drop)
        self.create_actions()
        self.setup_context_menu()
        # only use louie messages for assembly tree and dashboard tree
        # (i.e., a shared model); ignore them when instantiated in reqt
        # allocation mode (different models -> the indexes are not valid
        # anyway!!)
        if not show_allocs:
            self.expanded.connect(self.sys_node_expanded)
            self.collapsed.connect(self.sys_node_collapsed)
            self.clicked.connect(self.sys_node_selected)
            dispatcher.connect(self.sys_node_expand, 'dash node expanded')
            dispatcher.connect(self.sys_node_collapse, 'dash node collapsed')
            dispatcher.connect(self.sys_node_select, 'dash node selected')
            dispatcher.connect(self.sys_node_select, 'diagram go back')
        self.setStyleSheet('font-weight: normal; font-size: 12px')
        self.proxy_model.sort(0)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        self.setMaximumWidth(400)
        self.resizeColumnToContents(0)
        self.project = self.source_model.project
        if not state.get('sys_trees'):
            state['sys_trees'] = {}
        if not state['sys_trees'].get(self.project.id):
            state['sys_trees'][self.project.id] = {}

    @property
    def req(self):
        return self.source_model._req

    @req.setter
    def req(self, r):
        self.source_model._req = r
        self.dataChanged(QModelIndex(), QModelIndex())

    def sizeHint(self):
        return QSize(300, 300)

    def sys_node_expanded(self, index):
        dispatcher.send(signal='sys node expanded', index=index)

    def sys_node_collapsed(self, index):
        dispatcher.send(signal='sys node collapsed', index=index)

    def sys_node_selected(self, index):
        if len(self.selectedIndexes()) == 1:
            i = self.selectedIndexes()[0]
            mapped_i = self.proxy_model.mapToSource(i)
            obj = self.source_model.get_node(mapped_i).obj
            link = self.source_model.get_node(mapped_i).link
            dispatcher.send(signal='sys node selected', index=index, obj=obj,
                            link=link)

    def sys_node_expand(self, index=None):
        try:
            if index and not self.isExpanded(index):
                self.expand(index)
        except:
            # oops -- my C++ object probably got deleted
            pass

    def sys_node_collapse(self, index=None):
        try:
            if index and self.isExpanded(index):
                self.collapse(index)
        except:
            # oops -- my C++ object probably got deleted
            pass

    def sys_node_select(self, index=None):
        try:
            if index:
                self.selectionModel().setCurrentIndex(index,
                                          QItemSelectionModel.ClearAndSelect)
            else:
                # if no index, assume we want the project to be selected
                self.selectionModel().setCurrentIndex(
                    self.proxy_model.mapFromSource(
                    self.source_model.index(0, 0, QModelIndex())),
                    QItemSelectionModel.ClearAndSelect)
        except:
            # oops -- my C++ object probably got deleted
            pass

    def on_successful_drop(self):
        """
        Expand the currently selected node (connected to 'rowsInserted' signal,
        to expand the drop target after a new node has been created).
        """
        orb.log.info('* successful drop.')
        sdi = self.source_model.successful_drop_index
        if sdi:
            mapped_sdi = self.proxy_model.mapFromSource(sdi)
            self.expand(mapped_sdi)
        self.proxy_model.sort(0)

    def expand_project(self):
        """
        Expand the Project node (top node)
        """
        self.expand(self.proxy_model.mapFromSource(
                    self.source_model.index(0, 0, QModelIndex())))

    def create_actions(self):
        self.pgxnobj_action = QAction('View this object', self)
        self.pgxnobj_action.triggered.connect(self.display_object)
        mod_node_txt = 'Modify quantity and/or reference designator'
        self.mod_node_action = QAction(mod_node_txt, self)
        self.mod_node_action.triggered.connect(self.modify_node)
        self.del_component_action = QAction('Remove this component',
                                                      self)
        self.del_component_action.triggered.connect(self.del_component)
        self.del_position_action = QAction('Remove this assembly position',
                                           self)
        self.del_position_action.triggered.connect(self.del_position)

    def display_object(self):
        if len(self.selectedIndexes()) == 1:
            i = self.selectedIndexes()[0]
            mapped_i = self.proxy_model.mapToSource(i)
            obj = self.source_model.get_node(mapped_i).obj
            dlg = PgxnObject(obj, parent=self)
            dlg.show()

    def modify_node(self):
        """
        For the selected node, edit the 'quantity' and [1] if an Acu object,
        the 'reference_designator' attribute or [2] if a ProjectSystemUsage
        object, the 'system_role' attribute.
        """
        orb.log.info('* SystemTreeView: modify_node() ...')
        for i in self.selectedIndexes():
            mapped_i = self.proxy_model.mapToSource(i)
            node = self.source_model.get_node(mapped_i)
            rel_obj = node.link
            if rel_obj.__class__.__name__ == 'Acu':
                orb.log.info('  editing assembly node ...')
                ref_des = rel_obj.reference_designator
                quantity = rel_obj.quantity
                system = False
            elif rel_obj.__class__.__name__ == 'ProjectSystemUsage':
                orb.log.info('  editing project system node ...')
                ref_des = rel_obj.system_role
                quantity = None
                system = True
            else:
                return
            dlg = AssemblyNodeDialog(ref_des, quantity, system=system)
            if dlg.exec_() == QDialog.Accepted:
                if rel_obj.__class__.__name__ == 'Acu':
                    rel_obj.reference_designator = dlg.ref_des
                    rel_obj.quantity = dlg.quantity
                else:
                    rel_obj.system_role = dlg.ref_des
                orb.save([rel_obj])
                dispatcher.send('modified object', obj=rel_obj)

    def del_component(self):
        """
        Remove a component from an assembly position (a node in the system
        tree), replacing it with the `TBD` object.
        """
        orb.log.info('* SystemTreeView: del_component() ...')
        for i in self.selectedIndexes():
            mapped_i = self.proxy_model.mapToSource(i)
            node = self.source_model.get_node(mapped_i)
            if node.cname == 'Project':
                orb.log.info('  project node, no action taken.')
                QMessageBox.critical(self, 'Project node',
                    'Project node cannot be removed')
                return
            if node.link.__class__.__name__ == 'Acu':
                # replace component with special "TBD" product
                orb.log.info('  deleting component "%s" ...'
                             % node.link.component.id)
                if (not node.link.product_type_hint and
                    node.link.component.product_type):
                    pt = node.link.component.product_type
                    node.link.product_type_hint = pt
                tbd = orb.get('pgefobjects:TBD')
                self.source_model.setData(mapped_i, tbd)
                dispatcher.send('modified object', obj=node.link)
            elif node.link.__class__.__name__ == 'ProjectSystemUsage':
                orb.log.info('  deleting system usage "%s" ...' % node.obj.id)
                # replace system with special "TBD" product
                orb.log.info('  deleting system "%s" ...'
                             % node.link.system.id)
                tbd = orb.get('pgefobjects:TBD')
                self.source_model.setData(mapped_i, tbd)
                dispatcher.send('modified object', obj=node.link)

    def del_position(self):
        """
        Delete an assembly position (a node in the system tree).
        """
        orb.log.info('* SystemTreeView: del_position() ...')
        for i in self.selectedIndexes():
            mapped_i = self.proxy_model.mapToSource(i)
            node = self.source_model.get_node(mapped_i)
            if node.cname == 'Project':
                orb.log.info('  project node, no action taken.')
                QMessageBox.critical(self, 'Project node',
                    'Project node cannot be removed')
                return
            # NOTE: probably don't need to collapse node now that we are using
            # removeRow() / removeRows()
            # collapse the node before removing it
            # self.collapse(mapped_i)
            if node.link.__class__.__name__ == 'Acu':
                ref_des = getattr(node.link, 'reference_designator',
                                  '(No reference designator)')
                orb.log.info('  deleting position and component "%s"'
                             % ref_des)
            elif node.link.__class__.__name__ == 'ProjectSystemUsage':
                orb.log.info('  deleting system usage "%s" ...' % node.obj.id)
            pos = mapped_i.row()
            row_parent = mapped_i.parent()
            parent_id = self.source_model.get_node(row_parent).obj.id
            orb.log.info('  at row {} of parent {}'.format(pos, parent_id))
            # NOTE:  removeRow() dispatches the "deleted object" signal,
            # which triggers the "deleted" remote message to be published
            self.source_model.removeRow(pos, row_parent)

    def setup_context_menu(self):
        self.addAction(self.pgxnobj_action)
        self.addAction(self.mod_node_action)
        self.addAction(self.del_component_action)
        self.addAction(self.del_position_action)
        self.setContextMenuPolicy(Qt.ActionsContextMenu)

    # FIXME:  this probably doesn't work any more -- needs to map indexes ...
    def link_indexes_in_tree(self, link):
        """
        Find the indexes of all nodes in the system tree that reference the
        specified link (Acu or ProjectSystemUsage) -- this is needed for
        updating the tree in-place when a link object is modified.

        Args:
            link (Acu or ProjectSystemUsage):  specified link object
        """
        orb.log.info('* link_indexes_in_tree({})'.format(link.id))
        model = self.source_model
        project_index = model.index(0, 0, QModelIndex())
        project_node = model.get_node(project_index)
        orb.log.info('  for project {}'.format(project_node.obj.oid))
        orb.log.info('  (node cname: {})'.format(project_node.cname))
        # first check whether link is a PSU:
        is_a_psu = [psu for psu in model.project.systems
                    if psu.oid == link.oid]
        # then check whether link occurs in any system boms:
        systems = [psu.system for psu in model.project.systems]
        in_system = [sys for sys in systems if link in get_assembly(sys)]
        if is_a_psu or in_system:
            # systems exist -> project_index has children, so ...
            sys_idxs = [model.index(row, 0, project_index)
                        for row in range(model.rowCount(project_index))]
            link_idxs = []
            if is_a_psu:
                orb.log.debug('  - link is a ProjectSystemUsage ...')
                # orb.log.debug('    project has {} system(s).'.format(
                                                            # len(systems)))
                # orb.log.debug('    tree has {} system(s).'.format(
                                                            # len(sys_idxs)))
                for idx in sys_idxs:
                    system_node = model.get_node(idx)
                    if system_node.link.oid == link.oid:
                        orb.log.debug('    + {}'.format(system_node.link.id))
                        orb.log.debug('      system: {}'.format(
                                                        system_node.obj.id))
                        link_idxs.append(idx)
                orb.log.debug('    {} system occurrences found.'.format(
                              len(link_idxs)))
            if in_system:
                orb.log.debug('  - link is an Acu ...')
                for sys_idx in sys_idxs:
                    link_idxs += self.link_indexes_in_assembly(link, sys_idx)
                orb.log.debug('    {} link occurrences found.'.format(
                              len(link_idxs)))
            return list(set(link_idxs))
        else:
            orb.log.info('  - link not found in tree.')
        return []

    # FIXME:  this probably doesn't work any more -- needs to map indexes ...
    def object_indexes_in_tree(self, obj):
        """
        Find the indexes of all nodes in the system tree that reference the
        specified object (this is needed for updating the tree in-place when an
        object is modified).

        Args:
            obj (Product):  specified object
        """
        orb.log.info('* object_indexes_in_tree({})'.format(obj.id))
        model = self.source_model
        project_index = model.index(0, 0, QModelIndex())
        project_node = model.get_node(project_index)
        orb.log.info('  for project {}'.format(project_node.obj.oid))
        orb.log.info('  (node cname: {})'.format(project_node.cname))
        systems = [psu.system for psu in model.project.systems]
        # first check whether obj *is* one of the systems:
        is_a_system = [sys for sys in systems if sys.oid == obj.oid]
        # then check whether obj occurs in any system boms:
        in_system = [sys for sys in systems if obj.oid in get_bom_oids(sys)]
        if is_a_system or in_system:
            # systems exist -> project_index has children, so ...
            sys_idxs = [model.index(row, 0, project_index)
                        for row in range(model.rowCount(project_index))]
            system_idxs = []
            obj_idxs = []
            if is_a_system:
                orb.log.debug('  - object is a system.')
                orb.log.debug('    project has {} system(s).'.format(
                                                            len(systems)))
                orb.log.debug('    tree has {} system(s).'.format(
                                                            len(sys_idxs)))
                for idx in sys_idxs:
                    system_node = model.get_node(idx)
                    orb.log.debug('    + {}'.format(system_node.obj.id))
                    if system_node.obj.oid == obj.oid:
                        system_idxs.append(idx)
                orb.log.debug('    {} system occurrences found.'.format(
                              len(system_idxs)))
            if in_system:
                orb.log.debug('  - object is a component.')
                for sys_idx in sys_idxs:
                    obj_idxs += self.object_indexes_in_assembly(obj, sys_idx)
                orb.log.debug('    {} component occurrences found.'.format(
                              len(obj_idxs)))
            return list(set(system_idxs + obj_idxs))
        else:
            orb.log.info('  - object not found in tree.')
        return []

    # FIXME:  this probably doesn't work any more -- needs to map indexes ...
    def object_indexes_in_assembly(self, obj, idx):
        """
        Find the indexes of all nodes in an assembly that reference the
        specified object.

        Args:
            obj (Product):  specified object
            idx (QModelIndex):  index of the assembly or project node
        """
        model = self.source_model
        assembly_node = model.get_node(idx)
        if hasattr(assembly_node.link, 'component'):
            assembly = assembly_node.link.component
        else:
            assembly = assembly_node.link.system
        orb.log.info('* object_indexes_in_assembly({})'.format(assembly.id))
        if obj.oid == assembly.oid:
            orb.log.debug('  assembly *is* the object')
            return [idx]
        elif model.hasChildren(idx) and obj.oid in get_bom_oids(assembly):
            orb.log.debug('  obj in assembly bom -- looking for children ...')
            obj_idxs = []
            comp_idxs = [model.index(row, 0, idx)
                         for row in range(model.rowCount(idx))]
            for comp_idx in comp_idxs:
                obj_idxs += self.object_indexes_in_assembly(obj, comp_idx)
            return obj_idxs
        else:
            return []

    # FIXME:  this probably doesn't work any more -- needs to map indexes ...
    def link_indexes_in_assembly(self, link, idx):
        """
        Find the indexes of all nodes in an assembly that have the specified
        link as their `link` attribute.

        Args:
            link (Acu):  specified link
            idx (QModelIndex):  index of the assembly or project node
        """
        if link:
            model = self.source_model
            assembly_node = model.get_node(idx)
            if hasattr(assembly_node.link, 'component'):
                assembly = assembly_node.link.component
            else:
                assembly = assembly_node.link.system
            orb.log.info('* link_indexes_in_assembly({})'.format(link.id))
            if link.oid == assembly_node.link.oid:
                orb.log.debug('  assembly node *is* the link node')
                return [idx]
            elif model.hasChildren(idx) and link in get_assembly(assembly):
                orb.log.debug('  link in assembly -- looking for acus ...')
                link_idxs = []
                comp_idxs = [model.index(row, 0, idx)
                             for row in range(model.rowCount(idx))]
                for comp_idx in comp_idxs:
                    link_idxs += self.link_indexes_in_assembly(link, comp_idx)
                return link_idxs
            return []
        return []

#---------------------------------------------------------------
# Test/Prototyping script code ...
# [commented out until there is time to implement a side-by-side
# frame for tree and parts library to show dnd functions]
#---------------------------------------------------------------

# class MainForm(QMainWindow):
    # def __init__(self, obj, parent=None):
        # super(MainForm, self).__init__(parent)
        # self.view = SystemTreeView(obj, parent=self)
        # self.setCentralWidget(self.view)


# def main(app_home):
    # app = QApplication(sys.argv)
    # orb.start(home=app_home)
    # h2g2 = orb.get('project:H2G2')
    # if not h2g2:
        # orb.load_test_objects()
        # h2g2 = orb.get('project:H2G2')
    # tree = SystemTreeView(h2g2)
    # form = MainForm()
    # form.show()
    # sys.exit(app.exec_())

# if __name__ == '__main__':
    # app_home = sys.argv[1]
    # main(app_home)

