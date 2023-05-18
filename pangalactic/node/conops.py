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
#!/usr/bin/env python

# import pyqtgraph as pg
# from pyqtgraph.dockarea import Dock, DockArea
# from pyqtgraph.parametertree import Parameter, ParameterTree

# import numpy as np

import os

# Louie
from louie import dispatcher

from PyQt5.QtCore import pyqtSignal, Qt, QRectF, QObject, QPointF, QPoint
from PyQt5.QtWidgets import (QAction, QApplication, QComboBox, QDockWidget,
                             QMainWindow, QSizePolicy, QWidget, QGraphicsItem,
                             QGraphicsPolygonItem, QGraphicsScene,
                             QGraphicsView, QGridLayout, QMenu, QToolBox,
                             QGraphicsPathItem, QVBoxLayout, QToolBar,
                             QWidgetAction, QMessageBox)
# from PyQt5.QtWidgets import QStatusBar, QTreeWidgetItem, QTreeWidget
from PyQt5.QtGui import (QIcon, QPixmap, QCursor, QPainter, QPainterPath,
                         QPolygonF, QTransform)
# from PyQt5.QtGui import QGraphicsProxyWidget

# pangalactic
from pangalactic.core             import state
# from pangalactic.core.parametrics import get_pval
from pangalactic.core.meta        import DEFAULT_CLASS_PARAMETERS
from pangalactic.core.serializers import deserialize
from pangalactic.core.uberorb     import orb
from pangalactic.node.activities  import ActivityTable, ModesTool
from pangalactic.node.buttons     import SizedButton, ToolButton
from pangalactic.node.diagrams.shapes import BlockLabel
from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.utils       import clone
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
                      QGraphicsItem.ItemIsFocusable|
                      QGraphicsItem.ItemSendsGeometryChanges)
        self.style = style or Qt.SolidLine
        self.activity = activity
        self.scene = scene
        self.setBrush(Qt.white)
        path = QPainterPath()
        #---draw blocks depending on the 'shape' string passed in
        self.create_actions()
        if self.activity.activity_type.name == "Operation":
            self.myPolygon = QPolygonF([
                    QPointF(-50, 50), QPointF(50, 50),
                    QPointF(50, -50), QPointF(-50, -50)])
        elif self.activity.activity_type.name == "Event":
             self.myPolygon = QPolygonF([
                     QPointF(0, 0), QPointF(-50, 80),
                     QPointF(50, 80)])
        else:
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
        # dispatcher.send("double clicked", act=self.activity)

    def contextMenuEvent(self, event):
        self.menu = QMenu()
        self.menu.addAction(self.delete_action)
        self.menu.addAction(self.edit_action)
        self.menu.exec(QCursor.pos())

    def create_actions(self):
        self.delete_action = QAction("Delete", self.scene,
                                     statusTip="Delete Activity",
                                     triggered=self.delete_block_activity)
        self.edit_action = QAction("Edit", self.scene,
                                   statusTip="Edit activity",
                                   triggered=self.edit_activity)

    def edit_activity(self):
        self.scene.edit_scene_activity(self.activity)

    def delete_block_activity(self):
        orb.log.debug(' - calling scene to emit ()')
        self.scene.delete_scene_activity.emit(self.activity.oid)

    def itemChange(self, change, value):
        return value

    def mousePressEvent(self, event):
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)


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


class TimelineSignals(QObject):

    order_changed = pyqtSignal()


