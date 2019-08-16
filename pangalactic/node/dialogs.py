"""
Various dialogs.
"""
# NOTE:  deprecated class CondaDialog retired to "pgef_sandbox" in
# 'dialogs_with_CondaDialog.py'
# NOTE:  deprecated modules p.n.threads and process have been retired to the
# "pgef_sandbox", as they were used with the now-deprecated CondaDialog ...
# from pangalactic.node.threads     import threadpool, Worker
# from pangalactic.node.process     import run_conda

from __future__ import division
from builtins import range
# NOTE: fixed div's so old_div not needed
# from past.utils import old_div
from builtins import object
import sys

from PyQt5.QtCore import (Qt, QPoint, QRectF, QSize, QVariant)
from PyQt5.QtGui import QColor, QPainter, QPen, QPalette
from PyQt5.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                             QDialogButtonBox, QFormLayout, QFrame,
                             QHBoxLayout, QLabel, QLineEdit, QProgressDialog,
                             QSizePolicy, QTableView, QVBoxLayout, QWidget)

from louie import dispatcher

from pangalactic.core             import prefs, state
from pangalactic.core.meta        import (NUMERIC_FORMATS, NUMERIC_PRECISION,
                                          SELECTION_VIEWS)
from pangalactic.core.parametrics import parmz_by_dimz
from pangalactic.core.uberorb     import orb
from pangalactic.core.units       import alt_units, in_si
from pangalactic.core.utils.meta  import get_external_name_plural
from pangalactic.node.buttons     import SizedButton
from pangalactic.node.cad.viewer  import QtViewer3DColor
from pangalactic.node.tablemodels import ObjectTableModel
from pangalactic.node.widgets     import NameLabel, UnitsWidget, ValueLabel
from pangalactic.node.widgets     import StringFieldWidget, IntegerFieldWidget


COLORS = {True: 'green', False: 'red'}


class LoginDialog(QDialog):
    """
    Dialog for logging in to the message bus.
    """
    def __init__(self, userid=None, parent=None):
        """
        Initializer.

        Keyword Args:
            userid (list of str):  default userid
            parent (QWidget):  parent widget
        """
        super(LoginDialog, self).__init__(parent)
        self.setWindowTitle("Login")
        userid_label = QLabel('userid:', self)
        self.userid_field = QLineEdit(self)
        if userid:
            self.userid_field.setText(userid)
        passwd_label = QLabel('password:', self)
        self.passwd_field = QLineEdit(self)
        self.passwd_field.setEchoMode(QLineEdit.Password)
        form = QFormLayout(self)
        form.addRow(userid_label, self.userid_field)
        form.addRow(passwd_label, self.passwd_field)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        self.buttons.button(QDialogButtonBox.Ok).setText('Login')
        form.addRow(self.buttons)
        self.buttons.button(QDialogButtonBox.Ok).clicked.connect(self.login)
        self.buttons.rejected.connect(self.reject)

    def login(self):
        self.userid = self.userid_field.text()
        self.passwd = self.passwd_field.text()
        self.accept()


class NotificationDialog(QDialog):
    def __init__(self, something, parent=None):
        super(NotificationDialog, self).__init__(parent)
        self.setWindowTitle("Yo!")
        form = QFormLayout(self)
        something_happened_label = QLabel('woo:', self)
        something_happened = QLabel(something, self)
        form.addRow(something_happened_label, something_happened)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        form.addRow(self.buttons)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)


class OptionNotification(QDialog):
    def __init__(self, title, message, parent=None):
        super(OptionNotification, self).__init__(parent)
        self.setWindowTitle(title)
        form = QFormLayout(self)
        note_label = QLabel('Note:', self)
        message_label = QLabel(message, self)
        form.addRow(note_label, message_label)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        form.addRow(self.buttons)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)


class ValidationDialog(QDialog):
    """
    Dialog for displaying validation error messages in PgxnObject editor.
    """
    def __init__(self, msg_dict, parent=None):
        """
        Initialize.

        Args:
            msg_dict (dict):  maps field names to validation error messages
        """
        super(ValidationDialog, self).__init__(parent)
        self.setWindowTitle("Validation Error")
        form = QFormLayout(self)
        for fname, msg in msg_dict.items():
            field_label = QLabel(
                '<b><font color="purple">{}</font></b>'.format(fname), self)
            msg_label = QLabel(
                '<font color="red">{}</font>'.format(msg), self)
            form.addRow(field_label, msg_label)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok, Qt.Horizontal, self)
        form.addRow(self.buttons)
        self.buttons.accepted.connect(self.accept)


