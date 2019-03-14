## NOTES on louie ##

* define orb method 'register_signal' using dispatcher.connect():
  (NOTE: in old pangalactic, it was 'orb.register')

    def register_signal(self, receiver, signal, **kw):
        dispatcher.connect(receiver, signal, **kw)

* register a signal with a receiver (done in __init__()), e.g.:
  (new syntax)

        self.register_signal(self.addPgxnObj, 'pgxnobj spawned')
        self.register_signal(self.delPgxnObj, 'pgxnobj killed')

  ... where 'addPgxnObj' and 'delPgxnObj' were instance methods on the orb:
    #######################################################################
    def addPgxnObj(self, pgxnobj=None):
        """
        When a C{PanGalaxianObject} has been spawned, add its C{PgefObject}'s
        oid to the 'pgxnobjs' dict.
        """
        self.pgxnobjs[pgxnobj.obj.oid] = pgxnobj

    def delPgxnObj(self, pgxnobj=None):
        """
        When a C{PanGalaxianObject} has been killed, remove its C{PgefObject}'s
        oid from the 'pgxnobjs' dict.
        """
        del self.pgxnobjs[pgxnobj.obj.oid]
    #######################################################################

* use dispatcher.send() to set up senders of the signal, e.g.:

    # In PanGalaxianObject (editor), when started up:

        dispatcher.send(signal='pgxnobj spawned', pgxnobj=self)

    # In uberorb:

    def getAppOntologies(self, home=''):
        """
        Add application ontologies from models/owl to the core ontology.

        @param home:  directory in which the 'models/owl' directory will be
            found.  Typically this should be PanGalaxian's home directory path.
        @type  home:  C{str}
        """
        self.importApplicationOntologies(home)
        self.log.info('dispatching signal "interfaces updated"')
        dispatcher.send(signal='interfaces updated')

----------------------------------------------------------------------------
NOTES AND EXAMPLE from old version of pangalaxian ...

        orb.register(self.onLogin, 'login')
        orb.register(self.onLogout, 'logout')
        # to avoid creating loops:
        #   * 'objects saved' should be used *only* for local saves
        # FIXME:  should have kw arg 'objs'
        # FIXME:  this message should have its own, more specific, callback ...
        # instead of 'refreshView' it should be 'updateObjects', and it
        # should only update the display widgets for the specified objects,
        # rather than resetting the entire notebook, etc.
        orb.register(self.refreshView, 'objects saved')
        #   * 'refresh views' is used (so far) only by orb.deleteObjectsFromCache
        #     + it *only* triggers self.refreshView
        # FIXME:  should be 'objects deleted' and should have kw arg 'objs', and
        # should also be bound to 'updateObjects'
        orb.register(self.refreshView, 'refresh views')
        #   * 'updates received' should be used *only* for remote interactions
        #     + in addition to triggering self.refreshView,
        #       it triggers all PanGalaxianObjects to resync()
        #     + it's dispatched by the following UberORB methods:
        #       getObject, getObjectsFromServer, commit, getNamespaces, and
        #       getAcusByAssemblyOid.
        # FIXME:  'updates received' should also have kw arg 'objs', and should
        # also be bound to 'updateObjects'
        orb.register(self.refreshView, 'updates received')
        orb.register(self.updateProjectWidget, 'update projects')

----------------------------------------------------------------------------
EXAMPLE:  update() method in old version of uberorb ...

    def update(self, context):
        """
        Retrieve from a repository the latest versions of all Versionable
        objects in the current context (usually, a project) for which a
        checked-out version exists in the local cache.  Also, get any
        C{Relationship} instances in which any of the retrieved objects are the
        C{parent}.

        @param context:  the name (id) of the context whose objects are to be
            updated
        @type  context:  C{str}

        @return:  a list of all the HEAD C{VersionedObject} instances on the
            project which don't have local instances, plus any C{Relationship}
            instances in which any of the retrieved objects are the C{parent}
        @rtype:   C{list}
        """
        objs = []
        self.log.info(' - update()')
        if state['repo']:
            if self.cache:
                self.log.info('    * getting cached obj oids ...')
                oids = [o.oid for o in
                        self.searchLocalObjects(cm_authority=context)]
                self.log.info('      %s oids found.' % str(len(oids)))
            if oids:
                params = [('cm_authority', '=', context),
                          ('oid', 'not in', oids),
                          ('is_head', '=', True)]
            else:
                # (server does not like a 'not in' search with an empty tuple)
                params = [('cm_authority', '=', context),
                          ('is_head', '=', True)]
            objs = self.search('VersionableProduct', refs=True, subtypes=True,
                               params=params)
        if objs:
            oids = [obj.oid for obj in objs]
            self.log.info('    * total objects found: %s' % len(objs))
            self.log.info('      ... now looking for Relationship instances ...')
            # get Relationships in which any found objects are the parent
            # and add them to the cache (ZODB) and self.assy_maps
            if state['repo']:
                schema_name = 'Relationship'
                params = [('parent', 'in', oids)]
                rels = self.search(schema_name, subtypes=True, params=params)
                if rels:
                    acus = [x for x in rels if x._schema.__name__ == 'Acu']
                    parent_oids = set([a.parent for a in acus])
                    assy_map = dict(
                                [(oid, [x for x in acus if x.parent == oid])
                                 for oid in parent_oids])
                    self.assy_maps.update(assy_map)
                    self.log.info('      found %i.' % len(rels))
                else:
                    # pass
                    self.log.info('      none found.')
            self.log.info('dispatching signal "updates received"')
            dispatcher.send(signal='updates received')
        else:
            self.log.info('    * no updates found.')
        return objs

