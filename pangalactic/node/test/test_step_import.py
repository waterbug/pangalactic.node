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
import unittest

from pangalactic.core.test import data as test_data_module
from pangalactic.node.step_import import (Occurrence, read_assembly,
                                          scale_to_m, _ref_designators)

DATA = test_data_module.__path__[0]

# the same assembly through three vendors' translators
AS1_IDEAS = os.path.join(DATA, 'as1-id-203.stp')      # I-DEAS, AP203
AS1_DATAKIT = os.path.join(DATA, 'as1-oc-214.stp')    # Datakit/OCC, AP214
AS1_PROE = os.path.join(DATA, 'as1_pe_203.stp')       # Pro/ENGINEER, AP203
ALL_AS1 = (AS1_IDEAS, AS1_DATAKIT, AS1_PROE)


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


if __name__ == '__main__':
    unittest.main()