class ProgressDialog(QProgressDialog):
    def __init__(self, title='Progress', label='In progress...', maximum=10,
                 parent=None):
        super(ProgressDialog, self).__init__(parent)
        self.setModal(True)
        self.setWindowTitle(title)
        self.setLabelText(label)
        # self.setMinimum(0)
        self.setMaximum(maximum)
        # this sets minimum duration at 100 ms (i.e. sure to display)
        self.setMinimumDuration(0)
        self.setValue(0)
        self.show()


class Viewer3DDialog(QDialog):
    """
    A Dialog for CAD viewer.
    """
    def __init__(self, parent=None):
        super(Viewer3DDialog, self).__init__(parent)
        self.setWindowTitle("CAD Viewer")
        self.cad_viewer = QtViewer3DColor(self)
        self.cad_viewer.setSizePolicy(QSizePolicy.Expanding,
                                      QSizePolicy.Expanding)
        self.resize(800, 600)
        layout = QVBoxLayout()
        layout.addWidget(self.cad_viewer)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok |
                                        QDialogButtonBox.Cancel,
                                        Qt.Horizontal, self)
        layout.addWidget(self.buttons)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

    def view_cad(self, file_path):
        self.cad_viewer.init_shape_from_STEP(file_path)


class AssemblyNodeDialog(QDialog):
    """
    A dialog to edit reference_designator and quantity (or system_role) on a
    system assembly tree node Acu (or ProjectSystemUsage).
    """
    def __init__(self, ref_des, quantity, system=False, parent=None):
        super(AssemblyNodeDialog, self).__init__(parent)
        self.setWindowTitle("Edit System Tree Node")
        self.ref_des = ref_des or ''
        self.quantity = quantity or 1
        form = QFormLayout(self)
        if system:
            ref_des_label = QLabel('System Role', self)
        else:
            ref_des_label = QLabel('Reference Designator', self)
        self.ref_des_field = StringFieldWidget(parent=self, value=ref_des)
        form.addRow(ref_des_label, self.ref_des_field)
        if not system:
            quantity_label = QLabel('Quantity', self)
            self.quantity_field = IntegerFieldWidget(parent=self,
                                                     value=self.quantity)
            # self.quantity_field.setInputMask('D99')
            form.addRow(quantity_label, self.quantity_field)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        form.addRow(self.buttons)
        self.buttons.accepted.connect(self.on_save)
        self.buttons.rejected.connect(self.reject)

    def on_save(self):
        self.ref_des = self.ref_des_field.get_value()
        if hasattr(self, 'quantity_field'):
            self.quantity = self.quantity_field.get_value()
        self.accept()


class PopupDialogMixin(object):
    def make_popup(self, call_widget):
        """
        Turns the dialog into a popup dialog.
        call_widget is the widget responsible for calling the dialog (e.g. a
        toolbar button)
        """
        self.setContentsMargins(0,0,0,0)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Popup)
        self.setObjectName('ImportDialog')
        # Move the dialog to the widget that called it
        point = call_widget.rect().bottomRight()
        global_point = call_widget.mapToGlobal(point)
        self.move(global_point - QPoint(0, 0))


