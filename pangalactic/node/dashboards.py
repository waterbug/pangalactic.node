# -*- coding: utf-8 -*-
"""
Dashboards:  a dashboard in Pangalaxian is a dockable widget in the top section
of the main window, in which widgets can be added to display the current values
and realtime updates of specified parameters of a system that is being modeled.
"""
from louie import dispatcher

from PyQt5.QtCore    import Qt, QModelIndex, QItemSelectionModel
from PyQt5.QtWidgets import QAction, QDialog, QMessageBox, QTreeView

# pangalactic
from pangalactic.core         import prefs, state
from pangalactic.core.uberorb import orb
from pangalactic.node.utils   import extract_mime_data
from pangalactic.node.dialogs import (DeleteColsDialog, NewDashboardDialog,
                                      UnitPrefsDialog)


class SystemDashboard(QTreeView):

    def __init__(self, model, parent=None):
        super(SystemDashboard, self).__init__(parent)
        self.setSelectionMode(self.SingleSelection)
        self.setUniformRowHeights(True)
        if prefs.get('dash_no_row_colors'):
            self.setAlternatingRowColors(False)
        else:
            self.setAlternatingRowColors(True)
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
        # self.expandAll()
        self.setStyleSheet('font-weight: normal; '
                           'font-size: 12px; '
                           'QToolTip { font-weight: normal; '
                           'font-size: 12px; border: 2px solid; };')
        dash_header = self.header()
        dash_header.setStyleSheet(
                           'QHeaderView { font-weight: bold; '
                           'font-size: 14px; border: 1px; '
                           'padding-left: 10px; padding-right: 10px; } '
                           'QToolTip { font-weight: normal; '
                           'font-size: 12px; border: 2px solid; };')
        dash_header.setDefaultAlignment(Qt.AlignHCenter)
        # accept drops of parameters on dash to add columns
        self.setAcceptDrops(True)
        # provide a context menu for various actions
        set_units_action = QAction('set preferred units', dash_header)
        set_units_action.triggered.connect(self.set_units)
        dash_header.addAction(set_units_action)
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
        for column in range(model.sourceModel().columnCount(QModelIndex())):
            self.resizeColumnToContents(column)
        # DO NOT use `setMinimumSize()` here -- it breaks the slider that
        # appears when window size is too small to display the full width

    def on_section_moved(self, logical, old, new):
        orb.log.info('[Dashboard] section moved')
        orb.log.info('            logical: {} old: {} new: {}'.format(
                                                        logical, old, new))
        dashboard = prefs['dashboards'][state['dashboard_name']]
        colname = dashboard[old-1]
        del dashboard[old-1]
        dashboard.insert(new-1, colname)
        dispatcher.send(signal='dashboard mod')

    def mimeTypes(self):
        """
        Return MIME Types accepted for drops.
        """
        return ['application/x-pgef-parameter-definition']

    def supportedDropActions(self):
        return Qt.CopyAction

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat('application/x-pgef-parameter-definition'):
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat('application/x-pgef-parameter-definition'):
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
                             'column for "{}" ...')
                # if dropped PD is not in columns, add it
                prefs['dashboards'][dash_name].append(pd_id)
                orb.log.info('            '
                             'sending "dashboard column added" signal ...')
                # this will trigger refresh_tree_and_dashboard() in pangalaxian
                # (tree has to be rebuilt because columns are in model)
                dispatcher.send(signal='dashboard mod')
            else:
                orb.log.info(
                    "[Dashboard] Parameter drop event: ignoring '{}': "
                    "we already got one, it's verra nahss!".format(pd_id))
        else:
            # ignore anything that's not parameter-definition
            event.ignore()

    def set_units(self):
        dlg = UnitPrefsDialog(self)
        dlg.show()

    def delete_columns(self):
        """
        Dialog displayed in response to 'delete columns' context menu item.
        """
        dlg = DeleteColsDialog(parent=self)
        if dlg.exec_() == QDialog.Accepted:
            cols_deleted = False
            pids = prefs['dashboards'][state['dashboard_name']][:]
            for pid in pids:
                if dlg.checkboxes[pid].isChecked():
                    prefs['dashboards'][state['dashboard_name']].remove(pid)
                    cols_deleted = True
            if cols_deleted:
                dispatcher.send(signal='dashboard mod')

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
            dispatcher.send(signal='dashboard mod')

    def set_as_pref_dashboard(self):
        """
        Handler for 'set as preferred dashboard' context menu item.
        """
        dash_name = state['dashboard_name']
        prefs['dashboard_names'].remove(dash_name)
        prefs['dashboard_names'].insert(0, dash_name)
        dispatcher.send(signal='dashboard mod')

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
        for column in range(self.model().columnCount(
                            QModelIndex())):
            self.resizeColumnToContents(column)

    def dash_node_expanded(self, index):
        if not self.model():
            return
        for column in range(self.model().columnCount(
                            QModelIndex())):
            self.resizeColumnToContents(column)
        dispatcher.send(signal='dash node expanded', index=index)

    def dash_node_collapsed(self, index):
        # for column in range(self.model().columnCount(
                            # QModelIndex())):
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
            for column in range(self.model().columnCount(
                                QModelIndex())):
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

