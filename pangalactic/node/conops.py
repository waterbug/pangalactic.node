#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Defines the ConOps tool for modeling a Mission Concept of Operations.

NOTES:
Initially, ConOps shows a blank timeline for the current project
* can display timelines for all or any selected top-level project system:
  - spacecraft (may be multiple SCs, of course)
  - ground system(s)
* selected system timeline gets focus and can optionally display timelines
    for its subsystems and their activities
* subsystem timelines show sub-activities of the activities in the parent
  system's timeline, and the sub-activities are graphically in sync with their
  parent activities (vertical parallels), and show power levels, e.g.
* sub-activities durations can be specified graphically (drag edges) or
  numerically (editor from context menu), or using convenience functions (TBD)
  -- parameters (e.g. power level) can come from the subsystem spec or be
  specified ad hoc.
"""

# import pyqtgraph as pg
# from pyqtgraph.dockarea import Dock, DockArea
# from pyqtgraph.parametertree import Parameter, ParameterTree

# import numpy as np

import os

# Louie
from louie import dispatcher

from PyQt5.QtCore import Qt, QRectF, QPointF, QPoint
from PyQt5.QtGui import (QColor, QIcon, QPixmap, QCursor, QPainter,
                         QPainterPath, QPolygonF, QTransform)
# from PyQt5.QtGui import QGraphicsProxyWidget
from PyQt5.QtWidgets import (QAction, QApplication, QComboBox, QDockWidget,
                             QMainWindow, QSizePolicy, QWidget, QGraphicsItem,
                             QGraphicsPolygonItem, QGraphicsScene,
                             QGraphicsView, QGridLayout, QMenu, QToolBox,
                             QGraphicsPathItem, QVBoxLayout, QToolBar,
                             QWidgetAction, QMessageBox)
# from PyQt5.QtWidgets import QStatusBar, QTreeWidgetItem, QTreeWidget

# pangalactic
try:
    # if an orb has been set (uberorb or fastorb), this works
    from pangalactic.core             import orb, state
except:
    # if an orb has not been set, uberorb is set by default
    import pangalactic.core.set_uberorb
    from pangalactic.core             import orb, state
from pangalactic.core.clone       import clone
# from pangalactic.core.parametrics import get_pval
from pangalactic.core.parametrics import mode_defz
from pangalactic.core.utils.datetimes import dtstamp
from pangalactic.node.activities  import ActivityWidget, ModesTool
from pangalactic.node.buttons     import SizedButton, ToolButton
from pangalactic.node.diagrams.shapes import BlockLabel
# from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.widgets     import NameLabel


class EventBlock(QGraphicsPolygonItem):

    def __init__(self, activity=None, scene=None, style=None, parent=None):
        """
        Initialize Block.

        Keyword Args:
            activity (Activity):  the activity the block represents
            scene (QGraphicsScene):  scene containing this item
            style (Qt.PenStyle):  style of block border
            parent (QGraphicsItem): parent of this item
        """
        super().__init__(parent)
        self.setFlags(QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemIsMovable |
                      QGraphicsItem.ItemIsFocusable |
                      QGraphicsItem.ItemSendsGeometryChanges)
        self.style = style or Qt.SolidLine
        self.activity = activity
        self.scene = scene
        self.setBrush(Qt.white)
        path = QPainterPath()
        self.create_actions()
        # shape of block depends on activity_type.name
        if self.activity.activity_type.name == "Op":
            self.myPolygon = QPolygonF([
                    QPointF(-50, 50), QPointF(50, 50),
                    QPointF(50, -50), QPointF(-50, -50)])
        elif self.activity.activity_type.name == "Event":
             self.myPolygon = QPolygonF([
                     QPointF(0, 0), QPointF(-50, 80),
                     QPointF(50, 80)])
        else:
            # "Cycle"
            path.addEllipse(-100, 0, 200, 200)
            self.myPolygon = path.toFillPolygon(QTransform())
        self.setPolygon(self.myPolygon)
        self.block_label = BlockLabel(getattr(self.activity, 'name', '') or '',
                                      self, point_size=8)

    def update_block_label(self):
        self.block_label.set_text(getattr(self.activity, 'name', 'No Name')
                                          or 'No Name')

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        dispatcher.send("double clicked", act=self.activity)

    def contextMenuEvent(self, event):
        self.menu = QMenu()
        self.menu.addAction(self.delete_action)
        self.menu.addAction(self.show_modes_action)
        # self.menu.addAction(self.edit_action)
        self.menu.exec(QCursor.pos())

    def create_actions(self):
        self.delete_action = QAction("Delete", self.scene,
                                     statusTip="Delete Activity",
                                     triggered=self.delete_block_activity)
        self.show_modes_action = QAction("Assign Mode", self.scene,
                                     statusTip="Assign a Mode",
                                     triggered=self.show_modes)
        # self.edit_action = QAction("Edit", self.scene,
                                   # statusTip="Edit activity",
                                   # triggered=self.edit_activity)

    def edit_activity(self):
        self.scene.edit_scene_activity(self.activity)

    def delete_block_activity(self):
        orb.log.debug(' - dipatching "delete activity" signal')
        self.scene.removeItem(self)
        dispatcher.send(signal='delete activity', oid=self.activity.oid)

    def show_modes(self):
        orb.log.debug(' - showing modes possible to assign to this activity')

    def itemChange(self, change, value):
        return value

    def mousePressEvent(self, event):
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)

BAR_COLORS = ['red', 'darkRed', 'green', 'darkGreen', 'blue',
            'darkBlue', 'cyan', 'darkCyan', 'magenta', 'darkMagenta', 'yellow',
            'darkYellow', 'gray', 'darkGray', 'lightGray']
bar_colors = [getattr(Qt, color) for color in BAR_COLORS]
# -----------------------------------------------------
#  pinkity (#ffccf9)
#  purplish (#ecd4ff)
#  pinkish (#fbe4ff)
#  shade purple (#dcd3ff)
#  greenish  (#aff8db)
#  blue-green (#c4faf8)
#  yellow green (#dbffd6)
#  pale yelleen (#f3ffe3)
#  light yellow (#ffffd1)
#  med. yellow (#fff5ba)
#  light gray (#c0c0c0)
# -----------------------------------------------------


class TimelineBar(QGraphicsPolygonItem):
    """
    TimelineBar is a segmented rectangle representing the durations of all the
    subactivities of the subject activity.
    """

    def __init__(self, subject=None, scene=None, style=None, x_start=100, 
                 x_end=1000, color=Qt.cyan, parent=None):
        """
        Initialize TimelineBar.

        Keyword Args:
            subject (Activity):  the activity the block represents
            scene (QGraphicsScene):  scene containing this item
            style (Qt.PenStyle):  style of block border
            parent (QGraphicsItem): parent of this item
        """
        super().__init__(parent)
        self.setFlags(QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemIsFocusable |
                      QGraphicsItem.ItemSendsGeometryChanges)
        self.style = style or Qt.SolidLine
        self.subject = subject
        self.scene = scene
        color = QColor('#ffccf9')
        # color.setNamedColor('#d5aaff')
        self.setBrush(color)
        self.polygon = QPolygonF([
                QPointF(x_start, 480), QPointF(x_end, 480),
                QPointF(x_end, 460), QPointF(x_start, 460)])
        self.setPolygon(self.polygon)
        self.block_label = BlockLabel(getattr(self.subject, 'name', '') or '',
                                      self, point_size=8)


class TimelineView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing)

    def dragEnterEvent(self, event):
        try:
            event.accept()
        except:
            pass

    def dragMoveEvent(self, event):
        event.accept()

    def dragLeaveEvent(self, event):
        event.accept()


class Timeline(QGraphicsPathItem):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.evt_blocks = []
        self.path_length = 1000
        self.make_path()
        self.current_positions = []

    def make_path(self):
        self.path = QPainterPath(QPointF(100, 250))
        self.path.arcTo(QRectF(0, 200, 100, 100), 0, 360)
        self.circle_length = self.path.length()
        self.path.arcTo(QRectF(self.path_length, 200, 100, 100), 180, 360)
        self.setPath(self.path)
        self.length = round(self.path.length() - 2 * self.circle_length)
        factor = self.length // (len(self.evt_blocks) + 1)
        self.list_of_pos = [(n+1) * factor + 100
                            for n in range(0, len(self.evt_blocks))]

    def update_timeline(self):
        self.calc_length()
        self.make_path()
        self.arrange()

    def calc_length(self):
        if len(self.evt_blocks) <= 6:
            self.path_length = 1000
        else:
            # adjust timeline length and rescale scene
            delta = len(self.evt_blocks) - 6
            self.path_length = 1000 + (delta // 2) * 300
            scale = 70 - (delta // 2) * 10
            pscale = str(scale) + "%"
            dispatcher.send("rescale timeline", percentscale=pscale)

    def add_evt_block(self, evt_block):
        self.evt_blocks.append(evt_block)
        self.update_timeline()

    def populate(self, evt_blocks):
        self.evt_blocks = evt_blocks
        self.update_timeline()

    def arrange(self):
        orb.log.debug('* timeline.arrange()')
        self.evt_blocks.sort(key=lambda x: x.scenePos().x())
        orb.log.debug('  - setting sub_activity_sequence(s) ...')
        NOW = dtstamp()
        for i, evt_block in enumerate(self.evt_blocks):
            evt_block.setPos(QPoint(self.list_of_pos[i], 250))
            act = evt_block.activity
            # FIXME:  sequence is determined by start/end times -- they must be
            # kept consistent ...
            if act.sub_activity_sequence != i:
                act.sub_activity_sequence = i
                act.mod_datetime = NOW
                orb.save([act])
                dispatcher.send("modified object", obj=act)
        dispatcher.send("order changed", act=act)
        self.update()


class TimelineScene(QGraphicsScene):

    def __init__(self, parent, activity, position=None):
        super().__init__(parent)
        self.position = position
        self.subject = activity
        if activity:
            self.act_of = activity.of_system
            name = getattr(self.act_of, 'name', None) or 'None'
            orb.log.debug(f'  act_of: {name}')
        self.timeline = Timeline()
        self.addItem(self.timeline)
        self.timelinebar = TimelineBar()
        self.addItem(self.timelinebar)
        self.focusItemChanged.connect(self.focus_changed_handler)
        self.current_focus = None
        self.grabbed_item = None
        dispatcher.connect(self.on_act_mod, "act mod")

    def focus_changed_handler(self, new_item, old_item):
        if getattr(self, "right_button_pressed", False):
            # ignore: context menu event
            self.right_button_pressed = False
            return
        elif (self.position == "main" and
            new_item is not None and
            new_item != self.current_focus):
            self.current_focus = new_item
            if hasattr(self.focusItem(), 'activity'):
                dispatcher.send("activity focused",
                                act=self.focusItem().activity)

    def mousePressEvent(self, mouseEvent):
        if mouseEvent.button() == Qt.RightButton:
            self.right_button_pressed = True
        super().mousePressEvent(mouseEvent)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self.grabbed_item = self.mouseGrabberItem()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.grabbed_item != None:
            self.grabbed_item.setPos(event.scenePos().x(), 250)
            self.timeline.arrange()
        self.grabbed_item == None

    def dropEvent(self, event):
        orb.log.debug('* scene.dropEvent()')
        seq = len(self.subject.sub_activities) + 1
        # activity type is one of "Cycle", "Op", "Event"
        activity_type_name = event.mimeData().text()
        activity_type = orb.select("ActivityType", name=activity_type_name)
        prefix = (getattr(self.act_of, 'reference_designator', '') or
                  getattr(self.act_of, 'system_role', '') or
                  # for Mission ...
                  getattr(getattr(self.act_of, 'owner', None), 'id', '') or
                  'Mission')
        act_id = '-'.join([prefix, activity_type_name, str(seq)])
        act_name = ' '.join([prefix, activity_type_name, str(seq)])
        project = orb.get(state.get('project'))
        activity = clone("Activity", id=act_id, name=act_name,
                         activity_type=activity_type, owner=project,
                         of_system=self.act_of,
                         sub_activity_of=self.subject,
                         sub_activity_sequence=seq)
        orb.db.commit()
        evt_block = EventBlock(activity=activity,
                               scene=self)
        evt_block.setPos(event.scenePos())
        self.addItem(evt_block)
        self.timeline.add_evt_block(evt_block)
        self.timeline.arrange()
        orb.log.debug('* scene: sending "new activity" signal')
        dispatcher.send(signal="new activity", act=activity)
        self.update()

    def on_act_mod(self, act=None):
        """
        Handle 'act mod' signal from ActivityInfoTable, meaning an activity was
        modified.
        """
        orb.log.debug('* scene: received "act_mod" signal')
        for item in self.timeline.evt_blocks:
            # orb.log.debug(f'  checking for {item.activity.name} by oid')
            if item.activity.oid == act.oid:
                item.update_block_label()
                dispatcher.send("modified object", obj=item.activity)

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)


# TODO:  the TimelineWidget should display the timelines of either
# (1) if TimelineWidget activity is the Mission, a selected project system or
# group of systems (e.g. a selected SC, all SC's, ground system, all of the
# above, etc.), or
# (2) if TimelineWidget activity is a non-Mission activity instance, all
# subsystems of the current activity's "of_system" usage.

# TODO: implement "back" based on history

class TimelineWidget(QWidget):
    """
    Widget to contain the timeline scene with activity blocks.

    Attrs:
        history (list):  list of previous parent Activity instances
    """

    def __init__(self, subject, position=None, parent=None):
        """
        Initialize TimelineWidget.

        Keyword Args:
            subject (Activity):  the activity the timeline represents
            position (str):  "main" or "sub"
            parent (QGraphicsItem): parent of this item
        """
        super().__init__(parent=parent)
        orb.log.debug(' - initializing TimelineWidget ...')
        self.subject = subject
        self.position = position
        self.init_toolbar()
        # set_new_scene() calls self.set_title(), which sets a title_widget
        self.set_new_scene()
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.title_widget)
        self.layout.addWidget(self.toolbar)
        self.layout.addWidget(self.view)
        self.setLayout(self.layout)
        self.history = []
        self.sceneScaleChanged("70%")
        self.current_subsystem_index = 0
        self.deleted_acts = []
        dispatcher.connect(self.delete_activity, "remove activity")
        dispatcher.connect(self.delete_activity, "deleted object")
        dispatcher.connect(self.delete_activity, "delete activity")
        dispatcher.connect(self.on_rescale_timeline, "rescale timeline")
        dispatcher.connect(self.on_act_mod, "act mod")
        self.setUpdatesEnabled(True)

    @property
    def system(self):
        return getattr(self.subject, 'of_system', None) or None

    def set_new_scene(self):
        """
        Return a new scene with new subject activity or an empty scene if no
        subject activity.
        """
        orb.log.debug(' - set_new_scene ...')
        scene = TimelineScene(self, self.subject, position=self.position)
        if (self.subject != None and
            len(self.subject.sub_activities) > 0):
            evt_blocks=[]
            for activity in sorted(self.subject.sub_activities,
                                   key=lambda x: getattr(x,
                                   'sub_activity_sequence', 0) or 0):
                if (activity.of_system == self.system):
                    item = EventBlock(activity=activity,
                                      scene=scene)
                    evt_blocks.append(item)
                    scene.addItem(item)
                scene.update()
            scene.timeline.populate(evt_blocks)
        self.set_title()
        self.scene = scene
        if not getattr(self, 'view', None):
            self.view = TimelineView(self)
        self.view.setScene(self.scene)
        self.view.show()

    def set_title(self):
        # try:
        if not getattr(self, 'title_widget', None):
            self.title_widget = NameLabel('')
            self.title_widget.setStyleSheet(
                'font-weight: bold; font-size: 16px')
        red_text = '<font color="red">{}</font>'
        blue_text = '<font color="blue">{}</font>'
        title = ''
        if self.subject:
            if isinstance(self.subject, orb.classes['Mission']):
                txt = ''
                project = orb.get(state.get('project'))
                if project:
                    txt = project.id + ' '
                txt += 'Mission '
                title = red_text.format(txt)
            elif isinstance(self.subject, orb.classes['Activity']):
                txt = self.subject.name
                title = red_text.format(txt)
            if isinstance(self.system, orb.classes['Product']):
                title += blue_text.format(self.system.name + ' System ')
            title += ' Timeline'
        else:
            txt = 'No Activity Selected'
            title = red_text.format(txt)
        self.title_widget.setText(title)
        # except:
            # pass

    def widget_drill_down(self, act):
        """
        Handle a double-click event on an eventblock, creating and
        displaying a new view.

        Args:
            obj (EventBlock):  the block that received the double-click
        """
        dispatcher.send("drill down", obj=act, act_of=self.system,
                        position=self.position)
        previous = self.subject
        self.subject = act
        self.set_new_scene()
        self.history.append(previous)

    def show_empty_scene(self):
        """
        Return an empty scene.
        """
        self.set_title()
        scene = QGraphicsScene()
        return scene

    def init_toolbar(self):
        self.toolbar = QToolBar(parent=self)
        self.toolbar.setObjectName('ActionsToolBar')
        self.plot_action = self.create_action(
                                    "graph",
                                    slot=self.plot,
                                    icon="graph",
                                    tip="graph")
        self.toolbar.addAction(self.plot_action)
        #create and add scene scale menu
        self.scene_scales = ["25%", "30%", "40%", "50%", "60%", "70%", "80%"]
        self.scene_scale_select = QComboBox()
        self.scene_scale_select.addItems(self.scene_scales)
        self.scene_scale_select.setCurrentIndex(5)
        self.scene_scale_select.currentIndexChanged[str].connect(
                                                    self.sceneScaleChanged)
        self.toolbar.addWidget(self.scene_scale_select)

    def delete_activity(self, oid=None, cname=None, remote=False):
        """
        Handle "deleted object" and "deleted activity" dispatcher signals.

        Keyword Args:
            oid (str): oid of the object to be deleted
        """
        orb.log.debug('* TimelineWidget.delete_activity(')
        orb.log.debug(f'      oid="{oid}", cname="{cname}", remote={remote})')
        if oid is None:
            return
        obj = orb.get(oid)
        if not obj:
            orb.log.debug(f'  - obj with oid "{oid}" not found.')
            return
        current_subacts = self.subject.sub_activities
        subj_oid = self.subject.oid
        if obj in current_subacts:
            orb.log.debug(f'  - obj "{obj.id}" in sub-activities --')
            orb.log.debug('    removing ...')
            objs_to_delete = [obj] + obj.sub_activities
            oids = [o.oid for o in objs_to_delete]
            orb.delete(objs_to_delete)
            if not remote:
                for oid in oids:
                    dispatcher.send("deleted object", oid=oid,
                                    cname='Activity')
            if oid == subj_oid:
                self.subject = None
                self.setEnabled(False)
            self.set_new_scene()
        else:
            # if activity is not in the current diagram, ignore
            return

    def sceneScaleChanged(self, percentscale):
        newscale = float(percentscale[:-1]) / 100.0
        self.view.setTransform(QTransform().scale(newscale, newscale))

    def on_rescale_timeline(self, percentscale=None):
        if percentscale in self.scene_scales:
            new_index = self.scene_scales.index(percentscale)
            self.scene_scale_select.setCurrentIndex(new_index)
        else:
            orb.log.debug(f'* rescale factor {percentscale} unavailable')

    def on_act_mod(self, act):
        if act is self.subject:
            self.set_title()

    def on_activity_modified(self, oid):
        activity = orb.get(oid)
        if not activity:
            return
        if activity is self.subject:
            self.set_title()
        if self.system is activity.of_system:
            self.set_new_scene()

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

    def plot(self):
        pass
        # orb.log.debug('* plot()')
        # if not self.subject.sub_activities:
            # message = "No activities were found -- nothing to plot!"
            # popup = QMessageBox(
                        # QMessageBox.Warning,
                        # "No Activities Found", message,
                        # QMessageBox.Ok, self)
            # popup.show()
            # return
        # # self is TimelineWidget -- parent is ConOpsModeler
        # win = QMainWindow(parent=self.parent())
        # area = DockArea()
        # win.setCentralWidget(area)
        # win.resize(self.parent().width(), 700)
        # win.setWindowTitle('pyqtgraph example: dockarea')
        # sys_dock = Dock("system dock", size=(600, 400))
        # sys_dock.hideTitleBar()
        # sys_name = 'Spacecraft'
        # w1 = pg.PlotWidget(title=f"{sys_name} Power Levels")
        # w1.plot(np.random.normal(size=100))
        # sys_dock.addWidget(w1)
        # area.addDock(sys_dock, 'left')
        # # Add subsystem docks ...
        # subsystems = ['ACS', 'Comm', 'Avionics', 'Power', 'Propulsion',
                      # 'Thermal']
        # subsys_docks = {}
        # previous_dock = None
        # for n, subsys in enumerate(subsystems):
            # # Note that size arguments are only a suggestion; docks will still
            # # have to fill the entire dock area and obey the limits of their
            # # internal widgets.
            # new_dock = Dock(subsys, size=(600, 200))
            # if n == 0:
                # area.addDock(new_dock, 'right', sys_dock)
            # else:
                # area.addDock(new_dock, 'bottom', previous_dock)
            # new_pw = pg.PlotWidget(title=subsys)
            # new_pw.plot(np.random.normal(size=100))
            # new_dock.addWidget(new_pw)
            # new_lr = pg.LinearRegionItem([1, 30], bounds=[0,100], movable=True)
            # new_pw.addItem(new_lr)
            # subsys_docks[subsys] = new_dock
            # previous_dock = new_dock

        # win.show()

        # act_durations= []
        # start_times = []
        # power = []
        # d_r = []
        # for sub_activity in self.subject.sub_activities:
            # oid = getattr(sub_activity, "oid", None)
            # act_durations.append(get_pval(oid, 'duration'))
            # start_times.append(get_pval(oid, 't_start'))
            # power.append(get_pval(oid, 'P[CBE]'))
            # d_r.append(get_pval(oid, 'R_D[CBE]'))

        # win = QMainWindow()
        # combo = pg.ComboBox()
        # combo.addItem("Data Rate")
        # # win.addWidget(combo)
        # # proxy = QGraphicsProxyWidget()
        # # # tree = QTreeWidget()
        # # # i1  = QTreeWidgetItem(["Item 1"])
        # # # tree.addTopLevelItem(i1)
        # # proxy.setWidget(combo)
        # area = DockArea()
        # win.setCentralWidget(area)
        # win.resize(1000,1000)
        # win.setWindowTitle('pyqtgraph example: dockarea')
        # d4 = Dock("Power", size=(500,500))
        # d6 = Dock("Data Rate", size=(500,500))
        # d7 = Dock("Subsystems", size=(500,200))
        # # p3 = win.addLayout(row=1, col=3)
        # # p3.addItem(proxy,row=1,col=1)
        # #layout.addItem(tree)
        # #win.addItem(tree)
        # area.addDock(d4, 'left')
        # area.addDock(d6, 'above', d4)
        # area.addDock(d7, 'right')
        # w6 = pg.PlotWidget()
        # w4 = pg.PlotWidget()
        # d6.addWidget(w6)
        # d4.addWidget(w4)
        # win.resize(800,350)
        # win.setWindowTitle(' ')
        # self.plot_win = win
        # t = ParameterTree(showHeader=False)
        # d7.addWidget(t)
        # #p = pg.parametertree.parameterTypes.ActionParameter("parent")
        # lst = []
        # for usage in self.system.components:
            # pair = {'name': usage.component}
            # lst.append(pair)
        # params = [{'name': self.subject.id, 'children': lst}]
        # p = Parameter.create(name='params', type='group', children=params)
        # t.addParameters(p, showTop=False)

        # duration = sum(act_durations)
        # s_time = min(start_times)
        # generated_x = []
        # generated_power = []
        # for count, d in enumerate(act_durations):
            # start = start_times[count]
            # end = start_times[count] + d
            # generated_x.append(start)
            # generated_x.append(end)
        # for c, y in enumerate(act_durations):
            # generated_power.extend([power[c], power[c]])
            # #.extend([power[c]]*(int(act_durations[c])+1))
        # w4.plot(generated_x, generated_power, brush=(0,0,255,150))

        # #plt2 = win.addPlot(title="Data Rate")
        # generated_dr = []
        # for d_index, d in enumerate(act_durations):
           # generated_dr.extend([d_r[d_index], d_r[d_index]])
        # w6.plot(generated_x, generated_dr, brush=(0,0,255,150))
        # win.show()


class ConOpsModeler(QMainWindow):
    """
    Tool for modeling a Concept of Operations for the currently selected
    project and system.

    GUI structure of the ConOpsModeler is:

    ConOpsModeler (QMainWindow)
        - activity_table (ActivityWidget)
        - main_timeline (TimelineWidget(QWidget))
          + scene (TimelineScene(QGraphicsScene))
            * timeline (Timeline(QGraphicsPathItem))
            * activity blocks (EventBlock(QGraphicsPolygonItem)
            * timelinebars (TimelineBar(QGraphicsPolygonItem))
              for each subsystem usage that is the "of_system"
              in the main_timeline:

    Then if a subsystem TimelineBar gets focus, the following are added for
    that subsystem:
        - activity_table (ActivityWidget)
        - sub_timeline (TimelineWidget(QWidget))
          + scene (TimelineScene(QGraphicsScene))
            * timeline (Timeline(QGraphicsPathItem))
            * activity blocks (EventBlock(QGraphicsPolygonItem)
        - sub_activity_table (ActivityWidget)
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
        project = orb.get(state.get('project'))
        if not project:
            project = orb.get('pgefobjects:SANDBOX')
        mission_name = ' '.join([project.id, 'Mission'])
        mission = None
        # NOTE: usage_list is only relevant if the subject is a Mission;
        # otherwise, only the usage value of the 'of_system' attribute of the
        # subject is relevant
        self.usage_list = []
        if project.systems:
            for psu in project.systems:
                self.usage_list.append(psu)
        if subject:
            self.subject = subject
        else:
            mission = orb.select('Mission', name=mission_name)
            if not mission:
                message = "This project had no Mission object; creating one."
                popup = QMessageBox(
                            QMessageBox.Information,
                            "Creating Mission Object", message,
                            QMessageBox.Ok, self)
                popup.show()
                mission_id = '_'.join([project.id, 'mission'])
                mission = clone('Mission', id=mission_id, name=mission_name,
                                owner=project)
                orb.save([mission])
                orb.log.debug('* ConOpsModeler: sending "new object" signal')
                dispatcher.send("new object", obj=mission)
            self.subject = mission
        self.project = project
        self.create_toolbox()
        self.init_toolbar()
        self.set_widgets(init=True)
        self.setWindowTitle('Concept of Operations (Con Ops) Modeler')
        # NOTE:  bottom dock area is not currently being used but may be used
        # for graphs in the future ...
        # self.bottom_dock = QDockWidget()
        # self.bottom_dock.setObjectName('BottomDock')
        # self.bottom_dock.setFeatures(QDockWidget.DockWidgetFloatable)
        # self.bottom_dock.setAllowedAreas(Qt.BottomDockWidgetArea)
        # self.addDockWidget(Qt.BottomDockWidgetArea, self.bottom_dock)
        dispatcher.connect(self.on_double_click, "double clicked")
        dispatcher.connect(self.on_activity_got_focus, "activity focused")
        dispatcher.connect(self.on_remote_mod_acts, "remote new or mod acts")

    def create_toolbox(self):
        """
        Create the toolbox for activities.
        """
        orb.log.debug(' - ConOpsModeler.create_toolbox() ...')
        acts_layout = QGridLayout()
        square = QPixmap(os.path.join( orb.home, 'images', 'square.png'))
        triangle = QPixmap(os.path.join(orb.home, 'images', 'triangle.png'))
        circle = QPixmap(os.path.join(orb.home, 'images', 'circle.png'))
        op_button = ToolButton(square, "")
        op_button.setData("Op")
        ev_button = ToolButton(triangle, "")
        ev_button.setData("Event")
        cyc_button = ToolButton(circle, "")
        cyc_button.setData("Cycle")
        acts_layout.addWidget(op_button, 0, 0)
        acts_layout.addWidget(NameLabel("Op"), 0, 1)
        acts_layout.addWidget(ev_button, 1, 0)
        acts_layout.addWidget(NameLabel("Event"), 1, 1)
        acts_layout.addWidget(cyc_button, 2, 0)
        acts_layout.addWidget(NameLabel("Cycle"), 2, 1)
        toolbox_widget = QWidget()
        toolbox_widget.setLayout(acts_layout)
        toolbox_widget.setStyleSheet('background-color: #dbffd6;')
        self.toolbox = QToolBox()
        self.toolbox.addItem(toolbox_widget, "Activities")
        # set an icon for Activities item ...
        act_icon_file = 'tools' + state.get('icon_type', '.png')
        act_icon_dir = state.get('icon_dir', os.path.join(orb.home, 'icons'))
        act_icon_path = os.path.join(act_icon_dir, act_icon_file)
        self.toolbox.setItemIcon(0, QIcon(act_icon_path))
        self.toolbox.setMinimumWidth(250)
        self.toolbox.setSizePolicy(QSizePolicy.Minimum,
                                   QSizePolicy.Fixed)

    def update_mode_tools(self):
        """
        Update the Modes section of the toolbox depending on the selected
        subject activity and system of the conops tool.
        """
        orb.log.debug(' - ConOpsModeler.update_mode_tools() ...')
        if isinstance(self.subject, orb.classes['Mission']):
            # if the subject is a Mission, no modes can be defined for it
            return
        modes_layout = QGridLayout()
        # get all defined modes for the current system ...
        # first make sure that mode_defz[project.oid] is initialized ...
        if not mode_defz.get(self.project.oid):
            mode_defz[self.project.oid] = dict(modes={}, systems={},
                                               components={})
        # Only populate "Modes" toolbox item if the subject Activity has an
        # "of_system" for which modes have been defined
        system_usage = getattr(self.subject, 'of_system', None)
        modes_title = 'No Modes Defined'
        if system_usage:
            if isinstance(system_usage, orb.classes['Acu']):
                sys_name = getattr(system_usage, 'reference_designator', None)
                if not sys_name:
                    sys = system_usage.component
                    sys_name = sys.name or sys.id
            elif isinstance(system_usage, orb.classes['ProjectSystemUsage']):
                sys_name = getattr(system_usage, 'system_role', None)
                if not sys_name:
                    sys = system_usage.system
                    sys_name = sys.name or sys.id
            else:
                sys_name = 'Unknown'
            modes_title = f'Modes of {sys_name}'
        # modes = ['Spam', 'Eggs', 'More Spam']
        modes = []
        systems = mode_defz[self.project.oid]['systems']
        components = mode_defz[self.project.oid]['components']
        # WORKING HERE ...
        # comp_modez = 
        # if (self.system.oid in systems and
            # len(systems.get(self.system.oid) or {}) > 0):
            # # system has modes defined -- add them
            # for mode_name in list(systems[self.system.oid]):
                # modes.append(mode_name)
        # elif (self.system.oid in components and
              # len(components.get(self.system.oid) or {}) > 0):
            # # system has modes defined -- add them
            # for mode_name in components[self.system.oid]:
        circle = QPixmap(os.path.join(orb.home, 'images', 'circle.png'))
        for i, mode in enumerate(modes):
            button = ToolButton(circle, "")
            button.setData(mode)
            modes_layout.addWidget(button, i, 0)
            modes_layout.addWidget(NameLabel(mode), i, 1)
        self.modes_widget = QWidget()
        self.modes_widget.setLayout(modes_layout)
        self.modes_widget.setStyleSheet('background-color: #ffccf9;')
        self.modes_widget.setAttribute(Qt.WA_DeleteOnClose)
        self.toolbox.addItem(self.modes_widget, modes_title)
        # set an icon for Modes item ...
        mode_icon_file = 'lander' + state.get('icon_type', '.png')
        mode_icon_dir = state.get('icon_dir', os.path.join(orb.home, 'icons'))
        mode_icon_path = os.path.join(mode_icon_dir, mode_icon_file)
        self.toolbox.setItemIcon(1, QIcon(mode_icon_path))

    def init_toolbar(self):
        orb.log.debug(' - ConOpsModeler.init_toolbar() ...')
        self.toolbar = self.addToolBar("Actions")
        self.toolbar.setObjectName('ActionsToolBar')
        self.modes_tool_button = SizedButton("Modes Tool")
        self.modes_tool_button.clicked.connect(self.display_modes_tool)
        self.toolbar.addWidget(self.modes_tool_button)

    def set_widgets(self, init=False):
        """
        Add TimelineWidgets and ActivityInfoTables containing all activities of
        the current system.

        Note that focusing (mouse click) on an activity in the timeline will
        make that activity the "current_activity" and restrict the graph
        display to that activity's power graph.

        Keyword Args:
            init (bool): initial instantiation
        """
        orb.log.debug(' - ConOpsModeler.set_widgets() ...')
        self.main_timeline = TimelineWidget(self.subject, position='main')
        self.main_timeline.setMinimumSize(1000, 300)
        self.sub_timeline = TimelineWidget(
                                        self.main_timeline.scene.current_focus,
                                        position='sub')
        self.sub_timeline.setEnabled(False)
        self.sub_timeline.setMinimumSize(1000, 300)
        self.outer_layout = QGridLayout()
        self.create_activity_table()
        self.outer_layout.addWidget(self.activity_table, 0, 0,
                                    alignment=Qt.AlignTop)
        self.outer_layout.addWidget(self.main_timeline, 0, 1)
        self.create_sub_activity_table()
        self.sub_activity_table.setEnabled(False)
        self.outer_layout.addWidget(self.sub_activity_table, 1, 0,
                                    alignment=Qt.AlignTop)
        self.outer_layout.addWidget(self.sub_timeline, 1, 1)
        self.widget = QWidget()
        self.widget.setMinimumSize(1500, 700)
        self.widget.setLayout(self.outer_layout)
        self.setCentralWidget(self.widget)
        if init:
            self.right_dock = QDockWidget()
            self.right_dock.setObjectName('RightDock')
            self.right_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
            self.right_dock.setAllowedAreas(Qt.RightDockWidgetArea)
            self.addDockWidget(Qt.RightDockWidgetArea, self.right_dock)
            self.right_dock.setWidget(self.toolbox)
        dispatcher.connect(self.rebuild_tables, "order changed")
        dispatcher.connect(self.on_new_activity, "new activity")
        dispatcher.connect(self.on_delete_activity, "delete activity")
        dispatcher.connect(self.on_delete_activity, "remove activity")
        dispatcher.connect(self.on_delete_activity, "deleted object")
        self.resize(self.layout().sizeHint())

    def create_activity_table(self):
        orb.log.debug("* ConOpsModeler.create_activity_table()")
        self.activity_table = ActivityWidget(self.subject, parent=self,
                                             position='main')
        # self.activity_table.setSizePolicy(QSizePolicy.Fixed,
                                          # QSizePolicy.Fixed)
        self.activity_table.setSizePolicy(QSizePolicy.Minimum,
                                          QSizePolicy.MinimumExpanding)
        self.activity_table.setAttribute(Qt.WA_DeleteOnClose)

    def create_sub_activity_table(self):
        orb.log.debug("* ConOpsModeler.create_sub_activity_table()")
        act = getattr(self.main_timeline.scene.current_focus, 'activity', None)
        self.sub_activity_table = ActivityWidget(act, parent=self,
                                                 position='sub')
        # self.sub_activity_table.setSizePolicy(QSizePolicy.Fixed,
                                              # QSizePolicy.Fixed)
        self.sub_activity_table.setSizePolicy(QSizePolicy.Minimum,
                                              QSizePolicy.MinimumExpanding)
        self.sub_activity_table.setAttribute(Qt.WA_DeleteOnClose)

    def rebuild_tables(self):
        self.rebuild_activity_table()
        self.rebuild_sub_activity_table()
        self.resize(self.layout().sizeHint())

    def rebuild_activity_table(self):
        orb.log.debug("* ConOpsModeler.rebuild_activity_table()")
        if getattr(self, 'activity_table', None):
            self.outer_layout.removeWidget(self.activity_table)
            self.activity_table.parent = None
            self.activity_table.close()
            self.activity_table = None
        self.create_activity_table()
        self.outer_layout.addWidget(self.activity_table, 0, 0)

    def rebuild_sub_activity_table(self):
        orb.log.debug("* ConOpsModeler.rebuild_sub_activity_table()")
        if getattr(self, 'sub_activity_table', None):
            self.outer_layout.removeWidget(self.sub_activity_table)
            self.sub_activity_table.parent = None
            self.sub_activity_table.close()
            self.sub_activity_table = None
        self.create_sub_activity_table()
        self.outer_layout.addWidget(self.sub_activity_table, 1, 0)

    def display_modes_tool(self):
        win = ModesTool(self.project, parent=self)
        win.show()

    def change_system(self, index):
        orb.log.debug("* ConOpsModeler.change_system()")
        self.system = self.usage_list[index]
        self.update_mode_tools()
        self.set_widgets()

    def resizeEvent(self, event):
        state['model_window_size'] = (self.width(), self.height())

    def on_double_click(self, act):
        orb.log.debug("  - ConOpsModeler.on_double_click()...")
        try:
            orb.log.debug(f'     + activity: {act.id}')
            if act.activity_type.id == 'cycle':
                self.main_timeline.widget_drill_down(act)
        except Exception as e:
            orb.log.debug("    exception occurred:")
            orb.log.debug(e)
        self.rebuild_tables()

    def on_activity_got_focus(self, act):
        """
        Set sub_timeline to show all sub_activities of the focused activity.
        """
        self.sub_timeline.subject = act
        self.sub_timeline.set_new_scene()
        self.sub_timeline.setEnabled(True)
        self.sub_activity_table.setEnabled(True)
        self.rebuild_tables()

    def on_new_activity(self, act):
        orb.log.debug("* ConOpsModeler.on_new_activity()")
        orb.log.debug(f'  sending "new object" signal on {act.id}')
        dispatcher.send("new object", obj=act)
        self.rebuild_tables()

    def on_delete_activity(self, oid=None, cname=None, remote=False):
        sub_tl = getattr(self, 'sub_timeline', None)
        if (sub_tl and
            oid == getattr(sub_tl.subject, 'oid', None)):
            sub_tl.set_new_scene()
            sub_tl.setEnabled(False)
            txt = 'No Activity Selected'
            title = f'<font color="red">{txt}</font>'
            sub_tl.title_widget.setText(title)
            self.rebuild_tables()
            self.sub_activity_table.setEnabled(False)

    def on_remote_mod_acts(self, oids=None):
        """
        Handle dispatcher "remote new or mod acts" signal.
        """
        self.main_timeline.set_new_scene()
        self.rebuild_tables()


if __name__ == '__main__':
    import sys
    # orb.start(home='junk_home', debug=True)
    orb.start(home='/home/waterbug/cattens_home_dev', debug=True)
    app = QApplication(sys.argv)
    mw = ConOpsModeler()
    mw.show()
    sys.exit(app.exec_())

