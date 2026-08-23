# -*- coding: utf-8 -*-
"""
Unit tests for pangalactic.node.step_import, the CAD-facing half of the STEP
import.

Driven against the CAx-IF translator test files in pangalactic.core's test
data -- the same design exported by I-DEAS, Datakit/OpenCASCADE and
Pro/ENGINEER -- because the variation an importer has to survive is between
translators, not between application protocols.  See
NOTES_ON_STEP_IMPORT.md section 1.3.
"""
import os
import shutil
import tempfile
import unittest

from pangalactic.core.test import data as test_data_module
from pangalactic.node.step_import import (Occurrence, external_references,
                                          missing_references, read_assembly,
                                          scale_to_m, _ref_designators)

DATA = test_data_module.__path__[0]

# the same assembly through three vendors' translators
AS1_IDEAS = os.path.join(DATA, 'as1-id-203.stp')      # I-DEAS, AP203
AS1_DATAKIT = os.path.join(DATA, 'as1-oc-214.stp')    # Datakit/OCC, AP214
AS1_PROE = os.path.join(DATA, 'as1_pe_203.stp')       # Pro/ENGINEER, AP203
ALL_AS1 = (AS1_IDEAS, AS1_DATAKIT, AS1_PROE)

# exported as a set of thirteen files:  the assembly names four subassembly
# files, each of which names two part files
S1_PE = os.path.join(DATA, 's1-pe-214.stp')


