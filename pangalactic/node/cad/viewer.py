#!/usr/bin/env python

import argparse, os, platform, sys

try:
    from pangalactic.core         import orb
except:
    import pangalactic.core.set_uberorb
    from pangalactic.core         import orb
from pangalactic.core         import state
from pangalactic.node.buttons import MenuButton

from OCC.Display.backend import load_backend
load_backend("pyqt5")
import OCC.Display.qtDisplay as qtDisplay

from OCC.Core.BRep import BRep_Builder
from OCC.Core.BRepTools import breptools_Read
from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB
from OCC.Core.TopoDS import TopoDS_Shape
from OCC.Extend.DataExchange import (read_step_file_with_names_colors,
                                     read_stl_file)

from PyQt5 import QtGui
from PyQt5.QtWidgets import (QAction, QApplication, QFileDialog, QMainWindow,
                             QVBoxLayout)
from PyQt5.QtCore import Qt


class point(object):
    def __init__(self, obj=None):
        self.x = 0
        self.y = 0
        if obj is not None:
            self.set(obj)

    def set(self, obj):
        self.x = obj.x()
        self.y = obj.y()


class Model3DViewer(QMainWindow):
    def __init__(self, fpath='', h=600, w=800, parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle(self.tr("3D CAD Model Viewer"))
        self.viewer_in_use = False
        self.shape = None
        self.w = w
        self.h = h
        self.resize(self.w, self.h)
        self.init_viewer_3d()
        self.open_step_file_action = self.create_action("Open a STEP file...",
                                   slot=self.open_step_file,
                                   tip="View a CAD model from a STEP file")
        self.open_stl_file_action = self.create_action("Open an STL file...",
                                   slot=self.open_stl_file,
                                   tip="View a model from an STL file")
        self.open_brep_file_action = self.create_action("Open a brep file...",
                                   slot=self.open_brep_file,
                                   tip="View a model from an .brep file")
        self.export_to_image_action = self.create_action("Export to image...",
                                   slot=self.export_to_image,
                                   tip="Export current view to image...")
        self.export_to_image_action.setEnabled(False)
        self.toolbar = self.addToolBar("Actions")
        self.toolbar.setObjectName('ActionsToolBar')
        import_icon_file = 'open' + state.get('icon_type', '.png')
        self.icon_dir = state.get('icon_dir',
                             os.path.join(getattr(orb, 'home', ''), 'icons'))
        import_icon_path = os.path.join(self.icon_dir, import_icon_file)
        import_actions = [self.open_step_file_action,
                          self.open_stl_file_action,
                          self.open_brep_file_action]
        import_button = MenuButton(QtGui.QIcon(import_icon_path),
                                   tooltip='Import Data or Objects',
                                   actions=import_actions, parent=self)
        self.toolbar.addWidget(import_button)
        export_icon_file = 'save' + state.get('icon_type', '.png')
        export_icon_path = os.path.join(self.icon_dir, export_icon_file)
        export_actions = [self.export_to_image_action]
        self.export_button = MenuButton(QtGui.QIcon(export_icon_path),
                                   tooltip='Export Data or Objects',
                                   actions=export_actions, parent=self)
        self.toolbar.addWidget(self.export_button)
        if fpath:
            basename, fname = os.path.split(fpath)
            parts = fname.split('.')
            suffix = ''
            if len(parts) == 2:
                suffix = parts[1]
            if suffix in ['step', 'stp', 'p21']:
                self.open_specified_step_file(fpath)
            elif suffix == 'stl':
                self.viewer_in_use = True
                stl_shape = read_stl_file(fpath)
                self.shape = self.display.DisplayShape(stl_shape,
                                                       update=True)[0]
            elif suffix == 'brep':
                self.viewer_in_use = True
                brep_shape = TopoDS_Shape()
                builder = BRep_Builder()
                breptools_Read(brep_shape, fpath, builder)
                self.shape = self.display.DisplayShape(brep_shape,
                                                       update=True)[0]

    def init_viewer_3d(self):
        if getattr(self, 'viewer3d', None):
            if getattr(self, 'vbox', None):
                self.vbox.removeWidget(self.viewer3d)
            # close existing viewer
            self.viewer3d.setAttribute(Qt.WA_DeleteOnClose)
            self.viewer3d.parent = None
            self.viewer3d.close()
            self.viewer3d = None
        self.viewer3d = qtDisplay.qtViewer3d(self)
        self.viewer_in_use = False
        if not getattr(self, 'vbox', None):
            self.vbox = QVBoxLayout()
        self.vbox.addWidget(self.viewer3d)
        self.setCentralWidget(self.viewer3d)
        self.show()
        self.viewer3d.InitDriver()
        self.viewer3d.resize(self.w, self.h)
        self.display = self.viewer3d._display

    def create_action(self, text, icon=None, slot=None, tip=None):
        action = QAction(text, self)
        if icon is not None:
            icon_file = icon + state.get('icon_type', '.png')
            icon_path = os.path.join(self.icon_dir, icon_file)
            action.setIcon(QtGui.QIcon(icon_path))
        if tip is not None:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        if slot is not None:
            action.triggered.connect(slot)
        return action

    def export_to_image(self):
        fname = 'cad_view.png'
        fpath, filters = QFileDialog.getSaveFileName(
                                    self, 'Export to Image File',
                                    fname)
        if fpath:
            if orb.started:
                orb.log.debug('* exporting to image file...')
            self.display.ExportToImage(fpath)
            if orb.started:
                orb.log.debug('  done.')
        else:
            if orb.started:
                orb.log.debug('* no path for export, aborting.')
            return

    def open_specified_step_file(self, fpath):
        if fpath:
            # TODO: exception handling in case data import fails ...
            # TODO: add an "index" column for sorting, or else figure out how
            # to sort on the left header column ...
            state['last_step_path'] = os.path.dirname(fpath)
            if orb.started:
                orb.log.debug('  - opening STEP file "{}" ...'.format(fpath))
        else:
            return
        self.viewer_in_use = True
        shapes_labels_colors = read_step_file_with_names_colors(fpath)
        for shpt_lbl_color in shapes_labels_colors:
            label, c = shapes_labels_colors[shpt_lbl_color]
            self.display.display_triedron()
            self.shape = self.display.DisplayColoredShape(shpt_lbl_color,
                                    color=Quantity_Color(c.Red(),
                                                         c.Green(),
                                                         c.Blue(),
                                                         Quantity_TOC_RGB))[0]
        self.display.FitAll()

    def open_step_file(self):
        if platform.platform().startswith('Darwin'):
            # on Mac, can only open one file (next attempt will crash)
            self.removeToolBar(self.toolbar)
            self.open_step_file_action.setEnabled(False)
            self.open_stl_file_action.setEnabled(False)
        if orb.started:
            orb.log.debug('* opening a STEP file')
            if not state.get('last_step_path'):
                state['last_step_path'] = orb.test_data_dir
        fpath, filters = QFileDialog.getOpenFileName(
                                    self, 'Open STEP File',
                                    state.get('last_step_path', ''),
                                    'STEP Files (*.stp *.step *.p21)')
        if fpath:
            # TODO: exception handling in case data import fails ...
            # TODO: add an "index" column for sorting, or else figure out how
            # to sort on the left header column ...
            state['last_step_path'] = os.path.dirname(fpath)
            if orb.started:
                orb.log.debug('  - opening STEP file "{}" ...'.format(fpath))
            if self.viewer_in_use:
                self.display.EraseAll()
                self.viewer_in_use = False
            if hasattr(self, 'export_to_image_action'):
                self.export_to_image_action.setEnabled(True)
        else:
            return
        self.viewer_in_use = True
        shapes_labels_colors = read_step_file_with_names_colors(fpath)
        for shpt_lbl_color in shapes_labels_colors:
            label, c = shapes_labels_colors[shpt_lbl_color]
            self.display.display_triedron()
            self.shape = self.display.DisplayColoredShape(
                                    shpt_lbl_color,
                                    color=Quantity_Color(c.Red(),
                                                         c.Green(),
                                                         c.Blue(),
                                                         Quantity_TOC_RGB))[0]
        self.display.FitAll()

    def open_stl_file(self):
        if platform.platform().startswith('Darwin'):
            # on Mac, can only open one step file (next attempt will crash)
            self.removeToolBar(self.toolbar)
            self.open_step_file_action.setEnabled(False)
            self.open_stl_file_action.setEnabled(False)
        if orb.started:
            orb.log.debug('* opening an STL file')
            if not state.get('last_stl_path'):
                state['last_stl_path'] = orb.test_data_dir
        fpath, filters = QFileDialog.getOpenFileName(
                                    self, 'Open STL File',
                                    state.get('last_stl_path', ''),
                                    'STL Files (*.stl)')
        if fpath:
            # TODO: exception handling in case data import fails ...
            # TODO: add an "index" column for sorting, or else figure out how
            # to sort on the left header column ...
            state['last_path'] = os.path.dirname(fpath)
            if orb.started:
                orb.log.debug('  - opening STL file "{}" ...'.format(fpath))
            if self.viewer_in_use:
                self.display.EraseAll()
                self.viewer_in_use = False
            if hasattr(self, 'export_to_image_action'):
                self.export_to_image_action.setEnabled(True)
        else:
            return
        self.viewer_in_use = True
        stl_shape = read_stl_file(fpath)
        self.display.DisplayShape(stl_shape, update=True)
        self.display.FitAll()

    def open_brep_file(self):
        if platform.platform().startswith('Darwin'):
            # on Mac, can only open one step file (next attempt will crash)
            self.removeToolBar(self.toolbar)
            self.open_step_file_action.setEnabled(False)
            self.open_stl_file_action.setEnabled(False)
        if orb.started:
            orb.log.debug('* opening a brep file')
            if not state.get('last_brep_path'):
                state['last_brep_path'] = orb.test_data_dir
        fpath, filters = QFileDialog.getOpenFileName(
                                    self, 'Open brep File',
                                    state.get('last_brep_path', ''),
                                    'brep files (*.brep)')
        if fpath:
            # TODO: exception handling in case data import fails ...
            # TODO: add an "index" column for sorting, or else figure out how
            # to sort on the left header column ...
            state['last_brep_path'] = os.path.dirname(fpath)
            if orb.started:
                orb.log.debug('  - opening brep file "{}" ...'.format(fpath))
            if self.viewer_in_use:
                self.display.EraseAll()
                self.viewer_in_use = False
            if hasattr(self, 'export_to_image_action'):
                self.export_to_image_action.setEnabled(True)
        else:
            return
        self.viewer_in_use = True
        brep_shape = TopoDS_Shape()
        builder = BRep_Builder()
        breptools_Read(brep_shape, fpath, builder)
        self.display.DisplayShape(brep_shape, update=True)
        self.display.FitAll()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--file', type=str, help='file to load')
    options = parser.parse_args()
    if options.file:
        fpath = options.file
    else:
        # CAX-IF test file "bracket"
        fpath = '../test/data/as1-oc-214.stp'
        # Test file:  cubical electronic package
        # fpath = '../test/data/a7959_asm.p21'
        # CAX-IF test file "wheel"
        # fpath = '../test/data/io1-pe-203.stp'
        # CAX-IF test file "rocket"
        # fpath = '../test/data/s1-ug-203.stp'
    app = QApplication(sys.argv)
    frame = Model3DViewer(fpath=fpath)
    frame.show()
    sys.exit(app.exec_())