class ObjectSelectionDialog(QDialog, PopupDialogMixin):
    """
    Dialog for selecting an object from a set of objects.  Used by various
    interfaces -- e.g., used by PgxnObject to populate a foreign key
    attribute.
    """
    def __init__(self, objs, view=None, with_none=False, parent=None):
        """
        Args:
            objs (list):  list of objects

        Keyword Args:
            view (list):  list of strings (field names)
            parent (QWidget):  parent widget
        """
        super(ObjectSelectionDialog, self).__init__(parent)
        self.setSizePolicy(QSizePolicy.MinimumExpanding,
                           QSizePolicy.MinimumExpanding)
        self.objs = objs
        cname = ''
        if objs:
            cname = objs[0].__class__.__name__
            self.setWindowTitle(get_external_name_plural(cname))
        self.oids = [obj.oid for obj in self.objs]
        if with_none:
            self.oids.insert(0, None)
        view = view or SELECTION_VIEWS.get(cname,
                                           ['id', 'name', 'description'])
        self.table_model = ObjectTableModel(objs, view=view,
                                            with_none=with_none, parent=self)
        self.table_view = QTableView()
        self.table_view.setSelectionBehavior(QTableView.SelectRows)
        self.table_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # self.table_view.horizontalHeader().hide()          
        self.table_view.verticalHeader().hide()
        self.table_view.setModel(self.table_model)
        self.table_view.resizeColumnsToContents()
        self.table_view.clicked.connect(self.select_object)
        self.bbox = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.bbox.rejected.connect(self.reject)
        layout = QVBoxLayout()
        layout.addWidget(self.table_view)
        layout.addWidget(self.bbox)
        self.setLayout(layout)
        w = self.table_view.horizontalHeader().length() + 24
        h = self.table_view.verticalHeader().length() + 100
        default_h = state['height']
        if default_h < h:
            h = default_h
        self.setFixedSize(w, h)

    def get_oid(self):
        return self.oid

    def select_object(self, clicked_index):
        row = clicked_index.row()
        self.oid = self.oids[row]
        self.accept()


class CloakingDialog(QDialog):
    """
    Dialog for displaying the current cloaking status of an object and, if the
    user is the creator of the object, offering decloaking options.
    """
    def __init__(self, obj, msg, actors, decloak_button=True, parent=None):
        """
        Args:
            obj (Identifiable):  the object whose status is to be displayed
            msg (str):  message returned from 'get_cloaking_status'
            actors (list of Actor):  list of Actors to which the object has
                been decloaked

        Keyword Args:
            decloak_button (bool):  include the 'Decloak' button if True and
                the user has 'decloak' permission (only set to False if the
                dialog is being used to show the status as a result of a
                'decloak' operation)
        """
        super(CloakingDialog, self).__init__(parent)
        self.setWindowTitle('Cloaking')
        # self.setSizePolicy(QSizePolicy.MinimumExpanding,
                           # QSizePolicy.MinimumExpanding)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.obj = obj
        cloaked = False
        if msg == 'cloaked':
            cloaked = True
            form.addRow(NameLabel("Object is cloaked"))
        elif 'public' in actors:
            form.addRow(NameLabel(msg))
        elif not msg and actors:
            form.addRow(NameLabel("Object is decloaked to:"))
            actor_labels = [ValueLabel('{} ({})'.format(a.id, a.name))
                            for a in actors]
            for label in actor_labels:
                form.addRow(label)
        else:
            form.addRow(NameLabel("Object not found"))
        # OK button
        self.bbox = QDialogButtonBox(
            QDialogButtonBox.Close, Qt.Horizontal, self)
        form.addRow(self.bbox)
        self.bbox.rejected.connect(self.reject)
        # Add 'Decloak' button if object is cloaked and user is creator
        if cloaked and hasattr(obj, 'creator'):
            creator_oid = getattr(obj.creator, 'oid', None)
            if creator_oid and creator_oid == state.get('local_user_oid'):
                self.decloak_button = self.bbox.addButton('Decloak',
                                                   QDialogButtonBox.ActionRole)
                self.decloak_button.clicked.connect(self.on_decloak)
        layout.addLayout(form)

    def on_decloak(self):
        dispatcher.send(signal='decloaking', oid=self.obj.oid)
        self.reject()


