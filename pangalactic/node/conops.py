#!/usr/bin/env python
# NOTE: fixed div's so old_div is not needed.
# from past.utils import old_div
import pyqtgraph as pg
import os
from collections import namedtuple
from urllib.parse    import urlparse
from louie import dispatcher

from PyQt5.QtCore import Qt, QRectF, QPointF, QPoint, QMimeData

from PyQt5.QtWidgets import (QAction, QApplication, QComboBox, QDockWidget,
                             QMainWindow, QSizePolicy, QWidget, QGraphicsItem,
                             QGraphicsPolygonItem, QGraphicsScene,
                             QGraphicsView, QGridLayout, QMenu, QToolBox,
                             QPushButton, QGraphicsPathItem, QVBoxLayout,
                             QToolBar, QWidgetAction, QStatusBar, QMessageBox)
from PyQt5.QtGui import (QIcon, QTransform, QBrush, QDrag, QPainter, QPen,
                         QPixmap, QCursor, QPainterPath, QPolygonF)

# pangalactic
from pangalactic.core             import state
from pangalactic.core.uberorb     import orb
from pangalactic.core.utils.meta  import asciify, get_block_model_file_name
from pangalactic.node.activities  import ActivityTable, ParameterTable
from pangalactic.node.diagrams.shapes import BlockLabel
from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.utils       import clone
from pangalactic.node.widgets     import NameLabel
from pangalactic.core.serializers import serialize, deserialize
from pangalactic.core             import config
from pangalactic.core.parametrics import get_pval, get_pval_as_str, set_pval, set_pval_from_str
supported_model_types = {
    # CAD models get "eyes" icon, not a lable button
    'step:203' : None,
    'step:214' : None,
    'pgefobjects:Block' : 'Block',
    'pgefobjects:ConOps' : 'Con Ops'}

# a named tuple used in managing the "history" so that it can be navigated
ModelerState = namedtuple('ModelerState', 'obj idx')
# oid of "block" model type
BLOCK_OID = 'pgefobjects:Block'


def get_model_path(model):
    """
    Find the path for a model file.  For now, supported model types include
    STEP AP203, AP214, and PGEF Block and ConOps models.

    CAUTION:  this function short-circuits the model/rep/rep_files sequence and
    assumes that each model can be rendered from one file path!  (Granted, this
    works for STEP files, which may even include external references to other
    STEP files, as the test data "Heart of Gold Spacecraft" AP214 model does.)

    Args:
        model (Model):  the Model for which model files are sought
    Returns:
        a file path in the orb's "vault"
    """
    orb.log.info('* get_model_path(model with oid "{}")'.format(getattr(model,
                                                            'oid', 'None')))
    if not isinstance(model, orb.classes['Modelable']):
        orb.log.info('  not an instance of Modelable.')
        return ''
    # check if there is a STEP AP203 / AP214 model type
    model_type_oid = getattr(model.type_of_model, 'oid', '')
    orb.log.debug('  - model type oid: "{}"'.format(model_type_oid))
    if (model.has_representations and model_type_oid in supported_model_types):
        # FIXME:  for now we assume 1 Representation and 1 File
        rep = model.has_representations[0]
        if rep.has_files:
            rep_file = rep.has_files[0]
            u = urlparse(asciify(rep_file.url))
            if u.scheme == 'vault':
                fpath = os.path.join(orb.vault, u.netloc)
                # FIXME: for now, assume there is just one cad
                # model and file
                if os.path.exists(fpath):
                    return fpath
    elif model_type_oid == BLOCK_OID:
        # special path for pgef block model files
        fname = get_block_model_file_name(model.of_thing)
        fpath = os.path.join(orb.vault, fname)
        if os.path.exists(fpath):
            return fpath
        else:
            return ''
    else:
        return ''


