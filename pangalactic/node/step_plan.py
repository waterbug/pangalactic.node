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
import re

from pangalactic.core import orb, state
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
        is_root (bool):  True for the PRODUCT item standing for the file's
            top-level assembly
        product_type (ProductType or None):  for a PRODUCT item with status
            NEW, the type to assign the new product.  STEP carries nothing
            that implies a type, so this starts as the "unclassified"
            placeholder and is presented for the user to change per item --
            it is not guessed at.  None for a REUSED item, whose type is
            whatever the existing product already has.
    """

    def __init__(self, kind, status, path='', occurrence=None, acu=None,
                 product=None, note='', confirmed=None, key='',
                 parent_occurrence=None, product_type=None, is_root=False,
                 new_version_of=None):
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
        self.product_type = product_type
        # True for the PRODUCT item standing for the file's top-level
        # assembly -- the only one that could become a system of the project
        self.is_root = is_root
        # for a PRODUCT item that is a new *version* of something, the
        # product it is a version of.  The item is still NEW -- a version is
        # a new object -- but it is created by versioning that one rather
        # than from nothing.
        self.new_version_of = new_version_of
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
    _plan_level(root.children, assembly, '', items, set())
    return items


def _plan_level(occurrences, assembly, path, items, seen):
    """
    Pair one assembly's components with one occurrence list, then recurse.

    `seen` holds the prototypes whose contents have already been planned.  It
    starts empty:  the root's own prototype never needs to be in it, since an
    assembly cannot contain itself, and seeding it would suppress a child
    that happened to share the root's prototype key.  A
    prototype used twice is one product with one set of components, and its
    contents are the same wherever it is used -- a nut sits in the same place
    within a nut-bolt assembly however many of those the design contains --
    so planning it once per use would pair the same Acus repeatedly and
    report the surplus as missing.
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
        if occ.children and occ.prototype_key not in seen:
            seen.add(occ.prototype_key)
            _plan_level(occ.children, acu.component, here, items, seen)
    for acu in acus:
        if acu.oid not in used:
            here = (f'{path}/{acu.reference_designator}' if path
                    else acu.reference_designator)
            items.append(PlanItem(PLACEMENT, UNPLACED, path=here, acu=acu,
                                  note='no occurrence in the STEP file has '
                                       'that reference designator'))


def plan_creation(root, reuse_products=True, new_version_of=None):
    """
    Plan a CREATE import:  a HardwareProduct per distinct prototype and an Acu
    per occurrence.

    Args:
        root (Occurrence):  root of the tree from `step_import.read_assembly`

    Keyword Args:
        reuse_products (bool):  if True, a prototype whose name matches
            exactly one existing HardwareProduct is proposed as a reuse of it
            rather than as a new product
        new_version_of (Product):  if given, the file is a later revision of
            this product, and the import makes a new *version* of it rather
            than a new product.  Components are then reused wherever their
            name matches, since only the assembled product is versioned --
            see the Acu rule below.

    Returns:
        list of PlanItem:  the product items first, then the Acu items, so a
        reviewer sees what will exist before what will be assembled
    """
    unclassified = orb.get('pgefobjects:ProductType.unclassified')
    # A version import reuses everything it can:  a component that has not
    # changed is the same component, and only the product being versioned
    # gets a new version.
    #
    # NOTE: "has not changed" is decided by _find_product(), which matches on
    # name -- so a sub-assembly that was revised but kept its name is treated
    # as unchanged, and its own revision is not carried in.  Accepted for now
    # (author, 2026-09-13);  doing better means comparing the file's
    # structure against the stored correspondence, which is a larger piece of
    # work and complicated further by components that come from referenced
    # external files.
    reuse_products = reuse_products or new_version_of is not None
    product_items = {}
    for key, name in root.prototypes().items():
        is_root = (key == root.prototype_key)
        if is_root and new_version_of is not None:
            v = getattr(new_version_of, 'version', None) or '[no version]'
            item = PlanItem(PRODUCT, NEW, path=name, key=key, is_root=True,
                            product=new_version_of,
                            new_version_of=new_version_of,
                            note=f'new version of "{new_version_of.id}" '
                                 f'(currently {v})')
            product_items[key] = item
            continue
        existing = _find_product(name) if reuse_products else None
        if existing is not None:
            item = PlanItem(PRODUCT, REUSED, path=name, product=existing,
                            key=key, is_root=is_root,
                            note=f'existing product "{existing.id}"')
        else:
            item = PlanItem(PRODUCT, NEW, path=name, key=key,
                            product_type=unclassified, is_root=is_root,
                            note='no existing product with this name -- '
                                 'assign a product type below')
        product_items[key] = item
    acu_items = []
    _plan_acus(root, root.children, '', acu_items, set(), product_items)
    return list(product_items.values()) + acu_items


