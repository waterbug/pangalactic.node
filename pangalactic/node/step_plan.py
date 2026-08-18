# -*- coding: utf-8 -*-
"""
Plan a STEP import, so that the user can see and confirm what it will do
before anything is created or moved.

The user chooses the mode before the import begins:

* **PLACE** -- the assembly already exists in the repository and CAD supplies
  only where its components sit.  Occurrences are matched to existing Acus by
  reference designator and the user confirms the pairing.  Nothing is
  created except placements.

* **CREATE** -- the design exists only in CAD.  A HardwareProduct is proposed
  per distinct prototype and an Acu per occurrence, and the user confirms
  both sets.

Planning is separated from applying, and both are free of Qt, so what the
import will do can be tested without a dialog and reviewed without a
commitment.  `pangalactic.node.step_dialogs` presents a plan; this module
decides what is in one.
"""
import json

from pangalactic.core import orb
from pangalactic.core.names import get_acu_id, get_acu_name
from pangalactic.core.parametrics import get_dval, set_dval
from pangalactic.core.placements import (get_placement, new_thing,
                                         set_placement)
from pangalactic.core.utils.datetimes import dtstamp

# modes
PLACE = 'place'
CREATE = 'create'

# item kinds
PLACEMENT = 'placement'
PRODUCT = 'product'
ACU = 'acu'

# item statuses
MATCHED = 'matched'          # occurrence paired with an existing Acu
UNMATCHED = 'unmatched'      # occurrence has no counterpart in the assembly
UNPLACED = 'unplaced'        # Acu has no counterpart in the STEP file
NEW = 'new'                  # object would be created
REUSED = 'reused'            # an existing object would be used instead


class PlanItem:
    """
    One thing a STEP import proposes to do.

    Attributes:
        kind (str):  PLACEMENT, PRODUCT or ACU
        status (str):  MATCHED, UNMATCHED, UNPLACED, NEW or REUSED
        confirmed (bool):  whether the user has accepted this item.  Items
            start confirmed when the plan is unambiguous and unconfirmed when
            it is not, so that "accept all" is safe but a guess is never
            applied silently.
        path (str):  where in the assembly this sits, for display
        occurrence (Occurrence or None):  the STEP side
        acu (Acu or None):  the repository side, where one exists
        product (Product or None):  the existing product, where one was found
        note (str):  why this item is what it is, for display
        key (str):  for a PRODUCT item, the prototype_key it stands for
        parent_occurrence (Occurrence or None):  for an ACU item, the
            occurrence whose product is the assembly this Acu belongs to
    """

    def __init__(self, kind, status, path='', occurrence=None, acu=None,
                 product=None, note='', confirmed=None, key='',
                 parent_occurrence=None):
        self.kind = kind
        self.status = status
        self.path = path
        self.occurrence = occurrence
        self.acu = acu
        self.product = product
        self.note = note
        # for PRODUCT items, the prototype this stands for; for ACU items,
        # the occurrence whose product will be the assembly
        self.key = key
        self.parent_occurrence = parent_occurrence
        self.confirmed = (status in (MATCHED, NEW, REUSED)
                          if confirmed is None else confirmed)

    @property
    def actionable(self):
        """
        True if this item would change anything when applied.  UNMATCHED and
        UNPLACED items are reported so the user can see what the import does
        *not* cover; they are never applied.
        """
        return self.status in (MATCHED, NEW, REUSED)

    def __repr__(self):
        c = 'x' if self.confirmed else ' '
        return f'<[{c}] {self.kind} {self.status} {self.path!r}>'


def _norm(ref_des):
    """
    Normalize a reference designator for comparison.  CAD and the repository
    are maintained by different people in different tools, so matching is
    case- and whitespace-insensitive; the originals are kept for display.
    """
    return (ref_des or '').strip().casefold()


def plan_placements(root, assembly):
    """
    Plan a PLACE import:  pair the occurrences of a STEP assembly with the
    Acus of an existing assembly, by reference designator.

    Recurses through matched sub-assemblies, since an Acu's component is
    itself an assembly with its own Acus, and the STEP tree has the same
    shape.

    Args:
        root (Occurrence):  root of the tree from `step_import.read_assembly`
        assembly (Product):  the repository assembly to place

    Returns:
        list of PlanItem:  one per occurrence and one per Acu that has no
        occurrence, in tree order
    """
    items = []
    _plan_level(root.children, assembly, '', items)
    return items


