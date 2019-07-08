#!/usr/bin/env python
from __future__  import print_function
from __future__  import unicode_literals
from __future__ import division
from future import standard_library
standard_library.install_aliases()
# NOTE: fixed div's so old_div is not needed.
# from past.utils import old_div
import os
import copy
from collections import namedtuple
from urllib.parse    import urlparse

from louie import dispatcher

from PyQt5.QtCore import Qt, QRectF,QPointF, QSizeF, QObject, pyqtSignal, qrand, QLineF, QPoint, QMimeData
from PyQt5.QtWidgets import (QAction, QApplication, QComboBox, QHBoxLayout,
                             QLayout, QMainWindow, QSizePolicy, QVBoxLayout,
                             QWidget,QAction, QApplication, QButtonGroup, QComboBox,
        QFontComboBox, QGraphicsItem, QGraphicsLineItem, QGraphicsPolygonItem,
        QGraphicsScene, QGraphicsTextItem, QGraphicsView, QGridLayout,
        QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox, QSizePolicy,
        QToolBox, QToolButton, QWidget, QPushButton, QAbstractItemView, QGraphicsPathItem)
from PyQt5.QtGui import (QIcon, QTransform, QBrush, QColor, QDrag, QImage, QPainter, QPen, QPixmap, QCursor, QPainterPath,
                        QPolygon, QPolygonF, QFont)

# pangalactic
from pangalactic.core             import diagramz, state
from pangalactic.core.parametrics import componentz
from pangalactic.core.uberorb     import orb
from pangalactic.core.utils.meta  import (asciify, get_block_model_id,
                                             get_block_model_name,
                                             get_block_model_file_name)
