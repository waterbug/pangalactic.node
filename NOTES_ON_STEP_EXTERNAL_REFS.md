# Design note: STEP files that reference other STEP files, 2026-08-20

A STEP assembly may be exported as a set of files rather than one: the
assembly file names its subassembly and part files, and a reader is expected
to find them.  `s1-pe-214.stp` in the test corpus is such a file.  Importing
it succeeded, and the success was misleading in three separate ways.

Nothing here is built.  This note records what was found and the smallest
design that would fix it.

---

## 1. What the file says

The AP214 external reference mechanism is three entities per reference:

```
#80=DOCUMENT_FILE('mainbody_asm.stp','S1_PE_TOP - MAINBODY','',#79,'','');
#89=EXTERNAL_SOURCE(IDENTIFIER('mainbody_asm.stp'));
#91=APPLIED_EXTERNAL_IDENTIFICATION_ASSIGNMENT('mainbody_asm.stp',#90,#89,...
```

The references are transitive.  `s1-pe-214.stp` is 13 files:

```
s1-pe-214.stp             4 refs
  foot_asm.stp            2 refs -> foot_back_prt.stp, foot_front_prt.stp
  head_asm.stp            2 refs -> head_back_prt.stp, head_front_prt.stp
  mainbody_asm.stp        2 refs -> main_body_back_prt.stp, main_body_front_prt.stp
  tail_asm.stp            2 refs -> tail_middle_part_prt.stp, tail_turbine_prt.stp
```

## 2. Three failures, all silent

### 2.1 The imported structure is incomplete *when the files are absent*

> **CORRECTED 2026-08-25.  The claim this section originally made -- that
> "OCC does not follow external references" -- is false, and the
> "verification" recorded for it was faulty.  OCC follows them perfectly
> well when the referenced files are beside the file being read.  What was
> actually being observed was a file read *without* its siblings.  Left in
> place rather than deleted, because the wrong conclusion shaped sections 3
> and 5 and it should be visible why.**

Reading `s1-pe-214.stp` two ways, 2026-08-25:

```
WITH siblings:     39 occurrences        WITHOUT siblings:  6 occurrences
  MAINBODY_ASM-1     children=2            MAINBODY_ASM-1     children=0
  HEAD_ASM-1         children=2            HEAD_ASM-1         children=0
  TAIL_ASM-1         children=3            TAIL_ASM-1         children=0
  FOOT_ASM-1         children=2            FOOT_ASM-1         children=0
  FOOT_ASM-2         children=2            FOOT_ASM-2         children=0
```

The right-hand column is what the original claim was based on:  six
occurrences, every subassembly empty, `foot_back_prt` and the rest simply
absent.  The left-hand column is the same file read from the directory it was
exported into, and it is complete -- `plan_creation()` on it yields the full
nested structure down to `HEAD_ASM-1/HEAD_BACK/SOLID-1`.

So the failure was never OCC's;  it was reading a file that had been
separated from its set.  Which means **section 5's refusal did not merely
report this problem, it fixed it**:  by refusing to read a file whose
references do not resolve, the importer guarantees the condition under which
OCC reads the whole assembly.  That was not the intent at the time, and the
premise was never re-tested afterwards.

Note that `FOOT_ASM` is correctly one prototype used twice -- true either
way, and part of what made the truncated tree look plausible.

### 2.2 Only the top file is transferred

The import uploads the file it was given.  The other twelve are never sent,
so the repository's copy cannot be rendered by anything that *does* follow
references.

This did not show up when tested, because `s1-pe-214.stp` is the example file
for "Rocinante Spacecraft v.0" and its twelve companions were already in the
vault from that fixture.  Had they not been, the import would still have
reported success and the failure would have appeared later, in a different
session, at render time, with nothing pointing back at the import.

### 2.3 The vault's naming would defeat resolution anyway

Uploaded files are stored as `<oid>_<user_file_name>` (`orb.get_vault_fname`),
and downloads are written the same way.  References are by bare name.  So
even uploading all twelve would produce `<oid>_mainbody_asm.stp`, which a
reader looking for `mainbody_asm.stp` will not find.

