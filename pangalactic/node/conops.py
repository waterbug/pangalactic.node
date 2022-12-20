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

from louie import dispatcher

from PyQt5.QtCore import Qt, QRectF, QPointF, QPoint
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
from pangalactic.core.names       import get_acr_id, get_acr_name
from pangalactic.core.uberorb     import orb
from pangalactic.node.activities  import ActivityTable, ModesTool
from pangalactic.node.buttons     import SizedButton, ToolButton
from pangalactic.node.diagrams.shapes import BlockLabel
from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.utils       import clone
from pangalactic.node.widgets     import NameLabel
from pangalactic.core.serializers import serialize, deserialize
from pangalactic.core.parametrics import get_pval


class EventBlock(QGraphicsPolygonItem):

    def __init__(self, activity=None, parent_activity=None, style=None,
                 parent=None):
        """
        Initialize Block.

        Keyword Args:
            activity (Activity):  the activity the block represents
            parent_activity (Activity):  the parent of this activity
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
        self.setBrush(Qt.white)
        path = QPainterPath()
        #---draw blocks depending on the 'shape' string passed in
        self.parent_activity = (parent_activity or
                                self.activity.where_occurs[0].composite_activity)
        dispatcher.connect(self.id_changed_handler, "repositioned activity")
        self.create_actions()

        if self.activity.activity_type.name == "Operation":
            self.myPolygon = QPolygonF([
                    QPointF(-50, 50), QPointF(50, 50),
                    QPointF(50, -50), QPointF(-50, -50)
            ])
        elif self.activity.activity_type.name == "Event":
             self.myPolygon = QPolygonF([
                     QPointF(0, 0), QPointF(-50, 80),
                     QPointF(50, 80)
             ])
        else:
            path.addEllipse(-100, 0, 200, 200)
            self.myPolygon = path.toFillPolygon(QTransform())
        self.setPolygon(self.myPolygon)
        self.block_label = BlockLabel(getattr(self.activity, 'name', '') or '',
                                      self, point_size=8)
        dispatcher.connect(self.on_activity_edited, 'activity edited')

    def id_changed_handler(self, activity=None):
        try:
            if activity is self.activity:
                self.block_label.set_text(self.activity.name)
            orb.log.debug('* sending "activity modified" signal')
            dispatcher.send("activity modified", activity=activity,
                            position=self.scene().position)
        except:
            pass

    def on_activity_edited(self, activity=None):
        act_oid = getattr(activity, 'oid', None)
        if act_oid == self.activity.oid:
            self.block_label.set_text(getattr(self.activity, 'name',
                                      'No Name') or 'No Name')

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        dispatcher.send("double clicked", act=self.activity)

    def contextMenuEvent(self, event):
        self.menu = QMenu()
        self.menu.addAction(self.delete_action)
        self.menu.addAction(self.edit_action)
        self.menu.exec(QCursor.pos())

    def create_actions(self):
        self.delete_action = QAction("Delete", self.scene(),
                                     statusTip="Delete Item",
                                     triggered=self.delete_item)
        self.edit_action = QAction("Edit", self.scene(),
                                   statusTip="Edit activity",
                                   triggered=self.edit_activity)

    def edit_activity(self):
        self.scene().edit_parameters(self.activity)

    def delete_item(self):
        orb.log.debug('* sending "remove activity" signal')
        dispatcher.send("remove activity", act=self.activity)

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


class Timeline(QGraphicsPathItem):

    def __init__(self, scene, parent=None):
        super().__init__(parent)
        self.item_list = []
        self.path_length = 1000
        self.make_path()
        self.length = self.path.length()-2*self.circle_length
        self.num_of_item = len(scene.current_activity.sub_activities)
        self.make_point_list()
        self.current_positions = []

    def make_path(self):
        self.path =  QPainterPath(QPointF(100, 250))
        self.path.arcTo(QRectF(0, 200, 100, 100), 0, 360)
        self.circle_length = self.path.length()
        self.path.arcTo(QRectF(self.path_length, 200, 100, 100), 180, 360)
        self.setPath(self.path)

    def remove_item(self, item):
        if item in self.item_list:
            self.item_list.remove(item)
            self.num_of_item = len(self.item_list)
        self.update_timeline()

    def add_item(self, item):
        self.item_list.append(item)
        self.num_of_item = len(self.item_list)
        self.update_timeline(initial=True)

    def update_timeline(self, initial=False):
        self.calc_length()
        self.make_path()
        self.make_point_list()
        self.reposition(initial=initial)

    def calc_length(self):
        if len(self.item_list) <= 5:
            self.path_length = 1000
        else:
            # adjust timeline length and rescale scene
            delta = len(self.item_list) - 5
            self.path_length = 1000 + (delta // 2) * 300
            scale = 70 - (delta // 2) * 10
            pscale = str(scale) + "%"
            dispatcher.send("rescale timeline", percentscale=pscale)

    def make_point_list(self):
        self.length = self.path.length()-2*self.circle_length
        factor = self.length/(len(self.item_list)+1)
        self.list_of_pos = [(n+1)*factor+100
                            for n in range(0, len(self.item_list))]

    def populate(self, item_list):
        self.item_list = item_list
        # if len(self.item_list) > 5 :
        #     self.extend_timeline()
        # self.make_point_list()
        # self.reposition()
        self.update_timeline()

    def reposition(self, initial=False):
        # FIXME:  revise to use "of_function"/"of_system" (Acu/PSU)
        parent_act = self.scene().current_activity
        item_list_copy = self.item_list[:]
        self.item_list.sort(key=lambda x: x.scenePos().x())
        same = True
        for item in self.item_list:
            if self.item_list.index(item) != item_list_copy.index(item):
                same = False

        for i, item in enumerate(self.item_list):
            item.setPos(QPoint(self.list_of_pos[i], 250))
            # FIXME: this will not select a unique activity if an activity is
            # used more than once in the timeline ...
            acr = orb.select("ActCompRel", composite_activity=parent_act,
                             sub_activity=item.activity)
            acr.sub_activity_sequence = self.list_of_pos[i]
            orb.save([acr])
            # dispatcher.send("modified object", obj=acr)
            if initial:
                acr.sub_activity.id = (acr.sub_activity.id or
                                       acr.sub_activity_sequence)
                acr.sub_activity.name = (acr.sub_activity.name or
                                         "{} {}".format(parent_act.name,
                                                        str(i)))
                orb.save([acr.sub_activity])
                dispatcher.send("repositioned activity",
                                activity=acr.sub_activity)
                # FIXME: why is this commented???
                # dispatcher.send("modified object", obj=acr.sub_activity)
        if not same:
            act = self.scene().current_activity
            if act.of_function:
                dispatcher.send("order changed",
                                composite_activity=act, act_of=act.of_function,
                                position=self.scene().position)
            elif act.of_system:
                dispatcher.send("order changed",
                                composite_activity=act, act_of=act.of_system,
                                position=self.scene().position)
        self.update()


class TimelineScene(QGraphicsScene):
    def __init__(self, parent, current_activity=None, act_of=None,
                 position=None):
        super().__init__(parent)
        self.position = position
        self.current_activity = current_activity
        self.timeline = Timeline(self)
        self.addItem(self.timeline)
        self.focusItemChanged.connect(self.focus_changed_handler)
        self.current_focus = None
        self.act_of = act_of
        self.grabbed_item = None

    def focus_changed_handler(self, new_item, old_item):
        if (self.position == "top" and
            new_item is not None and
            new_item != self.current_focus):
            dispatcher.send("activity focused", act=self.focusItem().activity)

    def mousePressEvent(self, mouseEvent):
        super().mousePressEvent(mouseEvent)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self.grabbed_item = self.mouseGrabberItem()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.grabbed_item != None:
            self.grabbed_item.setPos(event.scenePos().x(), 250)
            self.timeline.reposition()
        self.grabbed_item == None

    def dropEvent(self, event):
        ### NOTE: do not limit "Cycle" activities to top system
        # if ((event.mimeData().text() == "Cycle") and
            # (self.act_of.product_type.id != 'spacecraft')):
            # pass
        # else:
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
                             of_function=self.act_of)
        elif isinstance(self.act_of, orb.classes['ProjectSystemUsage']):
            activity = clone("Activity", id=act_id, name=act_name,
                             activity_type=activity_type, owner=project,
                             of_system=self.act_of)
        else:
            activity = clone("Activity", id=act_id, name=act_name,
                             activity_type=activity_type, owner=project)
        acr_id = get_acr_id(self.current_activity.id, activity.id, seq)
        acr_name = get_acr_name(self.current_activity.name, activity.name, seq)
        acr = clone("ActCompRel", composite_activity=self.current_activity,
                    sub_activity=activity, id=acr_id, name=acr_name)
        orb.db.commit()
        item = EventBlock(activity=activity,
                          parent_activity=self.current_activity)
        item.setPos(event.scenePos())
        self.addItem(item)
        self.timeline.add_item(item)
        orb.log.debug('* sending "new activity" signal')
        dispatcher.send("new activity",
                        composite_activity=self.current_activity,
                        act_of=self.act_of, position=self.position)
        self.update()
        dispatcher.send("new object", obj=acr)

    def edit_parameters(self, activity):
        view = ['id', 'name', 'description']
        panels = ['main', 'parameters']
        pxo = PgxnObject(activity, edit_mode=True, view=view,
                         panels=panels, modal_mode=True, parent=self.parent())
        pxo.show()

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)


# TODO:  we need a subclass of TimelineWidget (maybe SubTimelineWidget) that
# displays the timelines of either (1) if TimelineWidget activity is the
# Mission, a selected project system or group of systems (e.g. a selected SC,
# all SC's, ground system, all of the above, etc.), or (2) if TimelineWidget
# activity is a non-Mission activity instance, all subsystems of the current
# activity's "of_function" component or "of_system" system.

class TimelineWidget(QWidget):
    def __init__(self, activity, position=None, parent=None):
        super().__init__(parent=parent)
        orb.log.debug(' - initializing TimelineWidget ...')
        self.activity = activity
        self.position = position
        self.possible_systems = []
        if state.get('discipline_subsystems'):
            self.possible_systems = list(state.get(
                                         'discipline_subsystems').values())
        self.plot_win = None
        self.subsys_ids = []
        self.create_subsys_list()
        self.init_toolbar()
        #### To do : make different title for subsystem timeline ##############
        if activity.of_function:
            ref_des = activity.of_function.reference_designator
            title_txt = f'{ref_des} {activity.name}'
            self.title = NameLabel(title_txt)
        elif activity.of_system:
            role = activity.of_system.system_role
            title_txt = f'{role} {activity.name}'
            self.title = NameLabel(title_txt)
        elif isinstance(activity, orb.classes['Mission']):
            title_txt = f'{activity.owner.id} Mission'
            self.title = NameLabel(title_txt)
        self.title.setStyleSheet(
                        'font-weight: bold; font-size: 18px; color: purple')
        # self.setVisible(visible)
        # self.set_title()
        self.scene = self.set_new_scene()
        self.view = TimelineView(self)
        self.update_view()
        # self.statusbar = QStatusBar()
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.title)
        self.layout.addWidget(self.toolbar)
        self.layout.addWidget(self.view)
        # self.layout.addWidget(self.statusbar)
        self.setLayout(self.layout)
        self.history = []
        # self.show_history()
        self.sceneScaleChanged("70%")
        self.current_subsystem_index = 0
        self.deleted_acts = []
        dispatcher.connect(self.change_subsystem, "make combo box")
        dispatcher.connect(self.delete_activity, "remove activity")
        # dispatcher.connect(self.disable_widget, "cleared activities")
        dispatcher.connect(self.enable_clear, "new activity")
        dispatcher.connect(self.on_activity_edited, 'activity edited')
        dispatcher.connect(self.on_rescale_timeline, "rescale timeline")
        self.setUpdatesEnabled(True)

    @property
    def system(self):
        sys = None
        if self.activity.of_function:
            sys = self.activity.of_function
        elif self.activity.of_system:
            sys = self.activity.of_system
        return sys

    def enable_clear(self, act_of=None):
        if self.system == act_of:
            self.clear_activities_action.setDisabled(False)

    def disable_widget(self, parent_act=None):
        try:
            # if ((self.act_of != self.system) and
                # (self.activity != parent_act)):
            if self.activity != parent_act:
                self.scene = self.set_new_scene()
                self.update_view()
                self.setDisabled(True)
                dispatcher.send("disable widget")
        except:
            pass

    def set_title(self):
        # try:
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
            if self.activity.activity_type:
                txt += ' ' + self.activity.activity_type.name
            txt += ': '
            title = red_text.format(txt)
        if isinstance(self.system, orb.classes['Product']):
            title += blue_text.format(self.system.name + ' System ')
        title += 'Timeline'
        self.title.setText(title)
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
        self.activity = act
        self.scene = self.set_new_scene()
        self.update_view()
        previous = act.where_occurs[0].composite_activity
        self.history.append(previous)
        self.go_back_action.setDisabled(False)

    def set_new_scene(self):
        """
        Return a new scene with new subject activity or an empty scene if no
        subject activity.
        """
        orb.log.debug(' - set_new_scene ...')
        scene = TimelineScene(self, self.activity,
                              act_of=self.system, position=self.position)
        if (self.activity != None and
            len(self.activity.sub_activities) > 0):
            all_acrs = [(acr.sub_activity_sequence, acr)
                        for acr in self.activity.sub_activities]
            try:
                all_acrs.sort()
            except:
                pass
            item_list=[]
            for acr_tuple in all_acrs:
                acr = acr_tuple[1]
                activity = acr.sub_activity
                if (activity.of_function == self.system or
                    activity.of_system == self.system):
                    self.clear_activities_action.setDisabled(False)
                    item = EventBlock(activity=activity,
                                  parent_activity=self.activity)
                    item_list.append(item)
                    scene.addItem(item)
                scene.update()
            scene.timeline.populate(item_list)
        self.set_title()
        return scene

    def show_empty_scene(self):
        """
        Return an empty scene.
        """
        self.set_title()
        scene = QGraphicsScene()
        return scene

    def update_view(self):
        """
        Update the view with a new scene.
        """
        self.view.setScene(self.scene)
        self.view.show()

    def init_toolbar(self):
        self.toolbar = QToolBar(parent=self)
        self.toolbar.setObjectName('ActionsToolBar')
        self.go_back_action = self.create_action(
                                    "Go Back",
                                    slot=self.go_back,
                                    icon="back",
                                    tip="Back to Previous Page")
        self.toolbar.addAction(self.go_back_action)
        self.go_back_action.setDisabled(True)
        self.clear_activities_action = self.create_action(
                                    "clear activities",
                                    slot=self.clear_activities,
                                    icon="brush",
                                    tip="delete activities on this page")
        self.toolbar.addAction(self.clear_activities_action)
        self.clear_activities_action.setDisabled(True)
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

    def delete_activity(self, act=None):
        """
        Delete an activity, after serializing it and all ActCompRel
        relationships in which it occurs either as a composite activity or a
        sub activity (to enable "undo").

        Keyword Args:
            act (Activity): the activity to be deleted
        """
        # NOTE: DO NOT use dispatcher.send("deleted object") !!
        # -- that will cause a cycle
        oid = getattr(act, "oid", None)
        if oid is None:
            return
        subj_oid = self.activity.oid
        current_subacts = [acr.sub_activity
                           for acr in self.activity.sub_activities]
        # NOTE: not sure what the purpose of this was ...
        # if len(act.sub_activities) == 1:
            # self.clear_activities_action.setEnabled(False)
        if act in current_subacts:
            self.undo_action.setEnabled(True)
            self.deleted_acts.append(self.serialize_act_rels(act))
            objs_to_delete = [act] + act.where_occurs + act.sub_activities
            del_data = [(obj.oid, obj.__class__.__name__)
                        for obj in objs_to_delete]
            orb.delete(objs_to_delete)
            dispatcher.send("removed activity",
                            composite_activity=self.activity,
                            act_of=self.system, position=self.position)
            for oid, cname in del_data:
                dispatcher.send("deleted object", oid=oid, cname=cname)
        else:
            # if activity is not in the current diagram, ignore
            return
        self.scene = self.set_new_scene()
        self.update_view()
        # self.update()
        if oid == subj_oid:
            self.setEnabled(False)

    def serialize_act_rels(self, act):
        """
        Serialize an activity and all ActCompRel relationships in which it
        occurs, to use for "undo".

        Args:
            act (Activity): target activity
        """
        return serialize(orb, [act] + act.where_occurs + act.sub_activities)

    def delete_children(self, act=None):
        """
        Delete the children of the target activity.

        Keyword Args:
            act (Activity): parent activity of the children to be deleted
        """
        act_oid = act.oid
        if len(act.sub_activities) <= 0:
            orb.delete([act])
            dispatcher.send("deleted object", oid=act_oid, cname='Activity')
        elif len(act.sub_activities) > 0:
            for acr in act.sub_activities:
                self.delete_children(act=acr.sub_activity)
            orb.delete([act])
            dispatcher.send("deleted object", oid=act_oid, cname='Activity')

    def clear_activities(self):
        """
        Delete all the activities and their children on this widget.
        """
        txt = "This will permanently delete all activities -- are you sure?"
        confirm_dlg = QMessageBox(QMessageBox.Question, "Delete All?", txt,
                                  QMessageBox.Yes | QMessageBox.No)
        response = confirm_dlg.exec_()
        if response == QMessageBox.Yes:
            children = [acr.sub_activity
                        for acr in self.activity.sub_activities]
            for child in children:
                self.deleted_acts.append(self.serialize_act_rels(child))
                self.delete_children(act=child)
            self.undo_action.setEnabled(True)
            self.scene = self.set_new_scene()
            self.update_view()
            self.clear_activities_action.setDisabled(True)
            # dispatcher.send("cleared activities",
                            # composite_activity=self.activity,
                            # act_of=self.system, position=self.position)

    def sceneScaleChanged(self, percentscale):
        newscale = float(percentscale[:-1]) / 100.0
        self.view.setTransform(QTransform().scale(newscale, newscale))

    def on_rescale_timeline(self, percentscale=None):
        if percentscale in self.scene_scales:
            new_index = self.scene_scales.index(percentscale)
            self.scene_scale_select.setCurrentIndex(new_index)
        else:
            orb.log.debug(f'* rescale factor {percentscale} unavailable')

    def on_activity_edited(self, activity=None):
        if activity == self.activity:
            self.set_title()
        elif self.system in [activity.of_function, activity.of_system]:
            self.update_view()

    def go_back(self):
        try:
            self.activity = self.history.pop()
            if len(self.history) == 0:
                self.go_back_action.setDisabled(True)
            self.scene = self.set_new_scene()
            self.update_view()
            self.disable_widget()
            dispatcher.send("go back", obj=self.activity,
                            position=self.position)
        except:
            pass

    def undo(self):
        try:
            del_acts = self.deleted_acts.pop()
            if len(self.deleted_acts) == 0:
                self.undo_action.setDisabled(True)
            deserialize(orb, del_acts)
            self.scene = self.set_new_scene()
            self.update_view()
            orb.log.debug('* sending "new activity" signal')
            dispatcher.send("new activity",
                            composite_activity=self.activity,
                            position=self.position)
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
        # for acr in self.activity.sub_activities:
            # act=acr.sub_activity
            # oid = getattr(act, "oid", None)
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
        # for system in self.possible_systems:
            # pair = {'name': system}
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

    def create_subsys_list(self):
        # allow for degenerate case (self.system is None)
        if isinstance(self.activity, orb.classes['Mission']):
            lst = [psu.system
                   for psu in self.activity.owner.systems]
        elif hasattr(self.activity.of_function, 'component'):
            lst = [acu.component
                   for acu in self.activity.of_function.component.components]
        elif hasattr(self.activity.of_system, 'system'):
            lst = [acu.component
                   for acu in self.activity.of_system.system.components]
        if lst:
            for system in lst:
                try:
                    subsys_id = system.id
                    # ignore TBD's
                    if subsys_id != "TBD":
                        self.subsys_ids.append(subsys_id)
                except:
                    pass

    def make_subsys_selector(self):
        self.subsys_selector = QComboBox(self)
        self.subsys_selector.addItems(self.subsys_ids)
        self.toolbar.addWidget(self.subsys_selector)
        self.subsys_selector.currentIndexChanged.connect(self.change_subsystem)
        # self.subsys_selector.setCurrentIndex(0)
        dispatcher.send("make combo box", index=0)

    # NOTE: this doesn't appear to be called anywhere
    def update_combo_box(self):
        self.scene = self.set_new_scene()
        self.update_view()

    def change_subsystem(self, index=None):
        orb.log.debug(f"* change_subsystem(index={index})")
        if index >= len(self.subsys_ids):
            orb.log.debug(f"  - index {index} is out of range")
            return
        system_id = getattr(self.system, 'id', 'unknown')
        orb.log.debug(f"  - self.system: {system_id}")
        subsys_id = self.subsys_ids[index]
        orb.log.debug(f"  - subsystem: {subsys_id}")
        orb.log.debug("---------------------------------")
        # Hmmmm ... this is weird
        if system_id != subsys_id:
            if hasattr(self, 'subsys_ids'):
                log_msg = f"  - self.subsys_ids: {self.subsys_ids}"
                orb.log.debug(log_msg)
            try:
                subsys_id = self.subsys_ids[index]
                if self.activity.activity_type.id == 'cycle':
                    pass
                else:
                    existing_subsystems = [acu.component for acu
                                           in self.system.components]
                    for subsystem in existing_subsystems:
                        orb.log.debug(f"  - looking for: {subsys_id}")
                        orb.log.debug(getattr(subsystem, 'id', 'NA'))
                        if getattr(subsystem, 'id', '') == subsys_id:
                            orb.log.debug(f"  - found: {subsys_id}")
                            self.act_of = subsystem
                    self.scene = self.set_new_scene()
                    self.update_view()
                orb.log.debug('* sending "changed subsystem" signal')
                dispatcher.send("changed subsystem",
                                act=self.activity,
                                act_of=self.act_of,
                                position=self.position)
            except:
                orb.log.debug("  - TLWidget.change_subsystem() failed.")


class ConOpsModeler(QMainWindow):
    """
    Tool for modeling a Mission Concept of Operations for the currently
    selected project.

    Attrs:
        history (list):  list of previous subject Activity instances
    """
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
        self.system_list = []
        if project.systems:
            for psu in project.systems:
                self.system_list.append(psu.system)
        mission = orb.select('Mission', name=mission_name)
        self.activity = mission
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
            dispatcher.send("new object", obj=mission)
        self.activity = mission
        self.project = project
        self.create_library()
        self.init_toolbar()
        # NOTE:  bottom dock area is not currently being used
        # self.bottom_dock = QDockWidget()
        # self.bottom_dock.setObjectName('BottomDock')
        # self.bottom_dock.setFeatures(QDockWidget.DockWidgetFloatable)
        # self.bottom_dock.setAllowedAreas(Qt.BottomDockWidgetArea)
        # self.addDockWidget(Qt.BottomDockWidgetArea, self.bottom_dock)
        self.set_widgets(current_activity=self.activity, init=True)
        dispatcher.connect(self.double_clicked_handler, "double clicked")
        dispatcher.connect(self.view_subsystem_activities, "activity focused")

    def create_library(self):
        """
        Create the library of operation/event block types.
        """
        orb.log.debug(' - create_library() ...')
        layout = QGridLayout()
        circle = QPixmap(os.path.join(orb.home, 'images', 'circle.png'))
        triangle = QPixmap(os.path.join(orb.home, 'images', 'triangle.png'))
        square = QPixmap(os.path.join( orb.home, 'images', 'square.png'))
        op_button = ToolButton(square, "  Operation")
        op_button.setData("Operation")
        ev_button = ToolButton(triangle, "  Event")
        ev_button.setData("Event")
        cyc_button = ToolButton(circle, "  Cycle")
        cyc_button.setData("Cycle")
        layout.addWidget(op_button)
        layout.addWidget(ev_button)
        layout.addWidget(cyc_button)
        itemWidget = QWidget()
        itemWidget.setLayout(layout)
        self.library = QToolBox()
        self.library.addItem(itemWidget, "Activities")
        self.library.setSizePolicy(QSizePolicy.Fixed,
                                   QSizePolicy.Fixed)

    def init_toolbar(self):
        orb.log.debug(' - init_toolbar() ...')
        self.toolbar = self.addToolBar("Actions")
        self.toolbar.setObjectName('ActionsToolBar')
        # self.sc_combo_box = QComboBox()
        # self.system_list_ids = [sc.id for sc in self.system_list]
        # self.sc_combo_box.addItems(self.system_list_ids)
        # self.sc_combo_box.currentIndexChanged.connect(self.change_system)
        # self.toolbar.addWidget(self.sc_combo_box)
        self.modes_tool_button = SizedButton("Modes Tool")
        self.modes_tool_button.clicked.connect(self.modes_tool)
        self.toolbar.addWidget(self.modes_tool_button)

    def modes_tool(self):
        win = ModesTool(self.project, parent=self)
        win.show()

    # def change_system(self, index):
        # self.system = self.system_list[index]
        # self.set_widgets(current_activity=self.activity)

    def resizeEvent(self, event):
        state['model_window_size'] = (self.width(), self.height())

    def double_clicked_handler(self, act):
        oid = getattr(act, "oid", None)
        try:
            print("%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%")
            print(get_pval(oid, 'duration'))
        except Exception as e:
            print("%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%")
            print(e)
        if act.activity_type.id == 'cycle':
            self.system_widget.widget_drill_down(act)

    def view_subsystem_activities(self, act=None):
        """
        Display timelines for all subsystems of the current system and any of
        their activities that are sub_activities of the currently focused
        activity.
        """
        self.sub_widget.activity = act
        if act.activity_type.id == 'cycle':
            self.sub_widget.scene = self.sub_widget.show_empty_scene()
            self.sub_widget.update_view()
            self.sub_widget.setEnabled(False)
            dispatcher.send("disable widget")
        else:
            self.sub_widget.setEnabled(True)
            dispatcher.send("enable widget")
            if hasattr(self.sub_widget, 'subsys_selector'):
                self.sub_widget.scene = self.sub_widget.set_new_scene()
                self.sub_widget.update_view()
            else:
                self.sub_widget.make_subsys_selector()

    def set_widgets(self, current_activity=None, init=False):
        """
        Add a TimelineWidget containing timelines for all subsystems of the
        current system with all activities of the subsystems.

        Note that focusing (mouse click) on an activity in the current system
        timeline will make that activity the "current_activity" and restrict
        the display in the "middle" TimelineWidget to sub-activities of the
        "current_activity".

        Keyword Args:
            current_activity (Activity): the main timeline activity that
                currently has focus
        """
        orb.log.debug(' - set_widgets() ...')
        self.system_widget = TimelineWidget(self.activity, position='top')
        self.system_widget.setMinimumSize(900, 150)
        self.sub_widget = TimelineWidget(current_activity, position='middle')
        self.sub_widget.setEnabled(False)
        self.sub_widget.setMinimumSize(900, 150)
        self.outer_layout = QGridLayout()
        act_of = self.activity.of_function or self.activity.of_system
        system_table = ActivityTable(subject=self.activity, parent=self,
                                     act_of=act_of, position='top')
        system_table.setMinimumSize(500, 300)
        system_table.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.outer_layout.addWidget(self.system_widget, 0, 1)
        self.outer_layout.addWidget(system_table, 0, 0)
        subsystem_table = ActivityTable(subject=self.activity,
                                        parent=self, position='middle')
        subsystem_table.setDisabled(True)
        subsystem_table.setMinimumSize(500, 300)
        subsystem_table.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.outer_layout.addWidget(subsystem_table, 1, 0)
        self.outer_layout.addWidget(self.sub_widget, 1, 1)
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


if __name__ == '__main__':
    import sys
    orb.start(home='junk_home', debug=True)
    app = QApplication(sys.argv)
    mw = ConOpsModeler()
    mw.show()
    sys.exit(app.exec_())
