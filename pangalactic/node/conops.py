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

import numpy as np

import sys, os
# from functools import reduce

# Louie
from louie import dispatcher

from PyQt5.QtCore import Qt, QPointF, QPoint, QRectF, QSize, QVariant
from PyQt5.QtGui import (QBrush, QIcon, QCursor, QFont, QPainter,
                         QPainterPath, QPen, QPixmap, QPolygonF, QTransform)
# from PyQt5.QtGui import QGraphicsProxyWidget
from PyQt5.QtWidgets import (QAction, QApplication, QComboBox, QDockWidget,
                             QDialog, QMainWindow, QSizePolicy, QWidget,
                             QGraphicsItem, QGraphicsPolygonItem,
                             QGraphicsScene, QGraphicsView, QGridLayout,
                             QMenu, QGraphicsPathItem, QPushButton,
                             QVBoxLayout, QToolBar, QToolBox, QWidgetAction,
                             QMessageBox)

# PythonQwt
import qwt
from qwt.text import QwtText

# pangalactic
try:
    # if an orb has been set (uberorb or fastorb), this works
    from pangalactic.core             import orb, state
except:
    # if an orb has not been set, uberorb is set by default
    import pangalactic.core.set_uberorb
    from pangalactic.core             import orb, state
from pangalactic.core.access      import get_perms
from pangalactic.core.clone       import clone
from pangalactic.core.names       import get_link_name, pname_to_header
# from pangalactic.core.parametrics import get_pval
from pangalactic.core.parametrics import (clone_mode_defs, get_pval,
                                          # get_duration,
                                          get_usage_mode_val,  mode_defz,
                                          round_to,
                                          set_comp_modal_context,
                                          set_dval)
from pangalactic.core.utils.datetimes import dtstamp
from pangalactic.node.activities  import (DEFAULT_ACTIVITIES,
                                          ActivityWidget,
                                          ModeDefinitionDashboard,
                                          SystemSelectionView)
from pangalactic.node.buttons     import ToolButton
from pangalactic.node.diagrams.shapes import BlockLabel
from pangalactic.node.dialogs     import (DefineModesDialog,
                                          DisplayNotesDialog,
                                          DocImportDialog,
                                          NotesDialog,
                                          PlotDialog)
# from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.utils       import pct_to_decimal, extract_mime_data
from pangalactic.node.widgets     import ColorLabel, NameLabel

# constants
POINT_SIZE = 8
if sys.platform == 'win32':
    POINT_SIZE = 6
    BLOCK_FACTOR = 26
elif sys.platform == 'darwin':
    POINT_SIZE = 10
    BLOCK_FACTOR = 20
else:
    # linux
    POINT_SIZE = 8
    BLOCK_FACTOR = 20
LABEL_COLORS = [Qt.darkRed, Qt.darkGreen, Qt.blue, Qt.darkBlue, Qt.cyan,
                Qt.darkCyan, Qt.magenta, Qt.darkMagenta]
# -----------------------------------------------------
# Qt's predefined QColor objects:
# -----------------------------------------------------
# Qt::white         3 White (#ffffff)
# Qt::black         2 Black (#000000)
# Qt::red           7 Red (#ff0000)
# Qt::darkRed      13 Dark red (#800000)
# Qt::green         8 Green (#00ff00)
# Qt::darkGreen    14 Dark green (#008000)
# Qt::blue          9 Blue (#0000ff)
# Qt::darkBlue     15 Dark blue (#000080)
# Qt::cyan         10 Cyan (#00ffff)
# Qt::darkCyan     16 Dark cyan (#008080)
# Qt::magenta      11 Magenta (#ff00ff)
# Qt::darkMagenta  17 Dark magenta (#800080)
# Qt::yellow       12 Yellow (#ffff00)
# Qt::darkYellow   18 Dark yellow (#808000)
# Qt::gray          5 Gray (#a0a0a4)
# Qt::darkGray      4 Dark gray (#808080)
# Qt::lightGray     6 Light gray (#c0c0c0)
# Qt::transparent  19 a transparent black value (i.e., QColor(0, 0, 0, 0))
# Qt::color0        0 0 pixel value (for bitmaps)
# Qt::color1        1 1 pixel value (for bitmaps)
# orange (not Qt for that):  QColor(255, 140, 0)
# -----------------------------------------------------


def flatten_subacts(act, all_subacts=None):
    """
    For an activity that contains more than one level of sub-activities,
    return all levels of sub-activities in a single list in the order of their
    occurrance.

    Args:
        act (Activity): the specified activity

    Keyword Args:
        all_subacts (list of Activity): the flattened list of sub-activities
    """
    all_subacts = all_subacts or []
    subacts = getattr(act, 'sub_activities', []) or []
    if subacts:
        subacts.sort(key=lambda x: x.sub_activity_sequence or 0)
        # orb.log.debug(f"  domain: {names}")
        # oids = [a.oid for a in subacts]
        for i, a in enumerate(subacts):
            a_subacts = getattr(a, 'sub_activities', []) or []
            if a_subacts:
                flatten_subacts(a, all_subacts=all_subacts)
            else:
                all_subacts.append(a)
            if i == len(subacts) - 1:
                return all_subacts
    else:
        return all_subacts


