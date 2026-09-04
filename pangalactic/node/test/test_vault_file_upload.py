# -*- coding: utf-8 -*-
"""
Tests for the client half of "a RepresentationFile syncs with its bytes":
the upload queue, and the ordering that keeps a file object from reaching the
repository before the file does.

The methods under test are ordinary python -- they queue work, answer
Deferreds and call rpcs -- so they are borrowed from `Main` and run against a
stand-in `self` that has only the few attributes they touch.  A real Main
cannot be made without building a whole main window (PyQt refuses attribute
access on an instance whose C++ constructor never ran), and the point is to
test the real functions rather than a copy of them:  the same reasoning as
the vger rpc harness, which borrows the rpcs out of onJoin().

Run headless with QT_QPA_PLATFORM=offscreen.
"""
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from twisted.internet.defer import Deferred

# set the orb
import pangalactic.core.set_uberorb

from pangalactic.core import orb, state
from pangalactic.core.serializers import deserialize
from pangalactic.core.test.utils import create_test_users, create_test_project

HOME = 'vault_upload_test'
orb.start(home=HOME)
deserialize(orb, create_test_users() + create_test_project())

from pangalactic.core.digital_files import (new_doc_with_file,
                                            new_model_with_file,
                                            stage_in_vault)
from pangalactic.node import pangalaxian
from pangalactic.node.pangalaxian import Main

MCAD = 'pgefobjects:ModelType.MCAD'
ASSEMBLY_OID = 'test:spacecraft0'
USER_OID = 'test:zaphod'


class FakeSession:
    """Stands in for the WAMP session:  records calls, answers with a Deferred."""

    def __init__(self):
        self.calls = []
        self.deferreds = []

    def call(self, name, *args, **kw):
        # positional args matter:  vger.save() takes its serialized objects
        # positionally, and a stub accepting only keywords turns a signature
        # mistake into a silently swallowed TypeError -- the client wraps
        # every rpc in a bare "except: possible loss of transport"
        self.calls.append((name, args, kw))
        d = Deferred()
        self.deferreds.append(d)
        return d


class FakeClient:
    """
    A stand-in for Main carrying the real methods under test.

    Anything they call that is not under test -- read_and_upload_file(), the
    status bar, the message bus -- is recorded instead of done.
    """

    # the functions being tested, taken from the class that defines them
    upload_vault_file = Main.upload_vault_file
    next_vault_file_upload = Main.next_vault_file_upload
    finish_vault_file_upload = Main.finish_vault_file_upload
    push_staged_files = Main.push_staged_files
    upload_missing_vault_files = Main.upload_missing_vault_files
    note_files_that_arrived = Main.note_files_that_arrived
    sync_user_created_objs_to_repo = Main.sync_user_created_objs_to_repo
    register_component_files = Main.register_component_files
    save_component_files = Main.save_component_files
    on_add_update_doc = Main.on_add_update_doc
    on_chunk_download_failure = Main.on_chunk_download_failure
    download_did_fail = Main.download_did_fail
    on_file_download_success = Main.on_file_download_success
    on_download_open_success = Main.on_download_open_success
    save_new_file_objects = Main.save_new_file_objects
    push_document_references = Main.push_document_references
    save_missing_document_references = Main.save_missing_document_references
    on_add_update_model = Main.on_add_update_model
    store_step_correspondence = Main.store_step_correspondence

    def __init__(self):
        self.mbus = SimpleNamespace(session=FakeSession())
        self.statusbar = SimpleNamespace(showMessage=lambda msg: None)
        self.uploads_started = []
        self.locally_created = []
        self.objects_sent = []

    def add_locally_created(self, oid):
        self.locally_created.append(oid)

    def on_vger_save_result(self, result):
        pass

    def next_viewable_file_download(self):
        self.next_download_started = True

    def open_vault_file(self, rep_file=None):
        self.opened = rep_file

    def read_and_upload_file(self, fpath='', rep_file_oid='',
                             chunk_size=None):
        # the real one sets these, and upload_vault_file() reads
        # fpath_to_upload to tell whether something is already in flight --
        # a stub that did not set it would let every file start at once,
        # which is the thing the queue exists to prevent
        self.fpath_to_upload = fpath
        self.rep_file_oid_to_upload = rep_file_oid
        self.uploads_started.append((fpath, rep_file_oid))

    def set_bus_state(self):
        pass

    def on_failure(self, failure):
        pass


def a_client():
    return FakeClient()


