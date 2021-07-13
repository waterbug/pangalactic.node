#!/usr/bin/env python
# -*- coding: utf-8 -*-

from louie import dispatcher

from collections import OrderedDict
from textwrap import wrap, fill

from PyQt5.QtCore import QSize, Qt, QAbstractTableModel, QVariant
from PyQt5.QtWidgets import (QApplication, QComboBox, QSizePolicy, QStatusBar,
                             QTableView, QVBoxLayout, QWidget)

from pangalactic.core             import state
from pangalactic.core.parametrics import get_pval_as_str, set_pval_from_str
from pangalactic.core.utils.meta  import get_acr_id, get_acr_name
from pangalactic.core.uberorb     import orb
from pangalactic.node.tablemodels import ODTableModel
from pangalactic.node.utils       import clone
from pangalactic.node.widgets     import NameLabel


class EditableTableModel(QAbstractTableModel):
    def __init__(self, obj_list, param, parent=None):
        super().__init__(parent=parent)
        self.obj = obj_list
        self.param = param

        orb.log.info('* EditableTableModel initializing...')

    def rowCount(self, parent):
        return len(self.obj)

    def columnCount(self, parent):
        return len(self.obj[0])

    def data(self, index, role):
        if not index.isValid():
            return QVariant()
        elif role != Qt.DisplayRole:
            return QVariant()

        cur_obj = list(self.obj[0])[index.column()]
        oid = cur_obj.oid
        return(get_pval_as_str(oid, self.param))
        # print(self.obj[index.row()].get(self.columns()[index.column()], ''))
        # return self.obj[index.row()].get(self.columns()[index.column()], '')

    def flags(self, index):
        if not index.isValid():
            return 0
        # return Qt.ItemIsEditable | Qt.ItemIsSelectable | Qt.ItemIsEnabled
        return Qt.ItemIsEditable | super().flags(index)

    def setData(self, index, value, role):
        self.obj[index.row()][index.column()] = value
        cur_obj = list(self.obj[0])[index.column()]
        # self.param = 'duration'
        oid = cur_obj.oid
        # print("VALUE", value)
        # print("parameter in table",self.param)
        set_pval_from_str(oid, self.param, value)
        # print("HEYYYY",get_pval_as_str(oid, self.param))
        return True

    def obj_cols(self):
        obj_id_list = []
        try:
            for obj in list(self.obj[0]):
                txt = '{} [{}]'.format(self.param, obj.id)
                obj_id_list.append(txt)
        except:
            pass
        return obj_id_list

    def columns(self):
        return list(self.obj[0].keys())

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.obj_cols()[section]
        return QAbstractTableModel.headerData(self, section, orientation, role)


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
        self.title = NameLabel(self.get_title())
        self.title.setStyleSheet('font-weight: bold; font-size: 14px')
        self.main_layout.addWidget(self.title)
        self.sort_and_set_table(self.subject, self.act_of,
                                position=self.position)
        self.setSizePolicy(QSizePolicy.Expanding,
                           QSizePolicy.Expanding)
        dispatcher.connect(self.on_activity_added, 'new activity')
        dispatcher.connect(self.on_activity_modified, 'modified activity')
        dispatcher.connect(self.on_activity_removed, 'removed activity')
        dispatcher.connect(self.on_order_changed, 'order changed')
        dispatcher.connect(self.on_drill_down, 'drill down')
        dispatcher.connect(self.on_drill_up, 'go back')
        dispatcher.connect(self.on_subsystem_changed, 'changed subsystem')
        dispatcher.connect(self.on_focused_changed, 'activity focused')
        dispatcher.connect(self.on_disable, 'disable widget')
        dispatcher.connect(self.on_enable, 'enable widget')
        dispatcher.connect(self.on_activities_cleared, 'cleared activities')

    def get_title(self):
        # try:
        red_text = '<font color="red">{}</font>'
        blue_text = '<font color="blue">{}</font>'
        title = ''
        txt = self.subject.name
        if self.subject.activity_type:
            txt += ' ' + self.subject_activity.activity_type.name
        txt += ': '
        title = red_text.format(txt)
        if isinstance(self.act_of, orb.classes['Product']):
            title += blue_text.format(self.act_of.name) + ' '
        title += 'Activity Details'
        return title

    def sort_and_set_table(self, activity=None, act_of=None, position=None):
        system_acts = []
        if act_of is None:
            pass
        else:
            # cur_pt_id = getattr(self.act_of.product_type,'id','None')
            fail_txt = '* {} table: all_acrs sort failed.'
            # if position == 'middle' and self.act_of != 'spacecraft':
            if position == 'middle' and self.position == 'middle':
                for acr in activity.sub_activities:
                    if self.act_of == acr.sub_activity.activity_of:
                        system_acts.append(acr)
                all_acrs = [(acr.sub_activity_role, acr)
                            for acr in system_acts]
                try:
                    all_acrs.sort()
                except:
                    orb.log.debug(fail_txt.format(self.position))
                activities = [acr_tuple[1].sub_activity for acr_tuple in all_acrs]
                self.set_table(activities)
            elif position == 'top' and self.position == 'top':
                activity = self.subject
                for acr in activity.sub_activities:
                    if self.act_of == getattr(acr.sub_activity, 'activity_of',
                                              None):
                        system_acts.append(acr)
                all_acrs = [(acr.sub_activity_role, acr)
                            for acr in system_acts]
                try:
                    all_acrs.sort()
                except:
                    orb.log.debug(fail_txt.format(self.position))
                activities = [acr_tuple[1].sub_activity for acr_tuple in all_acrs]
                self.set_table(activities)

    def set_table(self, objs):
        table_cols = ['id', 'name', 't_start', 'duration', 'description']
        table_headers = dict(id='ID', name='Name',
                           t_start='Start\nTime',
                           duration='Duration',
                           description='Description')
        od_list = []
        for obj in objs:
            obj_dict = OrderedDict()
            for col in table_cols:
                if col in orb.schemas['Activity']['field_names']:
                    attr_str = getattr(obj, col)
                    if attr_str and len(attr_str) > 28:
                        wrap(attr_str, width=28)
                        attr_str = fill(attr_str, width=28)
                    obj_dict[table_headers[col]] = attr_str
                else:
                    val = get_pval_as_str(obj.oid, col)
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

    def sizeHint(self):
        if self.preferred_size:
            return QSize(*self.preferred_size)
        return QSize(600, 500)

    def on_activity_modified(self, activity=None):
        txt = '* {} table: on_activity_modified()'
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
                orb.log.debug('  - activity modified!')
            else:
                self.statusbar.showMessage('Activity Added!')
                orb.log.debug('  - activity added!')
        self.sort_and_set_table(activity=composite_activity,
                                act_of=act_of, position=position)

    def on_activity_removed(self, composite_activity=None, act_of=None,
                            position=None):
        if self.position == position or self.position == 'bottom':
            self.statusbar.showMessage('Activity Removed!')
            self.sort_and_set_table(activity=composite_activity, act_of=act_of,
                                    position=position)

    def on_order_changed(self, composite_activity=None, act_of=None, position=None):
        if self.position == position or self.position == 'bottom':
            self.statusbar.showMessage('Order Updated!')
            self.sort_and_set_table(activity=composite_activity, act_of=act_of,
                                    position=position)

    def on_drill_down(self, obj=None, position=None):
        if self.position == 'middle':
            self.statusbar.showMessage("Drilled Down!")
            self.sort_and_set_table(activity=obj, position=position)

    def on_drill_up(self, obj=None, position=None):
        if self.position != 'middle':
            self.statusbar.showMessage("Drilled Up!")
            self.sort_and_set_table(activity=obj, position=position)

    def on_activities_cleared(self, composite_activity=None, position=None):
        # if self.position == position or self.position == 'bottom':
        self.statusbar.showMessage("Activities Cleared!")
        self.sort_and_set_table(activity=composite_activity, position=position)

    def on_subsystem_changed(self, act=None, act_of=None, position=None):
        if self.position == 'top':
            self.sort_and_set_table(activity=self.act,
                                    act_of=self.act_of,
                                    position=self.position)
        if position == 'middle':
            self.statusbar.showMessage("Subsystem Changed!")
        if self.position == 'middle':
            self.setDisabled(False)
            self.act_of = act_of
            self.sort_and_set_table(activity=act,
                                    act_of=act_of,
                                    position=position)

    def on_focused_changed(self, obj=None):
        if self.position == 'top':
            self.statusbar.showMessage("New Activity Selected!")
        elif self.position == 'middle':
            self.statusbar.showMessage("Table Refreshed!")
            self.sort_and_set_table(activity=obj, position=self.position)

    def on_disable(self):
        if self.position == 'middle':
            self.setDisabled(True)

    def on_enable(self):
        if self.position == 'middle':
            self.setEnabled(True)


