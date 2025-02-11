#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Message bus interface module to the pangalactic.vger repository service.
"""
import argparse, math, os, sys, time

# before importing any pyqt stuff, fix the import error ...
from pangalactic.node import fix_qt_import_error

from PyQt5.QtCore import QRectF, QSize, QTimer, Qt
from PyQt5.QtGui import QColor, QPainter, QPen, QPalette
from PyQt5.QtWidgets import qApp
from PyQt5.QtWidgets import (QApplication, QDialog, QDialogButtonBox,
                             QFormLayout, QHBoxLayout, QLabel, QMainWindow,
                             QMessageBox, QPushButton, QSizePolicy,
                             QVBoxLayout, QWidget)
from pydispatch import dispatcher


from twisted.internet._sslverify import OpenSSLCertificateAuthorities
from twisted.internet.ssl import CertificateOptions
from OpenSSL import crypto

# set to fastorb or uberorb
# import pangalactic.core.set_fastorb
import pangalactic.core.set_uberorb

from pangalactic.core                 import __version__
from pangalactic.core                 import orb
from pangalactic.core                 import state
# from pangalactic.core.parametrics     import set_dval
from pangalactic.core.serializers     import deserialize
# from pangalactic.core.utils.datetimes import dtstamp
from pangalactic.node.widgets         import LogWidget, ModeLabel
from pangalactic.node.message_bus     import PgxnMessageBus
from pangalactic.node.startup         import (setup_ref_db_and_version,
                                              setup_dirs_and_state)

message_bus = PgxnMessageBus()

@message_bus.signal('onjoined')
def onjoined():
    dispatcher.send(signal='onjoined')

@message_bus.signal('onleave')
def onleave():
    dispatcher.send(signal='onleave')

@message_bus.signal('ondisconnect')
def ondisconnect():
    dispatcher.send(signal='ondisconnect')


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
            delta = abs((self.nframe % 64) - math.ceil(diameter/2))
            alpha = 255 - math.ceil((delta * delta)/4) - diameter
            if alpha > 0:
                painter.setPen(QPen(QColor(0, math.ceil(diameter/2), 127,
                                           alpha), 3))
                painter.drawEllipse(QRectF(
                    -math.ceil(diameter/2.0), -math.ceil(diameter/2.0),
                    diameter, diameter))


class Main:
    """
    App for mbif.
    """
    def __init__(self, host, port, cert, reactor=None, gui=None, console=False,
                 output=None, parent=None):
        self.gui = gui
        self.console = console
        if gui:
            self.mainwindow = MainWindow(options.host, options.port,
                                         cert=options.cert,
                                         reactor=reactor)
            self.mainwindow.show()
        if console:
            self.log = print
        else:
            self.log = orb.log.debug
        self.host = host
        self.port = port
        self.cert = cert
        self.reactor = reactor
        if not gui:
            self.log(f'* host set to: {host}')
            self.log(f'* port set to: {port}')
            if options.cert:
                self.log('  using self-signed cert')
            self.output = output
            dispatcher.connect(self.on_joined, 'onjoined')
            dispatcher.connect(self.on_leave, 'onleave')
            dispatcher.connect(self.on_disconnect, 'ondisconnect')
            self.login()

    def on_joined(self):
        self.log('  + session joined')
        if self.gui and getattr(self, 'mainwindow', None):
            self.mainwindow.on_joined()
        else:
            # get userid from message_bus ("authid" of session details ...)
            authid = message_bus.session.details.authid
            self.log(f'    userid: "{authid}"')
            self.userid = authid
            self.log('* calling rpc vger.get_mode_defs()')
            rpc = message_bus.session.call('vger.get_mode_defs')
            rpc.addCallback(self.on_get_mode_defs_result)
            rpc.addErrback(self.on_failure)
            rpc.addCallback(self.logout)
            rpc.addErrback(self.on_logout_failure)

    def on_get_mode_defs_result(self, data):
        """
        Callback function to process the result of `vger.get_mode_defs`.

        Args:
            data:  response from the server, which is a tuple of (dts,
                mode_defz) in which dts is the last-modified datatime stamp of
                the mode_defz data and mode_defz is the mode_defz cache.
        """
        dts, self.mode_defz = data
        self.log('* vger.get_mode_defs data received ...')
        # self.log(f'* [0] {dts}')
        # self.log(f'* [1] {self.mode_defz}')
        # self.log(f'* {type(self.mode_defz)}')
        # self.log('    done.')
        proj_id = state.get('project')
        self.log(f'  specified project: {proj_id}')
        proj_dict = self.mode_defz.get(proj_id, {})
        p_peak = proj_dict.get('p_peak')
        p_average = proj_dict.get('p_average')
        if p_peak and p_average:
            self.log(f'  + p_peak = {p_peak}')
            self.log(f'  + p_average = {p_average}')
            if not self.console:
                if self.output:
                    with open(self.output, 'w') as f:
                        f.write(f'p_peak = {p_peak}\n'
                                f'p_average = {p_average}')
                else:
                    print(f'p_peak = {p_peak}')
                    print(f'p_average = {p_average}')
        else:
            self.log('p_peak and p_average not found in modes data.')
            if not self.console:
                print('p_peak and p_average not found in modes data.')

    def on_failure(self, f):
        self.log("* rpc failure: {}".format(f.getTraceback()))

    def on_logout_failure(self, f):
        self.log("* logout failure ignored.")

    def on_leave(self):
        self.log('  + mbus "onleave" signal received.')
        if self.gui and getattr(self, 'mainwindow', None):
            self.mainwindow.on_leave()
            from twisted.internet import reactor
            if reactor.threadpool is not None:
                reactor.threadpool.stop()
            qApp.quit()
        else:
            self.log('  + session left.')
            # message_bus.session.disconnect()
            # message_bus.session = None
            # from twisted.internet import reactor
            # if reactor.threadpool is not None:
                # reactor.threadpool.stop()

    def on_disconnect(self):
        self.log('  + mbus "ondisconnect" signal received.')

    def login(self):
        if self.cert:
            cert_fname = 'server_cert.pem'
            cert_path = cert_fname
            try:
                cert = crypto.load_certificate(
                        crypto.FILETYPE_PEM,
                        open(cert_path, 'r').read())
                tls_options = CertificateOptions(
                    trustRoot=OpenSSLCertificateAuthorities([cert]))
            except:
                message = 'Certificate not found or not readable ...\n'
                message += 'operating in local-only mode.'
                self.log(message)
                return
        else:
            self.log('  - no self-signed cert.')
            tls_options = CertificateOptions()
        self.log('* logging in using cryptosign auth ...')
        key_path = 'private.key'
        if os.path.exists(key_path):
            message_bus.set_key_path(key_path)
        else:
            message = f'Key file <{key_path}> not found ...\n'
            message += 'operating in local-only mode.'
            self.log(message)
        message_bus.run('wss://{}:{}/ws'.format(self.host, self.port),
                        auth_method='cryptosign',
                        realm='pangalactic-services',
                        start_reactor=False, ssl=tls_options)

    def logout(self, data=None):
        self.log('* logging out ...')
        message_bus.session.leave()
        message_bus.session = None
        self.reactor.stop()
        sys.exit()
        # NOTE: the order of these incantations is important ...
        # threadpool.stop() must be done *before* reactor.stop()
        # or it will raise an AlreadyQuit exception
        # if self.reactor:
            # try:
                # if self.reactor.threadpool is not None:
                    # self.reactor.threadpool.stop()
                # if self.reactor.running:
                    # self.reactor.stop()
                # sys.exit()
            # except:
                # try:
                    # if self.reactor.running:
                        # self.reactor.callFromThread(self.reactor.stop)
                    # sys.exit()
                # except:
                    # sys.exit()
        # else:
            # sys.exit()

class MainWindow(QMainWindow):
    MOD_COUNT = 0

    def __init__(self, host, port, cert, reactor=None, parent=None):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.cert = cert
        self.reactor = reactor
        self.create_main_frame()
        self.log(f'* host set to: {host}')
        self.log(f'* port set to: {port}')
        self.setGeometry(100, 100, 1000, 800)
        self.create_timer()
        dispatcher.connect(self.on_joined, 'onjoined')
        dispatcher.connect(self.on_leave, 'onleave')
        dispatcher.connect(self.on_disconnect, 'ondisconnect')

    def on_pubsub_msg(self, msg):
        """
        Handle pubsub messages.

        Args:
            msg (tuple): the message, a tuple of (subject, content)
        """
        for item in msg.items():
            subject, content = item
            if subject not in ['parameter set', 'data element set']:
                self.log(f'*** received pubsub msg "{subject}" ...')
                self.log("       subject: {}".format(subject))
                self.log("       content: {}".format(content))
            obj_id = '[unknown]'
            # base text
            text = "remote {}: ".format(subject)
            if subject in ['new', 'decloaked']:
                # NOTE: content of msg changed in version 2.2.dev8
                # -- it is now a list of serialized objects
                n = len(content)
                text += f'received {n} new or decloaked objects'
            elif subject == 'modified':
                # NOTE: content of 'modified' msg changed in version 2.2.dev8
                # -- it is now a list of serialized objects
                n = len(content)
                text += f"received {n} modified objects"
                if n:
                    objs = deserialize(orb, content)
                    for obj in objs:
                        if isinstance(obj, orb.classes['Product']):
                            pt = getattr(obj.product_type, 'name',
                                         'unknown type')
                            text += "{} ({}) [{}]".format(obj_id, obj.name, pt)
                        elif isinstance(obj, orb.classes['Acu']):
                            pth = getattr(obj.product_type_hint, 'name',
                                          'unknown type')
                            text += "{} [{}]".format(obj_id, pth)
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
            elif subject == 'parameter set':
                oid, pid, value, units, mod_datetime = content
            elif subject == 'data element set':
                oid, deid, value, mod_datetime = content
                if deid == 'cold_units':
                    self.log(f'*** pubsub msg "{subject}" ...')
                    self.log(f'    oid: "{oid}"')
                    self.log(f'    deid: "{deid}", value: {value}')
            w = NotificationDialog(text, parent=self)
            w.setWidth(200)
            w.show()

    def create_main_frame(self):
        self.circle_widget = CircleWidget()
        self.login_button = QPushButton('Log in')
        self.login_button.clicked.connect(self.login)
        self.logout_button = QPushButton('Log out')
        self.logout_button.setVisible(False)
        self.logout_button.clicked.connect(self.logout)
        self.role_label = ModeLabel('')
        self.role_label.setVisible(False)
        self.log_widget = LogWidget()
        vbox = QVBoxLayout()
        vbox.addWidget(self.role_label, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.login_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.logout_button, alignment=Qt.AlignVCenter)
        vbox.addWidget(self.circle_widget)
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
        self.log('* login()')
        if self.cert:
            cert_fname = 'server_cert.pem'
            cert_path = cert_fname
            try:
                cert = crypto.load_certificate(
                        crypto.FILETYPE_PEM,
                        open(cert_path, 'r').read())
                tls_options = CertificateOptions(
                    trustRoot=OpenSSLCertificateAuthorities([cert]))
            except:
                message = 'Certificate not found or not readable ...\n'
                message += 'operating in local-only mode.'
                popup = QMessageBox(QMessageBox.Warning,
                                    "No certificate", message,
                                    QMessageBox.Ok, self)
                popup.show()
                return
        else:
            self.log('  - no self-signed cert.')
            tls_options = CertificateOptions()
        self.log('* logging in using cryptosign auth ...')
        key_path = 'private.key'
        if os.path.exists(key_path):
            message_bus.set_key_path(key_path)
        else:
            message = f'Key file <{key_path}> not found ...\n'
            message += 'operating in local-only mode.'
            popup = QMessageBox(QMessageBox.Warning,
                                "No certificate", message,
                                QMessageBox.Ok, self)
            popup.show()
        message_bus.run('wss://{}:{}/ws'.format(self.host, self.port),
                        auth_method='cryptosign',
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
        self.log('  - syncing project H2G2 ...')
        self.on_sync_project()

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
            [4]:  all oids in the server's "deleted" cache
            [5]:  parameter data for all project-owned objects
            [6]:  data element data for all project-owned objects

        Args:
            data:  response from the server

        Keyword Args:
            project_sync (bool): called from a project sync
            user_objs_sync (bool): called from the result of a user created
                objects sync

        Return:
            deferred:  result of `vger.save` rpc
        """
        (sobjs, same_dts, to_update, local_only, deleted_oids,
         parm_data, de_data) = data
        self.log('* vger.sync_project result received: {} objects.'.format(
                                                                len(sobjs)))
        self.log('  - deserializing ...')
        deserialize(orb, sobjs)
        self.log('    done.')

    def on_failure(self, f):
        self.log("* rpc failure: {}".format(f.getTraceback()))

    def logout(self):
        self.log('* logging out ...')
        message_bus.session.leave()

    def on_leave(self):
        self.log('  + session left.')
        message_bus.session.disconnect()
        self.login_button.setVisible(True)
        self.logout_button.setVisible(False)
        self.role_label.setText('')
        self.role_label.setVisible(False)
        message_bus.session = None

    def on_disconnect(self):
        self.log('  + mbus "ondisconnect" signal received.')

    def log(self, msg, with_tds=False):
        timestamp = ''
        if with_tds:
            timestamp = '[%010.3f]' % time.process_time() + ' '
        self.log_widget.append(timestamp + str(msg))

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
    parser.add_argument('--project', dest='project', type=str,
                        default='H2G2',
                        help='project id [default: "H2G2"]')
    parser.add_argument('--home', dest='home', action="store_true",
                        help='directory for storage [default: mbif_home]')
    parser.add_argument('--out', dest='output', type=str,
                        help='name of output file')
    parser.add_argument('--cert', dest='cert', action="store_true",
                        help='use self-signed cert [default: no]')
    parser.add_argument('--gui', dest='gui', action="store_true",
                        help='bring up the GUI [default: no]')
    parser.add_argument('--console', dest='console', action="store_true",
                        help='send log msgs to stdout [default: no]')
    options = parser.parse_args()
    if options.gui:
        app = QApplication(sys.argv)
    if not options.home:
        home = os.path.join(os.getcwd(), 'mbif_home')
    if not os.path.exists(home):
        os.makedirs(home, mode=0o755)
    this_version = __version__
    setup_ref_db_and_version(home, this_version)
    orb.start(home, console=options.console, debug=True)
    setup_dirs_and_state()
    project = options.project
    state['project'] = project
    if options.console:
        print('app created')
    if options.gui:
        try:
            import qt5reactor
        except ImportError:
            # Maybe qt5reactor is placed inside twisted.internet in site-packages?
            from twisted.internet import qt5reactor
        qt5reactor.install()
    from twisted.internet import reactor
    main = Main(options.host, options.port, gui=options.gui,
                console=options.console, cert=options.cert,
                output=options.output, reactor=reactor)
    if options.gui:
        reactor.runReturn()
        sys.exit(app.exec_())
    else:
        reactor.run()

