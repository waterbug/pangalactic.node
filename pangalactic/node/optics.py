"""
A tool for computing the error budget of an optical system.

This tool obtains data from the Linear Optical Model (LOM), which is a Matlab
application that defines the optical surfaces and sensitivities of an optical
system.

The LOM data structure can be saved to a ".mat" file which can be read using
the scipy.io.loadmat() function.  For now, this is done on the server side
(pangalactic.vger) because of possible difficulties in packaging scipy for
desktop releases.
"""
#!/usr/bin/env python

import os, sys

from louie import dispatcher

from PyQt5.QtCore import pyqtSignal, Qt, QObject, QPointF, QPoint
from PyQt5.QtWidgets import (QAction, QApplication, QComboBox, QDockWidget,
                             QFileDialog, QMainWindow, QWidget, QGraphicsItem,
                             QGraphicsPolygonItem, QGraphicsScene,
                             QGraphicsView, QHBoxLayout, QMenu, QMessageBox,
                             QGraphicsPathItem, QSizePolicy, QToolBar,
                             QVBoxLayout, QWidgetAction)
# from PyQt5.QtWidgets import (QMessageBox, QStatusBar, QToolBox,
from PyQt5.QtGui import (QFont, QIcon, QCursor, QPainterPath, QPolygonF,
                         QTransform)
# from PyQt5.QtGui import QGraphicsProxyWidget

# pangalactic
from pangalactic.core             import state
from pangalactic.core.access      import get_perms
from pangalactic.core.clone       import clone
from pangalactic.core.meta        import PGXN_PLACEHOLDERS
from pangalactic.core.names       import (get_acu_id, get_acu_name,
                                          get_next_ref_des)
from pangalactic.core.parametrics import get_dval, set_dval
# from pangalactic.core.parametrics import get_pval
from pangalactic.core.errbudget   import gen_error_budget
from pangalactic.core.uberorb     import orb
from pangalactic.core.utils.datetimes import date2str, dtstamp
from pangalactic.core.validation  import get_bom_oids
from pangalactic.node.buttons     import SizedButton
from pangalactic.node.diagrams.shapes import BlockLabel, TextItem
from pangalactic.node.libraries   import LibraryDialog
from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.tableviews  import SystemInfoTable
from pangalactic.node.utils       import extract_mime_data
from pangalactic.node.widgets     import NameLabel, StringFieldWidget, ValueLabel


# -----------------------------------------------------------------------------
# LOM API
#
# These functions are being implemented on the server side -- this will change
# to an rpc-based API
# -----------------------------------------------------------------------------

# from scipy.io import loadmat

# def get_lom_data(fpath):
    # """
    # Read a LOM data set from a .mat file.

    # Args:
        # fpath (str): path to the .mat file
    # """
    # return loadmat(fpath, simplify_cells=True)

# def get_optical_surface_names(data):
    # """
    # Get the names of all surfaces in a LOM data set.

    # Args:
        # data (dict): LOM data set read from .mat file
    # """
    # return list(data["lomdata"]["SURFACES"])

# def get_LOM(data):
    # """
    # Get the LOM data as a list of dicts, one for each surface, with the
    # following keys:

        # ['surfacelabel', 'rdy', 'rdx', 'thi', 'map', 'mav', 'ape', 'k',
        # 'surfacetype', 'coefs_note', 'coefs_vals', 'glass', 'rindex',
        # 'refractmode', 'decenter_type', 'decenter_vals', 'return_surf',
        # 'refrays', 'globalcoord_ref', 'globalcoord_xyz', 'globalcoord_abc',
        # 'globalcoord_abc_note', 'globalcoord_ROT', 'dRR_dRBM', 'dFIR_dRBM',
        # 'dWFE_dRBM', 'MASK_dRBM', 'dRR_dRK', 'dFIR_dRK', 'dWFE_dRK',
        # 'MASK_dRK', 'dRR_dZFE', 'dFIR_dZFE', 'dWFE_dZFE', 'MASK_dZFE', 'Sag_m',
        # 'Sag_mask', 'Sag_xy', 'dSag_dZFE_m']

    # Args:
        # data (dict): LOM data set read from .mat file
    # """
    # return list(data["lomdata"]["LOM"])

# --------------------------------------------------------------------------
# END OF LOM API
# --------------------------------------------------------------------------