class VaultFileUploadTest(unittest.TestCase):

    def setUp(self):
        self.was_user = state.get('local_user_oid')
        self.was_connected = state.get('connected')
        state['local_user_oid'] = USER_OID
        self.tmpdir = os.path.join(orb.home, 'upload_test_files')
        if not os.path.exists(self.tmpdir):
            os.makedirs(self.tmpdir)

    def tearDown(self):
        state['local_user_oid'] = self.was_user
        state['connected'] = self.was_connected

    def a_rep_file(self, name='part.stp', staged=True):
        fpath = os.path.join(self.tmpdir, name)
        with open(fpath, 'wb') as f:
            f.write(b'ISO-10303-21; /* ' + name.encode() + b' */')
        parms = {'file name': name,
                 'file size': str(os.path.getsize(fpath)),
                 'mime_type': 'application/step',
                 'name': name.split('.')[0],
                 'of_thing_oid': ASSEMBLY_OID,
                 'owner_oid': 'H2G2', 'project_oid': 'H2G2'}
        model, rep_file = new_model_with_file(MCAD, fpath, parms)
        orb.save([model, rep_file])
        orb.db.commit()
        if staged:
            stage_in_vault(rep_file, fpath)
        return rep_file

    # ---- one at a time ---------------------------------------------------

    def test_01_the_first_file_starts_at_once(self):
        """
        CASE:  nothing in flight.  The upload begins, from the vault copy and
        not from wherever the file was imported from -- that path may be gone
        by the time there is a connection.
        """
        client = a_client()
        rep_file = self.a_rep_file('first.stp')
        client.upload_vault_file(rep_file)
        expected = [(orb.get_vault_fpath(rep_file), rep_file.oid)]
        value = client.uploads_started
        self.assertEqual(expected, value)

    def test_02_a_second_file_waits_for_the_first(self):
        """
        CASE:  a file queued while another is going up.  Two at once would
        overwrite each other -- read_and_upload_file() keeps the chunks, the
        path and the target oid in instance attributes.
        """
        client = a_client()
        one = self.a_rep_file('one.stp')
        two = self.a_rep_file('two.stp')
        client.upload_vault_file(one)
        client.fpath_to_upload = orb.get_vault_fpath(one)   # in flight
        client.upload_vault_file(two)
        expected = 1
        value = len(client.uploads_started)
        self.assertEqual(expected, value)

    def test_03_the_next_file_starts_when_one_finishes(self):
        """
        CASE:  the queue drains.  Finishing one upload starts the next and
        says so, so that the caller does not start one of its own.
        """
        client = a_client()
        one = self.a_rep_file('drain-one.stp')
        two = self.a_rep_file('drain-two.stp')
        client.upload_vault_file(one)
        client.fpath_to_upload = orb.get_vault_fpath(one)
        client.upload_vault_file(two)
        started_another = client.finish_vault_file_upload(True)
        expected = [True, 2]
        value = [started_another, len(client.uploads_started)]
        self.assertEqual(expected, value)

    def test_04_an_empty_queue_says_nothing_was_started(self):
        """
        CASE:  the last file finishes.  False is what lets the component-file
        queue have its turn.
        """
        client = a_client()
        rep_file = self.a_rep_file('last.stp')
        client.upload_vault_file(rep_file)
        expected = False
        value = client.finish_vault_file_upload(True)
        self.assertEqual(expected, value)

    # ---- answering the waiter -------------------------------------------

    def test_05_the_waiter_is_told_the_upload_succeeded(self):
        """
        CASE:  a completed upload.  The Deferred fires, which is what the
        sync chain and the "add update model" handler wait on.
        """
        client = a_client()
        rep_file = self.a_rep_file('told.stp')
        answers = []
        client.upload_vault_file(rep_file).addCallback(answers.append)
        client.finish_vault_file_upload(True)
        self.assertEqual([True], answers)

    def test_06_the_waiter_is_told_the_upload_failed(self):
        """
        CASE:  an abandoned upload.  It must fire *something*:  a chunk
        failure used to simply stop, which as part of a sync chain would hang
        the login rather than fail it.
        """
        client = a_client()
        rep_file = self.a_rep_file('failed.stp')
        answers = []
        client.upload_vault_file(rep_file).addCallback(answers.append)
        client.finish_vault_file_upload(False)
        self.assertEqual([False], answers)

    def test_07_a_file_with_no_bytes_here_is_not_queued(self):
        """
        CASE:  a RepresentationFile whose bytes are not in the local vault.
        There is nothing to send, so it answers False at once rather than
        queueing an upload that would read nothing.
        """
        client = a_client()
        rep_file = self.a_rep_file('never-staged.stp', staged=False)
        answers = []
        client.upload_vault_file(rep_file).addCallback(answers.append)
        expected = [[False], []]
        value = [answers, client.uploads_started]
        self.assertEqual(expected, value)

    # ---- the sync step ---------------------------------------------------

    def test_08_nothing_is_asked_while_disconnected(self):
        """
        CASE:  the sync step reached offline.  It passes its data through
        untouched -- there is no rpc to call and nothing to wait for.
        """
        client = a_client()
        self.a_rep_file('offline.stp')
        state['connected'] = False
        expected = ['carry on', []]
        value = [client.push_staged_files('carry on'),
                 client.mbus.session.calls]
        self.assertEqual(expected, value)

    def test_09_the_repository_is_asked_which_files_it_lacks(self):
        """
        CASE:  connected, with a staged file.  The question is keyed on the
        vault file name and carries the size, so the answer can be given from
        the vault alone -- before the repository has ever heard of the
        object.
        """
        client = a_client()
        rep_file = self.a_rep_file('asked-about.stp')
        state['connected'] = True
        client.push_staged_files(None)
        name, args, kw = client.mbus.session.calls[0]
        expected = ['vger.missing_vault_files', True, rep_file.file_size]
        value = [name,
                 orb.get_vault_fname(rep_file) in kw['files'],
                 kw['files'].get(orb.get_vault_fname(rep_file))]
        self.assertEqual(expected, value)

    def test_10_only_the_files_the_repository_lacks_are_sent(self):
        """
        CASE:  the repository already has one of two files.  The one it has
        is not sent again.
        """
        client = a_client()
        here = self.a_rep_file('needed.stp')
        there = self.a_rep_file('already-there.stp')
        state['connected'] = True
        client.push_staged_files(None)
        client.upload_missing_vault_files([orb.get_vault_fname(here)])
        expected = [(orb.get_vault_fpath(here), here.oid)]
        value = client.uploads_started
        self.assertEqual(expected, value)
        self.assertNotIn(there.oid, [oid for _, oid in value])

    def test_11_nothing_is_sent_when_the_repository_has_it_all(self):
        """
        CASE:  an empty answer.  No uploads, and the sync carries on.
        """
        client = a_client()
        self.a_rep_file('all-there.stp')
        state['connected'] = True
        client.push_staged_files(None)
        expected = [None, []]
        value = [client.upload_missing_vault_files([]),
                 client.uploads_started]
        self.assertEqual(expected, value)