def get_effective_duration(act, units=None):
    """
    Return the sum of the durations of all levels of sub-activities of the
    specified activity, or its specified duration if it has no sub-activities.
    (For cyclic activities or sub-activities, sum the durations of the
    sub-activities of a single cycle).

    Args:
        act (Activity): the specified activity

    Keyword Args:
        units (str): time units
    """
    all_subacts = flatten_subacts(act)
    if all_subacts:
        return sum([get_pval(a.oid, 'duration', units=units)
                    for a in all_subacts])
    else:
        return get_pval(act.oid, 'duration', units=units)


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
        elif self.activity.activity_type.name == "Cycle":
            path.addEllipse(-70, 0, 140, 140)
            self.myPolygon = path.toFillPolygon(QTransform())
            # only Cycles can accept drops ...
            self.setAcceptDrops(True)
        self.setPolygon(self.myPolygon)
        self.block_label = BlockLabel(getattr(self.activity, 'name', '') or '',
                                      self, point_size=POINT_SIZE)
        # orb.log.debug(f'* Block initialized with font size {POINT_SIZE}')

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

    def mousePressEvent(self, event):
        if self.scene:
            self.scene.clearSelection()
        self.setSelected(True)
        QGraphicsItem.mousePressEvent(self, event)

    def mouseReleaseEvent(self, event):
        # orb.log.debug("* EventBlock: mouseReleaseEvent()")
        self.setSelected(False)
        QGraphicsItem.mouseReleaseEvent(self, event)

    def mouseMoveEvent(self, event):
        QGraphicsItem.mouseMoveEvent(self, event)

    def highlight(self):
        self.setBrush(Qt.yellow)

    def unhighlight(self):
        self.setBrush(Qt.white)

    def mimeTypes(self):
        return ["application/x-pgef-activity"]

    def dragEnterEvent(self, event):
        if (self.activity.activity_type.name == "Cycle"
            and event.mimeData().hasFormat("application/x-pgef-activity")):
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        """
        Handle the drop event on a "Cycle" EventBlock.  This includes the
        following possible cases:

            00: drop target is not a "Cycle" -> ignore
            0: user permissions prohibit operation -> abort
            1: user has permissions and dropped item is an activity
        """
        orb.log.debug("* ObjectBlock: hm, something dropped on me ...")
        # drop_target = self.activity
        if not (self.activity.activity_type.name == "Cycle"):
            event.ignore()
            return
        if not 'modify' in get_perms(self.activity):
            # --------------------------------------------------------
            # 0: user permissions prohibit operation -> abort
            # --------------------------------------------------------
            popup = QMessageBox(
                  QMessageBox.Critical,
                  "Unauthorized Operation",
                  "User's roles do not permit this operation",
                  QMessageBox.Ok, self.parentWidget())
            popup.show()
            event.ignore()
            return
        if event.mimeData().hasFormat("application/x-pgef-activity"):
            data = extract_mime_data(event, "application/x-pgef-activity")
            icon, oid, _id, name, cname = data
            dropped_item = orb.get(oid)
            if dropped_item:
                # do stuff
                pass
            else:
                orb.log.info("  - dropped product not in db; nothing done.")
                event.accept()
        else:
            orb.log.info("  - dropped object was not an Activity")
            event.ignore()

    def contextMenuEvent(self, event):
        self.menu = QMenu()
        self.menu.addAction(self.display_notes_action)
        self.menu.addAction(self.edit_notes_action)
        self.menu.addAction(self.add_doc_action)
        self.menu.addAction(self.clone_action)
        self.menu.addAction(self.delete_action)
        self.menu.exec(QCursor.pos())

    def create_actions(self):
        self.display_notes_action = QAction("Display Notes", self.scene,
                                     statusTip="Display Notes",
                                     triggered=self.display_act_notes)
        self.edit_notes_action = QAction("Edit Notes", self.scene,
                                     statusTip="Edit Notes",
                                     triggered=self.edit_act_notes)
        # NOTE: deactivated until a function to display related documents is
        # added ...
        # self.add_doc_action = QAction("Add a Document", self.scene,
                                     # statusTip="Import a Document File",
                                     # triggered=self.add_act_doc)
        self.clone_action = QAction("Clone Activity", self.scene,
                             statusTip="Create a new Activity by cloning",
                             triggered=self.clone_activity_block)
        self.delete_action = QAction("Delete", self.scene,
                                     statusTip="Delete Activity",
                                     triggered=self.delete_activity_block)

    def display_act_notes(self):
        """
        Display an activity (mode) description / notes.
        """
        dlg = DisplayNotesDialog(self.activity, parent=self.scene.parent())
        dlg.show()

    def edit_act_notes(self):
        """
        Edit an activity (mode) description / notes.
        """
        dlg = NotesDialog(self.activity, parent=self.scene.parent())
        dlg.show()

    def add_act_doc(self):
        """
        Upload a document pertaining to an activity.
        """
        dlg = DocImportDialog(rel_obj=self.activity,
                              parent=self.scene.parent())
        dlg.show()

    def clone_activity_block(self):
        project = orb.get(state.get('project'))
        seq = 0
        parent = getattr(self.activity, 'sub_activity_of', None)
        if parent:
            seq = len(parent.sub_activities) + 1
        act_type = self.activity.activity_type
        activity = clone(self.activity, sub_activity_of=parent,
                         activity_type=act_type, owner=project,
                         sub_activity_sequence=seq)
        orb.db.commit()
        # set time units locally to default: "minutes" -- if connected,
        # this will be done in the callback after vger.save() succeeds
        set_dval(activity.oid, "time_units", "minutes")
        # also replicate the activity's mode definitions
        clone_mode_defs(self.activity, activity)
        evt_block = EventBlock(activity=activity, scene=self.scene)
        # evt_block.setPos(event.scenePos())
        self.scene.addItem(evt_block)
        self.scene.timeline.update_timeline()
        # orb.log.debug(' - dipatching "new activity" signal')
        # dispatcher.send(signal='new activity', act=activity)

    def delete_activity_block(self):
        self.scene.removeItem(self)
        orb.log.debug(' - dipatching "delete activity" signal')
        dispatcher.send(signal='delete activity', oid=self.activity.oid)

    def itemChange(self, change, value):
        return value

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

    def __init__(self, scene=None, parent=None):
        super().__init__(parent)
        if scene:
            scene.addItem(self)
        # self.evt_blocks = []
        self.path_length = 1200
        self.make_path()

    @property
    def evt_blocks(self):
        if self.scene():
            blocks = [x for x in self.scene().items()
                      if isinstance(x, EventBlock)]
            blocks.sort(key=lambda x: x.scenePos().x())
            return blocks
        else:
            return []

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
        # self.evt_blocks.sort(key=lambda x: x.scenePos().x())
        orb.log.debug('  - setting sub_activity_sequence(s) ...')
        NOW = dtstamp()
        mod_objs = []
        for i, evt_block in enumerate(self.evt_blocks):
            evt_block.setPos(QPoint(self.list_of_pos[i], 250))
            act = evt_block.activity
            if act.sub_activity_sequence != i:
                act.sub_activity_sequence = i
                act.mod_datetime = NOW
                orb.save([act])
                mod_objs.append(act)
        dispatcher.send("order changed")
        self.update()
        if mod_objs:
            dispatcher.send("modified objects", objs=mod_objs)


