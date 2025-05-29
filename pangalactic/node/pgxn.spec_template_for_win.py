# -*- mode: python -*-

block_cipher = None

import os
import pangalactic.core.ontology
import pangalactic.core.ref_db
import pangalactic.core.test.data
import pangalactic.core.test.vault
import OCC

onto_mod_path = pangalactic.core.ontology.__path__[0]
onto_paths = [(os.path.join(onto_mod_path, p),
               os.path.join('pangalactic', 'core', 'ontology'))
              for p in os.listdir(onto_mod_path)
              if not p.startswith('__init__')]
data_mod_path = pangalactic.core.test.data.__path__[0]
data_paths = [(os.path.join(data_mod_path, p),
               os.path.join('pangalactic', 'core', 'test', 'data'))
              for p in os.listdir(data_mod_path)
              if not p.startswith('__init__')]
ref_db_mod_path = pangalactic.core.ref_db.__path__[0]
ref_db_paths = [(os.path.join(ref_db_mod_path, p),
               os.path.join('pangalactic', 'core', 'ref_db'))
               for p in os.listdir(ref_db_mod_path)
               if not p.startswith('__init__')]
vault_mod_path = pangalactic.core.test.vault.__path__[0]
vault_paths = [(os.path.join(vault_mod_path, p),
                os.path.join('pangalactic', 'core', 'test', 'vault'))
               for p in os.listdir(vault_mod_path)
               if not p.startswith('__init__')]

import pangalactic.node.docs
import pangalactic.node.docs.images
import pangalactic.node.icons
import pangalactic.node.images
doc_mod_path = pangalactic.node.docs.__path__[0]
doc_paths = [(os.path.join(doc_mod_path, p),
              os.path.join('pangalactic', 'node', 'docs'))
              for p in os.listdir(doc_mod_path)
              if (not p.startswith('__init__') and
                  not p.startswith('images'))]
doc_img_mod_path = pangalactic.node.docs.images.__path__[0]
doc_img_paths = [(os.path.join(doc_img_mod_path, p),
                  os.path.join('pangalactic', 'node', 'docs', 'images'))
                  for p in os.listdir(doc_img_mod_path)
                  if not p.startswith('__init__')]
icon_mod_path = pangalactic.node.icons.__path__[0]
icon_paths = [(os.path.join(icon_mod_path, p),
               os.path.join('pangalactic', 'node', 'icons'))
              for p in os.listdir(icon_mod_path)
              if not p.startswith('__init__')]
image_mod_path = pangalactic.node.images.__path__[0]
image_paths = [(os.path.join(image_mod_path, p),
               os.path.join('pangalactic', 'node', 'images'))
               for p in os.listdir(image_mod_path)
               if not p.startswith('__init__')]
occ_pkg_path = os.path.dirname(OCC.__file__)
casroot = os.path.join(occ_pkg_path, '..', '..', '..',
                       'Library', 'share', 'opencascade')
casroot_paths = [(casroot, os.path.join('pangalactic', 'node', 'casroot'))]
platforms = os.path.join(occ_pkg_path, '..', '..', '..',
                         'Library', 'plugins', 'platforms')
platforms_paths = [(platforms, 'platforms')]

data_files = [(os.path.join('test', 'data'),
               os.path.join('node', 'test', 'data')),
              (os.path.join('test', 'vault'),
               os.path.join('node', 'test', 'vault')),
              (os.path.join('docs'),
               os.path.join('node', 'docs')),
              ('images', os.path.join('node', 'images'))
             ]
data_files += onto_paths
data_files += data_paths
data_files += doc_paths
data_files += doc_img_paths
data_files += vault_paths
data_files += icon_paths
data_files += image_paths
data_files += ref_db_paths
data_files += casroot_paths
data_files += platforms_paths

