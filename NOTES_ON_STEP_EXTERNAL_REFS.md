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

### 2.1 The imported structure is incomplete

**OCC does not follow external references.**  Verified by reading the file
three ways -- with the referenced files beside it, with them absent, and with
the top file renamed as the vault would name it.  All three give an identical
result, so the referenced files are not being read at all:

```
S1_PE_TOP                     children=5
  MAINBODY_ASM-1              children=0
  HEAD_ASM-1                  children=0
  TAIL_ASM-1                  children=0
  FOOT_ASM-1                  children=0
  FOOT_ASM-2                  children=0
```

Five prototypes where the design is thirteen files.  The subassemblies are
imported as products with correct placements and **no contents**:
`foot_back_prt`, `head_front_prt` and the rest are simply absent.  The import
reports success and the model is wrong.

Note that `FOOT_ASM` is correctly one prototype used twice -- the parts that
work, work.  That is what makes it hard to notice.

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
* Whether to detect this case at all when it is *not* supported:  an import
  that silently drops twelve files is the failure this note exists to
  describe, and refusing, or warning, would be better than appearing to work.
