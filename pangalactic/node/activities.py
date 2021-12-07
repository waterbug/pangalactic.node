#!/usr/bin/env python
# -*- coding: utf-8 -*-

from louie import dispatcher

from collections import OrderedDict
from textwrap import wrap, fill

from PyQt5.QtCore    import QSize, Qt, QModelIndex, QVariant
from PyQt5.QtGui     import QBrush, QStandardItemModel
from PyQt5.QtWidgets import (QApplication, QComboBox, QDockWidget, QItemDelegate,
                             QMainWindow, QSizePolicy, QStatusBar, QTableView,
                             QTreeView, QVBoxLayout, QWidget)

from pangalactic.core             import state
from pangalactic.core.parametrics import get_pval_as_str
from pangalactic.core.utils.meta  import get_acr_id, get_acr_name
from pangalactic.core.uberorb     import orb
from pangalactic.core.validation  import get_bom_oids
from pangalactic.node.systemtree  import SystemTreeModel, SystemTreeProxyModel
from pangalactic.node.tablemodels import MappingTableModel
from pangalactic.node.utils       import clone
from pangalactic.node.widgets     import NameLabel


class ActivityTable(QWidget):
    """
    Table for displaying the sub-activities of an Activity and related data.

    Attrs:
        subject (Activity):  the Activity whose sub-activities are shown
    """
    def __init__(self, subject=None, preferred_size=None, act_of=None,
                 position=None, parent=None):
        """
        Initialize table for displaying the sub-activities of an Activity and
        related data.

        Keyword Args:
            subject (Activity):  Activity whose sub-activities are to be
                shown in the table
            preferred_size (tuple):  default size -- (width, height)
            parent (QWidget):  parent widget
            act_of (Product):  Product of which the subject is an Activity
            position (str): the table "role" of the table in the ConOps tool,
                as the "top" or "middle" table, which will determine its
                response to signals
        """
        super().__init__(parent=parent)
        orb.log.info('* ActivityTable initializing for "{}" ...'.format(
                                                            subject.name))
        self.subject = subject
        self.project = orb.get(state.get('project'))
        self.preferred_size = preferred_size
        self.position = position
        self.act_of = act_of
        self.statusbar = QStatusBar()
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)
        self.title_widget = NameLabel('')
        self.title_widget.setStyleSheet('font-weight: bold; font-size: 14px')
        self.main_layout.addWidget(self.title_widget)
        self.set_title_text()
        self.set_table()
        self.setSizePolicy(QSizePolicy.Expanding,
                           QSizePolicy.Expanding)
        dispatcher.connect(self.on_activity_added, 'new activity')
        dispatcher.connect(self.on_activity_edited, 'activity edited')
        dispatcher.connect(self.on_activity_remote_mod, 'activity remote mod')
        dispatcher.connect(self.on_activity_removed, 'removed activity')
        dispatcher.connect(self.on_order_changed, 'order changed')
        dispatcher.connect(self.on_drill_down, 'drill down')
        dispatcher.connect(self.on_drill_up, 'go back')
        dispatcher.connect(self.on_subsystem_changed, 'changed subsystem')
        dispatcher.connect(self.on_activity_focused, 'activity focused')
        dispatcher.connect(self.on_disable, 'disable widget')
        dispatcher.connect(self.on_enable, 'enable widget')
        dispatcher.connect(self.on_activities_cleared, 'cleared activities')

    def set_title_text(self):
        if not hasattr(self, 'title_widget'):
            return
        red_text = '<font color="red">{}</font>'
        blue_text = '<font color="blue">{}</font>'
        title_txt = ''
        if self.position == "top":
            txt = self.subject.name
            if self.subject.activity_type:
                txt += ' ' + self.subject_activity.activity_type.name
            txt += ': '
            title_txt = red_text.format(txt)
        # if isinstance(self.act_of, orb.classes['Product']):
        sys_name = getattr(self.act_of, 'name', '')
        title_txt += blue_text.format(sys_name) + ' '
        if self.position == "top":
            title_txt += 'Activity Details'
        elif self.position == "middle":
            title_txt += red_text.format(self.subject.name)
            title_txt += ' Details'
        self.title_widget.setText(title_txt)

    @property
    def activities(self):
        """
        The relevant sub-activities that the table will display, namely the
        sub-activities of the "subject" activity which are activities of the
        table's "act_of" Product.
        """
        subj = getattr(self, 'subject', None)
        if not subj:
            return []
        system_acrs = []
        for acr in subj.sub_activities:
            if self.act_of == acr.sub_activity.activity_of:
                system_acrs.append(acr)
        all_acrs = [(acr.sub_activity_role, acr)
                    for acr in system_acrs]
        all_acrs.sort()
        return [acr_tuple[1].sub_activity for acr_tuple in all_acrs]

    def set_table(self):
        table_cols = ['id', 'name', 't_start', 'duration', 'description']
        table_headers = dict(id='ID', name='Name',
                           t_start='Start\nTime',
                           duration='Duration',
                           description='Description')
        d_list = []
        for act in self.activities:
            obj_dict = OrderedDict()
            for col in table_cols:
                if col in orb.schemas['Activity']['field_names']:
                    str_val = getattr(act, col, '')
                    if str_val and len(str_val) > 28:
                        wrap(str_val, width=28)
                        str_val = fill(str_val, width=28)
                    obj_dict[table_headers[col]] = str_val
                else:
                    val = get_pval_as_str(act.oid, col)
                    obj_dict[table_headers[col]] = val
            d_list.append(obj_dict)
        new_model = MappingTableModel(d_list)
        new_table = QTableView()
        new_table.setModel(new_model)
        new_table.setSizePolicy(QSizePolicy.Preferred,
                                QSizePolicy.Preferred)
        new_table.setAlternatingRowColors(True)
        new_table.resizeColumnsToContents()
        if getattr(self, 'table', None):
            self.main_layout.removeWidget(self.table)
            self.table.setAttribute(Qt.WA_DeleteOnClose)
            self.table.parent = None
            self.table.close()
            self.table = None
        self.main_layout.addWidget(new_table, stretch=1)
        self.table = new_table

    def sizeHint(self):
        if self.preferred_size:
            return QSize(*self.preferred_size)
        return QSize(600, 500)

    def on_activity_edited(self, activity=None):
        txt = '* {} table: on_activity_edited()'
        orb.log.debug(txt.format(self.position))
        if getattr(activity, 'oid', None) == self.subject.oid:
            self.set_title_text()
        elif activity in self.activities:
            self.set_table()

    def on_activity_remote_mod(self, activity=None):
        txt = '* {} table: on_activity_remote_mod()'
        orb.log.debug(txt.format(self.position))
        if activity and activity.where_occurs:
            composite_activity = getattr(activity.where_occurs[0],
                                         'composite_activity', None)
            if composite_activity:
                self.on_activity_added(composite_activity=composite_activity,
                                       modified=True)

    def on_activity_added(self, composite_activity=None, modified=False,
                          act_of=None, position=None):
        txt = '* {} table: on_activity_added(modified=True)'
        orb.log.debug(txt.format(self.position))
        if self.position == position:
            if modified:
                self.statusbar.showMessage('Activity Modified!')
                orb.log.debug('  - activity mod!')
            else:
                self.statusbar.showMessage('Activity Added!')
                orb.log.debug('  - activity added!')
        self.set_table()

    def on_activity_removed(self, composite_activity=None, act_of=None,
                            position=None):
        if self.position == position or self.position == 'bottom':
            self.statusbar.showMessage('Activity Removed!')
            self.set_table()

    def on_order_changed(self, composite_activity=None, act_of=None, position=None):
        if self.position == position or self.position == 'bottom':
            self.statusbar.showMessage('Order Updated!')
            self.set_table()

    def on_drill_down(self, obj=None, position=None):
        if self.position == 'middle':
            self.statusbar.showMessage("Drilled Down!")
            self.set_table()

    def on_drill_up(self, obj=None, position=None):
        if self.position != 'middle':
            self.statusbar.showMessage("Drilled Up!")
            self.set_table()

    def on_activities_cleared(self, composite_activity=None, position=None):
        # if self.position == position or self.position == 'bottom':
        self.statusbar.showMessage("Activities Cleared!")
        self.set_table()

    def on_subsystem_changed(self, act=None, act_of=None, position=None):
        if self.position == 'top':
            self.set_table()
        if position == 'middle':
            self.statusbar.showMessage("Subsystem Changed!")
        if self.position == 'middle':
            self.setDisabled(False)
            self.act_of = act_of
            self.set_table()

    def on_activity_focused(self, act=None):
        if self.position == 'top':
            self.statusbar.showMessage("New Activity Selected")
        elif self.position == 'middle':
            self.statusbar.showMessage("Table Refreshed")
            self.subject = act
            self.set_title_text()
            self.set_table()

    def on_disable(self):
        if self.position == 'middle':
            self.setDisabled(True)

    def on_enable(self):
        if self.position == 'middle':
            self.setEnabled(True)


