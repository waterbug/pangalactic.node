"""
Various dialogs.
"""
# NOTE:  deprecated class CondaDialog retired to "pgef_sandbox" in
# 'dialogs_with_CondaDialog.py'
# NOTE:  deprecated modules p.n.threads and process have been retired to the
# "pgef_sandbox", as they were used with the now-deprecated CondaDialog ...
# from pangalactic.node.threads     import threadpool, Worker
# from pangalactic.node.process     import run_conda

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
from pangalactic.core.parametrics import de_defz, parm_defz, parmz_by_dimz
from pangalactic.core.uberorb     import orb
from pangalactic.core.units       import alt_units, in_si
from pangalactic.core.utils.meta  import (get_attr_ext_name,
                                          get_external_name_plural)
from pangalactic.node.buttons     import SizedButton
from pangalactic.node.tablemodels import ObjectTableModel
from pangalactic.node.trees       import ParmDefTreeView
from pangalactic.node.widgets     import UnitsWidget
from pangalactic.node.widgets     import FloatFieldWidget, StringFieldWidget

COLORS = {True: 'green', False: 'red'}


class ParmDefsDialog(QDialog):
    """
    Dialog to display the Parameter Definition Tree
    """
    def __init__(self, parent=None):
        """
        Dialog for the Parameter Definition Tree.

        Keyword Args:
            parent (QWidget):  parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("Parameter Definitions")
        self.parm_tree = ParmDefTreeView(parent=self)
        self.parm_tree.setWindowTitle('Parameter Definition Library')
        layout = QVBoxLayout()
        layout.addWidget(self.parm_tree)
        layout.setContentsMargins(1, 1, 1, 1)
        self.setLayout(layout)
        # self.adjustSize()

    def minimumSizeHint(self):
        return QSize(300, 300)

    def sizeHint(self):
        return QSize(800, 800)


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
        super().__init__(parent)
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
    def __init__(self, something, news=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Notification")
        form = QFormLayout(self)
        if news:
            something_happened_label = QLabel('News:', self)
            something_happened = QLabel(something, self)
            form.addRow(something_happened_label, something_happened)
        else:
            something_happened = QLabel(something, self)
            form.addRow(something_happened)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok,
                                        Qt.Horizontal, self)
        form.addRow(self.buttons)
        self.buttons.accepted.connect(self.accept)


class OptionNotification(QDialog):
    def __init__(self, title, message, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        form = QFormLayout(self)
        note_label = QLabel(title + ':', self)
        message_label = QLabel(message, self)
        form.addRow(note_label, message_label)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok,
                                        Qt.Horizontal, self)
        form.addRow(self.buttons)
        self.buttons.accepted.connect(self.accept)


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
        super().__init__(parent)
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
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle(title)
        self.setLabelText(label)
        # self.setMinimum(0)
        self.setMaximum(maximum)
        # this sets minimum duration at 100 ms (i.e. sure to display)
        self.setMinimumDuration(0)
        self.setValue(0)
        self.show()


class ReqParmDialog(QDialog):
    """
    A dialog to edit the value of performance requirement parameters.
    """
    def __init__(self, req, parm, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Requirement Parameters")
        self.req = req
        self.parm = parm
        parm_name = get_attr_ext_name('Requirement', parm)
        parm_label = QLabel(parm_name, self)
        parm_val = getattr(req, parm, 0.0)
        self.parm_field = FloatFieldWidget(parent=self, value=parm_val)
        units_label = QLabel(req.req_units, self)
        form = QFormLayout(self)
        # TODO: add units label (needs hbox)
        hbox = QHBoxLayout()
        hbox.addWidget(self.parm_field)
        hbox.addWidget(units_label)
        form.addRow(parm_label, hbox)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        form.addRow(self.buttons)
        self.buttons.accepted.connect(self.on_save)
        self.buttons.rejected.connect(self.reject)

    def on_save(self):
        setattr(self.req, self.parm, self.parm_field.get_value())
        # re-generate requirement 'description'
        self.req.description = ' '.join([str(self.req.req_subject),
                                         str(self.req.req_predicate),
                                         str(self.parm_field.get_value()),
                                         str(self.req.req_units)])
        orb.save([self.req])
        dispatcher.send(signal='modified object', obj=self.req,
                        cname='Requirement')
        self.accept()


class AssemblyNodeDialog(QDialog):
    """
    A dialog to edit reference_designator and quantity (or system_role) on a
    system assembly tree node Acu (or ProjectSystemUsage).
    """
    def __init__(self, ref_des, quantity, system=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit System Tree Node")
        self.ref_des = ref_des or ''
        self.quantity = quantity or 1.0
        form = QFormLayout(self)
        if system:
            ref_des_label = QLabel('System Role', self)
        else:
            ref_des_label = QLabel('Reference Designator', self)
        self.ref_des_field = StringFieldWidget(parent=self, value=ref_des)
        form.addRow(ref_des_label, self.ref_des_field)
        if not system:
            quantity_label = QLabel('Quantity', self)
            self.quantity_field = FloatFieldWidget(parent=self,
                                                   value=self.quantity)
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
        self.move(global_point - QPoint(100, 0))


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
        super().__init__(parent)
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
        # self.table_view.resizeColumnsToContents()
        # resize only the 'id' and 'name' columns to their contents; let
        # 'description' column wrap (default behavior)
        self.table_view.resizeColumnToContents(0)
        self.table_view.resizeColumnToContents(1)
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


class UnitPrefsDialog(QDialog):
    """
    Dialog for setting preferred units for specified dimensions.
    Preferred units are stored in a `units` dict within the `prefs` dict
    in the form:

        {dimensions (str) : preferred units (str)}
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferred Units")
        form = QFormLayout(self)
        dim_labels = {}
        self.dim_widgets = {}
        if not prefs.get('units'):
            prefs['units'] = {}
        settables = [dims for dims in parmz_by_dimz if alt_units.get(dims)]
        for dims in settables:
            if dims:
                dim_labels[dims] = QLabel(dims, self)
            else:
                # dims == '' -> angle
                dim_labels[dims] = QLabel('angle', self)
            units = prefs['units'].get(dims, in_si[dims])
            choices = alt_units[dims]
            self.dim_widgets[dims] = UnitsWidget(dims, units, choices)
            self.dim_widgets[dims].setCurrentText(units)
            self.dim_widgets[dims].currentIndexChanged.connect(self.set_units)
            form.addRow(dim_labels[dims], self.dim_widgets[dims])
        # Ok and Close buttons
        self.bbox = QDialogButtonBox(Qt.Horizontal, self)
        ok_btn = self.bbox.addButton(QDialogButtonBox.Ok)
        ok_btn.clicked.connect(self.accept)
        form.addRow(self.bbox)

    def set_units(self):
        # msg = '<h3>Preferred Units set to:</h3><ul>'
        for dims, widget in self.dim_widgets.items():
            prefs['units'][dims] = widget.get_value()
            # msg += '<li>{}: {}</li>'
        # msg += '</ul>'
        # dispatcher.send('dashboard mod')


class PrefsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        form = QFormLayout(self)
        clear_rows_label = QLabel('Delete empty rows in imported data', self)
        self.clear_rows = QCheckBox(self)
        if prefs.get('clear_rows') is False:
            self.clear_rows.setChecked(False)
        else:
            self.clear_rows.setChecked(True)
        form.addRow(clear_rows_label, self.clear_rows)
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


class SelectColsDialog(QDialog):
    """
    Dialog for selecting from columns to customize a view.

    Args:
        columns (list of str):  the list of column names to select from
        view (list of str):  the current view to be customized
    """
    def __init__(self, columns, view, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Columns")
        if len(columns) < 25:
            form = QFormLayout(self)
        elif len(columns) >= 25:
            # create another form layout for the right side
            form = QFormLayout()
            r_form = QFormLayout()
            hbox = QHBoxLayout(self)
            hbox.addLayout(form)
            hbox.addLayout(r_form)
        # else:
            # Hm, should we do more wrapping in case > 50 columns?
        self.checkboxes = {}
        for i, col in enumerate(columns):
            label = QLabel(col, self)
            col_def = de_defz.get(col) or parm_defz.get(col)
            if col_def:
                dtxt = col_def.get('description', '')
                dtype = col_def.get('range_datatype', '')
                dims = col_def.get('dimensions', '')
                tt = f'<font><color="green">{dtype}</color></font>'
                if dims:
                    tt += f' <font><color="purple">[{dims}]</color></font>'
                tt += f' {dtxt}'
                label.setToolTip(tt)
            self.checkboxes[col] = QCheckBox(self)
            if col in view:
                self.checkboxes[col].setChecked(True)
            else:
                self.checkboxes[col].setChecked(False)
            if i < 25:
                form.addRow(self.checkboxes[col], label)
            else:
                r_form.addRow(self.checkboxes[col], label)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        form.addRow(self.buttons)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)


