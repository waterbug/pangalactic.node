#!/usr/bin/env python
from __future__  import print_function
from __future__  import unicode_literals
from __future__ import division
from future import standard_library
standard_library.install_aliases()
# NOTE: fixed div's so old_div is not needed.
# from past.utils import old_div
import os
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
    def __init__(self, scene, shape, obj=None, style=None,
                 editable=False, port_spacing=0):
        super(EventBlock, self).__init__()
        """
        Initialize Block.

        Args:
            position (QPointF):  where to put upper left corner of block
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
        self.setFocus()
        self.scene = scene
        self.shape = shape
        self.previous = None
        self.next = None
        self.setBrush(Qt.white)
        self.create_actions()
        path = QPainterPath()

        if self.shape == "Box":
            self.myPolygon = QPolygonF([
                    QPointF(0, 0), QPointF(0, 100),
                    QPointF(100, 100), QPointF(100, 0)
            ])
        if self.shape == "Triangle":
             self.myPolygon = QPolygonF([
                     QPointF(0, 0), QPointF(-80, 80),
                     QPointF(80, 80)
             ])
        if self.shape == "Circle":
            self.setFlags(QGraphicsItem.ItemSendsGeometryChanges)
            path.addEllipse(0, 0, 100, 100)
            self.myPolygon = path.toFillPolygon()
        self.setPolygon(self.myPolygon)

    def contextMenuEvent(self, event):
        self.menu = QMenu()
        self.menu.addAction(self.delete_action)
        # self.menu.exec(QPoint(event.scenePos().x(), event.scenePos().y()))
        self.menu.exec(QCursor.pos())
    def create_actions(self):
        self.delete_action = QAction("Delete", self.scene, statusTip="Delete Item", triggered= self.deleteItem)

    def deleteItem(self):
        self.scene.removeItem(self)
        self.scene.update()

    def itemChange(self, change, value):
        self.update_position()
        return value

    def update_position(self):
        self.left_point = self.mapToScene(self.boundingRect().left(), self.boundingRect().center().y())
        self.right_point = self.mapToScene(QPointF(self.boundingRect().right(), self.boundingRect().center().y()))
        if getattr(self, "previous", None) != None:
            self.previous.update_position()
        if getattr(self, "next", None) != None:
            self.next.update_position()

    def set_previous(self, item):
        self.previous = item
    def set_next(self, item):
        self.next = item
    def mouseReleaseEvent(self, event):
        super(EventBlock, self).mouseReleaseEvent(event)
        if (event.button() == Qt.LeftButton):
            if self.shape == "Triangle":
                self.setPos(event.scenePos().x(), 150)
            else:
                self.setPos(event.scenePos().x(), 100)

class DiagramView(QGraphicsView):
    def __init__(self, parent=None):
        super(DiagramView, self).__init__(parent)

    def dragEnterEvent(self, event):
        event.accept()

    def dropEvent(self, event):
        #print(event.mimeData().text())
        item = EventBlock(self.scene(), event.mimeData().text())
        self.scene().addItem(item)
        item.setPos(self.mapToScene(event.pos()))
        if item.shape == "Triangle":
            item.setPos(QPointF(self.mapToScene(event.pos()).x(), 150))
        else:
            item.setPos(QPointF(self.mapToScene(event.pos()).x(), 100))
        self.update()

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
        self.event_list = []
        self.item_1 = item_1
        self.item_2 = item_2
        self.previous = item_1
        self.next = item_2
        self.item_1.next = self
        self.item_2.previous = self

        self.p1 = self.previous.right_point
        self.p2 = self.next.left_point
        self.path =  QPainterPath(self.p1)
        self.path.lineTo(self.p2)
        self.setPath(self.path)

    def update_position(self):
        self.p1 = self.previous.right_point
        self.p2 = self.next.left_point
        self.path =  QPainterPath(self.p1)
        self.path.lineTo(self.p2)
        self.setPath(self.path)

class DiagramScene(QGraphicsScene):
    def __init__(self, parent):
        super(DiagramScene, self).__init__(parent)
        self.start = EventBlock(self, "Circle")
        self.end = EventBlock(self, "Circle")
        self.start.setPos(50, 100)
        self.end.setPos(1500, 100)
        # self.start.update_position()
        # self.end.update_position()
        self.addItem(self.start)
        self.addItem(self.end)
        # self.timeline = Timeline(self.start.scenePos().x(), self.end.scenePos().x(), self.end.scenePos().y())
        self.timeline = Timeline(self.start, self.end)
        #print(self.start.right_point.x(), self.end.left_point.x())
        self.addItem(self.timeline)


    def mousePressEvent(self, mouseEvent):
        super(DiagramScene, self).mousePressEvent(mouseEvent)

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
        self.history = []
        self.setSizePolicy(QSizePolicy.Expanding,
                           QSizePolicy.Expanding)
        self.createLibrary()
        self.scene = DiagramScene(self)
        self.scene.setSceneRect(0,0, 2000, 1000)
        # start = EventBlock(self.scene, "Circle")
        # end = EventBlock(self.scene, "Circle")
        # start.setPos(50, 100)
        # end.setPos(1500, 100)
        # # self.timeline = Timeline(start.scene_right_center.x(), end.scene_left_center.x(), start.scene_center.y())
        #
        # self.scene.addItem(start)
        # self.scene.addItem(end)
        self.set_new_view(self.scene)
        # self.timeline = Timeline(start.scene_center.x(), end.scene_center.x(), start.scene_center.y())
        # self.timeline.setPos(0, 0)
        # # self.timeline_pen = QPen()
        # # self.timeline_pen.setWidth(5)
        # # self.timeline.setPen(self.timeline_pen)
        # self.scene.addItem(self.timeline)
        self.view.setAcceptDrops(True)
        self.view.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self._init_ui()
        self.view.show()
        layout = QHBoxLayout()
        layout.addWidget(self.view)
        layout.addWidget(self.library)
        self.widget = QWidget()
        self.widget.setLayout(layout)
        self.setCentralWidget(self.widget)
        self.widget.setAcceptDrops(True)



    def createLibrary(self):
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
        # TODO:  create a dialog for saving a diagram to a SysML file ...
        # self.save_action = self.create_action(
                                    # "Save Model...",
                                    # slot=self.write_block_model,
                                    # icon="save",
                                    # tip="Save Model to a File")
        # self.toolbar.addAction(self.save_action)
        self.view_cad_action = self.create_action(
                                    "View CAD Model...",
                                    slot=self.display_cad_model,
                                    icon="view_16",
                                    tip="View CAD Model (from STEP File)")
        self.toolbar.addAction(self.view_cad_action)
        self.external_window_action = self.create_action(
                                    "Display external diagram window ...",
                                    slot=self.display_external_window,
                                    icon="system",
                                    tip="Display External Diagram Window")
        if not self.external:
            self.toolbar.addAction(self.external_window_action)
        self.scene_scale_select = QComboBox()
        self.scene_scale_select.addItems(["25%", "30%", "40%", "50%", "75%",
                                          "100%"])
        self.scene_scale_select.setCurrentIndex(3)
        self.scene_scale_select.currentIndexChanged[str].connect(
                                                    self.sceneScaleChanged)
        self.toolbar.addWidget(self.scene_scale_select)
        #self.toolbar.addAction(self.scene.print_action)
        #self.print_action = self.create_action("print",
        #                                       slot=self.print_preview,
        #                                       icon="printer",
        #                                       tip="Save as Image / Print")
        #self.toolbar.addAction(self.print_action)

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

    def print_preview(self):
        form = DocForm(scene=self.scene, edit_mode=False,
                       parent=self)
        form.show()

    '''def set_placeholder(self):
        new_placeholder = PlaceHolder(image=self.logo, min_size=200,
                                      parent=self)
        new_placeholder.setSizePolicy(QSizePolicy.Preferred,
                                      QSizePolicy.Preferred)
        self.setCentralWidget(new_placeholder)
        if getattr(self, 'placeholder', None):
            self.placeholder.close()
        self.placeholder = new_placeholder'''

    def display_external_window(self):
        orb.log.info('* ConOpsModeler.display_external_window() ...')
        mw = ConOpsModeler(scene=self.scene,
                           logo=self.logo, external=True,
                           preferred_size=(2000, 1000), parent=self.parent())
        mw.show()

    def set_new_view(self, scene):
        new_view = DiagramView(scene)
        new_view.setSizePolicy(QSizePolicy.Preferred,
                                       QSizePolicy.Preferred)
        layout = QVBoxLayout()
        layout.addWidget(new_view)
        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)
        if getattr(self, 'view', None):
            try:
                self.view.setAttribute(Qt.DeleteOnClose)
                self.view.parent = None
                self.view.close()
            except:
                # hmm, my C++ object was already deleted
                pass
        self.view = new_view
        self.sceneScaleChanged("50%")

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

    # def display_block_diagram(self):
    #     """
    #     Display a block diagram for the current object.
    #     """
    #     orb.log.info('* Modeler:  display_block_diagram()')
    #     if not getattr(self, 'obj', None):
    #         orb.log.info('  no object selected.')
    #         return
    #     self.set_new_view()
    #     scene = self.view.scene()
    #     model = diagramz.get(self.obj.oid)
    #     objs = []
    #     if hasattr(self.obj, 'components') and componentz.get(self.obj.oid):
    #         # self.obj is a Product -- use componentz cache (more efficient
    #         # than using obj.components ...
    #         oids = [c[0] for c in componentz[self.obj.oid]]
    #         objs = orb.get(oids=oids)
    #     elif hasattr(self.obj, 'systems') and len(self.obj.systems):
    #         # self.obj is a Project
    #         objs = [psu.system for psu in self.obj.systems]
    #     if model and not model.get('dirty'):
    #         orb.log.info('  - restoring saved block diagram ...')
    #         scene.restore_diagram(model, objs)
    #     else:
    #         if model and model.get('dirty'):
    #             orb.log.info('  - block diagram found needed redrawing,')
    #         elif not model:
    #             orb.log.info('  - no block diagram found in cache or files ')
    #         orb.log.info('    generating new block diagram ...')
    #         # orb.log.info('  - generating diagram (cache disabled for testing)')
    #         scene.create_ibd(objs)
    #         # create a block Model object if self.obj doesn't have one
    #         block_model_type = orb.get(BLOCK_OID)
    #         if self.obj.has_models:
    #             block_models = [m for m in self.obj.has_models
    #                 if getattr(m, 'type_of_model', None) == block_model_type]
    #             if not block_models:
    #                 model_id = get_block_model_id(self.obj)
    #                 model_name = get_block_model_name(self.obj)
    #                 self.model = clone('Model', id=model_id, name=model_name,
    #                                    type_of_model=block_model_type,
    #                                    of_thing=self.obj)

    def save_diagram_connector(self, start_item=None, end_item=None):
        pass

    def go_back(self):
        if self.history:
            hist = self.history.pop()
            obj, self.idx = hist.obj, hist.idx
            self.set_subject(obj=obj)
            if not self.history:
                self.back_action.setEnabled(False)
            dispatcher.send('diagram go back', index=self.idx)
        else:
            self.back_action.setEnabled(False)

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

    # DEPRECATED:  now using diagramz cache, not block model files
    # def write_block_model(self, cached_model=None, fpath=None):
        # """
        # Write the specified cached block model to a file (or if none is provided, the cached block
        # model of the current subject).

        # Args:
            # cached_model (dict): a serialized block model

        # Keyword args:
            # fpath (str):  path of file to be written.
        # """
        # orb.log.info('* Modeler: write_block_model()')
        # # TODO: find or create a Representation with 'of_object' == model.oid
        # # and a RepresentationFile that will get the file path as its 'url'
        # # attribute.
        # if not cached_model:
            # if (not self.obj or
                # not diagramz.get(self.obj.oid)):
                # orb.log.info('  no cached block model found; returning.')
                # return
            # cached_model = diagramz[self.obj.oid]
        # fname = get_block_model_file_name(self.obj)
        # if not fpath:
            # # write to vault if fpath is not given
            # orb.log.info('  writing to vault: {}'.format(fname))
            # fpath = os.path.join(orb.vault, fname)
        # f = open(fpath, 'w')
        # orb.log.info('  writing to path {} ...'.format(fpath))
        # f.write(json.dumps(cached_model,
                           # separators=(',', ':'),
                           # indent=4, sort_keys=True))
        # f.close()

    # DEPRECATED:  now using diagramz cache, not block model files
    # def read_block_model(self, fpath):
        # """
        # Read a serialized block model (dict) from the specified file path.

        # Args:
            # fpath (str): path to a serialized block model file
        # """
        # orb.log.info('* Modeler: read_block_model({})'.format(fpath))
        # if not os.path.exists(fpath):
            # orb.log.info('  - path does not exist.')
            # return None
        # f = open(fpath)
        # orb.log.info('  reading model from path {} ...'.format(fpath))
        # m = json.loads(f.read())
        # f.close()
        # return m

    # NOTE: 'set_canvas' is not currently used but should be
    def set_canvas(self, widget=None, name=None):
        if hasattr(self, 'canvas_widget') and self.canvas_widget is not None:
            self.canvas_box.removeWidget(self.canvas_widget)
            self.canvas_widget.deleteLater()
        if not hasattr(self, 'canvas_label'):
            self.canvas_label = NameLabel()
            self.canvas_label.setStyleSheet(
                            'font-weight: bold; font-size: 18px')
        self.canvas_label.setText(name or 'Model Canvas')
        self.canvas_box.addWidget(self.canvas_label)
        self.canvas_label.setAlignment(Qt.AlignLeft|Qt.AlignTop)
        if widget:
            self.canvas_widget = widget
        else:
            self.canvas_widget = PlaceHolder(image=self.logo, parent=self)
        self.canvas_box.addWidget(self.canvas_widget)
        self.canvas_box.setStretch(0, 0)
        self.canvas_box.setStretch(1, 1)
        self.canvas_box.setAlignment(Qt.AlignLeft|Qt.AlignTop)

    def create_new_model(self, event):
        if isinstance(self.obj, orb.classes['Identifiable']):
            # TODO:  check for parameters; if found, add them
            orb.log.info('* ConOpsModeler: creating new Model for '
                         'Product with id "%s"' % self.obj.id)
            owner = orb.get(state.get('project'))
            new_model = clone('Model', owner=owner, of_thing=self.obj)
            dlg = PgxnObject(new_model, edit_mode=True, parent=self)
            # dialog.show() -> non-modal dialog
            dlg.show()




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