class Timeline(QGraphicsPathItem):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.signals = TimelineSignals()
        self.evt_blocks = []
        self.path_length = 1000
        self.make_path()
        self.current_positions = []

    def make_path(self):
        self.path =  QPainterPath(QPointF(100, 250))
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
        if len(self.evt_blocks) <= 5:
            self.path_length = 1000
        else:
            # adjust timeline length and rescale scene
            delta = len(self.evt_blocks) - 5
            self.path_length = 1000 + (delta // 2) * 300
            scale = 70 - (delta // 2) * 10
            percentscale = str(scale) + "%"
            # TODO: replace with a pyqtSignal ...
            # dispatcher.send("rescale timeline", percentscale=pscale)
            self.scene().rescale_timeline.emit(percentscale)

    def add_evt_block(self, evt_block):
        self.evt_blocks.append(evt_block)
        self.update_timeline()

    def populate(self, evt_blocks):
        self.evt_blocks = evt_blocks
        self.update_timeline()

    def arrange(self):
        # FIXME:  revise to use "of_function"/"of_system" (Acu/PSU)
        parent_act = self.scene().current_activity
        # evt_blocks_list_copy = self.evt_blocks[:]
        self.evt_blocks.sort(key=lambda x: x.scenePos().x())
        # NOTE: don't care if order is same -- call "order changed" anyway
        # same = True
        # for evt_block in self.evt_blocks:
            # if self.evt_blocks.index(evt_block) != evt_blocks_copy.index(
                                                                # evt_block):
                # same = False
        for i, evt_block in enumerate(self.evt_blocks):
            evt_block.setPos(QPoint(self.list_of_pos[i], 250))
            # FIXME: this will not select a unique activity if an activity is
            # used more than once in the timeline ...
            act = evt_block.activity
            act.sub_activity_of = parent_act
            act.sub_activity_sequence = i
            orb.save([act])
            # TODO: replace with a pyqtSignal ...
            # dispatcher.send("modified object", obj=act)
        self.signals.order_changed.emit()
        self.update()


class TimelineScene(QGraphicsScene):

    activity_got_focus = pyqtSignal(str)     # arg: oid
    deleted_object = pyqtSignal(str, str)    # args: oid, cname
    new_activity = pyqtSignal(str)           # args: oid
    scene_activity_edited = pyqtSignal(str)  # args: oid
    delete_scene_activity = pyqtSignal(str)  # args: oid

    def __init__(self, parent, current_activity=None, act_of=None,
                 position=None):
        super().__init__(parent)
        self.position = position
        self.current_activity = current_activity
        if current_activity:
            offnc = current_activity.of_function
            ofsys = current_activity.of_system
            self.act_of = offnc or ofsys
            name = getattr(self.act_of, 'name', None) or 'None'
            orb.log.debug(f'  act_of: {name}')
        self.timeline = Timeline()
        self.addItem(self.timeline)
        self.focusItemChanged.connect(self.focus_changed_handler)
        self.current_focus = None
        self.grabbed_item = None

    def focus_changed_handler(self, new_item, old_item):
        if (self.position == "top" and
            new_item is not None and
            new_item != self.current_focus):
            self.activity_got_focus.emit(self.focusItem().activity.oid)

    def mousePressEvent(self, mouseEvent):
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
        seq = len(self.current_activity.sub_activities) + 1
        # activity type is one of "Cycle", "Operation", "Event"
        activity_type_name = event.mimeData().text()
        activity_type = orb.select("ActivityType", name=activity_type_name)
        prefix = (getattr(self.act_of, 'reference_designator', '') or
                  getattr(self.act_of, 'system_role', '') or
                  getattr(getattr(self.act_of, 'owner', None), 'id', '') or
                  'Timeline')
        act_id = '-'.join([prefix, activity_type_name, str(seq)])
        act_name = ' '.join([prefix, activity_type_name, str(seq)])
        project = orb.get(state.get('project'))
        if isinstance(self.act_of, orb.classes['Acu']):
            activity = clone("Activity", id=act_id, name=act_name,
                             activity_type=activity_type, owner=project,
                             of_function=self.act_of,
                             sub_activity_of=self.current_activity,
                             sub_activity_sequence=seq)
        elif isinstance(self.act_of, orb.classes['ProjectSystemUsage']):
            activity = clone("Activity", id=act_id, name=act_name,
                             activity_type=activity_type, owner=project,
                             of_system=self.act_of,
                             sub_activity_of=self.current_activity,
                             sub_activity_sequence=seq)
        else:
            activity = clone("Activity", id=act_id, name=act_name,
                             activity_type=activity_type, owner=project,
                             sub_activity_of=self.current_activity,
                             sub_activity_sequence=seq)
        orb.db.commit()
        evt_block = EventBlock(activity=activity,
                               parent_activity=self.current_activity,
                               scene=self)
        evt_block.setPos(event.scenePos())
        self.addItem(evt_block)
        self.timeline.add_evt_block(evt_block)
        # self.timeline.arrange()
        orb.log.debug('* scene: sending "new_activity" signal')
        self.new_activity.emit(activity.oid)
        self.update()

    def edit_scene_activity(self, activity):
        view = ['id', 'name', 'description']
        panels = ['main', 'parameters']
        # don't use contingencies for Activity default parameters
        # (t_start, t_end, duration)
        noctgcy = DEFAULT_CLASS_PARAMETERS.get('Activity')
        pxo = PgxnObject(activity, edit_mode=True, view=view, noctgcy=noctgcy,
                         panels=panels, modal_mode=True, parent=self.parent())
        pxo.activity_edited.connect(self.on_activity_edited)
        pxo.show()

    def on_act_mod(self, oid):
        """
        Handle 'act_mod' signal from ActivityInfoTable, meaning an activity was
        modified.
        """
        orb.log.debug('* scene: received "act_mod" signal')
        for item in self.timeline.evt_blocks:
            orb.log.debug(f'  checking {item.activity.name}')
            if item.activity.oid == oid:
                item.update_block_label()

    def on_activity_edited(self, oid):
        # emitted signal causes ActivityTable updates
        self.scene_activity_edited.emit(oid)
        # update activity block labels if necessary
        for item in self.timeline.evt_blocks:
            if item.activity.oid == oid:
                item.update_block_label()

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)


# TODO:  we need a subclass of TimelineWidget (maybe SubTimelineWidget) that
# displays the timelines of either (1) if TimelineWidget activity is the
# Mission, a selected project system or group of systems (e.g. a selected SC,
# all SC's, ground system, all of the above, etc.), or (2) if TimelineWidget
# activity is a non-Mission activity instance, all subsystems of the current
# activity's "of_function" component or "of_system" system.

class TimelineWidget(QWidget):

    object_deleted = pyqtSignal(str, str)  # args: oid, cname

    def __init__(self, activity, position=None, parent=None):
        super().__init__(parent=parent)
        orb.log.debug(' - initializing TimelineWidget ...')
        self.activity = activity
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
        # self.show_history()
        self.sceneScaleChanged("70%")
        self.current_subsystem_index = 0
        self.deleted_acts = []
        # TODO: replace with pyqtSignals ...
        # dispatcher.connect(self.delete_activity, "remove activity")
        # dispatcher.connect(self.enable_clear, "new activity")
        # TODO: need to connect this when scene is created in set_new_scene()
        dispatcher.connect(self.on_rescale_timeline, "rescale timeline")
        self.setUpdatesEnabled(True)

    @property
    def system(self):
        return (getattr(self.activity, 'of_function', None)
                or getattr(self.activity, 'of_system', None)
                or None)

    def set_new_scene(self):
        """
        Return a new scene with new subject activity or an empty scene if no
        subject activity.
        """
        orb.log.debug(' - set_new_scene ...')
        scene = TimelineScene(self, self.activity, position=self.position)
        if (self.activity != None and
            len(self.activity.sub_activities) > 0):
            evt_blocks=[]
            for activity in sorted(self.activity.sub_activities,
                                   key=lambda x: getattr(x,
                                   'sub_activity_sequence', 0) or 0):
                if (activity.of_function == self.system or
                    activity.of_system == self.system):
                    self.clear_activities_action.setDisabled(False)
                    item = EventBlock(activity=activity,
                                      parent_activity=self.activity,
                                      scene=scene)
                    evt_blocks.append(item)
                    scene.addItem(item)
                scene.update()
            scene.timeline.populate(evt_blocks)
        scene.delete_scene_activity.connect(self.delete_activity)
        self.set_title()
        self.scene = scene
        if not getattr(self, 'view', None):
            self.view = TimelineView(self)
        self.view.setScene(self.scene)
        self.view.show()

    def enable_clear(self, act_of=None):
        if self.system == act_of:
            self.clear_activities_action.setDisabled(False)

    def set_title(self):
        # try:
        if not getattr(self, 'title_widget', None):
            self.title_widget = NameLabel('')
            self.title_widget.setStyleSheet(
                'font-weight: bold; font-size: 16px')
        red_text = '<font color="red">{}</font>'
        blue_text = '<font color="blue">{}</font>'
        title = ''
        if isinstance(self.activity, orb.classes['Mission']):
            txt = ''
            project = orb.get(state.get('project'))
            if project:
                txt = project.id + ' '
            txt += 'Mission '
            title = red_text.format(txt)
        elif isinstance(self.activity, orb.classes['Activity']):
            txt = self.activity.name
            txt += ': '
            title = red_text.format(txt)
        if isinstance(self.system, orb.classes['Product']):
            title += blue_text.format(self.system.name + ' System ')
        title += 'Timeline'
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
        # TODO: replace with a pyqtSignal ...
        # dispatcher.send("drill down", obj=act, act_of=self.system,
                        # position=self.position)
        self.activity = act
        self.set_new_scene()
        previous = act.where_occurs[0].composite_activity
        self.history.append(previous)
        # self.go_back_action.setDisabled(False)

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
        # self.go_back_action = self.create_action(
                                    # "Go Back",
                                    # slot=self.go_back,
                                    # icon="back",
                                    # tip="Back to Previous Page")
        # self.toolbar.addAction(self.go_back_action)
        # self.go_back_action.setDisabled(True)
        # self.clear_activities_action = self.create_action(
                                    # "clear activities",
                                    # slot=self.clear_activities,
                                    # icon="brush",
                                    # tip="delete activities on this page")
        # self.toolbar.addAction(self.clear_activities_action)
        # self.clear_activities_action.setDisabled(True)
        self.undo_action = self.create_action(
                                    "undo",
                                    slot=self.undo,
                                    icon="undo",
                                    tip="undo")
        self.toolbar.addAction(self.undo_action)
        self.undo_action.setDisabled(True)
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

    def delete_activity(self, oid, remote=False):
        """
        Delete an activity, after serializing it (to enable "undo").

        Keyword Args:
            act (Activity): the activity to be deleted
        """
        if oid is None:
            return
        act = orb.get(oid)
        if not act:
            return
        current_subacts = self.activity.sub_activities
        subj_oid = self.activity.oid
        if act in current_subacts:
            self.undo_action.setEnabled(True)
            objs_to_delete = [act] + act.sub_activities
            oids = [o.oid for o in objs_to_delete]
            orb.delete(objs_to_delete)
            # for oid, cname in del_data:
                # dispatcher.send("deleted object", oid=oid, cname=cname)
            if oid == subj_oid:
                self.activity = None
                self.setEnabled(False)
            if not remote:
                # TODO: make it "deleted_objects" to be more efficient!!
                #       AND be careful about REMOTE deletion looping!!!
                for act_oid in oids:
                    self.object_deleted.emit(act_oid, 'Activity')
            self.set_new_scene()
        else:
            # if activity is not in the current diagram, ignore
            return

    def delete_children(self, act=None):
        """
        Delete the children of the target activity.

        Keyword Args:
            act (Activity): parent activity of the children to be deleted
        """
        # act_oid = act.oid
        if len(act.sub_activities) == 0:
            orb.delete([act])
            # TODO: replace with pyqtSignal ...
            # dispatcher.send("deleted object", oid=act_oid, cname='Activity')
        elif len(act.sub_activities) > 0:
            for sub_activity in act.sub_activities:
                self.delete_children(act=sub_activity)
            orb.delete([act])
            # TODO: replace with pyqtSignal ...
            # dispatcher.send("deleted object", oid=act_oid, cname='Activity')

    # def clear_activities(self):
        # """
        # Delete all the activities and their children on this widget.
        # """
        # txt = "This will permanently delete all activities -- are you sure?"
        # confirm_dlg = QMessageBox(QMessageBox.Question, "Delete All?", txt,
                                  # QMessageBox.Yes | QMessageBox.No)
        # response = confirm_dlg.exec_()
        # if response == QMessageBox.Yes:
            # children = self.activity.sub_activities
            # for child in children:
                # self.delete_children(act=child)
            # self.undo_action.setEnabled(True)
            # self.set_new_scene()
            # self.clear_activities_action.setDisabled(True)
            # # TODO: replace with pyqtSignal ...
            # # dispatcher.send("cleared activities",
                            # # composite_activity=self.activity,
                            # # act_of=self.system, position=self.position)

    def sceneScaleChanged(self, percentscale):
        newscale = float(percentscale[:-1]) / 100.0
        self.view.setTransform(QTransform().scale(newscale, newscale))

    def on_rescale_timeline(self, percentscale=None):
        if percentscale in self.scene_scales:
            new_index = self.scene_scales.index(percentscale)
            self.scene_scale_select.setCurrentIndex(new_index)
        else:
            orb.log.debug(f'* rescale factor {percentscale} unavailable')

    def on_activity_modified(self, oid):
        activity = orb.get(oid)
        if not activity:
            return
        if activity is self.activity:
            self.set_title()
        if self.system in [activity.of_function, activity.of_system]:
            self.set_new_scene()

    # def go_back(self):
        # try:
            # self.activity = self.history.pop()
            # if len(self.history) == 0:
                # self.go_back_action.setDisabled(True)
            # self.set_new_scene()
            # # TODO: replace with pyqtSignal ...
            # # dispatcher.send("go back", obj=self.activity,
                            # # position=self.position)
        # except:
            # pass

    def undo(self):
        try:
            del_acts = self.deleted_acts.pop()
            if len(self.deleted_acts) == 0:
                self.undo_action.setDisabled(True)
            deserialize(orb, del_acts)
            self.set_new_scene()
            orb.log.debug('* sending "new activity" signal')
            # TODO: replace with pyqtSignal ...
            # dispatcher.send("new activity",
                            # composite_activity=self.activity,
                            # position=self.position)
        except:
            pass

    def plot(self):
        pass
        # orb.log.debug('* plot()')
        # if not self.activity.sub_activities:
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
        # for sub_activity in self.activity.sub_activities:
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
        # params = [{'name': self.activity.id, 'children': lst}]
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


class ConOpsModeler(QMainWindow):
    """
    Tool for modeling a Mission Concept of Operations for the currently
    selected project.

    GUI structure of the ConOpsModeler is:

    ConOpsModeler (QMainWindow)
        - main_timeline (TimelineWidget(QWidget))
          + scene (TimelineScene(QGraphicsScene))
            * timeline (Timeline(QGraphicsPathItem))
        - activity_table (ActivityTable)
        - sub_timeline (TimelineWidget(QWidget))
          + scene (TimelineScene(QGraphicsScene))
            * timeline (Timeline(QGraphicsPathItem))
        - sub_activity_table (ActivityTable)

    Attrs:
        history (list):  list of previous subject Activity instances
    """

    activity_focused = pyqtSignal(str)     # args: oid
    deleted_object = pyqtSignal(str, str)  # args: oid, cname
    new_activity = pyqtSignal(str)         # args: oid
    new_object = pyqtSignal(str)           # args: oid

    def __init__(self, parent=None):
        """
        Initialize the tool.

        Keyword Args:
            parent (QWidget):  parent widget
        """
        super().__init__(parent=parent)
        orb.log.info('* ConOpsModeler initializing')
        project = orb.get(state.get('project'))
        mission_name = ' '.join([project.id, 'Mission'])
        mission = None
        self.usage_list = []
        if project.systems:
            for psu in project.systems:
                self.usage_list.append(psu)
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
            # dispatcher.send("new object", obj=mission)
            self.new_object.emit(mission.oid)
        self.activity = mission
        self.project = project
        self.create_block_library()
        self.init_toolbar()
        self.set_widgets(current_activity=self.activity, init=True)
        self.setWindowTitle('Concept of Operations (Con Ops) Modeler')
        # NOTE:  bottom dock area is not currently being used but may be used
        # for graphs in the future ...
        # self.bottom_dock = QDockWidget()
        # self.bottom_dock.setObjectName('BottomDock')
        # self.bottom_dock.setFeatures(QDockWidget.DockWidgetFloatable)
        # self.bottom_dock.setAllowedAreas(Qt.BottomDockWidgetArea)
        # self.addDockWidget(Qt.BottomDockWidgetArea, self.bottom_dock)
        # TODO: replace with pyqtSignal ...
        # dispatcher.connect(self.on_double_click, "double clicked")

    def create_block_library(self):
        """
        Create the library of operation/event block types.
        """
        orb.log.debug(' - create_block_library() ...')
        layout = QGridLayout()
        circle = QPixmap(os.path.join(orb.home, 'images', 'circle.png'))
        triangle = QPixmap(os.path.join(orb.home, 'images', 'triangle.png'))
        square = QPixmap(os.path.join( orb.home, 'images', 'square.png'))
        op_button = ToolButton(square, "")
        op_button.setData("Operation")
        ev_button = ToolButton(triangle, "")
        ev_button.setData("Event")
        cyc_button = ToolButton(circle, "")
        cyc_button.setData("Cycle")
        layout.addWidget(op_button, 0, 0)
        layout.addWidget(NameLabel("Operation"), 0, 1)
        layout.addWidget(ev_button, 1, 0)
        layout.addWidget(NameLabel("Event"), 1, 1)
        layout.addWidget(cyc_button, 2, 0)
        layout.addWidget(NameLabel("Cycle"), 2, 1)
        library_widget = QWidget()
        library_widget.setLayout(layout)
        self.library = QToolBox()
        self.library.addItem(library_widget, "Activities")
        self.library.setSizePolicy(QSizePolicy.Fixed,
                                   QSizePolicy.Fixed)

    def init_toolbar(self):
        orb.log.debug(' - init_toolbar() ...')
        self.toolbar = self.addToolBar("Actions")
        self.toolbar.setObjectName('ActionsToolBar')
        self.sc_combo_box = QComboBox()
        self.sys_names = [usage.system.name for usage in self.usage_list]
        self.sc_combo_box.addItems(self.sys_names)
        self.sc_combo_box.currentIndexChanged.connect(self.change_system)
        self.toolbar.addWidget(self.sc_combo_box)
        self.modes_tool_button = SizedButton("Modes Tool")
        self.modes_tool_button.clicked.connect(self.display_modes_tool)
        self.toolbar.addWidget(self.modes_tool_button)

    def set_widgets(self, current_activity=None, init=False):
        """
        Add a TimelineWidget containing all activities of the current system.

        Note that focusing (mouse click) on an activity in the timeline will
        make that activity the "current_activity" and restrict the graph
        display to that activity's power graph.

        Keyword Args:
            current_activity (Activity): the main timeline activity that
                currently has focus
        """
        orb.log.debug(' - set_widgets() ...')
        self.main_timeline = TimelineWidget(self.activity, position='top')
        self.main_timeline.setMinimumSize(900, 150)
        self.main_timeline.scene.new_activity.connect(
                                            self.on_main_timeline_new_activity)
        self.main_timeline.object_deleted.connect(
                                        self.on_main_timeline_activity_deleted)
        self.main_timeline.scene.activity_got_focus.connect(
                                                    self.on_activity_got_focus)
        # self.main_timeline.scene.delete_scene_activity.connect(
                                                # self.on_delete_activity)
        self.sub_timeline = TimelineWidget(current_activity, position='middle')
        self.sub_timeline.setEnabled(False)
        self.sub_timeline.setMinimumSize(900, 150)
        self.sub_timeline.scene.new_activity.connect(
                                            self.on_sub_timeline_new_activity)
        self.sub_timeline.object_deleted.connect(
                                        self.on_sub_timeline_activity_deleted)
        self.outer_layout = QGridLayout()
        self.create_activity_table()
        self.main_timeline.scene.new_activity.connect(
                                        self.activity_table.on_activity_added)
        self.main_timeline.scene.timeline.signals.order_changed.connect(
                                        self.rebuild_activity_table)
        self.main_timeline.scene.scene_activity_edited.connect(
                                            self.rebuild_activity_table)
        self.outer_layout.addWidget(self.main_timeline, 0, 1)
        self.outer_layout.addWidget(self.activity_table, 0, 0)
        self.create_sub_activity_table()
        self.sub_timeline.scene.new_activity.connect(
                                    self.sub_activity_table.on_activity_added)
        self.sub_timeline.scene.timeline.signals.order_changed.connect(
                                        self.rebuild_sub_activity_table)
        self.sub_timeline.scene.scene_activity_edited.connect(
                                        self.rebuild_sub_activity_table)
        self.outer_layout.addWidget(self.sub_activity_table, 1, 0)
        self.outer_layout.addWidget(self.sub_timeline, 1, 1)
        self.widget = QWidget()
        self.widget.setMinimumSize(1450, 600)
        self.widget.setLayout(self.outer_layout)
        self.setCentralWidget(self.widget)
        if init:
            self.right_dock = QDockWidget()
            self.right_dock.setObjectName('RightDock')
            self.right_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
            self.right_dock.setAllowedAreas(Qt.RightDockWidgetArea)
            self.addDockWidget(Qt.RightDockWidgetArea, self.right_dock)
            self.right_dock.setWidget(self.library)

    def create_activity_table(self):
        act_of = self.activity.of_function or self.activity.of_system
        self.activity_table = ActivityTable(self.activity, parent=self,
                                            act_of=act_of, position='top')
        self.activity_table.setMinimumSize(500, 300)
        self.activity_table.setSizePolicy(
                                    QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.activity_table.setAttribute(Qt.WA_DeleteOnClose)

    def rebuild_activity_table(self):
        if getattr(self, 'activity_table', None):
            self.outer_layout.removeWidget(self.activity_table)
            self.activity_table.parent = None
            self.activity_table.close()
            self.activity_table = None
        self.create_activity_table()
        self.outer_layout.addWidget(self.activity_table, 0, 0)

    def create_sub_activity_table(self):
        self.sub_activity_table = ActivityTable(self.activity, parent=self,
                                                position='middle')
        self.sub_activity_table.setEnabled(False)
        self.sub_activity_table.setMinimumSize(500, 300)
        self.sub_activity_table.setSizePolicy(QSizePolicy.Fixed,
                                              QSizePolicy.Expanding)
        self.sub_activity_table.setAttribute(Qt.WA_DeleteOnClose)

    def rebuild_sub_activity_table(self):
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
        self.system = self.usage_list[index]
        self.set_widgets(current_activity=self.activity)

    def resizeEvent(self, event):
        state['model_window_size'] = (self.width(), self.height())

    def on_double_click(self, act):
        orb.log.debug("  - on_double_click()...")
        try:
            orb.log.debug(f'     + activity: {act.id}')
            if act.activity_type.id == 'cycle':
                self.main_timeline.widget_drill_down(act)
        except Exception as e:
            orb.log.debug("    exception occurred:")
            orb.log.debug(e)

    def on_activity_got_focus(self, act_oid):
        """
        Display a timeline showing all subactivities of the focused activity.
        """
        act = orb.get(act_oid)
        self.sub_timeline.activity = act
        self.sub_timeline.set_new_scene()
        self.sub_timeline.setEnabled(True)
        self.sub_activity_table.on_activity_focused(act)

    def on_main_timeline_new_activity(self, oid):
        self.rebuild_activity_table()
        # self.new_or_modified_objects.emit(oid)

    def on_sub_timeline_new_activity(self, oid):
        self.rebuild_activity_table()
        # self.new_or_modified_objects.emit(oid)

    def on_main_timeline_activity_deleted(self, oid, cname):
        """
        Handle a main timeline activity deletion.
        """
        self.rebuild_activity_table()

    def on_sub_timeline_activity_deleted(self, oid, cname):
        """
        Handle a sub timeline activity deletion.
        """
        self.rebuild_sub_activity_table()

    # def on_delete_activity(self, oid, cname):
        # self.deleted_object.emit(oid, cname)


if __name__ == '__main__':
    import sys
    # orb.start(home='junk_home', debug=True)
    orb.start(home='/home/waterbug/cattens_home_dev', debug=True)
    app = QApplication(sys.argv)
    mw = ConOpsModeler()
    mw.show()
    sys.exit(app.exec_())

