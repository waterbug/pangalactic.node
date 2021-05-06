"""
Various dialogs.
"""
# NOTE:  deprecated class CondaDialog retired to "pgef_sandbox" in
# 'dialogs_with_CondaDialog.py'
# NOTE:  deprecated modules p.n.threads and process have been retired to the
# "pgef_sandbox", as they were used with the now-deprecated CondaDialog ...
# from pangalactic.node.threads     import threadpool, Worker
# from pangalactic.node.process     import run_conda

import os, sys
from textwrap import wrap

from PyQt5.QtCore import Qt, QPoint, QRectF, QSize, QTimer, QVariant
from PyQt5.QtGui import QColor, QPainter, QPen, QPalette
from PyQt5.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox,
                             QDialog, QDialogButtonBox, QFileDialog,
                             QFormLayout, QFrame, QHBoxLayout, QLabel,
                             QLineEdit, QProgressDialog, QRadioButton,
                             QScrollArea, QSizePolicy, QTableView,
                             QVBoxLayout, QWidget)

from louie import dispatcher

from pangalactic.core             import prefs, state
from pangalactic.core.access      import get_perms
from pangalactic.core.meta        import (NUMERIC_FORMATS, NUMERIC_PRECISION,
                                          SELECTION_VIEWS)
from pangalactic.core.parametrics import (de_defz, parm_defz, parmz_by_dimz,
                                          get_dval, set_dval)
from pangalactic.core.uberorb     import orb
from pangalactic.core.units       import alt_units, in_si
from pangalactic.core.utils.datetimes import dtstamp, date2str
from pangalactic.core.utils.meta  import (get_attr_ext_name,
                                          get_external_name_plural)
from pangalactic.core.utils.reports import get_mel_data, write_mel_to_tsv
from pangalactic.node.buttons     import SizedButton
from pangalactic.node.tablemodels import ObjectTableModel, ODTableModel
from pangalactic.node.trees       import ParmDefTreeView
from pangalactic.node.utils       import clone
from pangalactic.node.widgets     import UnitsWidget
from pangalactic.node.widgets     import (FloatFieldWidget, IntegerFieldWidget,
                                          StringFieldWidget)

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


