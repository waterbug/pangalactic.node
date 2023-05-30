#!/usr/bin/env python
from textwrap import wrap

from PyQt5.QtCore import (pyqtSignal, Qt, QAbstractListModel, QMimeData,
                          QModelIndex, QPoint, QSize, QVariant)
from PyQt5.QtGui import QDrag, QIcon
from PyQt5.QtWidgets import (QAbstractItemView, QAction, QApplication,
                             QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
                             QLabel, QListView, QScrollArea, QSizePolicy,
                             QStackedLayout, QVBoxLayout, QWidget)

from louie import dispatcher

# pangalactic
from pangalactic.core            import prefs, state
from pangalactic.core.names      import (display_id, get_external_name_plural,
                                         to_media_name)
from pangalactic.core.uberorb    import orb
from pangalactic.node.buttons    import SizedButton
from pangalactic.node.filters    import FilterPanel, ProductFilterDialog
from pangalactic.node.trees      import ParmDefTreeView
from pangalactic.node.utils      import create_mime_data, get_pixmap
from pangalactic.node.widgets    import ParameterLabel
from pangalactic.node.pgxnobject import PgxnObject


class LibraryListModel(QAbstractListModel):
    """
    Underlying model for a list view of library objects.
    """
    def __init__(self, cname, objs=None, include_subtypes=True,
                 icon_size=None, parent=None):
        """
        Initialize the library list model.

        Args:
            cname (str):  class name of the library objects

        Keyword Args:
            objs (list of Identifiable): optional list of library objects,
                which if provided will override the "cname" arg
            include_subtypes (bool): flag, if True include subtypes
            icon_size (Qsize):  size of the icons to be used for library items
            parent (QWidget):  the library model's parent widget
        """
        self.subtypes = include_subtypes
        self.specified_objects = False
        if objs:
            self.specified_objects = True
            self.cname = objs[0].__class__.__name__
            self.subtypes = False
        else:
            self.cname = cname
        if self.cname == 'DataElementDefinition':
            # only for DataElementDefinition (do not want ParameterDefinitions)
            self.subtypes = False
        super().__init__(parent=parent)
        if objs:
            self.objs = []
            for obj in objs:
                self.add_object(obj)
        else:
            self.refresh()

    def refresh(self):
        # orb.log.debug("* LibraryListModel: %s library refresh ..." % self.cname)
        if not self.specified_objects:
            if self.subtypes:
                objs = orb.get_all_subtypes(self.cname)
            else:
                objs = orb.get_by_type(self.cname)
            # sort by name
            objs.sort(
                key=lambda o: getattr(o, 'name', '') or  getattr(o, 'id', ''))
            self.objs = []
            for obj in objs:
                self.add_object(obj)
            # orb.log.debug("  - objs: {}".format(', '.join(
                # [getattr(obj, 'id', 'none') or 'none' for obj in self.objs])))

    def add_object(self, obj):
        """
        Convenience method for adding a new library object to the model, which
        calls the PyQt methods that signal the views to update.
        """
        new_row = self.rowCount()
        self.insertRow(new_row)
        self.setData(self.index(new_row), obj)

    def rowCount(self, parent=QModelIndex()):
        return len(self.objs)

    def mimeTypes(self):
        return [to_media_name(self.cname)]

    def mimeData(self):
        mime_data = QMimeData()
        mime_data.setData(to_media_name(self.cname), 'mimeData')
        return mime_data

    def supportedDropActions(self):
        return Qt.CopyAction

    def data(self, index, role):
        if (not index.isValid() or
            not (0 <= index.row() < len(self.objs))):
            return QVariant()
        obj = self.objs[index.row()]
        if role == Qt.DisplayRole:
            # how objects are displayed in the library widget
            return QVariant(getattr(obj, 'label', None) or obj.name)
        elif role == Qt.ToolTipRole:
            if isinstance(obj, orb.classes['Product']):
                id_v = display_id(obj)
                pt_name = getattr(obj.product_type, 'name', None)
                if pt_name:
                    tt = id_v + '\n[' + pt_name + ']'
                else:
                    tt = id_v + '\n[unknown type]'
            else:
                tt = '\n'.join(wrap(obj.description or '', width=40,
                                    break_long_words=False))
            return QVariant(tt)
        elif role == Qt.DecorationRole:
            return QIcon(get_pixmap(obj))
        elif role == Qt.UserRole:
            return obj
        return QVariant()

    def setData(self, index, value, role=Qt.UserRole):
        if index.isValid() and 0 <= index.row() < len(self.objs):
            self.objs[index.row()] = value
            self.dirty = True
            # NOTE the 3rd arg is an empty list -- reqd for pyqt5
            # (or the actual role(s) that changed, e.g. [Qt.EditRole])
            self.dataChanged.emit(index, index, [])
            return True
        return False

    def insertRow(self, row, index=QModelIndex()):
        self.beginInsertRows(QModelIndex(), row, row)
        self.objs.insert(row, None)
        self.endInsertRows()
        self.dirty = True
        return True

    def removeRow(self, row, index=QModelIndex()):
        if row < len(self.objs):
            self.beginRemoveRows(QModelIndex(), row, row)
            self.objs = self.objs[:row] + self.objs[row+1:]
            self.endRemoveRows()
            self.dirty = True
            return True
        return False


