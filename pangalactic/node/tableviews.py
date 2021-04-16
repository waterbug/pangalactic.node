"""
Widgets based on QTableView
"""
import os

# ruamel_yaml
import ruamel_yaml as yaml

# PyQt
from PyQt5.QtWidgets import (QAction, QDialog, QDialogButtonBox, QFileDialog,
                             QSizePolicy, QTableView, QVBoxLayout)
from PyQt5.QtCore import Qt, QTimer

# Louie
from louie import dispatcher

# pangalactic
from pangalactic.core             import prefs, state
from pangalactic.core.meta        import IDENTITY, MAIN_VIEWS, PGEF_COL_WIDTHS
from pangalactic.core.serializers import serialize
from pangalactic.core.uberorb     import orb
from pangalactic.core.utils.datetimes import dtstamp, date2str
from pangalactic.core.utils.meta  import get_external_name_plural
from pangalactic.node.tablemodels import (ObjectTableModel,
                                          CompareTableModel,
                                          SpecialSortModel)
from pangalactic.node.dialogs     import NotificationDialog, SelectColsDialog
from pangalactic.node.pgxnobject  import PgxnObject


class ObjectTableView(QTableView):
    """
    For a list of objects with the same class, a table view with sorting
    capabilities.
    """
    def __init__(self, objs, view=None, parent=None):
        """
        Initialize

        objs (Identifiable):  objects (rows)
        view (list of str):  specified attributes (columns)
        """
        super().__init__(parent=parent)
        orb.log.info('* [ObjectTableView] initializing ...')
        self.objs = objs
        self.view = view
        self.setup_table()
        self.add_context_menu()

    def setup_table(self):
        self.cname = None
        # if a main_table_proxy exists, remove it so gui doesn't get confused
        if self.objs:
            self.cname = self.objs[0].__class__.__name__
            orb.log.info('  - for class: "{}"'.format(self.cname))
            if not self.view:
                # if no view is specified, use the preferred view, if any
                if (prefs.get('db_views') or {}).get(self.cname):
                    self.view = prefs['db_views'][self.cname][:]
        else:
            orb.log.info('  - no objects provided.')
        # if there is neither a specified view nor a preferred view, use the
        # default view
        view = self.view or MAIN_VIEWS.get(self.cname, IDENTITY)
        self.main_table_model = ObjectTableModel(self.objs, view=view,
                                                 parent=self)
        self.view = self.main_table_model.view
        self.main_table_proxy = SpecialSortModel(parent=self)
        self.main_table_proxy.setSourceModel(self.main_table_model)
        self.setStyleSheet('font-size: 12px')
        # disable sorting while loading data
        self.setSortingEnabled(False)
        self.setSelectionBehavior(QTableView.SelectRows)
        self.setModel(self.main_table_proxy)
        column_header = self.horizontalHeader()
        column_header.setStyleSheet('font-weight: bold')
        # TODO:  try setting header colors using Qt functions ...
        column_header.setSectionsMovable(True)
        column_header.sectionMoved.connect(self.on_section_moved)
        # NOTE:  the following line will make table width fit into window
        #        ... but it also makes column widths non-adjustable
        # column_header.setSectionResizeMode(column_header.Stretch)
        # row_header = self.verticalHeader()
        # NOTE:  enable sorting *after* setting model but *before* resizing to
        # contents (so column sizing includes sort indicators)
        self.setSortingEnabled(True)
        # wrap columns that hold TEXT_PROPERTIES
        self.setTextElideMode(Qt.ElideNone)
        for i, a in enumerate(self.view):
            self.setColumnWidth(i, PGEF_COL_WIDTHS.get(a, 100))
        # self.resizeRowsToContents()
        # QTimer trick ...
        QTimer.singleShot(0, self.resizeRowsToContents)
        # IMPORTANT:  after a sort, rows retain the heights they had before
        # the sort (i.e. wrong) unless this is done:
        self.main_table_proxy.layoutChanged.connect(
                                    self.resizeRowsToContents)
        # sort by underlying model intrinsic order
        # ("row numbers" [aka vertical header] are column -1)
        self.main_table_proxy.sort(-1, Qt.AscendingOrder)
        self.doubleClicked.connect(self.main_table_row_double_clicked)
        self.setMinimumSize(300, 200)
        self.setSizePolicy(QSizePolicy.Expanding,
                           QSizePolicy.Expanding)
        dispatcher.connect(self.on_mod_object_signal, 'modified object')

    def add_context_menu(self):
        column_header = self.horizontalHeader()
        select_columns_action = QAction('select columns', column_header)
        select_columns_action.triggered.connect(self.select_columns)
        column_header.addAction(select_columns_action)
        export_tsv_action = QAction('write table to tsv file', column_header)
        export_tsv_action.triggered.connect(self.export_tsv)
        column_header.addAction(export_tsv_action)
        export_yaml_action = QAction('export objects to yaml file',
                                     column_header)
        export_yaml_action.triggered.connect(self.export_objs_to_yaml)
        column_header.addAction(export_yaml_action)
        column_header.setContextMenuPolicy(Qt.ActionsContextMenu)

    def main_table_row_double_clicked(self, clicked_index):
        # orb.log.debug('* ObjectTableView: main_table_row_double_clicked()')
        # NOTE: maybe not the most elegant way to do this ... look again later
        mapped_row = self.main_table_proxy.mapToSource(clicked_index).row()
        orb.log.debug(
            '* [ObjectTableView] row double-clicked [mapped row: {}]'.format(
                                                            str(mapped_row)))
        oid = getattr(self.main_table_model.objs[mapped_row], 'oid')
        obj = orb.get(oid)
        dlg = PgxnObject(obj, parent=self)
        dlg.show()

    def on_section_moved(self, logical_index, old_index, new_index):
        orb.log.debug('* ObjectTableView: on_section_moved() ...')
        orb.log.debug('  logical index: {}'.format(logical_index))
        orb.log.debug('  old index: {}'.format(old_index))
        orb.log.debug('  new index: {}'.format(new_index))
        orb.log.debug('  self.view: {}'.format(str(self.view)))
        new_view = self.view[:]
        moved_item = new_view.pop(old_index)
        if new_index > len(new_view) - 1:
            new_view.append(moved_item)
        else:
            new_view.insert(new_index, moved_item)
        orb.log.debug('  new view: {}'.format(str(new_view)))
        if not prefs.get('db_views'):
            prefs['db_views'] = {}
        prefs['db_views'][self.cname] = new_view[:]
        dispatcher.send('new object table view pref', cname=self.cname)

    def on_mod_object_signal(self, obj=None, cname=''):
        """
        Handle 'modified object' dispatcher signal.
        """
        orb.log.debug('* ObjectTableView: on_mod_object_signal()')
        idx = self.main_table_model.mod_object(obj)
        if idx is not None:
            try:
                self.selectRow(idx.row())
            except:
                # oops, my C++ object went away ...
                orb.log.debug('  - obj not found (table possibly recreated).')

    def select_columns(self):
        """
        Dialog displayed in response to 'select columns' context menu item.
        """
        orb.log.debug('* ObjectTableView: select_columns() ...')
        # NOTE: all_cols is a *copy* from the schema -- DO NOT modify the
        # original schema!!!
        all_cols = ((orb.schemas.get(self.cname) or {}).get(
                                                    'field_names') or [])[:]
        dlg = SelectColsDialog(all_cols, self.view, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            # rebuild custom view from the selected columns
            old_view = self.view[:]
            new_view = []
            # add any columns from old_view first
            for col in old_view:
                if col in dlg.checkboxes and dlg.checkboxes[col].isChecked():
                    new_view.append(col)
                    all_cols.remove(col)
            # then append any newly selected columns
            for col in all_cols:
                if dlg.checkboxes[col].isChecked():
                    new_view.append(col)
            orb.log.debug('  new view: {}'.format(new_view))
            if not prefs.get('db_views'):
                prefs['db_views'] = {}
            prefs['db_views'][self.cname] = new_view[:]
            self.view = new_view[:]
            orb.log.debug('  self.view: {}'.format(str(self.view)))
            self.setup_table()

    def export_tsv(self):
        """
        Write the table content to a tsv (tab-separated-values) file.
        """
        orb.log.debug('* export_tsv()')
        dtstr = date2str(dtstamp())
        objs_name = '-'.join(get_external_name_plural(self.cname).split(' '))
        fpath, filters = QFileDialog.getSaveFileName(
                                    self, 'Write to tsv File',
                                    objs_name + '-' + dtstr + '.tsv')
        if fpath:
            orb.log.debug('  - file selected: "%s"' % fpath)
            fpath = str(fpath)    # QFileDialog fpath is unicode; UTF-8 (?)
            state['last_path'] = os.path.dirname(fpath)
            f = open(fpath, 'w')
            table = self.main_table_proxy
            header = '\t'.join(self.view[:])
            rows = [header]
            for row in range(table.rowCount()):
                rows.append('\t'.join([table.data(table.index(row, col))
                                       for col in range(len(self.view))]))
            content = '\n'.join(rows)
            f.write(content)
            f.close()
            html = '<h3>Success!</h3>'
            msg = 'Table contents exported to file:'
            html += '<p><b><font color="green">{}</font></b><br>'.format(msg)
            html += '<b><font color="blue">{}</font></b></p>'.format(fpath)
            self.w = NotificationDialog(html, news=False, parent=self)
            self.w.show()
        else:
            orb.log.debug('  ... export to tsv cancelled.')
            return

    def export_objs_to_yaml(self):
        """
        Serialize the table objects to a yaml file.
        """
        dtstr = date2str(dtstamp())
        fpath, filters = QFileDialog.getSaveFileName(
                                    self, 'Export to yaml File',
                                    self.cname + '-objs-' + dtstr + '.yaml')
        if fpath:
            orb.log.debug('  - file selected: "%s"' % fpath)
            fpath = str(fpath)    # QFileDialog fpath is unicode; UTF-8 (?)
            state['last_path'] = os.path.dirname(fpath)
            f = open(fpath, 'w')
            sobjs = serialize(orb, self.objs, include_refdata=True)
            content = yaml.safe_dump(sobjs, default_flow_style=False)
            f.write(content)
            f.close()
            html = '<h3>Success!</h3>'
            msg = 'Objects exported to file:'
            html += '<p><b><font color="green">{}</font></b><br>'.format(msg)
            html += '<b><font color="blue">{}</font></b></p>'.format(fpath)
            self.w = NotificationDialog(html, news=False, parent=self)
            self.w.show()


class CompareWidget(QDialog):
    """
    A table for comparing objects side-by-side by their parameter values.
    """
    def __init__(self, objs, parameters, parent=None):
        """
        Initialize

        objs (Identifiable):  objects to be compared
        parameters (list of str):  ids of parameters to compare by
        """
        super().__init__(parent=parent)
        self.objs = objs
        self.parameters = parameters
        tablemodel = CompareTableModel(objs, parameters, parent=self)
        self.tableview = QTableView()
        self.tableview.setModel(tablemodel)
        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.tableview)
        self.bbox = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.bbox.rejected.connect(self.reject)
        self.layout.addWidget(self.bbox)
        self.setLayout(self.layout)
        self.resize(self.tableview.width()-200,
                    self.tableview.height()-100)
        dispatcher.connect(self.refresh, 'new object')

    def refresh(self, obj=None):
        # TODO: a more elegant refresh with setData() etc.
        if (obj and obj.__class__.__name__ == 'Acu'
            and obj.assembly in self.objs):
            self.layout.removeWidget(self.bbox)
            self.layout.removeWidget(self.tableview)
            tablemodel = CompareTableModel(self.objs, self.parameters,
                                           parent=self)
            self.tableview = QTableView()
            self.tableview.setModel(tablemodel)
            self.layout.addWidget(self.tableview)
            self.layout.addWidget(self.bbox)
            self.resize(self.tableview.width()-200,
                        self.tableview.height()-100)

