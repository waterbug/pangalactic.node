#!/usr/bin/env python
# NOTE: fixed div's so old_div is not needed.
# from past.utils import old_div
import os
from collections import namedtuple
from urllib.parse    import urlparse
from louie import dispatcher

from PyQt5.QtCore import Qt, QRectF, QPointF, QPoint, QMimeData

from PyQt5.QtWidgets import (QAction, QApplication, QComboBox, QDockWidget,
                             QHBoxLayout, QMainWindow, QSizePolicy, QWidget,
                             QGraphicsItem, QGraphicsPolygonItem,
                             QGraphicsScene, QGraphicsView, QGridLayout, QMenu,
                             QToolBox, QPushButton, QGraphicsPathItem,
                             QVBoxLayout, QToolBar, QWidgetAction, QStatusBar)
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
from pangalactic.core.serializers      import serialize, deserialize
from pangalactic.core               import config
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
        self.block_label = BlockLabel(getattr(self.activity, 'id', '') or '', self)
        #---draw blocks depending on the 'shape' string passed in
        self.parent_activity = parent_activity or self.activity.where_used[0].assembly
        dispatcher.connect(self.id_changed_handler, "modified activity")
        self.create_actions()
        self.setAcceptHoverEvents(True)
        self.subsystem = False

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

    def id_changed_handler(self, activity=None):
        if activity is self.activity:
            self.block_label.set_text(self.activity.id)

    def hoverEnterEvent(self, event):
        if self.activity.activity_type.name == "Cycle":
            pass
    def mouseDoubleClickEvent(self, event):
        # print("irhfp9w8ehrg888888888888888888888888888888888888888888888888888888888888888")
        dispatcher.send("double clicked", act=self.activity)

    def contextMenuEvent(self, event):


        self.menu = QMenu()
        self.menu.addAction(self.delete_action)
        self.menu.addAction(self.edit_action)
        self.menu.addAction(self.divide_to_subsystems_action)
        self.menu.exec(QCursor.pos())

    def create_actions(self):
        self.delete_action = QAction("Delete", self.scene(), statusTip="Delete Item",
                                     triggered=self.delete_item)
        self.edit_action = QAction("Edit", self.scene(), statusTip="Edit activity", triggered=self.edit_activity)
        self.divide_to_subsystems_action = QAction("View subsystems", self.scene(), statusTip="Divide into subsystems", triggered=self.subsystems)
        # self.view_subsystem_action = QAction("Edit", self.scene(), statusTip="Edit activity", triggered=self.edit_activity)

    def subsystem_selected(self):
        pass
        # dispatcher.send("subsystem selected", system=system)

    def subsystems(self):
        dispatcher.send("view subsystem", obj=self.activity)

    def edit_activity(self):
        self.scene().edit_parameters(self.activity)

    def delete_item(self):
        self.scene().timeline.remove_item(self)
        self.scene().removeItem(self)
        dispatcher.send("remove activity", parent_act=self.parent_activity, act=self.activity )

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

    def mouseReleaseEvent(self, event):
        super(EventBlock, self).mouseReleaseEvent(event)
        if (event.button() == Qt.LeftButton):
            self.setPos(event.scenePos().x(), 250)
            self.scene().timeline.reposition()

