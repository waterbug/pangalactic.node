#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Dashboards:  a dashboard in Pangalaxian is a dockable widget in the top section
of the main window, in which columns can be added to display the current values
and realtime updates of specified parameters of a system that is being modeled.
"""
import os
from pydispatch import dispatcher

from PyQt5.QtCore    import (pyqtSignal, Qt, QItemSelectionModel, QModelIndex,
                             QVariant)
from PyQt5.QtWidgets import (QAction, QComboBox, QDialog, QFileDialog,
                             QHBoxLayout, QLabel, QMessageBox, QStackedWidget,
                             QTreeView, QVBoxLayout, QWidget)

# pangalactic
try:
    from pangalactic.core                 import orb, prefs, state
except:
    import pangalactic.core.set_uberorb
    from pangalactic.core                 import orb, prefs, state
from pangalactic.core.parametrics     import mode_defz, parm_defz
from pangalactic.core.utils.datetimes import dtstamp, date2str
from pangalactic.core.utils.reports   import write_mel_to_tsv
from pangalactic.core.validation      import get_assembly, get_bom_oids
from pangalactic.node.utils           import extract_mime_data
from pangalactic.node.dialogs         import (CustomizeColsDialog,
                                              DeleteColsDialog,
                                              NewDashboardDialog,
                                              NotificationDialog,
                                              UnitPrefsDialog)
from pangalactic.node.systemtree      import (SystemTreeModel,
                                              SystemTreeProxyModel,
                                              SystemTreeView)


class SystemDashboard(QTreeView):

    units_set = pyqtSignal()

    def __init__(self, view_model, row_colors=True, grid_lines=False,
                 parent=None):
        """
        Initialize.

        Args:
            view_model (SystemTreeProxyModel): view model of the current system
                tree.

        Keyword Args:
            row_colors (bool): show rows with alternating bg colors
                (default: True)
            grid_lines (bool): show grid lines separting rows/columns
                (default: True)
            parent (QWidget):  parent widget
        """
        super().__init__(parent)
        self.setSelectionMode(self.SingleSelection)
        self.setUniformRowHeights(True)
        if 'dash_grid_lines' in prefs:
            self.grid_lines = prefs['dash_grid_lines']
        else:
            self.grid_lines = grid_lines
        if 'dash_row_colors' in prefs:
            self.row_colors = prefs['dash_row_colors']
        else:
            self.row_colors = row_colors
        self.setAlternatingRowColors(self.row_colors)
        self.setModel(view_model)
        # *********************************************************************
        # NOTE:  the following functions are HORRIBLY SENSITIVE to the order in
        # which they are called -- in particular, expandAll() will consistently
        # cause segfaults if it is done later in the initialization!  Per
        # testing done so far, this order is stable.
        # (1) expandAll
        # (2) setStyleSheet
        # (3) treeExpanded
        # *********************************************************************
        # NOTE: don't expand by default -- very cumbersome for big trees, and
        # anyway it is much better to use the "selected" state to determine the
        # level of expansion ...
        self.setStyleSheet('font-weight: normal; '
                           'font-size: 12px; '
                           'QToolTip { font-weight: normal; '
                           'font-size: 12px; border: 2px solid; };')
        dash_header = self.header()
        # DO NOT add "padding-left" or "padding-right" attrs to this
        # stylesheet -- that will mess up the alignment of headers w/columns!!
        dash_header.setStyleSheet(
                           'QHeaderView { font-weight: bold; '
                           'font-size: 14px; border: 1px; } '
                           'QToolTip { font-weight: normal; '
                           'font-size: 12px; border: 2px solid; };')
        dash_header.setDefaultAlignment(Qt.AlignHCenter)
        # accept drops of parameters on dash to add columns
        self.setAcceptDrops(True)
        self.accepted_mime_types = set([
                             "application/x-pgef-parameter-definition",
                             "application/x-pgef-data-element-definition",
                             "application/x-pgef-parameter-id"])
        # provide a context menu for various actions
        set_units_action = QAction('set preferred units', dash_header)
        set_units_action.triggered.connect(self.set_units)
        dash_header.addAction(set_units_action)
        show_grid_action = QAction('show grid lines', dash_header)
        show_grid_action.triggered.connect(self.show_grid)
        dash_header.addAction(show_grid_action)
        hide_grid_action = QAction('hide grid lines', dash_header)
        hide_grid_action.triggered.connect(self.hide_grid)
        dash_header.addAction(hide_grid_action)
        row_colors_action = QAction('set alternating row colors', dash_header)
        row_colors_action.triggered.connect(self.set_alt_colors)
        dash_header.addAction(row_colors_action)
        no_row_colors_action = QAction('clear row colors', dash_header)
        no_row_colors_action.triggered.connect(self.set_no_colors)
        dash_header.addAction(no_row_colors_action)
        prescriptive_parms_action = QAction('select prescriptive parameters',
                                            dash_header)
        prescriptive_parms_action.triggered.connect(
                                            self.select_prescriptive_parms)
        dash_header.addAction(prescriptive_parms_action)
        delete_columns_action = QAction('delete columns', dash_header)
        delete_columns_action.triggered.connect(self.delete_columns)
        dash_header.addAction(delete_columns_action)
        # -------------------------------------------------------------------
        # NOTE: dash board mods temporarily deactivated -- dash switching is
        # causing segfaults [SCW 2024-02-07]
        # -------------------------------------------------------------------
        # create_dashboard_action = QAction('create new dashboard', dash_header)
        # create_dashboard_action.triggered.connect(self.create_dashboard)
        # dash_header.addAction(create_dashboard_action)
        # set_as_pref_action = QAction('set as preferred dashboard', dash_header)
        # set_as_pref_action.triggered.connect(self.set_as_pref_dashboard)
        # dash_header.addAction(set_as_pref_action)
        dash_name = state.get('dashboard_name')
        # dash_name = 'MEL'
        # -------------------------------------------------------------------
        if dash_name in (state.get('app_dashboards') or {}).keys():
            txt = f'use standard {dash_name} dashboard schema'
            use_app_dash_action = QAction(txt, dash_header)
            use_app_dash_action.triggered.connect(self.use_app_dash_schema)
            dash_header.addAction(use_app_dash_action)
        # delete_dashboard_action = QAction('delete dashboard', dash_header)
        # delete_dashboard_action.triggered.connect(self.delete_dashboard)
        # dash_header.addAction(delete_dashboard_action)
        export_tsv_mks_action = QAction('export to .tsv file (mks units)',
                                        dash_header)
        export_tsv_mks_action.triggered.connect(self.export_tsv_mks)
        dash_header.addAction(export_tsv_mks_action)
        export_tsv_pref_action = QAction(
                                    'export to .tsv file (preferred units)',
                                    dash_header)
        export_tsv_pref_action.triggered.connect(self.export_tsv_pref)
        dash_header.addAction(export_tsv_pref_action)
        dash_header.setContextMenuPolicy(Qt.ActionsContextMenu)
        # NOTE: moving a section currently causes a crash -- temporarily
        # deactivated [SCW 2024-02-07]
        # dash_header.sectionMoved.connect(self.on_section_moved)
        dash_header.setStretchLastSection(False)
        # "successful_drop" refers to product drops on sys tree (for syncing)
        # *** DEPRECATED now that tree is not editable
        # view_model.sourceModel().successful_drop.connect(
                                               # self.on_successful_drop)
        dispatcher.connect(self.dash_node_expand, 'sys node expanded')
        dispatcher.connect(self.dash_node_collapse, 'sys node collapsed')
        dispatcher.connect(self.dash_node_select, 'sys node selected')
        dispatcher.connect(self.dash_node_select, 'diagram go back')
        dispatcher.connect(self.dash_node_select, 'diagram tree index')
        self.expanded.connect(self.dash_node_expanded)
        self.collapsed.connect(self.dash_node_collapsed)
        self.clicked.connect(self.dash_node_selected)
        n = state.get('sys_tree_expansion', {}).get(state.get('project'))
        if n is not None:
            self.expandToDepth(n + 1)
            # orb.log.debug(f'[Dashboard] expanded to level {n + 2}')
        else:
            self.expandToDepth(1)
            # orb.log.debug('[Dashboard] expanded to default level (2)')
        for column in range(1, view_model.sourceModel().columnCount()):
            self.resizeColumnToContents(column)
        # self.header().resizeSection(0, 400)
        # DO NOT use `setMinimumSize()` here -- it breaks the slider that
        # appears when window size is too small to display the full width

    def sizeHintForColumn(self, i):
        if i == 0:
            return 400
        # selected to fit most numeric values with 4 significant digits
        return 60

    def drawRow(self, painter, option, index):
        QTreeView.drawRow(self, painter, option, index)
        if self.grid_lines:
            painter.setPen(Qt.lightGray)
            y = option.rect.y()
            # saving is mandatory to keep alignment throughout the row painting
            painter.save()
            painter.translate(self.visualRect(
                self.model().index(0, 0)).x() - self.indentation() - .5, -.5)
            for sectionId in range(self.header().count() - 1):
                painter.translate(self.header().sectionSize(sectionId), 0)
                painter.drawLine(0, y, 0, y + option.rect.height())
            painter.restore()
            # don't draw the line before the root index
            if index == self.model().index(0, 0):
                return
            painter.drawLine(0, y, option.rect.width(), y)

    def on_section_moved(self, logical, old, new):
        orb.log.debug('[Dashboard] section moved')
        # orb.log.debug(' + logical: {} old: {} new: {}'.format(
                                                        # logical, old, new))
        cols = prefs['dashboards'][state.get('dashboard_name', 'MEL')]
        # orb.log.debug('   cols: {}'.format(str(cols)))
        colname = cols.pop(old-1)
        # orb.log.debug(f'   colname: {colname}')
        cols.insert(new-1, colname)
        # orb.log.debug('   inserting at {}'.format(new-1))
        prefs['dashboards'][state['dashboard_name']] = cols[:]
        # orb.log.debug('   new pref cols: {}'.format(str(cols)))
        dispatcher.send(signal='dashboard mod')

    def mimeTypes(self):
        """
        Return MIME Types accepted for drops.
        """
        return ['application/x-pgef-parameter-definition',
                "application/x-pgef-data-element-definition",
                "application/x-pgef-parameter-id"]

    def supportedDropActions(self):
        return Qt.CopyAction

    def dragEnterEvent(self, event):
        mime_formats = set(event.mimeData().formats())
        if mime_formats & self.accepted_mime_types:
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        mime_formats = set(event.mimeData().formats())
        if mime_formats & self.accepted_mime_types:
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        """
        Handle drop events (for "parameter-definition").
        """
        if event.mimeData().hasFormat(
            'application/x-pgef-parameter-definition'):
            data = extract_mime_data(event,
                                     'application/x-pgef-parameter-definition')
            icon, pd_oid, pd_id, pd_name, pd_cname = data
            dash_name = state.get('dashboard_name', 'unnamed')
            state['dashboard_name'] = dash_name
            if pd_id not in prefs['dashboards'].get(dash_name, []):
                orb.log.info('[Dashboard] New parameter dropped -- adding '
                             f'column for "{pd_id}" ...')
                # if dropped PD is not in columns, add it
                prefs['dashboards'][dash_name].append(pd_id)
                # orb.log.debug('sending "dashboard mod" signal ...')
                # this will trigger refresh_tree_and_dashboard() in pangalaxian
                # (tree has to be rebuilt because columns are in model)
                dispatcher.send(signal='refresh tree and dash')
                event.accept()
            else:
                event.ignore()
                orb.log.info(f'* Parameter drop event: ignoring "{pd_id}" -- '
                             "we already got one, it's verra nahss!")
        elif event.mimeData().hasFormat("application/x-pgef-parameter-id"):
            pid = extract_mime_data(event, "application/x-pgef-parameter-id")
            dash_name = state.get('dashboard_name', 'unnamed')
            state['dashboard_name'] = dash_name
            if not dash_name in prefs['dashboard_names']:
                prefs['dashboard_names'].append(dash_name)
            if pid not in prefs['dashboards'][dash_name]:
                orb.log.info('[Dashboard] New parameter dropped -- adding '
                             f'column for "{pid}" ...')
                prefs['dashboards'][dash_name].append(pid)
                dispatcher.send(signal='refresh tree and dash')
                event.accept()
            else:
                event.ignore()
                orb.log.info(f'* Parameter drop event: ignoring "{pid}" -- '
                             "we already got one, it's verra nahss!")
        elif event.mimeData().hasFormat(
            "application/x-pgef-data-element-definition"):
            orb.log.info("* dropEvent: got data element")
            data = extract_mime_data(event,
                             "application/x-pgef-data-element-definition")
            icon, ded_oid, deid, de_name, ded_cname = data
            orb.log.info(f'* DE drop event: "{de_name}" ("{deid}")')
            dash_name = state.get('dashboard_name', 'unnamed')
            state['dashboard_name'] = dash_name
            if not dash_name in prefs['dashboard_names']:
                prefs['dashboard_names'].append(dash_name)
            if deid not in prefs['dashboards'][dash_name]:
                orb.log.info(f'  adding column for "{deid}" ...')
                prefs['dashboards'][dash_name].append(deid)
                dispatcher.send(signal='refresh tree and dash')
                event.accept()
            else:
                event.ignore()
                orb.log.info(f'* Data Element drop event: ignoring "{deid}"'
                             " -- we already got one, it's verra nahss!")
        else:
            # ignore anything else
            event.ignore()

    def set_units(self):
        dlg = UnitPrefsDialog(self)
        dlg.units_set.connect(self.on_units_set)
        dlg.show()

    def on_units_set(self):
        self.units_set.emit()

    def show_grid(self):
        self.grid_lines = True
        prefs['dash_grid_lines'] = True
        self.update()

    def hide_grid(self):
        self.grid_lines = False
        prefs['dash_grid_lines'] = False
        self.update()

    def set_alt_colors(self):
        self.setAlternatingRowColors(True)
        prefs['dash_row_colors'] = True

    def set_no_colors(self):
        self.setAlternatingRowColors(False)
        prefs['dash_row_colors'] = False

    def delete_columns(self):
        """
        Dialog displayed in response to 'delete columns' context menu item.
        """
        dlg = DeleteColsDialog(parent=self)
        if dlg.exec_() == QDialog.Accepted:
            cols_to_delete = []
            pids = prefs['dashboards'][state['dashboard_name']][:]
            for pid in pids:
                if dlg.checkboxes[pid].isChecked():
                    # prefs['dashboards'][state['dashboard_name']].remove(pid)
                    cols_to_delete.append(pid)
            if cols_to_delete:
                src_model = self.model().sourceModel()
                src_model.delete_columns(cols=cols_to_delete)
                indexes = [pids.index(pid) for pid in cols_to_delete]
                if 0 in indexes:
                    dispatcher.send(signal='refresh tree and dash')
                else:
                    for column in range(1, src_model.columnCount()):
                        self.resizeColumnToContents(column)

    def select_prescriptive_parms(self):
        """
        Dialog displayed in response to 'select prescriptive parameters'
        context menu item.
        """
        parm_contexts = orb.search_exact(cname='ParameterContext',
                                         context_type='prescriptive')
        prescriptive_contexts = [obj.id for obj in parm_contexts]
        all_pids = sorted(list(parm_defz))
        prescriptive_pids = [pid for pid in all_pids
                             if parm_defz[pid]['context']
                             in prescriptive_contexts]
        prescriptive_pids.sort()
        current_pids = prefs['dashboards'][state['dashboard_name']][:]
        current_prescriptives = [pid for pid in current_pids
                                 if pid in prescriptive_pids]
        dlg = CustomizeColsDialog(title="Select Prescriptive Parameters",
                                  cols=current_prescriptives,
                                  selectables=prescriptive_pids,
                                  parent=self)
        if dlg.exec_() == QDialog.Accepted:
            src_model = self.model().sourceModel()
            cols_to_delete = []
            # delete any prescriptive pids that are not checked
            for pid in current_pids:
                if (pid in prescriptive_pids
                    and not dlg.checkboxes[pid].isChecked()):
                    cols_to_delete.append(pid)
            if cols_to_delete:
                src_model.delete_columns(cols=cols_to_delete)
            current_pids = prefs['dashboards'][state['dashboard_name']][:]
            # insert any prescriptive pids that are not in the current columns
            # but are checked
            cols_to_insert = []
            for pid in prescriptive_pids:
                if (pid in dlg.checkboxes
                    and dlg.checkboxes[pid].isChecked()
                    and pid not in current_pids):
                    cols_to_insert.append(pid)
            if cols_to_insert:
                for pid in cols_to_insert:
                    src_model.insert_column(pid)
            if cols_to_delete or cols_to_insert:
                dispatcher.send(signal='refresh tree and dash')

    def create_dashboard(self):
        """
        Dialog displayed in response to 'create new dashboard' context menu
        item.
        """
        dlg = NewDashboardDialog(parent=self)
        if dlg.exec_() == QDialog.Accepted:
            dash_name = dlg.new_dash_name.text()
            prefs['dashboards'][dash_name] = []
            if dlg.preferred_dash.isChecked():
                prefs['dashboard_names'].insert(0, dash_name)
            else:
                prefs['dashboard_names'].append(dash_name)
            state['dashboard_name'] = dash_name
            dispatcher.send(signal='refresh tree and dash')

    def set_as_pref_dashboard(self):
        """
        Handler for 'set as preferred dashboard' context menu item.
        """
        dash_name = state['dashboard_name']
        prefs['dashboard_names'].remove(dash_name)
        prefs['dashboard_names'].insert(0, dash_name)
        state['dashboard_name'] = dash_name
        dispatcher.send(signal='dash pref set')

    def use_app_dash_schema(self):
        """
        Handler for 'use standard [name] dashboard schema' context menu item.
        """
        dash_name = state['dashboard_name']
        app_dash_schema = (state.get('app_dashboards') or {}).get(dash_name)
        if app_dash_schema:
            prefs['dashboards'][dash_name] = app_dash_schema
            dispatcher.send(signal='refresh tree and dash')

    def delete_dashboard(self):
        """
        Handler for 'delete dashboard' context menu item.
        """
        txt = ('This will delete the current dashboard -- '
               'are you sure?')
        confirm_dlg = QMessageBox(QMessageBox.Question, 'Delete Dashboard?',
                                  txt, QMessageBox.Yes | QMessageBox.No)
        response = confirm_dlg.exec_()
        if response == QMessageBox.Yes:
            dash_name = state['dashboard_name']
            prefs['dashboard_names'].remove(dash_name)
            del prefs['dashboards'][dash_name]
            if prefs['dashboard_names']:
                state['dashboard_name'] = prefs['dashboard_names'][0]
            else:
                # if state['dashboard_name'] is empty,
                # SystemTreeModel.__init__ logic will take care of it (will
                # create a "TBD" dashboard) 
                state['dashboard_name'] = ''
            dispatcher.send(signal='dashboard mod')

    def export_tsv_mks(self):
        """
        Handler for 'export to .tsv file (mks units)' context menu item.  I.e.
        write the dashboard content to a tab-separated-values file.  Parameter
        values will be expressed in the base mks units, and headers will be
        explicitly annotated with units.
        """
        orb.log.debug('* export_tsv_mks()')
        proxy_model = self.model()
        src_model = proxy_model.sourceModel()
        proj_id = src_model.project.id
        dtstr = date2str(dtstamp())
        dash_name = state.get('dashboard_name') or 'unknown'
        if dash_name == 'System Power Modes':
            fname = proj_id + '-Modes-Table-' + dtstr + '.tsv'
        else:
            fname = proj_id + '-' + dash_name + '-dashboard-' + dtstr + '.tsv'
        state_path = state.get('dashboard_last_path') or ''
        suggested_fpath = os.path.join(state_path, fname)
        fpath, filters = QFileDialog.getSaveFileName(
                                    self, 'Write to tsv File',
                                    suggested_fpath, '(*.tsv)')
        if fpath:
            orb.log.debug(f'  - file selected: "{fpath}"')
            fpath = str(fpath)   # extra-cautious :)
            state['dashboard_last_path'] = os.path.dirname(fpath)
            # get dashboard content
            # cols() returns a list of strings
            data_cols = proxy_model.cols[1:]
            orb.log.debug(f'  - data cols: "{str(data_cols)}"')
            write_mel_to_tsv(src_model.project, schema=data_cols,
                             file_path=fpath)
            html = '<h3>Success!</h3>'
            msg = 'Dashboard contents exported to file:'
            html += f'<p><b><font color="green">{msg}</font></b><br>'
            html += f'<b><font color="blue">{fpath}</font></b></p>'
            self.w = NotificationDialog(html, news=False, parent=self)
            self.w.show()
        else:
            orb.log.debug('  ... export to tsv cancelled.')
            return

    def export_tsv_pref(self):
        """
        [Handler for 'export to .tsv file (preferred units)' menu item]
        Write the dashboard content to a tab-separated-values file.  Parameter
        values will be expressed in the user's preferred units, and headers
        will be explicitly annotated with units.
        """
        orb.log.debug('* export_tsv_pref()')
        proxy_model = self.model()
        src_model = proxy_model.sourceModel()
        proj_id = src_model.project.id
        dtstr = date2str(dtstamp())
        dash_name = state.get('dashboard_name') or 'unknown'
        fname = proj_id + '-' + dash_name + '-dashboard-' + dtstr + '.tsv'
        state_path = state.get('dashboard_last_path') or ''
        suggested_fpath = os.path.join(state_path, fname)
        fpath, filters = QFileDialog.getSaveFileName(
                                    self, 'Write to tsv File',
                                    suggested_fpath, '(*.tsv)')
        if fpath:
            orb.log.debug(f'  - file selected: "{fpath}"')
            fpath = str(fpath)   # extra-cautious :)
            state['dashboard_last_path'] = os.path.dirname(fpath)
            # get dashboard content
            # cols() returns a list of strings
            data_cols = proxy_model.cols[1:]
            orb.log.debug(f'  - data cols: "{str(data_cols)}"')
            write_mel_to_tsv(src_model.project, schema=data_cols, pref_units=True,
                             file_path=fpath)
            html = '<h3>Success!</h3>'
            msg = 'Dashboard contents exported to file:'
            html += f'<p><b><font color="green">{msg}</font></b><br>'
            html += f'<b><font color="blue">{fpath}</font></b></p>'
            self.w = NotificationDialog(html, news=False, parent=self)
            self.w.show()
        else:
            orb.log.debug('  ... export to tsv cancelled.')
            return

    def on_successful_drop(self):
        """
        Expand the currently selected node (connected to 'rowsInserted' signal,
        to expand the drop target after a new node has been created).
        """
        sdi = self.model().sourceModel().successful_drop_index
        # map to proxy_model index
        if sdi:
            mapped_sdi = self.model().mapFromSource(sdi)
            if mapped_sdi:
                self.expand(mapped_sdi)
        for column in range(1, self.model().columnCount()):
            self.resizeColumnToContents(column)

    def dash_node_expanded(self, index):
        if not self.model():
            return
        for column in range(1, self.model().columnCount()):
            self.resizeColumnToContents(column)
        dispatcher.send(signal='dash node expanded', index=index)

    def dash_node_collapsed(self, index):
        # for column in range(self.model().columnCount()):
            # self.resizeColumnToContents(column)
        dispatcher.send(signal='dash node collapsed', index=index)

    def dash_node_selected(self, index):
        # map to source model index
        mapped_i = self.model().mapToSource(index)
        node = self.model().sourceModel().get_node(mapped_i)
        state['system'][state.get('project')] = node.obj.oid
        self.expand(index)
        dispatcher.send(signal='dash node selected', index=index, obj=node.obj)

    # def dash_node_expand(self, index=None):
        # if not self.model():
            # return
        # if index and not self.isExpanded(index):
            # self.expand(index)
            # for column in range(1, self.model().columnCount()):
                # self.resizeColumnToContents(column)

    def dash_node_expand(self, obj=None, link=None):
        if not self.model():
            return
        # orb.log.debug('Dash: got "sys node expanded" signal ...')
        idxs = []
        if obj:
            # orb.log.debug(f'   ... on object: {obj.id}')
            idxs = self.object_indexes_in_tree(obj)
        elif link:
            # orb.log.debug(f'   ... on link: {link.id}')
            idxs = self.link_indexes_in_tree(link)
        else:
            return
        if idxs:
            # orb.log.debug(f'   found {len(idxs)} occurrances in tree.')
            proxy_idx = self.model().mapFromSource(idxs[0])
            self.expand(proxy_idx)
            for column in range(1, self.model().columnCount()):
                self.resizeColumnToContents(column)

    def dash_node_collapse(self, index=None):
        if index and self.isExpanded(index):
            self.collapse(index)

    def dash_node_select(self, index=None):
        try:
            if index:
                self.selectionModel().setCurrentIndex(index,
                                          QItemSelectionModel.ClearAndSelect)
            else:
                # if no index, assume we want the project to be selected
                self.selectionModel().setCurrentIndex(
                    self.model().mapFromSource(
                    self.model().sourceModel().index(0, 0, QModelIndex())),
                    QItemSelectionModel.ClearAndSelect)
        except:
            # oops -- my C++ object probably got deleted
            pass

    def object_indexes_in_tree(self, obj):
        """
        Find the source model indexes of all nodes in the system tree that
        reference the specified object (this is needed for updating the tree
        in-place when an object is modified).

        Args:
            obj (Product):  specified object
        """
        # orb.log.debug(f'* object_indexes_in_tree({obj.id})')
        # try:
            # model = self.proxy_model.sourceModel()
        # except:
            # # oops -- C++ object probably got deleted
            # return []
        model = self.model().sourceModel()
        # orb.log.debug(f'  model is a {type(model)}')
        project_index = model.index(0, 0, QModelIndex())
        # project_node = model.get_node(project_index)
        # orb.log.debug(f'  for project {project_node.obj.id}')
        # orb.log.debug(f'  (node cname: {project_node.cname})')
        # NOTE: systems could be created with a list comp except the sanity
        # check "if psu.system" is needed in case a psu got corrupted
        systems = []
        for psu in model.project.systems:
            if psu.system:
                systems.append(psu.system)
        # first check whether obj *is* one of the systems:
        is_a_system = [sys for sys in systems if sys.oid == obj.oid]
        # then check whether obj occurs in any system boms:
        in_system = [sys for sys in systems if obj.oid in get_bom_oids(sys)]
        if is_a_system or in_system:
            # systems exist -> project_index has children, so ...
            sys_idxs = [model.index(row, 0, project_index)
                        for row in range(model.rowCount(project_index))]
            system_idxs = []
            obj_idxs = []
            if is_a_system:
                # orb.log.debug('  - object is a system.')
                # orb.log.debug('    project has {} system(s).'.format(
                                                            # len(systems)))
                # orb.log.debug('    tree has {} system(s).'.format(
                                                            # len(sys_idxs)))
                for idx in sys_idxs:
                    system_node = model.get_node(idx)
                    # orb.log.debug('    + {}'.format(system_node.obj.id))
                    if system_node.obj.oid == obj.oid:
                        system_idxs.append(idx)
                # orb.log.debug('    {} system occurrences found.'.format(
                              # len(system_idxs)))
            if in_system:
                # orb.log.debug('  - object is a component.')
                for sys_idx in sys_idxs:
                    obj_idxs += self.object_indexes_in_assembly(obj, sys_idx)
                # orb.log.debug('    {} component occurrences found.'.format(
                              # len(obj_idxs)))
            return list(set(system_idxs + obj_idxs))
        else:
            # orb.log.info('  - object not found in tree.')
            return []
        return []

    def object_indexes_in_assembly(self, obj, idx):
        """
        Find the source model indexes of all nodes in an assembly that reference
        the specified object and source model index.

        Args:
            obj (Product):  specified object
            idx (QModelIndex):  source model index of the assembly or project
                node
        """
        # NOTE: ignore "TBD" objects
        if getattr(obj, 'oid', '') == 'pgefobjects:TBD':
            return []
        model = self.model().sourceModel()
        assembly_node = model.get_node(idx)
        assembly = assembly_node.obj
        # orb.log.debug('* object_indexes_in_assembly({})'.format(assembly.id))
        if obj.oid == assembly.oid:
            # orb.log.debug('  assembly *is* the object')
            return [idx]
        elif model.hasChildren(idx) and obj.oid in get_bom_oids(assembly):
            # orb.log.debug('  obj in assembly bom -- look for children ...')
            obj_idxs = []
            comp_idxs = [model.index(row, 0, idx)
                         for row in range(model.rowCount(idx))]
            for comp_idx in comp_idxs:
                obj_idxs += self.object_indexes_in_assembly(obj, comp_idx)
            return obj_idxs
        else:
            return []

    def link_indexes_in_tree(self, link):
        """
        Find the source model indexes of all nodes in the system tree that
        reference the specified link (Acu or ProjectSystemUsage) -- this is
        needed for updating the tree in-place when a link object is modified.

        Args:
            link (Acu or ProjectSystemUsage):  specified link object
        """
        # orb.log.debug('* link_indexes_in_tree({})'.format(link.id))
        if not link:
            return []
        model = self.model().sourceModel()
        project_index = model.index(0, 0, QModelIndex())
        # project_node = model.get_node(project_index)
        # orb.log.debug('  for project {}'.format(project_node.obj.oid))
        # orb.log.debug('  (node cname: {})'.format(project_node.cname))
        # ----------------------------------------------------
        # IMPORTANT: fully populate model with child nodes ...
        # ----------------------------------------------------
        model.populate()
        # first check whether link is a PSU:
        is_a_psu = [psu for psu in model.project.systems
                    if psu.oid == link.oid]
        # then check whether link occurs in any system boms:
        systems = [psu.system for psu in model.project.systems]
        in_system = [sys for sys in systems if link in get_assembly(sys)]
        if is_a_psu or in_system:
            # systems exist -> project_index has children, so ...
            child_count = model.rowCount(project_index)
            if child_count == 0:
                # orb.log.debug('  - no child nodes found.')
                return []
            sys_idxs = [model.index(row, 0, project_index)
                        for row in range(child_count)]
            if not sys_idxs:
                # orb.log.debug('  - no child indexes found.')
                return []
            link_idxs = []
            if is_a_psu:
                # orb.log.debug('  - link is a ProjectSystemUsage ...')
                # orb.log.debug('    project has {} system(s).'.format(
                                                            # len(systems)))
                # orb.log.debug('    tree has {} system(s).'.format(
                                                            # len(sys_idxs)))
                for idx in sys_idxs:
                    system_node = model.get_node(idx)
                    if system_node.link.oid == link.oid:
                        # orb.log.debug('    + {}'.format(system_node.link.id))
                        # orb.log.debug('      system: {}'.format(
                                                        # system_node.obj.id))
                        link_idxs.append(idx)
                # orb.log.debug('    {} system occurrences found.'.format(
                              # len(link_idxs)))
            if in_system:
                # orb.log.debug('  - link is an Acu ...')
                for sys_idx in sys_idxs:
                    link_idxs += self.link_indexes_in_assembly(link, sys_idx)
                # orb.log.debug('    {} link occurrences found.'.format(
                              # len(link_idxs)))
            return link_idxs
        else:
            # orb.log.debug('  - link not found in tree.')
            return []
        return []

    def link_indexes_in_assembly(self, link, idx):
        """
        Find the source model indexes of all nodes in an assembly that have the
        specified link as their `link` attribute and the specified source model
        index.

        Args:
            link (Acu):  specified link
            idx (QModelIndex):  index of the assembly or project node
        """
        if link:
            model = self.model().sourceModel()
            assembly_node = model.get_node(idx)
            if assembly_node.link is None:
                return []
            if hasattr(assembly_node.link, 'component'):
                assembly = assembly_node.link.component
            else:
                assembly = assembly_node.link.system
            # orb.log.debug('* link_indexes_in_assembly({})'.format(link.id))
            if link.oid == assembly_node.link.oid:
                # orb.log.debug('  assembly node *is* the link node')
                return [idx]
            elif model.hasChildren(idx) and link in get_assembly(assembly):
                # orb.log.debug('  link in assembly -- looking for acus ...')
                link_idxs = []
                comp_idxs = [model.index(row, 0, idx)
                             for row in range(model.rowCount(idx))]
                for comp_idx in comp_idxs:
                    link_idxs += self.link_indexes_in_assembly(link, comp_idx)
                return link_idxs
            return []
        return []


class MultiDashboard(QWidget):
    """
    Widget to contain multiple dashboards and switch between them.
    """
    def __init__(self, project, parent=None):
        """
        Initialize.

        Args:
            project (Project): the current project
        """
        super().__init__(parent=parent)
        # self.project = project
        self.project = project
        self.dashboards = QStackedWidget()
        self.setContextMenuPolicy(Qt.PreventContextMenu)
        dashboard_panel_layout = QVBoxLayout()
        self.dashboard_title_layout = QHBoxLayout()
        self.dash_title = QLabel()
        # orb.log.debug('           adding title ...')
        self.dashboard_title_layout.addWidget(self.dash_title)

        # --------------------------------------------------------------------
        self.dash_select = QComboBox()
        self.dash_select.setStyleSheet('font-weight: bold; font-size: 14px')
        if not prefs.get('dashboard_names'):
            prefs['dashboard_names'] = ['MEL', 'Mass', 'Data Rates',
                                        'Mechanical', 'Thermal',
                                        'System Resources']
        if not state.get('dashboard_name'):
            state['dashboard_name'] = self.dash_names[0]
        if (state.get('dashboard_name') == 'System Power Modes' and
            (state.get('project', '') not in mode_defz)):
            state['dashboard_name'] = 'MEL'
        for dash_name in self.dash_names:
            self.dash_select.addItem(dash_name, QVariant)
            self.add_dashboard(dash_name)
        dash_name = state.get('dashboard_name', 'MEL')
        state['dashboard_name'] = dash_name
        # self.dash_select.setCurrentText(dash_name)
        self.dash_select.activated.connect(self.set_dashboard)
        # orb.log.debug('           adding dashboard selector ...')
        self.dashboard_title_layout.addWidget(self.dash_select)
        # --------------------------------------------------------------------

        dashboard_panel_layout.addLayout(self.dashboard_title_layout)
        dashboard_panel_layout.addWidget(self.dashboards)
        self.setLayout(dashboard_panel_layout)
        self.setMinimumSize(500, 200)
        current_dash_name = state.get('dashboard_name')
        if current_dash_name in self.dash_names:
            self.set_dashboard(self.dash_names.index(current_dash_name))
        else:
            self.set_dashboard(0)

    @property
    def dash_names(self):
        names = prefs.get('dashboard_names', ['MEL']) + ['System Power Modes']
        if state.get('project') not in mode_defz:
            names.remove('System Power Modes')
        return names

    def add_dashboard(self, dashboard_name):
        # if dashboard_name in self.dash_names:
        # state['dashboard_name'] = dashboard_name
        sys_tree_model = SystemTreeModel(self.project)
        view_model = SystemTreeProxyModel(sys_tree_model)
        dash = SystemDashboard(view_model, parent=self)
        self.dashboards.addWidget(dash)

    def set_dashboard(self, idx):
        # orb.log.debug('* set_dashboard()')
        dash_name = self.dash_names[idx]
        state['dashboard_name'] = dash_name
        self.dashboards.setCurrentIndex(idx)
        dash = self.dashboards.widget(idx)
        # -----------------------------------------------------------------
        n = state.get('sys_tree_expansion', {}).get(state.get('project'))
        if n is not None:
            dash.expandToDepth(n + 1)
            # orb.log.debug(f'[Dashboard] expanded to level {n + 2}')
        else:
            dash.expandToDepth(2)
            # orb.log.debug('[Dashboard] expanded to default level (2)')
        # -----------------------------------------------------------------
        dash.model().sort(0)
        for column in range(1, dash.model().sourceModel().columnCount()):
            dash.resizeColumnToContents(column)
        dash.resizeColumnToContents(0)
        orb.log.debug(f'  - dashboard set to "{dash_name}"')

    # def rebuild_dash_selector(self):
        # orb.log.debug('* rebuild_dash_selector()')
        # if getattr(self, 'dashboard_title_layout', None):
            # orb.log.debug('  - dashboard_title_layout exists ...')
            # orb.log.debug('  - removing old dash selector ...')
            # self.dashboard_title_layout.removeWidget(self.dash_select)
            # self.dash_select.setAttribute(Qt.WA_DeleteOnClose)
            # self.dash_select.close()
            # self.dash_select = None
            # # orb.log.debug('  - creating new dash selector ...')
            # new_dash_select = QComboBox()
            # new_dash_select.setStyleSheet(
                                # 'font-weight: bold; font-size: 14px')
            # for dash_name in self.dash_names:
                # new_dash_select.addItem(dash_name, QVariant)
            # new_dash_select.setCurrentIndex(0)
            # new_dash_select.activated.connect(self.set_dashboard)
            # self.dash_select = new_dash_select
            # self.dashboard_title_layout.addWidget(self.dash_select)


if __name__ == '__main__':
    """
    Cmd line invocation for testing / prototyping
    """
    import argparse, sys
    from PyQt5.QtWidgets import QApplication, QWidget
    from pangalactic.core.serializers import deserialize
    from pangalactic.core.test.utils import create_test_users
    from pangalactic.core.test.utils import create_test_project
    from pangalactic.node.startup    import setup_dirs_and_state
    app = QApplication(sys.argv)
    parser = argparse.ArgumentParser()
    parser.add_argument('--console', dest='console', action="store_true",
                        help='send log msgs to stdout [default: no]')
    options = parser.parse_args()
    app_home = 'junk_home'
    app_home_path = os.path.join(os.getcwd(), app_home)
    if not os.path.exists(app_home_path):
        os.makedirs(app_home_path, mode=0o755)
    home = app_home_path
    print('* starting orb ...')
    orb.start(home=home, debug=True, console=True)
    print('  orb started.')
    setup_dirs_and_state()
    print('* loading test project H2G2 ...')
    test_objs = create_test_users()
    test_objs += create_test_project()
    deserialize(orb, test_objs)
    test_system = orb.get('test:spacecraft0')
    print('* test system created ...')
    proj = test_system.owner
    sys_tree = SystemTreeView(proj)
    window = QWidget()
    layout = QVBoxLayout(window)
    # dash = SystemDashboard(sys_tree.source_model, parent=window)
    dash = MultiDashboard(proj, parent=window)
    layout.addWidget(dash)
    layout.addWidget(sys_tree)
    sys_tree.expandAll()
    window.setGeometry(100, 100, 1200, 800)
    window.show()
    sys.exit(app.exec_())

