"""
Optical System tool for computing the error budget of an optical system.
"""
#!/usr/bin/env python

import os

from louie import dispatcher

from PyQt5.QtCore import Qt, QRectF, QPointF, QPoint
from PyQt5.QtWidgets import (QAction, QApplication, QComboBox, QDockWidget,
                             QMainWindow, QWidget, QGraphicsItem,
                             QGraphicsPolygonItem, QGraphicsScene,
                             QGraphicsView, QHBoxLayout, QMenu, QMessageBox,
                             QGraphicsPathItem, QSizePolicy, QToolBar,
                             QVBoxLayout, QWidgetAction)
# from PyQt5.QtWidgets import (QMessageBox, QStatusBar, QToolBox,
from PyQt5.QtGui import QIcon, QCursor, QPainterPath, QPolygonF, QTransform
# from PyQt5.QtGui import QGraphicsProxyWidget

# pangalactic
from pangalactic.core             import state
from pangalactic.core.access      import get_perms
from pangalactic.core.meta        import PGXN_PLACEHOLDERS
from pangalactic.core.names       import (get_acu_id, get_acu_name,
                                          get_next_ref_des)
from pangalactic.core.parametrics import get_dval, set_dval
# from pangalactic.core.parametrics import get_pval
from pangalactic.core.uberorb     import orb
from pangalactic.core.utils.datetimes import dtstamp
from pangalactic.core.validation  import get_bom_oids
from pangalactic.node.buttons     import SizedButton
from pangalactic.node.diagrams.shapes import BlockLabel
from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.tableviews  import SystemInfoTable
from pangalactic.node.utils       import (clone, extract_mime_data,
                                          create_product_from_template)
from pangalactic.node.widgets     import NameLabel, StringFieldWidget, ValueLabel


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

    def dropEvent(self, event):
        orb.log.debug("* OpticalSystemScene: hm, something dropped on me ...")
        user = orb.get(state.get('local_user_oid'))
        sys_oid = getattr(self.system, 'oid', '')
        if not sys_oid:
            popup = QMessageBox(
                  QMessageBox.Critical,
                  "No System",
                  "Cannot add a component",
                  QMessageBox.Ok, self.parent())
            popup.show()
            event.ignore()
            return
        if self.system and not 'modify' in get_perms(self.system):
            # --------------------------------------------------------
            # 00: user permissions prohibit operation -> abort
            # --------------------------------------------------------
            popup = QMessageBox(
                  QMessageBox.Critical,
                  "Unauthorized Operation",
                  "User's roles do not permit this operation",
                  QMessageBox.Ok, self.parent())
            popup.show()
            event.ignore()
            return
        if event.mimeData().hasFormat("application/x-pgef-hardware-product"):
            data = extract_mime_data(event,
                                     "application/x-pgef-hardware-product")
            icon, obj_oid, obj_id, obj_name, obj_cname = data
            if sys_oid == obj_oid:
                # ------------------------------------------------------------
                # 0: dropped item is system; would cause a cycle -> abort!
                # ------------------------------------------------------------
                orb.log.debug(
                  '    invalid: dropped object is the system, aborted.')
                popup = QMessageBox(
                            QMessageBox.Critical,
                            "Assembly same as Component",
                            "A product cannot be a component of itself.",
                            QMessageBox.Ok, self.parent())
                popup.show()
                event.ignore()
                return
            dropped_item = orb.get(obj_oid)
            if dropped_item:
                orb.log.info('  - dropped object name: "{}"'.format(obj_name))
            else:
                orb.log.info("  - dropped product oid not in db.")
                event.ignore()
                return
            bom_oids = get_bom_oids(dropped_item)
            if sys_oid in bom_oids:
                # ---------------------------------------------------------
                # 0: target is a component of dropped item (cycle) -> abort
                # ---------------------------------------------------------
                popup = QMessageBox(
                        QMessageBox.Critical,
                        "Prohibited Operation",
                        "Product cannot be used in its own assembly.",
                        QMessageBox.Ok, self.parent())
                popup.show()
                event.ignore()
                return
            if (isinstance(dropped_item.owner,
                  orb.classes['Project']) and
                  dropped_item.owner.oid != state.get('project')
                  and not dropped_item.frozen):
                msg = '<b>The spec for the dropped item is owned '
                msg += 'by another project and is not frozen, '
                msg += 'so it cannot be used on this project. '
                msg += 'If a similar item is '
                msg += 'needed, clone the item and then add the '
                msg += 'clone to this assembly.</b>'
                popup = QMessageBox(
                      QMessageBox.Critical,
                      "Prohibited Operation", msg,
                      QMessageBox.Ok, self.parent())
                popup.show()
                return
            # --------------------------------------------------------
            # -> add the dropped item as a new component
            # --------------------------------------------------------
            # add new Acu
            orb.log.info('      accepted as component ...')
            # orb.log.debug('      creating Acu ...')
            # generate a new reference_designator
            ref_des = get_next_ref_des(self.system, dropped_item)
            # NOTE: clone() adds create/mod_datetime & creator/modifier
            new_acu = clone('Acu',
                id=get_acu_id(self.system.id, ref_des),
                name=get_acu_name(self.system.name, ref_des),
                assembly=self.system,
                component=dropped_item,
                product_type_hint=dropped_item.product_type,
                creator=user,
                create_datetime=dtstamp(),
                modifier=user,
                mod_datetime=dtstamp(),
                reference_designator=ref_des)
            # new Acu -> self.system is modified (any computed
            # parameters must be recomputed, etc.)
            self.system.mod_datetime = dtstamp()
            self.system.modifier = user
            # add block before orb.save(), which takes time ...
            item = OpticalComponentBlock(usage=new_acu)
            item.setPos(event.scenePos())
            self.addItem(item)
            self.optical_path.add_item(item)
            orb.save([new_acu, self.system])
            # orb.log.debug('      Acu created: {}'.format(
                          # new_acu.name))
            dispatcher.send('new object', obj=new_acu)
            dispatcher.send('modified object', obj=self.system)
            self.update()

    def edit_parameters(self, component):
        view = ['id', 'name', 'description']
        panels = ['main', 'parameters']
        pxo = PgxnObject(component, edit_mode=True, view=view,
                         panels=panels, modal_mode=True, parent=self.parent())
        pxo.show()

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)