The twelve that are in the vault today are there under their *bare* names,
from the fixture rather than from an upload -- which is precisely why
resolution works at the moment.  Fixing 2.2 alone would not fix rendering.

## 3. The minimum that would fix it

### 3.1 Ontology: one property pair, no new class

The relationship needed is "this file references that one".  It does **not**
need to carry the name the reference is made under, because
`RepresentationFile.user_file_name` already *is* that name -- the identifier
in `EXTERNAL_SOURCE` is the file's own name.  So no relationship class is
required, only a self-referential link, for which there is precedent in
`Activity.sub_activity_of` / `sub_activities` and
`Organization.parent_organization` / `sub_organizations`:

| property | domain | range | functional | inverse of |
|---|---|---|---|---|
| `component_file_of` | `RepresentationFile` | `RepresentationFile` | yes | -- |
| `component_files` | `RepresentationFile` | `RepresentationFile` | no | `component_file_of` |

The functional direction points from child to parent, so the foreign key
column lands on the child and the parent gets the collection by inverse --
the same shape as the two existing self-referential pairs.

**What this costs elsewhere** is the list in
`pangalactic.core/NOTES_ON_ONTOLOGY_AND_DB.md` under "What a new class
costs".  A new *property* on an existing class is cheaper than a new class:
no `DESERIALIZATION_ORDER` entry, no `modifiables`/`is_cloaked` branch.  But
it does add a column to `representation_file_`, which `create_all()` will
**not** add to an existing table -- so unlike the placement classes, this one
genuinely needs the `schema_version` bump to do its work.

**The simplification is a judgement, not a fact.**  Reusing
`user_file_name` as the reference identifier assumes the two always agree.
They do in this corpus.  A file referenced under a name different from its
own -- a path, say, or a renamed copy -- would need the identifier stored
separately, and that *would* mean a relationship class.  Worth checking
against a wider sample of the CAx-IF corpus before committing.

### 3.2 Import: follow the references

The importer must build the closure itself, since OCC will not:

1. parse `EXTERNAL_SOURCE(IDENTIFIER('...'))` from the file;
2. resolve each name relative to the imported file's directory;
3. recurse, guarding against cycles;
4. read each file's own assembly structure and graft it beneath the
   occurrence that stands for it, so the subassemblies are no longer empty;
5. create a `Model` and `RepresentationFile` per file, linked by
   `component_file_of`, and upload each.

Step 4 is what fixes 2.1, and it is the substantial part:  the occurrence
`MAINBODY_ASM-1` in the parent and the root of `mainbody_asm.stp` are the
same thing, and joining them is the whole trick.

This also lands squarely on the **master model** idea:  each STEP file
becomes the MCAD `Model` of the `Product` it defines, so the file-reference
graph and the `Acu` graph become two views of one assembly.  Getting that
right makes 2.1 and 2.2 the same fix rather than two.

### 3.3 Download: write the closure under its own names

On fetching a file with `component_files`, the client must fetch them too and
write each **under its `user_file_name`**, not the vault name, into one
directory -- then the reader resolves them as the exporter intended.  This is
the fix for 2.3, and it is why 3.1 needs no new attribute.

## 4. Open

* Whether `user_file_name` is always the reference identifier (see 3.1).
* Whether a shared part file referenced by two assemblies should be one
  `RepresentationFile` with two parents -- which the functional
  `component_file_of` forbids -- or two records of the same physical file.
  The second is the simpler reading and is probably right:  a
  `RepresentationFile` is a file in an export set, not a file in the abstract.
*(The third question here -- whether to detect the case at all before
supporting it -- is answered:  see section 5.)*

## 5. What is built:  refuse rather than pretend

The importer now stops before reading anything if any referenced file is
missing, naming each one and the file that refers to it.

`step_import.missing_references()` walks the closure, resolving each
reference against the directory of the file that makes it -- which is how a
reader resolves them -- following those that resolve, so a reference missing
two levels down is still reported. It guards against cycles.