class StepImportTest(unittest.TestCase):
    maxDiff = None

    def test_00_reads_an_assembly(self):
        """
        CASE:  the AS1 assembly reads as a tree with the expected shape
        """
        root = read_assembly(AS1_IDEAS)
        expected = [4, 28, 18]
        value = [len(root.children), len(list(root.walk())),
                 len(list(root.leaves()))]
        self.assertEqual(expected, value)

    def test_01_lengths_are_metres(self):
        """
        CASE:  placements come back in metres, not in the file's units.

        OCC converts a file's declared unit to mm; PGEF stores SI base units.
        AS1 is about 200 mm across, so every coordinate should be well under
        one metre.
        """
        root = read_assembly(AS1_IDEAS)
        coords = [abs(c) for occ in root.walk() if occ.placement
                  for c in occ.placement.location]
        expected = True
        value = max(coords) < 1.0
        self.assertEqual(expected, value)

    def test_02_default_scale_is_from_mm(self):
        """
        CASE:  the conversion factor matches OCC's default length unit
        """
        expected = 0.001
        value = scale_to_m()
        self.assertEqual(expected, value)

    def test_03_placements_are_parent_local(self):
        """
        CASE:  a nested occurrence's placement is expressed in its parent's
        frame, as STEP expresses it, so placements compose down the tree.

        The nut inside a nut-bolt assembly sits at a small offset from that
        assembly, not at its position in the whole of AS1.
        """
        root = read_assembly(AS1_IDEAS)
        # first sub-assembly that itself has sub-assemblies
        nested = [occ for occ in root.walk()
                  if occ.children and occ.placement][0]
        child = nested.children[0]
        # the child's placement is not simply the parent's
        expected = False
        value = child.placement.location == nested.placement.location
        self.assertEqual(expected, value)

    def test_04_repeated_use_shares_a_prototype(self):
        """
        CASE:  two usages of one product report the same prototype_key.

        This is the case the whole design turns on:  one product, several
        Acus, a different placement at each.
        """
        root = read_assembly(AS1_IDEAS)
        keys = [occ.prototype_key for occ in root.children]
        # the l-bracket assembly is used twice
        expected = True
        value = len(keys) > len(set(keys))
        self.assertEqual(expected, value)

    def test_05_reference_designators_are_unique_among_siblings(self):
        """
        CASE:  every assembly's components get distinct reference designators,
        in all three translators' exports.

        Pro/ENGINEER names occurrences after their prototype or not at all,
        so the file's names cannot be used directly.
        """
        results = []
        for path in ALL_AS1:
            root = read_assembly(path)
            ok = True
            for occ in root.walk():
                rds = [c.ref_des for c in occ.children]
                if len(rds) != len(set(rds)) or not all(rds):
                    ok = False
            results.append(ok)
        expected = [True, True, True]
        self.assertEqual(expected, results)

    def test_06_proe_names_are_not_used_verbatim(self):
        """
        CASE:  where a translator names each occurrence after its prototype,
        the reference designators are synthesized instead
        """
        root = read_assembly(AS1_PROE)
        brackets = [c for c in root.children
                    if c.prototype_name.startswith('L_BRACKET')]
        expected = [2, True]
        value = [len(brackets),
                 brackets[0].ref_des != brackets[1].ref_des]
        self.assertEqual(expected, value)

    def test_07_ref_designators_prefers_usable_file_names(self):
        """
        CASE:  names that are present and distinct are used as given
        """
        expected = ['RF', 'LF', 'RR', 'LR']
        value = _ref_designators(['RF', 'LF', 'RR', 'LR'],
                                 ['wheel'] * 4)
        self.assertEqual(expected, value)

    def test_08_ref_designators_synthesizes_when_names_collide(self):
        """
        CASE:  names that repeat, or are missing, are replaced
        """
        expected = ['wheel-1', 'wheel-2', 'wheel-3', 'wheel-4']
        value = _ref_designators(['wheel', 'wheel', 'wheel', 'wheel'],
                                 ['wheel'] * 4)
        self.assertEqual(expected, value)

    def test_09_volumes_are_cubic_metres(self):
        """
        CASE:  volumes are converted from OCC's units, and a leaf with no
        solid geometry reports None rather than zero
        """
        root = read_assembly(AS1_IDEAS, with_volumes=True)
        vols = [occ.volume for occ in root.leaves()]
        # AS1's plate is the biggest part, about 530 cm^3
        expected = [True, True]
        value = [all(v is None or 0 < v < 1e-3 for v in vols),
                 max(v for v in vols if v) > 1e-4]
        self.assertEqual(expected, value)

    def test_10_zero_volume_leaves_report_none(self):
        """
        CASE:  Pro/ENGINEER emits an empty COMPOUND beside each SOLID; those
        have no volume and must be distinguishable from a measured zero
        """
        root = read_assembly(AS1_PROE, with_volumes=True)
        vols = [occ.volume for occ in root.leaves()]
        expected = [True, True]
        value = [any(v is None for v in vols),
                 any(v is not None for v in vols)]
        self.assertEqual(expected, value)

    def test_11_prototypes_are_the_distinct_products(self):
        """
        CASE:  the prototype map names each distinct product once
        """
        root = read_assembly(AS1_IDEAS)
        protos = root.prototypes()
        expected = True
        # 18 leaf occurrences built from far fewer distinct products
        value = 0 < len(protos) < len(list(root.walk()))
        self.assertEqual(expected, value)

    def test_12_missing_file_raises(self):
        """
        CASE:  a file that cannot be read raises rather than returning an
        empty assembly
        """
        self.assertRaises(IOError, read_assembly,
                          os.path.join(DATA, 'no_such_file.stp'))

    # ---- external references ---------------------------------------------

    def test_13_finds_direct_external_references(self):
        """
        CASE:  the files a STEP assembly names are found.

        s1-pe-214.stp is exported as a set:  the assembly file names its four
        subassembly files through the AP214 external reference mechanism.
        """
        expected = ['foot_asm.stp', 'head_asm.stp', 'mainbody_asm.stp',
                    'tail_asm.stp']
        value = sorted(external_references(S1_PE))
        self.assertEqual(expected, value)

    def test_14_a_file_without_references_has_none(self):
        """
        CASE:  a self-contained file reports no references
        """
        expected = []
        value = external_references(AS1_IDEAS)
        self.assertEqual(expected, value)

    def test_15_nothing_missing_when_the_set_is_complete(self):
        """
        CASE:  with all thirteen files present, nothing is missing
        """
        expected = []
        value = missing_references(S1_PE)
        self.assertEqual(expected, value)

    def test_16_missing_references_are_reported_with_their_referrer(self):
        """
        CASE:  a file on its own reports what it needs, and which file needs
        it -- so the message can name both
        """
        with tempfile.TemporaryDirectory() as d:
            alone = os.path.join(d, os.path.basename(S1_PE))
            shutil.copy(S1_PE, alone)
            missing = missing_references(alone)
        expected = [4, ['foot_asm.stp', 'head_asm.stp', 'mainbody_asm.stp',
                        'tail_asm.stp']]
        value = [len(missing), sorted(n for n, _ in missing)]
        self.assertEqual(expected, value)
        self.assertTrue(all(r == alone for _, r in missing))

    def test_17_missing_references_are_transitive(self):
        """
        CASE:  a reference missing two levels down is still reported.

        With only the four subassemblies beside the top file, the eight part
        files they name are missing -- and they are named by the
        subassemblies, not by the top file.
        """
        with tempfile.TemporaryDirectory() as d:
            top = os.path.join(d, os.path.basename(S1_PE))
            shutil.copy(S1_PE, top)
            for name in ('mainbody_asm.stp', 'head_asm.stp', 'tail_asm.stp',
                         'foot_asm.stp'):
                shutil.copy(os.path.join(DATA, name), d)
            missing = missing_references(top)
        referrers = {os.path.basename(r) for _, r in missing}
        expected = [8, True]
        value = [len(missing), top not in {r for _, r in missing}]
        self.assertEqual(expected, value)
        self.assertNotIn(os.path.basename(S1_PE), referrers)

    def test_18_a_reference_cycle_terminates(self):
        """
        CASE:  files that reference each other do not loop for ever
        """
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, 'a.stp')
            b = os.path.join(d, 'b.stp')
            open(a, 'w').write("EXTERNAL_SOURCE(IDENTIFIER('b.stp'));")
            open(b, 'w').write("EXTERNAL_SOURCE(IDENTIFIER('a.stp'));")
            expected = []
            value = missing_references(a)
            self.assertEqual(expected, value)

if __name__ == '__main__':
    unittest.main()


