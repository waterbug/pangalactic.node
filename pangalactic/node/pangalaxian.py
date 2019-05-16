#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Pangalaxian (the PanGalactic GUI client) main window
"""
from __future__ import division
from future import standard_library
standard_library.install_aliases()
from builtins import str
from builtins import range
import argparse, atexit, os, shutil, six, sys, traceback
import urllib.parse, urllib.request, urllib.parse, urllib.error
from collections import OrderedDict

from binaryornot.check import is_binary

# Louie (formerly known as PyDispatcher)
from louie import dispatcher

# ruamel_yaml
import ruamel_yaml as yaml

from twisted.internet.defer import DeferredList
from twisted.internet._sslverify import OpenSSLCertificateAuthorities
from twisted.internet.ssl import CertificateOptions
from OpenSSL import crypto

# pyqt
from PyQt5 import QtGui, QtWidgets
from PyQt5.QtCore import Qt, QModelIndex, QPoint, QVariant

# pangalactic
from pangalactic.core                 import __version__
from pangalactic.core                 import diagramz
from pangalactic.core                 import config, write_config
from pangalactic.core                 import prefs, write_prefs
from pangalactic.core                 import state, write_state
from pangalactic.core                 import trash, write_trash
from pangalactic.core.log             import get_loggers
from pangalactic.core.meta            import DESERIALIZATION_ORDER
from pangalactic.core.parametrics     import node_count
from pangalactic.core.refdata         import ref_pd_oids
from pangalactic.core.serializers     import deserialize, serialize
from pangalactic.core.test.utils      import (create_test_project,
                                              create_test_users)
from pangalactic.core.uberorb         import orb
from pangalactic.core.utils.meta      import (asciify,
                                              uncook_datetime)
from pangalactic.core.utils.datetimes import dtstamp, date2str
from pangalactic.core.utils.reports   import write_mel_xlsx
from pangalactic.node.admin           import AdminDialog
from pangalactic.node.buttons         import ButtonLabel, MenuButton
from pangalactic.node.dashboards      import SystemDashboard
from pangalactic.node.dialogs         import (CloakingDialog,
                                              # CondaDialog, ## deprecated
                                              LoginDialog,
                                              # CircleWidget,
                                              # NotificationDialog,
                                              ObjectSelectionDialog,
                                              # OptionNotification,
                                              PrefsDialog, Viewer3DDialog)
# from pangalactic.node.filters         import FilterDialog
from pangalactic.node.helpwidget      import HelpWidget
from pangalactic.node.libraries       import LibraryDialog, LibraryListWidget
from pangalactic.node.message_bus     import PgxnMessageBus
from pangalactic.node.modeler         import ModelWindow, ProductInfoPanel
from pangalactic.node.pgxnobject      import PgxnObject
from pangalactic.node.startup         import setup_dirs_and_state
from pangalactic.node.systemtree      import SystemTreeView
from pangalactic.node.tablemodels     import ODTableModel, NumericSortModel
# MatrixWidget is only used in compare_items(), which is temporarily removed
# from pangalactic.node.tableviews  import MatrixWidget
from pangalactic.node.tableviews      import ObjectTableView
from pangalactic.node.utils           import clone
from pangalactic.node.widgets         import (AutosizingListWidget,
                                              ModeLabel, PlaceHolder)
from pangalactic.node.wizards         import (NewProductWizard,
                                              DataImportWizard,
                                              wizard_state)
from pangalactic.node.reqmanager      import RequirementManager
from pangalactic.node.reqwizards      import ReqWizard, req_wizard_state
from pangalactic.node.splash          import SplashScreen

message_bus = PgxnMessageBus()

@message_bus.signal('onjoined')
def onjoined():
    dispatcher.send(signal='onjoined')

@message_bus.signal('onleave')
def onleave():
    dispatcher.send(signal='onleave')


class Main(QtWidgets.QMainWindow):
    """
    Main window of the 'pangalaxian' client gui.

    Attributes:
        mode (str):  name of current mode
            (persistent in the `state` module)
        project (Project):  currently selected project
            (its oid is persisted as `project` in the `state` dict)
        projects (list of Project):  current Projects in db
            (a read-only property linked to the local db)
        dataset (str):  name of currently selected dataset
            (persistent in the `state` module)
        datasets (list of str):  names of currently stored datasets
            (persistent in the `state` module)
        library_widget (LibraryListWidget):  a panel widget containing library
            views for specified classes and a selector (combo box)
        adminserv (bool):  True if admin service is to be used (default: False)
        app_version (str):  version of calling app (if any)
        reactor (qt5reactor):  twisted event loop
        roles (list of dicts):  actually, role assignments -- a list of dicts
            of the form {org oid : role name}
    """
    # enumeration of modes
    modes = ['system', 'component', 'db', 'data']

    def __init__(self, home='', test_data=None, width=None, height=None,
                 use_tls=True, console=False, debug=False, reactor=None,
                 adminserv=False, app_version=None):
        """
        Initialize main window.

        Keyword Args:
            home (str):       path to home directory
            test_data (list): list of serialized test objects (dicts)
            width (int):      width of main window (default: screen w - 300)
            height (int):     height of main window (default: screen h - 200)
            use_tls (bool):   use tls to connect to message bus
            console (bool):   if True: send log messages to stdout
                                       (*and* log file)
                              else: send stdout and stderr to the logger
            debug (bool):     set log level to DEBUG
        """
        super(Main, self).__init__(parent=None)
        ###################################################
        self.splash_msg = ''
        self.add_splash_msg('Starting ...')
        self.reactor = reactor
        self.use_tls = use_tls
        self.adminserv = adminserv
        self.app_version = app_version
        self.sys_tree_rebuilt = False
        self.dashboard_rebuilt = False
        # dict for states obtained from self.saveState() -- used for saving the
        # window state when switching between modes
        self.main_states = {}
        state['connected'] = False
        if not state.get('admin_of'):
            state['admin_of'] = []
        if not state.get('assigned_roles'):
            state['assigned_roles'] = {}
        if not state.get('disabled'):
            state['disabled'] = False
        # start up the orb and do some orb stuff, including setting the home
        # directory and related directories (added to state)
        orb.start(home=home, console=console, debug=debug)
        self.add_splash_msg('... database initialized ...')
        # orb loads reference data when it starts up, which includes parameter
        # definitions
        setup_dirs_and_state()
        self.get_or_create_local_user()
        self.app_test_data = test_data
        self.start_logging(console=console, debug=debug)
        self.add_splash_msg('... logging started ...')
        # NOTES ON `config` and `state`:
        # * config vars can be modified by the user locally (in the home dir),
        #   so the config file contents will override the app settings
        # * state vars are intended to be controlled by the app, so the file
        #   contents are always be overridden by any current app state vars
        # if not config.get('logo'):
            # config['logo'] = 'pangalactic_logo.png'
        self.logo = os.path.join(orb.image_dir, config.get('logo'))
        self.tall_logo = os.path.join(orb.image_dir, config['tall_logo'])
        self.auto_update = not config.get('no_auto_update', False)
        state['last_path'] = ""
        # set path to server cert
        self.cert_path = os.path.join(orb.home, 'server_cert.pem')
        if os.path.exists(self.cert_path):
            orb.log.info('    server cert found.')
        else:
            orb.log.info('    server cert NOT found.')
        # self.mode_widgets is a mapping from modes (see below) to the widgets
        # that are visible in each mode
        self.mode_widgets = dict((mode, set()) for mode in self.modes)
        self.mode_widgets['all'] = set()  # for actions visible in all modes
        # NOTE: the following function calls are *very* order-dependent!
        self._create_actions()
        orb.log.info('*** projects:  %s' % str([p.id for p in self.projects]))
        self.add_splash_msg('... projects identified ...')
        screen_resolution = QtWidgets.QApplication.desktop().screenGeometry()
        default_width = min(screen_resolution.width() - 300, 900)
        default_height = min(screen_resolution.height() - 200, 400)
        width = state.get('width') or default_width
        height = state.get('height') or default_height
        self._init_ui(width, height)
        state['width'] = width
        state['height'] = height
        # self.create_timer()
        # register various signals ...
        dispatcher.connect(self.on_new_object_signal, 'new object')
        dispatcher.connect(self.on_mod_object_signal, 'modified object')
        dispatcher.connect(self.on_new_project_signal, 'new project')
        dispatcher.connect(self.refresh_tree_and_dashboard, 'dashboard mod')
        dispatcher.connect(self.on_deleted_object_signal, 'deleted object')
        dispatcher.connect(self.get_cloaking_status, 'cloaking')
        dispatcher.connect(self.decloak, 'decloaking')
        dispatcher.connect(self.on_remote_decloaked_signal,
                                                    'remote: decloaked')
        dispatcher.connect(self.on_remote_modified_signal,
                                                    'remote: modified')
        dispatcher.connect(self.on_remote_deleted_signal,
                                                    'remote: deleted')
        dispatcher.connect(self.on_set_current_project_signal,
                                                   'set current project')
        dispatcher.connect(self.set_product, 'drop on product info')
        # connect dispatcher signals for message bus events
        dispatcher.connect(self.on_mbus_joined, 'onjoined')
        dispatcher.connect(self.on_mbus_leave, 'onleave')
        # 'set current product' only affects 'component mode' (the "product
        # modeler interface", so just call that)
        dispatcher.connect(self.set_product_modeler_interface,
                           'set current product')
        # use preferred mode, else state, else default mode (system)
        mode = prefs.get('mode') or state.get('mode') or 'system'
        # NOTE:  to set mode, use self.[mode]_action.trigger() --
        # the left dock widgets are created by these actions
        self.add_splash_msg('... configuring interface ...')
        if mode == 'component':
            self.component_mode_action.trigger()
        elif mode == 'system':
            self.system_mode_action.trigger()
        elif mode == 'db':
            self.db_mode_action.trigger()
        else:
            self.data_mode_action.trigger()

    def add_splash_msg(self, msg):
        self.splash_msg += msg + '\n'
        dispatcher.send('splash message', message=self.splash_msg)

    def get_or_create_local_user(self):
        """
        Get or create a Person object to represent the local user.
        """
        local_user = orb.get(state.get('local_user_oid', 'me'))
        if local_user:
            self.local_user = local_user
            # oid should be bytes (str)
        else:
            orb.startup_msg = '* creating local user "me" object ...'
            local_user = clone('Person')
            local_user.oid = 'me'
            local_user.id = 'me'
            local_user.name = 'Me'
            orb.save([local_user])
            self.local_user = local_user
        state['local_user_oid'] = str(self.local_user.oid)

    def connect_to_bus(self):
        """
        Connect to the message bus (crossbar server).
        """
        orb.log.info('* connect_to_bus() ...')
        self.statusbar.showMessage('connecting to message bus ...')
        # TODO:  add a remote url configuration item
        if self.connect_to_bus_action.isChecked():
            login_dlg = LoginDialog(userid=state.get('userid', ''),
                                    parent=self)
            if login_dlg.exec_() == QtWidgets.QDialog.Accepted:
                state['userid'] = asciify(login_dlg.userid)
                message_bus.set_authid(login_dlg.userid)
                message_bus.set_passwd(login_dlg.passwd)
                host = config.get('host', 'localhost')
                port = config.get('port', '8080')
                tls_options = None
                if self.use_tls:
                    if self.cert_path:
                        orb.log.info('  - using tls ...')
                        cert = crypto.load_certificate(
                                crypto.FILETYPE_PEM,
                                six.u(open(self.cert_path, 'r').read()))
                        tls_options = CertificateOptions(
                            trustRoot=OpenSSLCertificateAuthorities([cert]))
                        url = u'wss://{}:{}/ws'.format(host, port)
                    else:
                        orb.log.info('  - no server cert; cannot use tls.')
                        return
                else:
                    url = u'ws://{}:{}/ws'.format(host, port)
                orb.log.info('  logging in with userid "{}"'.format(
                                                            login_dlg.userid))
                orb.log.info('  to url "{}"'.format(url))
                message_bus.run(url, realm=None, start_reactor=False,
                                ssl=tls_options)
            else:
                # uncheck button if login dialog is cancelled
                self.connect_to_bus_action.setChecked(False)
                self.connect_to_bus_action.setToolTip(
                                                'Connect to the message bus')
        else:
            if state['connected']:
                orb.log.info('* disconnecting from message bus ...')
                message_bus.session.leave()
            else:
                orb.log.info('* already disconnected from message bus.')
            self.connect_to_bus_action.setToolTip('Connect to the message bus')

    def on_mbus_joined(self):
        orb.log.info('* on_mbus_joined:  message bus session joined.')
        state['connected'] = True
        self.statusbar.showMessage('connected to message bus.')
        self.connect_to_bus_action.setToolTip(
                                        'Disconnect from the message bus')
        self.role_label.setText('online - syncing data, please wait ...')
        self.net_status.setPixmap(self.online_icon)
        self.net_status.setToolTip('connected')
        # set 'synced' state to False (informs check_version whether to run
        # sync_with_services())
        state['synced'] = False
        self.sync_with_services()

    def sync_with_services(self):
        state['synced'] = True
        if self.adminserv:
            proc = config.get('admin_get_roles_rpc')
            args = []
            kw = {'no_filter': True}
        else:
            proc = u'vger.get_role_assignments'
            args = [state['userid']]
            kw = {'no_filter': True}
        orb.log.info('* calling rpc "{}"'.format(proc))
        orb.log.info('  with args: "{}"'.format(str(args)))
        orb.log.info('       kw: "{}"'.format(str(kw)))
        rpc = message_bus.session.call(proc, *args, **kw)
        rpc.addCallback(self.on_get_admin_result)
        rpc.addErrback(self.on_failure)
        rpc.addCallback(self.subscribe_to_mbus_channels)
        rpc.addErrback(self.on_failure)
        rpc.addCallback(self.sync_parameter_definitions)
        rpc.addErrback(self.on_failure)
        rpc.addCallback(self.on_sync_result)
        rpc.addErrback(self.on_failure)
        # sync_user_created_objs_to_repo() requires callback on_sync_result()
        rpc.addCallback(self.sync_user_created_objs_to_repo)
        rpc.addErrback(self.on_failure)
        rpc.addCallback(self.on_user_objs_sync_result)
        rpc.addErrback(self.on_failure)
        # sync_library_objs() requires callback on_sync_result()
        rpc.addCallback(self.sync_library_objs)
        rpc.addErrback(self.on_failure)
        rpc.addCallback(self.on_sync_library_result)
        rpc.addErrback(self.on_failure)
        # sync_projects_with_roles() does not require callback on_sync_result()
        rpc.addCallback(self.sync_projects_with_roles)
        rpc.addErrback(self.on_failure)
        # sync_current_project() requires callback on_project_sync_result()
        rpc.addCallback(self.sync_current_project)
        rpc.addErrback(self.on_failure)
        rpc.addCallback(self.on_project_sync_result)
        rpc.addCallback(self.on_result)
        rpc.addErrback(self.on_failure)

    def on_get_admin_result(self, data):
        """
        Handle result of the rpc that got our Person object and role
        assignments.  If the 'adminserv' option is True, the admin service is
        called using the rpc 'omb.state.query'; if False (for use in
        testing), the 'vger' service is called using the rpc
        'vger.get_role_assignments'.  Because the 'no_filter' keyword arg is
        used, the returned data includes the full serialized objects, and has
        the format:

            {u'organizations': [serialized Org objects],
             u'users': [serialized Person objects],
             u'roles': [serialized Role objects],
             u'roleAssignments': [serialized RoleAssignment objects]}

        If the 'no_filter' keyword arg is NOT used, these abbreviated
        dictionary formats will be returned:

            {u'organizations': [{oid, id, name, description,
                                 parent_organization}, ...],
             u'users': [{oid, id, name}, ...],
             u'roles': [{oid, name}, ...],
             u'roleAssignments': [{assigned_role, assigned_to,
                                   role_assignment_context}, ...]}
        """
        # TODO: cache all role assignments; update current role when local
        # project state is changed
        channels = []
        if data:
            if self.adminserv:
                log_msg = '* data from admin service:  %s' % str(data)
            else:
                # using vger to get role assignments
                # NOTE:  test objects must be loaded for this to work!
                log_msg = '* using vger admin service ...\n'
                log_msg += '  ... admin data:  %s' % str(data)
            orb.log.debug(log_msg)
            # add any new Roles from admin data
            deserialize(orb, data[u'roles'])
            # add any new Organizations from admin data
            deserialize(orb, data[u'organizations'])
            # find Person object returned in admin data 'users'
            users = deserialize(orb, data[u'users'])
            # delete any local RoleAssignments not in admin data
            local_ras_to_del = [ra for ra in orb.get_by_type('RoleAssignment')
                                if ra.oid not in
                                [new_ra['oid'] for new_ra in
                                 data[u'roleAssignments']]]
            if local_ras_to_del:
                oids = [ra.oid for ra in local_ras_to_del]
                orb.delete(local_ras_to_del)
                for oid in oids:
                    dispatcher.send('remote: deleted', content=oid)
            # add any new RoleAssignments from admin data
            deserialize(orb, data[u'roleAssignments'])
            persons_by_id = {u.id: u for u in users
                             if isinstance(u, orb.classes['Person'])}
            if persons_by_id:
                user_with_my_userid = persons_by_id.get(state['userid'])
                if user_with_my_userid:
                    self.local_user = user_with_my_userid
                    orb.log.info('* local user found in admin data: {}'.format(
                                                          self.local_user.oid))
                else:
                    orb.log.info('* person object for local user "{}" not '
                                 'found in data.'.format(state['userid']))
            else:
                orb.log.info('* no person objects found in admin data.')
            if str(state.get('local_user_oid')) == 'me':
                # current local user is 'me' -- replace ...
                orb.log.info('  setting new local user to {}'.format(
                                                        self.local_user.oid))
                state['local_user_oid'] = str(self.local_user.oid)
                me = orb.get('me')
                if me and me.created_objects:
                    orb.log.info('    updating {} local objects ...'.format(
                                  str(len(me.created_objects))))
                    for obj in me.created_objects:
                        obj.creator = self.local_user
                        obj.modifier = self.local_user
                        orb.save([obj])
                        dispatcher.send('modified object', obj=obj)
            else:
                orb.log.info('    login user matches local user.')

            # `state` keys for org/role/assignment data:
            #   * 'role_oids':
            #       a name-to-oid mapping for Role instances
            #   * 'admin_of':
            #       a list of org oids for which the user has the Administrator
            #       role
            #   * 'assigned_roles':
            #       maps org.oid to a list of role.name for the roles assigned
            #       to the user in that org

            # `ras_admin_serv` is role assignment data obtained from admin service
            # [note that all RA objects received from the admin service are
            # deserialized into the local repo ]
            ras_admin_serv = data[u'roleAssignments']
            if ras_admin_serv:
                orb.log.debug('    finding orgs in which we have a role ...')
                ra_org_oids = [ra.get(u'role_assignment_context')
                               for ra in ras_admin_serv
                               if ra.get(u'role_assignment_context')]
                orb.log.debug('    finding disabled_by_org ...')
                try:
                    disabled_by_org = [ra.get(u'role_assignment_context', 'global')
                                       for ra in ras_admin_serv
                                       if (ra[u'assigned_role'] ==
                                           u'pgefobjects.Role.Disabled')]
                except:
                    disabled_by_org = []
                orb.log.debug('    checking if we are globally disabled ...')
                if 'global' in disabled_by_org:
                    self.disabled = True
                roles = {str(r[u'oid']) : str(r[u'name'])
                         for r in data[u'roles']}
                state['role_oids'] = {str(r[u'name']) : str(r[u'oid'])
                                      for r in data[u'roles']}
                orgs = {str(o[u'oid']) : str(o[u'id'])
                        for o in data[u'organizations']
                        if o[u'oid'] in ra_org_oids}
                orb.log.debug('    finding assigned Admin roles ...')
                try:
                    state['admin_of'] = [str(ra.get(u'role_assignment_context',
                                                    'global'))
                                         for ra in ras_admin_serv
                                         if (ra[u'assigned_role'] ==
                                           u'pgefobjects:Role.Administrator')]
                except:
                    state['admin_of'] = []
                orb.log.debug('    finding other assigned roles ...')
                # NOTE: 'assigned_roles' is re-initialized here in case some
                # previously assigned roles have been removed
                state['assigned_roles'] = {}
                try:
                    for ra in ras_admin_serv:
                        if (str(ra[u'assigned_role'])
                            != 'pgefobjects:Role.Administrator'):
                            org_oid = str(ra.get(u'role_assignment_context',
                                                 'global'))
                            if org_oid in state['assigned_roles']:
                                if (str(roles[ra[u'assigned_role']])
                                    not in state['assigned_roles'][org_oid]):
                                    state['assigned_roles'][org_oid].append(
                                            str(roles[ra[u'assigned_role']]))
                            else:
                                state['assigned_roles'][
                                      org_oid] = [str(roles[
                                                        ra[u'assigned_role']])]
                    orb.log.debug('    - assigned roles found: {}'.format(
                                                str(state['assigned_roles'])))
                except:
                    orb.log.debug('    - no assigned roles found.')
                channels = [u'vger.channel.'+orgs[chan_oid]
                            for chan_oid in state['assigned_roles']
                            if chan_oid != 'global']
                orb.log.debug('    channels we will subscribe to: {}'.format(
                                                               str(channels)))
                if state['assigned_roles'] or state['admin_of']:
                    orb.log.info('  - role assignments found:')
                if state['assigned_roles']:
                    for ar_org_oid in state['assigned_roles']:
                        # don't die if there are 'global' roles, which may
                        # either have the `role_assignment_context` key omitted
                        # or if present, it may have a None value ...
                        orb.log.info('    {}: {}'.format(
                                 orgs.get(ar_org_oid, 'global') or 'global',
                                 str(state['assigned_roles'][ar_org_oid])))
                if state['admin_of']:
                    for adm_org_oid in state['admin_of']:
                        if adm_org_oid == 'global':
                            orb.log.info('    Global Administrator')
                        else:
                            orb.log.info('    {}: Administrator'.format(
                                          orgs[adm_org_oid]))
            else:
                orb.log.info('  - no role assignments found.')
            if self.project:
                if self.project.oid in state['assigned_roles']:
                    txt = u': '.join([self.project.id,
                              state['assigned_roles'][self.project.oid][0]])
                elif str(self.project.oid) == 'pgefobjects:SANDBOX':
                    txt = u'SANDBOX'
                else:
                    txt = u': '.join([self.project.id, '[local]'])
                self.role_label.setText(txt)
            else:
                self.role_label.setText('online [no project selected]')
        else:
            self.role_label.setText('online [no roles assigned]')
        channels.append(u'vger.channel.public')
        channels.append(u'omb.roleassignment')
        channels.append(u'omb.organizationlist')
        return channels

    def subscribe_to_mbus_channels(self, channels):
        # TODO: subscribe to channels for all our projects (as determined from
        # our role assignments)
        channels = channels or [u'vger.channel.public']
        orb.log.info('* attempting to subscribe to channels:  %s' % str(
                                                                    channels))
        subs = []
        for channel in channels:
            sub = message_bus.session.subscribe(self.on_pubsub_msg, channel)
            sub.addCallback(self.on_pubsub_success)
            sub.addErrback(self.on_pubsub_failure)
            subs.append(sub)
        return DeferredList(subs, consumeErrors=True)

    def on_pubsub_success(self, sub):
        orb.log.info("  - subscribed to: {}".format(str(sub.topic)))

    def on_pubsub_failure(self, f):
        orb.log.info("  - subscription failure: {}".format(f.getTraceback()))

    def sync_parameter_definitions(self, data):
        """
        Sync all ParameterDefinitions with the server.  If there are any local
        ParameterDefinition instances, this function assembles a list
        containing their [oid, mod_datetime] pairs and sends it to the server.
        The server response is a list of lists:

            [0]:  server objects with later mod_datetime(s)
            [1]:  oids of server objects with the same mod_datetime(s)
            [2]:  oids of server objects with earlier mod_datetime(s)
            [3]:  oids sent that were not found on the server

        Args:
            data:  parameter required for callback (ignored)

        Return:
            deferred: result of `vger.sync_parameter_definitions` rpc
        """
        orb.log.info('[pgxn] rpc: vger.sync_parameter_definitions()')
        self.statusbar.showMessage('syncing parameter definitions ...')
        # exclude refdata (already shared)
        pd_mod_dts = orb.get_mod_dts(cname='ParameterDefinition')
        data = {pd_oid : mod_dt for pd_oid, mod_dt in pd_mod_dts.items()
                if pd_oid not in ref_pd_oids}
        orb.log.info('       -> rpc: vger.sync_parameter_definitions()')
        return message_bus.session.call(u'vger.sync_parameter_definitions',
                                        data)

    def sync_user_created_objs_to_repo(self, data):
        """
        Sync all local objects created by the user to the repository.  This
        will save any new objects created since the last login along with any
        objects that exist in the repository but were modified since last login
        and will get any objects that were created by the local user that exist
        in the repository and are not in the user's 'trash'.  **NOTE**: this
        will only sync objects subclassed from `Modelable`, which is the class
        that introduces the `creator` attribute of which `created_objects` is
        the inverse.

        Args:
            data:  parameter required for callback (ignored)
        """
        orb.log.info('[pgxn] sync_user_created_objs_to_repo()')
        self.statusbar.showMessage('syncing locally created objects ...')
        oids = [o.oid for o in self.local_user.created_objects]
        data = orb.get_mod_dts(oids=oids)
        orb.log.info('       -> rpc: vger.sync_objects()')
        return message_bus.session.call(u'vger.sync_objects', data)

    def sync_library_objs(self, data):
        """
        Sync all library objects with the repository. This will synchronize the
        user's local collection of library objects with any `Modelable` objects
        to which the user has access in the repository (including "public"
        objects) that were created or modified since the last login.

        Args:
            data:  parameter required for callback (ignored)
        """
        # TODO:  Include all library classes (not just HardwareProduct)
        orb.log.info('[pgxn] sync_library_objs()')
        self.statusbar.showMessage('syncing library objects ...')
        # include the user's objects in `data`; it's faster and their oids will
        # come back in the set of oids to be ignored
        data = orb.get_mod_dts(cname='HardwareProduct')
        data.update(orb.get_mod_dts(cname='Template'))
        return message_bus.session.call(u'vger.sync_library_objects', data)

    def sync_projects_with_roles(self, data):
        """
        Get the project/org objects corresponding to the current roles assigned
        to the local user and add them to the local db.

        Args:
            data:  parameter required for callback (ignored)
        """
        orb.log.info('[pgxn] sync_projects_with_roles()')
        for org_oid in set(state['assigned_roles']).union(
                       set(state['admin_of'])):
            if org_oid and not orb.get(org_oid):
                rpc = message_bus.session.call(u'vger.get_object', org_oid)
                rpc.addCallback(self.on_rpc_get_object)
                rpc.addErrback(self.on_failure)
        return True

    def sync_current_project(self, data):
        """
        Sync all objects for the current project into the local db.  If there
        are any local project objects, this function internally assembles a
        list containing their [oid, mod_datetime] pairs and sends it to the
        server.  The server response is a list of lists:

            [0]:  server objects with later mod_datetime(s)
            [1]:  oids of server objects with the same mod_datetime(s)
            [2]:  oids of server objects with earlier mod_datetime(s),
            [3]:  oids sent that were not found on the server

        Args:
            data:  parameter required for callback (ignored)

        Return:
            deferred: result of `vger.sync_project` rpc
        """
        orb.log.info('[pgxn] sync_current_project()')
        proj_oid = state.get('project')
        project = orb.get(proj_oid)
        data = {}
        if (proj_oid != 'pgefobjects:SANDBOX') and project:
            orb.log.debug('       current project is: {}'.format(project.id))
            self.statusbar.showMessage('syncing project {} ...'.format(
                                                                 project.id))
            local_objs = orb.get_objects_for_project(project)
            if local_objs:
                for obj in local_objs:
                    dts = str(obj.mod_datetime)
                    data[obj.oid] = dts
        else:
            self.statusbar.showMessage('synced.')
        return message_bus.session.call(u'vger.sync_project', proj_oid, data)

    def on_user_objs_sync_result(self, data):
        self.on_sync_result(data, user_objs_sync=True)

    def on_project_sync_result(self, data):
        self.on_sync_result(data, project_sync=True)

    def on_sync_result(self, data, project_sync=False, user_objs_sync=False):
        """
        Callback function to process the result of the following rpcs:

            - `vger.sync_parameter_definitions` -- which is called by:
                + self.sync_parameter_definitions()

            - `vger.sync_objects` -- which is called by:
                + self.sync_user_created_objs_to_repo()

            - `vger.sync_project` -- which is called by:
                + self.sync_current_project()

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
        orb.log.info('[pgxn] on_sync_result()')
        orb.log.debug('       data: {}'.format(str(data)))
        sobjs, same_dts, to_update, local_only = data
        # TODO:  create a progress bar for this ...
        n = len(sobjs)
        if n:
            try:
                self.statusbar.showMessage(
                    'deserializing {} objects ...'.format(n))
                deserialize(orb, sobjs)
                if not project_sync:
                    # if new Parameter Definitions found, create icons
                    pd_oids = [so['oid'] for so in sobjs
                               if so['_cname'] == 'ParameterDefinition']
                    if pd_oids and hasattr(self, 'library_widget'):
                        self.library_widget.refresh(
                                                cname='ParameterDefinition')
            except:
                orb.log.info('      - deserialization failure')
                orb.log.info('        oids: {}'.format(
                             str([so.get('oid', 'no oid') for so in sobjs])))
        created_sos = []
        sobjs_to_save = serialize(orb, orb.get(oids=to_update))
        if local_only:
            orb.log.debug('       objects unknown to server found ...')
            # this will ignore objects in "trash", of course
            local_only_objs = orb.get(oids=local_only)
            created_objs = set()
            objs_to_delete = set()
            for o in local_only_objs:
                # TODO:  use 'get_perms' to determine permissions
                if hasattr(o, 'creator') and o.creator == self.local_user:
                    created_objs.add(o)
                elif (o.__class__.__name__ == 'ProjectSystemUsage' and
                    getattr(o.project, 'oid', None) == 'pgefobjects:SANDBOX'):
                    # NOTE:  SANDBOX PSUs are not synced
                    created_objs.add(o)
                else:
                    objs_to_delete.add(o)
            if objs_to_delete:
                orb.log.debug('       to be deleted: {}'.format(str([
                              o.oid for o in objs_to_delete])))
                orb.delete(objs_to_delete)
            # created_sos = serialize(orb, created_objs,
            #                         include_components=True)
            created_sos = serialize(orb, created_objs)
        if created_sos:
            sobjs_to_save += created_sos
            orb.log.debug('       to be saved in repo: {}'.format(str(
                          [sobj['oid'] for sobj in sobjs_to_save])))
        if project_sync:
            # if on_sync_result() was called from a project sync, update views
            # (which will update the 'role_label' with the project etc.)
            self._update_views()
        if user_objs_sync:
            state['synced_oids'] = [o.oid for o in
                                    self.local_user.created_objects]
        #######################################################################
        # NOTE: temp work-around for bug in syncing ParameterDefinitions and/or
        # ProductTypes ...
        # new_sobjs_to_save = sobjs_to_save[:]
        # sobjs_to_save = [so for so in new_sobjs_to_save
                         # if so['_cname'] not in ['ParameterDefinition',
                                                 # 'ProductType']]
        #######################################################################
        if sobjs_to_save:
            self.statusbar.showMessage('saving local objs to repo ...')
        else:
            self.statusbar.showMessage('synced.')
        return message_bus.session.call(u'vger.save', sobjs_to_save)

    def on_sync_library_result(self, data, project_sync=False):
        """
        Callback function to process the result of the
        `vger.sync_library_objects` rpc.  The server response is a list of
        lists:

            [0]:  server objects with later mod_datetime(s) or not found in the
                  local data sent with `sync_library_objects()`
                  -> add these to the local db
            [1]:  oids of server objects with the same mod_datetime(s)
                  -> ignore these
            [2]:  oids of server objects with earlier mod_datetime(s),
                  -> ignore these (*should* be empty!)
            [3]:  oids in the data sent with `sync_library_objects()` that were
                  not found on the server
                  -> delete these from the local db if they are either:
                     [a] not created by the local user
                     [b] created by the local user but are in 'trash'

        Args:
            data:  response from the server

        Return:
            deferred:  result of `vger.save` rpc
        """
        orb.log.info('[pgxn] on_sync_library_result()')
        orb.log.debug('       data: {}'.format(str(data)))
        update_needed = False
        sobjs, same_dts, to_ignore, local_only = data
        # TODO:  create a progress bar for this ...
        # deserialize the objects to be saved locally [1]
        if sobjs:
            # server objects that are either not in local db or have a later
            # mod_datetime than the corresponding local object ... so first
            # make sure they are not in our local trash ...
            not_trash = [so for so in sobjs if so.get('oid') not in trash]
            deserialize(orb, not_trash)
            update_needed = True
        # then collect any local objects that need to be saved to the repo ...
        sobjs_to_save = []
        if local_only:
            orb.log.debug('       objects unknown to server found ...')
            objs_to_delete = set(orb.get(oids=local_only))
            local_objs = set()
            for o in objs_to_delete:
                # TODO:  use 'get_perms' to determine permissions
                if (hasattr(o, 'creator') and o.creator == self.local_user
                    and o.oid not in list(trash.keys())):
                    objs_to_delete.remove(o)
                    local_objs.add(o)
                # NOTE: ProjectSystemUsages are not relevant to library sync
                # elif (o.__class__.__name__ == 'ProjectSystemUsage' and
                      # o.project.oid in state['admin_of']):
                    # objs_to_delete.remove(o)
                    # local_objs.add(o)
                else:
                    objs_to_delete.add(o)
            if objs_to_delete:
                orb.log.debug('       to be deleted: {}'.format(
                              ', '.join([o.oid for o in objs_to_delete])))
                orb.delete(objs_to_delete)
                update_needed = True
            if local_objs:
                # sobjs_to_save = serialize(orb, local_objs,
                                            # include_components=True)
                sobjs_to_save = serialize(orb, local_objs)
        if sobjs_to_save:
            orb.log.debug('       to be saved in repo: {}'.format(
                          ', '.join([sobj['oid'] for sobj in sobjs_to_save])))
        # if library objects have been added or deleted, call _update_views()
        if update_needed:
            self._update_views()
        return message_bus.session.call(u'vger.save', sobjs_to_save)

    def on_pubsub_msg(self, msg):
        for item in msg.items():
            subject, content = item
            orb.log.info("[pgxn] on_pubsub_msg")
            orb.log.info("       subject: {}".format(subject))
            orb.log.info("       content: {}".format(content))
            orb.log.info("       pop-up notification ...")
            # text = ('subject: {}<br>'.format(subject))
            obj_id = '[unknown]'
            if subject == u'decloaked':
                obj_oid, obj_id, actor_oid, actor_id = content
            elif subject == u'modified':
                obj_oid, obj_id, obj_mod_datetime = content
            elif subject == u'deleted':
                obj_oid = content
                obj = orb.get(obj_oid)
                if obj:
                    obj_id = obj.id
            elif subject == u'organization':
                obj_oid = content['oid']
                obj_id = content['id']
            self.statusbar.showMessage("remote {}: {}".format(subject, obj_id))
            # NOTE:  NotificationDialog BECOMES ANNOYING -- ACTIVATE ONLY FOR
            # DEBUGGING ... USE SELF.STATUSBAR FOR NORMAL OPERATIONS
            # text += '<table><tr>'
            # text += '<td><b><font color="green">object oid:</font></td>'
            # text += '<td>{}</td>'.format(obj_oid)
            # if obj_id:
                # text += '</tr><tr>'
                # text += '<td><b><font color="green">object id:</font></td>'
                # text += '<td>{}</td>'.format(obj_id)
            # text += '</tr></table>'
            # self.w = NotificationDialog(text, parent=self)
            # self.w.show()
            if subject == u'decloaked':
                dispatcher.send(signal="remote: decloaked", content=content)
            elif subject == u'modified':
                dispatcher.send(signal="remote: modified", content=content)
            elif subject == u'deleted':
                dispatcher.send(signal="remote: deleted", content=content)

    def get_cloaking_status(self, oid=''):
        """
        Get cloaking information on the specified object and display dialog
        with cloaking state and options to decloak.

        Keyword Args:
            obj (Identifiable):  object whose cloaking info is to be shown
        """
        orb.log.info('[pgxn] get_cloaking_status("{}")'.format(oid))
        orb.log.info('       (local "cloaking" signal received ...)')
        # TODO:  if not connected, show a warning to that effect ...
        if oid:
            rpc = message_bus.session.call(u'vger.get_cloaking_status', oid)
            rpc.addCallback(self.on_get_cloaking_status)
            rpc.addErrback(self.on_failure)

    def decloak(self, oid='', actor_oid=''):
        """
        Call 'vger.decloak' with the specified arguments, in response to a
        local 'decloaking' signal.

        Keyword Args:
            oid (str):  oid of the object to be decloaked
            actor_oid (str):  oid of the actor to which the object is to be
                decloaked
        """
        orb.log.info('[pgxn] local "decloaking" signal received:')
        orb.log.info('       decloak("{}")'.format(oid))
        # TODO:  if not connected, show a warning to that effect ...
        # NOTE:  currently only decloaks object to current project
        if not actor_oid:
            actor_oid = state.get('project')
            if not actor_oid:
                orb.log.info('  no current project; could not decloak.')
                return
            elif actor_oid == 'pgefobjects:SANDBOX':
                orb.log.info('       current project is SANDBOX;')
                orb.log.info('       cannot decloak to SANDBOX.')
                return
        if oid and actor_oid:
            orb.log.info('       sending vger.decloak("{}", "{}")'.format(oid,
                                                                    actor_oid))
            rpc = message_bus.session.call(u'vger.decloak', oid, actor_oid)
            rpc.addCallback(self.on_get_cloaking_status)
            rpc.addErrback(self.on_failure)

    def on_get_cloaking_status(self, result):
        """
        Display a dialog with the result of a request for cloaking status of an
        object.  The format of the result is a 3-tuple consisting of:

        (1) a list of the oids of any actors the object has been decloaked to
        (2) a status message (text)
        (3) the oid of the object whose cloaking status was returned
        """
        orb.log.info('[pgxn] get_cloaking_status() returned:')
        orb.log.info('       {}'.format(str(result)))
        decloak_button = True
        if result:
            actor_oids, msg, obj_oid = result
            obj = orb.get(obj_oid)
            if obj:
                actors = []
                # if 'public' is explicitly included, the object is public
                if 'public' in actor_oids:
                    actors = ['public']
                else:
                    for ao in actor_oids:
                        if ao:
                            actor = orb.get(ao)
                            if actor:
                                actors.append(actor)
                orb.log.info('       calling CloakingDialog() with:')
                orb.log.info('       - obj = {}'.format(obj.oid))
                orb.log.info('       - msg = {}'.format(msg))
                orb.log.info('       - actors = {}'.format(str(actors)))
                # if object has already been decloaked to the current project,
                # show the status dialog without the Decloak button
                if state.get('project') in actor_oids:
                    decloak_button = False
                # check whether this is a locally cloaked object that has just
                # been decloaked
                cloaked_oids = state.get('cloaked', [])
                if actors and (obj.oid in cloaked_oids):
                    # if just decloaked local object, update state['cloaked']
                    cloaked_oids.remove(obj.oid)
                    state['cloaked'] = cloaked_oids
                    # refresh the relevant views of the object
                    cname = obj.__class__.__name__
                    if hasattr(self, 'library_widget'):
                        self.library_widget.refresh(cname=cname)
                    if hasattr(self, 'sys_tree'):
                        self.update_object_in_trees(obj)
                dlg = CloakingDialog(obj, msg, actors,
                                     decloak_button=decloak_button,
                                     parent=self)
                if dlg.exec_():
                    pass
            else:
                # TODO:  handle failure ...
                pass
        else:
            # TODO:  handle failure ...
            pass

    def on_remote_decloaked_signal(self, content=None):
        """
        Call functions to update applicable widgets when a pub/sub message is
        received from the repository service indicating that a new object has
        been decloaked or an existing decloaked object has been modified.

        Keyword Args:
            content (tuple):  content of the pub/sub message, which has the
                form of a 4-tuple:  (obj_oid, obj_id, actor_oid, actor_id)
        """
        # TODO:  other actions will be needed ...
        orb.log.info('* "remote: decloaked" signal received ...')
        if not content:
            orb.log.debug(' - content was empty.')
            return
        try:
            obj_oid, obj_id, actor_oid, actor_id = content
        except:
            # handle the error (pop up a notification dialog)
            orb.log.debug('  - content could not be parsed:')
            orb.log.debug('    {}'.format(str(content)))
            return
        obj = orb.get(obj_oid)
        if obj:
            orb.log.info('  - decloaked object is already in local db.')
        else:
            # get object from repository ...
            orb.log.info('  - decloaked object unknown -- get from repo...')
            rpc = message_bus.session.call(u'vger.get_object', obj_oid,
                                           include_components=True)
            rpc.addCallback(self.on_rpc_get_object)
            rpc.addErrback(self.on_failure)

    def on_rpc_get_object(self, serialized_objects):
        orb.log.info("* on_rpc_get_object")
        orb.log.info("  got: {} serialized objects".format(
                                                    len(serialized_objects)))
        if not serialized_objects:
            orb.log.info('  result was empty!')
            return False
        objs = deserialize(orb, serialized_objects)
        rep = '\n  '.join([obj.name + " (" + obj.__class__.__name__ + ")"
                           for obj in objs])
        orb.log.info('  deserializes as:')
        orb.log.info('  {}'.format(str(rep)))
        for obj in objs:
            cname = obj.__class__.__name__
            if isinstance(obj, (orb.classes['Product'],
                                orb.classes['ParameterDefinition'])):
                # refresh library widgets ...
                orb.log.info('  updating libraries with: "{}"'.format(obj.id))
                if hasattr(self, 'library_widget'):
                    orb.log.info('  - refreshing library_widget')
                    self.library_widget.refresh(cname=cname)
            elif isinstance(obj, (orb.classes['Acu'],
                                  orb.classes['ProjectSystemUsage'])):
                if hasattr(self, 'sys_tree'):
                    orb.log.info('  updating trees with: "{}"'.format(obj.id))
                    # sys_tree_model = self.sys_tree.model()
                    sys_tree_model = self.sys_tree.source_model
                    if hasattr(obj, 'project'):
                        # NOTE:  SANDBOX PSUs are not synced
                        if (obj.project.oid == state.get('project') and
                            obj.project.oid != 'pgefobjects:SANDBOX'):
                            orb.log.info('  this is a ProjectSystemUsage for '
                                      'the current project ({}) ...'.format(
                                      state['project']))
                            orb.log.info('  its system is: "{}"'.format(
                                                                obj.system.id))
                            # Just adding a new system node did not work, so
                            # the whole tree is rebuilt (refreshed)
                            orb.log.info('  rebuilding tree ...')
                            self.refresh_tree_views()
                            # **********************************************
                            # DEACTIVATED stuff
                            # (below was an unsuccessful attempt to just add a
                            # system node to the tree ... abandoned for now --
                            # just rebuilding the tree.)
                            # **********************************************
                            # root_index = sys_tree_model.index(0, 0,
                                                              # QModelIndex())
                            # project_index = sys_tree_model.index(0, 0,
                                                                 # root_index)
                            # project_node = sys_tree_model.node_for_object(
                                              # obj.project, sys_tree_model.root)
                            # orb.log.info('  now try to add node ...')
                            # try:
                                # sys_tree_model.add_nodes(
                                    # [sys_tree_model.node_for_object(
                                        # obj.system, project_node, link=obj)],
                                    # parent=project_index)
                            # except Exception:
                                # orb.log.info(traceback.format_exc())
                            # orb.log.info('  dataChanged.emit()')
                            # sys_tree_model.dataChanged.emit(project_index,
                                                            # project_index)
                            # **********************************************
                        else:
                            orb.log.info('  new object is NOT a system for '
                                      'the current project ({}) ...'.format(
                                      state['project']))
                            orb.log.info('  no system node will be added.')
                    else:
                        orb.log.info('  this is an Acu ...')
                        orb.log.info('  - assembly:  {}'.format(
                                                            obj.assembly.id))
                        comp = obj.component
                        orb.log.info('  - component: {}'.format(comp.id))
                        idxs = self.sys_tree.object_indexes_in_tree(
                                                                obj.assembly)
                        orb.log.info('  the assembly occurs {} times'.format(
                                                                   len(idxs)))
                        orb.log.info('  in the system tree.')
                        if idxs:
                            orb.log.info('  adding component nodes ...')
                        for i, idx in enumerate(idxs):
                            try:
                                assembly_node = sys_tree_model.get_node(idx)
                                sys_tree_model.add_nodes(
                                    [sys_tree_model.node_for_object(
                                     comp, assembly_node, link=obj)],
                                    parent=idx)
                            except Exception:
                                orb.log.info(traceback.format_exc())
                    # resize dashboard columns if necessary
                    self.refresh_dashboard()
            if self.mode == 'db':
                orb.log.info('  updating db views with: "{}"'.format(obj.id))
                self.refresh_cname_list()
                self.set_object_table_for(cname)
        return True

    def on_mbus_leave(self):
        orb.log.info('* on_mbus_leave: message bus session left.')
        self.net_status.setPixmap(self.offline_icon)
        self.net_status.setToolTip('offline')
        # self.role_label.setVisible(False)
        message_bus.session.disconnect()
        message_bus.session = None
        state['connected'] = False

    def _create_actions(self):
        orb.log.debug('* creating actions ...')
        app_name = config.get('app_name', 'Pangalaxian'),
        self.about_action = self.create_action(
                                    "About",
                                    slot=self.show_about,
                                    tip="About {}".format(app_name))
        self.help_action = self.create_action(
                                    "Help",
                                    slot=self.show_help,
                                    icon='tardis',
                                    tip="Help")
        self.new_project_action = self.create_action(
                                    "Create New Project",
                                    slot=self.new_project,
                                    tip="Create a New Project")
        self.delete_project_action = self.create_action(
                                    "Delete This Project",
                                    slot=self.delete_project,
                                    tip="Delete the current Project")
        # default:  delete_project_action is not visible
        self.delete_project_action.setEnabled(False)
        self.delete_project_action.setVisible(False)
        enable_collab_tip = "Enable Collaboration on the current Project"
        self.enable_collaboration_action = self.create_action(
                                    "Enable Collaboration",
                                    slot=self.enable_collaboration,
                                    tip=enable_collab_tip)
        # default:  enable_collaboration_action is not visible
        self.enable_collaboration_action.setEnabled(False)
        self.enable_collaboration_action.setVisible(False)
        # Administer roles
        admin_action_tip = "Administer roles on the current Project"
        self.admin_action = self.create_action(
                                    "Administer Roles",
                                    slot=self.do_admin_stuff,
                                    tip=admin_action_tip)
        # default:  admin_action is not visible
        self.admin_action.setEnabled(False)
        self.admin_action.setVisible(False)
        self.set_project_action = self.create_action(
                                    "Set Project",
                                    slot=self.set_current_project,
                                    tip="Set Current Project")
        # self.display_disciplines_action = self.create_action(
                                    # "Display Disciplines",
                                    # slot=self.display_disciplines,
                                    # tip="Display List of Disciplines",
                                    # modes=['system', 'component'])
        self.display_product_types_action = self.create_action(
                                    "Product Types Library",
                                    slot=self.display_product_types,
                                    tip="Product Types Library",
                                    modes=['system', 'component', 'db'])
        self.reqts_manager_action = self.create_action(
                                "Project Requirements Manager",
                                slot=self.display_requirements_manager,
                                icon='lander',
                                tip="Manage Requirements for the Current Project",
                                modes=['system', 'component', 'db'])
        hw_lib_title = "Systems and Components (Hardware Products) Library"
        self.product_lib_action = self.create_action(
                                    hw_lib_title,
                                    slot=self.product_library,
                                    icon='part',
                                    tip=hw_lib_title,
                                    modes=['system', 'component', 'db'])
        port_lib_title = "Port Template Library"
        self.port_template_lib_action = self.create_action(
                                    port_lib_title,
                                    slot=self.port_template_library,
                                    icon='PortTemplate',
                                    tip=port_lib_title,
                                    modes=['system', 'component', 'db'])
        pd_lib_title = "Parameter Definition Library"
        self.parameter_lib_action = self.create_action(
                                    pd_lib_title,
                                    slot=self.parameter_library,
                                    icon='parameter',
                                    tip=pd_lib_title,
                                    modes=['system', 'component', 'db'])
        self.new_parameter_action = self.create_action(
                                    "New Parameter Definition",
                                    slot=self.new_parameter,
                                    icon='new_parameter',
                                    tip="Define a New Parameter",
                                    modes=['system', 'component', 'db'])
        self.new_product_action = self.create_action(
                                    "New System or Component (Product)",
                                    slot=self.new_product,
                                    icon='new_part',
                                    tip="Create a New System or Component",
                                    modes=['system', 'component', 'db'])
        self.new_product_type_action = self.create_action(
                                    "New Product Type",
                                    slot=self.new_product_type,
                                    icon="new_doc",
                                    tip="Create a New Product Type",
                                    modes=['system', 'component', 'db'])
        self.new_functional_requirement_action = self.create_action(
                                    "New Functional Requirement",
                                    slot=self.new_functional_requirement,
                                    icon="new_doc",
                                    tip="Create a New Requirement",
                                    modes=['system'])
        self.new_performance_requirement_action=self.create_action(
                                    "New Performance Requirement",
                                    slot=self.new_perform_requirement,
                                    icon="new_doc",
                                    tip="Create a New Requirement",
                                    modes=["system"])
        self.new_test_action = self.create_action(
                                    "New Test",
                                    slot=self.new_test,
                                    icon="new_doc",
                                    tip="Create a New Test",
                                    modes=['system', 'component', 'db'])
        self.view_cad_action = self.create_action(
                                    "View a CAD Model...",
                                    slot=self.open_step_file,
                                    icon="view_16",
                                    tip="View a CAD Model (from a STEP File)",
                                    modes=['system', 'component'])
        self.export_project_to_file_action = self.create_action(
                                    "Export Project to a File...",
                                    slot=self.export_project_to_file,
                                    tip="Export Project to a File...",
                                    modes=['system'])
        self.export_reqts_to_file_action = self.create_action(
                                "Export Project Requirements to a File...",
                                slot=self.export_reqts_to_file,
                                tip="Export Project Requirements to a File...",
                                modes=['system'])
        self.output_mel_action = self.create_action(
                                    "Write MEL...",
                                    slot=self.output_mel,
                                    tip="Write MEL...",
                                    modes=['system'])
        self.dump_db_action = self.create_action(
                                    "Dump Database to a File...",
                                    slot=self.dump_database,
                                    tip="Dump DB...",
                                    modes=['db'])
        # actions accessible via the 'Import Data or Objects' toolbar menu:
        # * import_excel_data_action
        # * import_objects (import project or other serialized objs)
        # * load_test_objects
        # self.import_excel_data_action = self.create_action(
                                    # "Import Data from Excel...",
                                    # slot=self.import_excel_data)
        self.import_objects_action = self.create_action(
                                    "Import Project from a File...",
                                    slot=self.import_objects,
                                    tip="Import Project from a File...",
                                    modes=['system'])
        self.import_reqts_from_file_action = self.create_action(
                            "Import Project Requirements from a File...",
                            slot=self.import_reqts_from_file,
                            tip="Import Project Requirements from a File...",
                            modes=['system'])
        # Load Test Objects needs more work -- make it local, or at least
        # non-polluting somehow ...
        self.load_test_objects_action = self.create_action(
                                    "Load Test Objects",
                                    slot=self.load_test_objects)
        self.connect_to_bus_action = self.create_action(
                                    "Connect to the message bus",
                                    slot=self.connect_to_bus,
                                    icon="system",
                                    checkable=True,
                                    tip="Connect to the message bus")
        self.component_mode_action = self.create_action(
                                    "Component Modeler",
                                    slot=self._set_component_mode,
                                    icon="part",
                                    checkable=True,
                                    tip="Component Modeler")
        self.system_mode_action = self.create_action(
                                    "Systems Modeler",
                                    slot=self._set_system_mode,
                                    icon="favicon",
                                    checkable=True,
                                    tip="Systems Modeler")
        self.db_mode_action = self.create_action(
                                    "Local DB",
                                    slot=self._set_db_mode,
                                    icon="cache_16",
                                    checkable=True,
                                    tip="Local DB")
        self.data_mode_action = self.create_action(
                                    "Data Mode",
                                    slot=self._set_data_mode,
                                    icon="data",
                                    checkable=True,
                                    tip="Data Mode")
        self.data_mode_action.setEnabled(False)
        self.edit_prefs_action = self.create_action(
                                    "Edit Preferences",
                                    slot=self.edit_prefs)
        self.refresh_tree_action = self.create_action(
                                    "Refresh System Tree and Dashboard",
                                    slot=self.refresh_tree_and_dashboard)
        # self.compare_items_action = self.create_action(
                                    # "Compare Items by Parameters",
                                    # slot=self.compare_items)
        # self.load_requirements_action = self.create_action(
                                    # "Load Requirements",
                                    # slot=self.load_requirements)
        self.exit_action = self.create_action(
                                    "Exit",
                                    slot=self.close)
        # set up a group for mode actions
        mode_action_group = QtWidgets.QActionGroup(self)
        self.component_mode_action.setActionGroup(mode_action_group)
        self.system_mode_action.setActionGroup(mode_action_group)
        self.db_mode_action.setActionGroup(mode_action_group)
        self.data_mode_action.setActionGroup(mode_action_group)
        orb.log.debug('  ... all actions created.')

    def create_action(self, text, slot=None, icon=None, tip=None,
                      checkable=False, modes=None):
        action = QtWidgets.QAction(text, self)
        if icon is not None:
            icon_file = icon + state['icon_type']
            icon_path = os.path.join(orb.icon_dir, icon_file)
            action.setIcon(QtGui.QIcon(icon_path))
        if tip is not None:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        if slot is not None:
            action.triggered.connect(slot)
        if checkable:
            action.setCheckable(True)
        if modes:
            for mode in modes:
                self.mode_widgets[mode].add(action)
        else:
            self.mode_widgets['all'].add(action)
        return action

    # 'mode' property (linked to state['mode'])
    def get_mode(self):
        """
        Get the current mode. (Default: 'system')
        """
        return state.get('mode', 'system')

    def set_mode(self, mode):
        """
        Set the current mode.
        """
        initial_size = self.size()
        if hasattr(orb, 'store'):
            orb.db.commit()
        modal_actions = set.union(*[a for a in self.mode_widgets.values()])
        if mode in self.modes:
            current_mode = state.get('mode')
            if current_mode in self.modes:
                self.main_states[current_mode] = self.saveState(
                                            self.modes.index(current_mode))
            state['mode'] = mode
            for action in modal_actions:
                action.setVisible(False)
            for action in set.union(self.mode_widgets[mode],
                                    self.mode_widgets['all']):
                action.setVisible(True)
            if mode == 'component':
                self.mode_label.setText('Component Modeler')
            elif mode == 'system':
                self.mode_label.setText('Systems Modeler')
            elif mode == 'db':
                self.mode_label.setText('Local Database')
            elif mode == 'data':
                self.mode_label.setText('Data Tools')
            self._update_views()
            saved_state = self.main_states.get(mode)
            if saved_state:
                self.restoreState(saved_state, self.modes.index(mode))
            self.resize(initial_size)

    def del_mode(self):
        pass

    mode = property(get_mode, set_mode, del_mode, "mode property")

    ########################################################################
    # mode-setting functions that are called by gui "actions"

    def _set_component_mode(self):
        self.mode = 'component'

    def _set_system_mode(self):
        self.mode = 'system'

    def _set_db_mode(self):
        self.mode = 'db'

    def _set_data_mode(self):
        self.mode = 'data'
    #######################################################################

    # 'datasets' property (linked to state['datasets']
    # NOTE:  the primary purpose of this property is to persist the *order* of
    # dataset names, to give the dataset list widget some coherence, because
    # the hdf5 file storage does not guarantee any particular order for the
    # stored datasets.  The order of the `datasets` list is intended to
    # correspond to the order in which the datasets were added.
    def get_datasets(self):
        """
        Get the current dataset names.

        Returns:
            datasets (list of str):  list of the names of currently stored
                datasets
        """
        return state.get('datasets', [])

    def set_datasets(self, names):
        """
        Set the current list of dataset names.

        Arguments:
            names (list of str):  list of the names of currently stored
                datasets
        """
        orb.log.info('* setting datasets: {}'.format(str(names)))
        state['datasets'] = [str(n) for n in names]

    def del_datasets(self):
        pass

    datasets = property(get_datasets, set_datasets, del_datasets,
                       "datasets property")

    # 'dataset' property (linked to state['dataset']
    def get_dataset(self):
        """
        Get the name of the currently selected dataset.

        Returns:
            dataset (str):  name of currently selected dataset
        """
        return state.get('dataset')

    def set_dataset(self, name):
        """
        Set the name of the currently selected dataset.

        Arguments:
            name (str):  name of currently selected dataset
        """
        orb.log.info('* setting dataset: {}'.format(name))
        state['dataset'] = name

    def del_dataset(self):
        pass

    dataset = property(get_dataset, set_dataset, del_dataset,
                       "dataset property")

    @property
    def cnames(self):
        """
        Sorted list of class names.
        """
        names = list(orb.classes.keys())[:]
        names.sort()
        return names

    @property
    def populated(self):
        """
        Class names for which the corresponding db table is non-empty.
        """
        names = [c for c in orb.classes if orb.get_count(c)]
        names.sort()
        return names

    def get_project(self):
        """
        Get the current project (or SANDBOX project if not set).
        """
        # if project in saved state is not found, return SANDBOX project
        return orb.get(state.get('project')) or orb.get('pgefobjects:SANDBOX')

    def set_project(self, p):
        """
        Set the current project.

        Args:
            p (Project):  Project instance to be set
        """
        # NOTE:  set_project() now just sets the 'project' state (project oid)
        # and dispatches the 'set current project' signal
        if p:
            orb.log.info('* set_project({})'.format(p.id))
            state['project'] = str(p.oid)
            if state['connected']:
                self.role_label.setText('online: syncing project data ...')
            else:
                self.role_label.setText('loading project data ...')
        else:
            orb.log.info('* set_project(None)')
            orb.log.info('  setting project to SANDBOX (default)')
            state['project'] = 'pgefobjects:SANDBOX'
        orb.log.info('  dispatching "set current project" signal ...')
        dispatcher.send(signal="set current project")

    def del_project(self):
        pass

    # current project (as a Project instance)
    project = property(get_project, set_project, del_project,
                       "project property")

    @property
    def projects(self):
        """
        The current list of project ids (codes/acronyms).
        """
        return list(orb.get_by_type('Project'))

    # 'systems' property (read-only)
    @property
    def systems(self):
        """
        The current systems of interest, determined by the current project.
        """
        project = orb.get(state.get('project'))
        return [psu.system for psu in project.systems]

    # 'product' property reflects the product selected in the product
    # modeler; state['product'] is set to its oid
    def get_product(self):
        """
        Get the current product.
        """
        return orb.get(state.get('product'))

    def set_product(self, p):
        """
        Set the current product.

        Args:
            p (Product):  the product to be set.
        """
        oid = getattr(p, 'oid', None)
        orb.log.info('* setting product: {}'.format(oid))
        state['product'] = str(oid)
        orb.log.debug('  - dispatching "set current product" ...')
        dispatcher.send(signal="set current product",
                        sender='set_product', product=p)

    def del_product(self):
        pass

    product = property(get_product, set_product, del_product,
                       "product property")

    def create_lib_list_widget(self, cnames=None, include_subtypes=True):
        """
        Creates an instance of 'LibraryListWidget' to be assigned to
        self.library_widget.

        Keyword Args:
            cnames (list of str):  class names of the libraries
            include_subtypes (bool):  flag indicating if library view should
                include subtypes of the specified cname
        """
        if not cnames:
            cnames = ['HardwareProduct', 'Template', 'PortType',
                      'PortTemplate', 'ParameterDefinition']
        widget = LibraryListWidget(cnames=cnames,
                                   include_subtypes=include_subtypes,
                                   parent=self)
        return widget

    def start_logging(self, console=False, debug=False):
        """
        Create a pangalaxian client (`pgxn`) log and begin writing to it.

        Keyword Args:
            console (bool):  if True, sends log messages to stdout
            debug (bool):  if True, sets level to debug
        """
        orb.log, self.error_log = get_loggers(orb.home, 'pgxn',
                                              console=console, debug=debug)
        orb.log.info('* pangalaxian client logging initialized ...')
        # TODO:  ignoring mb_error_log for now but will need it in future ...
        mb_log, mb_error_log = get_loggers(orb.home, 'mbus',
                                           console=console, debug=debug)
        message_bus.set_logger(mb_log)

    def init_toolbar(self):
        orb.log.debug('  - initializing toolbar ...')
        self.toolbar = self.addToolBar("Actions")
        self.toolbar.setObjectName('ActionsToolBar')
        import_icon_file = 'open' + state['icon_type']
        import_icon_path = os.path.join(orb.icon_dir, import_icon_file)
        import_actions = [
                          # self.import_excel_data_action,
                          self.import_objects_action,
                          self.import_reqts_from_file_action,
                          # Load Test Objects is currently flaky unless ONLY
                          # operating in standalone mode ...
                          # self.load_test_objects_action,
                          self.exit_action]
        # Import Excel deactivated until mapping is implemented, and/or support
        # for "data sets" is revised (hdf5 was breaking) ...
        # self.import_excel_data_action.setEnabled(False)
        import_button = MenuButton(QtGui.QIcon(import_icon_path),
                                   tooltip='Import Data or Objects',
                                   actions=import_actions, parent=self)
        self.toolbar.addWidget(import_button)
        export_icon_file = 'save' + state['icon_type']
        export_icon_path = os.path.join(orb.icon_dir, export_icon_file)
        export_actions = [self.export_project_to_file_action,
                          self.export_reqts_to_file_action,
                          self.output_mel_action,
                          self.dump_db_action]
        export_button = MenuButton(QtGui.QIcon(export_icon_path),
                                   tooltip='Export Data or Objects',
                                   actions=export_actions, parent=self)
        self.toolbar.addWidget(export_button)
        new_object_icon_file = 'new_box' + state['icon_type']
        new_object_icon_path = os.path.join(orb.icon_dir, new_object_icon_file)
        new_object_actions = [self.new_parameter_action,
                              self.new_product_action,
                              self.new_product_type_action,
                              self.new_functional_requirement_action,
                              self.new_performance_requirement_action,
                              self.new_test_action]
        new_object_button = MenuButton(QtGui.QIcon(new_object_icon_path),
                                   tooltip='Create New Objects',
                                   actions=new_object_actions, parent=self)
        self.toolbar.addWidget(new_object_button)

        system_tools_icon_file = 'tools' + state['icon_type']
        system_tools_icon_path = os.path.join(orb.icon_dir,
                                              system_tools_icon_file)
        system_tools_actions = [self.edit_prefs_action,
                                # self.admin_action,
                                self.refresh_tree_action,
                                self.product_lib_action,
                                self.port_template_lib_action,
                                self.parameter_lib_action,
                                # self.display_disciplines_action,
                                self.display_product_types_action,
                                self.reqts_manager_action
                                # self.compare_items_action
                                ]
        system_tools_button = MenuButton(QtGui.QIcon(system_tools_icon_path),
                                   tooltip='Tools',
                                   actions=system_tools_actions, parent=self)
        self.toolbar.addWidget(system_tools_button)

        self.toolbar.addAction(self.view_cad_action)

        help_icon_file = 'tardis' + state['icon_type']
        help_icon_path = os.path.join(orb.icon_dir, help_icon_file)
        help_actions = [self.help_action,
                        self.about_action]
        help_button = MenuButton(QtGui.QIcon(help_icon_path),
                                 tooltip='Help',
                                 actions=help_actions, parent=self)
        self.toolbar.addWidget(help_button)

        self.toolbar.addSeparator()

        project_label = QtWidgets.QLabel('Project:  ')
        project_label.setStyleSheet('font-weight: bold')
        self.toolbar.addWidget(project_label)
        self.project_selection = ButtonLabel(
                                    self.project.id,
                                    actions=[self.enable_collaboration_action,
                                             self.admin_action,
                                             self.delete_project_action,
                                             self.new_project_action],
                                    w=120)
        self.delete_project_action.setVisible(False)
        self.delete_project_action.setEnabled(False)
        self.enable_collaboration_action.setVisible(False)
        self.enable_collaboration_action.setEnabled(False)
        self.project_selection.clicked.connect(self.set_current_project)
        self.toolbar.addWidget(self.project_selection)
        # project_selection and its label will only be visible in 'data',
        # 'system', and 'component' modes
        self.mode_widgets['data'].add(self.project_selection)
        self.mode_widgets['data'].add(project_label)
        self.mode_widgets['system'].add(self.project_selection)
        self.mode_widgets['system'].add(project_label)
        self.mode_widgets['component'].add(self.project_selection)
        self.mode_widgets['component'].add(project_label)
        self.toolbar.addSeparator()

        spacer = QtWidgets.QWidget(parent=self)
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                             QtWidgets.QSizePolicy.Expanding)
        self.toolbar.addWidget(spacer)
        self.toolbar.addAction(self.connect_to_bus_action)
        # self.circle_widget = CircleWidget()
        # self.toolbar.addWidget(self.circle_widget)
        self.mode_label = ModeLabel('')
        self.toolbar.addWidget(self.mode_label)
        self.toolbar.addAction(self.data_mode_action)
        self.toolbar.addAction(self.db_mode_action)
        self.toolbar.addAction(self.system_mode_action)
        self.toolbar.addAction(self.component_mode_action)
        # Makes the next toolbar appear underneath this one
        self.addToolBarBreak()

    # def create_timer(self):
        # self.circle_timer = QTimer(self)
        # self.circle_timer.timeout.connect(self.circle_widget.next)
        # self.circle_timer.start(25)

    def _init_ui(self, width, height):
        orb.log.debug('* _init_ui() ...')
        # set a placeholder in central widget
        self.setCentralWidget(PlaceHolder(image=self.logo, min_size=300,
                                          parent=self))
        self.init_toolbar()
        # menubar is not being used -- not compatible with Macs, using a
        # toolbar instead ...
        # self.init_menubar()
        self.setCorner(Qt.TopLeftCorner, Qt.TopDockWidgetArea)
        self.setCorner(Qt.TopRightCorner, Qt.RightDockWidgetArea)
        self._setup_left_dock()
        self._setup_right_dock()
        self._setup_top_dock_widgets()
        # Initialize a statusbar for the window
        self.net_status = QtWidgets.QLabel()
        offline_icon_file = 'offline' + state['icon_type']
        offline_icon_path = os.path.join(orb.icon_dir, offline_icon_file)
        self.offline_icon = QtGui.QPixmap(offline_icon_path)
        online_icon_file = 'online' + state['icon_type']
        online_icon_path = os.path.join(orb.icon_dir, online_icon_file)
        self.online_icon = QtGui.QPixmap(online_icon_path)
        self.net_status.setPixmap(self.offline_icon)
        self.net_status.setToolTip('offline')
        self.role_label = ModeLabel('offline', w=300)
        self.statusbar = self.statusBar()
        self.statusbar.setStyleSheet('color: purple; font-weight: bold;')
        self.pb = QtWidgets.QProgressBar(self.statusbar)
        stl = "QProgressBar::chunk {background: QLinearGradient( x1: 0,"
        stl += "y1: 0, x2: 1, y2: 0,stop: 0 #A020F0,stop: 0.4999"
        stl += " #A020F0,stop: 0.5 #A020F0,stop: 1 #551A8B );"
        stl += "border-bottom-right-radius: 5px;border-bottom-left-radius:"
        stl += " 5px;border: .px solid black;}"
        self.pb.setStyleSheet(stl)
        self.pb.setTextVisible(False)
        self.pb.hide()
        self.statusbar.addPermanentWidget(self.pb)
        self.statusbar.addPermanentWidget(self.role_label)
        self.statusbar.addPermanentWidget(self.net_status)
        self.statusbar.showMessage("To infinity, and beyond! :)")
        dispatcher.connect(self.increment_progress, 'tree node fetched')
        # x and y coordinates and the screen, width, height
        self.setGeometry(100, 100, width, height)
        self.setWindowTitle(config['app_name'])

    def start_progress(self, msg, count=0):
        if hasattr(self, 'pb'):
            self.pb.show()
            self.pb.setValue(0)
            self.pb.setMaximum(count)
            self.statusbar.showMessage(msg)

    def increment_progress(self, inc=1, msg=''):
        if hasattr(self, 'pb'):
            if msg:
                self.statusbar.showMessage(msg)
            self.pb.setValue(self.pb.value() + inc)

    def end_progress(self):
        if hasattr(self, 'pb'):
            self.pb.reset()
            self.pb.hide()
            self.statusbar.showMessage("To infinity, and beyond!")

    def on_new_project_signal(self, obj=None):
        """
        Handle louie signal for (local) "new project".
        """
        orb.log.info('* on_new_project_signal(obj: {})'.format(
                                               getattr(obj, 'id', 'None')))
        if obj:
            self.project = obj
            if state['connected']:
                orb.log.info('  calling vger.save() for project id: {}'.format(
                                                                       obj.id))
                rpc = message_bus.session.call(u'vger.save',
                                               serialize(orb, [obj]))
                rpc.addCallback(self.on_result)
                rpc.addErrback(self.on_failure)

    def on_collaborate(self):
        pass   # to be implemented ...
        # NOTE:  the following code added the project to the admin service --
        # will be implemented in a separate action ("collaborate") which will
        # set up a previously local-only project on the server so that other
        # users can be given collaborative roles on it ...
        # if obj and state['connected'] and self.adminserv:
            # orb.log.info('  - calling rpc omb.organization.add')
            # orb.log.debug('    with arguments:')
            # orb.log.debug('      oid={}'.format(obj.oid))
            # orb.log.debug('      id={}'.format(obj.id))
            # orb.log.debug('      name={}'.format(obj.name))
            # orb.log.debug('      org_type={}'.format('Project'))
            # parent_org = getattr(obj.parent_organization, 'oid', None)
            # orb.log.debug('      parent={}'.format(parent_org))
            # rpc = message_bus.session.call(u'omb.organization.add',
                        # oid=obj.oid, id=obj.id, name=obj.name,
                        # org_type='Project', parent=parent_org)
            # rpc.addCallback(self.on_null_result)
            # rpc.addErrback(self.on_failure)

    def on_remote_modified_signal(self, content=None):
        """
        Handle louie signal "remote: modified".
        """
        orb.log.info('* received "remote: modified" signal on:')
        # content is a tuple:  (obj.oid, str(obj.mod_datetime))
        obj_oid, obj_id, dts_str = content
        orb.log.info('  oid: {}'.format(obj_oid))
        orb.log.info('  id: {}'.format(obj_id))
        # first check if we have the object
        obj = orb.get(obj_oid)
        if obj:
            orb.log.info('  ')
            # if the mod_datetime of the repo object is later, get it
            dts = None
            if dts_str:
                dts = uncook_datetime(dts_str)
            orb.log.info('  remote object mod_datetime: {}'.format(dts_str))
            orb.log.info('  local  object mod_datetime: {}'.format(
                                            str(obj.mod_datetime)))
            if dts == obj.mod_datetime:
                orb.log.info('  local and remote objects have')
                orb.log.info('  same mod_datetime, ignoring.')
            elif dts > obj.mod_datetime:
                # get the remote object
                orb.log.info('  remote object is newer, getting...')
                rpc = message_bus.session.call(u'vger.get_object', obj.oid,
                                               include_components=True)
                rpc.addCallback(self.on_remote_get_mod_object)
                rpc.addErrback(self.on_failure)
            else:
                orb.log.info('  local object is newer, ignoring remote.')
        else:
            orb.log.info('  ')
            orb.log.info('  object not found in local db, getting ...')
            rpc = message_bus.session.call(u'vger.get_object', obj.oid,
                                           include_components=True)
            rpc.addCallback(self.on_remote_get_mod_object)
            rpc.addErrback(self.on_failure)

    def on_remote_deleted_signal(self, content=None):
        """
        Handle louie signal "remote: deleted".
        """
        orb.log.info('* received "remote: deleted" signal on:')
        # content is an oid
        obj_oid = content
        orb.log.info('  oid: {}'.format(obj_oid))
        # first check if we have the object
        obj = orb.get(obj_oid)
        if obj:
            cname = obj.__class__.__name__
            if (cname in ['Acu', 'ProjectSystemUsage']
                and hasattr(self, 'sys_tree')):
                # find all expanded tree nodes that reference obj
                if cname == 'Acu':
                    comp = obj.component
                else:   # 'ProjectSystemUsage'
                    comp = obj.system
                idxs = self.sys_tree.object_indexes_in_tree(comp)
                # if any are found, signal them to update
                for idx in idxs:
                    node = self.sys_tree.source_model.get_node(idx)
                    ref_des = getattr(node.link, 'reference_designator',
                                      '(No reference designator)')
                    orb.log.info('  deleting position and component "%s"'
                                 % ref_des)
                    pos = idx.row()
                    row_parent = idx.parent()
                    parent_id = self.sys_tree.source_model.get_node(
                                                            row_parent).obj.id
                    orb.log.info('  at row {} of parent {}'.format(pos,
                                                                   parent_id))
                    # removeRow calls orb.delete on the object ...
                    self.sys_tree.source_model.removeRow(pos, row_parent)
                # resize dashboard columns if necessary
                self.refresh_dashboard()
            else:
                orb.delete([obj])
                dispatcher.send('deleted object', oid=obj_oid, cname=cname,
                                remote=True)
            orb.log.info('  - object deleted.')
        else:
            orb.log.info('  oid not found in local db; ignoring.')

    def on_remote_get_mod_object(self, serialized_objects):
        orb.log.info('* on_remote_get_mod_object()')
        for obj in deserialize(orb, serialized_objects):
            # same as for local 'modified object' but without the remote
            # calls ...
            cname = obj.__class__.__name__
            if hasattr(self, 'library_widget'):
                self.library_widget.refresh(cname=cname)
            if hasattr(self, 'sys_tree'):
                self.update_object_in_trees(obj)
            elif self.mode == 'db':
                self.refresh_cname_list()
                self.set_object_table_for(cname)

    def on_new_object_signal(self, obj=None, cname=''):
        """
        Handle louie signal for (local) "new object".
        """
        # for now, use on_mod_object_signal (may change in the future)
        self.on_mod_object_signal(obj=obj, cname=cname, msg='new')

    def on_mod_object_signal(self, obj=None, cname='', msg=None):
        """
        Handle local "new object" and "modified object" signals.
        """
        orb.log.info('* [pgxn] on_mod_object_signal()')
        if msg == 'new':
            orb.log.info('* received local "new object" signal')
            # currently, only HardwareProduct and its subclasses are cloaked
            if ((obj and isinstance(obj, orb.classes['HardwareProduct'])) or
                (cname and issubclass(orb.classes.get(cname),
                                      orb.classes['HardwareProduct']))):
                if state.get('cloaked'):
                    state['cloaked'].append(obj.oid)
                else:
                    state['cloaked'] = [obj.oid]
                orb.log.info('  - new object added to state["cloaked"]')
        else:
            orb.log.info('* received local "modified object" signal')
        if obj:
            cname = obj.__class__.__name__
            orb.log.info('  object oid: "{}"'.format(
                                        str(getattr(obj, 'oid', '[no oid]'))))
            orb.log.info('  cname: "{}"'.format(str(cname)))
            # the library widget will now refresh itself (it listens for "new
            # object", "modified object", etc. ...)
            # if hasattr(self, 'library_widget'):
                # self.library_widget.refresh(cname=cname)
            if self.mode == 'system':
                if getattr(self, 'sys_tree', None):
                    self.update_object_in_trees(obj)
                # NOTE:  EXPERIMENTALLY, set_system_model_window() is now run
                # inside refresh_tree_and_dashboard()
                # NOTE:  see if we can update the tree without rebuilding it
                # ... so comment out the refresh_tree_and_dashboard()
                # self.refresh_tree_and_dashboard()
                # run set_system_model_window() *AFTER* refreshing tree, so
                # that the model window will get all the remaining space
                # if cname == 'ProjectSystemUsage':
                    # orb.log.info('  - obj is PSU, resetting model window ...')
                    # # update the model window
                    # self.set_system_model_window(obj.system)
            elif self.mode == 'db':
                self.refresh_cname_list()
                self.set_object_table_for(cname)
            if state['connected']:
                if (msg == 'new' and
                    isinstance(obj, orb.classes['HardwareProduct'])):
                        # serialized_objs = serialize(orb, [obj],
                                                    # include_components=True)
                        serialized_objs = serialize(orb, [obj])
                else:
                    serialized_objs = serialize(orb, [obj])
                orb.log.info('  calling rpc vger.save() on obj id: {}'.format(
                                                                     obj.id))
                rpc = message_bus.session.call(u'vger.save', serialized_objs)
                rpc.addCallback(self.on_result)
                rpc.addErrback(self.on_failure)
        else:
            orb.log.info('  *** no object provided -- ignoring! ***')

    # def on_null_result(self):
        # orb.log.info('  rpc success.')
        # self.statusbar.showMessage('synced.')

    def on_result(self, stuff):
        orb.log.info('  rpc result: %s' % str(stuff))
        # TODO:  add more detailed status message ...
        self.statusbar.showMessage('synced.')

    def on_failure(self, f):
        orb.log.info("* rpc failure: {}".format(f.getTraceback()))

    def on_deleted_object_signal(self, oid='', cname='', remote=False):
        """
        Call functions to update applicable widgets when an object has been
        deleted.

        Keyword Args:
            oid (str):  oid of the deleted object
            cname (str):  class name of the deleted object
            remote (bool):  whether the action originated remotely
        """
        orb.log.info('* received local "deleted object" signal on:')
        # cname is needed here because at this point the local object has
        # already been deleted
        orb.log.info('  cname="{}", oid = "{}"'.format(str(cname), str(oid)))
        if ((cname in orb.classes and
             issubclass(orb.classes[cname], orb.classes['Modelable']))
            or cname == 'Acu'):
            orb.recompute_parmz()
            # TODO:  value might not be displayed until dashboard gets focus --
            # may have to explicitly set focus to dashboard to force it
            # self.refresh_tree_and_dashboard()
        # TODO:  other actions may be needed ...
        # NOTE:  libraries are now subscribed to the 'deleted object' signal
        # and update themselves, so no need to call them.
        if self.mode == 'db':
            if str(state['current_cname']) == str(cname):
                self.set_object_table_for(cname)
        elif self.mode == 'component':
            self.set_product_modeler_interface()
        if not remote and state.get('connected'):
            orb.log.info('  - publishing "deleted" msg to public channel')
            # cname is not needed for pub/sub msg because if it is of interest
            # to a remote user, they have the object
            message_bus.session.publish(u'vger.channel.public',
                                        {u'deleted': oid})
            if oid in state.get('synced_oids', []):
                state['synced_oids'].remove(oid)

    def on_set_current_project_signal(self):
        """
        Update views as a result of a project being set, syncing project data
        if online.
        """
        project_oid = state.get('project')
        project = orb.get(project_oid)
        # disable 'delete' and 'enable_collaboration' context menu opts if
        # project not created by local user or project is SANDBOX
        if (project_oid == 'pgefobjects:SANDBOX' or
            project.creator != self.local_user):
            self.delete_project_action.setVisible(False)
            self.delete_project_action.setEnabled(False)
            self.enable_collaboration_action.setVisible(False)
            self.enable_collaboration_action.setEnabled(False)
            self.admin_action.setVisible(False)
            self.admin_action.setEnabled(False)
        else:
            self.delete_project_action.setEnabled(True)
            self.delete_project_action.setVisible(True)
        if (project_oid and project_oid != 'pgefobjects:SANDBOX'
            and state.get('connected')):
            rpc = self.sync_current_project(None)
            rpc.addCallback(self.on_project_sync_result)
            rpc.addErrback(self.on_failure)
            rpc.addCallback(self._update_views)
            rpc.addErrback(self.on_failure)
        else:
            self.sys_tree_rebuilt = False
            self.dashboard_rebuilt = False
            self._update_views()

    def _update_views(self, obj=None):
        """
        Call functions to update all widgets when mode has changed due to some
        action.

        Keyword Args:
            obj (Identifiable):  object whose change triggered the update
        """
        orb.log.info('* [pgxn] _update_views()')
        orb.log.info('         triggered by object: {}'.format(
                                            getattr(obj, 'id', '[no object]')))
        if hasattr(self, 'system_model_window'):
            self.system_model_window.cache_block_model()
        # [gui refactor] creation of top dock moved to _init_ui()
        p = self.project
        role_label_txt = u''
        tt_txt = u''
        p_roles = []
        if p:
            self.project_selection.setText(self.project.id)
            orb.log.info('* set_project({})'.format(p.id))
            state['project'] = str(p.oid)
            if hasattr(self, 'delete_project_action'):
                if p.oid == 'pgefobjects:SANDBOX':
                    # SANDBOX cannot be deleted, made collaborative, nor have
                    # roles provisioned (admin)
                    self.enable_collaboration_action.setVisible(False)
                    self.enable_collaboration_action.setEnabled(False)
                    self.delete_project_action.setEnabled(False)
                    self.delete_project_action.setVisible(False)
                    self.admin_action.setVisible(False)
                    self.admin_action.setEnabled(False)
                    role_label_txt = 'SANDBOX'
                else:
                    project_is_local = False
                    if state.get('assigned_roles'):
                        if state['assigned_roles'].get(p.oid):
                            p_roles += state['assigned_roles'][p.oid]
                    # if user has Administrator role, append it
                    admin_of = state.get('admin_of') or []
                    if p.oid in admin_of and 'Administrator' not in p_roles:
                        p_roles.append('Administrator')
                    if p_roles:
                        if len(p_roles) > 1:
                            # add asterisk to indicate multiple roles
                            role_label_txt = u': '.join([p.id, p_roles[0],
                                                        ' *'])
                            tt_txt = u'<ul>\n'
                            for p_role in p_roles:
                                tt_txt += u'<li>' + str(p.id) + u': '
                                tt_txt += str(p_role) + u'</li>\n'
                            tt_txt += u'</ul>'
                        else:
                            role_label_txt = u': '.join([p.id, p_roles[0]])
                    else:
                        project_is_local = True
                        role_label_txt = u': '.join([p.id, '[local]'])
                    if state['connected']:
                        if p_roles:
                            # project is already collaborative
                            self.enable_collaboration_action.setVisible(False)
                            self.enable_collaboration_action.setEnabled(False)
                            if 'Administrator' in p_roles:
                                self.delete_project_action.setEnabled(True)
                                self.delete_project_action.setVisible(True)
                                self.admin_action.setVisible(True)
                                self.admin_action.setEnabled(True)
                        else:
                            # if we have no roles on the project but we have
                            # the project, then it is local, and it can be
                            # deleted or collaboration can be enabled
                            self.delete_project_action.setEnabled(True)
                            self.delete_project_action.setVisible(True)
                            self.enable_collaboration_action.setVisible(True)
                            self.enable_collaboration_action.setEnabled(True)
                    else:
                        # when offline, `enable collaboration` is disabled
                        self.enable_collaboration_action.setVisible(False)
                        self.enable_collaboration_action.setEnabled(False)
                        # NOTE:  THIS IS ONLY FOR TESTING!!
                        # when offline, admin action is disabled!!
                        self.admin_action.setVisible(True)
                        self.admin_action.setEnabled(True)
                        # when offline, only local projects can be deleted
                        if project_is_local:
                            self.delete_project_action.setEnabled(True)
                            self.delete_project_action.setVisible(True)
                        else:
                            self.delete_project_action.setEnabled(False)
                            self.delete_project_action.setVisible(False)
        else:
            self.project_selection.setText('None')
            orb.log.info('* set_project(None)')
            orb.log.info('  setting project to SANDBOX (default)')
            state['project'] = 'pgefobjects:SANDBOX'
            role_label_txt = u'SANDBOX'
            if hasattr(self, 'delete_project_action'):
                self.delete_project_action.setEnabled(False)
                self.delete_project_action.setVisible(False)
        self.role_label.setText(role_label_txt)
        if tt_txt:
            self.role_label.setToolTip(tt_txt)
        else:
            self.role_label.setToolTip(role_label_txt)
        if hasattr(self, 'library_widget'):
            self.library_widget.refresh()
        # connect mode-dependent signals to selection model
        # TODO:  check if it's ok to connect the same signal twice (hope so!)
        if self.mode == 'data':
            orb.log.debug('* mode: data')
            self.set_data_interface()
        elif self.mode == 'db':
            orb.log.debug('* mode: db')
            self.set_db_interface()
        elif self.mode == 'component':
            orb.log.debug('* mode: component')
            self.set_product_modeler_interface()
        elif self.mode == 'system':
            orb.log.debug('* mode: system')
            self.set_system_modeler_interface()

    def _setup_top_dock_widgets(self):
        orb.log.debug('  - no top dock widget -- building one now...')
        self.top_dock_widget = QtWidgets.QDockWidget()
        self.top_dock_widget.setObjectName('TopDock')
        self.top_dock_widget.setAllowedAreas(Qt.TopDockWidgetArea)
        # NOTE:  might not need to be floatable (now spans the whole window)
        self.top_dock_widget.setFeatures(
                                QtWidgets.QDockWidget.DockWidgetFloatable)
        # create widget for top dock:
        if self.mode == 'system':
            # ********************************************************
            # dashboard panel
            # ********************************************************
            self.refresh_tree_and_dashboard()
            self.top_dock_widget.setWidget(self.dashboard_panel)
        elif self.mode == 'component':
            # ********************************************************
            # product_info_panel (component view)
            # ********************************************************
            self.setup_product_info_panel()
            self.top_dock_widget.setWidget(self.product_info_panel)
        self.addDockWidget(Qt.TopDockWidgetArea, self.top_dock_widget)

    def setup_product_info_panel(self):
        self.product_info_panel = ProductInfoPanel(parent=self)
        self.product_info_panel.size_policy = QtWidgets.QSizePolicy(
                                    QtWidgets.QSizePolicy.Expanding,
                                    QtWidgets.QSizePolicy.Expanding)

    def _setup_left_dock(self):
        """
        Set up the persistent left dock widget containers.
        """
        orb.log.debug('  - no left dock widget -- adding one now...')
        # if we don't have a left dock widget yet, create ALL the stuff
        self.left_dock = QtWidgets.QDockWidget()
        self.left_dock.setObjectName('LeftDock')
        self.left_dock.setFeatures(QtWidgets.QDockWidget.DockWidgetFloatable)
        self.left_dock.setAllowedAreas(Qt.LeftDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.left_dock)

    def _setup_right_dock(self):
        # NOTE:  refactored to use LibraryListWidget instead of
        # multiple instances of LibraryListView
        orb.log.debug('  - no right dock widget -- building one now...')
        # if we don't have a right dock widget yet, create ALL the stuff
        self.right_dock = QtWidgets.QDockWidget()
        self.right_dock.setObjectName('RightDock')
        self.right_dock.setFeatures(QtWidgets.QDockWidget.DockWidgetFloatable)
        self.right_dock.setAllowedAreas(Qt.RightDockWidgetArea)
        self.library_widget = self.create_lib_list_widget()
        self.right_dock.setWidget(self.library_widget)
        self.addDockWidget(Qt.RightDockWidgetArea, self.right_dock)

    def update_pgxn_obj_panel(self, create_new=True):
        """
        Set up a new PgxnObject panel (left dock widget in Component mode).
        """
        orb.log.info('* [pgxn] update_pgxn_obj_panel(create_new={})'.format(
                                                           str(create_new)))
        # if there is an existing panel, remove and destroy its contents
        if getattr(self, 'pgxn_obj_panel', None):
            try:
                pgxn_panel_layout = self.pgxn_obj_panel.layout()
                if getattr(self, 'pgxn_obj', None):
                    pgxn_panel_layout.removeWidget(self.pgxn_obj)
                    # NOTE:  WA_DeleteOnClose kills the "ghost pgxnobject" bug
                    self.pgxn_obj.setAttribute(Qt.WA_DeleteOnClose)
                    self.pgxn_obj.parent = None
                    self.pgxn_obj.close()
                    self.pgxn_obj = None
                # if it has any other widgets, remove and close them
                if pgxn_panel_layout.count():
                    for i in range(pgxn_panel_layout.count()):
                        layout_item = pgxn_panel_layout.itemAt(i)
                        pgxn_panel_layout.removeItem(layout_item)
                        w = layout_item.widget()
                        if w:
                            w.close()
                # finally, close and destroy the panel
                self.pgxn_obj_panel.setAttribute(Qt.WA_DeleteOnClose)
                self.pgxn_obj_panel.parent = None
                self.pgxn_obj_panel.close()
                self.pgxn_obj_panel = None
            except:
                # oops, pgxn_obj_panel's C++ object got deleted
                pass
        if create_new:
            # create a new panel
            self.pgxn_obj_panel = QtWidgets.QWidget()
            self.pgxn_obj_panel.setSizePolicy(QtWidgets.QSizePolicy.Fixed,
                                              QtWidgets.QSizePolicy.Expanding)
            pgxn_panel_layout = QtWidgets.QVBoxLayout()
            self.pgxn_obj_panel.setLayout(pgxn_panel_layout)
            pgxn_panel_layout.setAlignment(self.pgxn_obj_panel,
                                         Qt.AlignLeft|Qt.AlignTop)
            if self.product:
                self.pgxn_obj = PgxnObject(self.product, embedded=True)
                pgxn_panel_layout.addWidget(self.pgxn_obj)
                pgxn_panel_layout.setAlignment(self.pgxn_obj,
                                             Qt.AlignLeft|Qt.AlignTop)
                pgxn_panel_layout.addStretch(1)
            else:
                placeholder = PlaceHolder(image=self.logo, min_size=400,
                                          parent=self)
                pgxn_panel_layout.addWidget(placeholder)

    def refresh_tree_and_dashboard(self):
        """
        Tree / dashboard refresh.  Can be user-activated by menu item.
        """
        orb.log.debug('* [pgxn] refresh_tree_and_dashboard()')
        self.sys_tree_rebuilt = False
        self.dashboard_rebuilt = False
        self.refresh_tree_views()

    def refresh_tree_views(self):
        orb.log.debug('* [pgxn] refresh_tree_views()')
        orb.log.debug('  refreshing system tree and rebuilding dashboard ...')
        # use number of tree components to set max in progress bar
        if not state.get('sys_trees'):
            state['sys_trees'] = {}
        if not state['sys_trees'].get(self.project.id):
            state['sys_trees'][self.project.id] = {}
        nodes = state['sys_trees'][self.project.id].get('nodes') or 0
        self.start_progress('rebuilding tree ...', count=nodes)
        # if getattr(self, 'sys_tree', None):
        try:
            # orb.log.debug('  + self.sys_tree exists ...')
            # if dashboard exists, it has to be destroyed too since the tree
            # and dashboard share their model()
            # if hasattr(self, 'dashboard_panel'):
            orb.log.debug('  + destroying existing dashboard, if any ...')
            dashboard_layout = self.dashboard_panel.layout()
            dashboard_layout.removeWidget(self.dashboard)
            self.dashboard.setAttribute(Qt.WA_DeleteOnClose)
            self.dashboard.hide()
            self.dashboard.parent = None
            self.dashboard.close()
            self.dashboard = None
            self.dashboard_rebuilt = False
        except:
            # if unsuccessful, it means there wasn't one, so no harm done
            pass
        try:
            orb.log.debug('  + destroying existing self.sys_tree, if any ...')
            # NOTE:  WA_DeleteOnClose kills the "ghost tree" bug
            self.sys_tree.setAttribute(Qt.WA_DeleteOnClose)
            self.sys_tree.parent = None
            self.sys_tree.close()
            self.sys_tree = None
        except:
            # if unsuccessful, it means there wasn't one, so no harm done
            pass
        orb.log.debug('  + destroying existing pgxn_obj panel, if any ...')
        self.update_pgxn_obj_panel(create_new=False)
        orb.log.debug('    self.pgxn_obj is {}'.format(str(
                      getattr(self, 'pgxn_obj', None))))
        # destroy left dock's widget
        ld_widget = self.left_dock.widget()
        if ld_widget:
            ld_widget.setAttribute(Qt.WA_DeleteOnClose)
            ld_widget.parent = None
            ld_widget.close()
        self.sys_tree = SystemTreeView(self.project)
        orb.log.debug('  + new self.sys_tree created ...')
        model = self.sys_tree.source_model
        orb.log.debug('    with source model: {}'.format(str(model)))
        self.sys_tree.setSizePolicy(QtWidgets.QSizePolicy.Minimum,
                                    QtWidgets.QSizePolicy.Expanding)
        self.sys_tree_rebuilt = True
        # node_count() gets # of nodes in sys tree for later use in setting max
        # for progress bar
        systems = [psu.system for psu in self.project.systems]
        nodes = 0
        if systems:
            for system in systems:
                nodes += node_count(system.oid) + 1
        state['sys_trees'][self.project.id]['nodes'] = nodes
        orb.log.debug('    and {} nodes.'.format(str(nodes)))
        # NB:  rebuild dashboard before expanding sys_tree, because their
        # expand events are linked so they must both exist
        self.rebuild_dashboard()
        if self.project:
            # TODO:  save last expanded state of project and reset to that
            # self._expand_tree_from_saved_state()
            # self.sys_tree.expandAll()
            self.sys_tree.expandToDepth(2)
        self.left_dock.setWidget(self.sys_tree)
        self.end_progress()
        self.set_system_model_window()

    def rebuild_dashboard(self):
        orb.log.info('* [pgxn] rebuild_dashboard()')
        if not self.sys_tree_rebuilt:
            orb.log.info('         sys_tree not rebuilt yet; not rebuilding.')
            return
        elif self.dashboard_rebuilt:
            # sys_tree has been rebuilt and dashboard has been rebuilt for this
            # sys_tree, so no need to rebuild
            orb.log.info('         dashboard already rebuilt; not rebuilding.')
            return
        orb.log.info('         + sys_tree rebuilt -- rebuilding dashboard ...')
        if getattr(self, 'dashboard_panel', None):
            orb.log.info('         + dashboard_panel exists ...')
            dashboard_layout = self.dashboard_panel.layout()
            if dashboard_layout.layout():
                orb.log.info('           dashboard_layout has a layout ...')
                orb.log.info('           clearing out old stuff ...')
                dashboard_title_layout = dashboard_layout.layout()
                dashboard_title_layout.removeWidget(self.dashboard)
                dashboard_title_layout.removeWidget(self.dash_select)
            if getattr(self, 'dashboard', None):
                self.dashboard.setAttribute(Qt.WA_DeleteOnClose)
                self.dashboard.close()
                self.dashboard = None
            orb.log.info('           destroying old dashboard_panel ...')
            self.dashboard_panel.setAttribute(Qt.WA_DeleteOnClose)
            self.dashboard_panel.close()
            self.dashboard_panel = None
        else:
            orb.log.info('         + no dashboard_panel exists ...')
        orb.log.info('           creating new dashboard panel ...')
        self.dashboard_panel = QtWidgets.QWidget(self)
        self.dashboard_panel.setMinimumSize(500, 200)
        self.dashboard_panel.size_policy = QtWidgets.QSizePolicy(
                                    QtWidgets.QSizePolicy.Preferred,
                                    QtWidgets.QSizePolicy.MinimumExpanding)
        dashboard_layout = QtWidgets.QVBoxLayout()
        dashboard_title_layout = QtWidgets.QHBoxLayout()
        self.dash_title = QtWidgets.QLabel()
        orb.log.info('           adding title ...')
        dashboard_title_layout.addWidget(self.dash_title)
        self.dash_select = QtWidgets.QComboBox()
        self.dash_select.setStyleSheet('font-weight: bold; font-size: 14px')
        for dash_name in prefs['dashboard_names']:
            self.dash_select.addItem(dash_name, QVariant)
        dash_idx = 0
        dash_name = state.get('dashboard_name') or prefs['dashboard_names'][0]
        if dash_name in prefs['dashboard_names']:
            dash_idx = prefs['dashboard_names'].index(dash_name)
        self.dash_select.setCurrentIndex(dash_idx)
        self.dash_select.activated.connect(self.set_dashboard)
        orb.log.info('           adding dashboard selector ...')
        dashboard_title_layout.addWidget(self.dash_select)
        dashboard_layout.addLayout(dashboard_title_layout)
        self.dashboard_panel.setLayout(dashboard_layout)
        self.top_dock_widget.setWidget(self.dashboard_panel)
        if getattr(self, 'sys_tree', None):
            orb.log.info('         + creating new dashboard tree ...')
            self.dashboard = SystemDashboard(self.sys_tree.model(),
                                             parent=self)
        else:
            orb.log.info('         + no sys_tree; using placeholder '
                         'for dashboard...')
            self.dashboard = QtWidgets.QLabel('No Project Selected')
            self.dashboard.setStyleSheet('font-weight: bold; font-size: 16px')
        self.dashboard.setFrameStyle(QtWidgets.QFrame.Panel |
                                     QtWidgets.QFrame.Raised)
        # self.dashboard.setMaximumSize(1000, 1000)
        self.dashboard.size_policy = QtWidgets.QSizePolicy(
                                        QtWidgets.QSizePolicy.Preferred,
                                        QtWidgets.QSizePolicy.Ignored)
        dashboard_layout.addWidget(self.dashboard)
        title = 'Systems Dashboard: <font color="purple">{}</font>'.format(
                                                               self.project.id)
        self.dash_title.setText(title)
        self.dash_title.setStyleSheet('font-weight: bold; font-size: 18px')
        self.dashboard_rebuilt = True

    def set_dashboard(self, index):
        """
        Set the dashboard state to the selected view.
        """
        state['dashboard_name'] = prefs['dashboard_names'][index]
        self.refresh_tree_and_dashboard()

    def refresh_dashboard(self):
        orb.log.info('* refreshing dashboard ...')
        if hasattr(self, 'dashboard'):
            for column in range(self.dashboard.model().columnCount(
                                                    QModelIndex())):
                self.dashboard.resizeColumnToContents(column)

    def update_object_in_trees(self, obj):
        """
        Update the tree and dashboard in response to a modified object.
        """
        orb.log.info('* [orb] update_object_in_tree() ...')
        if not obj:
            orb.log.info('  no object provided; ignoring.')
            return
        try:
            cname = obj.__class__.__name__
            idxs = []
            if cname in ['Acu', 'ProjectSystemUsage']:
                # for link objects, the modified link might not have the same
                # system/component, so we have to search for instances of the
                # link itself (rather than the system/component) in the tree.
                # NOTE: link_indexes_in_tree() returns *source* model indexes
                idxs = self.sys_tree.link_indexes_in_tree(obj)
                if idxs:
                    orb.log.info('  - indexes found in tree, updating ...')
                    if cname == 'Acu':
                        orb.log.info('  [obj is Acu]')
                        node_obj = obj.component
                    elif cname == 'ProjectSystemUsage':
                        orb.log.info('  [obj is PSU]')
                        node_obj = obj.system
                    for idx in idxs:
                        self.sys_tree.source_model.setData(idx, node_obj)
                else:
                    orb.log.info('  - no instances found in tree.')
            elif isinstance(obj, orb.classes['Product']):
                idxs = self.sys_tree.object_indexes_in_tree(obj)
                if idxs:
                    orb.log.info('  - instances found in tree, updating ...')
                    for idx in idxs:
                        self.sys_tree.source_model.dataChanged.emit(idx, idx)
                else:
                    orb.log.info('  - no instances found in tree.')
            # resize/refresh dashboard columns if necessary
            self.refresh_dashboard()
        except:
            # oops, sys_tree's C++ object got deleted
            orb.log.info('  - sys_tree C++ object might have got deleted '
                         '... bailing out!')

    ### SET UP 'component' mode (product modeler interface)

    def set_product_modeler_interface(self):
        orb.log.info('* setting product modeler interface')
        # update the model window
        self.set_system_model_window(self.product)
        self.top_dock_widget.setFloating(False)
        self.top_dock_widget.setFeatures(
                                QtWidgets.QDockWidget.NoDockWidgetFeatures)
        self.top_dock_widget.setVisible(True)
        if hasattr(self, 'dashboard_panel'):
            self.dashboard_panel.setVisible(False)
        self.setup_product_info_panel()
        self.top_dock_widget.setWidget(self.product_info_panel)
        self.right_dock.setVisible(True)
        # ********************************************************
        # left dock:  pgxnobject panel
        # ********************************************************
        # if there is a current left dock widget, destroy it
        ld_widget = self.left_dock.widget()
        if ld_widget:
            ld_widget.setAttribute(Qt.WA_DeleteOnClose)
            ld_widget.parent = None
            ld_widget.close()
        self.update_pgxn_obj_panel()
        self.left_dock.setWidget(self.pgxn_obj_panel)
        self.pgxn_obj_panel.show()
        self.left_dock.setVisible(True)

    ### SET UP 'system' mode (system modeler interface)

    def set_system_modeler_interface(self):
        orb.log.info('* setting system modeler interface')
        self.sys_tree_rebuilt = False
        self.dashboard_rebuilt = False
        # ********************************************************
        # system tree and dashboard
        # ********************************************************
        # refresh_tree_views() creates self.sys_tree if there isn't one
        self.refresh_tree_views()
        self.top_dock_widget.setFeatures(
                                QtWidgets.QDockWidget.DockWidgetFloatable)
        self.top_dock_widget.setVisible(True)
        self.top_dock_widget.setWidget(self.dashboard_panel)
        # TODO:  right dock contains libraries
        self.right_dock.setVisible(True)
        # run set_system_model_window() *AFTER* refreshing tree, so
        # that the model window will get all the remaining space
        # NOTE: EXPERIMENTALLY running set_system_model_window() as part of
        # refresh_tree_views()
        # self.set_system_model_window()

    def set_system_model_window(self, system=None):
        orb.log.debug('* [pgxn] setting system model window ...')
        if system:
            orb.log.info('  - using specified system {} ...'.format(
                                                                system.id))
            self.system_model_window = ModelWindow(obj=system,
                                                   logo=self.logo)
            self.setCentralWidget(self.system_model_window)
        elif self.project:
            psize = (600, 400)
            # if state.get('width') and state.get('height'):
                # w = int(float(state['width'])/2)
                # h = int(float(state['height'])/2)
                # psize = (w, h)
            self.system_model_window = ModelWindow(obj=self.project,
                                                   logo=self.logo,
                                                   preferred_size=psize)
            self.setCentralWidget(self.system_model_window)
        else:
            self.setCentralWidget(PlaceHolder(image=self.logo, min_size=300,
                                              parent=self))

    ### SET UP 'data' mode (currently deactivated ...)

    def set_data_interface(self):
        """
        Show data sets.  [Currently deactivated for re-implementation of data
        store without pandas/pytables/hdf5.]
        """
        orb.log.info('* setting data mode interface ...')
        # hide the top and right dock widgets
        self.top_dock_widget.setVisible(False)
        self.right_dock.setVisible(False)
        # ********************************************************
        # data view:  dataset_list (for selecting datasets)
        # ********************************************************
        self.dataset_list = AutosizingListWidget(parent=self)
        # size policy is set in the class AutosizingListWidget, so this is
        # unnecessary:
        # self.dataset_list.setSizePolicy(QtWidgets.QSizePolicy.Fixed,
                                        # QtWidgets.QSizePolicy.Expanding)
        self.dataset_list.currentRowChanged.connect(self.on_dataset_selected)
        # if there is a current left dock widget, destroy it
        ld_widget = self.left_dock.widget()
        if ld_widget:
            ld_widget.setAttribute(Qt.WA_DeleteOnClose)
            ld_widget.parent = None
            ld_widget.close()
        self.left_dock.setWidget(self.dataset_list)
        self.dataset_list.show()
        self.dataset_list.clear()
        # if orb.data_store.keys():
            # target_row = 0
            # # if hdf5 store has data, sync it up with self.datasets ...
            # # first, preserve the order of existing datasets
            # current_datasets = [n for n in self.datasets
                                # if '/'+n in orb.data_store.keys()]
            # for name in orb.data_store.keys():
                # if name[1:] not in current_datasets:
                    # # remove the leading '/' from hdf5 store key names
                    # # FIXME:  potential unicode whoopdeedoo
                    # current_datasets.append(str(name)[1:])
            # self.datasets = current_datasets
            # for name in self.datasets:
                # self.dataset_list.addItem(name)
            # if self.dataset and (self.dataset in self.datasets):
                # orb.log.debug('  - current dataset: {}'.format(self.dataset))
                # target_row = self.datasets.index(self.dataset)
            # elif self.datasets:
                # target_row = len(self.datasets) - 1
            # self.dataset_list.setCurrentRow(target_row)
        # else:
        self.datasets = []
        self.dataset_list.addItem('No Data')
        self.setCentralWidget(PlaceHolder(image=self.logo, min_size=300,
                                              parent=self))

    def on_dataset_selected(self, row):
        orb.log.info('* dataset selected')
        orb.log.debug('  - mode: "{}"'.format(self.mode))
        orb.log.debug('  - selected row: %i' % row)
        orb.log.debug('  - current dataset: {}'.format(self.dataset))
        orb.log.debug('  - current datasets: {}'.format(str(self.datasets)))
        if self.datasets and row >= 0:
            dataset_name = str(self.dataset_list.item(row).text())
            orb.log.debug('  - dataset: "%s"' % dataset_name)
            orb.log.debug(
                '  - calling select_dataset("%s")...' % dataset_name)
            self.select_dataset(dataset_name)
        else:
            orb.log.debug('    -> selected row < 0: selection aborted.')

    def select_dataset(self, dataset_name):
        orb.log.info('* selecting dataset "%s"' % dataset_name)
        # currently inactive -- orb.data_store is an empty dict
        df = orb.data_store.get(dataset_name)
        if df is not None:
            # set state to selected dataset
            self.dataset = dataset_name
            # TODO: if df is huge, use a generator form ...
            data = [OrderedDict(row) for i, row in df.iterrows()]
            tablemodel = ODTableModel(data, parent=self)
            proxy = NumericSortModel(parent=self)
            proxy.setSourceModel(tablemodel)
            tableview = QtWidgets.QTableView()
            tableview.setMinimumSize(300, 200)
            # disable sorting while loading data (which is in proxy)
            tableview.setSortingEnabled(False)
            tableview.setModel(proxy)
            tableview.setSortingEnabled(True)
            column_header = tableview.horizontalHeader()
            column_header.setSectionsMovable(True)
            cols = tablemodel.columns()
            # as a first cut, set col widths to header widths (use hints)
            for i, n in enumerate(cols):
                tableview.setColumnWidth(i, column_header.sectionSizeHint(i))
            # TODO:  use "field type" metadata to set specified col widths
            # if 'Category' in cols:
                # tableview.resizeColumnToContents(cols.index('Category'))
            tableview.resizeColumnsToContents()
            tableview.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                    QtWidgets.QSizePolicy.Expanding)
            self.setCentralWidget(tableview)

    ### SET UP 'db' mode

    def set_db_interface(self):
        orb.log.info('* setting db mode interface')
        # hide the top and right dock widgets and dashboard
        self.top_dock_widget.setVisible(False)
        self.right_dock.setVisible(False)
        if hasattr(self, 'dashboard_panel'):
            self.dashboard_panel.setVisible(False)
        if hasattr(self, 'product_info_panel'):
            self.product_info_panel.setVisible(False)
        # if there is a current left dock widget, remove and destroy it
        ld_widget = self.left_dock.widget()
        if ld_widget:
            ld_widget.setAttribute(Qt.WA_DeleteOnClose)
            ld_widget.parent = None
            ld_widget.close()
            # very important to set None: its C++ object is gone now ...
            self.cname_list = None
        # set current left dock widget to 'cname_list'
        # ********************************************************
        # db view:  class selection list (tables)
        # ********************************************************
        # cname_list (for selecting class names -> db tables)
        if not getattr(self, 'cname_list', None):
            self.cname_list = AutosizingListWidget(parent=self)
            self.cname_list.setSizePolicy(QtWidgets.QSizePolicy.Fixed,
                                          QtWidgets.QSizePolicy.Expanding)
            self.cname_list.currentRowChanged.connect(self.on_cname_selected)
        self.refresh_cname_list()
        self.left_dock.setWidget(self.cname_list)
        self.cname_list.show()

    def refresh_cname_list(self):
        self.cname_list.clear()
        for cname in self.cnames:
            self.cname_list.addItem(cname)
        cur_cname = state.get('current_cname')
        if cur_cname and cur_cname in self.cnames:
            target_idx = self.cnames.index(cur_cname)
        else:
            target_idx = 0
            cur_cname = self.cnames[0]
            state['current_cname'] = cur_cname
        self.cname_list.setCurrentRow(target_idx)
        if cur_cname:
            self.set_object_table_for(cur_cname)

    def on_cname_selected(self, idx):
        orb.log.info('* class selected')
        orb.log.debug('  - mode: "{}"'.format(self.mode))
        orb.log.debug('  - selected index: "%i"' % idx)
        # try:
        if idx == -1:
            cname = state.get('current_cname', 'HardwareProduct')
        else:
            cname = self.cnames[idx]
        state['current_cname'] = str(cname)
        orb.log.info('  - class: "%s"' % cname)
        self.set_object_table_for(cname)
        # except:
            # orb.log.info('  - set_object_table_for("%s") had an exception.'
                          # % cname)

    def set_object_table_for(self, cname):
        # TODO:  let view and sort_field be parameters
        orb.log.info('* setting object table for "%s"' % cname)
        objs = list(orb.get_by_type(cname))
        tableview = ObjectTableView(objs)
        self.setCentralWidget(tableview)
        self.object_tableview = tableview

    def show_about(self):
        # if app version is provided, use it; otherwise use ours
        version = self.app_version or __version__
        app_name = config.get('app_name', 'Pangalaxian')
        QtWidgets.QMessageBox.about(self, "Some call me...",
            '<html><p><b>{} {}</b></p></html>'.format(app_name, version))

    def show_help(self):
        ug_path = os.path.join(orb.home, 'doc', 'user_guide.html')
        help_url = urllib.parse.urljoin('file:', urllib.request.pathname2url(ug_path))
        help_widget = HelpWidget(help_url, parent=self)
        help_widget.show()

    def view_cad(self, file_path):
        orb.log.info('* view_cad({})'.format(file_path))
        viewer = Viewer3DDialog(self)
        viewer.show()
        viewer.view_cad(file_path)
        orb.log.info('  - displaying CAD model ...')

    def on_db_selected(self, selected, deselected):
        orb.log.info('* db selected [item: %i]' % selected.row())
        if deselected:
            orb.log.info('  - [deselected item: %i]' % deselected.row())

    def on_model_selected(self, selected, deselected):
        orb.log.info('* model selected [item: %i]' % selected.row())
        if deselected:
            orb.log.info('  - [deselected item: %i]' % deselected.row())

    def new_project(self):
        orb.log.info('* new_project()')
        proj = clone('Project')
        # NOTE:  use 'view' to restrict the fields in the interface; this
        # overrides the preconfigured default set of fields specified in
        # p.meta.meta.MAIN_VIEWS
        view = ['id', 'name', 'description']
        panels = ['main']
        pxo = PgxnObject(proj, edit_mode=True, new=True, view=view,
                         panels=panels, modal_mode=True, parent=self)
        pxo.show()

    def delete_project(self):
        """
        Delete a Project, removing it wherever it is referenced.
        """
        # TODO:  also remove ObjectAccess and RoleAssignment instances that
        # reference it -- or perhaps refuse to remove it if it has them?
        # TODO:  also remove it from the repository
        orb.log.info('* delete_project()')
        # first delete any ProjectSystemUsage relationships
        for psu in self.project.systems:
            orb.db.delete(psu)
        # if the project owns things, remove its ownership
        things = orb.search_exact(owner=self.project)
        for thing in things:
            thing.owner = None
        orb.save(things)
        for thing in things:
            dispatcher.send('modified object', obj=thing)
        oid = self.project.oid
        orb.db.delete(orb.get(oid))
        orb.db.commit()
        if len(self.projects) > 1:
            self.project = self.projects[-1]
            if self.project.oid == 'pgefobjects:SANDBOX':
                self.delete_project_action.setEnabled(False)
                self.delete_project_action.setVisible(False)
            # else:
                # self.delete_project_action.setVisible(True)
        else:
            self.project = orb.get('pgefobjects:SANDBOX')
            self.delete_project_action.setEnabled(False)
            self.delete_project_action.setVisible(False)

    def enable_collaboration(self):
        """
        Enable collaboration on a locally-defined Project, by adding it to the
        admin service.
        """
        # TODO: implement this!
        pass

    def new_parameter(self):
        # Parameter Definitions are *always* "public"
        param = clone('ParameterDefinition', public=True)
        pxo = PgxnObject(param, edit_mode=True, modal_mode=True, new=True,
                         parent=self)
        pxo.show()

    def new_product(self):
        """
        Display a dialog to create a new Product.  (Now simply calls
        new_product_wizard.)
        """
        orb.log.info('* [pgxn] new_product()')
        orb.log.info('         calling new_product_wizard() ...')
        self.new_product_wizard()

    def new_product_wizard(self):
        """
        Display New Product Wizard, a guided process to create new Product
        instances.
        """
        orb.log.info('* [pgxn] new_product_wizard()')
        wizard = NewProductWizard(parent=self)
        if wizard.exec_() == QtWidgets.QDialog.Accepted:
            orb.log.info('  [pgxn] New Product Wizard completed successfully.')
            product = orb.get(wizard_state.get('product_oid'))
            if product:
                self.product = product
                if getattr(wizard, 'pgxn_obj', None):
                    wizard.pgxn_obj.setAttribute(Qt.WA_DeleteOnClose)
                    wizard.pgxn_obj.parent = None
                    wizard.pgxn_obj.close()
                    wizard.pgxn_obj = None
                # switch to 'component' mode (in case not already there) ...
                self.component_mode_action.trigger()
        else:
            orb.log.info('  [pgxn] New Product Wizard cancelled.')
            oid = wizard_state.get('product_oid')
            # if wizard was canceled before saving the new product, oid will be
            # None and no object was created, so there is nothing to delete
            if oid:
                obj = orb.get(oid)
                cname = obj.__class__.__name__
                orb.delete([obj])
                dispatcher.send(signal='deleted object', oid=oid, cname=cname)

    def new_functional_requirement(self):
        wizard = ReqWizard(parent=self, performance=False)
        if wizard.exec_() == QtWidgets.QDialog.Accepted:
            orb.log.info('* reqt wizard completed.')
            req_oid = req_wizard_state.get('req_oid')
            req = orb.get(req_oid)
            if req and getattr(wizard, 'pgxn_obj', None):
                wizard.pgxn_obj.setAttribute(Qt.WA_DeleteOnClose)
                wizard.pgxn_obj.parent = None
                wizard.pgxn_obj.close()
                wizard.pgxn_obj = None
        else:
            orb.log.info('* reqt wizard cancelled.')
            if getattr(wizard, 'pgxn_obj', None):
                wizard.pgxn_obj.setAttribute(Qt.WA_DeleteOnClose)
                wizard.pgxn_obj.parent = None
                wizard.pgxn_obj.close()
                wizard.pgxn_obj = None

    def new_perform_requirement(self):
        wizard = ReqWizard(parent=self, performance=True)
        if wizard.exec_() == QtWidgets.QDialog.Accepted:
            orb.log.info('* reqt wizard completed.')
            if getattr(wizard, 'pgxn_obj', None):
                wizard.pgxn_obj.setAttribute(Qt.WA_DeleteOnClose)
                wizard.pgxn_obj.parent = None
                wizard.pgxn_obj.close()
                wizard.pgxn_obj = None
        else:
            orb.log.info('* reqt wizard cancelled...')
            if getattr(wizard, 'pgxn_obj', None):
                wizard.pgxn_obj.setAttribute(Qt.WA_DeleteOnClose)
                wizard.pgxn_obj.parent = None
                wizard.pgxn_obj.close()
                wizard.pgxn_obj = None

    def new_test(self):
        # TODO:  Wizard for Test?
        project_oid = state.get('project')
        if project_oid:
            proj = orb.get(project_oid)
        else:
            proj = None
        test = clone('Test', owner=proj)
        # modal_mode -> 'cancel' closes dialog
        panels = ['main', 'info', 'admin']
        pxo = PgxnObject(test, edit_mode=True, new=True, modal_mode=True,
                         panels=panels, parent=self)
        pxo.show()

    def new_product_type(self):
        product_type = clone('ProductType')
        view = ['id', 'name', 'abbreviation', 'description']
        panels = ['main']
        # modal_mode -> 'cancel' closes dialog
        pxo = PgxnObject(product_type, edit_mode=True, new=True, view=view,
                         panels=panels, modal_mode=True, parent=self)
        pxo.show()

    def parameter_library(self):
        view = ['id', 'name', 'range_datatype', 'dimensions', 'description']
        dlg = LibraryDialog('ParameterDefinition', view=view,
                            height=self.geometry().height(),
                            width=self.geometry().width()//2,
                            parent=self)
        dlg.show()

    def product_library(self):
        view = ['id', 'name', 'version', 'iteration', 'product_type',
                'description', 'comment']
        dlg = LibraryDialog('HardwareProduct', view=view,
                            height=self.geometry().height(),
                            width=(2 * self.geometry().width() / 3),
                            parent=self)
        dlg.show()

    def port_template_library(self):
        view = ['id', 'name', 'description', 'comment']
        dlg = LibraryDialog('PortTemplate', view=view,
                           width=self.geometry().width()//2,
                           height=self.geometry().height(), parent=self)
        dlg.show()

    def display_requirements_manager(self):
        project_oid = state.get('project') or 'pgefobjects:SANDBOX'
        proj = orb.get(project_oid)
        w = 4 * self.geometry().width() / 5
        h = self.geometry().height()
        dlg = RequirementManager(project=proj, width=w, height=h, parent=self)
        dlg.show()

    # def display_disciplines(self):
        # cname = 'Discipline'
        # objs = orb.get_by_type(cname)
        # dlg = FilterDialog(objs, label=get_external_name_plural(cname),
                           # height=self.geometry().height(), parent=self)
        # dlg.show()

    def display_product_types(self):
        view = ['id', 'name', 'description', 'comment']
        dlg = LibraryDialog('ProductType', view=view,
                            width=self.geometry().width()//2,
                            height=self.geometry().height(), parent=self)
        dlg.show()

    def export_data_to_file(self):
        pass
        # # TODO:  create a "wizard" dialog with some convenient defaults ...
        # # only open a file dialog if there is no filename yet
        # if not self.filename:
            # self.filename, filters = QtWidgets.QFileDialog.getSaveFileName(
                                                        # self, 'Export to File')
        # # append extension if not there yet
        # # TODO:  use extension based on export format option
        # if not str(self.filename).endswith(".xls"):
            # self.filename += ".xls"
        # # store the contents of the text file along with the format in html,
        # # which Qt does in a nice way ...
        # with open(self.filename, "wt") as file:
            # file.write(<function to export data to whatever>)

    def export_project_to_file(self):
        orb.log.info('* [pgxn] export_project_to_file() for {}'.format(
                 getattr(self.project, 'id', None) or '[no current project]'))
        # TODO:  create a "wizard" dialog with some convenient defaults ...
        dtstr = date2str(dtstamp())
        fpath, filters = QtWidgets.QFileDialog.getSaveFileName(
                                    self, 'Export Project to File',
                                    self.project.id + '-' + dtstr + '.yaml')
        if fpath:
            orb.log.info('  - file selected: "%s"' % fpath)
            fpath = str(fpath)    # QFileDialog fpath is unicode; make str
            state['last_path'] = os.path.dirname(fpath)
            # serialize all the objects relevant to the current project
            project_objects = orb.get_objects_for_project(self.project)
            serialized_objs = serialize(orb, project_objects,
                                        include_components=True)
            f = open(fpath, 'w')
            f.write(yaml.safe_dump(serialized_objs, default_flow_style=False))
            f.close()
            orb.log.info('    %i project objects written.' % len(
                                                        serialized_objs))
        else:
            return

    def export_reqts_to_file(self):
        orb.log.info('* [pgxn] export_reqts_to_file() for project {}'.format(
                 getattr(self.project, 'id', None) or '[no current project]'))
        # TODO:  create a "wizard" dialog with some convenient defaults ...
        dtstr = date2str(dtstamp())
        fname = self.project.id + '-requirements-'+ dtstr + '.yaml'
        fpath, filters = QtWidgets.QFileDialog.getSaveFileName(
                                self, 'Export Project Requirements to File',
                                fname)
        if fpath:
            orb.log.info('  - file selected: "%s"' % fpath)
            fpath = str(fpath)    # QFileDialog fpath is unicode; make str
            state['last_path'] = os.path.dirname(fpath)
            # serialize all the objects relevant to the current project
            reqts = orb.get_reqts_for_project(self.project)
            reqts += self.project
            if reqts:
                serialized_reqts = serialize(orb, reqts)
                f = open(fpath, 'w')
                f.write(yaml.safe_dump(serialized_reqts,
                                       default_flow_style=False))
                f.close()
                orb.log.info('    %i project requirements written.' % len(
                                                            serialized_reqts))
            else:
                # TODO: notify user that no requirements were found ...
                orb.log.info('    no project requirements found.')
                return
        else:
            return

    def import_reqts_from_file(self):
        orb.log.info('* [pgxn] import_reqts_from_file()')
        # TODO:
        # [1] create a "wizard" dialog with some convenient defaults ...
        # [2] replace Project in file with current Project
        data = None
        message = ''
        # TODO:  create a "wizard" dialog with some convenient defaults ...
        if not state.get('last_path'):
            state['last_path'] = ''
        # NOTE: can add filter if needed, e.g.: filter="(*.yaml)"
        dialog = QtWidgets.QFileDialog(self, 'Open File',
                                       directory=state['last_path'])
        fpath = ''
        if dialog.exec_():
            fpaths = dialog.selectedFiles()
            if fpaths:
                fpath = fpaths[0]
            dialog.close()
        if fpath:
            orb.log.info('  [pgxn] file path: {}'.format(fpath))
            if is_binary(fpath):
                message = "File '%s' is not importable." % fpath
                popup = QtWidgets.QMessageBox(
                            QtWidgets.QMessageBox.Warning,
                            "Wrong file type", message,
                            QtWidgets.QMessageBox.Ok, self)
                popup.show()
                return
            try:
                f = open(fpath)
                data = f.read()
                f.close()
                self.project_file_path = ''
            except:
                message = "File '%s' could not be opened." % fpath
                popup = QtWidgets.QMessageBox(
                            QtWidgets.QMessageBox.Warning,
                            "Error in file path", message,
                            QtWidgets.QMessageBox.Ok, self)
                popup.show()
                return
        else:
            # no file was selected
            return
        if data:
            try:
                sobjs = yaml.safe_load(data)
                # deserialize(orb, sobjs)
                byclass = {}
                for so in sobjs:
                    if byclass.get(so['_cname']):
                        byclass[so['_cname']].append(so)
                    else:
                        byclass[so['_cname']] = [so]
                if 'Project' in byclass:
                    projid = byclass['Project'][0].get('id', '')
                    if projid:
                        start_msg = 'Loading requirements for project'
                        start_msg += '{} ...'.format(projid)
                        message = "Success: project {} imported.".format(
                                                                    projid)
                    else:
                        start_msg = 'Loading project requirements ...'
                        message = "Your data has been imported."
                else:
                    start_msg = 'Loading project requirements ...'
                    message = "Your requirements have been imported."
                self.statusbar.showMessage(start_msg)
                self.pb.show()
                self.pb.setValue(0)
                self.pb.setMaximum(len(sobjs))
                i = 0
                for cname in DESERIALIZATION_ORDER:
                    if cname in byclass:
                        for so in byclass[cname]:
                            deserialize(orb, [so])
                            i += 1
                            self.pb.setValue(i)
                            self.statusbar.showMessage('{}: {}'.format(cname,
                                                         so.get('id', '')))
                        byclass.pop(cname)
                # deserialize any other classes ...
                if byclass:
                    for cname in byclass:
                        for so in byclass[cname]:
                            deserialize(orb, [so])
                            i += 1
                            self.pb.setValue(i)
                self.pb.hide()
                if not message:
                    message = "Your data has been imported."
                popup = QtWidgets.QMessageBox(
                            QtWidgets.QMessageBox.Information,
                            "Project Data Import", message,
                            QtWidgets.QMessageBox.Ok, self)
                popup.show()
                if hasattr(self, 'library_widget'):
                    self.library_widget.refresh()
                if hasattr(self, 'sys_tree'):
                    self.refresh_tree_and_dashboard()
                return
            except:
                message = "An error was encountered."
                popup = QtWidgets.QMessageBox(
                            QtWidgets.QMessageBox.Warning,
                            "Error in Data Import", message,
                            QtWidgets.QMessageBox.Ok, self)
                popup.show()
                return

    def import_objects(self):
        """
        Import a collection of serialized objects from a file (using a
        QFileDialog to select the file).
        """
        orb.log.info('* [pgxn] import_objects()')
        data = None
        message = ''
        # TODO:  create a "wizard" dialog with some convenient defaults ...
        if not state.get('last_path'):
            state['last_path'] = orb.test_data_dir
        # NOTE: can add filter if needed, e.g.: filter="(*.yaml)"
        dialog = QtWidgets.QFileDialog(self, 'Open File',
                                       directory=state['last_path'])
        fpath = ''
        if dialog.exec_():
            fpaths = dialog.selectedFiles()
            if fpaths:
                fpath = fpaths[0]
            dialog.close()
        if fpath:
            orb.log.info('  [pgxn] file path: {}'.format(fpath))
            if is_binary(fpath):
                message = "File '%s' is not importable." % fpath
                popup = QtWidgets.QMessageBox(
                            QtWidgets.QMessageBox.Warning,
                            "Wrong file type", message,
                            QtWidgets.QMessageBox.Ok, self)
                popup.show()
                return
            try:
                f = open(fpath)
                data = f.read()
                f.close()
                self.project_file_path = ''
            except:
                message = "File '%s' could not be opened." % fpath
                popup = QtWidgets.QMessageBox(
                            QtWidgets.QMessageBox.Warning,
                            "Error in file path", message,
                            QtWidgets.QMessageBox.Ok, self)
                popup.show()
                return
        else:
            # no file was selected
            return
        if data:
            try:
                sobjs = yaml.safe_load(data)
            except:
                message = "An error was encountered."
                popup = QtWidgets.QMessageBox(
                            QtWidgets.QMessageBox.Warning,
                            "Error in Data Import", message,
                            QtWidgets.QMessageBox.Ok, self)
                popup.show()
                return
            self.load_serialized_objects(sobjs)

    def load_serialized_objects(self, sobjs):
        if sobjs:
            byclass = {}
            message = ''
            for so in sobjs:
                if byclass.get(so['_cname']):
                    byclass[so['_cname']].append(so)
                else:
                    byclass[so['_cname']] = [so]
            if 'Project' in byclass:
                projid = byclass['Project'][0].get('id', '')
                if projid:
                    start_msg = 'Loading data for {} ...'.format(projid)
                    message = "Success: project {} imported.".format(projid)
                else:
                    start_msg = 'Loading data for your project ...'
                    message = "Your data has been imported."
            else:
                start_msg = 'Loading data for your project ...'
                message = "Your data has been imported."
            self.statusbar.showMessage(start_msg)
            self.pb.show()
            self.pb.setValue(0)
            self.pb.setMaximum(len(sobjs))
            i = 0
            user_is_me = (getattr(self.local_user, 'oid', None) == 'me')
            for cname in DESERIALIZATION_ORDER:
                if cname in byclass:
                    for so in byclass[cname]:
                        # if objs are still owned by 'me' but user has
                        # logged in and has a local_user object ...
                        if so.get('creator') == 'me' and not user_is_me:
                            so['creator'] = self.local_user.oid
                            so['modifier'] = self.local_user.oid
                        deserialize(orb, [so])
                        i += 1
                        self.pb.setValue(i)
                        self.statusbar.showMessage('{}: {}'.format(cname,
                                                       so.get('id', '')))
                    byclass.pop(cname)
            # deserialize any other classes ...
            if byclass:
                for cname in byclass:
                    for so in byclass[cname]:
                        # if objs are still owned by 'me' but user has
                        # logged in and has a local_user object ...
                        if so.get('creator') == 'me' and not user_is_me:
                            so['creator'] = self.local_user.oid
                            so['modifier'] = self.local_user.oid
                        deserialize(orb, [so])
                        i += 1
                        self.pb.setValue(i)
            self.pb.hide()
            if not message:
                message = "Your data has been imported."
            self.statusbar.showMessage(message)
            popup = QtWidgets.QMessageBox(
                        QtWidgets.QMessageBox.Information,
                        "Project Data Import", message,
                        QtWidgets.QMessageBox.Ok, self)
            popup.show()
            if hasattr(self, 'library_widget'):
                self.library_widget.refresh()
            if hasattr(self, 'sys_tree'):
                self.refresh_tree_and_dashboard()
            return
        else:
            message = "No data found."
            popup = QtWidgets.QMessageBox(
                        QtWidgets.QMessageBox.Warning,
                        "No data found.", message,
                        QtWidgets.QMessageBox.Ok, self)
            popup.show()
            return

    def load_test_objects(self):
        if not state.get('test_objects_loaded'):
            orb.log.info('* loading test objects ...')
            self.statusbar.showMessage('Loading test objects ... ')
            sobjs = create_test_users() + create_test_project()
            self.load_serialized_objects(sobjs)
            hw = orb.search_exact(cname='HardwareProduct', id_ns='test')
            orb.assign_test_parameters(hw)
            rfs = orb.search_exact(cname='RepresentationFile', id_ns='test')
            for rf in rfs:
                # look for the file and, if found, copy it ...
                if rf.url:
                    u = urllib.parse.urlparse(asciify(rf.url))
                    fpath = os.path.join(orb.test_data_dir, u.netloc)
                    if u.scheme == 'vault' and os.path.exists(fpath):
                        shutil.copy(fpath, orb.vault)
        else:
            orb.log.info('* test objects already loaded.')
            self.statusbar.showMessage('Test objects already loaded.')

    def output_mel(self):
        if self.project:
            if getattr(self.project, 'systems', None):
                dtstr = date2str(dtstamp())
                fpath, _ = QtWidgets.QFileDialog.getSaveFileName(
                                self, 'Open File',
                                self.project.id + '-MEL-' + dtstr + '.xlsx')
                if fpath:
                    write_mel_xlsx(self.project, file_path=fpath)
            else:
                message = "This project has no systems defined."
                popup = QtWidgets.QMessageBox(
                            QtWidgets.QMessageBox.Warning,
                            "No systems", message,
                            QtWidgets.QMessageBox.Ok, self)
                popup.show()
                return
        else:
            message = "You must select a project."
            popup = QtWidgets.QMessageBox(
                        QtWidgets.QMessageBox.Warning,
                        "No project selected", message,
                        QtWidgets.QMessageBox.Ok, self)
            popup.show()
            return

    def import_excel_data(self):
        # TODO:  list file format options -- use a "wizard" dialog
        # TODO:  load ALL data into a preview window, then let user select
        #        which row(s) are headers and which are data
        # TODO:  create either a toolbar or context menu (or both) with options
        # for adjusting column widths (and save as prefs) -- e.g.:
        #    tableview.setColumnWidth(i, 300)
        #    tableview.resizeColumnToContents(cols.index('Category'))
        if not state.get('last_path'):
            state['last_path'] = orb.test_data_dir
        fpath, filters = QtWidgets.QFileDialog.getOpenFileName(
                                    self, 'Open File',
                                    directory=state['last_path'])
        if fpath:
            # TODO: exception handling in case data import fails ...
            # TODO: add an "index" column for sorting, or else figure out how
            # to sort on the left header column ...
            fpath = str(fpath)    # QFileDialog fpath is unicode; make str
            if not (fpath.endswith('.xls') or fpath.endswith('.xlsx')):
                message = "File '%s' is not an Excel file." % fpath
                popup = QtWidgets.QMessageBox(
                            QtWidgets.QMessageBox.Warning,
                            "Wrong file type", message,
                            QtWidgets.QMessageBox.Ok, self)
                popup.show()
                return
            state['last_path'] = os.path.dirname(fpath)
            try:
                wizard = DataImportWizard(file_path=fpath, parent=self)
                wizard.exec_()
                orb.log.info('* import_excel_data: dialog completed:')
                orb.log.info('  setting mode to "data" (which updates view)')
                # set mode to "data"
                self.data_mode_action.trigger()
            except:
                message = "Data in '%s' could not be imported." % fpath
                popup = QtWidgets.QMessageBox(
                            QtWidgets.QMessageBox.Warning,
                            "An error occurred.", message,
                            QtWidgets.QMessageBox.Ok, self)
                popup.show()
                return
        else:
            return

    def open_step_file(self):
        orb.log.info('* opening a STEP file')
        # NOTE: for demo purposes ... actual function TBD
        if not state.get('last_path'):
            state['last_path'] = orb.test_data_dir
        fpath, filters = QtWidgets.QFileDialog.getOpenFileName(
                                    self, 'Open STEP File',
                                    state['last_path'],
                                    'STEP Files (*.stp *.step *.p21)')
        if fpath:
            # TODO: exception handling in case data import fails ...
            # TODO: add an "index" column for sorting, or else figure out how
            # to sort on the left header column ...
            state['last_path'] = os.path.dirname(fpath)
            orb.log.debug('  - calling view_cad({})'.format(fpath))
            orb.log.debug('    fpath type: {}'.format(type(fpath)))
            self.view_cad(fpath)
        else:
            return

    def set_current_project(self):
        orb.log.info('* set_current_project()')
        # NOTE:  will need to restrict the projects based on user's
        # authorizations ...
        projects = list(orb.get_by_type('Project'))
        if projects:
            dlg = ObjectSelectionDialog(projects, parent=self)
            dlg.make_popup(self.project_selection)
            # dlg.exec_() -> modal dialog
            if dlg.exec_():
                # dlg.exec_() being true means dlg was "accepted" (OK)
                # refresh project selection combo
                # and set the current project to the new project
                new_oid = dlg.get_oid()
                self.project = orb.get(new_oid)

    def edit_prefs(self):
        orb.log.info('* edit_prefs()')
        dlg = PrefsDialog(parent=self)
        if dlg.exec_():
            # TODO:  use 'clear_rows' setting for data imported in data mode
            prefs['clear_rows'] = dlg.get_clear_rows()
            prefs['dash_no_row_colors'] = not dlg.get_dash_row_colors()
            orb.log.info('  - edit_prefs dialog completed.')

    def do_admin_stuff(self):
        orb.log.info('* do_admin_stuff()')
        dlg = AdminDialog(org=self.project, parent=self)
        if dlg.exec_():
            orb.log.info('  - admin dialog completed.')

    # def compare_items(self):
        # # TODO:  this is just a mock-up for prototyping -- FIXME!
        # if state.get('test_objects_loaded'):
            # objs = orb.search_exact(id='HOG')
            # parms = state.get('dashboard', ['m[CBE]', 'P[CBE]', 'R_D[CBE]'])
            # widget = MatrixWidget(objs, parms, parent=self)
            # widget.show()

    def load_requirements(self):
        # TODO:  make this an excel import / map demo
        orb.log.info('* load_requirements()')
        if not state.get('last_path'):
            state['last_path'] = orb.test_data_dir

    def dump_database(self):
        orb.log.info('* dump_database()')
        orb.dump_db()

    def closeEvent(self, event):
        # things to do when window is closed
        # TODO:  save more MainWindow state (see p. 190 in PyQt book)
        state['mode'] = str(self.mode)
        state['width'] = self.geometry().width()
        state['height'] = self.geometry().height()
        # NOTE:  orb.data_store deactivated for reimplementation -- currently
        # it is just set to an empty dict
        # orb.data_store.close()
        self.statusbar.showMessage('saving parameters ...')
        orb._save_parmz()
        if orb.db.dirty:
            orb.db.commit()
        # save a serialized version of the db to vault/db.yaml
        self.statusbar.showMessage('Exporting local DB to vault...')
        if state.get('connected'):
            message_bus.session = None
            state['connected'] = False
        if diagramz:
            orb._save_diagramz()
        # if hasattr(self, 'system_model_window'):
            # self.system_model_window.cache_block_model()
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