def _plan_level(occurrences, assembly, path, items):
    """
    Pair one assembly's components with one occurrence list, then recurse.
    """
    acus = list(getattr(assembly, 'components', None) or [])
    by_ref = {}
    for acu in acus:
        by_ref.setdefault(_norm(acu.reference_designator), []).append(acu)
    used = set()
    for occ in occurrences:
        here = f'{path}/{occ.ref_des}' if path else occ.ref_des
        candidates = by_ref.get(_norm(occ.ref_des)) or []
        acu = None
        for c in candidates:
            if c.oid not in used:
                acu = c
                used.add(c.oid)
                break
        if acu is None:
            items.append(PlanItem(PLACEMENT, UNMATCHED, path=here,
                                  occurrence=occ,
                                  note='no component of this assembly has '
                                       'that reference designator'))
            continue
        items.append(PlanItem(PLACEMENT, MATCHED, path=here, occurrence=occ,
                              acu=acu,
                              note=f'reference designator '
                                   f'"{acu.reference_designator}"'))
        if occ.children:
            _plan_level(occ.children, acu.component, here, items)
    for acu in acus:
        if acu.oid not in used:
            here = (f'{path}/{acu.reference_designator}' if path
                    else acu.reference_designator)
            items.append(PlanItem(PLACEMENT, UNPLACED, path=here, acu=acu,
                                  note='no occurrence in the STEP file has '
                                       'that reference designator'))


def plan_creation(root, reuse_products=True):
    """
    Plan a CREATE import:  a HardwareProduct per distinct prototype and an Acu
    per occurrence.

    Args:
        root (Occurrence):  root of the tree from `step_import.read_assembly`

    Keyword Args:
        reuse_products (bool):  if True, a prototype whose name matches
            exactly one existing HardwareProduct is proposed as a reuse of it
            rather than as a new product

    Returns:
        list of PlanItem:  the product items first, then the Acu items, so a
        reviewer sees what will exist before what will be assembled
    """
    product_items = {}
    for key, name in root.prototypes().items():
        existing = _find_product(name) if reuse_products else None
        if existing is not None:
            item = PlanItem(PRODUCT, REUSED, path=name, product=existing,
                            key=key,
                            note=f'existing product "{existing.id}"')
        else:
            item = PlanItem(PRODUCT, NEW, path=name, key=key,
                            note='no existing product with this name')
        product_items[key] = item
    acu_items = []
    _plan_acus(root, root.children, '', acu_items)
    return list(product_items.values()) + acu_items


def _plan_acus(parent_occ, occurrences, path, items):
    for occ in occurrences:
        here = f'{path}/{occ.ref_des}' if path else occ.ref_des
        items.append(PlanItem(ACU, NEW, path=here, occurrence=occ,
                              parent_occurrence=parent_occ,
                              note=f'{occ.ref_des} of '
                                   f'"{occ.prototype_name}"'))
        _plan_acus(occ, occ.children, here, items)


def _find_product(name):
    """
    Find the one existing HardwareProduct with this name, or None if there is
    no such product or more than one -- an ambiguous name is not a match, and
    is left for the user to resolve.
    """
    if not name:
        return None
    found = orb.search_exact(cname='HardwareProduct', name=name)
    return found[0] if len(found) == 1 else None


class ImportResult:
    """
    What an import did.

    Attributes:
        created (list):  objects that did not exist before.
        modified (list):  objects that existed and were changed.  The
            distinction matters to the caller:  the repository is told about
            the two differently, and announcing a moved placement as new
            would misreport it.
        objects (list):  created + modified.  The caller is responsible for
            saving them; neither apply function commits.
        mapping (dict):  {occurrence path: oid}, the correspondence between
            the STEP file's occurrences and the repository's objects.

            **The key is the occurrence path, not the XCAF label entry.**
            Label entries are assigned in the order the exporter happened to
            write the file -- the same design through two translators gives
            `plate` the entry 0:1:1:2 in one and 0:1:1:9 in the other -- so a
            mapping keyed on them would point at the wrong part as soon as
            the model were re-exported.  The path is semantic, and stable for
            as long as the reference designators are, which is the same
            assumption the matching itself rests on.
        skipped (list of PlanItem):  items that were not applied, either
            because the user did not confirm them or because they had nothing
            to apply.
    """

    def __init__(self):
        self.created = []
        self.modified = []
        self.mapping = {}
        self.skipped = []

    @property
    def objects(self):
        return self.created + self.modified

    def __repr__(self):
        return (f'<ImportResult {len(self.created)} created, '
                f'{len(self.modified)} modified, '
                f'{len(self.mapping)} mapped, {len(self.skipped)} skipped>')


def apply_placements(items, NOW=None):
    """
    Apply the confirmed items of a PLACE plan.

    Args:
        items (list of PlanItem):  the plan, as confirmed by the user

    Keyword Args:
        NOW (datetime):  timestamp for the new or modified objects

    Returns:
        ImportResult
    """
    NOW = NOW or dtstamp()
    result = ImportResult()
    for item in items:
        if not (item.confirmed and item.actionable) or item.kind != PLACEMENT:
            result.skipped.append(item)
            continue
        if item.occurrence.placement is None:
            result.skipped.append(item)
            continue
        # an Acu that had no placement gains new objects; one that had a
        # placement has it moved, which is a modification
        was_placed = get_placement(item.acu) is not None
        touched = set_placement(item.acu, item.occurrence.placement, NOW=NOW)
        if was_placed:
            result.modified += touched
        else:
            result.created += touched
        result.mapping[item.path] = item.acu.oid
    return result


