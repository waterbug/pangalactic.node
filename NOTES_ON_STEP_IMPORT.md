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

### 1.3 Names

`label.GetLabelName()` yields `plate_1`, `l-bracket assy_2`,
`nut-bolt assy_4` — the reference-designator analogue. **Unverified:** the
reader appears to synthesise the `_N` suffixes, so whether a real CAD
export's NAUO id survives verbatim needs checking against a file from the
tool users actually run, not against this sample.

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

### 2.2 Four caveats

1. **Units.** The sample is in mm and the spike hardcodes mm→m. STEP carries
   its units; a real importer must read them. 42 wants m and kg.
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

It does **not** settle where placement should live in the model. That
decision is open, and the options were:

- data elements on the `Acu` — no ontology change; the ontology already
  distinguishes cleanly, `ParameterDefinition` being a subclass of
  `DataElementDefinition` ("a data element that represents a measurable
  physical property"), and placement is not a measurable physical property,
  so it would be a data element and not a parameter. The `Acu` already has
  22 `DataElementDefinition`s declared against it, including
  `position_in_optical_path`, which is the same shape of fact;
- a placement construct in the ontology along STEP's own lines
  (`context_dependent_shape_representation` → `axis2_placement_3d`),
  accepting the schema impact in exchange for a clean STEP mapping;
- no model change at all, with the exporter owning a layout per analysis.

§1.1 is the argument that bears on that choice: the closer the model is to
STEP's own construct, the closer import gets to transcription.

## 4. Running the spikes

They take a STEP file path; neither is wired into the app and neither is a
test. The AS1 file used here is not committed — it ships with the pythonocc
samples, and a copy is in `~/sandbox/pythonocc/as1-id-203.stp`.

```
python spikes/step_assembly/step_placements.py  <file.stp>
python spikes/step_assembly/step_mass_props.py  <file.stp> [density_kg_per_mm3]
```
