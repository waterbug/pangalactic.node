#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Defines the TimelineModeler tool for defining an operations (Ops) timeline.
Initially shows a blank timeline, which can then be populated either by:
    - auto-population with a default set of pre-defined Mission Ops
    - drag/drop to create operations from an Ops "palette"
"""
import sys, os

# pydispatch
from pydispatch import dispatcher

from PyQt5.QtCore import Qt, QPointF, QPoint, QRectF, QSize
from PyQt5.QtGui import (QIcon, QCursor, QPainter, QPainterPath, QPixmap,
                         QPolygonF, QTransform)
from PyQt5.QtWidgets import (QAction, QApplication, QComboBox, QSizePolicy,
                             QWidget, QGraphicsItem, QGraphicsPolygonItem,
                             QGraphicsScene, QGraphicsView, QGridLayout,
                             QHBoxLayout, QMenu, QGraphicsPathItem,
                             QPushButton, QVBoxLayout, QToolBar, QToolBox,
                             QWidgetAction, QMessageBox)

# pangalactic
try:
    # if an orb has been set (uberorb or fastorb), this works
    from pangalactic.core             import orb, state
except:
    # if an orb has not been set, uberorb is set by default
    import pangalactic.core.set_uberorb
    from pangalactic.core             import orb, state
from pangalactic.core.access      import get_perms, is_global_admin
from pangalactic.core.clone       import clone
from pangalactic.core.parametrics import (clone_mode_defs,
                                          set_dval)
from pangalactic.core.utils.datetimes import dtstamp
from pangalactic.node.buttons     import ToolButton
from pangalactic.node.diagrams.shapes import BlockLabel
from pangalactic.node.dialogs     import (DisplayNotesDialog,
                                          DocImportDialog,
                                          NotesDialog)
from pangalactic.node.tableviews  import ActInfoTable
from pangalactic.node.utils       import pct_to_decimal, extract_mime_data
from pangalactic.node.widgets     import NameLabel
# from pangalactic.node.widgets     import CustomSplitter

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

DEFAULT_ACT_NAMES = ['Launch', 'Calibration', 'Propulsion', 'Slew',
                     'Science Data Acquisition', 'Science Data Transmission',
                     'Safe Mode']


class ActivityBlock(QGraphicsPolygonItem):

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
        dispatcher.send("block double clicked", act=self.activity)

    def mousePressEvent(self, event):
        if self.scene:
            self.scene.clearSelection()
        self.setSelected(True)
        QGraphicsItem.mousePressEvent(self, event)

    def mouseReleaseEvent(self, event):
        # orb.log.debug("* ActivityBlock: mouseReleaseEvent()")
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
        Handle the drop event on a "Cycle" ActivityBlock.  This includes the
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
        # self.menu.addAction(self.add_doc_action)
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
        evt_block = ActivityBlock(activity=activity, scene=self.scene)
        # evt_block.setPos(event.scenePos())
        self.scene.addItem(evt_block)
        self.scene.timeline.update_timeline()
        # orb.log.debug(' - dipatching "new object" signal')
        dispatcher.send("new object", obj=activity)

    def delete_activity_block(self):
        self.scene.removeItem(self)
        # orb.log.debug(' - dipatching "delete activity" signal')
        dispatcher.send(signal='delete activity', oid=self.activity.oid)

    def itemChange(self, change, value):
        return value

# "bar colors" is intended to be used for a timeline bar
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
                      if isinstance(x, ActivityBlock)]
            blocks.sort(key=lambda x: x.scenePos().x())
            return blocks
        else:
            return []

    def update_timeline(self, remote=False, remote_mod_acts=None):
        # orb.log.debug('* timeline.update_timeline()')
        self.calc_length()
        self.make_path()
        self.arrange(remote=remote, remote_mod_acts=remote_mod_acts)

    def calc_length(self):
        # orb.log.debug('* timeline.calc_length()')
        self.path_length = 1200
        if len(self.evt_blocks) <= 8:
            orb.log.debug('  <= 8 activity blocks ... no length re-calc.')
        else:
            n = len(self.evt_blocks)
            orb.log.debug(f'  {n} activity blocks -- calculating length ...')
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

    def arrange(self, remote=False, remote_mod_acts=None):
        # orb.log.debug(f'* timeline.arrange(remote={remote})')
        # self.evt_blocks.sort(key=lambda x: x.scenePos().x())
        # orb.log.debug('  - setting sub_activity_sequence(s) ...')
        NOW = dtstamp()
        # mod_objs = []
        props = {}
        if remote:
            # activity sequence was set by the remote operation, do not change
            # acts = remote_mod_acts or []
            # if acts:
                # orb.log.debug('  - received new or mod acts:')
                # for act in acts:
                    # seq = act.sub_activity_sequence
                    # orb.log.debug(f'    + {act.name} (seq: {seq})')
            # else:
                # orb.log.debug('  - received no Activity objects.')
            evt_blocks = self.evt_blocks
            evt_blocks.sort(key=lambda x: x.activity.sub_activity_sequence)
            # orb.log.debug('  - arranging activity blocks ...')
            for i, evt_block in enumerate(evt_blocks):
                # name = evt_block.activity.name
                # orb.log.debug(f'    + block {i}: "{name}"')
                evt_block.setPos(QPoint(self.list_of_pos[i], 250))
            self.update()
        else:
            # orb.log.debug('  - arranging activity blocks ...')
            for i, evt_block in enumerate(self.evt_blocks):
                # name = evt_block.activity.name
                # orb.log.debug(f'    + block {i}: "{name}"')
                evt_block.setPos(QPoint(self.list_of_pos[i], 250))
                act = evt_block.activity
                if act.sub_activity_sequence != i:
                    act.sub_activity_sequence = i
                    act.mod_datetime = NOW
                    # orb.save([act])
                    orb.db.commit()
                    # mod_objs.append(act)
                    props[act.oid] = {'sub_activity_sequence': i,
                                      'mod_datetime': str(NOW)}
            dispatcher.send("order changed")
            self.update()
            # if mod_objs:
                # orb.log.debug('  - sending "modified objects" signal on:')
                # names = [o.name for o in mod_objs]
                # for name in names:
                    # orb.log.debug(f'    + {name}')
                # dispatcher.send("modified objects", objs=mod_objs)
            if props:
                dispatcher.send("act mods", prop_mods=props)


class TimelineScene(QGraphicsScene):

    def __init__(self, parent, activity):
        super().__init__(parent)
        orb.log.debug('* TimelineScene()')
        self.subject = activity
        if activity:
            self.act_of = activity.of_system
            # name = getattr(self.act_of, 'name', None) or 'None'
            # orb.log.debug(f'* TimelineScene act_of: {name}')
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
        if not 'modify' in get_perms(self.subject):
            # --------------------------------------------------------
            # 0: user permissions prohibit operation -> abort
            # --------------------------------------------------------
            popup = QMessageBox(
                  QMessageBox.Critical,
                  "Unauthorized Operation",
                  "User's roles do not permit this operation",
                  QMessageBox.Ok, self.parent())
            popup.show()
            event.ignore()
            return
        mod_acts = []
        position = event.scenePos()
        seq = 0
        # find nearest x position to the left -- seq is greater by 1
        for evt_block in self.timeline.evt_blocks:
            if position.x() > evt_block.x():
                seq = evt_block.activity.sub_activity_sequence + 1
                # orb.log.debug(f'  seq of new block: {seq}.')
                break
        # increment the sequence of all activities to the right ...
        for evt_block in self.timeline.evt_blocks:
            n = evt_block.activity.sub_activity_sequence
            if n >= seq:
                # orb.log.debug(f'  incrementing {n} to {n+1}.')
                evt_block.activity.sub_activity_sequence += 1
                mod_acts.append(evt_block.activity)
        # seq = len(self.subject.sub_activities) + 1
        # activity type is one of "Cycle", "Op", "Event"
        activity_type_name = event.mimeData().text()
        activity_type = orb.select("ActivityType", name=activity_type_name)
        prefix = self.subject.name
        act_name = ' '.join([prefix, activity_type_name])
        project = orb.get(state.get('project'))
        activity = clone("Activity", generate_id=True, name=act_name,
                         activity_type=activity_type, owner=project,
                         of_system=self.act_of,
                         sub_activity_sequence=seq,
                         sub_activity_of=self.subject)
        for act in mod_acts:
            # use the clone's mod_datetime for all updated activities
            act.mod_datetime = activity.mod_datetime
        orb.db.commit()
        mod_acts.append(activity)
        # set time units locally to default: "minutes" -- if connected,
        # this will be done in the callback after vger.save() succeeds
        set_dval(activity.oid, "time_units", "minutes")
        evt_block = ActivityBlock(activity=activity, scene=self)
        evt_block.setPos(event.scenePos())
        self.addItem(evt_block)
        self.timeline.update_timeline()

    def on_act_name_mod(self, act=None, remote=False):
        """
        Handle 'act name mod' signal from ActInfoTable, meaning an activity's
        name was modified.
        """
        # orb.log.debug('* scene: received "act name mod" signal')
        for item in self.timeline.evt_blocks:
            # orb.log.debug(f'  checking for {item.activity.name} by oid')
            if item.activity.oid == act.oid:
                item.update_block_label()

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)


# TimelineWidget displays the timeline of either
# (1) if the subject of the timeline is the Mission, all of the Mission's
# activities, or
# (2) if the subject of the timeline is a non-Mission activity, all of that
# activity's sub-activities

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
        # "deleted object" is sent by pangalaxian when it receives a "deleted"
        # pubsub message ...
        dispatcher.connect(self.delete_activity, "deleted object")
        # "delete activity" is sent by activity block when it is removed ...
        dispatcher.connect(self.delete_activity, "delete activity")
        dispatcher.connect(self.on_act_name_mod, "act name mod")
        dispatcher.connect(self.set_new_scene, "set new scene")
        self.setUpdatesEnabled(True)

    @property
    def system(self):
        return getattr(self.subject, 'of_system', None) or None

    def minimumSize(self):
        return QSize(800, 500)

    def set_new_scene(self, remote=False, remote_mod_acts=None):
        """
        Create a new scene with new subject activity or an empty scene if no
        subject activity.
        """
        orb.log.debug('  - set_new_scene ...')
        scene = TimelineScene(self, self.subject)
        subacts = getattr(self.subject, 'sub_activities', []) or []
        subacts.sort(key=lambda x: getattr(x,
                                   'sub_activity_sequence', 0) or 0)
        nbr_of_subacts = len(subacts)
        if (self.subject != None) and (nbr_of_subacts > 0):
            # orb.log.debug(f'  - placing {nbr_of_subacts} sub-acts:')
            for activity in reversed(subacts):
                if (activity.of_system == self.system):
                    item = ActivityBlock(activity=activity, scene=scene)
                    # n = activity.sub_activity_sequence
                    # name = activity.name
                    # orb.log.debug(f'    + [{n}] {name}')
                    scene.addItem(item)
                scene.update()
            scene.timeline.update_timeline(remote=remote,
                                           remote_mod_acts=remote_mod_acts)
            ada = getattr(self, 'add_defaults_action', None)
            if ada:
                self.add_defaults_action.setEnabled(False)
        elif (isinstance(self.subject, orb.classes['Mission'])
              and (nbr_of_subacts == 0)):
            # orb.log.debug(' - no sub-acts; can add default sub-acts')
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

    def activity_drill_down(self, act):
        """
        Handle a double-click event on an activity block, creating and
        displaying a new timeline for its sub-activities.

        Args:
            obj (ActivityBlock):  the block that received the double-click
        """
        dispatcher.send("drill down", obj=act, act_of=self.system)
        previous_oid = self.subject.oid
        self.subject = act
        self.set_new_scene()
        self.back_action.setEnabled(True)
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
        self.add_defaults_action = self.create_action(
                                    "Add Default Activities",
                                    slot=self.add_default_activities,
                                    icon="tools",
                                    tip="add default activities")
        self.toolbar.addAction(self.add_defaults_action)
        self.add_defaults_action.setEnabled(False)
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
        Load the last timeline from "timeline history" and remove it from the
        stack.
        """
        orb.log.debug('* load last timeline')
        if state.get('timeline history'):
            oid = state['timeline history'].pop() or ''
            self.subject = orb.get(oid)
            self.set_new_scene()
            if state.get('timeline history'):
                if len(state['timeline history']) > 1:
                    self.back_action.setEnabled(True)
                else:
                    self.back_action.setEnabled(False)
            dispatcher.send("new timeline", subject=self.subject)

    def add_default_activities(self):
        orb.log.debug('* add_default_activities()')
        sub_acts = getattr(self.subject, 'sub_activities', None)
        if sub_acts:
            orb.log.debug('  subject already has sub-activities, returning.')
            return
        acts = []
        seq = 0
        for name in DEFAULT_ACT_NAMES:
            activity_type = orb.get(
                            "pgefobjects:ActivityType.Operation")
            project = orb.get(state.get('project'))
            act_name = name
            NOW = dtstamp()
            user = orb.get(state.get('local_user_oid') or 'me')
            activity = clone("Activity", generate_id=True, name=act_name,
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
        # orb.log.debug('* sending "new objects" signal')
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
        if not isinstance(obj, orb.classes['Activity']):
            orb.log.debug('  - obj is not an Activity or Mission.')
            return
        subj_oid = getattr(self.subject, 'oid', '')
        # name = getattr(obj, 'name', None) or '[no name]'
        if remote:
            # NOTE: when a "deleted" pubsub message is received by pangalaxian
            # with cname "Mission" or "Activity" it will NOT delete the object
            # if conops is running (state["conops"] == True) but will send
            # dispatcher "deleted object"
            # signal ...
            objs_to_delete = [obj]
            if obj.sub_activities:
                objs_to_delete += obj.sub_activities
            if oid == subj_oid:
                orb.log.debug('  is current subject ...')
                project = orb.get(state.get('project'))
                mission = orb.select('Mission', owner=project)
                if obj is mission:
                    self.subject = None
                else:
                    self.subject = mission
                orb.delete(objs_to_delete)
                self.set_new_scene()
            else:
                current_act_oids = [getattr(act, 'oid', '') for act in
                                    self.subject.sub_activities]
                if oid in current_act_oids:
                    # orb.log.debug('  found in current timeline, removing ...')
                    # find activity block and remove it
                    for item in self.scene.items():
                        if (hasattr(item, 'activity') and
                            item.activity and item.activity.oid == oid):
                            # name = item.activity.name
                            # orb.log.debug(f'  removing block "{name}"')
                            self.scene.removeItem(item)
                    orb.delete(objs_to_delete)
                else:
                    # orb.log.debug('  not in current timeline, deleting ...')
                    orb.delete(objs_to_delete)
                # set_new_scene() might not be necessary here ...
                self.set_new_scene()
            # not necessary for deletions originating remotely ...
            # dispatcher.send("deleted object", oid=oid,
                            # cname='Activity')
        else:
            # locally originated action ...
            # orb.log.debug(f'  - deleting activity {name}')
            objs_to_delete = [obj] + obj.sub_activities
            # TODO: check whether any sub_activities have blocks ...
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
            orb.log.debug('  <= 8 activity blocks ... no rescale.')
            self.scale = 70
        else:
            orb.log.debug(f'  {n} activity blocks -- rescaling ...')
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
        # br_parms = (br.x(), br.y(), br.width(), br.height())
        # orb.log.debug(f'  scene items bounding rect: ({br_parms})')
        vp_x = -50.0
        vp_y = br.y() - 20
        vp_width = br.width() + 50.0
        vp_height = br.height() + 50.0
        vp_rect = QRectF(vp_x, vp_y, vp_width, vp_height)
        self.view.setSceneRect(vp_rect)
        # vp_parms = (vp_x, vp_y, vp_width, vp_height)
        # orb.log.debug(f'  viewport: ({vp_parms})')
        # self.get_scene_coords()

    def get_scene_coords(self):
        br = self.scene.itemsBoundingRect()
        self.br = br
        # br_parms = (br.x(), br.y(), br.width(), br.height())
        # orb.log.debug(f'  scene items bounding rect: ({br_parms})')
        # view_polygon = self.view.mapFromScene(
                                    # br.x(), br.y(), br.width(), br.height())
        # vbr = view_polygon.boundingRect()
        # vbr_parms = (vbr.x(), vbr.y(), vbr.width(), vbr.height())
        # orb.log.debug(f'  view coords of bounding rect: ({vbr_parms})')
        # find the view origin (0, 0) in scene coordinates ...
        # v_origin = self.view.mapToScene(0, 0)
        # vo_coords = (v_origin.x(), v_origin.y())
        # orb.log.debug(f'  scene coords of view origin: ({vo_coords})')

    def on_act_name_mod(self, act, remote=False):
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
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)
        self.title_widget = NameLabel('')
        self.title_widget.setStyleSheet('font-weight: bold; font-size: 14px')
        self.main_layout.addWidget(self.title_widget)
        self.set_title_text()
        self.set_table()
        self.setSizePolicy(QSizePolicy.MinimumExpanding,
                           QSizePolicy.Fixed)
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
        # self.main_layout.addStretch()
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
        self.reset_table()

    def on_drill_up(self, obj=None, position=None):
        if self.position != 'sub':
            self.reset_table()

    def on_subsystem_changed(self, act=None, act_of=None, position=None):
        if self.position == 'main':
            self.reset_table()
        if self.position == 'sub':
            self.setEnabled(True)
            self.act_of = act_of
            self.reset_table()