class ComponentFileTest(unittest.TestCase):
    """
    A CAD assembly exported as a *set*:  every file it names needs an object
    too, or only the file the user chose reaches the repository.

    `reference_closure()` is stubbed -- what it derives from a STEP file is
    test_step_import.py's business, and what matters here is that the objects
    it implies are built, in the right order, whether or not there is a
    connection.
    """

    def setUp(self):
        self.was_user = state.get('local_user_oid')
        self.was_connected = state.get('connected')
        state['local_user_oid'] = USER_OID
        self.was_products = state.get('step_component_products')
        self.tmpdir = os.path.join(orb.home, 'component_test_files')
        if not os.path.exists(self.tmpdir):
            os.makedirs(self.tmpdir)

    def tearDown(self):
        state['local_user_oid'] = self.was_user
        state['connected'] = self.was_connected
        state['step_component_products'] = self.was_products

    def a_file(self, name):
        fpath = os.path.join(self.tmpdir, name)
        with open(fpath, 'wb') as f:
            f.write(b'ISO-10303-21; /* ' + name.encode() + b' */')
        return fpath

    def an_assembly_file(self, name='top.stp'):
        fpath = self.a_file(name)
        parms = {'file name': name,
                 'file size': str(os.path.getsize(fpath)),
                 'mime_type': 'application/step',
                 'name': name.split('.')[0],
                 'of_thing_oid': ASSEMBLY_OID,
                 'owner_oid': 'H2G2', 'project_oid': 'H2G2'}
        model, rep_file = new_model_with_file(MCAD, fpath, parms)
        orb.save([model, rep_file])
        orb.db.commit()
        return model, rep_file, fpath

    def with_closure(self, closure):
        """
        Make reference_closure() answer with the given (child, parent) pairs.
        """
        from pangalactic.node import step_import
        self._real_closure = step_import.reference_closure
        step_import.reference_closure = lambda path: closure
        self.addCleanup(setattr, step_import, 'reference_closure',
                        self._real_closure)

    def test_01_every_referenced_file_gets_an_object_offline(self):
        """
        CASE:  a set imported while disconnected.  Registration used to be an
        rpc per file, so offline the set was reduced to the one file the user
        chose;  the objects are made here now, so the whole set is kept.
        """
        state['connected'] = False
        model, top_file, top = self.an_assembly_file('off-top.stp')
        one = self.a_file('off-one.stp')
        two = self.a_file('off-two.stp')
        self.with_closure([(one, top), (two, top)])
        client = a_client()
        client.register_component_files(top, top_file)
        orb.db.commit()
        names = sorted(rf.user_file_name
                       for rf in (top_file.component_files or []))
        expected = [['off-one.stp', 'off-two.stp'], []]
        value = [names, client.uploads_started]
        self.assertEqual(expected, value)

    def test_02_a_file_of_a_file_is_attached_to_its_own_parent(self):
        """
        CASE:  a nested set -- the assembly names a subassembly, which names
        a part.  "component_file_of" must point at the file that actually
        references it, which is why reference_closure() returns parents
        before children.
        """
        state['connected'] = False
        model, top_file, top = self.an_assembly_file('nest-top.stp')
        sub = self.a_file('nest-sub.stp')
        part = self.a_file('nest-part.stp')
        self.with_closure([(sub, top), (part, sub)])
        client = a_client()
        client.register_component_files(top, top_file)
        orb.db.commit()
        sub_file = [rf for rf in top_file.component_files
                    if rf.user_file_name == 'nest-sub.stp'][0]
        part_files = [rf.user_file_name
                      for rf in (sub_file.component_files or [])]
        expected = [['nest-part.stp'], 1]
        value = [part_files, len(top_file.component_files or [])]
        self.assertEqual(expected, value)

    def test_03_a_file_that_models_a_product_gets_its_own_model(self):
        """
        CASE:  the import identified which product a referenced file models.
        It gets a Model of that product rather than joining the assembly's,
        which is what lets the subassembly be opened on its own.
        """
        state['connected'] = False
        model, top_file, top = self.an_assembly_file('prod-top.stp')
        sub = self.a_file('prod-sub.stp')
        state['step_component_products'] = {sub: ASSEMBLY_OID}
        self.with_closure([(sub, top)])
        client = a_client()
        client.register_component_files(top, top_file)
        orb.db.commit()
        sub_file = top_file.component_files[0]
        expected = [ASSEMBLY_OID, False]
        value = [sub_file.of_object.of_thing.oid,
                 sub_file.of_object.oid == model.oid]
        self.assertEqual(expected, value)

    def test_04_a_missing_file_does_not_strand_the_rest(self):
        """
        CASE:  one referenced file is gone from disk.  It is dropped and the
        others are still registered -- the cascade this replaces had the same
        rule, for the same reason.
        """
        state['connected'] = False
        model, top_file, top = self.an_assembly_file('gone-top.stp')
        here = self.a_file('gone-here.stp')
        missing = os.path.join(self.tmpdir, 'not-on-disk.stp')
        self.with_closure([(missing, top), (here, top)])
        client = a_client()
        client.register_component_files(top, top_file)
        orb.db.commit()
        names = [rf.user_file_name for rf in (top_file.component_files or [])]
        expected = ['gone-here.stp']
        value = names
        self.assertEqual(expected, value)

    def test_05_the_objects_are_editable_offline(self):
        """
        CASE:  objects created here that the repository has not seen.  They
        are registered as locally created, which is what lets them be edited
        while disconnected -- access.is_writable_now(), rule [4].
        """
        state['connected'] = False
        model, top_file, top = self.an_assembly_file('edit-top.stp')
        one = self.a_file('edit-one.stp')
        self.with_closure([(one, top)])
        client = a_client()
        client.register_component_files(top, top_file)
        orb.db.commit()
        created = [rf for rf in top_file.component_files
                   if rf.user_file_name == 'edit-one.stp']
        expected = True
        value = created[0].oid in client.locally_created
        self.assertEqual(expected, value)

    def test_06_connected_the_bytes_are_queued(self):
        """
        CASE:  the same import with a connection.  Every file's bytes are
        queued, one at a time -- two uploads at once would overwrite each
        other's chunks.
        """
        state['connected'] = True
        model, top_file, top = self.an_assembly_file('conn-top.stp')
        one = self.a_file('conn-one.stp')
        two = self.a_file('conn-two.stp')
        self.with_closure([(one, top), (two, top)])
        client = a_client()
        client.register_component_files(top, top_file)
        orb.db.commit()
        expected = [1, 1]
        value = [len(client.uploads_started),
                 len(getattr(client, 'file_upload_queue', []))]
        self.assertEqual(expected, value)

    def test_07_the_objects_go_when_every_file_is_there(self):
        """
        CASE:  every upload of a set succeeded.  The objects are published --
        the "new objects" signal is what pushes them, so this is the send.
        """
        client = a_client()
        objs = ['stand-in for the objects']
        with mock.patch.object(pangalaxian, 'dispatcher') as fake:
            client.save_component_files(objs, [(True, True), (True, True)])
        fake.send.assert_called_once_with(signal='new objects', objs=objs)

    def test_08_nothing_is_published_until_every_file_is_there(self):
        """
        CASE:  one upload of a set failed.  All the objects are held back,
        not only the one that failed:  a set is only readable whole, so
        publishing the rest would describe an assembly nobody can open.

        They stay in created_objects, so the next sync retries them -- bytes
        first, again.
        """
        client = a_client()
        objs = ['stand-in for the objects']
        with mock.patch.object(pangalaxian, 'dispatcher') as fake:
            client.save_component_files(objs, [(True, True), (True, False)])
        fake.send.assert_not_called()


