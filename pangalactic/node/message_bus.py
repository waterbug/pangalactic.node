# -*- coding: utf-8 -*-
import txaio, websocket
txaio.use_twisted()

from twisted.internet.defer import inlineCallbacks
from autobahn import wamp
from autobahn.twisted.wamp import (Application, ApplicationRunner,
                                   _ApplicationSession)
from autobahn.wamp import cryptosign


def reachable(url):
    # NOTE: this only works for non-tls connections
    url = url or 'ws://localhost:8080/ws'
    websocket.enableTrace(True)
    s = websocket.WebSocket()
    try:
        s.connect(url)
        s.recv()   # this will contain header info
        s.close()
    except websocket.WebSocketConnectionClosedException:
        return True
    except:
        return False


class PgxnAuthSession(_ApplicationSession):

    def __init__(self, config, app, auth_method='cryptosign'):
        _ApplicationSession.__init__(self, config, app)
        self.auth_method = auth_method
        self.log.info(f'* auth_method set to: "{self.auth_method}"')
        if self.auth_method == 'cryptosign':
            # load the client private key (raw format)
            try:
                self._key = cryptosign.CryptosignKey.from_file(
                                                self.config.extra['key_path'])
                self.log.info("public key loaded: {}".format(
                              self._key.public_key()))
            except Exception as e:
                self.log.error("failed to load private key: {log_failure}",
                               log_failure=e)

    @inlineCallbacks
    def onConnect(self):
        """
        Implements :func:`autobahn.wamp.interfaces.ISession.onConnect`
        """
        yield self.app._fire_signal('onconnect')
        realm = self.config.realm or 'not specified'
        self.log.info("  onConnect:")
        self.log.info("  + session connected.")
        self.log.info(f'  + realm set to: "{realm}"')
        if self.auth_method == 'ticket':
            authid = self.config.extra['authid']
            self.log.info(f"  + joining realm <{realm}> as authid <{authid}>")
            self.join(realm,
                      authmethods=['ticket'],
                      authid=authid)
        elif self.auth_method == 'cryptosign':
            self.log.info("  + joining realm <{realm}> using cryptosign ...")
            extra = {'pubkey': self._key.public_key()}
            self.join(realm,
                      authmethods=['cryptosign'],
                      authextra=extra)

    def onChallenge(self, challenge):
        self.log.info("  + challenge received: {}".format(challenge))
        if challenge.method == 'ticket':
            return self.config.extra['passwd']
        elif challenge.method == 'cryptosign':
            self.log.info("authentication challenge received: {challenge}",
                          challenge=challenge)
            # sign challenge with private key.
            signed_challenge = self._key.sign_challenge(challenge)
            # return signed challenge for verification
            return signed_challenge
        else:
            raise Exception("Invalid authmethod {}".format(challenge.method))

    @inlineCallbacks
    def onJoin(self, details):
        """
        Implements :func:`autobahn.wamp.interfaces.ISession.onJoin`
        """
        for uri, proc in self.app._procs:
            yield self.register(proc, uri)

        for uri, handler in self.app._handlers:
            yield self.subscribe(handler, uri)

        self.details = details
        yield self.app._fire_signal('onjoined')
        self.log.info("  onJoin: session joined: {}".format(details))

    @inlineCallbacks
    def onLeave(self, details):
        """
        Implements :func:`autobahn.wamp.interfaces.ISession.onLeave`
        """
        yield self.app._fire_signal('onleave')
        self.log.info("  + session left: {}".format(details))
        self.disconnect()

    @inlineCallbacks
    def onDisconnect(self):
        """
        Implements :func:`autobahn.wamp.interfaces.ISession.onDisconnect`
        """
        yield self.app._fire_signal('ondisconnect')
        self.log.info("  + session disconnected")

    def send_rpc(self, rpc, *args, **kw):
        """
        Send a remote procedure call.  (This method is implemented solely for
        testing purposes to support the p.test.gui_client with a generic rpc.)
        """
        self.log.info('  + rpc "%s" sent ...' % rpc)
        return self.call(rpc, *args, **kw)

    # leave() copied from autobahn.wamp.protocol._ApplicationSession and
    # modified to avoid sending "Goodbye" message if no transport, to avoid a
    # Disconnected("Attempt to send on a closed protocol") exception ...
    def leave(self, reason: str | None = None, message: str | None = None):
        """
        Implements :meth:`autobahn.wamp.interfaces.ISession.leave`
        """
        if not self._session_id:
            self.log.warn("session is not joined on a realm - no session to leave")
            return

        if not self._goodbye_sent:
            if not reason:
                reason = "wamp.close.normal"
            msg = wamp.message.Goodbye(reason=reason, message=message)
            if not (self._transport is None or self._transport.is_closed):
                self._transport.send(msg)
            self._goodbye_sent = True
        else:
            self.log.warn(
                "session was already requested to leave - not sending GOODBYE again"
            )

        is_closed = self._transport is None or self._transport.is_closed

        return is_closed


class NullLogger(object):
    info = debug = lambda x: None


class PgxnRunner(ApplicationRunner):
    pass


class PgxnMessageBus(Application):

    def __init__(self, prefix=None):
        Application.__init__(self, prefix=prefix)
        self.extra = {}
        self.log = NullLogger()

    def set_authid(self, authid):
        self.extra['authid'] = authid

    def set_passwd(self, passwd):
        self.extra['passwd'] = passwd

    def set_key_path(self, key_path):
        self.extra['key_path'] = key_path

    def set_logger(self, logger):
        if logger:
            self.log = logger

    # @self.signal
    # def get_result(self, result):
        # return result

    def __call__(self, config):
        config.extra = self.extra
        if self.session is not None:
            self.session = None
        self.session = PgxnAuthSession(config, self, self.auth_method)
        return self.session

    def run(self, url="ws://localhost:8080/ws", realm="realm1",
            auth_method='cryptosign', start_reactor=True, ssl=None,
            auto_reconnect=True, max_retries=-1, initial_retry_delay=1):
        """
        Run the message bus with specified arguments.

        Keyword args:
            url (str): url of the crossbar host
            realm (str): realm to use on crossbar
            auth_method (str): WAMP auth method ("cryptosign" or "ticket")
            start_reactor (bool): start the twisted reactor
            ssl (dict): server cert info for TLS connection
            auto_reconnect (bool): if True, twisted service does auto-reconnect
            max_retries (int): -1 -> infinite retries
            initial_retry_delay (int): delay before retrying
        """
        self.auth_method = auth_method
        self.runner = ApplicationRunner(url, realm, ssl=ssl,
                                websocket_options={'maxMessagePayloadSize': 0})
        return self.runner.run(self.__call__, start_reactor,
                               auto_reconnect=True)

