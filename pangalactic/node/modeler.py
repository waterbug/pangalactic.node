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

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import (QAction, QComboBox, QDockWidget, QHBoxLayout,
                             QLayout, QMainWindow, QSizePolicy, QVBoxLayout,
                             QWidget)
from PyQt5.QtGui import QIcon, QTransform

# pangalactic
from pangalactic.core             import diagramz, state
from pangalactic.core.parametrics import componentz
from pangalactic.core.uberorb     import orb
from pangalactic.core.utils.meta  import (asciify, get_block_model_id,
                                             get_block_model_name,
                                             get_block_model_file_name)
from pangalactic.node.dialogs     import Viewer3DDialog
from pangalactic.node.diagrams    import DiagramView, DocForm
from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.utils       import (clone, extract_mime_data,
                                          get_object_title)
from pangalactic.node.widgets     import NameLabel, PlaceHolder, ValueLabel

supported_model_types = {
    # CAD models get "eyes" icon, not a lable button
    'step:203' : None,
    'step:214' : None,
    'pgefobjects:Block' : 'Block',
    'pgefobjects:ConOps' : 'Con Ops'}

# a named tuple used in managing the "history" of the ModelWindow so that it
# can be navigated
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


class ModelWindow(QMainWindow):
    """
    Main window for displaying models and their metadata.

    Attrs:
        model_files (dict):  maps model "types" (for now just "CAD" and
            "Block") to paths of associated files in vault
        idx (QModelIndex):  index in the system tree's proxy model
            corresponding to the object being modeled
        history (list):  list of previous ModelerState instances
    """
    def __init__(self, obj=None, scene=None, logo=None, idx=None,
                 external=False, preferred_size=None, parent=None):
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
        super(ModelWindow, self).__init__(parent=parent)
        orb.log.info('* ModelWindow initializing with:')
        orb.log.info('  obj "{}"'.format(getattr(obj, 'oid', 'None')))
        self.logo = logo
        self.external = external
        self.idx = idx
        self.preferred_size = preferred_size
        self.model_files = {}
        self.history = []
        # NOTE: this set_subject() call serves only to create the diagram_view,
        # which is needed by _init_ui(); the final set_subject() actually sets
        # the subject to the currently selected object
        self.set_subject(obj=obj)
        self._init_ui()
        self.setSizePolicy(QSizePolicy.Expanding,
                           QSizePolicy.Expanding)
        dispatcher.connect(self.set_subject_from_node, 'sys node selected')
        dispatcher.connect(self.set_subject_from_node, 'dash node selected')
        dispatcher.connect(self.set_subject_from_diagram_drill_down,
                           'diagram object drill down')
        dispatcher.connect(self.save_diagram_connector,
                           'diagram connector added')
        self.set_subject(obj=obj)

    def sizeHint(self):
        if self.preferred_size:
            return QSize(*self.preferred_size)
        return QSize(400, 400)

    def _init_ui(self):
        orb.log.debug('  - _init_ui() ...')
        # set a placeholder for the central widget
        self.set_placeholder()
        self.init_toolbar()
        self.setCorner(Qt.TopLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.TopRightCorner, Qt.RightDockWidgetArea)
        self.top_dock_widget = QDockWidget()
        self.top_dock_widget.setAllowedAreas(Qt.TopDockWidgetArea)
        self.top_dock_widget.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.subject_info_panel = SubjectInfoPanel(parent=self)
        self.top_dock_widget.setWidget(self.subject_info_panel)
        self.subject_info_panel.set_subject_info(self.obj)
        self.addDockWidget(Qt.TopDockWidgetArea, self.top_dock_widget)
        # Initialize a statusbar for the window
        self.statusbar = self.statusBar()
        # self.statusbar.showMessage("Models, woo!")

    def sceneScaleChanged(self, percentscale):
        newscale = float(percentscale[:-1]) / 100.0
        self.diagram_view.setTransform(QTransform().scale(newscale, newscale))

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
        # self.toolbar.addAction(self.diagram_view.scene().print_action)
        self.print_action = self.create_action("print",
                                               slot=self.print_preview,
                                               icon="printer",
                                               tip="Save as Image / Print")
        self.toolbar.addAction(self.print_action)

    def create_action(self, text, slot=None, icon=None, tip=None,
                      checkable=False):
        action = QAction(text, self)
        if icon is not None:
            icon_file = icon + state['icon_type']
            icon_path = os.path.join(orb.icon_dir, icon_file)
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
        form = DocForm(scene=self.diagram_view.scene(), edit_mode=False,
                       parent=self)
        form.show()

    def set_placeholder(self):
        new_placeholder = PlaceHolder(image=self.logo, min_size=200,
                                      parent=self)
        new_placeholder.setSizePolicy(QSizePolicy.Preferred,
                                      QSizePolicy.Preferred)
        self.setCentralWidget(new_placeholder)
        if getattr(self, 'placeholder', None):
            self.placeholder.close()
        self.placeholder = new_placeholder

    def display_external_window(self):
        orb.log.info('* ModelWindow.display_external_window() ...')
        mw = ModelWindow(obj=self.obj, scene=self.diagram_view.scene(),
                         logo=self.logo, external=True,
                         preferred_size=(700, 800), parent=self.parent())
        mw.show()

    def set_new_diagram_view(self):
        new_diagram_view = DiagramView(self.obj, embedded=True)
        new_diagram_view.setSizePolicy(QSizePolicy.Preferred,
                                       QSizePolicy.Preferred)
        layout = QVBoxLayout()
        layout.addWidget(new_diagram_view)
        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)
        if getattr(self, 'diagram_view', None):
            try:
                self.diagram_view.setAttribute(Qt.DeleteOnClose)
                self.diagram_view.parent = None
                self.diagram_view.close()
            except:
                # hmm, my C++ object was already deleted
                pass
        self.diagram_view = new_diagram_view
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
        orb.log.info('* ModelWindow.set_subject()')
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
                orb.log.info('* ModelWindow: checking for models ...')
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
                orb.log.info('* ModelWindow: obj is not Modelable, ignoring')
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
            for oid, fpath in list(self.model_files.items()):
                model = orb.get(oid)
                if getattr(model.type_of_model, 'oid', None) in ['step:203',
                                                                 'step:214']:
                    self.models_by_label['CAD'] = (model, fpath)
                    if hasattr(self, 'view_cad_action'):
                        self.view_cad_action.setVisible(True)
        if hasattr(self, 'subject_info_panel'):
            self.subject_info_panel.set_subject_info(self.obj)
        if self.history:
            if hasattr(self, 'back_action'):
                self.back_action.setEnabled(True)
        else:
            if hasattr(self, 'back_action'):
                self.back_action.setEnabled(False)
        self.cache_block_model()
        self.diagram_view.verticalScrollBar().setValue(0)
        self.diagram_view.horizontalScrollBar().setValue(0)

    def display_cad_model(self):
        try:
            model, fpath = self.models_by_label.get('CAD')
            if fpath:
                orb.log.info('* ModelWindow.display_cad_model({})'.format(
                                                                    fpath))
                viewer = Viewer3DDialog(self)
                viewer.show()
                viewer.view_cad(fpath)
        except:
            orb.log.info('  CAD model not found.')

    def display_block_diagram(self):
        """
        Display a block diagram for the current object.
        """
        orb.log.info('* Modeler:  display_block_diagram()')
        if not getattr(self, 'obj', None):
            orb.log.info('  no object selected.')
            return
        self.set_new_diagram_view()
        scene = self.diagram_view.scene()
        model = diagramz.get(self.obj.oid)
        objs = []
        if hasattr(self.obj, 'components') and componentz.get(self.obj.oid):
            # self.obj is a Product -- use componentz cache (more efficient
            # than using obj.components ...
            oids = [c[0] for c in componentz[self.obj.oid]]
            objs = orb.get(oids=oids)
        elif hasattr(self.obj, 'systems') and len(self.obj.systems):
            # self.obj is a Project
            objs = [psu.system for psu in self.obj.systems]
        if model and not model.get('dirty'):
            orb.log.info('  - restoring saved block diagram ...')
            scene.restore_diagram(model, objs)
        else:
            if model and model.get('dirty'):
                orb.log.info('  - block diagram found needed redrawing,')
            elif not model:
                orb.log.info('  - no block diagram found in cache or files ')
            orb.log.info('    generating new block diagram ...')
            # orb.log.info('  - generating diagram (cache disabled for testing)')
            scene.create_ibd(objs)
            # create a block Model object if self.obj doesn't have one
            block_model_type = orb.get(BLOCK_OID)
            if self.obj.has_models:
                block_models = [m for m in self.obj.has_models
                    if getattr(m, 'type_of_model', None) == block_model_type]
                if not block_models:
                    model_id = get_block_model_id(self.obj)
                    model_name = get_block_model_name(self.obj)
                    self.model = clone('Model', id=model_id, name=model_name,
                                       type_of_model=block_model_type,
                                       of_thing=self.obj)

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
        # NOTE:  do not write to a file -- orb._save_diagramz() does that
        # TODO: also send the serialized "model" to vger to be saved there ...
        # TODO: need to define a Model, Representation, and RepresentationFile
        try:
            scene = self.diagram_view.scene()
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
            orb.log.info('* ModelWindow: creating new Model for '
                         'Product with id "%s"' % self.obj.id)
            owner = orb.get(state.get('project'))
            new_model = clone('Model', owner=owner, of_thing=self.obj)
            dlg = PgxnObject(new_model, edit_mode=True, parent=self)
            # dialog.show() -> non-modal dialog
            dlg.show()


