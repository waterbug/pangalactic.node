#!/usr/bin/env python
# NOTE: fixed div's so old_div is not needed.
# from past.utils import old_div
import os
from collections import namedtuple
from urllib.parse    import urlparse
from louie import dispatcher

from PyQt5.QtCore import Qt, QRectF, QPointF, QPoint, QMimeData

from PyQt5.QtWidgets import (QAction, QApplication, QComboBox, QHBoxLayout,
                             QMainWindow, QSizePolicy, QWidget, QGraphicsItem,
                             QGraphicsPolygonItem, QGraphicsScene,
                             QGraphicsView, QGridLayout, QMenu, QToolBox,
                             QPushButton, QGraphicsPathItem, QVBoxLayout)
from PyQt5.QtGui import (QIcon, QTransform, QBrush, QDrag, QPainter, QPen,
                         QPixmap, QCursor, QPainterPath, QPolygonF)

# pangalactic
from pangalactic.core             import state
from pangalactic.core.uberorb     import orb
from pangalactic.core.utils.meta  import asciify, get_block_model_file_name
from pangalactic.node.activities  import ActivityTables
from pangalactic.node.diagrams.shapes import BlockLabel
from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.utils       import clone
from pangalactic.node.widgets    import NameLabel

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
    def __init__(self, act_type, activity=None, parent_activity=None, style=None,
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
        self.setBrush(Qt.white)
        self.create_actions()
        path = QPainterPath()
        self.activity = activity
        self.block_label = BlockLabel(getattr(self.activity, 'id', '') or '', self)
        self.act_type = act_type
        #---draw blocks depending on the 'shape' string passed in
        op_type = orb.select("ActivityType", name="Operation")
        ev_type = orb.select("ActivityType", name="Event")
        self.parent_activity = parent_activity
        dispatcher.connect(self.id_changed_handler, "modified activity")

        if self.activity.activity_type is op_type:
            self.myPolygon = QPolygonF([
                    QPointF(-50, 50), QPointF(50, 50),
                    QPointF(50, -50), QPointF(-50, -50)
            ])
        elif self.activity.activity_type is ev_type:
             self.myPolygon = QPolygonF([
                     QPointF(0, 0), QPointF(-50, 80),
                     QPointF(50, 80)
             ])
        else:
            path.addEllipse(-100, 0, 200, 200)
            self.myPolygon = path.toFillPolygon(QTransform())
            self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setPolygon(self.myPolygon)

    def id_changed_handler(self, activity=None):
        if activity is self.activity:
            self.block_label.set_text(self.activity.id)

    def mouseDoubleClickEvent(self, event):
        dispatcher.send("double clicked", obj=self)

    def contextMenuEvent(self, event):
        self.menu = QMenu()
        self.menu.addAction(self.delete_action)
        self.menu.addAction(self.edit_action)
        self.menu.exec(QCursor.pos())

    def create_actions(self):
        self.delete_action = QAction("Delete", self.scene(), statusTip="Delete Item",
                                     triggered=self.delete_item)
        self.edit_action = QAction("Edit", self.scene(), statusTip="Edit activity", triggered=self.edit_activity)

    def edit_activity(self):
        self.scene().edit_parameters(self.activity)

    def delete_item(self):
        acu = self.activity.where_used[0]
        parent_act = acu.assembly
        orb.delete([self.activity])
        self.scene().timeline.remove_item(self)
        self.scene().removeItem(self)
        dispatcher.send("removed activity", parent_act=parent_act)

    def itemChange(self, change, value):
        # super(EventBlock, self).itemChange(change, value)
        # self.update_position()
        #
        # if change ==  QGraphicsItem.ItemSelectedHasChanged:
        #     if value == True:
        #         acu = orb.select("Acu", assembly=self.scene().current_activity, component=self.activity)
        #         ref_des = acu.reference_designator
        #         print("reference designator for this item:", ref_des)
        return value
        # print(change)

    # def dragMoveEvent(self, event):
    #     print("dragMoveEvent")
    #     # if change == QGraphicsItem.ItemPositionHasChanged:
    #     self.setPos(event.pos().x(), 250)
    #     # if self.scene() != None:
    #     self.scene().timeline.reposition()
    #     # if change ==  QGraphicsItem.ItemPositionChange:
    #     #     super(EventBlock, self).itemChange(change, value)
    #     super(EventBlock, self).dragMoveEvent(event)
    #     self.scene().update()

    # def mouseMoveEvent(self, event):
    #     super(EventBlock, self).mouseMoveEvent(event)
    #     print("mousemove")

    def mouseReleaseEvent(self, event):
        super(EventBlock, self).mouseReleaseEvent(event)
        if (event.button() == Qt.LeftButton):
            self.setPos(event.scenePos().x(), 250)
            self.scene().timeline.reposition()

    # def collides_with_timeline(self):
        # self.on_timeline = False

class DiagramView(QGraphicsView):
    def __init__(self, parent=None):
        super(DiagramView, self).__init__(parent)

    def dragEnterEvent(self, event):
        event.accept()

    def dragMoveEvent(self, event):
        event.accept()

    def dragLeaveEvent(self, event):
        event.accept()

class Template(QGraphicsPathItem):
    def __init__(self, parent=None):
        super(Template, self).__init__(parent)
        self.setFlags(QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemIsMovable |
                      QGraphicsItem.ItemIsFocusable)
        self.path = QPainterPath(QPoint(0, -200))
        self.path.arcTo(QRectF(-200,-200,400,400), 90, -360)
        self.setPath(self.path)

class Timeline(QGraphicsPathItem):

    def __init__(self, scene, parent=None):
        super(Timeline, self).__init__(parent)
        self.setFlags(QGraphicsItem.ItemIsSelectable|
                      QGraphicsItem.ItemIsFocusable)
        self.item_list = []
        self.end_location = 1500
        self.make_path()
        self.length = self.path.length()-2*self.circle_length
        self.num_of_item = len(scene.current_activity.components)
        self.make_point_list()
        self.current_positions = []

    def make_path(self):
        self.path =  QPainterPath(QPointF(100,250))
        self.path.arcTo(QRectF(0, 200 ,100,100), 0, 360)
        self.circle_length = self.path.length()
        self.path.arcTo(QRectF(self.end_location, 200, 100,100), 180, 360)
        self.setPath(self.path)

    def remove_item(self, item):
        if item in self.item_list:
            self.item_list.remove(item)
            self.num_of_item = len(self.item_list)
        if len(self.item_list) >= 5 and self.end_location >= 1500:
            self.shorten_timeline()
        self.update_timeline()

    def add_item(self, item):
        self.item_list.append(item)
        self.num_of_item = len(self.item_list)
        if len(self.item_list) > 5 :
            self.extend_timeline()
        self.update_timeline()

    def update_timeline(self):
        self.make_point_list()
        self.reposition()


    def make_point_list(self):
        self.length = self.path.length()-2*self.circle_length
        factor = self.length/(self.num_of_item+1)
        self.list_of_pos = [(n+1)*factor+100 for n in range(0, self.num_of_item)]

    def populate(self, item_list):
        self.item_list = item_list
        self.make_point_list()
        for i,item in enumerate(item_list):
            item.setPos(QPoint(self.list_of_pos[i], 250))


    def reposition(self):
        parent_act = self.scene().current_activity
        item_list_copy = self.item_list[:]
        self.item_list.sort(key=lambda x: x.scenePos().x())
        same = True
        for item in self.item_list:
            if self.item_list.index(item) != item_list_copy.index(item):
                same = False

        for i,item in enumerate(self.item_list):
            item.setPos(QPoint(self.list_of_pos[i], 250))
            acu = orb.select("Acu", assembly=parent_act, component=item.activity)
            acu.reference_designator = "{}{}".format(parent_act.id,str(i))
            orb.save([acu])
        if not same:
            # print("sending signal")
            dispatcher.send("order changed", parent_act=self.scene().current_activity)
        self.update()
    def extend_timeline(self):
        self.end_location = self.end_location+self.length/(len(self.item_list)+1)
        self.make_path()
        self.update()
        self.scene().update()

    def shorten_timeline(self):
        self.end_location = self.end_location-self.length/(len(self.item_list))
        self.make_path()
        self.update()
        self.scene().update()

class DiagramScene(QGraphicsScene):
    def __init__(self, parent, current_activity=None):
        super(DiagramScene, self).__init__(parent)
        self.current_activity = current_activity
        self.timeline = Timeline(self)
        self.addItem(self.timeline)

    def mousePressEvent(self, mouseEvent):
        super(DiagramScene, self).mousePressEvent(mouseEvent)

    def dropEvent(self, event):
        if event.mimeData().text() == "Cycle":
            activity_type = orb.select("ActivityType", name="Cycle")

        elif event.mimeData().text() == "Operation":
            activity_type = orb.select("ActivityType", name="Operation")
        else:
            activity_type = orb.select("ActivityType", name="Event")
        project = orb.get(state.get("project"))
        activity = clone("Activity", activity_type = activity_type, owner=project)
        # self.edit_parameters(activity)
        acu = clone("Acu", assembly=self.current_activity, component=activity)
        orb.save([acu])
        item = EventBlock(activity.activity_type, activity=activity, parent_activity=self.current_activity)
        item.setPos(event.scenePos())
        self.addItem(item)
        self.timeline.add_item(item)
        dispatcher.send("new activity", parent_act=self.current_activity)
        self.update()

    def edit_parameters(self, activity):
        view = ['id', 'name', 'description']
        panels = ['main']
        pxo = PgxnObject(activity, edit_mode=True, view=view,
                         panels=panels, modal_mode=True, parent=self.parent())
        pxo.show()

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
    def __init__(self, scene=None, preferred_size=None, logo=None, idx=None,
                 external=False, parent=None):
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
            external (bool):  initialize as an external window
            preferred_size (tuple):  size to set -- (width, height)
        """
        super(ConOpsModeler, self).__init__(parent=parent)
        orb.log.info('* ConOpsModeler initializing')
        self.logo = logo
        self.external = external
        self.idx = idx
        self.preferred_size = preferred_size
        self.model_files = {}
        project = orb.get(state.get('project'))
        if project:
            mission = orb.select('Mission', owner=project)

            if not mission:
                mission_id = '_'.join([project.id, 'mission'])
                mission_name = ' '.join([project.name, 'Mission'])
                mission = clone('Mission', owner=project, id=mission_id,
                                name=mission_name)
                # psu_id = '_'.join([mission.id, '_of_', project.id])
                # psu_name = '_'.join([mission.name, ' of ', project.id,
                #                      ' Project'])
                # project_mission = clone('ProjectSystemUsage', id=psu_id,
                #                         name=psu_name, project=project,
                #                         system=mission, system_role='Mission')
                orb.save([mission])
            self.subject_activity = mission
        else:
            self.subject_activity = clone("Activity", id="temp", name="temp")
        self.project = project

        #-----------------------------------------------------------#
        self.createLibrary()
        self.scene = DiagramScene(self, self.subject_activity)
        self.history = []
        self._init_ui()
        self.set_new_view(self.scene, current_activity=self.subject_activity)
        #------------listening for signals------------#
        dispatcher.connect(self.double_clicked_handler, "double clicked")
        # display activity tables
        act = ActivityTables(subject=self.subject_activity, parent=self)
        act.show()

    def createLibrary(self):
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

    def resizeEvent(self, event):
        state['model_window_size'] = (self.width(), self.height())

    def _init_ui(self):
        orb.log.debug('  - _init_ui() ...')
        # set a placeholder for the central widget
        #self.set_placeholder()
        self.init_toolbar()
        self.setCorner(Qt.TopLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.TopRightCorner, Qt.RightDockWidgetArea)

        # Initialize a statusbar for the window
        self.statusbar = self.statusBar()
        # self.statusbar.showMessage("Models, woo!")

    def sceneScaleChanged(self, percentscale):
        newscale = float(percentscale[:-1]) / 100.0
        self.view.setTransform(QTransform().scale(newscale, newscale))

    def init_toolbar(self):
        self.toolbar = self.addToolBar("Actions")
        self.toolbar.setObjectName('ActionsToolBar')
        self.back_action = self.create_action(
                                    "Go Back",
                                    slot=self.go_back,
                                    icon="left_arrow",
                                    tip="Back to Previous Page")
        self.toolbar.addAction(self.back_action)
        self.clear_activities_action = self.create_action(
                                    "clear activities",
                                    slot=self.clear_activities,
                                    icon="left_arrow",
                                    tip="delete activities on this page")
        self.toolbar.addAction(self.clear_activities_action)
        # self.start_over_action = self.create_action(
        #                             "start over",
        #                             slot=self.start_over,
        #                             icon="left_arrow",
        #                             tip="Clear All Activities in This Project")
        # self.toolbar.addAction(self.start_over)



        # self.external_window_action = self.create_action(
        #                             "Display external diagram window ...",
        #                             slot=self.display_external_window,
        #                             icon="system",
        #                             tip="Display External Diagram Window")
        # if not self.external:
        #     self.toolbar.addAction(self.external_window_action)

        #create and add scene scale menu
        self.scene_scale_select = QComboBox()
        self.scene_scale_select.addItems(["25%", "30%", "40%", "50%", "75%",
                                          "100%"])
        self.scene_scale_select.setCurrentIndex(3)
        self.scene_scale_select.currentIndexChanged[str].connect(
                                                    self.sceneScaleChanged)
        self.toolbar.addWidget(self.scene_scale_select)

    def clear_activities(self):
        print("clear")
        children = [acu.component for acu in self.subject_activity.components]
        orb.delete(children)
        new_scene = DiagramScene(self, current_activity=self.subject_activity)
        self.set_new_view(new_scene, current_activity=self.subject_activity)
        dispatcher.send("removed activity", parent_act=self.subject_activity)

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
            # action.setStatusTip(tip)
        if slot is not None:
            action.triggered.connect(slot)
        if checkable:
            action.setCheckable(True)
        return action

    def display_external_window(self):
        orb.log.info('* ConOpsModeler.display_external_window() ...')
        mw = ConOpsModeler(scene=self.scene,
                           logo=self.logo, external=True,
                           preferred_size=(2000, 1000), parent=self.parent())
        mw.show()

    def double_clicked_handler(self, obj):
        """
        Handle a double-click event on an eventblock, creating and
        displaying a new view.

        Args:
            obj (EventBlock):  the block that received the double-click
        """
        dispatcher.send("drill down", obj=obj.activity)
        new_scene = DiagramScene(self, current_activity=obj.activity)
        self.set_new_view(new_scene, current_activity=obj.activity)
        self.subject_activity = obj.activity
        previous = obj.scene().current_activity
        self.history.append(previous)
        self.show_history()

    def set_new_view(self, scene=None, current_activity=None):
        """
        Set a new view and create or recreate a scene.  Used in __init__(),
        double_clicked_handler() (expanding an activity, aka "drilling down"),
        and go_back() (navigating back thru history).
        """
        self.show_history()
        self.subject_activity = current_activity
        self.scene = scene
        self.view = DiagramView(self.scene)
        self.setMinimumSize(1000,500)
        self.view.setSizePolicy(QSizePolicy.MinimumExpanding,
                                QSizePolicy.MinimumExpanding)
        self.view.setScene(self.scene)
        outer_layout = QVBoxLayout()
        layout = QHBoxLayout()
        self.title = NameLabel(getattr(self.subject_activity, 'id', 'NA'))
        self.title.setStyleSheet(
                            'font-weight: bold; font-size: 18px; color: purple')
        outer_layout.addWidget(self.title)

        layout.addWidget(self.view)
        layout.addWidget(self.library)
        outer_layout.addLayout(layout)

        widget = QWidget()
        widget.setLayout(outer_layout)
        self.setCentralWidget(widget)
        self.sceneScaleChanged("50%")

        if current_activity != None and len(current_activity.components) > 0:
            all_acus = [(acu.reference_designator, acu) for acu in current_activity.components]
            try:
                all_acus.sort()
            except:
                pass
            item_list=[]
            for acu_tuple in all_acus:
                acu = acu_tuple[1]
                activity = acu.component
                item = EventBlock("Box", activity=activity, parent_activity=current_activity)
                item_list.append(item)
                self.scene.addItem(item)
                self.scene.update()
            self.scene.timeline.populate(item_list)
        self.view.show()

    def show_history(self):
        history_string = ""
        for activity in self.history:
            id = activity.id or "NA"
            history_string += id + " >"
        history_string += self.subject_activity.id or "NA"
        history_string+= " >"
        self.statusbar.showMessage(history_string)

    def go_back(self):
        try:
            previous_activity = self.history.pop()
            new_scene = DiagramScene(self, previous_activity)
            self.set_new_view(new_scene, current_activity=previous_activity)
            self.show_history()
            dispatcher.send("go back", obj=previous_activity)
        except:
            pass

    def set_subject(self, activity=None):
        """
        Set an object for the current modeler context.  If the object does not
        have a Block model one is created from its components (or an empty
        Block Model if there are no components).

        Keyword Args:
            obj (Activity): if no model is provided, find models of obj
        """
        pass
        # orb.log.info('* ConOpsModeler.set_subject()')
        # orb.log.info('  obj "{}"'.format(getattr(obj, 'oid', 'None')))
        # # reset model_files
        # self.model_files = {}
        # if hasattr(self, 'view_cad_action'):
            # try:
                # self.view_cad_action.setVisible(False)
            # except:
                # # oops, C++ object got deleted
                # pass
        # self.obj = obj
        # if self.obj:
            # if isinstance(self.obj, orb.classes['Modelable']):
                # orb.log.info('* ConOpsModeler: checking for models ...')
                # # model_types = set()
                # if self.obj.has_models:
                    # for m in self.obj.has_models:
                        # fpath = get_model_path(m)
                        # if fpath:
                            # # fpath only needed for CAD models, since block
                            # # models have a canonical path
                            # self.model_files[m.oid] = fpath
                        # # model_types.add(m.type_of_model.oid)
                # self.display_block_diagram()
            # else:
                # orb.log.info('* ConOpsModeler: obj is not Modelable, ignoring')
                # self.obj = None
                # orb.log.info('  ... setting placeholder widget.')
                # self.set_placeholder()
        # else:
            # self.obj = None
            # orb.log.info('  no object; setting placeholder widget.')
            # self.set_placeholder()
        # # TODO:  enable multiple CAD models (e.g. "detailed" / "simplified")
        # if self.model_files:
            # self.models_by_label = {}
            # for oid, fpath in self.model_files.items():
                # model = orb.get(oid)
                # if getattr(model.type_of_model, 'oid', None) in ['step:203',
                                                                 # 'step:214']:
                    # self.models_by_label['CAD'] = (model, fpath)
                    # if hasattr(self, 'view_cad_action'):
                        # self.view_cad_action.setVisible(True)
        # if self.history:
            # if hasattr(self, 'back_action'):
                # self.back_action.setEnabled(True)
        # else:
            # if hasattr(self, 'back_action'):
                # self.back_action.setEnabled(False)
        # self.cache_block_model()
        # self.view.verticalScrollBar().setValue(0)
        # self.view.horizontalScrollBar().setValue(0)


if __name__ == '__main__':
    import sys
    orb.start(home='junk_home', debug=True)
    app = QApplication(sys.argv)
    mw = ConOpsModeler(external=True)
    mw.show()
    sys.exit(app.exec_())
