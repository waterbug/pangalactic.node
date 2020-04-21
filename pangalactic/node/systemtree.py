"""
System Tree view and models
"""
import re, traceback
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
from pangalactic.core.access      import get_perms
from pangalactic.core.parametrics import (de_defz, get_dval_as_str, get_pval,
                                          get_pval_as_str, parm_defz)
from pangalactic.core.uberorb     import orb
from pangalactic.core.utils.datetimes import dtstamp
from pangalactic.core.validation  import get_assembly, get_bom_oids
from pangalactic.core.units       import in_si
from pangalactic.core.utils.meta  import (get_display_name, get_acu_id,
                                          get_acu_name, get_next_ref_des)
from pangalactic.node.dialogs     import AssemblyNodeDialog
from pangalactic.node.pgxnobject  import PgxnObject
# from pangalactic.node.utils      import HTMLDelegate
from pangalactic.node.utils       import (clone, create_mime_data,
                                          extract_mime_content, get_pixmap)


class Node(object):

    def __init__(self, obj, link=None, refdes=True, parent=None, *args,
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
                designator or the component type in the node name
            parent (Node):  the Node's parent Node
        """
        super().__init__(*args, **kwargs)
        self._obj = obj
        self.link = link
        self.refdes = refdes
        # TODO:  make 'cname' a property
        self.parent = None
        self.children = []
        # if parent is not None:
            # parent.add_child(self)

    def child(self, row):
        if row < 0 or row >= len(self.children):
            return None
        return self.children[row]

    def child_count(self):
        return len(self.children)

    def row(self):
        if self.parent is not None and self in self.parent.children:
            return self.parent.children.index(self)
        return 0

    @property
    def cname(self):
        return self.obj.__class__.__name__

    @property
    def obj(self):
        return self._obj

    @obj.setter
    def obj(self, value):
        # orb.log.debug('* Node.obj.setter: set obj {}'.format(
                                            # getattr(value, 'id', 'unknown')))
        self._obj = value
        if self.link:
            if self.link.__class__.__name__ == 'Acu':
                self.link.component = value
            elif self.link.__class__.__name__ == 'ProjectSystemUsage':
                self.link.system = value
            # this modifies the existing link with new 'system' or 'component'
            self.link.mod_datetime = dtstamp()
            self.link.modifier = orb.get(state.get('local_user_oid'))
            orb.save([self.link])
            # "modified object" signal is sent by the drop event when object is
            # created or modified by a local action (a drop)
        else:
            # orb.log.debug('  - ERROR: node has no link.')
            return

    @property
    def name(self):
        """
        Return the node "name" (displayed as its label in the tree).
        """
        obj_name = get_display_name(self.obj)
        pth_name = ''
        pth_abbr = ''
        pt_name = ''
        pt_abbr = ''
        link = self.link
        if getattr(link, 'product_type_hint', None):
            pth_abbr = getattr(link.product_type_hint, 'abbreviation', '')
            pth_name = getattr(link.product_type_hint, 'name', '')
        if obj_name == 'TBD':
            if isinstance(link, orb.classes['Acu']):
                if self.refdes and link.reference_designator:
                    return '[{}] [TBD]'.format(link.reference_designator)
                else:
                    pth = pth_abbr or pth_name or '[unknown type]'
                    return '[{}] [TBD]'.format(pth)
        if getattr(link, 'system_role', None):
            # link is ProjectSystemUsage ...
            return '[{}] {}'.format(link.system_role, obj_name)
        else:
            if getattr(self.obj, 'product_type', None):
                pt_abbr = self.obj.product_type.abbreviation
                pt_name = self.obj.product_type.name
            pt = pth_abbr or pt_abbr or pth_name or pt_name
            refdes = getattr(link, 'reference_designator', None)
            if getattr(link, 'component', None) == self.obj:
                if (hasattr(link, 'quantity')
                    and link.quantity is not None
                    and link.quantity > 1):
                    if refdes and self.refdes:
                        return '[{}] {} ({})'.format(refdes, obj_name,
                                                str(link.quantity))
                    elif pt:
                        return '[{}] {} ({})'.format(pt, obj_name,
                                                str(link.quantity))
                    else:
                        return '{} ({})'.format(obj_name,
                                                str(link.quantity))
                else:
                    if refdes and self.refdes:
                        return '[{}] {}'.format(refdes, obj_name)
                    elif pt:
                        return '[{}] {}'.format(pt, obj_name)
            return obj_name

    @property
    def tooltip(self):
        if not self.refdes:
            return self.obj.name or self.obj.id or 'unidentified'
        else:
            if (self.link and
                ((getattr(self.link, 'component', None) == self.obj)
                 or (getattr(self.link, 'system', None) == self.obj))):
                if getattr(self.link, 'reference_designator', None):
                    return (self.link.reference_designator + ' : '
                            + (self.obj.name or 'Unnamed'))
                elif hasattr(self.link, 'system_role'):
                    return ((self.link.system_role or 'System') + ' : '
                            + (self.obj.name or 'Unnamed'))
                else:
                    return self.obj.name or 'Unnamed'
            else:
                return self.obj.name or 'Unnamed'

    @property
    def is_traversed(self):
        if self.cname == 'FakeRoot':
            return True
        elif isinstance(self.obj, orb.classes['Product']):
            return self.child_count() == len(self.obj.components)
        elif self.cname == 'Project':
            return self.child_count() == len(self.obj.systems)
        return True

    @property
    def is_branch_node(self):
        if self.cname == 'FakeRoot':
            return True
        elif isinstance(self.obj, orb.classes['Product']):
            return bool(self.obj.components)
        elif isinstance(self.obj, orb.classes['Project']):
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

    @property
    def cols(self):
        return self.sourceModel().cols

    @property
    def col_defs(self):
        return self.sourceModel().col_defs

    def __init__(self, source_model, parent=None):
        super().__init__(parent=parent)
        self.setSourceModel(source_model)

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
    TRANSPARENT_BRUSH = QBrush(Qt.transparent)
    WHITE_BRUSH = QBrush(Qt.white)

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
        orb.log.debug('* SystemTreeModel initializing ...')
        super().__init__(parent=parent)
        self.parent = parent
        self.refdes = refdes
        self.show_allocs = show_allocs
        self.req = req
        fake_root = FakeRoot()
        self.root = Node(fake_root)
        self.root.parent = None
        self.object_nodes = {}
        self._cols = []
        if obj is None:
            # create a "null" Project
            Project = orb.classes['Project']
            obj = Project(oid='No Project', id='No Project', name='No Project')
        self.project = obj
        top_node = self.node_for_object(obj, self.root)
        self.root.children = [top_node]
        self.successful_drop_index = None

    @property
    def dash_name(self):
        return state.get('dashboard_name', 'MEL')

    def get_cols(self):
        self._cols = prefs.get('dashboards', {}).get(self.dash_name, [])[:]
        return self._cols

    def set_cols(self, columns):
        prefs['dashboards'][self.dash_name] = columns[:]
        self._cols = prefs['dashboards'][self.dash_name]

    def del_cols(self):
        pass

    cols = property(get_cols, set_cols, del_cols, 'cols')

    def col_def(self, pid):
        pd = parm_defz.get(pid)
        if pd:
            description = pd['description']
        else:
            # it's a data element (we hope)
            de_def = de_defz.get(pid)
            if de_def:
                description = de_def['description']
            else:
                # oops, got nothin'
                log_msg = 'nothing found for id "{}"'.format(pid)
                orb.log.debug('* col_def: {}'.format(log_msg))
                return ''
        return '\n'.join(wrap(description, width=30,
                              break_long_words=False))

    @property
    def col_defs(self):
        return [self.col_def(pid) for pid in self.cols]

    def get_header(self, pid):
        pd = parm_defz.get(pid)
        if pd:
            units = prefs['units'].get(pd['dimensions'], '') or in_si.get(
                                                    pd['dimensions'], '')
            if units:
                units = '(' + units + ')'
            return '   \n   '.join(wrap(pd['name'], width=7,
                                   break_long_words=False) + [units])
        else:
            de_def = de_defz.get(pid, '')
            if de_def:
                return '   \n   '.join(wrap(de_def['name'], width=7,
                                       break_long_words=False))
            else:
                log_msg = 'nothing found for id "{}"'.format(pid)
                orb.log.debug('  - get_header: {}'.format(log_msg))
                return 'Unknown'

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
        if node.is_branch_node:
            if getattr(node.obj, 'components', None):
                # -> this is a Product node and it has acus
                return bool(len(node.obj.components) > len(node.children))
            elif node.cname == 'Project':
                return bool(len(node.obj.systems) > len(node.children))
            else:
                return False
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
        links = set([child.link for child in pnode.children])
        # if hasattr(pnode.obj, 'components'):
        if getattr(pnode.obj, 'components', None):
            # -> this is a Product node and it has acus
            # NOTE: "if acu.component" is needed in case Acu has been corrupted
            # (e.g. if its 'component' object is None)
            acus = set([acu for acu in pnode.obj.components if acu.component])
            new_acus = acus - links
            if new_acus:
                for acu in new_acus:
                    comp_node = self.node_for_object(acu.component, pnode,
                                                     link=acu)
                    nodes.append(comp_node)
                    dispatcher.send('tree node fetched')
        elif pnode.cname == 'Project':
            # -> this is a Project node
            psus = set([psu for psu in pnode.obj.systems if psu.system])
            new_psus = psus - links
            # NOTE: "if psu.system" is needed in case psu has been corrupted
            # (e.g. if its 'system' object is None)
            if new_psus:
                for psu in new_psus:
                    sys_node = self.node_for_object(psu.system, pnode,
                                                    link=psu)
                    nodes.append(sys_node)
                    dispatcher.send('tree node fetched')
        # only call add_nodes if nodes are found ...
        if nodes:
            self.add_nodes(nodes, index)

    def hasChildren(self, index):
        """
        Return True for assembly nodes so that Qt knows to check if there is
        more to load
        """
        node = self.get_node(index)
        if node.is_branch_node:
            return True
        return super().hasChildren(index)

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

    def columnCount(self, parent=QModelIndex()):
        """
        Return number of columns in the tree (for an assembly tree, it is 1;
        for a dashboard tree, the number of columns depends on the number of
        parameters being displayed).

        Keyword Args:
            index (QModelIndex):  this argument is required by the
                method in QAbstractItemView, but it is ignored in this
                implementation because the number of columns is the same for
                all nodes in the tree
        """
        if self.cols:
            return len(self.cols) + 1
        else:
            return 1

    def removeColumn(self, position, parent=QModelIndex()):
        orb.log.debug('* removeColumn({})'.format(position))
        self.beginRemoveColumns(parent, position, position)
        success = True
        if position < 0 or position >= len(self.cols):
            success = False
        dashboard_name = state.get('dashboard_name', 'MEL')
        pid = self.cols[position]
        prefs['dashboards'][dashboard_name].remove(pid)
        s = 'prefs["dashboards"]["{}"]'.format(dashboard_name)
        log_msg = '  - column "{}" removed from {}'
        orb.log.debug(log_msg.format(pid, s))
        orb.log.debug('    self.cols is now: "{}"'.format(str(self.cols)))
        self.endRemoveColumns()
        return success

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
            # MODIFIED 4/3/19:  new parameter paradigm .................
            # "descriptive" parameters (specs) apply to components/subsystems;
            # "prescriptive" parameters (requirements) apply to assembly
            # points/roles (i.e. node.link)
            # MODIFIED 4/8/20:  new data element / parameter paradigm ......
            # some columns are data elements, some are parameters ...
            if self.cols:
                if node.obj.__class__.__name__ == 'Project':
                    if index.column() == 0:
                        return node.obj.id
                    else:
                        return ''
                else:
                    if index.column() == 0:
                        return node.name
                    elif len(self.cols) >= index.column() > 0:
                        col_id = self.cols[index.column()-1]
                        pd = parm_defz.get(col_id)
                        if pd:
                            # it's a parameter
                            pid = col_id
                            units = prefs['units'].get(pd['dimensions'])
                            # descriptive parameters apply to node objects
                            # (components or subsystems)
                            if pd['context_type'] == 'descriptive':
                                oid = getattr(node.obj, 'oid', None)
                                if oid and oid != 'pgefobjects:TBD':
                                    return get_pval_as_str(node.obj.oid,
                                                           pid, units=units)
                                else:
                                    return '-'
                            # prescriptive parameters apply to node links
                            # (assembly nodes -> component/subsystem roles)
                            elif pd['context_type'] == 'prescriptive':
                                oid = getattr(node.link, 'oid', None)
                                if oid:
                                    return get_pval_as_str(oid, pid,
                                                           units=units)
                                else:
                                    return '-'
                            else:
                                # base parameter (no context)
                                return get_pval_as_str(node.obj.oid,
                                                       col_id)
                        else:
                            # it's a data element (we hope :)
                            return get_dval_as_str(node.obj.oid, col_id)
                    else:
                        return node.name
            else:
                return node.name
        if role == Qt.ForegroundRole:
            if index.column() == 0:
                return self.BRUSH
            elif self.cols and len(self.cols) >= index.column() > 0:
                col_id = self.cols[index.column()-1]
                pd = parm_defz.get(col_id)
                if pd:
                    if pd['context_type'] == 'descriptive':
                        pval = get_pval(node.obj.oid,
                                        self.cols[index.column()-1])
                    elif pd['context_type'] == 'prescriptive':
                        oid = getattr(node.link, 'oid', None)
                        if oid:
                            pval = get_pval(node.link.oid,
                                            self.cols[index.column()-1])
                        else:
                            pval = '-'
                    else:
                        # base parameter (no context)
                        pval = get_pval(node.obj.oid,
                                        self.cols[index.column()-1])
                    if isinstance(pval, (int, float)) and pval <= 0:
                        return self.RED_BRUSH
                    else:
                        return self.BRUSH
                else:
                    # data element, not a parameter
                    return self.BRUSH
            else:
                return self.BRUSH
        if role == Qt.BackgroundRole and self.req and self.show_allocs:
            # in case node.link is an Acu:
            allocs = getattr(node.link, 'allocated_requirements', [])
            # in case node.link is a ProjectSystemUsage:
            srs = getattr(node.link, 'system_requirements', [])
            if self.req in allocs or self.req in srs:
                return self.YELLOW_BRUSH
            else:
                return self.WHITE_BRUSH
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
                # ** NOTE: DO NOT dispatch "modified object" because this
                # action may have been initiated by a remote event
                node.obj = value
                # signal the views that data has changed
                self.dataChanged.emit(index, index)
                return True
        return False

    def headerData(self, section, orientation, role):
        if (orientation == Qt.Horizontal and
            role == Qt.DisplayRole):
            if self.cols and len(self.cols) > section-1:
                if section == 0:
                    return QVariant('System')
                else:
                    return QVariant(self.get_header(self.cols[section-1]))
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
        # NOTE:  systemtree may not accept drops in the future
        return ['application/x-pgef-hardware-product']

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
            1: drop target is "TBD" -> replace it if drop item is a Product
               and matches the "product_type_hint" of the Acu
            2: drop target is a normal Product -> add a new component position
               with the dropped item as the new component
            3: drop target is a Project ->
               if drop item is a Product *and* it is not already in use
               on the Project, use it to create a new ProjectSystemUsage
        """
        # orb.log.debug('* SystemTreeModel.dropMimeData()')
        try:
            # NOTE: for now, dropped item must be a HardwareProduct ... in the
            # future, may accomodate *ANY* Product subclass (including Model,
            # Document, etc.)
            drop_target = self.data(parent, Qt.UserRole)
            if not drop_target or not hasattr(drop_target, 'oid'):
                # orb.log.debug('  - drop ignored -- invalid drop target.')
                return False
            if data.hasFormat("application/x-pgef-hardware-product"):
                self.successful_drop_index = None
                content = extract_mime_content(data,
                                        "application/x-pgef-hardware-product")
                icon, obj_oid, obj_id, obj_name, obj_cname = content
                dropped_item = orb.get(obj_oid)
                # orb.log.debug('  - item dropped: %s' % (dropped_item.name))
                if drop_target.oid == obj_oid:
                    # orb.log.debug('    invalid: dropped item same as target.')
                    popup = QMessageBox(
                                QMessageBox.Critical,
                                "Assembly same as Component",
                                "A product cannot be a component of itself.",
                                QMessageBox.Ok, self.parent)
                    popup.show()
                    return False
                # orb.log.debug('  - action: {}'.format(action))
                # orb.log.debug('  - row: {}'.format(row))
                # orb.log.debug('  - column: {}'.format(column))
                # orb.log.debug('  - target name: {}'.format(drop_target.name))
                target_cname = drop_target.__class__.__name__
                if issubclass(orb.classes[target_cname],
                              orb.classes['Product']):
                    # orb.log.debug('    + target is a subclass of Product ...')
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
                        # avoid cycles:  check if the assembly is in the bom
                        if (hasattr(node.link, 'assembly') and
                            (getattr(node.link.assembly, 'oid', '')
                             in bom_oids)):
                            # dropped item would cause a cycle -> abort
                            txt = "Product cannot be used in its own assembly."
                            popup = QMessageBox(
                                        QMessageBox.Critical,
                                        "Prohibited Operation", txt,
                                        QMessageBox.Ok, self.parent)
                            popup.show()
                            return False
                        if not 'modify' in get_perms(node.link):
                            txt = "User's roles do not permit this operation"
                            ret = QMessageBox.critical(
                                      self.parent,
                                      "Unauthorized Operation", txt,
                                      QMessageBox.Ok)
                            if ret == QMessageBox.Ok:
                                return False
                        # use dropped item if (1) its product_type is the same as
                        # acu's "product_type_hint" or (2) position is any
                        # project-level system usage
                        pt = dropped_item.product_type
                        # NOTE that hint will be None for a PSU
                        hint = getattr(node.link, 'product_type_hint', None)
                        # TODO:  check for "Generic" hint
                        if hint and pt != hint:
                            # ret = QMessageBox.warning(
                            ret = QMessageBox.critical(
                                        self.parent, "Product Type Check",
                                        "The product you dropped is not a "
                                        "{}.".format(hint.name),
                                        QMessageBox.Cancel)
                            if ret == QMessageBox.Cancel:
                                return False
                        else:
                            if hasattr(node.link, 'product_type_hint'):
                                # if target is a TBD and its Acu didn't have a
                                # product_type_hint, to does now!
                                pt = dropped_item.product_type
                                node.link.product_type_hint = pt
                            # NOTE: orb.save([node.link]) is called by Node
                            # obj setter
                            node.obj = dropped_item
                            self.dataChanged.emit(parent, parent)
                            self.successful_drop.emit()
                            # orb.log.debug('   node link mod: {}'.format(
                                          # node.link.name))
                            dispatcher.send('modified object',
                                            obj=node.link)
                            if hasattr(node.link, 'assembly'):
                                # Acu modified -> assembly is modified
                                node.link.assembly.mod_datetime = dtstamp()
                                node.link.assembly.modifier = orb.get(state.get(
                                                                'local_user_oid'))
                                orb.save([node.link.assembly])
                                dispatcher.send('modified object',
                                                obj=node.link.assembly)
                            return True
                    else:
                        # case 2: drop target is normal product -> add new Acu
                        if not 'modify' in get_perms(drop_target):
                            popup = QMessageBox(
                                  QMessageBox.Critical,
                                  "Unauthorized Operation",
                                  "User's roles do not permit this operation",
                                  QMessageBox.Ok, self.parent)
                            popup.show()
                            return False
                        else:
                            # orb.log.debug('      creating Acu ...')
                            # generate a new reference_designator
                            ref_des = get_next_ref_des(drop_target,
                                                       dropped_item)
                            new_acu = clone('Acu',
                                id=get_acu_id(drop_target.id, ref_des),
                                name=get_acu_name(drop_target.name, ref_des),
                                assembly=drop_target,
                                component=dropped_item,
                                product_type_hint=dropped_item.product_type,
                                reference_designator=ref_des)
                            orb.save([new_acu])
                            # orb.log.debug('      Acu created: {}'.format(
                                          # new_acu.name))
                            self.add_nodes([self.node_for_object(
                                            dropped_item,
                                            parent=self.get_node(parent),
                                            link=new_acu)], parent)
                            self.successful_drop_index = parent
                            self.successful_drop.emit()
                            dispatcher.send('new object', obj=new_acu)
                            # new Acu -> assembly is modified
                            drop_target.mod_datetime = dtstamp()
                            drop_target.modifier = orb.get(state.get(
                                                            'local_user_oid'))
                            orb.save([drop_target])
                            dispatcher.send('modified object', obj=drop_target)
                            return True
                elif target_cname == 'Project':
                    # case 3: drop target is a project
                    # log_txt = '+ target is a Project -- creating PSU ...'
                    # orb.log.debug('    {}'.format(log_txt))
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
                        psu_id = ('psu-' + dropped_item.id + '-' +
                                  drop_target.id)
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
                        # orb.log.debug('      ProjectSystemUsage created: %s'
                                      # % psu_name)
                        self.add_nodes([self.node_for_object(
                                   dropped_item, parent=self.get_node(parent),
                                   link=new_psu)], parent)
                        self.successful_drop_index = parent
                        self.successful_drop.emit()
                        dispatcher.send('new object', obj=new_psu)
                else:
                    # orb.log.debug('    + target is not a Project or Product '
                                  # '-- no action taken.')
                    return False
                return True
            else:
                return False
        except:
            orb.log.info('* OOPS! Something bad happened in a drop ...')
            orb.log.info(traceback.format_exc())

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
        # orb.log.debug('* SystemTreeModel.removeRows()')
        # orb.log.debug('  position: {}'.format(position))
        # orb.log.debug('  count: {}'.format(count))
        parent_node = self.get_node(parent)
        # orb.log.debug('  parent_node: {}'.format(
                                 # getattr(parent_node.obj, 'id', '[no id]')))
        self.beginRemoveRows(parent, position, position + count - 1)
        links_to_delete = []
        for pos in range(position, position + count):
            i = self.index(position, 0, parent)
            node_being_removed = self.get_node(i)
            links_to_delete.append(node_being_removed.link)
        acus_by_oid = {l.oid: l for l in links_to_delete
                       if isinstance(l, orb.classes['Acu'])}
        assembly = None
        if acus_by_oid:
            acus = list(acus_by_oid.values())
            assembly = acus[0].assembly
        # if acus_by_oid:
            # orb.log.debug('  + acus to be deleted: {}'.format(
                          # [l.id for l in links_to_delete
                           # if isinstance(l, orb.classes['Acu'])]))
        psu_oids = [l.oid for l in links_to_delete
                if isinstance(l, orb.classes['ProjectSystemUsage'])]
        # if psu_oids:
            # orb.log.debug('  + psus to be deleted: {}'.format(
                          # [l.oid for l in links_to_delete
                # if isinstance(l, orb.classes['ProjectSystemUsage'])]))
        orb.delete(links_to_delete)
        success = parent_node.remove_children(position, count)
        self.endRemoveRows()
        self.dataChanged.emit(parent, parent)
        if acus_by_oid:
            for acu_oid in acus_by_oid:
                dispatcher.send(signal="deleted object", oid=acu_oid,
                                cname='Acu')
        # Acu deleted -> assembly is modified
        if assembly:
            assembly.mod_datetime = dtstamp()
            assembly.modifier = orb.get(state.get('local_user_oid'))
            orb.save([assembly])
            dispatcher.send('modified object', obj=assembly)
        if psu_oids:
            for psu_oid in psu_oids:
                dispatcher.send(signal="deleted object", oid=psu_oid,
                                cname='ProjectSystemUsage')
        return success

    def delete_columns(self, cols=None):
        """
        Remove columns from the dashboard.

        Args:
            pids (list of str): pids of columns to delete
        """
        orb.log.debug('* delete_columns({})'.format(str(cols)))
        orb.log.debug('  - column count: {}'.format(
                                  self.columnCount(QModelIndex())))
        pids = cols or []
        for pid in pids:
            if pid in self.cols:
                position = self.cols.index(pid)
                self.removeColumn(position)
                log_msg = '  - column count: {}'
                orb.log.debug(log_msg.format(
                              self.columnCount(QModelIndex())))
            else:
                orb.log.debug('  - "{}" not in cols.'.format(pid))

    def add_nodes(self, nodes, parent=QModelIndex()):
        # orb.log.debug('* SystemTreeModel: add_nodes()')
        node = self.get_node(parent)
        position = node.child_count()
        self.beginInsertRows(parent, position, position + len(nodes) - 1)
        for child in nodes:
            node.add_child(child)
        self.endInsertRows()
        self.dataChanged.emit(parent, parent)
        self.dirty = True
        return True


class SystemTreeView(QTreeView):
    def __init__(self, obj, selected_system=None, refdes=True,
                 show_allocs=False, req=None, parent=None):
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
        super().__init__(parent)
        # NOTE: this logging is only needed for deep debugging
        # orb.log.debug('* SystemTreeView initializing with ...')
        # orb.log.debug('  - root node: "{}"'.format(obj.id))
        # if selected_system:
            # sid = selected_system.id
            # orb.log.debug('  - selected system: "{}"'.format(sid))
        # else:
            # orb.log.debug('  - no selection specified.')
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
        # (i.e., a shared model); ignore them when instantiated in req
        # allocation mode (different models -> the indexes are not valid
        # anyway!!)
        if not show_allocs:
            self.expanded.connect(self.sys_node_expanded)
            self.collapsed.connect(self.sys_node_collapsed)
            self.clicked.connect(self.sys_node_selected)
            dispatcher.connect(self.sys_node_expand, 'dash node expanded')
            dispatcher.connect(self.sys_node_collapse, 'dash node collapsed')
            dispatcher.connect(self.on_dash_node_selected,
                                                       'dash node selected')
            dispatcher.connect(self.on_diagram_go_back,
                                                       'diagram go back')
            dispatcher.connect(self.on_diagram_tree_index,
                                                       'diagram tree index')
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
        if not state['sys_trees'][self.project.id].get('expanded'):
            state['sys_trees'][self.project.id]['expanded'] = []
        # set initial node selection
        if selected_system:
            self.expandToDepth(3)
            idxs = self.object_indexes_in_tree(selected_system)
            if idxs:
                idx_to_select = self.proxy_model.mapFromSource(idxs[0])
            else:
                # orb.log.debug('    selected system is not in tree.')
                idx_to_select = self.proxy_model.mapFromSource(
                            self.source_model.index(0, 0, QModelIndex()))
        else:
            # set the initial selection to the base node index
            # orb.log.debug(' - no current selection; selecting project node.')
            idx_to_select = self.proxy_model.mapFromSource(
                                self.source_model.index(0, 0, QModelIndex()))
        self.select_initial_node(idx_to_select)

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
        if index not in state['sys_trees'][self.project.id]['expanded']:
            state['sys_trees'][self.project.id]['expanded'].append(index)
        dispatcher.send(signal='sys node expanded', index=index)

    def sys_node_collapsed(self, index):
        if index in state['sys_trees'][self.project.id]['expanded']:
            state['sys_trees'][self.project.id]['expanded'].remove(index)
        dispatcher.send(signal='sys node collapsed', index=index)

    def sys_node_selected(self, index):
        if len(self.selectedIndexes()) == 1:
            i = self.selectedIndexes()[0]
            # need to expand when selected so its children are visible in the
            # tree and can be located if there is a diagram drill-down
            self.setExpanded(i, True)
            mapped_i = self.proxy_model.mapToSource(i)
            obj = self.source_model.get_node(mapped_i).obj
            link = self.source_model.get_node(mapped_i).link
            if link and not obj:
                if isinstance(link, orb.classes['Acu']):
                    obj = link.component
                elif isinstance(link, orb.classes['ProjectSystemUsage']):
                    obj = link.system
            # orb.log.debug('- node selected ...')
            # orb.log.debug('  + row: {}'.format(mapped_i.row()))
            # orb.log.debug('  + col: {}'.format(mapped_i.column()))
            # orb.log.debug('  + obj id: {}'.format(
                          # getattr(obj, 'id', '') or 'id unknown'))
            # orb.log.debug('  + parent node obj id: {}'.format(
                # getattr(self.source_model.get_node(mapped_i.parent()).obj,
                                                         # 'id', 'fake root')))
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

    def select_initial_node(self, index=None):
        self.sys_node_select(index=index, origin='tree initialization')

    def on_dash_node_selected(self, index=None):
        self.sys_node_select(index=index, origin='dash node selected')

    def on_diagram_go_back(self, index=None):
        self.sys_node_select(index=index, origin='diagram go back')

    def on_diagram_tree_index(self, index=None):
        self.sys_node_select(index=index, origin='diagram tree index')

    def sys_node_select(self, index=None, origin=''):
        """
        Set the selected node from the specified proxy model index or the
        project node if no index is specified.

        Keyword Args:
            index (QModelIndex):  the proxy model index
            origin (str):  origin of the call
        """
        # orb.log.debug('* sys_node_select() [{}]'.format(
                                            # origin or "unknown origin"))
        # try:
        if index:
            try:
                self.selectionModel().setCurrentIndex(index,
                                          QItemSelectionModel.ClearAndSelect)
                self.expand(index)
                src_idx = self.proxy_model.mapToSource(index)
                node = self.source_model.get_node(src_idx)
                obj = node.obj
                if obj:
                    msg = '* tree node selected: "{}".'.format(obj.id)
                    orb.log.debug(msg)
                    dispatcher.send('system selected', system=obj)
                # link = node.link
                # if link:
                    # msg = '  - link selected: "{}".'.format(link.id)
                    # orb.log.debug(msg)
            except:
                # oops -- C++ object for systree got deleted
                # orb.log.debug('  - index specified but exception encountered.')
                pass
        else:
            try:
                # if no index, assume we want the project to be selected
                self.selectionModel().setCurrentIndex(
                    self.proxy_model.mapFromSource(
                        self.source_model.index(0, 0, QModelIndex())),
                    QItemSelectionModel.ClearAndSelect)
                # orb.log.debug('  - index not found; project node selected.')
            except:
                # oops -- C++ object probably got deleted
                # orb.log.debug('  - exception encountered; node not selected.')
                pass

    def on_successful_drop(self):
        """
        Expand the currently selected node (connected to 'rowsInserted' signal,
        to expand the drop target after a new node has been created).
        """
        orb.log.debug('* successful drop.')
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
            dlg = PgxnObject(obj, modal_mode=True, parent=self)
            dlg.show()

    def modify_node(self):
        """
        For the selected node, if an Acu, edit the 'quantity' and
        'reference_designator', or if a ProjectSystemUsage, the 'system_role'.
        """
        # orb.log.debug('* SystemTreeView: modify_node() ...')
        for i in self.selectedIndexes():
            mapped_i = self.proxy_model.mapToSource(i)
            node = self.source_model.get_node(mapped_i)
            rel_obj = node.link
            assembly = None
            if rel_obj.__class__.__name__ == 'Acu':
                # orb.log.debug('  modifying assembly node ...')
                ref_des = rel_obj.reference_designator
                quantity = rel_obj.quantity
                system = False
                assembly = rel_obj.assembly
            elif rel_obj.__class__.__name__ == 'ProjectSystemUsage':
                # orb.log.debug('  modifying project system node ...')
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
                # Acu modified -> assembly is modified
                if assembly:
                    assembly.mod_datetime = dtstamp()
                    assembly.modifier = orb.get(state.get(
                                                    'local_user_oid'))
                    orb.save([assembly])
                    dispatcher.send('modified object', obj=assembly)

    def del_component(self):
        """
        Remove a component from an assembly position (a node in the system
        tree), replacing it with the `TBD` object.
        """
        orb.log.debug('* SystemTreeView: del_component() ...')
        for i in self.selectedIndexes():
            mapped_i = self.proxy_model.mapToSource(i)
            node = self.source_model.get_node(mapped_i)
            if node.cname == 'Project':
                orb.log.debug('  project node, no action taken.')
                QMessageBox.critical(self, 'Project node',
                    'Project node cannot be removed')
                return
            if node.link.__class__.__name__ == 'Acu':
                if not 'modify' in get_perms(node.link):
                    ret = QMessageBox.critical(
                              self,
                              "Unauthorized Operation",
                              "User's roles do not permit this operation",
                              QMessageBox.Ok)
                    if ret == QMessageBox.Ok:
                        return False
                # replace component with special "TBD" product
                orb.log.debug('  removing component "%s" ...'
                              % node.link.component.id)
                if (not node.link.product_type_hint and
                    node.link.component.product_type):
                    pt = node.link.component.product_type
                    node.link.product_type_hint = pt
                    node.link.quantity = 1
                tbd = orb.get('pgefobjects:TBD')
                self.source_model.setData(mapped_i, tbd)
                orb.save([node.link])
                dispatcher.send('modified object', obj=node.link)
                # Acu modified -> assembly is modified
                node.link.assembly.mod_datetime = dtstamp()
                node.link.assembly.modifier = orb.get(state.get(
                                                'local_user_oid'))
                orb.save([node.link.assembly])
                dispatcher.send('modified object', obj=node.link.assembly)
            elif node.link.__class__.__name__ == 'ProjectSystemUsage':
                if not 'modify' in get_perms(node.link):
                    ret = QMessageBox.critical(
                              self,
                              "Unauthorized Operation",
                              "User's roles do not permit this operation",
                              QMessageBox.Ok)
                    if ret == QMessageBox.Ok:
                        return False
                orb.log.debug('  deleting system usage "{}" ...'.format(
                              node.obj.id))
                # replace system with special "TBD" product
                orb.log.debug('  removing system "{}" ...'.format(
                              node.link.system.id))
                orb.save([node.link])
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
                orb.log.debug('  project node, no action taken.')
                QMessageBox.critical(self, 'Project node',
                    'Project node cannot be removed')
                return
            # NOTE: probably don't need to collapse node now that we are using
            # removeRow() / removeRows()
            # collapse the node before removing it
            # self.collapse(mapped_i)
            assembly = None
            if node.link.__class__.__name__ == 'Acu':
                # permissions are determined from the assembly and user's roles
                if not 'delete' in get_perms(node.link):
                    ret = QMessageBox.critical(
                              self,
                              "Unauthorized Operation",
                              "User's roles do not permit this operation",
                              QMessageBox.Ok)
                    if ret == QMessageBox.Ok:
                        return False
                ref_des = getattr(node.link, 'reference_designator',
                                  '(No reference designator)')
                assembly = node.link.assembly
                orb.log.debug('  deleting position and component "{}"'.format(
                              ref_des))
            elif node.link.__class__.__name__ == 'ProjectSystemUsage':
                # permissions are determined from the link and user's roles
                if not 'delete' in get_perms(node.link):
                    ret = QMessageBox.critical(
                              self,
                              "Unauthorized Operation",
                              "User's roles do not permit this operation",
                              QMessageBox.Ok)
                    if ret == QMessageBox.Ok:
                        return False
                orb.log.debug('  deleting system usage "%s" ...' % node.obj.id)
            pos = mapped_i.row()
            row_parent = mapped_i.parent()
            # parent_id = self.source_model.get_node(row_parent).obj.id
            # orb.log.debug('  at row {} of parent {}'.format(pos, parent_id))
            # NOTE:  removeRow() dispatches the "deleted object" signal,
            # which triggers the "deleted" remote message to be published
            self.source_model.removeRow(pos, row_parent)
            # Acu deleted -> assembly is modified
            if assembly:
                assembly.mod_datetime = dtstamp()
                assembly.modifier = orb.get(state.get('local_user_oid'))
                orb.save([assembly])
                dispatcher.send('modified object', obj=assembly)

    def setup_context_menu(self):
        self.addAction(self.pgxnobj_action)
        self.addAction(self.mod_node_action)
        self.addAction(self.del_component_action)
        self.addAction(self.del_position_action)
        self.setContextMenuPolicy(Qt.ActionsContextMenu)

    def link_indexes_in_tree(self, link):
        """
        Find the source model indexes of all nodes in the system tree that
        reference the specified link (Acu or ProjectSystemUsage) -- this is
        needed for updating the tree in-place when a link object is modified.

        Args:
            link (Acu or ProjectSystemUsage):  specified link object
        """
        # orb.log.debug('* link_indexes_in_tree({})'.format(link.id))
        model = self.proxy_model.sourceModel()
        project_index = model.index(0, 0, QModelIndex())
        # project_node = model.get_node(project_index)
        # orb.log.debug('  for project {}'.format(project_node.obj.oid))
        # orb.log.debug('  (node cname: {})'.format(project_node.cname))
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
                # orb.log.debug('  - link is a ProjectSystemUsage ...')
                # orb.log.debug('    project has {} system(s).'.format(
                                                            # len(systems)))
                # orb.log.debug('    tree has {} system(s).'.format(
                                                            # len(sys_idxs)))
                for idx in sys_idxs:
                    system_node = model.get_node(idx)
                    if system_node.link.oid == link.oid:
                        # orb.log.debug('    + {}'.format(system_node.link.id))
                        # orb.log.debug('      system: {}'.format(
                                                        # system_node.obj.id))
                        link_idxs.append(idx)
                # orb.log.debug('    {} system occurrences found.'.format(
                              # len(link_idxs)))
            if in_system:
                # orb.log.debug('  - link is an Acu ...')
                for sys_idx in sys_idxs:
                    link_idxs += self.link_indexes_in_assembly(link, sys_idx)
                # orb.log.debug('    {} link occurrences found.'.format(
                              # len(link_idxs)))
            return link_idxs
        else:
            # orb.log.debug('  - link not found in tree.')
            return []
        return []

    def object_indexes_in_tree(self, obj):
        """
        Find the source model indexes of all nodes in the system tree that
        reference the specified object (this is needed for updating the tree
        in-place when an object is modified).

        Args:
            obj (Product):  specified object
        """
        # orb.log.debug('* object_indexes_in_tree({})'.format(obj.id))
        model = self.proxy_model.sourceModel()
        project_index = model.index(0, 0, QModelIndex())
        # project_node = model.get_node(project_index)
        # orb.log.debug('  for project {}'.format(project_node.obj.oid))
        # orb.log.debug('  (node cname: {})'.format(project_node.cname))
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
                # orb.log.debug('  - object is a system.')
                # orb.log.debug('    project has {} system(s).'.format(
                                                            # len(systems)))
                # orb.log.debug('    tree has {} system(s).'.format(
                                                            # len(sys_idxs)))
                for idx in sys_idxs:
                    system_node = model.get_node(idx)
                    # orb.log.debug('    + {}'.format(system_node.obj.id))
                    if system_node.obj.oid == obj.oid:
                        system_idxs.append(idx)
                # orb.log.debug('    {} system occurrences found.'.format(
                              # len(system_idxs)))
            if in_system:
                # orb.log.debug('  - object is a component.')
                for sys_idx in sys_idxs:
                    obj_idxs += self.object_indexes_in_assembly(obj, sys_idx)
                # orb.log.debug('    {} component occurrences found.'.format(
                              # len(obj_idxs)))
            return list(set(system_idxs + obj_idxs))
        else:
            # orb.log.info('  - object not found in tree.')
            pass
        return []

    def object_indexes_in_assembly(self, obj, idx):
        """
        Find the source model indexes of all nodes in an assembly that reference
        the specified object and source model index.

        Args:
            obj (Product):  specified object
            idx (QModelIndex):  source model index of the assembly or project
                node
        """
        # NOTE: ignore "TBD" objects
        self.expandToDepth(3)
        if getattr(obj, 'oid', '') == 'pgefobjects:TBD':
            return []
        model = self.source_model
        assembly_node = model.get_node(idx)
        if hasattr(assembly_node.link, 'component'):
            assembly = assembly_node.link.component
        else:
            assembly = assembly_node.link.system
        # orb.log.debug('* object_indexes_in_assembly({})'.format(assembly.id))
        if obj.oid == assembly.oid:
            # orb.log.debug('  assembly *is* the object')
            return [idx]
        elif model.hasChildren(idx) and obj.oid in get_bom_oids(assembly):
            # orb.log.debug('  obj in assembly bom -- look for children ...')
            obj_idxs = []
            comp_idxs = [model.index(row, 0, idx)
                         for row in range(model.rowCount(idx))]
            for comp_idx in comp_idxs:
                obj_idxs += self.object_indexes_in_assembly(obj, comp_idx)
            return obj_idxs
        else:
            return []

    def link_indexes_in_assembly(self, link, idx):
        """
        Find the source model indexes of all nodes in an assembly that have the
        specified link as their `link` attribute and the specified source model
        index.

        Args:
            link (Acu):  specified link
            idx (QModelIndex):  index of the assembly or project node
        """
        if link:
            self.expandToDepth(3)
            model = self.source_model
            assembly_node = model.get_node(idx)
            if hasattr(assembly_node.link, 'component'):
                assembly = assembly_node.link.component
            else:
                assembly = assembly_node.link.system
            # orb.log.debug('* link_indexes_in_assembly({})'.format(link.id))
            if link.oid == assembly_node.link.oid:
                # orb.log.debug('  assembly node *is* the link node')
                return [idx]
            elif model.hasChildren(idx) and link in get_assembly(assembly):
                # orb.log.debug('  link in assembly -- looking for acus ...')
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
        # super().__init__(parent)
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

