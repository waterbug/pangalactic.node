"""
Various dialogs.
"""
import sys

from PyQt5.QtCore import (pyqtSignal, Qt, QObject, QPoint, QRectF, QSize,
                          QVariant)
from PyQt5.QtGui import QColor, QPainter, QPen, QPalette
from PyQt5.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                             QDialogButtonBox, QFormLayout, QFrame,
                             QHBoxLayout, QLabel, QLineEdit, QProgressBar,
                             QProgressDialog, QScrollArea, QSizePolicy,
                             QTableView, QTextBrowser, QVBoxLayout, QWidget)

from louie import dispatcher

from pangalactic.core             import config, prefs, state
from pangalactic.core.meta        import (NUMERIC_FORMATS, NUMERIC_PRECISION,
                                          SELECTION_VIEWS)
from pangalactic.core.parametrics import parmz_by_dimz
from pangalactic.core.uberorb     import orb
from pangalactic.core.units       import alt_units, in_si
from pangalactic.core.utils.meta  import get_external_name_plural
from pangalactic.node.buttons     import SizedButton
from pangalactic.node.cad.viewer  import QtViewer3DColor
from pangalactic.node.tablemodels import ObjectTableModel
from pangalactic.node.threads     import threadpool, Worker
from pangalactic.node.widgets     import NameLabel, UnitsWidget, ValueLabel
from pangalactic.node.process     import run_conda
from pangalactic.node.widgets     import AsciiFieldWidget, IntegerFieldWidget


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


# OutputStream and OutputWidget show output of text stream ... not currently
# used (were used previously by CondaDialog)
class OutputStream(QObject):
    text_written = pyqtSignal(str)

    def write(self, text):
        self.text_written.emit(str(text))

    def flush(self):
        pass


class OutputWidget(QTextBrowser):
    def __init__(self, parent=None):
        super(OutputWidget, self).__init__(parent)
        palette = QPalette()
        palette.setColor(QPalette.Base, QColor("#ddddfd"))
        self.setPalette(palette)
        self.setStyleSheet('font-size: 18px')
        self.setSizePolicy(QSizePolicy.Expanding,
                           QSizePolicy.Expanding)


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
        self.setMinimumDuration(100)
        self.setValue(0)
        self.show()


class CondaProgressDialog(QDialog):
    def __init__(self, title, action_name, maximum=100, parent=None):
        super(CondaProgressDialog, self).__init__(parent)
        self.vbox = QVBoxLayout(self)
        self.setModal(True)
        self.setWindowTitle(title)
        self.action_name = QLabel(action_name)
        if action_name == 'List Packages':
            self.connect_label = QLabel('<b>collecting package names ...</b>',
                                        self)
        else:
            self.connect_label = QLabel('<b>connecting ...</b>', self)
        self.install_label = QLabel('', self)
        self.vbox.addWidget(self.action_name)
        self.vbox.addWidget(self.connect_label)
        self.vbox.addWidget(self.install_label)
        self.progress_bar = QProgressBar(self)
        # min and max both set to 0 initially so progress bar "spins" until
        # the first signal is received from the process
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(0)
        self.vbox.addWidget(self.progress_bar)