def _plan_acus(parent_occ, occurrences, path, items, seen, product_items):
    """
    Propose an Acu per occurrence, once per distinct prototype, wherever the
    assembly end of it is a product this import creates.

    The reader expands the tree by descending into a prototype at every use
    of it, so the children of a prototype used six times appear six times.
    They are one product with one set of components, though:  planning an Acu
    per occurrence would hang six copies of "nut" off the one nut-bolt
    assembly.  `seen` holds the prototypes already accounted for.

    **An Acu is proposed only where its assembly is being created.**  If the
    assembly end is an existing product the import is reusing, that product
    already has its components and creating them again would give it two of
    each.  For an ordinary import every product is new, so every Acu is
    proposed and this changes nothing;  for a version import only the
    versioned product is new, so the top-level usages are created -- they
    must be, since their assembly is now the new version -- and everything
    below is left as it stands, both ends of it being unchanged (author's
    rule, 2026-09-13).
    """
    parent_item = product_items.get(getattr(parent_occ, 'prototype_key',
                                            None))
    parent_is_new = getattr(parent_item, 'status', None) == NEW
    for occ in occurrences:
        here = f'{path}/{occ.ref_des}' if path else occ.ref_des
        if parent_is_new:
            items.append(PlanItem(ACU, NEW, path=here, occurrence=occ,
                                  parent_occurrence=parent_occ,
                                  note=f'{occ.ref_des} of '
                                       f'"{occ.prototype_name}"'))
        if occ.children and occ.prototype_key not in seen:
            seen.add(occ.prototype_key)
            _plan_acus(occ, occ.children, here, items, seen, product_items)


def _find_product(name):
    """
    Find an existing HardwareProduct this prototype may reuse, or None.

    A specification controlled by another project is **not** a candidate.  In
    PGEF a spec's owner controls it, including its configuration management,
    and the standing assumption is that one project does not use another
    project's spec:  the way to take one up is to clone it, producing a new
    spec the second project owns and may modify.  So reuse is offered only
    for specs that are genuinely shareable --

    * `public` ones:  the standard library, vendor-owned COTS specs, and the
      public standards (SAE, MIL-SPEC and the like) that piece parts such as
      nuts and bolts are governed by;
    * the current project's own specs.

    **Visibility is a proxy for provenance, because a STEP file carries no
    provenance at all.**  Whoever exports one generally regards the ownership
    of the specs it contains as out of scope, so an importer cannot tell a
    standardised bolt from a bespoke bracket.  The level would be the real
    discriminator -- piece parts are public, boxes are often COTS, subsystems
    and assemblies are usually project-controlled -- and it is not inferable
    from the file.  The conservative reading is therefore taken:  anything
    that is not already shareable becomes a new spec owned by the importing
    project, to be corrected later when better information appears.

    An ambiguous name is still not a match, and is left for the user.

    Args:
        name (str):  the prototype name

    Returns:
        HardwareProduct or None
    """
    if not name:
        return None
    found = orb.search_exact(cname='HardwareProduct', name=name)
    project_oid = state.get('project') or ''
    reusable = [p for p in found
                if getattr(p, 'public', False)
                or (project_oid
                    and getattr(p.owner, 'oid', '') == project_oid)]
    return reusable[0] if len(reusable) == 1 else None


def product_key(item):
    """
    The correspondence key for a PRODUCT plan item.

    A PRODUCT item's `path` is the prototype's *name*, which is what a
    reviewer wants to read -- but names are not unique.  Pro/ENGINEER emits
    eight prototypes named "SOLID" or "COMPOUND" in the AS1 assembly alone,
    and keying the map on the name silently collapsed them:  an import that
    created 19 products recorded 11.  That is exactly the confusion the
    correspondence exists to prevent, so products are keyed on the prototype
    itself.

    The prefix distinguishes a product entry from a usage entry, whose key is
    an occurrence path, and would otherwise be free to collide with it.

    Args:
        item (PlanItem):  a PRODUCT item

    Returns:
        str:  its key in ImportResult.mapping
    """
    return f'prototype:{item.key}'


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


