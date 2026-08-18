# -*- coding: utf-8 -*-
"""
Unit tests for pangalactic.node.step_plan -- planning a STEP import and
applying the plan the user confirmed.

The planner is deliberately free of Qt, so what an import would do can be
tested without a dialog.
"""
import os
import unittest

# set the orb
import pangalactic.core.set_uberorb

from pangalactic.core import orb
from pangalactic.core.placements import get_placement
from pangalactic.core.serializers import deserialize
from pangalactic.core.test import data as test_data_module
from pangalactic.core.test.utils import create_test_users, create_test_project

HOME = 'step_plan_test'
orb.start(home=HOME)
deserialize(orb, create_test_users() + create_test_project())

from pangalactic.node.step_import import Occurrence, Placement
from pangalactic.node.step_plan import (ACU, CREATE, MATCHED, NEW, PLACE,
                                        PLACEMENT, PRODUCT, REUSED, UNMATCHED,
                                        UNPLACED, apply_creation,
                                        apply_placements, file_has_changed,
                                        get_correspondence, plan_creation,
                                        plan_placements, set_correspondence)

DATA = test_data_module.__path__[0]
AS1 = os.path.join(DATA, 'as1-id-203.stp')


def occ(ref_des, prototype_key='p', prototype_name='Part', children=(),
        placement=None):
    """
    Build an Occurrence without needing a STEP file, so the planner's
    behaviour can be stated directly.
    """
    return Occurrence(name=ref_des, ref_des=ref_des,
                      prototype_key=prototype_key,
                      prototype_name=prototype_name,
                      placement=placement or Placement((0.0, 0.0, 0.0),
                                                       (0.0, 0.0, 1.0),
                                                       (1.0, 0.0, 0.0)),
                      children=list(children))


