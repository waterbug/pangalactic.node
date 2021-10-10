#!/usr/bin/env python
# -*- coding: utf-8 -*-

from louie import dispatcher

from collections import OrderedDict
from textwrap import wrap, fill

from PyQt5.QtCore    import QSize, Qt, QModelIndex, QVariant
from PyQt5.QtGui     import QStandardItemModel
from PyQt5.QtWidgets import (QApplication, QComboBox, QItemDelegate,
                             QMainWindow, QSizePolicy, QStatusBar, QTableView,
                             QVBoxLayout, QWidget)

from pangalactic.core             import state
from pangalactic.core.parametrics import get_pval_as_str
from pangalactic.core.utils.meta  import get_acr_id, get_acr_name
from pangalactic.core.uberorb     import orb
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


class ModesTool(QMainWindow):
    """
    Tool for defining the operational Modes of a system in terms of the states
    of its subsystems.

    Attrs:
        project (Project): the project in which the system is operating
        system (HardwareProduct):  the system whose Modes are being defined
    """
    default_modes = ['Launch', 'Calibration', 'Slew', 'Safe Hold',
                     'Science Mode, Acquisition', 'Science Mode, Transmitting']

    def __init__(self, project, system, modes=None, parent=None):
        """
        Args:
            project (Project): the project in which the system is operating
            system (HardwareProduct): the system for which Modes are to be
                characterized 

        Keyword Args:
            modes (list of str):  initial set of mode names
            parent (QWidget):  parent widget
        """
        super().__init__(parent)
        self.project = project
        self.system = system
        self.modes = modes or self.default_modes
        self.setSizePolicy(QSizePolicy.MinimumExpanding,
                           QSizePolicy.MinimumExpanding)
        self.set_mode_definition_table()

    def set_mode_definition_table(self):
        if getattr(self, 'mode_definition_table', None):
            # remove and close current mode def table
            self.mode_definition_table.setAttribute(Qt.WA_DeleteOnClose)
            self.mode_definition_table.parent = None
            self.mode_definition_table.close()
        nbr_rows = 1
        nbr_cols = 1
        if self.system.components:
            nbr_rows = len(self.system.components) + 1
        if self.modes:
            nbr_cols = len(self.modes)
            # TODO: set headers by mode
        else:
            pass
            # TODO: set "no modes" header
        model = QStandardItemModel(nbr_rows, nbr_cols)
        for row in range(nbr_rows):
            for col in range(nbr_cols):
                index = model.index(row, col, QModelIndex())
                # TODO: get available states for row and set data to states[0]
                model.setData(index, 'Off')
        self.mode_definition_table = QTableView()
        self.mode_definition_table.setModel(model)
        delegate = StateSelectorDelegate()
        self.mode_definition_table.setItemDelegate(delegate)
        self.setCentralWidget(self.mode_definition_table)


class StateSelectorDelegate(QItemDelegate):
    default_states = ['Off', 'Survival', 'Nominal', 'Peak']

    def __init__(self, states=None, parent=None):
        super().__init__(parent)
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