class TimelineModeler(QWidget):
    """
    Tool for modeling a timeline of activities, which enables the definition of
    a Concept of Operations for a system as it will be used in the context of a
    mission.

    The GUI structure of the TimelineModeler is:

    - [left side]  activity_table (ActivityWidget)
    - [middle]     main_timeline (TimelineWidget(QWidget))
                   + scene (TimelineScene(QGraphicsScene))
                     * timeline (Timeline(QGraphicsPathItem))
                     * activity blocks (ActivityBlock(QGraphicsPolygonItem))
    - [right side] Op blocks palette (QToolBox)
    """

    def __init__(self, subject=None, usage=None, parent=None):
        """
        Initialize.

        Keyword Args:
            subject (Activity): (optional) a specified Activity
            parent (QWidget):  parent widget
        """
        super().__init__(parent=parent)
        orb.log.info('* TimelineModeler initializing')
        if subject:
            self.subject = subject
        else:
            proj_id = self.project.id
            self.mission = orb.select('Mission', owner=self.project)
            if not self.mission:
                orb.log.debug('* [TimelineModeler] creating a new Mission ...')
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
                self.mission = clone('Mission', id=mission_id,
                                     name=mission_name,
                                     owner=self.project,
                                     create_datetime=NOW, mod_datetime=NOW,
                                     creator=user, modifier=user)
                orb.save([self.mission])
                dispatcher.send("new object", obj=self.mission)
            self.subject = self.mission
        self._usage = usage
        self.create_toolbox()
        # no toolbar needed yet ...
        # self.init_toolbar()
        self.set_widgets()
        self.setWindowTitle('Timeline Modeler')
        dispatcher.connect(self.act_block_drill_down, "block double clicked")
        dispatcher.connect(self.on_activity_got_focus, "activity focused")
        dispatcher.connect(self.on_remote_mod_acts, "remote new or mod acts")
        dispatcher.connect(self.on_usage_set, "powermodeler set usage")

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

    def on_usage_set(self, usage=None):
        self.usage = usage

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
        orb.log.debug(' - TimelineModeler.init_toolbar() ...')
        self.toolbar = QToolBar("Tools")

    def create_toolbox(self):
        """
        Create the toolbox for activities and modes.
        """
        orb.log.debug(' - TimelineModeler.create_toolbox() ...')
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
        the "subject" (current activity).

        Note that focusing (mouse click) on an activity in the timeline will
        make that activity the subject (current activity) in the ConOpsModeler.
        """
        orb.log.debug(' - TimelineModeler.set_widgets() ...')
        self.main_timeline = TimelineWidget(self.subject)
        self.main_timeline.setSizePolicy(QSizePolicy.MinimumExpanding,
                                         QSizePolicy.Fixed)
        self.activity_table = self.create_activity_table()
        # ====================================================================
        central_layout = QHBoxLayout()
        central_layout.addWidget(self.activity_table, alignment=Qt.AlignTop)
        central_layout.addWidget(self.main_timeline, alignment=Qt.AlignTop)
        central_layout.addWidget(self.toolbox,
                                 alignment=Qt.AlignTop|Qt.AlignRight)
        self.setLayout(central_layout)
        # ====================================================================
        dispatcher.connect(self.rebuild_table, "order changed")
        dispatcher.connect(self.on_new_timeline, "new timeline")
        # NOTE: "new activity" signal is deprecated
        dispatcher.connect(self.on_delete_activity, "delete activity")
        dispatcher.connect(self.on_delete_activity, "remove activity")
        dispatcher.connect(self.on_delete_activity, "deleted object")

    def create_activity_table(self, timeline=None):
        """
        Create an ActivityWidget containing an ActInfoTable.

        Keyword Args:
            timeline (Timeline): the timeline graphic item contained in the
                TimelineScene of the main_timeline (TimelineWidget)
        """
        # orb.log.debug("* TimelineModeler.create_activity_table()")
        timeline = timeline or self.main_timeline.scene.timeline
        activity_table = ActivityWidget(self.subject, timeline=timeline,
                                        parent=self)
        activity_table.setAttribute(Qt.WA_DeleteOnClose)
        activity_table.setMaximumWidth(500)
        return activity_table

    def on_new_timeline(self, subject=None):
        """
        Respond to a new timeline scene having been set, such as resulting from
        an activity block drill-down.

        Keyword Args:
            subject (Activity): subject of the new timeline
        """
        # orb.log.debug("* conops: on_new_timeline()")
        self.subject = subject
        self.rebuild_table()

    def rebuild_table(self):
        orb.log.debug("* timeline: rebuild_table()")
        central_layout = self.layout()
        if getattr(self, 'activity_table', None):
            central_layout.removeWidget(self.activity_table)
            self.activity_table.parent = None
            self.activity_table.close()
            self.activity_table = None
        self.activity_table = self.create_activity_table(
                                    timeline=self.main_timeline.scene.timeline)
        central_layout.insertWidget(0, self.activity_table,
                                    alignment=Qt.AlignTop)

    def act_block_drill_down(self, act):
        """
        Handler for double-click on an activity block -- drill-down to view
        and/or create sub_activities timeline.

        Args:
            act (Activity): the Activity instance that was double-clicked
        """
        orb.log.debug("  - TimelineModeler.act_block_drill_down()...")
        try:
            orb.log.debug(f'     + activity: {act.name}')
            self.main_timeline.activity_drill_down(act)
        except Exception as e:
            orb.log.debug("    exception occurred:")
            orb.log.debug(e)

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
        n_objs = len(objs or [])
        orb.log.debug('* received "remote new or mod acts" signal')
        orb.log.debug(f'  with {n_objs} objects:')
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
            self.main_timeline.set_new_scene(remote=True, remote_mod_acts=objs)
            if sequence_adjusted:
                self.rebuild_table()


if __name__ == '__main__':
    import sys
    from pangalactic.core.serializers import deserialize
    from pangalactic.core.test.utils import (create_test_project,
                                             create_test_users)
    from pangalactic.node.startup import setup_dirs_and_state
    # orb.start(home='junk_home', debug=True)
    orb.start(home='/home/waterbug/cattens_home_dev', debug=True)
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
    test_act = False
    if test_act:
        # test ActivityWidget
        if not mission.sub_activities:
            launch = clone('Activity', id='launch', name='Launch',
                           owner=H2G2, sub_activity_of=mission)
            sub_act_role = '1'
            orb.save([launch])
        mw = ActivityWidget(subject=mission)
    else:
        mw = TimelineModeler()
    mw.show()
    sys.exit(app.exec_())

