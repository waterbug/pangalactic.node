from PyQt5.QtCore import Qt, QMimeData, QSize, QVariant
from PyQt5.QtGui  import (QDoubleValidator, QDrag, QIntValidator, QPainter,
                          QPixmap, QTextOption)
from PyQt5.QtWidgets  import (QApplication, QCheckBox, QComboBox, QDateEdit,
                              QDateTimeEdit, QFrame, QLabel, QLineEdit,
                              QListView, QListWidget, QSizePolicy,
                              QTextBrowser, QTextEdit, QVBoxLayout)
from sqlalchemy   import (BigInteger, Boolean, Date, DateTime, Float,
                          ForeignKey, Integer, String, Text, Time, Unicode)

from textwrap import wrap

# pangalactic
from pangalactic.core             import state
from pangalactic.core.meta        import TEXT_PROPERTIES, SELECTABLE_VALUES
from pangalactic.core.parametrics import (make_de_html, make_parm_html,
                                          mode_defz)
### uncomment orb if debug logging is needed ...
from pangalactic.core.uberorb     import orb
from pangalactic.node.buttons     import FkButton, UrlButton


def HLine():
    toto = QFrame()
    toto.setFrameShape(QFrame.HLine)
    toto.setFrameShadow(QFrame.Sunken)
    return toto


def VLine():
    toto = QFrame()
    toto.setFrameShape(QFrame.VLine)
    toto.setFrameShadow(QFrame.Sunken)
    return toto


class PlaceHolder(QLabel):
    """
    Widget for the main window CentralWidget space when nothing has been
    selected.

    Keyword Args:
        image (QImage):  image to be displayed
        min_size (int):  minimum size (side of a square area)
    """
    # TODO:  make this a widget that contains the label
    # TODO:  add optional text ...
    def __init__(self, image=None, min_size=None, parent=None):
        super().__init__(parent=parent)
        self.setMaximumSize(400, 400)
        if min_size:
            self.setMinimumSize(min_size, min_size)
        self.setAlignment(Qt.AlignLeft)
        self.setAlignment(Qt.AlignTop)
        # TODO:  there is probably a bug in how resize events are handled here
        # -- setMaximumSize is required to keep the placeholder widget from
        # setting itself too big when left and right docks are undocked and
        # then redocked (main window becomes too large and resists resizing).
        width = self.frameGeometry().width()
        height = self.frameGeometry().height()
        pixmap = QPixmap()
        if image:
            self.image = image
        else:
            # generic 'pangalaxian' icon/image
            self.image = 'icons/icon32' + state.get('icon_type', '.png')
        pixmap.load(self.image)
        pixmap_resized = pixmap.scaled(width, height, Qt.KeepAspectRatio)
        self.setPixmap(pixmap_resized)
        self.setSizePolicy(QSizePolicy(
                           QSizePolicy.Expanding, QSizePolicy.Expanding))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = self.frameGeometry().width()
        height = self.frameGeometry().height()
        # NOTE:  have to load new pixmap on resize -- old one gets corrupted
        new_pixmap = QPixmap()
        new_pixmap.load(self.image)
        pixmap_resized = new_pixmap.scaled(width, height, Qt.KeepAspectRatio)
        self.setPixmap(pixmap_resized)


