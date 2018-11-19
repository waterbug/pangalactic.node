from builtins import range
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

from louie import dispatcher


class SplashScreen(QtWidgets.QSplashScreen):
    def __init__(self, pixmap, center_point=None, font_size=None):
        QtWidgets.QSplashScreen.__init__(self)
        self._pixmap = pixmap
        self._color = Qt.black
        self._message = ''
        self._alignment = Qt.AlignLeft
        self._center_point = center_point
        self.setWindowFlags(Qt.FramelessWindowHint |
                            Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFixedSize(self._pixmap.size())
        font = QtGui.QFont(self.font())
        font_size = font_size or font.pointSize()
        font.setPointSize(font_size)
        font.setBold(True)
        self.setFont(font)
        self.setMask(self._pixmap.mask())
        if center_point:
            x = center_point.x() - pixmap.width()//2
            y = center_point.y() - pixmap.height()//2
            self.move(QtCore.QPoint(x,y))
        else:
            self.move(QtCore.QPoint(100,100))
        dispatcher.connect(self.show_msg, 'splash message')

    def clearMessage(self):
        self._message = ''
        self.repaint()

    def show_msg(self, message=''):
        QtWidgets.QApplication.processEvents()
        self.showMessage(message)
        QtWidgets.QApplication.processEvents()

    def showMessage(self, message, alignment=Qt.AlignTop|Qt.AlignLeft,
                    color=Qt.yellow):
        self._message = message
        self._alignment = alignment
        self._color = color
        self.repaint()

    def paintEvent(self, event):
        textbox = QtCore.QRect(self.rect())
        textbox.setRect(textbox.x() + 5, textbox.y() + 5,
                        textbox.width() - 10, textbox.height() - 10)
        painter = QtGui.QPainter(self)
        painter.drawPixmap(self.rect(), self._pixmap)
        painter.setPen(QtGui.QColor(self._color))
        painter.drawText(textbox, self._alignment, self._message)

    def mousePressEvent(self, event):
        self.hide()


class SimpleSplashScreen(QtWidgets.QWidget):
    def __init__(self, pixmap, center_point=None, font_size=None):
        QtWidgets.QWidget.__init__(self)
        self._pixmap = pixmap
        self._color = Qt.black
        self._message = ''
        self._alignment = Qt.AlignLeft
        self.setWindowFlags(Qt.FramelessWindowHint |
                            Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFixedSize(self._pixmap.size())
        font = QtGui.QFont(self.font())
        font_size = font_size or (font.pointSize() + 10)
        font.setPointSize(font_size)
        font.setBold(True)
        self.setFont(font)
        self.setMask(self._pixmap.mask())
        self.move(QtCore.QPoint(100,100))

    def clearMessage(self):
        self._message = ''
        self.repaint()

    def showMessage(self, message, alignment=Qt.AlignTop|Qt.AlignLeft,
                    color=Qt.yellow):
        self._message = message
        self._alignment = alignment
        self._color = color
        self.repaint()

    def paintEvent(self, event):
        textbox = QtCore.QRect(self.rect())
        textbox.setRect(textbox.x() + 5, textbox.y() + 5,
                        textbox.width() - 10, textbox.height() - 10)
        painter = QtGui.QPainter(self)
        painter.drawPixmap(self.rect(), self._pixmap)
        painter.setPen(QtGui.QColor(self._color))
        painter.drawText(textbox, self._alignment, self._message)

    def mousePressEvent(self, event):
        self.hide()

def show_splash(path, center_point=None):
    image = QtGui.QPixmap(path)
    splash = SplashScreen(image, center_point=center_point)
    splash.show()
    QtWidgets.QApplication.processEvents()
    for count in range(1, 6):
        splash.showMessage('Processing {} ...'.format(count))
        QtWidgets.QApplication.processEvents()
        QtCore.QThread.msleep(1000)
    splash.hide()
    splash.close()

if __name__ == '__main__':

    import sys
    app = QtWidgets.QApplication(sys.argv)
    screen_res = app.desktop().screenGeometry()
    screen_center = QtCore.QPoint(screen_res.width()//2,
                                  screen_res.height()//2)
    show_splash(sys.argv[1], center_point=screen_center)
    app.quit()

