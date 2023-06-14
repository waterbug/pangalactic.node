"""
A set of custom TableModels for use with QTableView.
"""
# stdlib
import os, re

# PyQt
from PyQt5.QtCore import (Qt, QAbstractTableModel, QMimeData, QModelIndex,
                          QSortFilterProxyModel, QVariant)
from PyQt5.QtGui import QIcon, QPixmap

# pangalactic
from pangalactic.core             import prefs, state
from pangalactic.core.meta        import MAIN_VIEWS
from pangalactic.core.names       import pname_to_header, to_media_name
from pangalactic.core.parametrics import de_defz, get_pval_as_str, parm_defz
from pangalactic.core.uberorb     import orb
from pangalactic.node.utils       import get_pixmap


test_mappings = [dict([('spam','00'), ('eggs','01'), ('more spam','02')]),
                 dict([('spam','10'), ('eggs','11'), ('more spam','12')]),
                 dict([('spam','20'), ('eggs','21'), ('more spam','22')])]


class ListTableModel(QAbstractTableModel):
    """
    A table model based on a list of lists.
    """
    def __init__(self, datain, parent=None, **kwargs):
        super().__init__(parent=parent, **kwargs)
        # TODO: some validity checking on the data ...
        self.datain = datain or [{0:'no data'}]

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        # if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            # return self.columns()[section]
        return QAbstractTableModel.headerData(self, section, orientation, role)

    def rowCount(self, parent=QModelIndex()):
        return len(self.datain)

    def columnCount(self, parent):
        return len(self.datain[0])

    def data(self, index, role):
        if not index.isValid():
            return QVariant()
        elif role != Qt.DisplayRole:
            return QVariant()
        return self.datain[index.row()][index.column()]


class MappingTableModel(QAbstractTableModel):
    """
    A table model based on a list of dict instances.

    Attributes:
        ds (list):  list of dict instances
        aligns (list of str):  list of alignments ("left", "right", or
            "center") for each column
        as_library (bool): (default: False) if True, provide icons, etc.
        default_icon (QIcon): default icon associated with a row
    """
    def __init__(self, ds, as_library=False, view=None, icons=None,
                 aligns=None, parent=None, **kwargs):
        """
        Args:
            ds (list):  list of dict instances

        Keyword Args:
            as_library (bool): (default: False) if True, provide icons, etc.
            view (list of str):  list of column names
            icons (list of icons):  list of icons by row
            aligns (list of str):  list of alignments ("left", "right", or
                "center") for each column
            parent (QWidget):  parent widget
        """
        super().__init__(parent=parent, **kwargs)
        # TODO: some validity checking on the data ...
        self.view = view or []
        self.icons = icons or []
        _aligns = dict(left=Qt.AlignLeft, right=Qt.AlignRight,
                       center=Qt.AlignHCenter)
        aligns = aligns or []
        self.aligns = [_aligns.get(a, Qt.AlignLeft) for a in aligns]
        self.as_library = as_library
        # self.ds = ds or [{0:'no data'}]
        self.ds = ds or []
        icon_dir = state.get('icon_dir', os.path.join(orb.home, 'icons'))
        self.default_icon = QIcon(QPixmap(os.path.join(icon_dir,
                                  'box'+state.get('icon_type', '.png'))))

    def columns(self):
        if self.view:
            return self.view
        if self.ds:
            return list(self.ds[0].keys())
        return ['id']

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.columns()[section]
        return QAbstractTableModel.headerData(self, section, orientation, role)

    def rowCount(self, parent=QModelIndex()):
        return len(self.ds)

    def columnCount(self, parent):
        try:
            if self.view:
                return len(self.view)
            elif self.ds:
                return len(self.ds[0])
            else:
                return 1
        except:
            return 1

    def setData(self, index, value, role=Qt.UserRole):
        """
        Reimplementation in which 'value' is a dict.
        """
        if index.isValid():
            if index.row() < len(self.ds):
                self.ds[index.row()] = value
            else:
                orb.log.debug('* setData(): index is out of range')
            # NOTE the 3rd arg is an empty list -- reqd for pyqt5
            # (or the actual role(s) that changed, e.g. [Qt.EditRole])
            self.dataChanged.emit(index, index, [])
            return True
        return False

    def insertRows(self, row, count, parent=QModelIndex()):
        if row <= len(self.ds):
            self.beginInsertRows(QModelIndex(), row, row+count-1)
            for n in range(count):
                self.ds.insert(row, {})
            self.endInsertRows()
            return True
        else:
            return False

    def removeRows(self, row, count, parent=QModelIndex()):
        if row + count - 1 < len(self.ds):
            self.beginRemoveRows(QModelIndex(), row, row + count - 1)
            del self.ds[row : row + count]
            self.endRemoveRows()
            return True
        else:
            return False

    def get_icon(self, row):
        return self.icons[row]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return QVariant()
        elif (self.as_library and role == Qt.DecorationRole
              and index.column() == 0):
            try:
                return self.get_icon(index.row())
            except IndexError:
                return self.default_icon
        elif role == Qt.TextAlignmentRole:
            try:
                return self.aligns[index.column()]
            except IndexError:
                return Qt.AlignLeft
        elif role != Qt.DisplayRole:
            return QVariant()
        return self.ds[index.row()].get(
                       self.columns()[index.column()], '')


