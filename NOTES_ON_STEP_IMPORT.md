# Design note: STEP assembly placements via pythonocc, 2026-08-15

Groundwork for the first 42 goal — using a project assembly as input to a 42
ACS simulation, which needs each component's position and orientation within
the assembly, and the assembly's mass properties.

PGEF has no geometry: `Acu` carries `reference_designator` and `quantity` and
nothing else, so there is nowhere today to record where a component sits. The
question this note answers is a narrow, factual one, deliberately settled
*before* the modelling decision that depends on it:

> If assembly geometry is imported from a CAD (STEP) model — and it will be,
> since no ACS engineer is going to reconstruct assembly geometry by hand for
> 42 — what exactly does the import give us?

Two spikes in `spikes/step_assembly/`, run against pythonocc-core 7.9.0.

---

## 1. The assembly structure is the Product/Acu structure

`STEPCAFControl_Reader` into a `TDocStd_Document` gives an XCAF tree whose
shape is the one PGEF already has:

| XCAF | PGEF |
|---|---|
| prototype label (`IsSimpleShape`/`IsAssembly`) | `Product` |
| component label (`IsReference`) | `Acu` |
| `GetReferredShape(component)` | `Acu.component` |
| `GetLocation(component)` | *(nothing today)* |
| label name of the component | `Acu.reference_designator` |

That correspondence is not a coincidence — the `Acu` concept comes almost
directly from STEP, which specialises it per application protocol (in AP203,
`NEXT_ASSEMBLY_USAGE_OCCURRENCE`).

Run against the classic AS1 test assembly (`as1-id-203.stp`, AP203, I-DEAS
export), `step_placements.py` reports **18 leaf occurrences from 6
prototypes** — `l-bracket assy` instantiated twice at different placements,
`nut-bolt assy` three times inside each. That is exactly the case that
motivated putting placement on the usage rather than the product: one
`Product`, many `Acu`s, a different placement per `Acu`.

```
assembly  0:1:1:1    as1
  component 0:1:1:1:2  l-bracket assy_2
            -> prototype 0:1:1:3    l-bracket assy
            location      (  125.000,  125.000,   80.000)
            axis (Z)      (    0.000,   -1.000,    0.000)
            ref_dir (X)   (    0.000,    0.000,   -1.000)
    component 0:1:1:3:2  nut-bolt assy_3
              -> prototype 0:1:1:4    nut-bolt assy
              location      (   68.500,    7.500,   37.010)
```

### 1.1 `axis2_placement_3d` comes back intact

The placement arrives as a `TopLoc_Location` wrapping a `gp_Trsf`. Its
`axis2_placement_3d` form — location, axis (local Z), ref_direction (local X)
— is recovered exactly by transforming the unit basis; see `placement()` in
the spike. Three consequences:

- **No lossy decomposition.** If the ontology grows a placement construct
  shaped like `axis2_placement_3d`, import is a transcription. Flattening to
  scalars instead would mean inventing a decomposition on the way in and a
  reconstruction on the way out.
- **No Euler-convention argument.** Direction cosines carry the orientation
  without anyone choosing a rotation sequence — which was the one gap with no
  clean answer under the "store it as parameters/data elements" options.
- **42 wants nearly this anyway** — a position vector plus a pointing axis per
  component.

### 1.2 Placements are parent-local and compose

Each occurrence's placement is relative to its parent, so body-frame
coordinates come from composing the chain (`TopLoc_Location.Multiplied`)
down the tree — the same composition a chain of `Acu`s would have to do. The
nut inside `nut-bolt assy` is at `(0, -17, 0)` in its own parent's frame and
lands at `(155, 75, -5.5)` in the assembly's.

### 1.3 Names are translator-dependent and cannot be trusted

`label.GetLabelName()` gives the occurrence name — the obvious candidate for
`reference_designator`. Running the spike over three translators' exports of
the *same* AS1 assembly, from
`pangalactic.core/pangalactic/core/test/data`, shows three different
behaviours:

| file | translator | AP | occurrence names |
|---|---|---|---|
| `as1-id-203.stp` | I-DEAS MS8 | 203 | `plate_1`, `l-bracket assy_2`, `nut_2` |
| `as1-oc-214.stp` | Datakit / OpenCASCADE | 214 | `rod-assembly_1`, `nut_1`, `nut_2` |
| `as1_pe_203.stp` | Pro/ENGINEER | 203 | `PLATE`, `L-BRACKET`, `=>[0:1:1:3]` |

**The variation here is by translator, not by application protocol.** The two
files that differ most are both AP203; the AP214 one agrees closely with the
AP203 I-DEAS export on mass properties (§2.2). In the corpus the two-letter
code is the translator — `id` I-DEAS, `pe` Pro/ENGINEER, `oc` Open CASCADE,
`ug` Unigraphics, `cm` CoCreate — and the numeric suffix is the AP, with the
same vendor appearing at both (`as1_pe_203` and `s1-pe-214`). Testing across
APs alone would have surfaced none of §1.3, §2.3 or §2.4's problems.

