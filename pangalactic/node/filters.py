# -*- coding: utf-8 -*-
"""
Filtering widgets: dialogs, tables, etc.
"""
from PyQt5.QtCore import (pyqtSignal, Qt, QModelIndex, QPoint, QRegExp,
                          QSortFilterProxyModel, QTimer, QVariant)
from PyQt5.QtGui import QDrag, QIcon
from PyQt5.QtWidgets import (QAbstractItemView, QAction, QApplication,
                             QCheckBox, QDialog, QDialogButtonBox, QGroupBox,
                             QHBoxLayout, QLabel, QLineEdit, QSizePolicy,
                             QTableView, QVBoxLayout, QWidget)

import re
from functools import reduce
from textwrap import wrap

from pangalactic.core             import prefs, state
from pangalactic.core.meta        import (MAIN_VIEWS, PGEF_COL_WIDTHS,
                                          PGEF_COL_NAMES)
from pangalactic.core.names       import (get_external_name_plural,
                                          pname_to_header_label)
from pangalactic.core.parametrics import de_defz, parameterz, parm_defz
from pangalactic.core.uberorb     import orb
from pangalactic.node.buttons     import SizedButton
from pangalactic.node.dialogs     import (HWFieldsDialog,
                                          SelectHWLibraryColsDialog)
from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.tablemodels import ObjectTableModel
from pangalactic.node.utils       import (create_mime_data,
                                          create_template_from_product,
                                          get_pixmap)
from pangalactic.node.widgets     import NameLabel


class ProductFilterDialog(QDialog):

    product_types_selected = pyqtSignal(str, list)  # args: msg, oids

    """
    Dialog with selectable product types and related disciplines for filtering
    the 'Hardware Product' library.
    """
    def __init__(self, parent=None):
        """
        Initialize.
        """
        super().__init__(parent)
        self.setWindowTitle('Filter Products by Type or Discipline')
        self.engineering_discipline_selected = None
        # default is to show all discipline product types -- if
        # user_disciplines are found, this will be overridden below ...
        self.show_all_disciplines = True
        proj_oid = state.get('project')
        project = orb.get(proj_oid)
        # orb.log.debug('[ProductFilterDialog] checking for project/roles ...')
        user_disciplines = set()
        if project:
            # first, get my role assignments on this project
            me = orb.get(state['local_user_oid'])
            ras = orb.search_exact(cname='RoleAssignment', assigned_to=me,
                                   role_assignment_context=project)
            roles = [ra.assigned_role for ra in ras]
            if roles:
                drs = reduce(lambda x,y: x.union(y),
                             [set(orb.search_exact(cname='DisciplineRole',
                                                   related_role=r))
                              for r in roles])
                user_disciplines = set([dr.related_to_discipline
                                        for dr in drs])
            # else:
                # orb.log.debug('[ProductFilterDialog] - no assigned roles '
                              # 'found on project "{}".'.format(project.id))
        # else:
            # orb.log.debug('[ProductFilterDialog] - either no project found '
                          # 'or no assigned roles found.')
        # if user_disciplines:
            # orb.log.debug('[ProductFilterDialog] - user disciplines found:')
            # for d in user_disciplines:
                # orb.log.debug('             {}'.format(d.id))
        # else:
            # orb.log.debug('[ProductFilterDialog] - no disciplines found '
                          # 'related to assigned roles.')
        hbox = QHBoxLayout()
        product_types = orb.get_by_type('ProductType')
        label = get_external_name_plural('ProductType')
        self.product_type_panel = FilterPanel(product_types, label=label,
                                              parent=self)
        self.product_type_view = self.product_type_panel.proxy_view
        self.product_type_view.clicked.connect(self.product_type_selected)
        hbox.addWidget(self.product_type_panel)
        discipline_panel = QGroupBox('Disciplines')
        vbox = QVBoxLayout()
        discipline_panel.setLayout(vbox)
        self.cb_all = QCheckBox('SELECT ALL / CLEAR SELECTIONS')
        self.cb_all.clicked.connect(self.on_check_all)
        vbox.addWidget(self.cb_all)
        all_disciplines = orb.get_by_type('Discipline')
        disciplines_by_name = {d.name : d for d in all_disciplines}
        discipline_names = [d.name for d in all_disciplines]
        discipline_names.sort()
        self.checkboxes = {}
        for dname in discipline_names:
            checkbox = QCheckBox(dname)
            checkbox.clicked.connect(self.on_check_cb)
            vbox.addWidget(checkbox)
            self.checkboxes[disciplines_by_name[dname].oid] = checkbox
        vbox.addStretch(1)
        if user_disciplines:
            self.show_all_disciplines = False
            for d in all_disciplines:
                if d in user_disciplines:
                    self.checkboxes[d.oid].setChecked(True)
        else:
            # if no roles/disciplines assigned, select all
            self.cb_all.click()
        hbox.addWidget(discipline_panel)
        main_layout = QVBoxLayout()
        main_layout.addLayout(hbox)
        # Apply and Close buttons
        bbox = QDialogButtonBox(QDialogButtonBox.Close, Qt.Horizontal, self)
        self.apply_btn = bbox.addButton(QDialogButtonBox.Apply)
        self.apply_btn.clicked.connect(self.select_product_types)
        bbox.rejected.connect(self.reject)
        main_layout.addWidget(bbox)
        self.setLayout(main_layout)
        self.resize(800, 500)
        self.on_check_cb()

    def on_check_all(self):
        if self.cb_all.isChecked():
            self.show_all_disciplines = True
            for cb in self.checkboxes.values():
                cb.setChecked(True)
        else:
            self.show_all_disciplines = False
            for cb in self.checkboxes.values():
                cb.setChecked(False)
        self.on_check_cb()

    def on_check_cb(self):
        d_oids = []
        discipline = None
        for d_oid, cb in self.checkboxes.items():
            if cb.isChecked():
                d_oids.append(d_oid)
        product_types = set()
        if self.show_all_disciplines:
            self.pt_list = orb.get_by_type('ProductType')
        else:
            for d_oid in d_oids:
                discipline = orb.get(d_oid)
                if discipline:
                    # exclude dpt's whose relevant_product_type got deleted
                    # (can cause crash if included)
                    pts = [dpt.relevant_product_type
                           for dpt in orb.search_exact(
                                               cname='DisciplineProductType',
                                               used_in_discipline=discipline)
                           if dpt.relevant_product_type]
                    if pts:
                        for product_type in pts:
                            product_types.add(product_type)
            self.pt_list = list(product_types)
        self.product_type_panel.set_source_model(
                self.product_type_panel.create_model(objs=self.pt_list))
        self.engineering_discipline_selected = discipline

    def product_type_selected(self, clicked_index):
        # clicked_row = clicked_index.row()
        # orb.log.debug('* clicked row is "{}"'.format(clicked_row))
        mapped_row = self.product_type_panel.proxy_model.mapToSource(
                                                        clicked_index).row()
        # orb.log.debug(
            # '  product type selected [mapped row] is: {}'.format(mapped_row))
        pt = self.product_type_panel.objs[mapped_row]
        # pt_name = getattr(pt, 'name', '[not set]')
        # orb.log.debug('  ... which is "{}"'.format(pt_name))
        if pt:
            msg = pt.name
            self.product_types_selected.emit(msg, [pt.oid])

    def select_product_types(self):
        """
        Respond to 'Apply' button, by selecting all product types shown in the
        `product_type_panel`, if any, unless "SELECT ALL / CLEAR SELECTIONS" is
        checked, in which case send "All Product Types" message.
        """
        pts = []
        for i in range(self.product_type_panel.proxy_model.rowCount()):
            idx = self.product_type_panel.proxy_model.index(i, 0,
                                                            QModelIndex())
            pts.append(self.product_type_panel.objs[
                       self.product_type_panel.proxy_model.mapToSource(
                                                                idx).row()])
        pts = [pt for pt in pts if pt.id != 'TBD']
        # orb.log.debug(' - selected product types: {}'.format(
                                   # '|'.join([pt.id for pt in pts])))
        if self.engineering_discipline_selected:
            name = self.engineering_discipline_selected.name
            msg = name + ' Products'
            # msg = 'Product Types:<ul>'
            # for pt in pts:
                # msg += '<li>{}</li>'.format(pt.name)
            # msg += '</ul>'
        elif self.cb_all.isChecked() or not pts:
            # all or none -> ALL
            msg = 'All Product Types'
            # 'All Product Types' msg overrides pts, so don't need any pts
            pts = []
        else:
            # all or none -> ALL
            msg = 'All Product Types'
            # 'All Product Types' msg overrides pts, so don't need any pts
            pts = []
        oids = [pt.oid for pt in pts]
        self.product_types_selected.emit(msg, oids)