def apply_placements(items, NOW=None, progress=None):
    """
    Apply the confirmed items of a PLACE plan.

    Args:
        items (list of PlanItem):  the plan, as confirmed by the user

    Keyword Args:
        NOW (datetime):  timestamp for the new or modified objects
        progress (callable):  called as progress(done, total) after each item
            is handled, so a caller can drive a progress bar.  Optional:  this
            module has no Qt dependency and does not acquire one here.

    Returns:
        ImportResult
    """
    NOW = NOW or dtstamp()
    result = ImportResult()
    done, total = 0, len(items)
    for item in items:
        done += 1
        if progress is not None:
            progress(done, total)
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


def add_project_system(product, project, NOW=None):
    """
    Make a product a system of a project, by creating a ProjectSystemUsage.

    Follows the convention established by the block modeler, which is the
    only other place a PSU is created (dropping a product onto a Project
    block):  same id and name forms, and system_role taken from the product
    type so the System Tree labels it usefully.

    Args:
        product (Product):  the system
        project (Project):  the project it is used on

    Keyword Args:
        NOW (datetime):  timestamp for the new object

    Returns:
        ProjectSystemUsage or None:  None if the product is already a system
        of that project, since a second PSU would put it in the tree twice
    """
    from pangalactic.core.clone import clone
    if product is None or project is None:
        return None
    if orb.search_exact(cname='ProjectSystemUsage', project=project,
                        system=product):
        orb.log.info(f'* step import: "{product.id}" is already a system of '
                     f'"{project.id}"; not adding it again')
        return None
    NOW = NOW or dtstamp()
    user = orb.get(state.get('local_user_oid'))
    return clone('ProjectSystemUsage',
                 id=f'psu-{product.id}-{project.id}',
                 name=f'psu: {product.name} (system used on) {project.name}',
                 creator=user, create_datetime=NOW,
                 modifier=user, mod_datetime=NOW,
                 system_role=getattr(product.product_type, 'name', 'System'),
                 project=project, system=product)


