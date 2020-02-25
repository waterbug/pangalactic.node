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
from OCC.IFSelect import IFSelect_RetDone, IFSelect_ItemsByEntity
from OCC.STEPControl import STEPControl_Reader

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


class QtViewer3D(QtBaseViewer):
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
        step_reader = STEPControl_Reader()
        status = step_reader.ReadFile(fpath)
        if status == IFSelect_RetDone:  # check status
            failsonly = False
            step_reader.PrintCheckLoad(failsonly, IFSelect_ItemsByEntity)
            step_reader.PrintCheckTransfer(failsonly, IFSelect_ItemsByEntity)

            # ok = step_reader.TransferRoot(1)
            # _nbs = step_reader.NbShapes()
            step_reader.TransferRoot(1)
            step_reader.NbShapes()
            step_shape = step_reader.Shape(1)
        else:
            sys.exit(0)
        self._display.DisplayShape(step_shape, update=True)
        self._display.SetModeShaded()
        self._display.EnableAntiAliasing()
        self._inited = True
        # dict mapping keys to functions
        self._SetupKeyMap()

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


def Test3d():
    class AppFrame(QtWidgets.QWidget):
        def __init__(self, parent=None):
            QtWidgets.QWidget.__init__(self, parent)
            self.setWindowTitle(self.tr("test viewer"))
            self.resize(800, 600)
            self.canva = QtViewer3D(self)
            mainLayout = QtWidgets.QHBoxLayout()
            mainLayout.addWidget(self.canva)
            mainLayout.setContentsMargins(0, 0, 0, 0)
            self.setLayout(mainLayout)

        def runTests(self):
            self.canva._display.Test()

    app = QtWidgets.QApplication(sys.argv)
    frame = AppFrame()
    frame.show()
    # Test file:  cubical electronic package
    # frame.canva.init_shape_from_STEP('../../../test/data/cad/a7959_asm.p21')
    # CAX-IF test file "wheel"
    # frame.canva.init_shape_from_STEP('../../../test/data/io1-pe-203.stp')
    # CAX-IF test file "rocket"
    # frame.canva.init_shape_from_STEP('../../../test/data/s1-ug-203.stp')
    # CAX-IF test file "bracket"
    frame.canva.init_shape_from_STEP('../../../test/data/as1-id-203.stp')
    # frame.runTests()
    sys.exit(app.exec_())

if __name__ == "__main__":
    Test3d()