class FullSyncDialog(QDialog):
    """
    Dialog for confirming a "Force Full Sync" operation.
    """
    def __init__(self, parent=None):
        """
        Initializer.

        Keyword Args:
            parent (QWidget):  parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("Danger Danger Danger!")
        msg = '<b><font color="red">Full Re-sync will overwrite '
        msg += 'all local data -- continue?</font></b>'
        msg_label = QLabel(msg, self)
        form = QFormLayout(self)
        form.addRow(msg_label)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        self.buttons.button(QDialogButtonBox.Ok).setText('Yes')
        self.buttons.button(QDialogButtonBox.Cancel).setText('No')
        form.addRow(self.buttons)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)


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
        # NOTE: float() cast is needed because (for now)
        # FloatFieldWidget.get_value() returns a string (guaranteed to be
        # castable to a float, at least ;)
        setattr(self.req, self.parm, float(self.parm_field.get_value()))
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
            self.quantity = int(self.quantity_field.get_value())
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


class MiniMelDialog(QDialog):
    """
    Dialog to display a Mini MEL (a Master Equipment List for a specified
    system).

    Attrs:
        mel_data (list of dicts):  a MEL dataset generated by
            p.core.utils.reports.get_mel_data()
    """
    def __init__(self, obj, parent=None):
        """
        Args:
            obj (HardwareProduct):  an instance of PGEF HardwareProduct that is
                a white box model (has components)

        Keyword Args:
            parent (QWidget):  parent widget
        """
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.MinimumExpanding,
                           QSizePolicy.MinimumExpanding)
        self.obj = obj
        layout = QVBoxLayout()
        self.setLayout(layout)
        self.dash_name = state.get('dashboard_name') or 'MEL'
        dash_schemas = prefs.get('dashboards') or {}
        self.data_cols = dash_schemas.get(self.dash_name)
        # set up dashboard selector
        # TODO:  in addition to dashboard names, give options to use all
        # default parameters or all parameters defined for self.obj
        self.dash_select = QComboBox()
        self.dash_select.setStyleSheet(
                            'font-weight: bold; font-size: 14px')
        for dash_name in prefs['dashboard_names']:
            self.dash_select.addItem(dash_name, QVariant)
        self.dash_select.setCurrentIndex(0)
        self.dash_select.activated.connect(self.on_dash_select)
        self.export_tsv_button = SizedButton("Export as tsv")
        self.export_tsv_button.clicked.connect(self.export_tsv)
        top_layout = QHBoxLayout()
        top_layout.addWidget(self.dash_select)
        top_layout.addWidget(self.export_tsv_button)
        top_layout.addStretch(1)
        layout.addLayout(top_layout)
        # set up mel table
        self.set_mini_mel_table()

    def on_dash_select(self, index):
        self.dash_name = prefs['dashboard_names'][index]
        dash_schemas = prefs.get('dashboards') or {}
        self.data_cols = dash_schemas.get(self.dash_name)
        self.set_mini_mel_table()

    def export_tsv(self):
        """
        [Handler for 'export as tsv' button]  Write the dashboard content to a
        tab-separated-values file.  Parameter values will be expressed in the
        user's preferred units, and headers will be explicitly annotated with
        units.
        """
        orb.log.debug('* export_tsv()')
        dtstr = date2str(dtstamp())
        name = '-' + self.dash_name + '-'
        fname = self.obj.id + name + dtstr + '.tsv'
        state_path = state.get('mini_mel_last_path') or ''
        suggested_fpath = os.path.join(state_path, fname)
        fpath, filters = QFileDialog.getSaveFileName(
                                    self, 'Write to tsv File',
                                    suggested_fpath, '(*.tsv)')
        if fpath:
            orb.log.debug(f'  - file selected: "{fpath}"')
            fpath = str(fpath)   # extra-cautious :)
            state['mini_mel_last_path'] = os.path.dirname(fpath)
            data_cols = prefs['dashboards'].get(self.dash_name)
            orb.log.debug(f'  - data cols: "{str(data_cols)}"')
            write_mel_to_tsv(self.obj, schema=data_cols, pref_units=True,
                             file_path=fpath)
            html = '<h3>Success!</h3>'
            msg = 'Mini MEL exported to file:'
            html += f'<p><b><font color="green">{msg}</font></b><br>'
            html += f'<b><font color="blue">{fpath}</font></b></p>'
            self.w = NotificationDialog(html, news=False, parent=self)
            self.w.show()
        else:
            orb.log.debug('  ... export to tsv cancelled.')
            return

    def set_mini_mel_table(self):
        layout = self.layout()
        if getattr(self, 'mini_mel_table', None):
            # remove and close current table
            layout.removeWidget(self.mini_mel_table)
            self.mini_mel_table.parent = None
            self.mini_mel_table.close()
        raw_data = get_mel_data(self.obj, schema=self.data_cols)
        # transform keys to formatted headers with units
        self.mel_data = [{self.get_header(col_id) : row[col_id]
                          for col_id in row}
                          for row in raw_data]
        mini_mel_model = ODTableModel(self.mel_data)
        self.mini_mel_table = QTableView()
        self.mini_mel_table.setAttribute(Qt.WA_DeleteOnClose)
        self.mini_mel_table.setModel(mini_mel_model)
        self.mini_mel_table.setAlternatingRowColors(True)
        self.mini_mel_table.setShowGrid(False)
        self.mini_mel_table.setSelectionBehavior(1)
        self.mini_mel_table.setStyleSheet('font-size: 12px')
        self.mini_mel_table.verticalHeader().hide()
        self.mini_mel_table.clicked.connect(self.item_selected)
        col_header = self.mini_mel_table.horizontalHeader()
        col_header.setStyleSheet('font-weight: bold')
        self.mini_mel_table.setSizePolicy(QSizePolicy.Expanding,
                                          QSizePolicy.Expanding)
        self.mini_mel_table.setSizeAdjustPolicy(QTableView.AdjustToContents)
        QTimer.singleShot(0, self.mini_mel_table.resizeColumnsToContents)
        layout.addWidget(self.mini_mel_table)

    def get_header(self, col_id):
        # code borrowed from systemtree.py, modified
        pd = parm_defz.get(col_id)
        if pd:
            units = prefs['units'].get(pd['dimensions'], '') or in_si.get(
                                                    pd['dimensions'], '')
            if units:
                units = '(' + units + ')'
            return '   \n   '.join(wrap(pd['name'], width=7,
                                   break_long_words=False) + [units])
        elif col_id in de_defz:
            de_def = de_defz.get(col_id, '')
            if de_def:
                return '   \n   '.join(wrap(de_def['name'], width=7,
                                       break_long_words=False))
        else:
            txt = ' '.join([s.capitalize() for s in col_id.split('_')])
            return txt

    def item_selected(self, clicked_index):
        """
        Handler for a clicked row (display something about the object?)
        """
        orb.log.debug('* mini mel item selected')
        # clicked_row = clicked_index.row()
        # item_data = self.mel_data[clicked_row]


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
        orb.log.debug('Preferred Units set to:')
        for dims, widget in self.dim_widgets.items():
            val = widget.get_value()
            prefs['units'][dims] = val
            orb.log.debug(f'  - {dims}: {val}')


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

    Keyword Args:
        cols (list of str): names of current columns
    """
    def __init__(self, title=None, cols=None, selectables=None, parent=None):
        super().__init__(parent)
        title = title or "Select Columns"
        self.setWindowTitle(title)
        self.setStyleSheet('QToolTip { font-weight: normal; font-size: 12px; '
                           'color: black; background: white;};')
        cols = cols or []
        self.checkboxes = {}
        selectables = selectables or []
        selectables.sort()
        names = self.get_col_names(selectables)
        nbr_of_cols = len(selectables) // 40
        if len(selectables) % 40:
            nbr_of_cols += 1
        form = QFormLayout()
        subforms = []
        for n in range(nbr_of_cols):
            subforms.append(QFormLayout())
        hbox = QHBoxLayout(self)
        hbox.addLayout(form)
        for subform in subforms:
            hbox.addLayout(subform)
        for i, pid in enumerate(selectables):
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
            subforms[i // 40].addRow(self.checkboxes[pid], label)
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


class Panel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

    def sizeHint(self):
        return QSize(400, 600)


class ScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)

    def sizeHint(self):
        return QSize(400, 600)