class StepPlanTest(unittest.TestCase):
    maxDiff = None

    # the test project's spacecraft0 and one of its component usages
    ASSEMBLY_OID = 'test:spacecraft0'
    ACU_OID = 'test:H2G2:acu-sc0-propsys'

    def _assembly(self):
        return orb.get(self.ASSEMBLY_OID)

    def test_00_matching_ref_des_is_matched(self):
        """
        CASE:  an occurrence whose reference designator matches a component of
        the assembly is paired with that component's Acu
        """
        acu = orb.get(self.ACU_OID)
        root = occ('root', children=[occ(acu.reference_designator)])
        items = plan_placements(root, self._assembly())
        matched = [i for i in items if i.status == MATCHED]
        expected = [1, acu.oid]
        value = [len(matched), matched[0].acu.oid]
        self.assertEqual(expected, value)

    def test_01_matching_ignores_case_and_whitespace(self):
        """
        CASE:  CAD and the repository are maintained by different people in
        different tools, so the pairing is not case sensitive
        """
        acu = orb.get(self.ACU_OID)
        root = occ('root',
                   children=[occ(f'  {acu.reference_designator.upper()} ')])
        items = plan_placements(root, self._assembly())
        expected = [MATCHED]
        value = [i.status for i in items if i.occurrence]
        self.assertEqual(expected, value)

    def test_02_unknown_ref_des_is_unmatched(self):
        """
        CASE:  an occurrence with no counterpart in the assembly is reported,
        not guessed at
        """
        root = occ('root', children=[occ('NOT-IN-THE-ASSEMBLY')])
        items = plan_placements(root, self._assembly())
        unmatched = [i for i in items if i.status == UNMATCHED]
        expected = [1, False]
        value = [len(unmatched), unmatched[0].confirmed]
        self.assertEqual(expected, value)

    def test_03_acus_without_occurrences_are_reported(self):
        """
        CASE:  components of the assembly that the STEP file says nothing
        about are listed, so the user can see what the import will not cover
        """
        root = occ('root', children=[])
        items = plan_placements(root, self._assembly())
        expected = True
        value = (len(items) > 0 and
                 all(i.status == UNPLACED for i in items))
        self.assertEqual(expected, value)

    def test_04_unmatched_items_are_never_applied(self):
        """
        CASE:  applying a plan does nothing for items that were not matched,
        even if something set their confirmed flag
        """
        root = occ('root', children=[occ('NOT-IN-THE-ASSEMBLY')])
        items = plan_placements(root, self._assembly())
        for item in items:
            item.confirmed = True
        result = apply_placements(items)
        expected = [0, 0]
        value = [len(result.objects), len(result.mapping)]
        self.assertEqual(expected, value)

    def test_05_applying_a_match_places_the_component(self):
        """
        CASE:  a confirmed match gives the Acu the occurrence's placement
        """
        acu = orb.get(self.ACU_OID)
        p = Placement((1.5, 2.5, 3.5), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        root = occ('root', children=[occ(acu.reference_designator,
                                         placement=p)])
        items = plan_placements(root, self._assembly())
        result = apply_placements(items)
        orb.db.commit()
        expected = [p, True]
        value = [get_placement(acu), len(result.objects) == 2]
        self.assertEqual(expected, value)

    def test_06_unconfirmed_matches_are_not_applied(self):
        """
        CASE:  a match the user rejected leaves the component where it was
        """
        acu = orb.get(self.ACU_OID)
        before = get_placement(acu)
        p = Placement((9.9, 9.9, 9.9), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0))
        root = occ('root', children=[occ(acu.reference_designator,
                                         placement=p)])
        items = plan_placements(root, self._assembly())
        for item in items:
            item.confirmed = False
        apply_placements(items)
        orb.db.commit()
        expected = before
        value = get_placement(acu)
        self.assertEqual(expected, value)

    def test_07_mapping_is_keyed_on_path_not_label_entry(self):
        """
        CASE:  the persisted correspondence is keyed on the occurrence path.

        XCAF label entries are assigned in the order the exporter wrote the
        file -- two translators give the same part different entries -- so a
        mapping keyed on them would point at the wrong part after a
        re-export.
        """
        acu = orb.get(self.ACU_OID)
        root = occ('root', children=[occ(acu.reference_designator)])
        items = plan_placements(root, self._assembly())
        result = apply_placements(items)
        orb.db.commit()
        expected = {acu.reference_designator: acu.oid}
        value = result.mapping
        self.assertEqual(expected, value)

    def test_08_nested_paths_are_qualified(self):
        """
        CASE:  a nested occurrence's path includes its parents, so two
        components with the same designator in different sub-assemblies do
        not collide
        """
        acu = orb.get(self.ACU_OID)
        child = occ('INNER')
        root = occ('root', children=[occ(acu.reference_designator,
                                         children=[child])])
        items = plan_placements(root, self._assembly())
        paths = [i.path for i in items if i.occurrence is child]
        expected = [f'{acu.reference_designator}/INNER']
        value = paths
        self.assertEqual(expected, value)

    # ---- CREATE mode -----------------------------------------------------

    def test_09_creation_proposes_a_product_per_prototype(self):
        """
        CASE:  a create plan proposes one product per distinct prototype and
        one Acu per occurrence
        """
        root = occ('root', prototype_key='k0', prototype_name='Assembly X',
                   children=[occ('A', 'k1', 'Widget'),
                             occ('B', 'k1', 'Widget'),
                             occ('C', 'k2', 'Gadget')])
        items = plan_creation(root)
        products = [i for i in items if i.kind == PRODUCT]
        acus = [i for i in items if i.kind == ACU]
        # three distinct prototypes (the root, Widget, Gadget), three usages
        expected = [3, 3]
        value = [len(products), len(acus)]
        self.assertEqual(expected, value)

    def test_10_creation_reuses_an_existing_product_by_name(self):
        """
        CASE:  a prototype whose name matches exactly one existing product is
        proposed as a reuse of it, rather than as a duplicate
        """
        existing = orb.search_exact(cname='HardwareProduct',
                                    name='Honeywell HR04')[0]
        root = occ('root', prototype_key='k0', prototype_name='Assembly Y',
                   children=[occ('A', 'k1', existing.name)])
        items = plan_creation(root)
        reused = [i for i in items if i.status == REUSED]
        expected = [1, existing.oid]
        value = [len(reused), reused[0].product.oid]
        self.assertEqual(expected, value)

    def test_10a_an_ambiguous_name_is_not_a_reuse(self):
        """
        CASE:  a prototype name held by more than one product is proposed as
        a new product, not matched to an arbitrary one of them.

        The test project has three products named "Rocinante Spacecraft",
        which is exactly the situation where guessing would be wrong.
        """
        dupes = orb.search_exact(cname='HardwareProduct',
                                 name='Rocinante Spacecraft')
        root = occ('root', prototype_key='k0', prototype_name='Assembly Z',
                   children=[occ('A', 'k1', 'Rocinante Spacecraft')])
        items = plan_creation(root)
        statuses = [i.status for i in items
                    if i.kind == PRODUCT and i.path == 'Rocinante Spacecraft']
        expected = [True, [NEW]]
        value = [len(dupes) > 1, statuses]
        self.assertEqual(expected, value)

    def test_11_applying_creation_builds_the_assembly(self):
        """
        CASE:  applying a create plan makes the products, the Acus that
        assemble them, and their placements
        """
        p = Placement((0.4, 0.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0))
        root = occ('root', prototype_key='r', prototype_name='Sled Assembly',
                   children=[occ('RF', 'w', 'Sled Wheel', placement=p)])
        items = plan_creation(root)
        result = apply_creation(items)
        orb.db.commit()
        acu_items = [i for i in items if i.kind == ACU]
        acu = orb.get(result.mapping[acu_items[0].path])
        expected = ['Sled Assembly', 'Sled Wheel', 'RF', p]
        value = [acu.assembly.name, acu.component.name,
                 acu.reference_designator, get_placement(acu)]
        self.assertEqual(expected, value)

    def test_12_an_unconfirmed_product_drops_its_usages(self):
        """
        CASE:  an Acu is not created with a dangling end.

        If the user declines a product, the usages that depend on it are
        skipped rather than created pointing at nothing.
        """
        root = occ('root', prototype_key='r2', prototype_name='Rig Assembly',
                   children=[occ('X', 'wx', 'Rig Widget')])
        items = plan_creation(root)
        for item in items:
            if item.kind == PRODUCT and item.path == 'Rig Widget':
                item.confirmed = False
        result = apply_creation(items)
        orb.db.commit()
        expected = [0, True]
        value = [len([i for i in items
                      if i.kind == ACU and i.path in result.mapping]),
                 any(i.kind == ACU for i in result.skipped)]
        self.assertEqual(expected, value)

    def test_12a_shared_prototype_structure_is_planned_once(self):
        """
        CASE:  a sub-assembly used twice yields one set of components, not
        one per use.

        The reader expands the tree by descending into a prototype at every
        use of it, so the children of a prototype used twice appear twice.
        They are one product with one set of components:  planning an Acu per
        occurrence would hang two copies of every child off the one product,
        and a later PLACE import would then report the surplus as missing
        from the file.
        """
        inner = [occ('N', 'nut', 'Nut'), occ('B', 'bolt', 'Bolt')]
        root = occ('root', prototype_key='asm', prototype_name='Rig',
                   children=[occ('P1', 'pair', 'Pair', inner),
                             occ('P2', 'pair', 'Pair', inner)])
        items = plan_creation(root, reuse_products=False)
        acus = [i for i in items if i.kind == ACU]
        # two uses of "Pair", plus the two components Pair is made of
        expected = 4
        value = len(acus)
        self.assertEqual(expected, value)

    def test_12b_shared_prototype_matches_once_when_placing(self):
        """
        CASE:  the same, for a PLACE import -- the components of a shared
        sub-assembly are paired once, not once per use
        """
        inner = [occ('N', 'nut', 'Nut'), occ('B', 'bolt', 'Bolt')]
        root = occ('root', prototype_key='asm', prototype_name='Rig2',
                   children=[occ('P1', 'pair', 'Pair2', inner),
                             occ('P2', 'pair', 'Pair2', inner)])
        result = apply_creation(plan_creation(root, reuse_products=False))
        orb.db.commit()
        top = [o for o in result.created
               if type(o).__name__ == 'HardwareProduct'
               and o.name == 'Rig2'][0]
        items = plan_placements(root, top)
        expected = [4, 0]
        value = [len([i for i in items if i.status == MATCHED]),
                 len([i for i in items if i.status == UNPLACED])]
        self.assertEqual(expected, value)

    def test_13_plans_a_real_step_file(self):
        """
        CASE:  a create plan for the AS1 test assembly proposes one product
        per distinct prototype and one usage per component of each.

        AS1 is 9 prototypes assembled as 4 + 4 + 2 + 3 = 13 usages.  That is
        fewer than its 27 occurrences, because "l-bracket assy" is used twice
        and "nut-bolt assy" six times, and each is one product with one set
        of components however often it is used.
        """
        from pangalactic.node.step_import import read_assembly
        root = read_assembly(AS1)
        items = plan_creation(root, reuse_products=False)
        products = [i for i in items if i.kind == PRODUCT]
        acus = [i for i in items if i.kind == ACU]
        expected = [9, 13, 27]
        value = [len(products), len(acus), len(list(root.walk())) - 1]
        self.assertEqual(expected, value)

    # ---- the stored correspondence ---------------------------------------

    def _rep_file(self, name='step-corr-test'):
        """
        A RepresentationFile to hang a correspondence on.
        """
        from pangalactic.core.placements import new_thing
        return new_thing('RepresentationFile', id=name, name=name,
                         user_file_name=f'{name}.stp')

    def test_14_no_correspondence_on_a_fresh_file(self):
        """
        CASE:  a file that has never been imported has no correspondence
        """
        expected = {}
        value = get_correspondence(self._rep_file('fresh'))
        self.assertEqual(expected, value)

    def test_15_correspondence_round_trips(self):
        """
        CASE:  what an import stored comes back, keyed on occurrence path
        """
        acu = orb.get(self.ACU_OID)
        root = occ('root', children=[occ(acu.reference_designator)])
        items = plan_placements(root, self._assembly())
        result = apply_placements(items)
        rf = self._rep_file('round-trip')
        set_correspondence(rf, result, PLACE, checksum='abc123')
        orb.db.commit()
        stored = get_correspondence(rf)
        expected = [PLACE, 'abc123', {acu.reference_designator: acu.oid}]
        value = [stored['mode'], stored['checksum'], stored['map']]
        self.assertEqual(expected, value)

    def test_16_unchanged_file_is_not_flagged(self):
        """
        CASE:  re-importing the same file is not treated as a change
        """
        rf = self._rep_file('same-file')
        set_correspondence(rf, apply_placements([]), PLACE, checksum='abc123')
        orb.db.commit()
        expected = False
        value = file_has_changed(rf, 'abc123')
        self.assertEqual(expected, value)

    def test_17_changed_file_is_flagged(self):
        """
        CASE:  a re-export is detected, so the caller can stop and ask.

        A changed file may have gained, lost or renamed parts, and silently
        re-matching it could move components that were placed deliberately.
        """
        rf = self._rep_file('changed-file')
        set_correspondence(rf, apply_placements([]), PLACE, checksum='abc123')
        orb.db.commit()
        expected = True
        value = file_has_changed(rf, 'def456')
        self.assertEqual(expected, value)

    def test_18_unknown_checksum_is_not_a_change(self):
        """
        CASE:  an absent checksum on either side is not evidence of a change.

        Reporting "changed" for a file we simply cannot compare would train
        the user to click through the warning.
        """
        rf = self._rep_file('no-checksum')
        set_correspondence(rf, apply_placements([]), PLACE, checksum='')
        orb.db.commit()
        expected = [False, False]
        value = [file_has_changed(rf, 'abc123'),
                 file_has_changed(self._rep_file('other'), '')]
        self.assertEqual(expected, value)

    def test_19_unreadable_correspondence_is_treated_as_absent(self):
        """
        CASE:  a correspondence that will not parse does not break the import.

        It is cached bookkeeping; losing it costs a re-match, not data.
        """
        from pangalactic.core.parametrics import set_dval
        rf = self._rep_file('corrupt')
        set_dval(rf.oid, 'step_correspondence', 'not json at all')
        orb.db.commit()
        expected = [{}, False]
        value = [get_correspondence(rf), file_has_changed(rf, 'abc123')]
        self.assertEqual(expected, value)


if __name__ == '__main__':
    unittest.main()
