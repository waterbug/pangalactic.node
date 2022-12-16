"""
Optical System tool for computing the error budget of an optical system.
"""
#!/usr/bin/env python

import os

from louie import dispatcher

from PyQt5.QtCore import Qt, QRectF, QPointF, QPoint, QMimeData
from PyQt5.QtWidgets import (QAction, QApplication, QComboBox, QDockWidget,
                             QMainWindow, QWidget, QGraphicsItem,
                             QGraphicsPolygonItem, QGraphicsScene,
                             QGraphicsView, QHBoxLayout, QMenu, QPushButton,
                             QGraphicsPathItem, QSizePolicy, QToolBar,
                             QVBoxLayout, QWidgetAction)
# from PyQt5.QtWidgets import (QMessageBox, QStatusBar, QToolBox,
from PyQt5.QtGui import (QBrush, QDrag, QIcon, QPen, QCursor, QPainterPath,
                         QPolygonF, QTransform)
# from PyQt5.QtGui import QGraphicsProxyWidget

# pangalactic
from pangalactic.core             import state
from pangalactic.core.parametrics import get_dval, set_dval
# from pangalactic.core.parametrics import get_pval
from pangalactic.core.uberorb     import orb
from pangalactic.node.diagrams.shapes import BlockLabel
from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.tableviews  import SystemInfoTable
# from pangalactic.node.utils       import clone
from pangalactic.node.widgets     import NameLabel


class OpticalComponentBlock(QGraphicsPolygonItem):

    def __init__(self, usage=None, style=None, parent=None):
        """
        Initialize Optical Component Block.

        Keyword Args:
            usage (Acu):  optical component usage that the block
                represents
            style (Qt.PenStyle):  style of block border
            parent (QGraphicsItem): graphical parent of this item
        """
        super().__init__(parent)
        self.setFlags(QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemIsMovable |
                      QGraphicsItem.ItemIsFocusable |
                      QGraphicsItem.ItemSendsGeometryChanges)
        self.style = style or Qt.SolidLine
        self.usage = usage
        self.component = usage.component
        self.setBrush(Qt.white)
        path = QPainterPath()
        #---draw blocks depending on the 'shape' string passed in
        self.create_actions()
        if self.component.product_type.name == "Lens":
            path.addEllipse(0, -50, 20, 100)
            self.myPolygon = path.toFillPolygon(QTransform())
        elif self.component.product_type.name == "Mirror":
            self.myPolygon = QPolygonF([
                    QPointF(-1, 50), QPointF(1, 50),
                    QPointF(1, -50), QPointF(-1, -50)
            ])
        else:
            # generic optical component
            self.myPolygon = QPolygonF([
                    QPointF(-10, 50), QPointF(10, 50),
                    QPointF(10, -50), QPointF(-10, -50)
            ])
        self.setPolygon(self.myPolygon)
        label_txt = getattr(self.usage, 'reference_designator', '') or ''
        self.block_label = BlockLabel(label_txt, self, point_size=8)

    def on_component_edited(self, component=None):
        oid = getattr(component, 'oid', None)
        if oid == self.component.oid:
            self.block_label.set_text(getattr(self.component, 'name',
                                      'No Name') or 'No Name')

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        dispatcher.send("double clicked", acu=self.component)

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
                                   statusTip="Edit component",
                                   triggered=self.edit_component)

    def edit_component(self):
        self.scene().edit_parameters(self.component)

    def delete_item(self):
        orb.log.debug('* sending "remove component" signal')
        dispatcher.send("remove component", acu=self.component)

    def itemChange(self, change, value):
        return value

    def mousePressEvent(self, event):
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)


class OpticalSystemView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)

    def dragEnterEvent(self, event):
        try:
            event.accept()
        except:
            pass

    def dragMoveEvent(self, event):
        event.accept()

    def dragLeaveEvent(self, event):
        event.accept()