class OpticalSysInfoPanel(QWidget):

    def __init__(self, system=None, parent=None):
        """
        Initialize OpticalSysInfoPanel.

        Keyword Args:
            system (HardwareProduct): an optical system
            parent (QWidget): the parent widget
        """
        # TODO: add a "Create Error Budget" button
        # TODO: make fields editable if "Create a New System" is clicked
        # - product_type is auto-set to "optical system"
        # - add "owner" field (selection list of orgs)
        # - add "TRL" field (selection list)
        # - "save" button validates fields ...
        # TODO: display a selection list of optical systems to which the user
        # has "modify" perms
        # - if only one, just load it
        # - if more than one but state has 'optical_system', load that one
        super().__init__(parent)
        orb.log.debug('* OpticalSysInfoPanel initializing ...')
        self._system = None
        self.setAcceptDrops(True)
        frame_vbox = QVBoxLayout()
        frame_vbox.setAlignment(Qt.AlignLeft|Qt.AlignTop)
        frame_vbox.setSizeConstraint(QVBoxLayout.SetMinimumSize)
        self.title = NameLabel('No System Loaded')
        self.title.setStyleSheet('font-weight: bold; font-size: 18px')
        frame_vbox.addWidget(self.title)
        info_panel_layout = QHBoxLayout()
        info_panel_layout.setAlignment(Qt.AlignLeft|Qt.AlignTop)
        self.system_id_label = NameLabel('id:')
        self.system_id_label.setStyleSheet('font-weight: bold')
        info_panel_layout.addWidget(self.system_id_label)
        self.system_id_value_label = ValueLabel('No System Loaded', w=200)
        info_panel_layout.addWidget(self.system_id_value_label)
        self.system_id_value_field = StringFieldWidget(value='', width=200,
            placeholder='generated (not editable)', parent=self)
        self.system_id_value_field.setEnabled(False)
        self.system_id_value_field.setVisible(False)
        info_panel_layout.addWidget(self.system_id_value_field)
        system_name_label = NameLabel('name:')
        system_name_label.setStyleSheet('font-weight: bold')
        info_panel_layout.addWidget(system_name_label)
        self.system_name_value_label = ValueLabel(
                            'Drag/Drop an Optical System here ...', w=320)
        info_panel_layout.addWidget(self.system_name_value_label)
        self.system_name_value_label = ValueLabel('No System Loaded', w=200)
        name_placeholder = PGXN_PLACEHOLDERS.get('name', '')
        self.system_name_value_field = StringFieldWidget(value='', width=200,
                                    placeholder=name_placeholder, parent=self)
        self.system_name_value_field.setVisible(False)
        info_panel_layout.addWidget(self.system_name_value_field)
        system_owner_label = NameLabel('owner:')
        system_owner_label.setStyleSheet('font-weight: bold')
        info_panel_layout.addWidget(system_owner_label)
        self.system_owner_value_label = ValueLabel('', w=320)
        info_panel_layout.addWidget(self.system_owner_value_label)
        self.system_owner_value_label = ValueLabel('No Owner Specified', w=200)
        owner_placeholder = PGXN_PLACEHOLDERS.get('owner', '')
        self.system_owner_value_field = StringFieldWidget(value='', width=200,
                                    placeholder=name_placeholder, parent=self)
        self.system_owner_value_field.setVisible(False)
        info_panel_layout.addWidget(self.system_owner_value_field)
        info_panel_layout.addStretch(1)
        self.new_system_button = SizedButton("Define New System")
        info_panel_layout.addWidget(self.new_system_button)
        self.new_system_button.clicked.connect(self.define_new_system)
        self.error_budget_button = SizedButton("Create Error Budget")
        info_panel_layout.addWidget(self.error_budget_button)
        self.setLayout(frame_vbox)
        frame_vbox.addLayout(info_panel_layout)
        self.setMinimumWidth(600)
        self.setMaximumHeight(150)
        self.system = system
        if not self.system and state.get('optical_system'):
            self.system = orb.get(state['optical_system'])

    # property: system

    def _get_system(self):
        return getattr(self, '_system', None)

    def _set_system(self, obj):
        orb.log.debug('* OpticalSysInfoPanel: _set_system')
        product_type = getattr(obj, 'product_type', None) or None
        if product_type:
            orb.log.debug(f'  - obj product type: {product_type.oid}')
        else:
            orb.log.debug('  - obj product type: None')
        optical_system = orb.get('pgefobjects:ProductType.optical_system')
        orb.log.debug(f'  - optical system product type: {optical_system}')
        if product_type and (product_type is optical_system):
            self._system = obj
        else:
            orb.log.debug('  - not an Optical System -- ignored.')
        if not self._system:
            # set widgets to disabled state
            self.title.setText('No System Loaded')
            self.system_id_value_label.setText('No System Loaded')
            self.system_id_value_label.setEnabled(False)
            self.system_name_value_label.setText(
                                'Drag/Drop an Optical System here ...')
            self.system_name_value_label.setEnabled(False)
            return
        self.title.setText(obj.name)
        self.system_id_value_label.setText(obj.id)
        self.system_name_value_label.setText(obj.name)
        self.system_id_value_label.setEnabled(True)
        self.system_name_value_label.setEnabled(True)
        state['optical_system'] = obj.oid

    system = property(fget=_get_system, fset=_set_system)

    def define_new_system(self):
        pass

    def supportedDropActions(self):
        return Qt.CopyAction

    def mimeTypes(self):
        # TODO:  should return mime types for Product and *ALL* subclasses
        return ["application/x-pgef-hardware-product",
                "application/x-pgef-template"]

    def dragEnterEvent(self, event):
        if (event.mimeData().hasFormat(
                        "application/x-pgef-hardware-product") or
            event.mimeData().hasFormat(
                        "application/x-pgef-template")):
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        orb.log.debug("* OpticalSysInfoPanel: hm, something dropped on me ...")
        if event.mimeData().hasFormat(
                                "application/x-pgef-hardware-product"):
            data = extract_mime_data(event,
                                     "application/x-pgef-hardware-product")
            icon, p_oid, p_id, p_name, p_cname = data
            system = orb.get(p_oid)
            if system:
                self.system = system
            else:
                event.ignore()
                orb.log.debug("* drop event: ignoring oid '%s' -- "
                              "not found in db." % p_oid)
        elif event.mimeData().hasFormat("application/x-pgef-template"):
            # drop item is Template -> create a new system from it
            data = extract_mime_data(event, "application/x-pgef-template")
            icon, t_oid, t_id, t_name, t_cname = data
            template = orb.get(t_oid)
            system = create_product_from_template(template)
            # NOTE: the below stuff is unnecessary, I think
            # if system.components:
                # orb.save(system.components)
                # for acu in system.components:
                    # dispatcher.send('new object', obj=acu)
            dispatcher.send("drop on system info", obj=system)
            dispatcher.send('new object', obj=system)
        else:
            event.ignore()


