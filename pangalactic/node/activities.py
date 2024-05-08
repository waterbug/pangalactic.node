#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
from copy import deepcopy
from functools import partial
# from pprint import pprint
from textwrap import wrap
# from textwrap import fill

from louie import dispatcher

from PyQt5.QtCore    import QSize, Qt, QModelIndex, QVariant
from PyQt5.QtGui     import QBrush, QStandardItemModel
from PyQt5.QtWidgets import (QAction, QApplication, QComboBox, QDialog,
                             QDockWidget, QGridLayout, QItemDelegate,
                             QMainWindow, QSizePolicy, QStatusBar, QTableView,
                             QTreeView, QHBoxLayout, QVBoxLayout, QWidget)

try:
    from pangalactic.core         import orb
except:
    import pangalactic.core.set_uberorb
    from pangalactic.core         import orb
from pangalactic.core             import state, write_state
from pangalactic.core.clone       import clone
from pangalactic.core.names       import get_link_name
# from pangalactic.core.parametrics import get_pval_as_str,
from pangalactic.core.parametrics import (get_pval, get_variable_and_context,
                                          get_usage_mode_val,
                                          get_usage_mode_val_as_str,
                                          mode_defz, parameterz, round_to)
from pangalactic.core.validation  import get_assembly
from pangalactic.node.buttons     import SizedButton
from pangalactic.node.dialogs     import DeleteModesDialog, EditModesDialog
from pangalactic.node.systemtree  import SystemTreeModel, SystemTreeProxyModel
from pangalactic.node.tableviews  import ActivityInfoTable
from pangalactic.node.widgets     import ColorLabel, NameLabel, ValueLabel


DEFAULT_CONTEXTS = ['Nominal', 'Peak', 'Standby', 'Survival', 'Off']
DEFAULT_ACTIVITIES = ['Launch', 'Calibration', 'Propulsion', 'Slew',
                      'Science Mode, Transmitting',
                      'Science Mode, Acquisition',
                      'Safe Mode']



class ActivityWidget(QWidget):
    """
    Table for displaying the sub-activities of an Activity and related data.

    Attrs:
        subject (Activity):  the Activity whose sub-activities are shown
    """
    def __init__(self, subject, position=None, parent=None):
        """
        Initialize.

        Args:
            subject (Activity):  Activity whose sub-activities are to be
                shown in the table

        Keyword Args:
            position (str): the table "role" of the table in the ConOps tool,
                as the "main" or "sub" table, which will determine its
                response to signals
            parent (QWidget):  parent widget
        """
        super().__init__(parent=parent)
        name = getattr(subject, 'name', 'None')
        orb.log.info(f'* ActivityWidget initializing for "{name}" ...')
        self.subject = subject
        self.project = orb.get(state.get('project'))
        self.position = position
        self.statusbar = QStatusBar()
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)
        self.title_widget = NameLabel('')
        self.title_widget.setStyleSheet('font-weight: bold; font-size: 14px')
        self.main_layout.addWidget(self.title_widget)
        self.set_title_text()
        self.set_table()
        # self.setSizePolicy(QSizePolicy.Minimum,
                           # QSizePolicy.Minimum)
        self.setSizePolicy(QSizePolicy.Maximum,
                           QSizePolicy.Maximum)
        dispatcher.connect(self.on_drill_down, 'drill down')
        dispatcher.connect(self.on_drill_up, 'go back')
        dispatcher.connect(self.on_subsystem_changed, 'changed subsystem')
        dispatcher.connect(self.on_act_mod, 'act mod')

    @property
    def act_of(self):
        return getattr(self.subject, 'of_system', None)

    @property
    def activities(self):
        """
        The relevant sub-activities that the table will display, namely the
        sub-activities of the "subject" activity which are activities of the
        table's "act_of".
        """
        subj = getattr(self, 'subject', None)
        if not subj:
            return []
        return subj.sub_activities

    def on_act_mod(self, act):
        if act is self.subject:
            self.set_title_text()

    def set_title_text(self):
        if not hasattr(self, 'title_widget'):
            return
        subj = getattr(self, 'subject', None)
        red_text = '<font color="red">{}</font>'
        blue_text = '<font color="blue">{}</font>'
        title_txt = ''
        if subj:
            if self.position == "main":
                txt = self.subject.name
                if self.subject.activity_type:
                    txt += ' ' + self.subject_activity.activity_type.name
                title_txt = red_text.format(txt)
            sys_name = (getattr(self.act_of, 'reference_designator', '') or
                        getattr(self.act_of, 'system_role', ''))
            title_txt += blue_text.format(sys_name) + ' '
            if self.position == "main":
                title_txt += 'Activity Details'
            elif self.position == "sub":
                title_txt += red_text.format(self.subject.name)
                title_txt += ' Activity Details'
        else:
            title_txt += red_text.format('No Activity')
        self.title_widget.setText(title_txt)

    def set_table(self):
        project = orb.get(state.get('project'))
        table = ActivityInfoTable(self.subject, project=project)
        table.setSizePolicy(QSizePolicy.MinimumExpanding,
                            QSizePolicy.MinimumExpanding)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.resizeColumnsToContents()
        table.setAlternatingRowColors(True)
        self.main_layout.addWidget(table)
        self.main_layout.addStretch()
        self.table = table

    def reset_table(self):
        pass

    def sizeHint(self):
        w = self.table.sizeHint().width()
        h = (self.table.sizeHint().height() +
             self.title_widget.sizeHint().height())
        return QSize(w, h)

    def on_activity_remote_mod(self, activity=None):
        # txt = '* {} table: on_activity_remote_mod()'
        # orb.log.debug(txt.format(self.position))
        if activity and activity.sub_activity_of:
            self.on_activity_added(activity.sub_activity_of.oid)

    def on_activity_added(self, oid):
        orb.log.debug('  - ActivityWidget.on_activity_added()')
        if oid in [act.oid for act in self.activities]:
            self.reset_table()

    def on_activity_removed(self, oid):
        orb.log.debug('  - ActivityWidget.on_activity_removed()')
        self.reset_table()

    def on_drill_down(self, obj=None, position=None):
        self.statusbar.showMessage("Drilled Down!")
        self.reset_table()

    def on_drill_up(self, obj=None, position=None):
        if self.position != 'sub':
            self.statusbar.showMessage("Drilled Up!")
            self.reset_table()

    def on_subsystem_changed(self, act=None, act_of=None, position=None):
        if self.position == 'main':
            self.reset_table()
        if position == 'sub':
            self.statusbar.showMessage("Subsystem Changed!")
        if self.position == 'sub':
            self.setDisabled(False)
            self.act_of = act_of
            self.reset_table()


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
        tree_model = SystemTreeModel(obj, refdes=refdes,
                                     show_mode_systems=True, parent=self)
        self.proxy_model = SystemTreeProxyModel(tree_model, parent=self)
        self.source_model = self.proxy_model.sourceModel()
        self.proxy_model.setDynamicSortFilter(True)
        self.setModel(self.proxy_model)
        # all rows are same height, so use this to optimize performance
        self.setUniformRowHeights(True)
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
        self.setSizePolicy(QSizePolicy.Preferred,
                           QSizePolicy.MinimumExpanding)
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
        if not link:
            return []
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


