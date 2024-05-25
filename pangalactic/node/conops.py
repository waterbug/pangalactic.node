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
# from functools import reduce

# Louie
from louie import dispatcher

from PyQt5.QtCore import Qt, QPointF, QPoint, QRectF, QSize, QVariant
from PyQt5.QtGui import (QColor, QIcon, QCursor, QPainter, QPainterPath,
                         QPixmap, QPolygonF, QTransform)
# from PyQt5.QtGui import QGraphicsProxyWidget
from PyQt5.QtWidgets import (QAction, QApplication, QComboBox, QDockWidget,
                             QDialog, QMainWindow, QSizePolicy, QWidget,
                             QGraphicsItem, QGraphicsPolygonItem,
                             QGraphicsScene, QGraphicsView, QGridLayout,
                             QMenu, QGraphicsPathItem, QPushButton,
                             QVBoxLayout, QToolBar, QToolBox, QWidgetAction,
                             QMessageBox)
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
from pangalactic.core.names       import get_link_name
# from pangalactic.core.parametrics import get_pval
from pangalactic.core.parametrics import mode_defz
from pangalactic.core.utils.datetimes import dtstamp
from pangalactic.node.activities  import (DEFAULT_ACTIVITIES,
                                          ActivityWidget,
                                          ModeDefinitionDashboard,
                                          SystemSelectionView)
from pangalactic.node.buttons     import ToolButton
from pangalactic.node.diagrams.shapes import BlockLabel
from pangalactic.node.dialogs     import (DefineModesDialog,
                                          NotificationDialog)
# from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.utils       import pct_to_decimal
from pangalactic.node.widgets     import ColorLabel, NameLabel



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
            path.addEllipse(-50, 0, 100, 100)
            self.myPolygon = path.toFillPolygon(QTransform())
        self.setPolygon(self.myPolygon)
        self.block_label = BlockLabel(getattr(self.activity, 'name', '') or '',
                                      self, point_size=8)

    def update_block_label(self):
        try:
            self.block_label.set_text(getattr(self.activity, 'name', 'No Name')
                                      or 'No Name')
        except:
            # our C++ object probably got deleted ...
            pass

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        dispatcher.send("double clicked", act=self.activity)

    def contextMenuEvent(self, event):
        self.menu = QMenu()
        self.menu.addAction(self.delete_action)
        # self.menu.addAction(self.edit_action)
        self.menu.exec(QCursor.pos())

    def create_actions(self):
        self.delete_action = QAction("Delete", self.scene,
                                     statusTip="Delete Activity",
                                     triggered=self.delete_block_activity)

    def edit_activity(self):
        self.scene.edit_scene_activity(self.activity)

    def delete_block_activity(self):
        orb.log.debug(' - dipatching "delete activity" signal')
        self.scene.removeItem(self)
        dispatcher.send(signal='delete activity', oid=self.activity.oid)

    def itemChange(self, change, value):
        return value

    def mousePressEvent(self, event):
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)

BAR_COLORS = ['red', 'darkRed', 'green', 'darkGreen', 'blue',
              'darkBlue', 'cyan', 'darkCyan', 'magenta', 'darkMagenta',
              'yellow', 'darkYellow', 'gray', 'darkGray', 'lightGray']
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

    def __init__(self, subject=None, scene=None, style=None, x_start=10, 
                 x_end=1000, color=Qt.cyan, timeline_length=None, parent=None):
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
        if timeline_length is not None:
            x_end = timeline_length
        tb_start = x_start + 90
        self.polygon = QPolygonF([
                QPointF(tb_start, 400), QPointF(x_end, 400),
                QPointF(x_end, 380), QPointF(tb_start, 380)])
        self.setPolygon(self.polygon)
        self.block_label = BlockLabel(getattr(self.subject, 'name', '') or '',
                                      self, point_size=8)