class LibraryListView(QListView):
    """
    Generic QListView-style View -- initially designed particularly to support
    the Parameter library, for which a table view is now used.
    """
    def __init__(self, cname, objs=None, include_subtypes=True,
                 draggable=True, icon_size=None, parent=None):
        """
        Initialize the library view.

        Args:
            cname (str):  class name of the library objects

        Keyword Args:
            include_subtypes (bool): flag, if True include subtypes
            draggable (bool):   flag indicating whether library objects should
                be able to be dragged and dropped -- set to False if the
                library view's objects are intended to be selected by clicking
            icon_size (Qsize):  size of the icons to be used for library items
            parent (QWidget):  the library view's parent widget
        """
        super().__init__(parent=parent)
        model = LibraryListModel(cname, objs=objs,
                                 include_subtypes=include_subtypes,
                                 parent=self)
        if objs:
            self.cname = objs[0].__class__.__name__
        else:
            self.cname = cname
        self.setModel(model)
        if draggable:
            self.setDragEnabled(True)
            self.setDragDropMode(QAbstractItemView.DragDrop)
        else:
            self.setDragEnabled(False)
        default_icon_size = QSize(16, 16)
        self.icon_size = icon_size or default_icon_size
        self.setIconSize(self.icon_size)
        # NOTE: width of library widget within the main window is set by the
        # right dock container (a QDockWidget)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.create_actions()
        self.setup_context_menu()

    def sizeHint(self):
        return QSize(400, 450)

    def create_actions(self):
        self.pgxnobj_action = QAction('View this object', self)
        self.pgxnobj_action.triggered.connect(self.display_object)

    def setup_context_menu(self):
        self.addAction(self.pgxnobj_action)
        # NOTE:  there may be templates for other object types in the future
        if self.cname == 'HardwareProduct':
            self.addAction(self.template_action)

    def display_object(self):
        # NOTE: maybe not the most elegant way to do this ... look again later
        # mapped_row = self.table_proxy.mapToSource(clicked_index).row()
        if len(self.selectedIndexes()) == 1:
            i = self.selectedIndexes()[0].row()
            # orb.log.debug('* clicked index: {}]'.format(i))
            oid = getattr(self.model().objs[i], 'oid')
            obj = orb.get(oid)
            dlg = PgxnObject(obj, modal_mode=True, parent=self)
            # TODO:  connect pgxo's "mod_object" signal to ...?
            dlg.show()

    def refresh(self, **kw):
        """
        Handle a 'deleted object', 'new object', 'modified object' signals.

        Keyword Args:
            oid (str):  oid of the deleted object
            cname (str):  class name of the deleted object
            remote (bool):  whether the action originated remotely
        """
        self.model().refresh()

    def startDrag(self, event):
        index = self.indexAt(event.pos())
        if not index.isValid:
            return
        obj = self.model().data(index, Qt.UserRole)
        if isinstance(obj, orb.classes['Identifiable']):
            drag = QDrag(self)
            if self.cname == "ParameterDefinition":
                label = ParameterLabel(obj)
                pixmap = label.get_pixmap()
                drag.setHotSpot(QPoint(30, 25))
                drag.setPixmap(pixmap)
                icon = QIcon(pixmap)
            else:
                icon = QIcon(get_pixmap(obj))
                drag.setHotSpot(QPoint(20, 10))
                drag.setPixmap(icon.pixmap(self.icon_size))
            mime_data = create_mime_data(obj, icon)
            drag.setMimeData(mime_data)
            drag.exec_(Qt.CopyAction)

    def mouseMoveEvent(self, event):
        if self.dragEnabled():
            self.startDrag(event)