# =============================================================================
# NOTE:  ModesTool is DEPRECATED but its code is retained here for reference in
# re-implementing certain of its functions, etc.
# =============================================================================
class ModesTool(QMainWindow):
    """
    Tool for defining the operational Modes of a set of systems in terms of
    the states of their subsystems.

    Attrs:
        project (Project): the project in which the systems are operating
    """

    def __init__(self, project, parent=None):
        """
        Args:
            project (Project): the project context in which the systems are
                operating

        Keyword Args:
            parent (QWidget):  parent widget
        """
        super().__init__(parent)
        orb.log.debug('* ModesTool')
        self.project = project
        # first make sure that mode_defz[project.oid] is initialized ...
        names = []
        if not mode_defz.get(project.oid):
            mode_defz[project.oid] = dict(modes={}, systems={}, components={})
        if mode_defz[project.oid]['systems']:
            for link_oid in mode_defz[project.oid]['systems']:
                link = orb.get(link_oid)
                names.append(get_link_name(link))
        modes = list(mode_defz[self.project.oid].get('modes') or [])
        modes = modes or DEFAULT_ACTIVITIES
        # set initial default system state for modes that don't have one ...
        for mode in modes:
            if not mode_defz[self.project.oid]['modes'].get(mode):
                mode_defz[self.project.oid]['modes'][mode] = 'Off'
        if names:
            orb.log.debug('  - specified systems:')
            for name in names:
                orb.log.debug(f'    {name}')
            # NOTE: VERY verbose debugging msg ...
            # orb.log.debug('  - mode_defz:')
            # orb.log.debug(f'   {pprint(mode_defz)}')
        else:
            orb.log.debug('  - no systems specified yet.')
        self.setSizePolicy(QSizePolicy.Expanding,
                           QSizePolicy.Expanding)
        title = 'Operational Modes of Specified Systems'
        self.setWindowTitle(title)
        self.sys_select_tree = SystemSelectionView(self.project, refdes=True)
        self.sys_select_tree.expandToDepth(1)
        self.sys_select_tree.setExpandsOnDoubleClick(False)
        self.sys_select_tree.clicked.connect(self.on_select_system)
        self.left_dock = QDockWidget()
        self.left_dock.setFloating(False)
        self.left_dock.setAllowedAreas(Qt.LeftDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.left_dock)
        self.sys_tree_panel = QWidget(self)
        self.sys_tree_panel.setSizePolicy(QSizePolicy.Preferred,
                                     QSizePolicy.MinimumExpanding)
        self.sys_tree_panel.setMinimumWidth(400)
        self.sys_tree_panel.setMaximumWidth(500)
        sys_tree_layout = QVBoxLayout(self.sys_tree_panel)
        sys_tree_layout.addWidget(self.sys_select_tree)
        self.left_dock.setWidget(self.sys_tree_panel)
        self.new_window = True
        dispatcher.connect(self.on_modes_edited, 'modes edited')
        dispatcher.connect(self.on_modes_published, 'modes published')
        dispatcher.connect(self.on_remote_sys_mode_datum,
                           'remote sys mode datum')
        dispatcher.connect(self.on_remote_comp_mode_datum,
                           'remote comp mode datum')
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.set_table_and_adjust()

    def minimumSize(self):
        if (hasattr(self, 'sys_tree_panel') and
            hasattr(self, 'mode_definition_table')):
            view = self.mode_definition_table.model().view
            hheader_width = sum([self.mode_definition_table.columnWidth(i)
                                 for i in range(len(view))])
            vheader_width = self.mode_definition_table.verticalHeader().width()
            table_width = hheader_width + vheader_width
            width = self.sys_tree_panel.width() + table_width + 50
            height = (max(self.sys_tree_panel.height(),
                          self.mode_definition_table.height()) +
                      100)
            screen_size = QApplication.desktop().screenGeometry()
            w = min(screen_size.width() - 100, width)
            h = min(screen_size.height() - 100, height)
            return QSize(w, h)
        else:
            return QSize(1200, 500)

    def on_remote_sys_mode_datum(self, project_oid=None, link_oid=None,
                                 mode=None, value=None):
        """
        Handle remote setting of a sys mode datum.

        Args:
            project_oid (str): oid of the project object
            link_oid (str): oid of the link (Acu or PSU)
            mode (str): name of the mode
            value (polymorphic): a context name or ...
        """
        # TODO: NEW SIGNATURE: instead of "value" -- elements to construct a
        # PowerState namedtuple:
        # value_type (str): whether there is a numeric value or a "context"
        # value (float): value (if any)
        # context (str): name of a context
        # contingency (int): interpreted as a percentage
        if ((link_oid is not None) and
            hasattr(self, 'mode_definition_table') and
            (project_oid == self.project.oid)):
            project_mode_defz = mode_defz[project_oid]
            sys_dict = project_mode_defz['systems']
            if link_oid in sys_dict:
                sys_dict[link_oid][mode] = value
                self.set_table_and_adjust()

    def on_remote_comp_mode_datum(self, project_oid=None, link_oid=None,
                                  comp_oid=None, mode=None, value=None):
        if ((link_oid is not None) and
            hasattr(self, 'mode_definition_table') and
            (project_oid == self.project.oid)):
            project_mode_defz = mode_defz[project_oid]
            comp_dict = project_mode_defz['components']
            if link_oid in comp_dict and comp_oid in comp_dict[link_oid]:
                comp_dict[link_oid][comp_oid][mode] = value
                self.set_table_and_adjust()
                if state.get('mode') == "system":
                    orb.log.debug('  - sending "power modes updated" signal')
                    dispatcher.send("power modes updated")

    def on_modes_edited(self, oid):
        self.set_table_and_adjust()

    def on_modes_published(self):
        self.set_table_and_adjust()

    def on_select_system(self, index):
        """
        Select a "product usage" (aka "link" or "node") in the assembly tree
        for inclusion in the mode definitions table.  Note that if the selected
        system has components, they will also be included in the mode
        definitions table by default but will not be considered "selected
        systems" -- i.e. their sub-components will NOT be included -- unless
        they are separately selected.
        """
        orb.log.debug('  - updating mode_defz ...')
        mapped_i = self.sys_select_tree.proxy_model.mapToSource(index)
        link = self.sys_select_tree.source_model.get_node(mapped_i).link
        if not hasattr(link, 'oid'):
            return
        name = get_link_name(link)
        project_mode_defz = mode_defz[self.project.oid]
        sys_dict = project_mode_defz['systems']
        comp_dict = project_mode_defz['components']
        mode_dict = project_mode_defz['modes']
        # link might be None -- allow for that
        if link.oid in sys_dict:
            # if selected link is in sys_dict, remove it
            orb.log.debug(f' - removing "{name}" from systems ...')
            del sys_dict[link.oid]
            # if it is in comp_dict, remove it there too
            if link.oid in comp_dict:
                del comp_dict[link.oid]
            # if it occurs as a component of an item in sys_dict, add it back
            # to components
            orb.log.debug(f'   checking if "{name}" is a component ...')
            for syslink_oid in sys_dict:
                lk = orb.get(syslink_oid)
                clink_oids = []
                if hasattr(lk, 'system') and lk.system.components:
                    clink_oids = [acu.oid for acu in lk.system.components]
                elif hasattr(lk, 'component') and lk.component.components:
                    clink_oids = [acu.oid for acu in lk.component.components]
                if link.oid in clink_oids:
                    orb.log.debug(f' - "{name}" is a component, adding it')
                    orb.log.debug('   back to components of its parent')
                    if not comp_dict.get(syslink_oid):
                        comp_dict[syslink_oid] = {}
                    comp_dict[syslink_oid][link.oid] = {}
                    for mode in mode_dict:
                        comp_dict[syslink_oid][link.oid][
                                                mode] = (mode_dict.get(mode)
                                                         or '[select state]')
        else:
            # selected link is NOT in sys_dict:
            # [1] if it it is in comp_dict and
            #     [a] it has components itself, remove its comp_dict entry and
            #         add it to sys_dict (also create comp_dict items for its
            #         components)
            #     [b] it has no components, ignore the operation because it is
            #         already included in comp_dict and adding it to sys_dict
            #         would not have any effect on modes calculations
            # [2] if it it is NOT in comp_dict, add it to sys_dict (creating
            #     comp_dict items for any components)
            has_components = False
            if ((hasattr(link, 'system')
                 and link.system.components) or
                (hasattr(link, 'component')
                 and link.component.components)):
                has_components = True
            in_comp_dict = False
            for syslink_oid in comp_dict:
                if link.oid in comp_dict[syslink_oid]:
                    in_comp_dict = True
                    # [1]
                    if has_components:
                        # [a] it has components -> remove it from comp_dict and
                        #     add it to sys_dict
                        del comp_dict[syslink_oid][link.oid]
                        sys_dict[link.oid] = {}
                        for mode in mode_dict:
                            sys_dict[link.oid][mode] = '[computed]'
                    else:
                        # [b] if it has no components, ignore the operation
                        # since it is already included as a component and
                        # adding it as a system would change nothing
                        has_components = False
                        orb.log.debug(' - item selected is a component with')
                        orb.log.debug('   no components -- operation ignored.')
            if not in_comp_dict:
                # [2] neither in sys_dict NOR in comp_dict -- add it *if* it
                #     exists ... in degenerate case it may be None (no oid)
                if hasattr(link, 'oid'):
                    sys_dict[link.oid] = {}
                    for mode in mode_dict:
                        if has_components:
                            sys_dict[link.oid][mode] = '[computed]'
                        else:
                            context = mode_dict.get(mode)
                            context = context or '[select state]'
                            sys_dict[link.oid][mode] = context
        # ensure that all selected systems (sys_dict) that have components,
        # have those components included in comp_dict ...
        for syslink_oid in sys_dict:
            link = orb.get(syslink_oid)
            system = None
            if hasattr(link, 'system'):
                system = link.system
            elif hasattr(link, 'component'):
                system = link.component
            if (system and system.components and not comp_dict.get(link.oid)):
                comp_dict[link.oid] = {}
                acus = [acu for acu in system.components
                        if acu.oid not in sys_dict]
                # sort by "name" (so order is the same as the system tree)
                by_name = [(get_link_name(acu), acu) for acu in acus]
                by_name.sort()
                for name, acu in by_name:
                    if not comp_dict[link.oid].get(acu.oid):
                        comp_dict[link.oid][acu.oid] = {}
                    for mode in mode_dict:
                        context = mode_dict.get(mode)
                        context = context or '[select state]'
                        comp_dict[link.oid][acu.oid][mode] = context
        # the expandToDepth is needed to make it repaint to show the selected
        # node as highlighted
        self.sys_select_tree.expandToDepth(1)
        self.sys_select_tree.scrollTo(index)
        self.sys_select_tree.clearSelection()
        self.set_table_and_adjust()
        dispatcher.send(signal='modes edited', oid=self.project.oid)

    def wrap_header(self, text):
        return '   \n   '.join(wrap(text, width=7,
                               break_long_words=False))

    def set_table_and_adjust(self):
        orb.log.debug('  - setting mode defs table ...')
        # NOTE: very verbose debugging msg ...
        # orb.log.debug('   *** current mode_defz:')
        # orb.log.debug(f'   {pprint(mode_defz)}')
        # if self.new_window:
            # size = QSize(state.get('mode_def_w') or self.width(),
                         # state.get('mode_def_h') or self.height())
        # else:
            # size = self.size()
            # state['mode_def_w'] = self.width()
            # state['mode_def_h'] = self.height()
        if getattr(self, 'mode_definition_table', None):
            # remove and close current mode def table
            self.mode_definition_table.parent = None
            self.mode_definition_table.close()
        sys_dict = mode_defz[self.project.oid]['systems']
        comp_dict = mode_defz[self.project.oid]['components']
        mode_dict = mode_defz[self.project.oid]['modes']
        view = list(mode_dict)
        items = []
        for oid in sys_dict:
            link = orb.get(oid)
            if link:
                items.append(link)
                if link.oid in comp_dict:
                    comps = []
                    for oid in comp_dict[link.oid]:
                        comps.append(orb.get(oid))
                    # sort comps by "name" (same as in the system tree)
                    by_name = [(get_link_name(comp), comp) for comp in comps]
                    by_name.sort()
                    comps = [bn[1] for bn in by_name]
                    items += comps
        model = ModesModel(items, view=view, project=self.project)
        for i, mode in enumerate(view):
            model.setHeaderData(i, Qt.Horizontal, self.wrap_header(mode))
        vheader_labels = [get_link_name(item) for item in items]
        orb.log.debug(f' - vheader labels: {vheader_labels}')
        for j, name in enumerate(vheader_labels):
            model.setHeaderData(j, Qt.Vertical, name)
            val = model.headerData(j, Qt.Vertical)
            orb.log.debug(f' - vheader[{j}]: {val}')
        for row in range(len(items)):
            for col in range(len(view)):
                index = model.index(row, col, QModelIndex())
                # in degenerate case, items[row] link might be None ...
                if hasattr(items[row], 'oid'):
                    oid = items[row].oid
                    # TODO: get states for row and set data to states[0]
                    if oid in sys_dict and oid in comp_dict:
                        # item is a system with components -> computed
                        model.setData(index, '[computed]')
                    else:
                        val = ''
                        if oid in sys_dict:
                            # item is a system with no components
                            val = sys_dict[oid].get(view[col])
                        for sys_oid in comp_dict:
                            if oid in comp_dict[sys_oid]:
                                # item is a component
                                val = comp_dict[sys_oid][oid].get(view[col])
                        # if no val, use default
                        val = val or mode_dict[view[col]]
                        model.setData(index, val)
        self.mode_definition_table = ModesView(self.project)
        self.mode_definition_table.setAttribute(Qt.WA_DeleteOnClose)
        self.mode_definition_table.setModel(model)
        self._delegates = []
        for row, item in enumerate(items):
            for sys_oid in sys_dict:
                # check for degenerate case first (item is None)
                if ((item is not None) and
                    ((sys_oid in comp_dict and item.oid in comp_dict[sys_oid])
                    or ((sys_oid == item.oid) and sys_oid not in comp_dict))):
                    obj = None
                    if hasattr(item, 'component'):
                        obj = item.component
                    elif hasattr(item, 'system'):
                        obj = item.system
                    self._delegates.append(StateSelectorDelegate(obj))
                    self.mode_definition_table.setItemDelegateForRow(
                                                    row, self._delegates[-1])
        self.setCentralWidget(self.mode_definition_table)
        self.mode_definition_table.resizeColumnsToContents()
        # try to expand the tree enough to show the last selected system
        links = [orb.get(oid)
                 for oid in mode_defz[self.project.oid]['systems']]
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
        self.resize(self.minimumSize())
        self.new_window = False

    # def resizeEvent(self, event):
        # state['mode_def_w'] = self.width()
        # state['mode_def_h'] = self.height()

    def closeEvent(self, event):
        dispatcher.send(signal='modes edited', oid=self.project.oid)
        event.accept()