def apply_creation(items, owner=None, project=None, NOW=None,
                   progress=None, version=''):
    """
    Apply the confirmed items of a CREATE plan:  create the products that do
    not exist, then the Acus that assemble them, then place them.

    An Acu is created only if the products at both ends of it were confirmed;
    an unconfirmed product therefore drops the usages that depend on it,
    which are reported in `skipped` rather than created with a dangling end.

    Args:
        items (list of PlanItem):  the plan, as confirmed by the user

    Keyword Args:
        owner (Organization):  owner for newly created products.  Leave it
            unset unless the caller has a reason to override:  clone()
            defaults the owner to the current project, and the creator to the
            local user, which is what a newly imported specification wants.
        project (Project):  if given, the file's top-level assembly is also
            made a system of this project, so that it appears in the System
            Tree.  Without it the assembly is created but is reachable only
            through the Hardware Library.
        NOW (datetime):  timestamp for the new objects
        version (str):  the version string for a PRODUCT item that is a new
            version of an existing product.  clone() sets "version" to None
            for every Product it copies, deliberately -- a copy is not a
            version -- so it is assigned afterwards rather than passed in.
        progress (callable):  called as progress(done, total) after each item
            is handled, so a caller can drive a progress bar.  The items are
            walked twice -- once for products, once for usages -- so `total`
            is twice their number.  Optional:  this module has no Qt
            dependency and does not acquire one here.

    Returns:
        ImportResult
    """
    # imported here rather than at module scope:  clone imports the orb and
    # much of the parametrics machinery, and planning must stay cheap
    from pangalactic.core.clone import clone
    NOW = NOW or dtstamp()
    result = ImportResult()
    products = {}
    # the items are walked twice:  products must all exist before the usages
    # that assemble them can be created
    done, total = 0, 2 * len(items)
    for item in items:
        done += 1
        if progress is not None:
            progress(done, total)
        if item.kind != PRODUCT:
            continue
        if not (item.confirmed and item.actionable):
            result.skipped.append(item)
            continue
        if item.status == REUSED:
            products[item.key] = item.product
            result.mapping[product_key(item)] = item.product.oid
            continue
        if item.new_version_of is not None:
            # A new version of an existing product:  another product with
            # the same id and name, the version the user gave it, and
            # iteration 0.  The one it is a version of is left exactly as it
            # is, with its own components still hanging off it.
            #
            # include_components=False, because the usages are the import's
            # to make:  the file says what this version is assembled from,
            # which is the whole reason for importing it.  Letting clone()
            # copy the old version's components would give the new one two
            # of everything.
            was = item.new_version_of
            seq = was.version_sequence
            product = clone(was, save_hw=False, include_components=False,
                            version_sequence=(seq if isinstance(seq, int)
                                              else 0) + 1)
            # Three attributes clone() decides for itself, because it makes
            # copies and a copy is neither a version nor the thing it was
            # copied from:  it names the result "clone of X", gives it its
            # own id, and nulls "version".  A version is the one case where
            # all three are wrong -- it is the same item, identified the
            # same way, at a later point in its life -- so they are set
            # here.  PgxnObject.on_new_version() keeps the id for the same
            # reason.
            #
            # Keeping the id is the STEP reading of what a version is.  STEP
            # carries the principal identifier on the PRODUCT entity and the
            # version on a separate PRODUCT_DEFINITION_FORMATION, whose own
            # "id" attribute *is* the version of the product it belongs to.
            # This ontology collapses PRODUCT, PRODUCT_DEFINITION and
            # PRODUCT_DEFINITION_FORMATION into one Product class (author),
            # so the two identifiers land on one object:  "id" stays the
            # product's, and "version" carries the formation's.  A new
            # version is therefore the same id with a different version, not
            # a new id.
            product.id = was.id
            product.name = was.name
            product.version = version
            products[item.key] = product
            result.created.append(product)
            result.mapping[product_key(item)] = product.oid
            continue
        # public=False is set explicitly rather than left to default:  an
        # unset "public" reads as cloaked only by falling through the last
        # branch of is_cloaked(), which is the right answer for the wrong
        # reason.  A newly imported specification belongs to the project that
        # imported it until someone decides otherwise.
        kw = dict(name=item.path, public=False, save_hw=False)
        if owner is not None:
            kw['owner'] = owner
        if item.product_type is not None:
            kw['product_type'] = item.product_type
        product = clone('HardwareProduct', **kw)
        products[item.key] = product
        result.created.append(product)
        result.mapping[product_key(item)] = product.oid
    for item in items:
        done += 1
        if progress is not None:
            progress(done, total)
        if item.kind != ACU:
            continue
        occ, parent = item.occurrence, item.parent_occurrence
        assembly = products.get(getattr(parent, 'prototype_key', None))
        component = products.get(occ.prototype_key)
        if not (item.confirmed and item.actionable) or not (assembly and
                                                            component):
            result.skipped.append(item)
            continue
        # NOTE: creator/modifier are stamped by new_thing() from the local
        # user, matching what clone() does for the Acus it creates.  An Acu
        # without a creator cannot appear in local_user.created_objects, so
        # the sync would never pick it up if the direct push were missed.
        acu = new_thing('Acu', NOW=NOW,
                        id=get_acu_id(assembly.id, occ.ref_des),
                        name=get_acu_name(assembly.name, occ.ref_des),
                        assembly=assembly, component=component,
                        reference_designator=occ.ref_des)
        result.created.append(acu)
        result.mapping[item.path] = acu.oid
        if occ.placement is not None:
            result.created += set_placement(acu, occ.placement, NOW=NOW)
    if project is not None:
        # the top-level assembly only:  the components below it are reached
        # through it, and making each of them a system of the project would
        # flatten the assembly into the tree
        root_item = next((i for i in items
                          if i.kind == PRODUCT and i.is_root), None)
        root_product = products.get(getattr(root_item, 'key', None))
        psu = add_project_system(root_product, project, NOW=NOW)
        if psu is not None:
            result.created.append(psu)
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
# An assembly is a file in which something is used as a component of
# something else, which in Part 21 is a NEXT_ASSEMBLY_USAGE_OCCURRENCE.  The
# same pattern part21.preparse() greps for, and the same reason:  it is the
# one entity that says "this file has structure".
#
# Counting products will not do it.  as1-oc-214.stp in the test data has
# thirteen assembly usages and not one entity written as "=PRODUCT(" --
# Part 21 permits whitespace the naive pattern misses, and some files
# describe their products by other means.  The usages are what matters here
# anyway:  without them there is nothing to place.
NAUO_PATTERN = re.compile(
        r'#\s*\d+\s*=\s*NEXT_ASSEMBLY_USAGE_OCCURRENCE\s*\(',
        re.IGNORECASE)


def file_has_assembly(path):
    """
    Say whether a STEP file describes an assembly -- whether anything in it
    is used as a component of anything else.

    Some STEP files carry a single part and no structure:  conrod.stp in the
    test data is one.  There is nothing in such a file to place, so offering
    to position and orient its components offers nothing.

    Read as text rather than through pythonocc:  this is asked as soon as the
    file is chosen, to decide what the dialog may offer, and reading a large
    assembly properly takes long enough to need a progress dialog.

    Args:
        path (str):  the file

    Returns:
        bool:  True if the file contains at least one assembly usage.  True
        also if the file cannot be read -- an option is not withdrawn on the
        strength of a guess, and the import itself reports the failure
        properly a moment later.
    """
    try:
        with open(path, 'r', errors='replace') as f:
            return bool(NAUO_PATTERN.search(f.read()))
    except OSError as e:
        orb.log.debug(f'  - file_has_assembly: cannot read "{path}": {e}')
        return True


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


