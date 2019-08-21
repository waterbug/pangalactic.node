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

import sys

from OCC.Display import OCCViewer
######################################
# old stuff from monochrome viewer ...
# from OCC.IFSelect import IFSelect_RetDone, IFSelect_ItemsByEntity
# from OCC.STEPControl import STEPControl_Reader
######################################
# new stuff for colorized viewer ...
from OCC.Core.TDocStd import Handle_TDocStd_Document
from OCC.Core.XCAFApp import XCAFApp_Application
from OCC.Core.XCAFDoc import (XCAFDoc_DocumentTool_ShapeTool,
                              XCAFDoc_DocumentTool_ColorTool)
from OCC.Core.STEPCAFControl import STEPCAFControl_Reader
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.TDF import TDF_LabelSequence, TDF_Label, TDF_Tool
from OCC.Core.TDataStd import Handle_TDataStd_Name, TDataStd_Name_GetID
from OCC.Core.TCollection import TCollection_ExtendedString, TCollection_AsciiString
from OCC.Core.Quantity import Quantity_Color
from OCC.Core.TopLoc import TopLoc_Location
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform

from PyQt5 import QtCore, QtOpenGL, QtWidgets


class point(object):
    def __init__(self, obj=None):
        self.x = 0
        self.y = 0
        if obj is not None:
            self.set(obj)

    def set(self, obj):
        self.x = obj.x()
        self.y = obj.y()