class ModesModel(QStandardItemModel):

    def __init__(self, objs, view=None, project=None, parent=None):
        """
        Initialize.
        """
        self.objs = objs
        self.view = view or ['name']
        self.project = project
        self.rows = len(objs)
        self.cols = len(view)
        super().__init__(self.rows, self.cols, parent=parent)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        """
        Return the header data for the section, orientation, and role.
        """
        if len(self.objs) > section:
            link = self.objs[section]
            if hasattr(link, 'oid'):
                sys_dict = mode_defz[self.project.oid]['systems']
                if (orientation == Qt.Vertical and
                    role == Qt.BackgroundRole):
                    if link.oid in sys_dict:
                        return QBrush(Qt.blue)
                    else:
                        return QBrush(Qt.white)
                if (orientation == Qt.Vertical and
                    role == Qt.ForegroundRole):
                    if link.oid in sys_dict:
                        return QBrush(Qt.white)
                    else:
                        return QBrush(Qt.black)
        return super().headerData(section, orientation, role=role)

    def data(self, index, role):
        """
        Return the data stored under the specified role for the index.
        """
        sys_dict = mode_defz[self.project.oid]['systems']
        comp_dict = mode_defz[self.project.oid]['components']
        link = self.objs[index.row()]
        if (not index.isValid()) or (not hasattr(link, 'oid')):
            return super().data(index, role)
        if role == Qt.DisplayRole:
            if self.cols:
                mode = self.view[index.column()]
                if self.cols > index.column():
                    if link.oid in sys_dict:
                        return sys_dict[link.oid].get(mode) or 'unspecified'
                    else:
                        val = 'unspecified'
                        for oid in comp_dict:
                            if link.oid in comp_dict[oid]:
                                val = comp_dict[oid][link.oid].get(mode)
                        return val
        if role == Qt.BackgroundRole:
            if link.oid in sys_dict:
                return QBrush(Qt.blue)
            else:
                return QBrush(Qt.white)
        if role == Qt.ForegroundRole:
            if link.oid in sys_dict:
                return QBrush(Qt.white)
            else:
                return QBrush(Qt.black)
        return super().data(index, role)

    def flags(self, index):
        """
        Return the item flags for the index -- main purpose here is to make
        "[computed]" items non-editable.
        """
        if not index.isValid():
            return Qt.NoItemFlags
        elif self.data(index, Qt.DisplayRole) == '[computed]':
            return Qt.NoItemFlags
        return Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def set_data(self, index, value, role=Qt.EditRole):
        """
        Method called by ItemDelegate -- invokes native "setData" method but
        also may send "set sys|comp mode datum" signal (must be separate from
        "setData" to avoid cycles).
        """
        orb.log.debug(' - mode datum set by delegate')
        if not index.isValid():
            return False
        if self.setData(index, value, role=Qt.EditRole):
            link = self.objs[index.row()]
            if not hasattr(link, 'oid'):
                return False
            mode = self.view[index.column()]
            sys_dict = mode_defz[self.project.oid]['systems']
            comp_dict = mode_defz[self.project.oid]['components']
            if link.oid in sys_dict:
                orb.log.debug(' - sending "sys mode datum set" signal')
                dispatcher.send(signal='sys mode datum set',
                                datum=(self.project.oid, link.oid, mode,
                                       value))
                return True
            else:
                sys_oid = None
                for oid in comp_dict:
                    if link.oid in comp_dict[oid]:
                        sys_oid = oid
                if sys_oid:
                    orb.log.debug(' - sending "comp mode datum set" signal')
                    dispatcher.send(signal='comp mode datum set',
                                    datum=(self.project.oid, sys_oid,
                                           link.oid, mode, value))
                    return True
                else:
                    return False

    def setData(self, index, value, role=Qt.EditRole):
        """
        Store the specified value at the index under the specified role.
        """
        if role != Qt.EditRole:
            return False
        if not index.isValid():
            return False
        link = self.objs[index.row()]
        if hasattr(link, 'oid'):
            mode = self.view[index.column()]
            sys_dict = mode_defz[self.project.oid]['systems']
            comp_dict = mode_defz[self.project.oid]['components']
            if link.oid in sys_dict:
                sys_dict[link.oid][mode] = value
                self.dataChanged.emit(index, index)
                return True
            else:
                mod = False
                for oid in comp_dict:
                    if link.oid in comp_dict[oid]:
                        comp_dict[oid][link.oid][mode] = value
                        mod = True
                if mod:
                    self.dataChanged.emit(index, index)
                    return True