from pangalactic.node.dialogs     import Viewer3DDialog
from pangalactic.node.diagrams    import DocForm
from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.utils       import clone, extract_mime_data
from pangalactic.node.widgets     import NameLabel, PlaceHolder, ValueLabel

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
    def __init__(self, shape, activity=None, current_activity=None, style=None,
                 editable=False, port_spacing=0):
        super(EventBlock, self).__init__()
        """
        Initialize Block.

        Args:
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
        self.shape = shape
        self.setBrush(Qt.white)
        self.create_actions()
        path = QPainterPath()
        self.activity = activity or clone("Activity")

    #---draw blocks depending on the 'shape' string passed in
        if self.shape == "Box":
            self.myPolygon = QPolygonF([
                    QPointF(-50, 50), QPointF(50, 50),
                    QPointF(50, -50), QPointF(-50, -50)
            ])
        if self.shape == "Triangle":
             self.myPolygon = QPolygonF([
                     QPointF(0, 0), QPointF(-50, 80),
                     QPointF(50, 80)
             ])
        if self.shape == "Circle":
            path.addEllipse(-50, -50, 100, 100)
            self.myPolygon = path.toFillPolygon()
            self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setPolygon(self.myPolygon)

    def mouseDoubleClickEvent(self, event):
        dispatcher.send("double clicked", obj=self.activity)

    def contextMenuEvent(self, event):
        self.menu = QMenu()
        self.menu.addAction(self.delete_action)
        self.menu.exec(QCursor.pos())

    def create_actions(self):
        self.delete_action = QAction("Delete", self.scene(), statusTip="Delete Item", triggered= self.deleteItem)

    def deleteItem(self):
        self.scene().timeline.remove_item(self)
        self.scene().removeItem(self)

    def itemChange(self, change, value):
        # super(EventBlock, self).itemChange(change, value)
        # self.update_position()
        return value


    def mouseReleaseEvent(self, event):
        super(EventBlock, self).mouseReleaseEvent(event)
        if (event.button() == Qt.LeftButton):
            if self.shape == "Triangle":
                self.setPos(event.scenePos().x(), 150)
            else:
                self.setPos(event.scenePos().x(), 150)
            self.scene().timeline.reposition()

    def collides_with_timeline(self):
        self.on_timeline = False

class DiagramView(QGraphicsView):
    def __init__(self, parent=None):
        super(DiagramView, self).__init__(parent)

    def dragEnterEvent(self, event):
        event.accept()

    def dragMoveEvent(self, event):
        event.accept()

    def dragLeaveEvent(self, event):
        event.accept()

class Timeline(QGraphicsPathItem):
    def __init__(self, item_1, item_2, parent=None):
        super(Timeline, self).__init__(parent)
        self.setFlags(QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemIsMovable |
                      QGraphicsItem.ItemIsFocusable)
        self.item_list = []
        self.item_1 = item_1
        self.item_2 = item_2
        self.p1 = item_1.scenePos()
        self.p2 = item_2.scenePos()
        self.path =  QPainterPath(QPointF(self.p1.x()+50, self.p1.y()))
        self.path.lineTo(QPointF(self.p2.x()-50, self.p2.y()))
        self.setPath(self.path)
        self.length = self.p2.x()-self.p1.x()
        self.num_of_item = len(self.item_list)
        self.make_point_list()
        self.current_positions = []

    def item_relocated_handler(self):
        print("")

    def add_item(self, item):
        self.item_list.append(item)
        self.num_of_item = len(self.item_list)
        self.update_timeline()

    def update_timeline(self):
        self.make_point_list()
        self.reposition()

    def make_point_list(self):
        factor = self.length/(self.num_of_item+1)
        self.list_of_pos = [(n+1)*factor+self.p1.x() for n in range(0, self.num_of_item)]

    def reposition(self):
        self.item_list.sort(key=lambda x: x.scenePos().x())
        for i in range(0, len(self.item_list)):
            if self.item_list[i].shape == "Triangle":
                self.item_list[i].setPos(QPoint(self.list_of_pos[i], 150))
                self.item_list[i].activity.components.reference_designator = u"{}".format(i)
            else:
                self.item_list[i].setPos(QPoint(self.list_of_pos[i], 150))
                self.item_list[i].activity.components.reference_designator = u"{}".format(i)


    def remove_item(self, item):
        if item in self.item_list:
            self.item_list.remove(item)
        self.update_timeline()

class DiagramScene(QGraphicsScene):
    def __init__(self, parent, current_activity=None):
        super(DiagramScene, self).__init__(parent)
        self.current_activity = current_activity
        self.val = 10
        self.start = EventBlock("Circle")
        self.end = EventBlock("Circle")
        self.start.setPos(100, 150)
        self.end.setPos(1500, 150)
        self.addItem(self.start)
        self.addItem(self.end)
        self.timeline = Timeline(self.start, self.end)
        self.addItem(self.timeline)

    def mousePressEvent(self, mouseEvent):
        super(DiagramScene, self).mousePressEvent(mouseEvent)

    def dropEvent(self, event):
        activity = clone("Activity")
        acu = clone("Acu", assembly=self.current_activity, component=activity)
        item = EventBlock(event.mimeData().text(), activity=activity, current_activity=self.current_activity)
        item.setPos(event.scenePos())
        self.timeline.add_item(item)
        self.addItem(item)
        print("reference_des:", item.activity.components.reference_designator)
        self.update()

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
    Main window for displaying models and their metadata.

    Attrs:
        model_files (dict):  maps model "types" (for now just "CAD" and
            "Block") to paths of associated files in vault
        idx (QModelIndex):  index in the system tree's proxy model
            corresponding to the object being modeled
        history (list):  list of previous ModelerState instances
    """
    def __init__(self, preferred_size, scene=None, logo=None, idx=None,
                 external=False, parent=None):
        """
        Main window for displaying models and their metadata.

        Keyword Args:
            obj (Identifiable):  object being modeled
            scene (QGraphicsScene):  existing scene to be used (if None, a new
                one will be created)
            logo (str):  relative path to an image file to be used as the
                "placeholder" image when object is not provided
            idx (QModelIndex):  index in the system tree's proxy model
                corresponding to the object being modeled
            external (bool):  initialize as an external window
            preferred_size (tuple):  size to set -- (width, height)
        """
        super(ConOpsModeler, self).__init__(parent=parent)
        orb.log.info('* ConOpsModeler initializing with:')
        orb.log.info('  obj "{}"'.format(getattr(obj, 'oid', 'None')))
        self.logo = logo
        self.external = external
        self.idx = idx
        self.preferred_size = preferred_size
        self.model_files = {}
        self.temp_activity = clone("Activity")