class NullObject(object):
    def __init__(self):
        self.oid = None
        self.id = 'None'
        self.name = ''
        self.description = ''


class ObjectTableModel(MappingTableModel):
    """
    A MappingTableModel subclass based on a list of objects.

    Attributes:
        cname (str): class name of the objects
        col_labels (list):  list of column header labels (strings)
    """

    def __init__(self, objs, view=None, with_none=False, as_library=False,
                 parent=None, **kwargs):
        """
        Args:
            objs (list):  list of objects

        Keyword Args:
            view (list):  list of field names (columns)
            with_none (bool):  (default: False) if True, include a "NullObject"
                (used for ObjectSelectionDialog when a "None" choice is needed)
            as_library (bool): (default: False) if True, provide icons, etc.
            parent (QWidget):  parent widget
        """
        # orb.log.debug("* ObjectTableModel initializing ...")
        self.objs = objs or []
        icons = []
        if as_library:
            self.as_library = True
            # orb.log.debug("  ... as library ...")
            icons = [QIcon(get_pixmap(obj)) for obj in objs]
        # orb.log.debug("  ... with {} objects.".format(len(objs)))
        view = view or ['id']
        self.cname = ''
        if self.objs:
            self.cname = objs[0].__class__.__name__
            self.schema = orb.schemas.get(self.cname) or {}
            if self.schema and view:
                # sanity-check view
                view = [a for a in view if
                             (a in self.schema['field_names']
                              or a in parm_defz
                              or a in de_defz)]
            if not view:
                if self.cname == 'HardwareProduct':
                    if as_library:
                        view = prefs.get('hw_library_view') or ['id', 'name',
                                                                'product_type']
                    else:
                        view = prefs.get('hw_db_view') or MAIN_VIEWS.get(
                                'HardwareProduct',
                                ['id', 'name', 'product_type', 'description'])
                elif self.cname == 'Requirement':
                    view = prefs.get('rqt_mgr_view') or []
                else:
                    view = MAIN_VIEWS.get(self.cname,
                                           ['id', 'name', 'description'])
            if with_none:
                null_obj = NullObject()
                for name in view:
                    val = ''
                    if name == 'id':
                        val = 'None'
                    setattr(null_obj, name, val)
                self.objs.insert(0, null_obj)
            ds = [orb.obj_view_to_dict(o, view) for o in self.objs]
        else:
            # ds = [{0:'no data'}]
            ds = []
            view = view or ['id']
            if with_none:
                null_obj = NullObject()
                for name in view:
                    val = ''
                    if name == 'id':
                        val = 'None'
                    setattr(null_obj, name, val)
                self.objs = [null_obj]
                d = dict()
                d['id'] = 'None'
                ds = [d]
        super().__init__(ds, as_library=as_library, icons=icons,
                         view=view, parent=parent, **kwargs)
        # self.view = view[:]

    @property
    def oids(self):
        if hasattr(self, 'objs') and self.objs:
            return [getattr(o, 'oid', '') for o in self.objs if o is not None]
        else:
            return []

    @property
    def view(self):
        as_library = getattr(self, 'as_library', False) or False
        if self.cname == 'HardwareProduct' and as_library:
            return prefs.get('hw_library_view') or ['id', 'name',
                                                    'product_type']
        elif self.cname == 'HardwareProduct':
            return prefs.get('hw_db_view') or ['id', 'name', 'product_type']
        elif self.cname == 'Requirement':
            return prefs.get('rqt_mgr_view') or ['id', 'name', 'description']
        else:
            return prefs.get('views', {}).get(self.cname) or ['id', 'name',
                                                              'description']

    @view.setter
    def view(self, v):
        as_library = getattr(self, 'as_library', False) or False
        if self.cname == 'HardwareProduct' and as_library:
            prefs['hw_library_view'] = v
        elif self.cname == 'HardwareProduct':
            prefs['hw_db_view'] = v
        elif self.cname == 'Requirement':
            prefs['rqt_mgr_view'] = v
        else:
            if not prefs.get('views'):
                prefs['views'] = {}
            prefs['views'][self.cname] = v

    @property
    def col_labels(self):
        if self.objs:
            return [pname_to_header(x, self.cname) for x in self.view]
        else:
            return ['No Data']

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if (role == Qt.DisplayRole and orientation == Qt.Horizontal
            and section < len(self.col_labels)):
            return self.col_labels[section]
        return QAbstractTableModel.headerData(self, section, orientation, role)

    def get_icon(self, row):
        """
        Overrides get_icon() method of MappingTable, so icon for the object can
        be returned dynamically.
        """
        return QIcon(get_pixmap(self.objs[row]))

    def setData(self, index, obj, role=Qt.UserRole):
        """
        Reimplementation using an object as the 'value' (based on underlying
        MappingTableModel setData, which takes a dict as the 'value').
        """
        try:
            # apply MappingTableModel.setData, which takes a dict as value
            super().setData(index, orb.obj_view_to_dict(obj, self.view))
            # this 'dataChanged' should not be necessary, since 'dataChanged is
            # emitted by the 'setData' we just called
            # super().dataChanged.emit(index, index)
            return True
        except:
            return False

    def add_object(self, obj):
        n = self.rowCount()
        self.insertRows(n, 1)
        idx = self.createIndex(n, 0)
        self.setData(idx, obj)
        self.objs.append(obj)
        return True

    def add_objects(self, objs):
        n = self.rowCount()
        m = len(objs)
        self.insertRows(n, m)
        for i, obj in enumerate(objs):
            idx = self.createIndex(n + i, 0)
            self.setData(idx, obj)
        self.objs += objs
        return True

    def mod_object(self, oid):
        """
        Replace an object (identified by oid) with a more recently modified
        instance of itself.
        """
        orb.log.debug("* ObjectTableModel.mod_object() ...")
        try:
            row = self.oids.index(oid)  # raises ValueError if problem
            orb.log.debug(f"    oid found at row {row}")
            idx = self.index(row, 0, parent=QModelIndex())
            obj = orb.get(oid)
            self.setData(idx, obj)
            return idx
        except:
            # possibly because my C++ object has been deleted ...
            txt = f'oid "{oid}" not found in table.'
            orb.log.debug(f"    {txt}")
        return QModelIndex()

    def del_object(self, oid):
        # now takes oid instead of obj so can remove row that corresponded to
        # the object even if the object has already been deleted from the db
        obj = orb.get(oid)
        if not obj:
            orb.log.debug('* ObjectTableModel.del_object(): oid not found.')
        try:
            if obj in self.objs:
                row = self.objs.index(obj)  # raises ValueError if problem
            elif oid in self.oids:
                row = self.oids.index(oid)  # raises ValueError if problem
            else:
                return False
            self.objs = self.objs[:row] + self.objs[row+1:]
            self.removeRows(row, 1, QModelIndex())
            return True
        except:
            return False

    def mimeTypes(self):
        return [to_media_name(self.cname)]

    def mimeData(self):
        mime_data = QMimeData()
        mime_data.setData(to_media_name(self.cname), 'mimeData')
        return mime_data

    def supportedDropActions(self):
        return Qt.CopyAction


