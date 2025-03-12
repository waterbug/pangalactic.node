#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Defines the ConOps tool for modeling a Mission Concept of Operations.

NOTES:
Initially, ConOps shows a blank timeline for the current project's mission
* can display timelines for any top-level project system:
  - spacecraft (may be multiple SCs, of course)
  - ground system(s)
* sub-activities durations can be specified numerically in the ActInfoTable
  (widget on the upper left)
  -- parameters (e.g. power level) come from the subsystem specs.
"""

import sys, os
# from functools import reduce

# Louie
from pydispatch import dispatcher

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
# from PyQt5.QtGui import QGraphicsProxyWidget
from PyQt5.QtWidgets import (QApplication, QSizePolicy, QWidget, QVBoxLayout,
                             QWidgetAction, QMessageBox)

# pangalactic
try:
    # if an orb has been set (uberorb or fastorb), this works
    from pangalactic.core             import orb, state
except:
    # if an orb has not been set, uberorb is set by default
    import pangalactic.core.set_uberorb
    from pangalactic.core             import orb, state
# from pangalactic.core.access          import get_perms
from pangalactic.core.clone           import clone
from pangalactic.core.names           import get_link_name
from pangalactic.core.parametrics     import (init_mode_defz,
                                          mode_defz)
from pangalactic.core.utils.datetimes import dtstamp
# from pangalactic.node.pgxnobject      import PgxnObject
from pangalactic.node.timeline        import TimelineModeler
from pangalactic.node.powermodeler    import PowerModeler
from pangalactic.node.widgets         import CustomSplitter


class ConOpsModeler(QWidget):
    """
    Tool for modeling a Concept of Operations for the currently selected
    project or usage (Acu or ProjectSystemUsage).

    GUI structure of the ConOpsModeler is:

    ConOpsModeler (QWidget)
    -----------------------
      * Top:  TimelineModeler
        - [left side]  activity_table (ActivityWidget)
        - [middle]     main_timeline (TimelineWidget(QWidget))
                       + scene (TimelineScene(QGraphicsScene))
                         * timeline (Timeline(QGraphicsPathItem))
                         * activity blocks (EventBlock(QGraphicsPolygonItem))
        - [right side] Op blocks palette (QToolBox)
      * Bottom:  PowerModeler
        - [left side]  sys_select_tree (SystemSelectionView)
        - [right side] mode_dash (ModeDefinitionDashboard(QWidget))
    """

    def __init__(self, subject=None, parent=None):
        """
        Initialize the tool.

        Keyword Args:
            subject (Activity): (optional) a specified Activity
            parent (QWidget):  parent widget
        """
        super().__init__(parent=parent)
        orb.log.info('* ConOpsModeler initializing')
        proj_id = self.project.id
        self.mission = orb.select('Mission', owner=self.project)
        if not self.mission:
            orb.log.debug('* [ConOps] creating a new Mission ...')
            message = f"{proj_id} had no Mission object; creating one ..."
            popup = QMessageBox(
                        QMessageBox.Information,
                        "Creating Mission Object", message,
                        QMessageBox.Ok, self)
            popup.show()
            mission_name = ' '.join([proj_id, 'Mission'])
            mission_id = '_'.join([self.project.id, 'mission'])
            NOW = dtstamp()
            user = orb.get(state.get('local_user_oid') or 'me')
            self.mission = clone('Mission', id=mission_id, name=mission_name,
                                 owner=self.project,
                                 create_datetime=NOW, mod_datetime=NOW,
                                 creator=user, modifier=user)
            orb.save([self.mission])
            dispatcher.send("new object", obj=self.mission)
        if subject:
            self.subject = subject
        else:
            self.subject = self.mission
        # first make sure that mode_defz[self.project.oid] is initialized ...
        names = []
        init_mode_defz(self.project.oid)
        if mode_defz[self.project.oid]['systems']:
            for link_oid in mode_defz[self.project.oid]['systems']:
                link = orb.get(link_oid)
                names.append(get_link_name(link))
        # set initial default system state for modes that don't have one ...
        if names:
            orb.log.debug('  - specified systems:')
            for name in names:
                orb.log.debug(f'    {name}')
            # NOTE: VERY verbose debugging msg ...
            # orb.log.debug('  - mode_defz:')
            # orb.log.debug(f'   {pprint(mode_defz)}')
        else:
            orb.log.debug('  - no systems specified yet.')
        # self.init_toolbar()
        self.set_widgets()
        self.setWindowTitle('Concept of Operations (ConOps) Modeler')
        dispatcher.connect(self.on_double_click, "double clicked")
        dispatcher.connect(self.on_activity_got_focus, "activity focused")
        dispatcher.connect(self.on_remote_mod_acts, "remote new or mod acts")
        dispatcher.connect(self.on_remote_mode_defs, "modes published")

    @property
    def project(self):
        proj = orb.get(state.get('project'))
        if not proj:
            proj = orb.get('pgefobjects:SANDBOX')
        return proj

    @property
    def usage(self):
        if self._usage:
            return self._usage
        elif self.project.systems:
            self._usage = self.project.systems[0]
        else:
            TBD = orb.get('pgefobjects:TBD')
            self._usage = TBD
        return self._usage

    @usage.setter
    def usage(self, val):
        orb.log.debug("* ConOpsModeler usage.setter()")
        if isinstance(val, (orb.classes['ProjectSystemUsage'],
                            orb.classes['Acu'])):
            self._usage = val
            state['conops_usage_oid'] = val.oid
        else:
            orb.log.debug("  invalid usage, not Acu or PSU")

    def create_action(self, text, slot=None, icon=None, tip=None,
                      checkable=False):
        action = QWidgetAction(self)
        if icon is not None:
            icon_file = icon + state.get('icon_type', '.png')
            icon_dir = state.get('icon_dir', os.path.join(orb.home, 'icons'))
            icon_path = os.path.join(icon_dir, icon_file)
            action.setIcon(QIcon(icon_path))
        if tip is not None:
            action.setToolTip(tip)
            # action.setStatusTip(tip)
        if slot is not None:
            action.triggered.connect(slot)
        if checkable:
            action.setCheckable(True)
        return action

    def init_toolbar(self):
        # NOTE: toolbar may have a role later ...
        # orb.log.debug(' - ConOpsModeler.init_toolbar() ...')
        # self.toolbar = self.QToolBar()
        pass

    def set_widgets(self):
        """
        Add TimelineModeler and PowerModeler.

        Note that focusing (mouse click) on an activity in the timeline will
        make that activity the "current_activity" and restrict the graph
        to that activity's (and current usage) power graph.
        """
        orb.log.debug(' - ConOpsModeler.set_widgets() ...')
        # self.setMinimumWidth(1500)
        # self.setMinimumHeight(1200)
        main_vbox = QVBoxLayout()
        self.setLayout(main_vbox)
        self.splitter = CustomSplitter(Qt.Vertical)
        # ====================================================================
        self.timeline_modeler = TimelineModeler(self.subject, parent=self)
        self.timeline_modeler.setSizePolicy(QSizePolicy.MinimumExpanding,
                                            QSizePolicy.Fixed)
        self.splitter.addWidget(self.timeline_modeler)
        # ====================================================================
        self.setMinimumSize(1000, 700)
        project = getattr(self, 'project', None)
        initial_usage = orb.get(state.get('conops_usage_oid'))
        if not initial_usage:
            if getattr(project, 'systems', []) or []:
                initial_usage = project.systems[0]
        # try to set initial usage, mainly so graph works when conops first
        # opens if power modes have already been defined ...
        if initial_usage:
            self.set_initial_usage(initial_usage)
            state['conops_usage_oid'] = initial_usage.oid
        # ====================================================================
        self.power_modeler = PowerModeler(self.subject,
                                          initial_usage=initial_usage,
                                          parent=self)
        self.power_modeler.setSizePolicy(QSizePolicy.Preferred,
                                         QSizePolicy.MinimumExpanding)
        self.splitter.addWidget(self.power_modeler)
        # ====================================================================
        main_vbox.addWidget(self.splitter)
        # ====================================================================
        self.resize(1700, 800)
        dispatcher.connect(self.on_usage_set, "conops usage set")

    def on_usage_set(self, usage=None):
        self.usage = usage

    def set_initial_usage(self, link):
        orb.log.debug("* ConOpsModeler.set_initial_usage()")
        name = get_link_name(link)
        orb.log.debug(f"  - initial usage is {name}")
        TBD = orb.get('pgefobjects:TBD')
        product = None
        # attr = '[none]'
        if isinstance(link, orb.classes['ProjectSystemUsage']):
            if link.system:
                product = link.system
                # attr = '[system]'
        elif isinstance(link, orb.classes['Acu']):
            if link.component and link.component is not TBD:
                product = link.component
                # attr = '[component]'
        # orb.log.debug(f"  - product {attr} is {product.name}")
        if product:
            project_mode_defz = mode_defz[self.project.oid]
            sys_dict = project_mode_defz['systems']
            if link.oid in sys_dict:
                # orb.log.debug("  - link oid is in sys_dict")
                # set as subject's usage
                self.usage = link
                # signal to mode_dash to set this link as its usage ...
                # orb.log.debug('    sending "set mode usage" signal ...')
                dispatcher.send(signal='set mode usage', usage=link)
            # else:
                # orb.log.debug("  - link oid is NOT in sys_dict")

    def on_set_no_compute(self, link_oid=None):
        """
        Remove the usage oid from the "computed" list in mode_defz.
        """
        # ---------------------------------------------------------------------
        # Old docstring:
        # If the item (aka "link" or "node") in the assembly tree exists in the
        # "systems" table, remove it and remove its components from the
        # "components" table, and if it is a component of an item in the
        # "systems" table, add it back to the "components" table, and change its
        # "level" from "[computed]" to a specifiable level value.
        # ---------------------------------------------------------------------
        # TODO: implement as a context menu action ...
        # acts = getattr(self.usage, 'activities', [])
        link = orb.get(link_oid)
        # link might be None -- allow for that
        if not hasattr(link, 'oid'):
            # orb.log.debug('  - link has no oid, ignoring ...')
            return
        # name = get_link_name(link)
        project_mode_defz = mode_defz[self.project.oid]
        sys_dict = project_mode_defz['systems']
        # comp_dict = project_mode_defz['components']
        computed_list = project_mode_defz['computed']
        if link.oid in computed_list:
            computed_list.remove(link.oid)
        # ---------------------------------------------------------------------
        # Old implementation (before "computed" list was added to mode_defz)
        # ---------------------------------------------------------------------
        # if link.oid in sys_dict:
            # # if selected link is in sys_dict, make subject (see below)
            # # orb.log.debug(f' - removing "{name}" from systems ...')
            # del sys_dict[link.oid]
            # # if it is in comp_dict, remove it there too
            # if link.oid in comp_dict:
                # del comp_dict[link.oid]
            # # if it occurs as a component of an item in sys_dict, add it back
            # # to components
            # # orb.log.debug(f'   checking if "{name}" is a component ...')
            # for syslink_oid in sys_dict:
                # lk = orb.get(syslink_oid)
                # clink_oids = []
                # if hasattr(lk, 'system') and lk.system.components:
                    # clink_oids = [acu.oid for acu in lk.system.components]
                # elif hasattr(lk, 'component') and lk.component.components:
                    # clink_oids = [acu.oid for acu in lk.component.components]
                # if link.oid in clink_oids:
                    # # orb.log.debug(f' - "{name}" is a component, adding it')
                    # # orb.log.debug('   back to components of its parent')
                    # if not comp_dict.get(syslink_oid):
                        # comp_dict[syslink_oid] = {}
                    # comp_dict[syslink_oid][link.oid] = {}
                    # for mode_oid in [getattr(act, 'oid', '') for act in acts
                                     # if act is not None]:
                        # if comp_dict[syslink_oid][link.oid].get(mode_oid):
                            # comp_dict[syslink_oid][link.oid][
                                                # mode_oid] = '[select state]'
            # -----------------------------------------------------------------
            # make sure link is not current usage and if so, unset it ...
            cur_usage_oid = getattr(self.usage, 'oid', '') or ''
            if cur_usage_oid == link.oid:
                if sys_dict:
                    new_usage_oid = list(sys_dict)[0]
                    self.usage = orb.get(new_usage_oid)
                elif self.project.systems:
                    self.usage = self.project.systems[0]
            dispatcher.send(signal='modes edited', oid=self.project.oid)

    def resizeEvent(self, event):
        """
        Reimplementation of resizeEvent to capture width and height in a state
        variable.

        Args:
            event (Event): the Event instance
        """
        state['model_window_size'] = (self.width(), self.height())

    def on_double_click(self, act):
        """
        Handler for double-click on an activity block -- drill-down to view
        and/or create sub_activities timeline.

        Args:
            act (Activity): the Activity instance that was double-clicked
        """
        orb.log.debug("  - ConOpsModeler.on_double_click()...")
        try:
            orb.log.debug(f'     + activity: {act.name}')
            self.timeline_modeler.widget_drill_down(act)
        except Exception as e:
            orb.log.debug("    exception occurred:")
            orb.log.debug(e)
        dispatcher.send("subject changed", obj=act)

    def on_activity_got_focus(self, act):
        """
        Do something when an activity gets focus ...

        Args:
            act (Activity): the Activity instance that got focus
        """
        pass

    def on_delete_activity(self, oid=None, cname=None, remote=False):
        """
        Handler for dispatcher signals "delete activity" (sent by an event
        block when it is removed) and "deleted object" (sent by pangalaxian).
        Refreshes the activity tables. The signals are also handled by the
        TimelineWidget.

        Keyword Args:
            oid (str): oid of the deleted activity
            cname (str): class name of the deleted object
            remote (bool): True if the operation was initiated remotely
        """
        self.rebuild_table()

    def on_remote_mod_acts(self, objs=None):
        """
        Handle dispatcher "remote new or mod acts" signal.

        Keyword Args:
            objs (list of Activity): the new or modified Activity instances
        """
        impacts_timeline = False
        sequence_adjusted = False
        # n_objs = len(objs or [])
        # orb.log.debug('* received "remote new or mod acts" signal')
        # orb.log.debug(f'  with {n_objs} objects:')
        for obj in objs:
            seq = obj.sub_activity_sequence
            # orb.log.debug(f'    + {obj.name} [seq: {seq}]')
            if obj.oid == self.subject.oid:
                # orb.log.debug('     this activity is subject of timeline ...')
                impacts_timeline = True
            elif obj.sub_activity_of.oid == self.subject.oid:
                impacts_timeline = True
                # orb.log.debug('  modified act is in timeline --')
                # orb.log.debug('  checking sequence assignments ...')
                # NOTE: these local adjustments are temporary but should be in
                # sync with the activity sequence on the server
                seqs = [act.sub_activity_sequence
                        for act in self.subject.sub_activities]
                # orb.log.debug(f'  - seqs: {seqs}')
                if (len(seqs) > len(set(seqs)) and seq in seqs):
                    # orb.log.debug(f'  seq ({seq}) occurs > once in seqs --')
                    # orb.log.debug('  bump seq of activity with same seq ...')
                    bumped_act_oid = ''
                    for act in self.subject.sub_activities:
                        if (act.oid != obj.oid and 
                            act.sub_activity_sequence == seq):
                            bumped_seq = seq + 1
                            act.sub_activity_sequence = bumped_seq
                            bumped_act_oid = act.oid
                            sequence_adjusted = True
                            orb.db.commit()
                    # orb.log.debug('  bump seq for rest of activities ...')
                    for act in self.subject.sub_activities:
                        if (act.oid != bumped_act_oid and
                            act.sub_activity_sequence >= bumped_seq):
                            act.sub_activity_sequence += 1
                            sequence_adjusted = True
                            orb.db.commit()
                # if sequence_adjusted:
                    # orb.log.debug('  new sequence is:')
                    # for act in self.subject.sub_activities:
                        # s = act.sub_activity_sequence
                        # orb.log.debug(f'  - {act.name}: {s}')
        if impacts_timeline:
            # orb.log.debug('  setting new scene and rebuilding table ...')
            self.timeline_modeler.set_new_scene(remote=True, remote_mod_acts=objs)
            if sequence_adjusted:
                self.rebuild_table()

    def on_remote_mode_defs(self):
        """
        Handle dispatcher "modes published" signal.
        """
        orb.log.debug('* received "modes published" signal')
        self.rebuild_table()
        # collapse and re-expand tree to refresh it
        tree_expansion_index = state.get('conops_tree_expansion', {}).get(
                                            self.project.oid) or 0
        level = tree_expansion_index + 2
        self.sys_select_tree.collapseAll()
        self.sys_select_tree.expandToDepth(level)

    def closeEvent(self, event):
        """
        Things to do when this window is closed.
        """
        state["conops"] = False


if __name__ == '__main__':
    from pangalactic.node.startup import (setup_ref_db_and_version,
                                          setup_dirs_and_state)
    from pangalactic.core import __version__
    # orb.start(home='junk_home', debug=True)
    home = '/home/waterbug/cattens_home_dev'
    # orb.start(home='junk_home', debug=True)
    setup_ref_db_and_version(home, __version__)
    orb.start(home=home, console=True, debug=True)
    setup_dirs_and_state()
    app = QApplication(sys.argv)
    mw = ConOpsModeler()
    mw.show()
    sys.exit(app.exec_())