def cleanup_and_save():
    write_config(os.path.join(orb.home, 'config'))
    write_prefs(os.path.join(orb.home, 'prefs'))
    write_state(os.path.join(orb.home, 'state'))
    write_trash(os.path.join(orb.home, 'trash'))

def run(home='', splash_image=None, test_data=None, use_tls=True,
        adminserv=True, console=False, debug=False, app_version=None):
    app = QtWidgets.QApplication(sys.argv)
    # app.setStyleSheet('QToolTip { border: 2px solid;}')
    app.setStyleSheet("QToolTip { color: #ffffff; "
                      "background-color: #2a82da; "
                      "border: 1px solid white; }")
    screen_resolution = app.desktop().screenGeometry()
    splash_image = splash_image or 'pangalacticon.png'
    # Create and display the splash screen
    # * if home is set, use image dir inside home
    splash_path = ''
    if home:
        splash_path = os.path.join(home, 'images', splash_image)
    x = screen_resolution.width() // 2
    y = screen_resolution.height() // 2
    # BEGIN importing and installing the reactor
    import qt5reactor
    qt5reactor.install()
    from twisted.internet import reactor
    # from twisted.internet.defer import setDebugging
    # END importing and installing the reactor
    if splash_path:
        splash_pix = QtGui.QPixmap(splash_path)
        splash = SplashScreen(splash_pix, center_point=QPoint(x, y))
        splash.show()
        # splash.showMessage('Starting ...')
        # processEvents() is needed for image to load
        app.processEvents()
        # TODO:  updates to showMessage() using thread/slot+signal
        main = Main(home=home, test_data=test_data, use_tls=use_tls,
                    console=console, debug=debug, reactor=reactor,
                    adminserv=adminserv, app_version=app_version)
        splash.finish(main)
    else:
        main = Main(home=home, test_data=test_data, use_tls=use_tls,
                    console=console, debug=debug, reactor=reactor,
                    adminserv=adminserv, app_version=app_version)
    main.show()
    atexit.register(cleanup_and_save)
    # run the reactor after creating the main window but before starting the
    # app -- using "runReturn" instead of reactor.run() here to enable the use
    # of app.exec_
    reactor.runReturn()
    # this should enable tracebacks instead of "Unhandled error in Deferred"
    # NOTE: these tracebacks are mostly relevant to protocol debugging
    # setDebugging(True)
    sys.exit(app.exec_())

    # **NOTE**
    # Since both PyQt and Twisted are based on event loops (in app.exec_() and
    # reactor.run(), respectively), one of them should drive the other. The
    # Twisted way is to let the reactor drive (hence we call
    # reactor.runReturn() first). Inside its implementation, qt5reactor takes
    # care of running an event loop in a way that dispatches events to both
    # Twisted and PyQt.


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--test', action='store_true',
                        help='test mode (send log output to console)')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='debug mode (verbose logging)')
    parser.add_argument('-n', '--noadmin', action='store_true',
                        help='no admin service available (use repo service)')
    parser.add_argument('-u', '--unencrypted', action='store_true',
                        help='use unencrypted transport (no tls)')
    options = parser.parse_args()
    tls = not options.unencrypted
    admin = not options.noadmin
    run(console=options.test, debug=options.debug, use_tls=tls,
        adminserv=admin)