class CompareTableModel(MappingTableModel):
    """
    A table model for the side-by-side comparison of a set of objects (columns)
    by a set of parameters (rows).
    """
    def __init__(self, objs, parameters, parent=None, **kwargs):
        """
        Initialize the table.

        Args:
            objs (Identifiable):  objects to be compared
            parameters (list of str):  ids of parameters to compare by
        """
        self.objs = objs
        self.parameters = parameters
        self.column_labels = ['Parameter']
        if objs:
            self.ds = []
            for pid in self.parameters:
                row_dict = {}
                pd = orb.select('ParameterDefinition', id=pid)
                row_dict['Parameter'] = pd.name
                for o in self.objs:
                    val = get_pval_as_str(o.oid, pid)
                    row_dict[o.oid] = val
                self.ds.append(row_dict)
            if self.objs:
                self.column_labels = [o.name for o in self.objs]
                self.column_labels.insert(0, 'Parameter')
            else:
                self.column_labels = list(self.ds[0].keys())
        else:
            self.ds = [{0:'no data'}]
        super().__init__(self.ds, parent=parent, **kwargs)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.column_labels[section]
        return QAbstractTableModel.headerData(self, section, orientation, role)


# class DFTableModel(QAbstractTableModel):
    # """
    # A table model based on a Pandas `DataFrame`.
    # """
    # def __init__(self, df, parent=None, **kwargs):
        # super().__init__(parent=parent, **kwargs)
        # # TODO: some validity checking on the data ...
        # self.df = df or pandas.DataFrame([{0:'no data'}])

    # def columns(self):
        # return self.df[0].keys()

    # def headerData(self, section, orientation, role=Qt.DisplayRole):
        # if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            # return self.columns()[section]
        # return QAbstractTableModel.headerData(self, section, orientation, role)

    # def rowCount(self, parent=QModelIndex()):
        # return len(self.df)

    # def columnCount(self, parent):
        # return len(self.df[0])

    # def data(self, index, role):
        # if not index.isValid():
            # return QVariant()
        # elif role != Qt.DisplayRole:
            # return QVariant()
        # return self.df[index.row()].get(
                        # self.columns()[index.column()], '')