class LogWidget(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet('font-size: 16px')
        self.setSizePolicy(QSizePolicy.Expanding,
                           QSizePolicy.Expanding)


class LeftPlaceHolder(QLabel):
    """
    Widget for the left dock window space when nothing is available to select.

    Args:
        text (str):  label text
    """
    # TODO:  make this a widget that contains the label
    # TODO:  add optional text ...
    def __init__(self, text, parent=None):
        super().__init__(parent=parent)
        # self.setMinimumSize(100, 400)
        self.setAlignment(Qt.AlignCenter)
        self.setText(text)


class ColorLabel(QLabel):
    """
    Label for general use when colored text is desired.

    Args:
        name (str):  label text

    Keyword Args:
        color (str):  color to use for text (default: purple)
        element (str):  html element to use for label
        border (int):  thickness of border (default: no border)
        margin (int):  width of margin surrounding contents
        parent (QWidget):  parent widget
    """
    def __init__(self, name, color=None, element=None, border=None,
                 margin=0, parent=None):
        super().__init__(margin=margin, parent=parent)
        self.name = name
        self.set_content(name, color=color, element=element, border=border,
                         margin=margin)

    def set_content(self, name, color=None, element=None, border=None,
                    margin=None):
        if border:
            self.setFrameStyle(QFrame.Box | QFrame.Plain)
            try:
                self.setLineWidth(border)
            except:
                self.setLineWidth(1)
        try:
            self.setMargin(margin)
        except:
            self.setMargin(0)
        # TODO: validate element (e.g. element in ['h2', 'h3', ...])
        element = element or 'b'
        # TODO: validate color (e.g. color in ['blue', 'red', ...])
        color = color or 'purple'
        text = '<{0}><font color="{1}">{2}</font></{0}>'.format(element, color,
                                                                name)
        self.setText(text)
        hint = self.sizeHint()
        if hint.isValid():
            self.setMinimumSize(hint)

    def get_content(self):
        return self.name


class NameLabel(QLabel):
    """
    Label for use in forms as the name in (name, value) pairs.
    """
    def __init__(self, name, parent=None, **kw):
        super().__init__(margin=5, parent=parent)
        self.setText(name)
        hint = self.sizeHint()
        if hint.isValid():
            self.setMinimumSize(hint)


class ValueLabel(QLabel):
    """
    Label for use in forms as the value in (name, value) pairs.
    """
    def __init__(self, value, w=None, h=None, wrappable=False,
                 parent=None, **kw):
        super().__init__(margin=5, parent=parent)
        self.w = w or 250
        self.h = h or 25
        if wrappable:
            # don't set height (duh)
            self.setMaximumWidth(self.w)
            self.setMinimumWidth(self.w)
            self.setTextFormat(Qt.AutoText)
            self.setScaledContents(True)
            self.setWordWrap(True)
        self.setFrameStyle(QFrame.Box | QFrame.Plain)
        self.setLineWidth(1)
        self.setStyleSheet('color: purple')
        self.setText(value)
        # THIS is the magic incantation to make word wrap work properly:
        self.setMinimumSize(self.sizeHint())


class ModeLabel(QLabel):
    """
    Label used to display the current "mode" of the pangalaxian client
    application.
    """
    def __init__(self, value, w=None, h=None, color=None, parent=None):
        super().__init__(value, parent=parent)
        self.setWordWrap(True)
        self.setFrameStyle(QFrame.Box | QFrame.Plain)
        self.setLineWidth(1)
        width = w or 200
        height = h or 25
        self.setMinimumSize(QSize(width, height))
        color = color or 'purple'
        bg = 'background-color: white;'
        fw = 'font-weight: bold;'
        fs = 'font-size: larger;'
        self.setStyleSheet(f'color: {color}; {bg} {fw} {fs}')


class ParameterLabel(QLabel):
    """
    Create an HTML label based on a ParameterDefinition id, for the purpose of
    generating an icon.

    Args:
        parameter_definition (ParameterDefinition):  a ParameterDefinition
            object
    """
    def __init__(self, parameter_definition, parent=None):
        QLabel.__init__(self, parent=parent)
        # 'x_y' will be interpreted as "x sub y".
        # 'x_y_z' will be interpreted as "x sub y-z", etc.
        html = make_parm_html(parameter_definition.id)
        super().__init__(html)

    def get_pixmap(self):
        pixmap = QPixmap(self.size())
        painter = QPainter(pixmap)
        painter.drawPixmap(self.rect(), self.grab())
        painter.end()
        # 2nd arg is "mode": 1 is Qt.SmoothTransformation
        pixmap_resized = pixmap.scaledToHeight(20, 1)
        return pixmap_resized

    def textFormat(self):
        return Qt.RichText

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_position = event.pos()

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        min_dist = (event.pos() - self.drag_start_position).manhattanLength()
        if min_dist < QApplication.startDragDistance():
            return
        drag = QDrag(self)
        mimedata = QMimeData()
        mimedata.setText(self.text())
        drag.setMimeData(mimedata)
        drag.setPixmap(self.get_pixmap())
        drag.setHotSpot(event.pos())
        drag.exec_(Qt.CopyAction | Qt.MoveAction)


def get_widget(field_name, field_type, value=None, editable=True,
               nullable=True, maxlen=50, obj_pk='', external_name='',
               related_cname=None, placeholder=None, choices=None,
               tooltip=None, parm_field=False, parm_type='float',
               de_field=False, de_type='str'):
    """
    Get the appropriate widget for a specified field_type -- main use is for
    `PgxnObject`.

    Args:
        field_name (str):  the name of the field -- used for (1) getting a
            default label, in case no label text is provided, and (2) for FK
            (QPushButton) types, for which the application may call a function
            to return a selection list of values, and that selection list may
            depend on the specific field name as context
        field_type (class):  the class of the field for which the widget is
            being supplied

    Keyword Args:
        value (any):  value of the field
        editable (bool):  whether the field is to be created in editable form
        nullable (bool):  whether the field will allow a null value
        maxlen (int):  maximum field length (not always applicable)
        obj_pk (str):  [FkButton only] pk value of the object that contains the
            field (the application may call a function to return a selection
            list of values, and that selection list may depend on the specific
            object as context)
        external_name (str):  the field name to be displayed in the user
            interface (i.e., on the field label)
        related_cname (str):  the name of the class associated with a foreign key --
            this will be `None` for a datatype field
        placeholder (str):  string to use in setPlaceholderText()
        choices (iterable of tuples):  for fields that have 'choices' defined
        tooltip (str):  tooltip to be shown on the label, typically the field
            definition
        parm_field (bool):  the field is a parameter field
        parm_type (str):  one of ['float', 'int', 'bool', 'text']
        de_field (bool):  the field is a data element field
        de_type (str):  one of ['float', 'int', 'bool', 'str', 'text']

    Returns:
        tuple: widget (QWidget) and label (QLabel)
    """
    # related_cname will be None for datatypes; a class name for FK fields
    ### for EXTREMELY verbose debugging, uncomment:
    # orb.log.debug('get_widget for field type: {}'.format(field_type))
    wrap_text = False
    if field_name == 'url':
        if editable:
            widget_class = UnicodeFieldWidget
        else:
            widget_class = UrlButton
    elif field_name in TEXT_PROPERTIES or de_type == 'text':
        widget_class = TextFieldWidget
        wrap_text = True
        # NOTE:  'maxlen' here this is NOT the maximum length of the text field
        # contents -- it just sets the minimum width of the "view" label for
        # its contents
        maxlen = 250
    elif field_name in SELECTABLE_VALUES:
        ### for EXTREMELY verbose debugging, uncomment:
        # orb.log.debug('* field "{}" is in SELECTABLE_VALUES'.format(
                                                            # field_name))
        widget_class = select_widgets.get(field_type)
        ### for EXTREMELY verbose debugging, uncomment:
        # if widget_class:
            # orb.log.debug('  ... setting widget {}'.format(widget_class))
        # else:
            # orb.log.debug('  ... selection widget not found...')
        if not widget_class:
            # in case this field_type is not found in select_widgets ...
            widget_class = widgets.get(field_type)
            # orb.log.debug('  setting plain widget {}'.format(widget_class))
    elif de_field:
        widget_class = widgets.get(de_type)
    else:
        widget_class = widgets.get(field_type)
    # print ' - widget_class = %s' % widget_class.__name__
    if widget_class:
        if field_name == 'url' and not editable:
            orb.log.debug('  instantiating UrlButton')
            widget = widget_class(value=value, maxlen=maxlen,
                                  editable=False)
        elif editable or field_type == "object":
            widget = widget_class(value=value, maxlen=maxlen,
                                  related_cname=related_cname, obj_pk=obj_pk,
                                  field_name=field_name, nullable=nullable,
                                  editable=editable, placeholder=placeholder,
                                  parm_field=parm_field, parm_type=parm_type,
                                  de_field=de_field, de_type=de_type)
        elif field_type == Boolean:
            # read-only boolean field -> disabled checkbox
            widget = widget_class(value=value, editable=editable)
        else:
            if isinstance(value, str):
                widget = ValueLabel(value, w=maxlen, wrappable=wrap_text,
                                    placeholder=placeholder)
            else:
                widget = ValueLabel(str(value), w=maxlen,
                                    placeholder=placeholder)
        label = QLabel()
        if parm_field:
            label.setTextFormat(Qt.RichText)
            html_name = make_parm_html(field_name)
            label.setText(html_name)
            label.setStyleSheet('QLabel {font-size: 15px; font-weight: bold} '
                                'QToolTip { font-weight: normal; '
                                'font-size: 12px; border: 2px solid; }')
        elif de_field:
            label.setTextFormat(Qt.RichText)
            html_name = make_de_html(field_name)
            label.setText(html_name)
            label.setStyleSheet('QLabel {font-size: 15px; font-weight: bold} '
                                'QToolTip { font-weight: normal; '
                                'font-size: 12px; border: 2px solid; }')
        else:
            label.setText(external_name)
            label.setStyleSheet('QLabel {font-size: 14px; font-weight: bold} '
                                'QToolTip { font-weight: normal; '
                                'font-size: 12px; border: 2px solid; }')
        if tooltip:
            txt = '\n'.join(wrap(tooltip, width=40, break_long_words=False))
            label.setToolTip(txt)
        return widget, label
    else:
        return None, None


class BooleanFieldWidget(QCheckBox):
    """
    Widget for `BooleanField` and `NullBooleanField`.
    """
    def __init__(self, parent=None, value=None, editable=True, **kw):
        super().__init__(parent=parent)
        self.set_value(value)
        if not editable:
            self.setEnabled(False)

    def set_value(self, value):
        if value:
            self.setChecked(True)
        else:
            self.setChecked(False)

    def get_value(self):
        return self.isChecked()


class StringFieldWidget(QLineEdit):
    """
    Widget for `String` field (maps to `token` datatype in ontology -- intended
    to represent strings that can serve as programmatic names/tokens, i.e. not
    unicode).

    Keyword Args:
        parent (QWidget):  parent widget
        value (str):  value of the field
        maxlen (int):  length of the field in characters
        width (int):  width of the field in pixels
    """
    def __init__(self, parent=None, value=None, maxlen=None, width=None, **kw):
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy(
                           QSizePolicy.Fixed, QSizePolicy.Fixed))
        self.parm_field = kw.get('parm_field')
        self.parm_type = kw.get('parm_type')
        self.width = width
        if maxlen is not None:
            self.setMaxLength(maxlen)
        self.maxlen = maxlen
        if kw.get('placeholder'):
            self.setPlaceholderText(kw['placeholder'])
        if self.parm_field and self.parm_type == 'int':
            self.setValidator(QIntValidator(self))
        elif self.parm_field and self.parm_type == 'float':
            self.setValidator(QDoubleValidator(self))
        self.set_value(value)

    def set_value(self, value):
        """
        Args:
            value (str):  value of the field
        """
        if value is not None:
            self.setText(value)
        else:
            self.setText('')

    def get_value(self):
        """
        Returns:
            value (str):  value of the field, cast to string
        """
        return str(self.text())

    def sizeHint(self):
        # TODO:  adjust this size in proportion to 'maxlen'
        if self.parm_field:
            if self.parm_type in ['int', 'float']:
                return QSize(100, 25)
        elif self.width:
            return QSize(self.width, 25)
        return QSize(250, 25)


