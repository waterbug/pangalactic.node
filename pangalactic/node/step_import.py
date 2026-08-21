# -*- coding: utf-8 -*-
"""
Read an assembly structure, with component placements, from a STEP file.

This module is the CAD-facing half of the STEP import:  it depends on
pythonocc but not on the orb, so it can be exercised without a repository.
It answers one question -- what does this STEP file say the assembly is, and
where does each component sit -- and returns plain data.

Turning that data into PGEF objects (Acu, ContextDependentShapeRepresentation,
Axis2Placement3D) is a separate step, so that neither half needs the other's
dependencies to be tested.

See pangalactic.node/NOTES_ON_STEP_IMPORT.md for the design, and
pangalactic.core/NOTES_ON_ONTOLOGY_AND_DB.md ("Component placement") for what
the objects mean.
"""
import os
import re
from collections import namedtuple

from OCC.Core.BRepGProp    import brepgprop
from OCC.Core.GProp        import GProp_GProps
from OCC.Core.gp           import gp_Dir
from OCC.Core.IFSelect     import IFSelect_RetDone
from OCC.Core.Interface    import Interface_Static
from OCC.Core.STEPCAFControl import STEPCAFControl_Reader
from OCC.Core.TCollection  import TCollection_AsciiString
from OCC.Core.TDF          import TDF_Label, TDF_LabelSequence, TDF_Tool
from OCC.Core.TDocStd      import TDocStd_Document
from OCC.Core.XCAFDoc      import XCAFDoc_DocumentTool

# OCC converts a STEP file's declared length unit to the unit named by the
# "xstep.cascade.unit" static, whose default is MM.  Verified against three
# vendors' exports of the same design, including one that declares INCH:  all
# arrive in mm.  We do *not* set that static -- it does not take reliably --
# so we read what it says and scale from there.  PGEF stores lengths in SI
# base units, i.e. metres.
UNIT_SCALE_TO_M = {'MM': 0.001, 'M': 1.0, 'CM': 0.01, 'INCH': 0.0254,
                   'FT': 0.3048}

# OCC's stand-in for a reference label that carries no name attribute
NO_NAME_PREFIX = '=>['

Placement = namedtuple('Placement', 'location axis ref_direction')
Placement.__doc__ = """A STEP axis2_placement_3d, in metres.

`location` is the origin of the component's frame, `axis` the direction of
its local z, `ref_direction` the direction of its local x -- each an (x, y, z)
tuple.  The placement is expressed in the frame of the *parent* assembly, as
STEP expresses it, so placements compose down a chain of usages.
"""


class Occurrence:
    """
    One node of a STEP assembly tree.

    An occurrence is a use of a prototype at a place, so it corresponds to a
    PGEF Acu; `prototype_key` identifies the thing being used, and two
    occurrences with the same `prototype_key` are two usages of one product.

    Attributes:
        name (str):  the occurrence name as the file gives it, or '' if it
            has none.  NOT trustworthy as a reference designator -- see
            NOTES_ON_STEP_IMPORT.md section 1.3 -- use `ref_des`.
        ref_des (str):  a reference designator, unique among siblings,
            derived from the file's name where that is usable and synthesized
            where it is not.
        prototype_key (str):  the XCAF entry of the prototype label, e.g.
            "0:1:1:3".  Stable within one reading of one file.
        prototype_name (str):  the prototype's name, or ''.
        placement (Placement or None):  where this occurrence sits in its
            parent's frame.  None for the root.
        children (list of Occurrence):  sub-occurrences.
        volume (float or None):  volume of the prototype's shape in m^3, or
            None if volumes were not requested or the shape has none.
    """

    def __init__(self, name='', ref_des='', prototype_key='',
                 prototype_name='', placement=None, children=None,
                 volume=None):
        self.name = name
        self.ref_des = ref_des
        self.prototype_key = prototype_key
        self.prototype_name = prototype_name
        self.placement = placement
        self.children = children if children is not None else []
        self.volume = volume

    def __repr__(self):
        n = len(self.children)
        return (f'<Occurrence {self.ref_des!r} of {self.prototype_name!r}'
                f'{f", {n} children" if n else ""}>')

    def walk(self):
        """
        Yield this occurrence and every occurrence below it, depth first.
        """
        yield self
        for child in self.children:
            yield from child.walk()

    def leaves(self):
        """
        Yield the occurrences below this one that have no children.
        """
        for occ in self.walk():
            if not occ.children:
                yield occ

    def prototypes(self):
        """
        Return {prototype_key: prototype_name} for everything in this tree,
        i.e. the distinct products the assembly is built from.
        """
        return {occ.prototype_key: occ.prototype_name
                for occ in self.walk() if occ.prototype_key}