class SubjectInfoPanel(QWidget):

    def __init__(self, parent=None):
        super(SubjectInfoPanel, self).__init__(parent)
        orb.log.info('* SubjectInfoPanel initializing ...')
        # model info panel
        subject_info_layout = QVBoxLayout()
        subject_info_layout.setAlignment(Qt.AlignLeft)
        self.subject_info_title = NameLabel('<h3>No Models</h3>')
        self.subject_info_title.setSizePolicy(QSizePolicy.Preferred,
                                            QSizePolicy.Preferred)
        subject_info_layout.addWidget(self.subject_info_title)
        self.setLayout(subject_info_layout)
        self.setMaximumHeight(120)
        # self.setSizePolicy(QSizePolicy.MinimumExpanding,
                           # QSizePolicy.Preferred)
        self.setSizePolicy(QSizePolicy.Preferred,
                           QSizePolicy.Preferred)

    def set_subject_info(self, obj):
        """
        Set model subject title and model buttons in the subject info panel.

        Args:
            obj (Modelable):  the current subject (modeled object)
        """
        orb.log.info('* SubjectInfoPanel: set_subject_info')
        if obj:
            title_text = get_object_title(obj)
        else:
            title_text = '<h3>No Models</h3>'
        self.subject_info_title.setText(title_text)