class EventBlock(QGraphicsPolygonItem):

    def __init__(self, activity=None, parent_activity=None, style=None,
                 editable=False, port_spacing=0,parent=None):
        super(EventBlock, self).__init__(parent)
        """
        Initialize Block.

        Args:
            act_type ():
            # position (QPointF):  where to put upper left corner of block
            scene (QGraphicsScene):  scene in which to create block

        Keyword Args:
            obj (Product):  object (Product instance) the block represents
            style (Qt.PenStyle):  style of block border
            editable (bool):  flag indicating whether block properties can be
                edited in place
        """
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
                                self.activity.where_used[0].assembly)
        dispatcher.connect(self.id_changed_handler, "modified activity")
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
            self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setPolygon(self.myPolygon)
        self.block_label = BlockLabel(getattr(self.activity, 'name', '') or '',
                                      self, point_size=8)

    def id_changed_handler(self, activity=None):
        try:
            if activity is self.activity:
                self.block_label.set_text(self.activity.name)
            dispatcher.send("activity modified", activity=activity,
                            position=self.scene().position)
        except:
            pass

    def mouseDoubleClickEvent(self, event):
        super(EventBlock, self).mouseDoubleClickEvent(event)
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
        dispatcher.send("remove activity", act=self.activity)

    def itemChange(self, change, value):
        return value

    def mousePressEvent(self, event):
        super(EventBlock, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super(EventBlock, self).mouseMoveEvent(event)



class TimelineView(QGraphicsView):
    def __init__(self, parent=None):
        super(TimelineView, self).__init__(parent)

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
        super(Timeline, self).__init__(parent)

        self.item_list = []
        self.path_length = 1500
        self.make_path()
        self.length = self.path.length()-2*self.circle_length
        self.num_of_item = len(scene.current_activity.components)
        self.make_point_list()
        self.current_positions = []

    def make_path(self):
        self.path =  QPainterPath(QPointF(100,250))
        self.path.arcTo(QRectF(0, 200 ,100,100), 0, 360)
        self.circle_length = self.path.length()
        self.path.arcTo(QRectF(self.path_length, 200, 100,100), 180, 360)
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
            self.path_length = 1500
        else:
            self.path_length = 1500 + (len(self.item_list)-5)*300

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
        parent_act = self.scene().current_activity
        item_list_copy = self.item_list[:]
        self.item_list.sort(key=lambda x: x.scenePos().x())
        same = True
        for item in self.item_list:
            if self.item_list.index(item) != item_list_copy.index(item):
                same = False

        for i,item in enumerate(self.item_list):
            item.setPos(QPoint(self.list_of_pos[i], 250))
            acu = orb.select("Acu", assembly=parent_act,
                             component=item.activity)
            acu.reference_designator = "{}{}".format(parent_act.id,str(i))
            orb.save([acu])
            dispatcher.send("modified object", obj=acu)
            if initial:
                acu.component.id = acu.component.id or acu.reference_designator
                acu.component.name = acu.component.name or "{} {}".format(
                                                        parent_act.name,str(i))
                orb.save([acu.component])
                dispatcher.send("modified activity", activity=acu.component)
                dispatcher.send("modified object", obj=acu.component)
        if not same:
            dispatcher.send("order changed",
                            parent_act=self.scene().current_activity,
                            position=self.scene().position)
        self.update()

class TimelineScene(QGraphicsScene):
    def __init__(self, parent, current_activity=None, act_of=None,
                 position=None):
        super(TimelineScene, self).__init__(parent)
        self.position = position
        self.current_activity = current_activity
        self.timeline = Timeline(self)
        self.addItem(self.timeline)
        self.focusItemChanged.connect(self.focus_changed_handler)
        self.current_focus = None
        self.act_of = act_of
        self.grabbed_item = None
    def focus_changed_handler(self, new_item, old_item):
        if new_item is not None:
            if new_item != self.current_focus:

                dispatcher.send("activity focused",
                                obj=self.focusItem().activity)

    def mousePressEvent(self, mouseEvent):
        super(TimelineScene, self).mousePressEvent(mouseEvent)

    def mouseMoveEvent(self, event):
        super(TimelineScene, self).mouseMoveEvent(event)
        self.grabbed_item = self.mouseGrabberItem()

    def mouseReleaseEvent(self, event):
        super(TimelineScene, self).mouseReleaseEvent(event)
        if self.grabbed_item != None:
            self.grabbed_item.setPos(event.scenePos().x(), 250)
            self.timeline.reposition()
        self.grabbed_item == None

    def dropEvent(self, event):
        if ((event.mimeData().text() == "Cycle") and
            (self.act_of.product_type.id != 'spacecraft')):
            pass
        else:
            if event.mimeData().text() == "Cycle":
                activity_type = orb.select("ActivityType", name="Cycle")

            elif event.mimeData().text() == "Operation":
                activity_type = orb.select("ActivityType", name="Operation")
            else:
                activity_type = orb.select("ActivityType", name="Event")
            project = orb.get(state.get("project"))
            activity = clone("Activity", activity_type=activity_type,
                             owner=project, activity_of=self.act_of,
                             public=True)
            acu = clone("Acu", assembly=self.current_activity,
                        component=activity)
            orb.save([acu, activity])
            item = EventBlock(activity=activity,
                              parent_activity=self.current_activity)
            item.setPos(event.scenePos())
            self.addItem(item)
            self.timeline.add_item(item)
            dispatcher.send("new activity", parent_act=self.current_activity,
                            act_of=self.act_of, position=self.position)
            dispatcher.send("new object", obj=activity)
            dispatcher.send("new object", obj=acu)
            self.update()

    def edit_parameters(self, activity):
        view = ['id', 'name', 'description']
        panels = ['main', 'parameters']
        pxo = PgxnObject(activity, edit_mode=True, view=view,
                         panels=panels, modal_mode=True, parent=self.parent())
        pxo.show()
    def mouseDoubleClickEvent(self, event):
        super(TimelineScene, self).mouseDoubleClickEvent(event)

class ToolButton(QPushButton):
    def __init__(self, text, parent=None):
        super(ToolButton, self).__init__(text, parent)

    def boundingRect(self):
        return QRectF(-5 , -5, 20, 20)

    def paint(self, painter, option, widget):
        painter.setPen(QPen(Qt.black, 1))
        painter.setBrush(QBrush(Qt.white))
        painter.drawRect(-5, -5, 20,20)

    def mouseMoveEvent(self, event):
        event.accept()
        drag = QDrag(self)
        mime = QMimeData()
        drag.setMimeData(mime)
        mime.setText(self.mime)
        pixmap = QPixmap(34, 34)
        pixmap.fill(Qt.white)
        painter = QPainter(pixmap)
        painter.translate(15, 15)
        painter.setRenderHint(QPainter.Antialiasing)
        self.paint(painter, None, None)
        painter.end()
        dragCursor = QCursor()
        dragCursor.setShape(Qt.ClosedHandCursor)
        drag.setDragCursor(pixmap, Qt.IgnoreAction)
        self.setCursor(Qt.OpenHandCursor)
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(15, 20))
        drag.exec_()

    def setData(self, mimeData):
        self.mime = mimeData

    def dragMoveEvent(self, event):
        event.setAccepted(True)

