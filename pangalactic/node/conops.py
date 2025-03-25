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
from PyQt5.QtWidgets import (QApplication, QMainWindow, QMessageBox,
                             QSizePolicy, QWidget, QVBoxLayout, QWidgetAction)

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
from pangalactic.core.utils.datetimes import dtstamp
from pangalactic.node.timeline        import TimelineModeler
from pangalactic.node.powermodeler    import PowerModeler
from pangalactic.node.widgets         import CustomSplitter


class ConOpsModeler(QMainWindow):
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
                         * activity blocks (ActivityBlock)
        - [right side] Op blocks palette (QToolBox)
      * Bottom:  PowerModeler
        - [left side]  sys_select_tree (SystemSelectionView)
        - [right side] mode_dash (ModeDefinitionDashboard(QWidget))
    """

    def __init__(self, subject=None, usage=None, parent=None):
        """
        Initialize the tool.

        Keyword Args:
            subject (Activity): (optional) a specified Activity
            parent (QWidget):  parent widget
        """
        super().__init__(parent=parent)
        orb.log.info('* ConOpsModeler initializing')
        self.project = orb.get(state.get('project'))
        proj_id = self.project.id
        self.usage = usage
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
        # self.init_toolbar()
        self.set_widgets()
        self.setWindowTitle('Concept of Operations (ConOps) Modeler')

    @property
    def project(self):
        return self._project

    @project.setter
    def project(self, val):
        if not val:
            val = orb.get(state.get('project'))
            if not val:
                val = orb.get('pgefobjects:SANDBOX')
        self._project = val

    @property
    def usage(self):
        _usage = orb.get(state.get('conops_usage_oid', {}).get(
                                                    self.project.oid))
        if _usage:
            self._usage = _usage
        elif self.project.systems:
            _usage = self.project.systems[0]
            self._usage = _usage
        return self._usage

    @usage.setter
    def usage(self, val):
        orb.log.debug("* ConOpsModeler usage.setter()")
        if not val:
            if self.project and self.project.systems:
                val = self.project.systems[0]
            else:
                orb.log.debug("  project has no systems, therefore, no usage.")
                val = None
        if isinstance(val, (orb.classes['ProjectSystemUsage'],
                            orb.classes['Acu'])):
            self._usage = val
            if not state.get('conops_usage_oid'):
                state['conops_usage_oid'] = {}
            state['conops_usage_oid'][self.project.oid] = val.oid
        else:
            orb.log.debug("  invalid usage, not Acu or PSU")
            val = None
        self._usage = val

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
        self.widget = QWidget()
        main_vbox = QVBoxLayout()
        self.widget.setLayout(main_vbox)
        self.splitter = CustomSplitter(Qt.Vertical)
        # ====================================================================
        self.timeline_modeler = TimelineModeler(subject=self.subject,
                                                usage=self.usage,
                                                parent=self)
        self.timeline_modeler.setSizePolicy(QSizePolicy.MinimumExpanding,
                                            QSizePolicy.Fixed)
        self.splitter.addWidget(self.timeline_modeler)
        # ====================================================================
        self.widget.setMinimumSize(1000, 700)
        # ====================================================================
        self.power_modeler = PowerModeler(self.subject,
                                          initial_usage=self.usage,
                                          parent=self)
        self.power_modeler.setSizePolicy(QSizePolicy.Preferred,
                                         QSizePolicy.MinimumExpanding)
        self.splitter.addWidget(self.power_modeler)
        # power modeler gets all the vertical stretch ...
        self.splitter.setStretchFactor(1, 1)
        # ====================================================================
        main_vbox.addWidget(self.splitter)
        # ====================================================================
        self.setCentralWidget(self.widget)
        self.resize(1700, 800)
        dispatcher.connect(self.on_usage_set, "powermodeler set usage")

    def on_usage_set(self, usage=None):
        self.usage = usage

    def resizeEvent(self, event):
        """
        Reimplementation of resizeEvent to capture width and height in a state
        variable.

        Args:
            event (Event): the Event instance
        """
        state['model_window_size'] = (self.width(), self.height())
        super().resizeEvent(event)

    def closeEvent(self, event):
        """
        Things to do when this window is closed.
        """
        state["conops"] = False


if __name__ == '__main__':
    from pangalactic.node.startup import setup_dirs_and_state
    # orb.start(home='junk_home', debug=True)
    home = '/home/waterbug/cattens_home_dev'
    # orb.start(home='junk_home', debug=True)
    orb.start(home=home, console=True, debug=True)
    setup_dirs_and_state()
    app = QApplication(sys.argv)
    mw = ConOpsModeler()
    mw.show()
    sys.exit(app.exec_())

