"""
Various dialogs.
"""
# NOTE:  deprecated class CondaDialog retired to "pgef_sandbox" in
# 'dialogs_with_CondaDialog.py'
# NOTE:  deprecated module p.n.process has been retired to the
# "pgef_sandbox" as it was only used with the now-deprecated CondaDialog ...
# from pangalactic.node.process     import run_conda

# NOTE:  threads module is not currently being used (was previously used in
# CondaDialog)
# from pangalactic.node.threads     import threadpool, Worker

import os, shutil, sys
from pathlib  import Path
from textwrap import wrap

from PyQt5.QtCore import (pyqtSignal, Qt, QPoint, QRectF, QSize, QTimer,
                          QVariant)
from PyQt5.QtGui import QColor, QPainter, QPen, QPalette
from PyQt5.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox,
                             QDialog, QDialogButtonBox, QFileDialog,
                             QFormLayout, QFrame, QHBoxLayout, QLabel,
                             QLineEdit, QProgressDialog, QRadioButton,
                             QScrollArea, QSizePolicy, QTableView,
                             QTableWidget, QTextBrowser, QTextEdit,
                             QVBoxLayout, QWidget)

from pydispatch import dispatcher

from pangalactic.core             import orb, prefs, state
from pangalactic.core.access      import get_perms
from pangalactic.core.clone       import clone
from pangalactic.core.meta        import (M2M, NUMERIC_FORMATS, ONE2M,
                                          NUMERIC_PRECISION, SELECTABLE_VALUES,
                                          SELECTION_FILTERS, SELECTION_VIEWS,
                                          TEXT_PROPERTIES)
from pangalactic.core.names       import (get_attr_ext_name,
                                          get_external_name_plural,
                                          get_link_name)
from pangalactic.core.parametrics import (componentz,
                                          de_defz,
                                          get_power_contexts,
                                          parm_defz,
                                          parmz_by_dimz,
                                          get_dval,
                                          set_dval)
from pangalactic.core.units       import alt_units, in_si, time_unit_names
from pangalactic.core.utils.datetimes import dtstamp, date2str
from pangalactic.core.utils.reports import (get_mel_data, write_mel_to_tsv,
                                            write_mel_to_xlsx)
from pangalactic.node.buttons     import (FileButtonLabel, FkButton,
                                          SizedButton, UrlButton)
from pangalactic.node.tablemodels import ObjectTableModel, MappingTableModel
from pangalactic.node.trees       import ParmDefTreeView
from pangalactic.node.utils       import InfoTableItem
from pangalactic.node.widgets     import (get_widget, ColorLabel,
                                          FloatFieldWidget, HLine,
                                          IntegerFieldWidget, LogWidget,
                                          StringFieldWidget,
                                          StringSelectWidget, TextFieldWidget,
                                          UnitsWidget)

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


class PlotDialog(QDialog):
    """
    Dialog to display a QwtPlot widget.
    """
    def __init__(self, plot_widget, title, parent=None):
        """
        Dialog to display a QwtPlot widget and output some parameters of the
        plot.

        Args:
            plot_widget (QwtPlot): the plot widget to display
            title (str):  title of the plot window

        Keyword Args:
            parent (QWidget):  parent widget
        """
        super().__init__(parent)
        title = title or 'Power vs. Time'
        self.setWindowTitle(title)
        self.plot = plot_widget
        vbox = QVBoxLayout()
        vbox.addWidget(self.plot)
        vbox.setContentsMargins(10, 10, 10, 10)
        self.setLayout(vbox)
        button_box = QHBoxLayout()
        button_box.addStretch(1)
        self.export_to_image_button = SizedButton("Export to Image")
        self.export_to_image_button.clicked.connect(self.export_to_image)
        button_box.addWidget(self.export_to_image_button, alignment=Qt.AlignRight)
        self.export_to_pdf_button = SizedButton("Export to PDF")
        self.export_to_pdf_button.clicked.connect(self.export_to_pdf)
        button_box.addWidget(self.export_to_pdf_button, alignment=Qt.AlignRight)
        vbox.addLayout(button_box)
        self.resize(1500, 700)

    def sizeHint(self):
        return QSize(1000, 800)

    def get_user_home(self):
        """
        Path to the user's home directory.
        """
        p = Path(orb.home)
        absp = p.resolve()
        home = absp.parent
        return str(home)

    def export_to_image(self):
        orb.log.debug('* export_to_image()')
        dtstr = date2str(dtstamp())
        user_home = self.get_user_home() or ''
        if not state.get('last_plot_path'):
            state['last_plot_path'] = user_home
        txt = '-'.join(self.plot.title().text().split(' '))
        fname = txt + '-' + dtstr + '.png'
        file_path = os.path.join(state['last_plot_path'], fname)
        fpath, filters = QFileDialog.getSaveFileName(
                                    self, 'Export Plot to Image',
                                    file_path)
        if fpath:
            if not fpath.endswith('.png'):
                fpath += '.png'
            orb.log.debug(f'  - file selected: "{fpath}"')
            state['last_path'] = os.path.dirname(fpath)
            self.plot.exportTo(fpath, size=(1400, 600))
        else:
            return

    def export_to_pdf(self):
        orb.log.debug('* export_to_pdf()')
        dtstr = date2str(dtstamp())
        user_home = self.get_user_home() or ''
        if not state.get('last_plot_path'):
            state['last_plot_path'] = user_home
        txt = '-'.join(self.plot.title().text().split(' '))
        fname = txt + '-' + dtstr + '.pdf'
        file_path = os.path.join(state['last_plot_path'], fname)
        fpath, filters = QFileDialog.getSaveFileName(
                                    self, 'Export Plot to PDF',
                                    file_path)
        if fpath:
            if not fpath.endswith('.pdf'):
                fpath += '.pdf'
            orb.log.debug(f'  - file selected: "{fpath}"')
            state['last_path'] = os.path.dirname(fpath)
            self.plot.exportTo(fpath, size=(1400, 600))
        else:
            return


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
        self.setWindowTitle("Danger, Will Robinson!")
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