class PriorImport:
    """
    An import a STEP file has already had, and what it produced.

    Attributes:
        rep_file (RepresentationFile):  the stored copy of that file
        file_name (str):  the name it was imported under
        product (Product or None):  the thing the import created -- the
            RepresentationFile's Model's "of_thing"
        project (Project or None):  the project that owns the product, where
            it is owned by one
        imported (str):  when, as recorded in the correspondence
        same_file (bool):  the file about to be imported is byte-for-byte the
            one that was imported then
    """

    def __init__(self, rep_file, correspondence, same_file):
        self.rep_file = rep_file
        self.correspondence = correspondence
        self.same_file = same_file
        self.file_name = getattr(rep_file, 'user_file_name', '')
        self.imported = correspondence.get('imported', '')
        model = getattr(rep_file, 'of_object', None)
        self.product = getattr(model, 'of_thing', None)
        owner = getattr(self.product, 'owner', None)
        self.project = (owner if isinstance(owner, orb.classes['Project'])
                        else None)

    def __repr__(self):
        what = 'same file' if self.same_file else 'same name'
        pid = getattr(self.product, 'id', None) or '[no product]'
        return f'<PriorImport {self.file_name!r} {what} -> {pid}>'


def prior_imports(fname='', checksum=''):
    """
    Every import already recorded for a STEP file, matched by content or by
    name.

    Configuration management, not curiosity:  a file that has been imported
    once has produced a product, and importing it again either means that
    product (in which case it should be reused) or means a different one (in
    which case it needs to be a different file).  Deciding that needs to know
    what the first import produced and where it lives, and the caller cannot
    know which assembly to look on -- the whole point is that the earlier
    import may have been into another project entirely.  So this looks at
    every stored correspondence rather than at one assembly's models, which
    is what `_stored_step_file()` in step_dialogs does for the narrower
    question a PLACE import asks.

    Matching is by checksum *and* by name because they mean different things:

    * same checksum -- the very same file, whatever it is called.  There is
      already a product for it.
    * same name, different checksum -- a file of that name has been imported
      and this one differs from it.  Either the product has changed, or two
      unrelated files have been given the same name.

    A RepresentationFile with no stored correspondence is skipped:  it was
    attached some other way and says nothing about a STEP import.

    Keyword Args:
        fname (str):  the file's name, as it would be stored
        checksum (str):  sha-256 of the file about to be imported

    Returns:
        list of PriorImport:  the ones matched by content first, then the
        ones matched only by name;  each group most recently imported first,
        so a caller taking the first has the most relevant one.
    """
    by_content, by_name = [], []
    for rep_file in orb.get_by_type('RepresentationFile'):
        stored = get_correspondence(rep_file)
        if not stored:
            continue
        was = stored.get('checksum') or ''
        same_file = bool(was and checksum and was == checksum)
        same_name = bool(fname
                         and getattr(rep_file, 'user_file_name', '') == fname)
        if same_file:
            by_content.append(PriorImport(rep_file, stored, True))
        elif same_name:
            by_name.append(PriorImport(rep_file, stored, False))
    for group in (by_content, by_name):
        group.sort(key=lambda p: p.imported, reverse=True)
    return by_content + by_name


def store_correspondence_map(rep_file, pending):
    """
    Write a correspondence that was built earlier than the
    RepresentationFile it belongs on.

    A STEP import knows its correspondence as soon as it has applied the
    plan, but the RepresentationFile is created by
    `vger.add_update_model()` and does not exist until that rpc returns.
    The import therefore leaves the map in `state` and the rpc callback
    writes it here.

    Args:
        rep_file (RepresentationFile):  the stored STEP file
        pending (dict):  keys "map", "mode" and "checksum", as left by the
            import

    Returns:
        dict:  the structure that was stored
    """
    stored = {'version': CORRESPONDENCE_VERSION,
              'mode': pending.get('mode', ''),
              'imported': str(dtstamp()),
              'checksum': pending.get('checksum', ''),
              'map': dict(pending.get('map') or {})}
    set_dval(rep_file.oid, CORRESPONDENCE_DEID, json.dumps(stored))
    return stored


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
