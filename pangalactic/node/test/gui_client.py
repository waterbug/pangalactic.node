# -*- coding: utf-8 -*-
"""
GUI client for autobahn/crossbar.

Based on:
  * pyqt twisted socket client example, by Eli Bendersky (eliben@gmail.com)
  * autobahn/crossbar gauges example, by Elvis Stansvik
    https://github.com/estan/gauges
  * crossbar examples "advanced" (CRA) auth example
"""
import argparse, os, pprint, random, sys, time
from copy import deepcopy
from uuid import uuid4
from PyQt5.QtCore import QRectF, QSize, QTimer, Qt
from PyQt5.QtGui import QColor, QPainter, QPen, QPalette
from PyQt5.QtWidgets import (QApplication, QDialog, QDialogButtonBox,
                             QFormLayout, QHBoxLayout, QLabel, QMainWindow,
                             QMessageBox, QPushButton, QSizePolicy,
                             QTextBrowser, QVBoxLayout, QWidget)
from louie import dispatcher
from twisted.internet.defer import DeferredList
from twisted.internet._sslverify import OpenSSLCertificateAuthorities
from twisted.internet.ssl import CertificateOptions
from OpenSSL import crypto

from pangalactic.core                 import state
from pangalactic.core.parametrics     import add_parameter
from pangalactic.core.refdata         import core
from pangalactic.core.serializers     import deserialize, serialize
from pangalactic.core.test.utils      import (create_test_project,
                                              create_test_users,
                                              gen_test_pvals, test_parms)
from pangalactic.core.utils.datetimes import dtstamp
from pangalactic.core.utils.meta      import uncook_datetime
from pangalactic.core.uberorb         import orb
# from pangalactic.node.conops          import ConOpsModeler
from pangalactic.node                 import fix_qt_import_error
from pangalactic.node.dialogs         import LoginDialog
from pangalactic.node.utils           import clone
from pangalactic.node.widgets         import ModeLabel
from pangalactic.node.widgets         import AutosizingListWidget
from pangalactic.node.message_bus     import PgxnMessageBus

message_bus = PgxnMessageBus()
cert_fname = 'server_cert.pem'
try:
    cert = crypto.load_certificate(
            crypto.FILETYPE_PEM,
            str(open(cert_fname, 'r').read()))
    tls_options = CertificateOptions(
        trustRoot=OpenSSLCertificateAuthorities([cert]))
except:
    cert = None

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
        super().__init__(parent)
        self.setWindowTitle("Hey!")
        form = QFormLayout(self)
        something_happened_label = QLabel('woo!', self)
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
        super().__init__(parent)
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
        painter.translate(self.width()/2, self.height()/2)

        #range of diameter must start at a number greater than 0
        for diameter in range(1, 50, 9):
            delta = abs((self.nframe % 64) - diameter/2)
            alpha = 255 - (delta * delta)/4 - diameter
            if alpha > 0:
                painter.setPen(QPen(QColor(0, diameter/2, 127, alpha), 3))
                painter.drawEllipse(QRectF(
                    -diameter/2.0, -diameter/2.0,
                    diameter, diameter))


