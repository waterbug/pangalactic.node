""" 
GUI client for autobahn/crossbar.

Based on:
  * pyqt twisted socket client example, by Eli Bendersky (eliben@gmail.com)
  * autobahn/crossbar gauges example, by Elvis Stansvik
    https://github.com/estan/gauges
  * crossbar examples "advanced" (CRA) auth example
"""
from __future__ import division
from __future__ import print_function
from builtins import str
from builtins import range
from past.utils import old_div
import argparse, random, six, sys, time
from copy import deepcopy
from uuid import uuid4
from PyQt5.QtCore import QRectF, QSize, QTimer, Qt
from PyQt5.QtGui import QColor, QPainter, QPen, QPalette
from PyQt5.QtWidgets import (QApplication, QDialog, QDialogButtonBox,
                             QFormLayout, QHBoxLayout, QLabel, QMainWindow,
                             QPushButton, QSizePolicy, QTextBrowser,
                             QVBoxLayout, QWidget)
from louie import dispatcher
from twisted.internet._sslverify import OpenSSLCertificateAuthorities
from twisted.internet.ssl import CertificateOptions
from OpenSSL import crypto

from pangalactic.core                 import state
from pangalactic.core.refdata         import core
from pangalactic.core.serializers     import deserialize
from pangalactic.core.test.utils      import (create_test_project,
                                              create_test_users,
                                              gen_test_pvals, test_parms)
from pangalactic.core.utils.datetimes import dtstamp
from pangalactic.core.uberorb         import orb
from pangalactic.node.activities      import ActivityTables
from pangalactic.node.conops          import ConOpsModeler
from pangalactic.node.dialogs         import LoginDialog
from pangalactic.node.widgets         import ModeLabel
from pangalactic.node.widgets         import AutosizingListWidget
from pangalactic.node.message_bus     import PgxnMessageBus

message_bus = PgxnMessageBus()
# cert_fname = './.crossbar_for_test_vger/server_cert.pem'
cert_fname = 'server_cert.pem'
cert = crypto.load_certificate(
        crypto.FILETYPE_PEM,
        six.u(open(cert_fname, 'r').read()))
tls_options = CertificateOptions(
    trustRoot=OpenSSLCertificateAuthorities([cert]))

@message_bus.signal('onjoined')
def onjoined():
    dispatcher.send(signal='onjoined')

@message_bus.signal('onleave')
def onleave():
    dispatcher.send(signal='onleave')

# @message_bus.signal('onresult')
# def onresult():
    # dispatcher.send(signal='onresult')

product_types = [d for d in core if d.get('_cname') == 'ProductType' and
                 d.get('name') not in ['Template', 'Generic']]


class NotificationDialog(QDialog):
    def __init__(self, something, parent=None):
        super(NotificationDialog, self).__init__(parent)
        self.setWindowTitle("Hey!")
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


class CircleWidget(QWidget):
    def __init__(self, parent=None):
        super(CircleWidget, self).__init__(parent)
        self.nframe = 0
        self.setBackgroundRole(QPalette.Base)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def minimumSizeHint(self):
        return QSize(50, 50)

    def sizeHint(self):
        return QSize(80, 80)

    def __next__(self):
        self.nframe += 1
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(old_div(self.width(), 2), old_div(self.height(), 2))

        #range of diameter must start at a number greater than 0
        for diameter in range(1, 50, 9):
            delta = abs((self.nframe % 64) - old_div(diameter, 2))
            alpha = 255 - old_div((delta * delta), 4) - diameter
            if alpha > 0:
                painter.setPen(QPen(QColor(0, old_div(diameter, 2), 127, alpha), 3))
                painter.drawEllipse(QRectF(
                    old_div(-diameter, 2.0),
                    old_div(-diameter, 2.0), 
                    diameter, 
                    diameter))


class LogWidget(QTextBrowser):
    def __init__(self, parent=None):
        super(LogWidget, self).__init__(parent)
        palette = QPalette()
        palette.setColor(QPalette.Base, QColor("#ddddfd"))
        self.setPalette(palette)
        self.setStyleSheet('font-size: 18px')
        self.setSizePolicy(QSizePolicy.Expanding,
                           QSizePolicy.Expanding)