class SystemSelectionView(QTreeView):
    def __init__(self, obj, refdes=True, parent=None):
        """
        Args:
            obj (Project or Product): root object of the tree

        Keyword Args:
            refdes (bool):  flag indicating whether to display the reference
                designator or the component name as the node name
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
        tree_model = SystemTreeModel(obj, refdes=refdes,
                                     show_mode_systems=True, parent=self)
        self.proxy_model = SystemTreeProxyModel(tree_model, parent=self)
        self.source_model = self.proxy_model.sourceModel()
        self.proxy_model.setDynamicSortFilter(True)
        self.setModel(self.proxy_model)
        # all rows are same height, so use this to optimize performance
        self.setUniformRowHeights(True)
        # delegate = HTMLDelegate()
        # self.setItemDelegate(delegate)
        self.setHeaderHidden(True)
        cols = self.source_model.cols
        if cols:
            for i in range(1, len(cols)):
                self.hideColumn(i)
        self.setSelectionMode(self.SingleSelection)
        # only use dispatcher messages for assembly tree and dashboard tree
        # (i.e., a shared model); ignore them when instantiated in req
        # allocation mode (different models -> the indexes are not valid
        # anyway!)
        self.setStyleSheet('font-weight: normal; font-size: 12px')
        self.proxy_model.sort(0)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        self.setMaximumWidth(500)
        self.resizeColumnToContents(0)
        self.project = self.source_model.project
        if not state.get('sys_trees'):
            state['sys_trees'] = {}
        if not state['sys_trees'].get(self.project.id):
            state['sys_trees'][self.project.id] = {}
        if not state['sys_trees'][self.project.id].get('expanded'):
            state['sys_trees'][self.project.id]['expanded'] = []
        # ** NOTE: the below section is probably superfluous ...
        # # set initial node selection
        # if selected_system:
            # idxs = self.object_indexes_in_tree(selected_system)
            # if idxs:
                # idx_to_select = self.proxy_model.mapFromSource(idxs[0])
            # else:
                # # orb.log.debug('    selected system is not in tree.')
                # idx_to_select = self.proxy_model.mapFromSource(
                            # self.source_model.index(0, 0, QModelIndex()))
        # else:
            # # set the initial selection to the base node index
            # # orb.log.debug(' - no current selection; selecting project node.')
            # idx_to_select = self.proxy_model.mapFromSource(
                                # self.source_model.index(0, 0, QModelIndex()))
        # self.select_initial_node(idx_to_select)

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

    def object_indexes_in_tree(self, obj):
        """
        Find the source model indexes of all nodes in the system tree that
        reference the specified object (this is needed for updating the tree
        in-place when an object is modified).

        Args:
            obj (Product):  specified object
        """
        # orb.log.debug('* object_indexes_in_tree({})'.format(obj.id))
        try:
            model = self.proxy_model.sourceModel()
        except:
            # oops -- C++ object probably got deleted
            return []
        project_index = model.index(0, 0, QModelIndex())
        # project_node = model.get_node(project_index)
        # orb.log.debug('  for project {}'.format(project_node.obj.oid))
        # orb.log.debug('  (node cname: {})'.format(project_node.cname))
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
            pass
        return []


class ModesTool(QMainWindow):
    """
    Tool for defining the operational Modes of a set of systems in terms of
    the states of their subsystems.

    Attrs:
        project (Project): the project in which the systems are operating
    """
    default_modes = ['Launch', 'Calibration', 'Slew', 'Safe Hold',
                     'Science Mode, Acquisition', 'Science Mode, Transmitting']

    def __init__(self, project, modes=None, parent=None):
        """
        Args:
            project (Project): the project context in which the systems are
                operating

        Keyword Args:
            modes (list of str):  initial set of mode names
            parent (QWidget):  parent widget
        """
        super().__init__(parent)
        self.setMinimumSize(1000, 600)
        orb.log.debug('* ModesTool')
        self.project = project
        # default is all top-level systems in the project
        systems = []
        if not state.get('mode_systems'):
            state['mode_systems'] = {}
        if not state['mode_systems'].get(project.id):
            systems = [psu.system for psu in project.systems]
            state['mode_systems'][project.id] = [sys.oid for sys in systems]
        sys_names = (', '.join([system.name for system in systems])
                     or '[none]')
        orb.log.debug(f'  - systems: {sys_names}')
        self.modes = modes or self.default_modes
        self.setSizePolicy(QSizePolicy.Expanding,
                           QSizePolicy.Expanding)
        title = 'Modes of Specified Systems'
        self.setWindowTitle(title)
        self.sys_select_tree = SystemSelectionView(self.project, refdes=True)
        # self.sys_select_tree.setItemDelegate(ReqAllocDelegate())
        self.sys_select_tree.expandToDepth(1)
        # self.sys_select_tree.setExpandsOnDoubleClick(False)
        self.sys_select_tree.clicked.connect(self.on_select_systems)
        self.left_dock = QDockWidget()
        self.left_dock.setFloating(False)
        self.left_dock.setAllowedAreas(Qt.LeftDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.left_dock)
        sys_tree_panel = QWidget(self)
        sys_tree_panel.setSizePolicy(QSizePolicy.Preferred,
                                     QSizePolicy.MinimumExpanding)
        sys_tree_panel.setMinimumWidth(400)
        sys_tree_panel.setMaximumWidth(500)
        sys_tree_layout = QVBoxLayout(sys_tree_panel)
        sys_tree_layout.addWidget(self.sys_select_tree)
        self.left_dock.setWidget(sys_tree_panel)
        self.new_window = True
        self.set_table_and_adjust()

    def on_select_systems(self, index):
        mapped_i = self.sys_select_tree.proxy_model.mapToSource(index)
        sys = self.sys_select_tree.source_model.get_node(mapped_i).obj
        if state['mode_systems'].get(self.project.id):
            if sys.oid in state['mode_systems'][self.project.id]:
                state['mode_systems'][self.project.id].remove(sys.oid)
            else:
                state['mode_systems'][self.project.id].append(sys.oid)
        else:
            state['mode_systems'][self.project.id] = [sys.oid]
        # the expandToDepth is needed to make it repaint to show the selected
        # node as green-highlighted
        self.sys_select_tree.expandToDepth(1)
        self.sys_select_tree.scrollTo(index)
        self.sys_select_tree.clearSelection()
        self.set_table_and_adjust()

    def set_table_and_adjust(self):
        if self.new_window:
            size = QSize(state.get('mode_def_w') or self.width(),
                         state.get('mode_def_h') or self.height())
        else:
            size = self.size()
            state['mode_def_w'] = self.width()
            state['mode_def_h'] = self.height()
        if getattr(self, 'mode_definition_table', None):
            # remove and close current mode def table
            self.mode_definition_table.setAttribute(Qt.WA_DeleteOnClose)
            self.mode_definition_table.parent = None
            self.mode_definition_table.close()
        vheader_labels = []
        sys_oids = state['mode_systems'].get(self.project.id) or []
        # objs lists all objects in the table
        # items = []
        objs = []
        # systems is a list of the specified systems (excluding components)
        systems = []
        computeds = []
        if sys_oids:
            for oid in sys_oids:
                system = orb.get(oid)
                systems.append(system)
                objs.append(system)
                vheader_labels.append(system.name)
                if system.components:
                    computeds.append(oid)
                    comps = [acu.component for acu in system.components
                             if acu.component.oid not in sys_oids]
                    vheader_labels += [comp.name for comp in comps]
                    objs += comps
        view = self.modes
        model = ModeDefinitionModel(objs, view=view, project=self.project)
        for i, mode in enumerate(self.modes):
            model.setHeaderData(i, Qt.Horizontal, mode)
        for j, name in enumerate(vheader_labels):
            model.setHeaderData(j, Qt.Vertical, name)
        for row in range(len(objs)):
            for col in range(len(view)):
                index = model.index(row, col, QModelIndex())
                # TODO: get available states for row and set data to states[0]
                if objs[row].oid in computeds:
                    model.setData(index, '(computed)')
                else:
                    model.setData(index, '[select state]')
        self.mode_definition_table = ModeDefinitionTable()
        self.mode_definition_table.setModel(model)
        # hheader = self.mode_definition_table.horizontalHeader()
        # hheader.setSectionResizeMode(hheader.ResizeToContents)
        delegate = StateSelectorDelegate()
        self.mode_definition_table.setItemDelegate(delegate)
        # self.mode_definition_table.adjustSize()
        self.setCentralWidget(self.mode_definition_table)
        self.mode_definition_table.resizeColumnsToContents()
        # try to expand the tree enough to show the last selected system
        if systems:
            level = 1
            tree = self.sys_select_tree
            while 1:
                # try:
                tree.expandToDepth(level)
                idxs = tree.object_indexes_in_tree(systems[-1])
                if idxs:
                    tree.scrollTo(tree.proxy_model.mapFromSource(idxs[0]))
                    break
                else:
                    level += 1
                    if level > 5:
                        # 5 really should be deep enough!
                        break
                # except:
                    # orb.log.debug('  - crashed while trying to expand tree.')
                    # break
        self.resize(size)
        self.new_window = False

    def resizeEvent(self, event):
        state['mode_def_w'] = self.width()
        state['mode_def_h'] = self.height()


class ModeDefinitionTable(QTableView):
    def sizeHint(self):
        hheader = self.horizontalHeader()
        vheader = self.verticalHeader()
        fwidth = self.frameWidth() * 2
        return QSize(hheader.width() + vheader.width() + fwidth,
                     vheader.height() + hheader.height())


class ModeDefinitionModel(QStandardItemModel):
    def __init__(self, objs, view=None, project=None, parent=None):
        self.objs = objs
        self.view = view or ['name']
        self.project = project
        rows = len(objs)
        cols = len(view)
        super().__init__(rows, cols, parent=parent)

    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.BackgroundRole:
            sys_oids = state['mode_systems'].get(self.project.id) or []
            oid = self.objs[index.row()].oid
            if oid in sys_oids:
                return QBrush(Qt.blue)
            else:
                return QBrush(Qt.white)
        if role == Qt.ForegroundRole:
            sys_oids = state['mode_systems'].get(self.project.id) or []
            oid = self.objs[index.row()].oid
            if oid in sys_oids:
                return QBrush(Qt.white)
            else:
                return QBrush(Qt.black)
        return super().data(index, role)


class StateSelectorDelegate(QItemDelegate):
    default_states = ['Quiescent', 'Nominal', 'Peak', 'Off']

    def __init__(self, states=None, parent=None):
        super().__init__(parent)
        # TODO: use the states defined for the subsystem as "states"
        self.states = states or self.default_states

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        for x in self.states:
            editor.addItem(x, QVariant())
        return editor

    def setEditorData(self, widget, index):
        value = index.model().data(index, Qt.EditRole)
        widget.setCurrentText(value)

    def setModelData(self, combo, model, index):
        value = combo.currentText()
        model.setData(index, value, Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)


if __name__ == '__main__':
    # for testing purposes only ...
    import sys
    from pangalactic.core.serializers import deserialize
    from pangalactic.core.test.utils import (create_test_project,
                                             create_test_users)
    orb.start(home='junk_home', debug=True)
    mission = orb.get('test:Mission.H2G2')
    if not mission:
        if not state.get('test_users_loaded'):
            # print('* loading test users ...')
            deserialize(orb, create_test_users())
            state['test_users_loaded'] = True
        # print('* loading test project H2G2 ...')
        deserialize(orb, create_test_project())
        mission = orb.get('test:Mission.H2G2')
    if not mission.sub_activities:
        launch = clone('Activity', id='launch', name='Launch')
        sub_act_role = '1'
        acr = clone('ActCompRel', id=get_acr_id(mission.id, sub_act_role),
                    name=get_acr_name(mission.name, sub_act_role),
                    composite_activity=mission, sub_activity=launch)
        orb.save([launch, acr])
    app = QApplication(sys.argv)
    w = ActivityTable(subject=mission)
    w.show()
    sys.exit(app.exec_())