class UnitPrefsDialog(QDialog):
    """
    Dialog for setting preferred units for specified dimensions.
    Preferred units are stored in a `units` dict within the `prefs` dict
    in the form:

        {dimensions (str) : preferred units (str)}
    """
    def __init__(self, parent=None):
        super(UnitPrefsDialog, self).__init__(parent)
        self.setWindowTitle("Units Preferences")
        form = QFormLayout(self)
        dim_labels = {}
        self.dim_widgets = {}
        if not prefs.get('units'):
            prefs['units'] = {}
        settables = [dims for dims in parmz_by_dimz if alt_units.get(dims)]
        for dims in settables:
            dim_labels[dims] = QLabel(dims, self)
            units = prefs['units'].get(dims, in_si[dims])
            choices = alt_units[dims]
            self.dim_widgets[dims] = UnitsWidget(dims, units, choices)
            self.dim_widgets[dims].setCurrentText(units)
            form.addRow(dim_labels[dims], self.dim_widgets[dims])
        # Apply and Close buttons
        self.bbox = QDialogButtonBox(
                                QDialogButtonBox.Close, Qt.Horizontal, self)
        apply_btn = self.bbox.addButton(QDialogButtonBox.Apply)
        apply_btn.clicked.connect(self.set_units)
        self.bbox.rejected.connect(self.reject)
        form.addRow(self.bbox)

    def set_units(self):
        # msg = '<h3>Preferred Units set to:</h3><ul>'
        for dims, widget in self.dim_widgets.items():
            prefs['units'][dims] = widget.get_value()
            # msg += '<li>{}: {}</li>'
        # msg += '</ul>'
        dispatcher.send('dashboard mod')


class PrefsDialog(QDialog):
    def __init__(self, parent=None):
        super(PrefsDialog, self).__init__(parent)
        self.setWindowTitle("Preferences")
        form = QFormLayout(self)
        clear_rows_label = QLabel('Delete empty rows in imported data', self)
        self.clear_rows = QCheckBox(self)
        if prefs.get('clear_rows') is False:
            self.clear_rows.setChecked(False)
        else:
            self.clear_rows.setChecked(True)
        form.addRow(clear_rows_label, self.clear_rows)
        dash_row_colors_label = QLabel(
                                  'Use alternating colors for dashboard rows',
                                  self)
        self.dash_row_colors = QCheckBox(self)
        if prefs.get('dash_no_row_colors'):
            self.dash_row_colors.setChecked(False)
        else:
            self.dash_row_colors.setChecked(True)
        self.dash_row_colors.toggled.connect(self.set_dash_row_colors)
        form.addRow(dash_row_colors_label, self.dash_row_colors)
        num_fmt_label = QLabel('Numeric Format', self)
        self.num_fmt_select = QComboBox()
        self.num_fmt_select.activated.connect(self.set_num_fmt)
        for nfmt in NUMERIC_FORMATS:
            self.num_fmt_select.addItem(nfmt, QVariant())
        nf = prefs.get('numeric_format')
        if nf in NUMERIC_FORMATS:
            self.num_fmt_select.setCurrentIndex(NUMERIC_FORMATS.index(nf))
        form.addRow(num_fmt_label, self.num_fmt_select)
        num_prec_label = QLabel('Numeric Precision', self)
        self.num_prec_select = QComboBox()
        self.num_prec_select.activated.connect(self.set_num_prec)
        for num_prec in NUMERIC_PRECISION:
            self.num_prec_select.addItem(num_prec, QVariant())
        np = prefs.get('numeric_precision')
        if np in NUMERIC_PRECISION:
            self.num_prec_select.setCurrentIndex(NUMERIC_PRECISION.index(np))
        else:
            self.num_prec_select.setCurrentIndex(NUMERIC_PRECISION.index('4'))
        form.addRow(num_prec_label, self.num_prec_select)
        unit_prefs_button = SizedButton("Set Preferred Units")
        unit_prefs_button.clicked.connect(self.set_preferred_units)
        form.addRow(unit_prefs_button)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        form.addRow(self.buttons)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

    def get_clear_rows(self):
        return self.clear_rows.isChecked()

    def set_dash_row_colors(self):
        prefs['dash_no_row_colors'] = not self.dash_row_colors.isChecked()
        dispatcher.send('dashboard mod')

    def get_dash_row_colors(self):
        return self.dash_row_colors.isChecked()

    def set_num_fmt(self, index):
        """
        Set the numeric format.
        """
        orb.log.info('* [orb] setting numeric format preference ...')
        try:
            nf = NUMERIC_FORMATS[index]
            prefs['numeric_format'] = nf
            orb.log.info('        set to "{}"'.format(nf))
            dispatcher.send('set numeric format', numeric_format=nf)
        except:
            orb.log.debug('        invalid index ({})'.format(index))

    def set_num_prec(self, index):
        """
        Set the numeric format.
        """
        orb.log.info('* [orb] setting numeric precision preference ...')
        try:
            np = NUMERIC_PRECISION[index]
            prefs['numeric_precision'] = np
            orb.log.info('        set to "{}"'.format(np))
            dispatcher.send('set numeric precision', numeric_precision=np)
        except:
            orb.log.debug('        invalid index ({})'.format(index))

    def set_preferred_units(self):
        dlg = UnitPrefsDialog(self)
        dlg.show()


