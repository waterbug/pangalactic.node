"""
Admin interface
"""
import sys
from collections import OrderedDict

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QAction, QApplication, QCheckBox, QDialog,
                             QDialogButtonBox, QFileDialog, QFormLayout,
                             QHBoxLayout, QLabel, QMenu, QMessageBox,
                             QSizePolicy, QTableView, QVBoxLayout, QWidget)

from louie import dispatcher

from binaryornot.check import is_binary

from pangalactic.core                 import config, state
from pangalactic.core.uberorb         import orb
from pangalactic.core.names           import get_ra_id, get_ra_name
from pangalactic.node.buttons         import ButtonLabel, SizedButton
from pangalactic.node.dialogs         import ObjectSelectionDialog
from pangalactic.node.libraries       import LibraryListWidget
from pangalactic.node.tablemodels     import MappingTableModel
from pangalactic.node.utils           import clone, extract_mime_data
from pangalactic.node.widgets         import (ColorLabel, NameLabel,
                                              StringFieldWidget, ValueLabel)


def get_styled_text(text):
    return '<b><font color="purple">{}</font></b>'.format(text)


class RADropLabel(ColorLabel):
    """
    A Label that represents a Person or Role object that is linked to its
    referenced RoleAssignment.  This label accepts a drag/drop event: a dropped
    Person or Role replaces the Person or Role object currently referenced by
    the label and modifies the RoleAssignment accordingly.  It also has a
    context menu with a 'delete' choice that deletes its referenced
    RoleAssignment.  
    """
    def __init__(self, name, ra, color=None, element=None, border=None,
                 margin=None, mime=None, parent=None, **kw):
        """
        Initialize.

        Args:
            name (str):  label text
            ra (RoleAssignment):  the RoleAssignment object

        Keyword Args:
            color (str):  color to use for text
            element (str):  html element to use for label
            border (int):  thickness of border (default: no border)
            margin (int):  width of margin surrounding contents
            mime (str):  mime type of dropped objects to be accepted
            parent (QWidget):  parent widget
        """
        super().__init__(name, color=color, element=element,
                                          border=border, margin=margin,
                                          parent=None)
        self.setStyleSheet('background-color: white')
        # Global Admin ra label does not accept drops
        if ra.role_assignment_context is not None:
            self.setAcceptDrops(True)
        self.ra = ra
        self.mime = mime
        self.setup_context_menu()
        dispatcher.connect(self.adjust_parent_size, 'ra label resized')

    def setup_context_menu(self):
        delete_role_action = QAction('Delete', self)
        delete_role_action.triggered.connect(self.delete_role)
        self.addAction(delete_role_action)
        # self.setContextMenuPolicy(Qt.ActionsContextMenu)
        self.menu = QMenu(self)
        self.menu.setStyleSheet(
            'QMenu::item {color: purple; background: white;} '
            'QMenu::item:selected {color: white; background: purple;}')
        self.menu.addAction(delete_role_action)

    def delete_role(self, event):
        """
        Delete a RoleAssignment.
        """
        ra_oid = self.ra.oid
        orb.delete([self.ra])
        dispatcher.send(signal='deleted object', oid=ra_oid,
                        cname='RoleAssignment')

    def adjust_parent_size(self):
        self.parent().adjustSize()
        dispatcher.send(signal='admin contents resized')

    def mimeTypes(self):
        """
        Return MIME Types accepted for drops.
        """
        return [self.mime]

    def supportedDropActions(self):
        return Qt.CopyAction

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(self.mime):
            self.setStyleSheet('background-color: yellow')
            event.accept()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet('background-color: white')
        event.accept()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(self.mime):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def contextMenuEvent(self, event):
        if self.menu:
            self.menu.exec_(self.mapToGlobal(event.pos()))

    def dropEvent(self, event):
        """
        Handle drop events (change 'assigned_role' if a Role is dropped or
        'assigned_to' if a Person is dropped).  Note that rather than modifying
        the existing RoleAssignment object this will delete that one and create
        a new one, because modifying the existing object would not trigger the
        appropriate notifications (i.e., for the old role being removed and the
        new one assigned).
        """
        if event.mimeData().hasFormat(self.mime):
            # get the Role object from the existing RoleAssignment
            role = self.ra.assigned_role
            org = self.ra.role_assignment_context
            if self.mime == 'application/x-pgef-person':
                data = extract_mime_data(event, self.mime)
                icon, p_oid, p_id, p_name, p_cname = data
                person = orb.get(p_oid)
                name = ' '.join([person.first_name or '',
                                 person.last_name or '[no last name]'])
                orb.log.info('[RADropLabel] Person dropped, {}: "{}"'.format(
                                                            person.oid, name))
                # create a new RoleAssignment
                ra_id = get_ra_id(org.id, role.id,
                                  person.first_name or '',
                                  person.mi_or_name or '',
                                  person.last_name or '')
                ra_name = get_ra_name(org.id, role.id,
                                  person.first_name or '',
                                  person.mi_or_name or '',
                                  person.last_name or '')
                local_user = orb.get(state.get('local_user_oid'))
                ra = clone('RoleAssignment', id=ra_id, name=ra_name,
                           assigned_to=person,
                           assigned_role=role,
                           role_assignment_context=org,
                           creator=local_user, modifier=local_user)
                # NOTE:  clone() adds a dtstamp()
                orb.save([ra])
                # pangalaxian will handle the 'new object' signal and call the
                # 'vger.assign_role' rpc ... also note that it's best to send
                # the "new object" notification before the "deleted object"
                # notification because that way the user will have at least one
                # role assigned on the project during the process.
                dispatcher.send(signal='new object', obj=ra)
                # now delete the existing RoleAssignment ...
                deleted_oid = self.ra.oid
                orb.delete([self.ra])
                # ... and set the new ra as the widget's ra
                self.ra = ra
                self.setText(get_styled_text(name))
                self.adjustSize()
                dispatcher.send(signal='ra label resized')
                dispatcher.send(signal='deleted object', oid=deleted_oid,
                                cname='RoleAssignment')
            elif self.mime == 'application/x-pgef-role':
                data = extract_mime_data(event, 'application/x-pgef-role')
                icon, r_oid, r_id, r_name, r_cname = data
                role = orb.get(r_oid)
                orb.log.info('[RADropLabel] Role dropped: "{}"'.format(
                                                               role.name))
                # get the Person object from the existing RoleAssignment
                person = self.ra.assigned_to
                # then create a new RoleAssignment
                ra_id = get_ra_id(org.id, role.id,
                                  person.first_name or '',
                                  person.mi_or_name or '',
                                  person.last_name or '')
                ra_name = get_ra_name(org.id, role.id,
                                  person.first_name or '',
                                  person.mi_or_name or '',
                                  person.last_name or '')
                local_user = orb.get(state.get('local_user_oid'))
                ra = clone('RoleAssignment', id=ra_id, name=ra_name,
                           assigned_to=person,
                           assigned_role=role,
                           role_assignment_context=org,
                           creator=local_user, modifier=local_user)
                # NOTE:  clone() adds a dtstamp()
                orb.save([ra])
                # pangalaxian will handle the 'new object' signal and call the
                # 'vger.assign_role' rpc ... also note that it's best to send
                # the "new object" notification before the "deleted object"
                # notification because that way the user will have at least one
                # role assigned on the project during the process.
                dispatcher.send(signal='new object', obj=ra)
                # now delete the existing RoleAssignment ...
                deleted_oid = self.ra.oid
                orb.delete([self.ra])
                # ... and set the new ra as the widget's ra
                self.ra = ra
                self.setText(get_styled_text(role.name))
                self.adjustSize()
                dispatcher.send(signal='ra label resized')
                dispatcher.send(signal='deleted object', oid=deleted_oid,
                                cname='RoleAssignment')
            else:
                event.ignore()
        else:
            event.ignore()