class ModesView(QTableView):

    def __init__(self, project, parent=None):
        super().__init__(parent=parent)
        self.project = project
        header = self.horizontalHeader()
        header.setStyleSheet('font-weight: bold')
        header.setContextMenuPolicy(Qt.ActionsContextMenu)
        header.setSectionsMovable(True)
        header.sectionMoved.connect(self.on_section_moved)
        edit_modes_action = QAction('add or edit modes', header)
        edit_modes_action.triggered.connect(self.edit_modes)
        header.addAction(edit_modes_action)
        delete_modes_action = QAction('delete modes', header)
        delete_modes_action.triggered.connect(self.delete_modes)
        header.addAction(delete_modes_action)

    def on_section_moved(self, logical_index, old_index, new_index):
        orb.log.debug('* ModesView: on_section_moved() ...')
        orb.log.debug('  logical index: {}'.format(logical_index))
        orb.log.debug('  old index: {}'.format(old_index))
        orb.log.debug('  new index: {}'.format(new_index))
        old_modes_dict = deepcopy(mode_defz[self.project.oid]['modes'])
        old_sys_dict = deepcopy(mode_defz[self.project.oid]['systems'])
        old_comp_dict = deepcopy(mode_defz[self.project.oid]['components'])
        del mode_defz[self.project.oid]
        modes = list(old_modes_dict)
        new_modes = modes[:]
        moved_item = new_modes.pop(old_index)
        if new_index > len(new_modes) - 1:
            new_modes.append(moved_item)
        else:
            new_modes.insert(new_index, moved_item)
        orb.log.debug(f'  new mode order: {str(new_modes)}')
        new_modes_dict = {mode : old_modes_dict[mode] for mode in new_modes}
        new_sys_dict = {link_oid : {mode : old_sys_dict[link_oid][mode]
                                    for mode in new_modes}
                        for link_oid in old_sys_dict}
        new_comp_dict = {link_oid : 
                            {comp_oid :
                                {mode : old_comp_dict[link_oid][comp_oid][mode]
                                 for mode in new_modes}
                             for comp_oid in old_comp_dict[link_oid]}
                         for link_oid in old_comp_dict}
        mode_defz[self.project.oid] = {}
        mode_defz[self.project.oid]['modes'] = new_modes_dict
        mode_defz[self.project.oid]['systems'] = new_sys_dict
        mode_defz[self.project.oid]['components'] = new_comp_dict

    def edit_modes(self):
        dlg = EditModesDialog(self.project, parent=self)
        dlg.show()

    def delete_modes(self):
        """
        Dialog displayed in response to 'delete modes' context menu item.
        """
        modes_dict = mode_defz[self.project.oid]['modes']
        modes = list(modes_dict)
        dlg = DeleteModesDialog(modes, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            modes_to_delete = []
            for mode in modes_dict:
                if dlg.checkboxes[mode].isChecked():
                    modes_to_delete.append(mode)
            if modes_to_delete:
                for mode in modes_to_delete:
                    del modes_dict[mode]
                if not modes_dict:
                    # in case all modes have been deleted, add "Undefined" mode
                    modes_dict['Undefined'] = 'Off'
                orb.log.debug('* ModesTool: modes deleted ...')
                dispatcher.send(signal='modes edited', oid=self.project.oid)


# TODO:  implement this in parametrics module and import it ...
def get_power_contexts(obj):
    """
    Return the contexts of all power (P) parameters for an object, adding an
    "Off" context.
    """
    pids = []
    if obj.oid in parameterz:
        pids = list(parameterz[obj.oid])
    if pids:
        ptups = [get_variable_and_context(pid) for pid in pids
                 if pid.split('[')[0] == 'P']
        return [ptup[1] for ptup in ptups
                if ptup[1] and ptup[1] != 'Ctgcy'] + ['Off']
    return ['Off']


class StateSelectorDelegate(QItemDelegate):

    def __init__(self, obj, parent=None):
        super().__init__(parent)
        # TODO: use the states defined for the subsystem or defaults
        self.states = get_power_contexts(obj) or DEFAULT_CONTEXTS

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
        model.set_data(index, value, Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)


class ModeDefinitionDashboard(QWidget):
    """
    Main interface for defining power modes related to an activity.
    """

    def __init__(self, activity=None, user=None, parent=None):
        """
        Initialize.

        Keyword Args:
            activity (Activity): the activity for which modes are to be defined
            user (Person): the user of the tool
            parent (QWidget):  parent widget
        """
        super().__init__(parent=parent)
        self.act = activity
        self.user = user
        self.edit_state = False
        # named fields
        self.fields = dict(power_level='Power\nLevel',
                           p_cbe='Power\nCBE\n(Watts)',
                           p_mev='Power\nMEV\n(Watts)',
                           notes='Notes')
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)
        title_layout = QHBoxLayout()
        self.setup_title_widget()
        title_layout.addWidget(self.title_widget)
        title_layout.addStretch(1)
        main_layout.addLayout(title_layout)
        self.edit_button = SizedButton('Edit')
        self.edit_button.clicked.connect(self.on_edit)
        self.view_button = SizedButton('View')
        self.view_button.setVisible(False)
        self.view_button.clicked.connect(self.on_view)
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.edit_button)
        button_layout.addWidget(self.view_button)
        button_layout.addStretch()
        main_layout.addLayout(button_layout)
        self.dash_panel = QWidget(parent=self)
        grid = QGridLayout()
        self.dash_panel.setLayout(grid)
        main_layout.addWidget(self.dash_panel)
        self.setup_dash_interface()
        self.setup_dash_data()
        dispatcher.connect(self.on_activity_focused, "activity focused")
        dispatcher.connect(self.on_set_of_system, "set of_system")

    @property
    def project(self):
        self._project = getattr(self.act, 'owner', None)
        return self._project

    @property
    def usage(self):
        self._usage = getattr(self.act, 'of_system', None)
        if not isinstance(self._usage, (orb.classes['ProjectSystemUsage'],
                                        orb.classes['Acu'])):
            self._usage = None
        return self._usage

    @property
    def sys_name(self):
        self._sys_name = get_link_name(self.usage)
        self._sys_name = self._sys_name or 'TBD'
        return self._sys_name

    def on_activity_focused(self, act=None):
        orb.log.debug('* MDD: received signal "activity focused"')
        self.act = act
        self.on_view(None)

    def on_set_of_system(self, usage=None):
        if usage:
            if isinstance(self.act, orb.classes['Mission']):
                # 'of_system' cannot be set for a Mission -- or equivalently,
                # system modes cannot be set at Mission level; must be for a
                # specified activity
                self.on_view(None)
                return
            act = orb.select('Activity', name=self.act.name, of_system=usage)
            if act and act is not self.act:
                self.act = act
            elif not act:
                # should also replicate parms? (start, duration, etc.)
                act_id = self.act.id + '-' + usage.id
                act_name = self.act.name
                act_owner = self.act.owner
                act_type = self.act.activity_type
                self.act = clone('Activity', id=act_id, name=act_name,
                                 activity_type=act_type, of_system=usage,
                                 owner=act_owner)
        self.on_view(None)

    def setup_title_widget(self):
        blue_text = '<font color="blue">{}</font>'
        title_txt = ''
        if isinstance(self.act, orb.classes['Mission']):
            title_txt += 'To specify '
            title_txt += blue_text.format('Power Modes')
            title_txt += ', select an '
            title_txt += blue_text.format('Activity')
            title_txt += ' in the timeline and a '
            title_txt += blue_text.format('System')
            title_txt += ' from the assembly ...'
        elif not self.act.of_system:
            title_txt += 'To specify '
            title_txt += blue_text.format(self.act.name)
            title_txt += ' Power Modes, select a '
            title_txt += blue_text.format('System')
            title_txt += ' ...'
        else:
            title_txt += blue_text.format(self.act.name)
            title_txt += ' Power Mode for '
            title_txt += blue_text.format(self.sys_name)
        if hasattr(self, 'title_widget'):
            self.title_widget.set_content(title_txt, element='h2')
        else:
            self.title_widget = ColorLabel(title_txt, element='h2')

    def setup_dash_interface(self):
        """
        Set the dash title and the header labels, which don't change.
        """
        grid = self.dash_panel.layout()
        self.system_title = ColorLabel('System', color='blue', element='h3')
        grid.addWidget(self.system_title, 0, 0)
        # column titles
        grid.addWidget(self.system_title, 0, 0)
        self.component_title = ColorLabel('Component', color='blue',
                                          element='h3')
        grid.addWidget(self.component_title, 0, 1)
        self.field_titles = {}
        # set col names
        for i, name in enumerate(self.fields):
            self.field_titles[name] = ColorLabel(self.fields[name],
                                                 color='blue', element='h3')
            grid.addWidget(self.field_titles[name], 0, i+2)

    def on_edit(self, evt):
        self.edit_state = True
        self.edit_button.setVisible(False)
        self.view_button.setVisible(True)
        # clear the grid layout
        grid = self.dash_panel.layout()
        for i in reversed(range(grid.count()-1)):
            grid.takeAt(i).widget().deleteLater()
        # repopulate it
        self.setup_dash_interface()
        self.setup_dash_data()

    def on_view(self, evt):
        self.edit_state = False
        self.edit_button.setVisible(True)
        self.view_button.setVisible(False)
        # clear the grid layout
        grid = self.dash_panel.layout()
        for i in reversed(range(grid.count()-1)):
            grid.takeAt(i).widget().deleteLater()
        # repopulate it
        self.setup_dash_interface()
        self.setup_dash_data()

    def setup_dash_data(self):
        """
        Add the data.
        """
        self.setup_title_widget()
        self.sys_dict = mode_defz[self.project.oid]['systems']
        self.comp_dict = mode_defz[self.project.oid]['components']
        # set row labels
        # ---------------------------------------------------------------------
        # TODO: row labels should be removed / re-added when self.usage changes
        # ---------------------------------------------------------------------
        grid = self.dash_panel.layout()
        self.sys_name_label = ColorLabel(self.sys_name, color='black',
                                         element='b')
        grid.addWidget(self.sys_name_label, 1, 0)
        if self.sys_name in ['TBD', '[unknown]']:
            # TODO: remove all previous data from dash, if any ...
            return
        if self.usage:
            self.set_row_fields(self.usage, 1)
            if isinstance(self.usage, orb.classes['ProjectSystemUsage']):
                system = self.usage.system
            elif isinstance(self.usage, orb.classes['Acu']):
                system = self.usage.component
            acus = system.components
            if not acus:
                # TODO: pop up notification that there are no components
                return
            TBD = orb.get('pgefobjects:TBD')
            row = 1
            # create a dict that maps usage.oid to row ...
            self.usage_to_row = {}
            # a dict that maps component.oid to power level selector
            self.usage_to_l_select = {}
            # and a dict that maps component.oid to power level setter
            self.usage_to_l_setter = {}
            for acu in acus:
                comp = acu.component
                if comp and comp is not TBD:
                    row += 1
                    name = get_link_name(acu)
                    label = ColorLabel(name, color='black', element='b')
                    grid.addWidget(label, row, 1)
                    self.usage_to_row[acu.oid] = row
                    l_select = self.get_l_select(comp)
                    self.usage_to_l_select[acu.oid] = l_select
                    set_l = partial(self.set_level, oid=acu.oid)
                    self.usage_to_l_setter[acu.oid] = set_l
                    l_select.currentIndexChanged[str].connect(set_l)
                    self.set_row_fields(acu, row)

    def get_l_select(self, comp):
        contexts = get_power_contexts(comp) or DEFAULT_CONTEXTS
        l_select = QComboBox(self)
        l_select.addItems(contexts)
        l_select.setCurrentIndex(0)
        return l_select

    def set_level(self, level, oid=None):
        self.comp_dict[self.usage.oid][oid][self.act.name] = level

    def set_row_fields(self, usage, row):
        # fields: power_level, p_cbe, p_mev, notes
        grid = self.dash_panel.layout()
        if isinstance(usage, orb.classes['ProjectSystemUsage']):
            comp = usage.system
        elif isinstance(usage, orb.classes['Acu']):
            comp = usage.component
        # -------------------
        # power_level (col 2)
        # -------------------
        if row == 1:
            # TODO: enable to switch from "[computed]" to a specified level
            val = '[computed]'
            label = ValueLabel(val, w=80)
            grid.addWidget(label, row, 2)
        else:
            if self.edit_state:
                grid.addWidget(self.usage_to_l_select[usage.oid], row, 2)
            else:
                val = self.comp_dict[self.usage.oid][usage.oid][self.act.name]
                label = ValueLabel(val, w=80)
                grid.addWidget(label, row, 2)
        # -------------------
        # p_cbe (col 3)
        # -------------------
        p_cbe_val_str = get_usage_mode_val_as_str(self.project.oid,
                                                  usage.oid,
                                                  comp.oid,
                                                  self.act.name)
        p_cbe_val = get_usage_mode_val(self.project.oid, usage.oid,
                                       comp.oid, self.act.name)
        p_cbe_field = ValueLabel(p_cbe_val_str, w=40)
        grid.addWidget(p_cbe_field, row, 3)
        # -------------------
        # p_mev (col 4)
        # -------------------
        ctgcy = get_pval(comp.oid, 'P[Ctgcy]')
        factor = 1.0 + ctgcy
        p_mev_val = round_to(p_cbe_val * factor, n=3)
        p_mev_field = ValueLabel(str(p_mev_val), w=40)
        grid.addWidget(p_mev_field, row, 4)
        # -------------------
        # notes (col 5)
        # -------------------
        name = get_link_name(usage)
        # if self.edit_state:
        # else:
        txt = f'{name} notes'
        label = ValueLabel(txt)
        grid.addWidget(label, row, 5)

    def set_p_level(self, p_level):
        orb.log.debug(f'[MDDash] p_level set to {p_level}')


