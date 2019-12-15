"""
A set of custom TableModels for use with QTableView.
"""
# stdlib
from builtins import str
from builtins import object
import os, re
# import sys  # only needed for testing stuff
from collections import OrderedDict

# SqlAlchemy
from sqlalchemy import ForeignKey

# louie
# from louie import dispatcher

# pandas
# import pandas

# PyQt
from PyQt5.QtCore import (Qt, QAbstractTableModel, QMimeData, QModelIndex,
                          QSortFilterProxyModel, QVariant)
from PyQt5.QtGui import QIcon, QPixmap
# only needed for testing stuff (commented below):
# from PyQt5.QtWidgets import QApplication, QWidget, QTableView, QVBoxLayout

# pangalactic
from pangalactic.core             import state
from pangalactic.core.meta        import MAIN_VIEWS, TEXT_PROPERTIES
from pangalactic.core.parametrics import get_pval_as_str
from pangalactic.core.uberorb     import orb
from pangalactic.core.utils.datetimes import dt2local_tz_str
from pangalactic.core.utils.meta  import (display_id, pname_to_header_label,
                                          to_media_name)
# from pangalactic.core.test.utils import create_test_users, create_test_project
from pangalactic.node.utils       import get_pixmap


test_od = [OrderedDict([('spam','00'), ('eggs','01'), ('more spam','02')]),
           OrderedDict([('spam','10'), ('eggs','11'), ('more spam','12')]),
           OrderedDict([('spam','20'), ('eggs','21'), ('more spam','22')])]

# test_df = pandas.DataFrame(test_od)


class ListTableModel(QAbstractTableModel):
    """
    A table model based on a list of lists.
    """
    def __init__(self, datain, parent=None, **kwargs):
        super(ListTableModel, self).__init__(parent=parent, **kwargs)
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


class ODTableModel(QAbstractTableModel):
    """
    A table model based on a list of OrderedDict instances.
    """
    def __init__(self, ods, as_library=False, icons=None, parent=None,
                 **kwargs):
        """
        Args:
            ods (list):  list of OrderedDict instances

        Keyword Args:
            as_library (bool): (default: False) if True, provide icons, etc.
            parent (QWidget):  parent widget
        """
        super(ODTableModel, self).__init__(parent=parent, **kwargs)
        # TODO: some validity checking on the data ...
        self.icons = icons or []
        self.as_library = as_library
        self.ods = ods or [{0:'no data'}]
        icon_dir = state.get('icon_dir', os.path.join(orb.home, 'icons'))
        self.default_icon = QIcon(QPixmap(os.path.join(icon_dir,
                                  'box'+state.get('icon_type', '.png'))))

    def columns(self):
        return list(self.ods[0].keys())

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.columns()[section]
        return QAbstractTableModel.headerData(self, section, orientation, role)

    def rowCount(self, parent=QModelIndex()):
        return len(self.ods)

    def columnCount(self, parent):
        try:
            return len(self.ods[0])
        except:
            return 1

    def setData(self, index, value, role=Qt.UserRole):
        """
        Reimplementation in which 'value' is an OrderedDict.
        """
        if index.isValid():
            if index.row() < len(self.ods):
                self.ods.insert(index.row(), value)
            else:
                self.ods.append(value)
            self.dirty = True
            # NOTE the 3rd arg is an empty list -- reqd for pyqt5
            # (or the actual role(s) that changed, e.g. [Qt.EditRole])
            self.dataChanged.emit(index, index, [])
            return True
        return False

    def removeRows(self, row, count, parent=QModelIndex()):
        if row < len(self.ods):
            # self.beginRemoveRows()
            self.beginResetModel()
            del self.ods[row]
            # self.endRemoveRows()
            self.endResetModel()
            self.dirty = True
            # NOTE the 3rd arg is an empty list -- reqd for pyqt5
            # (or the actual role(s) that changed, e.g. [Qt.EditRole])
            idx = self.createIndex(row, 0)
            self.dataChanged.emit(idx, idx, [])
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
        elif role != Qt.DisplayRole:
            return QVariant()
        return self.ods[index.row()].get(
                       self.columns()[index.column()], '')


class NullObject(object):
    oid = None


