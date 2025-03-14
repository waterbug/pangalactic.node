#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Message bus interface module to the pangalactic.vger repository service.
"""
import argparse, os, sys

# pydispatcher
from pydispatch import dispatcher

# twisted
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
# from pangalactic.core.utils.datetimes import dtstamp
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


class Main:
    """
    App for mbif.
    """
    def __init__(self, host, port, cert, reactor=None, console=False,
                 output=None, parent=None):
        self.console = console
        if console:
            self.log = print
        else:
            self.log = orb.log.debug
        self.host = host
        self.port = port
        self.cert = cert
        self.reactor = reactor
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
    parser.add_argument('--console', dest='console', action="store_true",
                        help='send log msgs to stdout [default: no]')
    options = parser.parse_args()
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
    from twisted.internet import reactor
    main = Main(options.host, options.port, console=options.console,
                cert=options.cert, output=options.output, reactor=reactor)
    reactor.run()