class NumericSortModel(QSortFilterProxyModel):

    versionpat = r'[0-9][0-9]*(\.[0-9][0-9]*)*'

    def is_version(self, s):
        m = re.match(self.versionpat, str(s))
        return m.group(0) == s

    def lessThan(self, left, right):
        # Numeric Sort
        # NOTE:  this must test using 'canConvert' first, then test the
        # conversion *results* too (which might not be successful -- i.e.,
        # might return False -- even if 'canConvert' returns True).
        try:
            float(left.data())
            float(right.data())
            lvalue = float(left.data())
            rvalue = float(right.data())
        except:
            return QSortFilterProxyModel.lessThan(self, left, right)
        if lvalue and rvalue:
            return lvalue < rvalue
        else:
            return QSortFilterProxyModel.lessThan(self, left, right)


class SpecialSortModel(QSortFilterProxyModel):
    """
    Model that sorts on "."-delimited string of concatenated segments, which
    may be one of the 3 patterns:

        version:  i.j.[k...] (integer segments)
        numeric:  i.j (integer segments)
        reqt id:  [project id].[sequence].[version]
    """
    versionpat = r'[0-9][0-9]*(\.[0-9][0-9]*)*'
    numpat = r'[0-9][0-9]*(\.[0-9][0-9]*)'
    reqpat = r'[a-zA-Z][a-zA-Z0-9]*(\.[0-9][0-9]*)(\.[a-zA-Z0-9][a-zA-Z0-9]*)'

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setSortCaseSensitivity(Qt.CaseInsensitive)

    def is_version(self, s):
        try:
            m = re.match(self.versionpat, str(s))
            return m.group(0) == s
        except:
            return False

    def is_numeric(self, s):
        try:
            m = re.match(self.numpat, str(s))
            return m.group(0) == s
        except:
            return False

    def is_reqt_id(self, s):
        try:
            m = re.match(self.reqpat, str(s))
            return m.group(0) == s
        except:
            return False

    def lessThan(self, left, right):
        # Version Sort
        # * tests for strings consisting only of integers separated by dots
        # * sort is done by leftmost integer, then sequentially by the next
        #   integer to the right, etc.
        # **** TODO:  needs exception handling!
        if (self.is_version(left.data()) and
            self.is_version(right.data())):
            lefties = [int(i) for i in left.data().split('.')]
            righties = [int(i) for i in right.data().split('.')]
            return lefties < righties
        # Numeric Sort
        # * tests for strings of integers separated by a single dot.
        elif (self.is_numeric(left.data()) and
              self.is_numeric(right.data())):
            lvalue = float(left.data())
            rvalue = float(right.data())
            if lvalue and rvalue:
                return lvalue < rvalue
            else:
                return QSortFilterProxyModel.lessThan(self, left, right)
        # Requirement ID Sort
        # * tests for strings of [project id].[seq].[version]
        elif (self.is_reqt_id(left.data()) and
              self.is_reqt_id(right.data())):
            ld = left.data().split('.')
            if len(ld) == 3:
                lvalue = [ld[0].lower(), int(ld[1]), ld[2].lower()]
            else:
                lvalue = ld
            rd = right.data().split('.')
            if len(rd) == 3:
                rvalue = [rd[0].lower(), int(rd[1]), rd[2].lower()]
            else:
                rvalue = rd
            if lvalue and rvalue:
                return lvalue < rvalue
            else:
                return QSortFilterProxyModel.lessThan(self, left, right)
        else:
            return QSortFilterProxyModel.lessThan(self, left, right)