a = Analysis(['main.py'],
             pathex=[ {{ path to pangalactic.node module in source code }} ],
             binaries=[( {{ path to installed 'TKOpenGl.dll' binary }},
                        'bin')],
             datas=data_files,
             hiddenimports=['openpyxl.cell._writer', '_sysconfigdata',
             'pangalactic.core', 'pangalactic.core.ontology',
             'pangalactic.node', 'pangalactic.node.pangalaxian',
             'sqlalchemy.ext.baked', 'sip', 'PyQt5', 'PyQt5.QtCore',
             'PyQt5.QtGui', 'PyQt5.QtWidgets', 'OCC.Core.Adaptor2d',
             'OCC.Core.BRepSweep', 'OCC.Core.GeomLProp', 'OCC.Core.MAT',
             'OCC.Core.StepGeom', 'OCC.Core.Adaptor3d', 'OCC.Core.BRepTools',
             'OCC.Core.GeomPlate', 'OCC.Core.MeshVS', 'OCC.Core.StepRepr',
             'OCC.Core.AdvApp2Var', 'OCC.Core.BRepTopAdaptor',
             'OCC.Core.GeomProjLib', 'OCC.Core.Message',
             'OCC.Core.STEPSelections', 'OCC.Core.AdvApprox',
             'OCC.Core.BSplCLib', 'OCC.Core.Geom', 'OCC.Core.MMgt',
             'OCC.Core.StepShape', 'OCC.Core.AIS', 'OCC.Core.BSplSLib',
             'OCC.Core.GeomTools', 'OCC.Core.NCollection',
             'OCC.Core.StepToGeom', 'OCC.Core.AppBlend', 'OCC.Core.ChFi2d',
             'OCC.Core.GeomToStep', 'OCC.Core.NLPlate',
             'OCC.Core.StepToTopoDS', 'OCC.Core.AppCont', 'OCC.Core.ChFi3d',
             'OCC.Core.gp', 'OCC.Core.OSD', 'OCC.Core.StlAPI',
             'OCC.Core.AppDef', 'OCC.Core.ChFiDS', 'OCC.Core.GProp',
             'OCC.Core.Plate', 'OCC.Core.StlMesh', 'OCC.Core.AppParCurves',
             'OCC.Core.ChFiKPart', 'OCC.Core.GraphDS', 'OCC.Core.PLib',
             'OCC.Core.StlTransfer', 'OCC.Core.ApproxInt', 'OCC.Core.Contap',
             'OCC.Core.Graphic3d', 'OCC.Core.Plugin', 'OCC.Core.Storage',
             'OCC.Core.Approx', 'OCC.Core.Convert', 'OCC.Core.GraphTools',
             'OCC.Core.Poly', 'OCC.Core.Sweep', 'OCC.Core.AppStdL',
             'OCC.Core.CPnts', 'OCC.Core.HatchGen', 'OCC.Core.Precision',
             'OCC.Core.TColGeom2d', 'OCC.Core.AppStd', 'OCC.Core.CSLib',
             'OCC.Core.Hatch', 'OCC.Core.Primitives', 'OCC.Core.TColGeom',
             'OCC.Core.Aspect', 'OCC.Core.Dico', 'OCC.Core.Hermit',
             'OCC.Core.ProjLib', 'OCC.Core.TColgp', 'OCC.Core.Bisector',
             'OCC.Core.Draft', 'OCC.Core.HLRAlgo', 'OCC.Core.Prs3d',
             'OCC.Core.TCollection', 'OCC.Core.BiTgte', 'OCC.Core.DsgPrs',
             'OCC.Core.HLRAppli', 'OCC.Core.PrsMgr', 'OCC.Core.TColQuantity',
             'OCC.Core.BlendFunc', 'OCC.Core.Dynamic', 'OCC.Core.HLRBRep',
             'OCC.Core.Quantity', 'OCC.Core.TColStd', 'OCC.Core.Blend',
             'OCC.Core.ElCLib', 'OCC.Core.HLRTopoBRep', 'OCC.Core.Resource',
             'OCC.Core.TDataStd', 'OCC.Core.BndLib', 'OCC.Core.ElSLib',
             'OCC.Core.IFSelect', 'OCC.Core.RWStepAP203', 'OCC.Core.TDataXtd',
             'OCC.Core.Bnd', 'OCC.Core.ExprIntrp', 'OCC.Core.IGESCAFControl',
             'OCC.Core.RWStepAP214', 'OCC.Core.TDF', 'OCC.Core.BOPAlgo',
             'OCC.Core.Expr', 'OCC.Core.IGESControl', 'OCC.Core.RWStepBasic',
             'OCC.Core.TDocStd', 'OCC.Core.BOPCol', 'OCC.Core.Extrema',
             'OCC.Core.Image', 'OCC.Core.RWStepGeom', 'OCC.Core.TFunction',
             'OCC.Core.BOPDS', 'OCC.Core.FairCurve', 'OCC.Core.IncludeLibrary',
             'OCC.Core.RWStepRepr', 'OCC.Core.TNaming', 'OCC.Core.BOPInt',
             'OCC.Core.FEmTool', 'OCC.Core.RWStepShape', 'OCC.Core.TopAbs',
             'OCC.Core.BOPTools', 'OCC.Core.FilletSurf', 'OCC.Core.IntAna2d',
             'OCC.Core.RWStl', 'OCC.Core.TopBas', 'OCC.Core.BRepAdaptor',
             'OCC.Core.FSD', 'OCC.Core.IntAna', 'OCC.Core.Select3D',
             'OCC.Core.TopClass', 'OCC.Core.BRepAlgoAPI', 'OCC.Core.IntCurve',
             'OCC.Core.SelectBasics', 'OCC.Core.TopCnx', 'OCC.Core.BRepAlgo',
             'OCC.Core.GccAna', 'OCC.Core.IntCurvesFace', 'OCC.Core.SelectMgr',
             'OCC.Core.TopExp', 'OCC.Core.BRepApprox', 'OCC.Core.GccEnt',
             'OCC.Core.IntCurveSurface', 'OCC.Core.ShapeAlgo',
             'OCC.Core.TopLoc', 'OCC.Core.BRepBlend', 'OCC.Core.GccGeo',
             'OCC.Core.InterfaceGraphic', 'OCC.Core.ShapeAnalysis',
             'OCC.Core.TopoDS', 'OCC.Core.BRepBndLib', 'OCC.Core.GccInt',
             'OCC.Core.Interface', 'OCC.Core.ShapeBuild',
             'OCC.Core.TopoDSToStep', 'OCC.Core.BRepBuilderAPI',
             'OCC.Core.GccIter', 'OCC.Core.Intf', 'OCC.Core.ShapeConstruct',
             'OCC.Core.TopOpeBRepBuild', 'OCC.Core.BRepCheck',
             'OCC.Core.GCE2d', 'OCC.Core.IntImpParGen', 'OCC.Core.ShapeCustom',
             'OCC.Core.TopOpeBRepDS', 'OCC.Core.BRepClass3d', 'OCC.Core.gce',
             'OCC.Core.IntImp', 'OCC.Core.ShapeExtend', 'OCC.Core.TopOpeBRep',
             'OCC.Core.BRepClass', 'OCC.Core.GCPnts', 'OCC.Core.IntPatch',
             'OCC.Core.ShapeFix', 'OCC.Core.TopOpeBRepTool',
             'OCC.Core.BRepExtrema', 'OCC.Core.GC', 'OCC.Core.IntPolyh',
             'OCC.Core.ShapeProcessAPI', 'OCC.Core.TopTools',
             'OCC.Core.BRepFeat', 'OCC.Core.Geom2dAdaptor', 'OCC.Core.IntPoly',
             'OCC.Core.ShapeProcess', 'OCC.Core.TopTrans',
             'OCC.Core.BRepFilletAPI', 'OCC.Core.Geom2dAPI',
             'OCC.Core.IntRes2d', 'OCC.Core.ShapeUpgrade', 'OCC.Core.TPrsStd',
             'OCC.Core.BRepFill', 'OCC.Core.Geom2dConvert', 'OCC.Core.Intrv',
             'OCC.Core.SortTools', 'OCC.Core.TShort', 'OCC.Core.BRepGProp',
             'OCC.Core.Geom2dGcc', 'OCC.Core.IntStart', 'OCC.Core.Standard',
             'OCC.Core.UnitsAPI', 'OCC.Core.BRepIntCurveSurface',
             'OCC.Core.Geom2dHatch', 'OCC.Core.IntSurf', 'OCC.Core.StdFail',
             'OCC.Core.Units', 'OCC.Core.BRepLib', 'OCC.Core.Geom2dInt',
             'OCC.Core.IntTools', 'OCC.Core.StdPrs', 'OCC.Core.V3d',
             'OCC.Core.BRepLProp', 'OCC.Core.Geom2dLProp', 'OCC.Core.IntWalk',
             'OCC.Core.StdSelect', 'OCC.Core.Visual3d', 'OCC.Core.BRepMAT2d',
             'OCC.Core.Geom2d', 'OCC.Core.Law', 'OCC.Core.StepAP203',
             'OCC.Core.Visualization', 'OCC.Core.BRepMesh', 'OCC.Core.GeomAbs',
             'OCC.Core.LocalAnalysis', 'OCC.Core.StepAP209',
             'OCC.Core.XBRepMesh', 'OCC.Core.BRepOffsetAPI',
             'OCC.Core.GeomAdaptor', 'OCC.Core.LocOpe', 'OCC.Core.StepAP214',
             'OCC.Core.XCAFApp', 'OCC.Core.BRepOffset', 'OCC.Core.GeomAPI',
             'OCC.Core.LProp3d', 'OCC.Core.StepBasic', 'OCC.Core.XCAFDoc',
             'OCC.Core.BRepPrimAPI', 'OCC.Core.GeomConvert', 'OCC.Core.LProp',
             'OCC.Core.STEPCAFControl', 'OCC.Core.XCAFPrs',
             'OCC.Core.BRepPrim', 'OCC.Core.GeomFill', 'OCC.Core.MAT2d',
             'OCC.Core.STEPConstruct', 'OCC.Core.XSControl',
             'OCC.Core.BRepProj', 'OCC.Core.GeomInt', 'OCC.Core.Materials',
             'OCC.Core.STEPControl', 'OCC.Core.BRep', 'OCC.Core.GeomLib',
             'OCC.Core.math', 'OCC.Core.STEPEdit', 'rdflib.plugins.memory',
             'rdflib.plugins.parsers.rdfxml'],
             hookspath=[],
             runtime_hooks=[],
             excludes=['docutils', 'FixTk', 'tcl', 'tk', '_tkinter', 'tkinter',
                'Tkinter', 'pyqt4', 'PySide', 'IPython', 'ipython', 'pdb',
                'sphinx', 'zmq'],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)
pyz = PYZ(a.pure, a.zipped_data,
          cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='run_pgxn',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=True )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='pgxn')