class DocumentTest(unittest.TestCase):
    """
    A document brings three objects, and one of them -- the
    DocumentReference -- has no creator and so no route of its own to the
    repository.  These cover the route it was given instead.
    """

    def setUp(self):
        self.was_user = state.get('local_user_oid')
        self.was_connected = state.get('connected')
        state['local_user_oid'] = USER_OID
        self.tmpdir = os.path.join(orb.home, 'doc_test_files')
        if not os.path.exists(self.tmpdir):
            os.makedirs(self.tmpdir)

    def tearDown(self):
        state['local_user_oid'] = self.was_user
        state['connected'] = self.was_connected

    def a_doc_file(self, name):
        fpath = os.path.join(self.tmpdir, name)
        with open(fpath, 'wb') as f:
            f.write(b'%PDF-1.4 ' + name.encode())
        return fpath

    def doc_parms(self, fpath):
        return {'file name': os.path.basename(fpath),
                'file size': str(os.path.getsize(fpath)),
                'name': os.path.basename(fpath).split('.')[0],
                'description': 'a document',
                'rel_obj_oid': ASSEMBLY_OID,
                'owner_oid': 'H2G2', 'project_oid': 'H2G2'}

    def test_01_a_document_imported_offline_is_kept_whole(self):
        """
        CASE:  a document attached while disconnected.  This used to be an
        rpc, so nothing happened at all;  all three objects are made here
        now, and the file is kept.
        """
        state['connected'] = False
        fpath = self.a_doc_file('offline-doc.pdf')
        client = a_client()
        client.on_add_update_doc(fpath=fpath, parms=self.doc_parms(fpath))
        orb.db.commit()
        doc = orb.select('Document', name='offline-doc')
        refs = orb.search_exact(cname='DocumentReference', document=doc)
        rep_file = doc.has_files[0]
        expected = [True, 1, ASSEMBLY_OID, True, []]
        value = [doc is not None, len(refs), refs[0].related_item.oid,
                 os.path.exists(orb.get_vault_fpath(rep_file)),
                 client.uploads_started]
        self.assertEqual(expected, value)

    def test_02_the_document_and_its_file_are_editable_offline(self):
        """
        CASE:  the same import.  Document and RepresentationFile are
        registered as locally created;  the DocumentReference does not need
        it, being in access.modifiables.
        """
        state['connected'] = False
        fpath = self.a_doc_file('editable-doc.pdf')
        client = a_client()
        client.on_add_update_doc(fpath=fpath, parms=self.doc_parms(fpath))
        orb.db.commit()
        doc = orb.select('Document', name='editable-doc')
        expected = [True, True]
        value = [doc.oid in client.locally_created,
                 doc.has_files[0].oid in client.locally_created]
        self.assertEqual(expected, value)

    def test_03_connected_the_bytes_go_before_the_objects(self):
        """
        CASE:  a document attached with a connection.  The upload is started
        and nothing is published until it succeeds -- the "new objects"
        signal is the push.
        """
        state['connected'] = True
        fpath = self.a_doc_file('online-doc.pdf')
        client = a_client()
        with mock.patch.object(pangalaxian, 'dispatcher') as fake:
            client.on_add_update_doc(fpath=fpath,
                                     parms=self.doc_parms(fpath))
            started = list(client.uploads_started)
            not_yet = fake.send.called
            client.finish_vault_file_upload(True)
            sent = fake.send.call_args
        objs = sent.kwargs['objs']
        cnames = sorted(o.__class__.__name__ for o in objs)
        expected = [1, False,
                    ['Document', 'DocumentReference', 'RepresentationFile']]
        value = [len(started), not_yet, cnames]
        self.assertEqual(expected, value)

    def test_04_a_failed_upload_publishes_nothing(self):
        """
        CASE:  the document's file could not be sent.  The objects are held
        back rather than describing a document nobody can open.
        """
        state['connected'] = True
        fpath = self.a_doc_file('failed-doc.pdf')
        client = a_client()
        with mock.patch.object(pangalaxian, 'dispatcher') as fake:
            client.on_add_update_doc(fpath=fpath,
                                     parms=self.doc_parms(fpath))
            client.finish_vault_file_upload(False)
        fake.send.assert_not_called()

    # ---- the reference's route -------------------------------------------

    def test_05_the_repository_is_asked_about_the_references(self):
        """
        CASE:  the sync step.  The reference is found by way of its Document
        -- it has no creator to be found by -- and the repository is asked
        which ones it already has.
        """
        state['connected'] = False
        fpath = self.a_doc_file('asked-doc.pdf')
        client = a_client()
        client.on_add_update_doc(fpath=fpath, parms=self.doc_parms(fpath))
        orb.db.commit()
        doc = orb.select('Document', name='asked-doc')
        ref = orb.search_exact(cname='DocumentReference', document=doc)[0]
        state['connected'] = True
        client.push_document_references(None)
        name, args, kw = client.mbus.session.calls[-1]
        expected = ['vger.get_mod_dts', True]
        value = [name, ref.oid in kw['oids']]
        self.assertEqual(expected, value)

    def test_06_a_missing_reference_is_sent_with_its_document(self):
        """
        CASE:  the repository does not have the reference.  It is sent with
        its Document -- the repository may not have that either, and
        DESERIALIZATION_ORDER puts Document first.
        """
        state['connected'] = False
        fpath = self.a_doc_file('missing-ref-doc.pdf')
        client = a_client()
        client.on_add_update_doc(fpath=fpath, parms=self.doc_parms(fpath))
        orb.db.commit()
        doc = orb.select('Document', name='missing-ref-doc')
        ref = orb.search_exact(cname='DocumentReference', document=doc)[0]
        state['connected'] = True
        client.push_document_references(None)
        # the repository reports nothing for it, so it does not have it
        client.save_missing_document_references({})
        name, args, kw = client.mbus.session.calls[-1]
        # vger.save takes the serialized objects positionally
        sent = {so['oid']: so['_cname'] for so in args[0]}
        expected = ['vger.save', 'DocumentReference', 'Document']
        value = [name, sent.get(ref.oid), sent.get(doc.oid)]
        self.assertEqual(expected, value)

    def test_07_nothing_is_sent_when_the_repository_has_them(self):
        """
        CASE:  the repository reports a mod_datetime for every reference, so
        it has them all.  No save at all -- an unconditional push would
        re-send every document on every sync.
        """
        state['connected'] = False
        fpath = self.a_doc_file('has-them-doc.pdf')
        client = a_client()
        client.on_add_update_doc(fpath=fpath, parms=self.doc_parms(fpath))
        orb.db.commit()
        state['connected'] = True
        client.push_document_references(None)
        oids = client.mbus.session.calls[-1][2]['oids']
        before = len(client.mbus.session.calls)
        answer = {oid: '2026-08-29 12:00:00' for oid in oids}
        result = client.save_missing_document_references(answer)
        expected = [None, before]
        value = [result, len(client.mbus.session.calls)]
        self.assertEqual(expected, value)