def select_product_types(lib_view, msg='', only_mine=False,
                         product_types=None):
    """
    Apply a product_type-based filter to the Hardware Product Library.

    Args:
        lib_view (FilterPanel): the HW Product Library's FilterPanel

    Keyword Args:
        msg (str): the message associated with the originating event
        only_mine (bool): whether to restrict the displayed products to those
            created by the user
        product_types (list of ProductType): the product types to be displayed
    """
    label_text = ''
    if msg == 'All Product Types':
        # -> "SELECT ALL / CLEAR SELECTIONS" is checked in Disciplines
        hw = orb.get_by_type('HardwareProduct')
        label_text = msg
    elif len(product_types) == 1:
        hw = orb.search_exact(cname='HardwareProduct',
                              product_type=product_types[0])
        label_text = msg
    elif len(product_types) == 0:
        # no selections -> show all product types
        hw = orb.get_by_type('HardwareProduct')
        label_text = 'All Product Types'
    elif len(product_types) > 1:
        # multiple (but not all) product types selected ...
        hw = set()
        for pt in product_types:
            hw |= set(orb.search_exact(cname='HardwareProduct',
                                       product_type=pt))
        hw = list(hw)
        label_text = msg
    else:
        # no product types are selected -> get all products
        label_text = 'All Product Types'
        hw = orb.get_by_type('HardwareProduct')
    if only_mine:
        local_user = orb.get(state.get('local_user_oid', 'me'))
        if local_user:
            hw = [h for h in hw if h.creator == local_user]
    if hasattr(lib_view, 'cur_filter_label') and label_text:
        lib_view.cur_filter_label.setText(label_text)
    lib_view.set_source_model(lib_view.create_model(hw))