class ObjectSortFilterProxyModel(QSortFilterProxyModel):
    """
    Special table model that includes text filtering and a special sort
    algorithm:

        * numeric sort (for integers and floats)
        * version sort (for version strings: 'x.x.x', etc.)
        * requirement sort:  [project id]-[parent sequence].[sequence]
        * text sort for everything else
    """
    versionpat = r'[0-9][0-9]*(\.[0-9][0-9]*)*'
    numpat = r'[0-9][0-9]*(\.[0-9][0-9]*)'
    reqpat = r'[a-zA-Z][a-zA-Z0-9-]*[a-zA-Z0-9](\-[0-9][0-9]*)(\.[0-9][0-9]*)*'

    def __init__(self, view=None, cname=None, headers_are_ids=False, parent=None):
        super().__init__(parent=parent)
        self.setSortCaseSensitivity(Qt.CaseInsensitive)
        self.view = view or []
        self.cname = cname
        self.headers_are_ids = headers_are_ids
        self.schema = orb.schemas[self.cname]

    @property
    def ncols(self):
        if self.view:
            return len(self.view)
        return 2

    @property
    def col_labels(self):
        return [PGEF_COL_NAMES.get(a, pname_to_header_label(
                                   a, headers_are_ids=self.headers_are_ids))
                for a in self.view]

    @property
    def col_defs(self):
        defs = []
        for a in self.view:
            if a in self.schema['fields']:
                defs.append('\n'.join(wrap(
                                self.schema['fields'][a]['definition'],
                                width=30, break_long_words=False)))
            elif a in parm_defz:
                defs.append('\n'.join(wrap(
                                parm_defz[a]['description'],
                                width=30, break_long_words=False)))
            elif a in de_defz:
                defs.append('\n'.join(wrap(
                                de_defz[a]['description'],
                                width=30, break_long_words=False)))
        return defs

    @property
    def col_dtypes(self):
        dtypes = []
        for a in self.view:
            if a in self.schema['fields']:
                dtypes.append(self.schema['fields'][a]['range'])
            elif a in parm_defz:
                dtypes.append(parm_defz[a]['range_datatype'])
            elif a in de_defz:
                dtypes.append(de_defz[a]['range_datatype'])
        return dtypes

    @property
    def col_to_label(self):
        return dict(zip(self.view, self.col_labels))

    def filterAcceptsRow(self, sourceRow, sourceParent):
        idxs = []
        for i in range(self.ncols):
            idxs.append(self.sourceModel().index(sourceRow, i, sourceParent))
        return any([(self.filterRegExp().indexIn(
                     str(self.sourceModel().data(idx))) >= 0) for idx in idxs])

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
        try:
            dtype = self.col_dtypes[left.column()]
        except:
            dtype = 'str'
        # left.data() and right.data() can have a value of None -- we need them
        # to be strings ...
        ldata = left.data() or ''
        rdata = right.data() or ''
        l_no_commas = ''.join(ldata.split(','))
        r_no_commas = ''.join(rdata.split(','))
        # Requirement ID Sort
        # * tests for strings of [project id]-[level].[sequence](.[sequence])*
        if (self.is_reqt_id(ldata) and
              self.is_reqt_id(rdata)):
            ldash_split = ldata.split('-')
            lnum = ldash_split[-1]
            ld_proj = '-'.join(ldash_split[:-1])
            ld = lnum.split('.')
            if len(ld) == 3:
                lvalue = [ld_proj.lower(), int(ld[0]), int(ld[1]), int(ld[2])]
            elif len(ld) == 2:
                lvalue = [ld_proj.lower(), int(ld[0]), int(ld[1])]
            elif len(ld) == 1:
                lvalue = [ld_proj.lower(), int(ld[0])]
            rdash_split = rdata.split('-')
            rnum = rdash_split[-1]
            rd_proj = '-'.join(rdash_split[:-1])
            rd = rnum.split('.')
            if len(rd) == 3:
                rvalue = [rd_proj.lower(), int(rd[0]), int(rd[1]), int(rd[2])]
            elif len(rd) == 2:
                rvalue = [rd_proj.lower(), int(rd[0]), int(rd[1])]
            else:
                rvalue = [rd_proj.lower(), int(rd[0])]
            if lvalue and rvalue:
                return lvalue < rvalue
            else:
                return QSortFilterProxyModel.lessThan(self, left, right)
        # Version Sort
        # * tests for strings consisting only of integers separated by dots
        # * sort is done by leftmost integer, then sequentially by the next
        #   integer to the right, etc.
        # **** TODO:  needs exception handling!
        elif (dtype == 'str' and
            self.is_version(ldata) and
            self.is_version(rdata)):
            lefties = [int(i) for i in ldata.split('.')]
            righties = [int(i) for i in rdata.split('.')]
            return lefties < righties
        # Numeric Sort
        # * tests for strings of integers separated by a single dot.
        elif (self.is_numeric(l_no_commas) and
              self.is_numeric(r_no_commas)):
            lvalue = float(l_no_commas)
            rvalue = float(r_no_commas)
            if lvalue and rvalue:
                return lvalue < rvalue
            else:
                return QSortFilterProxyModel.lessThan(self, left, right)
        else:
            lvalue = self.sourceModel().data(left)
            rvalue = self.sourceModel().data(right)
            text_pattern = QRegExp("([\\w\\.]*@[\\w\\.]*)")

            if left.column() == 1 and text_pattern.indexIn(lvalue) != -1:
                lvalue = text_pattern.cap(1)

            if right.column() == 1 and text_pattern.indexIn(rvalue) != -1:
                rvalue = text_pattern.cap(1)

            return str(lvalue).lower() < str(rvalue).lower()

    def data(self, index, role):
        model = self.sourceModel()
        model_idx = self.mapToSource(index)
        if (getattr(model, 'objs', None) and
            (model_idx.row() < len(model.objs))):
            if role == Qt.ToolTipRole:
                if hasattr(model.objs[0], 'description'):
                    descr = model.objs[model_idx.row()].description or ''
                    tt = '\n'.join(wrap(descr, width=30, break_long_words=False))
                    return tt
                else:
                    return ''
            else:
                return super().data(index, role)
        else:
            return ''

    def headerData(self, section, orientation, role):
        if (orientation == Qt.Horizontal and
            role == Qt.DisplayRole and
            len(self.col_labels) > section):
                return QVariant(self.col_labels[section])
        elif (role == Qt.ToolTipRole
              and len(self.col_defs) > section):
            return self.col_defs[section]
        return super().headerData(section, orientation, role)