class ObjectTableModel(ODTableModel):
    """
    A ODTableModel subclass based on a list of objects.
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
        self.column_labels = ['No Data']
        self.view = view or []
        self.cname = ''
        if self.objs:
            self.cname = objs[0].__class__.__name__
            self.schema = orb.schemas.get(self.cname, {})
            if self.schema and self.view:
                # sanity-check view
                self.view = [a for a in self.view if a in self.schema['field_names']]
            # TODO:  handle foreign key fields somehow ...
            # for a in view:
                # fk_cname = schema['fields'][a].get('related_cname')
                # if fk_cname in orb.classes:
                    # pass
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
            # NOTE:  this works but may need performance optimization when
            # the table holds a large number of objects
            ods = [self.get_odict_for_obj(o, self.view) for o in self.objs]
            if self.view:
                self.column_labels = [pname_to_header_label(x)
                                      for x in self.view]
            else:
                self.column_labels = list(ods[0].keys())
        else:
            ods = [{0:'no data'}]
            self.view = ['id']
            if with_none:
                null_obj = NullObject()
                for name in self.view:
                    val = ''
                    if name == 'id':
                        val = 'None'
                    setattr(null_obj, name, val)
                self.objs = [null_obj]
                odict = OrderedDict()
                odict['id'] = 'None'
                ods = [odict]
        super(ObjectTableModel, self).__init__(ods, as_library=as_library,
                                               icons=icons, parent=parent,
                                               **kwargs)

    def get_odict_for_obj(self, obj, view):
        """
        Return the OrderedDict representation of an object.
        """
        odict = OrderedDict()
        for name in view:
            if name not in self.schema['fields']:
                val = '-'
            elif name == 'id':
                val = display_id(obj)
            elif name in TEXT_PROPERTIES:
                val = (getattr(obj, name) or ' ').replace('\n', ' ')
            elif self.schema['fields'][name]['range'] == 'datetime':
                val = dt2local_tz_str(getattr(obj, name))
            elif self.schema['fields'][name]['field_type'] == ForeignKey:
                val = getattr(getattr(obj, name), 'id', '[no id]')
            else:
                val = str(getattr(obj, name))
            odict[name] = val
        return odict

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.column_labels[section]
        return QAbstractTableModel.headerData(self, section, orientation, role)

    def setData(self, index, obj, role=Qt.UserRole):
        """
        Reimplementation using an object as the 'value' (based on underlying
        ODTableModel setData, which takes an OrderedDict).
        """
        try:
            # apply ODTableModel.setData, which takes an OrderedDict as value
            super(ObjectTableModel, self).setData(
                                index, self.get_odict_for_obj(obj, self.view))
            # this 'dataChanged' should not be necessary, since 'dataChanged is
            # emitted by the 'setData' we just called
            # super(ObjectTableModel, self).dataChanged.emit(index, index)
            return True
        except:
            return False

    def add_object(self, obj):
        self.objs.append(obj)
        # NOTE: begin/endResetModel works better than begin/endInsertRows
        new_row = len(self.objs) - 1
        idx = self.createIndex(new_row, 0)
        self.beginResetModel()
        self.setData(idx, obj)
        self.endResetModel()
        self.dirty = True
        return True

    def mod_object(self, obj):
        # orb.log.debug("  ObjectTableModel.mod_object() ...")
        try:
            row = self.objs.index(obj)  # raises ValueError if problem
            # orb.log.debug("    object found at row {}".format(row))
            idx = self.index(row, 0, index=QModelIndex())
            self.beginResetModel()
            self.setData(idx, obj)
            self.endResetModel()
            self.dirty = True
            return True
        except:
            return False

    def removeRow(self, row, index=QModelIndex()):
        if row < len(self.objs):
            self.objs = self.objs[:row] + self.objs[row+1:]
            self.removeRows(row, 1, index)
            self.dirty = True
            return True
        else:
            return False

    def mimeTypes(self):
        return [to_media_name(self.cname)]

    def mimeData(self):
        mime_data = QMimeData()
        mime_data.setData(to_media_name(self.cname), 'mimeData')
        return mime_data

    def supportedDropActions(self):
        return Qt.CopyAction


class MatrixTableModel(ODTableModel):
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
            self.ods = []
            for pid in self.parameters:
                row_dict = OrderedDict()
                pd = orb.select('ParameterDefinition', id=pid)
                row_dict['Parameter'] = pd.name
                for o in self.objs:
                    val = get_pval_as_str(orb, o.oid, pid)
                    row_dict[o.oid] = val
                self.ods.append(row_dict)
            if self.objs:
                self.column_labels = [pname_to_header_label(o.name)
                                      for o in self.objs]
                self.column_labels.insert(0, 'Parameter')
            else:
                self.column_labels = list(self.ods[0].keys())
        else:
            self.ods = [{0:'no data'}]
        super(MatrixTableModel, self).__init__(self.ods, parent=parent,
                                               **kwargs)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.column_labels[section]
        return QAbstractTableModel.headerData(self, section, orientation, role)


# class DFTableModel(QAbstractTableModel):
    # """
    # A table model based on a Pandas `DataFrame`.
    # """
    # def __init__(self, df, parent=None, **kwargs):
        # super(DFTableModel, self).__init__(parent=parent, **kwargs)
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
        super(SpecialSortModel, self).__init__(parent=parent)
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

# NOTE: best not to use this stuff any more

# def main(home):
    # app = QApplication(sys.argv)
    # w = Window(home)
    # w.show()
    # sys.exit(app.exec_())


# class Window(QWidget):
    # def __init__(self, home, *args, **kwargs):
        # QWidget.__init__(self, *args, **kwargs)
        # orb.start(home=home, console=True, debug=True)
        # if not state.get('test_objects_loaded'):
            # deserialize(orb, create_test_users() + create_test_project())
        # objs = orb.search_exact(id='HOG')
        # parameters = ['m', 'P', 'TRL']
        # tablemodel = MatrixTableModel(objs, parameters, parent=self)
        # # tablemodel = ODTableModel(test_od)
        # # tablemodel = ODTableModel(None)
        # tableview = QTableView()
        # tableview.setModel(tablemodel)
        # layout = QVBoxLayout(self)
        # layout.addWidget(tableview)
        # self.setLayout(layout)


# if __name__ == "__main__":
    # if len(sys.argv) < 2:
        # print "*** you must provide a home directory path ***"
        # sys.exit()
    # main(sys.argv[1])