class StringSelectWidget(QComboBox):
    """
    Widget for `String` field with a specified set of valid values.

    Keyword Args:
        parent (QWidget):  parent widget
        field_name (str):  name of the field
        value (str):  value of the field
        valid_values (list of str):  selectable valid values of the field
    """
    def __init__(self, parent=None, field_name=None, value=None,
                 valid_values=None, **kw):
        super().__init__(parent=parent)
        self.setMinimumWidth(120)
        self.setMaximumWidth(250)
        self.valid_values = []
        # if 'valid_values' is provided, it will override the "default"
        # valid values specified in SELECTABLE_VALUES
        if valid_values:
            self.valid_values = valid_values
        elif SELECTABLE_VALUES.get(field_name):
            self.valid_values = list(SELECTABLE_VALUES[field_name].keys())
        self.addItems(self.valid_values)
        if value:
            self.set_value(value)

    def set_value(self, value):
        if value in self.valid_values:
            self.setCurrentIndex(self.valid_values.index(value))

    def get_value(self):
        return str(self.valid_values[self.currentIndex()])


class DashSelectCombo(QComboBox):
    """
    Widget for selecting a dashboard.

    Keyword Args:
        parent (QWidget):  parent widget
    """
    def __init__(self, parent=None, **kw):
        super().__init__(parent=parent)

    def mousePressEvent(self, evt):
        project_oid = state.get('project')
        if project_oid in mode_defz:
            if self.findText('System Power Modes') == -1:
                self.addItem('System Power Modes', QVariant)
        else:
            n = self.findText('System Power Modes')
            if n != -1:
                self.removeItem(n)
        super().mousePressEvent(evt)