# A STEP assembly may be exported as a set of files, the assembly naming its
# subassembly and part files.  In AP214 each reference is written as
#
#     #89=EXTERNAL_SOURCE(IDENTIFIER('mainbody_asm.stp'));
#
# and the identifier is the referenced file's own name, resolved relative to
# the referencing file.  Entity keywords are upper case by the standard, but
# the pattern is tolerant, and STEP entities may be wrapped across lines.
EXTERNAL_SOURCE_RE = re.compile(
    r"EXTERNAL_SOURCE\s*\(\s*IDENTIFIER\s*\(\s*'([^']*)'", re.IGNORECASE)


def external_references(path):
    """
    Get the names of the files a STEP file references directly.

    Args:
        path (str):  path to the STEP file

    Returns:
        list of str:  referenced file names, in the order first seen, without
        duplicates.  Empty if the file references nothing or cannot be read.
    """
    try:
        with open(path, errors='replace') as f:
            text = f.read()
    except OSError:
        return []
    seen, names = set(), []
    for name in EXTERNAL_SOURCE_RE.findall(text):
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def missing_references(path):
    """
    Find the files a STEP file needs, transitively, that are not beside it.

    A reference is resolved relative to the directory of the file that makes
    it, which is how a STEP reader will resolve it.  Files that do resolve are
    followed, so a reference missing two levels down is still reported.

    Args:
        path (str):  path to the STEP file

    Returns:
        list of tuple:  (missing file name, path of the file referencing it),
        in the order encountered.  Empty if everything resolves -- which is
        also the answer for a file that references nothing.
    """
    missing, visited = [], set()

    def walk(fpath):
        real = os.path.realpath(fpath)
        if real in visited:
            # a cycle, or a file reached by two routes
            return
        visited.add(real)
        directory = os.path.dirname(os.path.abspath(fpath))
        for name in external_references(fpath):
            child = os.path.join(directory, name)
            if os.path.exists(child):
                walk(child)
            else:
                missing.append((name, fpath))

    walk(path)
    return missing


def scale_to_m():
    """
    Get the factor that converts the lengths OCC produces into metres.

    Raises:
        ValueError:  if OCC is set to a unit we do not know how to convert.
    """
    unit = (Interface_Static.CVal('xstep.cascade.unit') or 'MM').upper()
    if unit not in UNIT_SCALE_TO_M:
        raise ValueError(f'unsupported OCC length unit "{unit}"')
    return UNIT_SCALE_TO_M[unit]


def read_document(path):
    """
    Read a STEP file into an XCAF document, preserving assembly structure and
    names.

    Args:
        path (str):  path to the STEP file

    Returns:
        TDocStd_Document
    """
    doc = TDocStd_Document('pgef-step-import')
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.SetColorMode(True)
    reader.SetLayerMode(True)
    if reader.ReadFile(path) != IFSelect_RetDone:
        raise IOError(f'could not read STEP file "{path}"')
    reader.Transfer(doc)
    return doc


def _entry(label):
    """
    Get an XCAF label's entry string (e.g. "0:1:1:3").
    """
    s = TCollection_AsciiString()
    TDF_Tool.Entry(label, s)
    return s.ToCString()


def _name(label):
    """
    Get a label's name, treating OCC's "no name" stand-in as no name.
    """
    name = label.GetLabelName() or ''
    return '' if name.startswith(NO_NAME_PREFIX) else name


def _placement(location, scale):
    """
    Convert a component's TopLoc_Location to a Placement in metres.

    An axis2_placement_3d is a location plus two directions; the directions
    are recovered by transforming the unit basis, which is exact and needs no
    choice of rotation sequence.
    """
    trsf = location.Transformation()
    t = trsf.TranslationPart()
    z = gp_Dir(0, 0, 1).Transformed(trsf)
    x = gp_Dir(1, 0, 0).Transformed(trsf)
    return Placement(location=(t.X() * scale, t.Y() * scale, t.Z() * scale),
                     axis=(z.X(), z.Y(), z.Z()),
                     ref_direction=(x.X(), x.Y(), x.Z()))


