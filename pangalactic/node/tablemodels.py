"""
A set of custom TableModels for use with QTableView.
"""
# stdlib
import os, re

# louie
# from louie import dispatcher

# pandas
# import pandas

# PyQt
from PyQt5.QtCore import (Qt, QAbstractTableModel, QMimeData, QModelIndex,
                          QSortFilterProxyModel, QVariant)
from PyQt5.QtGui import QIcon, QPixmap

# pangalactic
from pangalactic.core                 import prefs, state
from pangalactic.core.meta            import MAIN_VIEWS, TEXT_PROPERTIES
from pangalactic.core.names           import (display_id,
                                              pname_to_header_label,
                                              to_media_name)
from pangalactic.core.parametrics     import (de_defz, get_dval_as_str,
                                              get_pval_as_str, parm_defz)
from pangalactic.core.uberorb         import orb
from pangalactic.core.units           import in_si
from pangalactic.core.utils.datetimes import dt2local_tz_str
# from pangalactic.core.test.utils import create_test_users, create_test_project
from pangalactic.node.utils           import get_pixmap


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
    def __init__(self, ds, as_library=False, icons=None, aligns=None,
                 parent=None, **kwargs):
        """
        Args:
            ds (list):  list of dict instances

        Keyword Args:
            as_library (bool): (default: False) if True, provide icons, etc.
            icons (list of icons):  list of icons by row
            aligns (list of str):  list of alignments ("left", "right", or
                "center") for each column
            parent (QWidget):  parent widget
        """
        super().__init__(parent=parent, **kwargs)
        # TODO: some validity checking on the data ...
        self.icons = icons or []
        _aligns = dict(left=Qt.AlignLeft, right=Qt.AlignRight,
                       center=Qt.AlignHCenter)
        aligns = aligns or []
        self.aligns = [_aligns.get(a, Qt.AlignLeft) for a in aligns]
        self.as_library = as_library
        self.ds = ds or [{0:'no data'}]
        icon_dir = state.get('icon_dir', os.path.join(orb.home, 'icons'))
        self.default_icon = QIcon(QPixmap(os.path.join(icon_dir,
                                  'box'+state.get('icon_type', '.png'))))

    def columns(self):
        return list(self.ds[0].keys())

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.columns()[section]
        return QAbstractTableModel.headerData(self, section, orientation, role)

    def rowCount(self, parent=QModelIndex()):
        return len(self.ds)

    def columnCount(self, parent):
        try:
            return len(self.ds[0])
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
        if row + count - 1 <= len(self.ds):
            self.beginRemoveRows(QModelIndex(), row, row + count - 1)
            del self.ds[row : row + count - 1]
            self.endRemoveRows()
            return True
        else:
            return False

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return QVariant()
        elif (self.as_library and role == Qt.DecorationRole
              and index.column() == 0):
            try:
                return self.icons[index.row()]
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