class DeleteColsDialog(QDialog):
    """
    Dialog for deleting columns from the dashboard.
    """
    def __init__(self, parent=None):
        super(DeleteColsDialog, self).__init__(parent)
        self.setWindowTitle("Delete Columns")
        form = QFormLayout(self)
        self.checkboxes = {}
        pids = prefs['dashboards'][state['dashboard_name']]
        names = [orb.select('ParameterDefinition', id=p).name for p in pids]
        for i, pid in enumerate(pids):
            label = QLabel(names[i], self)
            self.checkboxes[pid] = QCheckBox(self)
            self.checkboxes[pid].setChecked(False)
            form.addRow(self.checkboxes[pid], label)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        form.addRow(self.buttons)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)


class NewDashboardDialog(QDialog):
    """
    Dialog for deleting columns from the dashboard.
    """
    def __init__(self, parent=None):
        super(NewDashboardDialog, self).__init__(parent)
        self.setWindowTitle("New Dashboard")
        form = QFormLayout(self)
        dash_name_label = QLabel('Name of new dashboard:', self)
        self.new_dash_name = QLineEdit(self)
        form.addRow(dash_name_label, self.new_dash_name)
        txt = 'Make this the\npreferred dashboard'
        pref_dash_label = QLabel(txt, self)
        self.preferred_dash = QCheckBox(self)
        self.preferred_dash.setChecked(False)
        form.addRow(pref_dash_label, self.preferred_dash)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        form.addRow(self.buttons)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)


class CircleWidget(QWidget):
    """
    A hypnotic widget of concentrically cycling circles.
    """
    def __init__(self, parent=None):
        super(CircleWidget, self).__init__(parent)
        self.nframe = 0
        self.setBackgroundRole(QPalette.Base)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def minimumSizeHint(self):
        return QSize(50, 50)

    def sizeHint(self):
        return QSize(80, 80)

    def next(self):
        self.nframe += 1
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(self.width() / 2.0, self.height() / 2.0)

        #range of diameter must start at a number greater than 0
        for diameter in range(1, 50, 9):
            delta = abs((self.nframe % 64) - diameter / 2.0)
            alpha = 255 - (delta * delta) / 4.0 - diameter
            if alpha > 0:
                painter.setPen(QPen(QColor(0, diameter / 2.0, 127, alpha), 3))
                painter.drawEllipse(QRectF(
                    -diameter / 2.0,
                    -diameter / 2.0, 
                    diameter, 
                    diameter))


class IdValidationPopup(QWidget):
    """
    A Popup for use in real-time `id` attribute validation, to help avoid
    duplicate `id` values.
    """
    def __init__(self, text, valid=True, parent=None):
        """
        Args:
            text (str):  text from `id` field widget

        Keyword Args:
            valid (bool):  flag indicating whether to show the text as valid or
                not (green or red) -- the caller should should set valid to
                False if the text matches another object's `id` value)
        """
        QWidget.__init__(self, parent)
        layout = QHBoxLayout(self)
        label = QLabel(text, self)
        label.setMargin(2)
        label.setFrameStyle(QFrame.Box | QFrame.Plain)
        label.setLineWidth(1)
        label.setStyleSheet('color: {}; background-color: yellow'.format(
                                                                COLORS[valid]))
        layout.addWidget(label)
        # adjust the margins to avoid invisible border (default is 5)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        self.adjustSize()
        self.setWindowFlags(Qt.Popup)
        # calculate the botoom right point from the parents rectangle
        point = parent.rect().bottomRight()
        # map that point as a global position
        global_point = parent.mapToGlobal(point)
        # by default, a widget will be placed from its top-left corner, so
        # move it to the left based on the widgets width
        self.move(global_point - QPoint(parent.width(), 0))


if __name__ == '__main__':
    """Script mode for testing."""
    app = QApplication(sys.argv)
    window = PrefsDialog()
    window.show()
    sys.exit(app.exec_())