def _volume(shape_tool, label, scale):
    """
    Get the volume of a label's shape in m^3, or None if it has none.

    Translators emit leaves with no solid geometry (empty compounds,
    wireframe, surfaces); those have zero volume and are reported as None so
    that callers do not have to guess whether zero is a measurement.
    """
    props = GProp_GProps()
    brepgprop.VolumeProperties(shape_tool.GetShape(label), props)
    vol = props.Mass()
    return vol * scale ** 3 if vol > 0 else None


def _ref_designators(names, prototype_names):
    """
    Derive a reference designator for each of an assembly's components.

    The file's own names are used where they are usable -- present, and
    distinct from one another -- and synthesized from the prototype name and
    position otherwise.  Some translators name every occurrence after its
    prototype and some name none of them, so this cannot be left to the file.

    Args:
        names (list of str):  the occurrence names, '' where absent
        prototype_names (list of str):  the corresponding prototype names

    Returns:
        list of str:  a reference designator per component, unique among them
    """
    usable = all(names) and len(set(names)) == len(names)
    if usable:
        return list(names)
    ref_des = []
    counts = {}
    for name, proto in zip(names, prototype_names):
        base = proto or name or 'component'
        counts[base] = counts.get(base, 0) + 1
        ref_des.append(f'{base}-{counts[base]}')
    return ref_des


def read_assembly(path, with_volumes=False):
    """
    Read the assembly structure and component placements from a STEP file.

    Args:
        path (str):  path to the STEP file

    Keyword Args:
        with_volumes (bool):  also compute each occurrence's volume, which
            costs a shape traversal per node

    Returns:
        Occurrence:  the root of the assembly tree.  Its `placement` is None;
        every other occurrence's placement is expressed in its parent's frame.

    Raises:
        IOError:  if the file cannot be read
        ValueError:  if the file has no shapes, or OCC is set to a length
            unit we cannot convert
    """
    scale = scale_to_m()
    doc = read_document(path)
    shape_tool = XCAFDoc_DocumentTool.ShapeTool(doc.Main())
    roots = TDF_LabelSequence()
    shape_tool.GetFreeShapes(roots)
    if not roots.Length():
        raise ValueError(f'no shapes found in "{path}"')
    # NOTE: a STEP file may hold several unrelated root shapes; only the
    # first is read.  Nothing in the CAx-IF corpus has more than one, and an
    # assembly by definition has a single root.
    root_label = roots.Value(1)
    root = Occurrence(name=_name(root_label),
                      ref_des=_name(root_label),
                      prototype_key=_entry(root_label),
                      prototype_name=_name(root_label),
                      volume=(_volume(shape_tool, root_label, scale)
                              if with_volumes else None))
    _read_children(shape_tool, root_label, root, scale, with_volumes)
    return root


def _read_children(shape_tool, label, parent, scale, with_volumes):
    """
    Populate `parent.children` from the components of an assembly label.
    """
    if not shape_tool.IsAssembly(label):
        return
    comps = TDF_LabelSequence()
    shape_tool.GetComponents(label, comps)
    components = []
    for i in range(1, comps.Length() + 1):
        comp = comps.Value(i)
        proto = TDF_Label()
        shape_tool.GetReferredShape(comp, proto)
        components.append((comp, proto))
    ref_des = _ref_designators([_name(c) for c, _ in components],
                               [_name(p) for _, p in components])
    for (comp, proto), rd in zip(components, ref_des):
        occ = Occurrence(
                name=_name(comp),
                ref_des=rd,
                prototype_key=_entry(proto),
                prototype_name=_name(proto),
                placement=_placement(shape_tool.GetLocation(comp), scale),
                volume=(_volume(shape_tool, proto, scale)
                        if with_volumes else None))
        parent.children.append(occ)
        # descend into the *prototype*:  the sub-structure belongs to the
        # thing being used, not to this use of it
        _read_children(shape_tool, proto, occ, scale, with_volumes)
