# -*- coding: utf-8 -*-
"""
Dashboards:  a dashboard in Pangalaxian is a dockable widget in the top section
of the main window, in which columns can be added to display the current values
and realtime updates of specified parameters of a system that is being modeled.
"""
import os
from louie import dispatcher

from PyQt5.QtCore    import pyqtSignal, Qt, QModelIndex, QItemSelectionModel
from PyQt5.QtWidgets import (QAction, QDialog, QFileDialog, QMessageBox,
                             QTreeView)

# pangalactic
from pangalactic.core                 import orb, prefs, state
from pangalactic.core.names           import get_link_name, get_link_object
from pangalactic.core.parametrics     import (get_usage_mode_val_as_str,
                                              mode_defz, parm_defz)
from pangalactic.core.utils.datetimes import dtstamp, date2str
from pangalactic.core.utils.reports   import (write_data_to_tsv,
                                              write_mel_to_tsv)
from pangalactic.node.utils           import extract_mime_data
from pangalactic.node.dialogs         import (CustomizeColsDialog,
                                              DeleteColsDialog,
                                              NewDashboardDialog,
                                              NotificationDialog,
                                              UnitPrefsDialog)


class SystemDashboard(QTreeView):

    units_set = pyqtSignal()

    def __init__(self, model, row_colors=True, grid_lines=False, parent=None):
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
        self.setModel(model)
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
        # self.expandAll()
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
        # dash_name = state.get('dashboard_name')
        dash_name = 'MEL'
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
        # model.sourceModel().successful_drop.connect(self.on_successful_drop)
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
        for column in range(model.sourceModel().columnCount()):
            self.resizeColumnToContents(column)
        # DO NOT use `setMinimumSize()` here -- it breaks the slider that
        # appears when window size is too small to display the full width

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
            if not dash_name in prefs['dashboard_names']:
                prefs['dashboard_names'].append(dash_name)
            if pd_id not in prefs['dashboards'][dash_name]:
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
                model = self.model().sourceModel()
                model.delete_columns(cols=cols_to_delete)
                indexes = [pids.index(pid) for pid in cols_to_delete]
                if 0 in indexes:
                    dispatcher.send(signal='refresh tree and dash')
                else:
                    for column in range(model.columnCount()):
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
            model = self.model().sourceModel()
            cols_to_delete = []
            # delete any prescriptive pids that are not checked
            for pid in current_pids:
                if (pid in prescriptive_pids
                    and not dlg.checkboxes[pid].isChecked()):
                    cols_to_delete.append(pid)
            if cols_to_delete:
                model.delete_columns(cols=cols_to_delete)
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
                    model.insert_column(pid)
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
        model = proxy_model.sourceModel()
        proj_id = model.project.id
        proj_oid = model.project.oid
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
            if dash_name == 'System Power Modes':
                if mode_defz.get(proj_oid):
                    data = []
                    sys_dict = mode_defz[model.project.oid]['systems']
                    comp_dict = mode_defz[model.project.oid]['components']
                    for link_oid in sys_dict:
                        link = orb.get(link_oid)
                        name = get_link_name(link)
                        obj = get_link_object(link)
                        row_data = [name]
                        row_data += [get_usage_mode_val_as_str(
                                     proj_oid, link_oid, obj.oid, col)
                                     for col in data_cols]
                        data.append(dict(zip(proxy_model.cols, row_data)))
                        if link_oid in comp_dict:
                            for clink_oid in comp_dict[link_oid]:
                                clink = orb.get(clink_oid)
                                cname = get_link_name(clink)
                                comp = get_link_object(clink)
                                crow_data = ['    ' + cname]
                                crow_data += [get_usage_mode_val_as_str(
                                         proj_oid, clink_oid, comp.oid, col)
                                         for col in data_cols]
                                data.append(dict(zip(proxy_model.cols,
                                                     crow_data)))
                    write_data_to_tsv(data, file_path=fpath)
                else:
                    # TODO: pop-up notification to this effect ...
                    orb.log.debug('  ... no modes defined for this project.')
                    return
            else:
                write_mel_to_tsv(model.project, schema=data_cols,
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
        model = proxy_model.sourceModel()
        proj_id = model.project.id
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
            write_mel_to_tsv(model.project, schema=data_cols, pref_units=True,
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
        for column in range(self.model().columnCount()):
            self.resizeColumnToContents(column)

    def dash_node_expanded(self, index):
        if not self.model():
            return
        for column in range(self.model().columnCount()):
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

    def dash_node_expand(self, index=None):
        if not self.model():
            return
        if index and not self.isExpanded(index):
            self.expand(index)
            for column in range(self.model().columnCount()):
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


# NOTE: this is pretty ugly ... need better smoke testing
# if __name__ == '__main__':
    # import sys
    # from PyQt5.QtWidgets import QApplication
    # from pangalactic.test.utils4test import create_test_users
    # from pangalactic.test.utils4test import create_test_project
    # """
    # Cmd line invocation for testing / prototyping
    # """
    # app = QApplication(sys.argv)
    # # ***************************************
    # # Test using test data
    # # ***************************************
    # if len(sys.argv) < 2:
        # print("*** you must provide a home directory path ***")
        # sys.exit()
    # orb.start(home=sys.argv[1])
    # print('* orb starting ...')
    # test_system = orb.get('hog')
    # if not test_system:
        # # test objects have not been loaded yet; load them
        # print('* loading test project H2G2 ...')
        # test_objs = create_test_users()
        # test_objs += create_test_project()
        # deserialize(orb, test_objs)
        # test_system = orb.get('hog')
    # print('* test system created ...')
    # window = SystemDashboard(test_system)
    # window.setGeometry(100, 100, 750, 400)
    # window.show()
    # sys.exit(app.exec_())