class OpticalComponentBlock(QGraphicsPolygonItem):

    def __init__(self, usage=None, scene=None, style=None, parent=None):
        """
        Initialize Optical Component Block.

        Keyword Args:
            usage (Acu):  optical component usage that the block
                represents
            scene (QGraphicsScene):  scene containing this item
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
        self.scene = scene
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
                    QPointF(0, 50), QPointF(1, 50),
                    QPointF(1, -50), QPointF(0, -50)
            ])
        else:
            # generic optical component
            self.myPolygon = QPolygonF([
                    QPointF(-10, 50), QPointF(10, 50),
                    QPointF(10, -50), QPointF(-10, -50)
            ])
        self.setPolygon(self.myPolygon)
        label_txt = getattr(self.usage, 'reference_designator', '') or ''
        self.block_label = BlockLabel(label_txt, self, y=-100, centered=False)
        dispatcher.connect(self.on_component_edited, 'component edited')

    def on_component_edited(self, component=None):
        oid = getattr(component, 'oid', None)
        if oid == self.component.oid:
            self.block_label.set_text(getattr(self.component, 'name',
                                      'No Name') or 'No Name')

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        self.menu = QMenu()
        self.menu.addAction(self.delete_action)
        self.menu.addAction(self.edit_action)
        self.menu.exec(QCursor.pos())

    def create_actions(self):
        self.delete_action = QAction("Delete", self.scene,
                                     statusTip="Delete Component",
                                     triggered=self.delete_block_usage)
        self.edit_action = QAction("Edit", self.scene,
                                   statusTip="Edit component",
                                   triggered=self.edit_component)

    def edit_component(self):
        self.scene.edit_parameters(self.component)

    def delete_block_usage(self):
        """
        Delete the usage (Acu) associated with this block.
        """
        orb.log.debug('* calling scene to emit "delete_scene_usage" signal')
        self.scene.delete_scene_usage.emit(self.usage.oid)

    def itemChange(self, change, value):
        return value

    def mousePressEvent(self, event):
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)


class OpticalSystemScene(QGraphicsScene):

    des_set = pyqtSignal(dict)
    new_or_modified_objects = pyqtSignal(list)
    delete_scene_usage = pyqtSignal(str)
    rescale_optical_path = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.optical_path = OpticalPathDiagram(self)
        self.optical_path.signals.des_set.connect(self.on_des_set)
        self.addItem(self.optical_path)
        # NOTE: not clear if this is necessary
        # self.focusItemChanged.connect(self.focus_changed_handler)
        self.current_focus = None
        self.grabbed_item = None

    @property
    def system(self):
        return orb.get(state.get('optical_system', ''))

    def on_des_set(self, des):
        self.des_set.emit(des)

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
            self.optical_path.arrange()
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
            item = OpticalComponentBlock(usage=new_acu, scene=self)
            item.setPos(event.scenePos())
            self.addItem(item)
            self.optical_path.add_item(item)
            orb.save([new_acu, self.system])
            # orb.log.debug('      Acu created: {}'.format(
                          # new_acu.name))
            self.new_or_modified_objects.emit([new_acu.oid, self.system.oid])
            self.update()

    def edit_parameters(self, component):
        view = ['id', 'name', 'description']
        panels = ['main', 'parameters']
        pxo = PgxnObject(component, edit_mode=True, view=view,
                         panels=panels, modal_mode=True, parent=self.parent())
        pxo.show()

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)


class OpticalPathDiagramSignals(QObject):

    des_set = pyqtSignal(dict)
    order_changed = pyqtSignal()


class OpticalPathDiagram(QGraphicsPathItem):

    def __init__(self, scene, parent=None):
        super().__init__(parent)
        self.signals = OpticalPathDiagramSignals()
        self.scene = scene
        self.item_list = []
        self.path_length = 1000
        self.make_path()
        self.current_positions = []

    @property
    def system(self):
        return orb.get(state.get('optical_system', ''))

    def make_path(self):
        start_point = QPointF(100, 250)
        self.path = QPainterPath(start_point)
        self.path.addRect(0, 200, 100, 100)
        self.path.moveTo(100, 250)
        self.end_x = 100 + self.path_length
        self.path.lineTo(self.end_x, 250)
        self.path.addRect(self.end_x, 200, 100, 100)
        self.setPath(self.path)
        # TextItem automatically adds itself to the specified scene
        self.obj_text = TextItem("object", QPointF(10, 230), self.scene,
                                 font=QFont("Arial", 18))
        self.obj_text.setSelected(False)
        self.add_image_label()
        self.length = round(self.path.length() - 800)
        factor = self.length // (len(self.item_list) + 1)
        self.list_of_pos = [(n + 1) * factor + 100
                            for n in range(0, len(self.item_list))]

    def add_image_label(self):
        current_image_label = getattr(self, 'img_text', None)
        if current_image_label:
            self.scene.removeItem(current_image_label)
        self.img_text = TextItem("image", QPointF(self.end_x + 10, 230),
                                 self.scene, font=QFont("Arial", 18))
        self.img_text.setSelected(False)

    def remove_item(self, item):
        if item in self.item_list:
            self.item_list.remove(item)
        self.update_optical_path()

    def add_item(self, item):
        self.item_list.append(item)
        self.update_optical_path()

    def update_optical_path(self):
        self.calc_length()
        self.make_path()
        self.arrange()

    def calc_length(self):
        if len(self.item_list) <= 5:
            self.path_length = 1000
        else:
            # adjust optical_path length and rescale scene
            delta = len(self.item_list) - 5
            self.path_length = 1000 + (delta // 2) * 300
            scale = 70 - (delta // 2) * 10
            percentscale = str(scale) + "%"
            self.scene.rescale_optical_path.emit(percentscale)

    def populate(self, item_list):
        self.item_list = item_list
        self.update_optical_path()

    def arrange(self):
        """
        Arrange the component blocks to be evenly spaced on the optical path,
        and update their "position_in_optical_path" data element to reflect
        their updated position.
        """
        item_list_copy = self.item_list[:]
        self.item_list.sort(key=lambda x: x.scenePos().x())
        same = True
        table_needs_update = False
        for item in self.item_list:
            if self.item_list.index(item) != item_list_copy.index(item):
                same = False
        for i, item in enumerate(self.item_list):
            item.setPos(QPoint(self.list_of_pos[i], 250))
            set_dval(item.usage.oid, 'position_in_optical_path', i)
            self.scene.new_or_modified_objects.emit([item.usage.oid])
            table_needs_update = True
        if not same:
            des = {}
            for i, item in enumerate(self.item_list):
                item.setPos(QPoint(self.list_of_pos[i], 250))
                acu = item.usage
                set_dval(acu.oid, 'position_in_optical_path', i)
                des[acu.oid] = {}
                des[acu.oid]['position_in_optical_path'] = self.list_of_pos[i]
            # "des_set" triggers pgxn to call rpc vger.set_data_elements()
            self.signals.des_set.emit(des)
        if not same or table_needs_update:
            # "order_changed" triggers the system table to update
            self.signals.order_changed.emit()
        self.update()


class OpticalSysInfoPanel(QWidget):

    def __init__(self, system=None, parent=None):
        """
        Initialize OpticalSysInfoPanel.

        Keyword Args:
            system (Model): an optical system
            parent (QWidget): the parent widget
        """
        # TODO: make fields editable if "Define New System" is clicked
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
        self.title = NameLabel('No System Loaded', parent=self)
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
        name_placeholder = PGXN_PLACEHOLDERS.get('name', '')
        self.system_name_value_field = StringFieldWidget(value='', width=200,
                                            placeholder=name_placeholder,
                                            parent=self)
        self.system_name_value_field.setVisible(False)
        info_panel_layout.addWidget(self.system_name_value_field)
        system_owner_label = NameLabel('owner:')
        system_owner_label.setStyleSheet('font-weight: bold')
        info_panel_layout.addWidget(system_owner_label)
        self.system_owner_value_label = ValueLabel('', w=320)
        info_panel_layout.addWidget(self.system_owner_value_label)
        self.system_owner_value_label = ValueLabel('No Owner Specified', w=200)
        self.system_owner_value_field = StringFieldWidget(value='', width=200,
                                            placeholder=name_placeholder,
                                            parent=self)
        self.system_owner_value_field.setVisible(False)
        info_panel_layout.addWidget(self.system_owner_value_field)
        info_panel_layout.addStretch(1)
        # self.library_button = SizedButton("Library", color="green")
        # info_panel_layout.addWidget(self.library_button)
        # self.import_lom_button = SizedButton("Import LOM", color="blue")
        # info_panel_layout.addWidget(self.import_lom_button)
        # self.import_lom_button.clicked.connect(self.import_lom)
        self.error_budget_button = SizedButton("Create Error Budget")
        info_panel_layout.addWidget(self.error_budget_button)
        self.error_budget_button.clicked.connect(self.output_error_budget)
        frame_vbox.addLayout(info_panel_layout)
        self.setLayout(frame_vbox)
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
        self._system = obj
        product_type = getattr(obj, 'product_type', None) or None
        if product_type:
            # orb.log.debug(f'  - obj product type: {product_type.name}')
            optical_system = orb.get('pgefobjects:ProductType.optical_system')
            instrument = orb.get('pgefobjects:ProductType.instrument')
            if product_type in [instrument, optical_system]:
                # orb.log.debug('  - populating panel widgets ...')
                self.title.setText(obj.name)
                self.title.update()
                self.system_id_value_label.setEnabled(True)
                self.system_name_value_label.setEnabled(True)
                self.system_id_value_label.setText(obj.id)
                self.system_name_value_label.setText(obj.name)
                state['optical_system'] = obj.oid
            else:
                # orb.log.debug('  - not an Optical System -- ignored.')
                # set widgets to disabled state
                self.title.setText('No System Loaded')
                self.system_id_value_label.setText('No System Loaded')
                self.system_id_value_label.setEnabled(False)
                self.system_name_value_label.setText(
                                    'Drag/Drop an Optical System here ...')
                self.system_name_value_label.setEnabled(False)
        else:
            orb.log.debug('  - no product type, ignored')
            return

    system = property(fget=_get_system, fset=_set_system)

    # def import_lom(self):
        # """
        # Perform the following steps:
        # 1. identify or create a system with name, id, version, etc.
        # 2. identify or create a model w/ name, id, version, etc.
        # 3. dispatch signal that triggers an rpc that adds/updates those objects
        # and upload the associated .mat file
        # """
        # lom_model_type = orb.get('pgefobjects:ModelType.LOM')
        # dlg = ModelImportDialog(lom_model_type)
        # if dlg.exec_():
            # orb.log.info('* lom submitted ...')
        # else:
            # return

    # ------------------------------------------------------------------------
    # NOTE: implementing this on the server (vger) side, but saving this code
    # for now, just in case ...
    # ------------------------------------------------------------------------
    # def import_lom_system(self):
        # """
        # Import an optical system from a LOM (.mat) file.
        # """
        # orb.log.debug('* import_lom_system()')
        # data = None
        # sys_name = ''
        # message = ''
        # if not state.get('last_lom_path'):
            # state['last_lom_path'] = self.user_home
        # # NOTE: can add filter if needed, e.g.: filter="(*.yaml)"
        # dialog = QFileDialog(self, 'Open File', state['last_lom_path'],
                             # "(*.mat)")
        # fpath = ''
        # if dialog.exec_():
            # fpaths = dialog.selectedFiles()
            # if fpaths:
                # fpath = fpaths[0]
            # dialog.close()
        # if fpath:
            # orb.log.debug('  file path: {}'.format(fpath))
            # try:
                # data = get_lom_data(fpath)
                # fname = os.path.basename(fpath)
                # sys_name = fname.split('.')[0]
            # except:
                # message = "File '%s' could not be opened." % fpath
                # popup = QMessageBox(QMessageBox.Warning,
                            # "Error in file path", message,
                            # QMessageBox.Ok, self)
                # popup.show()
                # return
        # else:
            # # no file was selected
            # return
        # if data:
            # new_objs = []
            # surface_names = get_optical_surface_names(data)
            # comp_names = []
            # optics = orb.search_exact(cname='Discipline', name='Optics')
            # LOM = orb.get('pgefobjects:ModelType.Optics.LOM')
            # optical_component = orb.get(
                                  # 'pgefobjects:ProductType.optical_component')
            # if surface_names:
                # NOW = dtstamp()
                # user = orb.get(state.get('local_user_oid'))
                # if sys_name:
                    # # TODO: have a discussion about versioning etc. ... if
                    # # versioning is used, the search for existing items should
                    # # reference version(s), and versions should be added to any
                    # # new objects created from the data.
                    # opt_sys = orb.search_exact(cname='HardwareProduct',
                                               # name=sys_name)
                    # opt_sys_model = orb.search_exact(
                                        # cname='Model', name=sys_name,
                                        # of_thing=opt_sys,
                                        # model_definition_context=optics,
                                        # type_of_model=LOM)
                    # if opt_sys_model:
                        # self.system = opt_sys_model
                        # comp_names = [acu.component.name
                                      # for acu in opt_sys_model.components]
                    # else:
                        # # create a HardwareProduct and a Model representing the
                        # # system
                        # opt_sys = clone('HardwareProduct', id=sys_name,
                                        # name=sys_name, create_datetime=NOW,
                                        # mod_datetime=NOW, creator=user,
                                        # modifier=user)
                        # self.system = clone('Model', id=sys_name,
                                            # name=sys_name,
                                            # of_thing=opt_sys,
                                            # model_definition_context=optics,
                                            # type_of_model=LOM,
                                            # create_datetime=NOW,
                                            # mod_datetime=NOW, creator=user,
                                            # modifier=user)
                        # new_objs += [opt_sys, self.system]
                # for name in surface_names:
                    # if name not in comp_names:
                        # # create a HW product and Acu for each surface that is
                        # # not found among the system components ...
                        # opt_comp = clone('HardwareProduct', id=name, name=name,
                                         # product_type=optical_component,
                                         # create_datetime=NOW, mod_datetime=NOW,
                                         # creator=user, modifier=user)
                        # surface = clone('Model', id=name, name=name,
                                        # of_thing=opt_comp,
                                        # model_definition_context=optics,
                                        # type_of_model=LOM,
                                        # create_datetime=NOW, mod_datetime=NOW,
                                        # creator=user, modifier=user)
                        # new_objs.append(surface)
                        # # TODO: add id and name to each Acu
                        # hw_ref_des = get_next_ref_des(opt_sys, opt_comp)
                        # hw_acu_id = get_acu_id(opt_sys.id, hw_ref_des)
                        # hw_acu_name = get_acu_name(opt_sys.name, hw_ref_des)
                        # hw_usage = clone('Acu', assembly=opt_sys,
                                    # id=hw_acu_id, name=hw_acu_name,
                                    # reference_designator=hw_ref_des,
                                    # component=opt_comp, create_datetime=NOW,
                                    # mod_datetime=NOW, creator=user,
                                    # modifier=user)
                        # model_ref_des = get_next_ref_des(self.system, surface)
                        # model_acu_id = get_acu_id(self.system.id, hw_ref_des)
                        # model_acu_name = get_acu_name(self.system.name,
                                                      # hw_ref_des)
                        # model_usage = clone('Acu', assembly=self.system,
                                        # id=model_acu_id, name=model_acu_name,
                                        # reference_designator=model_ref_des,
                                        # component=surface, create_datetime=NOW,
                                        # mod_datetime=NOW, creator=user,
                                        # modifier=user)
                        # new_objs += [hw_usage, model_usage]
                # if new_objs:
                    # orb.save(new_objs)
                    # dispatcher.send(signal="new objects", objs=new_objs)
            # else:
                # orb.log.debug('  no surface names were found.')
        # else:
            # orb.log.debug('  no data was found.')

    def output_error_budget(self):
        dtstr = date2str(dtstamp())
        if not state.get('last_eb_path'):
            state['last_eb_path'] = orb.home
        suggest_fname = os.path.join(
                          state['last_eb_path'],
                          'Error_Budget_' + dtstr + '.xlsx')
        fpath, _ = QFileDialog.getSaveFileName(
                        self, 'Save to File', suggest_fname,
                        "Excel Files (*.xlsx)")
        if fpath:
            gen_error_budget(self.system, file_path=fpath)
            orb.log.debug('  file saved.')
            # try to start Excel with file if on Win or Mac ...
            if sys.platform == 'win32':
                try:
                    os.system(f'start excel.exe "{fpath}"')
                except:
                    orb.log.debug('  could not start Excel')
            elif sys.platform == 'darwin':
                try:
                    cmd = f'open -a "Microsoft Excel.app" "{fpath}"'
                    os.system(cmd)
                except:
                    orb.log.debug('  unable to start Excel')

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
            if (system and
                getattr(system.product_type, 'id', '') in [
                                            'optical_system', 'instrument']):
                # triggers "_set_system()"
                self.system = system
            else:
                event.ignore()
                orb.log.debug("* drop event: ignoring -- "
                              "not found in db or incorrect product type.")
        # TODO: maybe support Templates later ...
        # elif event.mimeData().hasFormat("application/x-pgef-template"):
            # # drop item is Template -> create a new system from it
            # data = extract_mime_data(event, "application/x-pgef-template")
            # icon, t_oid, t_id, t_name, t_cname = data
            # template = orb.get(t_oid)
            # system = create_product_from_template(template)
            # # NOTE: the below stuff is unnecessary, I think
            # # if system.components:
                # # orb.save(system.components)
                # # for acu in system.components:
                    # # dispatcher.send('new object', obj=acu)
            # dispatcher.send("drop on system info", obj=system)
            # dispatcher.send('new object', obj=system)
        else:
            event.ignore()


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