class DefineModesDialog(QDialog):
    """
    Dialog for confirming that the user wants to define power modes for the
    specified product usage.
    """
    def __init__(self, usage=None, parent=None):
        """
        Initializer.

        Keyword Args:
            usage (Modelable):  the usage -- either a ProjectSystemUsage or an
                Acu (both are subclasses of Modelable)
            parent (QWidget):  parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("Define Power Modes for System?")
        name = get_link_name(usage)
        msg = f'<b><font color="blue">The {name} system does not yet have<br>'
        msg += 'power modes defined for it -- define them now?</font></b>'
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


class VersionDialog(QDialog):
    def __init__(self, html, url, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Download Current Version")
        vbox = QVBoxLayout(self)
        browsable_widget = QTextBrowser(parent=self)
        browsable_widget.setHtml(html)
        vbox.addWidget(browsable_widget)
        if url:
            download_button = UrlButton(value=url)
            vbox.addWidget(download_button)
        self.resize(600, 300)
        download_button.clicked.connect(self.accept)


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
        self.setMaximum(maximum)
        self.setMinimumDuration(0)
        self.setValue(0)
        # do not show a cancel button:
        self.setCancelButton(None)
        self.show()


class HWFieldsDialog(QDialog):
    """
    A dialog to edit selected fields of a HardwareProduct.
    """

    hw_fields_edited = pyqtSignal(str)  # arg: oid

    def __init__(self, hw_item, parent=None):
        super().__init__(parent)
        self.hw_item = hw_item
        self.setWindowTitle(f"Product {hw_item.id}")
        names = ['name', 'description', 'product_type', 'owner']
        vbox = QVBoxLayout(self)
        self.form = QFormLayout()
        self.fields = {}
        vbox.addLayout(self.form)
        for name in names:
            ename = get_attr_ext_name('HardwareProduct', name)
            schema = orb.schemas['HardwareProduct']
            if name in SELECTABLE_VALUES:
                val = getattr(hw_item, name)
                if val:
                    widget = StringSelectWidget(parent=self, field_name=name,
                                                value=val)
                else:
                    widget = StringSelectWidget(parent=self, field_name=name)
                widget.setStyleSheet('font-weight: bold;')
            elif name in TEXT_PROPERTIES:
                val = getattr(hw_item, name) or ''
                widget = TextFieldWidget(parent=self, value=val)
            elif schema['fields'][name]['range'] in orb.classes:
                val = getattr(hw_item, name) or None
                widget = FkButton(parent=self, value=val)
                widget.field_name = name
                widget.clicked.connect(self.on_select_related)
            else:
                val = getattr(hw_item, name) or ''
                widget = StringFieldWidget(parent=self, value=val)
            label = QLabel(ename, self)
            self.fields[name] = widget
            self.form.addRow(label, widget)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        vbox.addWidget(self.buttons)
        self.buttons.accepted.connect(self.on_save)
        self.buttons.rejected.connect(self.reject)

    def on_select_related(self):
        # orb.log.info('* [pgxo] select related object ...')
        widget = self.sender()
        # TODO:  if None, give option to create a new object
        # orb.log.debug('  [pgxo] current object: %s' % str(obj))
        cname = 'Requirement'
        field_name = widget.field_name
        # SELECTION_FILTERS define the set of valid objects for this field
        objs = []
        if SELECTION_FILTERS.get(field_name):
            fltrs = SELECTION_FILTERS[field_name]
            for cname in fltrs:
                objs += orb.get_by_type(cname)
        else:
            objs = orb.get_all_subtypes(cname)
        if objs:
            # orb.log.debug('  [pgxo] object being edited: {}'.format(
                                                            # self.obj.oid))
            objs.sort(key=lambda x: getattr(x, 'id', '') or '')
            dlg = ObjectSelectionDialog(objs, with_none=False, parent=self)
            if dlg.exec_():
                new_oid = dlg.get_oid()
                new_obj = orb.get(new_oid)
                widget.set_value(new_obj)
        else:
            # TODO:  pop-up message about no objects being available
            pass

    def on_save(self):
        for name, widget in self.fields.items():
            setattr(self.hw_item, name, widget.get_value())
        NOW = dtstamp()
        user = orb.get(state.get('local_user_oid'))
        self.hw_item.mod_datetime = NOW
        self.hw_item.modifier = user
        orb.save([self.hw_item])
        self.hw_fields_edited.emit(self.hw_item.oid)
        # dispatcher.send(signal='modified object', obj=self.hw_item,
                        # cname='HardwareProduct')
        self.accept()


class ModelImportDialog(QDialog):
    """
    A dialog to import a model file.

    Keyword Args:
        of_thing (Modelable): the Model's "of_thing" attribute -- i.e. the
            thing of which the Model is a model
        model_type_id (str): id of ModelType to be imported
        parent (QWidget): parent widget of the dialog
    """
    def __init__(self, of_thing=None, model_type_id='', parent=None):
        super().__init__(parent)
        self.of_thing = of_thing
        name = of_thing.name
        vbox = QVBoxLayout(self)
        if model_type_id:
            self.model_type = orb.select("ModelType", id=model_type_id)
            self.setWindowTitle(f"Import {model_type_id} Model of {name}")
            self.build_form()
        else:
            self.setWindowTitle(f"Import Model of {name}")
            self.model_type_select = QComboBox()
            self.model_type_select.setStyleSheet(
                                'font-weight: bold; font-size: 14px')
            model_types = orb.get_by_type('ModelType')
            self.mts = {mt.id : mt for mt in model_types}
            self.mt_ids = [mt.id for mt in model_types]
            self.mt_ids.sort()
            for mt_id in self.mt_ids:
                self.model_type_select.addItem(mt_id, QVariant)
            self.model_type_select.setCurrentIndex(0)
            self.model_type_select.activated.connect(self.on_model_type_select)
            model_type_layout = QHBoxLayout()
            model_type_layout.addWidget(self.model_type_select)
            model_type_layout.addStretch()
            label = ColorLabel("Select Model Type")
            vbox.addWidget(label)
            vbox.addLayout(model_type_layout)
        self.setMinimumWidth(500)

    def on_model_type_select(self, index):
        self.model_type = self.mts[self.mt_ids[index]]
        orb.log.debug(f'* selected model type: "{self.model_type.id}"')
        # if the form doesn't exist, build it
        if not getattr(self, 'form', None):
            self.build_form()

    def build_form(self):
        vbox = self.layout()
        self.file_select_button = SizedButton("Select Model File")
        self.file_select_button.clicked.connect(self.on_select_file)
        vbox.addWidget(self.file_select_button)
        self.form = QFormLayout()
        vbox.addLayout(self.form)
        self.mtype_oid = getattr(self.model_type, 'oid', '') or ''
        self.model_file_path = ''
        self.fields = {}
        file_widget, autolabel = get_widget('file name', 'str', value='',
                                            editable=False)
        self.fields['file name'] = file_widget
        file_label = ColorLabel('file name')
        self.form.addRow(file_label, file_widget)
        fsize_widget, autolabel = get_widget('file size', 'str', value='',
                                             editable=False)
        self.fields['file size'] = fsize_widget
        fsize_label = ColorLabel('file size')
        self.form.addRow(fsize_label, fsize_widget)
        m_label_text = '------------------- Model Properties '
        m_label_text += '-------------------'
        model_label = ColorLabel(m_label_text)
        self.form.addRow(model_label)
        for name in ['name', 'version', 'description']:
            if name == 'description':
                widget, autolabel = get_widget(name, 'text', value='')
            else:
                widget, autolabel = get_widget(name, 'str', value='')
            label = ColorLabel(name)
            self.fields[name] = widget
            self.form.addRow(label, widget)
        project = orb.get(state.get('project'))
        owner_widget = FkButton(parent=self, value=project)
        owner_widget.field_name = "owner"
        owner_widget.clicked.connect(self.on_select_owner)
        label = ColorLabel('owner')
        self.fields['owner'] = owner_widget
        self.form.addRow(label, owner_widget)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        vbox.addWidget(self.buttons)
        self.buttons.accepted.connect(self.on_submit)
        self.buttons.rejected.connect(self.reject)

    def on_select_file(self, evt):
        dirpath = state.get('last_model_path', '') or ''
        dialog = QFileDialog(self, 'Open File', dirpath)
        fpath = ''
        if dialog.exec_():
            fpaths = dialog.selectedFiles()
            if fpaths:
                fpath = fpaths[0]
            dialog.close()
        if fpath:
            orb.log.debug(f'  file selected: {fpath}')
            self.model_file_path = fpath
            fname = os.path.basename(fpath)
            fsize = os.path.getsize(fpath)
            self.fields['file name'].setText(fname)
            self.fields['file size'].setText(str(fsize))
            state['last_model_path'] = os.path.dirname(fpath)
        else:
            orb.log.debug('  no file was selected.')
            valid_dict = {'file name': 'no file was selected'}
            dlg = ValidationDialog(valid_dict, parent=self)
            dlg.show()
            return

    def on_select_owner(self):
        widget = self.sender()
        objs = orb.get_all_subtypes('Organization')
        objs.sort(key=lambda x: getattr(x, 'id', '') or '')
        dlg = ObjectSelectionDialog(objs, with_none=False, parent=self)
        if dlg.exec_():
            new_oid = dlg.get_oid()
            new_obj = orb.get(new_oid)
            widget.set_value(new_obj)

    def on_submit(self):
        if self.model_file_path:
            parms = {}
            valid_dict = {}
            for name, widget in self.fields.items():
                if name in ['file name', 'file size']:
                    val = widget.text()
                    if val:
                        parms[name] = val
                    else:
                        valid_dict[name] = 'is required'
                elif name == 'owner':
                    val = widget.get_value()
                    if val:
                        owner_oid = getattr(val, 'oid', None) or ''
                        if not owner_oid:
                            owner_oid = state.get('project') or ''
                    else:
                        owner_oid = state.get('project') or ''
                    parms['owner_oid'] = owner_oid
                else:
                    val = widget.get_value()
                    if val:
                        parms[name] = val
                    else:
                        valid_dict[name] = 'is required'
            if valid_dict:
                dlg = ValidationDialog(valid_dict, parent=self)
                dlg.show()
            else:
                parms['project_oid'] = state.get('project') or ''
                parms['of_thing_oid'] = self.of_thing.oid
                orb.log.debug(f'  - mtype_oid: {self.mtype_oid}')
                orb.log.debug(f'  - fpath: {self.model_file_path}')
                orb.log.debug(f'  - parms: {parms}')
                dispatcher.send(signal='add update model',
                                mtype_oid=self.mtype_oid,
                                fpath=self.model_file_path,
                                parms=parms)
                self.accept()
        else:
            orb.log.debug('  no file was selected -- select a file ...')
            return


class DocImportDialog(QDialog):
    """
    A dialog to import a document file.

    Keyword Args:
        rel_obj (Modelable): the related object, which will be the
            "related_item" in a DocumentReference relationship
        parent (QWidget): parent widget of the dialog
    """
    def __init__(self, rel_obj=None, parent=None):
        super().__init__(parent)
        self.rel_obj = rel_obj
        self.setWindowTitle(f"Import Document for {rel_obj.name}")
        self.build_form()
        self.setMinimumWidth(500)

    def build_form(self):
        vbox = QVBoxLayout(self)
        self.file_select_button = SizedButton("Select Document File")
        self.file_select_button.clicked.connect(self.on_select_file)
        vbox.addWidget(self.file_select_button)
        self.form = QFormLayout()
        vbox.addLayout(self.form)
        self.doc_file_path = ''
        self.fields = {}
        file_widget, autolabel = get_widget('file name', 'str', value='',
                                            editable=False)
        self.fields['file name'] = file_widget
        file_label = ColorLabel('file name')
        self.form.addRow(file_label, file_widget)
        fsize_widget, autolabel = get_widget('file size', 'str', value='',
                                             editable=False)
        self.fields['file size'] = fsize_widget
        fsize_label = ColorLabel('file size')
        self.form.addRow(fsize_label, fsize_widget)
        doc_label_text = '------------------- Document Properties '
        doc_label_text += '-------------------'
        doc_label = ColorLabel(doc_label_text)
        self.form.addRow(doc_label)
        for name in ['name', 'version', 'description']:
            if name == 'description':
                widget, autolabel = get_widget(name, 'text', value='')
            else:
                widget, autolabel = get_widget(name, 'str', value='')
            label = ColorLabel(name)
            self.fields[name] = widget
            self.form.addRow(label, widget)
        project = orb.get(state.get('project'))
        owner_widget = FkButton(parent=self, value=project)
        owner_widget.field_name = "owner"
        owner_widget.clicked.connect(self.on_select_owner)
        label = ColorLabel('owner')
        self.fields['owner'] = owner_widget
        self.form.addRow(label, owner_widget)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        vbox.addWidget(self.buttons)
        self.buttons.accepted.connect(self.on_submit)
        self.buttons.rejected.connect(self.reject)

    def on_select_file(self, evt):
        dirpath = state.get('last_doc_path', '') or ''
        dialog = QFileDialog(self, 'Open File', dirpath)
        fpath = ''
        if dialog.exec_():
            fpaths = dialog.selectedFiles()
            if fpaths:
                fpath = fpaths[0]
            dialog.close()
        if fpath:
            orb.log.debug(f'  file selected: {fpath}')
            self.doc_file_path = fpath
            fname = os.path.basename(fpath)
            fsize = os.path.getsize(fpath)
            self.fields['file name'].setText(fname)
            self.fields['file size'].setText(str(fsize))
            state['last_doc_path'] = os.path.dirname(fpath)
        else:
            orb.log.debug('  no file was selected.')
            valid_dict = {'file name': 'no file was selected'}
            dlg = ValidationDialog(valid_dict, parent=self)
            dlg.show()
            return

    def on_select_owner(self):
        widget = self.sender()
        objs = orb.get_all_subtypes('Organization')
        objs.sort(key=lambda x: getattr(x, 'id', '') or '')
        dlg = ObjectSelectionDialog(objs, with_none=False, parent=self)
        if dlg.exec_():
            new_oid = dlg.get_oid()
            new_obj = orb.get(new_oid)
            widget.set_value(new_obj)

    def on_submit(self):
        if self.doc_file_path:
            parms = {}
            valid_dict = {}
            for name, widget in self.fields.items():
                if name in ['file name', 'file size']:
                    val = widget.text()
                    if val:
                        parms[name] = val
                    else:
                        valid_dict[name] = 'is required'
                elif name == 'owner':
                    val = widget.get_value()
                    if val:
                        owner_oid = getattr(val, 'oid', None) or ''
                        if not owner_oid:
                            owner_oid = state.get('project') or ''
                    else:
                        owner_oid = state.get('project') or ''
                    parms['owner_oid'] = owner_oid
                else:
                    val = widget.get_value()
                    if val:
                        parms[name] = val
                    else:
                        valid_dict[name] = 'is required'
            if valid_dict:
                dlg = ValidationDialog(valid_dict, parent=self)
                dlg.show()
            else:
                parms['rel_obj_oid'] = self.rel_obj.oid
                parms['project_oid'] = state.get('project') or ''
                orb.log.debug(f'  - fpath: {self.doc_file_path}')
                orb.log.debug(f'  - parms: {parms}')
                dispatcher.send(signal='add update doc',
                                fpath=self.doc_file_path,
                                parms=parms)
                self.accept()
        else:
            orb.log.debug('  no file was selected -- select a file ...')
            return


class ModelsInfoTable(QTableWidget):
    """
    Table whose purpose is to display information about all Models related to a
    Modelable instance. The rows of the table contain attributes of the Models
    and their associated RepresentationFile(s) and buttons that link to the
    files associated with the RepresentationFile instances.
    """
    def __init__(self, obj=None, view=None, parent=None):
        """
        Initialize

        Keyword Args:
            obj (Modelable):  the Modelable
            view (list):  list of attributes that represent the table coluns
        """
        super().__init__(parent=parent)
        # orb.log.info('* [SystemInfoTable] initializing ...')
        self.obj = obj
        # TODO: get default view from prefs / config
        default_view = [
            'Model ID',
            'Type',
            'Name',
            'Description',
            # 'Version',
            'File(s)',
            'More Info'
            ]
        self.view = view or default_view[:]
        self.setup_table()

    def setup_table(self):
        self.setColumnCount(len(self.view))
        models = getattr(self.obj, 'has_models', []) or []
        if models:
            self.setRowCount(len(models))
        else:
            self.setRowCount(1)
        header_labels = []
        for col_name in self.view:
            header_labels.append('  ' + col_name + '  ')
        self.setHorizontalHeaderLabels(header_labels)
        # populate relevant data
        data = []
        # TODO: list representation "names" for a given model, etc. ...
        for m in self.obj.has_models:
            orb.log.debug('* models found ...')
            m_dict = {}
            m_dict['Model ID'] = m.id
            if m.type_of_model:
                orb.log.debug(f'  type: {m.type_of_model.id}')
                m_dict['Type'] = getattr(m.type_of_model, 'id',
                                               'UNKNOWN')
            m_dict['Name'] = m.name
            m_dict['Description'] = m.description
            if m.has_files:
                if len(m.has_files) == 1:
                    rep_file = m.has_files[0]
                    fname = rep_file.user_file_name or 'unknown'
                    orb.log.debug(f'  1 file found: {fname}')
                    vault_fname = rep_file.oid + '_' + fname
                    vault_file_path = os.path.join(orb.vault, vault_fname)
                    if os.path.exists(vault_file_path):
                        color='green'
                    else:
                        color='purple'
                    label = '  ' + fname + '  '
                    button = FileButtonLabel(label, file=rep_file, color=color)
                    button.clicked.connect(self.on_file_button)
                    m_dict['File(s)'] = button
                elif len(m.has_files) > 1:
                    orb.log.debug(f'  {len(m.has_files)} files found ...')
                    buttons_widget = QWidget()
                    hbox = QHBoxLayout()
                    buttons_widget.setLayout(hbox)
                    for rep_file in m.has_files:
                        fname = rep_file.user_file_name or 'unknown'
                        orb.log.debug(f'  - {fname}')
                        vault_fname = rep_file.oid + '_' + fname
                        vault_file_path = os.path.join(orb.vault, vault_fname)
                        if os.path.exists(vault_file_path):
                            color='green'
                        else:
                            color='purple'
                        label = '  ' + fname + '  '
                        button = FileButtonLabel(label, file=rep_file,
                                                 color=color)
                        button.clicked.connect(self.on_file_button)
                        hbox.addWidget(button)
                    m_dict['File(s)'] = buttons_widget
                mtype = m_dict['Type']
                if mtype == 'LOM':
                    info_button = SizedButton(f"{mtype} Info")
                    info_button.clicked.connect(self.on_more_info)
                    m_dict['More Info'] = info_button
            data.append(m_dict)
        for i, m_dict in enumerate(data):
            for j, name in enumerate(self.view):
                if name in ['File(s)', 'More Info'] and m_dict.get(name):
                    self.setCellWidget(i, j, m_dict[name])
                else:
                    self.setItem(i, j, InfoTableItem(
                        m_dict.get(name) or ''))
        height = self.rowCount() * 20
        self.resize(700, height)

    def on_file_button(self):
        """
        Get info about a model file and/or download or save a local copy of it.
        """
        button = self.sender()
        fname = button.text().strip()
        rep_file = button.file
        orb.log.debug(f'* file button "{fname}" was clicked.')
        # Open a dialog that displays the size of the file and offers to save a
        # copy into a user-specified folder, informing the user if downloading
        # from the server is required.
        dlg = FileInfoDialog(rep_file, parent=self)
        dlg.show()

    def on_more_info(self):
        button = self.sender()
        mtype = button.text().split()[0]
        orb.log.debug(f'* file button for "{mtype}" model was clicked.')
        # REFACTORING IN PROGRESS ...
        # Possibly use ModelDetailDialog for model types that don't have a
        # special interface ...
        for model in self.obj.has_models:
            if model.type_of_model.id == mtype:
                dlg = ModelDetailDialog(model)
                dlg.show()


class DocsInfoTable(QTableWidget):
    """
    Table whose purpose is to display information about all Documents related
    to a Modelable instance. The rows of the table contain attributes of the
    Documents and their associated RepresentationFile(s) and buttons that link
    to the files associated with the RepresentationFile instances.
    """
    def __init__(self, obj=None, view=None, parent=None):
        """
        Initialize

        Keyword Args:
            obj (Modelable):  the Modelable
            view (list):  list of attributes that represent the table coluns
        """
        super().__init__(parent=parent)
        # orb.log.info('* [SystemInfoTable] initializing ...')
        self.obj = obj
        # TODO: get default view from prefs / config
        default_view = [
            'Doc ID',
            'Name',
            'Description',
            # 'Version',
            'File(s)',
            'View'
            ]
        self.view = view or default_view[:]
        self.setup_table()

    def setup_table(self):
        self.setColumnCount(len(self.view))
        docs = [doc_ref.document for doc_ref in self.obj.doc_references]
        if docs:
            self.setRowCount(len(docs))
        else:
            self.setRowCount(1)
        header_labels = []
        for col_name in self.view:
            header_labels.append('  ' + col_name + '  ')
        self.setHorizontalHeaderLabels(header_labels)
        # populate relevant data
        data = []
        # TODO: list representation "names" for a given model, etc. ...
        for doc in docs:
            orb.log.debug('* documents found ...')
            doc_dict = {}
            doc_dict['Doc ID'] = doc.id
            doc_dict['Name'] = doc.name
            doc_dict['Description'] = doc.description
            if doc.has_files:
                if len(doc.has_files) == 1:
                    rep_file = doc.has_files[0]
                    fname = rep_file.user_file_name or 'unknown'
                    orb.log.debug(f'  1 file found: {fname}')
                    vault_fname = rep_file.oid + '_' + fname
                    vault_file_path = os.path.join(orb.vault, vault_fname)
                    if os.path.exists(vault_file_path):
                        color='green'
                    else:
                        color='purple'
                    label = '  ' + fname + '  '
                    button = FileButtonLabel(label, file=rep_file, color=color)
                    button.clicked.connect(self.on_file_button)
                    doc_dict['File(s)'] = button
                    open_button = FileButtonLabel("Open", file=rep_file)
                    open_button.clicked.connect(self.open_doc)
                    doc_dict['View'] = open_button
                elif len(doc.has_files) > 1:
                    orb.log.debug(f'  {len(doc.has_files)} files found ...')
                    buttons_widget = QWidget()
                    hbox = QHBoxLayout()
                    buttons_widget.setLayout(hbox)
                    for rep_file in doc.has_files:
                        fname = rep_file.user_file_name or 'unknown'
                        orb.log.debug(f'  - {fname}')
                        vault_fname = rep_file.oid + '_' + fname
                        vault_file_path = os.path.join(orb.vault, vault_fname)
                        if os.path.exists(vault_file_path):
                            color='green'
                        else:
                            color='purple'
                        label = '  ' + fname + '  '
                        button = FileButtonLabel(label, file=rep_file,
                                                 color=color)
                        button.clicked.connect(self.on_file_button)
                        hbox.addWidget(button)
                    selected = doc.has_files[0]
                    open_button = FileButtonLabel("Open", file=selected)
                    open_button.clicked.connect(self.open_doc)
                    doc_dict['View'] = open_button
                    doc_dict['File(s)'] = buttons_widget
            data.append(doc_dict)
        for i, doc_dict in enumerate(data):
            for j, name in enumerate(self.view):
                if name in ['File(s)', 'View'] and doc_dict.get(name):
                    self.setCellWidget(i, j, doc_dict[name])
                else:
                    self.setItem(i, j, InfoTableItem(
                        doc_dict.get(name) or ''))
        height = self.rowCount() * 20
        self.resize(700, height)

    def on_file_button(self):
        """
        Get info about a model file and/or download or save a local copy of it.
        """
        button = self.sender()
        fname = button.text().strip()
        rep_file = button.file
        orb.log.debug(f'* file button "{fname}" was clicked.')
        # Open a dialog that displays the size of the file and offers to save a
        # copy into a user-specified folder, informing the user if downloading
        # from the server is required.
        dlg = FileInfoDialog(rep_file, parent=self)
        dlg.show()

    def open_doc(self):
        button = self.sender()
        rep_file = button.file
        orb.log.debug('* "Open" button clicked')
        orb.log.debug(f'   for "{rep_file.user_file_name}"')
        dispatcher.send(signal='open doc file', rep_file=rep_file)


class FileInfoDialog(QDialog):
    """
    A dialog to display info about a physical file that is associated with a
    DigitalFile instance and offer to download it and/or save a local copy.

    Keyword Args:
        digital_file (RepresentationFile): the RepresentationFile instance
        parent (QWidget): parent widget of the dialog
    """
    def __init__(self, digital_file, parent=None):
        super().__init__(parent)
        orb.log.debug('* FileInfoDialog()')
        self.vbox = QVBoxLayout(self)
        self.dfile = digital_file
        self.build_info_form()
        vault_file_path = orb.get_vault_fpath(self.dfile)
        if os.path.exists(vault_file_path):
            orb.log.debug('  file exists in local vault')
            save_local_button = SizedButton("Save Local Copy")
            save_local_button.clicked.connect(self.on_save_local)
            self.vbox.addWidget(save_local_button)
        else:
            orb.log.debug('  file not found in local vault')
            download_button = SizedButton("Download File")
            download_button.clicked.connect(self.on_download_file)
            self.vbox.addWidget(download_button)

    def build_info_form(self):
        self.form = QFormLayout()
        self.vbox.addLayout(self.form)
        self.fields = {}
        label_text = '------------------- File Properties '
        label_text += '-------------------'
        file_label = ColorLabel(label_text)
        self.form.addRow(file_label)
        for name in ['user_file_name', 'file_size']:
            widget, autolabel = get_widget(name, 'str',
                                       value=getattr(self.dfile, name, ''),
                                       editable=False)
            label = ColorLabel(name)
            self.fields[name] = widget
            self.form.addRow(label, widget)

    def on_download_file(self, evt):
        dispatcher.send(signal='download file', digital_file=self.dfile)

    def on_save_local(self, evt):
        suggested_path = os.path.join(state.get('last_path', ''),
                                      (self.dfile.user_file_name or ''))
        fpath, filters = QFileDialog.getSaveFileName(
                                    self, 'Save As',
                                    suggested_path)
        if fpath:
            orb.log.debug(f'  - path selected: "{fpath}"')
            # copy vault file to fpath ...
            vault_fpath = orb.get_vault_fpath(self.dfile)
            shutil.copy(vault_fpath, fpath)
            self.accept()
        else:
            self.reject()


class ModelsAndDocsInfoDialog(QDialog):
    """
    Dialog to display info on Models and Documents related to a specified
    Modelable.
    """
    def __init__(self, obj, parent=None):
        """
        Args:
            obj (Modelable):  an instance of PGEF Modelable

        Keyword Args:
            parent (QWidget):  parent widget
        """
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.MinimumExpanding,
                           QSizePolicy.MinimumExpanding)
        self.obj = obj
        self.summary = False
        vbox = QVBoxLayout()
        self.setLayout(vbox)
        self.setWindowTitle("Models and Documents")
        # set up dashboard selector
        top_layout = QHBoxLayout()
        # TODO: add info about Modelable ...
        txt = f'Models and Documents related to {obj.name}'
        self.title = ColorLabel(f'<h3>{txt}</h3>', parent=self)
        top_layout.addWidget(self.title)
        vbox.addLayout(top_layout)
        self.set_tables()

    def set_tables(self):
        layout = self.layout()
        if getattr(self, 'models_table', None):
            # remove and close current models_table and docs_table
            layout.removeWidget(self.models_table)
            self.models_table.parent = None
            self.models_table.close()
            layout.removeWidget(self.docs_table)
            self.docs_table.parent = None
            self.docs_table.close()
        self.models_table = ModelsInfoTable(self.obj)
        self.models_table.setAttribute(Qt.WA_DeleteOnClose)
        self.models_table.setAlternatingRowColors(True)
        # SelectionBehavior: 0 -> select items (1 -> rows)
        self.models_table.setSelectionBehavior(0)
        self.models_table.setStyleSheet('font-size: 12px')
        self.models_table.verticalHeader().hide()
        self.models_table.clicked.connect(self.item_selected)
        col_header = self.models_table.horizontalHeader()
        col_header.setStyleSheet('font-weight: bold')
        self.models_table.setSizePolicy(QSizePolicy.Expanding,
                                 QSizePolicy.Expanding)
        self.models_table.setSizeAdjustPolicy(QTableView.AdjustToContents)
        self.models_table.setShowGrid(True)
        QTimer.singleShot(0, self.models_table.resizeColumnsToContents)
        layout.addWidget(self.models_table)
        # docs table
        self.docs_table = DocsInfoTable(self.obj)
        self.docs_table.setAttribute(Qt.WA_DeleteOnClose)
        self.docs_table.setAlternatingRowColors(True)
        # SelectionBehavior: 0 -> select items (1 -> rows)
        self.docs_table.setSelectionBehavior(0)
        self.docs_table.setStyleSheet('font-size: 12px')
        self.docs_table.verticalHeader().hide()
        self.docs_table.clicked.connect(self.item_selected)
        col_header = self.docs_table.horizontalHeader()
        col_header.setStyleSheet('font-weight: bold')
        self.docs_table.setSizePolicy(QSizePolicy.Expanding,
                                 QSizePolicy.Expanding)
        self.docs_table.setSizeAdjustPolicy(QTableView.AdjustToContents)
        self.docs_table.setShowGrid(True)
        QTimer.singleShot(0, self.docs_table.resizeColumnsToContents)
        layout.addWidget(self.docs_table)
        height = self.models_table.height() + self.docs_table.height() + 300
        # orb.log.debug(f'* height to fit tables: {height}')
        screen_height = QApplication.desktop().screenGeometry().height()
        # orb.log.debug(f'* screen height: {screen_height}')
        optimal_height = min(height, screen_height)
        width = self.models_table.width() + 200
        self.resize(width, optimal_height)

    def item_selected(self, clicked_index):
        """
        Handler for a clicked row ...
        """
        clicked_row = clicked_index.row()
        clicked_col = clicked_index.column()
        orb.log.debug(f'* item selected: ({clicked_row}, {clicked_col})')


class ModelDetailDialog(QDialog):
    """
    A dialog to display all available details about a Model.
    """
    def __init__(self, model, parent=None):
        """
        Args:
            model (Model): the Model instance

        Keyword Args:
            parent (QWidget):  parent widget
        """
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.MinimumExpanding,
                           QSizePolicy.MinimumExpanding)
        mtype = model.type_of_model.id
        layout = QVBoxLayout()
        self.setLayout(layout)
        self.setWindowTitle(f"{mtype} Details")
        # set up dashboard selector
        top_layout = QHBoxLayout()
        thing_name = model.of_thing.name
        self.title = ColorLabel(f'<h3>{mtype} Model of {thing_name}</h3>',
                                parent=self)
        top_layout.addWidget(self.title)
        layout.addLayout(top_layout)


class NotesDialog(QDialog):
    """
    A dialog to edit a "description" or notes about an object.
    Motivating use case is for notes about an Activity in a ConOps
    model.

    Args:
        obj (Identifiable): the object

    Keyword Args:
        parent (QWidget): parent widget of the dialog
    """
    def __init__(self, obj, parent=None):
        super().__init__(parent)
        self.obj = obj
        self.setWindowTitle(f"{obj.name}")
        vbox = QVBoxLayout(self)
        title = ColorLabel(f'<h3>Notes on {obj.name}</h3>', parent=self)
        vbox.addWidget(title)
        self.editor = QTextEdit()
        self.editor.setFrameStyle(QFrame.Sunken)
        display_txt = obj.description or ''
        self.editor.setText(display_txt)
        vbox.addWidget(self.editor)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        vbox.addWidget(self.buttons)
        self.buttons.accepted.connect(self.on_save)
        self.buttons.rejected.connect(self.reject)
        self.resize(500, 500)

    def on_save(self):
        NOW = dtstamp()
        user = orb.get(state.get('local_user_oid'))
        self.obj.mod_datetime = NOW
        self.obj.modifier = user
        self.obj.description = self.editor.toPlainText()
        orb.save([self.obj])
        dispatcher.send(signal='modified object', obj=self.obj)
        self.accept()


class DisplayNotesDialog(QDialog):
    """
    A dialog to display "description" or notes for an object.
    Motivating use case is for notes about an Activity / mode.

    Args:
        obj (Identifiable): the object

    Keyword Args:
        parent (QWidget): parent widget of the dialog
    """
    def __init__(self, obj, parent=None):
        super().__init__(parent)
        self.obj = obj
        self.setWindowTitle(f"{obj.name}")
        vbox = QVBoxLayout(self)
        title = ColorLabel(f'<h3>Notes on {obj.name}</h3>', parent=self)
        vbox.addWidget(title)
        self.editor = QTextEdit()
        self.editor.setFrameStyle(QFrame.Sunken)
        display_txt = obj.description or ''
        self.editor.setText(display_txt)
        self.editor.setReadOnly(True)
        vbox.addWidget(self.editor)
        self.resize(500, 500)


class RqtFieldsDialog(QDialog):
    """
    A dialog to edit fields of a requirement.

    Args:
        rqt (Requirement): the req whose fields are to be edited
        names (list of str): the names of the fields to be edited

    Keyword Args:
        parent (QWidget): parent widget of the dialog
    """
    def __init__(self, rqt, names, parent=None):
        super().__init__(parent)
        self.rqt = rqt
        self.setWindowTitle(f"Requirement {rqt.id}")
        vbox = QVBoxLayout(self)
        self.form = QFormLayout()
        self.fields = {}
        vbox.addLayout(self.form)
        for name in names:
            ename = get_attr_ext_name('Requirement', name)
            schema = orb.schemas['Requirement']
            if name in SELECTABLE_VALUES:
                val = getattr(rqt, name)
                if val:
                    widget = StringSelectWidget(parent=self, field_name=name,
                                                value=val)
                else:
                    widget = StringSelectWidget(parent=self, field_name=name)
                widget.setStyleSheet('font-weight: bold;')
            elif name in TEXT_PROPERTIES:
                val = getattr(rqt, name) or ''
                widget = TextFieldWidget(parent=self, value=val)
            elif schema['fields'][name]['range'] in orb.classes:
                val = getattr(rqt, name) or None
                widget = FkButton(parent=self, value=val)
                widget.field_name = name
                widget.clicked.connect(self.on_select_related)
            else:
                val = getattr(rqt, name)
                field_type = schema['fields'][name]['field_type']
                # ignoring returned label (autolabel) ...
                widget, autolabel = get_widget(name, field_type, value=val)
            label = QLabel(ename, self)
            self.fields[name] = widget
            self.form.addRow(label, widget)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        vbox.addWidget(self.buttons)
        self.buttons.accepted.connect(self.on_save)
        self.buttons.rejected.connect(self.reject)

    def on_select_related(self):
        # orb.log.info('* [pgxo] select related object ...')
        widget = self.sender()
        # TODO:  if None, give option to create a new object
        # orb.log.debug('  [pgxo] current object: %s' % str(obj))
        cname = 'Requirement'
        field_name = widget.field_name
        # SELECTION_FILTERS define the set of valid objects for this field
        objs = []
        if SELECTION_FILTERS.get(field_name):
            fltrs = SELECTION_FILTERS[field_name]
            for cname in fltrs:
                objs += orb.get_by_type(cname)
        else:
            objs = orb.get_all_subtypes(cname)
        if objs:
            # orb.log.debug('  [pgxo] object being edited: {}'.format(
                                                            # self.obj.oid))
            objs.sort(key=lambda x: getattr(x, 'id', '') or '')
            dlg = ObjectSelectionDialog(objs, with_none=False, parent=self)
            if dlg.exec_():
                new_oid = dlg.get_oid()
                new_obj = orb.get(new_oid)
                widget.set_value(new_obj)
        else:
            # TODO:  pop-up message about no objects being available
            pass

    def on_save(self):
        for name, widget in self.fields.items():
            setattr(self.rqt, name, widget.get_value())
        NOW = dtstamp()
        user = orb.get(state.get('local_user_oid'))
        self.rqt.mod_datetime = NOW
        self.rqt.modifier = user
        orb.save([self.rqt])
        dispatcher.send(signal='modified object', obj=self.rqt,
                        cname='Requirement')
        self.accept()


class RqtParmDialog(QDialog):
    """
    A dialog to edit the value of performance requirement parameters.
    """

    rqt_parm_mod = pyqtSignal(str)  # arg: oid

    def __init__(self, rqt, parm, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Requirement Parameters")
        self.rqt = rqt
        self.parm = parm
        parm_name = get_attr_ext_name('HardwareProduct', parm)
        parm_label = QLabel(parm_name, self)
        parm_val = getattr(rqt, parm, 0.0)
        self.parm_field = FloatFieldWidget(parent=self, value=parm_val)
        units_label = QLabel(rqt.rqt_units, self)
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
        setattr(self.rqt, self.parm, float(self.parm_field.get_value()))
        # re-generate requirement 'description'
        self.rqt.description = ' '.join([str(self.rqt.rqt_subject),
                                         str(self.rqt.rqt_predicate),
                                         str(self.parm_field.get_value()),
                                         str(self.rqt.rqt_units)])
        NOW = dtstamp()
        user = orb.get(state.get('local_user_oid'))
        self.rqt.mod_datetime = NOW
        self.rqt.modifier = user
        orb.save([self.rqt])
        self.rqt_parm_mod.emit(self.rqt.oid)
        self.accept()


class AssemblyNodeDialog(QDialog):
    """
    A dialog to edit reference_designator and quantity (or system_role) on a
    system assembly tree node Acu (or ProjectSystemUsage).
    """
    def __init__(self, ref_des, quantity, system=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Reference Designator or Quantity")
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
        self.summary = False
        layout = QVBoxLayout()
        self.setLayout(layout)
        self.setWindowTitle("Mini MEL")
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
        self.summary_select = QCheckBox(self)
        self.summary_select.setChecked(False)
        self.summary_select.clicked.connect(self.on_summary_checked)
        self.summary_label = QLabel('summary')
        self.export_tsv_button = SizedButton("Export as tsv")
        self.export_tsv_button.clicked.connect(self.export_tsv)
        self.export_excel_button = SizedButton("Export as Excel")
        self.export_excel_button.clicked.connect(self.export_excel)
        top_layout = QHBoxLayout()
        top_layout.addWidget(self.dash_select)
        top_layout.addWidget(self.summary_select)
        top_layout.addWidget(self.summary_label)
        top_layout.addWidget(self.export_tsv_button)
        top_layout.addWidget(self.export_excel_button)
        top_layout.addStretch(1)
        layout.addLayout(top_layout)
        # set up mel table
        self.set_mini_mel_table()

    def on_dash_select(self, index):
        self.dash_name = prefs['dashboard_names'][index]
        dash_schemas = prefs.get('dashboards') or {}
        self.data_cols = dash_schemas.get(self.dash_name)
        self.set_mini_mel_table()

    def on_summary_checked(self):
        if self.summary_select.isChecked():
            self.summary = True
        else:
            self.summary = False
        self.set_mini_mel_table()

    def export_tsv(self):
        """
        [Handler for 'Export as tsv' button]  Write the dashboard content to a
        tab-separated-values file.  Parameter values will be expressed in the
        user's preferred units, and headers will be explicitly annotated with
        units.
        """
        orb.log.debug('* export_tsv()')
        dtstr = date2str(dtstamp())
        dash_name = "Customized"
        if self.dash_name:
            dash_name = self.dash_name
        name = '-' + dash_name + '-'
        if self.summary:
            name = '-Summary' + name
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
            data_cols = prefs['dashboards'].get(dash_name)
            orb.log.debug(f'  - data cols: "{str(data_cols)}"')
            write_mel_to_tsv(self.obj, schema=data_cols, pref_units=True,
                             summary=self.summary, file_path=fpath)
            html = '<h3>Success!</h3>'
            msg = 'Mini MEL exported to file:'
            html += f'<p><b><font color="green">{msg}</font></b><br>'
            html += f'<b><font color="blue">{fpath}</font></b></p>'
            self.w = NotificationDialog(html, news=False, parent=self)
            self.w.show()
        else:
            orb.log.debug('  ... export to tsv cancelled.')
            return

    def export_excel(self):
        """
        [Handler for 'Export as Excel' button]  Write the dashboard content to
        a .xlsx file.  Parameter values will be expressed in the user's
        preferred units, and headers will be explicitly annotated with units.
        """
        orb.log.debug('* export_excel()')
        dtstr = date2str(dtstamp())
        dash_name = "Customized"
        if self.dash_name:
            dash_name = self.dash_name
        name = '-' + dash_name + '-'
        if self.summary:
            name = '-Summary' + name
        fname = self.obj.id + name + dtstr + '.xlsx'
        state_path = state.get('mini_mel_last_path') or ''
        suggested_fpath = os.path.join(state_path, fname)
        fpath, filters = QFileDialog.getSaveFileName(
                                    self, 'Write to .xlsx File',
                                    suggested_fpath, '(*.xlsx)')
        if fpath:
            orb.log.debug(f'  - file selected: "{fpath}"')
            fpath = str(fpath)   # extra-cautious :)
            state['mini_mel_last_path'] = os.path.dirname(fpath)
            data_cols = prefs['dashboards'].get(dash_name)
            orb.log.debug(f'  - data cols: "{str(data_cols)}"')
            write_mel_to_xlsx(self.obj, schema=data_cols, pref_units=True,
                              summary=self.summary, file_path=fpath)
            html = '<h3>Success!</h3>'
            msg = 'Mini MEL exported to Excel file:'
            html += f'<p><b><font color="green">{msg}</font></b><br>'
            html += f'<b><font color="blue">{fpath}</font></b></p>'
            self.w = NotificationDialog(html, news=False, parent=self)
            self.w.show()
            # try to start Excel with file if on Win or Mac ...
            if sys.platform == 'win32':
                try:
                    os.system(f'start excel.exe "{fpath}"')
                except:
                    orb.log.debug('  unable to start Excel')
            elif sys.platform == 'darwin':
                try:
                    os.system(f'open -a "Microsoft Excel.app" "{fpath}"')
                except:
                    orb.log.debug('  unable to start Excel')
        else:
            orb.log.debug('  ... export to Excel cancelled.')
            return

    def set_mini_mel_table(self):
        layout = self.layout()
        if getattr(self, 'mini_mel_table', None):
            # remove and close current table
            layout.removeWidget(self.mini_mel_table)
            self.mini_mel_table.parent = None
            self.mini_mel_table.close()
        raw_data = get_mel_data(self.obj, schema=self.data_cols,
                                summary=self.summary)
        # transform keys to formatted headers with units
        self.mel_data = [{self.get_header(col_id) : row[col_id]
                          for col_id in row}
                          for row in raw_data]
        # right-align parm data; left align everything else
        cols = list(raw_data[0])
        aligns = ['right' if col in parm_defz else 'left'
                  for col in cols]
        mini_mel_model = MappingTableModel(self.mel_data, aligns=aligns)
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
        self.setWindowTitle("Select Object")
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
        self.table_view.setColumnWidth(2, 300)
        self.table_view.clicked.connect(self.select_object)
        self.bbox = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.bbox.rejected.connect(self.reject)
        layout = QVBoxLayout()
        layout.addWidget(self.table_view)
        layout.addWidget(self.bbox)
        self.setLayout(layout)
        w = self.table_view.horizontalHeader().length() + 30
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

    units_set = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferred Units")
        form = QFormLayout(self)
        dim_labels = {}
        self.dim_widgets = {}
        if not prefs.get('units'):
            prefs['units'] = {}
        settables = [dims for dims in parmz_by_dimz if alt_units.get(dims)]
        settables.sort()
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
        # dispatcher.send('units set')
        self.units_set.emit()


class TimeUnitsDialog(QDialog):
    """
    Dialog for setting preferred units for time for a specified Activity
    object. The preferred units will be set as the data element "time_units".
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        orb.log.debug('* selecting preferred time units ...')
        # default time unit (mks) is seconds ...
        self.time_unit_name = 'seconds'
        self.time_unit_id = 's'
        self.setWindowTitle("Preferred Time Units")
        self.main_layout = QVBoxLayout(self)
        instructions = 'Accepted Time Units -- select one:'
        self.instructions_label = QLabel(instructions)
        self.instructions_label.setAttribute(Qt.WA_DeleteOnClose)
        self.main_layout.addWidget(self.instructions_label)
        self.dim_buttons = {}
        self.possible_units_layout = QVBoxLayout()
        self.possible_units_buttons = QButtonGroup()
        for unit in time_unit_names:
            button = QRadioButton(unit)
            button.clicked.connect(self.set_units)
            self.possible_units_buttons.addButton(button)
            self.possible_units_layout.addWidget(button)
            self.dim_buttons[unit] = button
            button.clicked.connect(self.set_units)
        self.main_layout.addLayout(self.possible_units_layout)

        # Ok button
        self.bbox = QDialogButtonBox(Qt.Horizontal, self)
        ok_btn = self.bbox.addButton(QDialogButtonBox.Ok)
        ok_btn.clicked.connect(self.accept)
        self.main_layout.addWidget(self.bbox)

    def set_units(self, index):
        b = self.possible_units_buttons.checkedButton()
        self.time_unit_name = b.text()
        orb.log.debug(f'  - selected units: {self.time_unit_name}')
        self.time_unit_id = time_unit_names.get(self.time_unit_name)
        orb.log.debug(f'  - selected unit symbol: "{self.time_unit_id}"')