#-----------------------------------------------------------#
        self.createLibrary()
        self.scene = DiagramScene(self, self.temp_activity)
        self.set_new_view(self.scene, current_activity=self.temp_activity)

        self._init_ui()
        #------------lisening for signals------------#
        dispatcher.connect(self.double_clicked_handler, "double clicked")
        self.history = []
        self.history.append(self.temp_activity)
        self.current_viewing_activity = self.temp_activity

    def createLibrary(self):
        '''create the shape library'''
        self.buttonGroup = QButtonGroup()
        self.buttonGroup.setExclusive(True)
        layout = QGridLayout()
        b1 = ToolButton("Rectangle")
        b1.setData("Box")
        b2 = ToolButton("Triangle")
        b2.setData("Triangle")
        layout.addWidget(b1)
        layout.addWidget(b2)
        itemWidget = QWidget()
        itemWidget.setLayout(layout)
        self.library = QToolBox()
        self.library.addItem(itemWidget, "Shapes")
        self.buttonGroup.addButton(b1, 1)
        self.buttonGroup.addButton(b2, 2)


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
                                    tip="Back to Previous Model")
        self.toolbar.addAction(self.back_action)

        self.external_window_action = self.create_action(
                                    "Display external diagram window ...",
                                    slot=self.display_external_window,
                                    icon="system",
                                    tip="Display External Diagram Window")
        if not self.external:
            self.toolbar.addAction(self.external_window_action)
        #create and add scene scale menu
        self.scene_scale_select = QComboBox()
        self.scene_scale_select.addItems(["25%", "30%", "40%", "50%", "75%",
                                          "100%"])
        self.scene_scale_select.setCurrentIndex(3)
        self.scene_scale_select.currentIndexChanged[str].connect(
                                                    self.sceneScaleChanged)
        self.toolbar.addWidget(self.scene_scale_select)


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
            action.setStatusTip(tip)
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
        '''handler for double clicking an eventblock. create and
        display new view'''
        new_scene = DiagramScene(self, current_activity=obj)
        self.set_new_view(new_scene, current_activity=obj)
        self.current_viewing_activity = obj
        # print("before append", len(self.history))
        previous = obj.where_used[0].assembly
        self.history.append(previous)
        # print("after append", len(self.history))

    def set_new_view(self, scene=None, current_activity=None):
        # print("set_new_view")
        current_activity = current_activity or self.temp_activity
        self.scene = scene
        self.scene.setSceneRect(0,0, 2000, 1000)
        self.view = DiagramView(self.scene)
        self.view.setSizePolicy(QSizePolicy.Preferred,
                                QSizePolicy.Preferred)
        self.view.setScene(self.scene)

        layout = QHBoxLayout()
        layout.addWidget(self.view)
        layout.addWidget(self.library)
        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)
        self.sceneScaleChanged("50%")

        if current_activity != None:
            print(len(current_activity.components))
        #    current_activity.components.sort(key=lambda acu:acu.reference_designator)
            for acu in current_activity.components:
                activity = acu.component
                item = EventBlock("Box", activity=activity, current_activity=current_activity)
                self.scene.timeline.add_item(item)
                self.scene.addItem(item)
                self.scene.update()
        self.view.show()

    def go_back(self):
        # print("go back clicked")
        try:
            # print("before pop", len(self.history))
            previous_activity = self.history.pop()
            # print("after pop", len(self.history))
            new_scene = DiagramScene(self, previous_activity)
            self.set_new_view(new_scene, current_activity=previous_activity)
        except IndexError:
            print("IndexError, length of self.history:", len(self.history))

    def set_subject_from_diagram_drill_down(self, obj=None):
        """
        Respond to a double-clicked diagram block by setting the corresponding
        object as the subject of the model window.

        Keyword Args:
            obj (Identifiable): if no model is provided, find models of obj
        """
        self.cache_block_model()
        self.history.append(ModelerState._make((self.obj, self.idx)))
        self.idx = None
        self.set_subject(obj=obj)

    def set_subject_from_node(self, index=None, obj=None):
        """
        Respond to a node selection in the system tree or dashboard by setting
        the corresponding object as the subject of the model window.

        Keyword Args:
            index (QModelIndex):  index in the system tree's proxy model
                corresponding to the object being modeled
            obj (Identifiable): obj being modeled
        """
        self.cache_block_model()
        self.history.append(ModelerState._make((self.obj, self.idx)))
        self.idx = index
        self.set_subject(obj=obj)

    def set_subject(self, obj=None):


        """
        Set an object for the current modeler context.  If the object does not
        have a Block model one is created from its components (or an empty
        Block Model if there are no components).

        Keyword Args:
            obj (Identifiable): if no model is provided, find models of obj
        """
        orb.log.info('* ConOpsModeler.set_subject()')
        orb.log.info('  obj "{}"'.format(getattr(obj, 'oid', 'None')))
        # reset model_files
        self.model_files = {}
        if hasattr(self, 'view_cad_action'):
            try:
                self.view_cad_action.setVisible(False)
            except:
                # oops, C++ object got deleted
                pass
        self.obj = obj
        if self.obj:
            if isinstance(self.obj, orb.classes['Modelable']):
                orb.log.info('* ConOpsModeler: checking for models ...')
                # model_types = set()
                if self.obj.has_models:
                    for m in self.obj.has_models:
                        fpath = get_model_path(m)
                        if fpath:
                            # fpath only needed for CAD models, since block
                            # models have a canonical path
                            self.model_files[m.oid] = fpath
                        # model_types.add(m.type_of_model.oid)
                self.display_block_diagram()
            else:
                orb.log.info('* ConOpsModeler: obj is not Modelable, ignoring')
                self.obj = None
                orb.log.info('  ... setting placeholder widget.')
                self.set_placeholder()
        else:
            self.obj = None
            orb.log.info('  no object; setting placeholder widget.')
            self.set_placeholder()
        # TODO:  enable multiple CAD models (e.g. "detailed" / "simplified")
        if self.model_files:
            self.models_by_label = {}
            for oid, fpath in self.model_files.items():
                model = orb.get(oid)
                if getattr(model.type_of_model, 'oid', None) in ['step:203',
                                                                 'step:214']:
                    self.models_by_label['CAD'] = (model, fpath)
                    if hasattr(self, 'view_cad_action'):
                        self.view_cad_action.setVisible(True)
        if self.history:
            if hasattr(self, 'back_action'):
                self.back_action.setEnabled(True)
        else:
            if hasattr(self, 'back_action'):
                self.back_action.setEnabled(False)
        self.cache_block_model()
        self.view.verticalScrollBar().setValue(0)
        self.view.horizontalScrollBar().setValue(0)

    def display_cad_model(self):
        try:
            model, fpath = self.models_by_label.get('CAD')
            if fpath:
                orb.log.info('* ConOpsModeler.display_cad_model({})'.format(
                                                                     fpath))
                viewer = Viewer3DDialog(self)
                viewer.show()
                viewer.view_cad(fpath)
        except:
            orb.log.info('  CAD model not found.')

    def save_diagram_connector(self, start_item=None, end_item=None):
        pass


    def cache_block_model(self):
        """
        Serialize block model metadata into a dictionary format and save it to
        the `diagramz` cache.
        """
        orb.log.info('* Modeler: cache_block_model()')
        # TODO: first "block"; then "activity" (mission models, etc.)
        if not getattr(self, 'obj'):
            orb.log.info('  ... no object, returning.')
            return
        try:
            scene = self.scene
            m = scene.save_diagram()
            # cache the saved diagram
            diagramz[self.obj.oid] = m
            orb.log.info('  ... block model cached.')
        except:
            orb.log.info('  ... could not cache model (C++ obj deleted?)')



if __name__ == '__main__':
    import sys
    from pangalactic.core.test.utils import (create_test_users,
                                             create_test_project)
    from pangalactic.core.serializers import deserialize
    orb.start(home='junk_home', debug=True)



    serialized_test_objects = create_test_users()
    serialized_test_objects += create_test_project()
    deserialize(orb, serialized_test_objects)
    obj = orb.get('test:twanger')
    app = QApplication(sys.argv)
    mw = ConOpsModeler(external=True, preferred_size=(2000, 1000))
    mw.show()
    sys.exit(app.exec_())
