"""
Admin interface
"""
import sys
from collections import OrderedDict

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QAction, QApplication, QDialog, QDialogButtonBox,
                             QFormLayout, QHBoxLayout, QLabel, QMenu,
                             QMessageBox, QSizePolicy, QTableView, QVBoxLayout,
                             QWidget)

from louie import dispatcher

from pangalactic.core                 import config, state
from pangalactic.core.uberorb         import orb
from pangalactic.core.utils.meta      import get_ra_id, get_ra_name
from pangalactic.node.buttons         import ButtonLabel, SizedButton
from pangalactic.node.dialogs         import ObjectSelectionDialog
from pangalactic.node.libraries       import LibraryListWidget
from pangalactic.node.tablemodels     import ODTableModel
from pangalactic.node.utils           import clone, extract_mime_data
from pangalactic.node.widgets         import (ColorLabel, NameLabel,
                                              StringFieldWidget)


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
    def __init__(self, name, ra, color=None, element=None, border=None,
                 margin=None, mime=None, parent=None, **kw):
        super(RADropLabel, self).__init__(name, color=color, element=element,
                                          border=border, margin=margin,
                                          parent=None)
        self.setStyleSheet('background-color: white')
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
        Deleta a RoleAssignment.
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
            if self.mime == 'application/x-pgef-person':
                data = extract_mime_data(event, self.mime)
                icon, p_oid, p_id, p_name, p_cname = data
                person = orb.get(p_oid)
                name = ' '.join([person.first_name or '',
                                 person.last_name or '[no last name]'])
                orb.log.info('[RADropLabel] Person dropped, {}: "{}"'.format(
                                                            person.oid, name))
                # get the Role object from the existing RoleAssignment
                role = self.ra.assigned_role
                # then create a new RoleAssignment
                ra_id = get_ra_id(self.org.id, role.id,
                                  person.first_name or '',
                                  person.mi_or_name or '',
                                  person.last_name or '')
                ra_name = get_ra_name(self.org.id, role.id,
                                  person.first_name or '',
                                  person.mi_or_name or '',
                                  person.last_name or '')
                local_user = orb.get(state.get('local_user_oid'))
                ra = clone('RoleAssignment', id=ra_id, name=ra_name,
                           assigned_to=person,
                           assigned_role=role,
                           role_assignment_context=self.org,
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
                ra_id = get_ra_id(self.org.id, role.id,
                                  person.first_name or '',
                                  person.mi_or_name or '',
                                  person.last_name or '')
                ra_name = get_ra_name(self.org.id, role.id,
                                  person.first_name or '',
                                  person.mi_or_name or '',
                                  person.last_name or '')
                local_user = orb.get(state.get('local_user_oid'))
                ra = clone('RoleAssignment', id=ra_id, name=ra_name,
                           assigned_to=person,
                           assigned_role=role,
                           role_assignment_context=self.org,
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


class LdapSearchDialog(QDialog):
    """
    Dialog for LDAP searches.
    """
    def __init__(self, parent=None):
        """
        Initialize.

        Keyword Args:
            parent (QWidget):  parent widget
        """
        orb.log.info('* LdapSearchDialog()')
        super(LdapSearchDialog, self).__init__(parent)
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
        self.schema = config['ldap_schema']
        self.form_widgets = {}
        for name in self.schema:
            self.form_widgets[name] = StringFieldWidget()
            form_layout.addRow(NameLabel(name), self.form_widgets[name])
        self.criteria_panel.setLayout(form_layout)
        outer_vbox.addWidget(self.criteria_panel)
        search_button = SizedButton('Search')
        search_button.clicked.connect(self.do_search)
        outer_vbox.addWidget(search_button)
        self.results_panel = QWidget()
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok, Qt.Horizontal,
                                        self)
        self.buttons.button(QDialogButtonBox.Ok).setText('Ok')
        outer_vbox.addWidget(self.buttons)
        self.buttons.accepted.connect(self.accept)
        dispatcher.connect(self.on_search_result, 'ldap result')

    def do_search(self):
        orb.log.info('* LdapSearchDialog: do_search()')
        q = {}
        # for testing:
        # q = {'test': 'result'}
        for name, w in self.form_widgets.items():
            val = w.get_value()
            if val:
                q[self.schema[name]] = val
        if q.get('id') or q.get('oid') or q.get('last_name'):
            orb.log.info('  query: {}'.format(str(q)))
            dispatcher.send('ldap search', query=q)
        else:
            orb.log.info('  bad query: must have Last Name, AUID, or UUPIC')
            message = "Query must include Last Name, AUID, or UUPIC"
            popup = QMessageBox(QMessageBox.Warning, 'Invalid Query',
                                message, QMessageBox.Ok, self)
            popup.show()

    def on_search_result(self, res=None):
        """
        Display result of LDAP search and enable selection of person for
        addition to repository for role assignments.
        """
        orb.log.info('* LdapSearchDialog: on_search_result()')
        orb.log.info('  result: {}'.format(res))
        self.ldap_schema = config['ldap_schema']
        res_cols = list(self.ldap_schema.values())
        res_headers = {self.ldap_schema[a]:a for a in self.ldap_schema}
        self.ldap_data = []
        for res_item in res:
            ldap_rec = OrderedDict()
            for col in res_cols:
                ldap_rec[res_headers[col]] = res_item.get(col, '[none]')
            self.ldap_data.append(ldap_rec)
        ldap_model = ODTableModel(self.ldap_data)
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
        self.layout().addWidget(self.ldap_table)
        self.add_person_panel = QWidget()
        hbox = QHBoxLayout()
        self.add_person_panel.setLayout(hbox)
        self.add_person_button = SizedButton('Add Person')
        self.add_person_button.clicked.connect(self.on_add_person)
        hbox.addWidget(self.add_person_button)
        self.person_label = ColorLabel('tbd')
        hbox.addWidget(self.person_label)
        self.layout().addWidget(self.add_person_panel)
        self.add_person_panel.setVisible(False)
        self.resize(700, 600)
        # self.adjustSize()

    def person_selected(self, clicked_index):
        orb.log.debug('* person_selected()')
        clicked_row = clicked_index.row()
        orb.log.debug('  clicked row is "{}"'.format(clicked_row))
        person_data = self.ldap_data[clicked_row]
        orb.log.debug('  person selected is:'.format(person_data))
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

    def on_add_person(self):
        """
        Handler for the add_person_button click: dispatch the "add person"
        signal, which will trigger pangalaxian to send the 'vger.add_person'
        rpc.
        """
        orb.log.debug('* on_add_person()')
        data = {self.ldap_schema[a]: self.person_data[a]
                for a in self.person_data}
        # send signal to call rpc "vger.add_person"
        dispatcher.send('add person', data=data)


class AdminDialog(QDialog):
    """
    Dialog for admin operations: basically, role provisioning for an
    organization.
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
        super(AdminDialog, self).__init__(parent)
        self.setAcceptDrops(True)
        self.org = org
        title = "Administer {} Roles".format(getattr(self.org, 'id', ''))
        self.setWindowTitle(title)
        outer_vbox = QVBoxLayout()
        self.left_vbox = QVBoxLayout()
        self.right_vbox = QVBoxLayout()
        hbox = QHBoxLayout()
        self.setLayout(outer_vbox)
        outer_vbox.addLayout(hbox)
        hbox.addLayout(self.left_vbox)
        hbox.addLayout(self.right_vbox)
        hbox.addStretch(1)

        self.org_selection = ButtonLabel(self.org.id,
                                    # actions=[self.new_org_action],
                                    w=120)
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
            self.ldap_search_button = SizedButton('LDAP Search for a Person')
            self.ldap_search_button.clicked.connect(self.do_ldap_search)
            self.right_vbox.addWidget(self.ldap_search_button)
        # populate Role and Person library widgets
        cnames = ['Role', 'Person']
        self.lib_widget = LibraryListWidget(cnames=cnames,
                                            title='Roles and People',
                                            parent=self)
        self.right_vbox.addWidget(self.lib_widget)
        self.right_vbox.addStretch(1)
        self.updateGeometry()
        dispatcher.connect(self.adjust_size, 'admin contents resized')
        dispatcher.connect(self.refresh_roles, 'deleted object')
        dispatcher.connect(self.refresh_roles, 'remote: deleted')
        dispatcher.connect(self.refresh_libs, 'person added')

    def do_ldap_search(self):
        dlg = LdapSearchDialog(parent=self)
        dlg.show()

    def refresh_libs(self, **kw):
        """
        Refresh the library widgets when a 'person added' signal is received,
        which is sent when the result of the rpc 'vger.add_person' is received
        in pangalaxian.
        """
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
        org_label = ColorLabel(orgid, element='h2', margin=10)
        # org_label should span 2 columns
        form_layout.setWidget(0, QFormLayout.SpanningRole, org_label)
        self.form_widgets.append(org_label)
        if self.org:
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
        orgs = [org for org in orb.get_all_subtypes('Organization')
                if org.id != 'PGANA']
        orgs.sort(key=lambda org: org.id)
        if orgs:
            dlg = ObjectSelectionDialog(orgs, parent=self)
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
        r = ra.assigned_role
        r_label = RADropLabel(r.name, ra,
                              mime='application/x-pgef-role',
                              margin=2, border=1)
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
                observer = orb.get('pgefobjects:Role.Observer')
                local_user = orb.get(state.get('local_user_oid'))
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
            if role:
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

