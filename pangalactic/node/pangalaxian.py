#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Pangalaxian (the PanGalactic GUI client) main window
"""
# NOTICE:
# Copyright 2022 United States Government as represented by the Administrator
# of the National Aeronautics and Space Administration.  No copyright is
# claimed in the United States under Title 17, U.S. Code.  All Other Rights
# Reserved.

# Disclaimer:
# No Warranty: THE SUBJECT SOFTWARE IS PROVIDED "AS IS" WITHOUT ANY WARRANTY OF
# ANY KIND, EITHER EXPRESSED, IMPLIED, OR STATUTORY, INCLUDING, BUT NOT LIMITED
# TO, ANY WARRANTY THAT THE SUBJECT SOFTWARE WILL CONFORM TO SPECIFICATIONS,
# ANY IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE,
# OR FREEDOM FROM INFRINGEMENT, ANY WARRANTY THAT THE SUBJECT SOFTWARE WILL BE
# ERROR FREE, OR ANY WARRANTY THAT DOCUMENTATION, IF PROVIDED, WILL CONFORM TO
# THE SUBJECT SOFTWARE. THIS AGREEMENT DOES NOT, IN ANY MANNER, CONSTITUTE AN
# ENDORSEMENT BY GOVERNMENT AGENCY OR ANY PRIOR RECIPIENT OF ANY RESULTS,
# RESULTING DESIGNS, HARDWARE, SOFTWARE PRODUCTS OR ANY OTHER APPLICATIONS
# RESULTING FROM USE OF THE SUBJECT SOFTWARE.  FURTHER, GOVERNMENT AGENCY
# DISCLAIMS ALL WARRANTIES AND LIABILITIES REGARDING THIRD-PARTY SOFTWARE, IF
# PRESENT IN THE ORIGINAL SOFTWARE, AND DISTRIBUTES IT "AS IS."
# Waiver and Indemnity: RECIPIENT AGREES TO WAIVE ANY AND ALL CLAIMS AGAINST
# THE UNITED STATES GOVERNMENT, ITS CONTRACTORS AND SUBCONTRACTORS, AS WELL AS
# ANY PRIOR RECIPIENT.  IF RECIPIENT'S USE OF THE SUBJECT SOFTWARE RESULTS IN
# ANY LIABILITIES, DEMANDS, DAMAGES, EXPENSES OR LOSSES ARISING FROM SUCH USE,
# INCLUDING ANY DAMAGES FROM PRODUCTS BASED ON, OR RESULTING FROM, RECIPIENT'S
# USE OF THE SUBJECT SOFTWARE, RECIPIENT SHALL INDEMNIFY AND HOLD HARMLESS THE
# UNITED STATES GOVERNMENT, ITS CONTRACTORS AND SUBCONTRACTORS, AS WELL AS ANY
# PRIOR RECIPIENT, TO THE EXTENT PERMITTED BY LAW.  RECIPIENT'S SOLE REMEDY FOR
# ANY SUCH MATTER SHALL BE THE IMMEDIATE, UNILATERAL TERMINATION OF THIS
# AGREEMENT.

# to ensure no output unless specified ...
import sys
import os

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import argparse, atexit, json, math, shutil
import time, webbrowser
# import traceback
import urllib.parse, urllib.request, urllib.error
from datetime import timedelta
from functools import partial
from pathlib  import Path

# autobahn
from autobahn.wamp import cryptosign

# binaryornot
from binaryornot.check import is_binary

from pydispatch import dispatcher
# Louie (formerly known as PyDispatcher) is deprecated
# from pydispatch import dispatcher

# packaging
from packaging.version import InvalidVersion, Version

# ruamel_yaml
import ruamel_yaml as yaml

# PyNaCl
from nacl.public import PrivateKey

# twisted
from twisted.internet.defer import DeferredList
from twisted.internet._sslverify import OpenSSLCertificateAuthorities
from twisted.internet.ssl import CertificateOptions
from OpenSSL import crypto

# fix qt import error -- import this before importing anything in PyQt5
from pangalactic.node import fix_qt_import_error

# fix Mac Big Sur qt problem -- set before importing PyQt stuff
if sys.platform == 'darwin':
    os.environ['QT_MAC_WANTS_LAYER'] = '1'

# PyQt5
from PyQt5.QtCore import Qt, QModelIndex, QPoint, QTimer, QVariant
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import (QAction, QActionGroup, QApplication, QCheckBox,
                             QComboBox, QDockWidget, QFileDialog, QFrame,
                             QHBoxLayout, QLabel, QMainWindow, QMessageBox,
                             QDialog, QProgressBar, QSizePolicy, QStyleFactory,
                             QVBoxLayout, QWidget)

# sets "orb" to uberorb.orb, so that
# "from pangalactic.core import orb" imports p.core.uberorb.orb
import pangalactic.core.set_uberorb

# pangalactic
from pangalactic.core                  import __version__
from pangalactic.core                  import diagramz, orb
from pangalactic.core                  import config, write_config
from pangalactic.core                  import get_user_home
from pangalactic.core                  import prefs, write_prefs
from pangalactic.core                  import state, write_state
from pangalactic.core                  import trash, write_trash
from pangalactic.core                  import (deletion_queue,
                                               write_deletion_queue)
from pangalactic.core                  import (parm_del_queue,
                                               write_parm_del_queue)
from pangalactic.core.access           import (get_perms,
                                               is_global_admin,
                                               is_reference_data)
from pangalactic.core.clone            import clone
from pangalactic.core.datastructures   import chunkify
from pangalactic.core.meta             import asciify
from pangalactic.core.names            import get_external_name_plural
from pangalactic.core.parametrics      import (data_elementz,
                                               add_parameter,
                                               add_data_element,
                                               delete_parameter,
                                               delete_data_element,
                                               mode_defz, parameterz,
                                               recompute_parmz,
                                               set_modal_context,
                                               save_data_elementz, save_parmz,
                                               set_dval)
from pangalactic.core.refdata          import ref_oids, ref_pd_oids
from pangalactic.core.serializers      import (DESERIALIZATION_ORDER,
                                               deserialize, serialize,
                                               uncook_datetime)
from pangalactic.core.test.utils       import (create_test_project,
                                               create_test_users)
from pangalactic.core.utils.datetimes  import dtstamp, date2str
from pangalactic.core.utils.reports    import write_mel_xlsx_from_model
from pangalactic.core.validation       import check_for_cycles, get_level_count
from pangalactic.node.admin            import AdminDialog, PersonSearchDialog
from pangalactic.node.buttons          import ButtonLabel, MenuButton
from pangalactic.node.cad.viewer       import Model3dDialog, Model3DViewer
from pangalactic.node.conops           import ConOpsModeler
# from pangalactic.node.dashboards       import SystemDashboard
from pangalactic.node.dashboards       import MultiDashboard
from pangalactic.node.dialogs          import (FullSyncDialog,
                                               LoginDialog,
                                               NotificationDialog,
                                               ObjectSelectionDialog,
                                               ParmDefsDialog,
                                               PrefsDialog,
                                               PrepareForOfflineDialog,
                                               ProgressDialog, VersionDialog)
from pangalactic.node.filters          import FilterPanel, ProductFilterDialog
from pangalactic.node.interface42      import SC42Window
from pangalactic.node.libraries        import (LibraryDialog,
                                               CompoundLibraryWidget,
                                               select_product_types)
from pangalactic.node.message_bus      import PgxnMessageBus
from pangalactic.node.blockmodeler     import ModelWindow, ProductInfoPanel
from pangalactic.node.pgxnobject       import PgxnObject
from pangalactic.node.rqtmanager       import RequirementManager
from pangalactic.node.rqtwizard        import RqtWizard, rqt_wizard_state
from pangalactic.node.splash           import SplashScreen
from pangalactic.node.startup          import setup_dirs_and_state
from pangalactic.node.systemtree       import SystemTreeView
# CompareWidget is only used in compare_items(), which is temporarily removed
# from pangalactic.node.tableviews       import CompareWidget
# from pangalactic.node.tableviews       import ObjectTableView
from pangalactic.node.threads          import threadpool, Worker
from pangalactic.node.widgets          import (AutosizingListWidget, Gripper,
                                               ModeLabel, PlaceHolder)
from pangalactic.node.wizards          import (NewProductWizard,
                                               DataImportWizard,
                                               wizard_state)


def safe_version(txt):
    """
    Convert a version string to a Version, returning None if it cannot be
    parsed.

    Version strings reach the client from sources that can be empty, absent,
    or corrupted -- the "VERSION" file in the app home directory (which a
    crash or a full disk mid-write can leave empty) and the "min_version"
    element of the vger.get_user_roles() result (which falls back to '' when
    the server does not respond).  Version() raises InvalidVersion for both,
    so callers use this and treat None as "unknown".

    Args:
        txt (str):  the version string to convert

    Returns:
        Version or None:  the parsed version, or None if unparseable
    """
    try:
        return Version((txt or '').strip())
    except InvalidVersion:
        return None


class Main(QMainWindow):
    """
    Main window of the 'Pangalaxian' client gui.

    Attributes:
        home (str):           full path of the app home directory
        app_base_name (str):  base name of the app; default: "Pangalaxian";
                              release_mode will be appended if "dev" or "test"
        app_version (str):    version of the app (if any)
        release_mode (str):   release status: production, dev, or test
        host (str):           the host to connect to [default: localhost])
        port (str):           the port to connect to [default: 8080])
        auth_method (str):    authentication method ("cryptosign" or "ticket")
        auto (bool):          whether to automatically connect to the
                              repository at startup (default: True)
        library_widget (CompoundLibraryWidget):  a panel widget containing
                              library views for specified classes and a
                              selector (combo box)
        project (Project):    currently selected project (its oid is persisted
                              as `project` in the `state` dict)
        projects (list of Project):  current authorized Projects in db
                              (a read-only property linked to the local db)
        project_oids (list of str):  oids of the current project objects, used
                              in calling vger.get_parmz() to update parameters
                              of the current project objects [added 2022-11-09]
        sys_tree (SystemTreeView):  the system tree widget (in left dock)
        reactor (qt5reactor): twisted event loop
        roles (list of dicts): actually, role assignments -- a list of dicts
                              of the form {org oid : role name}
        use_tls (bool):       use tls to connect to message bus
    """
    # enumeration of modes
    modes = ['system', 'component', 'db', 'data']

    # compatible release versions -- used to determine compatibility of the
    # "home" directory
    compat_versions = [
                       Version('4.4.dev3')
                       ]
    # signals
    # remote_deleted_object = pyqtSignal(str, str)  # args: oid, cname

    def __init__(self, app_base_name='Pangalaxian', app_version='',
                 release_mode='', home='', host=None, port=None,
                 auth_method='cryptosign', key_file_name=None, cert=False,
                 auto=True, mode= '', test_data=None, width=None, height=None,
                 use_tls=True, reactor=None, console=False, debug=False):
        """
        Initialize main window.

        Keyword Args:
            app_base_name (str): base name of the app; default: "Pangalaxian";
                                 the full app name will have release_mode
                                 appended if it is "dev" or "test"
            app_version (str):   version string
            release_mode (str):  release status: production, dev, or test
            home (str):          full path of the app home directory
            host (str):          the host to connect to [default: localhost])
            port (str):          the port to connect to [default: 8080])
            auth_method (str):   authentication method ("cryptosign", "ticket")
            key_file_name (str): name of file holding the user's private key
            cert (bool):         if True, the server uses a self-signed cert
            auto (bool):         whether to automatically connect to the
                                 repository at startup (default: True)
            console (bool):      if True: send log messages to stdout
                                          (*and* log file)
                                 else:    send stdout and stderr to the logger
            debug (bool):        set log level to DEBUG
            height (int):        height of main window
                                 (default: max of (screen h - 200) or 600)
            reactor (Reactor):   twisted Reactor instance
            test_data (list):    list of serialized test objects (dicts)
            use_tls (bool):      use tls to connect to message bus
            width (int):         width of main window
                                 (default: max of (screen w - 300) or 1000)
        """
        super().__init__(parent=None)
        ###################################################
        # this enables tooltips for inactive child windows ...
        self.setAttribute(Qt.WA_AlwaysShowToolTips)
        self.app_name = config.get('app_name')
        self.app_base_name = app_base_name or "Pangalaxian"
        if not self.app_name:
            # if app_name is not pre-configured, construct it from
            # app_base_name
            if release_mode in ['dev', 'test']:
                self.app_name = self.app_base_name + '_' + release_mode
            else:
                # for production releases, app_name == app_base_name
                self.app_name = self.app_base_name
        config['app_name'] = self.app_name
        config['app_base_name'] = self.app_base_name
        if host:
            config['host'] = host
        if port:
            try:
                config['port'] = int(port)
            except:
                pass
        self.splash_msg = ''
        self.add_splash_msg('Starting ...')
        self.channels = []
        self.key_file_name = key_file_name
        self.reactor = reactor
        self.use_tls = use_tls
        self.auth_method = auth_method
        self.app_version = app_version
        self.sys_tree_rebuilt = False
        self.dashboard_rebuilt = False
        self.project_oids = []
        # the "client" state is needed to enable the 'access' module to
        # differentiate permissions between client and server
        state['client'] = True
        # initialize internal "_product" attr, so getter for "product" (i.e.,
        # the subject of the Component Modeler mode) works
        # initialize internal "_product" attr, so getter for "product" works
        self._product = None
        # set flag to monitor when connecting to server
        self.attempting_to_connect = False
        # self.synced is set by dtstamp() when sync_with_services() is called
        self.synced = None
        # dict for states obtained from self.saveState() -- used for saving the
        # window state when switching between modes
        self.main_states = {}
        # if a home directory exists, check its version for compatibility ...
        compat_home_version = True
        home_version = Version('3.1')
        version_fpath = os.path.join(home, 'VERSION')
        if os.path.exists(home):
            if os.path.exists(version_fpath):
                with open(version_fpath) as f:
                    # NOTE: an empty or corrupted VERSION file (a plausible
                    # result of a crash or a full disk mid-write) is treated
                    # as an unknown -- and therefore incompatible -- version,
                    # so it degrades into the cleanup path below rather than
                    # raising InvalidVersion and aborting startup
                    home_version = safe_version(f.read()) or home_version
            if home_version not in self.compat_versions:
                compat_home_version = False
        if compat_home_version:
            msg = f'... home version ok: {home_version} ...'
            self.add_splash_msg(msg)
        else:
            msg = f'... home non-compatible: {home_version} ...'
            self.add_splash_msg(msg)
            # remove VERSION, local.db, onto, cache, all .json files
            if os.path.exists(version_fpath):
                os.remove(version_fpath)
            localdb_path = os.path.join(home, 'local.db')
            if os.path.exists(localdb_path):
                os.remove(localdb_path)
            cache_path = os.path.join(home, 'cache')
            if os.path.exists(cache_path):
                shutil.rmtree(cache_path)
            onto_path = os.path.join(home, 'onto')
            if os.path.exists(onto_path):
                shutil.rmtree(onto_path)
            fnames = os.listdir(home)
            for fname in fnames:
                if fname.endswith('.json'):
                    os.remove(os.path.join(home, fname))
            self.add_splash_msg('... home fixed ...')
        # =====================================================================
        # start up the orb and do some orb stuff, including setting the home
        # directory and related directories (added to state)
        orb.start(home=home, console=console, debug=debug)
        self.add_splash_msg('... database initialized ...')
        # orb.start() calls load_reference_data(), which includes parameter
        # definitions ... load_reference_data() also loads the data from
        # "parameters.json" and "data_elements.json" into the "parameterz" and
        # "data_elementz" caches -- if either of the those .json files is
        # missing or unreadable, the user will be informed at startup that
        # parameters and/or data_elements will be unavailable until the next
        # repository sync.
        setup_dirs_and_state()
        self.get_or_create_local_user()
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
        self.sandbox = orb.get('pgefobjects:SANDBOX')
        if not state.get('system') or isinstance(state['system'], str):
            state['system'] = {}
        state['synced_projects'] = []
        state['connected'] = False
        if not prefs.get('dashboard_names'):
            prefs['dashboard_names'] = ['MEL']
        if not state.get('dashboard_name'):
            state['dashboard_name'] = prefs['dashboard_names'][0]
        # ---------------------------------------------------------------------
        # NOTE: a cert file is only needed for a self-signed certificate -- if
        # the server is using a CA-signed cert, there is no server_cert.pem
        # ---------------------------------------------------------------------
        self.cert_path = None
        if cert:
            # argument from cmd line overrides and sets config
            config['self_signed_cert'] = True
        cert_fname = 'server_cert.pem'
        if config.get('self_signed_cert'):
            cert_path = os.path.join(orb.home, cert_fname)
            if os.path.exists(cert_path):
                orb.log.debug('    server cert found in orb home dir.')
                self.cert_path = cert_path
            else:
                # if not in home dir, try cwd
                if os.path.exists(cert_fname):
                    orb.log.debug('    server cert found in current dir.')
                    shutil.copy(cert_fname, os.path.join(orb.home, cert_fname))
                    self.cert_path = os.path.join(orb.home, cert_fname)
                else:
                    orb.log.debug('    server cert not found ...')
                    orb.log.debug('    config "self_signed_cert" requires one')
        else:
            config['self_signed_cert'] = False
        # set "auto" for auto-connect ...
        if 'auto' in prefs:
            self.auto = prefs['auto']
            orb.log.debug(f'* using "auto-connect" pref: {self.auto}')
        else:
            self.auto = auto
            orb.log.debug(f'* no "auto-connect" pref, setting to {self.auto}')
            prefs['auto'] = auto
        # initialize 'sys_tree_expansion' in case it has not been set yet ...
        if not state.get('sys_tree_expansion'):
            state['sys_tree_expansion'] = {}
        # self.mode_widget_actions is a mapping from modes (see below) to the
        # actions of toolbar widgets that are visible in each mode
        self.mode_widget_actions = dict((mode, set()) for mode in self.modes)
        self.mode_widget_actions['all'] = set()  # for actions visible in all modes
        # NOTE: the following function calls are *very* order-dependent!
        self._create_actions()
        orb.log.debug('*** projects:  %s' % str([p.id for p in self.projects]))
        self.add_splash_msg('... projects identified ...')
        screen_resolution = QApplication.desktop().screenGeometry()
        default_width = min(screen_resolution.width(), 1650)
        default_height = min(screen_resolution.height(), 800)
        width = state.get('width') or default_width
        height = state.get('height') or default_height
        self._init_ui(width, height)
        state['width'] = width
        state['height'] = height
        # set state vars related to sync processes ...
        state['role_asgts_received'] = False
        state['user_objs_sync_completed'] = False
        state['library_sync_completed'] = False
        # self.create_timer()
        # self.remote_deleted_object.connect(self.on_remote_deleted_object)
        # connect dispatcher signals ...
        dispatcher.connect(self.on_units_set, 'units set')
        dispatcher.connect(self.on_toggle_library_size,
                                                    'toggle library size')
        dispatcher.connect(self.on_log_info_msg, 'log info msg')
        dispatcher.connect(self.on_log_debug_msg, 'log debug msg')
        dispatcher.connect(self.on_system_selected_signal, 'system selected')
        dispatcher.connect(self.on_sys_node_selected_signal,
                                                         'sys node selected')
        dispatcher.connect(self.on_display_object_signal, 'display object')
        dispatcher.connect(self.on_new_rqt_signal, 'new rqt')
        dispatcher.connect(self.on_new_hardware_clone, 'new hardware clone')
        dispatcher.connect(self.on_new_object_signal, 'new object')
        dispatcher.connect(self.on_mod_object_signal, 'modified object')
        # "updated objects" will be a lightweight alternative to
        # "modified objects"
        # dispatcher.connect(self.on_updated_object_signal, 'updated objects')
        dispatcher.connect(self.on_act_mods_signal, 'act mods')
        dispatcher.connect(self.on_new_objects_signal, 'new objects')
        dispatcher.connect(self.on_mod_objects_signal, 'modified objects')
        dispatcher.connect(self.on_freeze_signal, 'freeze')
        dispatcher.connect(self.on_thaw_signal, 'thaw')
        dispatcher.connect(self.on_de_del, 'de del')
        dispatcher.connect(self.on_deleted_object_signal, 'deleted object')
        dispatcher.connect(self.on_parms_set, 'parms set')
        dispatcher.connect(self.on_parm_del, 'parm del')
        dispatcher.connect(self.on_parm_added, 'parm added')
        dispatcher.connect(self.get_parmz, 'get parmz')
        dispatcher.connect(self.on_comp_mode_datum_set, 'comp mode datum set')
        dispatcher.connect(self.on_mode_defs_edited, 'update mode defs')
        dispatcher.connect(self.on_mode_defs_edited, 'modes edited')
        # NOTE: "power modes udpated" signal can be ignored here because
        # currently there is no "System Power Modes" dashboard in pgxn ...
        # dispatcher.connect(self.on_power_modes_updated, 'power modes updated')
        dispatcher.connect(self.on_new_project_signal, 'new project')
        dispatcher.connect(self.mod_dashboard, 'dashboard mod')
        dispatcher.connect(self.on_parm_recompute, 'parameters recomputed')
        dispatcher.connect(self.refresh_tree_and_dashboard,
                                                    'refresh tree and dash')
        # dispatcher.connect(self.rebuild_dash_selector, 'dash pref set')
        # dispatcher.connect(self.on_ldap_search, 'ldap search')
        dispatcher.connect(self.on_add_person, 'add person')
        dispatcher.connect(self.on_update_person, 'update person')
        dispatcher.connect(self.on_delete_person, 'delete person')
        dispatcher.connect(self.on_get_people, 'get people')
        dispatcher.connect(self.set_new_object_table_view,
                                                'new object table view pref')
        dispatcher.connect(self.on_rqts_imported, 'rqts imported from excel')
        dispatcher.connect(self.on_add_update_model, 'add update model')
        dispatcher.connect(self.on_add_update_doc, 'add update doc')
        dispatcher.connect(self.download_file, 'download file')
        dispatcher.connect(self.open_doc_file, 'open doc file')
        dispatcher.connect(self.get_lom_surf_names, 'get lom surface names')
        dispatcher.connect(self.get_lom_structure, 'get lom structure')
        dispatcher.connect(self.get_lom_parms, 'refresh lom parms')
        # NOTE: 'remote: decloaked' is the normal way for the repository
        # service to announce new objects -- EVEN IF CLOAKING DOES NOT APPLY TO
        # THE TYPE OF OBJECT ANNOUNCED!  (E.g., Acu, RoleAssignment)
        dispatcher.connect(self.on_drop_product, 'drop on product info')
        dispatcher.connect(self.on_drill_down, 'diagram object drill down')
        dispatcher.connect(self.on_comp_back, 'comp modeler back')
        # connect dispatcher signals for message bus events
        dispatcher.connect(self.on_mbus_joined, 'onjoined')
        dispatcher.connect(self.on_mbus_disconnect, 'ondisconnect')
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
        state['done_with_progress'] = False
        parm_des_unavail = ''
        parms_unavail = orb.parmz_status in ['fail', 'not found']
        des_unavail = orb.data_elementz_status in ['fail', 'not found']
        if parms_unavail and des_unavail:
            parm_des_unavail = 'Parameters and Data Elements are unavailable'
        elif parms_unavail:
            parm_des_unavail = 'Parameters are unavailable'
        elif des_unavail:
            parm_des_unavail = 'Data Elements are unavailable'
        # detect whether we have logged into the repository ...
        if not (state.get('local_user_oid', 'me') == 'me'):
            # if still "me", then either it is initial startup or we have not
            # yet logged into the repo -- in either case don't worry about the
            # parameter or data element caches as they are not yet meaningful
            if parm_des_unavail:
                # parameters or data elements for non-reference data are
                # unavailable until next repo sync
                html = f'<p><b><font color="red">{parm_des_unavail}</font>'
                html += '</b></p><p><b>They will be restored during the next'
                html += 'login and repository sync process.</b></p>'
                dlg = NotificationDialog(html, news=False, parent=self)
                dlg.show()

    def set_auto_pref(self):
        """
        Set the preference for auto-connect.
        """
        if self.auto_cb.isChecked():
            orb.log.debug('* setting auto-connect pref to True.')
            prefs['auto'] = True
        else:
            orb.log.debug('* setting auto-connect pref to False.')
            prefs['auto'] = False

    def auto_connect(self):
        """
        Called by this module's run() method after main.show()
        """
        if self.auto:
            if (self.auth_method == 'cryptosign'
                and os.path.exists(self.key_path)):
                self.connect_to_bus_action.setChecked(True)
                QTimer.singleShot(0, self.set_bus_state)
            # message = f'<b>Auto-connect is enabled -- connect to the'
            # message += 'Repository now?</b>'
            # conf_dlg = QMessageBox(QMessageBox.Warning,
                         # "Connect?", message,
                         # QMessageBox.Yes | QMessageBox.No)
            # response = conf_dlg.exec_()
            # if response == QMessageBox.No:
                # conf_dlg.close()
                # return
            # elif response == QMessageBox.Yes:
                # conf_dlg.close()

    def on_log_info_msg(self, msg=''):
        orb.log.info(msg)

    def on_log_debug_msg(self, msg=''):
        orb.log.debug(msg)

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
        else:
            me = orb.get('me')
            if me:
                # if "me" Person exists, use it
                self.local_user = me
            else:
                # otherwise, create me ...
                orb.startup_msg = '* creating local user "me" object ...'
                local_user = clone('Person')
                local_user.oid = 'me'
                local_user.id = 'me'
                local_user.name = 'Me'
                orb.save([local_user])
                self.local_user = local_user
        state['local_user_oid'] = self.local_user.oid

    def set_bus_state(self):
        """
        Handler for checkable "Repository Service" button in the toolbar:
        connect to or disconnect from the message bus (crossbar server).
        """
        orb.log.debug('* setting message bus state ...')
        if not config.get('host'):
            config['host'] = 'localhost'
        host = config['host']
        if not config.get('port'):
            config['port'] = 8080
        port = config['port']
        url = f'wss://{host}:{port}/ws'
        if self.connect_to_bus_action.isChecked():
            ###########################################################
            # Initialize message bus instance
            ###########################################################
            self.attempting_to_connect = True
            self.mbus = PgxnMessageBus()

            @self.mbus.signal('onjoined')
            def onjoined():
                orb.log.info('* mbus "onjoined" event received ...')
                dispatcher.send(signal='onjoined')

            if self.auth_method == 'cryptosign':
                orb.log.info('* using "cryptosign" (public key) auth ...')
                if not os.path.exists(self.key_path):
                    message = f'Key file <{self.key_path}> not found ... '
                    message += 'operating in local-only mode.'
                    popup = QMessageBox(QMessageBox.Warning,
                                        "No certificate", message,
                                        QMessageBox.Ok, self)
                    popup.show()
                    self.connect_to_bus_action.setChecked(False)
                else:
                    self.mbus.set_key_path(self.key_path)
                    tls_options = None
                    if self.use_tls:
                        orb.log.debug('  - using tls ...')
                        if config.get('self_signed_cert') and self.cert_path:
                            orb.log.debug('  - with self-signed cert ...')
                            cert = crypto.load_certificate(
                                        crypto.FILETYPE_PEM,
                                        open(self.cert_path, 'r').read())
                            # ---------------------------------------------
                            # NOTE: trustRoot arg is only needed when using
                            # a self-signed certificate ...
                            # ---------------------------------------------
                            tls_options = CertificateOptions(
                                trustRoot=OpenSSLCertificateAuthorities(
                                                                [cert]))
                            url = 'wss://{}:{}/ws'.format(host, port)
                        else:
                            orb.log.debug('  - no self-signed cert.')
                            tls_options = CertificateOptions()
                            url = 'wss://{}:{}/ws'.format(host, port)
                    else:
                        orb.log.debug('  - not using tls ...')
                        url = 'ws://{}:{}/ws'.format(host, port)
                    orb.log.debug('  - setting up connection ...')
                    self.mbus.run(url, auth_method='cryptosign',
                                  realm='pangalactic-services',
                                  start_reactor=False, ssl=tls_options)
            else:  # password ("ticket") auth
                orb.log.info('* using "ticket" (userid/password) auth ...')
                login_dlg = LoginDialog(userid=state.get('userid', ''),
                                        parent=self)
                if login_dlg.exec_() == QDialog.Accepted:
                    state['userid'] = asciify(login_dlg.userid)
                    self.mbus.set_authid(login_dlg.userid)
                    self.mbus.set_passwd(login_dlg.passwd)
                    tls_options = None
                    if self.use_tls:
                        orb.log.debug('  - using tls ...')
                        if self.cert_path:
                            orb.log.debug('  -  with self-signed cert ...')
                            cert = crypto.load_certificate(
                                            crypto.FILETYPE_PEM,
                                            open(self.cert_path, 'r').read())
                            tls_options = CertificateOptions(
                                trustRoot=OpenSSLCertificateAuthorities([cert]))
                            url = 'wss://{}:{}/ws'.format(host, port)
                        else:
                            orb.log.debug('  - no self-signed cert.')
                            tls_options = CertificateOptions()
                            url = 'wss://{}:{}/ws'.format(host, port)
                    else:
                        orb.log.debug('  - not using tls ...')
                        url = 'ws://{}:{}/ws'.format(host, port)
                    orb.log.info('  logging in with userid "{}"'.format(
                                                                login_dlg.userid))
                    orb.log.info('  to url "{}"'.format(url))
                    self.mbus.run(url, auth_method='ticket',
                                  realm='pangalactic-services',
                                  start_reactor=False, ssl=tls_options)
                else:
                    # uncheck button if login dialog is cancelled
                    self.connect_to_bus_action.setChecked(False)
                    self.connect_to_bus_action.setToolTip(
                                                    'Connect to the message bus')
            self.check_for_connection()
            self.login_label.setText('Logout: ')
        else:
            if state['connected']:
                orb.log.info('* disconnecting from message bus ...')
                self.statusbar.showMessage(
                                        'disconnecting from message bus ...')
                if getattr(self.mbus, 'session', None) is not None:
                    self.mbus.session.leave()
                if getattr(self.mbus, 'runner', None) is not None:
                    self.mbus.runner.stop()
                orb.log.info('  message bus session disconnected.')
                self.sync_project_action.setEnabled(False)
                self.sync_all_projects_action.setEnabled(False)
                self.full_resync_action.setEnabled(False)
                self.net_status.setPixmap(self.offline_icon)
                self.net_status.setToolTip('offline')
                self.mbus = None
                self.synced = None
                state['connected'] = False
                state['done_with_progress'] = False
                state['synced_projects'] = []
            else:
                orb.log.info('* already disconnected from message bus.')
            self.login_label.setText('Login: ')
            self.connect_to_bus_action.setToolTip('Connect to the message bus')
        self.update_project_role_labels()

    def check_for_connection(self):
        if self.attempting_to_connect:
            orb.log.info('* checking for connection ...')
            n = 0
            while 1:
                if state.get('connected'):
                    orb.log.info('  connected.')
                    self.attempting_to_connect = False
                    return
                elif n < 20000000:
                    n += 1
                    QApplication.processEvents()
                    continue
                else:
                    orb.log.info('  connection failed.')
                    self.connect_to_bus_action.setChecked(False)
                    html = '<h3>Cannot connect to the Repository Service</h3>'
                    html += '<p><b><font color="red">Contact the Administrator '
                    html += 'for status.</font></b></p>'
                    dlg = NotificationDialog(html, news=False, parent=self)
                    dlg.show()
                    return
        else:
            return

    def on_mbus_joined(self):
        orb.log.info('* on_mbus_joined:  message bus session joined.')
        # first make sure state indicates that nothing is yet synced ...
        state['done_with_progress'] = False
        state['synced_projects'] = []
        state['connected'] = True
        # set userid from the returned session details ...
        state['userid'] = self.mbus.session.details.authid
        orb.log.info('  userid from session: "{}"'.format(state['userid']))
        self.connect_to_bus_action.setToolTip(
                                        'Disconnect from the message bus')
        self.net_status.setPixmap(self.online_ok_icon)
        self.net_status.setToolTip('connected')
        self.sync_project_action.setEnabled(True)
        self.sync_all_projects_action.setEnabled(True)
        self.full_resync_action.setEnabled(True)
        # delta is interval allowed for a disconnect before a project resync is
        # done -- default is 60 seconds; can be overridden by a user preference
        delta = prefs.get('disconnect_resync_interval') or 60
        if not getattr(self, 'synced', None):
            # if we haven't been synced in this session
            self.statusbar.showMessage('connected to message bus, syncing ...')
            orb.log.info('  connected to message bus, not synced, syncing ...')
            self.sync_with_services()
        else:
            now = dtstamp()
            # if (now - self.synced >= timedelta(seconds=10)
                # and not state.get('network_warning_displayed')):
                    # state['network_warning_displayed'] = True
                    # html = '<h3><font color="red">Warning: Unreliable Network'
                    # html += '</font></h3>'
                    # html += '<p><b>Connection to repository was lost '
                    # html += 'for 10 seconds or more -- <br>this can result '
                    # html += 'in out-of-sync conditions.</b></p>'
                    # html += '<p><b>Automatic re-sync is currently set '
                    # html += 'to occur when connection is lost<br>for '
                    # html += f'<font color="green">{delta}</font> seconds or '
                    # html += 'more -- this interval can be set in<br>'
                    # html += '<font color="blue">"Tools" / '
                    # html += '"Edit Preferences" /<br>'
                    # html += '"Disconnect Resync Interval [seconds]".'
                    # dlg = NotificationDialog(html, news=False, parent=self)
                    # dlg.show()
                    # self.net_status.setPixmap(self.spotty_nw_icon)
                    # self.net_status.setToolTip('unreliable network connection')
            if (now - self.synced > timedelta(seconds=delta)):
                # it's been more than [delta] seconds since we synced ...
                msg = f'reconnect > {delta} seconds since last sync, re-sync'
                orb.log.info(f'  {msg}')
                if (now - self.synced > timedelta(seconds=5*delta)):
                    # disconnect > 5*delta -> "unreliable"
                    self.net_status.setPixmap(self.spotty_nw_icon)
                    self.net_status.setToolTip('unreliable network connection')
                if state.get('library_sync_completed'):
                    self.resync_current_project(msg='reconnect: ')
                else:
                    msg = 'sync was aborted; restarting sync'
                    orb.log.info(f'  {msg}')
                    self.sync_with_services()
            else:
                # less than [delta] seconds since we synced
                msg = f'disconnected < {delta} secs; reconnected ...'
                self.statusbar.showMessage(msg)
                orb.log.info(f'  {msg}')
                if state.get('library_sync_completed'):
                    self.resync_current_project()
                else:
                    msg = 'sync was aborted; restarting sync'
                    orb.log.info(f'  {msg}')
                    self.sync_with_services()

    def on_mbus_disconnect(self):
        orb.log.info('* on_mbus_disconnect:  message bus session disconnected.')
        self.reactor.stop()

    def rpc_get_roles(self, userid, data=None, version=None):
        """
        Call initial rpc to get user roles.
        """
        rpc = self.mbus.session.call('vger.get_user_roles', userid, data=data,
                                     version=version)
        rpc.addTimeout(10, self.reactor,
                       onTimeoutCancel=self.on_rpc_timeout)
        rpc.addCallback(self.on_rpc_get_user_roles_result)
        rpc.addErrback(self.on_rpc_get_user_roles_failure)

    def sync_with_services(self, force=False):
        """
        Begin chain of initial synchronization rpcs.
        """
        self.force = force
        self.synced = dtstamp()
        self.role_label.setText('syncing library data ...')
        orb.log.debug('* calling rpc "vger.get_user_roles"')
        userid = state.get('userid', '')
        orb.log.debug('  with userid: "{}"'.format(userid))
        QApplication.processEvents()
        data = orb.get_mod_dts(cnames=['Person', 'Organization', 'Project',
                                       'RoleAssignment'])
        this_version = self.app_version or __version__
        if state.get('connected'):
            try:
                self.rpc_get_roles(userid, data=data, version=this_version)
                # rpc = self.mbus.session.call('vger.get_user_roles', userid,
                                             # data=data, version=this_version)
            except:
                orb.log.debug('  rpc "vger.get_user_roles" failed.')
                orb.log.debug('  trying again ...')
                time.sleep(1)
                try:
                    self.rpc_get_roles(userid, data=data, version=this_version)
                    # rpc = self.mbus.session.call('vger.get_user_roles',
                                                 # userid,
                                                 # data=data,
                                                 # version=this_version)
                except:
                    orb.log.debug('  rpc "vger.get_user_roles" failed again.')
                    message = "Could not reconnect -- log out & log in again."
                    popup = QMessageBox(QMessageBox.Warning,
                                        "Connection Lost", message,
                                        QMessageBox.Ok, self)
                    popup.show()

    def on_rpc_timeout(self, result, timeout):
        orb.log.debug(f'* rpc timed out after {timeout} seconds')
        html = '<h3>The Repository Service is not responding</h3>'
        html += '<p><b><font color="red">Contact the Administrator '
        html += 'for status.</font></b></p>'
        dlg = NotificationDialog(html, news=False, parent=self)
        dlg.show()
        return

    def on_rpc_get_user_roles_result(self, data):
        """
        Handle result of the rpc 'vger.get_user_roles'.  The returned data has
        the structure:

            [serialized local user (Person) object,
             serialized Organization/Project objects,
             serialized Person objects,
             serialized RoleAssignment objects,
             oids unknown to the server,
             minimum version string]
        """
        log_msg = '* processing results of rpc "vger.get_user_roles" ...'
        orb.log.debug(log_msg)
        orb.log.debug(' - data:')
        # data should be a list with 6 elements, but if no response from server
        # data may be None, so fall back to a list of 6 empty elements ...
        data = data or ['', '', '', '', '', '']
        szd_user, szd_orgs, szd_people, szd_ras, bad_oids, min_version = data
        orb.log.debug(f'   + user:  {szd_user}')
        orb.log.debug(f'   + orgs:  {len(szd_orgs)}')
        orb.log.debug(f'   + people:  {len(szd_people)}')
        orb.log.debug(f'   + role asgts:  {len(szd_ras)}')
        orb.log.debug(f'   + bad oids:  {len(bad_oids)}')
        orb.log.debug(f'   + min version:  {min_version}')
        this_version = self.app_version or __version__
        # NOTE: min_version is '' when the server did not respond (the
        # fallback above), and Version('') raises InvalidVersion -- so if
        # either side is unparseable the comparison is skipped rather than
        # turning the "no response" defence into a traceback
        this_v = safe_version(this_version)
        min_v = safe_version(min_version)
        if not (this_v and min_v):
            orb.log.debug(f'   + version unknown (this: "{this_version}", '
                          f'min: "{min_version}") -- version check skipped.')
        if (this_v and min_v and this_v < min_v
            and state.get('connected')):
            orb.log.info('* disconnecting from message bus ...')
            self.statusbar.showMessage(
                                    'disconnecting from message bus ...')
            if getattr(self.mbus, 'session', None) is not None:
                self.mbus.session.leave()
            if getattr(self.mbus, 'runner', None) is not None:
                self.mbus.runner.stop()
            orb.log.info('  message bus session disconnected.')
            self.sync_project_action.setEnabled(False)
            self.sync_all_projects_action.setEnabled(False)
            self.full_resync_action.setEnabled(False)
            self.net_status.setPixmap(self.offline_icon)
            self.net_status.setToolTip('offline')
            self.mbus = None
            self.synced = None
            state['connected'] = False
            state['done_with_progress'] = False
            state['synced_projects'] = []
            if self.connect_to_bus_action.isChecked():
                self.connect_to_bus_action.setChecked(False)
            self.login_label.setText('Login: ')
            self.connect_to_bus_action.setToolTip('Connect to the message bus')
            self.update_project_role_labels()
            name = self.app_name
            html = f'<h3>{name} {this_version} is Not Supported</h3><hr>'
            html += '<p><b>You must <font color="red">uninstall</font> '
            html += f'{name} {this_version}<br>and '
            html += '<font color="red">install</font> '
            html += f'{name} {min_version} or higher.</b></p>'
            url = state.get('app_download_url')
            if url:
                html += f'<p><b>The current version of {name} can be '
                html += 'downloaded from its installer site --<br>'
                html += 'use the button below to access the site ...</p>'
            dlg = VersionDialog(html, url, parent=self)
            dlg.show()
            return
        if szd_user:
            # deserialize local user's Person object (include refdata in case
            # we are the "admin" user)
            deserialize(orb, szd_user, include_refdata=True,
                        force_no_recompute=True)
            self.local_user = orb.select('Person', id=state['userid'])
            orb.log.debug(' - local user returned: {}'.format(
                                                  self.local_user.oid))
            state['local_user_oid'] = str(self.local_user.oid)
            if str(state.get('local_user_oid')) == 'me':
                # current local user is 'me' -- replace ...
                orb.log.debug(' - local user was "me", replacing ...')
                state['local_user_oid'] = str(self.local_user.oid)
                me = orb.get('me')
                if me and me.created_objects:
                    orb.log.debug('    updating {} local objects ...'.format(
                                            str(len(me.created_objects))))
                    for obj in me.created_objects:
                        obj.creator = self.local_user
                        obj.modifier = self.local_user
                        orb.save([obj])
                        dispatcher.send('modified object', obj=obj)
            else:
                orb.log.debug('    + login user matches current local user.')
            uid = '{} [{}]'.format(self.local_user.name,
                                   self.local_user.id)
            self.user_label.setText(uid)
            # QApplication.processEvents()
        else:
            orb.log.debug('    + user object for local user not returned!')
        orb.log.debug('  - inspecting projects and orgs ...')
        local_orgs = orb.get_by_type('Organization')
        invalid_orgs = [org for org in local_orgs if org.oid in bad_oids]
        if invalid_orgs:
            orb.log.debug('    deleting {} invalid orgs.'.format(
                                                        len(invalid_orgs)))
            orb.delete(invalid_orgs)
        else:
            orb.log.debug('    no invalid orgs found.')
        # *********************************************************************
        # NOTE: deserialize() is used for all new Person, Organization, and
        # RoleAssignment objects instead of load_serialized_objects() because
        # load_serialized_objects() is slow and leads to a disconnect due to
        # a lost transport exception.
        # *********************************************************************
        # deserialize all new Project and Organization objects
        self.statusbar.showMessage('deserializing organizations ...')
        deserialize(orb, szd_orgs)
        # deserialize all new Person objects
        self.statusbar.showMessage('deserializing users ...')
        deserialize(orb, szd_people)
        orb.log.debug('  - deserializing role assignments ...')
        self.statusbar.showMessage('receiving role assignments ...')
        # NOTE:  ONLY the server-side role assignment data is AUTHORITATIVE, so
        # delete any role assignments whose oids are not known to the server
        ras_local = orb.get_by_type('RoleAssignment')
        invalid_ras = [ra for ra in ras_local if ra.oid in bad_oids]
        if invalid_ras:
            orb.delete(invalid_ras)
        # NOTE: serialized RoleAssignment objects include all related
        # objects -- 'assigned_role' (Role), 'assigned_to' (Person), and
        # 'role_assignment_context' (Organization or Project)
        # deserialize all new RoleAssignment objects
        deserialize(orb, szd_ras)
        state['role_asgts_received'] = True
        ras = orb.get_by_type('RoleAssignment')
        org_ids = [getattr(ra.role_assignment_context, 'id', '')
                   for ra in ras]
        self.channels = ['vger.channel.' + org_id
                    for org_id in org_ids if org_id and org_id != 'global']
        # uniquify
        self.channels = list(set(self.channels))
        admins = [ra for ra in ras
                  if ra.assigned_role.oid == 'pgefobjects:Role.Administrator']
        if admins:
            # if we have *any* Administrator role assignments, subscribe to the
            # admin channel, so we will be notified when new Persons are added
            # to the repository
            self.channels.append('vger.channel.admin')
        orb.log.info('    channels we will subscribe to: {}'.format(
                                                       str(self.channels)))
        if self.project:
            proj_ras = orb.search_exact(cname='RoleAssignment',
                                        assigned_to=self.local_user,
                                        role_assignment_context=self.project)
            my_roles = [ra.assigned_role.name for ra in proj_ras]
            if my_roles:
                txt = ': '.join([self.project.id, my_roles[0]])
            elif self.project is self.sandbox:
                txt = 'SANDBOX'
            else:
                txt = ': '.join([self.project.id, '[local]'])
            self.role_label.setText(txt)
        else:
            self.role_label.setText('online [no project selected]')
        self.channels.append('vger.channel.public')
        rpc = self.subscribe_to_mbus_channels(self.channels)
        rpc.addErrback(self.on_failure)
        # the reconciliation report describes *this* sync, so start it empty
        rpc.addCallback(self.clear_sync_report)
        # ------------------------------------------------------------------
        # NOTE: the offline deletion queue is replayed FIRST, before any of
        # the syncs below.  Ordering here is load-bearing:  sync_project() and
        # sync_library_objects() both treat "the client did not report this
        # oid" as "the client needs it", so running them first would restore
        # the very objects that are about to be deleted -- the object would
        # reappear in the tree and then vanish again.  Same "push before pull"
        # rule that governs the parameter caches.
        # ------------------------------------------------------------------
        rpc.addCallback(self.replay_deletion_queue)
        rpc.addErrback(self.on_failure)
        rpc.addCallback(self.sync_user_created_objs_to_repo)
        rpc.addErrback(self.on_failure)
        rpc.addCallback(self.on_user_objs_sync_result)
        rpc.addErrback(self.on_failure)
        # populate the local mirror of active check-out claims (advisory
        # display only -- see the CHECK-OUT / CHECK-IN section below)
        rpc.addCallback(self.get_checkouts)
        rpc.addErrback(self.on_failure)
        if self.force:
            rpc.addCallback(self.force_sync_managed_objs)
            rpc.addErrback(self.on_failure)
            rpc.addCallback(self.on_force_sync_managed_result)
            rpc.addErrback(self.on_failure)
        else:
            rpc.addCallback(self.sync_library_objs)
            rpc.addErrback(self.on_failure)
            rpc.addCallback(self.on_sync_library_result)
            rpc.addErrback(self.on_failure)
            # syncing of current project is now done by adding a callback of
            # resync_current_project() when the last chunk of library data
            # is being requested by on_get_library_objects_result()

    def on_rpc_get_user_roles_failure(self, f):
        orb.log.debug("* rpc failure: {}".format(f.getTraceback()))
        if state['connected']:
            orb.log.info('* disconnecting from message bus ...')
            self.statusbar.showMessage(
                                    'disconnecting from message bus ...')
            if getattr(self.mbus, 'session', None) is not None:
                self.mbus.session.leave()
            if getattr(self.mbus, 'runner', None) is not None:
                self.mbus.runner.stop()
            orb.log.info('  message bus session disconnected.')
            self.sync_project_action.setEnabled(False)
            self.sync_all_projects_action.setEnabled(False)
            self.full_resync_action.setEnabled(False)
            self.net_status.setPixmap(self.offline_icon)
            self.net_status.setToolTip('offline')
            self.mbus = None
            self.synced = None
            state['connected'] = False
            state['done_with_progress'] = False
            state['synced_projects'] = []
        else:
            orb.log.info('* already disconnected from message bus.')
        if self.connect_to_bus_action.isChecked():
            self.connect_to_bus_action.setChecked(False)
        self.login_label.setText('Login: ')
        self.connect_to_bus_action.setToolTip('Connect to the message bus')
        self.update_project_role_labels()
        html = '<h3>The Repository Service is Unavailable</h3>'
        html += '<p><b><font color="red">Contact the Administrator '
        html += 'for status.</font></b></p>'
        dlg = NotificationDialog(html, news=False, parent=self)
        dlg.show()
        return

    def subscribe_to_mbus_channels(self, data):
        # NOTE: "data" is now ignored -- previously, it was "channels" and was
        # passed in from on_rpc_get_user_roles_result(), but now channels are
        # set as self.channels (mainly for use in re-subscribing when/if
        # connection is lost ...)
        self.channels = self.channels or ['vger.channel.public']
        orb.log.debug('* attempting to subscribe to channels:  %s' % str(
                                                                self.channels))
        subs = []
        for channel in self.channels:
            sub = self.mbus.session.subscribe(self.on_pubsub_msg, channel)
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
        orb.log.debug('* rpc: vger.sync_parameter_definitions')
        self.statusbar.showMessage('syncing parameter definitions ...')
        # exclude refdata (already shared)
        pd_mod_dts = orb.get_mod_dts(cnames=['ParameterDefinition'])
        data = {pd_oid : mod_dt for pd_oid, mod_dt in pd_mod_dts.items()
                if pd_oid not in ref_pd_oids}
        orb.log.debug('  -> rpc: vger.sync_parameter_definitions')
        try:
            return self.mbus.session.call('vger.sync_parameter_definitions',
                                          data)
        except:
            orb.log.debug('  ** rpc failed (possible loss of transport)')
            orb.log.debug('     trying to reconnect ...')
            self.set_bus_state()

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
        orb.log.debug('* sync_user_created_objs_to_repo()')
        self.statusbar.showMessage('syncing locally created objects ...')
        # ********************************************************************
        # NOTE: exclusion of "SANDBOX" PSUs here is IMPORTANT: without it, the
        # sync process will HANG for non-admin users (unclear why)
        # ********************************************************************
        # NOTE: reference data is excluded because it is not authored by
        # anyone:  load_reference_data() creates it on the client and on the
        # server independently, from refdata.py, stamping "admin" as its
        # creator.  For a user logged in as admin it therefore turns up in
        # created_objects and gets pushed -- where the repository rejects it,
        # since get_perms() gives reference data "view only".  Harmless but
        # confusing, and it recurs on every sync for every refdata addition
        # until both ends have the same refdata.py.
        oids = [o.oid for o in self.local_user.created_objects
                if not (isinstance(o, orb.classes['ProjectSystemUsage'])
                        and o.project.oid == 'pgefobjects:SANDBOX')
                and not is_reference_data(o)]
        data = orb.get_mod_dts(oids=oids)
        orb.log.debug('       -> rpc: vger.sync_objects()')
        try:
            return self.mbus.session.call('vger.sync_objects', data)
        except:
            orb.log.debug('  ** rpc failed (possible loss of transport)')
            orb.log.debug('     trying to reconnect ...')
            self.set_bus_state()

    def sync_library_objs(self, data):
        """
        Sync with the repository's non-project objects. This updates all
        objects that are not owned by a project.  (Project-owned objects are
        synced via the vger.sync_project() rpc.)

        Args:
            data:  parameter required for callback (ignored)
        """
        orb.log.debug('* sync_library_objs()')
        self.statusbar.showMessage('syncing library objects ...')
        # allow the user's objects in `data`; it's faster and their oids will
        # come back in the set of oids to be ignored.
        # Here we just include the most important subtypes of ManagedObject ...
        # we will get back ALL subtypes anyway.
        data = orb.get_mod_dts(cnames=['HardwareProduct', 'Template',
                                       'DataElementDefinition', 'Model',
                                       'Document', 'RepresentationFile'])
        # exclude reference data (ref_oids)
        non_ref_data = {oid: data[oid] for oid in (data.keys() - ref_oids)}
        try:
            return self.mbus.session.call('vger.sync_library_objects',
                                          non_ref_data)
        except:
            orb.log.debug('  ** rpc failed (possible loss of transport)')
            orb.log.debug('     trying to reconnect ...')
            self.set_bus_state()

    def force_sync_managed_objs(self, data):
        """
        Get all "public" instances of ManagedObject in the repository.

        Args:
            data:  parameter required for callback (ignored)
        """
        # TODO:  Include all library classes (not just HardwareProduct)
        orb.log.debug('* force_sync_managed_objs()')
        self.statusbar.showMessage('forcing sync of ALL library objects ...')
        data = orb.get_mod_dts(cnames=['HardwareProduct', 'Template',
                                       'DataElementDefinition', 'Model'])
        # exclude reference data (ref_oids)
        non_ref_data = {oid: data[oid] for oid in (data.keys() - ref_oids)}
        try:
            return self.mbus.session.call('vger.force_sync_managed_objects',
                                          non_ref_data)
        except:
            orb.log.debug('  ** rpc failed (possible loss of transport)')
            orb.log.debug('     trying to reconnect ...')
            self.set_bus_state()

    def sync_current_project(self, data, msg=''):
        """
        Sync all objects owned or used by the current project into the local
        db.  If there are any local project objects, this function internally
        assembles a list containing their [oid, mod_datetime] pairs and sends
        it to the server.  The server response is a list of lists:

            [0]:  server objects with later mod_datetime(s)
            [1]:  oids of server objects with the same mod_datetime(s)
            [2]:  oids of server objects with earlier mod_datetime(s),
            [3]:  oids sent that were not found on the server
            [4]:  all oids in the server's "deleted" cache
            [5]:  parameter data for all project-owned objects
            [6]:  data element data for all project-owned objects

        Args:
            data:  parameter required for callback (ignored)

        Return:
            deferred: result of `vger.sync_project` rpc
        """
        orb.log.info('* sync_current_project()')
        proj_oid = state.get('project') or ''
        project = orb.get(proj_oid)
        oid_dts = {}
        if (proj_oid != 'pgefobjects:SANDBOX') and project:
            orb.log.debug('  current project is: {}'.format(project.id))
            status_msg = f'syncing project {project.id} ...'
            if msg:
                status_msg = f'{msg} {status_msg} ...'
            self.statusbar.showMessage(status_msg)
            local_objs = orb.get_objects_for_project(project)
            # add in any role assignments for the project
            local_objs += orb.search_exact(cname='RoleAssignment',
                                           role_assignment_context=project)
            title_text = 'Syncing with Repository'
            project_text = f'<font color="blue">{project.id}</font>'
            label_text = f'<h3>Getting {project_text} data ...</h3>'
            self.sync_progress = ProgressDialog(title=title_text,
                                                label=label_text,
                                                parent=self)
            self.sync_progress.setMinimum(0)
            self.sync_progress.setMaximum(0)
            self.sync_progress.setMinimumDuration(500)
            self.sync_progress.resize(400, 100)
            QApplication.processEvents()
            if local_objs:
                for obj in local_objs:
                    # exclude reference data (ref_oids)
                    # make sure obj is valid (i.e. has an oid)
                    oid = getattr(obj, 'oid', None)
                    if oid and oid not in ref_oids:
                        dts = str(obj.mod_datetime)
                        oid_dts[obj.oid] = dts
        else:
            self.statusbar.showMessage('project synced.')
            QApplication.processEvents()
        # NOTE: callback to on_project_sync_result() to handle result is added
        # by on_set_current_project()
        try:
            return self.mbus.session.call('vger.sync_project', proj_oid,
                                          oid_dts)
        except:
            orb.log.debug('  ** rpc failed (possible loss of transport)')
            orb.log.debug('     trying to reconnect ...')
            self.set_bus_state()

    def on_user_objs_sync_result(self, data):
        self.on_sync_result(data, user_objs_sync=True)

    def on_project_sync_result(self, data):
        self.on_sync_result(data, project_sync=True)

    def on_sync_result(self, data, project_sync=False, user_objs_sync=False):
        """
        Callback function to process the result of the following rpcs:

            - `vger.sync_objects` -- which is called by:
                on startup:
                + self.sync_user_created_objs_to_repo()

            - `vger.sync_project` -- which is called by:
                + self.sync_current_project()

        The server response (data parameter) is a list of lists:

            [0]:  server objects with later mod_datetime(s) or whose oids were
                  not in the submitted list of oids
            [1]:  oids of server objects with the same mod_datetime(s)
            [2]:  oids of server objects with earlier mod_datetime(s),
            [3]:  oids sent that were not found on the server
            [4]:  oids of all objs that were deleted on the server
            [5]:  parameter data for all objs requested
            [6]:  data element data for all objs requested

        Args:
            data:  response from the server

        Keyword Args:
            project_sync (bool): called from a project sync
            user_objs_sync (bool): called from the result of a user created
                objects sync

        Return:
            deferred:  result of `vger.save` rpc
        """
        if project_sync:
            orb.log.info('* on_sync_result() for sync_current_project()')
        else:
            orb.log.info('* on_sync_result() for sync_user_created_objs_to_repo()')
        if getattr(self, 'sync_progress', None):
            try:
                self.sync_progress.done(0)
                self.sync_progress.close()
                QApplication.processEvents()
            except:
                # orb.log.debug('  - progress dialog C++ obj already deleted.')
                pass
        # sync_type = ''
        # if project_sync:
            # sync_type = 'project'
        # elif user_objs_sync:
            # sync_type = 'user objs'
        # orb.log.debug('       data: {}'.format(str(data)))
        try:
            (sobjs, same_dts, to_update, local_only, server_deleted_oids,
             parm_data, de_data) = data
        except:
            orb.log.info('  unable to unpack "{}"'.format(data))
            try:
                rpc = self.mbus.session.call('vger.save', [])
                rpc.addCallback(self.on_vger_save_result)
                rpc.addErrback(self.on_failure)
                return rpc
            except:
                orb.log.debug('  ** rpc failed (possible loss of transport)')
                orb.log.debug('     trying to reconnect ...')
                self.set_bus_state()
                return
        # [2022-11-09] "project_oids" attr used in updating parms of proj objs
        if project_sync:
            self.project_oids = list(parm_data)
        # update parameterz and data_elementz
        orb.log.debug('  - updating parameters ...')
        parameterz.update(parm_data)
        orb.log.debug('    parameters updated.')
        orb.log.debug('  - updating data elements ...')
        data_elementz.update(de_data)
        orb.log.debug('    data elements updated.')
        # TODO:  create a progress bar for this ...
        n = len(sobjs)
        if n:
            self.statusbar.showMessage(
                'deserializing {} objects ...'.format(n))
            # deserialize(orb, sobjs)
            self.load_serialized_objects(sobjs)
        objs_to_save = orb.get(oids=to_update)
        created_objs = []
        objs_to_delete = set()
        if local_only:
            orb.log.debug('       objects unknown to server found ...')
            local_only_objs = orb.get(oids=local_only)
            for o in local_only_objs:
                if hasattr(o, 'creator') and o.creator == self.local_user:
                    if not (o.__class__.__name__ == 'ProjectSystemUsage' and
                            o.project is self.sandbox):
                        # NOTE:  SANDBOX PSUs are ignored
                        created_objs.append(o)
                else:
                    objs_to_delete.add(o)
            if objs_to_delete:
                orb.log.debug('       to be deleted: {}'.format(str([
                              o.id for o in objs_to_delete])))
                orb.delete(objs_to_delete)
        objs_to_save += created_objs
        if created_objs:
            orb.log.debug('       to be saved in repo: {}'.format(str(
                          [obj.id for obj in objs_to_save])))
        if project_sync:
            # if on_sync_result() was called from a project sync, set
            # state['modal views need update'] so that
            # self._update_modal_views() will be run after vger.save() is
            # called, which will update the 'role_label' with the project etc.
            state['modal views need update'] = True
        if server_deleted_oids:
            n = len(server_deleted_oids)
            orb.log.debug(f'* sync: {n} deleted oids received from server.')
            deleted = list(set((state.get('deleted_oids') or []) +
                               (server_deleted_oids or [])))
            state['deleted_oids'] = deleted
            local_objs_to_del = orb.get(oids=server_deleted_oids)
            if local_objs_to_del:
                n = len(local_objs_to_del)
                orb.log.debug(f'  - {n} object(s) found in local db ...')
                for obj in local_objs_to_del:
                    cname = obj.__class__.__name__
                    obj_id = getattr(obj, 'id', 'unknown id')
                    orb.log.debug(f'    {obj_id} ({cname})')
                orb.log.debug('  - deleting them ...')
                orb.delete(local_objs_to_del)
                if cname:
                    # if multiple deletes, they will need to be looked up from
                    # state['deleted_oids']
                    state['updates_needed_for_remote_obj_deletion'] = cname
            else:
                orb.log.debug('        none were found in local db.')
        if user_objs_sync:
            # NOTE: state['locally_created_oids'] is deliberately NOT cleared
            # wholesale here.  It is pruned per-oid in on_vger_save_result(),
            # from the oids the repository actually confirmed -- so an object
            # whose save was *refused* (unauth, no owner) correctly stays
            # "locally created" and therefore still editable offline, rather
            # than being forgotten because a sync happened to run.
            state['user_objs_sync_completed'] = True
        # --------------------------------------------------------------------
        # The following is added to fix a bug involving the client attempting
        # to save the user's Person object, RoleAssignment for the current
        # Project, and the current Project object -- which should NOT be done
        # by a non-privileged user [SCW 2024-02-29]
        # --------------------------------------------------------------------
        # NOTE: this filter runs while *connected*, so it evaluates the user's
        # real permissions. Objects failing it are locally modified work that
        # will never be accepted by the repository -- they used to be dropped
        # here with no log entry and no user-visible indication, and because
        # the local mod_datetime stays newer than the server's, every
        # subsequent sync re-derived them and dropped them again. They are now
        # logged and recorded in state['last_sync_report'].
        valid_objs_to_save = []
        withheld = []
        for obj in objs_to_save:
            if 'modify' in get_perms(obj):
                valid_objs_to_save.append(obj)
            else:
                withheld.append(obj)
        if withheld:
            orb.log.info(f'  * {len(withheld)} locally modified object(s) '
                         'will NOT be sent to the repository')
            orb.log.info('    (user does not have "modify" permission):')
            for obj in withheld:
                obj_id = getattr(obj, 'id', None) or obj.oid
                cname = obj.__class__.__name__
                orb.log.info(f'    - {obj_id} ({cname})')
            report = state.get('last_sync_report') or {}
            report['withheld'] = list(set((report.get('withheld') or []) +
                                          [getattr(o, 'id', None) or o.oid
                                           for o in withheld]))
            state['last_sync_report'] = report
        if valid_objs_to_save:
            sobjs_to_save = serialize(orb, valid_objs_to_save)
            orb.log.debug('  calling rpc vger.save() ...')
            orb.log.debug('  [called from on_sync_result()]')
            orb.log.debug('  - saved objs ids:')
            try:
                rpc = self.mbus.session.call('vger.save', sobjs_to_save)
                rpc.addCallback(self.on_vger_save_result)
                rpc.addCallback(self.get_parmz)
            except:
                orb.log.debug('  ** rpc failed (possible loss of transport)')
                orb.log.debug('     trying to reconnect ...')
                self.set_bus_state()
                return
        else:
            # don't need the final "get_parmz" here because we're done
            try:
                rpc = self.mbus.session.call('vger.save', [])
                rpc.addCallback(self.on_vger_save_result)
            except:
                orb.log.debug('  ** rpc failed (possible loss of transport)')
                orb.log.debug('     trying to reconnect ...')
                self.set_bus_state()
                return
        try:
            rpc.addErrback(self.on_failure)
            return rpc
        except:
            orb.log.debug('  ** rpc failed (possible loss of transport)')
            orb.log.debug('     trying to reconnect ...')
            self.set_bus_state()

    def on_sync_library_result(self, data, project_sync=False):
        """
        Callback function to process the result of the
        `vger.sync_library_objects` rpc.  The server response is a list of
        lists:

            [0]:  oids of server objects (in DESERIALIZATION_ORDER) with later
                  mod_datetime(s) or not found in the local data sent with
                  `sync_library_objects()`
                  -> do one or more vger.get_objects() rpcs to get the objects
                  and add them to the local db
            [1]:  oids in the data sent with `sync_library_objects()` that were
                  not found on the server
                  -> delete these from the local db if they are either:
                     [a] not created by the local user
                     [b] created by the local user but are in 'trash'
            [2]:  parameter data for all oids in the data that correspond to
                  "public" objects known to the server, irrespective of their
                  mod_datetimes
            [3]:  data element data for all oids in the data that correspond to
                  "public" objects known to the server, irrespective of their
                  mod_datetimes
            [4]:  all mode definitions (serialized "mode_defz" cache)
            [5]:  datetime stamp for mode definitions (mode_defz_dts)

        Args:
            data:  response from the server

        Return:
            deferred:  result of `vger.get_objects` rpc
        """
        orb.log.debug('* on_sync_library_result()')
        if data is None:
            orb.log.debug('  no data received.')
            return 'success'  # return value will be ignored
        msg = 'no data received.'
        # data *should* be a list of 2 lists, 2 dicts, and 2 strings ...
        if len(data) == 6:
            n_new = len(data[0])
            n_del = len(data[1])
            n_obj_parms = len(data[2])
            n_obj_des = len(data[3])
            msg = f'data: {n_new} new oids, {n_del} oids not found on server'
        else:
            orb.log.debug('  data incorrectly formatted.')
            return 'invalid data format'  # return value will be ignored
        orb.log.debug(f'  {msg}'.format(str(data)))
        newer, local_only, parm_data, de_data, md_data, md_dts = data
        # update parameterz and data_elementz
        orb.log.debug('  - updating parameters ...')
        parameterz.update(parm_data)
        orb.log.debug(f'    parameters updated for {n_obj_parms} objects.')
        orb.log.debug('  - updating data elements ...')
        data_elementz.update(de_data)
        orb.log.debug(f'    data elements updated for {n_obj_des} objects.')
        # update mode_defz if md_dts is later than mode_defz_dts ...
        # NOTE: this conditional treatment is specific to mode_defz.  The
        # parameterz and data_elementz updates just above are deliberately
        # unconditional even though state['parmz_dts'] / state['dez_dts']
        # exist:  those two are diagnostic only, and gating the parameter
        # caches on them would defeat the convergence that unconditional
        # replacement provides.  See the note after the state key list in
        # p.core/NOTES_FOR_DEVELOPERS.md before copying this pattern.
        local_md_dts = state.get('mode_defz_dts')
        if (local_md_dts is None) or (md_dts > local_md_dts):
            orb.log.debug('  - updating mode_defz ...')
            all_proj_modes = json.loads(md_data)
            mode_defz.update(all_proj_modes)
        else:
            orb.log.debug('  - mode_defz is up to date.')
        # then collect any local objects that need to be saved to the repo ...
        if local_only:
            orb.log.debug('  objects unknown to server found ...')
            objs_to_delete = set(orb.get(oids=local_only))
            do_not_delete = set()
            for o in objs_to_delete:
                # NOTE: any local objects that are in the server's "deleted"
                # cache will be deleted separately, based on either the initial
                # sync of user objects or a published "deleted" message
                if (hasattr(o, 'creator') and o.creator == self.local_user
                    and o.oid not in list(trash)):
                    do_not_delete.add(o)
            objs_to_delete = objs_to_delete - do_not_delete
            if objs_to_delete:
                orb.log.debug('  to be deleted: {}'.format(
                              ', '.join([o.oid for o in objs_to_delete])))
                orb.delete(objs_to_delete)
        if newer:
            orb.log.debug('  new objects found ...')
            # chunks = chunkify(newer, 5)   # set chunks small for testing
            # chunks = chunkify(newer, 100)
            chunks = chunkify(newer, 50)   # 100 is too big sometimes
            n_chunks = len(chunks)
            c = 'chunks'
            if n_chunks == 1:
                c = 'chunk'
            orb.log.debug(f'  will get in {n_chunks} {c} ...')
            chunk = chunks.pop(0)
            state['chunks_to_get'] = chunks
            if state.get('connected'):
                try:
                    rpc = self.mbus.session.call('vger.get_objects', chunk)
                    rpc.addCallback(self.on_get_library_objects_result)
                    rpc.addErrback(self.on_failure)
                except:
                    orb.log.debug('  ** rpc failed (possible loss of transport)')
                    orb.log.debug('     trying to reconnect ...')
                    self.set_bus_state()
                    return
            else:
                pass
        else:
            # if no newer objects but objects have been deleted, resync the
            # current project ... which will also update views ...
            self.resync_current_project()

    def on_get_library_objects_result(self, data):
        """
        Handler for the result of the rpc 'vger.get_objects()' when called by
        'on_sync_library_result()' (i.e., only at login).  This should only be
        used as handler for 'on_sync_library_result()' (at login) because when
        finished (no more chunks to get) it calls
        'self.resync_current_project()', which calls
        'self.on_set_current_project()'

        Args:
            data (list):  a list of serialized objects
        """
        orb.log.debug('* on_get_library_objects_result')
        if data is not None:
            orb.log.debug('  - deserializing {} objects ...'.format(len(data)))
            self.load_serialized_objects(data)
            lib_widget = getattr(self, 'library_widget', None)
            if lib_widget:
                try:
                    lib_widget.refresh('HardwareProduct')
                except:
                    pass
        if state.get('chunks_to_get'):
            chunk = state['chunks_to_get'].pop(0)
            orb.log.debug('  - next chunk to get: {}'.format(str(chunk)))
            try:
                rpc = self.mbus.session.call('vger.get_objects', chunk)
                rpc.addCallback(self.on_get_library_objects_result)
                rpc.addErrback(self.on_failure)
            except:
                orb.log.debug('  ** rpc failed (possible loss of transport)')
                orb.log.debug('     trying to reconnect ...')
                self.set_bus_state()
                return
        else:
            orb.log.debug('  - done getting library objects ...')
            orb.log.debug('    now resyncing current project ...')
            state['library_sync_completed'] = True
            lib_widget = getattr(self, 'library_widget', None)
            if lib_widget:
                try:
                    lib_widget.refresh('HardwareProduct')
                except:
                    pass
            self.resync_current_project()

    def on_force_sync_managed_result(self, data, project_sync=False):
        """
        Callback function to process the result of the
        `vger.force_sync_managed_objs` rpc.  The server response is a list
        of lists:

            [0]:  oids of server objects (in DESERIALIZATION_ORDER), regardless
                  of their mod_datetime(s) or not found in the local data sent
                  with `force_sync_managed_objs()`
                  -> do one or more vger.get_objects() rpcs to get the objects
                  and add them to the local db
            [1]:  oids in the data sent with `force_sync_managed_objs()`
                  that were not found on the server
                  -> delete these from the local db if they are either:
                     [a] not created by the local user
                     [b] created by the local user but are in 'trash'

        Args:
            data:  response from the server

        Return:
            deferred:  result of `vger.get_objects` rpc
        """
        orb.log.debug('* on_force_sync_managed_result()')
        if data is None:
            orb.log.debug('  no data received.')
            return 'success'  # return value will be ignored
        msg = 'no data received.'
        # data *should* be a list of 2 lists ...
        if len(data) == 2:
            n_new = len(data[0])
            n_del = len(data[1])
            msg = f'data: {n_new} oids, {n_del} oids not found on server'
        orb.log.debug(f'  {msg}'.format(str(data)))
        newer, local_only = data
        # then collect any local objects that need to be saved to the repo ...
        if local_only:
            orb.log.debug('  objects unknown to server found ...')
            objs_to_delete = set(orb.get(oids=local_only))
            do_not_delete = set()
            for o in objs_to_delete:
                if (hasattr(o, 'creator') and o.creator == self.local_user
                    and o.oid not in list(trash)):
                    do_not_delete.add(o)
            objs_to_delete = objs_to_delete - do_not_delete
            if objs_to_delete:
                orb.log.debug('  to be deleted: {}'.format(
                              ', '.join([o.oid for o in objs_to_delete])))
                orb.delete(objs_to_delete)
        if newer:
            orb.log.debug('  server objects found ...')
            # chunks = chunkify(newer, 5)   # set chunks small for testing
            chunks = chunkify(newer, 50)
            n_chunks = len(chunks)
            c = 'chunks'
            if n_chunks == 1:
                c = 'chunk'
            orb.log.debug(f'  will get in {n_chunks} {c} ...')
            chunk = chunks.pop(0)
            state['chunks_to_get'] = chunks
            try:
                rpc = self.mbus.session.call('vger.get_objects', chunk)
                rpc.addCallback(self.on_force_get_managed_objects_result)
                rpc.addErrback(self.on_failure)
            except:
                orb.log.debug('  ** rpc failed (possible loss of transport)')
                orb.log.debug('     trying to reconnect ...')
                self.set_bus_state()
                return
        else:
            # if no newer objects but objects have been deleted, update views
            self._update_modal_views()
            return 'success'  # return value will be ignored

    def on_force_get_managed_objects_result(self, data):
        """
        Handler for the result of the rpc 'vger.get_objects()' when called by
        'on_force_sync_managed_result()' (i.e., only at login).  This should only be
        used as handler for 'on_force_sync_managed_result()' because it will
        force the deserializer to replace any local versions of the objects.

        Args:
            data (list):  a list of serialized objects
        """
        orb.log.debug('* on_force_get_managed_objects_result()')
        if data is not None:
            orb.log.debug('  - deserializing {} objects ...'.format(len(data)))
            self.force_load_serialized_objects(data)
        if state.get('chunks_to_get'):
            chunk = state['chunks_to_get'].pop(0)
            orb.log.debug('  - next chunk to get: {}'.format(str(chunk)))
            try:
                rpc = self.mbus.session.call('vger.get_objects', chunk)
                rpc.addCallback(self.on_force_get_managed_objects_result)
                rpc.addErrback(self.on_failure)
            except:
                orb.log.debug('  ** rpc failed (possible loss of transport)')
                orb.log.debug('     trying to reconnect ...')
                self.set_bus_state()
                return
        else:
            # if this was the last chunk, sync current project
            self.resync_current_project()

    def on_remote_freeze_or_thaw(self, obj_attrs, action):
        """
        Handler for content of pubsub "freeze completed" or "thawed" message.
        """
        orb.log.debug('* on_remote_freeze_or_thaw()')
        if not obj_attrs:
            return
        if action not in ['freeze', 'thaw']:
            return
        frozen_oids = []
        thawed_oids = []
        lib_widget = getattr(self, 'library_widget', None)
        for attrs in obj_attrs:
            # try:
            obj_oid, obj_mod_dts, obj_modifier_oid = attrs
            obj = orb.get(obj_oid)
            if obj:
                if action == 'freeze':
                    obj.frozen = True
                    frozen_oids.append(obj_oid)
                elif action == 'thaw':
                    obj.frozen = False
                    thawed_oids.append(obj_oid)
                obj.mod_datetime = uncook_datetime(obj_mod_dts)
                modifier = orb.get(obj_modifier_oid)
                if modifier:
                    obj.modifier = modifier
                orb.db.commit()
                if lib_widget:
                    lib_widget.on_remote_obj_mod(obj_oid,
                                                 obj.__class__.__name__)
            if action == 'freeze':
                # dispatcher.send('remote: frozen', frozen_oids=frozen_oids)
                dispatcher.send(signal='remote frozen', frozen_oids=frozen_oids)
            else:
                # dispatcher.send('remote: thawed', oids=thawed_oids)
                dispatcher.send(signal='remote thawed', oids=thawed_oids)
            # except:
                # orb.log.debug(f'  failed: could not parse content "{attrs}".')
        if self.mode == "system" and (frozen_oids or thawed_oids):
            self.refresh_tree_and_dashboard()

    # =====================================================================
    # CHECK-OUT / CHECK-IN (phase 1: advisory -- display only)
    # ---------------------------------------------------------------------
    # state['checkouts'] mirrors the repository's active CheckOut claims:
    #
    #     {oid: {'userid': str, 'expiry_datetime': str, 'purpose': str}}
    #
    # It is refreshed wholesale by get_checkouts() at sync time and kept up
    # to date by the "checked out" / "checked in" pubsub messages. Nothing
    # consults it for authorization yet -- access.py is untouched, so this
    # is purely informational. Enforcement is phase 2.
    #
    # NOTE: new signalling here uses pydispatcher rather than pyqtSignal,
    # per the ongoing migration back to pydispatcher.
    # See pangalactic.core/NOTES_ON_CHECKOUT_MODEL.md.
    # =====================================================================

    # ---------------------------------------------------------------------
    # state['locally_created_oids'] lists objects created on this client that
    # the repository has never seen.  access.is_writable_now() consults it as
    # rule [4]:  offline, with no check-out claim, these are the only objects
    # that may be edited.
    #
    # It replaces the old test "obj.oid not in state['synced_oids']", which
    # was inverted:  synced_oids held only the *user's own* objects, so
    # absence from it meant, in practice, "somebody else created this" --
    # exactly the objects that should NOT have been editable offline.  See
    # NOTES_ON_OFFLINE_AND_SYNC.md section 2 and NOTES_ON_CHECKOUT_MODEL.md
    # section 5.
    #
    # NOTE: state is persisted, so this survives a restart -- which it must,
    # since offline work can span sessions.  (state['synced_oids'], which the
    # old test used, was retired on 2026-08-04: it had stopped being consulted
    # for anything and was only being maintained.)
    # ---------------------------------------------------------------------

    # ---------------------------------------------------------------------
    # RECONCILIATION REPORT
    # ---------------------------------------------------------------------
    # state['last_sync_report'] accumulates everything a sync could not do,
    # as {category: [item descriptions]}.  It is written to from several
    # places -- objects withheld because the user lacks 'modify'
    # (on_sync_result), saves the repository refused (on_vger_save_result),
    # and deletions it refused (on_rpc_vger_delete_result) -- and presented
    # once, at the end of the sync, by show_sync_report().
    #
    # This exists because the failure mode throughout this area has been
    # silence:  work was dropped, reverted or restored with nothing said, so
    # the user's only clue was noticing later that their edit had gone.  See
    # NOTES_ON_OFFLINE_AND_SYNC.md section 3.4.
    # ---------------------------------------------------------------------

    def add_to_sync_report(self, category, item):
        """
        Record something a sync could not do, for the end-of-sync summary.

        Args:
            category (str):  short description of the outcome, used as the
                heading in the summary (e.g. 'deletions refused')
            item (str):  identifier of the object concerned
        """
        report = state.get('last_sync_report') or {}
        items = report.get(category) or []
        if item not in items:
            items.append(item)
        report[category] = items
        state['last_sync_report'] = report

    def clear_sync_report(self, data=None):
        """
        Start a sync with an empty report.

        Placed at the head of the sync chain so the summary describes *this*
        sync rather than accumulating across sessions.

        Keyword Args:
            data:  passed through for callback chaining (ignored)
        """
        state['last_sync_report'] = {}
        return data

    def show_sync_report(self, data=None):
        """
        Present what this sync could not do, if anything.

        Silent when there is nothing to report -- the point is to surface
        losses, not to add a dialog to every successful sync.

        Keyword Args:
            data:  passed through for callback chaining (ignored)
        """
        report = state.get('last_sync_report') or {}
        report = {k: v for k, v in report.items() if v}
        if not report:
            orb.log.info('* sync completed with nothing to report.')
            return data
        total = sum(len(v) for v in report.values())
        orb.log.info(f'* sync report: {total} item(s) need attention:')
        html = ['<p>The repository could not accept everything from this '
                'session:</p>']
        for category, items in sorted(report.items()):
            orb.log.info(f'   {category}: {len(items)}')
            html.append(f'<p><b>{category}</b> ({len(items)}):</p><ul>')
            for item in sorted(items):
                orb.log.info(f'     - {item}')
                html.append(f'<li>{item}</li>')
            html.append('</ul>')
        html.append('<p>These are listed in the log in full.</p>')
        # cleared once presented, so the same losses are not reported again on
        # the next rpc that happens to end in this callback
        state['last_sync_report'] = {}
        # NOTE: deferred via singleShot, and shown rather than exec_'d --
        # painting from inside an rpc callback while further rpcs are pending
        # raises "QBackingStore::endPaint() called ...".  Same reason as the
        # status-bar message in on_vger_save_result().
        def _show():
            dlg = NotificationDialog(''.join(html), parent=self)
            dlg.show()
            self.statusbar.showMessage(
                f'sync completed -- {total} item(s) need attention')
        QTimer.singleShot(0, _show)
        return data

    # ---------------------------------------------------------------------
    # OFFLINE DELETION QUEUE
    # ---------------------------------------------------------------------
    # Deletions made while offline are recorded in p.core.deletion_queue and
    # replayed at the next sync.  Without this the repository is never told
    # about them, and *both* sync paths treat "the client did not report this
    # oid" as "the client needs it" -- so the object is sent back and the
    # deletion is silently undone.  This applies to authorized deletions of
    # the user's own work just as much as to unauthorized ones.
    # See NOTES_ON_OFFLINE_AND_SYNC.md section 3.2.
    #
    # Ordering is load-bearing:  the replay must happen BEFORE
    # sync_project()/sync_library_objects(), or those will restore the very
    # objects about to be deleted, producing visible churn.  This is the same
    # "push before pull" rule that governs the parameter caches.
    # ---------------------------------------------------------------------

    def queue_deletion(self, oid, cname=''):
        """
        Record a deletion that could not be sent to the repository.

        Args:
            oid (str):  oid of the deleted object

        Keyword Args:
            cname (str):  class name of the deleted object.  Kept because the
                object is already gone from the local db by the time the
                queue is replayed, so it is the only thing left to report the
                deletion with.
        """
        if not oid:
            return
        deletion_queue[oid] = {'cname': cname or '',
                               'datetime': str(dtstamp())}
        # written immediately, not at shutdown:  a deletion lost in a crash
        # reappears at the next sync, silently
        write_deletion_queue(os.path.join(orb.home, 'deletion_queue'))
        n = len(deletion_queue)
        orb.log.info(f'  deletion of "{oid}" queued for sync ({n} queued).')

    def replay_deletion_queue(self, data=None):
        """
        Replay queued offline deletions to the repository.

        Placed early in the sync chain, before the project and library syncs
        (see the note above).  Entries are cleared only when the repository
        confirms them, in on_rpc_vger_delete_result(), so an interrupted sync
        retries rather than dropping the deletion.

        Keyword Args:
            data:  passed through for callback chaining (ignored)

        Returns:
            the 'data' argument, so this can sit in an addCallback chain
        """
        if not deletion_queue:
            return data
        if not state.get('connected'):
            return data
        oids = list(deletion_queue)
        orb.log.info(f'* replaying {len(oids)} queued offline deletion(s) ...')
        try:
            rpc = self.mbus.session.call('vger.delete', oids)
            rpc.addCallback(self.on_rpc_vger_delete_result)
            rpc.addErrback(self.on_failure)
        except:
            orb.log.debug('  ** rpc failed (possible loss of transport)')
            orb.log.debug('     queued deletions retained for the next sync.')
            self.set_bus_state()
        return data

    # ---------------------------------------------------------------------
    # OFFLINE PARAMETER / DATA ELEMENT DELETION QUEUE
    # ---------------------------------------------------------------------
    # Parameter and data element *additions and modifications* need no queue:
    # they are carried in the object's serialization, so they reach the
    # repository whenever the object itself is pushed -- which is why the
    # editor stamps mod_datetime on every parameter change, including adds
    # (see pgxnobject's drop handlers).
    #
    # Deletions cannot travel that way.  deserialize_parms() *merges*: it
    # assigns each pid present in the incoming dict and never removes one that
    # is absent, so "this pid is gone" and "this pid was not mentioned" are
    # indistinguishable to the server.  A parameter deleted offline therefore
    # survives on the server and is handed straight back by the next
    # get_parmz(), silently undoing the deletion -- exactly the failure the
    # object deletion queue exists to prevent, one level down.
    #
    # Ordering is load-bearing for the same reason: the replay must complete
    # before get_parmz(), which wholesale-replaces the local caches with the
    # server's copy.  Push before pull.
    # ---------------------------------------------------------------------

    def queue_parm_deletion(self, oid, item_id, kind='parm'):
        """
        Record a parameter or data element deletion that could not be sent.

        Args:
            oid (str):  oid of the object that owned the item
            item_id (str):  `id` of the parameter or data element

        Keyword Args:
            kind (str):  'parm' or 'de'
        """
        if not (oid and item_id):
            return
        key = f'{kind}|{oid}|{item_id}'
        parm_del_queue[key] = {'kind': kind, 'oid': oid, 'id': item_id,
                               'datetime': str(dtstamp())}
        # written immediately, not at shutdown (see queue_deletion)
        write_parm_del_queue(os.path.join(orb.home, 'parm_del_queue'))
        n = len(parm_del_queue)
        orb.log.info(f'  deletion of {kind} "{item_id}" from "{oid}" queued '
                     f'for sync ({n} queued).')

    def clear_queued_parm_deletion(self, msg, key=''):
        """
        Settle a queued item once the repository has answered.

        vger.del_parm() and vger.del_de() now authorize the caller and return
        a message beginning with "failure:" if they refuse, so a reply is not
        by itself a confirmation.  A refusal is still settled rather than
        retried -- the user will not acquire the permission by trying again,
        and an entry that can never succeed would be replayed on every sync
        forever -- but it is reported, because the local deletion is about to
        be undone by the next get_parmz() pulling the parameter back from the
        server.  That undo is correct (the server is authoritative); what
        would not be acceptable is its happening silently.

        Used as an rpc callback; `msg` is passed through so this can sit in a
        callback chain.
        """
        if msg:
            orb.log.info(f'* vger: {msg}.')
        if not key:
            return msg
        if key in parm_del_queue:
            del parm_del_queue[key]
            write_parm_del_queue(os.path.join(orb.home, 'parm_del_queue'))
        # the key encodes everything needed to describe the item, so this
        # reports the same way whether the deletion was queued offline or sent
        # live -- a refusal in the live path reverts the local cache just as
        # silently, and matters just as much
        kind, _, rest = key.partition('|')
        oid, _, item_id = rest.partition('|')
        what = 'data element' if kind == 'de' else 'parameter'
        item = f'{what} "{item_id}" of object "{oid}"'
        if isinstance(msg, str) and msg.startswith('failure:'):
            if 'not authorized' in msg:
                orb.log.info(f'  deletion of {item} was refused.')
                self.add_to_sync_report('parameter deletions refused', item)
            else:
                # e.g. the object itself is gone from the repository, which
                # makes the parameter deletion moot -- nothing to report
                orb.log.info(f'  deletion of {item} is moot: {msg}')
        else:
            n = len(parm_del_queue)
            orb.log.info(f'  deletion of {item} confirmed ({n} queued).')
        return msg

    def replay_parm_del_queue(self, data=None):
        """
        Replay queued offline parameter / data element deletions.

        Chained ahead of the rpc inside get_parmz() rather than merely placed
        early in the sync chain:  get_parmz() replaces the local caches
        wholesale with the server's copy (see the note above), and is also
        reached directly from the "parameters set" pubsub handler, which can
        arrive at any moment after reconnecting.  Guarding it at the one place
        the hazard actually is makes the ordering a guarantee rather than an
        accident of chain order.

        Entries are cleared only when the repository confirms them, so an
        interrupted sync retries rather than dropping the deletion.

        Keyword Args:
            data:  passed through for callback chaining (ignored)

        Returns:
            a DeferredList that fires once every queued deletion has been
            answered, or the 'data' argument if there was nothing to do.
            Callers that must not pull until the push has landed -- get_parmz()
            in particular -- should chain on the return value rather than
            assume this ran to completion.
        """
        if not parm_del_queue:
            return data
        if not state.get('connected'):
            return data
        n = len(parm_del_queue)
        orb.log.info(f'* replaying {n} queued offline parm/de deletion(s) ...')
        rpcs = []
        for key, entry in list(parm_del_queue.items()):
            oid = entry.get('oid') or ''
            item_id = entry.get('id') or ''
            if not (oid and item_id):
                # malformed entry: drop it rather than retry forever
                del parm_del_queue[key]
                write_parm_del_queue(os.path.join(orb.home, 'parm_del_queue'))
                continue
            if entry.get('kind') == 'de':
                rpc_name, kw = 'vger.del_de', {'oid': oid, 'deid': item_id}
            else:
                rpc_name, kw = 'vger.del_parm', {'oid': oid, 'pid': item_id}
            try:
                rpc = self.mbus.session.call(rpc_name, **kw)
                rpc.addCallback(self.clear_queued_parm_deletion, key=key)
                rpc.addErrback(self.on_failure)
                rpcs.append(rpc)
            except:
                orb.log.debug('  ** rpc failed (possible loss of transport)')
                orb.log.debug('     queued deletions retained for next sync.')
                self.set_bus_state()
                break
        if not rpcs:
            return data
        return DeferredList(rpcs, consumeErrors=True)

    def add_locally_created(self, oid):
        """
        Record an object as created here and not yet known to the repository.

        Args:
            oid (str):  oid of the object
        """
        if not oid:
            return
        oids = state.get('locally_created_oids') or []
        if oid not in oids:
            oids.append(oid)
            state['locally_created_oids'] = oids

    def clear_locally_created(self, oids):
        """
        Forget objects the repository has now confirmed it has.

        Args:
            oids (iterable of str):  oids the repository accepted
        """
        current = state.get('locally_created_oids') or []
        if not current:
            return
        remaining = [o for o in current if o not in set(oids or [])]
        if len(remaining) != len(current):
            n = len(current) - len(remaining)
            orb.log.debug(f'  {n} object(s) confirmed by the repository; '
                          'no longer "locally created".')
            state['locally_created_oids'] = remaining

    def on_remote_checked_out(self, content):
        """
        Handle the pubsub "checked out" message.

        Args:
            content (list of dict):  compact CheckOut records as produced by
                vger's serialize_checkout()
        """
        orb.log.debug('* pubsub: "checked out"')
        if not isinstance(content, list):
            orb.log.debug('  unexpected content format; ignored.')
            return
        checkouts = state.get('checkouts') or {}
        oids = []
        for rec in content:
            oid = (rec or {}).get('item_oid')
            if not oid:
                continue
            checkouts[oid] = {
                'userid': rec.get('userid', ''),
                'expiry_datetime': rec.get('expiry_datetime', ''),
                'purpose': rec.get('purpose', '')}
            oids.append(oid)
        state['checkouts'] = checkouts
        if oids:
            orb.log.debug(f'  {len(oids)} object(s) now checked out.')
            dispatcher.send(signal='checkouts changed', oids=oids)

    def on_remote_checked_in(self, content):
        """
        Handle the pubsub "checked in" message.

        Args:
            content (list of str):  oids of the objects whose claims were
                released
        """
        orb.log.debug('* pubsub: "checked in"')
        if not isinstance(content, list):
            orb.log.debug('  unexpected content format; ignored.')
            return
        checkouts = state.get('checkouts') or {}
        oids = []
        for oid in content:
            if oid in checkouts:
                del checkouts[oid]
                oids.append(oid)
        state['checkouts'] = checkouts
        if oids:
            orb.log.debug(f'  {len(oids)} object(s) released.')
            dispatcher.send(signal='checkouts changed', oids=oids)

    def get_checkouts(self, *args):
        """
        Refresh state['checkouts'] from the repository.

        NOTE: accepts (and ignores) positional args so it can be used
        directly as a deferred callback in the sync chain, where the
        preceding rpc's result is passed in.
        """
        if not state.get('connected'):
            return
        try:
            rpc = self.mbus.session.call('vger.get_checkouts')
            rpc.addCallback(self.on_get_checkouts_result)
            rpc.addErrback(self.on_failure)
        except:
            orb.log.debug('  ** vger.get_checkouts rpc failed.')

    def on_get_checkouts_result(self, data):
        """
        Handle the result of the 'vger.get_checkouts' rpc: replace the local
        mirror wholesale, since the repository is authoritative.
        """
        if not isinstance(data, list):
            orb.log.debug('* get_checkouts: unexpected result; ignored.')
            return
        checkouts = {}
        for rec in data:
            oid = (rec or {}).get('item_oid')
            if oid:
                checkouts[oid] = {
                    'userid': rec.get('userid', ''),
                    'expiry_datetime': rec.get('expiry_datetime', ''),
                    'purpose': rec.get('purpose', '')}
        state['checkouts'] = checkouts
        orb.log.info(f'* {len(checkouts)} active check-out(s) in repository.')
        dispatcher.send(signal='checkouts changed', oids=list(checkouts))

    def check_out_objects(self, oids, days=None, purpose=''):
        """
        Claim objects for offline editing (rpc "vger.check_out").

        Args:
            oids (list of str):  oids of the objects to claim
        """
        if not (state.get('connected') and oids):
            return
        orb.log.info(f'* requesting check-out of {len(oids)} object(s) ...')
        try:
            rpc = self.mbus.session.call('vger.check_out', oids,
                                         days=days, purpose=purpose)
            rpc.addCallback(self.on_check_out_result)
            rpc.addErrback(self.on_failure)
        except:
            orb.log.debug('  ** vger.check_out rpc failed.')

    def on_check_out_result(self, res):
        """
        Handle the result of 'vger.check_out'. Denials are reported rather
        than dropped -- see the reconciliation-reporting rationale in
        NOTES_ON_OFFLINE_AND_SYNC.md.
        """
        try:
            granted = res.get('granted') or []
            denied = res.get('denied') or {}
        except:
            orb.log.debug('* check_out: unexpected result; ignored.')
            return
        orb.log.info(f'* check-out: {len(granted)} granted, '
                     f'{len(denied)} denied.')
        for oid, reason in denied.items():
            obj = orb.get(oid)
            obj_id = getattr(obj, 'id', None) or oid
            orb.log.info(f'    - {obj_id}: {reason}')
        # the repository publishes "checked out", which updates the mirror;
        # refresh anyway so the caller sees the result immediately
        self.get_checkouts()
        if denied:
            msg = (f'{len(granted)} item(s) checked out, '
                   f'{len(denied)} refused (see log)')
            QTimer.singleShot(0, lambda: self.statusbar.showMessage(msg))

    def check_in_objects(self, oids):
        """
        Release the user's own claims (rpc "vger.check_in").

        Args:
            oids (list of str):  oids of the objects to release
        """
        if not (state.get('connected') and oids):
            return
        orb.log.info(f'* checking in {len(oids)} object(s) ...')
        try:
            rpc = self.mbus.session.call('vger.check_in', oids)
            rpc.addCallback(self.on_check_in_result)
            rpc.addErrback(self.on_failure)
        except:
            orb.log.debug('  ** vger.check_in rpc failed.')

    def on_check_in_result(self, res):
        """
        Handle the result of 'vger.check_in'.
        """
        try:
            checked_in = res.get('checked_in') or []
            not_held = res.get('not_held') or []
        except:
            orb.log.debug('* check_in: unexpected result; ignored.')
            return
        orb.log.info(f'* check-in: {len(checked_in)} released, '
                     f'{len(not_held)} not held by this user.')
        self.get_checkouts()

    def prepare_for_offline_work(self):
        """
        Let the user claim ("check out") the objects they intend to edit
        while disconnected, so that no one else changes them meanwhile.

        NOTE (phase 1): check-outs are advisory -- they are recorded,
        published and displayed, but access.py does not consult them yet, so
        claiming an object does not by itself change what may be edited.
        See pangalactic.core/NOTES_ON_CHECKOUT_MODEL.md.
        """
        orb.log.info('* prepare for offline work ...')
        if not state.get('connected'):
            # claims are granted by the repository, so this needs a
            # connection -- and the whole point is to do it *before*
            # disconnecting
            notice = QMessageBox(QMessageBox.Warning,
                    'Not Connected',
                    'You must be connected to the repository to check out '
                    'items for offline work.', QMessageBox.Ok, self)
            notice.exec_()
            return
        project = self.project
        if not project:
            notice = QMessageBox(QMessageBox.Warning,
                    'No Project Selected',
                    'Select a project before preparing for offline work.',
                    QMessageBox.Ok, self)
            notice.exec_()
            return
        dlg = PrepareForOfflineDialog(project, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            oids = dlg.get_selected_oids()
            if oids:
                self.check_out_objects(oids, days=dlg.get_days(),
                                       purpose=dlg.get_purpose())
            else:
                orb.log.info('  nothing selected -- nothing checked out.')

    def on_toggle_library_size(self, expand=False):
        if getattr(self, 'library_widget', None):
            if expand:
                self.library_widget.setMaximumWidth(600)
                self.library_widget.setMinimumWidth(600)
                self.library_widget.expanded = True
            else:
                self.library_widget.setMaximumWidth(200)
                self.library_widget.setMinimumWidth(200)
                self.library_widget.expanded = False
            self.update()

    def on_pubsub_msg(self, msg):
        """
        Handle pubsub messages.

        Args:
            msg (tuple): the message, a tuple of (subject, content)
        """
        userid = state.get('userid', '')
        # NOTE: this loop handles each subject in the message independently, so
        # the "ignore, it was my own action" paths below use "continue" rather
        # than "return" -- a "return" would abandon any remaining subjects in
        # the same message. Every vger.publish() currently sends a single-key
        # dict, so this has not been reachable, but the loop's contract should
        # not depend on that.
        for item in msg.items():
            subject, content = item
            orb.log.info("* pubsub msg received ...")
            orb.log.info("  subject: {}".format(subject))
            # orb.log.debug("  content: {}".format(content))
            obj_id = '[unknown]'
            # base msg
            log_msg = "  "
            if subject == 'decloaked':
                # NOTE: content of 'decloaked' msg changed in version 4.3
                # -- it is now a tuple: (authid, list of serialized objects)
                n = len(content)
                orb.log.debug(f'received {n} "decloaked" object(s)')
                authid, sobjs = content
                if authid == userid:
                    # ignore -- result of my action
                    orb.log.info('  "decloaked" ignored -- was my action.')
                    continue
                self.on_received_objects(sobjs)
            elif subject == 'new':
                # NOTE: content of 'new' msg changed in version 4.3
                # -- it is now a tuple: (authid, list of serialized objects)
                authid, sobjs = content
                if authid == userid:
                    # ignore -- result of my action
                    orb.log.info('  "new" ignored -- was my action.')
                    continue
                n = len(sobjs)
                orb.log.debug(f'received {n} "new" object(s)')
                self.on_received_objects(sobjs)
            elif subject == 'modified':
                # NOTE: content of 'modified' msg changed in version 4.3
                # -- it is now a tuple: (userid, list of serialized objects)
                authid, sobjs = content
                if authid == userid:
                    # ignore -- result of my action
                    orb.log.info('  "modified" ignored -- was my action.')
                    continue
                # n = len(sobjs)
                # orb.log.debug(f'received {n} modified object(s)')
                self.on_received_objects(sobjs)
            elif subject == 'new mode defs':
                orb.log.debug('  - vger pubsub msg: "new mode defs" ...')
                # NOTE: "md_userid" -- NOT "userid": the publisher's id must
                # not clobber the local user's id unpacked above, which the
                # "was my action" tests in the other branches depend on
                md_dts, project_oid, md_data, md_userid = content
                # orb.log.debug('    content:')
                orb.log.debug('==============================================')
                orb.log.debug('New project mode definitions:')
                orb.log.debug(f'- datetime stamp: {md_dts}')
                orb.log.debug(f'- userid:         {md_userid}')
                orb.log.debug('- <data>')
                # orb.log.debug(f'  {md_data}')
                orb.log.debug('==============================================')
                if md_userid == state.get('userid'):
                    # originated from me -- set dts to server's dts
                    state['mode_defz_dts'] = md_dts
                    orb.log.debug('    msg was from my action; ignoring.')
                else:
                    local_md_dts = state.get('mode_defz_dts')
                    if (local_md_dts is None) or (md_dts > local_md_dts):
                        if project_oid in mode_defz:
                            del mode_defz[project_oid]
                        mode_defz[project_oid] = md_data
                        state['mode_defz_dts'] = md_dts
                        orb.log.debug('    mode_defz updated.')
                        orb.log.debug('    dispatching "modes published"')
                        dispatcher.send(signal='modes published')
                    else:
                        orb.log.debug('    same datetime stamp; ignored.')
            elif subject == 'comp mode datum updated':
                orb.log.debug('  - vger msg: "comp mode datum updated" ...')
                # NOTE: "md_userid" -- NOT "userid"; see the note in the
                # "new mode defs" branch above
                (project_oid, link_oid, comp_oid, mode, value, md_dts,
                                                        md_userid) = content
                project = orb.get(project_oid)
                link = orb.get(link_oid)
                comp = orb.get(comp_oid)
                if project and link and comp:
                    # orb.log.debug('    content:')
                    orb.log.debug('=========================================')
                    orb.log.debug('Component Mode datum updated:')
                    orb.log.debug(f'- project:        {project.id}')
                    orb.log.debug(f'- link:           {link.id}')
                    orb.log.debug(f'- comp:           {comp.id}')
                    orb.log.debug(f'- mode:           {mode}')
                    orb.log.debug(f'- value:          {value}')
                    orb.log.debug(f'- userid:         {md_userid}')
                    orb.log.debug(f'- datetime stamp: {md_dts}')
                    orb.log.debug('=========================================')
                else:
                    orb.log.debug('    unknown project or link; ignoring.')
                    continue
                if md_userid == state.get('userid'):
                    # originated from me -- set dts to server's dts
                    state['mode_defz_dts'] = md_dts
                    orb.log.debug('    msg was from my action; ignoring.')
                else:
                    set_modal_context(project_oid, link_oid, comp_oid, mode,
                                      value)
                    # mode_defz[project_oid]['components'][link_oid][comp_oid][
                                                                # mode] = value
                    state['mode_defz_dts'] = md_dts
                    orb.log.debug('    mode_defz updated.')
                    orb.log.debug('    sending "remote comp mode datum"')
                    dispatcher.send(signal='remote comp mode datum',
                                    project_oid=project_oid,
                                    link_oid=link_oid,
                                    comp_oid=comp_oid,
                                    mode=mode,
                                    value=value)
            elif subject == 'deleted':
                orb.log.debug('  - pubsub msg received: "deleted" ...')
                obj_oid = content
                obj = orb.get(obj_oid)
                if obj:
                    obj_id = obj.id
                    cname = obj.__class__.__name__
                    log_msg += obj_id
                    # self.remote_deleted_object.emit(obj_oid, cname)
                    # -----------------------------------------
                    # NOTE: VERY IMPORTANT TO USE remote=True
                    # -----------------------------------------
                    dispatcher.send(signal="deleted object", oid=obj_oid,
                                    cname=cname, remote=True)
            elif subject == 'frozen':
                # content is a list of tuples:
                #   (obj.oid, str(obj.mod_datetime), obj.modifier.oid) 
                frozen_attrs = content
                if frozen_attrs:
                    orb.log.info('* "frozen" msg received')
                    items = []
                    oids = []
                    for attrs in frozen_attrs:
                        frozen_oid, frozen_mod_dts, frozen_modifier = attrs
                        obj = orb.get(frozen_oid)
                        if obj:
                            oids.append(frozen_oid)
                            items.append(f'<b>{obj.id}</b> ({obj.name})')
                    if oids:
                        # phrase = "products have been"
                        # if len(items) == 1:
                            # phrase = "product has been"
                        # html = f'<p>The following {phrase} <b>frozen</b><br>'
                        # html += 'in the repository:</p><ul>'
                        # items.sort()
                        # for item in items:
                            # html += f'<li>{item}</li>'
                        # html += '</ul></p>'
                        # dlg = FrozenDialog(html, parent=self)
                        # dlg.show()
                        log_msg = 'vger: object(s) have been frozen ... '
                        log_msg += f'{len(oids)} found locally '
                        log_msg += '-- getting frozen versions ...'
                        self.on_remote_freeze_or_thaw(frozen_attrs, 'freeze')
            elif subject == 'thawed':
                # content is a list of tuples of the form:
                #   (obj.oid, str(obj.modified_datetime), obj.modifier.oid)
                orb.log.info('* "thawed" msg received ...')
                thawed_attrs = content
                if thawed_attrs:
                    orb.log.info('  on oids:')
                    items = []
                    oids = []
                    if (isinstance(thawed_attrs, list) and len(thawed_attrs) > 0):
                        for attrs in thawed_attrs:
                            oid, dts, modifier_oid = attrs
                            orb.log.info(f'  {oid}')
                            obj = orb.get(oid)
                            if obj:
                                oids.append(oid)
                                items.append(f'<b>{obj.id}</b> ({obj.name})')
                    else:
                        orb.log.info('  but it had bad format!')
                    if oids:
                        # phrase = "products have been"
                        # if len(items) == 1:
                            # phrase = "product has been"
                        # html = f'<p>The following {phrase} <b>thawed</b><br>'
                        # html += 'in the repository:</p><ul>'
                        # items.sort()
                        # for item in items:
                            # html += f'<li>{item}</li>'
                        # html += '</ul></p>'
                        # notice = QMessageBox(QMessageBox.Information, 'Thawed',
                                     # html, QMessageBox.Ok, self)
                        # notice.show()
                        log_msg = 'vger: objects have been thawed ...'
                        log_msg += f'{len(oids)} found locally '
                        log_msg += '-- getting thawed versions ...'
                        self.on_remote_freeze_or_thaw(thawed_attrs, 'thaw')
                else:
                    orb.log.info('  but it was empty!')
            elif subject == 'checked out':
                self.on_remote_checked_out(content)
            elif subject == 'checked in':
                self.on_remote_checked_in(content)
            elif subject == 'properties set':
                self.on_remote_properties_set(content)
            elif subject == 'parameters set':
                self.get_parmz()
            elif subject == 'data elements set':
                self.on_remote_data_elements_set(content)
            elif subject == 'de added':
                self.on_remote_de_added(content)
            elif subject == 'de del':
                self.on_remote_de_del(content)
            elif subject == 'parm added':
                self.on_remote_parm_added(content)
            elif subject == 'parm del':
                self.on_remote_parm_del(content)
            elif subject == 'lom parms':
                dispatcher.send(signal="got lom parms", content=content)
            elif subject == 'organization':
                obj_oid = content['oid']
                obj_id = content['id']
                log_msg += obj_id
            elif subject == 'person added':
                try:
                    pk_added, ser_objs = content
                    objs = deserialize(orb, ser_objs)
                    if objs:
                        # NOTE: if the deserializer returned person and/or
                        # organization objects, it means we are not the ones
                        # who called vger.add_person(), so display a message in
                        # the status bar and log this ...
                        for obj in objs:
                            if isinstance(obj, orb.classes['Person']):
                                display_name = '{}, {} {} ({})'.format(
                                                                obj.last_name,
                                                                obj.first_name,
                                                                obj.mi_or_name,
                                                                obj.org.name)
                                txt = f'person "{display_name}" saved.'
                                orb.log.debug(f'  - {txt}')
                                log_msg += ' ... ' + txt
                                dispatcher.send('person added', obj=obj,
                                                display_name=display_name,
                                                pk_added=pk_added)
                            elif isinstance(obj, orb.classes['Organization']):
                                orb.log.debug('  - org "{}" saved.'.format(
                                                                    obj.name))
                except:
                    d = str(content)
                    orb.log.debug(f'- could not process received data: {d}')
            orb.log.debug(log_msg)

    def on_add_person(self, data=None):
        """
        Send 'vger.add_person' rpc when 'add person' signal is received.
        """
        orb.log.info("* on_add_person()")
        if state['connected']:
            try:
                rpc = self.mbus.session.call('vger.add_person', data)
                rpc.addCallback(self.on_rpc_add_person_result)
                rpc.addErrback(self.on_failure)
            except:
                orb.log.debug('  ** rpc failed (possible loss of transport)')
                orb.log.debug('     trying to reconnect ...')
                self.set_bus_state()
        else:
            orb.log.info('  not connected, cannot call "add_person()" rpc.')

    def on_rpc_add_person_result(self, res):
        """
        Handle the result of 'vger.add_person' rpc.

        Arg:
            res (list): if the rpc was successful, a list of serialized
                objects; otherwise, an empty list
        """
        if res:
            pk_added, ser_objs = res
            userid = ''
            for so in ser_objs:
                if so.get('_cname') == 'Person':
                    userid = so.get('id') or ''
            # NOTE: guarded the same way person_dlg is just below -- the admin
            # tool may never have been opened in this session
            admin_dlg = getattr(self, 'admin_dlg', None)
            if admin_dlg:
                admin_dlg.on_person_added_success(userid=userid,
                                                  pk_added=pk_added)
            if (getattr(self, 'person_dlg', None) and
                getattr(self.person_dlg, 'add_person_dlg', None)):
                try:
                    self.person_dlg.add_person_dlg.close()
                    self.person_dlg.close()
                except:
                    pass
        else:
            orb.log.debug('- rpc failed: no data received!')

    def on_update_person(self, data=None):
        """
        Send 'vger.update_person' rpc when 'update person' signal is received.
        """
        pass

    def on_delete_person(self, data=None):
        """
        Send 'vger.delete_person' rpc when 'delete person' signal is received.
        """
        pass

    def on_get_people(self):
        """
        Send 'vger.get_people' rpc when 'get people' signal is received from
        the admin tool.
        """
        orb.log.info("* on_get_people()")
        if state['connected']:
            try:
                rpc = self.mbus.session.call('vger.get_people')
                rpc.addCallback(self.on_rpc_get_people_result)
                rpc.addErrback(self.on_failure)
            except:
                orb.log.debug('  ** rpc failed (possible loss of transport)')
                orb.log.debug('     trying to reconnect ...')
                self.set_bus_state()
        else:
            orb.log.info("  not connected -- cannot get people from repo.")

    def on_rpc_get_people_result(self, res):
        """
        Handle the result of 'vger.get_people' rpc.

        Arg:
            res (list): if the rpc was successful, a list of lists
                (has_pk, serialized Person); otherwise, an empty list
        """
        orb.log.debug("* on_rpc_get_people_result()")
        orb.log.debug("  res: {}".format(str(res)))
        if res:
            actives = 0
            state['active_users'] = []
            try:
                for r in res:
                    # orb.log.debug("  * len: {}, 0: {}, 1: {}".format(
                                  # len(r), str(r[0]), str(r[1])))
                    if r[0]:
                        actives += 1
                        state['active_users'].append(r[1]['id'])
            except:
                orb.log.debug('  - could not process received data.')
            finally:
                orb.log.debug('  - active users: {}'.format(
                              state['active_users']))
                # NOTE: this runs even when the loop above raised, so it must
                # not assume the admin tool exists
                admin_dlg = getattr(self, 'admin_dlg', None)
                if admin_dlg:
                    admin_dlg.on_got_people()
        else:
            orb.log.debug('- rpc failed: no data received!')

    def on_received_objects(self, content=None):
        """
        Handle the result of the rpc 'vger.get_object', pubsub messages sent
        from 'vger.save', and other rpcs that return lists of serialized
        objects, and pubsub messages "decloaked", "new", and "modified", for
        which the content is a list of serialized objects.

        Args:
            content (list): a list of serialized objects
        """
        orb.log.debug("* on_received_objects")
        serialized_objects = content
        # if serialized_objects:
            # n = len(serialized_objects)
            # orb.log.debug(f"  got {n} serialized objects")
        # else:
            # orb.log.debug('  content was empty!')
        if not serialized_objects:
            return False
        # **************************************************************
        # NOTE:  using load_serialized_objects() here led to problematic
        # behavior due to unordered asynchronous operations
        # **************************************************************
        # NOTE:  ignore None or "empty" objects
        ser_objs = [so for so in serialized_objects if so]
        objs = deserialize(orb, ser_objs, force_no_recompute=True)
        # objs = self.load_serialized_objects(ser_objs)
        if objs:
            orb.log.debug(f'  deserialize() returned {len(objs)} object(s):')
            txt = str([o.id for o in objs if o is not None])
            orb.log.debug(f'  {txt}')
        else:
            orb.log.debug('  deserialize() returned no objects --')
            orb.log.debug('  (any received were already in the local db).')
        if not objs:
            return False
        rep = '\n  '.join([(obj.name or obj.id or 'no name or id') +
                            " (" + obj.__class__.__name__ + ")"
                           for obj in objs])
        # orb.log.debug('  deserializes as:')
        orb.log.debug('  received:')
        orb.log.debug('  {}'.format(str(rep)))
        lib_updates_needed = []
        need_to_refresh_tree = False
        need_to_refresh_diagram = False
        to_delete = []
        new_or_modified_acts = []
        for obj in objs:
            # TODO: check whether object is actually being displayed in system
            # tree and/or diagram before rebuilding them ...
            # ================================================================
            # TODO: set up state as a dict {cname : [list of oids]} so adds /
            # mods can be done using orb.get() then add|mod|del_object()
            # ================================================================
            oid = obj.oid
            cname = obj.__class__.__name__
            # ================================================================
            if self.mode == 'db' and cname == state.get('current_cname'):
                # object is in the current db table ...
                state['update db table'] = True
            # ================================================================
            if cname in ['ParameterDefinition',
                         'DataElementDefinition',
                         'HardwareProduct',
                         'Template',
                         'PortTemplate',
                         'PortType']:
                if lib_updates_needed:
                    lib_updates_needed.append(oid)
                else:
                    lib_updates_needed = [oid]
            if isinstance(obj, (orb.classes['Port'],
                                orb.classes['Flow'],
                                orb.classes['HardwareProduct'])):
                need_to_refresh_diagram = True
            elif isinstance(obj, (orb.classes['Acu'],
                                  orb.classes['ProjectSystemUsage'])):
                # NOTE:  SANDBOX PSUs are not synced, so any that are received
                # from the server are errors and will be ignored
                if (hasattr(obj, 'project') and
                    obj.project is self.sandbox):
                    to_delete.append(obj)
                    continue
                need_to_refresh_diagram = True
                if hasattr(self, 'sys_tree'):
                    need_to_refresh_tree = True
            elif isinstance(obj, orb.classes['RoleAssignment']):
                if getattr(obj, 'assigned_to', None) is self.local_user:
                    html = '<h3>You have been assigned the role:</h3>'
                    html += '<p><b><font color="green">{}</font></b>'.format(
                                                      obj.assigned_role.name)
                    context = getattr(obj.role_assignment_context, 'id',
                                                        'global context')
                    content = 'in <b><font color="green">{}</font></b></p>'
                    html += f' {content}'.format(context)
                    self.w = NotificationDialog(html, parent=self)
                    self.w.show()
                # whether ra applies to this user or not, send signal to
                # refresh the admin tool
                # TODO: move this signal to after get_parmz() ...
                dispatcher.send(signal='refresh admin tool')
                self.update_project_role_labels()
            elif cname == 'Requirement':
                if state.get('new_or_modified_rqts'):
                    state['new_or_modified_rqts'].append(obj.oid)
                else:
                    state['new_or_modified_rqts'] = [obj.oid]
            elif cname == 'Activity':
                orb.log.debug(f'  received Activity "{obj.name}"')
                new_or_modified_acts.append(obj)
        if to_delete:
            # delete any SANDBOX PSUs that were received
            orb.delete(to_delete)
        # ================================================================
        # TODO: use update_object_in_tree() (use oid to get obj ...)
        # ================================================================
        if (need_to_refresh_tree and state.get('mode') == 'system'):
            state['tree needs refresh'] = True
        if (need_to_refresh_diagram and
            getattr(self, 'system_model_window', None)):
            # set state to rebuild diagram in case an object corresponded to a
            # block in the current diagram -- will be rebuilt in handling of
            # get_parmz()
            state['diagram needs refresh'] = True
        if lib_updates_needed and hasattr(self, 'library_widget'):
            # set state for library classes whose widgets need a refresh ...
            # lmsg = f'  state["lib updates needed"] = {lib_updates_needed}'
            # orb.log.debug(lmsg)
            state["lib updates needed"] = lib_updates_needed
        if state.get('new_or_modified_rqts'):
            oids = state['new_or_modified_rqts']
            state['new_or_modified_rqts'] = []
            dispatcher.send(signal='remote new or mod rqts', oids=oids)
        if new_or_modified_acts:
            dispatcher.send(signal='remote new or mod acts',
                            objs=new_or_modified_acts)
        self.get_parmz()
        return True

    def _create_actions(self):
        # orb.log.debug('* creating actions ...')
        self.about_action = self.create_action(
                                    "About",
                                    slot=self.show_about,
                                    tip=f"About {self.app_name}")
        self.user_guide_action = self.create_action(
                                    "User Guide",
                                    slot=self.show_user_guide,
                                    icon='tardis',
                                    tip="User Guide / Getting Started")
        self.reference_action = self.create_action(
                                    "Reference Manual",
                                    slot=self.show_ref_manual,
                                    tip="Detailed Reference Information")
        self.new_project_action = self.create_action(
                                    "New Project",
                                    slot=self.new_project,
                                    tip="Create a New Project")
        self.delete_project_action = self.create_action(
                                    "Delete Project",
                                    slot=self.delete_project,
                                    tip="Delete the current Project")
        # default:  delete_project_action is not visible
        self.delete_project_action.setEnabled(False)
        self.delete_project_action.setVisible(False)
        # Administer roles
        admin_action_tip = "Add Users and Assign Roles"
        self.admin_action = self.create_action(
                                    "Administer Users and Roles",
                                    slot=self.do_admin_stuff,
                                    tip=admin_action_tip)
        # default:  admin_action is not visible
        self.admin_action.setEnabled(False)
        self.admin_action.setVisible(False)
        self.set_project_action = self.create_action(
                                    "Set Project",
                                    slot=self.set_current_project,
                                    tip="Switch to a selected Project")
        # self.display_disciplines_action = self.create_action(
                                    # "Display Disciplines",
                                    # slot=self.display_disciplines,
                                    # tip="Display List of Disciplines",
                                    # modes=['system', 'component'])
        self.rqts_manager_action = self.create_action(
                                "Project Requirements Manager",
                                slot=self.display_rqts_manager,
                                icon='lander',
                                tip="Manage Requirements for this Project",
                                modes=['system', 'component', 'db'])
        conops_tip_text = "Define a Concept of Operations & System Power Modes"
        self.conops_modeler_action = self.create_action(
                                "ConOps Modeler",
                                slot=self.conops_modeler,
                                icon='tools',
                                tip=conops_tip_text,
                                modes=['system', 'component'])
        self.modeler42_action = self.create_action(
                                "42 ACS Modeler",
                                slot=self.sc_42_modeler,
                                icon='lander',
                                tip="42 Attitude Control System Modeler",
                                modes=['system', 'component'])
        self.step_import_action = self.create_action(
                                "Import STEP Assembly",
                                slot=self.step_import,
                                icon='box',
                                tip="Import an assembly's structure and "
                                    "component placements from a STEP file",
                                modes=['system', 'component'])
        hw_lib_title = "Systems and Components (Hardware Products) Library"
        hw_lib_tip = "Library of Hardware Product Specifications"
        self.product_lib_action = self.create_action(
                                    hw_lib_title,
                                    slot=self.product_library,
                                    icon='part',
                                    tip=hw_lib_tip,
                                    modes=['system', 'component', 'db'])
        template_lib_title = "System and Component Templates Library"
        self.template_lib_action = self.create_action(
                                    template_lib_title ,
                                    slot=self.template_library,
                                    icon='Template',
                                    tip=template_lib_title,
                                    modes=['system', 'component', 'db'])
        self.product_types_lib_action = self.create_action(
                                    "Product Types Library",
                                    slot=self.product_types_library,
                                    tip="A list of pre-defined Product Types",
                                    modes=['system', 'component', 'db'])
        port_type_lib_title = "Port Types Library"
        port_type_lib_tip = "Types of ports available for use in diagrams"
        self.port_type_lib_action = self.create_action(
                                    port_type_lib_title,
                                    slot=self.port_type_library,
                                    icon='PortType',
                                    tip=port_type_lib_tip,
                                    modes=['system', 'component', 'db'])
        port_lib_title = "Port Templates Library"
        self.port_template_lib_action = self.create_action(
                                    port_lib_title,
                                    slot=self.port_template_library,
                                    icon='PortTemplate',
                                    tip=port_lib_title,
                                    modes=['system', 'component', 'db'])
        de_def_lib_title = "Data Element Definitions Library"
        self.de_def_lib_action = self.create_action(
                                    de_def_lib_title,
                                    slot=self.de_def_library,
                                    icon='parameter',
                                    tip=de_def_lib_title,
                                    modes=['system', 'component', 'db'])
        pd_lib_title = "Parameter Definitions Library"
        pd_lib_tip = "Definitions and dimensionality of available parameters"
        self.parameter_lib_action = self.create_action(
                                    pd_lib_title,
                                    slot=self.parameter_library,
                                    icon='parameter',
                                    tip=pd_lib_tip,
                                    modes=['system', 'component', 'db'])
        self.new_product_action = self.create_action(
                                    "New System or Component (HW Product)",
                                    slot=self.new_product,
                                    icon='new_part',
                                    tip="Create a New System or Component",
                                    modes=['system', 'component', 'db'])
        self.new_functional_rqt_action = self.create_action(
                                    "New Functional Requirement",
                                    slot=self.new_functional_rqt,
                                    icon="new_doc",
                                    tip="Define a New Functional Requirement",
                                    modes=['system'])
        self.new_performance_rqt_action = self.create_action(
                                    "New Performance Requirement",
                                    slot=self.new_performance_rqt,
                                    icon="new_doc",
                                    tip="Define a New Performance Requirement",
                                    modes=["system"])
        # self.data_element_action = self.create_action(
                                    # "New Data Element",
                                    # slot=self.new_data_element,
                                    # icon="new_doc",
                                    # tip="Create a New Data Element",
                                    # modes=['system', 'component', 'db'])
        # "open_3d_model_file" opens an external viewer ...
        self.view_3d_model_action = self.create_action(
                                    "View a 3D (CAD) Model...",
                                    slot=self.open_3d_model_file,
                                    icon="box",
                                    tip="Import & view a STEP or STL model",
                                    modes=['system', 'component'])
        self.export_project_to_file_action = self.create_action(
                                "Export Project to a File...",
                                slot=self.export_project_to_file,
                                tip="Export Project to an importable File...",
                                modes=['system'])
        mel_tip = 'Output a Master Equipment List'
        mel_tip += ' ["MEL", aka "Bill of Materials"] to Excel'
        self.output_mel_action = self.create_action(
                                "Write MEL (BOM) to Excel...",
                                slot=self.output_mel,
                                tip=mel_tip,
                                modes=['system', 'component'])
        self.dump_db_action = self.create_action(
                                "Dump Local Database to a File...",
                                slot=self.dump_database,
                                tip="Dump DB...",
                                modes=['system', 'component', 'db'])
        self.gen_keys_action = self.create_action(
                                "Generate a Public/Private Key Pair...",
                                slot=self.gen_keys,
                                tip="Generate credentials for authentication",
                                modes=['system', 'component', 'data', 'db'])
        # actions accessible via the 'Import Data or Objects' toolbar menu:
        # * import_rqts_excel_action
        self.import_rqts_excel_action = self.create_action(
                                    "Import Requirements from Excel...",
                                    tip="Use a wizard to import requirements",
                                    slot=self.import_rqts_from_excel)
        # * import_products_excel_action
        self.import_products_excel_action = self.create_action(
                                    "Import Products from Excel...",
                                    tip="Use a wizard to import new products",
                                    slot=self.import_products_from_excel)
        # * import_objects (import project or other serialized objs)
        self.import_objects_action = self.create_action(
                        "Import Serialized Objects...",
                        slot=self.import_objects,
                        tip="Import Serialized Objects from a File...",
                        modes=['system'])
        # * load_test_objects
        # Load Test Objects needs more work -- make it local, or at least
        # non-polluting somehow ...
        # self.load_test_objects_action = self.create_action(
                                    # "Load Test Objects",
                                    # slot=self.load_test_objects)
        self.connect_to_bus_action = self.create_action(
                                    "Repository Service",
                                    slot=self.set_bus_state,
                                    icon="system",
                                    checkable=True,
                                    tip="Connect to the Repository (database)")
        self.component_mode_action = self.create_action(
                                    "Component Modeler",
                                    slot=self._set_component_mode,
                                    icon="part",
                                    checkable=True,
                                    tip="Component Modeler")
        self.system_mode_action = self.create_action(
                                    "System Modeler",
                                    slot=self._set_system_mode,
                                    icon="favicon",
                                    checkable=True,
                                    tip="System Modeler")
        self.db_mode_action = self.create_action(
                                    "Local DB",
                                    slot=self._set_db_mode,
                                    icon="db",
                                    checkable=True,
                                    tip="Local DB")
        # self.data_mode_action = self.create_action(
                                    # "Data Mode",
                                    # slot=self._set_data_mode,
                                    # icon="data",
                                    # checkable=True,
                                    # tip="Data Mode")
        # self.data_mode_action.setEnabled(True)
        self.edit_prefs_action = self.create_action(
                                    "Edit Preferences",
                                    slot=self.edit_prefs)
        self.del_test_objs_action = self.create_action(
                                    "Delete Test Objects",
                                    slot=self.delete_test_objects)
        self.sync_project_action = self.create_action(
                                    "Re-Sync Current Project",
                                    slot=self.resync_current_project,
                                    modes=['system', 'component'])
        self.sync_all_projects_action = self.create_action(
                                    "Re-Sync All Projects",
                                    slot=self.resync_all_projects,
                                    modes=['system', 'component'])
        self.full_resync_action = self.create_action(
                                    "Force Full Re-Sync",
                                    slot=self.full_resync,
                                    modes=['system', 'component'])
        self.prepare_offline_action = self.create_action(
                                    "Prepare for Offline Work ...",
                                    slot=self.prepare_for_offline_work,
                                    modes=['system', 'component'])
        self.refresh_tree_action = self.create_action(
                                    "Refresh System Tree and Dashboard",
                                    slot=self.refresh_tree_and_dashboard,
                                    modes=['system'])
        self.update_pgxno_action = self.create_action(
                                    "Update Editor",
                                    slot=self.update_pgxno,
                                    modes=['system'])
        # self.compare_items_action = self.create_action(
                                    # "Compare Items by Parameters",
                                    # slot=self.compare_items)
        # self.exit_action = self.create_action(
                                    # "Exit",
                                    # slot=self.close)
        # set up a group for mode actions
        mode_action_group = QActionGroup(self)
        self.component_mode_action.setActionGroup(mode_action_group)
        self.system_mode_action.setActionGroup(mode_action_group)
        self.db_mode_action.setActionGroup(mode_action_group)
        # NOTE: "data mode" is disabled for now as it may cause problems ...
        # self.data_mode_action.setActionGroup(mode_action_group)
        # orb.log.debug('  ... all actions created.')

    def create_action(self, text, slot=None, icon=None, tip=None,
                      checkable=False, modes=None):
        action = QAction(text, self)
        if icon is not None:
            icon_file = icon + state.get('icon_type', '.png')
            icon_dir = state.get('icon_dir', os.path.join(orb.home, 'icons'))
            icon_path = os.path.join(icon_dir, icon_file)
            action.setIcon(QIcon(icon_path))
        if tip is not None:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        if slot is not None:
            action.triggered.connect(slot)
        if checkable:
            action.setCheckable(True)
        if modes:
            for mode in modes:
                self.mode_widget_actions[mode].add(action)
        else:
            self.mode_widget_actions['all'].add(action)
        return action

    # 'mode' property (linked to state['mode'])
    def get_mode(self):
        """
        Get the current mode. (Default: 'system')
        """
        # # NOTE: this is used if 'data' mode is temporarily disabled:
        # if state.get('mode') == 'data':
            # state['mode'] = 'system'
        return state.get('mode', 'system')

    def set_mode(self, mode):
        """
        Set the current mode.
        """
        initial_size = self.size()
        if hasattr(orb, 'store'):
            orb.db.commit()
        modal_actions = set.union(*[a for a in
                                    self.mode_widget_actions.values()])
        if mode in self.modes:
            current_mode = state.get('mode')
            if current_mode in self.modes:
                self.main_states[current_mode] = self.saveState(
                                            self.modes.index(current_mode))
            state['mode'] = mode
            for action in modal_actions:
                action.setVisible(False)
            for action in set.union(self.mode_widget_actions[mode],
                                    self.mode_widget_actions['all']):
                action.setVisible(True)
            self._update_modal_views()
            # NOTE: the saved_state stuff does not seem to be doing anything so
            # commented out for now ...
            # saved_state = self.main_states.get(mode)
            # if saved_state:
                # self.restoreState(saved_state, self.modes.index(mode))
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

    @property
    def cnames(self):
        """
        Sorted list of class names.
        """
        names = list(orb.classes.keys())[:]
        names.sort()
        return names

    @property
    def user_home(self):
        """
        Path to the user's home directory.

        NOTE: this used to be derived as the *parent of orb.home*, which is
        only correct when the app home sits exactly one level below the user's
        home directory -- an assumption broken by the "if all else fails"
        fallbacks that place the app home under the current working directory,
        and by any explicitly-passed nested --home path.  Where it broke,
        key_path() below looked for the user's private key in the wrong
        directory.  It now asks p.core.get_user_home(), and keeps the old
        derivation only as a fallback for the case where neither HOME nor
        USERPROFILE is set.
        """
        home = get_user_home()
        if home:
            return home
        return str(Path(orb.home).resolve().parent)

    @property
    def key_path(self):
        """
        Path to the private key used for cryptosign auth.
        """
        # NOTE: the intent is that the same key pair can be used for any
        # version of any app release mode (dev, test, or production), since
        # they all have the same app_base_name and the private key is stored in
        # the user's home directory, so it is not removed or altered when a new
        # release is installed.
        if not self.key_file_name:
            self.key_file_name = self.app_base_name.lower() + '.key'
        return os.path.join(self.user_home, self.key_file_name)

    @property
    def populated(self):
        """
        Class names for which the corresponding db table is non-empty.
        """
        names = [c for c in orb.classes if orb.get_count(c)]
        names.sort()
        return names

    @property
    def dashboard(self):
        """
        Current dashboard widget.
        """
        dash_name = state.get('dashboard_name')
        multidash = getattr(self, 'multidashboard', None)
        if (multidash and dash_name in prefs.get('dashboard_names', [])):
            idx = prefs['dashboard_names'].index(dash_name)
            return multidash.dashboards.widget(idx)
        else:
            dash = QLabel('No Project Selected')
            dash.setStyleSheet('font-weight: bold; font-size: 16px')
            return dash

    def get_project(self):
        """
        Get the current project (or SANDBOX project if not set).
        """
        # if project in saved state is not found, return SANDBOX project
        return orb.get(state.get('project') or '') or self.sandbox

    def set_project(self, p):
        """
        Set the current project.

        Args:
            p (Project):  Project instance to be set
        """
        if p:
            orb.log.debug(f'* set_project({str(p.id)})')
            state['project'] = p.oid
            if state['connected']:
                self.role_label.setText(f'online: syncing {p.id} data ...')
            else:
                self.role_label.setText(f'loading {p.id} data ...')
        else:
            # orb.log.debug('* set_project(None)')
            # orb.log.debug('  setting project to SANDBOX (default)')
            state['project'] = 'pgefobjects:SANDBOX'
            if not state['system'].get('pgefobjects:SANDBOX'):
                state['system']['pgefobjects:SANDBOX'] = 'pgefobjects:SANDBOX'
        # ensure proper dashboard selection state
        dash_name = state.get('dashboard_name', 'MEL')
        if (dash_name == 'System Power Modes' and
            not (state.get('project') in mode_defz)):
            state['dashboard_name'] = 'MEL'
        if not state['sys_tree_expansion'].get(self.project.oid):
            # orb.log.debug('* setting sys tree expansion level to default (2)')
            state['sys_tree_expansion'][self.project.oid] = 0
        self.on_set_current_project()

    def del_project(self):
        pass

    # current project (as a Project instance)
    project = property(get_project, set_project, del_project,
                       "project property")

    @property
    def projects(self):
        """
        The current list of project objects on which the user has a role
        assignment.
        """
        admin_role = orb.get('pgefobjects:Role.Administrator')
        global_admin = orb.select('RoleAssignment',
                                  assigned_role=admin_role,
                                  assigned_to=self.local_user,
                                  role_assignment_context=None)
        if global_admin:
            # orb.log.debug('  - user is a Global Admin ...')
            projects = orb.get_by_type('Project')
        else:
            # orb.log.debug('  - user is NOT a Global Admin ...')
            # if user is not a global admin, restrict the projects to those on
            # which the user has a role
            ras = orb.search_exact(cname='RoleAssignment',
                                   assigned_to=self.local_user)
            projects = set([ra.role_assignment_context for ra in ras
                            if isinstance(ra.role_assignment_context,
                                          orb.classes['Project'])])
            # Add user-created projects
            user_projects = set(orb.search_exact(cname='Project',
                                                 creator=self.local_user))
            projects |= user_projects
            projects = list(projects)
            # "SANDBOX project" doesn't have roles so add it separately
            projects.append(self.sandbox)
        # str() is needed in case p.id is None, which happens if the dialog
        # creating a project is cancelled
        projects.sort(key=lambda p: str(p.id))
        # orb.log.debug('  - project list: {}'.format(
                      # str([p.id for p in projects])))
        return projects

    # 'product' property is the Product that is the subject of the Component
    # Modler mode; state['product'] is set to its oid
    def get_product(self):
        """
        Get the current product.
        """
        if not self._product:
            self._product = orb.get(state.get('product') or '')
        return self._product

    def set_product(self, p):
        """
        Set the current product.

        Args:
            p (Product):  the product to be set.
        """
        if not p:
            # if we get a None product, set TBD as placeholder
            p = orb.get('pgefobjects:TBD')
        orb.log.debug('* setting state["product"] ...')
        oid = getattr(p, 'oid', None)
        orb.log.debug(f'  product: "{str(p.id)}" ({oid})')
        if self._product and not state.get('comp_modeler_back'):
            # if there was a product set before, add it to history unless
            # 'comp_modeler_back' is True (-> back navigation)
            prev_oid = self._product.oid
            # prev_id = self._product.id
            # orb.log.debug(f'  adding to cmh: "{prev_id}" ({prev_oid})')
            hist = state.get('component_modeler_history', [])
            if (hist and prev_oid != hist[-1]) or not hist:
                hist.append(prev_oid)
            state['component_modeler_history'] = hist
        else:
            # if comp_modeler_back was True, reset it to False
            # orb.log.debug('  "comp modeler back" was called')
            state['comp_modeler_back'] = False
        # cmh = state.get('component_modeler_history', [])
        # orb.log.debug(f'  cmh is now: {str(cmh)}')
        state['product'] = oid
        self._product = p

    def del_product(self):
        pass

    product = property(get_product, set_product, del_product,
                       "product property")

    def on_comp_back(self, oid=None):
        """
        Handle dispatcher signal for "comp modeler back" (sent by
        ProductInfoPanel): load the last product from history and remove it
        from the stack.
        """
        if state.get('component_modeler_history'):
            oid = state['component_modeler_history'].pop() or ''
            # 'comp_modeler_back' tells set_product() not to add this to
            # history (we just removed it!)
            state['comp_modeler_back'] = True
            self.product = orb.get(oid)
            self.set_product_modeler_interface()

    def on_drop_product(self, p=None):
        """
        Handle dispatcher signal for "drop on product info" (sent by
        ProductInfoPanel when a product is dropped on it): load the product
        and add it to the history stack.
        """
        hist = state.get('component_modeler_history', [])
        if (hist and p.oid != hist[-1]) or not hist:
            hist.append(p.oid)
        state['component_modeler_history'] = hist
        self.product = p
        self.set_product_modeler_interface()

    def on_drill_down(self, usage=None):
        """
        Handle dispatcher signal for "diagram object drill down" (sent by
        DiagramScene).
        """
        # only trigger setting of self.product if in 'component' mode
        if state.get('mode') == 'component':
            if getattr(usage, 'component', None):
                self.product = usage.component
                self.set_product_modeler_interface()
            elif getattr(usage, 'system', None):
                self.product = usage.system
                self.set_product_modeler_interface()
        elif state.get('mode') == 'system':
            if getattr(usage, 'component', None):
                state['system'][state['project']] = usage.component.oid
            elif getattr(usage, 'system', None):
                state['system'][state['project']] = usage.system.oid

    def on_system_selected_signal(self, system=None):
        """
        Handle dispatcher signal for "system selected" (sent by system tree).
        """
        if system:
            state['system'][state.get('project')] = system.oid
            # orb.log.debug('* state["system"]: "{}"'.format(state['system']))
            orb.log.debug(f'* system selected: "{system.oid}"')

    def on_sys_node_selected_signal(self, index=None, obj=None, link=None):
        if obj:
            state['system'][state.get('project')] = obj.oid
            # orb.log.debug('* state["system"]: "{}"'.format(state['system']))

    def create_lib_widget(self, cnames=None, include_subtypes=True):
        """
        Creates an instance of 'CompoundLibraryWidget' to be assigned to
        self.library_widget.

        Keyword Args:
            cnames (list of str):  class names of the libraries
            include_subtypes (bool):  flag indicating if library view should
                include subtypes of the specified cname
        """
        if not cnames:
            cnames = ['HardwareProduct', 'Template', 'PortType',
                      'PortTemplate', 'ParameterDefinition',
                      'DataElementDefinition']
        widget = CompoundLibraryWidget(cnames=cnames,
                                       include_subtypes=include_subtypes,
                                       parent=self)
        widget.setContextMenuPolicy(Qt.PreventContextMenu)
        return widget

    def init_toolbar(self):
        # orb.log.debug('  - initializing toolbar ...')
        self.toolbar = self.addToolBar("Actions")
        self.toolbar.setObjectName('ActionsToolBar')
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.toolbar.setContextMenuPolicy(Qt.PreventContextMenu)
        import_icon_file = 'open' + state['icon_type']
        icon_dir = state.get('icon_dir', os.path.join(orb.home, 'icons'))
        import_icon_path = os.path.join(icon_dir, import_icon_file)
        import_actions = [
                          self.import_rqts_excel_action,
                          self.import_products_excel_action,
                          self.import_objects_action,
                          # Load Test Objects is currently flaky unless ONLY
                          # operating in standalone mode ...
                          # self.load_test_objects_action,
                          # "Exit" is really superfluous -- use window
                          # manager's "close" on the window
                          # self.exit_action
                          ]
        self.import_rqts_excel_action.setEnabled(True)
        self.import_products_excel_action.setEnabled(True)
        import_button = MenuButton(QIcon(import_icon_path),
                                   text='Input',
                                   tooltip='Import Data or Objects',
                                   actions=import_actions, parent=self)
        self.toolbar.addWidget(import_button)
        export_icon_file = 'save' + state['icon_type']
        export_icon_path = os.path.join(icon_dir, export_icon_file)
        export_actions = [self.export_project_to_file_action,
                          self.output_mel_action,
                          self.dump_db_action,
                          self.gen_keys_action] 
        export_button = MenuButton(QIcon(export_icon_path),
                                   text='Output',
                                   tooltip='Export Data or Objects',
                                   actions=export_actions, parent=self)
        self.toolbar.addWidget(export_button)
        new_object_icon_file = 'new_box' + state['icon_type']
        new_object_icon_path = os.path.join(icon_dir, new_object_icon_file)
        new_object_actions = [
                              self.new_product_action,
                              self.new_functional_rqt_action,
                              self.new_performance_rqt_action]
        add_update_object_button = MenuButton(QIcon(new_object_icon_path),
                                   text='Create',
                                   tooltip='Create Objects',
                                   actions=new_object_actions,
                                   parent=self)
        self.toolbar.addWidget(add_update_object_button)

        system_tools_icon_file = 'tools' + state['icon_type']
        system_tools_icon_path = os.path.join(icon_dir,
                                              system_tools_icon_file)
        system_tools_actions = [self.rqts_manager_action,
                                # self.modes_def_action,
                                # self.mode_def_tool_action,
                                self.conops_modeler_action,
                                self.modeler42_action,
                                self.step_import_action,
                                self.product_lib_action,
                                self.template_lib_action,
                                self.product_types_lib_action,
                                self.port_type_lib_action,
                                self.port_template_lib_action,
                                self.parameter_lib_action,
                                self.de_def_lib_action,
                                self.refresh_tree_action,
                                self.update_pgxno_action,
                                self.sync_project_action,
                                self.sync_all_projects_action,
                                self.full_resync_action,
                                self.prepare_offline_action]
        system_tools_actions.append(self.view_3d_model_action)
        system_tools_actions.append(self.edit_prefs_action)
        if config.get('test'):
            system_tools_actions.append(self.del_test_objs_action)
        # disable sync project action until we are online
        self.sync_project_action.setEnabled(False)
        self.sync_all_projects_action.setEnabled(False)
        self.full_resync_action.setEnabled(False)
        system_tools_button = MenuButton(QIcon(system_tools_icon_path),
                                   text='Tools',
                                   tooltip='Tools',
                                   actions=system_tools_actions, parent=self)
        self.toolbar.addWidget(system_tools_button)
        help_icon_file = 'tardis' + state['icon_type']
        help_icon_path = os.path.join(icon_dir, help_icon_file)
        help_actions = [self.user_guide_action,
                        self.reference_action,
                        self.about_action]
        help_button = MenuButton(QIcon(help_icon_path),
                                 text='Help',
                                 tooltip='Help',
                                 actions=help_actions, parent=self)
        self.toolbar.addWidget(help_button)
        self.toolbar.addSeparator()
        project_label = QLabel('Select Project:  ')
        project_label.setStyleSheet('font-weight: bold')
        self.project_label_action = self.toolbar.addWidget(project_label)
        self.project_selection = ButtonLabel(
                                    self.project.id,
                                    actions=[
                                             self.admin_action,
                                             self.new_project_action,
                                             self.delete_project_action],
                                    w=120)
        self.delete_project_action.setVisible(False)
        self.delete_project_action.setEnabled(False)
        self.project_selection.clicked.connect(self.set_current_project)
        self.project_selection_action = self.toolbar.addWidget(
                                                    self.project_selection)
        # project_selection and its label will only be visible in 'data',
        # 'system', and 'component' modes
        self.toolbar.addSeparator()
        self.login_label = QLabel('Login: ')
        self.login_label.setStyleSheet('font-weight: bold')
        self.toolbar.addWidget(self.login_label)
        self.toolbar.addAction(self.connect_to_bus_action)
        if os.path.exists(self.key_path):
            auto_cb_label = QLabel('Auto-connect at startup', margin=5)
            auto_cb_label.setStyleSheet('font-weight: bold')
            self.toolbar.addWidget(auto_cb_label)
            self.auto_cb = QCheckBox('')
            self.auto_cb.setChecked(self.auto)
            self.auto_cb.clicked.connect(self.set_auto_pref)
            self.toolbar.addWidget(self.auto_cb)
        spacer = QWidget(parent=self)
        spacer.setSizePolicy(QSizePolicy.Expanding,
                             QSizePolicy.Expanding)
        self.toolbar.addWidget(spacer)
        # self.circle_widget = CircleWidget()
        # self.toolbar.addWidget(self.circle_widget)
        ### NOTE: don't need 'mode_label' now that mode buttons display their
        ### text [SCW 2020-12-18]
        # self.mode_label = ModeLabel('')
        # self.toolbar.addWidget(self.mode_label)
        # self.toolbar.addAction(self.data_mode_action)
        self.toolbar.addAction(self.db_mode_action)
        self.toolbar.addAction(self.system_mode_action)
        self.toolbar.addAction(self.component_mode_action)
        # Makes the next toolbar appear underneath this one
        self.addToolBarBreak()
        # self.mode_widget_actions['data'].add(self.project_selection_action)
        # self.mode_widget_actions['data'].add(self.project_label_action)
        self.mode_widget_actions['system'].add(self.project_selection_action)
        self.mode_widget_actions['system'].add(self.project_label_action)
        self.mode_widget_actions['component'].add(
                                              self.project_selection_action)
        self.mode_widget_actions['component'].add(self.project_label_action)

    # def create_timer(self):
        # self.circle_timer = QTimer(self)
        # self.circle_timer.timeout.connect(self.circle_widget.next)
        # self.circle_timer.start(25)

    def _init_ui(self, width, height):
        # orb.log.debug('* _init_ui() ...')
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
        self.net_status = QLabel()
        self.net_status.setStyleSheet(
            "QToolTip { color: #ffffff; "
            "background-color: #2a82da; "
            "border: 1px solid white; }")
        offline_icon_file = 'offline' + state['icon_type']
        icon_dir = state.get('icon_dir', os.path.join(orb.home, 'icons'))
        offline_icon_path = os.path.join(icon_dir, offline_icon_file)
        self.offline_icon = QPixmap(offline_icon_path)
        online_icon_file = 'online_ok' + state['icon_type']
        online_icon_path = os.path.join(icon_dir, online_icon_file)
        self.online_ok_icon = QPixmap(online_icon_path)
        spotty_nw_icon_file = 'online' + state['icon_type']
        spotty_nw_icon_path = os.path.join(icon_dir, spotty_nw_icon_file)
        self.spotty_nw_icon = QPixmap(spotty_nw_icon_path)
        self.net_status.setPixmap(self.offline_icon)
        self.net_status.setToolTip('offline')
        uid = '{} [{}]'.format(self.local_user.name, self.local_user.id)
        self.user_label = ModeLabel(uid, color='green', w=300)
        self.role_label = ModeLabel('offline', w=300)
        self.statusbar = self.statusBar()
        self.statusbar.setStyleSheet('color: purple; font-weight: bold;')
        self.pb = QProgressBar(self.statusbar)
        style = "QProgressBar::chunk {background: QLinearGradient( x1: 0,"
        style += "y1: 0, x2: 1, y2: 0,stop: 0 #A020F0,stop: 0.4999"
        style += " #A020F0,stop: 0.5 #A020F0,stop: 1 #551A8B );"
        style += "border-bottom-right-radius: 5px;border-bottom-left-radius:"
        style += " 5px;border: .px solid black;}"
        self.pb.setStyleSheet(style)
        self.pb.setTextVisible(False)
        self.pb.hide()
        self.statusbar.addPermanentWidget(self.pb)
        self.statusbar.addPermanentWidget(self.user_label)
        self.statusbar.addPermanentWidget(self.role_label)
        self.statusbar.addPermanentWidget(self.net_status)
        self.statusbar.showMessage("To infinity, and beyond! :)")
        # x and y coordinates and the screen, width, height
        self.setGeometry(100, 100, width, height)
        self.setWindowTitle(self.app_name)

    def on_new_project_signal(self, obj=None):
        """
        Handle dispatcher signal for (local) "new project".
        """
        orb.log.debug('* on_new_project_signal(obj: {})'.format(
                                               getattr(obj, 'id', 'None')))
        if obj:
            self.project = obj
            if state['connected']:
                orb.log.debug('  calling vger.save() for project id: {}'.format(
                                                                       obj.id))
                try:
                    rpc = self.mbus.session.call('vger.save',
                                                 serialize(orb, [obj]))
                    rpc.addCallback(self.on_vger_save_result)
                    rpc.addErrback(self.on_failure)
                except:
                    orb.log.debug('  ** rpc failed (possible loss of transport)')
                    orb.log.debug('     trying to reconnect ...')
                    self.set_bus_state()
            else:
                orb.log.debug('  not connected -- not saving to repo.')

    def on_collaborate(self):
        pass   # to be implemented ...
        # NOTE:  the following code added the project to the admin service --
        # will be implemented in a separate action ("collaborate") which will
        # set up a previously local-only project on the server so that other
        # users can be given collaborative roles on it ...
        # if obj and state['connected']:
            # orb.log.debug('  - calling rpc omb.organization.add')
            # orb.log.debug('    with arguments:')
            # orb.log.debug('      oid={}'.format(obj.oid))
            # orb.log.debug('      id={}'.format(obj.id))
            # orb.log.debug('      name={}'.format(obj.name))
            # orb.log.debug('      org_type={}'.format('Project'))
            # parent_org = getattr(obj.parent_organization, 'oid', None)
            # orb.log.debug('      parent={}'.format(parent_org))
            # rpc = self.mbus.session.call('omb.organization.add',
                        # oid=obj.oid, id=obj.id, name=obj.name,
                        # org_type='Project', parent=parent_org)
            # rpc.addCallback(self.on_null_result)
            # rpc.addErrback(self.on_failure)

    # def on_null_result(self):
        # orb.log.debug('  rpc success.')
        # self.statusbar.showMessage('synced.')

    def on_freeze_signal(self, oids=None):
        """
        Handle local "freeze" signal.
        """
        if state.get('connected') and oids:
            self.freeze_progress = ProgressDialog(title='Freezing ...',
                                              label='freezing items ...',
                                              parent=self)
            self.freeze_progress.setAttribute(Qt.WA_DeleteOnClose)
            self.freeze_progress.setMaximum(len(oids))
            self.freeze_progress.setValue(0)
            self.freeze_progress.setMinimumDuration(2000)
            QApplication.processEvents()
            state['remote_frozens'] = 0
            try:
                rpc = self.mbus.session.call('vger.freeze', oids)
                rpc.addCallback(self.on_freeze_result)
                rpc.addErrback(self.on_failure)
            except:
                orb.log.debug('  ** rpc failed (possible loss of transport)')
                orb.log.debug('     trying to reconnect ...')
                self.set_bus_state()

    def on_thaw_signal(self, oids=None):
        if state.get('connected') and oids:
            try:
                rpc = self.mbus.session.call('vger.thaw', oids)
                rpc.addCallback(self.on_thaw_result)
                rpc.addErrback(self.on_failure)
            except:
                orb.log.debug('  ** rpc failed (possible loss of transport)')
                orb.log.debug('     trying to reconnect ...')
                self.set_bus_state()

    # NOTE TODO: handle RoleAssignment objects separately -- need to call
    # vger.assign_role() for them ...
    # NOTE TODO: also need to update the diagram -- i.e., DiagramScene
    # (in view.py)

    def on_new_rqt_signal(self, obj=None, cname=''):
        """
        Handle local dispatcher signal for "new rqt".
        """
        orb.log.info('* on_new_rqt_signal()')
        self.on_mod_object_signal(obj=obj, cname=cname, new=True)

    def on_new_object_signal(self, obj=None, cname=''):
        """
        Handle local dispatcher signal for "new object".
        """
        # for now, use on_mod_object_signal (may change in the future)
        self.on_mod_object_signal(obj=obj, cname=cname, new=True)

    def on_mod_object_signal(self, obj=None, cname='', new=False):
        """
        Handle local "new object" and "modified object" signals.
        """
        orb.log.info('* on_mod_object_signal()')
        if new:
            orb.log.info('* received local "new object" signal')
        else:
            orb.log.info('* received local "modified object" signal')
        if obj:
            cname = obj.__class__.__name__
            orb.log.debug('  object oid: "{}"'.format(
                                        str(getattr(obj, 'oid', '[no oid]'))))
            orb.log.debug('  cname: "{}"'.format(str(cname)))
            if new:
                # this object was created here and the repository has not seen
                # it yet, so it is editable offline without a check-out claim
                # (access.is_writable_now(), rule [4]).  Removed again in
                # on_vger_save_result() once the repository confirms it.
                self.add_locally_created(getattr(obj, 'oid', ''))
            if (self.mode == 'system'
                and isinstance(obj, (orb.classes['HardwareProduct'],
                                     orb.classes['Acu'],
                                     orb.classes['ProjectSystemUsage']))):
                # update system tree and dashboard as necessary
                # NOTE (SCW 2023-01-14) delay gui ops until callback to
                # "get_parmz" executes, to avoid "paint" exceptions --
                # in this case, set state "upd_obj_in_trees_needed"
                state["upd_obj_in_trees_needed"] = (obj.oid, new)
            if (self.mode in ['component', 'system']
                  and isinstance(obj, (orb.classes['HardwareProduct'],
                                       orb.classes['Acu'],
                                       orb.classes['ProjectSystemUsage']))):
                # if object is in the diagram ..
                state['diagram needs refresh'] = True
            if self.mode in ['component', 'system']:
                if cname in ['ParameterDefinition',
                             'DataElementDefinition',
                             'HardwareProduct',
                             'Template',
                             'PortTemplate',
                             'PortType']:
                    state["lib updates needed"] = True
            if self.mode == 'db' and cname == state.get('current_cname'):
                # object is in the current db table ...
                state['update db table'] = True
            if state.get('connected'):
                # SANDBOX PSUs are not saved to the server
                serialized_objs = serialize(orb, [obj],
                                            include_components=True)
                if isinstance(obj, orb.classes['RoleAssignment']):
                    orb.log.debug('  calling rpc vger.assign_role() ...')
                    orb.log.debug('  - role assignment: {}'.format(obj.id))
                    try:
                        rpc = self.mbus.session.call('vger.assign_role',
                                                     serialized_objs)
                        rpc.addCallback(self.on_result)
                    except:
                        orb.log.debug('  ** rpc failed (possible loss of transport)')
                        orb.log.debug('     trying to reconnect ...')
                        self.set_bus_state()
                        return
                else:
                    orb.log.debug('  calling rpc vger.save() ...')
                    orb.log.debug('  [called by on_mod_object_signal()]')
                    orb.log.debug('  - saved obj id: {} | oid: {}'.format(
                                                          obj.id, obj.oid))
                    try:
                        rpc = self.mbus.session.call('vger.save', serialized_objs)
                        rpc.addCallback(self.on_vger_save_result)
                        rpc.addCallback(self.get_parmz)
                    except:
                        orb.log.debug('  ** rpc failed (possible loss of transport)')
                        orb.log.debug('     trying to reconnect ...')
                        self.set_bus_state()
                        return
                rpc.addErrback(self.on_failure)
            else:
                # if not connected, recompute parameters and do all gui updates
                # -------------------------------------------------------------
                # BEGIN OFFLINE LOCAL UPDATES
                # -------------------------------------------------------------
                recompute_parmz()
                if ((self.mode == 'system') and
                    state.get('tree needs refresh')):
                    # orb.log.info('  [ovgpr] tree needs refresh ...')
                    self.refresh_tree_views()
                    state['tree needs refresh'] = False
                if (getattr(self, 'system_model_window', None)
                    and state.get('diagram needs refresh')):
                    # orb.log.info('  [ovgpr] diagram needs refresh ...')
                    self.system_model_window.on_signal_to_refresh()
                    state['diagram needs refresh'] = False
                if state.get('modal views need update'):
                    # orb.log.info('  [ovgpr] modal views need update ...')
                    self._update_modal_views()
                # -------------------------------------------------------------
                # NOTE: lib updates are done last
                # -------------------------------------------------------------
                lun = "yes"
                if not state.get('lib updates needed'):
                    lun = "no"
                lmsg = f'lib updates needed: {lun}'
                orb.log.info(f'  - {lmsg}')
                lib_widget = getattr(self, 'library_widget', None)
                if lun == "yes" and lib_widget:
                    lib_widget.refresh()
                    state['lib updates needed'] = []
                # ------------------------------------------------------------
                # END OF OFFLINE LOCAL UPDATES
                # ------------------------------------------------------------
        else:
            orb.log.debug('  *** no object provided -- ignoring! ***')

    def on_act_mods_signal(self, prop_mods=None):
        """
        Handle local dispatcher signal for "act mods" -- specifically some of
        the properties (parameters, data elements, or attributes) of the
        activities in a timeline have been modified. The vger.set_properties
        rpc will publish the modified properties in a "properties set" message,
        which includes the date-time stamp.
        """
        if prop_mods and state.get('connected'):
            try:
                rpc = self.mbus.session.call('vger.set_properties',
                                             props=prop_mods)
                rpc.addCallback(self.on_vger_set_properties_result)
                rpc.addErrback(self.on_failure)
            except:
                orb.log.debug('  ** rpc failed (possible loss of transport)')
                orb.log.debug('     trying to reconnect ...')
                self.set_bus_state()

    def on_vger_set_properties_result(self, msg):
        if msg:
            orb.log.info(f'* vger: {msg}.')

    def on_new_objects_signal(self, objs=None):
        """
        Handle local dispatcher signal for "new objects".
        """
        self.on_mod_objects_signal(objs=objs, new=True)

    def on_mod_objects_signal(self, objs=None, new=False):
        """
        Handle local "new objects" and "modified objects" signals.
        """
        orb.log.info('* on_mod_objects_signal()')
        if new:
            orb.log.info('* received local "new objects" signal')
        else:
            orb.log.info('* received local "modified objects" signal')
        if not objs:
            return
        for obj in objs:
            cname = obj.__class__.__name__
            orb.log.debug('  object oid: "{}"'.format(
                                        str(getattr(obj, 'oid', '[no oid]'))))
            orb.log.debug('  cname: "{}"'.format(str(cname)))
            if (self.mode == 'system'
                and isinstance(obj, (orb.classes['HardwareProduct'],
                                     orb.classes['Acu'],
                                     orb.classes['ProjectSystemUsage']))):
                # update system tree and dashboard as necessary
                # NOTE (SCW 2023-01-14) delay gui ops until callback to
                # "get_parmz" executes
                state["upd_obj_in_trees_needed"] = (obj.oid, new)
            if (self.mode in ['component', 'system']
                  and isinstance(obj, (orb.classes['HardwareProduct'],
                                       orb.classes['Acu'],
                                       orb.classes['ProjectSystemUsage']))):
                # if object is in the diagram ..
                state['diagram needs refresh'] = True
            if self.mode in ['component', 'system']:
                if cname in ['ParameterDefinition',
                             'DataElementDefinition',
                             'HardwareProduct',
                             'Template',
                             'PortTemplate',
                             'PortType']:
                    state["lib updates needed"] = True
            if self.mode == 'db' and cname == state.get('current_cname'):
                # if object is in the current db table ...
                state['update db table'] = True
        if state.get('connected'):
            serialized_objs = serialize(orb, objs,
                                        include_components=True)
            orb.log.debug('  calling rpc vger.save() ...')
            orb.log.debug('  [called from on_mod_objects_signal()]')
            orb.log.debug('  - saved objs names:')
            for obj in objs:
                # NOTE: test this object's own class -- "cname" from the loop
                # above holds the class name of the *last* object in "objs",
                # so for a mixed batch ending in an Activity this branch was
                # taken for every object, and obj.sub_activity_sequence then
                # raised AttributeError out here, outside the try below,
                # preventing the vger.save() call entirely
                if obj.__class__.__name__ == "Activity":
                    n = obj.sub_activity_sequence
                    orb.log.debug(f'    + "{obj.name}" (subact_seq: {n})')
                else:
                    orb.log.debug(f'    + "{obj.name}"')
            try:
                rpc = self.mbus.session.call('vger.save', serialized_objs)
                rpc.addCallback(self.on_vger_save_result)
                rpc.addErrback(self.on_failure)
            except:
                orb.log.debug('  ** rpc failed (possible loss of transport)')
                orb.log.debug('     trying to reconnect ...')
                self.set_bus_state()
                return
        else:
            # if not connected, recompute parameters and do all gui updates
            # -------------------------------------------------------------
            # BEGIN OFFLINE LOCAL UPDATES
            # -------------------------------------------------------------
            recompute_parmz()
            if ((self.mode == 'system') and
                state.get('tree needs refresh')):
                # orb.log.info('  [ovgpr] tree needs refresh ...')
                self.refresh_tree_views()
                state['tree needs refresh'] = False
            if (getattr(self, 'system_model_window', None)
                and state.get('diagram needs refresh')):
                # orb.log.info('  [ovgpr] diagram needs refresh ...')
                self.system_model_window.on_signal_to_refresh()
                state['diagram needs refresh'] = False
            if state.get('modal views need update'):
                # orb.log.info('  [ovgpr] modal views need update ...')
                self._update_modal_views()
            # -------------------------------------------------------------
            # NOTE: lib updates are done last
            # -------------------------------------------------------------
            lun = "yes"
            if not state.get('lib updates needed'):
                lun = "no"
            lmsg = f'lib updates needed: {lun}'
            orb.log.info(f'  - {lmsg}')
            if lun == "yes" and hasattr(self, 'library_widget'):
                self.library_widget.refresh()
                state['lib updates needed'] = []
            # ------------------------------------------------------------
            # END OF OFFLINE LOCAL UPDATES
            # ------------------------------------------------------------

    def on_parms_set(self, parms=None):
        """
        Handle local dispatcher signal "parms set".
        """
        orb.log.debug(f'* on_parms_set({parms})')
        if parms and state.get('connected'):
            try:
                rpc = self.mbus.session.call('vger.set_parameters',
                                             parms=parms)
                rpc.addCallback(self.on_vger_set_parameters_result)
                rpc.addErrback(self.on_failure)
            except:
                orb.log.debug('  ** rpc failed (possible loss of transport)')
                orb.log.debug('     trying to reconnect ...')
                self.set_bus_state()

    def on_vger_set_parameters_result(self, msg):
        if msg:
            orb.log.info(f'* vger: {msg}.')
            if not msg.startswith('failure'):
                # if successful, msg is stringified datetime stamp
                # NOTE: state['parmz_dts'] is deliberately written and never
                # read -- a diagnostic record of when the cache last changed.
                # It is specifically NOT a conditional-fetch stamp; see the
                # note after the state key list in
                # p.core/NOTES_FOR_DEVELOPERS.md for why giving it the
                # mode_defz_dts treatment would break convergence.
                state['parmz_dts'] = msg

    def on_parm_added(self, oid='', pid=''):
        """
        Handle local dispatcher signal "parm added".

        NOTE: no queue is needed here.  Unlike a deletion, an addition is
        carried in the object's serialization and reaches the repository
        whenever the object is pushed -- which is why the editor stamps
        mod_datetime when a parameter is dropped onto an object.  This rpc
        only makes the addition visible to other users sooner.
        """
        if oid and pid and state.get('connected'):
            try:
                rpc = self.mbus.session.call('vger.add_parm', oid=oid,
                                             pid=pid)
                rpc.addCallback(self.on_vger_add_parm_result, oid=oid, pid=pid)
                rpc.addErrback(self.on_failure)
            except:
                orb.log.debug('  ** rpc failed (possible loss of transport)')
                orb.log.debug('     trying to reconnect ...')
                self.set_bus_state()

    def on_vger_add_parm_result(self, msg, oid='', pid=''):
        if msg:
            orb.log.info(f'* vger: {msg}.')
        if isinstance(msg, str) and msg.startswith('failure:'):
            # vger.add_parm() now authorizes the caller; a refusal means the
            # local addition will be reverted by the next get_parmz(), so say
            # so rather than let the parameter quietly disappear
            if 'not authorized' in msg:
                self.add_to_sync_report('parameter additions refused',
                                        f'parameter "{pid}" of object "{oid}"')
        return msg

    def on_parm_del(self, oid='', pid=''):
        """
        Handle local dispatcher signal "parm del".

        If the repository cannot be reached the deletion is queued rather than
        dropped:  unlike an addition it cannot ride along with the object at
        the next sync, because deserialize_parms() merges.  See the note on
        queue_parm_deletion().
        """
        if not (oid and pid):
            return
        if not state.get('connected'):
            self.queue_parm_deletion(oid, pid, kind='parm')
            return
        key = f'parm|{oid}|{pid}'
        try:
            rpc = self.mbus.session.call('vger.del_parm', oid=oid, pid=pid)
            rpc.addCallback(self.clear_queued_parm_deletion, key=key)
            rpc.addErrback(self.on_failure)
        except:
            orb.log.debug('  ** rpc failed (possible loss of transport)')
            orb.log.debug('     trying to reconnect ...')
            self.queue_parm_deletion(oid, pid, kind='parm')
            self.set_bus_state()

    def on_remote_parm_added(self, content):
        """
        Handle vger pubsub msg "parm added".
        """
        oid, pid = content
        orb.log.debug(f'* vger: added parm "{pid}" to oid "{oid}"')
        if parameterz.get(oid) and pid in parameterz[oid]:
            orb.log.debug('  already exists locally; no action.')
        else:
            add_parameter(oid, pid)
            orb.log.debug('  added.')
            self.update_pgxno(mod_oids=[oid])

    def on_remote_parm_del(self, content):
        """
        Handle vger pubsub msg "parm del".
        """
        oid, pid = content
        orb.log.debug(f'* vger: del parm "{pid}" from oid "{oid}"')
        if parameterz.get(oid) and pid in parameterz[oid]:
            delete_parameter(oid, pid, local=False)
            orb.log.debug('  deleted.')
            self.update_pgxno(mod_oids=[oid])
        else:
            orb.log.debug('  does not exist locally; no action.')

    def on_de_del(self, oid='', deid=''):
        """
        Handle local dispatcher signal "de del".

        Queued when offline, for the same reason as on_parm_del().
        """
        if not (oid and deid):
            return
        if not state.get('connected'):
            self.queue_parm_deletion(oid, deid, kind='de')
            return
        key = f'de|{oid}|{deid}'
        try:
            rpc = self.mbus.session.call('vger.del_de', oid=oid, deid=deid)
            rpc.addCallback(self.clear_queued_parm_deletion, key=key)
            rpc.addErrback(self.on_failure)
        except:
            orb.log.debug('  ** rpc failed (possible loss of transport)')
            orb.log.debug('     trying to reconnect ...')
            self.queue_parm_deletion(oid, deid, kind='de')
            self.set_bus_state()

    # NOTE: "on_des_set" and "on_des_set_qtsignal" were removed here -- both
    # were dead: nothing sent the 'des set' dispatcher signal (verified over
    # every project in the clones directory), and no pyqtSignal was ever
    # connected to the qtsignal variant. They were redundant in any case:
    # serialize() carries data elements with the object
    # (serializers.py: d['data_elements'] = serialize_des(obj.oid)), and the
    # code that edits data elements stamps mod_datetime and saves the object,
    # so the changes already travel to the repository via vger.save().
    # "on_vger_set_des_result" below is still live -- it is the callback for
    # the vger.set_data_elements() call in on_vger_save_result().

    def on_vger_set_des_result(self, msg):
        if msg:
            orb.log.info(f'* vger: {msg}.')

    def on_remote_properties_set(self, content):
        """
        Handle vger pubsub msg "properties set" (parameters, data elements, or
        attributes), with content in the format (prop_mods,
        mod_datetime_string), where prop_mods has the format {oid: {prop_id:
        value}}, where prop_id is the id of parameter, data element, or
        attribute, and if a parameter then value must be in base (mks) units.
        """
        orb.log.debug('* vger pubsub: "properties set"')
        prop_mods, mod_dt_str = content
        # NOTE: this message is published on "vger.channel.public", so it is
        # received for objects in *any* project -- including the ones this
        # client holds no objects for, which is the normal case.  Oids we do
        # not have are skipped entirely: orb.set_prop_val() writes directly
        # into the oid-keyed parameterz/data_elementz caches and reports
        # 'succeeded' without checking that an object exists, so applying
        # them would both crash on the obj.mod_datetime assignment below and
        # accumulate entries keyed to foreign oids in caches that are
        # persisted to parameters.json / data_elements.json.
        success_oids = set()
        skipped_oids = set()
        for oid, prop_dict in prop_mods.items():
            if orb.get(oid) is None:
                skipped_oids.add(oid)
                continue
            for prop_id, val in prop_dict.items():
                status = orb.set_prop_val(oid, prop_id, val)
                if status == 'succeeded':
                    success_oids.add(oid)
        if skipped_oids:
            n = len(skipped_oids)
            orb.log.debug(f'  {n} oid(s) not known locally; ignored.')
        if success_oids:
            mod_dt = uncook_datetime(mod_dt_str)
            mod_act_oids = set()
            for oid in success_oids:
                obj = orb.get(oid)
                obj.mod_datetime = mod_dt
                # TODO: handle other classes ...
                if isinstance(obj, orb.classes['Activity']):
                    mod_act_oids.add(oid)
            # commit once, rather than once per object
            orb.db.commit()
            if mod_act_oids:
                mod_acts = orb.get(oids=mod_act_oids)
                dispatcher.send(signal='remote new or mod acts',
                                objs=mod_acts)
        orb.log.debug('  success: properties updated.')

    def on_remote_data_elements_set(self, content):
        """
        Handle vger pubsub messages "data element set" and "data elements set".
        """
        # orb.log.debug('* vger pubsub: "data element(s) set"')
        try:
            if isinstance(content, str):
                orb.log.debug(f'  failed: {content}')
            else:
                # content from rpc "set_data_elements"
                orb.log.debug('  vger rpc: set_data_elements()')
                orb.log.debug(f'  message content: {content}')
                modified, dez_dts = content
                for oid in modified:
                    if oid in data_elementz:
                        data_elementz[oid].update(modified[oid])
                    else:
                        data_elementz[oid] = modified[oid].copy()
                # diagnostic only, deliberately never read (see the note on
                # state['parmz_dts'] in on_vger_set_parameters_result)
                state['dez_dts'] = dez_dts
                orb.log.debug('  success: data_elementz updated.')
        except:
            orb.log.debug('  failed: exception while processing msg content.')

    def on_remote_de_added(self, content):
        """
        Handle vger pubsub msg "de added".
        """
        oid, deid = content
        orb.log.debug(f'* vger: added de "{deid}" from oid "{oid}"')
        if data_elementz.get(oid) and deid in data_elementz[oid]:
            orb.log.debug('  already exists locally; no action.')
        else:
            add_data_element(oid, deid)
            orb.log.debug('  added.')
            self.update_pgxno(mod_oids=[oid])

    def on_remote_de_del(self, content):
        """
        Handle vger pubsub msg "de del".
        """
        oid, deid = content
        orb.log.debug(f'* vger: del data element "{deid}" from "{oid}"')
        if data_elementz.get(oid) and deid in data_elementz[oid]:
            delete_data_element(oid, deid, local=False)
            orb.log.debug('  deleted.')
            self.update_pgxno(mod_oids=[oid])
        else:
            orb.log.debug('  does not exist locally; no action.')

    # ------------------------------------------------------------------------
    # NOTE [SCW 2022-10-11]: when in "connected" state, call vger.get_parmz()
    # instead of recomputing parameters locally
    # ------------------------------------------------------------------------

    def get_parmz(self, oids=None):
        """
        Handle local dispatcher signal "get parmz".

        NOTE: this replaces the local parameter caches wholesale with the
        server's copy, so any queued offline deletion that has not yet been
        replayed would be undone here.  The queue is therefore drained here,
        chained ahead of the rpc, rather than at some earlier point in the
        sync chain:  this is also reached directly from the "parameters set"
        pubsub handler, which can arrive at any moment after reconnecting, so
        earlier placement would only have made the ordering look right.  Push
        before pull.  replay_parm_del_queue() is a no-op when the queue is
        empty, which is the usual case.
        """
        # orb.log.debug('* get_parmz')
        if not state.get('connected'):
            return
        if parm_del_queue:
            d = self.replay_parm_del_queue()
            if isinstance(d, DeferredList):
                d.addCallback(lambda _: self._call_get_parmz())
                return
        self._call_get_parmz()

    def _call_get_parmz(self, data=None):
        """
        Issue the vger.get_parmz() rpc.  Split out of get_parmz() so the
        offline deletion queue can be drained first (see get_parmz).
        """
        try:
            rpc = self.mbus.session.call('vger.get_parmz')
            rpc.addCallback(self.on_vger_get_parmz_result)
            rpc.addErrback(self.on_failure)
        except:
            orb.log.debug('  ** rpc failed (possible loss of transport)')
            orb.log.debug('     trying to reconnect ...')
            self.set_bus_state()

    def on_vger_get_parmz_result(self, data):
        """
        Handle result of rpc vger.get_parmz().  Since this rpc is typically the
        last in a chain of rpc callbacks, it has responsibility for doing all
        needed GUI updates (which would cause various problems and possibly
        crashes if attempted while rpc operations are being processed).
        """
        orb.log.info('* on_vger_get_parmz_result() [ovgpr]')
        # libs_refreshed = []
        if data:
            parmz_data = data
            # orb.log.info('  [ovgpr] got parmz data, updating ...')
            parameterz.update(parmz_data)
            oid, new = state.get("upd_obj_in_trees_needed", ("", ""))
            if oid:
                obj = orb.get(oid)
                # orb.log.info('  [ovgpr] calling update_object_in_trees() ...')
                self.update_object_in_trees(obj, new=new)
                state['tree needs refresh'] = False
            if state.get('updates_needed_for_remote_obj_deletion'):
                # if get_parmz was triggered by remote deleted object ...
                cname = state['updates_needed_for_remote_obj_deletion']
                state['updates_needed_for_remote_obj_deletion'] = ""
                if cname == 'RoleAssignment':
                    self.update_project_role_labels()
                    # whether ra applies to this user or not, send signal to
                    # refresh the admin tool
                    dispatcher.send(signal='refresh admin tool')
                elif cname == 'Activity':
                    # conops will handle the deletion -- DO NOT delete here
                    # because the activity oid is used to get the local
                    # activity, which is used to find the event block that
                    # needs to be removed from the timeline ...
                    pass
                elif ((self.mode == 'system') and
                    cname in ['Acu', 'ProjectSystemUsage', 'HardwareProduct',
                              'Port', 'Flow']):
                    # update tree and dashboard only if in "system" mode
                    # txt = 'calling refresh_tree_and_dashboard() ...'
                    # orb.log.info(f'  [ovgpr] {txt}')
                    self.refresh_tree_and_dashboard()
                    state['tree needs refresh'] = False
                    # DIAGRAM MAY NEED UPDATING
                    if getattr(self, 'system_model_window', None):
                        # rebuild diagram in case an object corresponded to a
                        # block in the current diagram
                        # txt = 'system_model_window.on_signal_to_refresh() ...'
                        # orb.log.info(f'  [ovgpr] calling {txt}')
                        self.system_model_window.on_signal_to_refresh()
                        state['diagram needs refresh'] = False
                elif self.mode == 'db' and state.get('update db table'):
                    # new or modified object is in current db table
                    # NOTE: set_db_interface() sets 'update db table' to False
                    self.set_db_interface()
                elif (self.mode == 'component' and
                    cname in ['Acu', 'ProjectSystemUsage', 'HardwareProduct',
                              'Port', 'Flow']):
                    # DIAGRAM MAY NEED UPDATING
                    # update state['product'] if needed, and regenerate diagram
                    # this will set placeholders in place of PgxnObject and diagram
                    self.set_product_modeler_interface()
                    if getattr(self, 'system_model_window', None):
                        # NOTE: no on_signal_to_refresh() -- same reason as in
                        # on_deleted_object_signal's component branches:
                        # set_product_modeler_interface() has just built a new
                        # ModelWindow, so the diagram is already regenerated.
                        # Clearing the flag is the part that matters.
                        state['diagram needs refresh'] = False
            else:
                # refresh dashboard and hw library if appropriate ...
                if getattr(self, 'dashboard_panel', None):
                    # NOTE: self.refresh_dashboard() is not enough.
                    # txt = 'rebuild_dashboard(force=True) ...'
                    # orb.log.info(f'  [ovgpr] calling {txt}')
                    self.rebuild_dashboard(force=True)
            # "parameters recomputed" triggers pgxnobject, rqtmanager,
            # powerdashboard, and wizard (data import) ...
            dispatcher.send("parameters recomputed")
        else:
            # orb.log.info('  [ovgpr] no parmz data, check other updates ...')
            pass
        if ((self.mode == 'system') and
            state.get('tree needs refresh')):
            # orb.log.info('  [ovgpr] tree needs refresh ...')
            self.refresh_tree_views()
            state['tree needs refresh'] = False
        if (getattr(self, 'system_model_window', None)
            and state.get('diagram needs refresh')):
            # orb.log.info('  [ovgpr] diagram needs refresh ...')
            self.system_model_window.on_signal_to_refresh()
            state['diagram needs refresh'] = False
        if state.get('modal views need update'):
            # orb.log.info('  [ovgpr] modal views need update ...')
            self._update_modal_views()
        # ---------------------------------------------------------------
        # NOTE: lib updates are done last
        # ---------------------------------------------------------------
        lun = "yes"
        if not state.get('lib updates needed'):
            lun = "no"
        lmsg = f'[ovgpr] lib updates needed: {lun}'
        orb.log.info(f'  {lmsg}')
        if lun == "yes" and hasattr(self, 'library_widget'):
            self.library_widget.refresh()
            state['lib updates needed'] = []
        self.statusbar.showMessage('synced.')
        # NOTE: this is the end of the rpc chain (see this method's docstring),
        # so it is where the reconciliation report is presented.  It is silent
        # unless something was refused, and clears itself once shown, so a
        # standalone save that had work rejected reports it here too rather
        # than only a full sync.
        self.show_sync_report()

    def on_vger_save_result(self, stuff):
        """
        Handle the data returned by the vger.save() rpc, which is a dict in the
        form:

                  {'new_obj_dts':  {obj0.oid : str(obj0.mod_datetime),
                                    obj1.oid : str(obj1.mod_datetime),
                                    ...},
                   'mod_obj_dts':  {obj2.oid : str(obj2.mod_datetime),
                                    obj3.oid : str(obj3.mod_datetime),
                                    ...}
                   'unauth': [ids of objects for which save was unauthorized],
                   'no_owners': [ids of objects that did not have owners but
                                 should]
        """
        orb.log.debug('* vger.save rpc result: {}'.format(str(stuff)))
        try:
            # NOTE: these parts are *accumulated* -- they used to be separate
            # assignments to "msg", so that when more than one category was
            # present only the last one survived (e.g. a result containing both
            # modified and unauthorized objects reported only the unauthorized
            # count). "msg" also serves as a control flag below: empty means
            # nothing at all came back, so accumulating preserves that meaning.
            msg_parts = []
            new_acts = []
            # anything the repository accepted is no longer "locally created"
            # -- it now exists there, so offline editability must come from a
            # check-out claim rather than from rule [4]
            self.clear_locally_created(list(stuff.get('new_obj_dts') or {})
                                       + list(stuff.get('mod_obj_dts') or {}))
            if stuff.get('new_obj_dts'):
                msg_parts.append('{} new'.format(len(stuff['new_obj_dts'])))
                new_obj_oids = list(stuff['new_obj_dts'])
                new_objs = orb.get(oids=new_obj_oids)
                for obj in new_objs:
                    if isinstance(obj, orb.classes['Activity']):
                        new_acts.append(obj)
                if new_acts:
                    orb.log.debug('  some new activities --')
                    orb.log.debug('  setting time_units to "minutes" ...')
                    for act in new_acts:
                        set_dval(act.oid, 'time_units', 'minutes')
            if stuff.get('mod_obj_dts'):
                msg_parts.append('{} modified'.format(
                                                len(stuff['mod_obj_dts'])))
            # ----------------------------------------------------------------
            # NOTE: "unauth" and "no_owners" are objects the repository
            # REFUSED to save -- i.e. the user's work did not land. These used
            # to be logged at debug level only and never shown, so the user got
            # no indication at all that anything had been rejected. They are
            # now logged at info level *with the object ids*, and recorded in
            # state['last_sync_report'] so the sync summary can present them.
            # ----------------------------------------------------------------
            rejected = {}
            if stuff.get('unauth'):
                unauth = stuff['unauth']
                rejected['unauthorized'] = list(unauth)
                msg_parts.append('{} unauthorized (NOT saved)'.format(
                                                            len(unauth)))
                orb.log.info('  * repository REFUSED to save '
                             f'{len(unauth)} object(s) (unauthorized):')
                for obj_id in unauth:
                    orb.log.info(f'    - {obj_id}')
            if stuff.get('no_owners'):
                no_owners = stuff['no_owners']
                rejected['no_owner'] = list(no_owners)
                msg_parts.append('{} without owner (NOT saved)'.format(
                                                            len(no_owners)))
                orb.log.info('  * repository REFUSED to save '
                             f'{len(no_owners)} object(s) (no owner):')
                for obj_id in no_owners:
                    orb.log.info(f'    - {obj_id}')
            msg = '; '.join(msg_parts)
            if msg:
                orb.log.info(f'  vger.save: {msg}.')
            report = state.get('last_sync_report') or {}
            if rejected:
                # merge, so several vger.save calls in one sync accumulate
                for k, ids in rejected.items():
                    report[k] = list(set((report.get(k) or []) + ids))
                state['last_sync_report'] = report
                # Surface it. NOTE: deferred via singleShot(0) rather than
                # calling showMessage() directly -- see the CAUTION below;
                # painting from inside an rpc callback while further rpcs are
                # pending raises "QBackingStore::endPaint() called ...".
                # Deferring lets the callback chain unwind first.
                n = sum(len(ids) for ids in rejected.values())
                warning = (f'WARNING: {n} item(s) were NOT saved to the '
                           'repository (see log for details)')
                QTimer.singleShot(0,
                            lambda: self.statusbar.showMessage(warning))
            if not msg:
                msg = 'nothing to save; synced.'
                # NOTE: CAUTION! ONLY call showMessage if no other rpcs are to
                # follow (e.g., no "get_parmz" callback, etc.) -- otherwise get
                # the dreaded "QBackingStore::endPaint() called..." exception
                self.statusbar.showMessage('synced.')
                # NOTE: VERY IMPORTANT: updates the project, gui, etc.
                if state.get('modal views need update'):
                    self._update_modal_views()
            elif new_acts:
                orb.log.debug('  calling "vger.set_data_elements() ...')
                # NOTE: vger.set_data_elements() will also publish message
                # "data elements set" to update data elements ...
                des = {act.oid: {'time_units': 'minutes'} for act in new_acts}
                try:
                    rpc = self.mbus.session.call('vger.set_data_elements',
                                                 des=des)
                    rpc.addCallback(self.on_vger_set_des_result)
                    rpc.addCallback(self.get_parmz)
                    rpc.addErrback(self.on_failure)
                except:
                    txt = 'rpc failed (possible loss of transport)'
                    orb.log.debug(f'  ** {txt}')
                    orb.log.debug('     trying to reconnect ...')
                    self.set_bus_state()
                    return
            else:
                msg = 'getting parmz'
                orb.log.debug(f'  {msg}')
                self.get_parmz()
        except:
            orb.log.debug('  result format incorrect.')

    def on_result(self, stuff):
        """
        Handle result of an operation that returns chunked data.
        """
        # orb.log.debug('  rpc result: {}'.format(stuff))
        # TODO:  add more detailed status message ...
        if state.get('chunks_to_get'):
            n = len(state['chunks_to_get'])
            if n == 1:
                msg = 'chunk synced -- getting 1 more chunk ...'
            else:
                msg = f'chunk synced -- getting {n} more chunks ...'
        else:
            msg = 'synced.'
        orb.log.debug(f'* {msg}')
        self.statusbar.showMessage(msg)

    def on_rpc_vger_delete_result(self, res):
        """
        Handle callback to the vger.delete rpc.
        """
        orb.log.debug('* on_rpc_vger_delete_result')
        # NOTE: vger.delete now returns a dict that distinguishes a *refused*
        # deletion from one the repository never saw.  The old 2-tuple shape
        # is still accepted so the client and repository can be upgraded
        # independently -- against an older repository "unauth" is simply
        # empty, and refusals remain indistinguishable from lost rpcs, which
        # is the pre-existing behaviour.
        if isinstance(res, dict):
            oids_not_found = res.get('not_found') or []
            oids_deleted = res.get('deleted') or []
            oids_unauth = res.get('unauth') or []
        else:
            oids_not_found, oids_deleted = res
            oids_unauth = []
        orb.log.debug(f'  oids_not_found: {oids_not_found}')
        orb.log.debug(f'  oids_deleted: {oids_deleted}')
        if oids_unauth:
            orb.log.info(f'  REFUSED by the repository: {oids_unauth}')
        # ------------------------------------------------------------------
        # Clear queued offline deletions the repository has now accounted for.
        # "not found" counts as settled:  the object is not in the repository,
        # which is the outcome the deletion was asking for -- most often
        # because it was created and deleted entirely offline and the
        # repository never saw it.
        #
        # A **refused** deletion is dropped from the queue and reported:
        # retrying it every sync would never succeed, and would keep restoring
        # the object locally with no explanation.  A deletion that is merely
        # *absent* from the result -- an rpc lost to a dropped connection --
        # stays queued and is retried, which is the distinction section 3.2
        # asks for and the old 2-tuple return could not express.
        # ------------------------------------------------------------------
        settled = [oid for oid in (oids_not_found + oids_deleted)
                   if oid in deletion_queue]
        if settled:
            for oid in settled:
                del deletion_queue[oid]
        refused = [oid for oid in oids_unauth if oid in deletion_queue]
        if refused:
            for oid in refused:
                entry = deletion_queue.pop(oid)
                self.add_to_sync_report('deletions refused',
                                        entry.get('cname') or oid)
        if settled or refused:
            write_deletion_queue(os.path.join(orb.home, 'deletion_queue'))
            orb.log.info(f'  {len(settled)} queued deletion(s) confirmed, '
                         f'{len(refused)} refused; '
                         f'{len(deletion_queue)} still queued (will retry).')

    def on_freeze_result(self, stuff):
        """
        Handle result of 'vger.freeze' rpc.
        """
        orb.log.debug('  vger.freeze result: {}'.format(stuff))
        if getattr(self, 'freeze_progress', None):
            self.freeze_progress.done(0)
            QApplication.processEvents()
        frozens, unauth = stuff
        msg = f'vger: {len(frozens)} frozen, {len(unauth)} unauthorized.'
        self.statusbar.showMessage(msg)

    def on_thaw_result(self, stuff):
        """
        Handle result of the 'vger.thaw' rpc.

        vger.thaw returns (thawed, failed), where "thawed" holds
        (oid, mod_datetime, modifier_oid) tuples for the objects the
        repository actually thawed and "failed" holds the oids it refused
        (e.g. the caller is not a Global Administrator) or could not thaw.

        NOTE: the *successful* thaws are deliberately NOT applied here -- the
        repository publishes a "thawed" message on the public channel, which
        this client also receives, and on_pubsub_msg() feeds it to
        on_remote_freeze_or_thaw(). Applying them here as well would commit
        the same values twice and pop up a second "thawed" notice.

        What this callback is for is the "failed" list: pgxnobject.thaw() sets
        obj.frozen = False locally *before* the rpc is sent, so any oid the
        repository refused has to be reverted here. Otherwise the client would
        go on showing the object as thawed while the repository still has it
        frozen, and since thaw() does not bump mod_datetime,
        vger.sync_objects() would classify the object as "same" and never
        reconcile the difference.
        """
        orb.log.debug('  vger.thaw result: {}'.format(stuff))
        try:
            thawed, failed = stuff
        except:
            orb.log.debug('  ** unexpected vger.thaw result format; ignoring.')
            return
        thawed = thawed or []
        failed = failed or []
        reverted = []
        for oid in failed:
            obj = orb.get(oid)
            # only revert objects we had optimistically thawed locally
            if obj is not None and not getattr(obj, 'frozen', True):
                obj.frozen = True
                reverted.append(oid)
        if reverted:
            orb.db.commit()
            n = len(reverted)
            orb.log.debug(f'  thaw refused by repository for {n} object(s);')
            orb.log.debug('  local "frozen" state reverted to match it.')
            # prompt any open editor to re-read the object and fix its toolbar
            dispatcher.send(signal='remote frozen', frozen_oids=reverted)
        msg = f'vger: {len(thawed)} thawed, {len(failed)} not thawed.'
        self.statusbar.showMessage(msg)

    def on_failure(self, f):
        orb.log.debug("* rpc failure: {}".format(f.getTraceback()))

    def on_set_value_result(self, stuff):
        # orb.log.debug('  rpc result: {}'.format(stuff))
        # NOTE:  this gets VERY verbose
        # TODO:  add more detailed status message ...
        pass

    def on_mode_defs_edited(self, oid=None):
        """
        Handle local "modes edited" signal, which is emitted by the ConOps
        assembly tree (usage selection) tool when the mode_defz cache is
        updated in certain situations, including:

            [1] when a new usage is selected for addition to mode_defz;
            [2] when a graph is computed and requires update(s) to mode_defz;
            [3] when a usage that had been designated as "[computed]" (i.e.,
                having its modal power values computed from those of its
                components) has that designation removed (set_no_compute()).

        Keyword Args:
            oid (str): oid of project whose mode defs are to be updated
        """
        orb.log.debug('* signal: "modes edited"')
        proj_mode_defs = mode_defz.get(oid) or {}
        if proj_mode_defs and state['connected']:
            # NOTE: mode_defz data does NOT need to be serialized
            data = proj_mode_defs
            orb.log.debug('  - sending modes data to server ...')
            # orb.log.debug('    =============================')
            # orb.log.debug(f'    {s}')
            # orb.log.debug('    =============================')
            try:
                rpc = self.mbus.session.call('vger.update_mode_defs',
                                             project_oid=oid,
                                             data=data)
                rpc.addCallback(self.rpc_update_mode_defs_result)
                rpc.addErrback(self.on_failure)
            except:
                orb.log.debug('  ** rpc failed (possible loss of transport)')
                orb.log.debug('     trying to reconnect ...')
                self.set_bus_state()

    def rpc_update_mode_defs_result(self, result):
        """
        Handle callback with result of vger.update_mode_defs.

        Args:
            result (str):  a stringified mod datetime stamp.
        """
        if result in ['unauthorized', 'no such project', 'no data submitted']:
            msg = 'mode defs update failed: ' + result
        else:
            state['mode_defz_dts'] = result
            msg = f'mode defs updated [dts: {result}]'
        orb.log.debug(f'* {msg}')

    def on_comp_mode_datum_set(self, datum=None):
        """
        Handle local dispatcher signal for "comp mode datum set".
        """
        orb.log.debug('* signal: "comp mode datum set"')
        if len(datum or []) == 5:
            project_oid, link_oid, comp_oid, mode, value = datum
            project = orb.get(project_oid)
            link = orb.get(link_oid)
            comp = orb.get(comp_oid)
            orb.log.debug('    =============================')
            orb.log.debug(f'   project:    {project.id}')
            orb.log.debug(f'   system:     {link.id}')
            orb.log.debug(f'   component:  {comp.id}')
            orb.log.debug(f'   mode:       {mode}')
            orb.log.debug(f'   value:      {value}')
            orb.log.debug('    =============================')
            if state.get('connected'):
                orb.log.debug('  - calling vger.set_comp_mode_datum()')
                try:
                    rpc = self.mbus.session.call('vger.set_comp_mode_datum',
                                                 project_oid=project_oid,
                                                 link_oid=link_oid,
                                                 comp_oid=comp_oid,
                                                 mode=mode,
                                                 value=value)
                    rpc.addCallback(self.rpc_set_comp_mode_datum_result)
                    rpc.addErrback(self.on_failure)
                except:
                    txt = 'rpc failed (possible loss of transport)'
                    orb.log.debug(f'  ** {txt}')
                    orb.log.debug('     trying to reconnect ...')
                    self.set_bus_state()
            else:
                orb.log.debug('  - not connected, no rpc call.')
        else:
            orb.log.debug('  improper comp mode datum format sent')

    def rpc_set_comp_mode_datum_result(self, result):
        """
        Handle callback with result of vger.set_comp_mode_datum.

        Args:
            result (str):  a stringified mod datetime stamp or an error.
        """
        if result in ['unauthorized', 'no such project']:
            msg = 'setting of comp mode datum failed: ' + result
        else:
            state['mode_defz_dts'] = result
            msg = f'comp mode datum set successfully [dts: {result}]'
            # update dashboard if appropriate
            if (state.get('mode') == "system" and
                state.get('dashboard_name') == 'System Power Modes'):
                self.refresh_dashboard()
        orb.log.debug(f'* {msg}')

    # NOT ACITVE: "System Power Modes" dashboard is not currently functioning
    # due to bug in dashboard switching ...
    def on_power_modes_updated(self):
        """
        Update dashboard when power modes are updated.
        """
        orb.log.debug('* on_power_modes_updated()')
        if (getattr(self, 'dashboard', None) and
            state.get('dashboard_name') == "System Power Modes"):
            self.rebuild_dashboard()
            self.dashboard.repaint()
            ## NOTE: all of the following do exactly NOTHING ...
            # self.dashboard.expandAll()
            # self.dashboard.activateWindow()
            # self.dashboard.setFocus()
            # self.dashboard.update()
            # QTimer.singleShot(0, self.dashboard.update)

    def on_deleted_object_signal(self, oid='', cname='', remote=False):
        """
        Handle dispatcher "deleted object" signal by calling functions to
        update applicable widgets when an object has been deleted, either
        locally or remotely.

        Keyword Args:
            oid (str):  oid of the deleted object
            cname (str):  class name of the deleted object
            remote (bool):  whether the action originated remotely
        """
        # make sure db transaction has been committed
        orb.db.commit()
        origin = 'local'
        if remote:
            origin = 'remote'
        orb.log.debug(f'* received {origin} "deleted object" signal on:')
        # cname is needed here because at this point the local object has
        # already been deleted
        orb.log.debug(f'  cname="{cname}", oid="{oid}"')
        # always fix state['product'] and state['system'] if either matches the
        # deleted oid
        if (state.get('system') or {}).get(state.get('project')) == oid:
            orb.log.debug('  state "system" oid matched, set to project ...')
            state['system'][state.get('project')] = state.get('project')
        elif self.mode == 'db':
            self.set_db_interface()
        if state.get('product') == oid:
            orb.log.debug('  state "product" oid matched, resetting ...')
            if state.get('component_modeler_history'):
                hist = state['component_modeler_history']
                next_oid = hist.pop()
                orb.log.debug(f'  to next comp history oid: "{next_oid}"')
                state['product'] = next_oid
            else:
                # otherwise, set to empty string
                orb.log.debug('  to empty')
                state['product'] = ''
        if not state.get('connected'):
            # deletion was local -- do updates ...
            recompute_parmz()
            if (self.mode in ['component', 'system']
                and cname == 'HardwareProduct'):
                # if a library_widget exists, refresh it ...
                lib_widget = getattr(self, 'library_widget', None)
                try:
                    lib_widget.refresh('HardwareProduct')
                except:
                    pass
            # only attempt to update tree and dashboard if in "system" mode ...
            if ((self.mode == 'system') and
                cname in ['Acu', 'ProjectSystemUsage', 'HardwareProduct']):
                self.refresh_tree_and_dashboard()
                if getattr(self, 'system_model_window', None):
                    # rebuild diagram in case an object corresponded to a
                    # block in the current diagram
                    self.system_model_window.on_signal_to_refresh()
            elif self.mode == 'db':
                filter_panel = getattr(self, 'object_tableview', None)
                if filter_panel:
                    # if the oid is not in the table, it will be ignored
                    filter_panel.remove_object(oid)
            elif (self.mode == 'component' and
                cname in ['Acu', 'ProjectSystemUsage', 'HardwareProduct',
                          'Port', 'Flow']):
                # DIAGRAM MAY NEED UPDATING
                # update state['product'] if needed, and regenerate diagram
                # this will set placeholders in place of PgxnObject and diagram
                self.set_product_modeler_interface()
                if getattr(self, 'system_model_window', None):
                    # NOTE: no on_signal_to_refresh() here, unlike the
                    # "system" branches.  set_product_modeler_interface()
                    # goes through set_system_model_window(), which
                    # constructs a *new* ModelWindow and reassigns
                    # self.system_model_window -- so the diagram has already
                    # been built from scratch and refreshing it would
                    # regenerate what was just generated.  Clearing the flag
                    # is what is actually needed, so that a later
                    # get_parmz callback does not rebuild it a third time.
                    # Resolves remaining-chunks review #4; this is
                    # del_object()'s version of the branch, which was the
                    # correct one.
                    state['diagram needs refresh'] = False
            elif (self.mode == 'system' and
                  cname in ['Acu', 'ProjectSystemUsage', 'HardwareProduct',
                            'Port', 'Flow']):
                # DIAGRAM MAY NEED UPDATING
                # regenerate diagram
                if getattr(self, 'system_model_window', None):
                    self.system_model_window.on_signal_to_refresh()
        if remote and state.get('connected'):
            # NOTE: revised to use code from on_remote_deleted_object() ...
            # which had originally handled dispatcher "deleted object" signal
            # but was adapted for pyqtSignal remote_deleted_object ...  arg.
            orb.log.info('* pgxn: "deleted object" signal originated remotely')
            obj_oid = oid
            orb.log.info('  oid: {}'.format(obj_oid))
            deleted_obj = orb.get(obj_oid or '')
            if deleted_obj:
                # NOTE (SCW 2023-01-14) new state key, used by get_parmz()
                state['updates_needed_for_remote_obj_deletion'] = cname
                # if deleted object was the selected system, set selected system
                # and diagram subject to the project and refresh the diagram
                selected_sys_oid = state['system'].get(state.get('project'))
                orb.log.debug(f'  deleted {cname} exists in local db ...')
                if self.mode == 'db' and cname == state.get('current_cname'):
                    # object is in the current db table ...
                    state['update db table'] = True
                if cname in ['Acu', 'ProjectSystemUsage', 'HardwareProduct']:
                    relevant_obj_oid = None
                    if cname == 'HardwareProduct':
                        relevant_obj_oid = obj_oid
                        state['lib updates needed'] = True
                    elif cname == 'Acu':
                        # don't crash if acu is corrupted ...
                        try:
                            relevant_obj_oid = deleted_obj.component.oid
                        except:
                            pass
                        state['lib updates needed'] = True
                    elif cname == 'ProjectSystemUsage':
                        # don't crash if psu is corrupted ...
                        try:
                            relevant_obj_oid = deleted_obj.system.oid
                        except:
                            pass
                    orb.delete([deleted_obj])
                    orb.log.debug('  deleted.')
                    if relevant_obj_oid and selected_sys_oid == relevant_obj_oid:
                        if (state.get('component_modeler_history') and
                        relevant_obj_oid in state['component_modeler_history']):
                            state['component_modeler_history'].remove(relevant_obj_oid)
                        orb.log.info('  deleted object was selected system')
                        state['system'][state['project']] = state['project']
                        # NOTE: not currently using system_model_window.history
                        # (was broken ... fixed now?)
                        if hasattr(self, 'system_model_window'):
                            try:
                                orb.log.info('  set diagram subject to project')
                                self.system_model_window.history.pop()
                                self.system_model_window.on_set_selected_system(
                                                                self.project.oid)
                            except:
                                orb.log.info('  setting diagram subject failed')
                                # diagram model window C++ object got deleted
                                pass
                elif cname == 'RoleAssignment':
                    if deleted_obj.assigned_to is self.local_user:
                        # TODO: if removed role assignment was the last one for
                        # this user on the project, switch to SANDBOX project
                        html = '<h3>Your role:</h3>'
                        html += '<p><b><font color="green">{}</font></b>'.format(
                                                    deleted_obj.assigned_role.name)
                        html += ' in <b><font color="green">{}</font>'.format(
                                getattr(deleted_obj.role_assignment_context, 'id',
                                        'global context'))
                        html += '<br> has been removed.</b></p>'
                        self.w = NotificationDialog(html, parent=self)
                        self.w.show()
                    orb.delete([deleted_obj])
                    orb.log.debug('  deleted.')
                elif cname in ['Mission', 'Activity']:
                    # DO NOT delete here if conops is running, it will handle the
                    # "deleted object" signal ...
                    if not state.get("conops"):
                        objs_to_delete = [deleted_obj]
                        subacts = getattr(deleted_obj, 'sub_activities', [])
                        if subacts:
                            # if it has sub_activities, delete them too
                            objs_to_delete += subacts
                        orb.delete(objs_to_delete)
                        orb.log.debug('  ConOpsModeler is not running --')
                        orb.log.debug(f'  "{cname}" object deleted.')
                else:
                    orb.delete([deleted_obj])
                    orb.log.debug('  deleted.')
                self.get_parmz()
            else:
                orb.log.debug('  oid not found in local db; ignoring.')

            # -----------------------------------------------------------------
            # The commented code below assumed that on_remote_deleted_object()
            # was called first and deleted the object, etc. ...
            # -----------------------------------------------------------------
            # # update library widget if one exists ...
            # lib_widget = getattr(self, 'library_widget', None)
            # if lib_widget:
                # try:
                    # lib_widget.refresh('HardwareProduct')
                # except:
                    # pass
            # # only attempt to update tree and dashboard if in "system" mode ...
            # if (self.mode in ['component', 'system']
                # and cname == 'HardwareProduct'):
                # try:
                    # self.library_widget.refresh()
                # except:
                    # pass
            # if ((self.mode == 'system') and
                # cname in ['Acu', 'ProjectSystemUsage', 'HardwareProduct',
                          # 'Port', 'Flow']):
                # self.refresh_tree_and_dashboard()
                # # DIAGRAM MAY NEED UPDATING
                # if getattr(self, 'system_model_window', None):
                    # # rebuild diagram in case an object corresponded to a
                    # # block in the current diagram
                    # self.system_model_window.on_signal_to_refresh()
            # elif self.mode == 'db':
                # self.set_db_interface()
            # elif (self.mode in ['system', 'component'] and
                  # cname in ['Acu', 'ProjectSystemUsage', 'HardwareProduct',
                            # 'Port', 'Flow']):
                # # DIAGRAM MAY NEED UPDATING
                # # update state['product'] if needed, and regenerate diagram
                # # this will set placeholders in place of PgxnObject and diagram
                # self.set_product_modeler_interface()
                # if getattr(self, 'system_model_window', None):
                    # self.system_model_window.on_signal_to_refresh()
        if not remote and state.get('connected'):
            # the "not remote" here is *extremely* important, to prevent a cycle ...
            # only attempt to update tree and dashboard if in "system" mode ...
            if (self.mode in ['component', 'system']
                and cname == 'HardwareProduct'):
                state['lib updates needed'] = True
            if ((self.mode == 'system') and
                cname in ['Acu', 'ProjectSystemUsage', 'HardwareProduct',
                          'Port', 'Flow']):
                self.refresh_tree_and_dashboard()
                # DIAGRAM MAY NEED UPDATING
                if getattr(self, 'system_model_window', None):
                    # rebuild diagram in case an object corresponded to a
                    # block in the current diagram
                    self.system_model_window.on_signal_to_refresh()
            elif self.mode == 'db':
                self.set_db_interface()
            elif (self.mode in ['system', 'component'] and
                  cname in ['Acu', 'ProjectSystemUsage', 'HardwareProduct',
                            'Port', 'Flow']):
                # DIAGRAM MAY NEED UPDATING
                # update state['product'] if needed, and regenerate diagram
                # this will set placeholders in place of PgxnObject and diagram
                self.set_product_modeler_interface()
                if getattr(self, 'system_model_window', None):
                    # NOTE: no on_signal_to_refresh() here, unlike the
                    # "system" branches.  set_product_modeler_interface()
                    # goes through set_system_model_window(), which
                    # constructs a *new* ModelWindow and reassigns
                    # self.system_model_window -- so the diagram has already
                    # been built from scratch and refreshing it would
                    # regenerate what was just generated.  Clearing the flag
                    # is what is actually needed, so that a later
                    # get_parmz callback does not rebuild it a third time.
                    # Resolves remaining-chunks review #4; this is
                    # del_object()'s version of the branch, which was the
                    # correct one.
                    state['diagram needs refresh'] = False
            orb.log.info('  - calling "vger.delete"')
            try:
                rpc = self.mbus.session.call('vger.delete', [oid])
                rpc.addCallback(self.on_rpc_vger_delete_result)
                rpc.addCallback(self.get_parmz)
                rpc.addErrback(self.on_failure)
            except:
                orb.log.debug('  ** rpc failed (possible loss of transport)')
                orb.log.debug('     trying to reconnect ...')
                # the rpc never went out, so this is in the same position as
                # a deletion made offline -- queue it rather than lose it
                self.queue_deletion(oid, cname)
                self.set_bus_state()
        elif not remote:
            # deleted locally while offline:  queue for replay at the next
            # sync.  Without this the repository is never told, and both sync
            # paths treat "the client did not report this oid" as "the client
            # needs it" -- so the object simply comes back.
            self.queue_deletion(oid, cname)

    # ------------------------------------------------------------------------
    # NOTE: self.remote_deleted_object is DEPRECATED in favor of dispatcher
    # "deleted object" signal
    # ------------------------------------------------------------------------
    # def on_remote_deleted_object(self, oid, cname):
        # """
        # Handle pyqtSignal "remote_deleted_object".
        # """
        # orb.log.info('* pgxn.on_remote_deleted_object()')
        # obj_oid = oid
        # orb.log.info('  oid: {}'.format(obj_oid))
        # # notify widgets looking for "deleted object" signal ...
        # # -----------------------------------------
        # # NOTE: VERY IMPORTANT TO USE remote=True
        # # -----------------------------------------
        # dispatcher.send(signal="deleted object", oid=oid, cname=cname,
                        # remote=True)
        # deleted_obj = orb.get(obj_oid or '')
        # if deleted_obj:
            # # NOTE (SCW 2023-01-14) new state key, used by get_parmz()
            # state['updates_needed_for_remote_obj_deletion'] = cname
            # # if deleted object was the selected system, set selected system
            # # and diagram subject to the project and refresh the diagram
            # selected_sys_oid = state['system'].get(state.get('project'))
            # orb.log.debug(f'  deleted {cname} exists in local db ...')
            # if self.mode == 'db' and cname == state.get('current_cname'):
                # # object is in the current db table ...
                # state['update db table'] = True
            # if cname in ['Acu', 'ProjectSystemUsage', 'HardwareProduct']:
                # relevant_obj_oid = None
                # if cname == 'HardwareProduct':
                    # relevant_obj_oid = obj_oid
                    # state['lib updates needed'] = True
                # elif cname == 'Acu':
                    # # don't crash if acu is corrupted ...
                    # try:
                        # relevant_obj_oid = deleted_obj.component.oid
                    # except:
                        # pass
                    # state['lib updates needed'] = True
                # elif cname == 'ProjectSystemUsage':
                    # # don't crash if psu is corrupted ...
                    # try:
                        # relevant_obj_oid = deleted_obj.system.oid
                    # except:
                        # pass
                # orb.delete([deleted_obj])
                # orb.log.debug('  deleted.')
                # if relevant_obj_oid and selected_sys_oid == relevant_obj_oid:
                    # if (state.get('component_modeler_history') and
                    # relevant_obj_oid in state['component_modeler_history']):
                        # state['component_modeler_history'].remove(relevant_obj_oid)
                    # orb.log.info('  deleted object was selected system')
                    # state['system'][state['project']] = state['project']
                    # # NOTE: not currently using system_model_window.history
                    # # (was broken ... fixed now?)
                    # if hasattr(self, 'system_model_window'):
                        # try:
                            # orb.log.info('  set diagram subject to project')
                            # self.system_model_window.history.pop()
                            # self.system_model_window.on_set_selected_system(
                                                            # self.project.oid)
                        # except:
                            # orb.log.info('  setting diagram subject failed')
                            # # diagram model window C++ object got deleted
                            # pass
            # elif cname == 'RoleAssignment':
                # if deleted_obj.assigned_to is self.local_user:
                    # # TODO: if removed role assignment was the last one for
                    # # this user on the project, switch to SANDBOX project
                    # html = '<h3>Your role:</h3>'
                    # html += '<p><b><font color="green">{}</font></b>'.format(
                                                # deleted_obj.assigned_role.name)
                    # html += ' in <b><font color="green">{}</font>'.format(
                            # getattr(deleted_obj.role_assignment_context, 'id',
                                    # 'global context'))
                    # html += '<br> has been removed.</b></p>'
                    # self.w = NotificationDialog(html, parent=self)
                    # self.w.show()
                # orb.delete([deleted_obj])
                # orb.log.debug('  deleted.')
            # elif cname in ['Mission', 'Activity']:
                # # DO NOT delete here if conops is running, it will handle the
                # # "deleted object" signal ...
                # if not state.get("conops"):
                    # objs_to_delete = [deleted_obj]
                    # subacts = getattr(deleted_obj, 'sub_activities', [])
                    # if subacts:
                        # # if it has sub_activities, delete them too
                        # objs_to_delete += subacts
                    # orb.delete(objs_to_delete)
                    # orb.log.debug('  ConOpsModeler is not running --')
                    # orb.log.debug(f'  "{cname}" object deleted.')
            # else:
                # orb.delete([deleted_obj])
                # orb.log.debug('  deleted.')
            # self.get_parmz()
        # else:
            # orb.log.debug('  oid not found in local db; ignoring.')

    def resync_current_project(self, msg=''):
        """
        Resync current project with repository.
        """
        orb.log.debug('* resync_current_project()')
        self.on_set_current_project(msg=msg)

    def resync_all_projects(self):
        """
        Convenience function that saves having to select each project to which
        the user has access in turn, which is rather boring and time-consuming.
        """
        for project in self.projects:
            oid = project.oid
            if oid != 'pgefobjects:SANDBOX':
                state['project'] = oid
                self.on_set_current_project(msg='')

    def full_resync(self):
        """
        Force full synchronization with server (ignoring mod_datetimes).
        """
        orb.log.debug('* user requested force full resync ...')
        dlg = FullSyncDialog(parent=self)
        if dlg.exec_():
            orb.log.debug('  confirmed, resyncing ...')
            self.sync_with_services(force=True)
        else:
            return

    def on_set_current_project(self, msg=''):
        """
        Update views as a result of a project being set, syncing project data
        if [1] in "connected" state and [2] project is not "SANDBOX".
        """
        # NOTE: (SCW 2023-01-13) project resync is now done even if the project
        # has already been synced previously in the current session -- which
        # also means the previously used "resync" kw arg is ignored.
        orb.log.debug('* on_set_current_project()')
        project_oid = state.get('project')
        if ((project_oid and project_oid != 'pgefobjects:SANDBOX')
             and state.get('connected')):
            # =================================================================
            # NOTE: this commented code is retained as a counter-example ...
            # DO NOT DO THIS!!!
            # =================================================================
            # NOTE: ProgressDialog stuff caused mbus to lose its transport --
            # BAD! -- so is disabled ...
            # project = orb.get(project_oid)
            # title_text = f'Syncing project {project.id}'
            # label_text = f'Receiving {project.id} items ... '
            # self.proj_sync_progress = ProgressDialog(title=title_text,
                                              # label=label_text,
                                              # parent=self)
            # self.proj_sync_progress.setAttribute(Qt.WA_DeleteOnClose)
            # self.proj_sync_progress.setValue(0)
            # self.proj_sync_progress.setMinimumDuration(2000)
            # QApplication.processEvents()
            # =================================================================
            orb.log.debug('  calling sync_current_project()')
            rpc = self.sync_current_project(None, msg=msg)
            rpc.addCallback(self.on_project_sync_result)
            rpc.addErrback(self.on_failure)
        else:
            self.sys_tree_rebuilt = False
            self.dashboard_rebuilt = False
            self._update_modal_views()

    def update_project_role_labels(self):
        """
        Refresh the 'role_label' widget (bottom right corner of gui) with the
        user's latest role assignment(s) for the current project.
        """
        p = self.project
        role_label_txt = ''
        tt_txt = ''
        p_roles = []
        admin_role = orb.get('pgefobjects:Role.Administrator')
        global_admin = is_global_admin(self.local_user)
        if p:
            self.project_selection.setText(str(p.id))
            # orb.log.debug('* set_project({})'.format(str(p.id)))
            # state['project'] = str(p.oid)
            # if hasattr(self, 'delete_project_action'):
            if p is self.sandbox:
                # SANDBOX cannot be deleted, made collaborative, nor have
                # roles provisioned (admin)
                self.delete_project_action.setEnabled(False)
                self.delete_project_action.setVisible(False)
                # admin menus accessible only to global admin ...
                if global_admin:
                    self.admin_action.setVisible(True)
                    self.admin_action.setEnabled(True)
                else:
                    self.admin_action.setVisible(False)
                    self.admin_action.setEnabled(False)
                role_label_txt = 'SANDBOX'
            else:
                project_is_local = False
                p_ras = orb.search_exact(cname='RoleAssignment',
                                         assigned_to=self.local_user,
                                         role_assignment_context=p)
                p_roles = [ra.assigned_role.name for ra in p_ras]
                project_admin = orb.select('RoleAssignment',
                                          assigned_role=admin_role,
                                          assigned_to=self.local_user,
                                          role_assignment_context=p)
                if 'delete' in get_perms(p):
                    project_is_local = True
                    role_label_txt = ': '.join([str(p.id), '[local]'])
                number_of_roles = len(p_roles)
                if global_admin:
                    number_of_roles += 1
                if number_of_roles:
                    if number_of_roles > 1:
                        # add asterisk to indicate multiple roles
                        role_label_txt = ': '.join([str(p.id), p_roles[0],
                                                    ' *'])
                        tt_txt = '<ul>\n'
                        for r in p_roles:
                            pid = str(p.id)
                            role = '&nbsp;'.join(str(r).split(' '))
                            tt_txt += f'<li>{pid}:&nbsp;{role}</li>\n'
                        if global_admin:
                            tt_txt += '<li>Global&nbsp;Administrator</li>\n'
                        tt_txt += '</ul>'
                    elif p_roles:
                        role_label_txt = ': '.join([str(p.id), p_roles[0]])
                    elif global_admin:
                        role_label_txt = 'Global Administrator'
                if state['connected']:
                    if ((p.creator is self.local_user) or global_admin):
                        # a project can be deleted by its creator or by a
                        # global admin
                        self.delete_project_action.setEnabled(True)
                        self.delete_project_action.setVisible(True)
                    else:
                        # project is collaborative ->
                        # to delete it, all roles must first be deleted ...
                        # (in which case it becomes a local project :)
                        self.delete_project_action.setEnabled(False)
                        self.delete_project_action.setVisible(False)
                    if project_admin or global_admin:
                        self.admin_action.setVisible(True)
                        self.admin_action.setEnabled(True)
                    # SELE = set(['Systems Engineer', 'Lead Engineer'])
                    # if project_admin or global_admin or (SELE & set(p_roles)):
                        # self.modes_def_action.setVisible(True)
                        # self.modes_def_action.setEnabled(True)
                    # else:
                        # self.modes_def_action.setVisible(False)
                        # self.modes_def_action.setEnabled(False)
                else:
                    # when offline, admin and modes def actions are disabled
                    self.admin_action.setVisible(False)
                    self.admin_action.setEnabled(False)
                    # self.modes_def_action.setVisible(False)
                    # self.modes_def_action.setEnabled(False)
                    # only local projects can be deleted
                    if (project_is_local and 
                        (p.creator == self.local_user or global_admin)):
                        self.delete_project_action.setEnabled(True)
                        self.delete_project_action.setVisible(True)
                    else:
                        self.delete_project_action.setEnabled(False)
                        self.delete_project_action.setVisible(False)
        else:
            self.project_selection.setText('None')
            # orb.log.debug('* set_project(None)')
            orb.log.debug('  setting project label to SANDBOX (default)')
            # state['project'] = 'pgefobjects:SANDBOX'
            role_label_txt = 'SANDBOX'
            if hasattr(self, 'delete_project_action'):
                self.delete_project_action.setEnabled(False)
                self.delete_project_action.setVisible(False)
        self.role_label.setText(role_label_txt)
        if tt_txt:
            self.role_label.setToolTip(tt_txt)
        else:
            self.role_label.setToolTip(role_label_txt)

    def _update_modal_views(self, obj=None):
        """
        Call functions to update all widgets when mode has changed due to some
        action.

        Keyword Args:
            obj (Identifiable):  object whose change triggered the update
        """
        # orb.log.debug('* _update_modal_views()')
        # orb.log.debug('  triggered by object: {}'.format(
                                        # getattr(obj, 'id', '[no object]')))
        state['modal views need update'] = False
        if getattr(self, 'system_model_window', None):
            self.system_model_window.cache_block_model()
        # [gui refactor] creation of top dock moved to _init_ui()
        self.update_project_role_labels()
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
        # orb.log.debug('  - no top dock widget -- building one now...')
        self.top_dock_widget = QDockWidget()
        self.top_dock_widget.setObjectName('TopDock')
        self.top_dock_widget.setAllowedAreas(Qt.TopDockWidgetArea)
        # NOTE:  might not need to be floatable (now spans the whole window)
        self.top_dock_widget.setFeatures(QDockWidget.DockWidgetFloatable)
        # create widget for top dock:
        if self.mode == 'system':
            # ********************************************************
            # dashboard panel
            # ********************************************************
            self.refresh_tree_and_dashboard()
            if not getattr(self, 'dashboard_panel', None):
                self.rebuild_dashboard()
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
        self.product_info_panel.setContextMenuPolicy(Qt.PreventContextMenu)

    def _setup_left_dock(self):
        """
        Set up the persistent left dock widget containers.
        """
        # orb.log.debug('  - no left dock widget -- adding one now...')
        # if we don't have a left dock widget yet, create ALL the stuff
        self.left_dock = QDockWidget()
        self.left_dock.setObjectName('LeftDock')
        self.left_dock.setContextMenuPolicy(Qt.PreventContextMenu)
        self.left_dock.setFeatures(QDockWidget.DockWidgetFloatable)
        self.left_dock.setAllowedAreas(Qt.LeftDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.left_dock)

    def _setup_right_dock(self):
        # orb.log.debug('  - no right dock widget -- building one now...')
        # if we don't have a right dock widget yet, create ALL the stuff
        self.right_dock = QDockWidget()
        self.right_dock.setObjectName('RightDock')
        self.right_dock.setFeatures(QDockWidget.DockWidgetFloatable)
        self.right_dock.setAllowedAreas(Qt.RightDockWidgetArea)
        self.right_dock.topLevelChanged.connect(self.on_library_floated)
        self.library_widget = self.create_lib_widget()
        self.library_widget.setMinimumWidth(600)
        self.library_widget.setMaximumWidth(600)
        self.right_dock.setWidget(self.library_widget)
        self.addDockWidget(Qt.RightDockWidgetArea, self.right_dock)

    def on_library_floated(self):
        if getattr(self, 'right_dock', None):
            if self.right_dock.isFloating():
                orb.log.debug('* library is floating now!')
                self.library_widget.expand_button.hide()
                self.library_widget.setMaximumWidth(self.geometry().width())
                self.library_widget.resize(self.geometry().width() - 200,
                                           self.geometry().height())
                self.library_widget.update()
            else:
                orb.log.debug('* library is docked')
                self.library_widget.setMaximumWidth(600)
                self.library_widget.expanded = True
                self.library_widget.expand_button.setVisible(True)
                self.library_widget.expand_button.setText('Collapse')

    def update_pgxno(self, mod_oids=None):
        """
        Send "update pgxno" signal to update the editor.
        """
        if not mod_oids:
             mod_oids = state.get('pgxno_oids')
        dispatcher.send(signal="update pgxno",
                        mod_oids=mod_oids)

    def update_pgxn_obj_panel(self, create_new=True):
        """
        Set up a new PgxnObject panel (left dock widget in Component mode).
        """
        # orb.log.debug('* update_pgxn_obj_panel(create_new={})'.format(
                                                           # str(create_new)))
        # if there is an existing panel, remove and destroy its contents
        if getattr(self, 'pgxn_obj_panel', None):
            try:
                pgxn_panel_layout = self.pgxn_obj_panel.layout()
                if getattr(self, 'pgxn_obj', None):
                    pgxn_panel_layout.removeWidget(self.pgxn_obj)
                    # NOTE:  WA_DeleteOnClose kills the "ghost pgxnobject" bug
                    self.pgxn_obj.setAttribute(Qt.WA_DeleteOnClose)
                    self.pgxn_obj.setParent(None)
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
                self.pgxn_obj_panel.setParent(None)
                self.pgxn_obj_panel.close()
                self.pgxn_obj_panel = None
            except:
                # oops, pgxn_obj_panel's C++ object got deleted
                pass
        if create_new:
            # create a new panel
            self.pgxn_obj_panel = QWidget()
            self.pgxn_obj_panel.setContextMenuPolicy(Qt.PreventContextMenu)
            self.pgxn_obj_panel.setSizePolicy(QSizePolicy.Fixed,
                                              QSizePolicy.Expanding)
            pgxn_panel_layout = QVBoxLayout()
            self.pgxn_obj_panel.setLayout(pgxn_panel_layout)
            pgxn_panel_layout.setAlignment(self.pgxn_obj_panel,
                                         Qt.AlignLeft|Qt.AlignTop)
            if self.product:
                self.pgxn_obj = PgxnObject(self.product, component=True,
                                           embedded=True)
                pgxn_panel_layout.addWidget(self.pgxn_obj)
                pgxn_panel_layout.setAlignment(self.pgxn_obj,
                                             Qt.AlignLeft|Qt.AlignTop)
                pgxn_panel_layout.addStretch(1)
            else:
                placeholder = PlaceHolder(image=self.logo, min_size=400,
                                          parent=self)
                pgxn_panel_layout.addWidget(placeholder)

    def refresh_tree_and_dashboard(self, selected_link_oid=None):
        """
        Tree / dashboard refresh.  Can be user-activated by menu item.
        """
        # orb.log.debug('* refresh_tree_and_dashboard()')
        if not state.get('connected'):
            recompute_parmz()
        self.sys_tree_rebuilt = False
        self.dashboard_rebuilt = False
        self.refresh_tree_views(selected_link_oid=selected_link_oid)

    def refresh_tree_views(self, rebuilding=False, selected_link_oid=None):
        """
        Refresh and/or rebuild the system tree and dashboard(s).  This is used
        both at startup when a project is initially set and whenever the
        current project is changed or when switching to "system mode" from
        another mode.

        Keyword Args:
            rebuilding (bool): views need to be rebuilt
            selected_link_oid (str): oid of the link (Acu or PSU) in the tree
                that was selected when this project was last viewed.
        """
        # orb.log.debug('* refresh_tree_views()')
        # first check for cycles in the current project systems
        psus = orb.search_exact(cname='ProjectSystemUsage',
                                project=self.project)
        systems = [psu.system for psu in psus]
        level_count = 0
        for system in systems:
            cycles = check_for_cycles(system)
            if cycles:
                html = '<h3>Cycles Found</h3>'
                html += f'<p><b><font color="red">{cycles}</font></b></p>'
                dlg = NotificationDialog(html, parent=self)
                dlg.show()
                return
            else:
                # determine how many levels are in the assembly ---------------
                system_level_count = get_level_count(system)
                if system_level_count > level_count:
                    level_count = system_level_count
        # orb.log.debug(f"* level count = {level_count}")
        ######################################################################
        # TODO: possibly use get_bom() or get_assembly() when the current
        # project is set to get all sys tree items for the current project,
        # cache all oids and use that to determine whether the tree needs to be
        # refreshed ...
        ######################################################################
        # orb.log.debug('* refreshing system tree and rebuilding dashboard ...')
        # use number of tree levels to set max in progress bar
        # ------------------------------------------------------------------
        # NOTE: a block here used to "destroy the existing dashboard" --
        # removeWidget / WA_DeleteOnClose / hide / setParent(None) / close on
        # self.dashboard.  It has been removed, for two reasons.
        #
        # First, "dashboard" is a read-only *property* (see above): it returns
        # multidashboard.dashboards.widget(idx), i.e. a page belonging to the
        # MultiDashboard stack, not a widget this window owns.  The block
        # ended with "self.dashboard = None", which a property without a
        # setter refuses -- so it raised AttributeError every time, was
        # swallowed by the bare "except: pass" below it, and the line after it
        # never ran at all.  The block never did what it said.
        #
        # Second, it became actively destructive once the widget-detach idiom
        # was corrected (".parent = None", which did nothing, became
        # setParent(None), which detaches): the page was then genuinely
        # destroyed, the MultiDashboard was left with a dead page, and the
        # Systems Dashboard went blank and stayed blank when a remote
        # modification arrived.  Reported from live two-machine testing,
        # 2026-08-04.
        #
        # The MultiDashboard's lifetime is rebuild_dashboard()'s business, and
        # it is called below.  The identical teardown *inside* that method was
        # already commented out.
        # ------------------------------------------------------------------
        try:
            # orb.log.debug('  + destroying existing self.sys_tree, if any ...')
            # NOTE:  WA_DeleteOnClose kills the "ghost tree" bug
            self.sys_tree.setAttribute(Qt.WA_DeleteOnClose)
            self.sys_tree.setParent(None)
            self.sys_tree.close()
            self.sys_tree = None
        except:
            # if unsuccessful, it means there wasn't one, so no harm done
            pass
        # orb.log.debug('  + destroying existing pgxn_obj panel, if any ...')
        self.update_pgxn_obj_panel(create_new=False)
        # orb.log.debug('    self.pgxn_obj is {}'.format(str(
                      # getattr(self, 'pgxn_obj', None))))
        # destroy left dock's widget
        ld_widget = self.left_dock.widget()
        if ld_widget:
            ld_widget.setAttribute(Qt.WA_DeleteOnClose)
            ld_widget.setParent(None)
            ld_widget.close()
        self.sys_tree = SystemTreeView(self.project)
        # orb.log.debug('  + new self.sys_tree created ...')
        # sys_id = getattr(sys, 'id', '[none]') or '[none]'
        # orb.log.debug(f'    with selected system: {sys_id}')
        # model = self.sys_tree.source_model
        # orb.log.debug('    with source model: {}'.format(str(model)))
        self.sys_tree.setSizePolicy(QSizePolicy.Expanding,
                                    QSizePolicy.Expanding)
        self.sys_tree_rebuilt = True
        # NB:  rebuild dashboard before expanding sys_tree, because their
        # expand events are linked so they must both exist
        self.rebuild_dashboard()
        sys_tree_panel = QWidget(self)
        sys_tree_panel.setContextMenuPolicy(Qt.PreventContextMenu)
        # set panel size policy to match the sys_tree's
        # sys_tree_panel.setSizePolicy(QSizePolicy.MinimumExpanding,
        sys_tree_panel.setSizePolicy(QSizePolicy.Expanding,
                                     QSizePolicy.Expanding)
        sys_tree_panel.setMinimumWidth(400)
        # set panel max width to match the max width set for sys_tree
        sys_tree_layout = QVBoxLayout(sys_tree_panel)
        self.expansion_select = QComboBox()
        self.expansion_select.setStyleSheet(
                                        'font-weight: bold; font-size: 14px')
        # set available expansion levels based on computed level_count ...
        if level_count and level_count >= 1:
            for n in range(2, level_count + 1):
                self.expansion_select.addItem(f'{n} levels', QVariant())
        sys_tree_layout.addWidget(self.expansion_select)
        sys_tree_layout.addWidget(self.sys_tree)
        gripper = Gripper(self.sys_tree, w=10, h=10)
        sys_tree_layout.addWidget(gripper,
                                  alignment=Qt.AlignLeft|Qt.AlignBottom)
        self.left_dock.setWidget(sys_tree_panel)
        # set sys tree expansion level
        self.expansion_select.currentIndexChanged.connect(
                                                    self.set_systree_expansion)
        if state['sys_tree_expansion'].get(self.project.oid):
            self.expansion_select.setCurrentIndex(
                state['sys_tree_expansion'][self.project.oid])
        else:
            state['sys_tree_expansion'][self.project.oid] = 0
        self.set_systree_expansion()

    def set_systree_expansion(self, index=None):
        if index is None:
            index = state.get('sys_tree_expansion', {}).get(
                                                self.project.oid) or 0
        # NOTE:  levels are 2 to 5, so level = index + 2
        #        expandToDepth(n) actually means level n + 1
        try:
            level = index + 2
            self.sys_tree.expandToDepth(level - 1)
            state['sys_tree_expansion'][self.project.oid] = index
            # orb.log.debug(f'* tree expanded to level {level}')
        except:
            orb.log.debug('* sys tree expansion failed.')
            pass
        finally:
            # orb.log.debug('* setting selected system ...')
            # after expanding, set the selected system
            dispatcher.send(signal='set selected system')

    def rebuild_dash_selector(self):
        # -------------------------------------------------------------------
        # NOTE: dash_select temporarily deactivated -- dash switching is
        # causing segfaults [SCW 2024-02-07]
        # -------------------------------------------------------------------
        pass
        # -------------------------------------------------------------------
        # orb.log.debug('* rebuild_dash_selector()')
        # if getattr(self, 'dashboard_title_layout', None):
            # orb.log.debug('  - dashboard_title_layout exists ...')
            # orb.log.debug('  - removing old dash selector ...')
            # self.dashboard_title_layout.removeWidget(self.dash_select)
            # self.dash_select.setAttribute(Qt.WA_DeleteOnClose)
            # self.dash_select.close()
            # self.dash_select = None
            # # orb.log.debug('  - creating new dash selector ...')
            # new_dash_select = QComboBox()
            # new_dash_select.setStyleSheet(
                                # 'font-weight: bold; font-size: 14px')
            # for dash_name in prefs['dashboard_names']:
                # new_dash_select.addItem(dash_name, QVariant)
            # if state.get('project', '') in mode_defz:
                # new_dash_select.addItem('System Power Modes', QVariant)
            # new_dash_select.setCurrentIndex(0)
            # new_dash_select.activated.connect(self.set_dashboard)
            # self.dash_select = new_dash_select
            # self.dashboard_title_layout.addWidget(self.dash_select)
        # -------------------------------------------------------------------

    def on_parm_recompute(self):
        # rebuilding dashboard is only needed in "system" mode
        if self.mode == 'system':
            try:
                # self.rebuild_dashboard(force=True)
                # NOTE: testing to see if refresh_dashboard() is enough
                self.refresh_dashboard()
            except:
                # sometimes mode might be set to "system" but transitioning to
                # "component", in which case the C++ object for the dashboard
                # ceased to exist
                pass

    def mod_dashboard(self):
        self.rebuild_dashboard(dashboard_mod=True)

    def rebuild_dashboard(self, dashboard_mod=False, force=False):
        # orb.log.debug('* rebuild_dashboard()')
        if not self.mode == 'system':
            # orb.log.debug('    not in "system mode" -- ignoring.')
            return
        if (not force and not dashboard_mod and
            (not self.sys_tree_rebuilt or self.dashboard_rebuilt)):
            # orb.log.debug('  + no force and no dash mod and either tree')
            # orb.log.debug('    not rebuilt or dashboard already rebuilt;')
            # orb.log.debug('    not rebuilding.')
            return
        # orb.log.debug(' + rebuilding ...')
        if getattr(self, 'dashboard_panel', None):
            # orb.log.debug('  + dashboard_panel exists ...')
            # orb.log.debug('    clearing out select and dashboard ...')
            dashboard_panel_layout = self.dashboard_panel.layout()
            # ----------------------------------------------------------------
            # NOTE: dash_select temporarily deactivated -- dash switching is
            # causing segfaults [SCW 2024-02-07]
            # if getattr(self, 'dash_select', None):
                # dashboard_panel_layout.removeWidget(self.dash_select)
                # self.dash_select.setAttribute(Qt.WA_DeleteOnClose)
                # self.dash_select.close()
                # self.dash_select = None
            # ----------------------------------------------------------------
            # if getattr(self, 'dashboard', None):
                # dashboard_panel_layout.removeWidget(self.dashboard)
                # self.dashboard.setAttribute(Qt.WA_DeleteOnClose)
                # self.dashboard.close()
                # self.dashboard = None
            if getattr(self, 'multidashboard', None):
                dashboard_panel_layout.removeWidget(self.multidashboard)
                self.multidashboard.setAttribute(Qt.WA_DeleteOnClose)
                self.multidashboard.close()
                self.multidashboard = None
            # orb.log.debug('    destroying old dashboard_panel ...')
            self.dashboard_panel.setAttribute(Qt.WA_DeleteOnClose)
            self.dashboard_panel.close()
            self.dashboard_panel = None
        # else:
            # orb.log.debug('  + no dashboard_panel exists ...')
        # orb.log.debug('    creating new dashboard panel ...')
        self.dashboard_panel = QWidget(self)
        self.dashboard_panel.setContextMenuPolicy(Qt.PreventContextMenu)
        self.dashboard_panel.setMinimumSize(500, 200)
        dashboard_panel_layout = QVBoxLayout()
        self.dashboard_title_layout = QHBoxLayout()
        self.dash_title = QLabel()
        # orb.log.debug('           adding title ...')
        self.dashboard_title_layout.addWidget(self.dash_title)
        # --------------------------------------------------------------------
        # NOTE: dash_select temporarily deactivated -- dash switching is
        # causing segfaults [SCW 2024-02-07]
        # self.dash_select = QComboBox()
        # self.dash_select.setStyleSheet('font-weight: bold; font-size: 14px')
        # for dash_name in prefs['dashboard_names']:
            # self.dash_select.addItem(dash_name, QVariant)
        # if state.get('project', '') in mode_defz:
            # self.dash_select.addItem('System Power Modes', QVariant)
        # if (state.get('dashboard_name') == 'System Power Modes' and
            # not (state.get('project', '') in mode_defz)):
            # state['dashboard_name'] = 'MEL'
        # dash_name = state.get('dashboard_name', 'MEL')
        # state['dashboard_name'] = dash_name
        # --------------------------------------------------------------------
        # state['dashboard_name'] = 'MEL'
        # --------------------------------------------------------------------
        # self.dash_select.setCurrentText(dash_name)
        # self.dash_select.activated.connect(self.set_dashboard)
        # # orb.log.debug('           adding dashboard selector ...')
        # self.dashboard_title_layout.addWidget(self.dash_select)
        # --------------------------------------------------------------------
        dashboard_panel_layout.addLayout(self.dashboard_title_layout)
        self.dashboard_panel.setLayout(dashboard_panel_layout)
        self.top_dock_widget.setWidget(self.dashboard_panel)
        if getattr(self, 'sys_tree', None):
            # orb.log.debug('         + creating new dashboard tree ...')
            # self.dashboard = SystemDashboard(self.sys_tree.model(),
                                             # parent=self)
            self.multidashboard = MultiDashboard(self.project, parent=self)
            self.dashboard.setFrameStyle(QFrame.Panel | QFrame.Raised)
        else:
            orb.log.debug('         + no sys_tree; using placeholder '
                          'for dashboard...')
            # self.dashboard = QLabel('No Project Selected')
            # self.dashboard.setStyleSheet('font-weight: bold; font-size: 16px')
        dashboard_panel_layout.addWidget(self.multidashboard)
        gripper = Gripper(self.sys_tree, w=10, h=10)
        dashboard_panel_layout.addWidget(gripper,
                                      alignment=Qt.AlignRight|Qt.AlignBottom)
        title = 'Systems Dashboard: <font color="purple">{}</font>'.format(
                                                               self.project.id)
        self.dash_title.setText(title)
        self.dash_title.setStyleSheet('font-weight: bold; font-size: 18px')
        # model = self.dashboard.model().sourceModel()
        # for column in range(model.columnCount()):
            # self.dashboard.resizeColumnToContents(column)
        self.dashboard.setFocus(True)
        self.dashboard.update()
        self.update()
        self.dashboard_rebuilt = True

    # def set_dashboard(self, index):
        # """
        # Set the dashboard state to the selected view.
        # """
        # # --------------------------------------------------------------------
        # # NOTE: dash_select temporarily deactivated -- dash switching is
        # # causing segfaults [SCW 2024-02-07]
        # # --------------------------------------------------------------------
        # # dash_name = self.dash_select.currentText()
        # # --------------------------------------------------------------------
        # dash_name = 'MEL'
        # if (dash_name == 'System Power Modes' and
            # not (state.get('project', '') in mode_defz)):
            # dash_name = 'MEL'
        # # --------------------------------------------------------------------
        # # self.dash_select.setCurrentText(dash_name)
        # # --------------------------------------------------------------------
        # state['dashboard_name'] = dash_name
        # self.refresh_tree_and_dashboard()

    def refresh_dashboard(self):
        # orb.log.debug('* refreshing dashboard ...')
        if hasattr(self, 'dashboard') and self.dashboard.model():
            self.dashboard.setFocus()
            for column in range(self.dashboard.model().columnCount(
                                                    QModelIndex())):
                self.dashboard.resizeColumnToContents(column)
            self.dashboard.update()
            self.update()

    def update_object_in_trees(self, obj, new=False):
        """
        Update the tree and dashboard in response to a modified object.

        Args:
            obj (Product, Acu, or ProjectSystemUsage): the object

        Keyword Args:
            new (bool):  True if a new object, otherwise False
        """
        # orb.log.debug('* update_object_in_trees() ...')
        if not obj:
            # orb.log.debug('  no object provided; ignoring.')
            state["upd_obj_in_trees_needed"] = ("", "")
            return
        try:
            cname = obj.__class__.__name__
            idxs = []
            if cname in ['Acu', 'ProjectSystemUsage']:
                # for link objects, the modified link might not have the same
                # system/component, so we have to search for instances of the
                # link itself (rather than the system/component) in the tree.
                # NOTE: link_indexes_in_tree() returns *source* model indexes
                # orb.log.debug('  - object is an acu/psu ...')
                idxs = self.sys_tree.link_indexes_in_tree(obj)
                if idxs:
                    log_msg = 'indexes found in tree, updating ...'
                    orb.log.debug('    {}'.format(log_msg))
                    if cname == 'Acu':
                        # orb.log.debug('    [obj is Acu]')
                        node_obj = obj.component
                    elif cname == 'ProjectSystemUsage':
                        # orb.log.debug('    [obj is PSU]')
                        node_obj = obj.system
                    for idx in idxs:
                        self.sys_tree.source_model.setData(idx, node_obj)
                    # resize/refresh dashboard columns if necessary
                    self.refresh_tree_and_dashboard()
                else:
                    log_msg = 'no indexes found in tree.'
                    orb.log.debug('    {}'.format(log_msg))
                    if cname == 'ProjectSystemUsage':
                        if new:
                            # rebuild tree when a new system has been added
                            self.refresh_tree_and_dashboard()
                        else:
                            # log_msg = 'obj is psu -- update project node'
                            # orb.log.debug('    {}'.format(log_msg))
                            source_model = self.sys_tree.source_model
                            root_index = source_model.index(0, 0,
                                                            QModelIndex())
                            project_index = source_model.index(0, 0,
                                                               root_index)
                            source_model.dataChanged.emit(
                                                project_index, project_index)
                            # resize/refresh dashboard columns if necessary
                            self.refresh_dashboard()
            elif isinstance(obj, orb.classes['Product']):
                # orb.log.debug('  - object is a product ...')
                # if it has components, refresh/rebuild
                if getattr(obj, 'components', None):
                    self.refresh_tree_and_dashboard()
                else:
                    idxs = self.sys_tree.object_indexes_in_tree(obj)
                    if idxs:
                        log_msg = 'indexes found in tree, updating ...'
                        orb.log.debug('    {}'.format(log_msg))
                        for idx in idxs:
                            self.sys_tree.source_model.dataChanged.emit(idx,
                                                                        idx)
                        # resize/refresh dashboard columns if necessary
                        self.refresh_dashboard()
                    else:
                        log_msg = 'no indexes for product found in tree.'
                        orb.log.debug('    {}'.format(log_msg))
                        # pass
            state["upd_obj_in_trees_needed"] = ("", "")
        except RuntimeError:
            # sys_tree's C++ object had been deleted -- this is the expected,
            # benign case:  PyQt raises RuntimeError ("wrapped C/C++ object
            # ... has been deleted") when the tree has gone away underneath us
            orb.log.debug('* update_object_in_trees(): sys_tree C++ object '
                          'might have got deleted, cannot update.')
            state["upd_obj_in_trees_needed"] = ("", "")
        except Exception as e:
            # NOTE: this was previously part of a bare "except:", so any bug
            # in the ~60 lines above -- an AttributeError from a renamed
            # attribute, a KeyError, a TypeError -- was reported as "the C++
            # object might have been deleted" and otherwise ignored, which is
            # a very effective way to hide a real defect.  Such failures are
            # now named, at error level so they are not lost in debug output.
            # Still swallowed rather than raised:  this runs inside rpc
            # callbacks, where an exception would break the callback chain.
            orb.log.error(f'* update_object_in_trees() failed: '
                          f'{e.__class__.__name__}: {e}')
            state["upd_obj_in_trees_needed"] = ("", "")

    ### SET UP 'component' mode (product modeler interface)

    def set_product_modeler_interface(self):
        orb.log.debug('* setting product modeler interface')
        # update the model window
        self.set_system_model_window(system=self.product)
        self.top_dock_widget.setFloating(False)
        self.top_dock_widget.setFeatures(QDockWidget.NoDockWidgetFeatures)
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
            ld_widget.setParent(None)
            ld_widget.close()
        self.update_pgxn_obj_panel()
        self.left_dock.setWidget(self.pgxn_obj_panel)
        self.pgxn_obj_panel.show()
        self.left_dock.setVisible(True)

    ### SET UP 'system' mode (system modeler interface)

    def set_system_modeler_interface(self):
        orb.log.debug('* setting system modeler interface')
        # ********************************************************
        # system tree and dashboard
        # ********************************************************
        # refresh_tree_views() creates self.sys_tree if there isn't one
        # (only rebuild tree & dash if called in a project sync)
        self.sys_tree_rebuilt = False
        self.dashboard_rebuilt = False
        self.set_system_model_window()
        self.refresh_tree_views(rebuilding=True)
        self.top_dock_widget.setFeatures(QDockWidget.DockWidgetFloatable)
        self.top_dock_widget.setVisible(True)
        self.top_dock_widget.setWidget(self.dashboard_panel)
        # TODO:  right dock contains libraries
        self.left_dock.setVisible(True)
        self.right_dock.setVisible(True)

    def set_system_model_window(self, system=None):
        orb.log.debug('* setting system model window ...')
        if system:
            # orb.log.debug('  - using specified system {} ...'.format(
                                                                # system.id))
            if state.get('mode') == 'system':
                state['system'][state.get('project')] = system.oid
            elif state.get('mode') == 'component':
                state['product'] = system.oid
            self.system_model_window = ModelWindow(obj=system,
                                                   logo=self.logo)
            self.setCentralWidget(self.system_model_window)
        elif (state.get('mode') == 'system' and
              orb.get((state.get('system') or {}).get(
                                        state.get('project')) or '')):
            system = orb.get(state['system'][state.get('project')])
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
        orb.log.debug('* setting data mode interface ...')
        # hide the top and right dock widgets
        self.top_dock_widget.setVisible(False)
        self.right_dock.setVisible(False)
        # ********************************************************
        # data view:  dataset_list (for selecting datasets)
        # ********************************************************
        self.dataset_list = AutosizingListWidget(parent=self)
        self.dataset_list.currentRowChanged.connect(self.on_dataset_selected)
        # if there is a current left dock widget, destroy it
        ld_widget = self.left_dock.widget()
        if ld_widget:
            ld_widget.setAttribute(Qt.WA_DeleteOnClose)
            ld_widget.setParent(None)
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
            ld_widget.setParent(None)
            ld_widget.close()
            # very important to set None: its C++ object is gone now ...
            self.cname_list = None
        # set current left dock widget to 'cname_list'
        # *********************************************************
        # db view (cname_list corresponds to db tables)
        # *********************************************************
        if not getattr(self, 'cname_list', None):
            self.cname_list = AutosizingListWidget(parent=self)
            self.cname_list.setSizePolicy(QSizePolicy.Fixed,
                                          QSizePolicy.Expanding)
            self.cname_list.currentRowChanged.connect(self.on_cname_selected)
        self.refresh_cname_list()
        self.left_dock.setWidget(self.cname_list)
        self.left_dock.setVisible(True)
        self.cname_list.show()
        state['update db table'] = False

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
        # orb.log.debug('* class selected')
        # orb.log.debug('  - mode: "{}"'.format(self.mode))
        # orb.log.debug('  - selected index: "%i"' % idx)
        # try:
        cur_cname = state.get('current_cname')
        if idx == -1:
            cname = state.get('current_cname', 'HardwareProduct')
        else:
            cname = self.cnames[idx]
        if not (cname == cur_cname):
            state['current_cname'] = str(cname)
            # orb.log.debug('  - class: "%s"' % cname)
            self.set_object_table_for(cname)

    def set_object_table_for(self, cname):
        orb.log.debug('* setting object table for {}'.format(cname))
        if not cname:
            # orb.log.debug('  no class specified, ignoring.')
            return
        objs = list(orb.get_by_type(cname))
        # ObjectTableView is deprecated in favor of FilterPanel
        # tableview = ObjectTableView(objs)
        title_text = get_external_name_plural(cname)
        tableview = FilterPanel(objs, cname=cname, title=title_text)
        if hasattr(tableview, 'ext_filters'):
            tableview.ext_filters.clicked.connect(self.show_ext_filters)
        self.setCentralWidget(tableview)
        self.object_tableview = tableview

    def show_ext_filters(self):
        self.filter_dlg = ProductFilterDialog(self)
        # self.filter_dlg.product_types_selected.connect(
                                # self.on_product_types_selected_signal)
        dispatcher.connect(self.on_product_types_selected,
                           "product types selected")
        self.filter_dlg.show()

    def on_product_types_selected(self, msg='', objs=None):
        orb.log.debug('* pgxn: on_product_types_selected()')
        orb.log.debug('  objs: {}'.format(', '.join([o.id for o in objs])))
        orb.log.debug('  msg: {}'.format(msg))
        obj_table = getattr(self, 'object_tableview', None)
        if obj_table:
            self.msg = msg
            self.product_types = objs
            select_product_types(obj_table, msg=msg,
                                 only_mine=state.get('only_mine'),
                                 product_types=objs)

    def set_new_object_table_view(self, cname=None):
        """
        Handler for dispatcher signal "new object table view pref", sent when
        a column in an ObjectTableView is moved; rebuilds the table.

        Keyword Args:
            cname (str):  class name of the table objects
        """
        # orb.log.debug('* resetting object table view to pref')
        if hasattr(self, 'object_tableview'):
            self.object_tableview.setAttribute(Qt.WA_DeleteOnClose)
            self.object_tableview.setParent(None)
            self.object_tableview.close()
            self.object_tableview = None
        self.set_object_table_for(cname)

    def on_rqts_imported(self):
        # rqts were imported from Excel -- close and reopen rqtmgr
        rqtmgr = getattr(self, 'rqtmgr', None)
        if rqtmgr:
            try:
                rqtmgr.close()
            except:
                # C++ obj was deleted (?)
                pass
        w = self.geometry().width()
        h = self.geometry().height()
        self.rqtmgr = RequirementManager(project=self.project, width=w,
                                         height=h, parent=self)
        self.rqtmgr.show()

    def show_about(self):
        # if app version is provided, use it; otherwise use ours
        version = self.app_version or __version__
        # app_name = config.get('app_name', 'Pangalaxian')
        QMessageBox.about(self, "Some call me...",
            f'<html><h2>{self.app_name} {version}</h2></html>')

    def show_user_guide(self):
        # TODO: search/replace app_name in user guide ...
        # app_name = config.get('app_name', '')
        if self.app_name.startswith('CATTENS'):
            ug_name = 'cattens_user_guide.html'
        else:
            ug_name = 'user_guide.html'
        ug_path = os.path.join(orb.home, 'docs', ug_name)
        ug_url = f'file://{ug_path}'
        webbrowser.open_new(ug_url)

    def show_ref_manual(self):
        # TODO: search/replace app_name in ref manual ...
        # app_name = config.get('app_name', '')
        if self.app_name.startswith('CATTENS'):
            ref_name = 'cattens_reference.html'
        else:
            ref_name = 'reference.html'
        ref_path = os.path.join(orb.home, 'docs', ref_name)
        ref_url = f'file://{ref_path}'
        webbrowser.open_new(ref_url)

    def open_viewer(self, file_path):
        self.cad_viewer = Model3DViewer(file_path)
        self.cad_viewer.show()

    def view_cad_success(self, result):
        orb.log.info('  - view_cad_success; res: "{}"'.format(result))

    def view_cad_error(self, e):
        orb.log.info('  - view_cad_error: {}'.format(e))

    # experimental -- not active (see note above)
    def open_viewer_dialog(self, file_path):
        dlg = Model3dDialog(file_path, parent=self)
        dlg.show()

    def new_project(self):
        """
        Create a new project.  Note that the project id will be checked for
        uniqueness among ids of projects known locally, which may not include
        all projects if the local client is offline and new projects have been
        created elsewhere.  If and when the status of the project is changed to
        "collaborative" (i.e. a Global Admin assigns the project Administrator
        role to the user), the server will check for global uniqueness of the
        project id and will report the problem if it is not unique -- then the
        user can be given the option of changing the project id to a globally
        unique one.
        """
        orb.log.info('* new_project()')
        # Projects and Organizations are always "public"
        view = ['id', 'name', 'description']
        panels = ['main']
        if self.project and not self.project is self.sandbox:
            org_parent = self.project
        else:
            org_parent = orb.get('pgefobjects:PGANA')
        proj = clone('Project', public=True, parent_organization=org_parent)
        if proj:
            pxo = PgxnObject(proj, edit_mode=True, new=True, view=view,
                             panels=panels, modal_mode=True)
            pxo.show()

    def delete_project(self):
        """
        Delete a Project, removing it wherever it is referenced.
        """
        # TODO:  also remove RoleAssignment instances that reference it -- or
        # perhaps refuse to remove it if it has them?
        # TODO:  and remove it from the repository
        orb.log.info('* delete_project()')
        # IMPORTANT: confirm deletion -- there is no "undelete"!
        txt = ('This will permanently delete the project:\n'
               'there is no "undelete"; if you want it back\n'
               'you will have to re-create it ...\n'
               'are you really really sure?')
        confirm_dlg = QMessageBox(QMessageBox.Question, 'Delete?', txt,
                                  QMessageBox.Yes | QMessageBox.No)
        response = confirm_dlg.exec_()
        to_delete_oids = [self.project.oid]
        if response == QMessageBox.Yes:
            # first delete any ProjectSystemUsage relationships
            psus = self.project.systems
            if psus:
                to_delete_oids += [psu.oid for psu in psus]
                orb.delete(psus)
            # if the project owns things, change the owner to 'PGANA'
            # -----------------------------------------------------------------
            # TODO:  create a dialog to go through things one by one and decide
            # whether to delete or save ...
            # -----------------------------------------------------------------
            pgana = orb.get('pgefobjects:PGANA')
            things = orb.search_exact(owner=self.project)
            if things:
                for thing in things:
                    thing.owner = pgana
                orb.db.commit()
                for thing in things:
                    dispatcher.send('modified object', obj=thing)
            orb.delete([self.project])
            if len(self.projects) > 1:
                self.project = self.projects[-1]
                if self.project is self.sandbox:
                    self.delete_project_action.setEnabled(False)
                    self.delete_project_action.setVisible(False)
                # else:
                    # self.delete_project_action.setVisible(True)
            else:
                self.project = self.sandbox
                self.delete_project_action.setEnabled(False)
                self.delete_project_action.setVisible(False)
            if state.get('connected'):
                orb.log.info('  - calling "vger.delete"')
                try:
                    rpc = self.mbus.session.call('vger.delete', to_delete_oids)
                    rpc.addCallback(self.on_rpc_vger_delete_result)
                    rpc.addErrback(self.on_failure)
                except:
                    orb.log.debug('  ** rpc failed (possible loss of transport)')
                    orb.log.debug('     trying to reconnect ...')
                    self.set_bus_state()
        else:
            return

    def delete_test_objects(self):
        orb.log.info('* delete_test_objects()')
        test_objs = orb.search_exact(comment='TEST TEST TEST')
        if test_objs:
            test_obj_oids = [o.oid for o in test_objs]
            orb.delete(test_objs)
            orb.log.info('  test objects deleted.')
            if state.get('connected'):
                orb.log.info('  - calling "vger.delete"')
                try:
                    rpc = self.mbus.session.call('vger.delete', test_obj_oids)
                    rpc.addCallback(self.on_rpc_vger_delete_result)
                    rpc.addErrback(self.on_failure)
                except:
                    txt = 'rpc failed (possible loss of transport)'
                    orb.log.debug(f'  ** {txt}')
                    orb.log.debug('     trying to reconnect ...')
                    self.set_bus_state()
                    return
        else:
            orb.log.info('  no test objects found.')

    def on_display_object_signal(self, obj=None):
        if obj:
            pxo = PgxnObject(obj)
            pxo.show()

    def new_product(self):
        """
        Display a dialog to create a new Product.  (Now simply calls
        new_product_wizard.)
        """
        # orb.log.debug('* new_product()')
        # orb.log.debug('  calling new_product_wizard() ...')
        self.new_product_wizard()

    def on_add_update_model(self, mtype_oid='', fpath='', parms=None):
        """
        Handle "add update model" signal: call rpc to add or update Model and
        RepresentationFile objects related to a specified item, and add
        callbacks to upload_file() to upload associated file(s) file if
        appropriate.
        """
        orb.log.debug('* "add update model" signal received ...')
        if mtype_oid and fpath and parms:
            orb.log.info('  - calling "vger.add_update_model"')
            try:
                rpc = self.mbus.session.call('vger.add_update_model',
                                             mtype_oid=mtype_oid,
                                             fpath=fpath,
                                             parms=parms)
                rpc.addCallback(self.on_model_added)
                rpc.addErrback(self.on_failure)
            except:
                orb.log.debug('  ** rpc failed (possible loss of transport)')
                orb.log.debug('     trying to reconnect ...')
                self.set_bus_state()
                return
        else:
            orb.log.debug('  incomplete signature, rpc not called')
            return

    def on_model_added(self, result):
        """
        Callback for return values of rpc 'vger.add_update_model',

        Args:
            result (tuple): [0] path to the local model file,
                            [1] serialized Model and RepresentationFile
                                instances
        """
        fpath, sobjs = result
        orb.log.debug(f'* on_model_added(fpath={fpath}, sobjs)')
        orb.log.debug('  deserializing Model and RepresentationFile ...')
        objs = deserialize(orb, sobjs)
        orb.log.debug('  deserialized objects:')
        for obj in objs:
            orb.log.debug(f'  {obj.id}')
        oid = ''
        for so in sobjs:
            if so['_cname'] == "RepresentationFile":
                oid = so['oid']
        if oid:
            self.read_and_upload_file(fpath=fpath, rep_file_oid=oid)
        else:
            orb.log.debug('  - RepresentationFile oid not found; no upload.')

    def on_add_update_doc(self, fpath='', parms=None):
        """
        Handle "add update doc" signal: call rpc to add or update Model and
        RepresentationFile objects related to a specified item, and add
        callbacks to upload_file() to upload associated file(s) file if
        appropriate.
        """
        orb.log.debug('* "add update doc" signal received ...')
        if fpath and parms:
            orb.log.info('  - calling "vger.add_update_doc"')
            try:
                rpc = self.mbus.session.call('vger.add_update_doc',
                                             fpath=fpath,
                                             parms=parms)
                rpc.addCallback(self.on_doc_added)
                rpc.addErrback(self.on_failure)
            except:
                orb.log.debug('  ** rpc failed (possible loss of transport)')
                orb.log.debug('     trying to reconnect ...')
                self.set_bus_state()
                return
        else:
            orb.log.debug('  incomplete signature, rpc not called')
            return

    def on_doc_added(self, result):
        """
        Callback for return values of rpc 'vger.add_update_doc',

        Args:
            result (tuple): [0] path to the local doc file,
                            [1] serialized Document, DocumentReference, and
                                RepresentationFile instances
        """
        fpath, sobjs = result
        orb.log.debug(f'* on_doc_added(fpath={fpath}, sobjs)')
        orb.log.debug('* serialized objects:')
        orb.log.debug(f'  {sobjs}')
        orb.log.debug('  deserializing Document, DocumentReference,')
        orb.log.debug('  and RepresentationFile ...')
        objs = deserialize(orb, sobjs)
        orb.log.debug('  deserialized objects:')
        for obj in objs:
            orb.log.debug(f'  {obj.id}')
        oid = ''
        for so in sobjs:
            if so['_cname'] == "RepresentationFile":
                oid = so['oid']
        if oid:
            self.read_and_upload_file(fpath=fpath, rep_file_oid=oid)
        else:
            orb.log.debug('  - RepresentationFile oid not found; no upload.')

    def read_and_upload_file(self, fpath='', rep_file_oid='', chunk_size=None):
        """
        Read a file into a list of chunks and call upload_file() to upload it
        to the server.
        """
        orb.log.info('* read_and_upload_file()')
        fname = os.path.basename(fpath)
        self.chunk_progress = ProgressDialog(title='Reading File',
                                             label=f'reading "{fname}" ...',
                                             parent=self)
        self.chunk_progress.setMaximum(100)
        self.chunk_progress.setAttribute(Qt.WA_DeleteOnClose)
        self.chunks_to_upload = []
        self.fpath_to_upload = fpath
        self.rep_file_oid_to_upload = rep_file_oid
        if fpath:
            worker = Worker(self.chunk_file, fpath, chunk_size)
            # worker.signals.result.connect(self.print_output)
            worker.signals.finished.connect(self.chunking_completed)
            worker.signals.progress.connect(self.update_chunk_progress)
            threadpool.start(worker)
        else:
            orb.log.info('  no file path specified.')

    def chunk_file(self, fpath, chunk_size, progress_signal):
        orb.log.info('* chunk_file()')
        fsize = os.path.getsize(fpath)
        chunk_size = chunk_size or 2**20
        # chunk_size = chunk_size or 2**19
        if chunk_size > fsize // 7:
            chunk_size = fsize // 7
        orb.log.info(f'  using chunk_size {chunk_size}')
        with open(fpath, 'rb') as f:
            for i, chunk in enumerate(iter(partial(f.read, chunk_size), b'')):
                self.chunks_to_upload.append(chunk)
                p = (len(self.chunks_to_upload) * chunk_size * 100) // fsize
                time.sleep(.01)
                progress_signal.emit('', p)
        orb.log.info(f'  yielding {len(self.chunks_to_upload)} chunks.')
        # return chunks
        # return "Done."

    def update_chunk_progress(self, what, n):
        """
        Set max and value for chunk_progress dialog.

        Args:
            n (float): progress as a fraction (<= 1.0)
        """
        orb.log.debug(f'  chunking {n}% done')
        self.chunk_progress.setValue(n)

    def chunking_completed(self):
        orb.log.debug('  chunking thread completed.')
        self.chunk_progress.done(0)
        self.chunk_progress.close()
        # self.chunk_progress.deleteLater()
        self.upload_file()

    def upload_file(self):
        """
        Upload a file from list of chunks, optionally specifying a
        RepresentationFile.oid which if provided will be prepended to the user
        file name to create the vault file name.
        """
        fpath = self.fpath_to_upload
        rep_file_oid = self.rep_file_oid_to_upload
        if fpath and self.chunks_to_upload:
            fname = os.path.basename(fpath)
            orb.log.info(f'* uploading file: "{fname}"')
            if rep_file_oid:
                self.vault_fname = rep_file_oid + '_' + fname
                orb.log.info(f'  using vault file name: "{self.vault_fname}"')
            else:
                self.vault_fname = fname
            # before uploading file, copy it to local vault ...
            shutil.copy(fpath, os.path.join(orb.vault, self.vault_fname))
            orb.log.info('  [copied to local vault]')
            self.uploaded_chunks = 0
            self.failed_chunks = 0
            self.upload_progress = ProgressDialog(title='File Upload',
                                              label=f'uploading "{fname}" ...',
                                              parent=self)
            self.upload_progress.setAttribute(Qt.WA_DeleteOnClose)
            try:
                numchunks = len(self.chunks_to_upload)
                self.upload_progress.setMaximum(numchunks)
                self.upload_progress.setValue(0)
                self.upload_progress.setMinimumDuration(2000)
                orb.log.info(f'  using {numchunks} chunks ...')
                try:
                    rpc = self.mbus.session.call('vger.upload_chunk',
                                                 fname=self.vault_fname,
                                                 seq=0,
                                                 data=self.chunks_to_upload[0])
                    rpc.addCallback(self.on_chunk_upload_success)
                    rpc.addErrback(self.on_chunk_upload_failure)
                except:
                    txt = 'rpc failed (possible loss of transport)'
                    orb.log.debug(f'  ** {txt}')
                    orb.log.debug('     trying to reconnect ...')
                    self.set_bus_state()
                    return
            except:
                message = f'File "{fpath}" could not be uploaded.'
                popup = QMessageBox(QMessageBox.Warning,
                                    "Error in uploading", message,
                                    QMessageBox.Ok, self)
                popup.show()
                return
        else:
            orb.log.info('  file path or list of chunks were missing.')
            return

    def on_chunk_upload_success(self, result):
        orb.log.info(f'  chunk {result} uploaded.')
        self.uploaded_chunks += 1
        self.upload_progress.setValue(self.uploaded_chunks)
        if self.uploaded_chunks < len(self.chunks_to_upload):
            try:
                rpc = self.mbus.session.call('vger.upload_chunk',
                                         fname=self.vault_fname,
                                         seq=self.uploaded_chunks,
                                         data=self.chunks_to_upload[
                                                        self.uploaded_chunks])
                rpc.addCallback(self.on_chunk_upload_success)
                rpc.addErrback(self.on_chunk_upload_failure)
            except:
                orb.log.debug('  ** rpc failed (possible loss of transport)')
                orb.log.debug('     trying to reconnect ...')
                self.set_bus_state()
                return
        else:
            self.on_file_upload_success()

    def on_chunk_upload_failure(self, result):
        orb.log.info(f'  chunk {result} failed.')
        self.failed_chunks += 1

    def on_file_upload_success(self):
        orb.log.info(f'  upload completed in {self.uploaded_chunks} chunks.')
        self.upload_progress.done(0)
        model_window = getattr(self, 'system_model_window', None)
        self.fpath_to_upload = ''
        self.rep_file_oid_to_upload = ''
        self.vault_fname = ''
        self.chunks_to_upload = []
        self.uploaded_chunks = 0
        if model_window:
            try:
                model_window.set_subject()
            except:
                # C++ object got deleted ...
                pass

    def open_doc_file(self, rep_file=None):
        """
        Open a document file corresponding to a RepresentationFile instance,
        downloading the physical file from the server if necessary before
        opening it.

        Args:
            rep_file (RepresentationFile): the RepresentationFile instance

        Keyword Args:
            chunk_size (int):  size of chunks to be used
        """
        vault_fpath = orb.get_vault_fpath(rep_file)
        if os.path.exists(vault_fpath):
            self.open_vault_file(rep_file=rep_file)
        else:
            self.download_file(digital_file=rep_file, open_file=True)

    def open_vault_file(self, rep_file=None):
        """
        Open a document file corresponding to a RepresentationFile instance
        for which the physical file is known to be in the vault.

        Args:
            rep_file (RepresentationFile): the RepresentationFile instance

        Keyword Args:
            chunk_size (int):  size of chunks to be used
        """
        # try to guess file type and select an app
        vault_fpath = orb.get_vault_fpath(rep_file)
        suffix = rep_file.user_file_name.split('.')[-1]
        if suffix in ['doc', 'docx', 'ppt', 'pptx']:
            # try to start Word with file if on Win or Mac ...
            if sys.platform == 'win32':
                try:
                    os.startfile(f'{vault_fpath}')
                except:
                    orb.log.debug('  unable to find app to open file.')
            elif sys.platform == 'darwin':
                try:
                    os.system(f'open -a "Microsoft Word.app" "{vault_fpath}"')
                except:
                    orb.log.debug('  unable to start Word')
        elif suffix in ['xls', 'xlsx', 'csv', 'tsv']:
            # try to start Excel with file if on Win or Mac ...
            if sys.platform == 'win32':
                try:
                    os.startfile(f'{vault_fpath}')
                except:
                    orb.log.debug('  unable to find app to open file.')
            elif sys.platform == 'darwin':
                try:
                    os.system(f'open -a "Microsoft Excel.app" "{vault_fpath}"')
                except:
                    orb.log.debug('  unable to start Excel')
        else:
            # fall-back to browser
            try:
                file_url = f'file:///{vault_fpath}'
                webbrowser.open_new(file_url)
            except:
                orb.log.debug('  browser unable to open file.')

    def download_file(self, digital_file=None, chunk_size=None,
                      open_file=False):
        """
        Download a file corresponding to a DigitalFile instance.

        Args:
            digital_file (DigitalFile): the DigitalFile whose physical file is
                to be downloaded

        Keyword Args:
            chunk_size (int): size of chunks to be used
            open_file (bool): open the file when download is complete
        """
        orb.log.info('* pgxn.download_file()')
        chunk_size = chunk_size or 2**19
        if (digital_file and
            isinstance(digital_file, orb.classes['DigitalFile'])):
            fname = digital_file.user_file_name
            oid = digital_file.oid
            orb.log.info(f'* downloading to vault: "{fname}"')
            orb.log.info(f'  of digital file: "{oid}"')
            self.downloaded_chunks = 0
            self.failed_chunks = 0
            self.download_progress = ProgressDialog(title='File Download',
                                          label=f'downloading "{fname}" ...',
                                          parent=self)
            self.download_progress.setAttribute(Qt.WA_DeleteOnClose)
            try:
                fsize = digital_file.file_size
                numchunks = math.ceil(fsize / chunk_size)
                self.download_progress.setMaximum(numchunks)
                self.download_progress.setValue(0)
                self.download_progress.setMinimumDuration(2000)
                orb.log.info(f'  using {numchunks} chunks ...')
                for i in range(numchunks):
                    try:
                        rpc = self.mbus.session.call('vger.download_chunk',
                                                     digital_file_oid=oid,
                                                     seq=i)
                        rpc.addCallback(self.on_chunk_download_success)
                        rpc.addErrback(self.on_chunk_download_failure)
                        if i == numchunks - 1:
                            if open_file:
                                rpc.addCallback(self.on_download_open_success)
                            else:
                                rpc.addCallback(self.on_file_download_success)
                    except:
                        txt = 'rpc failed (possible loss of transport)'
                        orb.log.debug(f'  ** {txt}')
                        orb.log.debug('     trying to reconnect ...')
                        self.set_bus_state()
                        return
            except:
                message = f'File "{fname}" could not be downloaded.'
                popup = QMessageBox(QMessageBox.Warning,
                                    "Error in downloading", message,
                                    QMessageBox.Ok, self)
                popup.show()
                return
        else:
            orb.log.info('  no DigitalFile instance; returning None.')
            return

    def on_chunk_download_success(self, result):
        oid, seq, data = result
        orb.log.info(f'  chunk {seq} received ...')
        self.downloaded_chunks += 1
        self.download_progress.setValue(self.downloaded_chunks)
        digital_file = orb.get(oid)
        vault_fpath = orb.get_vault_fpath(digital_file)
        with open(vault_fpath, 'ab') as vaultf:
            vaultf.write(data)
        orb.log.info('  appended to vault file.')
        return result

    def on_chunk_download_failure(self, result):
        orb.log.info(f'  chunk {result} failed.')
        self.failed_chunks += 1

    def on_file_download_success(self, result):
        orb.log.info(f'  download done in {self.downloaded_chunks} chunks.')
        self.download_progress.done(0)

    def on_download_open_success(self, result):
        orb.log.info(f'  download done in {self.downloaded_chunks} chunks.')
        self.download_progress.done(0)
        oid, seq, data = result
        digital_file = orb.get(oid)
        self.open_vault_file(rep_file=digital_file)

    def on_new_hardware_clone(self, product=None, objs=None):
        # go to component mode when clone() sends "new hardware clone" signal
        # NOTE: "new object" etc. is unnecessary since a new clone has no
        # connections to any existing systems, etc.
        orb.db.commit()
        self.product = product
        objs = objs or []
        self.component_mode_action.trigger()
        if state.get('connected'):
            # ... which has to be true to enable cloning ...
            orb.log.debug('  calling rpc vger.save() ...')
            orb.log.debug('  [called from on_new_hardware_clone()]')
            orb.log.debug('  - saved objs ids:')
            sobjs = serialize(orb, [product] + objs)
            try:
                rpc = self.mbus.session.call('vger.save', sobjs)
                rpc.addCallback(self.on_vger_save_result)
                rpc.addCallback(self.get_parmz)
                rpc.addErrback(self.on_failure)
            except:
                orb.log.debug('  ** rpc failed (possible loss of transport)')
                orb.log.debug('     trying to reconnect ...')
                self.set_bus_state()

    def new_product_wizard(self):
        """
        Display New Product Wizard, a guided process to create new Product
        instances.
        """
        orb.log.debug('* new_product_wizard')
        wizard = NewProductWizard(parent=self)
        if wizard.exec_() == QDialog.Accepted:
            # orb.log.debug('  New Product Wizard completed successfully.')
            product = orb.get(wizard_state.get('product_oid'))
            if product:
                self.product = product
                if getattr(wizard, 'pgxn_obj', None):
                    wizard.pgxn_obj.setAttribute(Qt.WA_DeleteOnClose)
                    wizard.pgxn_obj.setParent(None)
                    wizard.pgxn_obj.close()
                    wizard.pgxn_obj = None
                # switch to 'component' mode (in case not already there) ...
                self.component_mode_action.trigger()
        else:
            # orb.log.debug('  New Product Wizard cancelled.')
            oid = wizard_state.get('product_oid')
            # if wizard was canceled before saving the new product, oid will be
            # None and no object was created, so there is nothing to delete
            if oid:
                obj = orb.get(oid)
                cname = obj.__class__.__name__
                orb.delete([obj])
                dispatcher.send(signal='deleted object', oid=oid,
                                cname=cname)

    def new_functional_rqt(self):
        wizard = RqtWizard(parent=self, performance=False)
        if wizard.exec_() == QDialog.Accepted:
            # orb.log.debug('* rqt wizard completed.')
            rqt_oid = rqt_wizard_state.get('rqt_oid')
            rqt = orb.get(rqt_oid)
            if rqt and getattr(wizard, 'pgxn_obj', None):
                wizard.pgxn_obj.setAttribute(Qt.WA_DeleteOnClose)
                wizard.pgxn_obj.setParent(None)
                wizard.pgxn_obj.close()
                wizard.pgxn_obj = None
        else:
            # orb.log.debug('* rqt wizard cancelled.')
            if getattr(wizard, 'pgxn_obj', None):
                wizard.pgxn_obj.setAttribute(Qt.WA_DeleteOnClose)
                wizard.pgxn_obj.setParent(None)
                wizard.pgxn_obj.close()
                wizard.pgxn_obj = None

    def new_performance_rqt(self):
        wizard = RqtWizard(parent=self, performance=True)
        if wizard.exec_() == QDialog.Accepted:
            # orb.log.debug('* rqt wizard completed.')
            if getattr(wizard, 'pgxn_obj', None):
                wizard.pgxn_obj.setAttribute(Qt.WA_DeleteOnClose)
                wizard.pgxn_obj.setParent(None)
                wizard.pgxn_obj.close()
                wizard.pgxn_obj = None
        else:
            # orb.log.debug('* rqt wizard cancelled...')
            if getattr(wizard, 'pgxn_obj', None):
                wizard.pgxn_obj.setAttribute(Qt.WA_DeleteOnClose)
                wizard.pgxn_obj.setParent(None)
                wizard.pgxn_obj.close()
                wizard.pgxn_obj = None

    def parameter_library(self):
        dlg = ParmDefsDialog(parent=self)
        dlg.show()

    def de_def_library(self):
        # TODO:  should have 'dimensions' but that will take a schema change
        # view = ['id', 'name', 'range_datatype', 'dimensions', 'description']
        view = ['id', 'name', 'range_datatype', 'description']
        dlg = LibraryDialog('DataElementDefinition', view=view,
                            height=self.geometry().height(),
                            width=(2 * self.geometry().width() // 3),
                            parent=self)
        dlg.show()

    def product_library(self):
        # use the "MAIN_VIEWS" view -- it shows more [SCW 2020-10-20]
        # view = ['id', 'name', 'version', 'iteration', 'product_type',
                # 'description', 'comment']
        dlg = LibraryDialog('HardwareProduct',
                            height=self.geometry().height(),
                            width=self.geometry().width(),
                            parent=self)
        dlg.show()

    def template_library(self):
        view = ['id', 'name', 'description', 'comment']
        dlg = LibraryDialog('Template', view=view,
                            width=(2 * self.geometry().width() // 3),
                            height=self.geometry().height(), parent=self)
        dlg.show()

    def port_type_library(self):
        view = ['id', 'name', 'description']
        dlg = LibraryDialog('PortType', view=view,
                           width=self.geometry().width()//2,
                           height=self.geometry().height(), parent=self)
        dlg.show()

    def port_template_library(self):
        view = ['id', 'name', 'description']
        dlg = LibraryDialog('PortTemplate', view=view,
                           width=self.geometry().width()//2,
                           height=self.geometry().height(), parent=self)
        dlg.show()

    def display_rqts_manager(self):
        w = self.geometry().width()
        h = self.geometry().height()
        self.rqtmgr = RequirementManager(project=self.project, width=w,
                                         height=h, parent=self)
        self.rqtmgr.show()

    def conops_modeler(self):
        win = ConOpsModeler(parent=self)
        win.move(50, 50)
        state['conops'] = True
        win.setAttribute(Qt.WA_DeleteOnClose)
        win.show()

    def step_import(self):
        """
        Import an assembly's structure and component placements from a STEP
        file.
        """
        # imported here rather than at module scope so that start-up does not
        # pull in pythonocc
        from pangalactic.node.step_dialogs import run_step_import
        product = self.product
        if getattr(product, 'oid', '') == 'pgefobjects:TBD':
            # the placeholder is not an assembly to place into
            product = None
        run_step_import(assembly=product, parent=self)

    def sc_42_modeler(self):
        w = 4 * self.geometry().width() / 5
        h = self.geometry().height()
        window = SC42Window(width=w, height=h, parent=self)
        window.show()

    def get_lom_surf_names(self, lom_oid=None):
        orb.log.debug('* calling vger.get_lom_surface_names ...')
        try:
            rpc = self.mbus.session.call('vger.get_lom_surface_names',
                                         lom_oid=lom_oid)
            rpc.addCallback(self.on_vger_glsn_success)
            rpc.addErrback(self.on_vger_glsn_failure)
        except:
            orb.log.debug('  ** rpc failed (possible loss of transport)')
            orb.log.debug('     trying to reconnect ...')
            self.set_bus_state()

    def on_vger_glsn_success(self, result):
        orb.log.debug('* on_vger_glsn_success()')
        orb.log.debug(f'  result: {result}')
        dispatcher.send(signal='got lom surface names', surface_names=result)

    def on_vger_glsn_failure(self, result):
        orb.log.debug('* on_vger_glsn_failure()')

    def get_lom_structure(self, lom_oid=None):
        orb.log.debug('* calling vger.get_lom_structure ...')
        try:
            rpc = self.mbus.session.call('vger.get_lom_structure',
                                         lom_oid=lom_oid)
            rpc.addCallback(self.on_vger_gls_success)
            rpc.addErrback(self.on_vger_gls_failure)
        except:
            orb.log.debug('  ** rpc failed (possible loss of transport)')
            orb.log.debug('     trying to reconnect ...')
            self.set_bus_state()

    def on_vger_gls_success(self, result):
        orb.log.debug('* on_vger_gls_success()')
        orb.log.debug(f'  result: {result}')
        status, lom_oid = result
        if status == 'success':
            lom_model = orb.get(lom_oid)
            dispatcher.send(signal='got lom structure', lom_model=lom_model)

    def on_vger_gls_failure(self, f):
        orb.log.debug('* on_vger_gls_failure()')
        orb.log.debug(f'  {f.get_traceback()}')

    def get_lom_parms(self, lom_oid=None):
        orb.log.debug('* calling vger.get_lom_parms ...')
        try:
            rpc = self.mbus.session.call('vger.get_lom_parms',
                                         lom_oid=lom_oid)
            rpc.addCallback(self.on_vger_glp_success)
            rpc.addErrback(self.on_vger_glp_failure)
        except:
            orb.log.debug('  ** rpc failed (possible loss of transport)')
            orb.log.debug('     trying to reconnect ...')
            self.set_bus_state()

    def on_vger_glp_success(self, result):
        orb.log.debug('* vger.get_lom_parms succeeded ...')
        status, parms = result
        # extremely verbose:
        # orb.log.debug(f'  parms: {parms}')
        if status == 'success':
            dispatcher.send(signal='got lom parms', content=parms)

    def on_vger_glp_failure(self, result):
        orb.log.debug('* on_vger_gls_failure()')

    def product_types_library(self):
        dlg = LibraryDialog('ProductType',
                            width=(2 * self.geometry().width() // 3),
                            height=self.geometry().height(), parent=self)
        dlg.show()

    def export_data_to_file(self):
        pass
        # # TODO:  create a "wizard" dialog with some convenient defaults ...
        # # only open a file dialog if there is no filename yet
        # if not self.filename:
            # self.filename, filters = QFileDialog.getSaveFileName(
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
        orb.log.debug('* export_project_to_file() for {}'.format(
                 getattr(self.project, 'id', None) or '[no current project]'))
        # TODO:  create a "wizard" dialog with some convenient defaults ...
        dtstr = date2str(dtstamp())
        if not state.get('last_path'):
            state['last_path'] = self.user_home
        file_path = os.path.join(state['last_path'],
                                 self.project.id + '-' + dtstr + '.yaml')
        fpath, filters = QFileDialog.getSaveFileName(
                                    self, 'Export Project to File',
                                    file_path)
        if fpath:
            orb.log.debug('  - file selected: "%s"' % fpath)
            fpath = str(fpath)    # QFileDialog fpath is unicode; make str
            state['last_path'] = os.path.dirname(fpath)
            # serialize all the objects relevant to the current project
            project_objects = orb.get_objects_for_project(self.project)
            serialized_objs = serialize(orb, project_objects,
                                        include_components=True,
                                        include_refdata=True)
            f = open(fpath, 'w')
            f.write(yaml.safe_dump(serialized_objs, default_flow_style=False))
            f.close()
            orb.log.debug('    %i project objects written.' % len(
                                                        serialized_objs))
        else:
            return

    def import_objects(self):
        """
        Import a collection of serialized objects from a file (using a
        QFileDialog to select the file).
        """
        orb.log.debug('* import_objects()')
        data = None
        message = ''
        # TODO:  create a "wizard" dialog with some convenient defaults ...
        if not state.get('last_path'):
            state['last_path'] = self.user_home
        # NOTE: can add filter if needed, e.g.: filter="(*.yaml)"
        dialog = QFileDialog(self, 'Open File',
                                       state['last_path'],
                                       "(*.yaml)")
        fpath = ''
        if dialog.exec_():
            fpaths = dialog.selectedFiles()
            if fpaths:
                fpath = fpaths[0]
            dialog.close()
        if fpath:
            orb.log.debug('  file path: {}'.format(fpath))
            if is_binary(fpath):
                message = "File '%s' is not importable." % fpath
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
                message = "File '%s' could not be opened." % fpath
                popup = QMessageBox(QMessageBox.Warning,
                            "Error in file path", message,
                            QMessageBox.Ok, self)
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
                popup = QMessageBox(QMessageBox.Warning,
                            "Error in Data Import", message,
                            QMessageBox.Ok, self)
                popup.show()
                return
            self.load_serialized_objects(sobjs)
            orb.remove_deprecated_data()

    def load_serialized_objects(self, sobjs, importing=False):
        objs = []
        if sobjs:
            byclass = {}
            if importing:
                begin = 'loading'
                end = 'imported'
            else:
                begin = 'syncing'
                end = 'synced'
            for so in sobjs:
                if byclass.get(so['_cname']):
                    byclass[so['_cname']].append(so)
                else:
                    byclass[so['_cname']] = [so]
            if 'Project' in byclass:
                projid = byclass['Project'][0].get('id', '')
                if projid:
                    start_msg = f'{begin} data for {projid} ...'
                    msg = f"success: project {projid} {end}"
                else:
                    start_msg = f'{begin} project data ...'
                    if end == 'synced' and state.get('chunks_to_get'):
                        n = len(state['chunks_to_get'])
                        if n == 1:
                            msg = 'chunk synced -- getting 1 more chunk ...'
                        else:
                            msg = f'chunk synced -- getting {n} more chunks ...'
                    else:
                        msg = f"data has been {end}."
            else:
                start_msg = f'{begin} library data ...'
                if end == 'synced' and state.get('chunks_to_get'):
                    n = len(state['chunks_to_get'])
                    if n == 1:
                        msg = 'chunk synced -- getting 1 more chunk ...'
                    else:
                        msg = f'chunk synced -- getting {n} more chunks ...'
                else:
                    msg = f"data has been {end}."
            self.statusbar.showMessage(start_msg)
            self.pb.show()
            self.pb.setValue(0)
            self.pb.setMaximum(len(sobjs))
            i = 0
            user_is_me = (getattr(self.local_user, 'oid', None) == 'me')
            for cname in DESERIALIZATION_ORDER:
                if cname in byclass:
                    if cname == "Activity":
                        # instances of Activity must all be deserialized
                        # together so "subactivity_of" is handled properly
                        for so in byclass[cname]:
                            # if objs are still owned by 'me' but user has
                            # logged in and has a local_user object ...
                            if so.get('creator') == 'me' and not user_is_me:
                                so['creator'] = self.local_user.oid
                                so['modifier'] = self.local_user.oid
                        n_byclass = len(byclass[cname])
                        objs += deserialize(orb, byclass[cname],
                                            force_no_recompute=True)
                        i += n_byclass
                        self.pb.setValue(i)
                        msg = f'{n_byclass} Activities deserialized'
                        self.statusbar.showMessage(msg)
                    else:
                        for so in byclass[cname]:
                            # if objs are still owned by 'me' but user has
                            # logged in and has a local_user object ...
                            if so.get('creator') == 'me' and not user_is_me:
                                so['creator'] = self.local_user.oid
                                so['modifier'] = self.local_user.oid
                            # n_byclass = len(byclass[cname])
                            objs += deserialize(orb, [so],
                                                force_no_recompute=True)
                            i += 1
                            self.pb.setValue(i)
                            name = so.get('name', '')
                            msg = f'{cname}:  {name}'
                            self.statusbar.showMessage(msg)
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
                        # n_byclass = len(byclass[cname])
                        objs += deserialize(orb, [so],
                                            force_no_recompute=True)
                        i += 1
                        self.pb.setValue(i)
            self.pb.hide()
            if not msg:
                msg = "data has been {}.".format(end)
            self.statusbar.showMessage(msg)
            QApplication.processEvents()
            new_products_psus_or_acus = [obj for obj in objs if isinstance(obj,
                                         (orb.classes['Product'],
                                          orb.classes['Acu'],
                                          orb.classes['ProjectSystemUsage']))]
            if new_products_psus_or_acus:
                if state.get('connected'):
                    state['lib updates needed'] = True
                    # if connected, call get_parmz() ...
                    try:
                        rpc = self.mbus.session.call('vger.get_parmz')
                        rpc.addCallback(self.on_vger_get_parmz_result)
                        rpc.addErrback(self.on_failure)
                    except:
                        txt = 'rpc failed (possible loss of transport)'
                        orb.log.debug(f'  ** {txt}')
                        orb.log.debug('     trying to reconnect ...')
                        self.set_bus_state()
                        return
                else:
                    # if not connected, work in synchronous mode ...
                    recompute_parmz()
                    if self.mode == 'system':
                        for obj in new_products_psus_or_acus:
                            self.update_object_in_trees(obj)
                        # might need to refresh dashboard, e.g. if acu quantities
                        # have changed ...
                        self.refresh_dashboard()
                    if hasattr(self, 'library_widget'):
                        self.library_widget.refresh()
            if importing:
                popup = QMessageBox(QMessageBox.Information,
                            "Project Data Import", msg,
                            QMessageBox.Ok, self)
                popup.show()
            return objs
        else:
            if importing:
                msg = "no data found."
                popup = QMessageBox(QMessageBox.Warning,
                            "no data found.", msg,
                            QMessageBox.Ok, self)
                popup.show()

    def force_load_serialized_objects(self, sobjs, importing=False):
        """
        Used for the result of 'vger.get_objects()' when called by
        'on_force_get_managed_objects_result()'.  This should only be
        used as handler for 'on_force_get_managed_objects_result()' because it
        will force the deserializer to replace any local versions of the
        objects.

        Args:
            data (list):  a list of serialized objects
        """
        objs = []
        if sobjs:
            byclass = {}
            if importing:
                begin = 'loading'
                end = 'imported'
            else:
                begin = 'syncing'
                end = 'synced'
            for so in sobjs:
                if byclass.get(so['_cname']):
                    byclass[so['_cname']].append(so)
                else:
                    byclass[so['_cname']] = [so]
            if 'Project' in byclass:
                projid = byclass['Project'][0].get('id', '')
                if projid:
                    start_msg = f'{begin} data for {projid} ...'
                    msg = f"success: project {projid} {end}"
                else:
                    start_msg = f'{begin} project data ...'
                    if end == 'synced' and state.get('chunks_to_get'):
                        n = len(state['chunks_to_get'])
                        if n == 1:
                            msg = 'chunk synced -- getting 1 more chunk ...'
                        else:
                            msg = f'chunk synced -- getting {n} more chunks ...'
                    else:
                        msg = f"data has been {end}."
            else:
                start_msg = f'{begin} library data ...'
                if end == 'synced' and state.get('chunks_to_get'):
                    n = len(state['chunks_to_get'])
                    if n == 1:
                        msg = 'chunk synced -- getting 1 more chunk ...'
                    else:
                        msg = f'chunk synced -- getting {n} more chunks ...'
                else:
                    msg = f"data has been {end}."
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
                        objs += deserialize(orb, [so], force_no_recompute=True,
                                            force_update=True)
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
                        objs += deserialize(orb, [so], force_no_recompute=True,
                                            force_update=True)
                        i += 1
                        self.pb.setValue(i)
            self.pb.hide()
            if not msg:
                msg = "data has been {}.".format(end)
            self.statusbar.showMessage(msg)
            QApplication.processEvents()
            new_products_psus_or_acus = [obj for obj in objs if isinstance(obj,
                                         (orb.classes['Product'],
                                          orb.classes['Acu'],
                                          orb.classes['ProjectSystemUsage']))]
            if new_products_psus_or_acus:
                if state.get('connected'):
                    # if connected, call get_parmz() ...
                    state['lib updates needed'] = True
                    try:
                        rpc = self.mbus.session.call('vger.get_parmz')
                        rpc.addCallback(self.on_vger_get_parmz_result)
                        rpc.addErrback(self.on_failure)
                    except:
                        txt = 'rpc failed (possible loss of transport)'
                        orb.log.debug(f'  ** {txt}')
                        orb.log.debug('     trying to reconnect ...')
                        self.set_bus_state()
                        return
                else:
                    # if not connected, work in synchronous mode ...
                    recompute_parmz()
                    if hasattr(self, 'library_widget'):
                        self.library_widget.refresh()
                    if self.mode == 'system':
                        for obj in new_products_psus_or_acus:
                            self.update_object_in_trees(obj)
                        # might need to refresh dashboard, e.g. if acu
                        # quantities have changed ...
                        self.refresh_dashboard()
            if importing:
                popup = QMessageBox(QMessageBox.Information,
                            "Project Data Import", msg,
                            QMessageBox.Ok, self)
                popup.show()
        else:
            if importing:
                msg = "no data found."
                popup = QMessageBox(QMessageBox.Warning,
                            "no data found.", msg,
                            QMessageBox.Ok, self)
                popup.show()

    def load_test_objects(self):
        if not state.get('test_objects_loaded'):
            orb.log.debug('* loading test objects ...')
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
            orb.log.debug('* test objects already loaded.')
            self.statusbar.showMessage('Test objects already loaded.')

    def output_mel(self):
        if self.project:
            if getattr(self.project, 'systems', None):
                dtstr = date2str(dtstamp())
                if not state.get('last_path'):
                    state['last_path'] = self.user_home
                suggest_fname = os.path.join(
                                  state['last_path'],
                                  self.project.id + '-MEL-' + dtstr + '.xlsx')
                fpath, _ = QFileDialog.getSaveFileName(
                                self, 'Open File', suggest_fname,
                                "Excel Files (*.xlsx)")
                if fpath:
                    write_mel_xlsx_from_model(self.project, file_path=fpath)
                    orb.log.debug('  file saved.')
                    # try to start Excel with file if on Win or Mac ...
                    if sys.platform == 'win32':
                        try:
                            os.system(f'start excel.exe "{fpath}"')
                        except:
                            orb.log.debug('  could not start Excel')
                    elif sys.platform == 'darwin':
                        try:
                            cmd = f'open -a "Microsoft Excel.app" "{fpath}"'
                            os.system(cmd)
                        except:
                            orb.log.debug('  unable to start Excel')
            else:
                message = "This project has no systems defined."
                popup = QMessageBox(QMessageBox.Warning,
                            "No systems", message,
                            QMessageBox.Ok, self)
                popup.show()
                return
        else:
            message = "You must select a project."
            popup = QMessageBox(QMessageBox.Warning,
                        "No project selected", message,
                        QMessageBox.Ok, self)
            popup.show()
            return

    def import_rqts_from_excel(self):
        start_path = state.get('rqts_file_path') or state.get('last_path')
        start_path = start_path or self.user_home
        fpath, _ = QFileDialog.getOpenFileName(
                                    self, 'Open File', start_path,
                                    "Excel Files (*.xlsx | *.xls)")
        if fpath:
            fpath = str(fpath)    # QFileDialog fpath is unicode; make str
            if not (fpath.endswith('.xls') or fpath.endswith('.xlsx')):
                message = "File '%s' is not an Excel file." % fpath
                popup = QMessageBox(QMessageBox.Warning,
                            "Wrong file type", message,
                            QMessageBox.Ok, self)
                popup.show()
                return
            state['rqts_file_path'] = os.path.dirname(fpath)
            wizard = DataImportWizard(
                            object_type='Requirement',
                            file_path=fpath,
                            height=self.geometry().height(),
                            width=self.geometry().width(),
                            parent=self)
            wizard.exec_()
            orb.log.debug('* import_rqts_from_excel: dialog completed.')
        else:
            return

    def import_products_from_excel(self):
        start_path = (state.get('prod_excel_file_path')
                      or state.get('last_path'))
        start_path = start_path or self.user_home
        fpath, _ = QFileDialog.getOpenFileName(
                                    self, 'Open File', start_path,
                                    "Excel Files (*.xlsx | *.xls)")
        if fpath:
            fpath = str(fpath)    # QFileDialog fpath is unicode; make str
            if not (fpath.endswith('.xls') or fpath.endswith('.xlsx')):
                message = "File '%s' is not an Excel file." % fpath
                popup = QMessageBox(QMessageBox.Warning,
                            "Wrong file type", message,
                            QMessageBox.Ok, self)
                popup.show()
                return
            state['prod_excel_file_path'] = os.path.dirname(fpath)
            wizard = DataImportWizard(
                            object_type='HardwareProduct',
                            file_path=fpath,
                            height=self.geometry().height(),
                            width=self.geometry().width(),
                            parent=self)
            wizard.exec_()
            orb.log.debug('* import_products_from_excel: dialog completed.')
        else:
            return

    def open_3d_model_file(self):
        orb.log.debug('* opening a 3D Model file')
        # NOTE: for demo purposes ... actual function TBD
        if not state.get('last_model_path'):
            state['last_model_path'] = orb.test_data_dir
        fpath, filters = QFileDialog.getOpenFileName(
                            self, 'Open STEP, STL, or brep File',
                            state['last_model_path'],
                            'Model Files (*.stp *.step *.p21 *.stl *.brep)')
        if fpath:
            # TODO: exception handling in case data import fails ...
            # TODO: add an "index" column for sorting, or else figure out how
            # to sort on the left header column ...
            state['last_model_path'] = os.path.dirname(fpath)
            orb.log.info('  - running external viewer ...')
            self.open_viewer(fpath)
            # this was an experiment to see if a dialog did not have the
            # resize-disabling effect ... it was the same, alas.
            # self.open_viewer_dialog(fpath)
        else:
            return

    def set_current_project(self):
        orb.log.debug('* set_current_project')
        # this is a good time to save data elements and parameters ...
        save_data_elementz(orb.home)
        save_parmz(orb.home)
        dlg = ObjectSelectionDialog(self.projects, parent=self)
        dlg.make_popup(self.project_selection)
        # dlg.exec_() -> modal dialog
        if dlg.exec_():
            # dlg.exec_() being true means dlg was "accepted" (OK)
            # refresh project selection combo
            # and set the current project to the new project
            new_oid = dlg.get_oid()
            self.project = orb.get(new_oid)

    def edit_prefs(self):
        orb.log.debug('* edit_prefs()')
        dlg = PrefsDialog(parent=self)
        if dlg.exec_():
            orb.log.debug('  - prefs dialog completed.')

    def on_units_set(self):
        lib_widget = getattr(self, 'library_widget', None)
        if lib_widget:
            lib_widget.refresh()

    def do_admin_stuff(self):
        orb.log.debug('* admin dialog')
        # --------------------------------------------------------------------
        # NOTE: a new AdminDialog is built on each invocation, so the previous
        # one's connections must be removed first. AdminDialog does not set
        # WA_DeleteOnClose and is parented to the main window, so closing it
        # only hides it -- without this teardown every open would leave another
        # live dialog connected to "refresh_admin_tool" and to the "deleted
        # object" dispatcher signal, so a single deletion would run
        # refresh_roles() on every dialog ever opened this session (and each
        # AdminDialog.__init__ also dispatches "get people", firing another
        # rpc).
        # --------------------------------------------------------------------
        old_dlg = getattr(self, 'admin_dlg', None)
        if old_dlg is not None:
            try:
                dispatcher.disconnect(old_dlg.refresh_roles,
                                      'refresh admin tool')
            except Exception:
                # pydispatcher raises if the receiver was not connected
                pass
            try:
                dispatcher.disconnect(old_dlg.refresh_roles, "deleted object")
            except Exception:
                # pydispatcher raises if the receiver was not connected
                pass
            old_dlg.close()
            old_dlg.deleteLater()
        self.admin_dlg = AdminDialog(org=self.project, parent=self)
        # NOTE: AdminDialog only creates "ldap_search_button" when an
        # "ldap_schema" is configured, so it may not exist.  Connecting to it
        # unconditionally raised AttributeError and prevented the admin tool
        # from opening *at all* on any deployment not using LDAP.  This is
        # masked when the wrapper app sets an ldap_schema (gargleblaster
        # does), which is why it went unnoticed.
        ldap_search_button = getattr(self.admin_dlg, 'ldap_search_button',
                                     None)
        if ldap_search_button:
            ldap_search_button.clicked.connect(self.open_person_dlg)
        dispatcher.connect(self.admin_dlg.refresh_roles,
                           'refresh admin tool')
        # ---------------------------------------------------------------------
        # NOTE: self.deleted_object and self.remote_deleted_object are
        # DEPRECATED in favor of dispatcher signal "deleted object"
        # ---------------------------------------------------------------------
        # self.deleted_object.connect(self.admin_dlg.refresh_roles)
        # self.remote_deleted_object.connect(self.admin_dlg.refresh_roles)
        # ---------------------------------------------------------------------
        dispatcher.connect(self.admin_dlg.refresh_roles, "deleted object")
        self.admin_dlg.show()

    def open_person_dlg(self):
        """
        Invoke the PersonSearchDialog.
        """
        self.person_dlg = PersonSearchDialog(parent=self)
        self.person_dlg.search_button.clicked.connect(self.do_person_search)
        self.person_dlg.show()

    def do_person_search(self):
        orb.log.info('* do_person_search()')
        q = {}
        if self.person_dlg.db_mode:
            q = {'known_users': 'result',
                 'id': 'x'}
        for name, w in self.person_dlg.form_widgets.items():
            val = w.get_value()
            if val:
                q[self.person_dlg.schema[name]] = val
        if q.get('id') or q.get('oid') or q.get('email'):
            orb.log.info('  query: {}'.format(str(q)))
            # dispatcher.send('ldap search', query=q)
            if state['connected']:
                try:
                    rpc = self.mbus.session.call('vger.search_ldap', **q)
                    rpc.addCallback(self.on_rpc_ldap_result)
                    rpc.addErrback(self.on_failure)
                except:
                    txt = 'rpc failed (possible loss of transport)'
                    orb.log.debug(f'  ** {txt}')
                    orb.log.debug('     trying to reconnect ...')
                    self.set_bus_state()
                    return
        else:
            ldap_schema = config.get('ldap_schema', {'userid': 'id',
                                                     'email': 'email'})
            names = []
            for ext_name, field in ldap_schema.items():
                if field in ['id', 'email', 'oid']:
                    names.append(ext_name)
            ext_names = ', '.join(names)
            orb.log.info(f'  bad query: must have one of {ext_names}')
            message = f"Query must include one of {ext_names}"
            popup = QMessageBox(QMessageBox.Warning, 'Invalid Query',
                                message, QMessageBox.Ok, self)
            popup.show()

    def on_rpc_ldap_result(self, res):
        """
        Display result of LDAP search and enable selection of person for
        addition to repository for role assignments.

        Keyword Args:
            res (tuple): a tuple containing [0] the ldap search string and [1]
                the result of the search or a test result.
        """
        self.person_dlg.on_search_result(res=res)

    # def compare_items(self):
        # # TODO:  this is just a mock-up for prototyping -- FIXME!
        # if state.get('test_objects_loaded'):
            # objs = orb.search_exact(id='HOG')
            # parms = state.get('dashboard', ['m[CBE]', 'P[CBE]', 'R_D[CBE]'])
            # widget = CompareWidget(objs, parms, parent=self)
            # widget.show()

    def dump_database(self):
        self.statusbar.showMessage('Exporting DB to file ...')
        orb.log.debug('* dump_database')
        dtstr = date2str(dtstamp())
        if not state.get('last_path'):
            state['last_path'] = self.user_home
        suggested_path = os.path.join(state['last_path'], 
                                    'DB-' + dtstr + '.yaml')
        fpath, filters = QFileDialog.getSaveFileName(
                                    self, 'Export DB to File',
                                    suggested_path)
        if fpath:
            orb.log.debug('  - file selected: "%s"' % fpath)
            fpath = str(fpath)    # QFileDialog fpath is unicode; make str
            state['last_path'] = os.path.dirname(fpath)
            orb.dump_db(fpath=fpath)
            self.statusbar.showMessage('All DB objects exported to file.')
        else:
            orb.log.debug('  db export cancelled.')
            self.statusbar.showMessage('DB export cancelled.')
            return

    def gen_keys(self):
        """
        Generate a public/private key pair for use when logging into the
        message bus.  The public key will be submitted to an administrator when
        access is requested.
        """
        self.statusbar.showMessage('Generating public/private key pair ...')
        orb.log.debug('* gen_keys')
        # NOTE: the existence check comes *before* PrivateKey.generate(), so an
        # aborted call does no work.  It used to generate a key pair and then
        # discard it every time the user hit this with a key already in place.
        if os.path.exists(self.key_path):
            # if private key already exists, warn user
            orb.log.debug('  - private key already exists, warning user.')
            message = '<html><font color="red">A private key'
            message += f' (<b>{self.key_path}</b>) already exists.</font><br>'
            message += ' If you want to generate a new one, you must first'
            message += ' delete the current private key; then after generating'
            message += ' a new public/private key pair, send the new'
            message += ' <font color="green"><b>public.key</b></font> file'
            message += ' to an administrator and request that it be used to'
            message += ' replace your current public key.'
            # NOTE: the result is deliberately not inspected.  "Ok" is the only
            # button, and Qt also returns it for Esc and for closing the
            # window, so the old "if response == QMessageBox.Ok: return" was
            # unconditional -- it read as a choice that was never offered.
            QMessageBox(QMessageBox.Warning, "Private Key Exists ...",
                        message, QMessageBox.Ok, self).exec_()
            return
        privkey = PrivateKey.generate()
        # NOTE: create the file already-restricted rather than chmod-ing after
        # the write.  The previous "open(path, 'wb') ... chmod(0o400)" left the
        # private key on disk at the process umask in between -- measured at
        # 0o664, i.e. world-readable -- and left it that way permanently if the
        # write raised, because the chmod never ran.  O_EXCL additionally
        # refuses to clobber a key that appeared since the check above.
        #
        # 0o600-then-chmod rather than creating 0o400 directly: both close the
        # exposure window identically, but this does not depend on being able
        # to write to a file created read-only, which is the part that differs
        # on Windows -- and this app ships a Windows build.
        fd = os.open(self.key_path,
                     os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as f:
            f.write(privkey.encode())
        os.chmod(self.key_path, 0o400)
        sk = cryptosign.CryptosignKey.from_file(self.key_path)
        public_key_path = os.path.join(orb.home, 'public.key')
        # NOTE: no trailing newline, and this must stay that way.  vger stores
        # this string verbatim in principals.db and the authenticator matches
        # it against the bare hex key from the WAMP handshake, so a newline
        # here would silently prevent login for every app-generated key.  See
        # admin_tool_review.md #4, which is the same failure arriving by the
        # other route (a key that picked up a newline in transit).
        with open(public_key_path, 'w') as f:
            f.write(sk.public_key())
        orb.log.debug('  - keys generated; "public.key" is in cattens_home.')
        msg = '<html>The <font color="green"><b>public key</b></font> file'
        msg += f' is here: <br><b>{public_key_path}</b><br>'
        msg += '-- send it to the administrator with your request for access.'
        popup = QMessageBox(QMessageBox.Information,
                            "Public key generated.", msg,
                            QMessageBox.Ok, self)
        popup.show()
        self.statusbar.showMessage(
            f'public key file is here: {public_key_path}.')

    def closeEvent(self, event):
        # things to do when window is closed
        # TODO:  save more MainWindow state (see p. 190 in PyQt book)
        state['mode'] = str(self.mode)
        state['width'] = self.geometry().width()
        state['height'] = self.geometry().height()
        if getattr(self, 'library_widget', None):
            # ensure that final col moves in hw lib are saved
            hw_lib = self.library_widget.libraries.get('HardwareProduct')
            if hw_lib and hw_lib.col_moved_view:
                prefs['hw_lib_view'] = hw_lib.col_moved_view
        self.statusbar.showMessage('* saving data elements and parameters...')
        # NOTE: save_caches saves the cache files *and* creates backup copies
        orb.save_caches()
        if orb.db.dirty:
            orb.db.commit()
        mods = False
        if mods:
            self.statusbar.showMessage('* backing up db...')
            orb.dump_db()
            self.statusbar.showMessage('* db backed up.')
        if state.get('connected'):
            self.mbus.session = None
            self.mbus = None
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
    # clear 'synced_projects' and 'network_warning_displayed'
    state['synced_projects'] = []
    state['network_warning_displayed'] = False
    write_state(os.path.join(orb.home, 'state'))
    write_trash(os.path.join(orb.home, 'trash'))

def run(app_base_name='', app_version='', app_home='', release_mode='',
        auto=False, host=None, port=None, use_tls=True, auth_method='crypto',
        key_file_name=None, cert=False, splash_image=None, console=False,
        debug=False):
    """
    app_base_name (str): base name of the app; default: "Pangalaxian";
                         release_mode will be appended if "dev" or "test"
    app_version (str):   version of the app (if any)
    app_home (str):      specified name of app home directory
                         default: empty str
    release_mode (str):  release status (production, dev, or test)
                         default: production (empty string)
    auto (bool):         whether to automatically connect to the repository at
                         startup (default: False)
    host (str):          the host to connect to [default: localhost])
    port (str):          the port to connect to [default: 8080])
    use_tls (bool):      use tls to connect to message bus
    auth_method (str):   authentication method ("cryptosign" or "ticket")
    key_file_name (str): name of file holding the user's private key
    cert (bool):         if True, the server uses a self-signed cert
    splash_image (str):  name of the splash image file
    console (bool):      send log messages to stdout (default: False)
    debug (bool):        set logging to debug level (default: False)
    """
    app = QApplication(sys.argv)
    app_base_name = app_base_name or 'Pangalaxian'
    # app.setStyleSheet('QToolTip { border: 2px solid;}')
    # app.setStyleSheet("QToolTip { color: #ffffff; "
                      # "background-color: #2a82da; "
                      # "border: 1px solid white; }")
    app.setStyleSheet("QToolTip { color: blue; "
                      "background-color: white; "
                      "border: 1px solid black; }")
    styles = QStyleFactory.keys()
    if 'Fusion' in styles:
        app.setStyle(QStyleFactory.create('Fusion'))
    screen_resolution = app.desktop().screenGeometry()
    splash_image = splash_image or 'pangalactic_logo_splash.png'
    #--------------------------------------------------------------------------
    # set up path to "home" based on app_home and user "home" ...
    # [1] for the dir name:
    #     [a] use app_home if not empty + release_mode
    #     [b] use lower case app_base_name if not empty + release_mode
    #     [c] use "pangalaxian_home" + release_mode
    # [2] for the dir path:
    # determine the user home/profile dir path based on platform and append the
    # dir name to that.
    #--------------------------------------------------------------------------
    app_home_path = ''
    # if release_mode is empty str or "production", release_suffix is empty str
    release_suffix = ''
    if release_mode in ["dev", "test"]:
        release_suffix = '_' + release_mode
    if not app_home:
        app_home = app_base_name.lower() + '_home' + release_suffix
    # NOTE: the platform branch that used to be inlined here now lives in
    # p.core.get_user_home(), shared with orb.start() and gargleblaster
    user_home = get_user_home()
    if user_home:
        app_home_path = os.path.join(user_home, app_home)
    # if all else fails, create app_home inside the current directory --
    # not desirable because app_home holds user data that needs to
    # persist when a new version of the client is installed, which may
    # destroy the directory.
    if not app_home_path:
        app_home_path = os.path.join(os.getcwd(), app_home)
    if not os.path.exists(app_home_path):
        os.makedirs(app_home_path, mode=0o755)
    home = app_home_path
    # Create and display the splash screen
    # * if it exists, use image inside home 'images' subdir
    images_dir = os.path.join(home, 'images')
    std_img_path = os.path.join(images_dir, splash_image)
    splash_path = std_img_path
    try:
        images_mod_path = pangalactic.node.images.__path__[0]
    except:
        images_mod_path = ''
    if os.path.exists(splash_image):
        # if img is in current dir, use it ...
        splash_path = splash_image
    elif (images_mod_path and os.path.exists(images_mod_path)
          and os.path.exists(os.path.join(
                            images_mod_path, 'pangalactic_logo_splash.png'))):
        # if splash image not provided and not in "std" path (home), use the
        # splash image from the installed "images" module
        splash_path = os.path.join(images_mod_path,
                                   'pangalactic_logo_splash.png')
    else:
        splash_path = ''
    x = screen_resolution.width() // 2
    y = screen_resolution.height() // 2
    # BEGIN importing and installing the reactor
    import qt5reactor
    qt5reactor.install()
    from twisted.internet import reactor
    # from twisted.internet.defer import setDebugging
    # END importing and installing the reactor
    if splash_path:
        splash_pix = QPixmap(splash_path)
        splash = SplashScreen(splash_pix, center_point=QPoint(x, y))
        splash.show()
        splash.showMessage('Starting ...')
        # processEvents() is needed for image to load
        QApplication.processEvents()
        # TODO:  updates to showMessage() using thread/slot+signal
        main = Main(home=home, app_base_name=app_base_name,
                    app_version=app_version, auto=auto, host=host, port=port,
                    use_tls=use_tls, auth_method=auth_method,
                    key_file_name=key_file_name, cert=cert, reactor=reactor,
                    console=console, debug=debug)
        splash.finish(main)
    else:
        main = Main(home=home, app_base_name=app_base_name,
                    app_version=app_version, auto=auto, host=host, port=port,
                    use_tls=use_tls, auth_method=auth_method,
                    key_file_name=key_file_name, cert=cert, reactor=reactor,
                    console=console, debug=debug)
    main.setContextMenuPolicy(Qt.PreventContextMenu)
    main.show()
    if auto or prefs.get('auto'):
        main.auto_connect()
    atexit.register(cleanup_and_save)
    # run the reactor after creating the main window but before starting the
    # app -- using "runReturn" instead of reactor.run() here to enable the use
    # of app.exec_
    reactor.runReturn()
    # this should enable tracebacks instead of "Unhandled error in Deferred"
    # NOTE: these tracebacks are mostly relevant to protocol debugging
    # setDebugging(True)

    sys.exit(app.exec_())

    # NOTE: with the addition of pyqtgraph, segfaults began to happen at exit
    # on Windows and randomly on OSX.  The following app.exec_ idiom was
    # suggested on the pyqtgraph email list ... but it doesn't help. :(
    # app.exec_()
    # app.deleteLater()
    # sys.exit()

    # **NOTE**
    # Since both PyQt and Twisted are based on event loops (in app.exec_() and
    # reactor.run(), respectively), one of them should drive the other. The
    # Twisted way is to let the reactor drive (hence we call
    # reactor.runReturn() first). Inside its implementation, qt5reactor takes
    # care of running an event loop in a way that dispatches events to both
    # Twisted and PyQt.


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', dest='app_home', type=str,
                        default='',
                        help='name of application home directory '
                             '[defaults to "pangalaxian_home")')
    parser.add_argument('--host', dest='host', type=str,
                        default='localhost',
                        help='the host to connect to [default: "localhost"]')
    parser.add_argument('--port', dest='port', type=int,
                        default=8080,
                        help='the port to connect to [default: 8080]')
    # DO NOT ever use an unencrypted transport!
    # parser.add_argument('-u', '--unencrypted', action='store_true',
                        # help='use unencrypted transport (no tls)')
    parser.add_argument('--auto', action='store_true',
                        help='debug mode (verbose logging)')
    parser.add_argument('--auth', dest='auth', type=str, default='cryptosign',
                        help='authentication method: "ticket" or "cryptosign" '
                             '[default: "cryptosign" (pubkey auth)]')
    parser.add_argument('--key', action='store_true',
                        help="name of file holding the user's private key")
    parser.add_argument('--cert', dest='cert', action="store_true",
                        help='the server uses a self-signed certificate')
    parser.add_argument('--name', dest='app_name', type=str,
                        default='Pangalaxian',
                        help='application name, default: "Pangalaxian"')
    parser.add_argument('--version', dest='version', type=str,
                        default='',
                        help='app version string, default: ""')
    parser.add_argument('--release_mode', dest='release_mode', type=str,
                        default='',
                        help='release mode '
                        '(possible values: "production", "dev", or "test") '
                        'default: "production"')
    parser.add_argument('--splash_image', dest='splash_image', type=str,
                        default='pangalactic_logo_splash.png',
                        help='name of an image file to use as a splash image '
                             '[default: pangalactic_logo_splash.png)')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='debug mode (verbose logging)')
    parser.add_argument('-c', '--console', action='store_true',
                        help='send log msgs to stdout (default: False)')
    options = parser.parse_args()
    # DO NOT ever use an unencrypted transport!
    # tls = not options.unencrypted
    run(app_base_name=options.app_name, app_version=options.version,
        app_home=options.app_home, release_mode=options.release_mode,
        auto=options.auto, host=options.host, port=options.port,
        cert=options.cert, debug=options.debug, console=options.console,
        auth_method=options.auth, key_file_name=options.key,
        splash_image=options.splash_image)

