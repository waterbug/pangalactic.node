# -*- coding: utf-8 -*-
"""
Dashboards:  a dashboard in Pangalaxian is a dockable widget in the top section
of the main window, in which columns can be added to display the current values
and realtime updates of specified parameters of a system that is being modeled.
"""
from louie import dispatcher

from PyQt5.QtCore    import Qt, QModelIndex, QItemSelectionModel
from PyQt5.QtWidgets import QAction, QDialog, QMessageBox, QTreeView

# pangalactic
from pangalactic.core             import prefs, state
from pangalactic.core.parametrics import de_defz, parm_defz
from pangalactic.core.uberorb     import orb
from pangalactic.node.utils       import extract_mime_data
from pangalactic.node.dialogs     import (CustomizeColsDialog,
                                          DeleteColsDialog,
                                          NewDashboardDialog,
                                          UnitPrefsDialog)


class SystemDashboard(QTreeView):

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
        ## NOTE: "customize columns" is currently deactivated in favor of
        ## drag/drop of parameters / data elements from library to add columns
        # customize_columns_action = QAction('customize columns', dash_header)
        # customize_columns_action.triggered.connect(self.customize_columns)
        # dash_header.addAction(customize_columns_action)
        delete_columns_action = QAction('delete columns', dash_header)
        delete_columns_action.triggered.connect(self.delete_columns)
        dash_header.addAction(delete_columns_action)
        create_dashboard_action = QAction('create new dashboard', dash_header)
        create_dashboard_action.triggered.connect(self.create_dashboard)
        dash_header.addAction(create_dashboard_action)
        set_as_pref_action = QAction('set as preferred dashboard', dash_header)
        set_as_pref_action.triggered.connect(self.set_as_pref_dashboard)
        dash_header.addAction(set_as_pref_action)
        delete_dashboard_action = QAction('delete dashboard', dash_header)
        delete_dashboard_action.triggered.connect(self.delete_dashboard)
        dash_header.addAction(delete_dashboard_action)
        dash_header.setContextMenuPolicy(Qt.ActionsContextMenu)
        dash_header.sectionMoved.connect(self.on_section_moved)
        # "successful_drop" refers to product drops on sys tree (for syncing)
        model.sourceModel().successful_drop.connect(self.on_successful_drop)
        dispatcher.connect(self.dash_node_expand, 'sys node expanded')
        dispatcher.connect(self.dash_node_collapse, 'sys node collapsed')
        dispatcher.connect(self.dash_node_select, 'sys node selected')
        dispatcher.connect(self.dash_node_select, 'diagram go back')
        dispatcher.connect(self.dash_node_select, 'diagram tree index')
        self.expanded.connect(self.dash_node_expanded)
        self.collapsed.connect(self.dash_node_collapsed)
        self.clicked.connect(self.dash_node_selected)
        self.expandToDepth(1)
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
        else:
            # ignore anything else
            event.ignore()

    def set_units(self):
        dlg = UnitPrefsDialog(self)
        dlg.show()

    def show_grid(self):
        self.grid_lines = True
        prefs['dash_grid_lines'] = True
        self.repaint()

    def hide_grid(self):
        self.grid_lines = False
        prefs['dash_grid_lines'] = False
        self.repaint()

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

    def customize_columns(self):
        """
        Dialog displayed in response to 'customize columns' context menu item.
        """
        current_pids = prefs['dashboards'][state['dashboard_name']][:]
        dlg = CustomizeColsDialog(cols=current_pids, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            all_pids = list(parm_defz) + list(de_defz)
            model = self.model().sourceModel()
            cols_to_delete = []
            for pid in current_pids:
                if not dlg.checkboxes[pid].isChecked():
                    cols_to_delete.append(pid)
            if cols_to_delete:
                model.delete_columns(cols=cols_to_delete)
            current_pids = prefs['dashboards'][state['dashboard_name']][:]
            cols_to_insert = []
            for pid in all_pids:
                if dlg.checkboxes[pid].isChecked() and pid not in current_pids:
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
        state['system'] = node.obj.oid
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

