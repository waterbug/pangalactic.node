# -*- coding: utf-8 -*-
"""
Tests for fetching model files automatically.

A sync brings a project's Products, Acus, Models and RepresentationFiles --
but a RepresentationFile is a *record* of a file, not the file.  A client
syncing a project someone else imported therefore got the whole assembly and
rendered nothing.

Files the built-in viewer can render are now fetched as they arrive, because
the vault copy is what the viewer opens.  Anything the client cannot display
itself is left on demand:  "Models and Docs" -> save a local copy is the
right route for those, and is what it is for.

Run headless with QT_QPA_PLATFORM=offscreen.
"""
import os

import pytest

# set the orb -- must precede any pangalactic.core import that pulls in "orb"
import pangalactic.core.set_uberorb

from pangalactic.core import orb, state
from pangalactic.core.clone import clone
from pangalactic.core.uberorb import is_viewable_file

from pangalactic.node.pangalaxian import Main


class FakeMain:
    """
    Just enough of Main to drive the queue.  download_file() is recorded
    rather than performed -- what these test is which files are chosen and
    in what order, not the transfer.
    """
    queue_viewable_files = Main.queue_viewable_files
    next_viewable_file_download = Main.next_viewable_file_download

    def __init__(self):
        self.downloaded = []
        self.viewable_file_queue = []
        self.downloading_viewable_file = False
        self.downloading_file_oid = ''

    def download_file(self, digital_file=None, **kw):
        self.downloaded.append(digital_file)


@pytest.fixture
def main(test_orb):
    saved = state.get('connected')
    state['connected'] = True
    yield FakeMain()
    state['connected'] = saved


def rep_file(name, in_vault=False):
    rf = clone('RepresentationFile', user_file_name=name,
               id=name.replace('.', '_'), name=name)
    orb.save([rf])
    if in_vault:
        with open(orb.get_vault_fpath(rf), 'wb') as f:
            f.write(b'x')
    return rf


# ---------------------------------------------------------------------------
# which formats count
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('name', ['asm.stp', 'asm.STP', 'part.step',
                                  'part.p21', 'mesh.stl', 'solid.brep',
                                  'SOLID.BREP'])
def test_01_viewable_formats(test_orb, name):
    """
    CASE:  formats the OCC viewer renders.  Both cases of each suffix,
    because a file name's suffix is whatever the exporter wrote.
    """
    assert is_viewable_file(rep_file(name))


@pytest.mark.parametrize('name', ['spec.pdf', 'notes.docx', 'data.xlsx',
                                  'photo.png', 'noextension'])
def test_02_other_formats_are_not(test_orb, name):
    """
    CASE:  formats the client cannot display.  Left on demand -- fetching
    every document in a project in order to look at an assembly would be the
    wrong trade.
    """
    assert not is_viewable_file(rep_file(name))


# ---------------------------------------------------------------------------
# what gets queued
# ---------------------------------------------------------------------------

def test_03_a_model_file_is_fetched(main):
    """
    CASE:  a STEP file arrives in a sync.  It is fetched, without the user
    asking -- this is the whole point.
    """
    rf = rep_file('arrived.stp')
    main.queue_viewable_files([rf])
    assert main.downloaded == [rf]


def test_04_a_document_is_not(main):
    """
    CASE:  a PDF arrives.  Left alone.
    """
    rf = rep_file('arrived.pdf')
    main.queue_viewable_files([rf])
    assert main.downloaded == []


def test_05_a_file_already_in_the_vault_is_not_refetched(main):
    """
    CASE:  the vault already has it -- the usual case for the client that
    did the import, which copies to its own vault as it uploads.
    """
    rf = rep_file('already.stp', in_vault=True)
    main.queue_viewable_files([rf])
    assert main.downloaded == []


def test_06_other_objects_are_ignored(main):
    """
    CASE:  a sync batch is mostly not files.
    """
    product = orb.get('test:spacecraft0')
    rf = rep_file('among_others.stp')
    main.queue_viewable_files([product, rf, product])
    assert main.downloaded == [rf]


def test_07_nothing_is_fetched_while_disconnected(main):
    """
    CASE:  disconnected.  There is nothing to fetch from.
    """
    state['connected'] = False
    main.queue_viewable_files([rep_file('offline.stp')])
    assert main.downloaded == []


# ---------------------------------------------------------------------------
# one at a time
# ---------------------------------------------------------------------------

def test_08_files_are_fetched_one_at_a_time(main):
    """
    CASE:  several files arrive together -- an assembly exported as a set is
    thirteen of them.

    Only the first starts.  download_file() keeps the chunk count and the
    progress dialog in instance attributes, so two at once would report each
    other's progress and close each other's dialog.
    """
    files = [rep_file(f'set_{i}.stp') for i in range(4)]
    main.queue_viewable_files(files)
    assert main.downloaded == [files[0]]
    assert len(main.viewable_file_queue) == 3


def test_09_each_completion_starts_the_next(main):
    """
    CASE:  the queue drains as downloads finish, in order.
    """
    files = [rep_file(f'drain_{i}.stp') for i in range(3)]
    main.queue_viewable_files(files)
    for i in range(1, 3):
        main.next_viewable_file_download()
        assert main.downloaded[-1] is files[i]
    # and the queue is empty afterwards
    main.next_viewable_file_download()
    assert main.viewable_file_queue == []
    assert not main.downloading_viewable_file


def test_10_a_second_batch_joins_the_queue(main):
    """
    CASE:  more files arrive while one is being fetched -- a sync arrives in
    chunks.  They join the queue rather than starting a second download.
    """
    first = [rep_file(f'batch_a_{i}.stp') for i in range(2)]
    main.queue_viewable_files(first)
    assert len(main.downloaded) == 1
    second = [rep_file(f'batch_b_{i}.stp') for i in range(2)]
    main.queue_viewable_files(second)
    assert len(main.downloaded) == 1, 'a second download was started'
    assert len(main.viewable_file_queue) == 3


def test_11_a_file_is_not_queued_twice(main):
    """
    CASE:  the same file arrives in two batches, which a re-sync will do.

    Including while it is being fetched:  it is not in the queue then, but
    must not go back into it.
    """
    rf = rep_file('twice.stp')
    main.queue_viewable_files([rf])
    main.queue_viewable_files([rf])
    assert main.downloaded == [rf]
    assert main.viewable_file_queue == []


def test_12_a_file_that_arrived_meanwhile_is_skipped(main):
    """
    CASE:  a queued file turns up in the vault by another route before its
    turn -- opening a model fetches its closure, for one.  It is skipped and
    the next one starts, rather than being fetched again.
    """
    first, second = rep_file('q1.stp'), rep_file('q2.stp')
    main.queue_viewable_files([first, second])
    assert main.downloaded == [first]
    with open(orb.get_vault_fpath(second), 'wb') as f:
        f.write(b'arrived by another route')
    main.next_viewable_file_download()
    assert second not in main.downloaded
    assert main.viewable_file_queue == []
