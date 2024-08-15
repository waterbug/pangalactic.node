"""
Widgets based on QTableView and QTableWidget
"""
import os

# ruamel_yaml
import ruamel_yaml as yaml

# PyQt
from PyQt5.QtCore    import Qt, QSize, QTimer
from PyQt5.QtWidgets import (QAction, QApplication, QDialog, QDialogButtonBox,
                             QFileDialog, QSizePolicy, QTableView,
                             QTableWidget, QVBoxLayout)

# Louie
from louie import dispatcher

# pangalactic
from pangalactic.core             import orb
from pangalactic.core             import prefs, state
from pangalactic.core.meta        import IDENTITY, MAIN_VIEWS, PGEF_COL_WIDTHS
from pangalactic.core.names       import (get_external_name_plural,
                                          pname_to_header)
from pangalactic.core.parametrics import get_dval, get_pval, get_pval_as_str
from pangalactic.core.serializers import serialize
from pangalactic.core.units       import time_unit_names
from pangalactic.core.utils.datetimes import dtstamp, date2str
from pangalactic.node.tablemodels import (ObjectTableModel,
                                          CompareTableModel,
                                          SpecialSortModel)
from pangalactic.node.dialogs     import (NotificationDialog, SelectColsDialog,
                                          TimeUnitsDialog)