class PersonSearchDialog(QDialog):
    """
    Dialog for LDAP searches.
    """
    def __init__(self, parent=None):
        """
        Initialize.

        Keyword Args:
            parent (QWidget):  parent widget
        """
        orb.log.info('* PersonSearchDialog()')
        super().__init__(parent)
        self.test_mode = False
        self.setWindowTitle("LDAP Search")
        outer_vbox = QVBoxLayout()
        self.setLayout(outer_vbox)
        self.setSizePolicy(QSizePolicy.Expanding,
                           QSizePolicy.Expanding)
        self.criteria_panel = QWidget()
        form_layout = QFormLayout()
        self.criteria_panel.setLayout(form_layout)
        form_label = ColorLabel('Search Criteria', element='h2', margin=10)
        form_layout.setWidget(0, QFormLayout.SpanningRole, form_label)
        self.schema = config.get('ldap_schema')
        if not self.schema:
            # if no schema is configured, use a default LDAP schema
            self.schema = {'UUPIC': 'oid',
                           'AUID': 'id',
                           'First Name': 'first_name',
                           'Last Name': 'last_name',
                           'MI or Name': 'mi_or_name',
                           'Email': 'email',
                           'Employer': 'employer_name',
                           'Code': 'org_code'}
            config['ldap_schema'] = self.schema.copy()
        self.form_widgets = {}
        for name in self.schema:
            self.form_widgets[name] = StringFieldWidget()
            form_layout.addRow(NameLabel(name), self.form_widgets[name])
        self.criteria_panel.setLayout(form_layout)
        outer_vbox.addWidget(self.criteria_panel)
        self.search_button = SizedButton('Search')
        outer_vbox.addWidget(self.search_button)
        self.test_mode_checkbox = QCheckBox('Test Mode')
        self.test_mode_checkbox.clicked.connect(self.on_check_cb)
        outer_vbox.addWidget(self.test_mode_checkbox)
        # dispatcher.connect(self.on_search_result, 'ldap result')

    def on_check_cb(self):
        if self.test_mode_checkbox.isChecked():
            orb.log.info('* LDAP search test mode activated')
            self.test_mode = True
        else:
            orb.log.info('* LDAP search test mode deactivated')
            self.test_mode = False

    def on_search_result(self, res=None):
        """
        Display result of LDAP search and enable selection of person for
        addition to repository for role assignments.

        Keyword Args:
            res (tuple): a tuple containing [0] the ldap search string and [1]
                the result of the search or a test result.
        """
        orb.log.info('* PersonSearchDialog: on_search_result()')
        orb.log.info('  result: {}'.format(res))
        if len(res) == 2:
            search_string, records = res
        else:
            orb.log.info('  nothing found.')
            message = "No result."
            popup = QMessageBox(QMessageBox.Warning, 'No result',
                                message, QMessageBox.Ok, self)
            popup.show()
        self.ldap_schema = config['ldap_schema']
        res_cols = list(self.ldap_schema.values())
        res_headers = {self.ldap_schema[a]:a for a in self.ldap_schema}
        layout = self.layout()
        search_string_label = NameLabel('LDAP Search String:')
        search_string_field = ValueLabel(search_string, w=300)
        ss_hbox = QHBoxLayout()
        ss_hbox.addWidget(search_string_label)
        ss_hbox.addWidget(search_string_field, alignment=Qt.AlignLeft,
                          stretch=1)
        layout.addLayout(ss_hbox)
        self.ldap_data = []
        for res_item in records:
            ldap_rec = OrderedDict()
            for col in res_cols:
                ldap_rec[res_headers[col]] = res_item.get(col, '[none]')
            self.ldap_data.append(ldap_rec)
        ldap_model = MappingTableModel(self.ldap_data)
        self.ldap_table = QTableView()
        # self.ldap_table.setSizeAdjustPolicy(QTableView.AdjustToContents)
        self.ldap_table.setModel(ldap_model)
        self.ldap_table.setAlternatingRowColors(True)
        self.ldap_table.setShowGrid(False)
        self.ldap_table.setSelectionBehavior(1)
        self.ldap_table.setStyleSheet('font-size: 12px')
        self.ldap_table.verticalHeader().hide()
        self.ldap_table.clicked.connect(self.person_selected)
        col_header = self.ldap_table.horizontalHeader()
        col_header.setSectionResizeMode(col_header.Stretch)
        col_header.setStyleSheet('font-weight: bold')
        # self.ldap_table.setSizePolicy(QSizePolicy.Expanding,
                                     # QSizePolicy.Expanding)
        self.ldap_table.resizeColumnsToContents()
        layout.addWidget(self.ldap_table)
        self.add_person_panel = QWidget()
        hbox = QHBoxLayout()
        self.add_person_panel.setLayout(hbox)
        self.add_person_button = SizedButton('Add Person')
        self.add_person_button.clicked.connect(self.on_add_person)
        hbox.addWidget(self.add_person_button)
        self.person_label = ColorLabel('tbd')
        hbox.addWidget(self.person_label)
        layout.addWidget(self.add_person_panel)
        self.add_person_panel.setVisible(False)
        self.resize(700, 600)
        # self.adjustSize()

    def person_selected(self, clicked_index):
        orb.log.debug('* person_selected()')
        clicked_row = clicked_index.row()
        orb.log.debug('  clicked row is "{}"'.format(clicked_row))
        person_data = self.ldap_data[clicked_row]
        orb.log.debug(f'  person selected is: {person_data}')
        # TODO: make "ldap_person_format" a config item ...
        person_display_name = '{}, {} {} ({})'.format(
                                             person_data['Last Name'],
                                             person_data['First Name'],
                                             person_data['MI or Name'],
                                             person_data['Code']
                                             )
        orb.log.debug('  {}'.format(person_display_name))
        orb.log.debug('  ... ldap record: {}'.format(person_data))
        if person_data:
            self.person_data = person_data
            self.person_label.set_content(person_display_name)
            self.add_person_panel.setVisible(True)

    def create_person(self):
        """
        Handler for the create_person_button click: clones a new Person object
        using the object editor and dispatches the "add person" signal, which
        will trigger pangalaxian to send the 'vger.add_person' rpc.
        """
        pass

    def on_add_person(self):
        """
        Handler for the add_person_button click: dispatches the "add person"
        signal, which will trigger pangalaxian to send the 'vger.add_person'
        rpc.
        """
        orb.log.debug('* on_add_person()')
        data = {self.ldap_schema[a]: self.person_data[a]
                for a in self.person_data}
        self.add_person_dlg = AddPersonDialog(data=data, parent=self)
        self.add_person_dlg.show()