class MainWindow(QMainWindow):
    MOD_COUNT = 0

    def __init__(self, host, port, reactor=None, parent=None):
        super(MainWindow, self).__init__(parent)
        self.host = host
        self.port = port
        self.reactor = reactor
        self.create_main_frame()
        self.setGeometry(100, 100, 1000, 800)
        self.create_timer()
        dispatcher.connect(self.on_joined, 'onjoined')
        dispatcher.connect(self.on_leave, 'onleave')
        dispatcher.connect(self.on_activity, 'new activity')
        self.new_index = 0
        self.test_oid = ''
        self.cloaked = []
        self.decloaked = []
        self.last_saved_obj = None 
        self.system_level_obj = None
        self.latest_acu = None

    def on_signal(self, msg):
        print("event received on: {}".format(msg))
        subject, content = list(msg.items())[0]
        text = "Event: {} '{}'".format(str(subject), str(content))
        self.log("Event received:")
        self.log("      subject: {}".format(str(subject)))
        self.log("      content: {}".format(str(content)))
        print(text)
        print("Opening notification dialog ...")
        self.w = NotificationDialog(text, parent=self)
        # self.w.setWidth(200)
        self.w.show()
        if str(subject) in ['decloaked', 'modified']:
            self.log('* calling rpc vger.get_object() on {}'.format(content[0]))
            rpc = message_bus.session.call(u'vger.get_object', content[0])
            rpc.addCallback(self.on_get_object_result)
            rpc.addErrback(self.on_failure)

    def create_main_frame(self):
        self.circle_widget = CircleWidget()
        self.login_button = QPushButton('Log in')
        self.login_button.clicked.connect(self.login)
        # Con Ops Modeler --> opens a ConOpsModeler window
        self.conops_button = QPushButton('Con Ops Modeler')
        self.conops_button.clicked.connect(self.start_conops)
        self.conops_button.setVisible(True)
        # start up Activity Tables --> opens an ActivityTables window
        self.acttabs_button = QPushButton('Activity Tables')
        self.acttabs_button.clicked.connect(self.start_act_tabs)
        self.acttabs_button.setVisible(True)
        # check version -- just displays result
        self.check_version_button = QPushButton('Check Version')
        self.check_version_button.setVisible(False)
        self.check_version_button.clicked.connect(self.on_check_version)
        # ldap search -- displays result of an ldap "test search"
        self.ldap_search_button = QPushButton('Test LDAP Search')
        self.ldap_search_button.setVisible(False)
        self.ldap_search_button.clicked.connect(self.on_test_ldap_search)
        self.ldap_result_button = QPushButton('Test LDAP Result')
        self.ldap_result_button.setVisible(False)
        self.ldap_result_button.clicked.connect(self.on_test_ldap_result)
        # check output of 'get_user_roles' -- just displays result
        # self.get_user_roles_button = QPushButton('Test Get User Roles')
        # self.get_user_roles_button.setVisible(False)
        # self.get_user_roles_button.clicked.connect(self.get_user_roles)
        self.save_object_button = QPushButton('Save Object')
        self.save_object_button.setVisible(False)
        self.save_object_button.clicked.connect(self.on_save_object)
        self.add_project_button = QPushButton('Add a Project')
        self.add_project_button.setVisible(False)
        self.add_project_button.clicked.connect(self.on_add_project)
        self.add_psu_button = QPushButton('Add a Project System Usage')
        self.add_psu_button.setVisible(False)
        self.add_psu_button.clicked.connect(self.on_add_psu)
        self.add_acu_button = QPushButton('Add an Assembly Component Usage')
        self.add_acu_button.setVisible(False)
        self.add_acu_button.clicked.connect(self.on_add_acu)
        self.remove_comp_button = QPushButton('Remove Component (leave position)')
        self.remove_comp_button.setVisible(False)
        self.remove_comp_button.clicked.connect(self.on_remove_component)
        self.gcs_button = QPushButton('Get Cloaking Status')
        self.gcs_button.setVisible(False)
        self.gcs_button.clicked.connect(self.get_cloaking_status)
        self.get_object_button = QPushButton('Get Object')
        self.get_object_button.setVisible(False)
        self.get_object_button.clicked.connect(self.on_get_object)
        self.sync_project_button = QPushButton('Sync Project')
        self.sync_project_button.setVisible(False)
        self.sync_project_button.clicked.connect(self.on_sync_project)
        self.logout_button = QPushButton('Log out')
        self.logout_button.setVisible(False)
        self.logout_button.clicked.connect(self.logout)
        self.role_label = ModeLabel('')
        self.role_label.setVisible(False)
        self.log_widget = LogWidget()
        cloaked_list_label = QLabel('Cloaked Objects:\n'
                                    '[select an object to decloak it]', self)
        self.cloaked_list = AutosizingListWidget(height=100, parent=self)
        self.cloaked_list.itemClicked.connect(self.on_cloaked_selected)
        decloaked_list_label = QLabel('Decloaked Objects:', self)
        self.decloaked_list = AutosizingListWidget(height=50, parent=self)
        vbox = QVBoxLayout()
        vbox.addWidget(self.role_label, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.login_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.conops_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.acttabs_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.check_version_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.ldap_search_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.ldap_result_button, alignment=Qt.AlignVCenter)
        # vbox.addWidget(self.get_user_roles_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.add_project_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.save_object_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.add_psu_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.add_acu_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.remove_comp_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.gcs_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.get_object_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.sync_project_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.logout_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.circle_widget)
        vbox.addWidget(cloaked_list_label)
        vbox.addWidget(self.cloaked_list)
        vbox.addWidget(decloaked_list_label)
        vbox.addWidget(self.decloaked_list)
        hbox = QHBoxLayout()
        hbox.addLayout(vbox)
        hbox.addWidget(self.log_widget, stretch=1)
        main_frame = QWidget()
        main_frame.setLayout(hbox)
        self.setCentralWidget(main_frame)

    def create_timer(self):
        self.circle_timer = QTimer(self)
        self.circle_timer.timeout.connect(self.circle_widget.__next__)
        self.circle_timer.start(25)

    def login(self):
        login_dlg = LoginDialog(parent=self)
        if login_dlg.exec_() == QDialog.Accepted:
            self.log('* logging in with userid "{}" ...'.format(
                                                        login_dlg.userid))
            self.log('  (oid "{}"'.format('test:' + login_dlg.userid))
            self.userid = login_dlg.userid
            message_bus.set_authid(login_dlg.userid)
            message_bus.set_passwd(login_dlg.passwd)
            message_bus.run(u'wss://{}:{}/ws'.format(self.host, self.port),
                            realm=six.u('pangalactic-services'),
                            start_reactor=False, ssl=tls_options)

    def on_joined(self):
        self.log('  + session joined')
        self.login_button.setVisible(False)
        self.logout_button.setVisible(True)
        self.check_version_button.setVisible(True)
        self.ldap_search_button.setVisible(True)
        self.ldap_result_button.setVisible(True)
        # self.get_user_roles_button.setVisible(True)
        self.add_project_button.setVisible(True)
        self.save_object_button.setVisible(True)
        self.add_psu_button.setVisible(False)
        self.add_acu_button.setVisible(False)
        self.remove_comp_button.setVisible(False)
        self.gcs_button.setVisible(True)
        self.get_object_button.setVisible(True)
        self.sync_project_button.setVisible(True)
        self.log('  - getting roles from repo ...')
        # rpc = message_bus.session.call(u'vger.get_role_assignments',
                                       # self.userid)
        # rpc.addCallback(self.on_get_admin_result)
        rpc = message_bus.session.call(u'vger.get_user_roles',
                                       self.userid)
        rpc.addCallback(self.on_get_user_roles_result)
        rpc.addCallback(self.sync_user)
        rpc.addErrback(self.on_failure)

    def start_conops(self):
        mw = ConOpsModeler(external=True, preferred_size=(2000, 1000),
                           parent=self)
        mw.show()

    def start_act_tabs(self):
        win = ActivityTables(parent=self)
        win.show()

    def start_activities(self):
        win = ActivityTables(parent=self)
        win.show()

    def on_get_admin_result(self, data):
        """
        Handle result of the rpc that got our role assignments, which comes in
        one of two forms.  The data has the format:

            {u'organizations': [{oid, id, name, description,
                                 parent_organization}, ...],
             u'users': [{oid, id, name}, ...],
             u'roles': [{oid, name}, ...],
             u'roleAssignments': [{assigned_role, assigned_to,
                                   role_assignment_context}, ...]}

        ... unless the 'no_filter' keyword arg is set to True, in which case
        the full serialized objects are returned.
        """
        ra_txt = ''
        if data:
            self.log('* test role data from repo ...')
            self.log('  Organizations:')
            orgs = data[u'organizations']
            for i, org in enumerate(orgs):
                self.log('    [{}] oid: {}'.format(i, org['oid']))
                self.log('         id: {}'.format(org['id']))
                self.log('         name: {}'.format(org['name']))
                self.log('         mod_datetime: {}'.format(
                                org.get('mod_datetime', '[none]')))
            self.log('  Users:')
            users = data[u'users']
            for i, user in enumerate(users):
                self.log('    [{}] oid: {}'.format(i, user['oid']))
                self.log('         id: {}'.format(user['id']))
                self.log('         name: {}'.format(user['name']))
            self.log('  Roles:')
            roles = data[u'roles']
            for i, role in enumerate(roles):
                self.log('    [{}] oid: {}'.format(i, role['oid']))
                self.log('         name: {}'.format(role['name']))
            self.log('  Role Assignments:')
            ras = data[u'roleAssignments']
            if ras:
                for i, rasgt in enumerate(ras):
                    self.log('    [{}] assigned role: {}'.format(i,
                                                    rasgt['assigned_role']))
                    self.log('         assigned to: {}'.format(
                                                    rasgt['assigned_to']))
                    self.log('         assignment context: {}'.format(
                                        rasgt['role_assignment_context']))
                ra = ras[0]
                roles = {r[u'oid']:r[u'name'] for r in data[u'roles']}
                self.log('  - role data:  %s' % str(roles))
                ra_txt = ': '.join([ra.get('role_assignment_context', 'Global'),
                                    roles[ra['assigned_role']]])
            if ra_txt:
                self.role_label.setText(ra_txt)
                self.role_label.setVisible(True)
        else:
            self.log('* no role assignments found.')
        self.subscribe_to_channels()

    def subscribe_to_channels(self, channels=None):
        channels = channels or []
        if not channels:
            channels = [u'vger.channel.public', u'vger.channel.H2G2']
        for channel in channels:
            sub = message_bus.session.subscribe(self.on_signal, channel)
            sub.addCallback(self.on_success)
            sub.addErrback(self.on_failure)
        return channels

    def on_success(self, result):
        print("* subscribed successfully: {}".format(str(result)))

    def on_failure(self, f):
        print("* subscription failure: {}".format(f.getTraceback()))

    def sync_user(self, data):
        """
        Sync the user's Person object with the admin/repo service.

        Args:
            data:  parameter required for callback (ignored)
        """
        # get Person object corresponding to login userid
        self.log('* calling rpc get_user_object ...')
        rpc = message_bus.session.call(u'vger.get_user_object', self.userid)
        rpc.addCallback(self.reset_user)
        rpc.addErrback(self.on_failure)

    def reset_user(self, data):
        """
        Substitute the user's Person object for the admin/repo service.

        Args:
            data:  parameter required for callback (ignored)
        """
        # TODO:  replace all 'me' objects with user's Person instance
        # -- use 'created_objects' to find them ...
        self.log('* return from get_user_object:  {}'.format(data))

    def get_user_roles(self):
        rpc = message_bus.session.call(u'vger.get_user_roles', self.userid)
        # first, let's see what we get ...
        # rpc.addCallback(self.on_result)
        rpc.addCallback(self.on_get_user_roles_result)
        rpc.addErrback(self.on_failure)

    def on_activity(self, obj=None):
        self.log('I just got activity {}'.format(
                 getattr(obj, 'id', '[unnamed activity]')))

    def on_get_user_roles_result(self, data):
        """
        Handle result of the rpc 'vger.get_user_roles'.  The data has the
        format:

            [serialized user, serialized role assignments]

        ... in which both items are lists of serialized objects.
        """
        if data:
            user_data, ras_data = data
            szd_user = user_data[0]
            self.log('---- USER ROLE DATA ---------------')
            self.log('* userid: {}'.format(szd_user['id']))
            self.log('* serialized role-related objects:')
            for so in ras_data:
                self.log('  - class: {}'.format(so['_cname']))
                self.log('    + id: "{}", oid: "{}"'.format(so['id'],
                                                            so['oid']))
                if so['_cname'] == 'RoleAssignment':
                    self.log('    + assigned role: {}'.format(
                                                     so['assigned_role']))
                    self.log('    + assigned to: {}'.format(
                                                     so['assigned_to']))
                    self.log('    + assignment context: {}'.format(
                                    so.get('role_assignment_context', 'None')))
            self.log('---- END USER ROLE DATA -----------')

    def on_check_version(self):
        self.log('* calling rpc "vger.get_version()" ...')
        rpc = message_bus.session.call(u'vger.get_version')
        rpc.addCallback(self.on_result)
        rpc.addErrback(self.on_failure)

    def on_test_ldap_search(self):
        self.log('* calling rpc "vger.search_ldap()" ...')
        rpc = message_bus.session.call(u'vger.search_ldap', test='search',
                                       first_name='Stephen',
                                       last_name='Waterbury')
        rpc.addCallback(self.on_result)
        rpc.addErrback(self.on_failure)

    def on_test_ldap_result(self):
        self.log('* calling rpc "vger.search_ldap()" ...')
        rpc = message_bus.session.call(u'vger.search_ldap', test='result',
                                       first_name='Stephen',
                                       last_name='Waterbury')
        rpc.addCallback(self.on_result)
        rpc.addErrback(self.on_failure)

    def on_cloaked_selected(self, item):
        self.log('* on_cloaked_selected()')
        self.log('  calling rpc "vger.decloak()" ...')
        obj_oid = self.cloaked[self.cloaked_list.currentRow()]
        actor_oid = 'H2G2'
        # for testing "public" decloak:
        # actor_oid = ''
        rpc = message_bus.session.call(u'vger.decloak', obj_oid, actor_oid)
        rpc.addCallback(self.on_decloak_result)
        rpc.addErrback(self.on_failure)

    def on_decloak_result(self, stuff):
        self.log('* result received from rpc vger.decloak:  %s' % str(stuff))
        actor_oids, msg, obj_oid = stuff
        if not msg:
            if obj_oid in self.cloaked:
                idx = self.cloaked.index(obj_oid)
                self.log('  - removing item %i from cloaked...' % idx)
                self.cloaked_list.takeItem(idx)
                self.cloaked.remove(obj_oid)
            if not obj_oid in self.decloaked:
                self.log('  - adding to decloaked...')
                self.decloaked.append(obj_oid)
                self.decloaked_list.addItem(obj_oid)
            self.log('* decloak succeeded.')
        else:
            self.log('* decloak was unsuccessful:')
            self.log('  status: {}'.format(msg))

    def get_cloaking_status(self, obj=None):
        """
        Get cloaking information on the specified object and display dialog
        with cloaking state and options to decloak.

        Keyword Args:
            obj (Identifiable):  object whose cloaking info is to be shown
        """
        rpc = message_bus.session.call(u'vger.get_cloaking_status',
                                       self.test_oid)
        rpc.addCallback(self.on_get_cloaking_status)
        rpc.addErrback(self.on_failure)

    def on_get_cloaking_status(self, result):
        """
        Display a dialog with the result of a request for cloaking status of an
        object.
        """
        self.log('* cloaking status:')
        self.log(str(result))

    def on_save_object(self):
        """
        Save a generated test object to the repo.  NOTE: this function will
        only succeed of the client has logged in as one of the test users
        (steve, buckaroo, zaphod).
        """
        new_oid = str(uuid4())
        self.test_oid = new_oid
        suffix = new_oid[0:5]
        ptype = product_types[random.randint(0, len(product_types) - 1)]
        new_id = 'TEST_' + ptype['id'][0:5] + '_' + suffix
        new_name = str(ptype['name']) + ' ' + str(suffix)
        now = str(dtstamp())
        obj_parms = {}
        for pid, parm in test_parms.items():
            obj_parms[pid] = deepcopy(parm)
        gen_test_pvals(obj_parms)
        user_oid = 'test:' + self.userid
        serialized_obj = dict(_cname='HardwareProduct', oid=new_oid, id=new_id,
                              name=new_name, creator=user_oid,
                              create_datetime=now, modifier=user_oid,
                              mod_datetime=now, version='1', iteration=0,
                              version_sequence=0, product_type=ptype['oid'],
                              parameters=obj_parms)
        self.log('* calling rpc "vger.save()" ...')
        self.last_saved_obj = serialized_obj
        if self.system_level_obj:
            self.add_acu_button.setVisible(True)
        else:
            self.add_psu_button.setVisible(True)
        rpc = message_bus.session.call(u'vger.save', [serialized_obj])
        rpc.addCallback(self.on_save_result)
        rpc.addErrback(self.on_failure)

    def on_save_result(self, stuff):
        self.log('* result received from rpc "vger.save":  %s' % str(stuff))
        if stuff.get('new_obj_dts'):
            self.log('  - adding new cloaked objects ...')
            for oid in stuff['new_obj_dts']:
                if not oid in self.cloaked:
                    self.cloaked.append(oid)
                    self.cloaked_list.addItem(oid)

    def on_null_result(self):
        self.log('* no result expected.')

    def on_add_project(self):
        new_oid = str(uuid4())
        self.test_oid = new_oid
        suffix = new_oid[0:5]
        new_id = 'TEST_PROJECT_' + suffix
        new_name = str('Test Project ') + str(suffix)
        self.log('* calling rpc vger.save() with project "{}"'.format(new_id))
        rpc = message_bus.session.call(u'omb.organization.add',
                oid=new_oid, id=new_id, name=new_name, org_type='Project',
                parent=None)
        rpc.addCallback(self.on_save_project_result)
        rpc.addErrback(self.on_failure)

    def on_save_project_result(self, stuff):
        self.log('* result received from rpc "vger.save":  %s' % str(stuff))

    def on_add_psu(self):
        if self.last_saved_obj:
            self.log('* Adding a ProjectSystemUsage for system {} ...'.format(
                                                    self.last_saved_obj['id']))
        else:
            self.log("* Can't add a PSU -- haven't saved any objects yet.")
            return
        new_oid = str(uuid4())
        new_id = 'psu-H2G2-' + self.last_saved_obj['id']
        new_name = u'Test ProjectSystemUsage ' + str(new_id)
        now = str(dtstamp())
        user_oid = 'test:' + self.userid
        psu = dict(_cname='ProjectSystemUsage', oid=new_oid, id=new_id,
                   name=new_name, create_datetime=now, mod_datetime=now,
                   creator=user_oid, modifier=user_oid, project='H2G2',
                   system=self.last_saved_obj['oid'])
        self.system_level_obj = self.last_saved_obj
        self.last_saved_obj = None
        self.cloaked = []
        self.cloaked_list.clear()
        self.add_psu_button.setVisible(False)
        rpc = message_bus.session.call(u'vger.save', [psu])
        rpc.addCallback(self.on_save_result)
        rpc.addErrback(self.on_failure)

    def on_add_acu(self):
        if self.last_saved_obj and self.system_level_obj:
            self.log('* Adding an AssemblyComponentUsage (Acu) to {}'.format(
                                                    self.last_saved_obj['id']))
        else:
            self.log("* Can't add an Acu -- don't have system level object "
                     "and component object yet.")
            return
        new_oid = str(uuid4())
        new_id = '-'.join(['acu', self.system_level_obj['id'],
                           self.last_saved_obj['id']])
        new_name = u'Test Acu ' + str(new_id)
        now = str(dtstamp())
        user_oid = 'test:' + self.userid
        acu = dict(_cname='Acu', oid=new_oid, id=new_id,
                   name=new_name, create_datetime=now, mod_datetime=now,
                   creator=user_oid, modifier=user_oid,
                   assembly=self.system_level_obj['oid'],
                   component=self.last_saved_obj['oid'],
                   product_type_hint=self.last_saved_obj['product_type'])
        # Don't use that object again
        self.last_saved_obj = None
        self.system_level_obj = None
        self.latest_acu = acu
        self.add_acu_button.setVisible(False)
        self.remove_comp_button.setVisible(True)
        self.cloaked = []
        self.cloaked_list.clear()
        rpc = message_bus.session.call(u'vger.save', [acu])
        rpc.addCallback(self.on_save_result)
        rpc.addErrback(self.on_failure)

    def on_remove_component(self):
        self.log("* on_remove_component()")
        if self.latest_acu:
            self.log("  acu located -- removing component ...")
            self.latest_acu['component'] = 'pgefobjects:TBD'
            self.latest_acu['mod_datetime'] = str(dtstamp())
            acu = self.latest_acu
            self.latest_acu = None
            self.remove_comp_button.setVisible(False)
            rpc = message_bus.session.call(u'vger.save', [acu])
            rpc.addCallback(self.on_save_result)
            rpc.addErrback(self.on_failure)
        else:
            self.log("  no acu found -- can't remove.")
            return

    def on_get_object(self):
        self.log('* calling rpc "vger.get_object()" ...')
        rpc = message_bus.session.call(u'vger.get_object', 'H2G2')
        rpc.addCallback(self.on_result)
        rpc.addErrback(self.on_failure)

    def on_sync_project(self):
        self.log('* calling rpc vger.sync_project({})'.format('H2G2'))
        rpc = message_bus.session.call(u'vger.sync_project', 'H2G2', [])
        rpc.addCallback(self.on_result)
        rpc.addErrback(self.on_failure)

    def on_result(self, stuff):
        self.log('* result received:  %s' % str(stuff))

    def on_get_object_result(self, stuff):
        self.log('* result of get_object() received:')
        self.log('  {} serialized objects:'.format(len(stuff)))
        for so in stuff:
            if str(so['_cname']) == 'HardwareProduct':
                self.log('  - HardwareProduct "{}"'.format(so['oid']))

    def logout(self):
        self.log('* logging out ...')
        message_bus.session.leave()

    def on_leave(self):
        self.log('  + session left.')
        message_bus.session.disconnect()
        self.login_button.setVisible(True)
        self.logout_button.setVisible(False)
        self.check_version_button.setVisible(False)
        self.ldap_search_button.setVisible(False)
        self.ldap_result_button.setVisible(False)
        # self.get_user_roles_button.setVisible(False)
        self.add_project_button.setVisible(False)
        self.save_object_button.setVisible(False)
        self.add_psu_button.setVisible(False)
        self.gcs_button.setVisible(False)
        self.get_object_button.setVisible(False)
        self.sync_project_button.setVisible(False)
        self.role_label.setText('')
        self.role_label.setVisible(False)
        message_bus.session = None

    def log(self, msg):
        timestamp = '[%010.3f]' % time.process_time()
        self.log_widget.append(timestamp + ' ' + str(msg))

    def closeEvent(self, event):
        # things to do when window is closed
        message_bus.session = None
        # NOTE: the order of these incantations is important ...
        # threadpool.stop() must be done *before* reactor.stop()
        # or it will raise an AlreadyQuit exception
        if self.reactor:
            try:
                if self.reactor.threadpool is not None:
                    self.reactor.threadpool.stop()
                if self.reactor.running:
                    self.reactor.callFromThread(self.reactor.stop)
            except:
                try:
                    if self.reactor.running:
                        self.reactor.stop()
                except:
                    pass
        event.accept()
        sys.exit()