from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.utils       import InfoTableHeaderItem, InfoTableItem


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
        # orb.log.debug('* [ObjectTableView] initializing ...')
        self.objs = objs
        self.view = view
        self.setup()
        self.add_context_menu()

    def setup(self):
        self.cname = None
        # if a main_table_proxy exists, remove it so gui doesn't get confused
        if self.objs:
            self.cname = self.objs[0].__class__.__name__
            # orb.log.debug('  - for class: "{}"'.format(self.cname))
            if not self.view:
                # if no view is specified, use the preferred view, if any
                if (prefs.get('db_views') or {}).get(self.cname):
                    self.view = prefs['db_views'][self.cname][:]
        # else:
            # orb.log.debug('  - no objects provided.')
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
        self.setModel(self.main_table_proxy)
        self.setSelectionBehavior(QTableView.SelectRows)
        column_header = self.horizontalHeader()
        column_header.setStyleSheet('font-weight: bold')
        # TODO:  try setting header colors using Qt functions ...
        column_header.setSectionsMovable(True)
        column_header.sectionMoved.connect(self.on_section_moved)
        # NOTE:  the following line will make table width fit into window
        #        ... but it also makes column widths non-adjustable
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
        try:
            self.main_table_model.mod_object(obj.oid)
        except:
            # oops, my model's C++ object went away ...
            orb.log.debug('  - obj not found (table possibly recreated).')
        # if idx is not None:
            # try:
                # self.selectRow(idx.row())
            # except:
                # # oops, my C++ object went away ...
                # orb.log.debug('  - obj not found (table possibly recreated).')

    def select_columns(self):
        """
        Displays the SelectColsDialog in response to 'select columns' context
        menu item.
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
            self.setup()

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



class ActInfoTable(QTableWidget):
    """
    Table to provide an editable view of Activity instances in the timeline of
    a parent activity. The rows of the table contain properties and parameters
    of Activity instances.

    The target use case is the Concept of Operations (ConOps) for a mission.
    """
    def __init__(self, subject, project=None, timeline=None, view_conf=None,
                 editable=False, min_col_width=20, max_col_width=300,
                 parent=None):
        """
        Initialize

        Args:
            subject (Activity):  Activity whose sub-activities are to be
                shown in the table

        Keyword Args:
            project (Project): [required] the project whose systems' activities
                are displayed in the table
            timeline (Timeline): the timeline (QGraphicsPathItem) containing
                the activity event blocks
            view_conf (list):  list in which each element is a 3-tuple
                (pname, colname, width), where pname is the property id,
                colname is the column name (if empty string, pname is the
                column name), and width is the column width
            editable (bool): whether values in the table can be edited
            min_col_width (int): minimum column width (default: 100)
            max_col_width (int): maximum column width (default: 300)
            parent (QWidget):  parent widget
        """
        super().__init__(parent=parent)
        orb.log.info('* ActInfoTable initializing ...')
        self.project = project
        self.subject = subject
        self.timeline = timeline
        self.editable = editable
        self.min_col_width = min_col_width
        self.max_col_width = max_col_width
        default_view_conf = [
            ('name', '', 200),
            ('t_start', 'Start', 80),
            ('duration', 'Duration', 80),
            ('t_end', 'End', 80),
            ('time_units', 'Time Units', 120)
            ]
        self.view_conf = view_conf or default_view_conf[:]
        self.setup()
        self.itemChanged.connect(self.on_item_mod)

    @property
    def acts(self):
        """
        The "acts" are the activities corresponding to the event blocks shown
        in the timeline.
        """
        # a = []
        # if self.subject:
            # a = getattr(self.subject, 'sub_activities', []) or []
        # if a:
            # a.sort(key=lambda x: x.sub_activity_sequence or 0)
        # return a
        timeline = getattr(self, 'timeline', None)
        if timeline:
            return [block.activity for block in self.timeline.evt_blocks]
        else:
            return []

    @property
    def view(self):
        """
        The "view" is simply the list of property names associated with the
        columns (in keeping with its definition elsewhere).
        """
        return [x[0] for x in self.view_conf]

    def setup(self):
        orb.log.debug('  - ActInfoTable.setup()')
        self.setColumnCount(len(self.view))
        self.setRowCount(len(self.acts))
        for i, (pname, colname, width) in enumerate(self.view_conf):
            if colname:
                header_label = InfoTableHeaderItem(text=colname)
            else:
                # create col names based on pnames
                header_label = InfoTableHeaderItem(
                                text=pname_to_header(pname, '', width=width))
            self.setHorizontalHeaderItem(i, header_label)
        # populate relevant data
        for i, act in enumerate(self.acts):
            oid = act.oid
            time_unit_name = get_dval(oid, "time_units") or 'minutes'
            time_units = time_unit_names.get(time_unit_name) or 'minute'
            for j, ptuple in enumerate(self.view_conf):
                pname, colname, width = ptuple
                if pname == 'time_units':
                    item = InfoTableItem(time_unit_name)
                else:
                    item = InfoTableItem(orb.get_prop_val_as_str(oid, pname,
                                                             units=time_units)
                                                             or '')
                if pname in ('t_start', 't_end'):
                    # always non-editable (computed from sequences/durations)
                    item.setFlags(Qt.NoItemFlags)
                    item.setForeground(Qt.darkMagenta)
                if not self.editable:
                    item.setFlags(Qt.NoItemFlags)
                self.setItem(i, j, item)
        for j, ptuple in enumerate(self.view_conf):
            pname, colname, width = ptuple
            self.setColumnWidth(j, width)
        self.recompute_timeline()

    def sizeHint(self):
        # return QSize(400, 400)
        horizontal = self.horizontalHeader()
        vertical = self.verticalHeader()
        frame = self.frameWidth() * 2
        return QSize(horizontal.width(),
                     vertical.length() + horizontal.height() + frame)

    def on_item_mod(self, item=None):
        orb.log.debug('  - ActInfoTable.on_item_mod()')
        row = item.row()
        col = item.column()
        cur_item = self.currentItem()
        cur_row = cur_item.row()
        cur_col = cur_item.column()
        if (row == cur_row and col == cur_col):
            act = self.acts[row]
            oid = act.oid
            pname = self.view[col]
            str_val = item.data(Qt.EditRole)
            # set_prop_val() tries to cast value to correct datatype and
            # returns a status message with what happened
            msg = f'setting {pname} of {act.name} to <{str_val}>'
            orb.log.debug(f'    {msg} ...')
            if pname == 'name':
                act.name = str_val
                act.mod_datetime = dtstamp()
                orb.save([act])
                # self.resizeColumnsToContents()
                dispatcher.send(signal="act name mod", act=act, remote=False)
            elif pname == 'time_units':
                # TODO: when time units are set, convert existing values (if
                # any) and do other computations as necessary ...
                if str_val in time_unit_names:
                    time_unit_id = time_unit_names[str_val]
                else:
                    dlg = TimeUnitsDialog(parent=self)
                    if dlg.exec_() == QDialog.Accepted:
                        str_val = dlg.time_unit_name
                        time_unit_id = time_unit_names[str_val]
                    else:
                        str_val = 'minutes'
                        time_unit_id = 'minute'
                # NOTE: "time_units" data element is a time unit *name*
                status = orb.set_prop_val(oid, "time_units", str_val)
                item.setData(Qt.EditRole, str_val)
                # show time parameters in the appropriate units ...
                for pid in 't_start', 'duration', 't_end':
                    val_str = orb.get_prop_val_as_str(oid, pid,
                                                      units=time_unit_id)
                    self.item(row, self.view.index(pid)).setData(Qt.EditRole,
                                                                 val_str)
                if 'failed' in status:
                    # TODO: pop-up notification to user ...
                    orb.log.debug(f'    {status}')
                    orb.log.debug('    operation aborted.')
                    return
                orb.log.debug('    succeeded.')
                # self.resizeColumnsToContents()
                des = {oid : {'time_units' : str_val}}
                dispatcher.send(signal="des set", des=des)
            else:
                # a time parameter was modified, set and propagate ...
                act_units = get_dval(oid, "time_units") or 's'
                txt = f'setting {act.name} {pname} to {str_val} {act_units}'
                orb.log.debug(f'    {txt}')
                status = orb.set_prop_val(oid, pname, str_val, units=act_units)
                if 'failed' in status:
                    # TODO: pop-up notification to user ...
                    orb.log.debug(f'    {status}')
                    orb.log.debug('    operation aborted.')
                    return
                orb.log.debug('    succeeded.')
                # NOTE: get parm val in base units before sending --
                # vger.set_properties only takes values in base units!!
                val = get_pval(oid, pname)
                props = {oid : {pname : val}}
                dispatcher.send(signal="act mods", prop_mods=props)
                self.blockSignals(True)
                self.adjust_timeline(item)
                self.blockSignals(False)
            for j, ptuple in enumerate(self.view_conf):
                width = ptuple[2]
                self.setColumnWidth(j, width)
        else:
            loc = f'({row}, {col})'
            orb.log.debug(f'    item {loc} is not current item; ignoring.')

    def adjust_timeline(self, item):
        """
        Adjust all activity timeline properties when an item value has been
        set.

        Args:
            item (InfoTableItem): item whose value was set
        """
        orb.log.debug('    adjust_timeline()')
        # prop_mods collects all property modifications
        NOW = dtstamp()
        prop_mods = {}
        row = item.row()
        col = item.column()
        act = self.acts[row]
        oid = act.oid
        act_units = get_dval(oid, "time_units") or 'minute'
        act.mod_datetime = NOW
        acts_modded = [act]
        pname = self.view[col]
        # prop_mods contains all mods in base units
        prop_mods[oid] = {}
        if pname == 'duration':
            # get current value of "t_start" in base units
            t_start = orb.get_prop_val(oid, 't_start')
            # get new value of "duration" in base units
            duration = orb.get_prop_val(oid, 'duration')
            prop_mods[oid]['duration'] = duration
            new_t_end = t_start + duration
            # new_t_end is also in base units
            orb.set_prop_val(oid, 't_end', new_t_end)
            prop_mods[oid]['t_end'] = new_t_end
            txt = f'setting {act.name} t_end to <{new_t_end}> (seconds)'
            orb.log.debug(f'    {txt}')
            # get new value of "t_end" in specified units as a str
            t_end_str = orb.get_prop_val_as_str(oid, 't_end', units=act_units)
            self.item(row, self.view.index('t_end')).setData(Qt.EditRole,
                                                             t_end_str)
            # also set the item value using the corrected datatype str
            duration_str = orb.get_prop_val_as_str(oid, 'duration',
                                                   units=act_units)
            item.setData(Qt.EditRole, duration_str)
        elif pname == 'time_units':
            # if 'time_units' is set, just set the item's t_start, duration and
            # t_end in the new units (the value is stored in parameterz dict in
            # base units)
            new_units_name = self.item(row,
                                       self.view.index('time_units')).data(
                                                                Qt.EditRole)
            if not new_units_name:
                new_units_name = 'minutes'
            time_units = time_unit_names.get(new_units_name) or 'minute'
            conv_t_start = get_pval_as_str(oid, 't_start',
                                           units=time_units)
            conv_duration = get_pval_as_str(oid, 'duration',
                                            units=time_units)
            conv_t_end = get_pval_as_str(oid, 't_end', units=time_units)
            self.item(row, self.view.index('t_start')).setData(Qt.EditRole,
                                                                conv_t_start)
            self.item(row, self.view.index('duration')).setData(Qt.EditRole,
                                                                conv_duration)
            self.item(row, self.view.index('t_end')).setData(Qt.EditRole,
                                                                conv_t_end)
            prop_mods[oid]['time_units'] = new_units_name
        # if a time parameter was modified (t_start, duration, or t_end) and
        # there are activities following this one, adjust their properties
        # accordingly ...
        time_parms = set(['duration'])
        time_parms_modified = time_parms & set(prop_mods[oid])
        if time_parms_modified:
            # if len(self.acts) > row + 1:
            # TODO: test!
            mod_acts, more_prop_mods = self.recompute_timeline()
            act_names = [act.name for act in mod_acts]
            orb.log.debug('  - modified activities:')
            for aname in act_names:
                orb.log.debug(f'    + {aname}')
            if mod_acts:
                for other_act in mod_acts:
                    other_act.mod_datetime = NOW
                acts_modded += mod_acts
            if more_prop_mods:
                prop_mods.update(more_prop_mods)

        if not state.get('connected'):
            # * if not connected, save locally
            # * if connected, the server will time-date-stamp them, save, and
            #   publish the time-date-stamp in "properties set" message.
            orb.save(acts_modded)
        for j, ptuple in enumerate(self.view_conf):
            width = ptuple[2]
            self.setColumnWidth(j, width)
        dispatcher.send(signal="act mods", prop_mods=prop_mods)

    def recompute_timeline(self):
        """
        Recompute t_start and t_end parameters for all timeline activities
        beginning from the specified row.
        """
        orb.log.debug('* recompute_timeline()')
        t_end = 0.0
        acts_modded = []
        prop_mods = {}
        for row, act in enumerate(self.acts):
            mods = False
            oid = act.oid
            t_units = get_dval(oid, "time_units") or 'minutes'
            prop_mods[oid] = {}
            txt = f'updating {act.name} ...'
            orb.log.debug(f'    {txt}')
            orig_t_start = orb.get_prop_val(oid, 't_start')
            if orig_t_start != t_end:
                orb.set_prop_val(oid, 't_start', t_end)
                prop_mods[oid]['t_start'] = t_end
                orb.log.debug(f'    {act.name} t_start set to {t_end}')
                mods = True
            t_start = orb.get_prop_val(oid, 't_start')
            t_start_str = orb.get_prop_val_as_str(oid, 't_start', units=t_units)
            self.item(row, self.view.index('t_start')).setData(Qt.EditRole,
                                                                t_start_str)
            duration = orb.get_prop_val(oid, 'duration')
            orig_t_end = orb.get_prop_val(oid, 't_end')
            new_t_end = t_start + duration
            if new_t_end != orig_t_end:
                orb.set_prop_val(oid, 't_end', new_t_end)
                prop_mods[oid]['t_end'] = new_t_end
                orb.log.debug(f'    {act.name} t_end set to {new_t_end}')
                mods = True
            t_end_str = orb.get_prop_val_as_str(oid, 't_end', units=t_units)
            self.item(row, self.view.index('t_end')).setData(Qt.EditRole,
                                                                t_end_str)
            # set t_end (in base units, of course) for next loop ...
            t_end = orb.get_prop_val(oid, 't_end')
            if mods:
                acts_modded.append(act)
        return acts_modded, prop_mods


class SystemInfoTable(QTableWidget):
    """
    Table whose main purpose is to provide an editable view of one level of a
    composite system and possibly additional related items. The rows of the
    table contain properties and parameters of components, their usages in the
    assembled system, and possibly related items.

    The target use case is the Error Budget for an optical system, which will
    also include sources of errors.
    """
    def __init__(self, system=None, view=None, sort_on='component',
                 sort_by_field=None, min_col_width=100, max_col_width=300,
                 parent=None):
        """
        Initialize

        Keyword Args:
            system (HardwareProduct):  the system whose assembly is shown
            view (list):  list in which each element is a 3-tuple
                (pname, colname, otype), where pname is the property id,
                colname is the column name (if empty string, pname is the
                column name, and otype is either "component" or "usage" (Acu),
                indicating the owner of the property
            sort_on (str): 'usage' or 'component' (default: 'component')
            sort_by_field (str): id of attr, parm, or data element to sort by
            min_col_width (int): minimum column width (default: 100)
            max_col_width (int): maximum column width (default: 300)
        """
        super().__init__(parent=parent)
        # orb.log.info('* [SystemInfoTable] initializing ...')
        self.system = system
        self.sort_on = sort_on
        self.sort_by_field = sort_by_field
        self.min_col_width = min_col_width
        self.max_col_width = max_col_width
        # TODO: get default view from prefs / config
        default_view = [
            ('m[CBE]', '', 'component'),
            ('P[CBE]', '', 'component'),
            ('R_D[CBE]', '', 'component')
            ]
        self.view = view or default_view[:]
        self.setup()

    def setup(self):
        self.setColumnCount(len(self.view))
        usages = getattr(self.system, 'components', []) or []
        if usages:
            self.setRowCount(len(usages))
        else:
            self.setRowCount(1)
        header_labels = []
        widths = []
        for pname, colname, otype in self.view:
            if colname:
                header_label = colname
                header_labels.append(header_label)
            else:
                header_label = pname_to_header(pname, '', pwidth=15,
                                               headers_are_ids=True)
                header_labels.append(header_label)
            # set col widths based on length of header text
            if colname:
                width = len(colname)*20
            else:
                width = max([len(l) for l in header_label.split('\n')])*20
            width = max(max(width, self.min_col_width), self.max_col_width)
            widths.append(width)
        self.setHorizontalHeaderLabels(header_labels)
        # populate relevant data
        if usages:
            if self.sort_by_field:
                if self.sort_on == 'component':
                    usages.sort(key=lambda x:orb.get_prop_val(x.component,
                                                          self.sort_by_field))
                elif self.sort_on == 'usage':
                    usages.sort(key=lambda x:
                                orb.get_prop_val(x, self.sort_by_field))
            for i, usage in enumerate(usages):
                for j, ptuple in enumerate(self.view):
                    pname, colname, otype = ptuple
                    if otype == 'component':
                        component = getattr(usage, 'component')
                        self.setItem(i, j, InfoTableItem(
                            orb.get_prop_val_as_str(component, pname) or ''))
                    elif otype == 'usage':
                        self.setItem(i, j, InfoTableItem(
                            orb.get_prop_val_as_str(usage, pname) or ''))
        width_fit = sum(w for w in widths) + 100
        self.resize(width_fit, 240)


if __name__ == "__main__":
    import sys
    orb.start(home='/home/waterbug/cattens_home_dev', debug=True, test=True,
              console=True)
    app = QApplication(sys.argv)
    # example code goes here ...
    sys.exit(app.exec_())

