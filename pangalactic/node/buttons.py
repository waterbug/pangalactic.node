"""
PanGalactic widgets based on QPushButton
"""
import webbrowser

from PyQt5.QtCore import Qt, QRectF, QSize, QPoint, QMimeData
from PyQt5.QtGui import QBrush, QDrag, QIcon, QPen, QCursor
from PyQt5.QtWidgets  import QMenu, QPushButton

from pangalactic.core.meta import asciify


class MenuButton(QPushButton):
    """
    A button to serve as a toolbar menu.
    """
    def __init__(self, icon, text='', tooltip='', actions=None, parent=None):
        """
        Args:
            icon (QIcon):  icon for the button

        Keyword Args:
            text (str):  text of button (display is optional)
            tooltip (str):  text of tooltip
            actions (iterable of QAction):  items for the menu
        """
        super().__init__(parent=parent)
        self.setIcon(icon)
        if text:
            self.setText(text)
        if tooltip:
            self.setToolTip(tooltip)
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        if actions and hasattr(actions, '__iter__'):
            for action in actions:
                menu.addAction(action)
        self.setMenu(menu)


class ButtonLabel(QPushButton):
    """
    A button with specifiable minimum size and optional context menu.
    """
    def __init__(self, value, w=None, h=None, actions=None, color="purple",
                 parent=None):
        """
        Args:
            value (str):  text for the button label

        Keyword Args:
            w (int):  minimum width of the button
            h (int):  minimum height of the button
            actions (iterable of QAction):  items for the optional context menu
            color (str):  color to use for button text
        """
        super().__init__(value, parent=parent)
        self.setFlat(True)
        width = w or 200
        height = h or 25
        self.setMinimumSize(QSize(width, height))
        self.actions = actions
        self.color = color
        self.menu = None
        if self.actions:
            self.menu = QMenu(self)
            self.menu.setStyleSheet(
                'QMenu::item {color: purple; background: white;} '
                'QMenu::item:selected {color: white; background: purple;}')
            for action in self.actions:
                self.menu.addAction(action)
        self.setStyleSheet(f'color: {color}; background-color: white; '
                           'border: 1px solid black;')

    def contextMenuEvent(self, event):
        if self.menu:
            self.menu.exec_(self.mapToGlobal(event.pos()))

    def enterEvent(self, event):
        self.setStyleSheet(f'color: {self.color}; background-color: white; '
                           'border: 2px solid purple;')

    def leaveEvent(self, event):
        self.setStyleSheet(f'color: {self.color}; background-color: white; '
                           'border: 1px solid black;')


class FileButtonLabel(ButtonLabel):
    """
    A subclass of ButtonLabel that points to a DigitalFile instance.
    """
    def __init__(self, value, file=None, w=None, h=None, actions=None,
                 color="purple", parent=None):
        """
        Args:
            value (str):  text for the button label

        Keyword Args:
            file (DigitalFile): the DigitalFile instance
            w (int):  minimum width of the button
            h (int):  minimum height of the button
            actions (iterable of QAction):  items for the optional context menu
        """
        super().__init__(value, w=w, h=h, actions=actions, color=color,
                         parent=parent)
        self.file = file


class CheckButtonLabel(QPushButton):
    """
    A checkable button with specifiable minimum size.
    """
    def __init__(self, value, w=None, h=None, parent=None):
        """
        Args:
            value (str):  text for the button label

        Keyword Args:
            w (int):  minimum width of the button
            h (int):  minimum height of the button
            parent (QWidget): parent widget
        """
        super().__init__(value, parent=parent)
        self.setFlat(True)
        self.setCheckable(True)
        width = w or 200
        height = h or 25
        self.setMinimumSize(QSize(width, height))
        self.setStyleSheet('color: purple; background-color: white; '
                           'border: 1px solid black;')

    def keyPressEvent(self, event):
        if self.isChecked():
            self.setStyleSheet('color: purple; background-color: yellow; '
                               'border: 1px solid black;')
        else:
            self.setStyleSheet('color: purple; background-color: white; '
                               'border: 1px solid black;')

    def enterEvent(self, event):
        if self.isChecked():
            self.setStyleSheet('color: purple; background-color: yellow; '
                               'border: 2px solid purple;')
        else:
            self.setStyleSheet('color: purple; background-color: white; '
                               'border: 2px solid purple;')

    def leaveEvent(self, event):
        if self.isChecked():
            self.setStyleSheet('color: purple; background-color: yellow; '
                               'border: 1px solid black;')
        else:
            self.setStyleSheet('color: purple; background-color: white; '
                               'border: 1px solid black;')