class UnicodeFieldWidget(QLineEdit):
    """
    Widget for `Unicode` field.  (Not needed -- python 3 strings are unicode --
    but retained for legacy; may be removed in the future.)
    """
    def __init__(self, parent=None, value=None, maxlen=None, **kw):
        super().__init__(parent=parent)
        if maxlen is not None:
            self.setMaxLength(maxlen)
        self.maxlen = maxlen
        if kw.get('placeholder'):
            self.setPlaceholderText(kw['placeholder'])
        self.set_value(value)

    def set_value(self, value):
        if value is not None:
            self.setText(value)
        else:
            self.setText(u'')

    def get_value(self):
        # TODO:  hmm ... shouldn't this be unicode?
        return str(self.text())

    def sizeHint(self):
        # TODO:  adjust this size in proportion to 'maxlen'
        return QSize(250, 25)


class IntegerFieldWidget(QLineEdit):
    """
    Widget for `IntegerField`, `BigIntegerField`,
    `PositiveIntegerField`, `PositiveSmallIntegerField`,
    and `SmallIntegerField`.
    """
    def __init__(self, parent=None, value=None, **kw):
        """
        Keyword Args:
            parent (QWidget):  parent widget
            value (str):  value of the field (can be an int, in which case it
                will be converted to str)
        """
        super().__init__(parent=parent)
        if kw.get('placeholder'):
            self.setPlaceholderText(kw['placeholder'])
        self.set_value(value)
        self.setValidator(QIntValidator(self))

    def set_value(self, value):
        """
        Args:
            value (str):  value of the field (can be an int, in which case it
                will be converted to str)
        """
        if value is not None:
            self.setText(str(value))
        else:
            self.setText('')

    def get_value(self):
        """
        Returns:
            value (str):  value of the field (int) as a string
        """
        # in case we get commas, remove them before cast
        return (self.text() or '0').replace(',', '')

    def sizeHint(self):
        return QSize(100, 25)