class StepModelTest(unittest.TestCase):
    """
    The whole tail of "add update model":  a STEP import's Model, its
    RepresentationFile, the correspondence written on it, and the one push
    that sends them.

    The rule the handler exists to keep is that **the objects go up after the
    bytes, and together**.  A RepresentationFile that reaches the repository
    on its own reaches it before its Model, and the repository then has a
    file whose "of_object" resolves to nothing:  nothing cloaks it
    (access.is_cloaked) and nobody may fetch it (access.may_fetch_file), so
    it is announced on the public channel and then refused to everyone,
    including its own project.  That is what "download not authorized" was,
    observed on a two-client STEP import 2026-09-03.
    """

    def setUp(self):
        self.was_user = state.get('local_user_oid')
        self.was_connected = state.get('connected')
        self.was_pending = state.get('step_pending_correspondence')
        state['local_user_oid'] = USER_OID
        self.tmpdir = os.path.join(orb.home, 'step_model_test_files')
        if not os.path.exists(self.tmpdir):
            os.makedirs(self.tmpdir)
        # register_component_files() is not what is under test here, and a
        # single self-contained file references nothing
        from pangalactic.node import step_import
        real = step_import.reference_closure
        step_import.reference_closure = lambda path: []
        self.addCleanup(setattr, step_import, 'reference_closure', real)

    def tearDown(self):
        state['local_user_oid'] = self.was_user
        state['connected'] = self.was_connected
        state['step_pending_correspondence'] = self.was_pending

    def a_step_file(self, name):
        fpath = os.path.join(self.tmpdir, name)
        with open(fpath, 'wb') as f:
            f.write(b'ISO-10303-21;\nHEADER;\nENDSEC;\nEND-ISO-10303-21;\n')
        return fpath

    def parms(self, fpath):
        return {'file name': os.path.basename(fpath),
                'file size': str(os.path.getsize(fpath)),
                'mime_type': 'application/step',
                'name': 'TO-5',
                'description': 'a STEP model for testing',
                'of_thing_oid': ASSEMBLY_OID,
                'owner_oid': 'H2G2', 'project_oid': 'H2G2'}

    def a_pending_correspondence(self, fpath):
        """
        What _register_step_model() leaves in state for the handler.
        """
        state['step_pending_correspondence'] = {'fpath': fpath,
                                                'checksum': 'abc123',
                                                'mode': 'create',
                                                'map': {'#1': 'an-oid'}}

    def test_01_nothing_is_pushed_before_the_bytes(self):
        """
        CASE:  a STEP import with a connection and a correspondence to store.

        Storing the correspondence used to end with a "modified object"
        signal, which is a vger.save() of the RepresentationFile alone --
        sent before the Model, and before the bytes.  Nothing may go up
        until the upload answers.
        """
        state['connected'] = True
        fpath = self.a_step_file('pending-one.stp')
        self.a_pending_correspondence(fpath)
        client = a_client()
        with mock.patch.object(pangalaxian, 'dispatcher') as fake:
            client.on_add_update_model(mtype_oid=MCAD, fpath=fpath,
                                       parms=self.parms(fpath))
            expected = [1, False]
            value = [len(client.uploads_started), fake.send.called]
        self.assertEqual(expected, value)

    def test_02_the_model_and_its_file_go_up_together(self):
        """
        CASE:  the upload succeeded.  One push, carrying both objects -- the
        Model first, so that the repository can resolve "of_object" when it
        deserializes the file.
        """
        state['connected'] = True
        fpath = self.a_step_file('pending-two.stp')
        self.a_pending_correspondence(fpath)
        client = a_client()
        with mock.patch.object(pangalaxian, 'dispatcher') as fake:
            client.on_add_update_model(mtype_oid=MCAD, fpath=fpath,
                                       parms=self.parms(fpath))
            client.finish_vault_file_upload(True)
            sends = fake.send.call_args_list
        cnames = [o.__class__.__name__ for o in sends[0].kwargs['objs']]
        expected = [1, ['Model', 'RepresentationFile']]
        value = [len(sends), cnames]
        self.assertEqual(expected, value)

    def test_03_the_correspondence_travels_with_the_objects(self):
        """
        CASE:  the correspondence is written before the pair is sent, so it
        is a data element of the RepresentationFile the push carries.  That
        is why the separate save it used to do is not needed.
        """
        from pangalactic.node.step_plan import get_correspondence
        state['connected'] = True
        fpath = self.a_step_file('pending-three.stp')
        self.a_pending_correspondence(fpath)
        client = a_client()
        with mock.patch.object(pangalaxian, 'dispatcher') as fake:
            client.on_add_update_model(mtype_oid=MCAD, fpath=fpath,
                                       parms=self.parms(fpath))
            client.finish_vault_file_upload(True)
            objs = fake.send.call_args.kwargs['objs']
        rep_file = [o for o in objs
                    if o.__class__.__name__ == 'RepresentationFile'][0]
        stored = get_correspondence(rep_file)
        expected = ['abc123', {'#1': 'an-oid'}, {}]
        value = [stored.get('checksum'), stored.get('map'),
                 state.get('step_pending_correspondence')]
        self.assertEqual(expected, value)

    def test_04_a_failed_upload_publishes_nothing(self):
        """
        CASE:  the bytes did not go up.  Neither object follows, so no file
        record is created that nobody can fetch.
        """
        state['connected'] = True
        fpath = self.a_step_file('pending-four.stp')
        self.a_pending_correspondence(fpath)
        client = a_client()
        with mock.patch.object(pangalaxian, 'dispatcher') as fake:
            client.on_add_update_model(mtype_oid=MCAD, fpath=fpath,
                                       parms=self.parms(fpath))
            client.finish_vault_file_upload(False)
        fake.send.assert_not_called()

    def test_05_offline_nothing_is_pushed_and_the_file_is_kept(self):
        """
        CASE:  the same import with no connection.  Both objects and the
        correspondence are here, and nothing was sent anywhere.
        """
        state['connected'] = False
        fpath = self.a_step_file('pending-five.stp')
        self.a_pending_correspondence(fpath)
        client = a_client()
        with mock.patch.object(pangalaxian, 'dispatcher') as fake:
            client.on_add_update_model(mtype_oid=MCAD, fpath=fpath,
                                       parms=self.parms(fpath))
            sent = fake.send.called
        expected = [False, [], 2]
        value = [sent, client.uploads_started, len(client.locally_created)]
        self.assertEqual(expected, value)