class PrefsDialog(QDialog):

    units_set = pyqtSignal()

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
        dri_label = QLabel('Disconnect Resync Interval [seconds]', self)
        self.dri_select = QComboBox()
        self.dri_select.activated.connect(self.set_disconnect_resync_interval)
        deltas = ('10', '30', '60', '120', '300')
        for delta in deltas:
            self.dri_select.addItem(delta, QVariant())
        dri_pref = prefs.get('disconnect_resync_interval')
        if str(dri_pref) in deltas:
            self.dri_select.setCurrentIndex(deltas.index(str(dri_pref)))
        else:
            self.dri_select.setCurrentIndex(deltas.index('60'))
        form.addRow(dri_label, self.dri_select)
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
        Set the global numeric precision.
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
        dlg.units_set.connect(self.on_units_set)
        dlg.show()

    def on_units_set(self):
        self.units_set.emit()

    def set_disconnect_resync_interval(self, index):
        """
        Set the preferred allowable disconnection interval before an automatic
        project resync is done.
        """
        orb.log.info('* [orb] setting numeric precision preference ...')
        try:
            dri = int(('10', '30', '60', '120', '300')[index])
            prefs['disconnect_resync_interval'] = dri
            orb.log.info(f'        set to "{dri}"')
        except:
            orb.log.debug(f'        invalid index ({index})')


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
        self.setMinimumWidth(400)
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
                dims = col_def.get('dimensions', '')
                tt = f'<p><b>Definition:</b> {dtxt}</p>'
                if dims:
                    tt += f'<b>Dimensions:</b> {dims}'
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


