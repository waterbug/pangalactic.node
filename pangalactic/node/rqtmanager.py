# -*- coding: utf-8 -*-
"""
Requirement Manager
"""
import os, sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QAction, QDialog, QDialogButtonBox, QFileDialog,
                             QHBoxLayout, QLabel, QMessageBox, QSizePolicy,
                             QVBoxLayout)

from pangalactic.core             import prefs, state
from pangalactic.core.access      import get_perms
from pangalactic.core.meta        import MAIN_VIEWS
from pangalactic.core.names       import (get_attr_ext_name, get_ext_name_attr,
                                          pname_to_header, STD_VIEWS)
from pangalactic.core.uberorb     import orb
from pangalactic.core.utils.datetimes import dtstamp, date2str
from pangalactic.core.utils.reports import write_objects_to_xlsx
from pangalactic.node.buttons     import SizedButton
from pangalactic.node.dialogs     import (NotificationDialog, RqtFieldsDialog,
                                          RqtParmDialog, SelectColsDialog)
from pangalactic.node.filters     import FilterPanel
from pangalactic.node.systemtree  import SystemTreeView
from pangalactic.node.rqtwizard   import RqtWizard
from pangalactic.node.wizards     import DataImportWizard

# Louie
from louie import dispatcher


class RequirementManager(QDialog):
    """
    Manager of Requirements. :)

    Note that the actions in the FilterPanel are handled there, sending signals
    to invoke the RqtWizard for editing a requirement, etc.

    Keyword Args:
        project (Project):  sets a project context
        sized_cols (dict):  mapping of col names to widths
    """
    def __init__(self, project=None, width=None, height=None, parent=None):
        super().__init__(parent=parent)
        view = prefs.get('rqt_mgr_view') or MAIN_VIEWS['Requirement']
        self.view = view
        self.sized_cols = {'id': 0, 'name': 150}
        self.project = project
        self.rqts = orb.search_exact(cname='Requirement', owner=project)
        title_txt = 'Project Requirements for {}'.format(project.id)
        self.title = QLabel(title_txt)
        self.title.setStyleSheet('font-weight: bold; font-size: 20px')
        main_layout = QVBoxLayout(self)
        # self.setLayout(main_layout)
        # main_layout = self.layout()
        main_layout.addWidget(self.title)
        self.setWindowTitle('Requirements Manager')
        self.select_cols_button = SizedButton("Customize Columns")
        self.select_cols_button.clicked.connect(self.select_cols)
        self.export_tsv_button = SizedButton("Export as tsv")
        self.export_tsv_button.clicked.connect(self.export_tsv)
        self.export_excel_button = SizedButton("Export as Excel")
        self.export_excel_button.clicked.connect(self.export_excel)
        self.import_excel_button = SizedButton("Import from Excel")
        self.import_excel_button.clicked.connect(self.import_excel)
        self.hide_tree_button = SizedButton('Hide Allocations',
                                             color="purple")
        self.hide_tree_button.clicked.connect(self.hide_allocation_panel)
        self.show_tree_button = SizedButton('Show Allocations', color="green")
        self.show_tree_button.clicked.connect(self.display_allocation_panel)
        top_layout = QHBoxLayout()
        top_layout.addWidget(self.select_cols_button)
        top_layout.addWidget(self.export_tsv_button)
        top_layout.addWidget(self.export_excel_button)
        top_layout.addWidget(self.import_excel_button)
        top_layout.addStretch(1)
        top_layout.addWidget(self.hide_tree_button)
        top_layout.addWidget(self.show_tree_button)
        self.content_layout = QHBoxLayout()
        main_layout.addLayout(top_layout)
        main_layout.addLayout(self.content_layout, stretch=1)
        self.bbox = QDialogButtonBox(
            QDialogButtonBox.Close, Qt.Horizontal, self)
        main_layout.addWidget(self.bbox)
        self.bbox.rejected.connect(self.reject)
        # NOTE: now using word wrap and PGEF_COL_WIDTHS
        self.fpanel = FilterPanel(self.rqts, view=view, cname='Requirement',
                                  sized_cols=self.sized_cols, word_wrap=True,
                                  parent=self)
        self.fpanel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.fpanel.proxy_view.clicked.connect(self.on_select_rqt)
        self.setup_context_menu()
        self.fpanel_layout = QVBoxLayout()
        self.fpanel_layout.addWidget(self.fpanel)
        self.content_layout.addLayout(self.fpanel_layout)
        dispatcher.connect(self.on_modified_object, 'modified object')
        # "parameters recomputed" is the ultimate signal resulting from a
        # "received objects" pubsub msg after a "modified object" signal
        # triggers a "save" rpc ... so in a "connected" state, that is when a
        # modified requirement should be updated in the fpanel
        dispatcher.connect(self.on_parmz_recomputed, 'parameters recomputed')
        # TODO:  make project a property; in its setter, enable the checkbox
        # that opens the "allocation panel" (tree)
        self.display_allocation_panel()
        width = width or 600
        height = height or 500
        self.resize(width, height)

    @property
    def view(self):
        return prefs.get('rqt_mgr_view') or []

    @view.setter
    def view(self, v):
        prefs['rqt_mgr_view'] = v

    def setup_context_menu(self):
        txt = 'Edit parameters of this requirement'
        self.rqt_parms_action = QAction(txt, self)
        self.rqt_parms_action.triggered.connect(self.edit_rqt_parms)
        txt = 'Edit selected fields of this requirement'
        self.rqt_fields_action = QAction(txt, self)
        self.rqt_fields_action.triggered.connect(self.edit_rqt_fields)
        txt = 'Edit this requirement in the wizard'
        self.rqtwizard_action = QAction(txt, self)
        self.rqtwizard_action.triggered.connect(self.edit_in_rqt_wiz)
        txt = 'Delete this requirement'
        self.rqt_delete_action = QAction(txt, self)
        self.rqt_delete_action.triggered.connect(self.delete_rqt)
        self.fpanel.proxy_view.addAction(self.rqt_parms_action)
        self.fpanel.proxy_view.addAction(self.rqt_fields_action)
        self.fpanel.proxy_view.addAction(self.rqtwizard_action)
        self.fpanel.proxy_view.addAction(self.rqt_delete_action)

    def select_cols(self):
        """
        [Handler for 'Customize Columns' button]  Display the SelectColsDialog.
        """
        orb.log.debug('* select_cols() ...')
        std_view = STD_VIEWS['Requirement']
        if self.fpanel.col_moved_view:
            cur_view = self.fpanel.col_moved_view[:]
            self.fpanel.col_moved_view = []
            # orb.log.debug(f'  current view (columns moved): {cur_view}')
        elif self.fpanel.custom_view:
            cur_view = self.fpanel.custom_view[:]
            self.fpanel.custom_view[:] = []
        else:
            cur_view = self.fpanel.proxy_model.view[:]
            # orb.log.debug(f'  current view (self.view): {cur_view}')
        all_cols = [get_attr_ext_name('Requirement', a) for a in std_view]
        cur_cols = [get_attr_ext_name('Requirement', a) for a in cur_view]
        dlg = SelectColsDialog(all_cols, cur_cols, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            # rebuild custom view from the selected columns
            new_cols = []
            # add any columns from cur_view first
            for col in cur_cols:
                if col in dlg.checkboxes and dlg.checkboxes[col].isChecked():
                    new_cols.append(col)
                    all_cols.remove(col)
            # then append any newly selected columns
            for col in all_cols:
                if dlg.checkboxes[col].isChecked():
                    new_cols.append(col)
            # orb.log.debug(f'  new columns: {new_cols}')
            v = [get_ext_name_attr('Requirement', c) for c in new_cols]
            # orb.log.debug(f'  new view: {v}')
            self.view = v[:]
            self.fpanel.custom_view = v[:]
            self.fpanel.proxy_model.view = v[:]
            self.fpanel.view = v[:]
            self.fpanel.refresh()

    def export_tsv(self):
        """
        [Handler for 'Export as tsv' button]  Write the requirements to a
        tab-separated-values file.
        """
        orb.log.debug('* export_tsv()')
        dtstr = date2str(dtstamp())
        name = '-' + 'Requirements' + '-'
        fname = self.project.id + name + dtstr + '.tsv'
        state_path = state.get('rqt_tsv_last_path') or ''
        suggested_fpath = os.path.join(state_path, fname)
        fpath, filters = QFileDialog.getSaveFileName(
                                    self, 'Write to tsv File',
                                    suggested_fpath, '(*.tsv)')
        if fpath:
            orb.log.debug(f'  - file selected: "{fpath}"')
            fpath = str(fpath)   # extra-cautious :)
            f = open(fpath, 'w')
            state['rqt_tsv_last_path'] = os.path.dirname(fpath)
            orb.log.debug(f'  - cols: "{self.view}"')
            data = []
            headers = '\t'.join([pname_to_header(a, 'Requirement')
                                 for a in self.view])
            data.append(headers)
            for rqt in self.rqts:
                d = orb.obj_view_to_dict(rqt, self.view)
                data.append('\t'.join([d.get(a) or '' for a in self.view]))
            output = '\n'.join(data)
            f.write(output)
            f.close()
            html = '<h3>Success!</h3>'
            msg = 'Requirements exported to file:'
            html += f'<p><b><font color="green">{msg}</font></b><br>'
            html += f'<b><font color="blue">{fpath}</font></b></p>'
            self.w = NotificationDialog(html, news=False, parent=self)
            self.w.show()
        else:
            orb.log.debug('  ... export to tsv cancelled.')
            return

    def export_excel(self):
        """
        [Handler for 'Export as Excel' button]  Write the requirements to
        a .xlsx file.
        """
        orb.log.debug('* export_excel()')
        dtstr = date2str(dtstamp())
        name = '-Requirements-'
        fname = self.project.id + name + dtstr + '.xlsx'
        state_path = state.get('rqt_excel_last_path') or ''
        suggested_fpath = os.path.join(state_path, fname)
        fpath, filters = QFileDialog.getSaveFileName(
                                    self, 'Write to .xlsx File',
                                    suggested_fpath, '(*.xlsx)')
        if fpath:
            orb.log.debug(f'  - file selected: "{fpath}"')
            state['rqt_excel_last_path'] = os.path.dirname(fpath)
            write_objects_to_xlsx(self.rqts, fpath, view=self.view)
            html = '<h3>Success!</h3>'
            msg = 'Requirements exported to Excel file:'
            html += f'<p><b><font color="green">{msg}</font></b><br>'
            html += f'<b><font color="blue">{fpath}</font></b></p>'
            self.w = NotificationDialog(html, news=False, parent=self)
            self.w.show()
            # try to start Excel with file if on Win or Mac ...
            if sys.platform == 'win32':
                try:
                    os.system(f'start excel.exe "{fpath}"')
                except:
                    orb.log.debug('  unable to start Excel')
            elif sys.platform == 'darwin':
                try:
                    os.system(f'open -a "Microsoft Excel.app" "{fpath}"')
                except:
                    orb.log.debug('  unable to start Excel')
        else:
            orb.log.debug('  ... export to Excel cancelled.')
            return

    def import_excel(self):
        """
        [Handler for 'Import from Excel' button]  Read requirements from
        a .xlsx file.
        """
        orb.log.debug('* import_excel()')
        start_path = state.get('rqts_file_path') or state.get('last_path')
        start_path = start_path or orb.home
        fpath, _ = QFileDialog.getOpenFileName(
                                    self, 'Open File', start_path,
                                    "Excel Files (*.xlsx | *.xls)")
        if fpath:
            if not (fpath.endswith('.xls') or fpath.endswith('.xlsx')):
                message = "File '%s' is not an Excel file." % fpath
                popup = QMessageBox(QMessageBox.Warning,
                            "Wrong file type", message,
                            QMessageBox.Ok, self)
                popup.show()
                return
            state['rqts_file_path'] = os.path.dirname(fpath)
            wizard = DataImportWizard(
                            object_type='Requirement',
                            file_path=fpath,
                            height=self.geometry().height(),
                            width=self.geometry().width(),
                            parent=self)
            wizard.exec_()
            orb.log.debug('* import_rqts_from_excel: dialog completed.')
            dispatcher.send('rqts imported from excel')
        else:
            return

    def on_modified_object(self, obj=None, cname=None):
        if obj in self.fpanel.objs:
            self.fpanel.refresh()

    def on_parmz_recomputed(self):
        if state.get('new_or_modified_rqts'):
            need_refresh = False
            for rqt_oid in state['new_or_modified_rqts']:
                rqt = orb.get(rqt_oid)
                if rqt in self.fpanel.objs:
                    need_refresh = True
                elif rqt.owner.id == self.project.id:
                    need_refresh = True
            if need_refresh:
                self.fpanel.refresh()

    def edit_in_rqt_wiz(self):
        orb.log.debug('* edit_in_rqt_wiz()')
        rqt = None
        if len(self.fpanel.proxy_view.selectedIndexes()) >= 1:
            i = self.fpanel.proxy_model.mapToSource(
                self.fpanel.proxy_view.selectedIndexes()[0]).row()
            # orb.log.debug('  at selected row: {}'.format(i))
            oid = getattr(self.fpanel.proxy_model.sourceModel().objs[i], 'oid', '')
            if oid:
                rqt = orb.get(oid)
        if rqt:
            if 'modify' in get_perms(rqt):
                is_perf = (rqt.rqt_type == 'performance')
                wizard = RqtWizard(parent=self, rqt=rqt, performance=is_perf)
                if wizard.exec_() == QDialog.Accepted:
                    orb.log.info('* rqt wizard completed.')
                else:
                    orb.log.info('* rqt wizard cancelled...')
            else:
                message = "Not Authorized"
                popup = QMessageBox(QMessageBox.Warning, 'Not Authorized',
                                    message, QMessageBox.Ok, self)
                popup.show()

    def edit_rqt_parms(self):
        orb.log.debug('* edit_rqt_parms()')
        rqt = None
        if len(self.fpanel.proxy_view.selectedIndexes()) >= 1:
            i = self.fpanel.proxy_model.mapToSource(
                self.fpanel.proxy_view.selectedIndexes()[0]).row()
            orb.log.debug('  at selected row: {}'.format(i))
            oid = getattr(self.fpanel.proxy_model.sourceModel().objs[i],
                          'oid', '')
            if oid:
                rqt = orb.get(oid)
        if rqt:
            if not rqt.rqt_type == 'performance':
                message = "Not a performance requirement -- no parameters."
                popup = QMessageBox(QMessageBox.Warning, 'No Parameter',
                                    message, QMessageBox.Ok, self)
                popup.show()
            elif 'modify' in get_perms(rqt):
                parm = None
                if rqt.rqt_constraint_type == 'maximum':
                    parm = 'rqt_maximum_value'
                elif rqt.rqt_constraint_type == 'minimum':
                    parm = 'rqt_minimum_value'
                elif rqt.rqt_constraint_type == 'single_value':
                    parm = 'rqt_target_value'
                if parm:
                    dlg = RqtParmDialog(rqt, parm, parent=self)
                    dlg.rqt_parm_mod.connect(self.on_rqt_parm_mod)
                    if dlg.exec_() == QDialog.Accepted:
                        orb.log.info('* rqt parm edited.')
                        dispatcher.send('modified object', obj=rqt)
                        dlg.close()
                    else:
                        orb.log.info('* rqt parm editing cancelled.')
                        dlg.close()
                else:
                    message = "No editable parameter found."
                    popup = QMessageBox(QMessageBox.Warning, 'No Parameter',
                                        message, QMessageBox.Ok, self)
                    popup.show()
            else:
                message = "Not Authorized"
                popup = QMessageBox(QMessageBox.Warning, 'Not Authorized',
                                    message, QMessageBox.Ok, self)
                popup.show()
        else:
            message = "No requirement found."
            popup = QMessageBox(QMessageBox.Warning, 'No Requirement',
                                message, QMessageBox.Ok, self)
            popup.show()

    def on_rqt_parm_mod(self, oid):
        if not state.get('connected'):
            self.fpanel.mod_object(oid)

    def edit_rqt_fields(self):
        orb.log.debug('* edit_rqt_fields()')
        rqt = None
        if len(self.fpanel.proxy_view.selectedIndexes()) >= 1:
            i = self.fpanel.proxy_model.mapToSource(
                self.fpanel.proxy_view.selectedIndexes()[0]).row()
            # orb.log.debug('  at selected row: {}'.format(i))
            oid = getattr(self.fpanel.proxy_model.sourceModel().objs[i],
                          'oid', '')
            if oid:
                rqt = orb.get(oid)
        if rqt:
            if 'modify' in get_perms(rqt):
                dlg = RqtFieldsDialog(rqt, self.view, parent=self)
                if dlg.exec_() == QDialog.Accepted:
                    orb.log.info('* rqt fields edited.')
                    dlg.close()
                else:
                    orb.log.info('* rqt fields editing cancelled.')
                    dlg.close()
            else:
                message = "Not Authorized"
                popup = QMessageBox(QMessageBox.Warning, 'Not Authorized',
                                    message, QMessageBox.Ok, self)
                popup.show()

    def delete_rqt(self):
        orb.log.debug('* delete_rqt()')
        rqt = None
        if len(self.fpanel.proxy_view.selectedIndexes()) >= 1:
            i = self.fpanel.proxy_model.mapToSource(
                self.fpanel.proxy_view.selectedIndexes()[0]).row()
            orb.log.debug('  at selected row: {}'.format(i))
            oid = getattr(self.fpanel.proxy_model.sourceModel().objs[i],
                          'oid', '')
            if oid:
                rqt = orb.get(oid)
        if rqt:
            if 'delete' not in get_perms(rqt):
                message = "Not Authorized"
                popup = QMessageBox(QMessageBox.Warning, 'Not Authorized',
                                    message, QMessageBox.Ok, self)
                popup.show()
                return
            rqt_oid = rqt.oid
            # delete any related Relation and ParameterRelation objects
            rel = rqt.computable_form
            if rel:
                # pr_oid = rqt_wizard_state.get('pr_oid')
                # pr = orb.get(pr_oid)
                prs = rel.correlates_parameters
                if prs:
                    pr_oid = prs[0].oid
                    orb.delete(prs)
                    dispatcher.send(signal='deleted object',
                                    oid=pr_oid,
                                    cname='ParameterRelation')
                rel_oid = rel.oid
                orb.delete([rel])
                dispatcher.send(signal='deleted object',
                                oid=rel_oid, cname='Relation')
            # remove the rqt object from the filter panel
            self.fpanel.remove_object(rqt_oid)
            # delete the Requirement object
            orb.delete([rqt])
            dispatcher.send(signal='deleted object', oid=rqt_oid,
                            cname='Requirement')
            orb.delete([rqt])
            orb.log.info('* requirement deleted.')

    def hide_allocation_panel(self, evt):
        self.content_layout.removeItem(self.tree_layout)
        self.sys_tree.setVisible(False)
        self.content_layout.setStretchFactor(self.fpanel_layout, 1)
        self.hide_tree_button.setVisible(False)
        self.show_tree_button.setVisible(True)

    def display_allocation_panel(self):
        if getattr(self, 'tree_layout', None):
            self.tree_layout.removeItem(self.tree_layout)
        self.sys_tree = SystemTreeView(self.project, refdes=True,
                                       show_allocs=True)
        self.sys_tree.collapseAll()
        self.sys_tree.expandToDepth(1)
        self.sys_tree.clicked.connect(self.on_select_node)
        self.tree_layout = QVBoxLayout()
        self.tree_layout.addWidget(self.sys_tree)
        self.content_layout.addLayout(self.tree_layout, stretch=1)
        self.show_tree_button.setVisible(False)
        self.hide_tree_button.setVisible(True)

    def on_select_node(self, index):
        # TODO:  filter requirements by selected PSU/Acu
        # TODO:  enable allocation/deallocation as in wizard if user has
        # edit permission for selected rqt. (in which case there should appear
        # a checkbox for "enable allocation/deallocation" above the tree;
        # otherwise, filtering behavior (as above) is in effect.
        pass

    def set_rqt(self, r):
        self.sys_tree.rqt = r

    def on_select_rqt(self):
        # orb.log.debug('* RequirementManager: on_select_rqt() ...')
        if len(self.fpanel.proxy_view.selectedIndexes()) >= 1:
            i = self.fpanel.proxy_model.mapToSource(
                self.fpanel.proxy_view.selectedIndexes()[0]).row()
            # orb.log.debug('  selected row: {}'.format(i))
            oid = getattr(self.fpanel.proxy_model.sourceModel().objs[i],
                          'oid', '')
            rqt = orb.get(oid)
            if rqt:
                self.set_rqt(rqt)
                # if allocated to an acu, send signal to ensure that node of
                # the tree is made visible -- not necessary if allocated to a
                # "system", since tree will be expanded to at least 1 level
                acu = rqt.allocated_to
                if acu:
                    dispatcher.send(signal='show alloc acu', acu=acu)
            else:
                orb.log.debug('  rqt with oid "{}" not found.'.format(oid))

    def closeEvent(self, event):
        if self.fpanel.col_moved_view:
            # ensure that final column moves are saved ...
            prefs['rqt_mgr_view'] = self.fpanel.col_moved_view[:]