cloning_instructions = """
<h3>Instructions</h3>
<p>You are cloning a <b>White Box</b> item, meaning it has a known<br>
set of components.  You have the option to create a clone that is a<br>
<b>White Box</b> or a <b>Black Box</b> (unspecified components):
<ul>
<li><b>White Box Clone</b>:<br>
you can select all or any subset of the components<br>
of the original item to be components of the clone</li>
<li><b>Black Box Clone</b>:<br>
the clone will have no specified components,<br>
but you have the option of setting the <i>Mass</i>, <i>Power</i>,<br>
and <i>Data Rate</i> of the clone to be the <i>CBE</i> values<br>
of those parameters in the original item.</li>
<ul>
</p>
"""

white_box_heading = """
<h3>White Box Clone</h3>
Select all or any subset of the components<br>
of the original item to be components of the clone:
"""

black_box_heading = """
<h3>Black Box Clone</h3>
<p>You can <b>flatten</b> the original object to create the clone:<br>
i.e. set the <i>Mass</i>, <i>Power</i>, and <i>Data Rate</i><br>
of the clone from the <i>CBE</i> values of those parameters<br>
in the original object (which are the summed values of those<br>
parameters over its components).</p>
<p>If you do <i>not</i> choose <b>flatten</b>, all parameter and data<br>
element values of the original object will simply be copied over<br>
to the clone.</p>
"""