class OpticalSystemWidget(QWidget):
    def __init__(self, system=None, parent=None):
        super().__init__(parent=parent)
        orb.log.debug(' - initializing OpticalSystemWidget ...')
        self.system = system
        self.info_panel = OpticalSysInfoPanel(self.system)
        self.init_toolbar()
        self.scene = self.set_new_scene()
        self.view = OpticalSystemView(self)
        self.update_view()
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.info_panel)
        self.layout.addWidget(self.toolbar)
        self.layout.addWidget(self.view)
        self.setLayout(self.layout)
        self.sceneScaleChanged("70%")
        dispatcher.connect(self.delete_component, "remove component")
        # dispatcher.connect(self.on_component_edited, 'component edited')
        dispatcher.connect(self.on_rescale_optical_path, "rescale optical_path")
        self.setUpdatesEnabled(True)

    def init_toolbar(self):
        self.toolbar = QToolBar(parent=self)
        self.toolbar.setObjectName('ActionsToolBar')
        self.scene_scales = ["25%", "30%", "40%", "50%", "60%", "70%", "80%"]
        self.scene_scale_select = QComboBox()
        self.scene_scale_select.addItems(self.scene_scales)
        self.scene_scale_select.setCurrentIndex(5)
        self.scene_scale_select.currentIndexChanged[str].connect(
                                                    self.sceneScaleChanged)
        self.toolbar.addWidget(self.scene_scale_select)

    def set_title(self):
        sys_name = getattr(self.system, 'name', 'No System Loaded')
        sys_name = sys_name or 'No System Loaded'
        self.info_panel.title.setText(sys_name)

    def set_new_scene(self):
        """
        Return a new scene with new system or an empty scene if no system.
        """
        orb.log.debug(' - set_new_scene ...')
        scene = OpticalSystemScene(system=self.system, parent=self)
        # TODO:  replace this with a sort function ...
        acus = getattr(self.system, 'components', []) or []
        if acus:
            acus.sort(lambda x: get_dval(x.oid, 'position_in_optical_path'))
            item_list=[]
            for acu in acus:
                item = OpticalComponentBlock(usage=acu)
                item_list.append(item)
                scene.addItem(item)
            scene.diagram.populate(item_list)
        self.set_title()
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
        self.create_library()
        self.init_toolbar()
        self.set_widgets(init=True)
        dispatcher.connect(self.double_clicked_handler, "double clicked")

    def create_library(self):
        """
        Create the library of optical component block types.
        """
        pass

    def set_widgets(self, init=False):
        """
        Populate the OpticalSystemModeler with an OpticalSystemWidget and a
        SystemInfoTable.

        Note that clicking on a component in the OpticalSystemWidget will
        select that component in the SystemInfoTable.
        """
        orb.log.debug(' - set_widgets() ...')
        self.system_widget = OpticalSystemWidget(system=self.system,
                                                 parent=self)
        self.system_widget.setMinimumSize(900, 250)
        view = ['Optical Surface Label',
                'Optical Surface Description',
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
        self.system_table.setSizePolicy(QSizePolicy.Expanding,
                                        QSizePolicy.Expanding)
        self.system_table_panel = QWidget()
        self.system_table_panel.setMinimumSize(1200, 600)
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
    orb.start(home='/home/waterbug/cattens_home_dev', debug=True, console=True)
    app = QApplication(sys.argv)
    mw = OpticalSystemModeler()
    mw.show()
    sys.exit(app.exec_())