class RefusedDownloadTest(unittest.TestCase):
    """
    vger.download_chunk() can now refuse a request -- the caller may not view
    what the file represents -- and every chunk of that file then fails.

    The chunk errback returns None, which tells twisted the failure is
    handled, so the success callback chained after it runs anyway.  That was
    harmless when the only failures were transport ones;  it is not now.
    """

    def a_downloading_client(self):
        client = a_client()
        client.downloaded_chunks = 0
        client.failed_chunks = 0
        client.next_download_started = False
        client.opened = None
        client.download_progress = SimpleNamespace(
                                        done=lambda n: None,
                                        setValue=lambda n: None)
        return client

    def test_01_a_refusal_is_not_announced_as_a_download(self):
        """
        CASE:  every chunk refused.  The completion callback must not report
        a finished download, and must not start the next queued one as
        though this had worked.
        """
        client = self.a_downloading_client()
        client.on_chunk_download_failure('not authorized')
        client.on_file_download_success(None)
        expected = [1, False]
        value = [client.failed_chunks, client.next_download_started]
        self.assertEqual(expected, value)

    def test_02_nothing_is_opened_after_a_refusal(self):
        """
        CASE:  the user asked to open the file.  Opening what was never
        downloaded is the visible form of this bug -- and unpacking the
        errback's None was the invisible one, a traceback in the reactor.
        """
        client = self.a_downloading_client()
        client.on_chunk_download_failure('not authorized')
        client.on_download_open_success(None)
        self.assertIsNone(client.opened)

    def test_03_a_download_with_no_data_opens_nothing(self):
        """
        CASE:  the callback reached with no result at all.  It used to unpack
        it -- "oid, seq, data = result" -- and raise TypeError.
        """
        client = self.a_downloading_client()
        client.on_download_open_success(None)
        self.assertIsNone(client.opened)

    def test_04_a_good_download_still_completes(self):
        """
        CASE:  the ordinary one.  The guard must not have broken the path it
        guards -- a neighbouring case that cannot pass vacuously.
        """
        client = self.a_downloading_client()
        client.on_file_download_success(('rf-oid', 0, b'data'))
        self.assertTrue(client.next_download_started)