class CustomizeColsDialog(QDialog):
    """
    Dialog for selecting columns for the dashboard.
    """
    def __init__(self, cols=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Columns")
        self.setStyleSheet('QToolTip { font-weight: normal; font-size: 12px; '
                           'color: black; background: white;};')
        cols = cols or []
        form = QFormLayout()
        m_form = QFormLayout()
        r_form = QFormLayout()
        hbox = QHBoxLayout(self)
        hbox.addLayout(form)
        hbox.addLayout(m_form)
        hbox.addLayout(r_form)
        self.checkboxes = {}
        all_pids = list(de_defz) + list(parm_defz)
        all_pids.sort()
        names = self.get_col_names(all_pids)
        for i, pid in enumerate(all_pids):
            label = QLabel(names[i], self)
            col_def = de_defz.get(pid) or parm_defz.get(pid)
            if col_def:
                dtxt = col_def.get('description', '')
                dtype = col_def.get('range_datatype', '')
                dims = col_def.get('dimensions', '')
                tt = f'type: {dtype}<br>'
                if dims:
                    tt += f'dimensions: {dims}<br>'
                tt += f'definition: {dtxt}'
                label.setToolTip(tt)
            self.checkboxes[pid] = QCheckBox(self)
            if pid in cols:
                self.checkboxes[pid].setChecked(True)
            else:
                self.checkboxes[pid].setChecked(False)
            if pid in cols:
                self.checkboxes[pid].setChecked(True)
            else:
                self.checkboxes[pid].setChecked(False)
            if 0 <= i < 40:
                form.addRow(self.checkboxes[pid], label)
            elif 40 <= i < 80:
                m_form.addRow(self.checkboxes[pid], label)
            else:
                r_form.addRow(self.checkboxes[pid], label)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        form.addRow(self.buttons)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

    def get_col_names(self, pids):
        col_names = []
        for pid in pids:
            if parm_defz.get(pid):
                col_names.append(parm_defz[pid]['name'])
            elif de_defz.get(pid):
                col_names.append(de_defz[pid]['name'])
            else:
                col_names.append('Unknown')
        return col_names


class DeleteColsDialog(QDialog):
    """
    Dialog for deleting columns from the dashboard.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Delete Columns")
        form = QFormLayout(self)
        self.checkboxes = {}
        pids = prefs['dashboards'][state['dashboard_name']]
        names = self.get_col_names(pids)
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

    def get_col_names(self, pids):
        col_names = []
        for pid in pids:
            if parm_defz.get(pid):
                col_names.append(parm_defz[pid]['name'])
            elif de_defz.get(pid):
                col_names.append(de_defz[pid]['name'])
            else:
                col_names.append('Unknown')
        return col_names


class NewDashboardDialog(QDialog):
    """
    Dialog for deleting columns from the dashboard.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
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
        super().__init__(parent)
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