class QtBaseViewer(QtOpenGL.QGLWidget):
    ''' The base Qt Widget for an OCC viewer
    '''
    def __init__(self, parent=None):
        QtOpenGL.QGLWidget.__init__(self, parent)
        self._display = None
        self._inited = False

        # enable Mouse Tracking
        self.setMouseTracking(True)
        # Strong focus
        self.setFocusPolicy(QtCore.Qt.WheelFocus)

        # required for overpainting the widget
        self.setAttribute(QtCore.Qt.WA_PaintOnScreen)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground)
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
    def __init__(self, *kargs):
        QtBaseViewer.__init__(self, *kargs)
        self._drawbox = False
        self._zoom_area = False
        self._select_area = False
        self._inited = False
        self._leftisdown = False
        self._middleisdown = False
        self._rightisdown = False
        self._selection = None
        self._drawtext = True

    def init_shape_from_STEP(self, fpath):
        """
        Load a STEP file into the viewer.

        @param fpath:  path to a STEP file
        @type  fpath:  `str`
        """
        self._display = OCCViewer.Viewer3d(self.GetHandle())
        self._display.Create()
        # background gradient
        # self._display.set_bg_gradient_color(206, 215, 222, 128, 128, 128)

        #########################
        # new stuff for XCAF ...
        # create a handle to a document
        doc = Handle_TDocStd_Document()
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
        # self._display.DisplayShape(step_shape, update=True)
        self._display.SetModeShaded()
        self._display.EnableAntiAliasing()
        self._display.FitAll()
        self._inited = True
        # dict mapping keys to functions
        self._SetupKeyMap()

    def get_label_name(self, label):
        entry = TCollection_AsciiString()
        TDF_Tool.Entry(label, entry)
        N = Handle_TDataStd_Name()
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

        users = TDF_LabelSequence()
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
                    trans = loc.Transformation()
                    # print("    tran form    :", trans.Form())
                    rot = trans.GetRotation()
                    # print("    rotation     :", rot)
                    # print("    X            :", rot.X())
                    # print("    Y            :", rot.Y())
                    # print("    Z            :", rot.Z())
                    # print("    W            :", rot.W())
                    tran = trans.TranslationPart()
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

            trans = loc.Transformation()
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
            # print('    final color Name & RGB: ', c, n, c.Red(), c.Green(),
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
            self._display.Repaint()

    def focusOutEvent(self, event):
        if self._inited:
            self._display.Repaint()

    def paintEvent(self, event):
        if self._inited:
            self._display.Context.UpdateCurrentViewer()
            # important to allow overpainting of the OCC OpenGL context in Qt
            self.swapBuffers()

    def resizeGL(self, width, height):
        self.setupViewport(width, height)

    def ZoomAll(self, evt):
        self._display.FitAll()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta > 0:
            zoom_factor = 1.1
        else:
            zoom_factor = 0.9
        self._display.Repaint()
        self._display.ZoomFactor(zoom_factor)

    def dragMoveEvent(self, event):
        pass

    def mousePressEvent(self, event):
        self.setFocus()
        self.dragStartPos = point(event.pos())
        self._display.StartRotation(self.dragStartPos.x, self.dragStartPos.y)

    def mouseReleaseEvent(self, event):
        pt = point(event.pos())
        modifiers = event.modifiers()

        if event.button() == QtCore.Qt.LeftButton:
            pt = point(event.pos())
            if self._select_area:
                [Xmin, Ymin, dx, dy] = self._drawbox
                self._display.SelectArea(Xmin, Ymin, Xmin+dx, Ymin+dy)
                self._select_area = False
            else:
                # multiple select if shift is pressed
                if modifiers == QtCore.Qt.ShiftModifier:
                    self._display.ShiftSelect(pt.x, pt.y)
                else:
                    # single select otherwise
                    self._display.Select(pt.x, pt.y)
        elif event.button() == QtCore.Qt.RightButton:
            if self._zoom_area:
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
        pt = point(evt.pos())
        buttons = int(evt.buttons())
        modifiers = evt.modifiers()
        # ROTATE
        if (buttons == QtCore.Qt.LeftButton
            and not modifiers == QtCore.Qt.ShiftModifier):
            dx = pt.x - self.dragStartPos.x
            dy = pt.y - self.dragStartPos.y
            self._display.Rotation(pt.x, pt.y)
            self._drawbox = False
        # DYNAMIC ZOOM
        elif (buttons == QtCore.Qt.RightButton
              and not modifiers == QtCore.Qt.ShiftModifier):
            self._display.Repaint()
            self._display.DynamicZoom(abs(self.dragStartPos.x),
                                      abs(self.dragStartPos.y),
                                      abs(pt.x), abs(pt.y))
            self.dragStartPos.x = pt.x
            self.dragStartPos.y = pt.y
            self._drawbox = False
        # PAN
        elif buttons == QtCore.Qt.MidButton:
            dx = pt.x - self.dragStartPos.x
            dy = pt.y - self.dragStartPos.y
            self.dragStartPos.x = pt.x
            self.dragStartPos.y = pt.y
            self._display.Pan(dx, -dy)
            self._drawbox = False
        # DRAW BOX
        # ZOOM WINDOW
        elif (buttons == QtCore.Qt.RightButton
              and modifiers == QtCore.Qt.ShiftModifier):
            self._zoom_area = True
            self.DrawBox(evt)
        # SELECT AREA
        elif (buttons == QtCore.Qt.LeftButton
              and modifiers == QtCore.Qt.ShiftModifier):
            self._select_area = True
            self.DrawBox(evt)
        else:
            self._drawbox = False
            self._display.MoveTo(pt.x, pt.y)


class STEP3DViewer(QtWidgets.QWidget):
    def __init__(self, step_file=None, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.setWindowTitle(self.tr("STEP 3D viewer"))
        self.canva = QtViewer3DColor(self)
        mainLayout = QtWidgets.QHBoxLayout()
        mainLayout.addWidget(self.canva)
        mainLayout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(mainLayout)
        self.resize(800, 600)
        self.show()
        if step_file:
            self.load_file(step_file)

    def load_file(self, fpath):
        self.canva.init_shape_from_STEP(fpath)


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
    frame = STEP3DViewer(fpath)
    frame.show()
    sys.exit(app.exec_())