class ToolbarAction(QWidgetAction):
    def __init__(self, scene, view, toolbar, visible, parent=None):
        super(ToolbarAction, self).__init__(parent=parent)


class TimelineWidget(QWidget):
    def __init__(self, spacecraft, subject_activity=None,
                 act_of=None,parent=None, position=None):
        super(TimelineWidget, self).__init__(parent=parent)
        self.possible_systems = []
        self.position = position
        ds = config.get('discipline_subsystems')
        if ds:
            self.possible_systems = list(config.get(
                                         'discipline_subsystems').values())
        self.plot_win = None
        self.spacecraft = spacecraft
        self.init_toolbar()
        self.subject_activity = subject_activity
        self.act_of = act_of
        #### To do : make different title for subsystem timeline###############
        self.title = NameLabel(getattr(self.subject_activity, '', ' '))
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
        self.sceneScaleChanged("50%")
        self.current_subsystem_index = 0
        self.temp_serialized = []
        self.deleted_acts = []
        dispatcher.connect(self.change_subsystem, "make combo box")
        dispatcher.connect(self.delete_activity, "remove activity")
        dispatcher.connect(self.disable_widget, "cleared activities")
        dispatcher.connect(self.enable_clear, "new activity")
        self.setUpdatesEnabled(True)

    def enable_clear(self, act_of=None):
        if self.act_of == act_of:
            self.clear_activities_action.setDisabled(False)

    def disable_widget(self, parent_act=None):
        try:
            if ((self.act_of != self.spacecraft) and
                (self.subject_activity != parent_act)):
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
        if isinstance(self.subject_activity, orb.classes['Mission']):
            txt = ''
            project = orb.get(state.get('project'))
            if project:
                txt = project.id + ' '
            txt += 'Mission: '
            title = red_text.format(txt)
        elif isinstance(self.subject_activity, orb.classes['Activity']):
            txt = self.subject_activity.name
            if self.subject_activity.activity_type:
                txt += ' ' + self.subject_activity.activity_type.name
            txt += ': '
            title = red_text.format(txt)
        if isinstance(self.act_of, orb.classes['Product']):
            title += blue_text.format(self.act_of.name) + ' '
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

        dispatcher.send("drill down", obj=act, act_of=self.act_of,
                        position=self.position)
        self.subject_activity = act
        self.scene = self.set_new_scene()
        self.update_view()
        previous = act.where_used[0].assembly
        self.history.append(previous)
        self.go_back_action.setDisabled(False)

    def set_new_scene(self):
        """
        Return a new scene with new subject activity or an empty scene if no
        subject activity.
        """
        if self.act_of is not None:
            scene = TimelineScene(self, self.subject_activity,
                                 act_of=self.act_of, position=self.position)
            if (self.subject_activity != None and
                len(self.subject_activity.components) > 0):
                all_acus = [(acu.reference_designator, acu)
                            for acu in self.subject_activity.components]
                try:
                    all_acus.sort()
                except:
                    pass
                item_list=[]
                for acu_tuple in all_acus:
                    acu = acu_tuple[1]
                    activity = acu.component
                    if activity.activity_of == self.act_of:
                        self.clear_activities_action.setDisabled(False)
                        item = EventBlock(activity=activity,
                                      parent_activity=self.subject_activity)
                        item_list.append(item)
                        scene.addItem(item)
                    scene.update()
                scene.timeline.populate(item_list)
            self.set_title()
            return scene
        else:
            self.show_empty_scene()

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
                                    "plot",
                                    slot=self.plot,
                                    tip="plot")
        self.toolbar.addAction(self.plot_action)
        #create and add scene scale menu
        self.scene_scale_select = QComboBox()
        self.scene_scale_select.addItems(["25%", "30%", "40%", "50%", "75%",
                                          "100%"])
        self.scene_scale_select.setCurrentIndex(3)
        self.scene_scale_select.currentIndexChanged[str].connect(
                                                    self.sceneScaleChanged)
        self.toolbar.addWidget(self.scene_scale_select)

    def delete_activity(self, act=None):
        """
        Delete an activity, along with the children of this activity

        Keyword Args:
            act (Activity): the activity to be deleted
        """
        # NOTE: DO NOT dispatcher.send("deleted object") !!
        # -- that will cause a cycle
        oid = getattr(act, "oid", None)
        subj_oid = self.subject_activity.oid
        current_comps = [acu.component
                         for acu in self.subject_activity.components]
        if len(current_comps) == 1:
            self.clear_activities_action.setDisabled(True)
        if act in current_comps:
            self.undo_action.setDisabled(False)
            self.serialized_deleted(act=act)
            self.delete_children(act=act)
            self.deleted_acts.append(self.temp_serialized)
            self.temp_serialized = []
            dispatcher.send("removed activity",
                            parent_act=self.subject_activity,
                            act_of=self.act_of, position=self.position)
        self.scene = self.set_new_scene()
        self.update_view()
        # self.update()
        if oid == subj_oid:
            self.setEnabled(False)

    def serialized_deleted(self, act=None):
        """
        Serialize the target activity and its children.

        Keyword Args:
            act (Activity) -- target activity
        """
        if len(act.components) <= 0:
            serialized_act = serialize(orb, [act, act.where_used[0]],
                                       include_components=True)
            self.temp_serialized.extend(serialized_act)
        elif len(act.components) > 0:
            for acu in act.components:
                self.serialized_deleted(act=acu.component)
            serialized_act = serialize(orb, [act, act.where_used[0]],
                                       include_components=True)
            self.temp_serialized.extend(serialized_act)

    def delete_children(self, act=None):
        """
        Delete the children of the target activity.

        Keyword Args:
            act (Activity): parent activity of the children to be deleted
        """
        if len(act.components) <= 0:
            orb.delete([act])
        elif len(act.components) > 0:
            for acu in act.components:
                self.delete_children(act=acu.component)
            orb.delete([act])

    def clear_activities(self):
        """
        Delete all the activities and their children on this widget.
        """
        children = [acu.component for acu in self.subject_activity.components]
        for child in children:
            self.undo_action.setDisabled(False)
            self.serialized_deleted(act=child)
            self.delete_children(act=child)
        self.deleted_acts.append(self.temp_serialized)
        self.temp_serialized = []
        self.scene = self.set_new_scene()
        self.update_view()
        self.clear_activities_action.setDisabled(True)
        dispatcher.send("cleared activities", parent_act=self.subject_activity,
                        act_of=self.act_of, position=self.position)

    def sceneScaleChanged(self, percentscale):
        newscale = float(percentscale[:-1]) / 100.0
        self.view.setTransform(QTransform().scale(newscale, newscale))

    def go_back(self):
        try:
            self.subject_activity = self.history.pop()
            if len(self.history) == 0:
                self.go_back_action.setDisabled(True)
            self.scene = self.set_new_scene()
            self.update_view()
            self.disable_widget()
            dispatcher.send("go back", obj=self.subject_activity,
                            position=self.position)
        except:
            pass

    def undo(self):
        try:
            objs = self.deleted_acts.pop()
            if len(self.deleted_acts) == 0:
                self.undo_action.setDisabled(True)
            deserialize(orb, objs)
            self.scene = self.set_new_scene()
            self.update_view()
            dispatcher.send("new activity", parent_act=self.subject_activity,
                            position=self.position)
        except:
            pass
    def plot(self):
        act_durations= []
        start_times = []
        power = []
        d_r = []
        for acu in self.subject_activity.components:
            act=acu.component
            oid = getattr(act, "oid", None)
            act_durations.append(get_pval(orb, oid, 'duration'))
            start_times.append(get_pval(orb, oid, 't_start'))
            power.append(get_pval(orb, oid, 'P'))
            d_r.append(get_pval(orb, oid, 'R_D'))
        win = pg.GraphicsWindow()
        win.resize(800,350)
        win.setWindowTitle(' ')
        self.plot_win = win
        plt1 = win.addPlot(title="Power")
        duration = sum(act_durations)
        s_time = min(start_times)
        generated_x = []
        generated_power = []
        for count, d in enumerate(act_durations):
            start = start_times[count]
            end = start_times[count] + d
            generated_x.append(start)
            generated_x.append(end)
        for c, y in enumerate(act_durations):
            generated_power.extend([power[c], power[c]])
            #.extend([power[c]]*(int(act_durations[c])+1))
        plt1.plot(generated_x, generated_power, brush=(0,0,255,150))

        plt2 = win.addPlot(title="Data Rate")
        generated_dr = []
        for d_index, d in enumerate(act_durations):
           generated_dr.extend([d_r[d_index], d_r[d_index]])
        plt2.plot(generated_x, generated_dr, brush=(0,0,255,150))

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

    def create_option_list(self):
        lst = [acu.component for acu in self.spacecraft.components]
        # print(lst,"0000000000000000000000000000000000000000000000000000000")
        options = []
        for system in lst:
            try:
                #check if the id is TBD
                system_id = system.id
                if system_id != "TBD":
                    options.append(system_id)
            except:
                pass
        return options

    def make_combo_box(self):
        self.combo_box = QComboBox(self)
        self.options = self.create_option_list()
        # print("self.options =", self.options)
        self.combo_box.addItems(self.options)
        self.toolbar.addWidget(self.combo_box)
        self.combo_box.currentIndexChanged.connect(self.change_subsystem)
        # self.combo_box.setCurrentIndex(0)
        dispatcher.send("make combo box", index=0)

    def update_combo_box(self):
        self.scene = self.set_new_scene()
        self.update_view()

    def change_subsystem(self, index=None):
        # print("change subsystem called~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~)")
        # print("act_of", self.act_of)
        # print("spacecraft:", self.spacecraft)
        # print("---------------------------------")
        if self.act_of != self.spacecraft:
            # system_name = ''
            # if hasattr(self, 'options'):
            # print("self.options:8888888888888888888888888", self.options)
            try:
                system_name = self.options[index]
                if self.subject_activity.activity_type.id == 'cycle':
                    pass
                else:
                    existing_subsystems = [acu.component for acu
                                           in self.spacecraft.components]
                    for subsystem in existing_subsystems:
                        # print("looking for:", system_name)
                        # print(getattr(subsystem, 'id', 'NA'))
                        if getattr(subsystem, 'id', '') == system_name:
                            # print("found subsystem:", system_name)
                            self.act_of = subsystem
                    self.scene = self.set_new_scene()
                    self.update_view()
                dispatcher.send("changed subsystem",
                                parent_act=self.subject_activity,
                                act_of=self.act_of,
                                position=self.position)
            except:
                orb.log.debug("* TLWidget.change_subsystem() failed.")

    def make_new_system(self, system_name):
        """
        (Deprecated) Make a new subsystem if one does not exist.
        """
        pro_type = orb.select("ProductType", id=system_name)
        new_subsystem = clone("HardwareProduct", owner=self.spacecraft.owner,
                              product_type=pro_type, id=pro_type.id,
                              name=pro_type.id, public=True)
        acu = clone("Acu", assembly=self.spacecraft, component=new_subsystem)
        self.act_of = new_subsystem
        orb.save([new_subsystem, acu])
        dispatcher.send("new object", obj=new_subsystem)
        dispatcher.send("new object", obj=acu)