# ---------------------------------------------------------------------------
# the reference closure
#
# missing_references() reports what is absent;  reference_closure() enumerates
# what is present, which is what has to be transferred for the assembly to be
# readable anywhere else.  Only the file the user chose used to be uploaded,
# so a round trip rendered whatever geometry was inline -- for these files,
# none at all.
# ---------------------------------------------------------------------------

def test_30_closure_of_a_file_that_references_nothing():
    """
    CASE:  a single-file assembly.  Nothing to transfer but itself.
    """
    from pangalactic.node.step_import import reference_closure
    assert reference_closure(AS1_IDEAS) == []


def test_31_closure_is_the_whole_set():
    """
    CASE:  s1-pe-214.stp, which is exported as thirteen files.  Every one of
    the other twelve is found, at both levels -- the four subassemblies it
    names, and the parts those name in turn.
    """
    from pangalactic.node.step_import import reference_closure
    found = reference_closure(S1_PE)
    names = [os.path.basename(c) for c, p in found]
    assert len(names) == 12, names
    # the subassemblies it names directly
    for name in ('mainbody_asm.stp', 'head_asm.stp', 'tail_asm.stp',
                 'foot_asm.stp'):
        assert name in names
    # ... and parts named by those, which is the level that proves recursion
    for name in ('main_body_back_prt.stp', 'head_front_prt.stp',
                 'tail_turbine_prt.stp', 'foot_back_prt.stp'):
        assert name in names


def test_32_closure_pairs_each_file_with_its_referrer():
    """
    CASE:  the referencing file comes back with each one.

    This is what "component_file_of" needs:  a part file belongs to the
    subassembly that names it, not to the top-level file.
    """
    from pangalactic.node.step_import import reference_closure
    by_child = {os.path.basename(c): os.path.basename(p)
                for c, p in reference_closure(S1_PE)}
    assert by_child['mainbody_asm.stp'] == 's1-pe-214.stp'
    assert by_child['main_body_back_prt.stp'] == 'mainbody_asm.stp'
    assert by_child['foot_front_prt.stp'] == 'foot_asm.stp'


def test_33_parents_come_before_children():
    """
    CASE:  ordering.  A caller creating an object per file links each to its
    referrer, which must therefore already exist -- so every referrer has to
    appear before anything it references.
    """
    from pangalactic.node.step_import import reference_closure
    found = reference_closure(S1_PE)
    seen = {os.path.realpath(S1_PE)}
    for child, parent in found:
        assert os.path.realpath(parent) in seen, (
            f'{os.path.basename(child)} comes before its referrer '
            f'{os.path.basename(parent)}')
        seen.add(os.path.realpath(child))


def test_34_a_file_reached_twice_appears_once():
    """
    CASE:  no duplicates.  "component_file_of" is functional, so a file has
    one referring file;  a part shared by two subassemblies is one file in
    the export set.
    """
    from pangalactic.node.step_import import reference_closure
    found = reference_closure(S1_PE)
    reals = [os.path.realpath(c) for c, p in found]
    assert len(reals) == len(set(reals))
    assert os.path.realpath(S1_PE) not in reals   # the root is not its own


def test_35_missing_files_are_left_out_not_raised(tmp_path):
    """
    CASE:  a file whose references are not beside it.  The closure is what
    can be found;  missing_references() is what reports the rest, and the
    importer refuses before it gets this far.
    """
    import shutil as _shutil
    from pangalactic.node.step_import import reference_closure
    lonely = str(tmp_path / os.path.basename(S1_PE))
    _shutil.copy(S1_PE, lonely)
    assert reference_closure(lonely) == []


def test_36_occ_follows_external_references_when_the_files_are_there(tmp_path):
    """
    CASE:  the same file read with its referenced files beside it, and
    without them.

    This pins a fact that was got wrong and stayed wrong for five days:  OCC
    *does* follow AP214 external references, provided the files resolve.  The
    original claim that it does not was based on reading a file separated
    from its set -- which is the second half of this test, and looks entirely
    plausible on its own.

    It matters because it is what makes the importer's refusal (section 5 of
    NOTES_ON_STEP_EXTERNAL_REFS.md) sufficient:  by refusing to read a file
    whose references do not resolve, the importer guarantees the condition
    under which the whole assembly is read.  If OCC's behaviour here ever
    changes, the planned-and-abandoned "graft the structure" work comes back,
    and this test is what would say so.
    """
    import shutil as _shutil
    from pangalactic.node.step_import import read_assembly

    def count(occ):
        return 1 + sum(count(c) for c in occ.children)

    whole = read_assembly(S1_PE)
    assert count(whole) > 30, 'the referenced files were not followed'
    assert all(c.children for c in whole.children), (
        'a subassembly came back empty with every file present')

    lonely = str(tmp_path / os.path.basename(S1_PE))
    _shutil.copy(S1_PE, lonely)
    alone = read_assembly(lonely)
    # the same five usages, and nothing under any of them
    assert len(alone.children) == len(whole.children)
    assert not any(c.children for c in alone.children)
    assert count(alone) < count(whole)
