#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from louie import dispatcher

from collections import OrderedDict
from textwrap import wrap, fill

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import (QAction, QApplication, QMainWindow, QSizePolicy,
                             QVBoxLayout, QWidget, QTableView)
from PyQt5.QtGui import QIcon

from pangalactic.core             import state
from pangalactic.core.parametrics import get_pval_as_str #parameterz
from pangalactic.core.utils.meta  import get_acu_id, get_acu_name
from pangalactic.core.uberorb     import orb
from pangalactic.node.tablemodels import ODTableModel
from pangalactic.node.utils       import clone
from pangalactic.node.widgets     import NameLabel


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
        dispatcher.connect(self.on_activity_modified, 'modified activity')
        dispatcher.connect(self.on_activity_removed, 'removed activity')
        dispatcher.connect(self.on_order_changed, 'order changed')
        dispatcher.connect(self.on_drill_down, 'drill down')
        dispatcher.connect(self.on_drill_up, 'go back')

    def _init_ui(self):
        orb.log.debug('  - _init_ui() ...')
        self.set_central_widget()
        self.init_toolbar()
        self.setCorner(Qt.TopLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.TopRightCorner, Qt.RightDockWidgetArea)
        self.statusbar = self.statusBar()

    def set_central_widget(self):
        self.main_widget = QWidget()
        self.main_layout = QVBoxLayout()
        self.main_widget.setLayout(self.main_layout)
        self.setCentralWidget(self.main_widget)
        self.title = NameLabel(getattr(self.subject, 'name', 'No Parent Activity'))
        self.title.setStyleSheet(
            'font-weight: bold; font-size: 18px; color: purple')
        self.main_layout.addWidget(self.title)
        self.sort_and_set_table(self.subject)
        #initial_activities = [acu.component for acu in
                              # getattr(self.subject, 'components', [])]
        # all_acus = [(acu.reference_designator, acu) for acu in  getattr(self.subject, 'components', [])]
        #
        # try:
        #     all_acus.sort()
        # except:
        #     print(all_acus)
        # activities = [acu_tuple[1].component for acu_tuple in all_acus]
        # self.set_table(activities)
        #self.sort_and_set_table(activities)

    def set_title(self, activity):
        if getattr(activity, 'activity_type', None):
            a_type = activity.activity_type.name
            txt = 'Components of {} "{}"'.format(a_type, activity.id)
        else:
            txt = 'Components of "{}"'.format(getattr(activity, 'id',
                                                      'unidentified activity'))
        self.title.setText(txt)

    def set_table(self, objs):
        table_cols = ['reference_designator', 'id', 'name', 'start_time', 'duration', 'description']
        table_headers = dict(reference_designator='Reference\nDesignator',
                           id='ID', name='Name',
                           start_time='Start\nTime',
                           duration='Duration',
                           description='Description')
        od_list = []
        for obj in objs:
            obj_dict = OrderedDict()
            for col in table_cols:
                if col in orb.schemas['Activity']['field_names']:
                    attr_str = getattr(obj, col)
                    if attr_str and len(attr_str) > 15:
                        wrap(attr_str, width=15)
                        attr_str = fill(attr_str, width=15)
                    obj_dict[table_headers[col]] = attr_str
                elif col == 'reference_designator':
                    obj_dict[table_headers[col]] = obj.where_used[0].reference_designator
                else:
                    val = get_pval_as_str(orb, obj.oid, col)
                    obj_dict[table_headers[col]] = val
            od_list.append(obj_dict)

        new_model = ODTableModel(od_list)
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

    def on_activity_modified(self, activity=None):
        if activity:
            parent_act = getattr(activity.where_used[0], 'assembly', None)
            if parent_act:
                self.on_activity_added(parent_act=parent_act, modified=True)

    def on_activity_added(self, parent_act=None, modified=False):
        if modified:
            self.statusbar.showMessage('Activity Modified!')
        else:
            self.statusbar.showMessage('Activity Added!')
        self.sort_and_set_table(parent_act=parent_act)

    def on_activity_removed(self, parent_act=None):
        self.statusbar.showMessage('Activity Removed!')
        self.sort_and_set_table(parent_act=parent_act)

    def on_order_changed(self, parent_act=None):
        self.statusbar.showMessage('Order Updated!')
        self.sort_and_set_table(parent_act=parent_act)

    def on_drill_down(self, obj=None):
        self.statusbar.showMessage("Drilled Down!")
        self.sort_and_set_table(parent_act=obj)

    def on_drill_up(self, obj=None):
        self.statusbar.showMessage("Drilled Up!")
        self.sort_and_set_table(parent_act=obj)

    def sort_and_set_table(self, parent_act=None):
        all_acus = [(acu.reference_designator, acu) for acu in parent_act.components]

        try:
            all_acus.sort()
        except:
            print("sort_and_set_table fail:", all_acus)
        activities = [acu_tuple[1].component for acu_tuple in all_acus]

        self.set_table(activities)
        self.set_title(parent_act)

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