class ProductInfoPanel(QWidget):

    def __init__(self, parent=None):
        super(ProductInfoPanel, self).__init__(parent)
        orb.log.info('* ProductInfoPanel initializing ...')
        self.setAcceptDrops(True)
        # product frame
        product_frame_vbox = QVBoxLayout()
        product_frame_vbox.setAlignment(Qt.AlignLeft|Qt.AlignTop)
        product_frame_vbox.setSizeConstraint(QLayout.SetMinimumSize)
        title = NameLabel('Product')
        title.setStyleSheet('font-weight: bold; font-size: 18px')
        product_frame_vbox.addWidget(title)
        # product_info_layout = QGridLayout()
        product_info_layout = QHBoxLayout()
        product_info_layout.setAlignment(Qt.AlignLeft|Qt.AlignTop)
        product_id_label = NameLabel('id:')
        product_id_label.setStyleSheet('font-weight: bold')
        # product_info_layout.addWidget(product_id_label, 0, 0)
        product_info_layout.addWidget(product_id_label)
        self.product_id_value_label = ValueLabel('No Product Selected', w=200)
        # product_info_layout.addWidget(self.product_id_value_label, 0, 1)
        product_info_layout.addWidget(self.product_id_value_label)
        product_name_label = NameLabel('name:')
        product_name_label.setStyleSheet('font-weight: bold')
        # product_info_layout.addWidget(product_name_label, 0, 2)
        product_info_layout.addWidget(product_name_label)
        self.product_name_value_label = ValueLabel(
                                'Drag/Drop a Product from Library ...', w=320)
        # product_info_layout.addWidget(self.product_name_value_label, 0, 3)
        product_info_layout.addWidget(self.product_name_value_label)
        product_version_label = NameLabel('version:')
        product_version_label.setStyleSheet('font-weight: bold')
        # product_info_layout.addWidget(product_version_label, 0, 4)
        product_info_layout.addWidget(product_version_label)
        self.product_version_value_label = ValueLabel('', w=150)
        # product_info_layout.addWidget(self.product_version_value_label, 0, 5)
        product_info_layout.addWidget(self.product_version_value_label)
        self.setLayout(product_frame_vbox)
        product_frame_vbox.addLayout(product_info_layout)
        self.setMinimumWidth(600)
        self.setMaximumHeight(150)
        # subscribe to the 'set current product' signal, which is sent by
        # pangalaxian.Main.set_product()
        self.set_product(product=orb.get(state.get('product')))
        dispatcher.connect(self.on_update, 'update product modeler')

    def on_update(self, obj=None):
        if obj:
            self.set_product(obj)

    def supportedDropActions(self):
        return Qt.CopyAction

    def mimeTypes(self):
        # TODO:  should return mime types for Product and *ALL* subclasses
        return ['application/x-pgef-hardware-product']

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(
                                "application/x-pgef-hardware-product"):
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasFormat(
                                "application/x-pgef-hardware-product"):
            # if the dropped object is not a HardwareProduct, the
            # drop event is ignored
            data = extract_mime_data(event,
                                     "application/x-pgef-hardware-product")
            icon, p_oid, p_id, p_name, p_cname = data
            product = orb.get(p_oid)
            if product:
                dispatcher.send("drop on product info", p=product)
            else:
                event.ignore()
                orb.log.info("* product drop event: ignoring oid '%s' -- "
                             "not found in db." % p_oid)
        else:
            event.ignore()

    def set_product(self, product=None):
        """
        Set a product in the modeler context.
        """
        orb.log.info('* ProductInfoPanel: set_product')
        # product_oid = state.get('product')
        # product = orb.get(product_oid)
        if product:
            # if not a HardwareProduct, product is ignored
            if product.__class__.__name__ != 'HardwareProduct':
                orb.log.info('  - not a HardwareProduct -- ignored.')
                return
            orb.log.info('  - oid: %s' % product.oid)
            self.product_id_value_label.setText(product.id)
            self.product_name_value_label.setText(product.name)
            if hasattr(product, 'version'):
                self.product_version_value_label.setText(getattr(product,
                                                              'version'))
            self.product_id_value_label.setEnabled(True)
            self.product_name_value_label.setEnabled(True)
            self.product_version_value_label.setEnabled(True)
        else:
            orb.log.info('  - None')
            # set widgets to disabled state
            self.product_id_value_label.setEnabled(False)
            self.product_name_value_label.setEnabled(False)
            self.product_version_value_label.setEnabled(False)