#-------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', dest='host', type=six.text_type,
                        default='localhost',
                        help='the host to connect to [default: localhost]')
    parser.add_argument('--port', dest='port', type=six.text_type,
                        default='8080',
                        help='the port to connect to [default: 8080]')
    options = parser.parse_args()
    app = QApplication(sys.argv)
    orb.start('junk_home', debug=True)
    mission = orb.get('test:Mission.H2G2')
    if not mission:
        if not state.get('test_users_loaded'):
            print('* loading test users ...')
            deserialize(orb, create_test_users())
            state['test_users_loaded'] = True
        print('* loading test project H2G2 ...')
        deserialize(orb, create_test_project())
        mission = orb.get('test:Mission.H2G2')
    # if not mission.components:
        # launch = clone('Activity', id='launch', name='Launch')
        # ref_des = '1'
        # acu = clone('Acu', id=get_acu_id(mission.id, ref_des),
                    # name=get_acu_name(mission.name, ref_des),
                    # assembly=mission, component=launch)
        # orb.save([launch, acu])
    print('app created')
    try:
        import qt5reactor
    except ImportError:
        # Maybe qt5reactor is placed inside twisted.internet in site-packages?
        from twisted.internet import qt5reactor
    qt5reactor.install()
    from twisted.internet import reactor
    mainwindow = MainWindow(options.host, options.port, reactor=reactor)
    print('MainWindow instantiated ...')
    print('  configured to connect to "{}"'.format(options.host))
    print('  on port {}'.format(options.port))
    mainwindow.show()
    reactor.runReturn()
    sys.exit(app.exec_())