class SelectHWColsDialog(QDialog):
    """
    Dialog for selecting columns to be displayed in the FilterPanel when
    populated by Hardware Products.

    Args:
        parameters (list of str): list of parameter ids to select from
        data_elements (list of str): list of data_element ids to select from
        view (list of str): the current view to be customized
    """
    def __init__(self, parameters, data_elements, view, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Columns")
        vbox = QVBoxLayout(self)
        properties_label = QLabel(
            '<h3><font color="purple">Properties</font></h3>')
        vbox.addWidget(properties_label)
        schema = orb.schemas['HardwareProduct']
        fields = [name for name in schema['field_names']
                  if (name not in M2M and name not in ONE2M)]
        fields.sort(key=lambda x: x.lower())
        flen = len(fields)
        f = flen // 5
        if flen % 5:
            field_forms = {i : QFormLayout() for i in range(f + 1)}
        else:
            field_forms = {i : QFormLayout() for i in range(f)}
        fields_hbox = QHBoxLayout()
        for form in field_forms.values():
            fields_hbox.addLayout(form)
        self.checkboxes = {}
        for i, col in enumerate(fields):
            label = QLabel(get_attr_ext_name('HardwareProduct', col), self)
            col_def = schema['fields'][col]['definition']
            tt = f'<p><b>Definition:</b> {col_def}</p>'
            label.setToolTip(tt)
            self.checkboxes[col] = QCheckBox(self)
            if col in view:
                self.checkboxes[col].setChecked(True)
            else:
                self.checkboxes[col].setChecked(False)
            idx = i // 5
            field_forms[idx].addRow(self.checkboxes[col], label)
        vbox.addLayout(fields_hbox)

        # Parameters
        parm_sep = HLine()
        vbox.addWidget(parm_sep)
        parameters_label = QLabel(
            '<h3><font color="purple">Parameters</font></h3>')
        vbox.addWidget(parameters_label)
        plen = len(parameters)
        m = plen // 10
        if plen % 10:
            parm_forms = {i : QFormLayout() for i in range(m + 1)}
        else:
            parm_forms = {i : QFormLayout() for i in range(m)}
        parm_hbox = QHBoxLayout()
        for form in parm_forms.values():
            parm_hbox.addLayout(form)
        parameters.sort(key=lambda x: (parm_defz.get(x, {}).get('name')
                                       or x).lower())
        for i, col in enumerate(parameters):
            col_def = parm_defz.get(col)
            if col_def:
                label = QLabel(col_def['name'], self)
                dtxt = col_def.get('description', '')
                dims = col_def.get('dimensions', '')
                tt = f'<p><b>Definition:</b> {dtxt}</p>'
                if dims:
                    tt += f'<b>Dimensions:</b> {dims}'
                label.setToolTip(tt)
            else:
                label = QLabel(col, self)
            self.checkboxes[col] = QCheckBox(self)
            if col in view:
                self.checkboxes[col].setChecked(True)
            else:
                self.checkboxes[col].setChecked(False)
            idx = i // 10
            parm_forms[idx].addRow(self.checkboxes[col], label)
        vbox.addLayout(parm_hbox)

        # Data Elements
        de_sep = HLine()
        vbox.addWidget(de_sep)
        de_label = QLabel(
            '<h3><font color="purple">Data Elements</font></h3>')
        vbox.addWidget(de_label)
        dlen = len(data_elements)
        d = dlen // 5
        if dlen % 5:
            de_forms = {i : QFormLayout() for i in range(d + 1)}
        else:
            de_forms = {i : QFormLayout() for i in range(d)}
        de_hbox = QHBoxLayout()
        for form in de_forms.values():
            de_hbox.addLayout(form)
        data_elements.sort(key=lambda x: (de_defz.get(x, {}).get('name')
                                       or de_defz.get(x, {}).get('name')
                                       or x).lower())
        for i, col in enumerate(data_elements):
            col_def = de_defz.get(col)
            if col_def:
                label = QLabel(col_def['name'], self)
                dtxt = col_def.get('description', '')
                dims = col_def.get('dimensions', '')
                tt = f'<p><b>Definition:</b> {dtxt}</p>'
                if dims:
                    tt += f'<b>Dimensions:</b> {dims}'
                label.setToolTip(tt)
            else:
                label = QLabel(col, self)
            self.checkboxes[col] = QCheckBox(self)
            if col in view:
                self.checkboxes[col].setChecked(True)
            else:
                self.checkboxes[col].setChecked(False)
            idx = i // 5
            de_forms[idx].addRow(self.checkboxes[col], label)
        vbox.addLayout(de_hbox)

        button_sep = HLine()
        vbox.addWidget(button_sep)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        vbox.addWidget(self.buttons)


class CustomizeColsDialog(QDialog):
    """
    Dialog for selecting columns for the dashboard.

    Keyword Args:
        cols (list of str): names of current columns
        selectables (list of str): names of all possible columns
    """
    def __init__(self, cols=None, title=None, selectables=None, parent=None):
        super().__init__(parent)
        title = title or "Select Columns"
        self.setWindowTitle(title)
        self.setStyleSheet('QToolTip { font-weight: normal; font-size: 12px; '
                           'color: black; background: white;};')
        cols = cols or []
        self.checkboxes = {}
        selectables = selectables or []
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
        for i, col_id in enumerate(selectables):
            ext_name = get_attr_ext_name('HardwareProduct', col_id)
            label = QLabel(ext_name, self)
            col_def = de_defz.get(col_id) or parm_defz.get(col_id)
            if col_def:
                dtxt = col_def.get('description', '')
                dtype = col_def.get('range_datatype', '')
                dims = col_def.get('dimensions', '')
                tt = f'type: {dtype}<br>'
                if dims:
                    tt += f'dimensions: {dims}<br>'
                tt += f'definition: {dtxt}'
                label.setToolTip(tt)
            self.checkboxes[col_id] = QCheckBox(self)
            if col_id in cols:
                self.checkboxes[col_id].setChecked(True)
            else:
                self.checkboxes[col_id].setChecked(False)
            subforms[i // 40].addRow(self.checkboxes[col_id], label)
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


class DeleteModesDialog(QDialog):
    """
    Dialog for deleting modes from the Modes Definition Table.
    """
    def __init__(self, modes, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Delete Modes")
        form = QFormLayout(self)
        self.checkboxes = {}
        for i, mode in enumerate(modes):
            label = QLabel(modes[i], self)
            self.checkboxes[mode] = QCheckBox(self)
            self.checkboxes[mode].setChecked(False)
            form.addRow(self.checkboxes[mode], label)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        form.addRow(self.buttons)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)


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
        self.setWindowTitle("Clone a Product")
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
        acus = [orb.get(c.usage_oid) for c in componentz.get(self.obj.oid, [])]
        for acu in acus:
            comp = acu.component
            if comp is None:
                # ignore "None" components
                continue
            if comp.oid == 'pgefobjects:TBD':
                refdes = acu.reference_designator or ''
                name_str = '[' + refdes + '] ' + '(unpopulated)'
                id_str = '(TBD)'
            else:
                ptype = getattr(comp.product_type, 'abbreviation', None)
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
        self.white_box_panel = QWidget()
        self.white_box_panel.setLayout(white_box_form)
        self.white_box_scroll_area = QScrollArea()
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
        self.black_box_panel = QWidget()
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


class LogDialog(QDialog):
    """
    Dialog for displaying log messages while syncing.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.MinimumExpanding,
                           QSizePolicy.MinimumExpanding)
        orb.log.debug('* LogDialog started ...')
        self.setWindowTitle("Syncing with Repository")
        main_layout = QVBoxLayout(self)
        self.title = QLabel('<h3>Receiving objects ...</h3>', self)
        main_layout.addWidget(self.title)
        self.log_widget = LogWidget(parent=self)
        main_layout.addWidget(self.log_widget, 1)
        self.resize(900, 900)
        self.updateGeometry()

    def set_title(self, txt):
        self.title.setText(f'<h3>Receiving {txt} ...</h3>')

    def write(self, txt):
        self.log_widget.append(txt)


freezing_instructions = """
<h3>Instructions</h3>
<p>You have requested to freeze a <b>White Box</b> item, meaning it has a<br>
known set of components.  The components shown below are not currently<br>
frozen; freezing this item will freeze ALL of those components.
</p>
"""

class FreezingDialog(QDialog):
    """
    Dialog for freezing a product that has components which are not yet frozen.

    Args:
        obj (Product): the item to be frozen
        not_frozens (list of Product): unfrozen components of the item

    Keyword Args:
        parent (QWidget): parent of this dialog
    """
    def __init__(self, obj, not_frozens, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.MinimumExpanding,
                           QSizePolicy.MinimumExpanding)
        orb.log.debug(f'* FreezingDialog({obj.id})')
        self.setWindowTitle("Freeze")
        main_layout = QVBoxLayout(self)
        instructions_label = QLabel(freezing_instructions)
        instructions_label.setAttribute(Qt.WA_DeleteOnClose)
        main_layout.addWidget(instructions_label)
        main_object_title = QLabel('<h3>Item to be frozen:</h3>', self)
        main_layout.addWidget(main_object_title)
        obj_name_str = obj.id + ' (' + obj.name + ')'
        main_object_label = QLabel(obj_name_str, self)
        main_layout.addWidget(main_object_label)
        components_title = QLabel('<h3>Components to be frozen:</h3>', self)
        main_layout.addWidget(components_title)
        components_layout = QVBoxLayout()
        name_strs = []
        for comp in not_frozens:
            if comp is None:
                # ignore "None" components
                continue
            elif comp.oid == 'pgefobjects:TBD':
                # ignore "TBD" components
                continue
            else:
                name_str = comp.id + ' (' + comp.name + ')'
                name_strs.append(name_str)
        name_strs.sort()
        for name_str in name_strs:
            label = QLabel(name_str, self)
            components_layout.addWidget(label)
        components_panel = QWidget()
        components_panel.setLayout(components_layout)
        components_scroll_area = QScrollArea()
        components_scroll_area.setWidget(components_panel)
        main_layout.addWidget(components_scroll_area, 1)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        main_layout.addWidget(self.buttons)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.resize(550, 700)
        self.updateGeometry()


class FrozenDialog(QDialog):
    """
    Dialog for displaying products that have been frozen.

    Args:
        frozen_html (str): html list of frozen items

    Keyword Args:
        parent (QWidget): parent of this dialog
    """
    def __init__(self, frozen_html, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.MinimumExpanding,
                           QSizePolicy.MinimumExpanding)
        self.setWindowTitle("Frozen Products")
        main_layout = QVBoxLayout(self)
        main_title = QLabel('<h3>Frozen Items:</h3>', self)
        main_layout.addWidget(main_title)
        components_layout = QVBoxLayout()
        label = QLabel(frozen_html, self)
        components_layout.addWidget(label)
        components_panel = QWidget()
        components_panel.setLayout(components_layout)
        components_scroll_area = QScrollArea()
        components_scroll_area.setWidget(components_panel)
        main_layout.addWidget(components_scroll_area, 1)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok,
            Qt.Horizontal, self)
        main_layout.addWidget(self.buttons)
        self.buttons.accepted.connect(self.accept)
        self.resize(550, 700)
        self.updateGeometry()


class CannotFreezeDialog(QDialog):
    """
    Dialog to inform the user that an item cannot be frozen by them.

    Args:
        obj (Product): the item to be frozen
        cannot_freezes (list of Product): components the user cannot freeze

    Keyword Args:
        parent (QWidget): parent of this dialog
    """
    def __init__(self, obj, cannot_freezes, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.MinimumExpanding,
                           QSizePolicy.MinimumExpanding)
        orb.log.debug(f'* CannotFreezeDialog({obj.id})')
        self.setWindowTitle("Cannot Freeze")
        main_layout = QVBoxLayout(self)
        instructions_label = QLabel(freezing_instructions)
        instructions_label.setAttribute(Qt.WA_DeleteOnClose)
        main_layout.addWidget(instructions_label)
        main_object_title = QLabel('<h3>Item cannot be frozen:</h3>', self)
        main_layout.addWidget(main_object_title)
        obj_name_str = obj.id + ' (' + obj.name + ')'
        main_object_label = QLabel(obj_name_str, self)
        main_layout.addWidget(main_object_label)
        txt = '<h3>Components that cannnot be frozen:</h3>'
        components_title = QLabel(txt, self)
        main_layout.addWidget(components_title)
        components_layout = QVBoxLayout()
        name_strs = []
        for comp in cannot_freezes:
            if comp is None:
                # ignore "None" components
                continue
            elif comp.oid == 'pgefobjects:TBD':
                # ignore "TBD" components
                continue
            else:
                name_str = comp.id + ' (' + comp.name + ')'
                name_strs.append(name_str)
        name_strs.sort()
        for name_str in name_strs:
            label = QLabel(name_str, self)
            components_layout.addWidget(label)
        components_panel = QWidget()
        components_panel.setLayout(components_layout)
        components_scroll_area = QScrollArea()
        components_scroll_area.setWidget(components_panel)
        main_layout.addWidget(components_scroll_area, 1)
        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok,
            Qt.Horizontal, self)
        main_layout.addWidget(self.buttons)
        self.buttons.accepted.connect(self.accept)
        self.resize(550, 700)
        self.updateGeometry()


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
            start_name = getattr(flow.start_port_context,
                                 'reference_designator',
                                 flow.start_port.of_product.id)
            start_txt = ' '.join([start_name, flow.start_port.name, 'to'])
            end_name = getattr(flow.end_port_context,
                               'reference_designator',
                               flow.end_port.of_product.id)
            end_txt = ' '.join([end_name, flow.end_port.name])
            label_text = '\n'.join([start_txt, end_txt])
            label = QLabel(label_text, self)
            self.checkboxes[flow.oid] = QCheckBox(self)
            self.checkboxes[flow.oid].setChecked(False)
            self.checkboxes[flow.oid].stateChanged.connect(self.show_conns)
            self.flows[flow.oid] = flow
            spc_oid = getattr(flow.start_port_context, 'oid', None)
            epc_oid = getattr(flow.end_port_context, 'oid', None)
            start_port_block = scene.usage_port_blocks.get(
                                            (spc_oid, flow.start_port.oid))
            end_port_block = scene.usage_port_blocks.get(
                                            (epc_oid, flow.end_port.oid))
            start_conns = set(start_port_block.connectors)
            end_conns = set(end_port_block.connectors)
            self.conns[flow.oid] = start_conns & end_conns
            form.addRow(self.checkboxes[flow.oid], label)
        # Delete and Cancel buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        all_flows = list(self.flows.values())
        perms = []
        if all_flows:
            # all of these flows will have the same perms so pick first one
            user = orb.get(state.get('local_user_oid'))
            perms = get_perms(all_flows[0], user=user)
        if 'modify' in perms:
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
        self.setWindowTitle("ID attribute validation")
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

