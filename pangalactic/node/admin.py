"""
Admin interface
"""
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QApplication, QDialog, QDialogButtonBox,
                             QFormLayout, QGridLayout, QHBoxLayout, QLabel,
                             QScrollArea, QVBoxLayout, QWidget)

# from louie import dispatcher

from pangalactic.core.uberorb   import orb
from pangalactic.node.libraries import LibraryListWidget
from pangalactic.node.utils     import clone, extract_mime_data
from pangalactic.node.widgets   import ColorLabel


class RADropLabel(ColorLabel):
    """
    Label that accepts a drag/drop, to be used for Person and Role objects that
    are linked by a RoleAssignment.  A dropped Person or Role should replace
    the object currently referenced by the RoleAssignment.

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
                name = ' '.join([p.first_name or '', p.last_name or ''])
                orb.log.info('[RADropLabel] Person dropped: "{}"'.format(name))
                self.ra.assigned_to = p
                orb.save([self.ra])
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
        self.scrollarea = QScrollArea()
        self.scrollarea.setWidgetResizable(True)
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
        self.scrollarea.setWidget(self.users_widget)
        self.left_vbox.addWidget(self.scrollarea)
        self.left_vbox.addStretch(1)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        self.buttons.button(QDialogButtonBox.Ok).setText('Ok')
        self.left_vbox.addWidget(self.buttons)
        self.buttons.rejected.connect(self.reject)
        self.buttons.accepted.connect(self.accept)
        # populate left side with person and role library widgets
        cnames = ['Role', 'Person']
        lib_widget = LibraryListWidget(cnames=cnames, title='Roles and People',
                                       parent=self)
        self.right_vbox.addWidget(lib_widget)
        self.right_vbox.addStretch(1)
        self.updateGeometry()

    def get_labels(self, ra):
        # Role
        r = ra.assigned_role
        r_label = RADropLabel(r.name, ra,
                              mime='application/x-pgef-role',
                              margin=2, border=1)
        # Person
        p = ra.assigned_to
        p_name = ' '.join([p.first_name, p.last_name])
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
            p = orb.get(p_oid)
            name = ' '.join([p.first_name or '', p.last_name or ''])
            orb.log.info('[Admin] Person dropped -- adding "{}"'.format(name))
            # TODO:  when a Person is dropped, create an "Observer" role
            # assignment for them
            observer = orb.get('pgefobjects:Role.Observer')
            # TODO:  add me as creator, timedate stamp (or does clone do that?)
            ra = clone('RoleAssignment', assigned_to=p, assigned_role=observer)
                       role_assignment_context=self.org)
            orb.save([ra])
            r_label, p_label = self.get_labels(ra)
            self.form_layout.addRow(r_label, p_label)
        elif event.mimeData().hasFormat('application/x-pgef-role'):
            data = extract_mime_data(event, 'application/x-pgef-role')
            icon, r_oid, r_id, r_name, r_cname = data
            role = orb.get(r_oid)
            orb.log.info('[Admin] Role dropped -- adding "{}"'.format(
                                                           role.name))
            # TODO:  when a Role is dropped, use a "TBD" person as a
            # placeholder for the role assignment -- also to be used for
            # "templates" of projects with roles to be assigned
        else:
            # ignore anything that's not a Person or a Role
            event.ignore()



if __name__ == '__main__':
    """Script mode for testing."""
    app = QApplication(sys.argv)
    window = AdminDialog()
    window.show()
    sys.exit(app.exec_())