Only the middle one is really usable: its two nuts in `rod-assembly` are
`nut_1` and `nut_2`, both referring to prototype `nut`, so the suffix does
distinguish the occurrences. I-DEAS suffixes look synthesised rather than
authored. **Pro/ENGINEER names many occurrences after their prototype, and
leaves others with no name at all** — `=>[0:1:1:3]` is OCC's stand-in for a
reference label with no name attribute.

So an importer must not take `reference_designator` from the file on faith.
It will have to derive one (from the occurrence path, which is always
available and always unique) or have the user assign it, and treat any name
in the file as a hint. The assembly *decomposition* is translator-dependent
too: Pro/E nests a `SOLID` and an empty `COMPOUND` under each part where the
others have a single leaf.

## 2. Mass properties: what CAD gives and what it doesn't

Mass distribution is genuinely out of scope for a STEP model — it belongs to
analysis, and normally arrives when an FE model is built from the explicit
geometry with masses allocated by material and density. STEP (AP203, AP214,
AP242) will not hand us mass properties.

It does not have to. `BRepGProp.VolumeProperties` gives, for any located
shape, its volume, its centroid, **and the full inertia tensor about that
centroid at unit density**. That splits the work cleanly:

- **CAD supplies geometry and distribution** — where the mass is.
- **PGEF supplies mass** — the `m` parameter of each component's
  `HardwareProduct`, which is authoritative and already maintained.
- Scale the unit-density tensor by `m / volume` per component, then roll up
  with the parallel-axis theorem.

No FEM, no material assignments, no density data in the STEP file. And the
result is per *component*, not per subsystem — finer than "lumped" implies.

### 2.1 Verified by execution

`step_mass_props.py` rolls AS1 up from its 18 leaf occurrences and checks the
result against OCC computing the whole assembly compound in one shot:

```
                     rolled up from parts           whole assembly, one shot
mass (kg)                          2.0668                             2.0672
CoM (mm)  [89.999980, 75.000508, 18.788668]  [90.000467, 75.000058, 18.790745]
MoI       [0.003854, 0.007583, 0.010103]     [0.003855, 0.007582, 0.010103]
PoI       [-0.000000, 0.000000, -0.000000]   [0.000000, -0.000000, 0.000000]
```

Agreement to ~5 significant figures, the residual being tolerance noise and
the double-counting noted below. The products of inertia come out at zero,
which is the right answer for AS1's symmetry and a check that the
parallel-axis arithmetic is not accidentally right.

The left column is exactly 42's Body block: Mass, Moments of Inertia,
Products of Inertia, Location of mass center.

### 2.2 The same assembly through two translators agrees

I-DEAS and Datakit exports of AS1, rolled up independently:

| | mass (kg) | CoM z (mm) | MoI (kg-m^2) |
|---|---|---|---|
| `as1-id-203.stp` | 2.0668 | 18.789 | 0.003854, 0.007583, 0.010103 |
| `as1-oc-214.stp` | 2.0642 | 18.860 | 0.003851, 0.007564, 0.010088 |

Agreement to about 0.1–0.4% across independent translations of the same
design — a stronger check than the internal one in §2.1, since nothing is
shared between the two paths but the original geometry.

The Pro/ENGINEER export is left out of this comparison not because it
disagrees but because it describes a physically different object: its
dimensions are the same numbers declared in inches, so it is 25.4× the size.
See caveat 1 in §2.4.

### 2.3 Zero-volume leaves are real and must be skipped

The Pro/E export has 36 leaf occurrences where the others have 18: each part
appears as a `SOLID` *and* an empty `COMPOUND`. Those compounds have zero
volume, and the first version of the roll-up divided by volume to scale the
unit-density inertia tensor, so it raised `ZeroDivisionError` on this file.
`roll_up()` now skips zero-volume occurrences and reports how many. Any real
importer needs the same guard — translators emit leaves with no solid
geometry (empty compounds, wireframe, surfaces) and they carry no mass.

### 2.4 Four caveats

1. **Units.** *(Corrected 2026-08-17 — the original text of this caveat
   claimed OCC had failed to convert the inch file, and that was wrong.)*
   OCC converts a file's declared length unit to the unit named by the
   `xstep.cascade.unit` static, whose default is `MM`. It does this
   correctly: `as1_pe_203.stp` declares
   `CONVERSION_BASED_UNIT('INCH', ...)` and arrives in millimetres, its
   5080 mm extent being 200 inches converted. The other two declare
   millimetres and arrive unscaled.

   So the **33,888 kg** figure was not a conversion failure — that assembly
   really is 5.08 m across at the density the spike assumes. The three files
   are the same *design numerically* (about 200 × 150 × 84 units) with the
   unit differing by vendor, so after correct conversion the Pro/ENGINEER
   one is 25.4× the size of the others. That is also why its mass ratio
   landed so near 25.4³: the ratio is real, not an error.

   The practical consequences for an importer are unchanged in substance but
   different in mechanism: convert OCC's output (mm) to metres, and do not
   assume two exports of "the same" CAx-IF design describe the same physical
   object. `step_import.scale_to_m()` reads the static rather than setting
   it — setting it did not take reliably, only having an effect when set
   after the STEP machinery had been imported, and not consistently even
   then. 42 wants m and kg.