class CloningDialog(QDialog):
    """
    Dialog for selecting options to use when cloning a product that has
    components: black box or white box; if black box, option to roll up CBE
    values of components into clone's parameters; if white box, it will include
    refs (new Acus) to selected components of the cloned object.

    NOTE:  calling clone() (as this dialog does) automatically signals the
    "pangalaxian" interface to go into "Component Modeler" mode, so that the
    clone can have its properties edited and components can be added or
    modified.
    """
    def __init__(self, obj, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.MinimumExpanding,
                           QSizePolicy.MinimumExpanding)
        orb.log.debug(f'* CloningDialog({obj.id})')
        self.setWindowTitle("Clone")
        self.obj = obj
        self.main_layout = QVBoxLayout(self)
        self.instructions_label = QLabel(cloning_instructions)
        self.instructions_label.setAttribute(Qt.WA_DeleteOnClose)
        self.main_layout.addWidget(self.instructions_label)
        self.blackwhite_layout = QVBoxLayout()
        self.blackwhite_buttons = QButtonGroup()
        self.white_box_button = QRadioButton('Create White Box Clone')
        self.white_box_button.clicked.connect(self.set_white_box)
        self.black_box_button = QRadioButton('Create Black Box Clone')
        self.black_box_button.clicked.connect(self.set_black_box)
        self.blackwhite_buttons.addButton(self.white_box_button)
        self.blackwhite_buttons.addButton(self.black_box_button)
        self.blackwhite_layout.addWidget(self.white_box_button)
        self.blackwhite_layout.addWidget(self.black_box_button)
        self.main_layout.addLayout(self.blackwhite_layout)

    def set_white_box(self):
        self.main_layout.removeItem(self.blackwhite_layout)
        self.main_layout.removeWidget(self.instructions_label)
        self.instructions_label.close()
        heading = QLabel(white_box_heading)
        self.main_layout.addWidget(heading)
        self.comp_checkboxes = {}
        self.cb_all = QCheckBox(self)
        self.cb_all.clicked.connect(self.on_check_all)
        cb_all_txt = "SELECT ALL / CLEAR SELECTIONS"
        cb_all_label = QLabel(cb_all_txt, self)
        white_box_form = QFormLayout()
        white_box_form.addRow(self.cb_all, cb_all_label)
        for acu in self.obj.components:
            comp = acu.component
            ptype = getattr(comp.product_type, 'abbreviation')
            ptype = ptype or getattr(comp.product_type, 'id',
                                     '[unknown type]')
            refdes = acu.reference_designator or ptype
            name_str = '[' + refdes + '] ' + comp.name
            id_str = '(' + comp.id + ')'
            label_text = '\n'.join([name_str, id_str])
            label = QLabel(label_text, self)
            self.comp_checkboxes[acu.oid] = QCheckBox(self)
            self.comp_checkboxes[acu.oid].setChecked(False)
            white_box_form.addRow(self.comp_checkboxes[acu.oid], label)
        self.white_box_panel = Panel()
        self.white_box_panel.setLayout(white_box_form)
        self.white_box_scroll_area = ScrollArea()
        self.white_box_scroll_area.setWidget(self.white_box_panel)
        self.main_layout.addWidget(self.white_box_scroll_area, 1)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        self.main_layout.addWidget(self.buttons)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.resize(500, 700)
        self.updateGeometry()

    def set_black_box(self):
        self.main_layout.removeItem(self.blackwhite_layout)
        self.main_layout.removeWidget(self.instructions_label)
        self.instructions_label.close()
        self.white_box_button.close()
        self.black_box_button.close()
        heading = QLabel(black_box_heading)
        self.main_layout.addWidget(heading)
        black_box_form = QFormLayout()
        self.black_box_panel = Panel()
        self.black_box_panel.setLayout(black_box_form)
        self.flatten_cb = QCheckBox(self)
        label = QLabel('flatten', self)
        black_box_form.addRow(self.flatten_cb, label)
        self.main_layout.addWidget(self.black_box_panel)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        self.main_layout.addWidget(self.buttons)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.updateGeometry()

    def on_check_all(self):
        if self.cb_all.isChecked():
            for cb in self.comp_checkboxes.values():
                cb.setChecked(True)
        else:
            for cb in self.comp_checkboxes.values():
                cb.setChecked(False)

    def accept(self):
        if self.white_box_button.isChecked():
            orb.log.debug('  - creating white box clone ...')
            # TODO:  progress bar -- cloning takes time!
            if self.cb_all.isChecked():
                # original clone() -- include all components
                self.new_obj = clone(self.obj)
            else:
                acus = []
                for acu_oid, cb in self.comp_checkboxes.items():
                    if cb.isChecked():
                        acu = orb.get(acu_oid)
                        acus.append(acu)
                sel_comps = str([acu.reference_designator for acu in acus])
                orb.log.debug(f'  - selected components: {sel_comps}')
                # NOTE:  calling clone() will automatically put pangalaxian
                # into "Component Modeler" mode
                self.new_obj = clone(self.obj,
                                     include_specified_components=acus)
        elif self.black_box_button.isChecked():
            orb.log.debug('  - creating black box clone ...')
            if self.flatten_cb.isChecked():
                # NOTE:  calling clone() will automatically put pangalaxian
                # into "Component Modeler" mode
                self.new_obj = clone(self.obj, include_components=False,
                                     flatten=True)
            else:
                self.new_obj = clone(self.obj, include_components=False)
        super().accept()