class ConOpsModeler(QMainWindow):
    """
    Tool for modeling a Concept of Operations.

    Attrs:
        model_files (dict):  maps model "types" (for now just "CAD" and
            "Block") to paths of associated files in vault
        idx (QModelIndex):  index in the system tree's proxy model
            corresponding to the object being modeled
        history (list):  list of previous subject Activity instances
    """
    def __init__(self, parent=None):
        """
        Main window for displaying models and their metadata.

        Keyword Args:
            scene (QGraphicsScene):  existing scene to be used (if None, a new
                one will be created)
            preferred_size (tuple of int): preferred size (not currently used)
            logo (str):  relative path to an image file to be used as the
                "placeholder" image when object is not provided
            idx (QModelIndex):  index in the system tree's proxy model
                corresponding to the object being modeled
            preferred_size (tuple):  size to set -- (width, height)
        """
        super(ConOpsModeler, self).__init__(parent=parent)
        orb.log.info('* ConOpsModeler initializing')
        # self.logo = logo
        # self.idx = idx
        # self.preferred_size = preferred_size
        # self.model_files = {}
        project = orb.get(state.get('project'))
        sc_type = orb.select("ProductType", id='spacecraft')
        if project:
            mission = orb.select('Mission', owner=project)

            if not mission:
                mission_id = '_'.join([project.id, 'mission'])
                mission_name = ' '.join([project.name, 'Mission'])
                mission = clone('Mission', owner=project, id=mission_id,
                                name=mission_name)
                orb.save([mission])
                dispatcher.send("new object", obj=mission)
            self.subject_activity = mission
            # self.mission = mission
        else:
            self.subject_activity = clone("Activity", id="temp", name="temp")
            self.mission = self.subject_activity
        self.project = project
        self.spacecraft = None
        psus = orb.search_exact(cname='ProjectSystemUsage', project=project)
        self.sc_lst = []
        if psus:
            for p in psus:
                if p.system.product_type is sc_type:
                    self.sc_lst.append(p.system)
        if self.sc_lst:
            self.spacecraft = self.sc_lst[0]
        else:
            message = "You don't have a spacecraft!"
            popup = QMessageBox(
                        QMessageBox.Warning,
                        "No spacecraft", message,
                        QMessageBox.Ok, self)
            popup.show()

        self.create_library()
        self._init_ui()
        self.init_toolbar()

        self.bottom_dock = QDockWidget()
        self.bottom_dock.setObjectName('BottomDock')
        self.bottom_dock.setFeatures(QDockWidget.DockWidgetFloatable)
        self.bottom_dock.setAllowedAreas(Qt.BottomDockWidgetArea)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.bottom_dock)

        self.set_widgets(current_activity=self.subject_activity, init=True)
        #------------listening for signals------------#
        dispatcher.connect(self.double_clicked_handler, "double clicked")
        dispatcher.connect(self.view_subsystem, "activity focused")

    def set_bottom_table(self):
        self.bottom_dock.setWidget(self.bottom_table)
        self.setCorner(Qt.TopLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.TopRightCorner, Qt.RightDockWidgetArea)

    def create_library(self):
        """
        Create the library of operation/event block types.
        """
        layout = QGridLayout()
        op_button = ToolButton("Operation")
        op_button.setData("Operation")
        ev_button = ToolButton("Event")
        ev_button.setData("Event")
        cyc_button = ToolButton("Cycle")
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
        self.toolbar = self.addToolBar("Actions")
        self.toolbar.setObjectName('ActionsToolBar')
        self.sc_combo_box = QComboBox()
        self.sc_lst_ids = [sc.id for sc in self.sc_lst]
        self.sc_combo_box.addItems(self.sc_lst_ids)
        self.sc_combo_box.currentIndexChanged.connect(self.change_spacecraft)
        self.toolbar.addWidget(self.sc_combo_box)

    def change_spacecraft(self, index):
        self.spacecraft = self.sc_lst[index]
        self.set_widgets(current_activity=self.subject_activity)

    def resizeEvent(self, event):
        state['model_window_size'] = (self.width(), self.height())

    def _init_ui(self):
        orb.log.debug('  - _init_ui() ...')

    def double_clicked_handler(self, act):
        oid = getattr(act, "oid", None)
        try:
            print("%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%")
            print(get_pval(orb, oid, 'duration'))
        except Exception as e:
            print("%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%")
            print(e)
        if act.activity_type.id == 'cycle':
            self.system_widget.widget_drill_down(act)

    def view_subsystem(self, obj=None):
        ### change obj to activity
        if obj.activity_of is self.spacecraft:
            self.sub_widget.subject_activity = obj
            if obj.activity_type.id == 'cycle':
                self.sub_widget.scene = self.sub_widget.show_empty_scene()
                self.sub_widget.update_view()
                self.sub_widget.setEnabled(False)
                dispatcher.send("disable widget")
            else:
                self.sub_widget.setEnabled(True)
                dispatcher.send("enable widget")
                if hasattr(self.sub_widget, 'combo_box'):
                    self.sub_widget.scene = self.sub_widget.set_new_scene()
                    self.sub_widget.update_view()
                else:
                    self.sub_widget.make_combo_box()


    def set_widgets(self, current_activity=None, init=False):
        self.system_widget = TimelineWidget(
                                    self.spacecraft,
                                    subject_activity=self.subject_activity,
                                    act_of=self.spacecraft, position='top')
        self.system_widget.setMinimumSize(900, 300)
        self.sub_widget = TimelineWidget(self.spacecraft, position='middle')
        self.sub_widget.setEnabled(False)
        self.sub_widget.setMinimumSize(900, 300)
        self.outer_layout = QGridLayout()
        system_table = ActivityTable(subject=self.subject_activity,
                                     parent=self, act_of=self.spacecraft,
                                     position='top')
        system_table.setMinimumSize(500, 300)
        system_table.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.outer_layout.addWidget(self.system_widget, 0, 1)
        self.outer_layout.addWidget(system_table, 0, 0)
        subsystem_table = ActivityTable(subject=self.subject_activity,
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
        self.bottom_table = ParameterTable(subject=self.subject_activity,
                                           act_of=self.spacecraft,
                                           parent=self)
        self.set_bottom_table()
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
