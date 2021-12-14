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
from pangalactic.core.parametrics import get_pval_as_str, mode_defz
from pangalactic.core.utils.meta  import get_acr_id, get_acr_name
from pangalactic.core.uberorb     import orb
from pangalactic.core.validation  import get_assembly
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
        names = []
        # first make sure that mode_defz[project.oid] is initialized ...
        if not mode_defz.get(project.oid):
            mode_defz[project.oid] = {}
        if mode_defz[project.oid]:
            for link_oid in mode_defz[project.oid]:
                link = orb.get(link_oid)
                if hasattr(link, 'system'):
                    # link is a psu
                    names.append(link.system_role + ': ' + link.system.name)
                elif hasattr(link, 'component'):
                    # link is an acu
                    names.append(link.reference_designator + ': ' +
                                 link.component.name)
        if names:
            orb.log.debug('  - systems:')
            for name in names:
                orb.log.debug(f'    {name}')
        else:
            orb.log.debug('  - no systems specified yet.')
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
        link = self.sys_select_tree.source_model.get_node(mapped_i).link
        if mode_defz[self.project.oid]:
            if link.oid in mode_defz[self.project.oid]:
                del mode_defz[self.project.oid][link.oid]
            else:
                mode_defz[self.project.oid][link.oid] = ''
        else:
            mode_defz[self.project.oid][link.oid] = ''
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
        link_oids = list(mode_defz[self.project.oid].keys())
        # objs lists *all* objects shown in the modes table
        objs = []
        # links is a list of the *selected* roles/functions, which is a subset
        # of all the objects displayed in the table (which typically includes
        # components of the selected links/systems)
        links = []
        computeds = []
        if link_oids:
            for oid in link_oids:
                link = orb.get(oid)
                links.append(link)
                objs.append(link)
                name = "unknown"
                system = None
                if hasattr(link, 'system'):
                    system = link.system
                    name = link.system_role + ': ' + system.name
                elif hasattr(link, 'component'):
                    system = link.component
                    name = link.reference_designator + ': ' + system.name
                vheader_labels.append(name)
                if system and system.components:
                    computeds.append(oid)
                    acus = [acu for acu in system.components
                            if acu.oid not in link_oids]
                    names = [(acu.reference_designator + ': ' +
                              acu.component.name) for acu in acus]
                    vheader_labels += names
                    objs += acus
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
        if links:
            level = 1
            tree = self.sys_select_tree
            while 1:
                # try:
                tree.expandToDepth(level)
                idxs = tree.link_indexes_in_tree(links[-1])
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
        self.rows = len(objs)
        self.cols = len(view)
        super().__init__(self.rows, self.cols, parent=parent)

    def get_name(self, obj):
        if hasattr(obj, 'system'):
            return obj.system_role + ': ' + obj.system.name
        elif hasattr(obj, 'component'):
            return obj.reference_designator + ': ' + obj.component.name
        else:
            return "unknown"

    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            if self.cols:
                if index.column() == 0:
                    link = self.objs[index.row()]
                    return self.get_name(link)
                elif self.cols > index.column() > 0:
                    mode_name = self.view[index.column()]
                    if mode_name in mode_defz[self.project.oid]:
                        val = mode_defz[self.project.oid][mode_name]
                        return val
                    else:
                        return 'unspecified'
        if role == Qt.BackgroundRole:
            link_oids = mode_defz[self.project.oid] or {}
            oid = self.objs[index.row()].oid
            if oid in link_oids:
                return QBrush(Qt.blue)
            else:
                return QBrush(Qt.white)
        if role == Qt.ForegroundRole:
            link_oids = mode_defz[self.project.oid] or {}
            oid = self.objs[index.row()].oid
            if oid in link_oids:
                return QBrush(Qt.white)
            else:
                return QBrush(Qt.black)
        return super().data(index, role)

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole:
            return False



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