class HeldBackFileObjectTest(unittest.TestCase):
    """
    The rule is that a RepresentationFile reaches the repository only with
    its bytes.  save_new_file_objects() keeps it on the immediate path;  the
    sync used to break it, pushing every object in created_objects whether or
    not push_staged_files() had managed to send the file.
    """

    def setUp(self):
        self.was_user = state.get('local_user_oid')
        self.was_connected = state.get('connected')
        state['local_user_oid'] = USER_OID
        state['connected'] = True
        self.tmpdir = os.path.join(orb.home, 'heldback_test_files')
        if not os.path.exists(self.tmpdir):
            os.makedirs(self.tmpdir)

    def tearDown(self):
        state['local_user_oid'] = self.was_user
        state['connected'] = self.was_connected

    def a_staged_file(self, name):
        fpath = os.path.join(self.tmpdir, name)
        with open(fpath, 'wb') as f:
            f.write(b'ISO-10303-21; /* ' + name.encode() + b' */')
        parms = {'file name': name,
                 'file size': str(os.path.getsize(fpath)),
                 'mime_type': 'application/step',
                 'name': name.split('.')[0],
                 'of_thing_oid': ASSEMBLY_OID,
                 'owner_oid': 'H2G2', 'project_oid': 'H2G2'}
        model, rep_file = new_model_with_file(MCAD, fpath, parms)
        orb.save([model, rep_file])
        orb.db.commit()
        stage_in_vault(rep_file, fpath)
        return rep_file

    def a_syncing_client(self):
        client = a_client()
        client.local_user = orb.get(USER_OID)
        return client

    def test_01_a_file_that_did_not_go_up_holds_its_object_back(self):
        """
        CASE:  the upload failed.  Sending the object anyway would publish a
        file record that every other client can see and none can fetch.
        """
        client = self.a_syncing_client()
        rep_file = self.a_staged_file('held-back.stp')
        client.push_staged_files(None)
        client.upload_missing_vault_files([orb.get_vault_fname(rep_file)])
        client.finish_vault_file_upload(False)      # the upload failed
        client.sync_user_created_objs_to_repo(None)
        name, args, kw = client.mbus.session.calls[-1]
        expected = ['vger.sync_objects', False]
        value = [name, rep_file.oid in args[0]]
        self.assertEqual(expected, value)

    def test_02_a_file_that_went_up_is_synced(self):
        """
        CASE:  the upload succeeded.  The neighbouring case that cannot pass
        vacuously -- a test of the hold-back alone would pass just as well if
        nothing were ever synced.
        """
        client = self.a_syncing_client()
        rep_file = self.a_staged_file('went-up.stp')
        client.push_staged_files(None)
        client.upload_missing_vault_files([orb.get_vault_fname(rep_file)])
        client.finish_vault_file_upload(True)       # the upload succeeded
        client.sync_user_created_objs_to_repo(None)
        name, args, kw = client.mbus.session.calls[-1]
        expected = ['vger.sync_objects', True]
        value = [name, rep_file.oid in args[0]]
        self.assertEqual(expected, value)

    def test_03_a_file_the_repository_already_has_is_synced(self):
        """
        CASE:  nothing to upload at all -- the repository reported no missing
        files.  Nothing is held back.
        """
        client = self.a_syncing_client()
        rep_file = self.a_staged_file('already-there.stp')
        client.push_staged_files(None)
        client.upload_missing_vault_files([])       # it has them all
        client.sync_user_created_objs_to_repo(None)
        name, args, kw = client.mbus.session.calls[-1]
        expected = ['vger.sync_objects', True]
        value = [name, rep_file.oid in args[0]]
        self.assertEqual(expected, value)

    def test_04_the_record_does_not_outlive_its_sync(self):
        """
        CASE:  a file held back by one sync, and gone up by the next.  The
        set is rebuilt at the start of every push, so a stale entry cannot
        hold back a file that has since arrived.
        """
        client = self.a_syncing_client()
        rep_file = self.a_staged_file('next-time.stp')
        client.push_staged_files(None)
        client.upload_missing_vault_files([orb.get_vault_fname(rep_file)])
        client.finish_vault_file_upload(False)
        held_after_failure = rep_file.oid in client._files_missing_upstream
        # the next sync:  the repository now has it, so it is not offered
        client.push_staged_files(None)
        client.upload_missing_vault_files([])
        client.sync_user_created_objs_to_repo(None)
        name, args, kw = client.mbus.session.calls[-1]
        expected = [True, True]
        value = [held_after_failure, rep_file.oid in args[0]]
        self.assertEqual(expected, value)


if __name__ == '__main__':
    unittest.main()
