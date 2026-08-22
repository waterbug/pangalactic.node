# -*- coding: utf-8 -*-
"""
Tests for detecting a pending schema migration at start-up.

An incompatible home used to be emptied -- local.db, the caches and every
.json file removed -- because there was no migration.  There is one now, so
the removals are gone and the version check only reports.  What it reports
has to be right:  the message is shown while the user waits, and a wrong one
would either promise a migration that is not happening or say nothing while
the client appears to hang.

This deliberately does not start the orb.  pending_schema_migration() runs
*before* orb.start(), and reads the state file itself for that reason.
"""
import os

import pytest
import ruamel_yaml as yaml

from pangalactic.core.mapping import schema_version

from pangalactic.node.pangalaxian import pending_schema_migration


@pytest.fixture
def home(tmp_path):
    return str(tmp_path)


def write_state_file(home, **items):
    with open(os.path.join(home, 'state'), 'w') as f:
        f.write(yaml.safe_dump(items, default_flow_style=False))


def test_01_older_schema_is_a_pending_migration(home):
    """
    CASE:  the home records an older schema version.  A migration is pending,
    and both versions come back so the message can name them.
    """
    write_state_file(home, schema_version='3.6.0')
    assert pending_schema_migration(home) == ('3.6.0', schema_version)


def test_02_matching_schema_is_not(home):
    """
    CASE:  the home is already on the app's schema.  Nothing to say.
    """
    write_state_file(home, schema_version=schema_version)
    assert pending_schema_migration(home) is None


def test_03_no_state_file(home):
    """
    CASE:  a brand new home.  Nothing to migrate, and nothing to read.
    """
    assert pending_schema_migration(home) is None


def test_04_state_without_a_schema_version(home):
    """
    CASE:  a home whose state records no schema version.

    Reported as "no migration", because there is nothing to compare against
    -- which is exactly the hole that made such a home unmigratable in the
    first place.  orb.start() now records a version when it finds none, so
    this state stops arising;  the case is kept because a home written before
    that can still be out there.
    """
    write_state_file(home, project='H2G2')
    assert pending_schema_migration(home) is None


def test_05_unreadable_state_file(home):
    """
    CASE:  the state file will not parse -- a plausible result of a crash or
    a full disk mid-write.  Start-up is not worth failing over a splash
    message, and the orb makes its own decision about it a moment later.
    """
    with open(os.path.join(home, 'state'), 'w') as f:
        f.write('{[not: valid yaml')
    assert pending_schema_migration(home) is None


def test_06_empty_state_file(home):
    """
    CASE:  the state file exists but is empty.
    """
    with open(os.path.join(home, 'state'), 'w') as f:
        f.write('')
    assert pending_schema_migration(home) is None


def test_07_no_home_at_all(home):
    """
    CASE:  no home directory.  First run.
    """
    assert pending_schema_migration('') is None
    assert pending_schema_migration(os.path.join(home, 'nope')) is None


def test_08_reading_does_not_disturb_the_state(home):
    """
    CASE:  asking must not change anything.  It runs before orb.start(),
    which reads the same file, so a side effect here would carry into
    start-up.
    """
    from pangalactic.core import state
    write_state_file(home, schema_version='3.6.0', project='SOMETHING-ELSE')
    before = dict(state)
    pending_schema_migration(home)
    assert dict(state) == before


# ---------------------------------------------------------------------------
# emptying a home that is too old to migrate
#
# This is what happened to *every* incompatible home before there was a
# migration.  It now happens only below Main.min_migratable_version, and it
# has to leave the home in a state that start-up reads as "new" -- not as one
# part-way through a migration.
# ---------------------------------------------------------------------------

from pangalactic.node.pangalaxian import Main, empty_home


def populate(home):
    """
    A home with everything empty_home() is supposed to remove, and two things
    it is not.
    """
    for name in ('VERSION', 'local.db', 'db.yaml', 'parameters.json',
                 'data_elements.json', 'prefs'):
        with open(os.path.join(home, name), 'w') as f:
            f.write('x')
    for name in ('cache', 'onto'):
        os.makedirs(os.path.join(home, name), exist_ok=True)
        with open(os.path.join(home, name, 'thing'), 'w') as f:
            f.write('x')


def test_10_empty_home_removes_the_derived_data(home):
    """
    CASE:  a home too old to migrate.  Everything derived from the
    repository goes, so the next sync rebuilds it.
    """
    populate(home)
    empty_home(home)
    for name in ('VERSION', 'local.db', 'parameters.json',
                 'data_elements.json'):
        assert not os.path.exists(os.path.join(home, name)), name
    for name in ('cache', 'onto'):
        assert not os.path.exists(os.path.join(home, name)), name


def test_11_empty_home_keeps_what_is_the_users(home):
    """
    CASE:  prefs are not derived from the repository and nothing about a
    schema requires losing them.
    """
    populate(home)
    empty_home(home)
    assert os.path.exists(os.path.join(home, 'prefs'))


def test_12_empty_home_removes_the_migration_dump(home):
    """
    CASE:  a stale db.yaml is left behind.

    It has to go.  If the home were emptied while a dump from an earlier
    migration remained, and anything then sent start-up into the migration
    branch, that dump would be reloaded over the freshly copied reference
    database -- putting back some of what was just discarded, out of date.
    """
    populate(home)
    empty_home(home)
    assert not os.path.exists(os.path.join(home, 'db.yaml'))


def test_13_empty_home_drops_the_recorded_schema_version(home):
    """
    CASE:  the state file records a schema version.

    It must not survive:  a home that has just been reset to the reference
    database is not one that needs migrating, and leaving the old version
    there would say it was.  The rest of the state is kept -- it is the
    user's session, not repository data.
    """
    populate(home)
    write_state_file(home, schema_version='3.6.0', project='H2G2')
    empty_home(home)
    with open(os.path.join(home, 'state')) as f:
        saved = yaml.safe_load(f.read())
    assert 'schema_version' not in saved
    assert saved.get('project') == 'H2G2'


def test_14_empty_home_survives_an_unreadable_state_file(home):
    """
    CASE:  the state file will not parse.  Start-up rewrites it in a moment
    anyway, so this is not worth failing over.
    """
    populate(home)
    with open(os.path.join(home, 'state'), 'w') as f:
        f.write('{[not: valid yaml')
    empty_home(home)          # must not raise
    assert not os.path.exists(os.path.join(home, 'local.db'))


def test_15_empty_home_on_a_home_that_is_not_there(home):
    """
    CASE:  nothing to empty.  First run, or a home already removed by hand.
    """
    empty_home(os.path.join(home, 'nope'))      # must not raise


def test_16_the_migratable_floor_is_below_the_compatible_versions(home):
    """
    CASE:  the two version settings are consistent with each other.

    A floor at or above the compatible versions would make every
    incompatible home "too old", quietly restoring the behaviour this
    replaced -- and the tests above would still pass.
    """
    assert Main.compat_versions
    assert all(Main.min_migratable_version < v for v in Main.compat_versions)