class FloatFieldWidget(QLineEdit):
    """
    Widget for `FloatField`.
    """
    def __init__(self, parent=None, value=None, **kw):
        """
        Keyword Args:
            parent (QWidget):  parent widget
            value (str):  value of the field (can be a float) -- must be
                castable to a float or it will be ignored
        """
        super().__init__(parent=parent)
        if kw.get('placeholder'):
            self.setPlaceholderText(kw['placeholder'])
        self.set_value(value)
        self.setValidator(QDoubleValidator(self))

    def set_value(self, value):
        """
        Args:
            value (str):  value of the field (can be an int, in which case it
                will be converted to str)
        """
        if value is not None:
            # TODO:  might need to set significant digits, etc.
            try:
                self.setText(str(float(value)))
            except:
                # if value cannot be cast to float, set to null string
                self.setText('')
        else:
            self.setText('')

    def get_value(self):
        """
        Returns:
            value (str):  value of the field (float) as a string
        """
        return self.text() or '0.0'

    def sizeHint(self):
        return QSize(100, 25)


class DateFieldWidget(QDateEdit):
    """
    Widget for `DateField`.
    """
    def __init__(self, parent=None, value=None, **kw):
        super().__init__(parent=parent)
        self.set_value(value)

    def set_value(self, value):
        if value:
            self.setDate(value)

    def get_value(self):
        return self.date()

    def sizeHint(self):
        # TODO:  adjust this size in proportion to 'maxlen'
        return QSize(250, 25)


class TimeFieldWidget(QDateEdit):
    """
    Widget for `TimeField`.
    """
    def __init__(self, parent=None, value=None, **kw):
        super().__init__(parent=parent)
        self.set_value(value)

    def set_value(self, value):
        if value:
            self.setTime(value)

    def get_value(self):
        return self.date()

    def sizeHint(self):
        # TODO:  adjust this size in proportion to 'maxlen'
        return QSize(100, 25)


class DateTimeFieldWidget(QDateTimeEdit):
    """
    Widget for `DateTimeField`.
    """
    def __init__(self, parent=None, value=None, **kw):
        super().__init__(parent=parent)
        self.set_value(value)

    def set_value(self, value):
        if value:
            self.setDateTime(value)

    def get_value(self):
        return self.dateTime()

    def sizeHint(self):
        # TODO:  adjust this size in proportion to 'maxlen'
        return QSize(250, 25)