def apply_creation(items, owner=None, NOW=None):
    """
    Apply the confirmed items of a CREATE plan:  create the products that do
    not exist, then the Acus that assemble them, then place them.

    An Acu is created only if the products at both ends of it were confirmed;
    an unconfirmed product therefore drops the usages that depend on it,
    which are reported in `skipped` rather than created with a dangling end.

    Args:
        items (list of PlanItem):  the plan, as confirmed by the user

    Keyword Args:
        owner (Organization):  owner for newly created products
        NOW (datetime):  timestamp for the new objects

    Returns:
        ImportResult
    """
    # imported here rather than at module scope:  clone imports the orb and
    # much of the parametrics machinery, and planning must stay cheap
    from pangalactic.core.clone import clone
    NOW = NOW or dtstamp()
    result = ImportResult()
    products = {}
    for item in items:
        if item.kind != PRODUCT:
            continue
        if not (item.confirmed and item.actionable):
            result.skipped.append(item)
            continue
        if item.status == REUSED:
            products[item.key] = item.product
            result.mapping[item.path] = item.product.oid
            continue
        kw = dict(name=item.path, save_hw=False)
        if owner is not None:
            kw['owner'] = owner
        product = clone('HardwareProduct', **kw)
        products[item.key] = product
        result.created.append(product)
        result.mapping[item.path] = product.oid
    for item in items:
        if item.kind != ACU:
            continue
        occ, parent = item.occurrence, item.parent_occurrence
        assembly = products.get(getattr(parent, 'prototype_key', None))
        component = products.get(occ.prototype_key)
        if not (item.confirmed and item.actionable) or not (assembly and
                                                            component):
            result.skipped.append(item)
            continue
        acu = new_thing('Acu', NOW=NOW,
                        id=get_acu_id(assembly.id, occ.ref_des),
                        name=get_acu_name(assembly.name, occ.ref_des),
                        assembly=assembly, component=component,
                        reference_designator=occ.ref_des)
        result.created.append(acu)
        result.mapping[item.path] = acu.oid
        if occ.placement is not None:
            result.created += set_placement(acu, occ.placement, NOW=NOW)
    return result


# ---------------------------------------------------------------------------
# The correspondence between a STEP file and the objects imported from it.
#
# Kept as a data element on the RepresentationFile the STEP file was stored
# as -- RepresentationFile is a Modelable, so this needs no ontology change,
# it syncs with the file object, and a new version of the file gets its own
# correspondence.
# ---------------------------------------------------------------------------

# id of the DataElementDefinition in pangalactic.core.refdata
CORRESPONDENCE_DEID = 'step_correspondence'

# bumped if the stored structure changes in a way readers must notice
CORRESPONDENCE_VERSION = 1


def get_correspondence(rep_file):
    """
    Get the stored correspondence for a STEP file.

    Args:
        rep_file (RepresentationFile):  the stored STEP file

    Returns:
        dict:  the stored structure, or {} if the file has never been
        imported or what is stored cannot be read.  A correspondence that
        will not parse is treated as absent rather than raising:  it is
        cached bookkeeping, and losing it costs a re-match, not data.
    """
    raw = get_dval(getattr(rep_file, 'oid', None), CORRESPONDENCE_DEID)
    if not raw:
        return {}
    try:
        stored = json.loads(raw)
    except (ValueError, TypeError):
        orb.log.warning('* step: unreadable correspondence on '
                        f'"{getattr(rep_file, "id", "?")}", ignoring it')
        return {}
    return stored if isinstance(stored, dict) else {}


def set_correspondence(rep_file, result, mode, checksum='', NOW=None):
    """
    Store the correspondence produced by an import.

    Args:
        rep_file (RepresentationFile):  the stored STEP file
        result (ImportResult):  what the import did
        mode (str):  PLACE or CREATE

    Keyword Args:
        checksum (str):  the checksum of the file as imported, so that a
            later import can tell whether it is reading the same file
        NOW (datetime):  timestamp recorded as the import time

    Returns:
        dict:  the structure that was stored
    """
    stored = {'version': CORRESPONDENCE_VERSION,
              'mode': mode,
              'imported': str(NOW or dtstamp()),
              'checksum': checksum or getattr(rep_file, 'checksum', '') or '',
              'map': dict(result.mapping)}
    set_dval(rep_file.oid, CORRESPONDENCE_DEID, json.dumps(stored))
    return stored


def file_has_changed(rep_file, checksum):
    """
    Say whether a STEP file differs from the one a stored correspondence was
    built against.

    A changed file may have gained, lost or renamed parts, so re-matching it
    silently could move components that were placed deliberately.  The caller
    is expected to stop and ask rather than re-import on this answer.

    Args:
        rep_file (RepresentationFile):  the stored STEP file
        checksum (str):  checksum of the file about to be imported

    Returns:
        bool:  True if there is a stored correspondence and it was built
        against a different file.  False if there is none -- nothing to
        contradict -- or if the checksums agree, or if either checksum is
        unknown, since an absent checksum is not evidence of a change.
    """
    stored = get_correspondence(rep_file)
    if not stored:
        return False
    was = stored.get('checksum') or ''
    return bool(was and checksum and was != checksum)
