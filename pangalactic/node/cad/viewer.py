#!/usr/bin/env python

##Copyright 2009-2014 Thomas Paviot (tpaviot@gmail.com)
##
##This file is part of pythonOCC.
##
##pythonOCC is free software: you can redistribute it and/or modify
##it under the terms of the GNU Lesser General Public License as published by
##the Free Software Foundation, either version 3 of the License, or
##(at your option) any later version.
##
##pythonOCC is distributed in the hope that it will be useful,
##but WITHOUT ANY WARRANTY; without even the implied warranty of
##MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
##GNU Lesser General Public License for more details.
##
##You should have received a copy of the GNU Lesser General Public License
##along with pythonOCC.  If not, see <http://www.gnu.org/licenses/>.

import os, platform, sys

from pangalactic.core         import state
from pangalactic.core.uberorb import orb
from pangalactic.node.buttons import MenuButton

from OCC.Display import OCCViewer
# new stuff for colorized viewer ...
from OCC.Core.TDocStd import TDocStd_Document
from OCC.Core.XCAFApp import XCAFApp_Application
from OCC.Core.XCAFDoc import (XCAFDoc_DocumentTool_ShapeTool,
                              XCAFDoc_DocumentTool_ColorTool)
from OCC.Core.STEPCAFControl import STEPCAFControl_Reader
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.TDF import TDF_LabelSequence, TDF_Label, TDF_Tool
from OCC.Core.TDataStd import TDataStd_Name, TDataStd_Name_GetID
from OCC.Core.TCollection import (TCollection_ExtendedString,
                                  TCollection_AsciiString)
from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB
from OCC.Core.TopLoc import TopLoc_Location
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCC.Display.SimpleGui import init_display
from OCC.Extend.DataExchange import (read_step_file_with_names_colors,
                                     read_stl_file)

from PyQt5 import QtGui, QtWidgets
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


def run_ext_3dviewer(fpath):
    if not fpath:
        return
    # init graphic display
    basename, fname = os.path.split(fpath)
    parts = fname.split('.')
    suffix = ''
    if len(parts) == 2:
        suffix = parts[1]
    if not suffix:
        # unidentifiable file type
        return
    display, start_display, add_menu, add_function_to_menu = init_display()
    if suffix in ['step', 'stp', 'p21']:
        shapes_labels_colors = read_step_file_with_names_colors(fpath)
        for shpt_lbl_color in shapes_labels_colors:
            label, c = shapes_labels_colors[shpt_lbl_color]
            display.DisplayColoredShape(shpt_lbl_color,
                                        color=Quantity_Color(c.Red(),
                                                             c.Green(),
                                                             c.Blue(),
                                                             Quantity_TOC_RGB))
    elif suffix == 'stl':
        stl_shape = read_stl_file(fpath)
        display.DisplayShape(stl_shape, update=True)
    display.FitAll()
    start_display()


# TODO: figure out what's going on with:
# "TKOpenGl | Type: Other | ID: 0 | Severity: Medium | Message:
#  OpenGl_Window::CreateWindow: window Visual is incomplete: no stencil buffer"
class QtBaseViewer(QtWidgets.QOpenGLWidget):
    ''' The base Qt Widget for an OCC viewer
    '''
    def __init__(self, parent=None):
        super().__init__(parent)
        self._display = None
        self._inited = False

        # enable Mouse Tracking
        self.setMouseTracking(True)
        # Strong focus
        self.setFocusPolicy(Qt.WheelFocus)

        # required for overpainting the widget
        ########################################
        ### NOTE: commented out this line and things still work AND no longer
        ### get the "QWidget::paintEngine: Should no longer be called" errors
        # self.setAttribute(Qt.WA_PaintOnScreen)
        ########################################
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAutoFillBackground(False)

    def GetHandle(self):
        ''' returns an the identifier of the GUI widget.
        It must be an integer
        '''
        win_id = self.winId()  ## this returns either an int or voitptr
        if type(win_id) is not int:  # cast to int using the int() funtion
            win_id = int(win_id)
        return win_id

    def resizeEvent(self, event):
        if self._inited:
            self._display.OnResize()