This does **not** make such files importable. It converts a silent, delayed
failure into an immediate and specific one, which is worth having on its own:
the alternative was an assembly with empty subassemblies and a vault copy
that would not render, discovered later by someone else.

Two points of care in the message:

* **The user is not assumed to have exported the file.** They may well have
  received it (author, 2026-08-20). The message says the file is part of a
  set, names what is missing, and says the files come from wherever the file
  itself came from and must be placed alongside it under exactly those names
  -- rather than implying the user should already have them.
* **It names the referrer, not just the missing file.** With only the
  subassemblies present, the eight missing parts are named by the
  subassemblies, not by the top-level file, and saying so is the difference
  between an actionable message and a puzzling one.


## 6. Synthesis:  writing an assembly file rather than reading one (2026-08-22)

The author found, by editing `mainbody_asm.stp` by hand, that **substituting
a different file name in a reference substitutes a different component into
the assembly** -- the assembly still calls it by the original name, and the
geometry that arrives is whatever the named file contains.

That is not a quirk.  It follows from what an assembly file actually holds
for a referenced component:  a *stub*.  The child's `SHAPE_REPRESENTATION`
sits in a context explicitly marked `'external'` --

    #106=(GEOMETRIC_REPRESENTATION_CONTEXT(3)...
          REPRESENTATION_CONTEXT('ID2','external'));
    #111=SHAPE_REPRESENTATION('',(#110),#106);

-- so the assembly file carries the component's *identity, placement and
usage* but none of its geometry.  The file name is the only thing binding
that stub to any actual shape.  Name and content are therefore independent,
which is the opportunity below and also a hazard worth stating: an assembly
can name a part `MAIN_BODY_BACK` and be given something else entirely, with
nothing in the file disagreeing.

### 6.1 What one referenced component consists of

From `mainbody_asm.stp`, the entities for a single component, in four groups:

**Identity** -- `PRODUCT` / `PRODUCT_DEFINITION_FORMATION` /
`PRODUCT_DEFINITION` (#40, #41, #42).

**Usage** -- `NEXT_ASSEMBLY_USAGE_OCCURRENCE('0', ..., 'MAIN_BODY_BACK',
#187, #42, $)`:  reference designator, parent definition, child definition.

**Placement** -- `AXIS2_PLACEMENT_3D` (#75), `ITEM_DEFINED_TRANSFORMATION`
from the child's own frame to it (#76), the
`(REPRESENTATION_RELATIONSHIP ... WITH_TRANSFORMATION ...)` complex (#81),
`PRODUCT_DEFINITION_SHAPE('Placement #0', ...)` (#67) and
`CONTEXT_DEPENDENT_SHAPE_REPRESENTATION(#81, #67)` (#82).

**External reference** -- `DOCUMENT_FILE` naming the file (#84),
`DOCUMENT_REPRESENTATION_TYPE`, a `PROPERTY_DEFINITION('external
definition')` tying the document to the stub shape rep, the document-format
representation (`DESCRIPTIVE_REPRESENTATION_ITEM('data format','STEP
AP214')`), `EXTERNAL_SOURCE(IDENTIFIER(<file name>))` (#93),
`APPLIED_EXTERNAL_IDENTIFICATION_ASSIGNMENT` (#95),
`APPLIED_DOCUMENT_REFERENCE(#84,'',(#42))` binding it to the child's product
definition (#96), and `OBJECT_ROLE('mandatory','')` + `ROLE_ASSOCIATION`.

Plus the `'external'` representation context and stub `SHAPE_REPRESENTATION`
quoted above.

### 6.2 Why this is worth keeping on the roadmap

**PGEF already holds every input.**  This is the striking part, and it fell
out of the import work rather than being designed for:

| needed in the file | where it already is |
| --- | --- |
| product identity, name | `HardwareProduct.id`, `.name` |
| reference designator | `Acu.reference_designator` |
| parent/child structure | `Acu.assembly`, `Acu.component` |
| placement | `Axis2Placement3D` + `ContextDependentShapeRepresentation` |
| file to reference | `RepresentationFile.user_file_name` |
| the component files themselves | the vault, via `component_files` (3.7.0) |

So a "STEP assembly template" -- a parent file with the boilerplate, to which
component references are appended -- is a matter of *emitting* what the
ontology already carries, not of acquiring anything new.  It is the exact
inverse of `step_import.read_assembly()`, over the same entities.

This also makes the roadmap item in the sandbox TODO -- "provide STEP models
of library components" -- more valuable than it looks:  a library of
per-component STEP files plus this synthesis is a route from a PGEF assembly
to a CAD-readable one without a CAD system in the loop, which is the same
direction as generating 42 input.

### 6.3 Where the placements would come from

Reading an assembly gives placements;  synthesizing one has to *decide*
them, which is a harder problem and the one that decides how far this can go.

An imported assembly has a placement per usage already, so re-emitting it is
straightforward.  A *synthesized* assembly -- components picked from the
library and assembled -- has no placements to re-emit, and the interesting
half is where they come from.

**Orientation is often implied by interfaces** (author, 2026-08-22):  a
component's orientation is frequently not free, but fixed by what it has to
mate with, point at, or radiate away from -- a connector's mating direction,
a radiator facing deep space, a thruster's line of action, a sensor
boresight.  That is a constraint the component itself carries, not something
the person assembling it should have to supply each time.

PGEF has somewhere to put it.  `Port` and `PortType` already describe a
component's interfaces, and `Flow` describes what connects to what;  an
orientation attached to a port -- a direction in the component's own frame --
would let a placement be *derived* from a connection rather than entered.
Whether that belongs on `Port`, on `PortType` (so it is a property of the
kind of interface), or on a `PortTemplate` is exactly the sort of question
the placement classes needed answering, and the answer there was to follow
STEP's own model.  Worth asking whether STEP has a corresponding notion
before inventing one -- it has kinematics and assembly constraint schemas
(AP242 in particular), which is where to look first.

Note this is the same question the 42 work runs into from the other side:  an
ACS simulation needs to know where things point, not only where they sit.
The two would share whatever answer this gets.

### 6.4 Not yet identified

* **Entity numbering.**  Ids are file-local and every appended component
  needs a fresh block;  a template plus text substitution needs a renumbering
  pass, or generation from a model rather than by concatenation.
* **Units.**  Each file declares its own (`mainbody_asm.stp` is in
  centimetres).  A synthesized parent has to agree with, or convert for, the
  files it references -- and `scale_to_m()` shows how easily this is got
  wrong in the other direction.
* **What else a reader requires** to accept the file:  the header
  (`FILE_DESCRIPTION`, `FILE_SCHEMA`), application context, and the
  validation properties Pro/E writes (centroid, area, volume) -- which are
  presumably optional, but that is an assumption, not a finding.
* **Whether OCC will read a synthesized file at all.**  It does not follow
  these references (section 2.1), so any test of a synthesized assembly needs
  a reader that does, or a check against a real CAD system.
* Whether this belongs in `pangalactic.node` beside the importer, or in
  `pangalactic.core` as a serializer.  It needs no Qt and no OCC, which
  argues for core.

**Priority:  roadmap, not now** (author, 2026-08-22).


## 7. File transfer, both ways (2026-08-25)

Found by the author on a round trip:  an assembly imported from a multi-file
export renders correctly from the directory it was imported from, and
**incorrectly when fetched back from the repository** -- because only the
file the user chose was ever uploaded.  For the CAx-IF files that means
almost nothing renders:  `s1-pe-214.stp` and its subassemblies contain *no*
inline geometry at all (0 `ADVANCED_BREP_SHAPE_REPRESENTATION`, 5 and 2
`EXTERNAL_SOURCE` respectively), so every component's geometry is in another
file.

This is 3.2 step 5 and 3.3.  Step 4 -- grafting each referenced file's
structure beneath the occurrence that stands for it -- is **not** done, so an
imported assembly still has empty subassemblies in the PGEF object graph.
What is fixed is the *files*:  the geometry now survives a round trip, which
is what the 3D view depends on.

### 7.1 Up:  `digital_files.new_component_file()`

`reference_closure()` (node) walks the set the same way `missing_references()`
does, returning `(referenced file, referencing file)` pairs, **parents before
children** -- which matters because `component_file_of` points at the
referencing file, whose `RepresentationFile` has to exist first.

`register_component_files()` then makes one pass over that list, creating the
objects locally as it goes.  Ordering is all it needs:  a child's parent is
always already in hand.

**This was a cascade until 2026-08-28**, and the change is worth recording.
Each file used to be registered by `vger.add_component_file(...)`, and the
*upload's* completion started the next one -- so registering a set required a
connection and took as long as transferring it, and a set imported offline
was reduced to the one file the user chose.  The rpc is still registered, for
older clients;  nothing here calls it.

Uploads are still one at a time -- `read_and_upload_file()` keeps the chunks,
path and target oid in instance attributes, so two at once would overwrite
each other -- but they are now a queue behind the object creation rather than
the thing driving it.  Offline there are simply no uploads to queue, and the
objects sync with their bytes at the next connection like any other file (see
NOTES_ON_STEP_IMPORT.md section 3c).

The rules the rpc established are unchanged, and are now in
`pangalactic.core.digital_files.new_component_file()`:  a component file
**joins the Model of the file that references it** -- it is not a model of
anything in its own right -- *unless* the import identified which product it
models, in which case it gets a Model of that product;  and it is
**idempotent** on `(referencing file, user_file_name)`, since an import can
legitimately be repeated and a part shared by two subassemblies is named by
both of them in one set.

One difference: the whole set is published together or not at all.  If any
file's bytes fail to go up, every object of that set is held back for the
next sync -- a set is only readable whole, so publishing the rest would
describe an assembly nobody can open.

### 7.2 Down:  `orb.stage_file_closure()`

Section 2.3's problem, solved where it has to be.  A vault file is named
`<oid>_<user_file_name>`, so an assembly opened from the vault resolves none
of its references *even when every file has been downloaded*.  Staging copies
the closure into one directory per root file, each under its own
`user_file_name`, and returns the staged root.  `get_mcad_model_file_path()`
uses it, and skips files that are `component_file_of` something -- opening
one of those directly would render a component instead of the assembly.

One directory *per root file* rather than one shared one, because two
assemblies can each reference a part file of the same name and they are not
the same file.

Partial sets stage as far as they can rather than refusing:  a reader given
part of a set renders part of the assembly, which beats nothing.

### 7.3 The files travel with the product

The first version of this fetched missing component files when the 3D view
was opened, which the author corrected (2026-08-25):  **a product sent from
the server should always include all its components, models and documents,
with all their files.**  The client is meant to hold everything the server
knows about a product -- that is what the master-model paradigm means -- so
fetching pieces on demand is the wrong shape, and the user will not be
looking at a product before its download has finished anyway.

Three things were in the way:

1. `serialize()` deliberately withheld Models and RepresentationFiles from
   the Products they represent.  The note there gave differing "owners" and
   access controls as the reason.  That is answered structurally rather than
   by withholding:  **a project-owned object can only be built from objects
   that are public or owned by that project** (author), so a requester
   entitled to a product is entitled to what it is made of.  There is now an
   `include_models` keyword, off by default -- a client saving a product has
   no reason to send the models back -- which `vger.get_objects()` turns on,
   and which carries down to components.
2. **Library models never reached clients at all.**  `sync_library_objects`
   filters on `public`, and nothing sets `public` on a Model -- `clone()`
   leaves it None -- so every model of every public library product was
   withheld.  `add_update_model` now takes it from the thing modelled, and
   the library sync also accepts a model whose `of_thing` is public, which
   covers models already created.
3. A `Model` already carried its `has_files`, so once a model travels its
   files do -- which is why the component-file work needed no further
   plumbing to reach the client.

The on-view fetch is kept as a safety net.  It should now never find
anything missing, and costs nothing when it does not.

### 7.4 What is still weak

* **Nothing removes staged directories.**  They are copies of vault content
  under `<home>/staged/<oid>/` and will accumulate.
* **Step 4 turned out to be unnecessary** -- see the correction at the head
  of section 2.1.  OCC grafts the referenced files' structure itself, so an
  imported assembly's subassemblies are *not* empty and the object graph is
  complete.  Nothing needs writing;  what needed correcting was this note.

* Section 3.2 step 5 -- one Model per file -- **is now built**;  see 7.5.

### 7.5 One Model per file (2026-08-25)

Every referenced file used to hang off the *master's* Model, which
transferred the files but identified them with nothing.  Each file now gets a
Model of the product it defines, so the file graph and the assembly graph
become two views of one thing -- and a subassembly can be opened in the 3D
viewer on its own, which is the visible consequence.

**The file says which product it defines.**  It is not inferred from the file
name.  The chain, in the *referencing* file:

    DOCUMENT_FILE('main_body_back_prt.stp', ...)            -- #84
    APPLIED_DOCUMENT_REFERENCE(#84, '', (#42))              -- binds it
    PRODUCT_DEFINITION('part definition', '', #41, #38)     -- #42
    PRODUCT_DEFINITION_FORMATION('1', 'LAST_VERSION', #40)  -- #41
    PRODUCT('MAIN_BODY_BACK', ...)                          -- #40

`referenced_product_names()` follows it with targeted expressions rather than
the part21 grammar in `p.core.utils.part21`, which parses everything and is
far more than four hops need.  `closure_product_names()` walks the closure,
because a file names the products of the files *it* references -- the top
file names MAINBODY\_ASM, and `mainbody_asm.stp` names MAIN\_BODY\_BACK.  All
12 files of the s1 export are identified.

**The join is the product name**, which is also the occurrence prototype name
OCC reports, and a plan item's `path`.  A test pins that they agree, since
nothing pairs up if they ever diverge.  Two prototypes sharing a name are
dropped rather than guessed at -- Pro/ENGINEER emits eight called SOLID or
COMPOUND in one assembly, though those have no files of their own.

**A file whose product cannot be identified still transfers** and is still
linked by `component_file_of`;  it simply joins the referencing file's Model
as before.  Nothing is lost by failing to identify it.

**One consequence in `get_mcad_model_file_path()`**, worth stating because it
is not obvious:  choosing "the file that no other references" is wrong now.
A subassembly's file *is* referenced -- by its parent, which belongs to a
different Model.  The test is against the files of *the same* Model, which
gets both shapes right:  this one, and the older one where a whole set hung
off a single Model.

### 7.6 The file follows the Model (2026-08-26)

Reported by the author after testing from a second machine:  syncing the
project brings the whole assembly -- Products, Acus, Models,
RepresentationFiles -- and **nothing renders**, because a
`RepresentationFile` is a *record* of a file, not the file.  The files could
be had through "Models and Docs" -> save a local copy, one at a time, which
works but is not what that function is for:  it is for taking a copy *away*,
to share or to use elsewhere.  The vault copy is infrastructure -- it is what
the viewer opens -- and the user should not have to assemble it by hand.

So a file the built-in viewer can render is now fetched as it arrives, from
`load_serialized_objects()` and its `force_` twin, which is where every
incoming batch lands.  Anything else is left on demand:  fetching every
document in a project in order to look at an assembly would be the wrong
trade, and "save a local copy" is the right route for a file the client
cannot display anyway.

`VIEWABLE_FILE_SUFFIXES` in `p.core.uberorb` is the one list -- `.stp`,
`.step`, `.p21`, `.stl`, `.brep`, each in both cases, since a suffix is
whatever the exporter wrote.  `get_mcad_model_file_path()` uses the same
list, which is what it means for these to be *the* viewable formats rather
than two opinions about it.

**One at a time**, for the same reason uploads are:  `download_file()` keeps
the chunk count and the progress dialog in instance attributes, so two at
once would report each other's progress and close each other's dialog.  A
file already in the vault is skipped -- which is the normal case for the
client that did the import, since uploading copies to the local vault on the
way past -- and so is one that arrives by another route while it waits in the
queue.