class OpticalSystemWidget(QWidget):

    new_or_modified_objects = pyqtSignal(list)
    object_deleted = pyqtSignal(str, str)  # args: oid, cname

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        orb.log.debug('* initializing OpticalSystemWidget ...')
        self.info_panel = OpticalSysInfoPanel(self.system)
        # self.library_button = self.info_panel.library_button
        self.init_toolbar()
        self.set_scene_and_view()
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.info_panel)
        self.layout.addWidget(self.toolbar)
        self.layout.addWidget(self.view)
        self.setLayout(self.layout)
        self.scene_scale_changed("70%")
        dispatcher.connect(self.on_rescale_optical_path,
                           "rescale optical path")
        self.scene.rescale_optical_path.connect(self.on_rescale_optical_path)
        self.setUpdatesEnabled(True)

    @property
    def system(self):
        return orb.get(state.get('optical_system', ''))

    def init_toolbar(self):
        self.toolbar = QToolBar(parent=self)
        self.toolbar.setObjectName('ActionsToolBar')
        self.scene_scales = ["25%", "30%", "40%", "50%", "60%", "70%", "80%"]
        self.scene_scale_select = QComboBox()
        self.scene_scale_select.addItems(self.scene_scales)
        self.scene_scale_select.setCurrentIndex(5)
        self.scene_scale_select.currentIndexChanged[str].connect(
                                                    self.scene_scale_changed)
        self.toolbar.addWidget(self.scene_scale_select)

    def set_scene_and_view(self):
        """
        Return a new scene with new system or an empty scene if no system.
        """
        orb.log.debug(' - set_scene_and_view() ...')
        scene = OpticalSystemScene(parent=self)
        # TODO:  replace this with a sort function ...
        acus = getattr(self.system, 'components', []) or []
        if acus:
            acus.sort(key=lambda x:
                      get_dval(x.oid, 'position_in_optical_path'))
            item_list=[]
            for acu in acus:
                item = OpticalComponentBlock(usage=acu, scene=scene)
                item_list.append(item)
                scene.addItem(item)
            scene.optical_path.populate(item_list)
        scene.update()
        # signal from local (graphical) item deletion
        scene.delete_scene_usage.connect(self.delete_usage)
        scene.new_or_modified_objects.connect(self.on_new_or_modified_objects)
        self.scene = scene
        if not getattr(self, 'view', None):
            self.view = OpticalSystemView(self)
        self.view.setScene(self.scene)
        self.view.show()

    def on_new_or_modified_objects(self, oids):
        self.new_or_modified_objects.emit(oids)

    def show_empty_scene(self):
        """
        Return an empty scene.
        """
        scene = QGraphicsScene()
        return scene

    def remote_objects_deleted(self, oids):
        """
        Respond to remote deletions.

        Args:
            oids (list): oids of deleted objects.
        """
        for oid in oids:
            self.delete_usage(oid, remote=True)

    def delete_usage(self, oid, remote=False):
        """
        Delete a component usage (Acu)

        Args:
            oid (str): oid of the Acu to be deleted
        """
        acu = orb.get(oid)
        if not acu:
            # the acu does not exist in local db, so ignore
            return
        if acu not in getattr(self.system, 'components', []):
            # component is not in the current optical system, ignore
            return
        orb.delete([acu])
        self.set_scene_and_view()
        if not remote:
            self.object_deleted.emit(oid, "Acu")

    def scene_scale_changed(self, percentscale):
        newscale = float(percentscale[:-1]) / 100.0
        self.view.setTransform(QTransform().scale(newscale, newscale))

    def on_rescale_optical_path(self, percentscale):
        if percentscale in self.scene_scales:
            new_index = self.scene_scales.index(percentscale)
            self.scene_scale_select.setCurrentIndex(new_index)
        else:
            orb.log.debug(f'* rescale factor {percentscale} unavailable')

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
    Tool for modeling a system with optical properties.
    """

    new_or_modified_objects = pyqtSignal(list)
    local_object_deleted = pyqtSignal(str, str)  # args: oid, cname

    def __init__(self, system=None, parent=None):
        """
        Initialize the tool.

        Keyword Args:
            system (HardwareProduct): a system with optical properties
            parent (QWidget): parent widget
        """
        super().__init__(parent=parent)
        orb.log.info('* OpticalSystemModeler initializing')
        self.system = system
        self.init_toolbar()
        self.set_widgets(init=True)
        self.setWindowTitle('Optical System Modeler')
        sys_widget_w = self.system_widget.width()
        sys_widget_h = self.system_widget.height()
        sys_table_h = self.system_table.rowCount() * 20
        self.resize(sys_widget_w + 400,
                    sys_widget_h + sys_table_h + 200)
        # self.system_widget.library_button.clicked.connect(self.display_library)
        # dispatcher.connect(self.on_double_click, "double clicked")
        dispatcher.connect(self.construct_lom_visualization,
                           'got lom surface names')
        lom = None
        if getattr(system, 'has_models', None):
            for model in system.has_models:
                if getattr(model.type_of_model, 'id', '') == 'LOM':
                    # TODO: check for latest version of LOM
                    lom = model
        if lom:
            orb.log.info('  - found ref to LOM, getting surface names ...')
            dispatcher.send(signal='get lom surface names', lom_oid=lom.oid)
        else:
            orb.log.info('  - did not find ref to LOM.')

    def display_library(self):
        """
        Open dialog with library of instruments and optical product types.
        """
        optical_system = orb.select('ProductType', id='optical_system')
        optical_component = orb.select('ProductType', id='optical_component')
        instrument = orb.select('ProductType', id='instrument')
        lens = orb.select('ProductType', id='lens')
        mirror = orb.select('ProductType', id='mirror')
        pts = [instrument, optical_system, optical_component, lens, mirror]
        dlg = LibraryDialog('Model',
                            height=self.geometry().height(),
                            width=self.geometry().width() // 2,
                            parent=self)
        dlg.lib_view.only_mine_checkbox.setChecked(False)
        state['only_mine'] = False
        dlg.on_product_types_selected(objs=pts)
        dlg.show()

    def set_widgets(self, init=False):
        """
        Populate the OpticalSystemModeler with an OpticalSystemWidget and a
        SystemInfoTable.

        Note that clicking on a component in the OpticalSystemWidget will
        select that component in the SystemInfoTable.
        """
        orb.log.debug(' - set_widgets() ...')
        self.system_widget = OpticalSystemWidget(parent=self)
        self.system_widget.setMinimumSize(900, 400)
        self.system_widget.new_or_modified_objects.connect(
                                    self.on_new_or_modified_objects)
        self.system_widget.object_deleted.connect(self.on_local_object_deleted)
        self.system_widget.scene.optical_path.signals.order_changed.connect(
                                                    self.rebuild_system_table)
        self.system_table_panel = QWidget()
        self.system_table_panel.setMinimumSize(1200, 300)
        self.system_table_layout = QHBoxLayout()
        self.create_system_table()
        self.system_table_layout.addWidget(self.system_table)
        self.system_table_panel.setLayout(self.system_table_layout)
        self.setCentralWidget(self.system_table_panel)
        self.top_dock = QDockWidget()
        self.top_dock.setObjectName('TopDock')
        self.top_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.top_dock.setAllowedAreas(Qt.TopDockWidgetArea)
        self.addDockWidget(Qt.TopDockWidgetArea, self.top_dock)
        self.top_dock.setWidget(self.system_widget)

    def rebuild_system_table(self):
        if getattr(self, 'system_table', None):
            self.system_table_layout.removeWidget(self.system_table)
            self.system_table.parent = None
            self.system_table.close()
            self.system_table = None
        self.create_system_table()
        self.system_table_layout.addWidget(self.system_table)

    def create_system_table(self):
        view = [('reference_designator', 'Optical\nSurface\nLabel', 'usage'),
                ('name', 'Optical\nSurface\nName', 'component'),
                ('description', 'Optical\nSurface\nDescription', 'component'),
                ('dRMSWFE_dx', '', 'usage'),
                ('dRMSWFE_dy', '', 'usage'),
                ('dRMSWFE_dz', '', 'usage'),
                ('dRMSWFE_rx', '', 'usage'),
                ('dRMSWFE_ry', '', 'usage'),
                ('dRMSWFE_rz', '', 'usage'),
                ('dLOSx_dx', '', 'usage'),
                ('dLOSx_dy', '', 'usage'),
                ('dLOSx_dz', '', 'usage'),
                ('dLOSx_rx', '', 'usage'),
                ('dLOSx_ry', '', 'usage'),
                ('dLOSx_rz', '', 'usage'),
                ('dLOSy_dx', '', 'usage'),
                ('dLOSy_dy', '', 'usage'),
                ('dLOSy_dz', '', 'usage')]
                # 'RoC', 'K',
                # 'X_vertex', 'Y_vertex', 'Z_vertex',
                # 'RotX_vertex', 'RotY_vertex', 'RotZ_vertex',
        self.system_table = SystemInfoTable(
                                    system=self.system, view=view,
                                    sort_by_field='position_in_optical_path',
                                    sort_on='usage',
                                    parent=self)
        self.system_table.setSizePolicy(QSizePolicy.Expanding,
                                        QSizePolicy.Expanding)
        self.system_table.setAttribute(Qt.WA_DeleteOnClose)

    def construct_lom_visualization(self, surface_names=None):
        """
        Construct a LOM visualization from a set of LOM surfaces.

        Keyword Args:
            surface_names (list of str): surface names extracted from the LOM
        """
        orb.log.debug('* construct_lom_visualization()')
        orb.log.debug(f'  surface names: {surface_names}')
        new_objs = []
        opt_sys = self.system
        # optics = orb.search_exact(cname='Discipline', name='Optics')
        # LOM = orb.get('pgefobjects:ModelType.Optics.LOM')
        optical_component = orb.get(
                              'pgefobjects:ProductType.optical_component')
        if surface_names:
            NOW = dtstamp()
            user = orb.get(state.get('local_user_oid'))
            # HardwareProduct = orb.classes['HardwareProduct']
            # Acu = orb.classes['Acu']
            for name in surface_names:
                # create a Model and Acu for each surface
                opt_comp = clone('HardwareProduct', id=name, name=name,
                                 product_type=optical_component,
                                 create_datetime=NOW, mod_datetime=NOW,
                                 creator=user, modifier=user)
                # opt_comp = HardwareProduct(id=name, name=name,
                                 # product_type=optical_component,
                                 # create_datetime=NOW, mod_datetime=NOW,
                                 # creator=user, modifier=user)
                new_objs.append(opt_comp)
                # surface = clone('Model', id=name, name=name,
                                # model_definition_context=optics,
                                # type_of_model=LOM,
                                # create_datetime=NOW, mod_datetime=NOW,
                                # creator=user, modifier=user)
                # new_objs.append(surface)
                # TODO: add id and name to each Acu
                # surface_ref_des = get_next_ref_des(opt_sys, opt_comp)
                # surface_acu_id = get_acu_id(opt_sys.id, surface_ref_des)
                # surface_acu_name = get_acu_name(opt_sys.name, surface_ref_des)
                # surface_usage = Acu(assembly=opt_sys,
                            # id=surface_acu_id, name=surface_acu_name,
                            # reference_designator=surface_ref_des,
                            # component=opt_comp, create_datetime=NOW,
                            # mod_datetime=NOW, creator=user,
                            # modifier=user)
                surface_ref_des = get_next_ref_des(opt_sys, opt_comp)
                surface_acu_id = get_acu_id(opt_sys.id, surface_ref_des)
                surface_acu_name = get_acu_name(opt_sys.name,
                                                surface_ref_des)
                surface_usage = clone('Acu', assembly=opt_sys,
                            id=surface_acu_id, name=surface_acu_name,
                            reference_designator=surface_ref_des,
                            component=opt_comp, create_datetime=NOW,
                            mod_datetime=NOW, creator=user,
                            modifier=user)
                new_objs += [surface_usage]
                # model_ref_des = get_next_ref_des(self.model, surface)
                # model_acu_id = get_acu_id(self.model.id, hw_ref_des)
                # model_acu_name = get_acu_name(self.model.name,
                                              # hw_ref_des)
                # model_usage = clone('Acu', assembly=self.model,
                                # id=model_acu_id, name=model_acu_name,
                                # reference_designator=model_ref_des,
                                # component=surface, create_datetime=NOW,
                                # mod_datetime=NOW, creator=user,
                                # modifier=user)
                # new_objs += [model_usage]
            if new_objs:
                orb.save(new_objs)
                # dispatcher.send(signal="new objects", objs=new_objs)
                self.set_widgets()
                self.system_widget.set_scene_and_view()
        else:
            orb.log.debug('  no surface names were found.')

    def remote_objects_deleted(self, oids):
        """
        Respond to deletion of remote objects by calling scene to be updated.
        """
        if getattr(self, 'system_widget', None):
            self.system_widget.remote_objects_deleted(oids)

    def on_local_object_deleted(self, oid, cname):
        """
        Pass along the signal when an item is removed from the scene and its
        usage is deleted.
        """
        self.rebuild_system_table()
        self.local_object_deleted.emit(oid, cname)

    def on_new_or_modified_objects(self, oids):
        self.rebuild_system_table()
        self.new_or_modified_objects.emit(oids)

    def on_double_click(self, acu):
        # """
        # Handle a double-click event on a OpticalComponentBlock, creating and
        # displaying a new view.
        # Args:
            # obj (OpticalComponentBlock):  the block that received the
            #   double-click
        # """
        # self.component = acu
        # self.set_scene_and_view()
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
    # orb.start(home='junk_home', debug=True)
    orb.start(home='/home/waterbug/cattens_home_dev', debug=True, console=True)
    app = QApplication(sys.argv)
    mw = OpticalSystemModeler()
    mw.show()
    sys.exit(app.exec_())

