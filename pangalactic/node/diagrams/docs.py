"""
A canvas-style document editor example
"""
# NOTE: divisions fixed so probably don't need old_div ...
# from past.utils import old_div
import functools, os, random, sys

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtPrintSupport import QPrintDialog, QPrinter

# pangalactic
from pangalactic.core.meta            import asciify
from pangalactic.core.uberorb         import orb
from pangalactic.node.diagrams.shapes import TextItem

# NOTE: not using native Mac menus ...
# MAC = True
# try:
    # from PyQt5.QtGui import qt_mac_set_native_menubar
# except ImportError:
    # MAC = False

# A4 in points
#PAGE_SIZE = (595, 842)
# US Letter in points
PAGE_SIZE = (612, 792)
POINT_SIZE = 10
MagicNumber = 0x70616765
FileVersion = 1


class BoxItem(QtWidgets.QGraphicsItem):

    def __init__(self, position, scene, style=Qt.SolidLine,
                 rect=None):
        super().__init__()
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsSelectable |
                      QtWidgets.QGraphicsItem.ItemIsMovable |
                      QtWidgets.QGraphicsItem.ItemIsFocusable)
        if rect is None:
            rect = QtCore.QRectF(-10 * POINT_SIZE, -POINT_SIZE, 20 * POINT_SIZE,
                          2 * POINT_SIZE)
        self.rect = rect
        self.style = style
        self.setPos(position)
        scene.clearSelection()
        scene.addItem(self)
        self.setSelected(True)
        self.setFocus()

    def parentWidget(self):
        return self.scene().views()[0]

    def boundingRect(self):
        return self.rect.adjusted(-2, -2, 2, 2)

    def paint(self, painter, option, widget):
        pen = QtGui.QPen(self.style)
        pen.setColor(Qt.black)
        pen.setWidth(1)
        if option.state & QtWidgets.QStyle.State_Selected:
            pen.setColor(Qt.blue)
        painter.setPen(pen)
        painter.drawRect(self.rect)

    def itemChange(self, change, variant):
        return QtWidgets.QGraphicsItem.itemChange(self, change, variant)

    def contextMenuEvent(self, event):
        wrapped = []
        menu = QtWidgets.QMenu(self.parentWidget())
        for text, param in (
                ("&Solid", Qt.SolidLine),
                ("&Dashed", Qt.DashLine),
                ("D&otted", Qt.DotLine),
                ("D&ashDotted", Qt.DashDotLine),
                ("DashDo&tDotted", Qt.DashDotDotLine)):
            wrapper = functools.partial(self.setStyle, param)
            wrapped.append(wrapper)
            menu.addAction(text, wrapper)
        menu.exec_(event.screenPos())

    def setStyle(self, style):
        self.style = style
        self.update()

    def keyPressEvent(self, event):
        factor = POINT_SIZE // 4
        changed = False
        if event.modifiers() & Qt.ShiftModifier:
            if event.key() == Qt.Key_Left:
                self.rect.setRight(self.rect.right() - factor)
                changed = True
            elif event.key() == Qt.Key_Right:
                self.rect.setRight(self.rect.right() + factor)
                changed = True
            elif event.key() == Qt.Key_Up:
                self.rect.setBottom(self.rect.bottom() - factor)
                changed = True
            elif event.key() == Qt.Key_Down:
                self.rect.setBottom(self.rect.bottom() + factor)
                changed = True
        if changed:
            self.update()
        else:
            QtWidgets.QGraphicsItem.keyPressEvent(self, event)


class GraphicsView(QtWidgets.QGraphicsView):

    def __init__(self, edit_mode=True, parent=None):
        super().__init__(parent)
        self.setDragMode(QtWidgets.QGraphicsView.RubberBandDrag)
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setRenderHint(QtGui.QPainter.TextAntialiasing)

    def wheelEvent(self, event):
        factor = 1.41 ** (-event.angleDelta().y() / 240.0)
        self.scale(factor, factor)