class TimelineScene(QGraphicsScene):

    def __init__(self, parent, activity):
        super().__init__(parent)
        orb.log.debug('* TimelineScene()')
        self.subject = activity
        if activity:
            self.act_of = activity.of_system
            name = getattr(self.act_of, 'name', None) or 'None'
            orb.log.debug(f'* TimelineScene act_of: {name}')
        self.timeline = Timeline(scene=self)
        # self.addItem(self.timeline)
        self.focusItemChanged.connect(self.focus_changed_handler)
        self.current_focus = None
        self.grabbed_item = None
        self.setSceneRect(QRectF(150.0, 150.0, 1200.0, 300.0))
        width = self.sceneRect().width()
        height = self.sceneRect().height()
        orb.log.debug(f'* TimelineScene size: ({width}, {height}).')
        dispatcher.connect(self.on_act_name_mod, "act name mod")

    def focus_changed_handler(self, new_item, old_item):
        if getattr(self, "right_button_pressed", False):
            # ignore: context menu event
            self.right_button_pressed = False
            return
        elif (new_item is not None and
              new_item != self.current_focus):
            self.current_focus = new_item
            if hasattr(self.focusItem(), 'activity'):
                new_item.highlight()
                if hasattr(old_item, 'activity'):
                    old_item.unhighlight()
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
        position = event.scenePos()
        seq = 0
        for evt_block in self.timeline.evt_blocks:
            if position.x() > evt_block.x():
                seq = evt_block.activity.sub_activity_sequence + 1
        # seq = len(self.subject.sub_activities) + 1
        # activity type is one of "Cycle", "Op", "Event"
        activity_type_name = event.mimeData().text()
        activity_type = orb.select("ActivityType", name=activity_type_name)
        prefix = self.subject.name
        act_id = '-'.join([prefix, activity_type_name, str(seq)])
        act_name = ' '.join([prefix, activity_type_name, str(seq)])
        project = orb.get(state.get('project'))
        activity = clone("Activity", id=act_id, name=act_name,
                         activity_type=activity_type, owner=project,
                         of_system=self.act_of,
                         sub_activity_sequence=seq,
                         sub_activity_of=self.subject)
        orb.db.commit()
        # set time units locally to default: "minutes" -- if connected,
        # this will be done in the callback after vger.save() succeeds
        set_dval(activity.oid, "time_units", "minutes")
        evt_block = EventBlock(activity=activity, scene=self)
        evt_block.setPos(event.scenePos())
        self.addItem(evt_block)
        self.timeline.update_timeline()
        # NOTE: DO NOT send "new activity signal: timeline.update_timeline()
        # will send a "modified objects" signal ...
        orb.log.debug('* scene: sending "set new scene" signal')
        dispatcher.send(signal="set new scene")

    def on_act_name_mod(self, act=None):
        """
        Handle 'act name mod' signal from ActInfoTable, meaning an activity's
        name was modified.
        """
        orb.log.debug('* scene: received "act name mod" signal')
        for item in self.timeline.evt_blocks:
            # orb.log.debug(f'  checking for {item.activity.name} by oid')
            if item.activity.oid == act.oid:
                item.update_block_label()
                dispatcher.send("modified object", obj=item.activity)

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)


