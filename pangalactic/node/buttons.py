"""
PanGalactic widgets based on QPushButton
"""
from PyQt5.QtCore import QSize
from PyQt5.QtWidgets  import QMenu, QPushButton

from pangalactic.core.utils.meta import asciify


class MenuButton(QPushButton):
    """
    A button to serve as a toolbar menu
    """
    def __init__(self, icon, tooltip='', actions=None, parent=None):
        """
        Args:
            icon (QIcon):  icon for the button

        Keyword Args:
            tooltip (str):  text of tooltip
            actions (iterable of QAction):  items for the menu
        """
        super(MenuButton, self).__init__(parent=parent)
        self.setIcon(icon)
        if tooltip:
            self.setToolTip(tooltip)
        menu = QMenu(self)
        if actions and hasattr(actions, '__iter__'):
            for action in actions:
                menu.addAction(action)
        self.setMenu(menu)


class ButtonLabel(QPushButton):
    """
    A button with specifiable minimum size and optional context menu.
    """
    def __init__(self, value, w=None, h=None, actions=None, parent=None):
        """
        Args:
            value (str):  text for the button label
            w (int):  minimum width of the button
            h (int):  minimum height of the button

        Keyword Args:
            actions (iterable of QAction):  items for the optional context menu
        """
        super(ButtonLabel, self).__init__(value, parent=parent)
        self.setFlat(True)
        width = w or 200
        height = h or 25
        self.setMinimumSize(QSize(width, height))
        self.actions = actions
        self.menu = None
        if self.actions:
            self.menu = QMenu(self)
            self.menu.setStyleSheet(
                'QMenu::item {color: purple; background: white;} '
                'QMenu::item:selected {color: white; background: purple;}')
            for action in self.actions:
                self.menu.addAction(action)
        self.setStyleSheet('color: purple; background-color: white; '
                           'border: 1px solid black;'
                           )

    def contextMenuEvent(self, event):
        if self.menu:
            action = self.menu.exec_(self.mapToGlobal(event.pos()))


class SizedButton(QPushButton):

    def __init__(self, text, parent=None):
        super(SizedButton, self).__init__(text, parent=parent)
        width = self.fontMetrics().boundingRect(text).width() + 30
        self.setMaximumWidth(width)
        self.setStyleSheet('color: white; background-color: purple;'
                           'font-weight: bold')


class FkButton(QPushButton):
    """
    Button for rendering a `ForeignKey` field.
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
        QPushButton.__init__(self, text, parent=parent)
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