class QtViewer3DColor(QtBaseViewer):
    def __init__(self, *args):
        super().__init__(*args)
        self._drawbox = False
        self._zoom_area = False
        self._select_area = False
        self._inited = False
        self._leftisdown = False
        self._middleisdown = False
        self._rightisdown = False
        self._selection = None
        self._drawtext = True

    def init_shape_from_model(self, fpath, model_type='step'):
        """
        Load a STEP file into the viewer.

        Args:
            fpath (str):  path to a STEP file

        Keyword Args:
            model_type (str):  "step" or "stl"
        """
        self._display = OCCViewer.Viewer3d(self.GetHandle())
        self._display.Create()
        self._display.set_bg_gradient_color([206, 215, 222],
                                            [128, 128, 128])
        # new stuff for XCAF ...
        # create a handle to a document
        doc = TDocStd_Document(TCollection_ExtendedString("pythonocc-doc"))
        # Create the application
        app = XCAFApp_Application.GetApplication()
        app.NewDocument(TCollection_ExtendedString("MDTV-CAF"), doc)
        # Get root assembly
        # doc = h_doc
        self.h_shape_tool = XCAFDoc_DocumentTool_ShapeTool(doc.Main())
        h_color_tool = XCAFDoc_DocumentTool_ColorTool(doc.Main())
        # TODO:  figure out what "layer tool" and "material tool" do ...
        # h_layer_tool = XCAFDoc_DocumentTool_LayerTool(doc.Main())
        # h_mat_tool = XCAFDoc_DocumentTool_MaterialTool(doc.Main())
        if model_type in ['step', 'stl']:
            if model_type == 'step':
                step_reader = STEPCAFControl_Reader()
                step_reader.SetColorMode(True)
                step_reader.SetLayerMode(True)
                step_reader.SetNameMode(True)
                step_reader.SetMatMode(True)
                #########################

                status = step_reader.ReadFile(fpath)
                if status == IFSelect_RetDone:  # check status
                    # failsonly = False
                    # step_reader.PrintCheckLoad(failsonly, IFSelect_ItemsByEntity)
                    # step_reader.PrintCheckTransfer(failsonly, IFSelect_ItemsByEntity)
                    # ok = step_reader.TransferRoot(1)
                    # _nbs = step_reader.NbShapes()
                    # step_reader.TransferRoot(1)
                    # step_reader.NbShapes()
                    # step_shape = step_reader.Shape(1)
                    step_reader.Transfer(doc)
                else:
                    sys.exit(0)

                #########################
                # new stuff for XCAF ...
                # self.shape_tool = self.h_shape_tool.GetObject()
                self.shape_tool = self.h_shape_tool
                self.shape_tool.SetAutoNaming(True)
                # self.color_tool = h_color_tool.GetObject()
                self.color_tool = h_color_tool
                self.lvl = 0
                self.locs = []
                self.count = 0
                #########################

                self.getShapes()
            elif model_type == 'stl':
                stl_shape = read_stl_file(fpath)
                self._display.DisplayShape(stl_shape, update=True)
            self._display.SetModeShaded()
            # NOTE: "EnableAntiAliasing" raises a warning ...
            # self._display.EnableAntiAliasing()
            self._display.FitAll()
            self._inited = True
            # dict mapping keys to functions
            self._SetupKeyMap()
        else:
            # model is not a suppored type
            sys.exit(0)

    def get_label_name(self, label):
        entry = TCollection_AsciiString()
        TDF_Tool.Entry(label, entry)
        N = TDataStd_Name()
        label.FindAttribute(TDataStd_Name_GetID(), N)
        # n = N.GetObject()
        if N:
            return N.Get().PrintToString()
        return "No Name"

    def getShapes(self):
        labels = TDF_LabelSequence()
        # self.h_shape_tool.GetObject().GetFreeShapes(labels)
        self.h_shape_tool.GetFreeShapes(labels)
        self.count += 1
        # print()
        # print("Number of shapes at root :", labels.Length())
        # print()
        root = labels.Value(1)
        self.getSubShapes(root, None)

    def getSubShapes(self, lab, loc):
        self.count += 1
        # print("\n[%d] level %d, handling LABEL %s\n" % (self.count, self.lvl,
                                                    # self.get_label_name(lab)))
        # print()
        # print(lab.DumpToString())
        # print()
        # print("Is Assembly    :", self.shape_tool.IsAssembly(lab))
        # print("Is Free        :", self.shape_tool.IsFree(lab))
        # print("Is Shape       :", self.shape_tool.IsShape(lab))
        # print("Is Compound    :", self.shape_tool.IsCompound(lab))
        # print("Is Component   :", self.shape_tool.IsComponent(lab))
        # print("Is SimpleShape :", self.shape_tool.IsSimpleShape(lab))
        # print("Is Reference   :", self.shape_tool.IsReference(lab))

        # users = TDF_LabelSequence()
        # users_count = self.shape_tool.GetUsers(lab, users)
        # print("Nr Users       :", users_count)

        l_subss = TDF_LabelSequence()
        self.shape_tool.GetSubShapes(lab, l_subss)
        # print("Nb subshapes   :", l_subss.Length())
        l_comps = TDF_LabelSequence()
        self.shape_tool.GetComponents(lab, l_comps)
        # print("Nb components  :", l_comps.Length())
        # print()

        if self.shape_tool.IsAssembly(lab):
            l_c = TDF_LabelSequence()
            self.shape_tool.GetComponents(lab, l_c)
            for i in range(l_c.Length()):
                label = l_c.Value(i+1)
                if self.shape_tool.IsReference(label):
                    # print("\n########  reference label :", label)
                    label_reference = TDF_Label()
                    self.shape_tool.GetReferredShape(label, label_reference)
                    loc = self.shape_tool.GetLocation(label)
                    # print("    loc          :", loc)
                    # trans = loc.Transformation()
                    # print("    tran form    :", trans.Form())
                    # rot = trans.GetRotation()
                    # print("    rotation     :", rot)
                    # print("    X            :", rot.X())
                    # print("    Y            :", rot.Y())
                    # print("    Z            :", rot.Z())
                    # print("    W            :", rot.W())
                    # tran = trans.TranslationPart()
                    # print("    translation  :", tran)
                    # print("    X            :", tran.X())
                    # print("    Y            :", tran.Y())
                    # print("    Z            :", tran.Z())

                    self.locs.append(loc)
                    # print(">>>>")
                    self.lvl += 1
                    self.getSubShapes(label_reference, loc)
                    self.lvl -= 1
                    # print("<<<<")
                    self.locs.pop()

        elif self.shape_tool.IsSimpleShape(lab):
            # print("\n########  simpleshape label :", lab)
            shape = self.shape_tool.GetShape(lab)
            # print("    all assmbly locs:", self.locs)

            loc = TopLoc_Location()
            for i in range(len(self.locs)):
                # print("    take loc       :", self.locs[i])
                loc = loc.Multiplied(self.locs[i])

            # trans = loc.Transformation()
            # print("    FINAL loc    :")
            # print("    tran form    :", trans.Form())
            # rot = trans.GetRotation()
            # print("    rotation     :", rot)
            # print("    X            :", rot.X())
            # print("    Y            :", rot.Y())
            # print("    Z            :", rot.Z())
            # print("    W            :", rot.W())
            # tran = trans.TranslationPart()
            # print("    translation  :", tran)
            # print("    X            :", tran.X())
            # print("    Y            :", tran.Y())
            # print("    Z            :", tran.Z())
            shape = BRepBuilderAPI_Transform(shape,
                                             loc.Transformation()).Shape()
            c = Quantity_Color()
            color_set = False
            if (self.color_tool.GetInstanceColor(shape, 0, c) or
                    self.color_tool.GetInstanceColor(shape, 1, c) or
                    self.color_tool.GetInstanceColor(shape, 2, c)):
                for i in (0, 1, 2):
                    self.color_tool.SetInstanceColor(shape, i, c)
                color_set = True
                # n = c.Name(c.Red(), c.Green(), c.Blue())
                # print('    instance color Name & RGB: ', c, n, c.Red(),
                      # c.Green(), c.Blue())

            if not color_set:
                if (self.color_tool.GetColor(lab, 0, c) or
                        self.color_tool.GetColor(lab, 1, c) or
                        self.color_tool.GetColor(lab, 2, c)):
                    for i in (0, 1, 2):
                        self.color_tool.SetInstanceColor(shape, i, c)

                    # n = c.Name(c.Red(), c.Green(), c.Blue())
                    # print('    shape color Name & RGB: ', c, n, c.Red(),
                          # c.Green(), c.Blue())

            # n = c.Name(c.Red(), c.Green(), c.Blue())
            # print('    final color Name & RGB: ', n, c.Red(), c.Green(),
                  # c.Blue())
            # Display shape
            if c.Red() == 1.0 and c.Green() == 1.0 and c.Blue() == 0.0:
                self._display.DisplayColoredShape(shape, 'ORANGE')
            else:
                self._display.DisplayColoredShape(shape, c)

            for i in range(l_subss.Length()):
                lab = l_subss.Value(i+1)
                # print("\n########  simpleshape subshape label :", lab)
                shape = self.shape_tool.GetShape(lab)

                c = Quantity_Color()
                color_set = False
                if (self.color_tool.GetInstanceColor(shape, 0, c) or
                        self.color_tool.GetInstanceColor(shape, 1, c) or
                        self.color_tool.GetInstanceColor(shape, 2, c)):
                    for i in (0, 1, 2):
                        self.color_tool.SetInstanceColor(shape, i, c)
                    color_set = True
                    # n = c.Name(c.Red(), c.Green(), c.Blue())
                    # print('    instance color Name & RGB: ', c, n, c.Red(),
                          # c.Green(), c.Blue())

                if not color_set:
                    if (self.color_tool.GetColor(lab, 0, c) or
                            self.color_tool.GetColor(lab, 1, c) or
                            self.color_tool.GetColor(lab, 2, c)):
                        for i in (0, 1, 2):
                            self.color_tool.SetInstanceColor(shape, i, c)

                        # n = c.Name(c.Red(), c.Green(), c.Blue())
                        # print('    shape color Name & RGB: ', c, n, c.Red(),
                              # c.Green(), c.Blue())

                # n = c.Name(c.Red(), c.Green(), c.Blue())
                # print('    color Name & RGB: ', c, n, c.Red(), c.Green(),
                #       c.Blue())
                # Display shape
                self._display.DisplayColoredShape(shape, c)

    def _SetupKeyMap(self):
        def set_shade_mode():
            self._display.DisableAntiAliasing()
            self._display.SetModeShaded()

        self._key_map = {ord('W'): self._display.SetModeWireFrame,
                         ord('S'): set_shade_mode,
                         ord('A'): self._display.EnableAntiAliasing,
                         ord('B'): self._display.DisableAntiAliasing,
                         ord('H'): self._display.SetModeHLR,
                         ord('F'): self._display.FitAll,
                         ord('G'): self._display.SetSelectionMode
                         }

    def keyPressEvent(self, event):
        code = event.key()
        if code in self._key_map:
            self._key_map[code]()

    def Test(self):
        if self._inited:
            self._display.Test()

    def focusInEvent(self, event):
        if self._inited:
            self.makeCurrent()
            self._display.Repaint()

    def focusOutEvent(self, event):
        if self._inited:
            self.makeCurrent()
            self._display.Repaint()

    def paintEvent(self, event):
        if self._inited:
            self.makeCurrent()
            self._display.Context.UpdateCurrentViewer()
            # important to allow overpainting of the OCC OpenGL context in Qt
            ## -> but this gives an error message in Windows
            # self.swapBuffers()

    def resizeGL(self, width, height):
        self.setupViewport(width, height)

    def ZoomAll(self, evt):
        if self._inited:
            self._display.FitAll()

    def wheelEvent(self, event):
        if self._inited:
            delta = event.angleDelta().y()
            if delta > 0:
                zoom_factor = 1.1
            else:
                zoom_factor = 0.9
            self.makeCurrent()
            self._display.Repaint()
            self._display.ZoomFactor(zoom_factor)

    def dragMoveEvent(self, event):
        pass

    def mousePressEvent(self, event):
        if self._inited:
            self.setFocus()
            self.dragStartPos = point(event.pos())
            self._display.StartRotation(self.dragStartPos.x, self.dragStartPos.y)

    def mouseReleaseEvent(self, event):
        if self._inited:
            pt = point(event.pos())
            modifiers = event.modifiers()
            if event.button() == Qt.LeftButton:
                pt = point(event.pos())
                if self._select_area:
                    if self._drawbox:
                        [Xmin, Ymin, dx, dy] = self._drawbox
                        self._display.SelectArea(Xmin, Ymin, Xmin+dx, Ymin+dy)
                    self._select_area = False
                else:
                    # multiple select if shift is pressed
                    if modifiers == Qt.ShiftModifier:
                        self._display.ShiftSelect(pt.x, pt.y)
                    else:
                        # single select otherwise
                        self._display.Select(pt.x, pt.y)
            elif event.button() == Qt.RightButton:
                if self._zoom_area:
                    if self._drawbox:
                        [Xmin, Ymin, dx, dy] = self._drawbox
                        self._display.ZoomArea(Xmin, Ymin, Xmin+dx, Ymin+dy)
                    self._zoom_area = False

    def DrawBox(self, event):
        tolerance = 2
        pt = point(event.pos())
        dx = pt.x - self.dragStartPos.x
        dy = pt.y - self.dragStartPos.y
        if abs(dx) <= tolerance and abs(dy) <= tolerance:
            return
        self._drawbox = [self.dragStartPos.x, self.dragStartPos.y, dx, dy]
        self.update()

    def mouseMoveEvent(self, evt):
        if self._inited:
            pt = point(evt.pos())
            buttons = int(evt.buttons())
            modifiers = evt.modifiers()
            # ROTATE
            if (buttons == Qt.LeftButton
                and not modifiers == Qt.ShiftModifier):
                dx = pt.x - self.dragStartPos.x
                dy = pt.y - self.dragStartPos.y
                self._display.Rotation(pt.x, pt.y)
                self._drawbox = False
            # DYNAMIC ZOOM
            elif (buttons == Qt.RightButton
                  and not modifiers == Qt.ShiftModifier):
                self.makeCurrent()
                self._display.Repaint()
                self._display.DynamicZoom(abs(self.dragStartPos.x),
                                          abs(self.dragStartPos.y),
                                          abs(pt.x), abs(pt.y))
                self.dragStartPos.x = pt.x
                self.dragStartPos.y = pt.y
                self._drawbox = False
            # PAN
            elif buttons == Qt.MidButton:
                dx = pt.x - self.dragStartPos.x
                dy = pt.y - self.dragStartPos.y
                self.dragStartPos.x = pt.x
                self.dragStartPos.y = pt.y
                self._display.Pan(dx, -dy)
                self._drawbox = False
            # DRAW BOX
            # ZOOM WINDOW
            elif (buttons == Qt.RightButton
                  and modifiers == Qt.ShiftModifier):
                self._zoom_area = True
                self.DrawBox(evt)
            # SELECT AREA
            elif (buttons == Qt.LeftButton
                  and modifiers == Qt.ShiftModifier):
                self._select_area = True
                self.DrawBox(evt)
            else:
                self._drawbox = False
                self._display.MoveTo(pt.x, pt.y)
        else:
            evt.ignore()