class OpticalSystemDiagram(QGraphicsPathItem):

    def __init__(self, scene, parent=None):
        super().__init__(parent)
        self.item_list = []
        self.path_length = 1000
        self.make_path()
        self.length = self.path.length() - 2 * self.circle_length
        if getattr(scene.system, 'components', None):
            self.num_of_item = len(scene.system.components)
        else:
            self.num_of_item = 0
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
        self.update_optical_path()

    def add_item(self, item):
        self.item_list.append(item)
        self.num_of_item = len(self.item_list)
        self.update_optical_path()

    def update_optical_path(self):
        self.calc_length()
        self.make_path()
        self.make_point_list()
        self.arrange()

    def calc_length(self):
        if len(self.item_list) <= 5:
            self.path_length = 1000
        else:
            # adjust optical_path length and rescale scene
            delta = len(self.item_list) - 5
            self.path_length = 1000 + (delta // 2) * 300
            scale = 70 - (delta // 2) * 10
            pscale = str(scale) + "%"
            dispatcher.send("rescale optical_path", percentscale=pscale)

    def make_point_list(self):
        self.length = self.path.length() - 2 * self.circle_length
        factor = self.length/(len(self.item_list) + 1)
        self.list_of_pos = [(n + 1) * factor + 100
                            for n in range(0, len(self.item_list))]

    def populate(self, item_list):
        self.item_list = item_list
        # if len(self.item_list) > 5 :
        #     self.extend_optical_path()
        # self.make_point_list()
        # self.arrange()
        self.update_optical_path()

    def arrange(self):
        item_list_copy = self.item_list[:]
        self.item_list.sort(key=lambda x: x.scenePos().x())
        same = True
        for item in self.item_list:
            if self.item_list.index(item) != item_list_copy.index(item):
                same = False
        if not same:
            des = {}
            for i, item in enumerate(self.item_list):
                item.setPos(QPoint(self.list_of_pos[i], 250))
                acu = item.usage
                set_dval(acu.oid, 'position_in_optical_path',
                         self.list_of_pos[i])
                des[acu.oid] = {}
                des[acu.oid]['position_in_optical_path'] = self.list_of_pos[i]
            # "des set" triggers pgxn to call rpc vger.set_data_elements()
            dispatcher.send("des set", des=des)
            # "order changed" only triggers the system table to update
            dispatcher.send("order changed")
        self.update()


class OpticalSystemScene(QGraphicsScene):
    def __init__(self, system=None, parent=None):
        super().__init__(parent)
        self.system = system
        self.diagram = OpticalSystemDiagram(self)
        self.addItem(self.diagram)
        # NOTE: not clear if this is necessary
        # self.focusItemChanged.connect(self.focus_changed_handler)
        self.current_focus = None
        self.grabbed_item = None

    # def focus_changed_handler(self, new_item, old_item):
        # if (new_item is not None and
            # new_item != self.current_focus):
            # pass

    def mousePressEvent(self, mouseEvent):
        super().mousePressEvent(mouseEvent)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self.grabbed_item = self.mouseGrabberItem()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.grabbed_item != None:
            self.grabbed_item.setPos(event.scenePos().x(), 250)
            self.diagram.arrange()
        self.grabbed_item == None

    # component type is one of "Lens", "Mirror", "Component"
    # ... but this is all going to change -- dropping a library item!!
    def dropEvent(self, event):
        # seq needs to be position_in_optical_path ...
        # seq = len(self.system.components) + 1
        # project = orb.get(state.get('project'))
        # TODO: come up with refdes
        # acu_id = get_acu_id(self.system.id, component.id, seq)
        # acu_name = get_acu_name(self.system.name, component.name, seq)
        # acu = clone("Acu", assembly=self.system,
                    # component=component, id=acu_id, name=acu_name)
        # orb.db.commit()
        # item = OpticalComponentBlock(usage=acu)
        # item.setPos(event.scenePos())
        # self.addItem(item)
        # self.optical_path.add_item(item)
        # orb.log.debug('* sending "new component" signal')
        # dispatcher.send("new component", assembly=self.system)
        self.update()
        # dispatcher.send("new object", obj=acu)

    def edit_parameters(self, component):
        view = ['id', 'name', 'description']
        panels = ['main', 'parameters']
        pxo = PgxnObject(component, edit_mode=True, view=view,
                         panels=panels, modal_mode=True, parent=self.parent())
        pxo.show()

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)


class ToolButton(QPushButton):
    def __init__(self, pixmap, text, parent=None):
        self.pixmap = pixmap
        super().__init__(QIcon(pixmap), text, parent)
        self.setFlat(True)

    def boundingRect(self):
        return QRectF(-5 , -5, 20, 20)

    def paint(self, painter, option, widget):
        painter.setPen(QPen(Qt.black, 1))
        painter.setBrush(QBrush(Qt.white))
        painter.drawRect(-5, -5, 20, 20)

    def mouseMoveEvent(self, event):
        event.accept()
        drag = QDrag(self)
        mime = QMimeData()
        drag.setMimeData(mime)
        mime.setText(self.mime)
        dragCursor = QCursor()
        dragCursor.setShape(Qt.ClosedHandCursor)
        drag.setDragCursor(self.pixmap, Qt.IgnoreAction)
        self.setCursor(Qt.OpenHandCursor)
        drag.setPixmap(self.pixmap)
        drag.setHotSpot(QPoint(15, 20))
        drag.exec_()
        self.clearFocus()

    def setData(self, mimeData):
        self.mime = mimeData

    def dragMoveEvent(self, event):
        event.setAccepted(True)


class OpticalSystemWidget(QWidget):
    def __init__(self, system, parent=None):
        super().__init__(parent=parent)
        orb.log.debug(' - initializing OpticalSystemWidget ...')
        self.system = system
        self.title = NameLabel('Optical System')
        self.set_title_text()
        self.plot_win = None
        self.subsys_ids = []
        self.init_toolbar()
        # self.title.setStyleSheet(
                        # 'font-weight: bold; font-size: 18px; color: purple')
        # self.setVisible(visible)
        self.scene = self.set_new_scene()
        self.view = OpticalSystemView(self)
        self.update_view()
        # self.statusbar = QStatusBar()
        self.layout = QVBoxLayout()
        # self.layout.addWidget(self.title)
        self.layout.addWidget(self.toolbar)
        self.layout.addWidget(self.view)
        # self.layout.addWidget(self.statusbar)
        self.setLayout(self.layout)
        # self.show_history()
        self.sceneScaleChanged("70%")
        dispatcher.connect(self.delete_component, "remove component")
        # dispatcher.connect(self.on_component_edited, 'component edited')
        dispatcher.connect(self.on_rescale_optical_path, "rescale optical_path")
        self.setUpdatesEnabled(True)

    def set_title_text(self):
        title_text = 'Optical System'
        sys_name = getattr(self.system, 'name', '')
        if sys_name:
            title_text += f' {sys_name}'
        self.title.setText(title_text)

    def set_new_scene(self):
        """
        Return a new scene with new system or an empty scene if no system.
        """
        orb.log.debug(' - set_new_scene ...')
        scene = OpticalSystemScene(system=self.system, parent=self)
        # TODO:  replace this with a sort function ...
        comps = getattr(self.system, 'components', []) or []
        if comps:
            all_acus = [(get_dval(acu, 'position_in_optical_path'), acu)
                        for acu in comps]
            try:
                all_acus.sort()
            except:
                pass
            item_list=[]
            for acu_tuple in all_acus:
                acu = acu_tuple[1]
                item = OpticalComponentBlock(usage=acu)
                item_list.append(item)
                scene.addItem(item)
            scene.diagram.populate(item_list)
        self.set_title_text()
        scene.update()
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
        #create and add scene scale menu
        self.scene_scales = ["25%", "30%", "40%", "50%", "60%", "70%", "80%"]
        self.scene_scale_select = QComboBox()
        self.scene_scale_select.addItems(self.scene_scales)
        self.scene_scale_select.setCurrentIndex(5)
        self.scene_scale_select.currentIndexChanged[str].connect(
                                                    self.sceneScaleChanged)
        self.toolbar.addWidget(self.scene_scale_select)

    def delete_component(self, acu=None):
        """
        Delete a component.

        Keyword Args:
            acu (Acu): the component to be deleted
        """
        # NOTE: DO NOT use dispatcher.send("deleted object") !!
        # -- that will cause a cycle
        oid = getattr(acu, "oid", None)
        if oid is None:
            return
        if acu in getattr(self.system, 'components', []):
            orb.delete(acu)
            dispatcher.send("removed component",
                            assembly=self.system)
        else:
            # if component is not in the current diagram, ignore
            return
        self.scene = self.set_new_scene()
        self.update_view()

    def sceneScaleChanged(self, percentscale):
        newscale = float(percentscale[:-1]) / 100.0
        self.view.setTransform(QTransform().scale(newscale, newscale))

    def on_rescale_optical_path(self, percentscale=None):
        if percentscale in self.scene_scales:
            new_index = self.scene_scales.index(percentscale)
            self.scene_scale_select.setCurrentIndex(new_index)
        else:
            orb.log.debug(f'* rescale factor {percentscale} unavailable')

    # def on_component_edited(self, component=None):
        # if component == self.component:
            # self.set_title()

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


class OpticalSystemModeler(QMainWindow):
    """
    Tool for modeling a Mission Concept of Operations for the currently
    selected project.
    """
    def __init__(self, system=None, parent=None):
        """
        Initialize the tool.

        Keyword Args:
            parent (QWidget):  parent widget

        Keyword Args:
            system (HardwareProduct): the optical system being modeled
        """
        super().__init__(parent=parent)
        orb.log.info('* OpticalSystemModeler initializing')
        self.system = system
        project = orb.get(state.get('project'))
        self.project = project
        self.setup_library()
        self.init_toolbar()
        self.top_dock = QDockWidget()
        self.top_dock.setObjectName('TopDock')
        self.top_dock.setFeatures(QDockWidget.DockWidgetFloatable)
        self.top_dock.setAllowedAreas(Qt.TopDockWidgetArea)
        self.addDockWidget(Qt.TopDockWidgetArea, self.top_dock)
        self.set_widgets(init=True)
        dispatcher.connect(self.double_clicked_handler, "double clicked")

    def set_widgets(self, init=False):
        """
        Add an OpticalSystemWidget containing all components of the system.

        Note that focusing (mouse click) on a component in the current system
        optical_path will select that component in the system table.
        """
        orb.log.debug(' - set_widgets() ...')
        self.system_widget = OpticalSystemWidget(self.system)
        self.system_widget.setMinimumSize(900, 150)
        # FilterPanel with all optical system components
        view = ['ref des',
                'RoC', 'K',
                'X_vertex',
                'Y_vertex',
                'Z_vertex',
                'RotX_vertex',
                'RotY_vertex',
                'RotZ_vertex',
                'dRMSWFE_dx', 'dRMSWFE_dy', 'dRMSWFE_dz',
                'dRMSWFE_rx', 'dRMSWFE_ry', 'dRMSWFE_rz',
                'dLOSx_dx', 'dLOSx_dy', 'dLOSx_dz',
                'dLOSx_rx', 'dLOSx_ry', 'dLOSx_rz',
                'dLOSy_dx', 'dLOSy_dy', 'dLOSy_dz',
                'dLOSy_rx', 'dLOSy_ry', 'dLOSy_rz']
        self.system_table = SystemInfoTable(system=self.system, view=view,
                                            parent=self)
        # self.system_table.setMinimumSize(500, 300)
        self.system_table.setSizePolicy(QSizePolicy.Expanding,
                                        QSizePolicy.Expanding)
        self.system_table_panel = QWidget()
        self.system_table_panel.setMinimumSize(1450, 600)
        # self.system_table_panel.setMinimumSize(1000, 600)
        system_table_layout = QHBoxLayout()
        system_table_layout.addWidget(self.system_table)
        self.system_table_panel.setLayout(system_table_layout)
        self.setCentralWidget(self.system_table_panel)
        self.top_dock = QDockWidget()
        self.top_dock.setObjectName('TopDock')
        self.top_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.top_dock.setAllowedAreas(Qt.TopDockWidgetArea)
        self.addDockWidget(Qt.TopDockWidgetArea, self.top_dock)
        self.top_dock.setWidget(self.system_widget)

    def setup_library(self):
        """
        Set up the library of optical system components
        """
        orb.log.debug(' - setup_library() ...')
        # set up a HW library widget filtered by "optical component"

    # TODO -- *MAYBE* do drill-down later ... whatever it means here ...
    def double_clicked_handler(self, acu):
        # """
        # Handle a double-click event on an eventblock, creating and
        # displaying a new view.
        # Args:
            # obj (EventBlock):  the block that received the double-click
        # """
        # dispatcher.send("drill down", obj=acu)
        # self.component = acu
        # self.scene = self.set_new_scene()
        # self.update_view()
        # previous = acu.where_occurs[0].assembly
        # self.go_back_action.setDisabled(False)
        pass

    def init_toolbar(self):
        orb.log.debug(' - init_toolbar() ...')
        self.toolbar = self.addToolBar("Actions")
        self.toolbar.setObjectName('ActionsToolBar')

    def resizeEvent(self, event):
        state['model_window_size'] = (self.width(), self.height())


if __name__ == '__main__':
    import sys
    # orb.start(home='junk_home', debug=True)
    orb.start(home='/home/waterbug/cattens_home_dev', debug=True)
    app = QApplication(sys.argv)
    mw = OpticalSystemModeler()
    mw.show()
    sys.exit(app.exec_())