class DiagramView(QGraphicsView):
    def __init__(self, parent=None):
        super(DiagramView, self).__init__(parent)

    def dragEnterEvent(self, event):
        try:
            has_act_of = self.scene().act_of
            event.accept()
        except:
            pass

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
        self.update_timeline(initial=True)

    def update_timeline(self, initial=False):
        self.make_point_list()
        self.reposition(initial=initial)


    def make_point_list(self):
        self.length = self.path.length()-2*self.circle_length
        factor = self.length/(len(self.item_list)+1)
        self.list_of_pos = [(n+1)*factor+100 for n in range(0, len(self.item_list))]

    def populate(self, item_list):
        self.item_list = item_list
        self.make_point_list()
        for i,item in enumerate(item_list):
            item.setPos(QPoint(self.list_of_pos[i], 250))


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
            acu = orb.select("Acu", assembly=parent_act, component=item.activity)
            acu.reference_designator = "{}{}".format(parent_act.id,str(i))
            orb.save([acu])
            if initial:
                acu.component.id = acu.reference_designator# for testing purposes
                orb.save([acu.component])
                dispatcher.send("modified activity", activity=acu.component)
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
    def __init__(self, parent, current_activity=None, act_of=None):
        super(DiagramScene, self).__init__(parent)
        self.current_activity = current_activity
        self.timeline = Timeline(self)
        self.addItem(self.timeline)
        self.focusItemChanged.connect(self.focus_changed_handler)
        self.current_focus = None
        self.act_of = act_of

    def focus_changed_handler(self, new_item, old_item):
        if new_item is not None:

            if new_item != self.current_focus:
                self.current_focus = new_item
                # print("true^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^0^^^^^6")
                dispatcher.send("activity focused", obj=self.focusItem().activity)
                # print("signal sent, new act:", new_item.activity.id)


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
        # print(self.act_of.product_type.id, "#################################################")
        activity = clone("Activity", activity_type = activity_type, owner=project, activity_of=self.act_of)
        # print(activity.activity_of.product_type.id, "after#################################################")
        # self.edit_parameters(activity)
        acu = clone("Acu", assembly=self.current_activity, component=activity)
        orb.save([acu, activity])
        item = EventBlock(activity=activity, parent_activity=self.current_activity)
        item.setPos(event.scenePos())
        self.addItem(item)
        self.timeline.add_item(item)
        dispatcher.send("new activity", parent_act=self.current_activity)
        self.update()

    def edit_parameters(self, activity):
        view = ['id', 'name', 'description']
        panels = ['main', 'parameters']
        pxo = PgxnObject(activity, edit_mode=True, view=view,
                         panels=panels, modal_mode=True, parent=self.parent())
        pxo.show()
    def mouseDoubleClickEvent(self, event):
        super(DiagramScene, self).mouseDoubleClickEvent(event)

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
    def __init__(self,spacecraft, subject_activity=None, act_of=None,parent=None):
        super(TimelineWidget, self).__init__(parent=parent)
        self.possible_systems = []
        ds = config.get('discipline_subsystems')
        if ds:
            self.possible_systems = list(config.get(
                                         'discipline_subsystems').values())
        self.spacecraft = spacecraft
        self.init_toolbar()
        self.subject_activity = subject_activity
        self.act_of = act_of
        #### To do : make different title for subsystem timeline###############
        self.title = NameLabel(getattr(self.subject_activity, 'id', ' '))
        self.title.setStyleSheet(
                        'font-weight: bold; font-size: 18px; color: purple')

        # self.setVisible(visible)
        # self.set_title()
        self.scene = self.set_new_scene()
        self.view = DiagramView(self)
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
        # dispatcher.connect(self.double_clicked_handler, "double clicked")

    def set_title(self):
        try:
            title = self.subject_activity.id + ": " + self.act_of.id
            self.title.setText(title)
            self.update()
        except:
            pass

    def widget_drill_down(self, obj):
        """
        Handle a double-click event on an eventblock, creating and
        displaying a new view.

        Args:
            obj (EventBlock):  the block that received the double-click
        """
        if obj.subsystem == False:
            dispatcher.send("drill down", obj=obj.activity)
            self.set_new_scene(current_activity=obj.activity)
            self.subject_activity = obj.activity

            previous = obj.scene().current_activity
            self.history.append(previous)
            # self.show_history()

    def set_new_scene(self):
        if self.act_of is not None:
            # print('---------------------------------------------',self.subject_activity.id)
            # print("set new scene act of", self.act_of.id)
            scene = DiagramScene(self, self.subject_activity, act_of=self.act_of)
            if self.subject_activity != None and len(self.subject_activity.components) > 0:
                # subsystem_comps = [acu for acu in current_activity.components if acu.component.activity_of is self.act_of]
                all_acus = [(acu.reference_designator, acu) for acu in self.subject_activity.components]
                try:
                    all_acus.sort()
                except:
                    pass
                item_list=[]
                for acu_tuple in all_acus:
                    acu = acu_tuple[1]
                    activity = acu.component
                    # print(" activities", activity)
                    if activity.activity_of == self.act_of:
                        item = EventBlock(activity=activity, parent_activity=self.subject_activity)
                        item_list.append(item)
                        scene.addItem(item)
                    scene.update()
                scene.timeline.populate(item_list)
            # self.view.show()
            # self.show_history()
            self.set_title()
            return scene
        else:
            self.show_empty_scene()

    def show_empty_scene(self):
        self.set_title()
        scene = QGraphicsScene()
        return scene

    def update_view(self):
        self.view.setScene(self.scene)
        self.view.show()

    def init_toolbar(self):
        self.toolbar = QToolBar(parent=self)
        try:
            self.toolbar.setObjectName('ActionsToolBar')
            self.back_action = self.create_action(
                                        "Go Back",
                                        slot=self.go_back,
                                        icon="left_arrow",
                                        tip="Back to Previous Page")
            self.toolbar.addAction(self.back_action)
            # print("created")
        except:
            # print("excespt")
            pass
        # self.clear_activities_action = self.create_action(
        #                             "clear activities",
        #                             slot=self.clear_activities,
        #                             icon="left_arrow",
        #                             tip="delete activities on this page")
        # self.toolbar.addAction(self.clear_activities_action)
        # self.back_to_mission_action = self.create_action(
        #                             "back to mission",
        #                             slot=self.view_mission,
        #                             icon="system",
        #                             tip="go back to mission")
        # self.toolbar.addAction(self.back_to_mission_action)
        # self.undo_action = self.create_action(
        #                             "undo",
        #                             slot=self.undo,
        #                             icon="left_arrow",
        #                             tip="undo")
        # self.toolbar.addAction(self.undo_action)
        #create and add scene scale menu
        self.scene_scale_select = QComboBox()
        self.scene_scale_select.addItems(["25%", "30%", "40%", "50%", "75%",
                                          "100%"])
        self.scene_scale_select.setCurrentIndex(3)
        self.scene_scale_select.currentIndexChanged[str].connect(
                                                    self.sceneScaleChanged)
        self.toolbar.addWidget(self.scene_scale_select)

    def sceneScaleChanged(self, percentscale):
        newscale = float(percentscale[:-1]) / 100.0
        self.view.setTransform(QTransform().scale(newscale, newscale))

    def go_back(self):
        try:
            previous_activity = self.history.pop()
            self.set_new_scene(current_activity=previous_activity)
            # self.show_history()
            # dispatcher.send("go back", obj=previous_activity)
        except:
            pass
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
    def return_scene(self):
        return self.scene
    def return_view(self):
        return self.view
    # def toolbar(self):
    #     return self.toolbar
    # def show_history(self):
    #     try:
    #         history_string = ""
    #         for activity in self.history:
    #             id = activity.id or "NA"
    #             history_string += id + " >"
    #         history_string += self.subject_activity.id or "NA"
    #         history_string+= " >"
    #         self.statusbar.showMessage(history_string)
    #     except:
    #         pass


    def make_combo_box(self, activity):
        self.subject_activity = activity
        box = QComboBox(self)
        box.addItems(self.possible_systems)
        self.combo_box = box
        self.combo_box.currentIndexChanged[str].connect(self.change_subsystem)
        self.toolbar.addWidget(self.combo_box)



    def update_combo_box(self):
        self.scene = self.set_new_scene()
        self.update_view()

    def change_subsystem(self, system_name=None):
        #target_system: string
        if self.subject_activity.activity_type.id == 'cycle':
            pass
        else:
            existing_subsystems = [acu.component for acu in self.spacecraft.components] #list of objects
            system_exists = False
            # print("looking for", system_name)
            # for sys in existing_subsystems:
            #     print(sys.product_type.id)
            for subsystem in existing_subsystems:
                if subsystem.product_type.id == system_name:
                    system_exists = True
                    self.act_of = subsystem
                else:
                    # print('"{}" not the same as "{}"'.format(subsystem.product_type.id, system_name))
                    pass
            if not system_exists:
                self.make_new_system(system_name)

            self.scene = self.set_new_scene()
            self.update_view()
            # except Exception as e:
            #     print(e)
            #     print('============================================')
    def make_new_system(self, system_name):
        pro_type = orb.select("ProductType", id=system_name)
        new_subsystem = clone("HardwareProduct", owner=self.spacecraft.owner, product_type=pro_type, id=pro_type.id, name=pro_type.id)
        acu = clone("Acu", assembly=self.spacecraft, component=new_subsystem)
        self.act_of = new_subsystem
        orb.save([new_subsystem, acu])
            # orb.select("HardwareProduct", product_type)
        #
        # target_system = target_system or self.possible_systems[self.combo_box.currentIndex()]
        # self.current_subsystem_index = target_system
        # ex_subsys_names = [sys.product_type for sys in existing_subsystems]
        # if target_system in ex_subsys_names:
        #     print("dne--------------------------------------------------")
        # sys_exist = False
        # for system in existing_subsystems:
        #     if system.product_type.id == target_system:
        #         sys_exist = True
        #         self.current_subsystem_index = existing_subsystems.index(system)
        #         self.act_of = system
        #         self.scene = self.set_new_scene()
        #         self.update_view()
        # if sys_exist == False:
        #     pro_type = orb.select("ProductType", id=target_system)
        #     new_subsystem = clone("HardwareProduct", owner=self.spacecraft.owner,product_type=pro_type)
        #     acu = clone("Acu", assembly=self.spacecraft, component=new_subsystem)
        #     self.current_subsystem_index = self.possible_systems.index(pro_type.id)
        #     self.act_of = pro_type
        #     self.scene = self.set_new_scene()
        #     self.update_view()
        #
        # self.update()

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
        sc_type = orb.select("ProductType", id='spacecraft')
        if project:
            mission = orb.select('Mission', owner=project)

            if not mission:
                mission_id = '_'.join([project.id, 'mission'])
                mission_name = ' '.join([project.name, 'Mission'])
                mission = clone('Mission', owner=project, id=mission_id,
                                name=mission_name)
                orb.save([mission])
            self.subject_activity = mission
            self.mission = mission

        else:
            self.subject_activity = clone("Activity", id="temp", name="temp")
            self.mission = self.subject_activity

        self.project = project

        spacecraft = orb.select('HardwareProduct', owner=project, product_type=sc_type)
        # print("already have sc", spacecraft.name)
        if not spacecraft:
            spacecraft = clone("HardwareProduct", owner=project, product_type=sc_type)
            psu = clone("ProjectSystemUsage", project=project, system=spacecraft)
            orb.save([psu, spacecraft])


        self.spacecraft = spacecraft
        # print("my sc name ------------------", self.spacecraft.name)
        #-----------------------------------------------------------#
        self.create_library()
        # self.scene = DiagramScene(self, self.subject_activity)
        self.subsys_act = None
        self.history = []
        self._init_ui()
        # self.set_new_view(self.scene, current_activity=self.subject_activity, init=True)
        self.set_widgets(current_activity=self.subject_activity, init=True)
        #------------listening for signals------------#
        dispatcher.connect(self.double_clicked_handler, "double clicked")
        dispatcher.connect(self.delete_activity, "remove activity")
        dispatcher.connect(self.view_subsystem, "activity focused")
        dispatcher.connect(self.view_subsystem, "view subsystem")
        # add left dock
        self.left_dock = QDockWidget()
        self.left_dock.setObjectName('LeftDock')
        self.left_dock.setFeatures(QDockWidget.DockWidgetFloatable)
        self.left_dock.setAllowedAreas(Qt.LeftDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.left_dock)
        # display activity tables
        left_table = ActivityTables(subject=self.subject_activity, parent=self, location='left')
        # act.show()
        self.left_dock.setWidget(left_table)

        # add bottom dock
        self.bottom_dock = QDockWidget()
        self.bottom_dock.setObjectName('BottomDock')
        self.bottom_dock.setFeatures(QDockWidget.DockWidgetFloatable)
        self.bottom_dock.setAllowedAreas(Qt.BottomDockWidgetArea)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.bottom_dock)
        # display activity tables
        bottom_table = ActivityTables(subject=self.subject_activity, parent=self, location='bottom')
        # act.show()
        self.bottom_dock.setWidget(bottom_table)

        self.setCorner(Qt.TopLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.TopRightCorner, Qt.RightDockWidgetArea)
        self.deleted_acts = []
        self.temp_serialized = []
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

    def resizeEvent(self, event):
        state['model_window_size'] = (self.width(), self.height())

    def _init_ui(self):
        orb.log.debug('  - _init_ui() ...')
        # set a placeholder for the central widget
        #self.set_placeholder()
        # self.init_toolbar()
        # Initialize a statusbar for the window
        self.statusbar = self.statusBar()
        # self.statusbar.showMessage("Models, woo!")

    def sceneScaleChanged(self, percentscale):
        newscale = float(percentscale[:-1]) / 100.0
        # self.view.setTransform(QTransform().scale(newscale, newscale))
        # self.sub_view.setTransform(QTransform().scale(newscale, newscale))

    # def init_toolbar(self):
    #     self.toolbar = self.addToolBar("Actions")
    #     self.toolbar.setObjectName('ActionsToolBar')
    #     self.back_action = self.create_action(
    #                                 "Go Back",
    #                                 slot=self.go_back,
    #                                 icon="left_arrow",
    #                                 tip="Back to Previous Page")
    #     self.toolbar.addAction(self.back_action)
    #     self.clear_activities_action = self.create_action(
    #                                 "clear activities",
    #                                 slot=self.clear_activities,
    #                                 icon="left_arrow",
    #                                 tip="delete activities on this page")
    #     self.toolbar.addAction(self.clear_activities_action)
    #     self.back_to_mission_action = self.create_action(
    #                                 "back to mission",
    #                                 slot=self.view_mission,
    #                                 icon="system",
    #                                 tip="go back to mission")
    #     self.toolbar.addAction(self.back_to_mission_action)
    #     self.undo_action = self.create_action(
    #                                 "undo",
    #                                 slot=self.undo,
    #                                 icon="left_arrow",
    #                                 tip="undo")
    #     self.toolbar.addAction(self.undo_action)
    #     #create and add scene scale menu
    #     self.scene_scale_select = QComboBox()
    #     self.scene_scale_select.addItems(["25%", "30%", "40%", "50%", "75%",
    #                                       "100%"])
    #     self.scene_scale_select.setCurrentIndex(3)
    #     self.scene_scale_select.currentIndexChanged[str].connect(
    #                                                 self.sceneScaleChanged)
    #     self.toolbar.addWidget(self.scene_scale_select)

    # def view_mission(self):
    #     new_scene = DiagramScene(self, current_activity=self.mission)
    #     self.set_new_view(new_scene, current_activity=self.mission)
    #     self.subject_activity = self.mission
    #     self.history.clear()
    #     self.show_history()
    #
    # def clear_activities(self):
    #     children = [acu.component for acu in self.subject_activity.components]
    #     orb.delete(children)
    #     new_scene = DiagramScene(self, current_activity=self.subject_activity)
    #     self.set_new_view(new_scene, current_activity=self.subject_activity)
    #     dispatcher.send("removed activity", parent_act=self.subject_activity)

    def delete_activity(self, act=None):
        self.serialized_deleted(act=act)
        self.delete_children(act=act)
        self.deleted_acts.append(self.temp_serialized)
        self.temp_serialized = []
        dispatcher.send("removed activity", parent_act=self.subject_activity)

    def serialized_deleted(self, act=None):
        if len(act.components) <= 0:
            serialized_act = serialize(orb, [act, act.where_used[0]], include_components=True)
            self.temp_serialized.extend(serialized_act)
        elif len(act.components) > 0:
            for acu in act.components:
                self.serialized_deleted(act=acu.component)
            serialized_act = serialize(orb, [act, act.where_used[0]], include_components=True)
            self.temp_serialized.extend(serialized_act)

    def delete_children(self, act=None):
        if len(act.components) <= 0:
            orb.delete([act])
        elif len(act.components) > 0:
            for acu in act.components:
                self.delete_children(act=acu.component)
            orb.delete([act])
    #
    # def undo(self):
    #     try:
    #         objs = self.deleted_acts.pop()
    #         ds = deserialize(orb, objs)
    #         new_scene = DiagramScene(self, current_activity=self.subject_activity)
    #         self.set_new_view(new_scene, current_activity=self.subject_activity)
    #         dispatcher.send("new activity", parent_act=self.subject_activity)
    #     except:
    #         pass
    # def create_action(self, text, slot=None, icon=None, tip=None,
    #                   checkable=False):
    #     action = QAction(text, self)
    #     if icon is not None:
    #         icon_file = icon + state.get('icon_type', '.png')
    #         icon_dir = state.get('icon_dir', os.path.join(orb.home, 'icons'))
    #         icon_path = os.path.join(icon_dir, icon_file)
    #         action.setIcon(QIcon(icon_path))
    #     if tip is not None:
    #         action.setToolTip(tip)
    #         # action.setStatusTip(tip)
    #     if slot is not None:
    #         action.triggered.connect(slot)
    #     if checkable:
    #         action.setCheckable(True)
    #     return action
    #
    # def display_external_window(self):
    #     orb.log.info('* ConOpsModeler.display_external_window() ...')
    #     mw = ConOpsModeler(scene=self.scene,
    #                        logo=self.logo, external=True,
    #                        preferred_size=(2000, 1000), parent=self.parent())
    #     mw.show()

    def double_clicked_handler(self, act):

        # print("=============================kdnfianeignojsepojfpfjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjj")
        if act.activity_type.id == 'cycle':
            pass



        # to do:
        # 1. find the activity_of of the activity:
        #   I. if belongs to spacecraft:
        #       a. send obj to subsystem timeline
        #   II. if belongs to subsystem:
        #       a. pass




    # def update_widgets(self, obj):
    #     self.sub_widget.set_new_scene(obj.activity)


    # def display_subsystem(self, act):
    #     # self.subsys_act = act
    #     # self.set_new_view(self.scene, current_activity=self.subject_activity)
    #     # pass
    def view_subsystem(self, obj=None):
        ### change obj to activity
        if obj.activity_of is self.spacecraft:
            self.sub_widget.subject_activity = obj
            if obj.activity_type.id == 'cycle':
                self.sub_widget.scene = self.sub_widget.show_empty_scene()
                self.sub_widget.update_view()
                try:
                    # self.sub_widget.combo_box.hide()
                    self.sub_widget.init_toolbar()
                    self.sub_widget.update()
                except Exception as e:
                    # print("Exception raised in view_subsystem", e)
                    pass
            else:
                if hasattr(self.sub_widget, 'combo_box'):
                    self.sub_widget.update_combo_box()
                else:
                    self.sub_widget.make_combo_box(obj)


    def set_widgets(self, scene=None, current_activity=None, init=False):
        self.subject_activity = current_activity
        self.system_widget = TimelineWidget( self.spacecraft, subject_activity = self.subject_activity, act_of=self.spacecraft)

        self.sub_widget = TimelineWidget(self.spacecraft)
        self.outer_layout = QVBoxLayout()
        self.outer_layout.addWidget(self.system_widget)
        try:
            self.outer_layout.addWidget(self.sub_widget)
        except:
            pass
        self.widget = QWidget()
        self.widget.setMinimumSize(900, 600)
        self.widget.setLayout(self.outer_layout)
        # widget.setLayout(sub_layout)
        self.setCentralWidget(self.widget)
        self.sceneScaleChanged("50%")
        if init:
            # add right dock
            self.right_dock = QDockWidget()
            self.right_dock.setObjectName('RightDock')
            self.right_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
            self.right_dock.setAllowedAreas(Qt.RightDockWidgetArea)
            self.addDockWidget(Qt.RightDockWidgetArea, self.right_dock)
            self.right_dock.setWidget(self.library)

        # if current_activity != None and len(current_activity.components) > 0:
        #     all_acus = [(acu.reference_designator, acu) for acu in current_activity.components]
        #     try:
        #         all_acus.sort()
        #     except:
        #         pass
        #     item_list=[]
        #     for acu_tuple in all_acus:
        #         acu = acu_tuple[1]
        #         activity = acu.component
        #         item = EventBlock(activity=activity, parent_activity=current_activity)
        #         item_list.append(item)
        #         self.scene.addItem(item)
        #         self.scene.update()
        #     self.scene.timeline.populate(item_list)
        # self.view.show()


    #
    # def set_new_view(self, scene=None, current_activity=None, init=False):
    #     """
    #     Set a new view and create or recreate a scene.  Used in __init__(),
    #     double_clicked_handler() (expanding an activity, aka "drilling down"),
    #     and go_back() (navigating back thru history).
    #     """
    #     self.show_history()
    #     self.subject_activity = current_activity
    #     self.scene = scene
    #     self.view = DiagramView(self.scene)
    #     # self.setMinimumSize(1000, 00)
    #     self.view.setSizePolicy(QSizePolicy.MinimumExpanding,
    #                             QSizePolicy.MinimumExpanding)
    #     self.view.setScene(self.scene)
    #
    #
    #     outer_layout = QVBoxLayout()
    #     layout = QHBoxLayout()
    #     self.title = NameLabel(getattr(self.subject_activity, 'id', 'NA'))
    #     self.title.setStyleSheet(
    #                         'font-weight: bold; font-size: 18px; color: purple')
    #     # view_toolbar = self.make_toolbar("first", parent=system_widget)
    #     # outer_layout.addWidget(view_toolbar)
    #     # outer_layout.addWidget(self.view)
    #     # outer_layout.addWidget(self.view)
    #     # system_widget.setLayout(outer_layout)
    #     # d_view_toolbar = self.make_toolbar("second",parent=self.d_scene)
    #     # outer_layout.addWidget(d_view_toolbar)
    #     # outer_layout.addWidget(self.sub_view)
    #     sys_toolbar = QToolBar()
    #     system_widget = TimelineWidget(self.scene, self.view, sys_toolbar, visible=True)
    #     system_layout = QVBoxLayout()
    #     system_layout.addWidget(sys_toolbar)
    #     system_layout.addWidget(self.view)
    #     system_widget.setLayout(system_layout)
    #
    #     if self.subsys_act == None:
    #         self.sub_scene = QGraphicsScene()
    #     else:
    #         self.sub_scene = self.set_new_scene(current_activity=self.subsys_act)
    #     self.sub_view = DiagramView(self.sub_scene)
    #     self.sub_view.setScene(self.sub_scene)
    #     sub_toolbar = QToolBar()
    #     sub_widget = TimelineWidget(self.sub_scene, self.sub_view, sub_toolbar, visible=False)
    #     # # sub_widget.setVisible(False)
    #     sub_layout = QVBoxLayout()
    #     sub_layout.addWidget(sub_toolbar)
    #     # system_layout.addWidget(sub_toolbar)
    #     sub_layout.addWidget(self.sub_view)
    #     sub_widget.setLayout(sub_layout)
    #         # system_layout.addWidget(self.sub_view)
    #
    #
    #     outer_layout = QVBoxLayout()
    #     outer_layout.addWidget(system_widget)
    #     try:
    #         outer_layout.addWidget(sub_widget)
    #     except:
    #         pass
    #     widget = QWidget()
    #     widget.setMinimumSize(900, 600)
    #     widget.setLayout(outer_layout)
    #     # widget.setLayout(sub_layout)
    #     self.setCentralWidget(widget)
    #     self.sceneScaleChanged("50%")
    #     if init:
    #         # add right dock
    #         self.right_dock = QDockWidget()
    #         self.right_dock.setObjectName('RightDock')
    #         self.right_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
    #         self.right_dock.setAllowedAreas(Qt.RightDockWidgetArea)
    #         self.addDockWidget(Qt.RightDockWidgetArea, self.right_dock)
    #         self.right_dock.setWidget(self.library)
    #
    #     # if current_activity != None and len(current_activity.components) > 0:
    #     #     all_acus = [(acu.reference_designator, acu) for acu in current_activity.components]
    #     #     try:
    #     #         all_acus.sort()
    #     #     except:
    #     #         pass
    #     #     item_list=[]
    #     #     for acu_tuple in all_acus:
    #     #         acu = acu_tuple[1]
    #     #         activity = acu.component
    #     #         item = EventBlock(activity=activity, parent_activity=current_activity)
    #     #         item_list.append(item)
    #     #         self.scene.addItem(item)
    #     #         self.scene.update()
    #     #     self.scene.timeline.populate(item_list)
    #     self.view.show()

    # def set_new_scene(self, current_activity=None):
    #     scene = DiagramScene(self, current_activity)
    #     if current_activity != None and len(current_activity.components) > 0:
    #         if self.combo_box:
    #             current_system = self.possible_systems[self.combo_box.currentIndex()]
    #         all_acus = [(acu.reference_designator, acu) for acu in current_activity.components]
    #         try:
    #             all_acus.sort()
    #         except:
    #             pass
    #         item_list=[]
    #         for acu_tuple in all_acus:
    #             acu = acu_tuple[1]
    #             activity = acu.component
    #             if activity.activity_of.id == current_system:
    #                 item = EventBlock(activity=activity, parent_activity=current_activity)
    #                 item_list.append(item)
    #                 scene.addItem(item)
    #                 scene.update()
    #         scene.timeline.populate(item_list)
    #     # self.view.show()
    #     return scene
    #

    # def show_history(self):
    #     history_string = ""
    #     for activity in self.history:
    #         id = activity.id or "NA"
    #         history_string += id + " >"
    #     history_string += self.subject_activity.id or "NA"
    #     history_string+= " >"
    #     self.statusbar.showMessage(history_string)

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