class ProxyView(QTableView):
    """
    Presentation table view for a filtered set of objects.
    """
    def __init__(self, proxy_model, sized_cols=None, as_library=False,
                 headers_are_ids=False, word_wrap=False, parent=None):
        super().__init__(parent=parent)
        self.sized_cols = sized_cols or {}
        # always resize "id" and "name" cols to fit contents -- see
        # resize_sized_cols(), below ...
        fitted_cols = {'id': 0, 'name': 0}
        self.sized_cols.update(fitted_cols)
        self.setAlternatingRowColors(True)
        # disable editing
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # wrapping now enabled if specified [SCW 01/16/2022]
        if not word_wrap:
            self.setWordWrap(False)
        if proxy_model:
            self.setModel(proxy_model)
        self.setSortingEnabled(True)
        header = self.horizontalHeader()
        header.setSectionsMovable(True)
        header.setStyleSheet('font-weight: bold')
        # sort indicators take up too much space!
        header.setSortIndicatorShown(False)
        if as_library:
            # orb.log.debug('  ... as library.')
            self.setWordWrap(False)
            self.setDragEnabled(True)
            self.setDragDropMode(QAbstractItemView.DragDrop)
        else:
            # orb.log.debug('  ... non-library.')
            self.setDragEnabled(False)
        self.setShowGrid(False)
        # NOTE: default is Qt.ElideRight
        # self.setTextElideMode(Qt.ElideNone)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(1)   # row selection
        self.verticalHeader().hide()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.sortByColumn(0, Qt.AscendingOrder)
        # NOTE:  word_wrap is deprecated but this code is kept commented as an
        # example of how to do those "resize..." methods
        # if word_wrap:
            # # QTimer trick ...
            # QTimer.singleShot(0, self.resizeRowsToContents)
        # else:
            # QTimer.singleShot(0, self.resizeColumnsToContents)
        QTimer.singleShot(0, self.resize_sized_cols)

    def resize_sized_cols(self):
        labels = [self.model().headerData(i, Qt.Horizontal, Qt.DisplayRole)
                  for i in range(len(self.model().view))]
        for col in self.model().col_to_label:
            if col in self.sized_cols:
                # get int of col position ... use try/except to be extra safe
                try:
                    pos = labels.index(self.model().col_to_label[col])
                    w = self.sized_cols[col]
                    if w:
                        self.setColumnWidth(pos, w)
                    else:
                        self.resizeColumnToContents(pos)
                except:
                    continue
            elif col in PGEF_COL_WIDTHS:
                try:
                    pos = labels.index(self.model().col_to_label[col])
                    self.setColumnWidth(pos, PGEF_COL_WIDTHS[col])
                except:
                    continue

    def mouseMoveEvent(self, event):
        if self.dragEnabled():
            self.startDrag(event)

    def startDrag(self, event):
        # orb.log.debug('* starting drag operation ...')
        index = self.indexAt(event.pos())
        if not index.isValid:
            return
        i = self.model().mapToSource(index).row()
        obj = self.model().sourceModel().objs[i]
        # orb.log.debug('  ... at object "{}"'.format(obj.id))
        if isinstance(obj, orb.classes['Identifiable']):
            pixmap = get_pixmap(obj)
            icon = QIcon(pixmap)
            mime_data = create_mime_data(obj, icon)
            # orb.log.debug('  - setting mime data to: {}'.format(
                                                        # mime_data.formats()))
            drag = QDrag(self)
            drag.setMimeData(mime_data)
            # TODO: IF we really want to use a table for ParameterDefinition
            # if self.model().cname == "ParameterDefinition":
                # drag.setHotSpot(QPoint(30, 25))
            # else:
            drag.setHotSpot(QPoint(20, 10))
            drag.setPixmap(icon.pixmap(pixmap.size()))
            drag.exec_(Qt.CopyAction)