class ParameterTable(QWidget):
    """
    Table for displaying the sub-activities of an Activity and related data.

    Attrs:
        subject (Activity):  the Activity whose sub-activities are shown
    """
    def __init__(self, subject=None, preferred_size=None, act_of=None,
                 initial_param=None, parent=None):
        """
        Initialize table for displaying the sub-activities of an Activity and
        related data.

        Keyword Args:
            subject (Activity):  Activity whose sub-activities are to be shown
                in the table
            preferred_size (tuple):  default size -- (width, height)
            parent (QWidget):  parent widget
            act_of (Product):  Product of which the subject is an Activity
            initial_param (str):  id of initial parameter setting
        """
        super().__init__(parent=parent)
        orb.log.info('* ParameterTable initializing for "{}" ...'.format(
                                                            subject.name))
        self.subject = subject
        self.project = orb.get(state.get('project'))
        self.preferred_size = preferred_size
        self.act_of = act_of
        self.current_param = initial_param or 'P'
        self.statusbar = QStatusBar()
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)
        self.title = NameLabel('Timeline Details')
        self.title.setStyleSheet(
            'font-weight: bold; font-size: 18px; color: purple')
        self.main_layout.addWidget(self.title)
        # TODO: refactor param_menu creation into function
        self.param_menu = QComboBox()
        self.param_menu.addItems(["Power", "Data Rate"])
        self.param_menu.setCurrentIndex(0)
        self.param_menu.currentIndexChanged[str].connect(self.param_changed)
        self.main_layout.addWidget(self.param_menu)
        self.sort_and_set_table(activity=self.subject, act_of=self.act_of)
        self.setSizePolicy(QSizePolicy.Expanding,
                           QSizePolicy.Expanding)
        dispatcher.connect(self.on_activity_added, 'new activity')
        dispatcher.connect(self.on_activity_modified, 'modified activity')
        dispatcher.connect(self.on_activity_removed, 'removed activity')
        dispatcher.connect(self.on_order_changed, 'order changed')
        dispatcher.connect(self.on_drill_down, 'drill down')
        dispatcher.connect(self.on_drill_up, 'go back')
        dispatcher.connect(self.on_subsystem_changed, 'changed subsystem')
        dispatcher.connect(self.on_focused_changed, 'activity focused')
        dispatcher.connect(self.on_activities_cleared, 'cleared activities')

    def sort_and_set_table(self, activity=None, act_of=None,
                           position=None):
        system_acts = []
        activity = activity or self.subject
        if self.act_of is None:
            pass
        if position == 'top':
            for acr in activity.sub_activities:
                if self.act_of == getattr(acr.sub_activity, 'activity_of',
                                          None):
                    system_acts.append(acr)
            all_acrs = [(acr.sub_activity_role, acr)
                        for acr in system_acts]
        else:
            for acr in activity.sub_activities:
                if self.act_of == acr.sub_activity.activity_of:
                    system_acts.append(acr)
            all_acrs = [(acr.sub_activity_role, acr)
                        for acr in system_acts]
        try:
            all_acrs.sort()
        except:
            orb.log.debug('* ParameterTable: all_acrs sort failed.')
        activities = [acr_tuple[1].sub_activity for acr_tuple in all_acrs]
        self.set_table(activities)
        self.set_title(activity)

    def set_table(self, objs):
        param = self.current_param

        obj_list = []
        for obj in objs:
            obj_list.append(obj)

        od_list = []
        obj_dict = OrderedDict()
        for obj_name in obj_list:
            val = get_pval_as_str(obj.oid, param)
            obj_dict[obj_name] = val
        od_list.append(obj_dict)

        new_model = EditableTableModel(od_list, param)
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

    def set_title(self, activity):
        try:
            txt = '{} for {} in {}'.format(self.param_menu.currentText(),
                                           self.act_of.product_type.name,
                                           activity.name)
        except:
            txt = '{}'.format(self.param_menu.currentText())
        self.title.setText(txt)

    def param_changed(self, param=None):
        # dispatcher.send("parameter changed", param=param)
        if param == 'Power':
            self.current_param = 'P'
        elif param == "Data Rate":
            self.current_param = 'R_D'
        self.sort_and_set_table()

    def sizeHint(self):
        if self.preferred_size:
            return QSize(*self.preferred_size)
        return QSize(600, 500)

    def on_activity_modified(self, activity=None):
        txt = '* ParameterTable: on_activity_modified()'
        orb.log.debug(txt)
        if activity and activity.where_occurs:
            composite_activity = getattr(activity.where_occurs[0],
                                         'composite_activity', None)
            if composite_activity:
                self.on_activity_added(composite_activity=composite_activity,
                                       modified=True)

    def on_activity_added(self, composite_activity=None, modified=False,
                          act_of=None, position=None):
        txt = '* ParameterTable: on_activity_added(modified=True) ({})'
        orb.log.debug(txt.format(position))
        self.sort_and_set_table(activity=composite_activity,
                                act_of=act_of, position=position)

    def on_activity_removed(self, composite_activity=None, act_of=None,
                            position=None):
        self.statusbar.showMessage('Activity Removed! ({})'.format(position))
        self.sort_and_set_table(activity=composite_activity,
                                act_of=act_of, position=position)

    def on_order_changed(self, composite_activity=None, act_of=None,
                         position=None):
        self.statusbar.showMessage('Order Updated! ({})'.format(position))
        self.sort_and_set_table(activity=composite_activity,
                                act_of=act_of, position=position)

    def on_drill_down(self, obj=None, position=None):
        pass
        # NOTE:  should this never affect the parameter table?
        # if self.position == 'middle':
            # self.statusbar.showMessage("Drilled Down!")
            # self.sort_and_set_table(activity=obj, position=position)

    def on_drill_up(self, obj=None, position=None):
        pass
        # NOTE:  should this never affect the parameter table?
        # if self.position != 'middle':
            # self.statusbar.showMessage("Drilled Up!")
            # self.sort_and_set_table(activity=obj, position=position)

    def on_activities_cleared(self, composite_activity=None, position=None):
        self.statusbar.showMessage("Activities Cleared! ({})".format(position))
        self.sort_and_set_table(activity=composite_activity,
                                position=position)

    def on_subsystem_changed(self, act=None, act_of=None, position=None):
        self.setDisabled(False)
        if self.act_of is None:
            self.act_of = act_of
        else:
            pt_id = getattr(self.act_of.product_type,'id','None')
            if pt_id  == 'spacecraft':
                # print("ITS THE SPACECRAFT!")
                pass
            else:
                self.act_of = act_of
                self.sort_and_set_table(activity=act, act_of=act_of)

    def on_focused_changed(self, obj=None):
        self.act_of = obj.activity_of
        self.sort_and_set_table(
                    activity=obj.where_occurs[0].composite_activity)


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