class CompoundLibraryWidget(QWidget):
    """
    Widget containing a collection of library widgets.

    Attributes:
        libraries (dict):  a dictionary that maps the name of the class
            displayed in a library view widget (LibraryListView instance) to
            the widget
        library_indexes (dict):  a dictionary that maps the name of the class
            displayed in a library view (LibraryListView instance) to the index
            of the library view in the QStackedLayout
    """

    obj_modified = pyqtSignal(str)          # arg: oid
    delete_obj = pyqtSignal(str, str)       # args: oid, cname
    toggle_library_size = pyqtSignal(bool)  # args: expand

    def __init__(self, cnames=None, include_subtypes=True, icon_size=None,
                 title=None, min_width=None, parent=None):
        """
        Initialize the library container widget.

        Args:
            cnames (list of str):  class names determining the content of the
                library's default views.  If None, include all Identifiables.

        Keyword Args:
            include_subtypes (bool): flag, if True include subtypes
            icon_size (Qsize):  size of the icons to be used for library items
            title (str):  optional text for widget title; default is 'Libraries'
            min_width (int):  minimum width of the contained library widgets
            parent (QWidget):  the library view's parent widget
        """
        super().__init__(parent)
        # orb.log.debug(f'* CompoundLibraryWidget(cnames={cnames})')
        layout = QVBoxLayout(self)
        hbox = QHBoxLayout()
        # layout.setSizeConstraint(layout.SetMinimumSize)
        title = title or 'Libraries'
        title = QLabel(title)
        title.setStyleSheet('font-weight: bold; font-size: 18px')
        hbox.addWidget(title, alignment=Qt.AlignLeft)
        self.expanded = True
        self.expand_button = SizedButton('Collapse', color='green')
        self.expand_button.clicked.connect(self.toggle_size)
        hbox.addWidget(self.expand_button)
        layout.addLayout(hbox)
        self.library_select = QComboBox()
        self.library_select.setStyleSheet('font-weight: bold; font-size: 14px')
        self.library_select.activated.connect(self.set_library)
        layout.addWidget(self.library_select)
        lib_scroll_area = QScrollArea()
        lib_scroll_area.setWidgetResizable(True)
        lib_panel = QWidget(self)
        lib_scroll_area.setWidget(lib_panel)
        self.stack = QStackedLayout(lib_panel)
        self.stack.setContentsMargins(1, 1, 1, 1)
        layout.addWidget(lib_scroll_area)
        self.libraries = {}
        if cnames:
            for cname in cnames:
                self.create_lib_widget(cname, min_width=min_width)
        if min_width:
            self.setMinimumWidth(min_width)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        dispatcher.connect(self.on_hw_lib_dlg_closed,
                           'hw library dialog closed')

    def create_lib_widget(self, cname, include_subtypes=True, icon_size=None,
                          min_width=None):
        """
        Creates an instance of 'FilterPanel' or 'LibraryListView' for the
        specified class name (cname), sets it as the self.libraries dict entry
        for the cname, adds it to the stacked widgets, and adds the cname's
        display name to the 'library_select' combo box.

        Args:
            cname (str):  class name of the library's objects

        Keyword Args:
            obj (subtype of ManagedObject):  the selected object
            include_subtypes (bool):  flag indicating if library view should
                include subtypes of the specified cname
        """
        self.msg = 'All Product Types'
        self.product_types = None
        select_label = get_external_name_plural(cname)
        # special cases for HardwareProduct, ParameterDefinition, Person
        if cname == 'HardwareProduct':
            select_label = 'Systems & Components (Hardware Products)'
            lib_table = FilterPanel(None, as_library=True,
                                    cname=cname, label=select_label,
                                    external_filters=True,
                                    min_width=min_width,
                                    parent=self)
            lib_table.obj_modified.connect(self.on_obj_modified)
            lib_table.delete_obj.connect(self.on_delete_obj)
            if hasattr(lib_table, 'ext_filters'):
                lib_table.ext_filters.clicked.connect(self.show_ext_filters)
                lib_table.clear_filters_btn.clicked.connect(
                                                    self.clear_product_filters)
                lib_table.only_mine_checkbox.clicked.connect(
                                                self.on_only_mine_toggled)
        elif cname == 'ParameterDefinition':
            select_label = 'Parameters'
            lib_table = ParmDefTreeView(parent=self)
        elif cname == 'DataElementDefinition':
            select_label = 'Data Elements'
            view = ['id', 'range_datatype', 'name']
            # exclude DEs that are only computed for the MEL -- this is kludgy:
            # identify them by oid endings (same as id endings)
            ded_objs = orb.get_by_type('DataElementDefinition')
            excluded_oids = [o.oid for o in ded_objs
                             if (o.oid.endswith('_cbe') or
                                 o.oid.endswith('_mev') or
                                 o.oid.endswith('assembly_level') or
                                 o.oid.endswith('m_unit') or
                                 o.oid.endswith('quoted_unit_price') or
                                 o.oid.endswith('_units') or
                                 o.oid.endswith('_spares') or
                                 o.oid.endswith('_ctgcy'))]
            lib_table = FilterPanel(None, view=view, as_library=True,
                                    cname=cname, label=select_label,
                                    min_width=min_width,
                                    excluded_oids=excluded_oids,
                                    parent=self)
            lib_table.obj_modified.connect(self.on_obj_modified)
        elif cname == 'Person':
            select_label = 'People'
            view = ['id', 'last_name', 'first_name', 'org']
            # exclude "me", "TBD", and "admin"
            excluded_oids = ['me', 'pgefobjects:Person.TBD',
                             'pgefobjects:admin']
            people = [p for p in orb.get_by_type('Person')
                      if p.oid not in excluded_oids]
            # orb.log.debug('- oids non grata: {}'.format(str(excluded_oids)))
            # orb.log.debug('- people: {}'.format([p.oid for p in people]))
            people.sort(key=lambda o: getattr(o, 'last_name', '') or '')
            lib_table = FilterPanel(people, view=view, as_library=True,
                                    min_width=min_width,
                                    label=select_label,
                                    excluded_oids=excluded_oids,
                                    parent=self)
            lib_table.obj_modified.connect(self.on_obj_modified)
        else:
            lib_table = LibraryListView(cname,
                                        include_subtypes=include_subtypes,
                                        icon_size=icon_size, parent=self)
        if cname == 'Template':
            select_label = 'System & Component Templates'
        self.libraries[cname] = lib_table
        self.stack.addWidget(lib_table)
        self.library_select.addItem(select_label, QVariant())

    def on_obj_modified(self, oid):
        self.obj_modified.emit(oid)

    def on_delete_obj(self, oid, cname):
        self.delete_obj.emit(oid, cname)

    def on_remote_obj_mod(self, oid, cname):
        # orb.log.debug(f"* CompLibWidget.on_remote_obj_mod(oid, {cname})")
        if cname in self.libraries:
            self.libraries[cname].mod_object(oid)

    def set_library(self, index):
        """
        Set the selected library widget.
        """
        self.stack.setCurrentIndex(index)

    def toggle_size(self, evt):
        if self.expanded:
            self.expand_button.setText('Expand')
            expand = False
        else:
            self.expand_button.setText('Collapse')
            expand = True
        self.toggle_library_size.emit(expand)

    def refresh(self, cname=None, **kw):
        # orb.log.debug(f"* CompoundLibraryWidget.refresh(cname={cname})")
        cnames = list(self.libraries)
        if cname:
            cnames = [cname]
        for cname in cnames:
            lib_widget = self.libraries.get(cname)
            if hasattr(lib_widget, 'refresh'):
                # orb.log.debug(f"  lib_widget.refresh() for {cname}")
                lib_widget.refresh()
            elif (hasattr(lib_widget, 'model') and
                  hasattr(lib_widget.model(), 'refresh')):
                # orb.log.debug("  lib_widget.model().refresh()")
                # orb.log.debug(f"  for {cname}")
                lib_widget.model().refresh()
            # call on_only_mine_toggled() to ensure filtering is consistent
            # with state after a refresh
            self.on_only_mine_toggled()

    def on_hw_lib_dlg_closed(self):
        self.refresh(cname='HardwareProduct')

    def show_ext_filters(self):
        self.filter_dlg = ProductFilterDialog(self)
        self.filter_dlg.product_types_selected.connect(
                                self.on_product_types_selected_signal)
        self.filter_dlg.show()

    def clear_product_filters(self):
        hw_lib = self.libraries.get('HardwareProduct')
        if hw_lib:
            self.product_types = []
            select_product_types(hw_lib, msg='All Product Types',
                                 only_mine=state.get('only_mine'),
                                 product_types=[])

    def on_product_types_selected(self, msg='', objs=None):
        # orb.log.debug('* on_product_types_selected:')
        # orb.log.debug('  objs: {}'.format(', '.join([o.id for o in objs])))
        # orb.log.debug('  msg: {}'.format(msg))
        hw_lib = self.libraries.get('HardwareProduct')
        if hw_lib:
            self.msg = msg
            self.product_types = objs
            select_product_types(hw_lib, msg=msg,
                                 only_mine=state.get('only_mine'),
                                 product_types=objs)

    def on_product_types_selected_signal(self, msg='', oids=None):
        # orb.log.debug('* on_product_types_selected:')
        # orb.log.debug('  msg: {}'.format(msg))
        hw_lib = self.libraries.get('HardwareProduct')
        if hw_lib:
            self.msg = msg
            self.product_types = orb.get(oids=oids)
            # orb.log.debug(f'  product types: {self.product_types}')
            select_product_types(hw_lib, msg=msg,
                                 only_mine=state.get('only_mine'),
                                 product_types=self.product_types)

    def on_only_mine_toggled(self):
        hw_lib = self.libraries.get('HardwareProduct')
        if hw_lib:
            # keep only_mine_checkbox in sync with state ...
            hw_lib.only_mine_checkbox.setChecked(state.get('only_mine', False))
            select_product_types(hw_lib, msg=self.msg,
                                 only_mine=state.get('only_mine'),
                                 product_types=self.product_types)