class Model3DViewer(QtWidgets.QMainWindow):
    def __init__(self, step_file=None, stl_file=None, parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle(self.tr("3D Model Viewer"))
        self.init_viewer_3d()
        self.viewer_in_use = False
        self.resize(800, 600)
        self.open_step_file_action = self.create_action("Open a STEP file...",
                                   slot=self.open_step_file,
                                   tip="View a CAD model from a STEP file")
        self.open_stl_file_action = self.create_action("Open an STL file...",
                                   slot=self.open_stl_file,
                                   tip="View a model from an STL file")
        self.export_to_image_action = self.create_action("Export to image...",
                                   slot=self.export_to_image,
                                   tip="Export current view to image...")
        self.export_to_image_action.setEnabled(False)
        self.toolbar = self.addToolBar("Actions")
        self.toolbar.setObjectName('ActionsToolBar')
        import_icon_file = 'open' + state['icon_type']
        self.icon_dir = state.get('icon_dir',
                             os.path.join(getattr(orb, 'home', ''), 'icons'))
        import_icon_path = os.path.join(self.icon_dir, import_icon_file)
        import_actions = [self.open_step_file_action,
                          self.open_stl_file_action]
        import_button = MenuButton(QtGui.QIcon(import_icon_path),
                                   tooltip='Import Data or Objects',
                                   actions=import_actions, parent=self)
        self.toolbar.addWidget(import_button)
        export_icon_file = 'save' + state['icon_type']
        export_icon_path = os.path.join(self.icon_dir, export_icon_file)
        export_actions = [self.export_to_image_action]
        self.export_button = MenuButton(QtGui.QIcon(export_icon_path),
                                   tooltip='Export Data or Objects',
                                   actions=export_actions, parent=self)
        self.toolbar.addWidget(self.export_button)
        self.loaded_file = step_file or stl_file
        if step_file:
            self.load_step_file(step_file)
        elif stl_file:
            self.load_stl_file(stl_file)

    def create_action(self, text, icon=None, slot=None, tip=None):
        action = QtWidgets.QAction(text, self)
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

    def init_viewer_3d(self):
        if getattr(self, 'qt_viewer_3d', None):
            # close existing viewer
            self.qt_viewer_3d.setAttribute(Qt.WA_DeleteOnClose)
            self.qt_viewer_3d.parent = None
            self.qt_viewer_3d.close()
            self.qt_viewer_3d = None
        self.qt_viewer_3d = QtViewer3DColor(self)
        viewer_layout = QtWidgets.QHBoxLayout()
        viewer_layout.setContentsMargins(0, 0, 0, 0)
        viewer_layout.setSpacing(0)
        self.qt_viewer_3d.setLayout(viewer_layout)
        self.qt_viewer_3d.resize(800, 600)
        self.setCentralWidget(self.qt_viewer_3d)

    def load_step_file(self, fpath):
        if self.viewer_in_use:
            self.init_viewer_3d()
        self.qt_viewer_3d.init_shape_from_model(fpath, model_type='step')
        self.loaded_file = fpath
        if hasattr(self, 'export_to_image_action'):
            self.export_to_image_action.setEnabled(True)

    def load_stl_file(self, fpath):
        if self.viewer_in_use:
            self.init_viewer_3d()
        self.qt_viewer_3d.init_shape_from_model(fpath, model_type='stl')
        self.loaded_file = fpath
        if hasattr(self, 'export_to_image_action'):
            self.export_to_image_action.setEnabled(True)

    def export_to_image(self):
        fname = 'cad_view.png'
        fpath, filters = QtWidgets.QFileDialog.getSaveFileName(
                                    self, 'Export to Image File',
                                    fname)
        if fpath:
            orb.log.debug('* exporting to image file...')
            self.qt_viewer_3d._display.ExportToImage(fpath)
            orb.log.debug('  done.')
        else:
            orb.log.debug('* no path for export, aborting.')
            return

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
        fpath, filters = QtWidgets.QFileDialog.getOpenFileName(
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
                self.init_viewer_3d()
            self.qt_viewer_3d.init_shape_from_model(fpath, model_type='step')
            if hasattr(self, 'export_to_image_action'):
                self.export_to_image_action.setEnabled(True)
        else:
            return

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
        fpath, filters = QtWidgets.QFileDialog.getOpenFileName(
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
                self.init_viewer_3d()
            self.qt_viewer_3d.init_shape_from_model(fpath, model_type='stl')
            if hasattr(self, 'export_to_image_action'):
                self.export_to_image_action.setEnabled(True)
        else:
            return


if __name__ == "__main__":
    # Test file:  cubical electronic package
    # fpath = '../../../test/data/cad/a7959_asm.p21'
    # CAX-IF test file "wheel"
    # fpath = '../../../test/data/io1-pe-203.stp'
    # CAX-IF test file "rocket"
    # fpath = '../../../test/data/s1-ug-203.stp'
    # CAX-IF test file "bracket" copied into current dir.
    fpath = 'as1-oc-214.stp'
    app = QtWidgets.QApplication(sys.argv)
    frame = Model3DViewer(step_file=fpath)
    frame.show()
    sys.exit(app.exec_())