class ReadOnlyGraphicsView(QtWidgets.QGraphicsView):

    def __init__(self, edit_mode=True, parent=None):
        super().__init__(parent)
        self.setDragMode(QtWidgets.QGraphicsView.RubberBandDrag)
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setRenderHint(QtGui.QPainter.TextAntialiasing)

    def wheelEvent(self, event):
        factor = 1.41 ** (-event.angleDelta().y() / 240.0)
        self.scale(factor, factor)

    def mouseMoveEvent(self, event):
        event.accept()

    def mousePressEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()


class DocForm(QtWidgets.QDialog):

    def __init__(self, scene=None, edit_mode=True, parent=None):
        super().__init__(parent)
        self.scene = scene
        self.edit_mode = edit_mode
        self.filename = ''
        self.copiedItem = QtCore.QByteArray()
        self.pasteOffset = 5
        self.prev_point = QtCore.QPoint()
        self.addOffset = 5
        self.borders = []
        self.create_widgets()
        self.layout_widgets()
        fm = QtGui.QFontMetrics(self.font())
        screen_res = QtWidgets.QApplication.desktop().screenGeometry()
        height = min(screen_res.height() - 100, self.scene.height() + 50)
        self.resize(self.scene.width() + fm.width(" Delete... ") + 100,
                    height)
        self.move(0, 0)
        self.setWindowTitle("Page Designer")

    def create_widgets(self):
        self.printer = QPrinter(QPrinter.HighResolution)
        self.printer.setPageSize(QPrinter.Letter)
        if self.edit_mode:
            self.view = GraphicsView()
        else:
            self.view = ReadOnlyGraphicsView()
        if self.scene is None:
            self.scene = QtWidgets.QGraphicsScene(self)
            self.scene.setSceneRect(0, 0, PAGE_SIZE[0], PAGE_SIZE[1])
        self.view.setScene(self.scene)
        self.view.centerOn(0, 0)
        # self.addBorders()
        self.buttonLayout = QtWidgets.QVBoxLayout()
        functions = [("Save as Image", self.write_image),
                     ("Print...", self.print_),
                     ("Quit", self.accept)]
        if self.edit_mode:
            functions += [
                ("Add &Box", self.addBox),
                ("Add &Object", self.add_object),
                ("Add Pi&xmap", self.addPixmap),
                ("&Copy", self.copy),
                ("C&ut", self.cut),
                ("&Paste", self.paste),
                ("&Delete...", self.delete),
                # ("&Rotate", self.rotate),  # rotate is broken
                ("&Open...", self.open),
                ("&Save", self.save)]
        for text, slot in functions:
            button = QtWidgets.QPushButton(text)
            # if not MAC:
                # button.setFocusPolicy(Qt.NoFocus)
            button.clicked.connect(slot)
            self.buttonLayout.addWidget(button)
        self.buttonLayout.addStretch()

    def layout_widgets(self):
        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(self.view, 1)
        layout.addLayout(self.buttonLayout)
        self.setLayout(layout)

    def addBorders(self):
        self.borders = []
        rect = QtCore.QRectF(0, 0, PAGE_SIZE[0], PAGE_SIZE[1])
        self.borders.append(self.scene.addRect(rect, Qt.green))
        margin = 5.25 * POINT_SIZE
        self.borders.append(self.scene.addRect(
                rect.adjusted(margin, margin, -margin, -margin),
                Qt.green))

    def removeBorders(self):
        while self.borders:
            item = self.borders.pop()
            self.scene.removeItem(item)
            del item

    def reject(self):
        self.accept()

    def accept(self):
        # self.offerSave()
        QtWidgets.QDialog.accept(self)

    # def offerSave(self):
        # if (Dirty and
            # QtWidgets.QMessageBox.question(self,
                # "Page Designer - Unsaved Changes",
                # "Save unsaved changes?",
                # QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No) ==
                # QtWidgets.QMessageBox.Yes):
            # self.save()

    def position(self):
        """
        Return a random point in the scene.
        """
        point = self.mapFromGlobal(QtGui.QCursor.pos())
        if not self.view.geometry().contains(point):
            coord = random.randint(36, 144)
            point = QtCore.QPoint(coord, coord)
        else:
            if point == self.prev_point:
                point += QtCore.QPoint(self.addOffset, self.addOffset)
                self.addOffset += 5
            else:
                self.addOffset = 5
                self.prev_point = point
        return self.view.mapToScene(point)

    def addBox(self):
        BoxItem(self.position(), self.scene)

    def add_object(self, obj, pos=None):
        self.scene.addItem(obj)
        if pos:
            obj.setPos(pos)

    def addPixmap(self):
        path = (QtCore.QFileInfo(self.filename).path()
                if self.filename else ".")
        fname, f = QtWidgets.QFileDialog.getOpenFileName(self,
                "Page Designer - Add Pixmap", path,
                "Pixmap Files (*.bmp *.jpg *.png *.xpm)")
        if not fname:
            return
        self.createPixmapItem(QtGui.QPixmap(fname), self.position())

    def createPixmapItem(self, pixmap, position):
        item = QtWidgets.QGraphicsPixmapItem(pixmap)
        item.setFlags(QtWidgets.QGraphicsItem.ItemIsSelectable |
                      QtWidgets.QGraphicsItem.ItemIsMovable)
        item.setPos(position)
        self.scene.clearSelection()
        self.scene.addItem(item)
        item.setSelected(True)

    def selectedItem(self):
        items = self.scene.selectedItems()
        if len(items) == 1:
            return items[0]
        return None

    def copy(self):
        item = self.selectedItem()
        if item is None:
            return
        self.copiedItem.clear()
        self.pasteOffset = 5
        stream = QtCore.QDataStream(self.copiedItem,
                                    QtCore.QIODevice.WriteOnly)
        self.writeItemToStream(stream, item)

    def cut(self):
        item = self.selectedItem()
        if item is None:
            return
        self.copy()
        self.scene.removeItem(item)
        del item

    def paste(self):
        if self.copiedItem.isEmpty():
            return
        stream = QtCore.QDataStream(self.copiedItem, QtCore.QIODevice.ReadOnly)
        self.readItemFromStream(stream, self.pasteOffset)
        self.pasteOffset += 5

    def rotate(self):
        for item in self.scene.selectedItems():
            item.rotate(30)

    def delete(self):
        items = self.scene.selectedItems()
        if (len(items) and QtWidgets.QMessageBox.question(self,
                "Page Designer - Delete",
                "Delete {0} item{1}?".format(len(items),
                "s" if len(items) != 1 else ""),
                QtWidgets.QMessageBox.Yes|QtWidgets.QMessageBox.No) ==
                QtWidgets.QMessageBox.Yes):
            while items:
                item = items.pop()
                self.scene.removeItem(item)
                del item

    def write_image(self):
        fpath = os.path.join(orb.home, 'diagram.png')
        fout, filters = QtWidgets.QFileDialog.getSaveFileName(self,
                                "Save As Image", fpath, "PNG (*.png)")
        if fout:
            self.scene.clearSelection()
            image = QtGui.QImage(self.scene.sceneRect().size().toSize(),
                                 QtGui.QImage.Format_ARGB32)
            image.fill(Qt.white)
            painter = QtGui.QPainter(image)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.setRenderHint(QtGui.QPainter.TextAntialiasing)
            self.removeBorders()
            self.scene.render(painter)
            painter.end()
            image.save(fout)

    def print_(self):
        dialog = QPrintDialog(self.printer)
        if dialog.exec_():
            painter = QtGui.QPainter(self.printer)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.setRenderHint(QtGui.QPainter.TextAntialiasing)
            self.scene.clearSelection()
            self.removeBorders()
            self.scene.render(painter)

    def open(self):
        # self.offerSave()
        path = (QtCore.QFileInfo(self.filename).path()
                if self.filename else ".")
        fname, f = QtWidgets.QFileDialog.getOpenFileName(self,
                "Page Designer - Open", path,
                "Page Designer Files (*.pgd)")
        if not fname:
            return
        self.filename = str(fname)   # fname is unicode; make str
        file = None
        try:
            file = QtCore.QFile(self.filename)
            if not file.open(QtCore.QIODevice.ReadOnly):
                raise IOError(str(file.errorString()))
            items = list(self.scene.items())
            while items:
                item = items.pop()
                self.scene.removeItem(item)
                del item
            # self.addBorders()
            stream = QtCore.QDataStream(file)
            stream.setVersion(QtCore.QDataStream.Qt_4_2)
            magic = stream.readInt32()
            if magic != MagicNumber:
                raise IOError("not a valid .pgd file")
            fileVersion = stream.readInt16()
            if fileVersion != FileVersion:
                raise IOError("unrecognised .pgd file version")
            while not file.atEnd():
                self.readItemFromStream(stream)
        except IOError as err:
            QtWidgets.QMessageBox.warning(self, "Page Designer -- Open Error",
                    "Failed to open {0}: {1}".format(self.filename, err))
        finally:
            if file is not None:
                file.close()

    def save(self):
        if not self.filename:
            fpath = "."
            fout = QtWidgets.QFileDialog.getSaveFileName(self,
                    "Page Designer - Save As", fpath,
                    "Page Designer Files (*.pgd)")
            if not fout:
                return
            self.filename = asciify(fout[0])
        file = None
        try:
            print('file name is: "%s"' % str(self.filename))
            file = QtCore.QFile(self.filename)
            if not file.open(QtCore.QIODevice.WriteOnly):
                raise IOError(str(file.errorString()))
            self.scene.clearSelection()
            stream = QtCore.QDataStream(file)
            stream.setVersion(QtCore.QDataStream.Qt_4_2)
            stream.writeInt32(MagicNumber)
            stream.writeInt16(FileVersion)
            for item in self.scene.items():
                self.writeItemToStream(stream, item)
        except IOError as err:
            QtWidgets.QMessageBox.warning(self, "Page Designer -- Save Error",
                    "Failed to save {0}: {1}".format(self.filename, err))
        finally:
            if file is not None:
                file.close()

    def readItemFromStream(self, stream, offset=0):
        type = ''
        position = QtCore.QPointF()
        matrix = QtGui.QTransform()
        stream >> type >> position >> matrix
        if offset:
            position += QtCore.QPointF(offset, offset)
        if type == "Text":
            text = ''
            font = QtGui.QFont()
            stream >> text >> font
            TextItem(text, position, self.scene, font, matrix)
        elif type == "Box":
            rect = QtCore.QRectF()
            stream >> rect
            style = Qt.PenStyle(stream.readInt16())
            BoxItem(position, self.scene, style, rect, matrix)
        elif type == "Pixmap":
            pixmap = QtGui.QPixmap()
            stream >> pixmap
            self.createPixmapItem(pixmap, position, matrix)

    def writeItemToStream(self, stream, item):
        if isinstance(item, QtWidgets.QGraphicsTextItem):
            stream << "Text" << item.pos() 
            stream << item.matrix() << item.toPlainText() << item.font()
        elif isinstance(item, QtWidgets.QGraphicsPixmapItem):
            stream << "Pixmap" << item.pos()
            stream << item.matrix() << item.pixmap()
        elif isinstance(item, BoxItem):
            stream << "Box" << item.pos()
            stream << item.matrix() << item.rect
            stream.writeInt16(item.style)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    form = DocForm()
    rect = QtWidgets.QApplication.desktop().availableGeometry()
    form.resize(int(rect.width() * 0.6), int(rect.height() * 0.9))
    form.show()
    app.exec_()

