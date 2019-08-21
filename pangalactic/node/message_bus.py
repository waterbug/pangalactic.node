from twisted.internet.defer import inlineCallbacks
from autobahn.twisted.wamp import (Application, ApplicationRunner,
                                   _ApplicationSession)

# for testing
TICKETS = {
    u'user1': u'123secret',
    u'user2': u'456secret',
    u'systems_engineer': u'1234',
    u'lead_engineer': u'1234',
    u'acs_engineer': u'1234',
    u'power_engineer': u'1234',
    u'flight_dynamics_engineer': u'1234',
}


class PgxnAuthSession(_ApplicationSession):

    @inlineCallbacks
    def onConnect(self):
        """
        Implements :func:`autobahn.wamp.interfaces.ISession.onConnect`
        """
        yield self.app._fire_signal('onconnect')
        realm = self.config.realm
        self.log.info("  onConnect:")
        self.log.info("  + realm set to: %s" % realm)
        authid = self.config.extra[u'authid']
        self.log.info("  + session connected.")
        self.log.info("  + joining realm <{}> under authid <{}>".format(
                                realm if realm else 'not specified', authid))
        self.join(realm, [u'ticket'], authid)

    def onChallenge(self, challenge):
        self.log.info("  + challenge received: {}".format(challenge))
        if challenge.method == u'ticket':
            return self.config.extra['passwd']
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


class NullLogger(object):
    info = debug = lambda x: None


class PgxnMessageBus(Application):
    def __init__(self, prefix=None):
        Application.__init__(self, prefix=prefix)
        self.extra = {}
        self.log = NullLogger()

    def set_authid(self, authid):
        self.extra[u'authid'] = authid

    def set_passwd(self, passwd):
        self.extra[u'passwd'] = passwd

    def set_logger(self, logger):
        if logger:
            self.log = logger

    # @self.signal
    # def get_result(self, result):
        # return result

    def __call__(self, config):
        config.extra = self.extra
        # assert(self.session is None)
        if self.session is not None:
            self.session = None
        self.session = PgxnAuthSession(config, self)
        return self.session

    def run(self, url=u"ws://localhost:8080/ws", realm=u"realm1",
            start_reactor=True, ssl=None):
        self.runner = ApplicationRunner(url, realm, ssl=ssl)
        return self.runner.run(self.__call__, start_reactor,
                               auto_reconnect=True)


if __name__ == '__main__':

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--authid', dest='authid', type=str,
                        default=u'user1',
                        help='The authid to connect under (required)')
    parser.add_argument('--realm', dest='realm', type=str,
                        default=None,
                        help='The realm to join. If not provided, let the '
                        'router auto-choose the realm (default).')
    parser.add_argument('--url', dest='url', type=str,
                        default=u'ws://localhost:8080/ws',
                        help='The router URL '
                             '(default: ws://localhost:8080/ws).')
    options = parser.parse_args()

    print("Connecting to {}: realm={}, authid={}".format(options.url,
                                                         options.realm,
                                                         options.authid))
    app = PgxnMessageBus(options.authid)
    app.run(options.url, realm=options.realm)

