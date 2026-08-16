#!/usr/bin/env python
"""
Spike:  what does pythonocc give us for assembly placements from a STEP file?

Walks the XCAF assembly tree and reports, for each component occurrence, the
prototype it instantiates and its placement expressed as an
`axis2_placement_3d` (location + axis + ref_direction).

Usage::

    python step_placements.py <file.stp> [...]

See ../../NOTES_ON_STEP_IMPORT.md for what this demonstrates and why.
"""
import sys

from OCC.Core.gp          import gp_Dir
from OCC.Core.IFSelect    import IFSelect_RetDone
from OCC.Core.STEPCAFControl import STEPCAFControl_Reader
from OCC.Core.TCollection import TCollection_AsciiString
from OCC.Core.TDF         import TDF_Label, TDF_LabelSequence, TDF_Tool
from OCC.Core.TDocStd     import TDocStd_Document
from OCC.Core.XCAFDoc     import XCAFDoc_DocumentTool


def read_doc(path):
    """
    Read a STEP file into an XCAF document, preserving assembly structure
    and names.

    Args:
        path (str):  path to the STEP file

    Returns:
        TDocStd_Document:  the populated document
    """
    doc = TDocStd_Document('pgef-step-spike')
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.SetColorMode(True)
    reader.SetLayerMode(True)
    if reader.ReadFile(path) != IFSelect_RetDone:
        raise IOError(f'could not read "{path}"')
    reader.Transfer(doc)
    return doc


def entry(label):
    """
    Get an XCAF label's entry string (e.g. "0:1:1:3"), which identifies it
    within the document.
    """
    s = TCollection_AsciiString()
    TDF_Tool.Entry(label, s)
    return s.ToCString()


def placement(trsf):
    """
    Recover an `axis2_placement_3d` from a transformation:  its location, its
    axis (the local Z direction) and its ref_direction (the local X).

    Args:
        trsf (gp_Trsf):  the occurrence's transformation

    Returns:
        tuple:  (location, axis, ref_direction), each an (x, y, z) tuple
    """
    t = trsf.TranslationPart()
    z = gp_Dir(0, 0, 1).Transformed(trsf)
    x = gp_Dir(1, 0, 0).Transformed(trsf)
    return ((t.X(), t.Y(), t.Z()),
            (z.X(), z.Y(), z.Z()),
            (x.X(), x.Y(), x.Z()))


def dump(path, out=sys.stdout):
    """
    Print the assembly tree of a STEP file with each occurrence's placement.
    """
    doc = read_doc(path)
    shape_tool = XCAFDoc_DocumentTool.ShapeTool(doc.Main())
    roots = TDF_LabelSequence()
    shape_tool.GetFreeShapes(roots)
    out.write(f'=== {path}\n')
    out.write(f'free (root) shapes: {roots.Length()}\n\n')

    def walk(label, depth=0):
        pad = '  ' * depth
        is_asm = shape_tool.IsAssembly(label)
        is_ref = shape_tool.IsReference(label)
        kind = 'assembly' if is_asm else ('component' if is_ref else 'part')
        out.write(f'{pad}{kind:9} {entry(label):10} {label.GetLabelName()}\n')
        proto = None
        if is_ref:
            # a component occurrence:  points at a prototype (the "Product")
            # and carries the placement of this instance of it
            proto = TDF_Label()
            shape_tool.GetReferredShape(label, proto)
            loc, axis, ref = placement(
                            shape_tool.GetLocation(label).Transformation())
            out.write(f'{pad}          -> prototype {entry(proto):10} '
                      f'{proto.GetLabelName()}\n')
            for tag, v in (('location     ', loc), ('axis (Z)     ', axis),
                           ('ref_dir (X)  ', ref)):
                out.write(f'{pad}          {tag} '
                          f'({v[0]:9.3f},{v[1]:9.3f},{v[2]:9.3f})\n')
        children = TDF_LabelSequence()
        if is_asm:
            shape_tool.GetComponents(label, children)
        elif is_ref and shape_tool.IsAssembly(proto):
            shape_tool.GetComponents(proto, children)
        for i in range(1, children.Length() + 1):
            walk(children.Value(i), depth + 1)

    for i in range(1, roots.Length() + 1):
        walk(roots.Value(i))


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for p in sys.argv[1:]:
        dump(p)