if __name__ == '__main__':
    # for testing purposes only ...
    import os
    from pangalactic.core import __version__
    from pangalactic.core.serializers import deserialize
    from pangalactic.core.test.utils import (create_test_project,
                                             create_test_users)
    from pangalactic.node.startup import (setup_ref_db_and_version,
                                          setup_dirs_and_state)
    print("* starting orb ...")
    home = 'junk_home'
    orb.start(home=home, debug=True, console=True)
    print("* setting up ref_db and version ...")
    setup_ref_db_and_version(home, __version__)
    print("* setting up dirs and state ...")
    setup_dirs_and_state(app_name='Pangalaxian')
    if state.get('test_project_loaded'):
        print('* test project H2G2 already loaded.')
    else:
        print('* loading test project H2G2 ...')
        deserialize(orb, create_test_project())
        state['test_project_loaded'] = True
    mission = orb.get('test:Mission.H2G2')
    H2G2 = orb.get('H2G2')
    if state.get('test_project_loaded'):
        print('* test users already loaded.')
    else:
        print('* loading test users ...')
        deserialize(orb, create_test_users())
        state['test_users_loaded'] = True
    app = QApplication(sys.argv)
    # NOTE:  set either test_mdt or test_act to True ...
    test_mt = False
    test_mdt = True
    test_act = False
    if test_mt:
        w = ModesTool(H2G2)
        w.show()
    elif test_act:
        # test ActivityWidget
        if not mission.sub_activities:
            launch = clone('Activity', id='launch', name='Launch',
                           owner=H2G2, sub_activity_of=mission)
            sub_act_role = '1'
            orb.save([launch])
        w = ActivityWidget(subject=mission)
        w.show()
    write_state(os.path.join(home, 'state'))
    sys.exit(app.exec_())

