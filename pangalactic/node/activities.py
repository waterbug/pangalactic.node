#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from louie import dispatcher

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import (QAction, QApplication, QMainWindow, QSizePolicy,
                             QVBoxLayout, QWidget)
from PyQt5.QtGui import QIcon

from pangalactic.core            import state
from pangalactic.core.utils.meta import get_acu_id, get_acu_name
from pangalactic.core.uberorb    import orb
from pangalactic.node.tableviews import ObjectTableView
from pangalactic.node.utils      import clone
from pangalactic.node.widgets    import NameLabel


class ActivityTables(QMainWindow):
    """
    Main window for displaying activity tables and related data.

    Attrs:
        subject (Activity):  the Activity whose component Activities are shown
    """
    def __init__(self, subject=None, preferred_size=None, parent=None):
        """
        Main window for displaying activity tables and related data.

        Keyword Args:
            subject (Activity):  Activity whose component Activities are to be
                shown in the tables
            preferred_size (tuple):  default size -- (width, height)
            parent (QWidget):  parent widget
        """
        super(ActivityTables, self).__init__(parent=parent)
        orb.log.info('* ActivityTables initializing...')
        self.subject = subject
        self.preferred_size = preferred_size
        self._init_ui()
        self.setSizePolicy(QSizePolicy.Expanding,
                           QSizePolicy.Expanding)
        dispatcher.connect(self.on_activity_added, 'new activity')

    def _init_ui(self):
        orb.log.debug('  - _init_ui() ...')
        self.set_table()
        self.init_toolbar()
        self.setCorner(Qt.TopLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.TopRightCorner, Qt.RightDockWidgetArea)
        self.statusbar = self.statusBar()

    def set_table(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)
        title = NameLabel(getattr(self.subject, 'name', 'No Parent Activity'))
        title.setStyleSheet(
            'font-weight: bold; font-size: 18px; color: purple')
        main_layout.addWidget(title)
        initial_activities = [acu.component for acu in
                              getattr(self.subject, 'components', [])]
        new_table = ObjectTableView(initial_activities)
        new_table.setSizePolicy(QSizePolicy.Preferred,
                                QSizePolicy.Preferred)
        main_layout.addWidget(new_table, stretch=1)
        self.setCentralWidget(main_widget)
        if getattr(self, 'table', None):
            self.table.close()
        self.table = new_table

    def init_toolbar(self):
        self.toolbar = self.addToolBar("Actions")
        self.toolbar.setObjectName('ActionsToolBar')
        self.report_action = self.create_action("report",
                                                slot=self.write_report,
                                                icon="document",
                                                tip="Save to file")
        self.toolbar.addAction(self.report_action)

    def create_action(self, text, slot=None, icon=None, tip=None,
                      checkable=False):
        action = QAction(text, self)
        if icon is not None:
            icon_file = icon + state.get('icon_type', '.png')
            icon_dir = state.get('icon_dir', os.path.join(orb.home, 'icons'))
            icon_path = os.path.join(icon_dir, icon_file)
            action.setIcon(QIcon(icon_path))
        if tip is not None:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        if slot is not None:
            action.triggered.connect(slot)
        if checkable:
            action.setCheckable(True)
        return action

    def sizeHint(self):
        if self.preferred_size:
            return QSize(*self.preferred_size)
        return QSize(900, 800)

    def on_activity_added(self, act=None, acu=None):
        # TODO:  add a row for the new activity ...
        if acu:
            assembly_activity_name = getattr(acu.assembly, 'name',
                                             'Other Unnamed Activity')
        self.statusbar.showMessage('New Activity "{}" added in "{}"'.format(
                                   getattr(act, 'id', '[unnamed activity]'),
                                   assembly_activity_name))

    def write_report(self):
        pass

if __name__ == '__main__':
    import sys
    from pangalactic.core.serializers import deserialize
    from pangalactic.core.test.utils import (create_test_project,
                                             create_test_users)
    orb.start(home='junk_home', debug=True)
    mission = orb.get('test:Mission.H2G2')
    if not mission:
        if not state.get('test_users_loaded'):
            print('* loading test users ...')
            deserialize(orb, create_test_users())
            state['test_users_loaded'] = True
        print('* loading test project H2G2 ...')
        deserialize(orb, create_test_project())
        mission = orb.get('test:Mission.H2G2')
    if not mission.components:
        launch = clone('Activity', id='launch', name='Launch')
        ref_des = '1'
        acu = clone('Acu', id=get_acu_id(mission.id, ref_des),
                    name=get_acu_name(mission.name, ref_des),
                    assembly=mission, component=launch)
        orb.save([launch, acu])
    app = QApplication(sys.argv)
    w = ActivityTables(subject=mission)
    w.show()
    sys.exit(app.exec_())