class LibraryDialog(QDialog):
    """
    Dialog containing a table or list of library items.
    """

    obj_modified = pyqtSignal(str)  # arg: oid

    def __init__(self, cname, objs=None, include_subtypes=False,
                 icon_size=None, tabular=True, prefilter=None, view=None,
                 word_wrap=False, width=None, height=None, parent=None):
        """
        Initialize the library dialog.

        Args:
            cname (str):  class name of the library objects

        Keyword Args:
            objs (list):  list of objects to include, rather than all
                instances of the specified class
            include_subtypes (bool): flag, if True include subtypes
            icon_size (Qsize):  size of the icons to be used for library items
            tabular (bool):  if True [default]: table, else: list
            prefilter (str):  filter to select the base library objects
            view (list):  list of attributes/parameters to be used for columns
            parent (QWidget):  the library view's parent widget
        """
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.msg = 'All Product Types'
        self.product_types = None
        self.cname = cname
        # TODO:  include_subtypes, prefilter ...
        if not objs:
            objs = orb.get_by_type(cname)
        label = get_external_name_plural(cname)
        if tabular:
            if self.cname == 'HardwareProduct':
                label = 'Systems and Components (Hardware Products)'
                self.setWindowTitle(label)
                lib_view = FilterPanel(objs, view=view, as_library=True,
                                       label=label, external_filters=True,
                                       parent=self)
                lib_view.ext_filters.clicked.connect(self.show_ext_filters)
                lib_view.clear_filters_btn.clicked.connect(
                                                self.clear_product_filters)
                lib_view.only_mine_checkbox.clicked.connect(
                                                self.on_only_mine_toggled)
                lib_view.obj_modified.connect(self.on_obj_modified)
            else:
                if self.cname == 'Template':
                    label = 'System and Component Templates'
                self.setWindowTitle(label)
                lib_view = FilterPanel(objs, view=view, as_library=True,
                                       word_wrap=word_wrap, label=label,
                                       parent=self)
            # only listen for these signals if using FilterPanel, which does
            # not itself listen for them; if using LibraryListView, it already
            # listens for them
        else:
            lib_view = LibraryListView(cname, parent=parent)
        lib_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.lib_view = lib_view
        bbox = QDialogButtonBox(QDialogButtonBox.Close)
        bbox.rejected.connect(self.reject)
        layout = QVBoxLayout()
        layout.addWidget(lib_view)
        layout.addWidget(bbox)
        self.setLayout(layout)
        width = width or 600
        height = height or 500
        self.resize(width, height)
        # call on_only_mine_toggled() to ensure initial filtering is consistent
        # with state
        self.on_only_mine_toggled()

    def on_obj_modified(self, oid):
        self.obj_modified.emit(oid)

    def show_ext_filters(self):
        self.filter_dlg = ProductFilterDialog(self)
        self.filter_dlg.product_types_selected.connect(
                                self.on_product_types_selected_signal)
        self.filter_dlg.show()

    def clear_product_filters(self):
        self.product_types = []
        select_product_types(self.lib_view, msg='All Product Types',
                             only_mine=state.get('only_mine'),
                             product_types=[])

    def on_product_types_selected(self, msg='', objs=None):
        # orb.log.debug('* on_product_types_selected:')
        # orb.log.debug('  objs: {}'.format(', '.join([o.id for o in objs])))
        # orb.log.debug('  msg: {}'.format(msg))
        self.msg = msg
        self.product_types = objs
        select_product_types(self.lib_view, msg=msg,
                             only_mine=state.get('only_mine'),
                             product_types=objs)

    def on_product_types_selected_signal(self, msg='', oids=None):
        # orb.log.debug('* on_product_types_selected:')
        # orb.log.debug('  objs: {}'.format(', '.join([o.id for o in objs])))
        # orb.log.debug('  msg: {}'.format(msg))
        self.msg = msg
        self.product_types = orb.get(oids=oids)
        select_product_types(self.lib_view, msg=msg,
                             only_mine=state.get('only_mine'),
                             product_types=self.product_types)

    def on_only_mine_toggled(self):
        # keep only_mine_checkbox in sync with state ...
        if hasattr(self.lib_view, 'only_mine_checkbox'):
            self.lib_view.only_mine_checkbox.setChecked(state.get('only_mine',
                                                                  False))
            select_product_types(self.lib_view, msg=self.msg,
                                 only_mine=state.get('only_mine'),
                                 product_types=self.product_types)

    def refresh(self, cname=None, **kw):
        # orb.log.debug("* LibraryDialog.refresh(cname={})".format(cname))
        if self.cname == 'HardwareProduct':
            select_product_types(self.lib_view, msg=self.msg,
                                 only_mine=state.get('only_mine'),
                                 product_types=self.product_types)
        else:
            objs = orb.get_by_type(cname or self.cname)
            self.lib_view.set_source_model(
                            self.lib_view.create_model(objs))

    def closeEvent(self, evt):
        if self.lib_view.col_moved_view:
            # ensure that final column moves are saved ...
            prefs['hw_library_view'] = self.lib_view.col_moved_view[:]
        if self.cname == 'HardwareProduct':
            dispatcher.send('hw library dialog closed')


if __name__ == '__main__':
    """Script mode for testing."""
    import sys
    if len(sys.argv) < 2:
        print('You must provide a home directory path (for the orb).')
        sys.exit()
    home = sys.argv[1]
    orb.start(home=home, console=True, debug=True)
    app = QApplication(sys.argv)
    cname = 'ParameterDefinition'
    if len(sys.argv) == 3:
        cname = sys.argv[2]
    # window = LibraryDialog(cname)
    window = CompoundLibraryWidget(cnames=['HardwareProduct',
                                           'ParameterDefinition',
                                           'Template'])
    window.show()
    sys.exit(app.exec_())

