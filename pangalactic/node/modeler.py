#!/usr/bin/env python
import os
from collections import namedtuple
from urllib.parse    import urlparse

from louie import dispatcher

from PyQt5.QtCore import pyqtSignal, Qt, QModelIndex, QSize
from PyQt5.QtWidgets import (QAction, QApplication, QComboBox, QHBoxLayout,
                             QLayout, QMainWindow, QPushButton, QSizePolicy,
                             QVBoxLayout, QWidget)
from PyQt5.QtGui import QIcon, QTransform

# pangalactic
from pangalactic.core             import diagramz, state
# from pangalactic.core.clone       import clone
# from pangalactic.core.names       import (get_block_model_id,
                                          # get_block_model_name,
                                          # get_block_model_file_name)
from pangalactic.core.uberorb     import orb
from pangalactic.node.cad.viewer  import Model3DViewer
from pangalactic.node.diagrams    import DiagramView, DocForm
from pangalactic.node.dialogs     import ModelImportDialog
# from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.utils       import (extract_mime_data,
                                          create_product_from_template)
from pangalactic.node.widgets     import NameLabel, PlaceHolder, ValueLabel

supported_model_types = {
    # CAD models get "eyes" icon, not a label button
    'pgefobjects:ModelType.MCAD' : None,
    }

# a named tuple used in managing the "history" of the ModelWindow so that it
# can be navigated
ModelerState = namedtuple('ModelerState', 'obj idx')


def get_step_file_path(model):
    """
    Find the path of a STEP file for a model.

    Args:
        model (Model):  the Model instance for which the STEP file is sought

    Returns:
        the path to the STEP file in the orb's "vault"
    """
    # orb.log.debug('* get_step_model_path(model with oid "{}")'.format(
                  # getattr(model, 'oid', 'None')))
    if (model.has_representations and model.type_of_model.id == "MCAD"):
        for rep in model.has_representations:
            if rep.has_files:
                for rep_file in rep.has_files:
                    u = urlparse(rep_file.url)
                    if (u.scheme == 'vault' and
                        rep_file.url.endswith(('.stp', '.step', '.p21'))):
                        fpath = os.path.join(orb.vault, u.netloc)
                        if os.path.exists(fpath):
                            return fpath
                    else:
                        continue
            else:
                continue
    else:
        return ''