class AddPersonDialog(QDialog):
    """
    Dialog for adding a person and their public key credential.
    """
    def __init__(self, data=None, parent=None):
        """
        Initialize.

        Keyword Args:
            data (dict):  data related to the person
            parent (QWidget):  parent widget
        """
        orb.log.info('* AddPersonDialog()')
        super().__init__(parent)
        self.public_key = None
        self.setWindowTitle("Create User")
        outer_vbox = QVBoxLayout()
        self.setLayout(outer_vbox)
        self.setSizePolicy(QSizePolicy.Expanding,
                           QSizePolicy.Expanding)
        self.data_panel = QWidget()
        form_layout = QFormLayout()
        self.data_panel.setLayout(form_layout)
        form_label = ColorLabel('User Data', element='h2', margin=10)
        form_layout.setWidget(0, QFormLayout.SpanningRole, form_label)
        self.schema = config.get('ldap_schema')
        self.form_widgets = {}
        for name in self.schema:
            self.form_widgets[name] = StringFieldWidget(
                                        value=data.get(self.schema[name], ''),
                                        parent=self)
            form_layout.addRow(NameLabel(name), self.form_widgets[name])
        self.data_panel.setLayout(form_layout)
        outer_vbox.addWidget(self.data_panel)
        self.get_key_button = SizedButton('Load User Public Key from File')
        self.get_key_button.clicked.connect(self.on_get_key)
        outer_vbox.addWidget(self.get_key_button)
        self.got_key_label = ButtonLabel('Public Key ready for upload')
        self.got_key_label.setVisible(False)
        outer_vbox.addWidget(self.got_key_label)
        save_button = SizedButton('Save')
        save_button.clicked.connect(self.on_save)
        outer_vbox.addWidget(save_button)
        # make sure we are deleted when closed
        self.setAttribute(Qt.WA_DeleteOnClose)
        # DEPRECATED:  now closed by pangalaxian
        # dispatcher.connect(self.on_person_added_success, 'person added')

    def on_get_key(self):
        orb.log.debug('* on_get_key()')
        d = state.get('last_path') or ''
        dlg = QFileDialog(self, 'Open Key File', directory=d)
        fpath = ''
        data = ''
        if dlg.exec_():
            fpaths = dlg.selectedFiles()
            if fpaths:
                fpath = fpaths[0]
            dlg.close()
        if fpath:
            orb.log.debug('* key file path: {}'.format(fpath))
            if is_binary(fpath):
                message = f'File at "{fpath}" was not in correct format.'
                orb.log.debug(' - ' + message)
                popup = QMessageBox(QMessageBox.Warning,
                            "Wrong file type", message,
                            QMessageBox.Ok, self)
                popup.show()
                return
            try:
                f = open(fpath)
                data = f.read()
                f.close()
                self.project_file_path = ''
            except:
                message = f'File at "{fpath}" could not be opened.'
                orb.log.debug(' - ' + message)
                popup = QMessageBox(QMessageBox.Warning,
                            "Error in file path", message,
                            QMessageBox.Ok, self)
                popup.show()
                return
        else:
            # no file was selected
            message = "No file was selected."
            orb.log.debug(' - ' + message)
            popup = QMessageBox(QMessageBox.Warning,
                        "No file", message,
                        QMessageBox.Ok, self)
            popup.show()
            return
        if data:
            self.public_key = data
            orb.log.debug(' - public key: "{}"'.format(data))
            message = "Public key has been captured."
            popup = QMessageBox(QMessageBox.Warning,
                        "Success", message,
                        QMessageBox.Ok, self)
            popup.show()
            self.get_key_button.setVisible(False)
            self.got_key_label.setVisible(True)
            return
        else:
            message = "Public key file was empty."
            orb.log.debug(' - ' + message)
            popup = QMessageBox(QMessageBox.Warning,
                        "Empty file", message,
                        QMessageBox.Ok, self)
            popup.show()
            return

    def on_save(self):
        # translate from LDAP schema to Person attrs
        data = {self.schema[name] : self.form_widgets[name].text()
                for name in self.schema}
        if self.public_key:
            data['public_key'] = self.public_key
        # send signal to call rpc "vger.add_person"
        dispatcher.send('add person', data=data)

    # DEPRECATED:  now closed by pangalaxian
    # def on_person_added_success(self):
        # self.close()


