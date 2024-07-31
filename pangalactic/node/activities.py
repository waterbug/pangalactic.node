#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
from functools import partial

from louie import dispatcher

from PyQt5.QtCore    import QSize, Qt, QModelIndex
from PyQt5.QtWidgets import (QApplication, QComboBox, QGridLayout, QSizePolicy,
                             QStatusBar, QTreeView, QHBoxLayout, QVBoxLayout,
                             QWidget)

try:
    from pangalactic.core         import orb
except:
    import pangalactic.core.set_uberorb
    from pangalactic.core         import orb
from pangalactic.core             import state, write_state
from pangalactic.core.access      import is_global_admin
from pangalactic.core.clone       import clone
from pangalactic.core.names       import get_link_name
from pangalactic.core.parametrics import (get_pval, get_power_contexts,
                                          get_modal_context,
                                          get_usage_mode_val,
                                          get_usage_mode_val_as_str,
                                          mode_defz, round_to,
                                          set_comp_modal_context)
from pangalactic.core.validation  import get_assembly
from pangalactic.node.buttons     import SizedButton
from pangalactic.node.systemtree  import SystemTreeModel, SystemTreeProxyModel
from pangalactic.node.tableviews  import ActInfoTable
from pangalactic.node.utils       import get_all_project_usages
from pangalactic.node.widgets     import ColorLabel, NameLabel, ValueLabel


DEFAULT_CONTEXTS = ['Off', 'Nominal', 'Peak', 'Standby', 'Survival']
DEFAULT_ACTIVITIES = ['Launch', 'Calibration', 'Propulsion', 'Slew',
                      'Science Data Acquisition', 'Science Data Transmission',
                      'Safe Mode']


class ActivityWidget(QWidget):
    """
    Container widget for the ActInfoTable that displays the sub-activities
    of an Activity with their start, duration, and end parameters.

    Attrs:
        subject (Activity):  the Activity whose sub-activities are shown
    """
    def __init__(self, subject, timeline=None, position=None, parent=None):
        """
        Initialize.

        Args:
            subject (Activity):  Activity whose sub-activities are to be
                shown in the table

        Keyword Args:
            timeline (Timeline):  the Timeline (QGraphicsPathItem) containing
                the scene with the activity event blocks
            position (str): the table "role" of the table in the ConOps tool,
                as the "main" or "sub" table, which will determine its
                response to signals
            parent (QWidget):  parent widget
        """
        super().__init__(parent=parent)
        name = getattr(subject, 'name', 'None')
        orb.log.info(f'* ActivityWidget initializing for "{name}" ...')
        self.timeline = timeline
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
        self.setSizePolicy(QSizePolicy.MinimumExpanding,
                           QSizePolicy.Fixed)
        # self.setSizePolicy(QSizePolicy.Maximum,
                           # QSizePolicy.Maximum)
        dispatcher.connect(self.on_drill_down, 'drill down')
        dispatcher.connect(self.on_drill_up, 'go back')
        dispatcher.connect(self.on_subsystem_changed, 'changed subsystem')
        dispatcher.connect(self.on_act_name_mod, 'act name mod')

    @property
    def act_of(self):
        return getattr(self.subject, 'of_system', None)

    @property
    def activities(self):
        """
        The relevant sub-activities that the table will display, namely the
        activities of the event blocks contained in the timeline scene.
        """
        # subj = getattr(self, 'subject', None)
        # if not subj:
            # return []
        # return subj.sub_activities
        return [evt_block.activity for evt_block in self.timeline.evt_blocks]

    def on_act_name_mod(self, act):
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
            txt = self.subject.name
            if self.subject.activity_type:
                txt += ' ' + self.subject.activity_type.name
            title_txt = red_text.format(txt)
            sys_name = (getattr(self.act_of, 'reference_designator', '') or
                        getattr(self.act_of, 'system_role', ''))
            title_txt += blue_text.format(sys_name) + ' '
            title_txt += 'Details'
        else:
            title_txt += red_text.format('No Activity')
        self.title_widget.setText(title_txt)

    def set_table(self):
        project = orb.get(state.get('project'))
        # if user has SE, LE, or admin role, table is editable
        user = orb.get(state.get('local_user_oid', 'me'))
        ras = orb.search_exact(cname='RoleAssignment',
                               assigned_to=user,
                               role_assignment_context=self.project)
        role_names = set([ra.assigned_role.name for ra in ras])
        allowed_roles = set(['Lead Engineer', 'Systems Engineer',
                             'Administrator'])
        global_admin = is_global_admin(user)
        if global_admin or (role_names & allowed_roles):
            table = ActInfoTable(self.subject, project=project,
                                 timeline=self.timeline, editable=True)
        else:
            # default: editable=False
            table = ActInfoTable(self.subject, project=project,
                                 timeline=self.timeline)
        table.setSizePolicy(QSizePolicy.Fixed,
                            # QSizePolicy.MinimumExpanding,
                            QSizePolicy.Fixed)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # table.resizeColumnsToContents()
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
            self.setEnabled(True)
            self.act_of = act_of
            self.reset_table()


