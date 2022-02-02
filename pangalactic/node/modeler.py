#!/usr/bin/env python
import os
from collections import namedtuple
from urllib.parse    import urlparse

from louie import dispatcher

from PyQt5.QtCore import Qt, QModelIndex, QSize
from PyQt5.QtWidgets import (QAction, QApplication, QComboBox, QHBoxLayout,
                             QLayout, QMainWindow, QPushButton, QSizePolicy,
                             QVBoxLayout, QWidget)
from PyQt5.QtGui import QIcon, QTransform

# pangalactic
from pangalactic.core             import diagramz, state
from pangalactic.core.uberorb     import orb
from pangalactic.core.utils.meta  import (get_block_model_id,
                                          get_block_model_name,
                                          get_block_model_file_name)
from pangalactic.node.cad.viewer  import Model3DViewer
from pangalactic.node.diagrams    import DiagramView, DocForm
from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.utils       import (clone, extract_mime_data,
                                          create_product_from_template)
from pangalactic.node.widgets     import NameLabel, PlaceHolder, ValueLabel

supported_model_types = {
    # CAD models get "eyes" icon, not a label button
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
    # orb.log.debug('* get_model_path(model with oid "{}")'.format(
                  # getattr(model, 'oid', 'None')))
    if not isinstance(model, orb.classes['Modelable']):
        # orb.log.debug('  not an instance of Modelable.')
        return ''
    # check if there is a STEP AP203/214/242 model type
    model_type_oid = getattr(model.type_of_model, 'oid', '')
    # orb.log.debug('  - model type oid: "{}"'.format(model_type_oid))
    if (model.has_representations and model_type_oid in supported_model_types):
        # FIXME:  for now we assume 1 Representation and 1 File
        rep = model.has_representations[0]
        if rep.has_files:
            rep_file = rep.has_files[0]
            u = urlparse(rep_file.url)
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
            idx (QModelIndex):  for "system" mode:  index in the system tree's
                proxy model corresponding to the object whose model is
                being displayed
            external (bool):  initialize as an external window
            preferred_size (tuple):  size to set -- (width, height)
        """
        super().__init__(parent=parent)
        # orb.log.debug('* ModelWindow initializing with:')
        # orb.log.debug('  obj "{}"'.format(getattr(obj, 'oid', 'None')))
        self.obj = obj
        self.logo = logo
        self.external = external
        self.idx = idx
        self.preferred_size = preferred_size
        self.model_files = {}
        self.history = []
        # NOTE: this set_subject() call serves only to create the diagram_view,
        # which is needed by _init_ui(); the final set_subject() actually sets
        # the subject to the currently selected object
        # obj_id = getattr(obj, 'id', '[None]')
        # orb.log.debug('  init calling set_subject() to create diagram:')
        # orb.log.debug(f'  set_subject(obj={obj_id})')
        self.set_subject(obj=obj, msg='(creating diagram view)')
        self._init_ui()
        self.setSizePolicy(QSizePolicy.Expanding,
                           QSizePolicy.Expanding)
        dispatcher.connect(self.set_subject_from_node, 'sys node selected')
        dispatcher.connect(self.set_subject_from_node, 'dash node selected')
        dispatcher.connect(self.set_subject_from_diagram_drill_down,
                           'diagram object drill down')
        dispatcher.connect(self.save_diagram_connector,
                           'diagram connector added')
        dispatcher.connect(self.refresh_block_diagram, 'refresh diagram')
        dispatcher.connect(self.refresh_block_diagram, 'new object')
        dispatcher.connect(self.refresh_block_diagram, 'modified object')
        # NOTE: 'deleted object' signal will be triggered by "remote: deleted"
        # signal handling in pangalaxian after object is deleted, so if it is a
        # port or flow, diagram should be regenerated properly
        dispatcher.connect(self.refresh_block_diagram, 'deleted object')
        dispatcher.connect(self.on_set_selected_system, 'set selected system')
        # orb.log.debug('  init calls set_subject() again to set system:')
        # orb.log.debug(f'  set_subject(obj={obj_id})')
        self.set_subject(obj=obj, msg='(setting to selected object)')

    @property
    def diagram_oids(self):
        """
        Returns oids of the subject block and all object blocks in the diagram.
        This is used by pangalaxian to decide whether to send a "block mod"
        dispatcher signal to its blocks as a result of a callback to
        on_remote_get_mod_object().
        """
        oids = [self.obj.oid]
        if hasattr(self.obj, 'components'):
            oids += [acu.component.oid for acu in self.obj.components]
        elif hasattr(self.obj, 'systems'):
            oids += [psu.system.oid for psu in self.obj.systems]
        return oids

    def sizeHint(self):
        if self.preferred_size:
            return QSize(*self.preferred_size)
        return QSize(900, 800)

    def _init_ui(self):
        # orb.log.debug('  - _init_ui() ...')
        # set a placeholder for the central widget
        self.set_placeholder()
        self.init_toolbar()
        self.setCorner(Qt.TopLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.TopRightCorner, Qt.RightDockWidgetArea)
        # Initialize a statusbar for the window
        self.statusbar = self.statusBar()
        # self.statusbar.showMessage("Models, woo!")

    def sceneScaleChanged(self, percentscale):
        newscale = float(percentscale[:-1]) / 100.0
        self.diagram_view.setTransform(QTransform().scale(newscale, newscale))

    def init_toolbar(self):
        self.toolbar = self.addToolBar("Actions")
        self.toolbar.setObjectName('ActionsToolBar')
        # NOTE: disabling the history stuff for now -- it's broken and is not
        # very useful anyway ... *might* fix in future.  The "component" mode
        # history stuff still works, and that is *way* more important!
        # self.back_action = self.create_action(
                                    # "Back",
                                    # slot=self.go_back,
                                    # icon="back",
                                    # tip="Back to Previous Model")
        # self.toolbar.addAction(self.back_action)
        # TODO:  create a dialog for saving a diagram to a SysML file ...
        # self.save_action = self.create_action(
                                    # "Save Model...",
                                    # slot=self.write_block_model,
                                    # icon="save",
                                    # tip="Save Model to a File")
        # self.toolbar.addAction(self.save_action)
        # TODO:  fix bug that crashes the external window ...
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
            try:
                self.placeholder.close()
            except:
                # C++ object got deleted
                pass
        self.placeholder = new_placeholder

    def display_external_window(self):
        # orb.log.debug('* ModelWindow.display_external_window() ...')
        mw = ModelWindow(obj=self.obj, scene=self.diagram_view.scene(),
                         logo=self.logo, external=True,
                         parent=self.parent())
        mw.show()

    def set_new_diagram_view(self):
        new_diagram_view = DiagramView(self.obj, embedded=True, parent=self)
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

    def set_subject_from_diagram_drill_down(self, usage=None):
        """
        Respond to a double-clicked diagram block by "drilling down" (setting
        the corresponding component or system as the subject of the model
        window).

        Keyword Args:
            usage (Acu or ProjectSystemUsage):  the usage represented by the
                block
        """
        # orb.log.debug('* set_subject_from_diagram_drill_down')
        self.cache_block_model()
        previous_obj = self.obj
        self.history.append(ModelerState._make((self.obj, self.idx)))
        # now change self.obj to the new object
        if isinstance(usage, orb.classes['Acu']):
            self.obj = usage.component
        elif isinstance(usage, orb.classes['ProjectSystemUsage']):
            self.obj = usage.system
        else:
            return
        # obj_id = getattr(self.obj, 'id', '[None]')
        # orb.log.debug(f'  set_subject(obj={obj_id})')
        self.idx = None
        if state.get('mode') == 'system':
            state['system'][state.get('project')] = self.obj.oid
            # if in "system" mode, attempt to find index of obj in tree
            sys_tree = getattr(self.parent(), 'sys_tree', None)
            if sys_tree:
                idxs = sys_tree.object_indexes_in_tree(self.obj)
                # orb.log.debug('  + found {} indexes in tree'.format(len(idxs)))
                target_idx = None
                if len(idxs) == 1:
                    target_idx = idxs[0]
                elif len(idxs) > 1:
                    for idx in idxs:
                        node = sys_tree.source_model.get_node(idx)
                        assembly = getattr(node.link, 'assembly', None)
                        # msg = 'obj found in assembly "{}"'.format(
                                                        # assembly.id)
                        # orb.log.debug('  + {}'.format(msg))
                        if assembly is previous_obj:
                            # orb.log.debug("    that's the one!")
                            target_idx = idx
                            break
                if target_idx:
                    # orb.log.debug('  + found index of object')
                    self.idx = sys_tree.proxy_model.mapFromSource(target_idx)
                else:
                    # if not found in tree, set self.idx to root node index
                    idx = sys_tree.source_model.index(0, 0, QModelIndex())
                    self.idx = sys_tree.proxy_model.mapFromSource(idx)
                    # orb.log.debug('  + object not in tree; setting root index')
                dispatcher.send('diagram tree index', index=self.idx)
        elif state.get('mode') == 'component':
            state['product'] = self.obj.oid
            dispatcher.send(signal='update product modeler', obj=self.obj)
            self.set_subject(obj=self.obj,
                             msg='(setting from diagram drill-down)')

    def set_subject_from_node(self, index=None, obj=None, link=None):
        """
        Respond to a node selection in the system tree or dashboard by setting
        the corresponding object as the subject of the model window.

        Keyword Args:
            index (QModelIndex):  index in the system tree's proxy model
                corresponding to the object being modeled
            obj (Identifiable): obj being modeled
        """
        if state.get('mode') == 'system':
            self.cache_block_model()
            self.history.append(ModelerState._make((self.obj, self.idx)))
            self.idx = index
            # orb.log.debug('  setting subject from tree node selection ...')
            # obj_id = getattr(self.obj, 'id', '[None]')
            # orb.log.debug(f'  set_subject(obj={obj_id})')
            self.set_subject(obj=obj, msg='(setting from tree node selection)')

    def on_set_selected_system(self):
        """
        If in "system" mode, set the selected system as the subject of the
        model window.
        """
        if state.get('mode') == 'system':
            oid = (state.get('system') or {}).get(state.get('project'))
            obj = orb.get(oid)
            if obj:
                # orb.log.debug('  setting subject from selected system..')
                self.set_subject(obj=obj, msg='(setting from selected system)')

    def set_subject(self, obj=None, msg=''):
        """
        Set an object for the current modeler context.  If the object does not
        have a Block model one is created from its components (or an empty
        Block Model if there are no components).

        Keyword Args:
            obj (Identifiable): if no model is provided, find models of obj
        """
        # orb.log.debug('* ModelWindow.set_subject({})'.format(
                      # getattr(obj, 'id', 'None')))
        # if msg:
            # orb.log.debug('  {}'.format(msg))
        # reset model_files
        self.model_files = {}
        if hasattr(self, 'view_cad_action'):
            try:
                self.view_cad_action.setVisible(False)
            except:
                # oops, C++ object got deleted
                pass
        self.obj = obj or self.obj
        if self.obj:
            if isinstance(self.obj, orb.classes['Modelable']):
                # orb.log.debug('* ModelWindow: checking for models ...')
                # model_types = set()
                if self.obj.has_models:
                    for m in self.obj.has_models:
                        fpath = get_model_path(m)
                        if fpath:
                            # fpath only needed for CAD models, since block
                            # models have a canonical path
                            self.model_files[m.oid] = fpath
                        # model_types.add(m.type_of_model.oid)
                try:
                    self.display_block_diagram()
                except:
                    # orb.log.debug('* ModelWindow C++ object deleted.')
                    pass
            else:
                # orb.log.debug('* ModelWindow: obj not Modelable, ignoring')
                self.obj = None
                # orb.log.debug('  ... setting placeholder widget.')
                self.set_placeholder()
        else:
            self.obj = None
            # orb.log.debug('  no object; setting placeholder widget.')
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
        # if self.history:
            # if hasattr(self, 'back_action'):
                # self.back_action.setEnabled(True)
        # else:
            # if hasattr(self, 'back_action'):
                # self.back_action.setEnabled(False)
        self.cache_block_model()
        if hasattr(self, 'diagram_view'):
            try:
                self.diagram_view.verticalScrollBar().setValue(0)
                self.diagram_view.horizontalScrollBar().setValue(0)
            except:
                # diagram_view C++ object got deleted
                pass

    def display_cad_model(self):
        try:
            model, fpath = self.models_by_label.get('CAD')
            if fpath:
                # orb.log.debug('* ModelWindow.display_cad_model({})'.format(
                                                                    # fpath))
                viewer = Model3DViewer(step_file=fpath, parent=self)
                viewer.show()
        except:
            # orb.log.debug('  CAD model not found.')
            pass

    def display_block_diagram(self):
        """
        Display a block diagram for the currently selected product or project.
        """
        # orb.log.debug('* Modeler:  display_block_diagram()')
        if state.get('mode') in ['data', 'db']:
            # NOTE:  without this we will crash -- there is no model window in
            # these modes!
            return
        if state.get('mode') == 'system':
            # orb.log.debug('  mode is "system" ...')
            # in "system" mode, sync with tree selection
            sys_tree = getattr(self.parent(), 'sys_tree', None)
            # if obj has been set, use it; if not look for tree selection
            if not self.obj:
                if (sys_tree and len(sys_tree.selectedIndexes()) > 0):
                    i = sys_tree.selectedIndexes()[0]
                    mapped_i = sys_tree.proxy_model.mapToSource(i)
                    self.obj = sys_tree.source_model.get_node(mapped_i).obj
                    # orb.log.debug(f'  using tree selection: {obj.id}')
                else:
                    project = orb.get(state.get('project'))
                    sys_oid = (state.get('system') or {}).get(project) or ''
                    state_sys = None
                    if sys_oid:
                        state_sys = orb.get(sys_oid)
                    if state_sys:
                        # orb.log.debug(f'  - using system: "{state_sys.id}"')
                        self.obj = state_sys
                    elif project:
                        # msg = f'  - no system, using project: {project.id}'
                        # orb.log.debug(msg)
                        self.obj = project
        elif state.get('mode') == 'component':
            # orb.log.debug('  mode is "component"')
            self.obj = orb.get(state.get('product'))
        # if not self.obj:
            # orb.log.debug('  no object selected.')
            # self.set_subject(None)
            # return
        # else:
            # orb.log.debug('  object selected: {}.'.format(obj.id))
        self.set_new_diagram_view()
        scene = self.diagram_view.scene()
        block_ordering = diagramz.get(self.obj.oid)
        if block_ordering:
            # orb.log.debug('  - generating diagram with ordering ...')
            scene.generate_ibd(self.obj, ordering=block_ordering)
        else:
            # orb.log.debug('  - generating new block diagram ...')
            # orb.log.debug('  - generating diagram (cache disabled for testing)')
            scene.generate_ibd(self.obj)
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

    def refresh_block_diagram(self):
        """
        Regenerate block diagram using either its subject product or the
        currently selected system or project.
        """
        # orb.log.debug('* Modeler:  refresh_block_diagram()')
        self.set_new_diagram_view()
        scene = self.diagram_view.scene()
        if (state['mode'] == "system" and state.get('system')
            and state['system'].get(state.get('project'))):
            selected_oid = state['system'][state['project']]
            selected_obj = orb.get(selected_oid)
            if selected_obj:
                self.obj = selected_obj
        oid = getattr(self.obj, 'oid', '') or ''
        block_ordering = diagramz.get(oid)
        if block_ordering:
            # orb.log.debug('  - generating diagram with ordering ...')
            scene.generate_ibd(self.obj, ordering=block_ordering)
        else:
            # orb.log.debug('  - generating new block diagram ...')
            # orb.log.debug('  - generating diagram (cache disabled for testing)')
            scene.generate_ibd(self.obj)
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

    # NOTE: disabled for now because broken (see note above)
    # def go_back(self):
        # orb.log.debug('* Modeler: go_back()')
        # if self.history:
            # hist = self.history.pop()
            # obj, self.idx = hist.obj, hist.idx
            # if hasattr(obj, 'oid'):
                # if state.get('mode') == 'system':
                    # state['system'][state.get('project')] = obj.oid
                # elif state.get('mode') == 'component':
                    # state['product'] = obj.oid
            # if not self.history:
                # self.back_action.setEnabled(False)
                # # if that was the last history item and we are in "system" mode
                # # and the history item didn't specify a tree index, use the
                # # project as the "system" state
                # if not self.idx:
                    # state['system'][
                                # state.get('project')] = state.get('project')
                    # obj = orb.get(state.get('project'))
            # self.obj = obj
            # obj_id = getattr(obj, 'id', '[None]')
            # orb.log.debug(f'  - calling set_subject(obj={obj_id})')
            # self.set_subject(obj=obj)
            # dispatcher.send('diagram go back', index=self.idx)
        # else:
            # self.back_action.setEnabled(False)

    def cache_block_model(self):
        """
        Serialize block model metadata into a dictionary format and save it to
        the `diagramz` cache.
        """
        # orb.log.debug('* Modeler: cache_block_model()')
        # TODO: first "block"; then "activity" (mission models, etc.)
        if not getattr(self, 'obj'):
            # orb.log.debug('  ... no object, returning.')
            return
        # NOTE:  do not write to a file -- orb._save_diagramz() does that
        # TODO: also send the serialized "model" to vger to be saved there ...
        # TODO: need to define a Model, Representation, and RepresentationFile
        # orb.log.debug('* Modeler: caching diagram geometry ...')
        try:
            scene = self.diagram_view.scene()
            # cache the diagram geometry (layout of blocks)
            # NOTE: get_diagram_geometry() got arbitrary block positions --
            # this is deprecated in favor of using the ordering of the blocks
            # to generate the diagram with 2 uniform columns of blocks
            # diagramz[self.obj.oid] = scene.get_diagram_geometry()
            diagramz[self.obj.oid] = scene.get_block_ordering()
            # orb.log.debug('  ... cached.')
        except:
            # orb.log.debug('  ... could not cache (C++ obj deleted?)')
            pass

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
        # orb.log.debug('* Modeler: write_block_model()')
        # # TODO: find or create a Representation with 'of_object' == model.oid
        # # and a RepresentationFile that will get the file path as its 'url'
        # # attribute.
        # if not cached_model:
            # if (not self.obj or
                # not diagramz.get(self.obj.oid)):
                # orb.log.debug('  no cached block model found; returning.')
                # return
            # cached_model = diagramz[self.obj.oid]
        # fname = get_block_model_file_name(self.obj)
        # if not fpath:
            # # write to vault if fpath is not given
            # orb.log.debug('  writing to vault: {}'.format(fname))
            # fpath = os.path.join(orb.vault, fname)
        # f = open(fpath, 'w')
        # orb.log.debug('  writing to path {} ...'.format(fpath))
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
        # orb.log.debug('* Modeler: read_block_model({})'.format(fpath))
        # if not os.path.exists(fpath):
            # orb.log.debug('  - path does not exist.')
            # return None
        # f = open(fpath)
        # orb.log.debug('  reading model from path {} ...'.format(fpath))
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
            orb.log.debug('* ModelWindow: creating new Model for '
                          'Product with id "%s"' % self.obj.id)
            owner = orb.get(state.get('project'))
            model_id = get_block_model_id(self.obj)
            model_name = get_block_model_name(self.obj)
            block_model_type = orb.get(BLOCK_OID)
            new_model = clone('Model', id=model_id, name=model_name,
                              type_of_model=block_model_type,
                              owner=owner, of_thing=self.obj)
            dlg = PgxnObject(new_model, edit_mode=True, parent=self)
            # dialog.show() -> non-modal dialog
            dlg.show()


class ProductInfoPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        # orb.log.debug('* ProductInfoPanel initializing ...')
        self.setAcceptDrops(True)
        # product frame
        product_frame_vbox = QVBoxLayout()
        product_frame_vbox.setAlignment(Qt.AlignLeft|Qt.AlignTop)
        product_frame_vbox.setSizeConstraint(QLayout.SetMinimumSize)
        title = NameLabel('Product')
        title.setStyleSheet('font-weight: bold; font-size: 18px')
        product_frame_vbox.addWidget(title)
        product_info_layout = QHBoxLayout()
        product_info_layout.setAlignment(Qt.AlignLeft|Qt.AlignTop)
        icon_file = 'back.png'
        icon_dir = state.get('icon_dir', os.path.join(orb.home, 'icons'))
        icon_path = os.path.join(icon_dir, icon_file)
        back_icon = QIcon(icon_path)
        self.back_button = QPushButton(back_icon, 'Back')
        self.back_button.setToolTip('Back')
        self.back_button.clicked.connect(self.load_last_product)
        product_info_layout.addWidget(self.back_button)
        self.clear_hist_button = QPushButton('Clear History')
        self.clear_hist_button.setToolTip('Clear the modeler history')
        self.clear_hist_button.clicked.connect(self.clear_history)
        product_info_layout.addWidget(self.clear_hist_button)
        if state.get('component_modeler_history'):
            self.back_button.setEnabled(True)
            self.clear_hist_button.setEnabled(True)
        else:
            self.back_button.setEnabled(False)
            self.clear_hist_button.setEnabled(False)
        product_id_label = NameLabel('id:')
        product_id_label.setStyleSheet('font-weight: bold')
        product_info_layout.addWidget(product_id_label)
        self.product_id_value_label = ValueLabel('No Product Selected', w=200)
        product_info_layout.addWidget(self.product_id_value_label)
        product_name_label = NameLabel('name:')
        product_name_label.setStyleSheet('font-weight: bold')
        product_info_layout.addWidget(product_name_label)
        self.product_name_value_label = ValueLabel(
                                'Drag/Drop a Product from Library ...', w=320)
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
        if state.get('product'):
            product = orb.get(state['product'])
            if product:
                self.set_product(product)
        dispatcher.connect(self.on_update, 'update product modeler')

    def load_last_product(self):
        # pangalaxian will pop the previous product in history and set it as
        # product
        dispatcher.send('comp modeler back')

    def clear_history(self):
        state['component_modeler_history'] = []
        self.back_button.setEnabled(False)
        self.clear_hist_button.setEnabled(False)

    def on_update(self, obj=None):
        if obj:
            self.set_product(obj)

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
        if event.mimeData().hasFormat(
                                "application/x-pgef-hardware-product"):
            data = extract_mime_data(event,
                                     "application/x-pgef-hardware-product")
            icon, p_oid, p_id, p_name, p_cname = data
            product = orb.get(p_oid)
            if product:
                dispatcher.send("drop on product info", p=product)
            else:
                event.ignore()
                orb.log.debug("* product drop event: ignoring oid '%s' -- "
                              "not found in db." % p_oid)
        elif event.mimeData().hasFormat("application/x-pgef-template"):
            # drop item is Template -> create a new product from it
            data = extract_mime_data(event, "application/x-pgef-template")
            icon, t_oid, t_id, t_name, t_cname = data
            template = orb.get(t_oid)
            product = create_product_from_template(template)
            # NOTE: the below stuff is unnecessary, I think
            # if product.components:
                # orb.save(product.components)
                # for acu in product.components:
                    # dispatcher.send('new object', obj=acu)
            dispatcher.send("drop on product info", p=product)
            dispatcher.send('new object', obj=product)
        else:
            event.ignore()

    def set_product(self, product=None):
        """
        Set a product in the modeler context.
        """
        # orb.log.debug('* ProductInfoPanel: set_product')
        # product_oid = state.get('product')
        # product = orb.get(product_oid)
        if product:
            # if not a HardwareProduct, product is ignored
            if product.__class__.__name__ != 'HardwareProduct':
                # orb.log.debug('  - not a HardwareProduct -- ignored.')
                return
            # orb.log.debug('  - oid: %s' % product.oid)
            self.product_id_value_label.setText(product.id)
            self.product_name_value_label.setText(product.name)
            if hasattr(product, 'version'):
                self.product_version_value_label.setText(getattr(product,
                                                              'version'))
            self.product_id_value_label.setEnabled(True)
            self.product_name_value_label.setEnabled(True)
            self.product_version_value_label.setEnabled(True)
        else:
            # orb.log.debug('  - None')
            # set widgets to disabled state
            self.product_id_value_label.setEnabled(False)
            self.product_name_value_label.setEnabled(False)
            self.product_version_value_label.setEnabled(False)

if __name__ == '__main__':
    import sys
    from pangalactic.core.serializers import deserialize
    from pangalactic.core.test.utils import (create_test_project,
                                             create_test_users)
    orb.start(home='junk_home', debug=True)
    obj = orb.get('test:spacecraft0')
    if not obj:
        if not state.get('test_users_loaded'):
            print('* loading test users ...')
            deserialize(orb, create_test_users())
            state['test_users_loaded'] = True
        print('* loading test project H2G2 ...')
        deserialize(orb, create_test_project())
        hw = orb.search_exact(cname='HardwareProduct', id_ns='test')
        orb.assign_test_parameters(hw)
        obj = orb.get('test:spacecraft0')
    app = QApplication(sys.argv)
    mw = ModelWindow(obj=obj, external=True)
    mw.show()
    sys.exit(app.exec_())