class ConnectionsDialog(QDialog):
    """
    Dialog for selecting, inspecting, and deleting connections (diagram objects
    that are instances of RoutedConnector, for which the underlying "model"
    objects are Flow instances) associated with a block in an IBD (Internal
    Block Diagram). Note that each block in such a diagram represents a
    component "usage" (an Acu instance) in the assembly that is the subject of
    the diagram.
    """
    def __init__(self, scene, usage, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connections")
        form = QFormLayout(self)
        self.scene = scene
        self.checkboxes = {}
        self.flows = {}
        self.conns = {}
        flows = orb.get_all_usage_flows(usage)
        for flow in flows:
            start_txt = ' '.join([flow.start_port.of_product.name,
                                  flow.start_port.name, 'to'])
            end_txt = ' '.join([flow.end_port.of_product.name,
                                flow.end_port.name])
            label_text = '\n'.join([start_txt, end_txt])
            label = QLabel(label_text, self)
            self.checkboxes[flow.oid] = QCheckBox(self)
            self.checkboxes[flow.oid].setChecked(False)
            self.checkboxes[flow.oid].stateChanged.connect(self.show_conns)
            self.flows[flow.oid] = flow
            start_port_block = scene.port_blocks.get(flow.start_port.oid)
            end_port_block = scene.port_blocks.get(flow.end_port.oid)
            start_conns = set(start_port_block.connectors)
            end_conns = set(end_port_block.connectors)
            self.conns[flow.oid] = start_conns & end_conns
            form.addRow(self.checkboxes[flow.oid], label)
        # Delete and Cancel buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        if (state.get('connected') and hasattr(usage, 'assembly')
            and 'modify' in get_perms(usage.assembly)):
            self.buttons.addButton("Delete Selected Connections",
                                   QDialogButtonBox.AcceptRole)
            self.buttons.accepted.connect(self.accept)
        form.addRow(self.buttons)
        self.buttons.rejected.connect(self.reject)

    def show_conns(self):
        checked_flows = 0
        orb.log.debug('* connections:')
        for flow_oid, cb in self.checkboxes.items():
            flow = self.flows[flow_oid]
            if cb.isChecked():
                checked_flows += 1
                orb.log.debug(f'  checked: {flow.name}')
                if self.conns[flow_oid]:
                    for conn in self.conns[flow_oid]:
                        conn.pen.setColor(Qt.black)
                else:
                    orb.log.debug('  no connector found.')
            else:
                if self.conns[flow_oid]:
                    for conn in self.conns[flow_oid]:
                        conn.pen.setColor(conn.color)
        if not checked_flows:
            orb.log.debug('  None.')
        self.scene.update()

    def accept(self):
        for flow_oid, cb in self.checkboxes.items():
            flow = self.flows[flow_oid]
            if cb.isChecked():
                orb.delete([flow])
                dispatcher.send(signal='deleted object', oid=flow_oid,
                                cname='Flow')
        for flow_oid in self.checkboxes:
            if orb.get(flow_oid):
                for conn in self.conns[flow_oid]:
                    conn.pen.setColor(conn.color)
        super().accept()

    def reject(self):
        for flow_oid in self.checkboxes:
            if self.conns.get(flow_oid):
                for conn in self.conns[flow_oid]:
                    conn.pen.setColor(conn.color)
        super().reject()