class CondaDialog(QDialog):
    """
    Dialog for interacting with conda.
    """
    CONDA_CHANNELS = ['defaults', 'conda-forge', 'pythonocc', 'oce', 'dlr-sc']

    def __init__(self, option, parent=None):
        """
        Initialize a conda dialog for the specified option.

        Args:
            option (str):  one of
                ['update'|'install_admin'|'update_admin'|'list']
        """
        super(CondaDialog, self).__init__(parent)
        self.pkg_name = ''     # set to the pkg being installed/updated
        self.current_pkg = ''  # tracks the current pkg being downloaded
        self.cmd_type = ''
        self.option = option
        self.vbox = QVBoxLayout(self)
        if option == 'list':
            self.setWindowTitle("List Installed Packages")
            self.status_heading = QLabel()
            self.vbox.addWidget(self.status_heading)
            self.status = QLabel()
            self.scroll_area = QScrollArea(self)
            self.scroll_area.setWidget(self.status)
            self.scroll_area.setWidgetResizable(True)
            self.vbox.addWidget(self.scroll_area)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.setGeometry(100, 100, 600, 600)
        else:
            if option == 'install_admin':
                self.setWindowTitle("Install Admin Tool")
            elif option == 'update_admin':
                self.setWindowTitle("Update Admin Tool")
            else:
                self.setWindowTitle("Update")
            self.status_heading = QLabel()
            self.vbox.addWidget(self.status_heading)
            self.status = QLabel()
            self.vbox.addWidget(self.status)
            self.vbox.addStretch(1)
            self.setGeometry(100, 100, 600, 400)
        # Cancel button
        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel, self)
        self.buttons.rejected.connect(self.reject)
        self.vbox.addWidget(self.buttons)
        self.vbox.setAlignment(self.buttons, Qt.AlignLeft|Qt.AlignBottom)
        if option == 'list':
            self.on_list()
        elif option == 'install_admin':
            self.on_install_admin_tool()
        else:
            self.on_update()

    def on_update(self):
        """
        Run conda update [app package].
        """
        orb.log.info('* CondaDialog.on_update()')
        self.cmd_type = 'update'
        update_args = ['update', '--json', '-y']
        # NOTE:  THIS CODE USED FOR TESTING ONLY *********
        # update_args = ['install', '--json', '-y']
        # app_channel = 'http://pangalactic.us/conda_repo'
        # app_channel = 'defaults'
        # self.pkg_name = 'geos'    # or whatever
        # ************************************************
        app_channel = config.get('app_channel')
        if app_channel:
            update_args += ['-c', app_channel]
        for channel in self.CONDA_CHANNELS:
            update_args += ['-c', channel]
        if self.option == 'update':
            self.pkg_name = config.get('app_package_name', 'pangalactic')
        else:  # option 'update_admin'
            self.pkg_name = config.get('admin_package_name')
        update_args.append(self.pkg_name)
        update_args = tuple(update_args)
        msg = '<b>Updating {} to latest version ...</b><br>'.format(
                                                                self.pkg_name)
        self.progress_dialog = CondaProgressDialog('Update', msg,
                                                   parent=self)
        self.progress_dialog.show()
        worker = Worker(run_conda, *update_args)
        worker.signals.progress.connect(self.increment_progress)
        worker.signals.result.connect(self.report_result)
        worker.signals.error.connect(self.log_error)
        worker.signals.finished.connect(self.progress_done)
        orb.log.debug('  - calling conda with args: {}'.format(
                      str(update_args)))
        threadpool.start(worker)

    def log_error(self, error):
        orb.log.info('* CondaDialog.log_error() ...')
        exception_type, value, tb = error
        orb.log.info('  - exception type: {}'.format(str(exception_type)))
        orb.log.info('    value: {}'.format(str(value)))
        orb.log.info('    traceback:')
        orb.log.info(tb)

    def report_result(self, res):
        orb.log.info('* CondaDialog.report_result() ...')
        orb.log.debug(str(res))  # this will log errors, if any
        if res and len(res) == 2:
            status, pkgs = res
            orb.log.info('packages: {}'.format(str(pkgs)))
            orb.log.info('status: {}'.format(status))
            status_label = ''
            heading = '<hr><h3>{}{}</h3>'
            msg = ''
            if status:
                if pkgs:
                    heading_msg = '<font color="green">Success!</font>'
                    if self.cmd_type == 'list':
                        msg += '<b>Installed Packages:</b>'
                    else:
                        status_label = 'Status: '
                        msg += '<b>Packages Installed:</b>'
                    msg += '<ul>'
                    for pkg in pkgs:
                        msg += '<li>{}</li>'.format(pkg)
                    msg += '</ul>'
                    if self.option == 'install_admin':
                        state['admin_installed'] = True
                        self.parent().run_admin_tool_action.setEnabled(True)
                        self.parent().install_admin_action.setEnabled(False)
                    if self.option == 'update':
                        heading_msg += '<p><i>Please restart now to '
                        heading_msg += 'activate the new version.</i></p>'
                        state['restart_needed'] = True
                else:
                    heading_msg = 'Latest version of <font color="green">'
                    heading_msg += '{}</font>'.format(self.pkg_name)
                    heading_msg += ' is already installed.'
            else:
                heading_msg = '<font color="red">Failure!</font>'
                msg += '<b>Please notify your support person ...</b>'
            self.status_heading.setText(heading.format(status_label,
                                                       heading_msg))
            self.status.setText(msg + '<hr>')

    def progress_done(self):
        if getattr(self, 'progress_dialog', None):
            self.progress_dialog.done(0)

    def increment_progress(self, pkg, n):
        """
        Increment progress dialog by value `n` (0 < n < 100).

        Args:
            pkg (str):  name of pkg being installed or updated
            n (int):  % progress
        """
        if self.current_pkg != pkg:
            self.current_pkg = pkg
            msg = '<b>downloading {} ...</b>'.format(pkg)
            self.progress_dialog.install_label.setText(msg)
        if n == 100:
            msg = '<b>installing {} ...</b>'.format(pkg)
            self.progress_dialog.install_label.setText(msg)
        self.progress_dialog.progress_bar.setMaximum(100)
        self.progress_dialog.progress_bar.setValue(n)

    def on_install_admin_tool(self):
        orb.log.info('* CondaDialog.on_install_admin_tool()')
        self.cmd_type = 'install'
        self.pkg_name = config.get('admin_package_name')
        if self.pkg_name:
            # TODO:  check for admin_pkg_name availability in channels
            install_args = ['install', '-y', '--json']
            app_channel = config.get('app_channel',
                                     'http://pangalactic.us/conda_repo')
            if app_channel:
                install_args += ['-c', app_channel]
            for channel in self.CONDA_CHANNELS:
                install_args += ['-c', channel]
            install_args.append(self.pkg_name)
            install_args = tuple(install_args)
            msg = '<b>Installing "{}" ...</b>'.format(self.pkg_name)
            self.progress_dialog = CondaProgressDialog('Install Admin Tool',
                                                       msg, parent=self)
            self.progress_dialog.show()
            orb.log.debug('  - calling conda with args: {}'.format(
                          str(install_args)))
            worker = Worker(run_conda, *install_args)
            worker.signals.progress.connect(self.increment_progress)
            worker.signals.result.connect(self.report_result)
            worker.signals.error.connect(self.log_error)
            worker.signals.finished.connect(self.progress_done)
            orb.log.info('  - installing "{}".'.format(self.pkg_name))
            threadpool.start(worker)
        else:
            orb.log.info('  - failed: `admin_pkg_name` not set in config.')

    def on_list(self):
        orb.log.info('* CondaDialog.on_list()')
        self.cmd_type = 'list'
        msg = '<b>Listing installed packages ...</b>'
        self.progress_dialog = CondaProgressDialog('List Packages',
                                                   msg, parent=self)
        self.progress_dialog.show()
        # TODO:  'list' doesn't need progress, but we need to parse the json
        # and format the output for presentation
        args = ('list', '--json')
        worker = Worker(run_conda, *args)
        worker.signals.result.connect(self.report_result)
        worker.signals.error.connect(self.log_error)
        worker.signals.finished.connect(self.progress_done)
        orb.log.info('  - calling conda with args:')
        orb.log.info('    {}'.format(str(args)))
        threadpool.start(worker)


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
        self.ref_des_field = AsciiFieldWidget(parent=self, value=ref_des)
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
        # currently, actor is left out -- only decloaking to current project
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
        painter.translate(self.width() / 2, self.height() / 2)

        #range of diameter must start at a number greater than 0
        for diameter in range(1, 50, 9):
            delta = abs((self.nframe % 64) - diameter / 2)
            alpha = 255 - (delta * delta) / 4 - diameter
            if alpha > 0:
                painter.setPen(QPen(QColor(0, diameter / 2, 127, alpha), 3))
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

