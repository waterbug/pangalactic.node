"""
Admin interface
"""
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QApplication, QDialog, QDialogButtonBox,
                             QFormLayout, QHBoxLayout, QLabel, QVBoxLayout,
                             QWidget)

from louie import dispatcher

from pangalactic.core           import state
from pangalactic.core.uberorb   import orb
from pangalactic.node.libraries import LibraryListWidget
from pangalactic.node.utils     import clone, extract_mime_data
from pangalactic.node.widgets   import ColorLabel


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
        dispatcher.connect(self.adjust_parent_size, 'ra label resized')

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

    def dropEvent(self, event):
        """
        Handle drop events.
        """
        if event.mimeData().hasFormat(self.mime):
            if self.mime == 'application/x-pgef-person':
                data = extract_mime_data(event, self.mime)
                icon, p_oid, p_id, p_name, p_cname = data
                p = orb.get(p_oid)
                name = ' '.join([p.first_name or '',
                                 p.last_name or '[no last name]'])
                orb.log.info('[RADropLabel] Person dropped, {}: "{}"'.format(
                                                                p.oid, name))
                self.ra.assigned_to = p
                orb.save([self.ra])
                self.setText(get_styled_text(name))
                self.adjustSize()
                dispatcher.send(signal='ra label resized')
                # TODO:  dispatch "object modified" louie event so that it is
                # saved to the repo
            elif self.mime == 'application/x-pgef-role':
                data = extract_mime_data(event, 'application/x-pgef-role')
                icon, r_oid, r_id, r_name, r_cname = data
                role = orb.get(r_oid)
                orb.log.info('[RADropLabel] Role dropped: "{}"'.format(
                                                               role.name))
                self.ra.assigned_role = role
                orb.save([self.ra])
                self.setText(get_styled_text(role.name))
                self.adjustSize()
                dispatcher.send(signal='ra label resized')
                # TODO:  dispatch "object modified" louie event so that it is
                # saved to the repo
            else:
                event.ignore()
        else:
            event.ignore()


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
        title = "Administer {} Roles".format(getattr(org, 'id', ''))
        self.setWindowTitle(title)
        self.left_vbox = QVBoxLayout()
        self.right_vbox = QVBoxLayout()
        hbox = QHBoxLayout()
        self.setLayout(hbox)
        hbox.addLayout(self.left_vbox)
        hbox.addLayout(self.right_vbox)
        hbox.addStretch(1)
        self.users_widget = QWidget()
        self.form_layout = QFormLayout()
        orgid = getattr(org, 'id', 'No Organization')
        org_label = ColorLabel(orgid, element='h2', margin=10)
        # span 2 columns
        self.form_layout.setWidget(0, QFormLayout.SpanningRole, org_label)
        if self.org:
            ras = [ra for ra in orb.get_by_type('RoleAssignment')
                    if ra.role_assignment_context == self.org]
            for i, ra in enumerate(ras):
                r_label, p_label = self.get_labels(ra)
                self.form_layout.addRow(r_label, p_label)
        else:
            none_label = QLabel('None')
            self.form_layout.addRow(none_label)
        self.users_widget.setLayout(self.form_layout)
        self.left_vbox.addWidget(self.users_widget)
        self.left_vbox.addStretch(1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok, Qt.Horizontal,
                                        self)
        self.buttons.button(QDialogButtonBox.Ok).setText('Ok')
        self.left_vbox.addWidget(self.buttons)
        self.buttons.accepted.connect(self.accept)
        # populate left side with person and role library widgets
        cnames = ['Role', 'Person']
        lib_widget = LibraryListWidget(cnames=cnames, title='Roles and People',
                                       parent=self)
        self.right_vbox.addWidget(lib_widget)
        self.right_vbox.addStretch(1)
        self.updateGeometry()
        dispatcher.connect(self.adjust_size, 'admin contents resized')

    def adjust_size(self):
        self.adjustSize()

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
        Handle drop events.
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
                # don't need a timedate stamp -- clone() adds that
                local_user = orb.get(state.get('local_user_oid'))
                ra = clone('RoleAssignment', assigned_to=person,
                           assigned_role=observer,
                           role_assignment_context=self.org,
                           creator=local_user)
                orb.save([ra])
                r_label, p_label = self.get_labels(ra)
                self.form_layout.addRow(r_label, p_label)
            else:
                orb.log.info('[Admin] Unknown Person dropped: "{}"'.format(
                                                                   p_name))
        elif event.mimeData().hasFormat('application/x-pgef-role'):
            data = extract_mime_data(event, 'application/x-pgef-role')
            icon, r_oid, r_id, r_name, r_cname = data
            role = orb.get(r_oid)
            if role:
                orb.log.info('[Admin] Role dropped -- adding "{}"'.format(
                                                               role.name))
                tbd = orb.get('pgefobjects:Person.TBD')
                # don't need a timedate stamp -- clone() adds that
                ra = clone('RoleAssignment', assigned_to=tbd,
                           assigned_role=role,
                           role_assignment_context=self.org)
                orb.save([ra])
                r_label, p_label = self.get_labels(ra)
                self.form_layout.addRow(r_label, p_label)
            else:
                orb.log.info('[Admin] Undefined Role dropped: "{}"'.format(
                                                             r_name or ''))
        else:
            # ignore anything that's not a Person or a Role
            event.ignore()


if __name__ == '__main__':
    """Script mode for testing."""
    app = QApplication(sys.argv)
    window = AdminDialog()
    window.show()
    sys.exit(app.exec_())