class TimelineView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)

    def minimumSize(self):
        return QSize(800, 500)

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
        self.path_length = 1200
        self.make_path()

    def update_timeline(self):
        orb.log.debug('* timeline.update_timeline()')
        self.calc_length()
        self.make_path()
        self.arrange()

    def calc_length(self):
        orb.log.debug('* timeline.calc_length()')
        self.path_length = 1200
        if len(self.evt_blocks) <= 8:
            orb.log.debug('  <= 8 event blocks ... no length re-calc.')
        else:
            n = len(self.evt_blocks)
            orb.log.debug(f'  {n} event blocks -- calculating length ...')
            # adjust timeline length
            delta = n - 7
            self.path_length = 1200 + (delta // 2) * 300

    def make_path(self):
        self.path = QPainterPath(QPointF(100, 250))
        self.path.arcTo(QRectF(0, 200, 100, 100), 0, 360)
        self.circle_length = self.path.length()
        self.path.arcTo(QRectF(self.path_length, 200, 100, 100), 180, 360)
        self.setPath(self.path)
        length = round(self.path.length() - 2 * self.circle_length)
        factor = length // (len(self.evt_blocks) + 1)
        self.list_of_pos = [(n+1) * factor + 100
                            for n in range(0, len(self.evt_blocks))]

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
        dispatcher.send("order changed")
        self.update()

    def add_evt_block(self, evt_block):
        self.evt_blocks.append(evt_block)
        self.update_timeline()

    def populate(self, evt_blocks):
        self.evt_blocks = evt_blocks
        self.update_timeline()


class TimelineScene(QGraphicsScene):

    def __init__(self, parent, activity):
        super().__init__(parent)
        orb.log.debug('* TimelineScene()')
        self.subject = activity
        if activity:
            self.act_of = activity.of_system
            name = getattr(self.act_of, 'name', None) or 'None'
            orb.log.debug(f'* TimelineScene act_of: {name}')
        self.timeline = Timeline()
        self.addItem(self.timeline)
        self.focusItemChanged.connect(self.focus_changed_handler)
        self.current_focus = None
        self.grabbed_item = None
        self.setSceneRect(QRectF(150.0, 150.0, 1200.0, 300.0))
        width = self.sceneRect().width()
        height = self.sceneRect().height()
        orb.log.debug(f'* TimelineScene size: ({width}, {height}).')
        dispatcher.connect(self.on_act_mod, "act mod")

    def focus_changed_handler(self, new_item, old_item):
        if getattr(self, "right_button_pressed", False):
            # ignore: context menu event
            self.right_button_pressed = False
            return
        elif (new_item is not None and
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
        self.timeline.update_timeline()
        orb.log.debug('* scene: sending "new activity" signal')
        dispatcher.send(signal="new activity", act=activity)
        self.update()

    def on_act_mod(self, act=None):
        """
        Handle 'act mod' signal from ActivityInfoTable, meaning an activity was
        modified.
        """
        orb.log.debug('* scene: received "act mod" signal')
        for item in self.timeline.evt_blocks:
            # orb.log.debug(f'  checking for {item.activity.name} by oid')
            if item.activity.oid == act.oid:
                item.update_block_label()
                dispatcher.send("modified object", obj=item.activity)

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)


# TODO:  the TimelineWidget should display the timeline of either
# (1) if TimelineWidget activity is the Mission, a selected project system or
# group of systems (e.g. a selected SC, all SC's, ground system, all of the
# above, etc.), or
# (2) if TimelineWidget activity is a non-Mission activity instance, all of
# its sub-activities

# TODO: implement "back" based on history

class TimelineWidget(QWidget):
    """
    Widget to contain the timeline scene with activity blocks.

    Attrs:
        history (list):  list of previous parent Activity instances
    """

    def __init__(self, subject, parent=None):
        """
        Initialize TimelineWidget.

        Keyword Args:
            subject (Activity):  the activity the timeline represents
            parent (QGraphicsItem): parent of this item
        """
        super().__init__(parent=parent)
        orb.log.debug(' - initializing TimelineWidget ...')
        self.subject = subject
        state['timeline history'] = [subject.oid]
        self.init_toolbar()
        self.scale = 70
        # set_new_scene() calls self.set_title(), which sets a title_widget
        self.set_new_scene()
        self.br = self.scene.itemsBoundingRect()
        layout = QVBoxLayout()
        layout.addWidget(self.title_widget)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.view)
        self.setLayout(layout)
        self.current_subsystem_index = 0
        self.deleted_acts = []
        dispatcher.connect(self.delete_activity, "deleted object")
        # "delete activity" is sent by event block when it is removed ...
        dispatcher.connect(self.delete_activity, "delete activity")
        dispatcher.connect(self.on_act_mod, "act mod")
        self.setUpdatesEnabled(True)

    @property
    def system(self):
        return getattr(self.subject, 'of_system', None) or None

    def minimumSize(self):
        return QSize(800, 500)

    def set_new_scene(self):
        """
        Return a new scene with new subject activity or an empty scene if no
        subject activity.
        """
        orb.log.debug(' - set_new_scene ...')
        scene = TimelineScene(self, self.subject)
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
        elif len(self.subject.sub_activities) == 0:
            ada = getattr(self, 'add_defaults_action', None)
            if ada:
                self.add_defaults_action.setEnabled(True)
        self.set_title()
        if not getattr(self, 'view', None):
            self.view = TimelineView(self)
        self.scene = scene
        # ---------------------------------------------------------------------
        # add the timelinebar here -- it needs timeline.path_length
        # ... also do update_timeline to rescale if necessary ...
        # which has to be done *after* the TimelineView is created, because
        # TimelineView controls the scaling of the scene, which is done in the
        # update_timeline() ...
        scene.timeline.update_timeline()
        length = scene.timeline.path_length
        orb.log.debug(f'  creating timelinebar with length {length}')
        scene.timelinebar = TimelineBar(timeline_length=length)
        scene.addItem(scene.timelinebar)
        # ---------------------------------------------------------------------
        self.view.setScene(self.scene)
        self.auto_rescale_timeline()
        self.view.show()

    def set_title(self):
        # try:
        if not getattr(self, 'title_widget', None):
            self.title_widget = NameLabel('')
            self.title_widget.setStyleSheet(
                'font-weight: bold; font-size: 14px')
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
        displaying a new timeline for its sub-activities.

        Args:
            obj (EventBlock):  the block that received the double-click
        """
        dispatcher.send("drill down", obj=act, act_of=self.system)
        previous_oid = self.subject.oid
        self.subject = act
        self.set_new_scene()
        self.back_action.setEnabled(True)
        self.clear_history_action.setEnabled(True)
        if state.get('timeline history'):
            state['timeline history'].append(previous_oid)
        else:
            state['timeline history'] = [previous_oid]
        dispatcher.send("new timeline", subject=act)

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
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.back_action = self.create_action(
                                    text="back",
                                    slot=self.load_last_timeline,
                                    icon="back",
                                    tip="Back to last timeline")
        self.back_action.setEnabled(False)
        self.toolbar.addAction(self.back_action)
        self.clear_history_action = self.create_action(
                                    text="clear history",
                                    slot=self.clear_history,
                                    tip="Clear timeline history")
        self.clear_history_action.setEnabled(False)
        self.add_defaults_action = self.create_action(
                                    "add default activities",
                                    slot=self.add_default_activities,
                                    icon="tools",
                                    tip="add default activities")
        self.toolbar.addAction(self.clear_history_action)
        self.plot_action = self.create_action(
                                    text="graph",
                                    slot=self.plot,
                                    icon="graph",
                                    tip="graph")
        self.toolbar.addAction(self.plot_action)
        spacer = QWidget(parent=self)
        spacer.setSizePolicy(QSizePolicy.Expanding,
                             QSizePolicy.Expanding)
        self.toolbar.addWidget(spacer)
        #create and add scene scale menu
        self.scene_scales = ["25%", "30%", "40%", "50%", "60%", "70%", "80%"]
        self.scene_scale_select = QComboBox()
        self.scene_scale_select.addItems(self.scene_scales)
        self.scene_scale_select.setCurrentIndex(5)
        self.scene_scale_select.currentIndexChanged.connect(
                                                    self.sceneScaleChanged)
        self.toolbar.addWidget(self.scene_scale_select)

    def load_last_timeline(self):
        """
        Handle dispatcher signal for "comp modeler back" (sent by
        ProductInfoPanel): load the last product from history and remove it
        from the stack.
        """
        orb.log.debug('* load last timeline')
        if state.get('timeline history'):
            oid = state['timeline history'].pop() or ''
            self.subject = orb.get(oid)
            self.set_new_scene()
            if state.get('timeline history'):
                if len(state['timeline history']) > 1:
                    self.back_action.setEnabled(True)
                    self.clear_history_action.setEnabled(True)
                else:
                    self.back_action.setEnabled(False)
                    self.clear_history_action.setEnabled(False)
            dispatcher.send("new timeline", subject=self.subject)

    def clear_history(self):
        orb.log.debug('* clear timeline history')
        state['timeline history'] = [self.subject.oid]
        self.back_action.setEnabled(False)
        self.clear_history_action.setEnabled(False)

    def add_default_activities(self):
        orb.log.debug('* creating default activities ...')
        acts = []
        seq = 0
        for name in DEFAULT_ACTIVITIES:
            activity_type = orb.get(
                            "pgefobjects:ActivityType.Operation")
            project = orb.get(state.get('project'))
            prefix = project.id
            act_id = '-'.join([prefix, name])
            act_name = name
            NOW = dtstamp()
            user = orb.get(state.get('local_user_oid') or 'me')
            activity = clone("Activity", id=act_id, name=act_name,
                             activity_type=activity_type,
                             owner=project,
                             sub_activity_of=self.subject,
                             sub_activity_sequence=seq,
                             create_datetime=NOW, mod_datetime=NOW,
                             creator=user, modifier=user)
            orb.db.commit()
            acts.append(activity)
            seq += 1
        orb.save(acts)
        orb.log.debug('* sending "new objects" signal')
        dispatcher.send("new objects", objs=acts)

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
        subj_oid = getattr(self.subject, 'oid', '')
        name = getattr(obj, 'name', None) or '[no name]'
        if remote:
            if oid == subj_oid:
                project = orb.get(state.get('project'))
                mission = orb.select('Mission', owner=project)
                self.subject = mission
                self.set_new_scene()
            else:
                current_act_oids = [getattr(act, 'oid', '') for act in
                                    self.subject.sub_activities]
                if oid in current_act_oids:
                    # find event block and remove it
                    for item in self.scene.items():
                        if (hasattr(item, 'activity') and
                            item.activity and item.activity.oid == oid):
                            act = item.activity
                            self.scene.remove(item)
                            if item in self.scene.timeline.evt_blocks:
                                self.scene.timeline.evt_blocks.remove(item)
                            item.deleteLater()
                            orb.delete([act])
                            dispatcher.send("deleted object", oid=oid,
                                            cname='Activity')
                self.set_new_scene()
        else:
            # locally originated action ...
            orb.log.debug(f'  - deleting activity {name}')
            objs_to_delete = [obj] + obj.sub_activities
            # TODO: check whether any sub_activities have event blocks ...
            oids = [o.oid for o in objs_to_delete]
            orb.delete(objs_to_delete)
            for oid in oids:
                dispatcher.send("deleted object", oid=oid,
                                cname='Activity')
            if oid == subj_oid:
                self.subject = None
            self.set_new_scene()

    def sceneScaleChanged(self, index):
        percentscale = self.scene_scales[index]
        orb.log.debug(f'* rescaling to {percentscale}')
        newscale = pct_to_decimal(percentscale)
        self.view.setTransform(QTransform().scale(newscale, newscale))

    def auto_rescale_timeline(self):
        orb.log.debug('* auto_rescale_timeline()')
        n = len(self.scene.timeline.evt_blocks)
        if n <= 8:
            orb.log.debug('  <= 8 event blocks ... no rescale.')
            self.scale = 70
        else:
            orb.log.debug(f'  {n} event blocks -- rescaling ...')
            delta = n - 7
            self.scale = 70 - (delta // 2) * 10
        pscale = str(self.scale) + "%"
        orb.log.debug(f'  new scale is {pscale}')
        length = self.scene.timeline.path_length
        # adjust size of timelinebar, if there is one ...
        tlb = getattr(self.scene, 'timelinebar', None)
        if tlb:
            # TODO: in future, more adjustments may be needed!
            orb.log.debug(f'  adjusting timelinebar to path length {length}')
            tlb_start = 100
            x_end = length
            polygon = QPolygonF([
                            QPointF(tlb_start, 400), QPointF(x_end, 400),
                            QPointF(x_end, 380), QPointF(tlb_start, 380)])
            tlb.setPolygon(polygon)
        new_index = self.scene_scales.index(pscale)
        self.scene_scale_select.setCurrentIndex(new_index)
        self.sceneScaleChanged(new_index)
        self.scene.update()
        self.center_timeline()

    def center_timeline(self):
        """
        Adjust the viewport dimensions and center the timeline in it.
        """
        orb.log.debug('* center_timeline()')
        br = self.scene.itemsBoundingRect()
        br_parms = (br.x(), br.y(), br.width(), br.height())
        orb.log.debug(f'  scene items bounding rect: ({br_parms})')
        vp_x = -50.0
        vp_y = br.y() - 20
        vp_width = br.width() + 50.0
        vp_height = br.height() + 50.0
        vp_rect = QRectF(vp_x, vp_y, vp_width, vp_height)
        self.view.setSceneRect(vp_rect)
        vp_parms = (vp_x, vp_y, vp_width, vp_height)
        orb.log.debug(f'  viewport: ({vp_parms})')
        # self.get_scene_coords()

    def get_scene_coords(self):
        br = self.scene.itemsBoundingRect()
        self.br = br
        br_parms = (br.x(), br.y(), br.width(), br.height())
        orb.log.debug(f'  scene items bounding rect: ({br_parms})')
        tlb_br = self.scene.timelinebar.boundingRect()
        tlb_parms = (tlb_br.x(), tlb_br.y(), tlb_br.width(), tlb_br.height())
        orb.log.debug(f'  scene coords of timelinebar: ({tlb_parms})')
        view_polygon = self.view.mapFromScene(
                                    br.x(), br.y(), br.width(), br.height())
        vbr = view_polygon.boundingRect()
        vbr_parms = (vbr.x(), vbr.y(), vbr.width(), vbr.height())
        orb.log.debug(f'  view coords of bounding rect: ({vbr_parms})')
        # find the view origin (0, 0) in scene coordinates ...
        v_origin = self.view.mapToScene(0, 0)
        vo_coords = (v_origin.x(), v_origin.y())
        orb.log.debug(f'  scene coords of view origin: ({vo_coords})')

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

    def create_action(self, text=None, slot=None, icon=None, tip=None,
                      checkable=False):
        action = QWidgetAction(self)
        button = QPushButton(self)
        action.setDefaultWidget(button)
        if icon is not None:
            icon_file = icon + state.get('icon_type', '.png')
            icon_dir = state.get('icon_dir', os.path.join(orb.home, 'icons'))
            icon_path = os.path.join(icon_dir, icon_file)
            button.setIcon(QIcon(icon_path))
        if tip is not None:
            button.setToolTip(tip)
            # action.setStatusTip(tip)
        if text:
            button.setText(text)
        if slot is not None:
            button.clicked.connect(slot)
        if checkable:
            button.setCheckable(True)
        return action

    def plot(self):
        orb.log.debug('* plot()')
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
    project or usage (Acu or ProjectSystemUsage).

    GUI structure of the ConOpsModeler is:

    ConOpsModeler (QMainWindow)
    ---------------------------
      * CentralWidget contains:
        - main_timeline (TimelineWidget(QWidget))
          + scene (TimelineScene(QGraphicsScene))
            * timeline (Timeline(QGraphicsPathItem))
            * activity blocks (EventBlock(QGraphicsPolygonItem))
            * timelinebar (TimelineBar(QGraphicsPolygonItem))
        - mode_dash (ModeDefinitionDashboard(QWidget))
      * Left Dock contains:
        - sys_select_tree (SystemSelectionView)
        - activity_table (ActivityWidget)
      * Right Dock contains:
        - Op blocks palette (QToolBox)
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
        mission_name = ' '.join([proj_id, 'Mission'])
        self.mission = orb.select('Mission', name=mission_name,
                                  owner=self.project)
        if not self.mission:
            orb.log.debug('* [ConOps] creating a new Mission ...')
            message = f"{proj_id} had no Mission object; creating one ..."
            popup = QMessageBox(
                        QMessageBox.Information,
                        "Creating Mission Object", message,
                        QMessageBox.Ok, self)
            popup.show()
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
        if not mode_defz.get(self.project.oid):
            mode_defz[self.project.oid] = dict(modes={},
                                               systems={},
                                               components={})
        if mode_defz[self.project.oid]['systems']:
            for link_oid in mode_defz[self.project.oid]['systems']:
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
        self.create_toolbox()
        self.init_toolbar()
        self.set_widgets()
        self.setWindowTitle('Concept of Operations (ConOps) Modeler')
        dispatcher.connect(self.on_double_click, "double clicked")
        dispatcher.connect(self.on_activity_got_focus, "activity focused")
        dispatcher.connect(self.on_remote_mod_acts, "remote new or mod acts")

    @property
    def project(self):
        proj = orb.get(state.get('project'))
        if not proj:
            proj = orb.get('pgefobjects:SANDBOX')
        self._project = proj
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
        if isinstance(val, (orb.classes['ProjectSystemUsage'],
                            orb.classes['Acu'])):
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
        # NOTE: toolbar is currently empty but may have a role later ...
        orb.log.debug(' - ConOpsModeler.init_toolbar() ...')
        self.toolbar = self.addToolBar("Actions")
        self.toolbar.setObjectName('ActionsToolBar')

    def create_toolbox(self):
        """
        Create the toolbox for activities and modes.
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
        self.toolbox.setMinimumWidth(150)
        self.toolbox.setSizePolicy(QSizePolicy.Minimum,
                                   QSizePolicy.Fixed)

    def set_widgets(self):
        """
        Add a TimelineWidget and ActivityInfoTable containing all
        sub-activities of the "subject" (current activity), and the Mission
        Systems selection tree and ModeDefinitionDashboard.

        Note that focusing (mouse click) on an activity in the timeline will
        make that activity the "current_activity" and restrict the graph
        display to that activity's power graph.
        """
        orb.log.debug(' - ConOpsModeler.set_widgets() ...')
        self.main_timeline = TimelineWidget(self.subject)
        self.main_timeline.setSizePolicy(QSizePolicy.MinimumExpanding,
                                         QSizePolicy.Fixed)
        central_layout = QVBoxLayout()
        central_layout.addWidget(self.main_timeline, alignment=Qt.AlignTop)
        self.widget = QWidget()
        self.widget.setMinimumSize(1000, 700)
        self.widget.setLayout(central_layout)
        self.setCentralWidget(self.widget)
        # ====================================================================
        self.left_dock = QDockWidget()
        self.left_dock.setObjectName('LeftDock')
        self.left_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.left_dock.setAllowedAreas(Qt.LeftDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.left_dock)
        self.left_dock_panel = QWidget()
        self.left_dock_layout = QVBoxLayout(self.left_dock_panel)
        self.create_activity_table()
        self.left_dock_layout.addWidget(self.activity_table,
                                        alignment=Qt.AlignTop)
        # ====================================================================
        self.expansion_select = QComboBox()
        self.expansion_select.setStyleSheet(
                                        'font-weight: bold; font-size: 14px')
        self.expansion_select.addItem('2 levels', QVariant())
        self.expansion_select.addItem('3 levels', QVariant())
        self.expansion_select.addItem('4 levels', QVariant())
        self.expansion_select.addItem('5 levels', QVariant())
        self.expansion_select.currentIndexChanged.connect(
                                                self.set_select_tree_expansion)
        # -- set initial value of tree expansion level select -----------------
        if 'conops_tree_expansion' not in state:
            state['conops_tree_expansion'] = {}
        if self.project.oid in state['conops_tree_expansion']:
            self.expansion_select.setCurrentIndex(
                state['conops_tree_expansion'][self.project.oid])
        else:
            state['conops_tree_expansion'][self.project.oid] = 0
        # ---------------------------------------------------------------------
        sys_tree_title = f'{self.project.id} Mission Systems'
        sys_tree_title_widget = ColorLabel(sys_tree_title, element='h2')
        self.sys_select_tree = SystemSelectionView(self.project,
                                                   refdes=True)
        self.sys_select_tree.setSizePolicy(QSizePolicy.Preferred,
                                           QSizePolicy.MinimumExpanding)
        self.sys_select_tree.setObjectName('Sys Select Tree')
        self.sys_select_tree.setMinimumWidth(400)
        # -- set initial tree expansion level ---------------------------------
        expand_level = 1
        idx = state['conops_tree_expansion'][self.project.oid]
        expand_level = idx + 1
        self.sys_select_tree.expandToDepth(expand_level)
        # ---------------------------------------------------------------------
        self.sys_select_tree.setExpandsOnDoubleClick(False)
        self.sys_select_tree.clicked.connect(self.on_item_clicked)
        sys_tree_layout = QVBoxLayout()
        sys_tree_layout.setObjectName('Sys Tree Layout')
        sys_tree_layout.addWidget(sys_tree_title_widget,
                                  alignment=Qt.AlignTop)
        sys_tree_layout.addWidget(self.expansion_select)
        sys_tree_layout.addWidget(self.sys_select_tree,
                                  stretch=1)
        self.left_dock_layout.addLayout(sys_tree_layout, stretch=1)
        self.left_dock.setWidget(self.left_dock_panel)
        # ====================================================================
        self.mode_dash = ModeDefinitionDashboard(parent=self,
                                                 activity=self.mission)
        self.right_dock = QDockWidget()
        self.right_dock.setObjectName('RightDock')
        self.right_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.right_dock.setAllowedAreas(Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.RightDockWidgetArea, self.right_dock)
        self.right_dock.setWidget(self.toolbox)
        # ====================================================================
        self.mode_dash.setObjectName('Mode Dash')
        mode_dash_layout = QVBoxLayout()
        mode_dash_layout.setObjectName('Mode Dash Layout')
        mode_dash_layout.addWidget(self.mode_dash, alignment=Qt.AlignTop)
        central_layout.addLayout(mode_dash_layout, stretch=1)
        # ====================================================================
        dispatcher.connect(self.rebuild_table, "order changed")
        dispatcher.connect(self.on_new_timeline, "new timeline")
        dispatcher.connect(self.on_new_activity, "new activity")
        dispatcher.connect(self.on_delete_activity, "delete activity")
        dispatcher.connect(self.on_delete_activity, "remove activity")
        dispatcher.connect(self.on_delete_activity, "deleted object")

    def set_select_tree_expansion(self, index=None):
        if index is None:
            index = state.get('conops_tree_expansion', {}).get(
                                                self.project.oid) or 0
        # NOTE:  levels are 2 to 5, so level = index + 2
        #        expandToDepth(n) actually means level n + 1
        try:
            level = index + 2
            self.sys_select_tree.expandToDepth(level - 1)
            state['conops_tree_expansion'][self.project.oid] = index
            # orb.log.debug(f'* tree expanded to level {level}')
        except:
            orb.log.debug('* conops tree expansion failed.')
            pass
        finally:
            # orb.log.debug('* setting selected conops system ...')
            # after expanding, set the selected system
            dispatcher.send(signal='set selected conops system')

    def create_activity_table(self):
        orb.log.debug("* ConOpsModeler.create_activity_table()")
        self.activity_table = ActivityWidget(self.subject, parent=self)
        self.activity_table.setAttribute(Qt.WA_DeleteOnClose)

    def on_new_timeline(self, subject=None):
        """
        Respond to a new timeline scene having been set, such as resulting from
        an event block drill-down.

        Keyword Args:
            subject (Activity): subject of the new timeline
        """
        orb.log.debug("* conops: on_new_timeline()")
        self.subject = subject
        self.rebuild_activity_table()
        self.resize(self.layout().sizeHint())

    def rebuild_table(self):
        orb.log.debug("* conops: rebuild_table()")
        self.rebuild_activity_table()
        self.resize(self.layout().sizeHint())

    def rebuild_activity_table(self):
        orb.log.debug("* ConOpsModeler.rebuild_activity_table()")
        if getattr(self, 'activity_table', None):
            self.left_dock_layout.removeWidget(self.activity_table)
            self.activity_table.parent = None
            self.activity_table.close()
            self.activity_table = None
        self.create_activity_table()
        self.left_dock_layout.insertWidget(0, self.activity_table,
                                           alignment=Qt.AlignTop)

    def on_item_clicked(self, index):
        orb.log.debug("* ConOpsModeler.on_item_clicked()")
        if isinstance(self.mode_dash.act, orb.classes['Mission']):
            msg = 'Select an activity first ...'
            dlg = NotificationDialog(msg, news=False, parent=self)
            dlg.show()
            return
        mapped_i = self.sys_select_tree.proxy_model.mapToSource(index)
        link = self.sys_select_tree.source_model.get_node(mapped_i).link
        name = get_link_name(link)
        orb.log.debug(f"  - clicked item usage is {name}")
        TBD = orb.get('pgefobjects:TBD')
        product = None
        attr = '[none]'
        if isinstance(link, orb.classes['ProjectSystemUsage']):
            if link.system:
                product = link.system
                attr = '[system]'
        elif isinstance(link, orb.classes['Acu']):
            if link.component and link.component is not TBD:
                product = link.component
                attr = '[component]'
        orb.log.debug(f"  - product {attr} is {product.name}")
        if product:
            # usage should be made the subject's "of_system" if it exists in
            # sys_dict (i.e. if it is of interest in defining modes ...)
            project_mode_defz = mode_defz[self.project.oid]
            sys_dict = project_mode_defz['systems']
            # all_comp_acu_oids = reduce(lambda x,y: x+y,
                # [list(project_mode_defz['components'].get(sys_oid, {}).keys())
                 # for sys_oid in sys_dict], [])
            if link.oid in sys_dict:
                orb.log.debug("  - link oid is in sys_dict")
                # set as subject's usage
                self.set_usage(link)
                # signal to mode_dash to set this link as its usage ...
                orb.log.debug('    sending "set mode usage" signal ...')
                dispatcher.send(signal='set mode usage', usage=link)
            else:
                orb.log.debug("  - link oid is NOT in sys_dict")
                # the item does not yet exist in mode_defz as a system
                # -- notify the user and ask if they want to
                # define modes for it ...
                dlg = DefineModesDialog(usage=link)
                if dlg.exec_() == QDialog.Accepted:
                    orb.log.debug('    calling on_add_usage() ..."')
                    self.on_add_usage(index)
                else:
                    # TODO: maybe change focus to project node (?)
                    return

    def on_add_usage(self, index):
        """
        If the item (aka "link" or "node") in the assembly tree does not exist
        in the the mode definitions "systems" table, add it, and if it has
        components, add them to the mode definitions "components" table.

        If the item already exists in the "systems" table, remove it and remove
        its components from the "components" table, and if it is a component of
        an item in the "systems" table, add it back to the "components" table.
        """
        orb.log.debug('  - updating mode_defz ...')
        mapped_i = self.sys_select_tree.proxy_model.mapToSource(index)
        link = self.sys_select_tree.source_model.get_node(mapped_i).link
        # link might be None -- allow for that
        if not hasattr(link, 'oid'):
            orb.log.debug('  - link has no oid, ignoring ...')
            return
        name = get_link_name(link)
        project_mode_defz = mode_defz[self.project.oid]
        sys_dict = project_mode_defz['systems']
        comp_dict = project_mode_defz['components']
        mode_dict = project_mode_defz['modes']
        in_comp_dict = False
        # if link.oid in sys_dict:
            # # if selected link is in sys_dict, make subject (see below)
            # orb.log.debug(f' - removing "{name}" from systems ...')
            # del sys_dict[link.oid]
            # # if it is in comp_dict, remove it there too
            # if link.oid in comp_dict:
                # del comp_dict[link.oid]
            # # if it occurs as a component of an item in sys_dict, add it back
            # # to components
            # orb.log.debug(f'   checking if "{name}" is a component ...')
            # for syslink_oid in sys_dict:
                # lk = orb.get(syslink_oid)
                # clink_oids = []
                # if hasattr(lk, 'system') and lk.system.components:
                    # clink_oids = [acu.oid for acu in lk.system.components]
                # elif hasattr(lk, 'component') and lk.component.components:
                    # clink_oids = [acu.oid for acu in lk.component.components]
                # if link.oid in clink_oids:
                    # orb.log.debug(f' - "{name}" is a component, adding it')
                    # orb.log.debug('   back to components of its parent')
                    # if not comp_dict.get(syslink_oid):
                        # comp_dict[syslink_oid] = {}
                    # comp_dict[syslink_oid][link.oid] = {}
                    # for mode in mode_dict:
                        # comp_dict[syslink_oid][link.oid][
                                                # mode] = (mode_dict.get(mode)
                                                         # or '[select state]')
        # else:
        if link.oid not in sys_dict:
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
                        orb.log.debug(' - item selected has no components')
                        orb.log.debug('   -- operation ignored.')
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
                            context = context or '[select level]'
                            sys_dict[link.oid][mode] = context
        # ensure that all selected systems (sys_dict) that have components,
        # have those components included in comp_dict ...
        product = None
        for syslink_oid in sys_dict:
            link = orb.get(syslink_oid)
            if hasattr(link, 'system'):
                product = link.system
            elif hasattr(link, 'component'):
                product = link.component
            if (product and product.components and not comp_dict.get(link.oid)):
                comp_dict[link.oid] = {}
                acus = [acu for acu in product.components
                        if acu.oid not in sys_dict]
                # sort by "name" (so order is the same as in the assembly tree)
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
        if in_comp_dict and has_components:
            # if this usage was in the comp_dict and it has components, it has
            # now been added to the sys_dict -- make it the subject usage ...
            self.set_usage(link)
        elif link.oid in sys_dict:
            # if this usage was in the sys_dict, make it the subject usage ...
            self.set_usage(link)
        # dispatcher.send(signal='modes edited', oid=self.project.oid)
        # signal to the mode_dash to set this link as its usage
        dispatcher.send(signal='set mode usage', usage=link)

    def set_usage(self, usage):
        orb.log.debug("* ConOpsModeler.set_usage()")
        self.usage = usage

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
            orb.log.debug(f'     + activity: {act.id}')
            self.main_timeline.widget_drill_down(act)
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

    def on_new_activity(self, act):
        """
        Handler for "new activity" dispatcher signal.

        Args:
            act (Activity): the new Activity instance
        """
        orb.log.debug("* ConOpsModeler.on_new_activity()")
        orb.log.debug(f'  sending "new object" signal on {act.id}')
        self.main_timeline.auto_rescale_timeline()
        dispatcher.send("new object", obj=act)
        self.rebuild_table()

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

    def on_remote_mod_acts(self, oids=None):
        """
        Handle dispatcher "remote new or mod acts" signal.

        Keyword Args:
            oids (list of str): oids of the new or modified Activity instances
        """
        self.main_timeline.set_new_scene()
        self.rebuild_table()


if __name__ == '__main__':
    import sys
    # orb.start(home='junk_home', debug=True)
    orb.start(home='/home/waterbug/cattens_home_dev', debug=True)
    app = QApplication(sys.argv)
    mw = ConOpsModeler()
    mw.show()
    sys.exit(app.exec_())