2. **Uniform density per component** is the assumption doing all the work.
   It is wrong for, say, an electronics box with one dense corner — but
   boundedly and explicably wrong, and taking mass from PGEF keeps the
   *total* exact even where the distribution is approximate.
3. **Overlapping solids double-count volume** (bolts through plates).
   Harmless when mass comes from PGEF and only distribution comes from CAD —
   which is a further argument for that split.
4. AS1 is **AP203**. The same XCAF path should serve AP214 and AP242, but
   that is unverified here, as is anything involving PMI.

## 3. What this does and does not settle

It settles the factual question: a STEP import yields per-occurrence
placements in `axis2_placement_3d` form, and those placements plus PGEF's
existing mass parameters are sufficient to produce 42's Body block.

**Where placement lives in the model has since been decided** (2026-08-16):
the ontology gained `ContextDependentShapeRepresentation` and
`Axis2Placement3D`, along STEP's own lines, at schema version 3.5.0.  The
design and the full STEP mapping are recorded in
`pangalactic.core/NOTES_ON_ONTOLOGY_AND_DB.md` under "Component placement";
`pangalactic.core/pangalactic/core/test/test_placement.py` is the test suite.

The alternatives considered and rejected were data elements on the `Acu` (no
ontology change, and the ontology does distinguish cleanly —
`ParameterDefinition` is a subclass of `DataElementDefinition`, "a data
element that represents a measurable physical property", so placement would
have been a data element and not a parameter), and no model change at all
with the exporter owning a layout per analysis.

§1.1 is the argument that decided it: the closer the model is to STEP's own
construct, the closer import gets to transcription.  Nothing populates the
new classes yet — that is the importer, and it is the next piece.

## 3a. The correspondence, and what round-tripping would need

An import records which occurrence of the STEP file became which object, as
a `step_correspondence` data element on the `RepresentationFile` the file was
stored as. `RepresentationFile` is a `Modelable`, so this needs no ontology
change, it syncs with the file object, and a new version of the file gets its
own correspondence. It holds the import mode, the time, the file's checksum,
and a map of **occurrence path** to oid.

The key is the occurrence path and not any identifier internal to the file,
for the reason in §1.3's neighbourhood: XCAF label entries are assigned in
the order the exporting tool happened to write the file. The same design
through two translators gives `plate` the entry `0:1:1:2` in one and
`0:1:1:9` in the other, so a correspondence keyed on them would point at the
wrong part as soon as the model were re-exported. The path is semantic, and
stable for exactly as long as the reference designators are — the same
assumption the matching itself rests on.

A re-import whose checksum differs from the stored one **stops and asks**
rather than re-matching. A re-export may have gained, lost or renamed parts,
and silently re-placing components that were positioned deliberately is the
failure mode with the worst consequences. An absent checksum on either side
is *not* treated as a change: warning about a file we cannot compare would
only train the user to click through the warning.

### What a round trip would additionally need — not built

Writing changes back out through STEP is a larger thing than it looks, and
nothing here attempts it. Recorded so the shape of the problem is not
rediscovered:

- **PGEF cannot produce a STEP file.** It holds assembly structure,
  placements and mass parameters; it holds no BREP geometry. So an export is
  necessarily a *modification of the original file*, not a generation of a
  new one — which means the original must still be in the vault, and must be
  the file the correspondence was built against.
- **Write-back would re-read that original.** The correspondence's keys are
  derived paths, not offsets into the file, so locating the transform to
  rewrite means reading the file again and re-deriving the same paths. That
  is sound because the derivation is deterministic, but it makes the checksum
  check a precondition of export and not only of import.
- **Round-tripping is therefore only meaningful for the placements and the
  structure** — the things PGEF is authoritative for. Geometry edits belong
  to CAD and would be lost or, worse, silently reverted.

Whether any of this is worth building depends on a use case that has not
appeared yet.

## 4. Running the spikes

They take a STEP file path; neither is wired into the app and neither is a
test.

**The test corpus is already in the tree**, at
`pangalactic.core/pangalactic/core/test/data` — 37 STEP files, many of them
the canonical examples used to test vendor STEP translators in the PDES, Inc.
consortium's CAx-IF test forum. That is why the multi-translator comparisons
above were cheap, and it is the right place to draw files from for any
further work here: the `as1-*`, `dm1-*`, `io1-*` and `s1-*` families are the
same designs exported by different vendors' translators, which is exactly the
variation an importer has to survive.

```
python spikes/step_assembly/step_placements.py  <file.stp>
python spikes/step_assembly/step_mass_props.py  <file.stp> [density_kg_per_mm3]
```