class ModelWindow(QMainWindow):
    """
    Main window for displaying models and their metadata.

    Attrs:
        idx (QModelIndex):  index in the system tree's proxy model
            corresponding to the object being modeled
        history (list):  list of previous ModelerState instances
    """

    deleted_object = pyqtSignal(str, str)  # args: oid, cname

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
        self.setWindowTitle('Block Modeler')
        # orb.log.debug('* ModelWindow initializing with:')
        # orb.log.debug('  obj "{}"'.format(getattr(obj, 'oid', 'None')))
        self.obj = obj
        self.logo = logo
        self.external = external
        self.idx = idx
        self.preferred_size = preferred_size
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
        dispatcher.connect(self.on_signal_to_refresh, 'refresh diagram')
        dispatcher.connect(self.on_signal_to_refresh, 'new object')
        dispatcher.connect(self.on_signal_to_refresh, 'modified object')
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

    @property
    def models(self):
        """
        Returns a dict mapping "Model.type_of_model" (ModelType) id to the
        models of that type for all models of self.obj.
        """
        model_instances = getattr(self.obj, 'has_models', [])
        model_dict = {}
        if model_instances:
            for m in model_instances:
                mtype_id = m.type_of_model.id
                if mtype_id in model_dict:
                    model_dict[mtype_id].append(m)
                else:
                    model_dict[mtype_id] = [m]
        return model_dict

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
        if hasattr(self, 'view_cad_action'):
            try:
                self.view_cad_action.setVisible(False)
            except:
                # oops, C++ object got deleted
                pass
        self.obj = obj or self.obj
        if self.obj:
            if hasattr(self, 'add_model_action'):
                try:
                    if hasattr(self.obj, 'owner'):
                        self.add_model_action.setEnabled(True)
                    else:
                        self.add_model_action.setEnabled(False)
                except:
                    # C++ object got deleted
                    pass
            try:
                self.display_block_diagram()
            except:
                # orb.log.debug('* ModelWindow C++ object deleted.')
                pass
        else:
            self.obj = None
            # orb.log.debug('  no object; setting placeholder widget.')
            self.set_placeholder()
        # TODO:  enable multiple CAD models (e.g. "detailed" / "simplified")
        if self.models:
            # orb.log.debug('* ModelWindow: subject has models ...')
            if hasattr(self, 'show_models_action'):
                try:
                    self.show_models_action.setVisible(True)
                except:
                    # oops, C++ object got deleted
                    pass
            # for oid, fpath in self.model_files.items():
                # model = orb.get(oid)
                # fname = os.path.basename(fpath)
                # suffix = fname.split('.')[1]
                # # orb.log.debug(f'  {model.id} has suffix "{suffix}"')
                # mtype_oid = getattr(model.type_of_model, 'oid', '') or ''
                # if mtype_oid == 'pgefobjects:ModelType.MCAD':
            # NOTE: a given product may have more than one MCAD model -- e.g.,
            # a fully detailed model and one or more "simplified" models -- so
            # the "view cad" action should display a dialog with info about all
            # the MCAD models ...
            mcad_models = self.models.get('MCAD')
            if mcad_models:
                step_fpaths = [get_step_file_path(m) for m in mcad_models]
                if step_fpaths and hasattr(self, 'view_cad_action'):
                    try:
                        self.view_cad_action.setVisible(True)
                    except:
                        # oops, C++ object got deleted
                        pass
                else:
                    orb.log.debug('  no step files found.')
        self.cache_block_model()
        if hasattr(self, 'diagram_view'):
            try:
                self.diagram_view.verticalScrollBar().setValue(0)
                self.diagram_view.horizontalScrollBar().setValue(0)
            except:
                # diagram_view C++ object got deleted
                pass

    def show_models(self):
        pass

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
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.toolbar.setContextMenuPolicy(Qt.PreventContextMenu)
        self.toolbar.setObjectName('ActionsToolBar')
        # TODO:  create a dialog for exporting a diagram to a SysML file ...
        # self.export_action = self.create_action(
                                    # "Export SysML ...",
                                    # slot=self.export_sysml,
                                    # icon="save",
                                    # tip="Export Model to SysML")
        # self.toolbar.addAction(self.export_action)
        self.scene_scale_select = QComboBox()
        self.scene_scale_select.addItems(["25%", "30%", "40%", "50%", "75%",
                                          "100%"])
        self.scene_scale_select.setCurrentIndex(3)
        self.scene_scale_select.currentIndexChanged[str].connect(
                                                    self.sceneScaleChanged)
        self.toolbar.addWidget(self.scene_scale_select)
        self.image_action = self.create_action("Snap",
                                               slot=self.image_preview,
                                               icon="camera",
                                               tip="Save as Image or Print")
        self.toolbar.addAction(self.image_action)
        self.show_models_action = self.create_action(
                                "Info on Models ...",
                                slot=self.show_models,
                                icon="view_16",
                                tip="Show Available Models of this Product")
        self.view_cad_action = self.create_action(
                                    "View CAD",
                                    slot=self.display_step_models,
                                    icon="box",
                                    tip="View CAD Model (from STEP File)")
        self.toolbar.addAction(self.view_cad_action)
        self.add_model_action = self.create_action(
                                    "Upload a Model",
                                    slot=self.add_update_model,
                                    icon="lander",
                                    tip="Add or Update a Model File")
        self.toolbar.addAction(self.add_model_action)
        if getattr(self.obj, 'owner', None):
            self.add_model_action.setEnabled(True)
        else:
            self.add_model_action.setEnabled(False)
        # self.external_window_action = self.create_action(
                                    # "Display external diagram window ...",
                                    # slot=self.display_external_window,
                                    # icon="system",
                                    # tip="Display External Diagram Window")
        # if not self.external:
            # self.toolbar.addAction(self.external_window_action)

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

    def image_preview(self):
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

    # def display_external_window(self):
        # # orb.log.debug('* ModelWindow.display_external_window() ...')
        # mw = ModelWindow(obj=self.obj, scene=self.diagram_view.scene(),
                         # logo=self.logo, external=True,
                         # parent=self.parent())
        # mw.show()

    def set_new_diagram_view(self):
        new_diagram_view = DiagramView(self.obj, embedded=True, parent=self)
        new_diagram_view.scene().deleted_object.connect(self.on_deleted_object)
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

    def display_step_models(self):
        """
        Display the STEP models associated with the current self.subject (a
        Modelable instance, which may or may not have a STEP model). If there
        is only one, simply open a Model3DViewer with that one; if more than
        one, open a dialog with information about all and offer to display a
        selected one.
        """
        # TODO: display a dialog if multiple STEP models ...
        # ... if only one, just display it in the viewer ...
        mcad_models = self.models.get("MCAD")
        fpath = ''
        fpaths = []
        if mcad_models:
            orb.log.debug('  MCAD models found:')
            for m in mcad_models:
                orb.log.debug(f'      - model: "{m.id}"')
                fpath = get_step_file_path(m)
                fpaths.append(fpath)
                if fpath:
                    orb.log.debug(f'        step file path: {fpath}')
                else:
                    orb.log.debug('        no step file found.')
                orb.log.debug(f'      - {fpath}')
            orb.log.debug(f'  fpaths: {fpaths}')
        else:
            orb.log.debug('  MCAD models not found.')
            return
        if fpaths:
            fpath = fpaths[0]
            orb.log.debug(f'  step file: "{fpath}"')
        try:
            if fpath:
                viewer = Model3DViewer(step_file=fpath, parent=self)
                viewer.show()
        except:
            orb.log.debug('  CAD model not found or not in STEP format.')
            pass

    def add_update_model(self, model_type_id=None):
        dlg = ModelImportDialog(of_thing_oid=self.obj.oid,
                                model_type_id=model_type_id, parent=self)
        dlg.show()

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
        # whenever a new scene is created (in association with the view), its
        # "deleted_object" signal (and possibly other signals) must be
        # connected ...
        block_ordering = diagramz.get(self.obj.oid)
        if block_ordering:
            # orb.log.debug('  - generating diagram with ordering ...')
            scene.generate_ibd(self.obj, ordering=block_ordering)
        else:
            # orb.log.debug('  - generating new block diagram ...')
            # orb.log.debug('  - generating diagram (cache disabled for testing)')
            scene.generate_ibd(self.obj)
            # # create a block Model object if self.obj doesn't have one
            # block_model_type = orb.get(BLOCK_OID)
            # if self.obj.has_models:
                # block_models = [m for m in self.obj.has_models
                    # if getattr(m, 'type_of_model', None) == block_model_type]
                # if not block_models:
                    # model_id = get_block_model_id(self.obj)
                    # model_name = get_block_model_name(self.obj)
                    # self.model = clone('Model', id=model_id, name=model_name,
                                       # type_of_model=block_model_type,
                                       # of_thing=self.obj)

    def on_deleted_object(self, oid, cname):
        """
        Handle "deleted object" signal -- ignore if not in "system" or
        "component" mode (ModelWindow C++ object will not exist!).

        NOTE: 'deleted_object' signal handled in pangalaxian so diagram should
        be regenerated properly
        """
        if state.get('mode') in ['system', 'component']:
            self.refresh_block_diagram()
            self.deleted_object.emit(oid, cname)
        return

    def on_signal_to_refresh(self):
        try:
            self.refresh_block_diagram()
        except:
            # Modeler instance C++ obj deleted, like if we are in db mode
            return

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
        if self.obj is None:
            # ignore if self.obj is None -- otherwise may crash
            return
        oid = getattr(self.obj, 'oid', '') or ''
        block_ordering = diagramz.get(oid)
        if block_ordering:
            # orb.log.debug('  - generating diagram with ordering ...')
            scene.generate_ibd(self.obj, ordering=block_ordering)
        else:
            # orb.log.debug('  - generating new block diagram ...')
            # orb.log.debug('  - generating diagram (cache disabled for testing)')
            scene.generate_ibd(self.obj)

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