class SizedButton(QPushButton):

    def __init__(self, text, color="purple", parent=None):
        super().__init__(text, parent=parent)
        self.setStyleSheet(';'.join([
            f'color: white; background-color: {color}',
            'font-weight: bold;']))
        width = self.fontMetrics().boundingRect(text).width() + 30
        self.setMaximumWidth(width)


class ItemButton(QPushButton):
    """
    Subclass of QPushButton that can be related to an item by its oid.
    """
    def __init__(self, text, oid=None, color="purple", parent=None):
        super().__init__(text, parent=parent)
        self.oid = oid
        self.setStyleSheet(';'.join([
            f'color: white; background-color: {color}',
            'font-weight: bold;']))
        width = self.fontMetrics().boundingRect(text).width() + 30
        self.setMaximumWidth(width)


class FkButton(QPushButton):
    """
    Button for rendering an "object" field (a.k.a. a foreign key or an
    ObjectProperty).
    """
    def __init__(self, parent=None, value=None, related_cname=None,
                 obj_pk=None, field_name=None, nullable=True, editable=False,
                 **kw):
        """
        Initialize an FkButton.

        Keyword Args:
            value (any):  value of the field
            related_cname (str):  the name of the class associated with a
                foreign key -- this will be `None` for a datatype field
            obj_pk (str):  [FkButton only] pk value of the object that contains
                the field (the application may call a function to return a
                selection list of values, and that selection list may depend on
                the specific object as context)
            field_name (str):  the name of the field -- used for (1) getting a
                default label, in case no label text is provided, and (2) for
                FK (QPushButton) types, for which the application may call a
                function to return a selection list of values, and that
                    selection list may depend on the specific field name as context
            nullable (bool):  whether the field will allow a null value
            editable (bool):  whether the field is to be created in editable
                form
        """
        if hasattr(value, '__str__'):
            text = value.__str__()
        else:
            text = asciify(value)
        super().__init__(text, parent=parent)
        if editable:
            pass
        else:
            self.setStyleSheet('color: purple')
        self.editable = editable
        self.set_value(value)
        self.obj_pk = obj_pk
        self.field_name = field_name
        self.related_cname = related_cname
        self.nullable = nullable
        self.clicked.connect(self.get_value)

    def get_value(self):
        """
        @return: an Identifiable of some kind
        @rtype:  `Identifiable`
        """
        return self.value

    def set_value(self, value):
        """
        @param: an Identifiable (or subtype) instance, which has an 'id'
        @type:  `Identifiable`
        """
        self.value = value
        self.setText(getattr(value, 'id', 'None'))


class UrlButton(QPushButton):
    """
    Button for rendering a "url" field.
    """
    def __init__(self, parent=None, value='none', **kw):
        """
        Initialize a UrlButton.

        Keyword Args:
            value (str):  a url (value of the field)
        """
        super().__init__(value)
        self.setStyleSheet('color: purple')
        self.set_value(value)
        self.clicked.connect(self.open_url)

    def get_value(self):
        """
        @return: an Identifiable of some kind
        @rtype:  `Identifiable`
        """
        return self.value

    def set_value(self, value):
        """
        Args:
            value (str): a url
        """
        self.value = value
        self.setToolTip(value)
        self.setStyleSheet(
                        "QToolTip { color: #ffffff; "
                        "background-color: #2a82da; "
                        "border: 1px solid white; }")
        txt = 'none'
        try:
            if value and len(value) > 40:
                txt = value[:40] + '...'
            else:
                txt = value
        except:
            pass
        self.setText(txt)

    def open_url(self, evt):
        if self.value:
            webbrowser.open_new(self.value)


class ToolButton(QPushButton):
    def __init__(self, pixmap, text, parent=None):
        self.pixmap = pixmap
        super().__init__(QIcon(pixmap), text, parent)
        self.setFlat(True)

    def boundingRect(self):
        return QRectF(-5 , -5, 20, 20)

    def paint(self, painter, option, widget):
        painter.setPen(QPen(Qt.black, 1))
        painter.setBrush(QBrush(Qt.white))
        painter.drawRect(-5, -5, 20, 20)

    def mouseMoveEvent(self, event):
        event.accept()
        drag = QDrag(self)
        mime = QMimeData()
        drag.setMimeData(mime)
        mime.setText(self.mime)
        dragCursor = QCursor()
        dragCursor.setShape(Qt.ClosedHandCursor)
        drag.setDragCursor(self.pixmap, Qt.IgnoreAction)
        self.setCursor(Qt.OpenHandCursor)
        drag.setPixmap(self.pixmap)
        drag.setHotSpot(QPoint(15, 20))
        drag.exec_()
        self.clearFocus()

    def setData(self, mimeData):
        self.mime = mimeData

    def dragMoveEvent(self, event):
        event.setAccepted(True)


