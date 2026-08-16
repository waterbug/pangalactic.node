#!/usr/bin/env python
"""
Spike:  can 42's Body block (Mass, MoI, PoI, CoM) be derived from a STEP
assembly plus a mass per component?

Composes each leaf occurrence's placement down the assembly tree, takes its
volume / centroid / unit-density inertia tensor from OCC, scales that tensor
to the component's real mass, and rolls the lot up with the parallel-axis
theorem.

The roll-up is cross-checked against OCC computing the whole assembly in one
shot, which is the point of the spike:  it shows the arithmetic is right, not
merely plausible.

Usage::

    python step_mass_props.py <file.stp> [density_kg_per_mm3]

See ../../NOTES_ON_STEP_IMPORT.md for what this demonstrates and why.
"""
import sys

from OCC.Core.BRepGProp import brepgprop
from OCC.Core.GProp     import GProp_GProps
from OCC.Core.TDF       import TDF_Label, TDF_LabelSequence
from OCC.Core.TopLoc    import TopLoc_Location
from OCC.Core.XCAFDoc   import XCAFDoc_DocumentTool

from step_placements import read_doc

# NOTE:  the sample files are in mm; a real importer must read the units
# from the STEP file rather than assume them.  42 wants m and kg.
MM2_TO_M2 = 1e-6
# aluminium, kg/mm^3 -- stands in here for a per-component mass, which in
# PGEF would come from the `m` parameter of the component's HardwareProduct
DEFAULT_RHO = 2.7e-6


def leaf_occurrences(shape_tool, label, loc=None, path=(), out=None):
    """
    Collect every leaf (non-assembly) occurrence in the tree below a label,
    composing placements as the walk descends.

    Args:
        shape_tool (XCAFDoc_ShapeTool):  the document's shape tool
        label (TDF_Label):  label to walk from

    Keyword Args:
        loc (TopLoc_Location):  accumulated placement
        path (tuple):  accumulated occurrence names
        out (list):  accumulator

    Returns:
        list:  of (name_path, prototype_label, composed_location)
    """
    loc = loc if loc is not None else TopLoc_Location()
    out = out if out is not None else []
    if shape_tool.IsAssembly(label):
        comps = TDF_LabelSequence()
        shape_tool.GetComponents(label, comps)
        for i in range(1, comps.Length() + 1):
            comp = comps.Value(i)
            proto = TDF_Label()
            shape_tool.GetReferredShape(comp, proto)
            leaf_occurrences(
                shape_tool, proto,
                loc=loc.Multiplied(shape_tool.GetLocation(comp)),
                path=path + (comp.GetLabelName(),), out=out)
    else:
        out.append((path, label, loc))
    return out


def volume_props(shape):
    """
    Get the volume properties of a shape:  volume, centroid, and the inertia
    tensor about the centroid at unit density.
    """
    props = GProp_GProps()
    brepgprop.VolumeProperties(shape, props)
    return props


def roll_up(entries, rho):
    """
    Roll per-occurrence properties up to assembly mass, centre of mass and
    inertia about that centre of mass.

    Args:
        entries (list):  of (name_path, volume, centroid, GProp_GProps)
        rho (float):  density, kg/mm^3

    Returns:
        dict:  mass, com, moi, poi
    """
    mass = sum(vol * rho for _, vol, _, _ in entries)
    com = [sum(vol * rho * c.Coord(i) for _, vol, c, _ in entries) / mass
           for i in (1, 2, 3)]
    ixx = iyy = izz = ixy = ixz = iyz = 0.0
    for _, vol, c, props in entries:
        m = vol * rho
        tensor = props.MatrixOfInertia()     # about the part centroid
        scale = m / vol                      # unit density -> real mass
        dx, dy, dz = (c.Coord(i + 1) - com[i] for i in range(3))
        ixx += scale * tensor.Value(1, 1) + m * (dy * dy + dz * dz)
        iyy += scale * tensor.Value(2, 2) + m * (dx * dx + dz * dz)
        izz += scale * tensor.Value(3, 3) + m * (dx * dx + dy * dy)
        ixy += scale * tensor.Value(1, 2) - m * dx * dy
        ixz += scale * tensor.Value(1, 3) - m * dx * dz
        iyz += scale * tensor.Value(2, 3) - m * dy * dz
    return dict(mass=mass, com=com,
                moi=[i * MM2_TO_M2 for i in (ixx, iyy, izz)],
                poi=[i * MM2_TO_M2 for i in (ixy, ixz, iyz)])


def whole_assembly(shape_tool, root, rho):
    """
    Compute the same quantities from the whole assembly in one shot, as a
    check on `roll_up`.
    """
    props = volume_props(shape_tool.GetShape(root))
    c = props.CentreOfMass()
    t = props.MatrixOfInertia()
    return dict(mass=props.Mass() * rho,
                com=[c.X(), c.Y(), c.Z()],
                moi=[t.Value(i, i) * rho * MM2_TO_M2 for i in (1, 2, 3)],
                poi=[t.Value(*ij) * rho * MM2_TO_M2
                     for ij in ((1, 2), (1, 3), (2, 3))])


def report(path, rho=DEFAULT_RHO, out=sys.stdout):
    doc = read_doc(path)
    shape_tool = XCAFDoc_DocumentTool.ShapeTool(doc.Main())
    roots = TDF_LabelSequence()
    shape_tool.GetFreeShapes(roots)
    root = roots.Value(1)

    entries = []
    out.write(f'=== {path}\n')
    out.write(f'{"occurrence":36} {"prototype":12} {"volume":>11} '
              f'{"centroid (assembly coords)":>32}\n')
    for names, proto, loc in leaf_occurrences(shape_tool, root):
        props = volume_props(shape_tool.GetShape(proto).Located(loc))
        c, vol = props.CentreOfMass(), props.Mass()
        entries.append((names, vol, c, props))
        out.write(f'{"/".join(names):36.36} {proto.GetLabelName():12.12} '
                  f'{vol:11.1f} ({c.X():9.2f},{c.Y():9.2f},{c.Z():9.2f})\n')

    rolled = roll_up(entries, rho)
    whole = whole_assembly(shape_tool, root, rho)
    out.write(f'\n{len(entries)} leaf occurrences, rho={rho} kg/mm^3\n\n')
    out.write(f'{"":14} {"rolled up from parts":>34} '
              f'{"whole assembly, one shot":>34}\n')
    fmt = lambda v: '[' + ', '.join(f'{x:.6f}' for x in v) + ']'
    out.write(f'{"mass (kg)":14} {rolled["mass"]:>34.4f} '
              f'{whole["mass"]:>34.4f}\n')
    for key, label in (('com', 'CoM (mm)'), ('moi', 'MoI (kg-m^2)'),
                       ('poi', 'PoI (kg-m^2)')):
        out.write(f'{label:14} {fmt(rolled[key]):>34} '
                  f'{fmt(whole[key]):>34}\n')
    out.write('\nthe left column is 42\'s Body block; the right column is '
              'the check on it\n')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    rho = float(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_RHO
    report(sys.argv[1], rho=rho)