class FilterPanel(QWidget):
    """
    A widget containing a filterable table of objects.
    """

    obj_modified = pyqtSignal(str)      # arg: oid
    delete_obj = pyqtSignal(str, str)   # args: oid, cname

    def __init__(self, objs, cname=None, view=None, sized_cols=None, label='',
                 title='', headers_are_ids=False, width=None, min_width=None,
                 height=None, as_library=False, external_filters=False,
                 excluded_oids=None, word_wrap=False, parent=None):
        """
        Initialize.

        Args:
            objs (Identifiable):  objects to be displayed

        Keyword Args:
            cname (str): name of a PGEF class (orb.classes) -- NOTE: if cname
                is supplied, 'objs' may be None, and if not None, must be
                instances of cname
            view (iterable):  names of columns to be shown
            sized_cols (iterable):  names of columns to be sized to fit
                contents
            label (str):  string to incorporate in title
            title (str):  string to use for title
            headers_are_ids (str):  use ids of column items as their headers;
                otherwise, use item names or labels (default: False)
            width (int):  width widget will be initially resized to
            min_width (int):  minimum width of widget
            height (int):  height of widget
            as_library (bool):  (default: False) flag whether to act as library
                -- i.e. its objects can be drag/dropped onto other widgets
            external_filters (bool):  (default: False) flag whether external
                widgets will be called to select additional filter states --
                so far this is only used for the Product library
            excluded_oids (list of str) oids of objs to be excluded from a
                "library"
            word_wrap (bool):  set word wrapping for table cells
            parent (QWidget): parent widget
        """
        super().__init__(parent=parent)
        # orb.log.debug(f'* FilterPanel(view={view}, cname="{cname}")')
        self.as_library = as_library
        self.sized_cols = sized_cols
        self.word_wrap = word_wrap
        self.headers_are_ids = headers_are_ids
        self.excluded_oids = excluded_oids or []
        self.edit_req_calls = 0
        self.edit_req_fields_calls = 0
        if as_library and cname:
            self.cname = cname
            if cname in orb.classes:
                # orb.log.debug(f'* FilterPanel is {cname} library ...')
                objs = orb.get_by_type(cname) or [orb.get('pgefobjects:TBD')]
                self.objs = [o for o in objs
                             if o.oid not in self.excluded_oids]
            else:
                # not a pangalactic domain object, can't display as a library
                # orb.log.debug('  - Cannot display objs of class "{}".'.format(
                                                                        # cname))
                self.objs = [orb.get('pgefobjects:TBD')]
        else:
            if objs and isinstance(objs[0], orb.classes['Identifiable']):
                self.objs = objs
                self.cname = self.objs[0].__class__.__name__
            else:
                # empty table
                self.objs = [orb.get('pgefobjects:TBD')]
                self.cname = 'Product'
        self.schema = orb.schemas[self.cname]
        # make sure items in a supplied view are valid ...
        # orb.log.debug('  - setting view ...')
        if view:
            # orb.log.debug('    using specified view')
            self.view = [a for a in view
                         if ((a in self.schema['field_names']) or
                             (a in parm_defz) or
                             (a in de_defz))]
            if self.cname == 'HardwareProduct':
                prefs['hw_library_view'] = self.view
        else:
            if self.cname == 'HardwareProduct':
                if prefs.get('hw_library_view'):
                    # orb.log.debug('    using prefs["hw_library_view"]')
                    self.view = prefs['hw_library_view'][:]
                else:
                    # default HW Product Lib view (don't need to include
                    # description because it is in the tooltip)
                    self.view = ['id', 'name', 'product_type']
                    prefs['hw_library_view'] = self.view
            else:
                # orb.log.debug('    using default class view')
                self.view = MAIN_VIEWS.get(self.cname,
                                           ['id', 'name', 'description'])
        if external_filters:
            self.ext_filters = SizedButton("Filters")
            self.clear_filters_btn = SizedButton("Clear Product Filters",
                                                 color="green")
            self.cur_filter_label = QLabel("All Product Types")
            self.cur_filter_label.setStyleSheet(
                                           'font-weight: bold; color: green;')
            self.only_mine_checkbox = QCheckBox()
            self.only_mine_checkbox.clicked.connect(self.on_only_mine)
            # in case state['only_mine'] has never been set ...
            state['only_mine'] = state.get('only_mine', False)
            self.only_mine_checkbox.setChecked(state['only_mine'])
            self.only_mine_label = QLabel("Only My Products")
            self.only_mine_label.setStyleSheet(
                                           'font-weight: bold; color: green;')
            self.set_view_button = SizedButton('Customize Columns')
            self.set_view_button.clicked.connect(self.set_custom_hw_lib_view)

        self.filter_case_checkbox = QCheckBox("case sensitive")
        filter_pattern_label = QLabel("Text Filter:")
        filter_pattern_label.setStyleSheet('font-weight: bold; color: purple;')
        self.filter_pattern_line_edit = QLineEdit()
        self.filter_pattern_line_edit.setText("")
        filter_pattern_label.setBuddy(self.filter_pattern_line_edit)
        self.clear_btn = SizedButton("Clear", color="green")
        self.clear_btn.clicked.connect(self.clear_text)

        self.proxy_layout = QVBoxLayout()
        if external_filters:
            only_mine_hbox = QHBoxLayout()
            only_mine_hbox.addWidget(self.only_mine_checkbox)
            only_mine_hbox.addWidget(self.only_mine_label)
            only_mine_hbox.addStretch(1)
            only_mine_hbox.addWidget(self.set_view_button)
            self.proxy_layout.addLayout(only_mine_hbox)
            filters_hbox = QHBoxLayout()
            filters_hbox.addWidget(self.ext_filters)
            filters_hbox.addWidget(self.clear_filters_btn)
            filters_hbox.addWidget(self.cur_filter_label)
            self.proxy_layout.addLayout(filters_hbox)
        text_filter_hbox = QHBoxLayout()
        text_filter_hbox.addWidget(filter_pattern_label)
        text_filter_hbox.addWidget(self.filter_pattern_line_edit)
        text_filter_hbox.addWidget(self.clear_btn)
        text_filter_hbox.addWidget(self.filter_case_checkbox)
        self.proxy_layout.addLayout(text_filter_hbox)
        self.build_proxy_view()
        proxy_group_box = QGroupBox()
        proxy_group_box.setLayout(self.proxy_layout)
        if not title and as_library:
            title = label + ' Library'
        title_widget = NameLabel(title)
        title_widget.setStyleSheet(
            'font-weight: bold; font-size: 18px; color: purple')
        main_layout = QVBoxLayout()
        main_layout.addWidget(title_widget)
        main_layout.addWidget(proxy_group_box)
        self.setLayout(main_layout)
        self.setWindowTitle("Custom Sort/Filter Model")
        width = width or 500
        height = height or 500
        self.resize(width, height)
        if min_width:
            self.setMinimumWidth(min_width)
        self.create_actions()
        self.setup_context_menu()
        self.dirty = False

    def build_proxy_view(self, objs=None):
        if getattr(self, 'proxy_view', None):
            self.proxy_layout.removeWidget(self.proxy_view)
            self.proxy_view.setAttribute(Qt.WA_DeleteOnClose)
            self.proxy_view.parent = None
            self.proxy_view.close()
            self.proxy_view = None
        if getattr(self, 'proxy_model', None):
            self.proxy_model = None
        self.proxy_model = ObjectSortFilterProxyModel(
                                        view=self.view,
                                        cname=self.cname,
                                        headers_are_ids=self.headers_are_ids,
                                        parent=self)
        self.proxy_model.setDynamicSortFilter(True)
        self.proxy_view = ProxyView(self.proxy_model,
                                    sized_cols=self.sized_cols,
                                    as_library=self.as_library,
                                    word_wrap=self.word_wrap,
                                    headers_are_ids=self.headers_are_ids,
                                    parent=self)
        self.proxy_view.horizontalHeader().sectionMoved.connect(
                                                        self.on_column_moved)
        # IMPORTANT:  after a sort, rows retain the heights they had before
        # the sort (i.e. wrong) unless this is done:
        # [2020-10-22 SCW] NO, not necessary because not word-wrapping -> rows
        # are all the same height!
        # [2021-01-16 SCW] now necessary again because word-wrapping ...
        self.proxy_model.layoutChanged.connect(
                                    self.proxy_view.resizeRowsToContents)
        self.proxy_model.layoutChanged.connect(
                                        self.proxy_view.resize_sized_cols)
        self.proxy_model.beginResetModel()
        if not objs:
            if self.as_library and self.cname:
                objs = orb.get_by_type(self.cname)
                self.objs = [o for o in objs
                             if o.oid not in self.excluded_oids]
        self.objs = self.objs or [orb.get('pgefobjects:TBD')]
        model = ObjectTableModel(self.objs, view=self.view,
                                 as_library=self.as_library)
        self.proxy_model.setSourceModel(model)
        self.proxy_model.endResetModel()
        for i, colname in enumerate(self.view):
            self.proxy_view.setColumnWidth(i,
                                           PGEF_COL_WIDTHS.get(colname, 100))
        self.proxy_view.resizeRowsToContents()
        if self.cname == 'Requirement':
            # for Reqt Manager, show grid
            self.proxy_view.setShowGrid(True)
        self.filter_pattern_line_edit.textChanged.connect(
                                                        self.textFilterChanged)
        self.filter_case_checkbox.toggled.connect(self.textFilterChanged)
        self.textFilterChanged()
        self.proxy_layout.addWidget(self.proxy_view, stretch=1)

    def set_source_model(self, model):
        """
        Set the source model.

        Args:
            model (ObjectTableModel):  model to be set
        """
        # orb.log.debug('  - FilterPanel.set_source_model()')
        # very verbose:
        # orb.log.debug('    with objects: {}'.format(str(objs)))
        self.proxy_model.setSourceModel(model)
        for i, colname in enumerate(self.view):
            self.proxy_view.setColumnWidth(i,
                                           PGEF_COL_WIDTHS.get(colname, 100))
        self.proxy_view.resizeRowsToContents()
        if self.cname == 'Requirement':
            # for Reqt Manager, show grid
            self.proxy_view.setShowGrid(True)

    def create_model(self, objs=None):
        # orb.log.debug('  - FilterPanel.create_model()')
        # very verbose:
        # orb.log.debug('    with objects: {}'.format(str(objs)))
        if not objs:
            objs = self.objs
        if not self.objs:
            objs = [orb.get('pgefobjects:TBD')]
        model = ObjectTableModel(objs, view=self.view,
                                 as_library=self.as_library)
        return model

    def set_custom_hw_lib_view(self):
        """
        Set a specified view for the panel when used for the HW Library.
        """
        oids = [o.oid for o in self.objs]
        parms = reduce(lambda x,y: x.union(y),
                       [set(parameterz.get(oid, [])) for oid in oids])
        parms = [pid for pid in parms]
        parms.sort(key=lambda x: x.lower())
        dlg = SelectHWLibraryColsDialog(parms, self.view, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            old_view = self.proxy_model.view[:]
            new_view = []
            # add any columns from old_view first
            for col in old_view:
                if col in dlg.checkboxes and dlg.checkboxes[col].isChecked():
                    new_view.append(col)
            # then append any newly selected columns
            for col in dlg.checkboxes:
                if col not in new_view and dlg.checkboxes[col].isChecked():
                    new_view.append(col)
            prefs['hw_library_view'] = new_view[:]
            self.set_view(new_view[:])
            # orb.log.debug(f'* new HW Library view: {new_view}')
            self.refresh()

    def set_view(self, view):
        """
        Set a new view.

        Args:
            view (iterable):  view to be set.
        """
        self.view = view
        self.proxy_model.view = view

    def refresh(self):
        # orb.log.debug('  - FilterPanel.refresh()')
        # self.build_proxy_view(objs=self.objs)
        self.set_source_model(self.create_model())

    def on_column_moved(self, logical_index, old_index, new_index):
        # orb.log.debug('* FilterPanel.on_column_moved():')
        # orb.log.debug(f'  old index: {old_index}')
        # orb.log.debug(f'  new index: {new_index}')
        if self.cname == 'HardwareProduct':
            # orb.log.debug('  self.cname == "HardwareProduct"')
            new_view = prefs['hw_library_view']
            # orb.log.debug(f'* HW Library view: {new_view}')
        else:
            new_view = self.view
        if 0 <= old_index < len(self.view):
            item = new_view.pop(old_index)
            new_view.insert(new_index, item)
            # orb.log.debug(f'  modified view is: {new_view}')
            if not prefs.get('views'):
                prefs['views'] = {}
            prefs['views'][self.cname] = new_view[:]
            if self.as_library and self.cname == 'HardwareProduct':
                # orb.log.debug(f'* new HW Library view: {new_view}')
                prefs['hw_library_view'] = new_view[:]
        else:
            # orb.log.debug('  - could not move: old col out of range.')
            pass

    def clear_text(self):
        self.filter_pattern_line_edit.setText("")

    def textFilterChanged(self):
        if self.filter_case_checkbox.isChecked():
            cs = Qt.CaseSensitive
        else:
            cs = Qt.CaseInsensitive
        regExp = QRegExp(self.filter_pattern_line_edit.text(), cs, syntax=2)
        self.proxy_model.setFilterRegExp(regExp)
        for i, colname in enumerate(self.view):
            self.proxy_view.setColumnWidth(i,
                                           PGEF_COL_WIDTHS.get(colname, 100))
        self.proxy_view.resizeRowsToContents()

    def on_only_mine(self, evt=None):
        # checkbox was clicked, so toggle state ...
        if state.get('only_mine'):
            state['only_mine'] = False
        else:
            state['only_mine'] = True

    def create_actions(self):
        self.pgxnobj_action = QAction('View or edit this object', self)
        self.pgxnobj_action.triggered.connect(self.display_object)
        # the hw_fields_action is only used by the DataImportWizard when
        # importing HW Product data (because it assumes edit perms exist), so
        # it is only added to the context menu in the wizard module
        txt = 'Edit selected fields of this hardware item'
        self.hw_fields_action = QAction(txt, self)
        self.hw_fields_action.triggered.connect(self.edit_hw_fields)
        txt = 'Edit parameters of this requirement'
        self.req_parms_action = QAction(txt, self)
        txt = 'Edit selected fields of this requirement'
        self.req_fields_action = QAction(txt, self)
        txt = 'Edit this requirement in the wizard'
        self.reqwizard_action = QAction(txt, self)
        # TODO:  include 'Model', 'Document', etc. when they have libraries
        self.template_action = QAction('Create template from object', self)
        self.template_action.triggered.connect(self.create_template)

    def setup_context_menu(self):
        self.proxy_view.setContextMenuPolicy(Qt.ActionsContextMenu)
        if self.cname == 'Requirement':
            # for Requirements, use ReqWizard to edit ...
            # TODO:  only offer this action if user is authorized to edit
            self.proxy_view.addAction(self.req_parms_action)
            self.proxy_view.addAction(self.req_fields_action)
            self.proxy_view.addAction(self.reqwizard_action)
        elif self.cname == 'HardwareProduct':
            self.proxy_view.addAction(self.pgxnobj_action)
            # NOTE: disabled because templates need more work
            # self.proxy_view.addAction(self.template_action)
        else:
            # for all objs other than Requirements, use PgxnObject
            self.proxy_view.addAction(self.pgxnobj_action)

    def edit_hw_fields(self):
        """
        Edit some fields of the selected product in the table.
        """
        # orb.log.debug('* edit_hw_fields()')
        hw = None
        if len(self.proxy_view.selectedIndexes()) >= 1:
            i = self.proxy_model.mapToSource(
                            self.proxy_view.selectedIndexes()[0]).row()
            # orb.log.debug('  at selected row: {}'.format(i))
            oid = getattr(self.proxy_model.sourceModel().objs[i], 'oid', '')
            if oid:
                hw = orb.get(oid)
        if hw:
            dlg = HWFieldsDialog(hw, parent=self)
            dlg.hw_fields_edited.connect(self.on_hw_fields_edited)
            if dlg.exec_() == QDialog.Accepted:
                # orb.log.info('* hw item fields edited.')
                dlg.close()
            else:
                # orb.log.info('* hw item fields editing cancelled.')
                dlg.close()

    def on_hw_fields_edited(self, oid):
        # orb.log.debug('* on_hw_fields_edited()')
        self.mod_object(oid)

    def display_object(self):
        # orb.log.debug('* display object ...')
        if len(self.proxy_view.selectedIndexes()) >= 1:
            i = self.proxy_model.mapToSource(
                self.proxy_view.selectedIndexes()[0]).row()
            # orb.log.debug('  at selected row: {}'.format(i))
            oid = getattr(self.proxy_model.sourceModel().objs[i], 'oid', '')
            if oid:
                obj = orb.get(oid)
                dlg = PgxnObject(obj, parent=self)
                dlg.obj_modified.connect(self.on_pgxo_mod_object_signal)
                dlg.delete_obj.connect(self.on_delete_obj_signal)
                dlg.show()

    def create_template(self):
        """
        Create a Template instance from the selected library product.
        """
        # TODO:  invoke a "Template Wizard"
        if len(self.proxy_view.selectedIndexes()) >= 1:
            i = self.proxy_model.mapToSource(
                self.proxy_view.selectedIndexes()[0]).row()
            # orb.log.debug('* clicked index: {}]'.format(i))
            oid = getattr(self.proxy_model.sourceModel().objs[i], 'oid', '')
            obj = orb.get(oid)
            template = create_template_from_product(obj)
            dlg = PgxnObject(template, edit_mode=True, modal_mode=True,
                             parent=self)
            dlg.show()

    def get_oids(self):
        """
        Get the oids of all objects in the table.
        """
        source_model = self.proxy_model.sourceModel()
        return [obj.oid for obj in source_model.objs]

    def add_object(self, obj):
        """
        Convenience method for adding a new library object to the model, which
        calls the PyQt methods that signal the views to update.
        """
        # orb.log.debug('* FilterPanel.add_object({})'.format(
                                            # getattr(obj, 'id', 'unknown')))
        source_model = self.proxy_model.sourceModel()
        source_model.add_object(obj)

    def mod_object(self, oid):
        """
        Method for modifying an existing library object, which calls the PyQt
        methods that signal the views to update.
        """
        # orb.log.debug(f'* FilterPanel.mod_object({oid})')
        source_model = self.proxy_model.sourceModel()
        source_model.mod_object(oid)

    def remove_object(self, oid):
        """
        Convenience method for deleting a library object from the model.
        """
        # orb.log.debug('  [FilterPanel] remove_object({})'.format(oid))
        try:
            obj = orb.get(oid)
            if not obj:
                # orb.log.debug('  ... object not found in local db.')
                return False
            if obj in self.objs:
                self.objs.remove(obj)
            # else:
                # orb.log.debug('  ... object not found in FilterPanel.objs.')
            source_model = self.proxy_model.sourceModel()
            source_model.del_object(oid)
        except:
            # orb.log.debug('                ... object not found')
            return False

    def on_new_object_signal(self, obj=None, cname=''):
        # orb.log.debug('* [filters] received "new object" signal')
        if obj and obj.__class__.__name__ == self.cname:
            # orb.log.debug('               ... on obj: {}'.format(obj.id))
            self.add_object(obj)

    def on_pgxo_mod_object_signal(self, oid):
        # orb.log.info('* [filters] received obj_modified signal from pgxo')
        # orb.log.debug(f'            on oid: {oid}')
        source_model = self.proxy_model.sourceModel()
        source_model.mod_object(oid)
        self.obj_modified.emit(oid)

    def on_delete_obj_signal(self, oid, cname):
        # orb.log.debug('  [FilterPanel] received "delete_obj" signal.')
        self.delete_obj.emit(oid, cname)


class FilterDialog(QDialog):
    def __init__(self, objs, view=None, sized_cols=None, label='', title='',
                 width=None, min_width=None, height=None, as_library=False,
                 cname=None, external_filters=False, excluded_oids=None,
                 word_wrap=False, parent=None):
        """
        Initialize.

        Args:
            objs (Identifiable):  objects to be displayed

        Keyword Args:
            view (iterable):  attributes of object to be shown
            sized_cols (iterable):  ids of columns to be sized to fit contents
            label (str):  string to incorporate into title
            title (str):  string to use for title
            width (int):  width dialog widget will be initially resized to
            min_width (int):  minimum width of dialog widget
            as_library (bool):  (default: False) flag whether to act as library
                -- i.e. its objects can be drag/dropped onto other widgets
            cname (str):  class name of the objects to be displayed ("objs" arg
                will be ignored)
            external_filters (bool):  (default: False) flag whether external
                widgets will be called to select additional filter states --
                so far this is only used for the Product library
            excluded_oids (list of str) oids of objs to be excluded from a
                "library"
            word_wrap (bool):  set word wrapping for table cells
            height (int):  height of dialog widget
            parent (QWidget): parent widget
        """
        super().__init__(parent=parent)
        self.setWindowTitle('Filter Products by Type or Discipline')
        panel = FilterPanel(objs, view=view, sized_cols=sized_cols,
                    label=label, title=title, width=width, min_width=min_width,
                    height=height, as_library=as_library, cname=cname,
                    external_filters=external_filters,
                    excluded_oids=excluded_oids, word_wrap=word_wrap,
                    parent=self)
        vbox = QVBoxLayout()
        vbox.addWidget(panel)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel,
                                        Qt.Horizontal, self)
        self.buttons.rejected.connect(self.reject)
        vbox.addWidget(self.buttons)
        self.setLayout(vbox)
        width = width or 600
        height = height or 500
        self.resize(width, height)


if __name__ == "__main__":

    import sys

    app = QApplication(sys.argv)

    # window = FilterPanel('ProductType', label='Product Type', parent=None)
    window = FilterPanel('ProductType', label='Product Type', parent=None)
    window.show()

    sys.exit(app.exec_())