class SystemSelectionView(QTreeView):
    def __init__(self, obj, refdes=True, usage=None, parent=None):
        """
        Args:
            obj (Project or Product): root object of the tree

        Keyword Args:
            refdes (bool):  flag indicating whether to display the reference
                designator or the component name as the node name
            usage (Acu or PSU):  initially selected usage
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
        if usage and isinstance(usage, (orb.classes['Acu'],
                                        orb.classes['ProjectSystemUsage'])):
            idxs = self.link_indexes_in_tree(usage)
            if idxs:
                proxy_idx = self.proxy_model.mapFromSource(idxs[0])
                self.setCurrentIndex(proxy_idx)

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
                # orb.log.debug('  link in assembly -- looking for indexes ...')
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
        # orb.log.debug('  for project {}'.format(project_node.obj.id))
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


class ModeDefinitionDashboard(QWidget):
    """
    Main interface for defining power modes related to mission and system
    activities.
    """

    def __init__(self, activity=None, usage=None, user=None, parent=None):
        """
        Initialize.

        Keyword Args:
            activity (Activity): the activity in the context of which modes are
                to be defined -- initially, this should be the project mission
            user (Person): the user of the tool
            parent (QWidget):  parent widget
        """
        super().__init__(parent=parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        mdd_state = state.get('mdd', {})
        mdd_proj = mdd_state.get(self.project.oid, {})
        self.act = activity or orb.get(mdd_proj.get("act"))
        act_name = getattr(self.act, 'name', '(not set)')
        orb.log.debug(f'* MDD: activity is "{act_name}"')
        self.user = user
        self.usage = getattr(self.act, 'of_system', None) or usage
        if not self.usage:
            valid_usage = False
            usage = orb.get(mdd_proj.get('usage'))
            if hasattr(usage, 'component'):
                projects = get_all_project_usages(usage.component)
                if self.project in projects:
                    valid_usage = True
            elif hasattr(usage, 'project'):
                if self.project is usage.project:
                    valid_usage = True
            if valid_usage:
                self.usage = usage
        self.edit_state = False
        # named fields
        self.fields = dict(power_level='Power\nLevel',
                           p_cbe='Power\nCBE\n(Watts)',
                           p_mev='Power\nMEV\n(Watts)')
                           # notes='Notes')
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)
        title_layout = QHBoxLayout()
        self.setup_title_widget()
        title_layout.addWidget(self.title_widget)
        title_layout.addStretch(1)
        self.main_layout.addLayout(title_layout)
        self.dash_panel = QWidget(parent=self)
        grid = QGridLayout()
        self.dash_panel.setLayout(grid)
        self.main_layout.addWidget(self.dash_panel)
        self.setup_dash_interface()
        self.setup_dash_data()
        dispatcher.connect(self.on_act_name_mod, 'act name mod')
        dispatcher.connect(self.on_activity_focused, "activity focused")
        dispatcher.connect(self.on_activity_deleted, "delete activity")
        dispatcher.connect(self.on_set_mode_usage, "set mode usage")
        dispatcher.connect(self.on_new_timeline, "new timeline")
        dispatcher.connect(self.on_modes_edited, 'modes edited')
        dispatcher.connect(self.on_modes_published, 'modes published')
        dispatcher.connect(self.on_remote_sys_mode_datum,
                           'remote sys mode datum')
        dispatcher.connect(self.on_remote_comp_mode_datum,
                           'remote comp mode datum')

    @property
    def act(self):
        return getattr(self, '_act', None)

    @act.setter
    def act(self, v):
        if (isinstance(v, orb.classes['Activity'])
            and v.owner is self.project):
            self._act = v
            if not state.get('mdd'):
                state['mdd'] =  {}
            if self.project.oid not in state['mdd']:
                state['mdd'][self.project.oid] =  {}
            state['mdd'][self.project.oid]["act"] = v.oid
        else:
            self._act = None

    @property
    def project(self):
        self._project = (orb.get(state.get('project'))
                         or orb.get('pgefobjects:SANDBOX'))
        return self._project

    @property
    def sys_name(self):
        if getattr(self, 'usage', None):
            self._sys_name = get_link_name(self.usage)
        else:
            self._sys_name = 'TBD'
        return self._sys_name

    @property
    def mode_dict(self):
        # maps act.oid to act.name for sub_activities of the
        # project's Mission
        md = {}
        mission = orb.select('Mission', owner=self.project)
        if mission:
            acts = mission.sub_activities
            if acts:
                md = {act.oid: act.name for act in acts}
        mode_defz[self.project.oid]['modes'] = md
        return md

    @property
    def sys_dict(self):
        sd = mode_defz[self.project.oid].get('systems')
        if sd is None:
            mode_defz[self.project.oid]['systems'] = {}
            sd = mode_defz[self.project.oid]['systems']
        return sd

    @property
    def comp_dict(self):
        cd = mode_defz[self.project.oid].get('components')
        if cd is None:
            mode_defz[self.project.oid]['components'] = {}
            cd = mode_defz[self.project.oid]['components']
        return cd

    def minimumSize(self):
        return QSize(800, 300)

    def on_new_timeline(self):
        """
        Respond to a new timeline scene having been set, such as resulting from
        an event block drill-down; no activity focused yet.
        """
        orb.log.debug('* MDD: received signal "new timeline"')
        mission = orb.select('Mission', owner=self.project)
        self.act = mission
        if self.edit_state:
            self.on_edit(None)
        else:
            self.on_view(None)

    def on_activity_focused(self, act=None):
        orb.log.debug('* MDD: received signal "activity focused"')
        self.act = act
        # make sure mode_defz has this activity oid as a mode
        if act and act.oid not in self.mode_dict:
            self.mode_dict[act.oid] = act.name
        if self.edit_state:
            self.on_edit(None)
        else:
            self.on_view(None)

    def on_activity_deleted(self, act=None):
        orb.log.debug('* MDD: received signal "delete activity"')
        mission = orb.select('Mission', owner=self.project)
        if mission:
            self.act = mission
        if mission and mission.oid not in self.mode_dict:
            self.mode_dict[mission.oid] = mission.name
        if self.edit_state:
            self.on_edit(None)
        else:
            self.on_view(None)

    def on_modes_edited(self, oid):
        orb.log.debug('* MDD: "modes edited" signal received ...')
        if self.edit_state:
            self.on_edit(None)
        else:
            self.on_view(None)

    def on_modes_published(self):
        orb.log.debug('* MDD: "modes published" signal received ...')
        if self.edit_state:
            self.on_edit(None)
        else:
            self.on_view(None)

    def on_remote_sys_mode_datum(self, project_oid=None, link_oid=None,
                                 mode=None, value=None):
        """
        Handle remote setting of a sys mode datum.

        Args:
            project_oid (str): oid of the project object
            link_oid (str): oid of the link (Acu or PSU)
            mode (str): oid of the mode
            value (polymorphic): a context name or ...
        """
        # TODO: NEW SIGNATURE: instead of "value" -- elements to construct a
        # PowerState namedtuple:
        # value_type (str): whether there is a numeric value or a "context"
        # value (float): value (if any)
        # context (str): name of a context
        # contingency (int): interpreted as a percentage
        orb.log.debug('* MDD: "remote sys mode datum" signal received ...')
        if ((link_oid is not None)
            and (project_oid == self.project.oid)
            and link_oid in self.sys_dict):
            self.sys_dict[link_oid][mode] = value
            if self.edit_state:
                self.on_edit(None)
            else:
                self.on_view(None)
            # DEACTIVATED -- was used to signal "System Power Modes" dashboard
            # to update, but not currently functioning due to dashboard bug ...
            # orb.log.debug('  - sending "power modes updated" signal')
            # dispatcher.send("power modes updated")

    def on_remote_comp_mode_datum(self, project_oid=None, link_oid=None,
                                  comp_oid=None, mode=None, value=None):
        """
        Handle remote setting of a sys mode datum.

        Args:
            project_oid (str): oid of the project object
            link_oid (str): oid of the link (Acu or PSU)
            comp_oid (str): oid of the link component
            mode (str): oid of the mode
            value (polymorphic): a context name or ...
        """
        orb.log.debug('* MDD: "remote comp mode datum" signal received ...')
        if (link_oid is not None
            and project_oid == self.project.oid
            and link_oid in self.comp_dict
            and comp_oid in self.comp_dict[link_oid]):
            orb.log.debug('  updating comp_dict ...')
            self.comp_dict[link_oid][comp_oid][mode] = value
            if self.edit_state:
                orb.log.debug('  calling on_edit() ...')
                self.on_edit(None)
            else:
                orb.log.debug('  calling on_view() ...')
                self.on_view(None)
            # DEACTIVATED -- was used to signal "System Power Modes" dashboard
            # to update, but not currently functioning due to dashboard bug ...
            # orb.log.debug('  - sending "power modes updated" signal')
            # dispatcher.send("power modes updated")

    def on_set_mode_usage(self, usage=None):
        orb.log.debug('* MDD: received signal "set mode usage"')
        name = get_link_name(usage) or '[none]'
        orb.log.debug(f'  usage: {name}')
        if usage:
            self.usage = usage
            if not state.get('mdd'):
                state['mdd'] =  {}
            if self.project.oid not in state['mdd']:
                state['mdd'][self.project.oid] =  {}
            state['mdd'][self.project.oid]["usage"] = usage.oid
            if self.edit_state:
                orb.log.debug('  in edit state: calling on_edit()')
                self.on_edit(None)
            else:
                orb.log.debug('  in view state: calling on_view()')
                self.on_view(None)

    def setup_title_widget(self):
        blue_text = '<font color="blue">{}</font>'
        title_txt = ''
        if isinstance(self.act, orb.classes['Mission']):
            if self.usage:
                title_txt += 'To specify a '
                title_txt += blue_text.format('Power Mode')
                title_txt += ' for the '
                title_txt += blue_text.format(self.sys_name)
                title_txt += ',<br>select an '
                title_txt += blue_text.format('Activity')
                title_txt += ' in the timeline ... '
            else:
                title_txt += 'To specify '
                title_txt += blue_text.format('Power Modes')
                title_txt += ', select an '
                title_txt += blue_text.format('Activity')
                title_txt += ' in the Timeline<br>and a '
                title_txt += blue_text.format('System')
                title_txt += ' from the Mission Systems ...'
        elif self.act and not self.usage:
            title_txt += 'To specify '
            title_txt += blue_text.format(self.act.name)
            title_txt += ' Power Modes,<br>select a '
            title_txt += blue_text.format('System')
            title_txt += ' ...'
        elif self.act and self.usage:
            title_txt += blue_text.format(self.act.name)
            title_txt += ' Power Mode for '
            title_txt += blue_text.format(self.sys_name)
        if hasattr(self, 'title_widget'):
            self.title_widget.set_content(title_txt, element='h2')
        else:
            self.title_widget = ColorLabel(title_txt, element='h2')

    def on_act_name_mod(self, act, remote=False):
        if act is self.act:
            self.setup_title_widget()

    def setup_dash_interface(self):
        """
        Set the dash title and the header labels, which don't change.
        """
        grid = self.dash_panel.layout()
        self.system_title = ColorLabel('System', color='blue', element='h3')
        grid.addWidget(self.system_title, 0, 0)
        # column titles
        self.field_titles = {}
        # set col names
        for i, name in enumerate(self.fields):
            self.field_titles[name] = ColorLabel(self.fields[name],
                                                 color='blue', element='h3')
            grid.addWidget(self.field_titles[name], 0, i+1)

    def on_edit(self, evt):
        self.edit_state = True
        # clear the grid layout
        try:
            grid = self.dash_panel.layout()
            for i in reversed(range(grid.count())):
                grid.takeAt(i).widget().deleteLater()
        except:
            self.dash_panel = QWidget(parent=self)
            grid = QGridLayout()
            self.dash_panel.setLayout(grid)
            self.main_layout.addWidget(self.dash_panel)
        # repopulate it
        self.setup_dash_interface()
        self.setup_dash_data()

    def on_view(self, evt):
        self.edit_state = False
        # clear the grid layout
        try:
            grid = self.dash_panel.layout()
            for i in reversed(range(grid.count())):
                grid.takeAt(i).widget().deleteLater()
        except:
            self.dash_panel = QWidget(parent=self)
            grid = QGridLayout()
            self.dash_panel.setLayout(grid)
            self.main_layout.addWidget(self.dash_panel)
        # repopulate it
        self.setup_dash_interface()
        self.setup_dash_data()

    def setup_dash_data(self):
        """
        Add the data.
        """
        self.setup_title_widget()
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
            for i in reversed(range(grid.count())):
                grid.takeAt(i).widget().deleteLater()
            return
        if self.usage and not isinstance(self.act, orb.classes['Mission']):
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
                    link_name = get_link_name(acu)
                    name = f'---- {link_name}'
                    label = ColorLabel(name, color='black', element='b',
                                       maxwidth=240)
                    label.setToolTip(link_name)
                    grid.addWidget(label, row, 0)
                    self.usage_to_row[acu.oid] = row
                    if self.edit_state:
                        l_select = self.get_l_select(comp)
                        self.usage_to_l_select[acu.oid] = l_select
                        set_l = partial(self.set_level, oid=acu.oid)
                        self.usage_to_l_setter[acu.oid] = set_l
                        l_select.activated[str].connect(set_l)
                    self.set_row_fields(acu, row)
            row += 1
            if self.edit_state:
                self.view_button = SizedButton('View')
                self.view_button.clicked.connect(self.on_view)
                grid.addWidget(self.view_button, row, 0)
            else:
                self.edit_button = SizedButton('Edit')
                self.edit_button.clicked.connect(self.on_edit)
                grid.addWidget(self.edit_button, row, 0)

    def get_l_select(self, comp):
        contexts = get_power_contexts(comp) or DEFAULT_CONTEXTS
        l_select = QComboBox(self)
        l_select.setAttribute(Qt.WA_DeleteOnClose)
        l_select.addItems(contexts)
        l_select.setCurrentIndex(0)
        return l_select

    def set_level(self, level, oid=None):
        """
        Set power level (context) for the acu whose oid is specified for the
        mode self.act.oid.
        """
        set_comp_modal_context(self.project.oid, self.usage.oid, oid,
                               self.act.oid, level)
        orb.log.debug(' - comp mode datum set:')
        orb.log.debug(f'   level = {level}')
        orb.log.debug(f'   acu oid = {oid}')
        # NOTE: "system" dict settings can be handled later ...
        # (i.e. items in the "system" dict that either have no components or
        # whose components power specs are being ignored ...)
        # if oid in self.sys_dict:
            # orb.log.debug(' - sending "sys mode datum set" signal')
            # dispatcher.send(signal='sys mode datum set',
                            # datum=(self.project.oid, oid, self.act.oid,
                                   # value))
        # else:
        sys_oid = self.usage.oid
        mode_oid = self.act.oid
        value = level
        orb.log.debug(' - sending "comp mode datum set" signal')
        dispatcher.send(signal='comp mode datum set',
                    datum=(self.project.oid, sys_oid, oid, mode_oid, value))
        self.on_edit(None)

    def set_row_fields(self, usage, row):
        # fields: power_level, p_cbe, p_mev
        grid = self.dash_panel.layout()
        self.p_cbe_fields = {}
        self.p_mev_fields = {}
        if isinstance(usage, orb.classes['ProjectSystemUsage']):
            comp = usage.system
        elif isinstance(usage, orb.classes['Acu']):
            comp = usage.component
        # -------------------
        # power_level (col 1)
        # -------------------
        modal_context = ''  # a.k.a. power level
        if row == 1:
            # TODO: enable to switch from "[computed]" to a specified level
            modal_context = '[computed]'
            label = ValueLabel(modal_context, w=80)
            grid.addWidget(label, row, 1)
        else:
            modal_context = get_modal_context(self.project.oid, usage.oid,
                                              self.act.oid)
            if modal_context == '[computed]':
                label = ValueLabel(modal_context, w=80)
                grid.addWidget(label, row, 1)
            else:
                if not modal_context:
                    # modal_context has not been set -- use default value
                    modal_context = 'Off'   # TODO: use default "template"
                if self.edit_state:
                    i = self.usage_to_l_select[usage.oid].findText(
                                                            modal_context)
                    l_sel = self.usage_to_l_select[usage.oid]
                    l_sel.setCurrentIndex(i)
                    grid.addWidget(l_sel, row, 1)
                else:
                    label = ValueLabel(modal_context, w=80)
                    grid.addWidget(label, row, 1)
        # -------------------
        # p_cbe (col 2)
        # -------------------
        p_cbe_val_str = get_usage_mode_val_as_str(self.project.oid,
                                                  usage.oid,
                                                  comp.oid,
                                                  self.act.oid)
        p_cbe_val = get_usage_mode_val(self.project.oid, usage.oid,
                                       comp.oid, self.act.oid)
        # p_cbe_val = get_modal_power(self.project.oid, usage.oid, comp.oid,
                                    # self.act.oid, modal_context)
        # TODO: possible to get None -- possible bug in get_pval ...
        p_cbe_val = p_cbe_val or 0.0
        p_cbe_field = self.p_cbe_fields.get(comp.oid)
        if p_cbe_field:
            p_cbe_field.setText(p_cbe_val_str)
        else:
            p_cbe_field = ValueLabel(p_cbe_val_str, w=40)
            self.p_cbe_fields[comp.oid] = p_cbe_field
            grid.addWidget(p_cbe_field, row, 2)
        # -------------------
        # p_mev (col 3)
        # -------------------
        ctgcy = get_pval(comp.oid, 'P[Ctgcy]')
        factor = 1.0 + ctgcy
        p_mev_val = round_to(p_cbe_val * factor, n=3)
        p_mev_val_str = str(p_mev_val)
        p_mev_field = self.p_mev_fields.get(comp.oid)
        if p_mev_field:
            p_mev_field.setText(p_mev_val_str)
        else:
            p_mev_field = ValueLabel(p_mev_val_str, w=40)
            self.p_mev_fields[comp.oid] = p_mev_field
            grid.addWidget(p_mev_field, row, 3)

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
    if test_act:
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