def obj_view_to_dict(obj, view):
    d = {}
    schema = orb.schemas.get(obj.__class__.__name__)
    if not schema:
        # this will only be the case for a NullObject, which is only used for
        # ObjectSelectionDialog as a "None" choice, so the only fields needed
        # are id, name, description
        return {'id': 'None',
                'name': '',
                'description': ''}
    for a in view:
        if a in schema['field_names']:
            if a == 'id':
                d[a] = obj.id
                # a possible option (for Product instances): id + version
                # d[a] = display_id(obj)
            elif a in TEXT_PROPERTIES:
                d[a] = (getattr(obj, a) or ' ').replace('\n', ' ')
            elif schema['fields'][a]['range'] == 'datetime':
                d[a] = dt2local_tz_str(getattr(obj, a))
            elif schema['fields'][a]['field_type'] == 'object':
                rel_obj = getattr(obj, a)
                if rel_obj.__class__.__name__ == 'ProductType':
                    d[a] = rel_obj.abbreviation or ''
                elif rel_obj.__class__.__name__ in ['HardwareProduct',
                                                    'Organization',
                                                    'Person', 'Project']:
                    d[a] = rel_obj.id or rel_obj.name or '[unnamed]'
                else:
                    d[a] = getattr(rel_obj, 'name', None) or '[unnamed]'
            else:
                d[a] = str(getattr(obj, a))
        elif a in parm_defz:
            pd = parm_defz.get(a)
            units = prefs['units'].get(pd['dimensions'], '') or in_si.get(
                                                    pd['dimensions'], '')
            d[a] = get_pval_as_str(obj.oid, a, units=units)
        elif a in de_defz:
            d[a] = get_dval_as_str(obj.oid, a)
    return d


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
            # orb.log.debug("  ... as library ...")
            icons = [QIcon(get_pixmap(obj)) for obj in objs]
        # orb.log.debug("  ... with {} objects.".format(len(objs)))
        self.view = view or ['']
        self.cname = ''
        if self.objs:
            self.cname = objs[0].__class__.__name__
            self.schema = orb.schemas.get(self.cname) or {}
            if self.schema and self.view:
                # sanity-check view
                self.view = [a for a in self.view if
                             (a in self.schema['field_names']
                              or a in parm_defz
                              or a in de_defz)]
            if not self.view:
                self.view = MAIN_VIEWS.get(self.cname,
                                           ['id', 'name', 'description'])
            if with_none:
                null_obj = NullObject()
                for name in self.view:
                    val = ''
                    if name == 'id':
                        val = 'None'
                    setattr(null_obj, name, val)
                self.objs.insert(0, null_obj)
            ds = [obj_view_to_dict(o, self.view) for o in self.objs]
        else:
            ds = [{0:'no data'}]
            self.view = ['id']
            if with_none:
                null_obj = NullObject()
                for name in self.view:
                    val = ''
                    if name == 'id':
                        val = 'None'
                    setattr(null_obj, name, val)
                self.objs = [null_obj]
                d = dict()
                d['id'] = 'None'
                ds = [d]
        super().__init__(ds, as_library=as_library, icons=icons,
                         parent=parent, **kwargs)

    @property
    def col_labels(self):
        if self.objs:
            return [pname_to_header_label(x) for x in self.view]
        else:
            return ['No Data']

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.col_labels[section]
        return QAbstractTableModel.headerData(self, section, orientation, role)

    def setData(self, index, obj, role=Qt.UserRole):
        """
        Reimplementation using an object as the 'value' (based on underlying
        MappingTableModel setData, which takes a dict as the 'value').
        """
        try:
            # apply MappingTableModel.setData, which takes a dict as value
            super().setData(index, obj_view_to_dict(obj, self.view))
            # this 'dataChanged' should not be necessary, since 'dataChanged is
            # emitted by the 'setData' we just called
            super().dataChanged.emit(index, index)
            return True
        except:
            return False

    def add_object(self, obj):
        n = self.rowCount()
        self.beginResetModel()
        self.insertRows(n, 1)
        idx = self.createIndex(n, 0)
        self.setData(idx, obj)
        self.endResetModel()
        return True

    def add_objects(self, objs):
        n = self.rowCount()
        self.beginResetModel()
        m = len(objs)
        self.insertRows(n, m)
        for i, obj in enumerate(objs):
            idx = self.createIndex(n + i, 0)
            self.setData(idx, obj)
        self.endResetModel()
        return True

    def mod_object(self, obj):
        """
        Replace an object (identified by oid) with a more recently modified
        instance of itself.
        """
        orb.log.debug("* ObjectTableModel.mod_object() ...")
        try:
            oids = [o.oid for o in self.objs]
            row = oids.index(obj.oid)  # raises ValueError if problem
            orb.log.debug(f"    object found at row {row}")
            idx = self.index(row, 0, parent=QModelIndex())
            self.beginResetModel()
            self.setData(idx, obj)
            self.endResetModel()
            return idx
        except:
            # possibly because my C++ object has been deleted ...
            txt = f'object "{obj.id}" (oid {obj.oid}) not found in table.'
            orb.log.debug(f"    {txt}")
        return QModelIndex()

    def del_object(self, obj):
        try:
            oids = [o.oid for o in self.objs]
            row = oids.index(obj.oid)  # raises ValueError if problem
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
                self.column_labels = [pname_to_header_label(o.name)
                                      for o in self.objs]
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


# if __name__ == "__main__":
    # import sys
    # if len(sys.argv) < 2:
        # print "*** you must provide a home directory path ***"
        # sys.exit()
    # main(sys.argv[1])