class TextFieldWidget(QTextEdit):
    """
    Widget for `TextField`.  Can accomodate unlimited plain text or "rich text"
    / html.  Note that all properties that use this field are defined as having
    datatype 'unicode', so the field value needs to be handled as unicode and
    the database will be expecting unicode.
    """
    def __init__(self, parent=None, value=None, maxlen=None, **kw):
        super().__init__(parent=parent)
        # NOTE:  a TextField can have a 'max_length' attr, but it is not
        # enforced at the model level, only in the user interface (e.g., the
        # Textarea widget of an auto-generated form field).
        # NOTE:  `QTextEdit` can explicitly accommodate rich text / html, so
        # that will be included in the future ... need to get user feedback to
        # determine what is desirable (and supported by QTextEdit)
        # TODO:  implement validation/control based on 'maxlen' for this widget.
        # TODO:  support for rich text
        self.maxlen = maxlen
        self.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.setTabChangesFocus(True)
        if kw.get('placeholder'):
            self.setPlaceholderText(kw['placeholder'])
        self.set_value(value)

    def set_value(self, value):
        if value is not None:
            self.setText(value)
        else:
            self.setText(u'')

    def get_value(self):
        # TODO:  support for rich text
        # NOTE:  toPlainText returns a UTF-16 unicode string.
        ### this was the PyQt4 implementation ##################
        # utf16_qstring = self.toPlainText()
        # utf16_codec = QTextCodec.codecForName("UTF-16")
        # return unicode(utf16_codec.fromUnicode(utf16_qstring), 'UTF-16')
        ### end of PyQt4 implementation ##################
        return self.toPlainText()

    def sizeHint(self):
        # TODO:  adjust this size in proportion to 'maxlen'
        return QSize(250, 100)


class UnitsWidget(QComboBox):
    """
    Widget for units selection / display.
    """
    def __init__(self, field_name, units, choices, parent=None):
        """
        Args:
            field_name:  field name (parm id), to enable referencing
            units (str):  for parm_field, its current "units" setting
            dimensions (str):  dimension of the parameter
        """
        super().__init__(parent=parent)
        self.field_name = field_name
        self.valid_units = choices
        self.addItems(choices)
        # set units to empty string if None
        self.set_value(units or '')

    def set_value(self, value):
        if value in self.valid_units:
            self.setCurrentText(value)

    def get_value(self):
        return str(self.currentText())


# keys based on SqlAlchemy column data types, except for 'parameter'
widgets = {
    BigInteger  : IntegerFieldWidget,
    Boolean     : BooleanFieldWidget,
    Date        : DateFieldWidget,
    DateTime    : DateTimeFieldWidget,
    Float       : FloatFieldWidget,
    Integer     : IntegerFieldWidget,
    String      : StringFieldWidget,
    Text        : TextFieldWidget,
    Unicode     : UnicodeFieldWidget,
    Time        : TimeFieldWidget,
    ForeignKey  : FkButton,
    'object'    : FkButton,
    'parameter' : StringFieldWidget,
    # these are for data elements, 'de_type'
    'bool'      : BooleanFieldWidget,
    'str'       : StringFieldWidget,
    'float'     : FloatFieldWidget,
    'int'       : IntegerFieldWidget,
    'text'      : TextFieldWidget,
    # FIXME: stop-gap pending policy for "non-functional" properties -- really
    # should at least make it some kind of list widget
    set         : TextFieldWidget
    }

# currently only used for ParameterDefinition.range_datatype and dimensions
# (both are String/Unicode datatypes)
select_widgets = {
    # BigInteger  : IntegerSelectWidget,
    # Float       : FloatSelectWidget,
    # Integer     : IntegerSelectWidget,
    String      : StringSelectWidget,
    Unicode     : StringSelectWidget,
    # ForeignKey  : FkSelectWidget,
    # set         : TextSelectWidget
    }


class AutosizingListWidget(QListWidget):
    def __init__(self, height=None, parent=None):
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Fixed,
                                       QSizePolicy.Expanding))
        self.setResizeMode(self.Adjust)
        self.installEventFilter(self)
        if height and height < 400:
            self.setMinimumHeight(height)
        else:
            self.setMinimumHeight(300)
        self.setStyleSheet('font-weight: bold; font-size: 12px')
        layout = QVBoxLayout()
        self.setLayout(layout)
        layout.setAlignment(self, Qt.AlignLeft|Qt.AlignTop)

    def sizeHint(self):
        s = QSize()
        # s.setWidth(self.sizeHintForColumn(0) + 50)
        # size hint not working!  wtf?
        # for now, hard code a width
        s.setWidth(250)
        return s


class AutosizingListView(QListView):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding,
                                       QSizePolicy.Expanding))
        self.setResizeMode(self.Adjust)
        self.installEventFilter(self)
        self.setMinimumHeight(300)

    def sizeHint(self):
        s = QSize()
        # s.setWidth(self.sizeHintForColumn(0) + 50)
        # size hint not working!  wtf?
        # for now, hard code a width
        s.setWidth(250)
        return s