class DirectionalityDialog(QDialog):
    """
    Dialog for selecting the "directionality" assigned to a Port, which may be
    "input", "output", or "bidirectional" (default).

    Args:
        port (Port): port to receive directionality

    Keyword Args:
        allowed (set of str): allowed directionalities
    """
    def __init__(self, port, allowed=None, parent=None):
        super().__init__(parent)
        orb.log.debug('* DirectionalityDialog')
        self.setWindowTitle("Directionality")
        port_dir = get_dval(port.oid, 'directionality') or 'bidirectional'
        self.port = port
        orb.log.debug(f'  directionality is currently "{port_dir}"')
        layout = QVBoxLayout(self)
        if allowed is None:
            allowed = set(['input', 'output', 'bidirectional'])
        if allowed != set(['input', 'output', 'bidirectional']):
            msg = '<b><font color="red">Directionality is constrained by<br>'
            msg += 'other ports connected to this one.</font></b>'
            msg_label = QLabel(msg, self)
            layout.addWidget(msg_label)
        self.dir_buttons = QButtonGroup()
        self.input_button = QRadioButton('input')
        self.output_button = QRadioButton('output')
        self.bidir_button = QRadioButton('bidirectional')
        self.dir_buttons.addButton(self.input_button)
        self.dir_buttons.addButton(self.output_button)
        self.dir_buttons.addButton(self.bidir_button)
        layout.addWidget(self.input_button)
        layout.addWidget(self.output_button)
        layout.addWidget(self.bidir_button)
        if 'input' not in allowed:
            self.input_button.setEnabled(False)
        if 'output' not in allowed:
            self.output_button.setEnabled(False)
        if port_dir == 'input':
            self.input_button.setChecked(True)
        elif port_dir == 'output':
            self.output_button.setChecked(True)
        else:
            self.bidir_button.setChecked(True)
        self.dir_buttons.buttonClicked.connect(self.set_directionality)

    def set_directionality(self, clicked_index):
        b = self.dir_buttons.checkedButton()
        port_dir = b.text()
        orb.log.debug(f'  setting directionality to: "{port_dir}"')
        set_dval(self.port.oid, 'directionality', port_dir)
        NOW = dtstamp()
        user = orb.get(state.get('local_user_oid'))
        self.port.mod_datetime = NOW
        self.port.modifier = user
        product = self.port.of_product
        product.mod_datetime = NOW
        product.modifier = user
        orb.db.commit()
        dispatcher.send(signal='modified object', obj=self.port)
        dispatcher.send(signal='modified object', obj=product)
        self.accept()


class NewDashboardDialog(QDialog):
    """
    Dialog for creating a new dashboard.
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

