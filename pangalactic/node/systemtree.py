"""
System Tree view and models
"""
import re
from textwrap import wrap
# pydispatch
from pydispatch import dispatcher

# PyQt
from PyQt5.QtGui  import QBrush, QCursor
from PyQt5.QtCore import (pyqtSignal, Qt, QAbstractItemModel,
                          QItemSelectionModel, QModelIndex,
                          QSortFilterProxyModel, QVariant)
from PyQt5.QtWidgets import QAction, QMenu, QSizePolicy, QTreeView

# pangalactic
from pangalactic.core             import orb
from pangalactic.core             import prefs, state
from pangalactic.core.names       import get_display_name, pname_to_header
from pangalactic.core.parametrics import (de_defz, get_dval, get_dval_as_str,
                                          get_pval, get_pval_as_str, 
                                          get_modal_context, get_modal_power,
                                          parm_defz, mode_defz)
from pangalactic.core.utils.datetimes import dtstamp
from pangalactic.core.validation  import get_assembly, get_bom_oids
from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.utils       import get_pixmap


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
            local_user_obj = orb.get(state.get('local_user_oid'))
            if local_user_obj:
                self.link.modifier = local_user_obj
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
            return self.obj.id or 'unidentified'
        else:
            if (self.link and
                ((getattr(self.link, 'component', None) == self.obj)
                 or (getattr(self.link, 'system', None) == self.obj))):
                if getattr(self.link, 'reference_designator', None):
                    return (self.link.reference_designator + ' : '
                            + (self.obj.id or 'Unidentified'))
                elif hasattr(self.link, 'system_role'):
                    return ((self.link.system_role or 'System') + ' : '
                             + (self.obj.id or 'Unidentified'))
                else:
                    return self.obj.id or 'Unidentified'
            else:
                return self.obj.id or 'Unidentified'

    @property
    def is_traversed(self):
        if self.cname == 'FakeRoot':
            return True
        elif orb.is_a(self.obj, 'Product'):
            return self.child_count() == len(self.obj.components)
        elif self.cname == 'Project':
            return self.child_count() == len(self.obj.systems)
        return True

    @property
    def is_branch_node(self):
        if self.cname == 'FakeRoot':
            return True
        elif orb.is_a(self.obj, 'Product'):
            return bool(self.obj.components)
        elif orb.is_a(self.obj, 'Project'):
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

    # MODIFIED 5/12/22:  drag/drop is disabled in the system tree -- was both
    # buggy and unnecessary, now that block diagram drag/drop works
    BRUSH = QBrush()
    RED_BRUSH = QBrush(Qt.red)
    GRAY_BRUSH = QBrush(Qt.lightGray)
    DARK_GRAY_BRUSH = QBrush(Qt.darkGray)
    GREEN_BRUSH = QBrush(Qt.green)
    BLUE_BRUSH = QBrush(Qt.blue)
    CYAN_BRUSH = QBrush(Qt.cyan)
    YELLOW_BRUSH = QBrush(Qt.yellow)
    TRANSPARENT_BRUSH = QBrush(Qt.transparent)
    WHITE_BRUSH = QBrush(Qt.white)

    def __init__(self, obj, refdes=True, rqt_allocs=False, show_allocs=False,
                 rqt=None, show_mode_systems=False, parent=None):
        """
        Args:
            obj (Project): root object of the tree

        Keyword Args:
            refdes (bool):  flag indicating whether to display the reference
                designator as part of the tooltip (default: True)
            rqt_allocs (bool):  flag indicating whether the tree is being used
                in the context of linking nodes to their allocated
                requirement(s) and vice versa (default: False)
            show_allocs (bool):  flag indicating that a node should be
                highlighted in yellow if it corresponds to self.rqt
                (default: False)
            rqt (Requirement):  the requirement whose allocation should be
                highlighted if 'show_allocs' is True
            show_mode_systems (bool):  flag indicating whether to highlight
                systems selected for the Modes Table
            parent (QWidget): parent widget of the SystemTreeModel
        """
        # orb.log.debug('* SystemTreeModel initializing ...')
        super().__init__(parent=parent)
        self.parent = parent
        self.refdes = refdes
        self.rqt_allocs = rqt_allocs
        self.show_allocs = show_allocs
        self.rqt = rqt
        self.show_mode_systems = show_mode_systems
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
        # set initial state for deletions as local (if remote,
        # on_remote_deletion() will be called and will set this to True)
        self.remote_deletion = False

    @property
    def dash_name(self):
        return state.get('dashboard_name', 'MEL')

    @property
    def cols(self):
        columns = ['System']
        if self.dash_name == 'System Power Modes':
            proj_modes = (mode_defz.get(self.project.oid) or {}).get('modes')
            if proj_modes:
                columns += list(proj_modes.values())
        else:
            columns += (prefs.get('dashboards') or {}).get(self.dash_name)
        return columns

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
                # log_msg = 'nothing found for id "{}"'.format(pid)
                # orb.log.debug('* col_def: {}'.format(log_msg))
                return ''
        return '\n'.join(wrap(description, width=30,
                              break_long_words=False))

    @property
    def col_defs(self):
        data_cols = self.cols[1:]
        return [self.col_def(col_id) for col_id in data_cols]

    def get_header(self, col_id):
        if self.dash_name == 'System Power Modes':
            # col_id is an Activity name ...
            return '  \n  '.join(wrap(col_id, width=20,
                                 break_long_words=False))
        else:
            return pname_to_header(col_id, 'HardwareProduct',
                                   project_oid=self.project.oid)

    @property
    def rqt(self):
        return self._rqt

    @rqt.setter
    def rqt(self, r):
        self._rqt = r

    def node_for_object(self, obj, parent, link=None):
        """
        Return a Node instance for an object and "parent" node.  This is
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
        # NOTE:  Selectable is needed for node selection
        return (Qt.ItemIsEnabled | Qt.ItemIsSelectable)

    # def supportedDropActions(self):
        # return Qt.CopyAction | Qt.MoveAction

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
        # only call add_nodes if nodes are found ...
        if nodes:
            self.add_nodes(nodes, index)

    def populate(self, idx=None):
        """
        Fetch all children recursively.
        """
        # orb.log.debug('* populate()')
        if idx is None:
            idx = self.index(0, 0, QModelIndex())
        if self.canFetchMore(idx):
            # orb.log.debug('  fetching more ...')
            self.fetchMore(idx)
            next_idx = self.index(0, 0, idx)
            while 1:
                if self.canFetchMore(next_idx):
                    self.populate(next_idx)
                else:
                    # orb.log.debug('  done with node, breaking ...')
                    break

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
            return len(self.cols)
        else:
            return 1

    def insertColumn(self, position, parent=QModelIndex()):
        orb.log.debug('* insertColumn({})'.format(position))
        self.beginInsertColumns(parent, position, position)
        success = True
        if position < 0 or position > len(self.cols) - 1:
            success = False
        self.endInsertColumns()
        return success

    def removeColumn(self, position, parent=QModelIndex()):
        # orb.log.debug('* removeColumn({})'.format(position))
        self.beginRemoveColumns(parent, position, position)
        success = True
        if position < 0 or position > len(self.cols) - 1:
            success = False
        if position < len(self.cols):
            pid = self.cols[position]
            prefs['dashboards'][self.dash_name].remove(pid)
            s = f'prefs["dashboards"]["{self.dash_name}"]'
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
        # orb.log.debug('* SystemTreeModel.data()')
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
                    # orb.log.debug('  Project node ...')
                    if index.column() == 0:
                        return node.obj.id
                    else:
                        return ''
                elif ((self.dash_name == 'System Power Modes')
                      and mode_defz.get(self.project.oid)):
                    # orb.log.debug('  dash is "System Power Modes" ...')
                    if index.column() == 0:
                        return node.name
                    proj_mode_defz = mode_defz[self.project.oid]
                    proj_modes = proj_mode_defz.get('modes')
                    mode_oids = []
                    if proj_modes:
                        mode_oids = list(proj_modes)
                    if len(mode_oids) > index.column() > 0:
                        mode_oid = mode_oids[index.column() -1]
                        sys_usage_oid = getattr(node.link, 'oid', None)
                        oid = getattr(node.obj, 'oid', None)
                        modal_context = get_modal_context(self.project.oid,
                                                          sys_usage_oid,
                                                          mode_oid)
                        # p_cbe_val = get_modal_power(self.project.oid,
                                                    # sys_usage_oid,
                                                    # oid,
                                                    # mode_oid,
                                                    # modal_context)
                        return str(modal_context)
                    else:
                        return ''
                else:
                    if index.column() == 0:
                        return node.name
                    elif len(self.cols) > index.column() > 0:
                        col_id = self.cols[index.column()]
                        pd = parm_defz.get(col_id)
                        de_def = de_defz.get(col_id)
                        if pd:
                            units = prefs['units'].get(pd['dimensions'])
                            # it's a parameter
                            pid = col_id
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
                                                       col_id, units=units)
                        elif de_def:
                            # it's a data element (we hope :)
                            units = prefs['units'].get(
                                                de_def.get('dimensions')) or ''
                            return get_dval_as_str(node.obj.oid, col_id,
                                                   units=units)
                    else:
                        return ''
            else:
                return node.name
        if role == Qt.ForegroundRole:
            if index.column() == 0:
                if ((self.show_mode_systems or
                     self.dash_name == 'System Power Modes')
                    and mode_defz.get(self.project.oid)):
                    computed_list = mode_defz[self.project.oid].get(
                                                            'computed') or []
                    if getattr(node.link, 'oid', None) in computed_list:
                        return self.YELLOW_BRUSH
                    else:
                        return self.BRUSH
            elif self.cols and len(self.cols) > index.column() > 0:
                col_id = self.cols[index.column()]
                pd = parm_defz.get(col_id)
                de_def = de_defz.get(col_id)
                if pd:
                    if pd['context_type'] == 'descriptive':
                        pval = get_pval(node.obj.oid, col_id)
                    elif pd['context_type'] == 'prescriptive':
                        oid = getattr(node.link, 'oid', None)
                        if oid:
                            pval = get_pval(node.link.oid, col_id)
                        else:
                            pval = '-'
                    else:
                        # base parameter (no context)
                        pval = get_pval(node.obj.oid, col_id)
                    if isinstance(pval, (int, float)) and pval <= 0:
                        return self.RED_BRUSH
                    else:
                        return self.BRUSH
                elif de_def:
                    units = prefs['units'].get(de_def.get('dimensions')) or ''
                    dval = get_dval(node.obj.oid, col_id, units=units)
                    if isinstance(dval, (int, float)) and dval <= 0:
                        return self.RED_BRUSH
                    else:
                        return self.BRUSH
                elif ((self.show_mode_systems or
                     self.dash_name == 'System Power Modes')
                    and mode_defz.get(self.project.oid)):
                    computed_list = mode_defz[self.project.oid].get(
                                                            'computed') or []
                    if getattr(node.link, 'oid', None) in computed_list:
                        return self.YELLOW_BRUSH
                    else:
                        return self.BRUSH
                else:
                    return self.BRUSH
            else:
                return self.BRUSH
        if role == Qt.BackgroundRole and self.rqt and self.show_allocs:
            # in case node.link is an Acu:
            allocs = getattr(node.link, 'allocated_requirements', [])
            proj_allocs = []
            # in case node is the project node:
            if node.cname == 'Project':
                proj_allocs = getattr(node.obj, 'allocated_requirements', [])
            if self.rqt in allocs or self.rqt in proj_allocs:
                return self.YELLOW_BRUSH
            else:
                return self.WHITE_BRUSH
        elif (role == Qt.BackgroundRole
              and (self.show_mode_systems or
                   self.dash_name == 'System Power Modes')
              and mode_defz.get(self.project.oid)):
                computed_list = mode_defz[self.project.oid].get(
                                                        'computed') or []
                if getattr(node.link, 'oid', None) in computed_list:
                    return self.DARK_GRAY_BRUSH
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
            if self.cols and len(self.cols) > section:
                if section == 0:
                    return QVariant('System')
                else:
                    return QVariant(self.get_header(self.cols[section]))
            # else:
                # try:
                    # self.removeColumn(section)
                # except:
                    # pass
        elif role == Qt.ToolTipRole:
            if section == 0:
                return 'System or component identifier'
            if section <= len(self.col_defs):
                return self.col_defs[section-1]
        return QVariant()

    def on_remote_deletion(self, pos, row_parent):
        self.remote_deletion = True
        self.removeRow(pos, row_parent)

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
        orb.log.debug('* SystemTreeModel.removeRows()')
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
        if acus_by_oid:
            orb.log.debug('  + deleting Acus: {}'.format(
                          [l.id for l in links_to_delete
                           if isinstance(l, orb.classes['Acu'])]))
        psu_oids = [l.oid for l in links_to_delete
                if isinstance(l, orb.classes['ProjectSystemUsage'])]
        if psu_oids:
            orb.log.debug('  + deleting PSUs: {}'.format(
                          [l.oid for l in links_to_delete
                if isinstance(l, orb.classes['ProjectSystemUsage'])]))
        orb.delete(links_to_delete)
        success = parent_node.remove_children(position, count)
        self.endRemoveRows()
        self.dataChanged.emit(parent, parent)
        # Acu deleted -> assembly is modified
        if assembly:
            assembly.mod_datetime = dtstamp()
            assembly.modifier = orb.get(state.get('local_user_oid'))
            orb.save([assembly])
            # dispatcher.send('modified object', obj=assembly)
        return success

    def insert_column(self, element_id):
        """
        Insert a data element or parameter column at the end of the dashboard.

        Args:
            element_id (str): id of data element or parameter to insert
        """
        orb.log.debug(f'* insert_column({element_id})')
        if element_id in self.cols:
            orb.log.debug("  - we already got one, it's verra nahce.")
        else:
            prefs['dashboards'][self.dash_name].append(element_id)
            success = self.insertColumn(len(self.cols)-1)
            if success:
                orb.log.debug('  - success')
                orb.log.debug('    self.cols is now: "{}"'.format(str(self.cols)))
                log_msg = '  - column count: {}'
                orb.log.debug(log_msg.format(
                              self.columnCount(QModelIndex())))
            else:
                orb.log.debug('  - column insert failed.')

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

    obj_modified = pyqtSignal(str)     # arg: oid

    # MODIFIED 5/12/22:  drag/drop is disabled in the system tree -- was both
    # buggy and unnecessary, now that block diagram drag/drop works

    def __init__(self, obj, refdes=True, rqt_allocs=False, rqt=None,
                 parent=None):
        """
        Args:
            obj (Project or Product): root object of the tree

        Keyword Args:
            refdes (bool):  flag indicating whether to display the reference
                designator or the component name as the node name
            rqt_allocs (bool):  flag indicating whether to highlight nodes to
                which a specified requirement has been allocated
            rqt (Requirement):  the requirement whose allocation should be
                highlighted if 'rqt_allocs' is True
        """
        super().__init__(parent)
        # NOTE: this logging is only needed for deep debugging
        # orb.log.debug('* SystemTreeView initializing with ...')
        # orb.log.debug('  - root node: "{}"'.format(obj.id))
        self.rqt_allocs = rqt_allocs
        tree_model = SystemTreeModel(obj, refdes=refdes,
                                     rqt_allocs=rqt_allocs,
                                     rqt=rqt, parent=self)
        self.proxy_model = SystemTreeProxyModel(tree_model, parent=self)
        self.source_model = self.proxy_model.sourceModel()
        self.proxy_model.setDynamicSortFilter(True)
        self.setModel(self.proxy_model)
        # all rows are same height, so use this to optimize performance
        self.setUniformRowHeights(True)
        # delegate = HTMLDelegate()
        # self.setItemDelegate(delegate)
        # --------------------------------------------------------------------
        # the system tree (view) has no headers or columns ...
        # --------------------------------------------------------------------
        self.setHeaderHidden(True)
        cols = self.source_model.cols
        if cols:
            for i in range(1, len(cols)):
                self.hideColumn(i)
        if self.rqt_allocs:
            self.setSelectionMode(self.NoSelection)
        else:
            self.setSelectionMode(self.SingleSelection)
        self.create_actions()
        # only use dispatcher messages for assembly tree and dashboard tree
        # (i.e., a shared model); ignore them when instantiated in rqt
        # allocation mode (different models -> the indexes are not valid
        # anyway!)
        if rqt_allocs:
            dispatcher.connect(self.on_show_allocated_to, 'show allocated_to')
            self.clicked.connect(self.sys_node_clicked)
        else:
            self.expanded.connect(self.sys_node_expanded)
            self.collapsed.connect(self.sys_node_collapsed)
            self.clicked.connect(self.sys_node_selected)
            dispatcher.connect(self.sys_node_expand, 'dash node expanded')
            dispatcher.connect(self.sys_node_collapse, 'dash node collapsed')
            dispatcher.connect(self.on_dash_node_selected,
                                                       'dash node selected')
            dispatcher.connect(self.on_set_selected_system,
                                                       'set selected system')
            dispatcher.connect(self.on_diagram_go_back,
                                                       'diagram go back')
            dispatcher.connect(self.on_diagram_tree_index,
                                                       'diagram tree index')
            dispatcher.connect(self.on_new_diagram_block, 'new diagram block')
        self.setStyleSheet('font-weight: normal; font-size: 12px')
        self.proxy_model.sort(0)
        self.setSizePolicy(QSizePolicy.Expanding,
                           QSizePolicy.Expanding)
        self.resizeColumnToContents(0)
        self.project = self.source_model.project
        if not state.get('sys_trees'):
            state['sys_trees'] = {}
        if not state['sys_trees'].get(self.project.id):
            state['sys_trees'][self.project.id] = {}
        if not state['sys_trees'][self.project.id].get('expanded'):
            state['sys_trees'][self.project.id]['expanded'] = []

    def create_actions(self):
        self.pgxnobj_action = QAction('View or edit this object', self)
        self.pgxnobj_action.triggered.connect(self.view_object)

    def contextMenuEvent(self, event):
        orb.log.debug('* contextMenuEvent()')
        menu = QMenu()
        if len(self.selectedIndexes()) == 1:
            i = self.selectedIndexes()[0]
            mapped_i = self.proxy_model.mapToSource(i)
            # obj = self.source_model.get_node(mapped_i).obj
            # orb.log.debug(f'  obj: {obj.id}')
            link = self.source_model.get_node(mapped_i).link
            # NOTE: root node (project) has a link of None ...
            if link and isinstance(link, (orb.classes['Acu'],
                                          orb.classes['ProjectSystemUsage'])):
                # orb.log.debug(f'  usage: {link.id}')
                menu.addAction(self.pgxnobj_action)
                menu.exec_(QCursor().pos())

    @property
    def rqt(self):
        return self.source_model._rqt

    @rqt.setter
    def rqt(self, r):
        self.source_model._rqt = r
        self.dataChanged(QModelIndex(), QModelIndex())

    def on_show_allocated_to(self, item=None):
        if item:
            level = 1
            while 1:
                try:
                    self.expandToDepth(level)
                    idxs = self.link_indexes_in_tree(item)
                    if idxs:
                        self.scrollTo(self.proxy_model.mapFromSource(idxs[0]))
                        return
                    else:
                        level += 1
                        if level > 7:
                            # we have our limits! ;)
                            return
                except:
                    orb.log.debug('  on_show_allocated_to() crashed.')
                    return

    def get_node_for_index(self, index):
        """
        Get the tree node with the specified proxy model index.
        """
        # orb.log.debug('*  get_node_for_index() ...')
        i = index
        try:
            mapped_i = self.proxy_model.mapToSource(i)
            node = self.source_model.get_node(mapped_i)
            return node
        except:
            # oops -- my C++ object probably got deleted
            return None

    # NOTE: new version of "sys node expanded" signal for use with
    # MultiDashboard, which does not use the same model internally, so can't
    # use an "index" from this model ...
    def sys_node_expanded(self, index):
        # orb.log.debug('*  sys_node_expanded() ...')
        if (self.project.id in state['sys_trees'] and
            index not in state['sys_trees'][self.project.id]['expanded']):
            state['sys_trees'][self.project.id]['expanded'].append(index)
        node = self.get_node_for_index(index)
        if node:
            # orb.log.debug('- node expanded ...')
            # orb.log.debug('  + obj id: {}'.format(
                          # getattr(node.obj, 'id', '') or 'id unknown'))
            # dispatcher.send(signal='sys node expanded', index=index)
            dispatcher.send(signal='sys node expanded', obj=node.obj,
                            link=node.link)

    # NOTE: new version of "sys node collapsed" signal for use with
    # MultiDashboard, which does not use the same model internally, so can't
    # use an "index" from this model ...
    def sys_node_collapsed(self, index):
        if (self.project.id in state['sys_trees'] and
            index in state['sys_trees'][self.project.id]['expanded']):
            state['sys_trees'][self.project.id]['expanded'].remove(index)
        node = self.get_node_for_index(index)
        if node:
            dispatcher.send(signal='sys node collapsed', obj=node.obj,
                            link=node.link)

    def sys_node_selected(self, index):
        # orb.log.debug('*  sys_node_selected() ...')
        if len(self.selectedIndexes()) == 1:
            i = self.selectedIndexes()[0]
            # need to expand when selected so its children are visible in the
            # tree and can be located if there is a diagram drill-down
            self.setExpanded(i, True)
            try:
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
                    # getattr(self.source_model.get_node(
                                                    # mapped_i.parent()).obj,
                                                    # 'id', 'fake root')))
                state['system'][state['project']] = obj.oid
                # orb.log.debug(f'* sys node selected: {obj.oid}')
                dispatcher.send(signal='sys node selected', index=index,
                                obj=obj, link=link)
            except:
                # oops -- my C++ object probably got deleted
                pass

    def sys_node_clicked(self, index):
        i = index
        # need to expand when selected so its children are visible in the
        # tree and can be located if there is a diagram drill-down
        self.setExpanded(i, True)
        try:
            mapped_i = self.proxy_model.mapToSource(i)
            obj = self.source_model.get_node(mapped_i).obj
            link = self.source_model.get_node(mapped_i).link
            if link and not obj:
                if isinstance(link, orb.classes['Acu']):
                    obj = link.component
                elif isinstance(link, orb.classes['ProjectSystemUsage']):
                    obj = link.system
            orb.log.debug('- node clicked ...')
            orb.log.debug('  + obj id: {}'.format(
                          getattr(obj, 'id', '') or 'id unknown'))
            # orb.log.debug('  + parent node obj id: {}'.format(
                # getattr(self.source_model.get_node(
                                                # mapped_i.parent()).obj,
                                                # 'id', 'fake root')))
            state['system'][state['project']] = obj.oid
            orb.log.debug('  dispatching "sys node clicked"')
            dispatcher.send(signal='sys node clicked', index=index,
                            obj=obj, link=link)
        except:
            # oops -- my C++ object probably got deleted
            pass

    def sys_node_expand(self, index=None):
        # orb.log.debug('* sys_node_expand()')
        try:
            if index and not self.isExpanded(index):
                self.expand(index)
        except:
            # oops -- my C++ object probably got deleted
            pass

    def sys_node_collapse(self, index=None):
        # orb.log.debug('* sys_node_collapse()')
        try:
            if index and self.isExpanded(index):
                self.collapse(index)
        except:
            # oops -- my C++ object probably got deleted
            pass

    def on_new_diagram_block(self, acu=None):
        orb.log.debug('* systree: "new diagram block" signal received.')
        if acu:
            try:
                idxs = self.object_indexes_in_tree(acu.assembly)
            except:
                # oops, tree C++ object got destroyed
                idxs = []
            if idxs:
                orb.log.debug('  assembly found in tree, updating ...')
                for idx in idxs:
                    src_model = self.source_model
                    # pnode = src_model.get_node(src_idx)
                    # src_model.add_nodes([src_model.node_for_object(
                                         # acu.assembly, pnode, link=acu)],
                                         # src_idx)
                    src_model.fetchMore(idx)

    def on_dash_node_selected(self, index=None):
        self.sys_node_select(index=index, origin='dash node selected')

    def on_set_selected_system(self):
        # orb.log.debug('- systree: "set selected system" signal received.')
        try:
            oid = (state.get('system') or {}).get(state.get('project'))
            obj = orb.get(oid)
            proxy_idx = None
            if obj:
                idxs = self.object_indexes_in_tree(obj)
                if idxs:
                    idx = idxs[0]
                    proxy_idx = self.proxy_model.mapFromSource(idx)
            self.sys_node_select(proxy_idx)
        except:
            # orb.log.debug('  model had been destroyed.')
            pass

    def on_diagram_go_back(self, index=None):
        self.sys_node_select(index=index, origin='diagram go back')

    def on_diagram_tree_index(self, index=None):
        self.sys_node_select(index=index, origin='diagram tree index')

    def sys_node_select(self, index=None, origin=''):
        """
        Set the selected node from the specified proxy model index or the
        project node if no index is specified.  This method is *only* called
        programmatically, not bound to mouse click events, so the dispatcher
        signal "sys node selected" sent here is not redundant to the one sent
        by the 'sys_node_selected()' method, which is only activated by the
        mouse click event.

        Keyword Args:
            index (QModelIndex):  the proxy model index
            origin (str):  origin of the call
        """
        # orb.log.debug('* sys_node_select() [{}]'.format(
                                            # origin or "unknown origin"))
        if index:
            try:
                self.selectionModel().setCurrentIndex(index,
                                          QItemSelectionModel.ClearAndSelect)
                self.expand(index)
            except:
                # oops -- C++ object for systree got deleted
                # orb.log.debug('  - exception encountered.')
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
                # orb.log.debug('  - exception; node not selected.')
                pass
        dispatcher.send(signal='sys node selected', index=index)

    def expand_project(self):
        """
        Expand the Project node (top node)
        """
        self.expand(self.proxy_model.mapFromSource(
                    self.source_model.index(0, 0, QModelIndex())))

    def view_object(self):
        if len(self.selectedIndexes()) == 1:
            i = self.selectedIndexes()[0]
            mapped_i = self.proxy_model.mapToSource(i)
            obj = self.source_model.get_node(mapped_i).obj
            dlg = PgxnObject(obj, modal_mode=True, parent=self)
            dlg.obj_modified.connect(self.on_obj_modified)
            dlg.show()

    def on_obj_modified(self, oid):
        self.obj_modified.emit(oid)

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
        # ----------------------------------------------------
        # IMPORTANT: fully populate model with child nodes ...
        # ----------------------------------------------------
        model.populate()
        # first check whether link is a PSU:
        is_a_psu = [psu for psu in model.project.systems
                    if psu.oid == link.oid]
        # then check whether link occurs in any system boms:
        systems = [psu.system for psu in model.project.systems]
        in_system = [sys for sys in systems if link in get_assembly(sys)]
        if is_a_psu or in_system:
            # systems exist -> project_index has children, so ...
            child_count = model.rowCount(project_index)
            if child_count == 0:
                # orb.log.debug('  - no child nodes found.')
                return []
            sys_idxs = [model.index(row, 0, project_index)
                        for row in range(child_count)]
            if not sys_idxs:
                # orb.log.debug('  - no child indexes found.')
                return []
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
        # try:
            # model = self.proxy_model.sourceModel()
        # except:
            # oops -- C++ object probably got deleted
            # return []
        model = self.source_model
        project_index = model.index(0, 0, QModelIndex())
        # project_node = model.get_node(project_index)
        # orb.log.debug(f'  for project {project_node.obj.id}')
        # orb.log.debug(f'  (node cname: {project_node.cname})')
        # NOTE: systems could be created with a list comp except the sanity
        # check "if psu.system" is needed in case a psu got corrupted
        systems = []
        for psu in model.project.systems:
            if psu.system:
                systems.append(psu.system)
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
            return []
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
        if getattr(obj, 'oid', '') == 'pgefobjects:TBD':
            return []
        model = self.source_model
        assembly_node = model.get_node(idx)
        assembly = assembly_node.obj
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
            model = self.source_model
            assembly_node = model.get_node(idx)
            if assembly_node.link is None:
                return []
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
# [commented out for now]
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