class LogWidget(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        palette = QPalette()
        palette.setColor(QPalette.Base, QColor("#ddddfd"))
        self.setPalette(palette)
        self.setStyleSheet('font-size: 18px')
        self.setSizePolicy(QSizePolicy.Expanding,
                           QSizePolicy.Expanding)


class MainWindow(QMainWindow):
    MOD_COUNT = 0

    def __init__(self, host, port, auth_method='cryptosign', reactor=None,
                 parent=None):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.auth_method = auth_method
        self.reactor = reactor
        self.create_main_frame()
        self.log(f'* host set to: {host}')
        self.log(f'* port set to: {port}')
        self.log(f'* auth method set to: "{auth_method}"')
        self.setGeometry(100, 100, 1000, 800)
        self.create_timer()
        dispatcher.connect(self.on_joined, 'onjoined')
        dispatcher.connect(self.on_leave, 'onleave')
        dispatcher.connect(self.on_remote_decloaked_signal,
                                                    'remote: decloaked')
        dispatcher.connect(self.on_remote_modified_signal,
                                                    'remote: modified')
        dispatcher.connect(self.on_remote_deleted_signal,
                                                    'remote: deleted')
        self.new_index = 0
        self.test_oid = ''
        self.cloaked = []
        self.decloaked = []
        self.last_saved_obj = None
        self.system_level_obj = None
        self.latest_acu = None

    # NOTE: this method is not connected to anything
    # def on_signal(self, msg):
        # print("event received on: {}".format(msg))
        # subject, content = list(msg.items())[0]
        # self.log("Event received:")
        # self.log("      subject: {}".format(str(subject)))
        # self.log("      content: {}".format(str(content)))
        # if str(subject) in ['new', 'decloaked', 'modified', 'deleted']:
            # self.log('* calling rpc vger.get_object() on {}'.format(content[0]))
            # rpc = message_bus.session.call('vger.get_object', content[0])
            # rpc.addCallback(self.on_get_object_result)
            # rpc.addErrback(self.on_failure)

    def on_pubsub_msg(self, msg):
        """
        Handle pubsub messages.

        Args:
            msg (tuple): the message, a tuple of (subject, content)
        """
        for item in msg.items():
            subject, content = item
            self.log("*** received pubsub msg ...")
            self.log("       subject: {}".format(subject))
            self.log("       content: {}".format(content))
            obj_id = '[unknown]'
            # base text
            text = "remote {}: ".format(subject)
            if subject in ['new', 'decloaked']:
                # actor_oid is the oid of the Actor to which the object has
                # been decloaked (usually an Organization or Project)
                obj_oid, obj_id, actor_oid, actor_id = content
                text += obj_id
            elif subject == 'modified':
                obj_oid, obj_id, obj_mod_datetime = content
                obj = orb.get(obj_oid)
                if obj and obj.name:
                    if isinstance(obj, orb.classes['Product']):
                        pt = getattr(obj.product_type, 'name', 'unknown type')
                        text += "{} ({}) [{}]".format(obj_id, obj.name, pt)
                    elif isinstance(obj, orb.classes['Acu']):
                        pth = getattr(obj.product_type_hint, 'name',
                                      'unknown type')
                        text += "{} [{}]".format(obj_id, pth)
                else:
                    text += obj_id
            elif subject == 'deleted':
                obj_oid = content
                obj = orb.get(obj_oid)
                if obj:
                    obj_id = obj.id
                text += obj_id
            elif subject == 'organization':
                obj_oid = content['oid']
                obj_id = content['id']
                text += obj_id
            elif subject == 'person added':
                obj_oid = content['oid']
                obj_id = content['id']
                text += obj_id
            w = NotificationDialog(text, parent=self)
            w.setWidth(200)
            w.show()

    def create_main_frame(self):
        self.circle_widget = CircleWidget()
        self.login_button = QPushButton('Log in')
        self.login_button.clicked.connect(self.login)
        # Con Ops Modeler --> opens a ConOpsModeler window
        # self.conops_button = QPushButton('Con Ops Modeler')
        # self.conops_button.clicked.connect(self.start_conops)
        # self.conops_button.setVisible(True)
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
        self.save_object_button = QPushButton('Save Cloaked Object')
        self.save_object_button.setVisible(False)
        self.save_object_button.clicked.connect(self.on_save_object)
        self.save_public_object_button = QPushButton('Save Public Object')
        self.save_public_object_button.setVisible(False)
        self.save_public_object_button.clicked.connect(
                                            self.on_save_public_object)
        self.add_psu_button = QPushButton('Add a Project System Usage')
        self.add_psu_button.setVisible(False)
        self.add_psu_button.clicked.connect(self.on_add_psu)
        self.add_acu_button = QPushButton('Add an Assembly Component Usage')
        self.add_acu_button.setVisible(False)
        self.add_acu_button.clicked.connect(self.on_add_acu)
        self.remove_comp_button = QPushButton('Remove Component (leave position)')
        self.remove_comp_button.setVisible(False)
        self.remove_comp_button.clicked.connect(self.on_remove_component)
        self.get_object_button = QPushButton('Get Object')
        self.get_object_button.setVisible(False)
        self.get_object_button.clicked.connect(self.on_get_object)
        # self.sync_project_button = QPushButton('Sync Project')
        # self.sync_project_button.setVisible(False)
        # self.sync_project_button.clicked.connect(self.on_sync_project)
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
        if cert:
            vbox.addWidget(self.login_button, alignment=Qt.AlignVCenter)
        else:
            message = 'Certificate not found or not readable ...\n'
            message += 'operating in local-only mode.'
            popup = QMessageBox(QMessageBox.Warning,
                                "No certificate", message,
                                QMessageBox.Ok, self)
            popup.show()
        # vbox.addWidget(self.conops_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.check_version_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.ldap_search_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.ldap_result_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.save_object_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.save_public_object_button,
                                                alignment=Qt.AlignVCenter)
        vbox.addWidget(self.add_psu_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.add_acu_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.remove_comp_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.get_object_button, alignment=Qt.AlignVCenter)
        # vbox.addWidget(self.sync_project_button, alignment=Qt.AlignVCenter)
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
        if self.auth_method == 'cryptosign':
            self.log('* logging in using cryptosign auth ...')
            key_path = os.path.join(orb.home, '.creds', 'private.key')
            if os.path.exists(key_path):
                message_bus.set_key_path(key_path)
            else:
                message = 'Key file <{key_path}> not found ...\n'
                message += 'operating in local-only mode.'
                popup = QMessageBox(QMessageBox.Warning,
                                    "No certificate", message,
                                    QMessageBox.Ok, self)
                popup.show()
            message_bus.run('wss://{}:{}/ws'.format(self.host, self.port),
                            auth_method='cryptosign', realm='pangalactic-services',
                            start_reactor=False, ssl=tls_options)
        else:  # password ("ticket") auth
            login_dlg = LoginDialog(parent=self)
            if login_dlg.exec_() == QDialog.Accepted:
                self.log('* logging in with userid "{}" ...'.format(
                                                            login_dlg.userid))
                self.log('  (oid "{}"'.format('test:' + login_dlg.userid))
                message_bus.set_authid(login_dlg.userid)
                message_bus.set_passwd(login_dlg.passwd)
                message_bus.run('wss://{}:{}/ws'.format(self.host, self.port),
                                auth_method='ticket',
                                realm='pangalactic-services',
                                start_reactor=False, ssl=tls_options)

    def on_joined(self):
        self.log('  + session joined')
        # get userid from message_bus ("authid" of session details ...)
        authid = message_bus.session.details.authid
        self.log(f'    userid: "{authid}"')
        self.userid = authid
        self.login_button.setVisible(False)
        self.logout_button.setVisible(True)
        self.check_version_button.setVisible(True)
        self.ldap_search_button.setVisible(True)
        self.ldap_result_button.setVisible(True)
        self.save_object_button.setVisible(True)
        self.save_public_object_button.setVisible(True)
        self.add_psu_button.setVisible(False)
        self.add_acu_button.setVisible(False)
        self.remove_comp_button.setVisible(False)
        self.get_object_button.setVisible(True)
        # self.sync_project_button.setVisible(True)
        self.log('  - getting roles from repo ...')
        rpc = message_bus.session.call('vger.get_user_roles',
                                       self.userid)
        rpc.addCallback(self.on_get_user_roles_result)
        rpc.addErrback(self.on_failure)
        rpc.addCallback(self.subscribe_to_channels)
        rpc.addErrback(self.on_failure)
        rpc.addCallback(self.on_sync_project)
        rpc.addErrback(self.on_failure)

    # def start_conops(self):
        # mw = ConOpsModeler(parent=self)
        # mw.show()

    def subscribe_to_channels(self, channels=None):
        channels = channels or []
        if not channels:
            channels = ['vger.channel.public', 'vger.channel.H2G2']
        subs = []
        for channel in channels:
            sub = message_bus.session.subscribe(self.on_pubsub_msg, channel)
            sub.addCallback(self.on_success)
            sub.addErrback(self.on_failure)
            subs.append(sub)
        self.log('* subscribed to channels: {}'.format(channels))
        return DeferredList(subs, consumeErrors=True)

    def on_success(self, result):
        self.log("* subscribed successfully: {}".format(str(result)))

    def on_failure(self, f):
        self.log("* subscription failure: {}".format(f.getTraceback()))

    def on_get_user_roles_result(self, data):
        """
        Handle result of the rpc 'vger.get_user_roles'.  The returned data has
        the structure:

            [serialized local user (Person) object,
             serialized Organization/Project objects,
             serialized Person objects,
             serialized RoleAssignment objects,
             oids unknown to the server]
        """
        if data:
            self.log('---- RAW DATA FROM "get_user_roles" ---------------')
            self.log(pprint.pformat(data))
            self.log('---- END OF RAW DATA ------------------------------')
            szd_user, szd_orgs, szd_people, szd_ras, unknown_oids = data
            deserialize(orb, szd_user)
            deserialize(orb, szd_orgs)
            deserialize(orb, szd_people)
            deserialize(orb, szd_ras)
            self.user = orb.select('Person', id=self.userid)
            self.log('---- USER OBJECT ASSIGNED ----------')
            self.log('* self.user.oid: "{}"'.format(self.user.oid))
            self.log('* userid: "{}"'.format(self.user.id))
            self.log('---- USER ROLES INFO ---------------')
            self.log('* roles assigned to this user:')
            for so in szd_ras:
                if (so['_cname'] == 'RoleAssignment' and
                    so['assigned_to'] == self.user.oid):
                    self.log('    + assigned role oid: {}'.format(
                                                     so['assigned_role']))
                    self.log('    + assignment context oid: {}'.format(
                                    so.get('role_assignment_context', 'None')))
            self.log('---- END USER ROLES INFO -----------')

    def on_check_version(self):
        self.log('* calling rpc "vger.get_version()" ...')
        rpc = message_bus.session.call('vger.get_version')
        rpc.addCallback(self.on_result)
        rpc.addErrback(self.on_failure)

    def on_test_ldap_search(self):
        self.log('* calling rpc "vger.search_ldap()" ...')
        rpc = message_bus.session.call('vger.search_ldap', test='search',
                                       first_name='Stephen',
                                       last_name='Waterbury')
        rpc.addCallback(self.on_result)
        rpc.addErrback(self.on_failure)

    def on_test_ldap_result(self):
        self.log('* calling rpc "vger.search_ldap()" ...')
        rpc = message_bus.session.call('vger.search_ldap', test='result',
                                       first_name='Stephen',
                                       last_name='Waterbury')
        rpc.addCallback(self.on_result)
        rpc.addErrback(self.on_failure)

    def on_cloaked_selected(self, item):
        self.log('* on_cloaked_selected()')
        self.log('  setting "public" and saving object ...')
        obj_oid = self.cloaked[self.cloaked_list.currentRow()]
        obj = orb.get(obj_oid)
        obj.public = True
        obj.mod_datetime = dtstamp()
        orb.save([obj])
        sobjs = serialize(orb, [obj])
        rpc = message_bus.session.call('vger.save', sobjs)
        rpc.addCallback(self.on_vger_save_result)
        rpc.addErrback(self.on_failure)

    def on_vger_save_result(self, stuff):
        self.log('  vger.save result: {}'.format(str(stuff)))
        try:
            msg = ''
            if stuff.get('new_obj_dts'):
                msg += '{} new'.format(len(stuff['new_obj_dts']))
            if stuff.get('mod_obj_dts'):
                msg += '{} modified'.format(len(stuff['mod_obj_dts']))
            if stuff.get('unauth'):
                msg += '{} unauthorized'.format(len(stuff['unauth']))
            if stuff.get('no_owners'):
                msg += '{} no owners (not saved); '.format(
                                                    len(stuff['no_owners']))
            self.log('- vger save: {}'.format(msg))
            new_cloaked = 0
            newly_decloaked = 0
            if stuff.get('new_obj_dts'):
                self.log('  - checking for new cloaked objects ...')
                for oid in stuff['new_obj_dts']:
                    if not oid in self.cloaked:
                        self.cloaked.append(oid)
                        self.cloaked_list.addItem(oid)
                        new_cloaked += 1
            if stuff.get('mod_obj_dts'):
                self.log('  - checking for newly decloaked objects ...')
                for oid in stuff['mod_obj_dts']:
                    if oid in self.cloaked:
                        self.cloaked.remove(oid)
                        obj = orb.get(oid)
                        if obj and obj.public:
                            self.cloaked_list.clear()
                        newly_decloaked += 1
            if new_cloaked:
                self.log(f'    {new_cloaked} new cloaked object(s) added.')
            else:
                self.log('    no cloaked objects found.')
            if newly_decloaked:
                self.log(f'    {newly_decloaked} newly decloaked object(s).')
            else:
                self.log('    no newly decloaked objects found.')
        except:
            self.log('  result format incorrect.')

    def on_remote_decloaked_signal(self, content=None):
        """
        Call functions to update applicable widgets when a pub/sub message is
        received from the repository service indicating that a new object has
        been decloaked or an existing decloaked object has been modified.

        Keyword Args:
            content (tuple):  content of the pub/sub message, which has the
                form of a 4-tuple:  (obj_oid, obj_id, actor_oid, actor_id)
        """
        self.log('* "remote: decloaked" signal received ...')
        if not content:
            self.log(' - content was empty.')
            return
        try:
            obj_oid, obj_id, actor_oid, actor_id = content
        except:
            # handle the error
            # TODO: pop up a notification dialog
            self.log('  - content could not be parsed:')
            self.log('    {}'.format(str(content)))
            return
        obj = orb.get(obj_oid)
        if obj:
            self.log('  - object is already in local db.')
        else:
            # get object from repository ...
            self.log('  - object unknown -- getting from repo...')
            rpc = message_bus.session.call('vger.get_object', obj_oid,
                                           include_components=True)
            rpc.addCallback(self.on_rpc_get_object)
            rpc.addErrback(self.on_failure)

    def on_rpc_get_object(self, serialized_objects):
        """
        Handle the result of the rpc 'vger.get_object', which returns a list of
        serialized objects.

        Args:
            serialized_objects (list): a list of serialized objects
        """
        self.log("* on_rpc_get_object")
        self.log("  got: {} serialized objects".format(
                                                    len(serialized_objects)))
        if not serialized_objects:
            self.log('  result was empty!')
            return False
        objs = deserialize(orb, serialized_objects)
        for obj in objs:
            cname = obj.__class__.__name__
            if cname == 'RoleAssignment':
                if obj.assigned_to.oid == self.user.oid:
                    html = '<h3>You have been assigned the role:</h3>'
                    html += '<p><b><font color="green">{}</font></b>'.format(
                                                        obj.assigned_role.id)
                    html += ' in <b><font color="green">{}</font>'.format(
                                    getattr(obj.role_assignment_context, 'id',
                                            'global context'))
                    html += '</b></p>'
                    self.w = NotificationDialog(html, parent=self)
                    self.w.show()
        if not objs:
            self.log('  deserialize() returned no objects --')
            self.log('  those received were already in the local db.')

    def on_remote_modified_signal(self, content=None):
        """
        Handle louie signal "remote: modified".
        """
        self.log('* "remote: modified" signal received ...')
        # content is a tuple:  (obj.oid, str(obj.mod_datetime))
        obj_oid, obj_id, dts_str = content
        self.log('  oid: {}'.format(obj_oid))
        self.log('  id: {}'.format(obj_id))
        # first check if we have the object
        obj = orb.get(obj_oid)
        if obj:
            self.log('  ')
            # if the mod_datetime of the repo object is later, get it
            dts = None
            if dts_str:
                dts = uncook_datetime(dts_str)
            self.log('  remote object mod_datetime: {}'.format(dts_str))
            self.log('  local  object mod_datetime: {}'.format(
                                            str(obj.mod_datetime)))
            if dts == obj.mod_datetime:
                self.log('  local and remote objects have')
                self.log('  same mod_datetime, ignoring.')
            elif dts > obj.mod_datetime:
                # get the remote object
                self.log('  remote object is newer, getting...')
                rpc = message_bus.session.call('vger.get_object', obj.oid,
                                               include_components=True)
                rpc.addCallback(self.on_remote_get_mod_object)
                rpc.addErrback(self.on_failure)
            else:
                self.log('  local object is newer, ignoring remote.')
        else:
            self.log('  ')
            self.log('  object not found in local db, getting ...')
            rpc = message_bus.session.call('vger.get_object', obj.oid,
                                           include_components=True)
            rpc.addCallback(self.on_remote_get_mod_object)
            rpc.addErrback(self.on_failure)

    def on_remote_get_mod_object(self, serialized_objects):
        self.log('* on_remote_get_mod_object()')
        objs =  deserialize(orb, serialized_objects)
        if not objs:
            self.log('  deserialize() returned nothing --')
            self.log('  the objs received were already in the local db.')
        for obj in objs:
            # same as for local 'modified object' but without the remote
            # calls ...
            cname = obj.__class__.__name__
            if cname == 'RoleAssignment':
                if obj.assigned_to.oid == self.user.oid:
                    html = '<h3>You have been assigned the role:</h3>'
                    html += '<p><b><font color="green">{}</font></b>'.format(
                                                        obj.assigned_role.id)
                    html += ' in <b><font color="green">{}</font>'.format(
                                    getattr(obj.role_assignment_context, 'id',
                                            'global context'))
                    html += '</b></p>'
                    self.w = NotificationDialog(html, parent=self)
                    self.w.show()

    def on_remote_deleted_signal(self, content=None):
        """
        Handle louie signal "remote: deleted".
        """
        self.log('* "remote: deleted" signal received ...')
        # content is an oid
        obj_oid = content
        self.log('  oid: {}'.format(obj_oid))
        # first check if we have the object
        obj = orb.get(obj_oid)
        if obj:
            cname = obj.__class__.__name__
            if (cname in ['Acu', 'ProjectSystemUsage']
                and hasattr(self, 'sys_tree')):
                # find all expanded tree nodes that reference obj
                idxs = self.sys_tree.link_indexes_in_tree(obj)
                # if any are found, signal them to update
                for idx in idxs:
                    node = self.sys_tree.source_model.get_node(idx)
                    if cname == 'Acu':
                        node_des = (getattr(node.link, 'reference_designator',
                                    None) or '(No reference designator)')
                    else:
                        node_des = (getattr(node.link, 'system_role',
                                    None) or '(No system role)')
                    self.log('  deleting position "%s"'.format(node_des))
                    pos = idx.row()
                    row_parent = idx.parent()
                    parent_id = self.sys_tree.source_model.get_node(
                                                            row_parent).obj.id
                    self.log('  at row {} of parent {}'.format(pos,
                                                                   parent_id))
                    # removeRow calls orb.delete on the object ...
                    self.sys_tree.source_model.removeRow(pos, row_parent)
                # resize dashboard columns if necessary
                self.refresh_dashboard()
            elif cname == 'RoleAssignment':
                if obj.assigned_to.oid == self.user.oid:
                    # TODO: if removed role assignment was the last one for
                    # this user on the project, switch to SANDBOX project
                    html = '<h3>Your role:</h3>'
                    html += '<p><b><font color="green">{}</font></b>'.format(
                                                        obj.assigned_role.id)
                    html += ' in <b><font color="green">{}</font>'.format(
                                    getattr(obj.role_assignment_context, 'id',
                                            'global context'))
                    html += '<br> has been removed.</b></p>'
                    self.w = NotificationDialog(html, parent=self)
                    self.w.show()
                orb.delete([obj])
            else:
                orb.delete([obj])
            self.log('  - object deleted.')
        else:
            self.log('  oid not found in local db; ignoring.')

    def on_save_object(self):
        """
        Save a generated "non-public" (cloaked) test object to the repo.  NOTE:
        this function will only succeed of the client has logged in as one of
        the test users (steve, buckaroo, zaphod).
        """
        new_oid = str(uuid4())
        self.test_oid = new_oid
        suffix = new_oid[0:5]
        ptype = product_types[random.randint(0, len(product_types) - 1)]
        new_id = 'TEST_' + ptype['id'][0:5] + '_' + suffix
        new_name = str(ptype['name']) + ' ' + str(suffix)
        now = dtstamp()
        for pid in test_parms:
            add_parameter(new_oid, pid)
        # gen_test_pvals(obj_parms)
        obj = clone('HardwareProduct', oid=new_oid, id=new_id,
                    name=new_name, creator=self.user, public=False,
                    owner=orb.get('H2G2'), create_datetime=now,
                    modifier=self.user, mod_datetime=now,
                    version='1', iteration=0, version_sequence=0,
                    product_type=orb.get(ptype['oid']))
        serialized_objs = serialize(orb, [obj])
        for so in serialized_objs:
            if so['oid'] == new_oid:
                serialized_obj = so
        self.log('* calling rpc "vger.save()" with serialized object:')
        self.log('  {}'.format(str(serialized_obj)))
        self.last_saved_obj = serialized_obj
        if self.system_level_obj:
            self.add_acu_button.setVisible(True)
        else:
            self.add_psu_button.setVisible(True)
        rpc = message_bus.session.call('vger.save', [serialized_obj])
        rpc.addCallback(self.on_vger_save_result)
        rpc.addErrback(self.on_failure)

    def on_save_public_object(self):
        """
        Save a generated "public" (decloaked) test object to the repo.  NOTE:
        this function will only succeed of the client has logged in as one of
        the test users (steve, buckaroo, zaphod).
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
        serialized_obj = dict(_cname='HardwareProduct', oid=new_oid, id=new_id,
                              name=new_name, creator=self.user.oid,
                              owner='H2G2', create_datetime=now,
                              modifier=self.user.oid, mod_datetime=now,
                              public=True, version='1', iteration=0,
                              version_sequence=0, product_type=ptype['oid'],
                              parameters=obj_parms)
        self.log('* calling rpc "vger.save()" with serialized object:')
        self.log('  {}'.format(str(serialized_obj)))
        self.last_saved_obj = serialized_obj
        if self.system_level_obj:
            self.add_acu_button.setVisible(True)
        else:
            self.add_psu_button.setVisible(True)
        rpc = message_bus.session.call('vger.save', [serialized_obj])
        rpc.addCallback(self.on_save_result)
        rpc.addErrback(self.on_failure)

    def on_save_result(self, stuff):
        self.log('* result received from rpc "vger.save":  %s' % str(stuff))

    def on_null_result(self):
        self.log('* no result expected.')

    def on_add_psu(self):
        if self.last_saved_obj:
            self.log('* Adding a ProjectSystemUsage for system {} ...'.format(
                                                    self.last_saved_obj['id']))
        else:
            self.log("* Can't add a PSU -- haven't saved any objects yet.")
            return
        new_oid = str(uuid4())
        new_id = 'psu-H2G2-' + self.last_saved_obj['id']
        new_name = 'Test ProjectSystemUsage ' + str(new_id)
        now = str(dtstamp())
        psu = dict(_cname='ProjectSystemUsage', oid=new_oid, id=new_id,
                   name=new_name, create_datetime=now, mod_datetime=now,
                   creator=self.user.oid, modifier=self.user.oid,
                   project='H2G2', system=self.last_saved_obj['oid'])
        self.system_level_obj = self.last_saved_obj
        self.last_saved_obj = None
        self.cloaked = []
        self.cloaked_list.clear()
        self.add_psu_button.setVisible(False)
        rpc = message_bus.session.call('vger.save', [psu])
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
        new_name = 'Test Acu ' + str(new_id)
        now = str(dtstamp())
        acu = dict(_cname='Acu', oid=new_oid, id=new_id,
                   name=new_name, create_datetime=now, mod_datetime=now,
                   creator=self.user.oid, modifier=self.user.oid,
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
        rpc = message_bus.session.call('vger.save', [acu])
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
            rpc = message_bus.session.call('vger.save', [acu])
            rpc.addCallback(self.on_save_result)
            rpc.addErrback(self.on_failure)
        else:
            self.log("  no acu found -- can't remove.")
            return

    def on_get_object(self):
        self.log('* calling rpc "vger.get_object()" ...')
        rpc = message_bus.session.call('vger.get_object', 'H2G2')
        rpc.addCallback(self.on_get_object_result)
        rpc.addErrback(self.on_failure)

    def on_sync_project(self, data=None):
        """
        Function to call rpc 'vger.sync_project'.  Note that the "data"
        argument is a dummy that is required when using this as a callback
        """
        self.log('* calling rpc vger.sync_project({})'.format('H2G2'))
        rpc = message_bus.session.call('vger.sync_project', 'H2G2', {})
        rpc.addCallback(self.on_sync_project_result)
        rpc.addErrback(self.on_failure)

    def on_sync_project_result(self, data):
        """
        Callback function to process the result of `vger.sync_project`.

        The server response is a list of lists:
            [0]:  server objects with later mod_datetime(s) or whose oids were
                  not in the submitted list of oids
            [1]:  oids of server objects with the same mod_datetime(s)
            [2]:  oids of server objects with earlier mod_datetime(s),
            [3]:  oids sent that were not found on the server

        Args:
            data:  response from the server

        Keyword Args:
            project_sync (bool): called from a project sync
            user_objs_sync (bool): called from the result of a user created
                objects sync

        Return:
            deferred:  result of `vger.save` rpc
        """
        sobjs, same_dts, to_update, local_only = data
        self.log('* vger.sync_project result received: {} objects.'.format(
                                                                len(sobjs)))
        self.log('  - deserializing ...')
        deserialize(orb, sobjs)
        self.log('    done.')

    def on_result(self, stuff):
        self.log('* result received:  %s' % str(stuff))

    def on_get_object_result(self, stuff):
        self.log('* result of get_object() received:')
        self.log('  {} serialized objects:'.format(len(stuff)))
        self.log('  {}'.format(pprint.pformat(stuff)))
        for so in stuff:
            if str(so['_cname']) == 'HardwareProduct':
                self.log('  - HardwareProduct "{}"'.format(so['oid']))
        deserialize(orb, stuff)

    def logout(self):
        self.log('* logging out ...')
        message_bus.session.leave()

    def on_leave(self):
        self.log('  + session left.')
        message_bus.session.disconnect()
        if cert:
            self.login_button.setVisible(True)
        self.logout_button.setVisible(False)
        self.check_version_button.setVisible(False)
        self.ldap_search_button.setVisible(False)
        self.ldap_result_button.setVisible(False)
        self.save_object_button.setVisible(False)
        self.save_public_object_button.setVisible(False)
        self.add_psu_button.setVisible(False)
        self.get_object_button.setVisible(False)
        # self.sync_project_button.setVisible(False)
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
    parser.add_argument('--host', dest='host', type=str,
                        default='localhost',
                        help='the host to connect to [default: "localhost"]')
    parser.add_argument('--port', dest='port', type=int,
                        default=8080,
                        help='the port to connect to [default: 8080]')
    parser.add_argument('--crypto', dest='crypto', type=bool,
                        default=True,
                        help='use cryptosign (pubkey auth) [default: True]')
    options = parser.parse_args()
    app = QApplication(sys.argv)
    orb.start('junk_home', console=True, debug=True)
    # set project to oid 'H2G2' because ConOps will look it up and use it to
    # find spacecraft(s)
    state['project'] = 'H2G2'
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
    auth = "cryptosign"
    if not options.crypto:
        auth = "ticket"
    mainwindow = MainWindow(options.host, options.port, auth_method=auth,
                            reactor=reactor)
    print('MainWindow instantiated ...')
    print('  configured to connect to "{}"'.format(options.host))
    print('  on port {}'.format(options.port))
    print('  using "{}" authentication'.format(auth))
    mainwindow.show()
    reactor.runReturn()
    sys.exit(app.exec_())