class AdminDialog(QDialog):
    """
    Dialog for admin operations: basically, role provisioning for persons
    relative to organizations.
    """
    def __init__(self, org=None, parent=None):
        """
        Initialize.

        Keyword Args:
            org (Organization):  the organization for which roles are to be
                managed
            parent (QWidget):  parent widget
        """
        orb.log.info('* AdminDialog()')
        super().__init__(parent)
        self.setAcceptDrops(True)
        # this triggers an rpc that asynchronously updates the Person table
        dispatcher.send(signal='get people')
        self.org = org
        context = getattr(self.org, 'id', '')
        if context == 'PGANA':
            context = 'Global Administrator'
        title = f"Administer {context} Roles"
        self.setWindowTitle(title)
        outer_vbox = QVBoxLayout()
        self.left_vbox = QVBoxLayout()
        self.right_vbox = QVBoxLayout()
        hbox = QHBoxLayout()
        self.setLayout(outer_vbox)
        outer_vbox.addLayout(hbox, stretch=1)
        hbox.addLayout(self.left_vbox)
        hbox.addLayout(self.right_vbox, stretch=1)
        self.org_selection = ButtonLabel(self.org.id, w=120)
        self.org_selection.clicked.connect(self.set_current_org)
        self.left_vbox.addWidget(self.org_selection)
        # build role assignments in left_vbox
        self.refresh_roles()
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok, Qt.Horizontal,
                                        self)
        self.buttons.button(QDialogButtonBox.Ok).setText('Ok')
        outer_vbox.addWidget(self.buttons)
        self.buttons.accepted.connect(self.accept)
        # if we have an ldap_schema, add an LDAP search button
        if config.get('ldap_schema'):
            self.ldap_search_button = SizedButton('Search for a Person')
            self.right_vbox.addWidget(self.ldap_search_button)
        # populate Role and Person library widgets
        cnames = ['Role', 'Person']
        self.lib_widget = LibraryListWidget(cnames=cnames,
                                            title='Roles and People',
                                            min_width=600,
                                            parent=self)
        # self.lib_widget.resize(700, 600)
        self.right_vbox.addWidget(self.lib_widget, stretch=1)
        self.updateGeometry()
        dispatcher.connect(self.adjust_size, 'admin contents resized')
        dispatcher.connect(self.refresh_roles, 'deleted object')
        dispatcher.connect(self.refresh_roles, 'remote: deleted')
        # DEPRECATED: on_person_added_success() now called directly in
        # pangalaxian
        # dispatcher.connect(self.on_person_added_success, 'person added')
        # DEPRECATED: on_got_people() now called directly in pgxn
        # dispatcher.connect(self.on_got_people, 'got people')
        dispatcher.connect(self.refresh_roles, 'refresh admin tool')

    def on_got_people(self):
        """
        Refresh the Persons widget when the "got people" signal is received as
        a result of the vger.get_people() rpc being received by pangalaxian --
        this will refresh the display of active users (green box icons) even if
        there are no new people.
        """
        orb.log.info('* on_got_people()')
        self.lib_widget.refresh(cname='Person')

    def on_person_added_success(self, userid='', pk_added=False):
        """
        Update the "active_users" state and refresh the Persons widget when the
        "person added" signal is received from pangalaxian after it has
        received the result of the vger.add_person() rpc.  This will refresh
        the display of active users (green box icons) even if no new people
        were added.
        """
        if userid:
            message = f'Person "{userid}" has been added'
            if pk_added:
                message += ' with public key'
                if state.get('active_users'):
                    state['active_users'].append(userid)
                else:
                    state['active_users'] = [userid]
            orb.log.debug(' - ' + message)
            popup = QMessageBox(QMessageBox.Information,
                        "Person Added", message,
                        QMessageBox.Ok, self)
            popup.show()
        self.lib_widget.refresh(cname='Person')

    def refresh_roles(self):
        """
        Build the users_widget, which contains the role assignments for the
        specified organization.
        """
        if hasattr(self, 'users_widget'):
            # if there is an existing users_widget, destroy it
            form_layout = self.users_widget.layout()
            for w in self.form_widgets:
                form_layout.removeWidget(w)
                w.setParent(None)
        else:
            self.users_widget = QWidget()
            form_layout = QFormLayout()
            self.users_widget.setLayout(form_layout)
            self.left_vbox.addWidget(self.users_widget)
        self.form_widgets = []
        orgid = getattr(self.org, 'id', 'No Organization')
        if orgid == 'PGANA':
            orgid = 'Global Administrators'
        org_label = ColorLabel(orgid, element='h2', margin=10)
        # org_label should span 2 columns
        form_layout.setWidget(0, QFormLayout.SpanningRole, org_label)
        self.form_widgets.append(org_label)
        if orgid == 'Global Administrators':
            # show global admins
            admin_role = orb.get('pgefobjects:Role.Administrator')
            garas = orb.search_exact(cname='RoleAssignment',
                                     assigned_role=admin_role,
                                     role_assignment_context=None)
            for gara in garas:
                r_label, p_label = self.get_labels(gara)
                form_layout.addRow(p_label)
                self.form_widgets.append(p_label)
        elif self.org:
            ra_dict = {
                (ra.assigned_role.name, ra.assigned_to.last_name or '') : ra
                for ra in orb.search_exact(cname='RoleAssignment',
                                           role_assignment_context=self.org)}
            ra_tuples = list(ra_dict.keys())
            ra_tuples.sort()
            for ra_tuple in ra_tuples:
                ra = ra_dict[ra_tuple]
                r_label, p_label = self.get_labels(ra)
                form_layout.addRow(r_label, p_label)
                self.form_widgets.append(r_label)
                self.form_widgets.append(p_label)
        else:
            none_label = QLabel('None')
            form_layout.addRow(none_label)
            self.form_widgets.append(none_label)

    def adjust_size(self):
        self.adjustSize()

    def set_current_org(self):
        orb.log.info('* admin: set_current_org()')
        orgs = [org for org in orb.get_by_type('Organization')
                if org.id != 'PGANA']
        orgs += [org for org in orb.get_by_type('Project')
                 if org.id != 'SANDBOX']
        # only show orgs for which user is admin, or all orgs if user is a
        # global admin ... vger will refuse to allow a role assignment by the
        # user if user is not an admin for the org or a global admin, anyway.
        userid = state.get('userid')
        user_obj = orb.select('Person', id=userid)
        admin_for = []
        admin_role = orb.get('pgefobjects:Role.Administrator')
        global_admin = orb.select('RoleAssignment',
                                  assigned_role=admin_role,
                                  assigned_to=user_obj,
                                  role_assignment_context=None)
        for org in orgs:
            admin_ra = orb.select('RoleAssignment',
                                  assigned_role=admin_role,
                                  assigned_to=user_obj,
                                  role_assignment_context=org)
            if admin_ra or global_admin:
                admin_for.append(org)
        if global_admin:
            # Global Admins see the "PGANA" org, enabling them to create other
            # Global Admins
            pgana = orb.get('pgefobjects:PGANA')
            if pgana:
                admin_for.append(pgana)
        if admin_for:
            admin_for.sort(key=lambda org: org.id)
            dlg = ObjectSelectionDialog(admin_for, parent=self)
            dlg.make_popup(self.org_selection)
            # dlg.exec_() -> modal dialog
            if dlg.exec_():
                # dlg.exec_() being true means dlg was "accepted" (OK)
                # refresh project selection combo
                # and set the current project to the new project
                new_oid = dlg.get_oid()
                self.org = orb.get(new_oid)
                self.org_selection.setText(self.org.id)
                self.refresh_roles()

    def get_labels(self, ra):
        # Role
        if ra.role_assignment_context is not None:
            r = ra.assigned_role
            r_label = RADropLabel(r.name, ra,
                                  mime='application/x-pgef-role',
                                  margin=2, border=1)
        else:
            r_label = None
        # Person
        p = ra.assigned_to
        p_name = ' '.join([p.first_name or '',
                           p.last_name or '[no last name]'])
        p_label = RADropLabel(p_name, ra,
                              mime='application/x-pgef-person',
                              margin=2, border=1)
        return r_label, p_label

    def mimeTypes(self):
        """
        Return MIME Types accepted for drops.
        """
        return ['application/x-pgef-person', 'application/x-pgef-role']

    def supportedDropActions(self):
        return Qt.CopyAction

    def dragEnterEvent(self, event):
        if (event.mimeData().hasFormat('application/x-pgef-person')
            or event.mimeData().hasFormat('application/x-pgef-role')):
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if (event.mimeData().hasFormat('application/x-pgef-person')
            or event.mimeData().hasFormat('application/x-pgef-role')):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        """
        Handle drop events:  add a new RoleAssignment; if a Person is dropped,
        assign the "Observer" Role; if a Role is dropped, assign it to the
        "TBD" Person.
        """
        if event.mimeData().hasFormat('application/x-pgef-person'):
            data = extract_mime_data(event, 'application/x-pgef-person')
            icon, p_oid, p_id, p_name, p_cname = data
            person = orb.get(p_oid)
            if person:
                name = ' '.join([person.first_name or '',
                                 person.last_name or '[no last name]'])
                orb.log.info('[Admin] Person dropped: {} ("{}")'.format(
                                                       person.oid, name))
                local_user = orb.get(state.get('local_user_oid'))
                if self.org.oid == 'pgefobjects:PGANA':
                    admin = orb.get('pgefobjects:Role.Administrator')
                    ra_id = get_ra_id('', 'global_admin',
                                      person.first_name or '',
                                      person.mi_or_name or '',
                                      person.last_name or '')
                    ra_name = get_ra_name('', 'Global Administrator',
                                      person.first_name or '',
                                      person.mi_or_name or '',
                                      person.last_name or '')
                    ra = clone('RoleAssignment', id=ra_id, name=ra_name,
                               assigned_to=person,
                               assigned_role=admin,
                               role_assignment_context=None,
                               creator=local_user, modifier=local_user)
                else:
                    observer = orb.get('pgefobjects:Role.Observer')
                    ra_id = get_ra_id(self.org.id, observer.id,
                                      person.first_name or '',
                                      person.mi_or_name or '',
                                      person.last_name or '')
                    ra_name = get_ra_name(self.org.id, observer.id,
                                      person.first_name or '',
                                      person.mi_or_name or '',
                                      person.last_name or '')
                    ra = clone('RoleAssignment', id=ra_id, name=ra_name,
                               assigned_to=person,
                               assigned_role=observer,
                               role_assignment_context=self.org,
                               creator=local_user, modifier=local_user)
                # NOTE:  clone() adds a dtstamp()
                orb.save([ra])
                # rebuild role assignments
                self.refresh_roles()
                # pangalaxian will handle the 'new object' signal and call the
                # 'vger.assign_role' rpc ...
                dispatcher.send(signal='new object', obj=ra)
            else:
                orb.log.info('[Admin] Unknown Person dropped: "{}"'.format(
                                                                   p_name))
            event.accept()
        elif event.mimeData().hasFormat('application/x-pgef-role'):
            data = extract_mime_data(event, 'application/x-pgef-role')
            icon, r_oid, r_id, r_name, r_cname = data
            role = orb.get(r_oid)
            if role and not self.org.oid == 'pgefobjects:PGANA':
                orb.log.info('[Admin] Role dropped: "{}"'.format(role.name))
                tbd = orb.get('pgefobjects:Person.TBD')
                # check whether we already have a TBD for that role ...
                ra_tbd = orb.search_exact(cname='RoleAssignment',
                                          assigned_role=role,
                                          assigned_to=tbd)
                if ra_tbd:
                    orb.log.info('        already have TBD -- ignoring.')
                else:
                    orb.log.info('        adding as TBD ...')
                    local_user = orb.get(state.get('local_user_oid'))
                    ra_id = get_ra_id(self.org.id, role.id, 'TBD', '', '')
                    ra_name = get_ra_name(self.org.id, role.id, 'TBD', '', '')
                    ra = clone('RoleAssignment', id=ra_id, name=ra_name,
                               assigned_to=tbd,
                               assigned_role=role,
                               role_assignment_context=self.org,
                               creator=local_user, modifier=local_user)
                    # NOTE:  clone() adds a dtstamp()
                    orb.save([ra])
                    # rebuild role assignments
                    self.refresh_roles()
                    # pangalaxian will handle the 'new object' signal and call
                    # the 'vger.assign_role' rpc (if online)
                    dispatcher.send(signal='new object', obj=ra)
            else:
                orb.log.info('[Admin] Undefined Role dropped: "{}"'.format(
                                                             r_name or ''))
            event.accept()
        else:
            # ignore anything that's not a Person or a Role
            event.ignore()


if __name__ == '__main__':
    """Script mode for testing."""
    app = QApplication(sys.argv)
    window = AdminDialog()
    window.show()
    sys.exit(app.exec_())