# TODO:  the TimelineWidget should display the timeline of either
# (1) if the subject of the timeline is the Mission, all of the Mission's
# activities, or
# (2) if the subject of the timeline is a non-Mission activity, all of that
# activity's sub-activities

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
        layout = QVBoxLayout()
        self.setLayout(layout)
        self.set_new_scene()
        dispatcher.connect(self.delete_activity, "deleted object")
        # "delete activity" is sent by event block when it is removed ...
        dispatcher.connect(self.delete_activity, "delete activity")
        dispatcher.connect(self.on_act_name_mod, "act name mod")
        dispatcher.connect(self.set_new_scene, "set new scene")
        self.setUpdatesEnabled(True)

    @property
    def system(self):
        return getattr(self.subject, 'of_system', None) or None

    def minimumSize(self):
        return QSize(800, 500)

    def set_new_scene(self):
        """
        Create a new scene with new subject activity or an empty scene if no
        subject activity.
        """
        orb.log.debug(' - set_new_scene ...')
        scene = TimelineScene(self, self.subject)
        subacts = getattr(self.subject, 'sub_activities', []) or []
        subacts.sort(key=lambda x: getattr(x,
                                   'sub_activity_sequence', 0) or 0)
        nbr_of_subacts = len(subacts)
        if (self.subject != None) and (nbr_of_subacts > 0):
            orb.log.debug(f' - with {nbr_of_subacts} sub-acts ...')
            evt_blocks=[]
            for activity in reversed(subacts):
                if (activity.of_system == self.system):
                    item = EventBlock(activity=activity,
                                      scene=scene)
                    evt_blocks.append(item)
                    scene.addItem(item)
                scene.update()
            scene.timeline.update_timeline()
            ada = getattr(self, 'add_defaults_action', None)
            if ada:
                self.add_defaults_action.setEnabled(False)
        elif (isinstance(self.subject, orb.classes['Mission'])
              and (nbr_of_subacts == 0)):
            orb.log.debug(' - no sub-acts; can add default sub-acts')
            ada = getattr(self, 'add_defaults_action', None)
            if ada:
                self.add_defaults_action.setEnabled(True)

        layout = self.layout()

        if getattr(self, 'view', None):
            try:
                layout.removeWidget(self.view)
                self.view.close()
                self.view.deleteLater()
            except:
                # C++ object probably got deleted
                pass
        if getattr(self, 'title_widget', None):
            try:
                layout.removeWidget(self.title_widget)
                self.title_widget.close()
                self.title_widget.deleteLater()
            except:
                # C++ object probably got deleted
                pass
        self.title_widget = self.get_title_widget()
        layout.addWidget(self.title_widget)
        layout.addWidget(self.toolbar)
        self.view = TimelineView(self)
        layout.addWidget(self.view)
        self.scene = scene
        # TimelineView controls the scaling of the scene, which is done in the
        # update_timeline() ...
        scene.timeline.update_timeline()
        # ---------------------------------------------------------------------
        self.view.setScene(self.scene)
        self.br = self.scene.itemsBoundingRect()
        self.auto_rescale_timeline()
        self.view.show()

    def get_title_widget(self):
        title_widget = NameLabel('')
        title_widget.setStyleSheet(
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
        title_widget.setText(title)
        return title_widget

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
                                    text="Back",
                                    slot=self.load_last_timeline,
                                    icon="back",
                                    tip="Back to last timeline")
        self.back_action.setEnabled(False)
        self.toolbar.addAction(self.back_action)
        self.clear_history_action = self.create_action(
                                    text="Clear History",
                                    slot=self.clear_history,
                                    tip="Clear timeline history")
        self.toolbar.addAction(self.clear_history_action)
        self.clear_history_action.setEnabled(False)
        self.add_defaults_action = self.create_action(
                                    "Add Default Activities",
                                    slot=self.add_default_activities,
                                    icon="tools",
                                    tip="add default activities")
        self.toolbar.addAction(self.add_defaults_action)
        self.add_defaults_action.setEnabled(False)
        self.plot_action = self.create_action(
                                    text="Graph",
                                    slot=self.graph,
                                    icon="graph",
                                    tip="graph")
        self.toolbar.addAction(self.plot_action)
        if not state.get('conops usage oid'):
            self.plot_action.setEnabled(False)
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
        orb.log.debug('* add_default_activities()')
        sub_acts = getattr(self.subject, 'sub_activities', None)
        if sub_acts:
            orb.log.debug('  subject already has sub-activities, returning.')
            return
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
        self.set_new_scene()
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
                orb.log.debug('  is current subject, removing ...')
                project = orb.get(state.get('project'))
                mission = orb.select('Mission', owner=project)
                self.subject = mission
                self.set_new_scene()
            else:
                current_act_oids = [getattr(act, 'oid', '') for act in
                                    self.subject.sub_activities]
                if oid in current_act_oids:
                    orb.log.debug('  found in current timeline, removing ...')
                    # find event block and remove it
                    for item in self.scene.items():
                        if (hasattr(item, 'activity') and
                            item.activity and item.activity.oid == oid):
                            act = item.activity
                            self.scene.removeItem(item)
                            if item in self.scene.timeline.evt_blocks:
                                self.scene.timeline.evt_blocks.remove(item)
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
        view_polygon = self.view.mapFromScene(
                                    br.x(), br.y(), br.width(), br.height())
        vbr = view_polygon.boundingRect()
        vbr_parms = (vbr.x(), vbr.y(), vbr.width(), vbr.height())
        orb.log.debug(f'  view coords of bounding rect: ({vbr_parms})')
        # find the view origin (0, 0) in scene coordinates ...
        v_origin = self.view.mapToScene(0, 0)
        vo_coords = (v_origin.x(), v_origin.y())
        orb.log.debug(f'  scene coords of view origin: ({vo_coords})')

    def on_act_name_mod(self, act):
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

    def power_time_function(self, project=None, act=None, usage=None,
                            context="CBE", time_units="minutes",
                            subtimelines=True):
        """
        Return a function that computes system net power value as a function of
        time. Note that the time variable "t" in the returned function can be a
        scalar (float) or can be array-like (list, etc.).

        Keyword Args:
            act (Activity): restrict to the specified activity (default if act
                is None: the Mission)
            usage (Acu or ProjectSystemUsage): restrict to the power of the
                specified usage, or self.usage if none is specified
            context (str): "CBE" (Current Best Estimate) or "MEV" (Maximum
                Estimated Value)
            time_units (str): units of time to be used (default: minutes)
            subtimelines (bool):  whether to include sub-activity timelines
                (e.g. for cyclic activities, like orbits) explicitly in the
                graph (default: True)
        """
        orb.log.debug("* ConOpsModeler.power_time_function()")
        # The current assumption is that we are only considering activities in
        # the context of a single usage ... that may change in the future but
        # would complicate things dramatically (e.g. considering
        # subsystem-specific timelines that may be asynchronous to the "main"
        # timeline).
        if usage:
            if isinstance(usage, orb.classes['ProjectSystemUsage']):
                comp = usage.system
            elif isinstance(usage, orb.classes['Acu']):
                comp = usage.component
        else:
            orb.log.debug("  no usage: zero function")
            f = (lambda t: 0.0)
        if isinstance(act, orb.classes['Activity']):
            subacts = act.sub_activities
            if subacts:
                names = [a.name for a in subacts]
                orb.log.debug(f"  domain: {names}")
                subacts.sort(key=lambda x: x.sub_activity_sequence or 0)
                if subtimelines:
                    all_acts = flatten_subacts(act)
                    t_seq = [0.0]
                    for i, a in enumerate(all_acts):
                        t_seq.append(t_seq[i] + get_pval(a.oid, 'duration',
                                                         units=time_units))
                else:
                    all_acts = subacts
                    t_seq = [get_pval(a.oid, 't_start', units=time_units)
                             for a in subacts]
                val_dict = {a.name: get_usage_mode_val(project.oid,
                                            usage.oid, comp.oid,
                                            a.oid)
                            for a in all_acts}
                orb.log.debug(f"  mapping: {val_dict}")
                def f_scalar(t):
                        a = all_acts[-1]
                        for i in range(len(all_acts) - 1):
                            if (t_seq[i] <= t) and (t < t_seq[i+1]):
                                a = all_acts[i]
                        p_cbe_val = get_usage_mode_val(project.oid,
                                                       usage.oid, comp.oid,
                                                       a.oid)
                        if context == "CBE":
                            return p_cbe_val
                        else:
                            # context == "mev"
                            ctgcy = get_pval(comp.oid, 'P[Ctgcy]')
                            factor = 1.0 + ctgcy
                            p_mev_val = round_to(p_cbe_val * factor, n=3)
                            return p_mev_val
                def f(t):
                    if isinstance(t, float):
                        return f_scalar
                    else:
                        # t is array-like: return a list function
                        return [f_scalar(x) for x in t]
            else:
                # no subactivities -> 1 mode -> constant function
                p_cbe_val = get_usage_mode_val(project.oid, usage.oid,
                                               comp.oid, self.act.oid)
                if context == "cbe":
                    f = (lambda t: p_cbe_val)
                else:
                    ctgcy = get_pval(comp.oid, 'P[Ctgcy]')
                    factor = 1.0 + ctgcy
                    p_mev_val = round_to(p_cbe_val * factor, n=3)
                    f = (lambda t: p_mev_val)
        else:
            orb.log.debug("  no activity: zero function")
            f = (lambda t: 0.0)
        return f

    def energy_time_integral(self, act=None, usage=None):
        """
        Compute system net energy consumption as a function of time.

        Keyword Args:
            act (Activity): a specified activity over which to integrate, or
                over the Mission if none is specified
            usage (Acu or ProjectSystemUsage): restrict to energy consumption
                of the specified usage, or self.usage if none is specified
        """
        pass

    def graph(self):
        orb.log.debug('* graph()')
        project = orb.get(state.get('project'))
        orb.log.debug(f"  project: {project.id}")
        usage = orb.get(state.get('conops usage oid'))
        # TODO:  if no usage, show dialog about selecting a usage ...
        if usage:
            orb.log.debug(f"  usage: {usage.id}")
        else:
            orb.log.debug("  no usage set; returning.")
        if isinstance(usage, orb.classes['Acu']):
            comp = usage.component
        else:
            # PSU
            comp = usage.system
        orb.log.debug(f"  system: {comp.name}")
        mission = orb.select('Mission', owner=project)
        act = self.subject or mission
        orb.log.debug(f"  activity: {act.name}")
        subacts = act.sub_activities
        # TODO:  allow time_units to be specified ...
        time_units = "minutes"
        p_cbe_dict = {}
        p_mev_dict = {}
        if subacts:
            # default is to break out all sub-activity timelines
            # ("subtimelines") -- this can be made configurable in the future
            subtimelines = True
            orb.log.debug('  durations of sub_activities:')
            if subtimelines:
                all_acts = flatten_subacts(act)
            else:
                all_acts = subacts
            for a in all_acts:
                d = get_effective_duration(a, units=time_units)
                orb.log.debug(f'  {a.name}: {d}')
                p_cbe_val = get_usage_mode_val(project.oid,
                                               usage.oid, comp.oid,
                                               a.oid)
                p_cbe_dict[a.name] = p_cbe_val
                ctgcy = get_pval(comp.oid, 'P[Ctgcy]')
                factor = 1.0 + ctgcy
                p_mev_val = round_to(p_cbe_val * factor, n=3)
                p_mev_dict[a.name] = p_mev_val
        duration = get_effective_duration(act, units=time_units)
        max_val = max(list(p_mev_dict.values()))
        if time_units:
            orb.log.debug(f'  duration of {act.name}: {duration} {time_units}')
        else:
            orb.log.debug(f'  duration of {act.name}: {duration} seconds')
        plot = qwt.QwtPlot(f"{comp.name} Power vs. Time")
        plot.setFlatStyle(False)
        plot.setAxisTitle(qwt.QwtPlot.xBottom, "time (minutes)")
        plot.setAxisTitle(qwt.QwtPlot.yLeft, "Power (Watts)")
        # set y-axis to begin at 0 and end 10% above max
        plot.setAxisScale(qwt.QwtPlot.xBottom, 0.0, duration)
        plot.setAxisScale(qwt.QwtPlot.yLeft, 0.0, 1.4 * max_val)
        f_cbe = self.power_time_function(context="CBE", project=project,
                                         act=act, usage=usage,
                                         time_units=time_units)
        f_mev = self.power_time_function(context="MEV", project=project,
                                         act=act, usage=usage,
                                         time_units=time_units)
        t_array = np.linspace(0, duration, 400)
        # orb.log.debug(f'  {t_array}')
        orb.log.debug(f'  f_cbe: {f_cbe(t_array)}')
        qwt.QwtPlotCurve.make(t_array, f_cbe(t_array), "P[CBE]", plot,
                              z=1.0, linecolor="blue", linewidth=2,
                              antialiased=True)
        qwt.QwtPlotCurve.make(t_array, f_mev(t_array), "P[MEV]", plot,
                              z=1.0, linecolor="red", linewidth=2,
                              antialiased=True)
        last_label_y = 0
        if subtimelines:
            t_seq = [0.0]
            for i, a in enumerate(all_acts):
                t_seq.append(t_seq[i] + get_pval(a.oid, 'duration',
                                                 units=time_units))
        super_acts = {}
        for i, a in enumerate(all_acts):
            if subtimelines:
                t_start = t_seq[i]
                t_end = t_seq[i+1]
            else:
                t_start = get_pval(a.oid, 't_start', units=time_units)
                t_end = get_pval(a.oid, 't_end', units=time_units)
            super_act = a.sub_activity_of
            if super_act is not act and super_act not in super_acts.values():
                super_acts[t_start] = a.sub_activity_of
            # insert a vertical line for t_start of each activity
            qwt.QwtPlotMarker.make(
                xvalue=t_start,
                linestyle=qwt.QwtPlotMarker.VLine,
                width=2.0,
                z=0.0,
                color="green",
                plot=plot
            )
            # insert a label marker for each activity
            p_cbe_val = p_cbe_dict[a.name]
            p_mev_val = p_mev_dict[a.name]
            name = pname_to_header(a.name, 'Activity', width=20)
            label_txt = f'  {name}  '
            label_txt += f'\n P[cbe] = {p_cbe_val} Watts '
            label_txt += f'\n P[mev] = {p_mev_val} Watts '
            pen = QPen(Qt.black, 1)
            white_brush = QBrush(Qt.white)
            name_label = QwtText.make(text=label_txt, weight=QFont.Bold,
                                      borderpen=pen, borderradius=3.0,
                                      brush=white_brush)
            if p_cbe_val < .5 * max_val:
                if last_label_y == .65 * max_val:
                    y_label = .9 * max_val
                else:
                    y_label = .65 * max_val
            else:
                if last_label_y == .15 * max_val:
                    y_label = .35 * max_val
                else:
                    y_label = .15 * max_val
            last_label_y = y_label
            if t_start == 0:
                x_label = 0
                align_label = Qt.AlignRight
            elif t_end >= duration and (t_end - t_start < .3 * duration):
                x_label = duration
                align_label = Qt.AlignLeft
            else:
                x_label = (t_start + t_end) / 2
                align_label = Qt.AlignCenter
            qwt.QwtPlotMarker.make(
                xvalue=x_label,
                yvalue=y_label,
                align=align_label,
                z=3.0,
                label=name_label,
                plot=plot
                )
        # insert markers for the super-activities ...
        plot.resize(1400, 650)
        j = 1
        plot.updateLayout()
        canvas_map = plot.canvasMap(2)
        canvas_map.setScaleInterval(0.0, duration)
        canvas_map.setPaintInterval(0, 1400)
        # orb.log.debug(f'  canvas_map: {type(canvas_map)}')
        # label all "super activities" (most importantly, cycles)
        for t_start, super_act in super_acts.items():
            # compute peak and average power
            e_total = 0
            p_peak = 0
            for a in super_act.sub_activities:
                a_dur = get_effective_duration(a, units=time_units)
                # yes, this gives energy in weird units like Watt-minutes but
                # doesn't matter because just using to calculate avg. power
                a_p_cbe = p_cbe_dict[a.name]
                a_p_mev = p_mev_dict[a.name]
                e_total += a_dur * a_p_cbe
                if a_p_mev > p_peak:
                    p_peak = a_p_mev
            dur = get_effective_duration(super_act, units=time_units)
            t_end = t_start + dur
            p_average = round_to(e_total / dur, n=3)
            label_txt = f'  {super_act.name}  \n'
            label_txt += f' Peak Power: {p_peak} Watts \n'
            label_txt += f' Average Power: {p_average} Watts '
            pen = QPen(LABEL_COLORS[j-1], 1)
            white_brush = QBrush(Qt.white)
            sa_name_label = QwtText.make(text=label_txt, weight=QFont.Bold,
                                         pointsize=12, borderpen=pen,
                                         borderradius=0.0, brush=white_brush)
            y_label = (1.4 - .1 * j) * max_val
            orb.log.debug(f'  super act: {super_act.name}')
            orb.log.debug(f'      begins at: {t_start} {time_units}')
            duration_pixels = canvas_map.transform_scalar(dur)
            orb.log.debug(f'      (duration: {duration_pixels} pixels)')
            symbol_size = QSize(duration_pixels, 10)
            symbol_brush = QBrush(LABEL_COLORS[j-1])
            rect_symbol = qwt.QwtSymbol.make(pen=pen, brush=symbol_brush,
                                             style=qwt.QwtSymbol.Rect,
                                             size=symbol_size)
            qwt.QwtPlotMarker.make(
                xvalue=(t_start + t_end) / 2,
                yvalue=y_label,
                z=4.0,
                label=sa_name_label,
                symbol=rect_symbol,
                plot=plot
                )
            j += 1
        # plot.resize(1400, 650)
        dlg = PlotDialog(plot, title="Power vs Time", parent=self)
        dlg.show()


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
        Add a TimelineWidget and ActInfoTable containing all sub-activities of
        the "subject" (current activity), and the Mission Systems selection
        tree and ModeDefinitionDashboard.

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
        self.create_activity_table(timeline=self.main_timeline.scene.timeline)
        self.left_dock_layout.addWidget(self.activity_table,
                                        alignment=Qt.AlignTop)
        # ====================================================================
        self.expansion_select = QComboBox()
        self.expansion_select.setStyleSheet(
                                        'font-weight: bold; font-size: 14px')
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
            state['conops_tree_expansion'][self.project.oid] = 2
        # ---------------------------------------------------------------------
        sys_tree_title = f'{self.project.id} Mission Systems'
        sys_tree_title_widget = ColorLabel(sys_tree_title, element='h2')
        project = getattr(self, 'project', None)
        proj_oid = getattr(project, 'oid', None)
        mdd_state = state.get('mdd', {}).get(proj_oid, {})
        initial_usage = orb.get(mdd_state.get('usage'))
        if not initial_usage:
            if getattr(project, 'systems', []) or []:
                initial_usage = project.systems[0]
        # try to set initial usage, mainly so graph works when conops first
        # opens!
        if initial_usage:
            self.set_initial_usage(initial_usage)
        self.sys_select_tree = SystemSelectionView(self.project,
                                                   refdes=True,
                                                   usage=initial_usage)
        self.sys_select_tree.setSizePolicy(QSizePolicy.Preferred,
                                           QSizePolicy.MinimumExpanding)
        self.sys_select_tree.setObjectName('Sys Select Tree')
        self.sys_select_tree.setMinimumWidth(400)
        # -- set initial tree expansion level ---------------------------------
        expand_level = 3
        idx = state['conops_tree_expansion'][self.project.oid]
        expand_level = idx + 2
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
        # NOTE:  levels are 3 to 5, so level = index + 2
        #        expandToDepth(n) actually means level n + 1
        try:
            level = index + 2
            self.sys_select_tree.expandToDepth(level)
            state['conops_tree_expansion'][self.project.oid] = index
            orb.log.debug(f'* tree expanded to level {level}')
        except:
            # orb.log.debug('* conops tree expansion failed ...')
            # orb.log.debug('  sys_select_tree C++ obj probably gone.')
            # no big deal ...
            pass

    def create_activity_table(self, timeline=None):
        """
        Create an ActivityWidget containing an ActInfoTable.

        Keyword Args:
            timeline (Timeline): the timeline graphic item contained in the
                TimelineScene of the main_timeline (TimelineWidget)
        """
        orb.log.debug("* ConOpsModeler.create_activity_table()")
        self.activity_table = ActivityWidget(self.subject, timeline=timeline,
                                             parent=self)
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
        self.rebuild_table()

    def rebuild_table(self):
        orb.log.debug("* conops: rebuild_table()")
        if getattr(self, 'activity_table', None):
            self.left_dock_layout.removeWidget(self.activity_table)
            self.activity_table.parent = None
            self.activity_table.close()
            self.activity_table = None
        self.create_activity_table(timeline=self.main_timeline.scene.timeline)
        self.left_dock_layout.insertWidget(0, self.activity_table,
                                           alignment=Qt.AlignTop)
        self.resize(self.layout().sizeHint())

    def on_item_clicked(self, index):
        orb.log.debug("* ConOpsModeler.on_item_clicked()")
        n = len(self.sys_select_tree.selectedIndexes())
        orb.log.debug(f"  {n} items are selected.")
        self.sys_select_tree.expand(index)
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
            # sys_dict (i.e. it is of interest in defining modes ...)
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
                    self.set_usage(link)
                else:
                    # TODO: maybe change focus to project node (?)
                    return

    def set_initial_usage(self, link):
        orb.log.debug("* ConOpsModeler.set_initial_usage()")
        name = get_link_name(link)
        orb.log.debug(f"  - initial usage is {name}")
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
            project_mode_defz = mode_defz[self.project.oid]
            sys_dict = project_mode_defz['systems']
            if link.oid in sys_dict:
                orb.log.debug("  - link oid is in sys_dict")
                # set as subject's usage
                self.set_usage(link)
                # signal to mode_dash to set this link as its usage ...
                orb.log.debug('    sending "set mode usage" signal ...')
                dispatcher.send(signal='set mode usage', usage=link)
            else:
                orb.log.debug("  - link oid is NOT in sys_dict")

    def on_ignore_components(self, index):
        """
        If the item (aka "link" or "node") in the assembly tree exists in the
        "systems" table, remove it and remove its components from the
        "components" table, and if it is a component of an item in the
        "systems" table, add it back to the "components" table, and change its
        "level" from "[computed]" to a specifiable level value.
        """
        # TODO: implement as a context menu action ...
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
        if link.oid in sys_dict:
            # if selected link is in sys_dict, make subject (see below)
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

    def on_add_usage(self, index):
        """
        If the item (aka "link" or "node") selected in the assembly tree does
        not exist in the the mode definitions "systems" table, add it, and if
        it has components, add them to the mode definitions "components" table.

        If the item already exists in the "systems" table, switch to it as the
        current selected usage and deselect the previously selected usage.
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
                        for mode_oid in mode_dict:
                            sys_dict[link.oid][mode_oid] = '[computed]'
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
                    for mode_oid in mode_dict:
                        if has_components:
                            sys_dict[link.oid][mode_oid] = '[computed]'
                        else:
                            context = mode_dict.get(mode_oid)
                            context = context or '[select level]'
                            sys_dict[link.oid][mode_oid] = context
        # ensure that all selected systems (sys_dict) that have components,
        # have those components included in comp_dict ...
        # * set their modal_context (level) to "Off"
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
                    for mode_oid in mode_dict:
                        # assign default modal_context
                        modal_context = 'Off'   # TODO: use default "template"
                        set_comp_modal_context(self.project.oid,
                                               syslink_oid,
                                               acu.oid, mode_oid,
                                               modal_context)

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
        dispatcher.send(signal='modes edited', oid=self.project.oid)
        # signal to the mode_dash to set this link as its usage
        dispatcher.send(signal='set mode usage', usage=link)

    def set_usage(self, usage):
        orb.log.debug("* ConOpsModeler.set_usage()")
        state['conops usage oid'] = usage.oid
        self.usage = usage
        self.main_timeline.plot_action.setEnabled(True)

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
        # orb.log.debug(f'  sending "new object" signal on {act.id}')
        self.main_timeline.auto_rescale_timeline()
        # dispatcher.send("new object", obj=act)
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
        n_oids = len(oids or [])
        orb.log.debug('* received "remote new or mod acts" signal')
        orb.log.debug(f'  with {n_oids} oids --')
        orb.log.debug('  setting new scene and rebuilding table ...')
        # act_oids = set([getattr(self.subject, 'oid', None)])
        # act_oids += set([act.oid for act in
                         # getattr(self.subject, 'sub_activities', []) or []])
        # new_or_mod_acts = orb.get(oids=oids)
        # owners = []
        # if new_or_mod_acts:
            # owners = [a.owner for a in new_or_mod_acts]
        # if oids and ((set(oids) & act_oids) or self.project in owners):
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

