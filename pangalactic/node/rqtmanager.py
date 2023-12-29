# -*- coding: utf-8 -*-
"""
Requirement Manager
"""
import os, sys

from PyQt5.QtWidgets import (QAction, QDialog, QFileDialog, QHBoxLayout,
                             QLabel, QMessageBox, QSizePolicy, QVBoxLayout)

from pangalactic.core             import orb
from pangalactic.core             import prefs, state
from pangalactic.core.access      import get_perms, is_global_admin
from pangalactic.core.names       import (STD_VIEWS, get_attr_ext_name,
                                          get_ext_name_attr, pname_to_header)
from pangalactic.core.utils.datetimes import dtstamp, date2str
from pangalactic.core.utils.reports import write_objects_to_xlsx
from pangalactic.node.buttons     import SizedButton
from pangalactic.node.dialogs     import (NotificationDialog, RqtFieldsDialog,
                                          RqtParmDialog, SelectColsDialog)
from pangalactic.node.filters     import FilterPanel
from pangalactic.node.systemtree  import SystemTreeView
from pangalactic.node.rqtwizard   import RqtWizard
from pangalactic.node.widgets     import ColorLabel
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
        view = prefs.get('rqt_mgr_view') or STD_VIEWS['Requirement']
        self.view = view
        self.sized_cols = {'id': 0, 'name': 150}
        self.project = project
        self.rqts = orb.search_exact(cname='Requirement', owner=project)
        title_txt = f'Requirements for {project.id}'
        self.title = QLabel(title_txt)
        self.title.setStyleSheet('font-weight: bold; font-size: 20px')
        main_layout = QVBoxLayout(self)
        title_layout = QHBoxLayout()
        title_layout.addWidget(self.title)
        self.mode_label = ColorLabel('View Mode', color="green", border=2)
        self.mode_label.setStyleSheet('font-size: 20px')
        title_layout.addWidget(self.mode_label)
        title_layout.addStretch(1)
        main_layout.addLayout(title_layout)
        self.setWindowTitle('Requirements Manager')
        self.select_cols_button = SizedButton("Customize Columns")
        self.select_cols_button.clicked.connect(self.select_cols)
        self.export_tsv_button = SizedButton("Export as tsv")
        self.export_tsv_button.clicked.connect(self.export_tsv)
        self.export_excel_button = SizedButton("Export as Excel")
        self.export_excel_button.clicked.connect(self.export_excel)
        self.export_excel_templ_button = SizedButton("Export Excel Template")
        self.export_excel_templ_button.clicked.connect(self.export_excel_templ)
        self.import_excel_button = SizedButton("Import from Excel")
        self.import_excel_button.clicked.connect(self.import_excel)
        self.hide_tree_button = SizedButton('Hide Allocations',
                                             color="purple")
        self.hide_tree_button.clicked.connect(self.hide_allocation_panel)
        self.show_tree_button = SizedButton('Show Allocations', color="green")
        self.show_tree_button.clicked.connect(self.display_allocation_panel)
        self.enable_allocs_button = SizedButton('Enter Allocation Mode',
                                                color="green")
        self.enable_allocs_button.clicked.connect(self.enable_allocations)
        # "allocations mode" can only be enabled if user has correct role
        # -- has to be a project Admin, LE, or SE, or a global admin
        user = orb.get(state.get('local_user_oid'))
        user_roles = orb.search_exact(cname='RoleAssignment', assigned_to=user,
                                      role_assignment_context=self.project)
        role_names = set([r.name for r in user_roles])
        authorized_roles = set(['Systems Engineer', 'Lead Engineer',
                                'Administrator'])
        if (role_names & authorized_roles) or is_global_admin(user):
            self.enable_allocs_button.setVisible(True)
        else:
            self.enable_allocs_button.setVisible(False)
        self.disable_allocs_button = SizedButton('Exit Allocation Mode',
                                                 color="red")
        self.disable_allocs_button.clicked.connect(self.disable_allocations)
        top_layout = QHBoxLayout()
        top_layout.addWidget(self.select_cols_button)
        top_layout.addWidget(self.export_tsv_button)
        top_layout.addWidget(self.export_excel_button)
        top_layout.addWidget(self.export_excel_templ_button)
        top_layout.addWidget(self.import_excel_button)
        top_layout.addStretch(1)
        top_layout.addWidget(self.enable_allocs_button)
        top_layout.addWidget(self.disable_allocs_button)
        top_layout.addWidget(self.hide_tree_button)
        top_layout.addWidget(self.show_tree_button)
        self.content_layout = QHBoxLayout()
        main_layout.addLayout(top_layout)
        main_layout.addLayout(self.content_layout, stretch=1)
        # NOTE: now using word wrap and PGEF_COL_WIDTHS
        self.fpanel = FilterPanel(self.rqts, view=view,
                                  sized_cols=self.sized_cols, word_wrap=True,
                                  parent=self)
        self.fpanel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.fpanel.proxy_view.clicked.connect(self.on_click_rqt)
        self.setup_context_menu()
        self.fpanel_layout = QVBoxLayout()
        self.fpanel_layout.addWidget(self.fpanel)
        self.content_layout.addLayout(self.fpanel_layout)
        dispatcher.connect(self.on_new_or_mod_rqts, 'remote new or mod rqts')
        dispatcher.connect(self.on_modified_object, 'modified object')
        dispatcher.connect(self.on_deleted_object, 'deleted object')
        dispatcher.connect(self.on_sys_node_clicked, 'sys node clicked')
        # "parameters recomputed" is the ultimate signal resulting from a
        # "received objects" pubsub msg after a "modified object" signal
        # triggers a "save" rpc ... so in a "connected" state, that is when a
        # modified requirement should be updated in the fpanel
        dispatcher.connect(self.on_parmz_recomputed, 'parameters recomputed')
        # TODO:  make project a property; in its setter, enable the checkbox
        # that opens the "allocation panel" (tree)
        self.display_allocation_panel()
        self.disable_allocations()
        self.alloc_node = None
        width = width or 600
        height = height or 500
        self.resize(width, height)

    @property
    def view(self):
        return prefs.get('rqt_mgr_view') or STD_VIEWS['Requirement']

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
        # NOTE: STD_VIEWS[cname] returns a dict, which is ok for this purpose
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

    def export_excel_templ(self):
        """
        [Handler for 'Export Excel Template' button]  Write the requirements to
        a .xlsx file.
        """
        orb.log.debug('* export_excel_template()')
        name = 'Requirements-Template'
        fname = name + '.xlsx'
        state_path = state.get('rqt_excel_last_path') or ''
        suggested_fpath = os.path.join(state_path, fname)
        fpath, filters = QFileDialog.getSaveFileName(
                                    self, 'Write to .xlsx File',
                                    suggested_fpath, '(*.xlsx)')
        if fpath:
            orb.log.debug(f'  - file selected: "{fpath}"')
            state['rqt_excel_last_path'] = os.path.dirname(fpath)
            write_objects_to_xlsx(None, fpath, view=self.view,
                                  cname='Requirement')
            html = '<h3>Success!</h3>'
            msg = 'Requirements Template written to Excel file:'
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
            orb.log.debug('  ... Excel Template cancelled.')
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

    def on_new_or_mod_rqts(self, oids):
        orb.log.debug('* got "remote new or mod rqts" signal ...')
        rqts = orb.get(oids=oids)
        orb.log.debug('  remote new or mod rqts are:')
        for i, rqt in enumerate(rqts):
            if rqt:
                oid = rqt.oid
                orb.log.debug(f'  [{i}] {rqt.id}: {rqt.name}')
                if oid in self.fpanel.oids:
                    orb.log.debug('      + is modified, updating ...')
                    self.fpanel.mod_object(oid)
                else:
                    orb.log.debug('      + is new, adding ...')
                    self.fpanel.add_object(rqt)
                self.fpanel.refresh()
            else:
                orb.log.debug(f'  rqt [{i}] not found.')

    def on_modified_object(self, obj=None, cname=None):
        if obj in self.fpanel.objs:
            self.fpanel.refresh()

    def on_deleted_object(self, oid=None, cname=None):
        orb.log.debug('* received "deleted object" signal.')
        self.fpanel.remove_object(oid)

    def on_parmz_recomputed(self):
        if state.get('new_or_modified_rqts'):
            need_refresh = False
            for rqt_oid in state['new_or_modified_rqts']:
                if rqt_oid in self.fpanel.oids:
                    need_refresh = True
                else:
                    rqt = orb.get(rqt_oid)
                    if rqt and rqt.owner.id == self.project.id:
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
        self.enable_allocs_button.setVisible(False)
        self.show_tree_button.setVisible(True)

    def display_allocation_panel(self):
        if getattr(self, 'tree_layout', None):
            self.tree_layout.removeItem(self.tree_layout)
        self.sys_tree = SystemTreeView(self.project, refdes=True,
                                       rqt_allocs=True)
        self.sys_tree.collapseAll()
        self.sys_tree.expandToDepth(1)
        self.tree_layout = QVBoxLayout()
        self.tree_layout.addWidget(self.sys_tree)
        self.content_layout.addLayout(self.tree_layout, stretch=1)
        self.show_tree_button.setVisible(False)
        self.hide_tree_button.setVisible(True)
        self.enable_allocs_button.setVisible(True)

    def enable_allocations(self, evt):
        """
        Set up the fpanel and tree to enable a requirement or a group of
        requirements to be allocated to an item in the system tree. This can
        only be done by an admin, lead engineer, or systems engineer.
        """
        # turn off "show_allocs" (yellow highlighting of tree nodes)
        source_model = self.sys_tree.proxy_model.sourceModel()
        source_model.show_allocs = False
        self.sys_tree.repaint()
        # make sure all rqts are being displayed ...
        self.fpanel.set_source_model(self.fpanel.create_model(self.rqts))
        # make sure fpanel title is empty and alloc_node is None
        self.fpanel.set_title("", border=0)
        self.alloc_node = None
        self.enable_allocs_button.setVisible(False)
        self.disable_allocs_button.setVisible(True)
        self.hide_tree_button.setVisible(False)
        self.allocs_mode = True
        self.mode_label.set_content('Allocation Mode', color='red', border=2)

    def disable_allocations(self):
        """
        Disable the capability to create new allocations, leaving the
        configuration to display allocations of selected rqts and/or rqts
        allocated to selected nodes.
        """
        self.enable_allocs_button.setVisible(True)
        self.disable_allocs_button.setVisible(False)
        self.hide_tree_button.setVisible(True)
        self.allocs_mode = False
        self.mode_label.set_content('View Mode', color="green", border=2)
        self.sys_tree.repaint()

    def on_sys_node_clicked(self, index=None, obj=None, link=None):
        orb.log.debug('* received "sys node clicked" signal.')
        if self.allocs_mode:
            # turn "show_allocs" off
            source_model = self.sys_tree.proxy_model.sourceModel()
            source_model.show_allocs = False
            orb.log.debug('  in "Allocation Mode" ...')
            NOW = dtstamp()
            user = orb.get(state.get('local_user_oid'))
            allocation = 'None'
            allocated_rqts_info = []
            allocated_rqts = []
            # if in allocation mode, allocate the selected rqts to the selected
            # tree node (or toggle: if allocated, de-allocate)
            rqts = []
            if len(self.fpanel.proxy_view.selectedIndexes()) >= 1:
                rows = set()
                for idx in self.fpanel.proxy_view.selectedIndexes():
                    rows.add(self.fpanel.proxy_model.mapToSource(idx).row())
                orb.log.debug(f'  selected rows: {rows}')
                for row in rows:
                    oid = getattr(
                            self.fpanel.proxy_model.sourceModel().objs[row],
                            'oid', '')
                    rqt = orb.get(oid)
                    if rqt:
                        rqts.append(rqt)
            else:
                # TODO: notify user ...
                orb.log.debug('  no rows selected.')

            if ((not link and not isinstance(obj, orb.classes['Project'])) or
                not rqts):
                orb.log.debug('  no link or project, or no rqts selected.')
                return
            if isinstance(obj, orb.classes['Project']):
                for rqt in rqts:
                    if not rqt.allocated_to is self.project:
                        rqt.allocated_to = self.project
                        rqt.mod_datetime = NOW
                        rqt.modifier = user
                        allocated_rqts.append(rqt)
                        allocated_rqts_info.append(f'{rqt.id}: {rqt.name}')
                allocation = self.project.id + ' project'
            else:
                for rqt in rqts:
                    if not rqt.allocated_to is link:
                        rqt.allocated_to = link
                        rqt.mod_datetime = NOW
                        rqt.modifier = user
                        allocated_rqts.append(rqt)
                        allocated_rqts_info.append(f'{rqt.id}: {rqt.name}')
                if hasattr(link, 'system'):
                    allocation = link.system_role
                elif hasattr(link, 'component'):
                    allocation = link.reference_designator
            # the expandToDepth is needed to make it repaint to show the allocation
            # node as yellow-highlighted
            self.sys_tree.expandToDepth(1)
            self.sys_tree.scrollTo(index)
            if allocated_rqts:
                orb.save(allocated_rqts)
                orb.log.debug('* requirements:')
                for rqt_info in allocated_rqts_info:
                    orb.log.debug(f'  - {rqt_info}')
                orb.log.debug(f'  are now allocated to: {allocation}')
                message = "<h3>Requirements:</h3><ul>"
                for rqt_info in allocated_rqts_info:
                    message += f'<li>{rqt_info}</li>'
                message += "</ul>"
                message += f'  are now allocated to: {allocation}'
                popup = QMessageBox(QMessageBox.Warning,
                            "Requirements Allocated", message,
                            QMessageBox.Ok, self)
                popup.show()
                # "modified objects" signal triggers pgxn save() rpc
                dispatcher.send(signal="modified objects", objs=allocated_rqts)
        else:
            orb.log.debug('  in "View Mode" ...')
            # in view mode, turn "show_allocs" (yellow highlighting) off
            source_model = self.sys_tree.proxy_model.sourceModel()
            source_model.show_allocs = False
            # in view mode, filter rqts to show those allocated to the
            # clicked tree node
            self.fpanel.set_source_model(self.fpanel.create_model(self.rqts))
            # if clicked node *is* self.alloc_node, toggle the view off
            if (isinstance(obj, orb.classes['Project']) and
                self.alloc_node and self.alloc_node is obj):
                orb.log.debug('  alloc node is project')
                self.alloc_node = None
                self.fpanel.set_title("", border=0)
                return
            elif self.alloc_node and self.alloc_node is link:
                orb.log.debug('  alloc node is link')
                self.alloc_node = None
                self.fpanel.set_title("", border=0)
                return
            alloc_rqts = []
            if isinstance(obj, orb.classes['Project']):
                alloc_rqts = obj.allocated_requirements
                self.alloc_node = obj
                orb.log.debug('  setting alloc node to project')
                self.fpanel.set_title("Project Requirements", color="green",
                                      border=1)
            else:
                alloc_rqts = link.allocated_requirements
                self.alloc_node = link
                orb.log.debug('  setting alloc node to link')
                item_id = getattr(link, 'system_role', '') or getattr(link,
                                                    'reference_designator', '')
                self.fpanel.set_title(f"Requirements Allocated to {item_id}",
                                      color="green", border=1)
            rqt_ids = [rqt.id for rqt in alloc_rqts]
            orb.log.debug(f'  allocated rqts: {rqt_ids}')
            self.fpanel.set_source_model(self.fpanel.create_model(alloc_rqts))
            self.sys_tree.repaint()

    def set_rqt(self, r):
        self.sys_tree.rqt = r

    def on_click_rqt(self, index):
        # turn "show_allocs" on
        tree_source_model = self.sys_tree.proxy_model.sourceModel()
        tree_source_model.show_allocs = True
        orb.log.debug('* RequirementManager: on_click_rqt() ...')
        # if len(self.fpanel.proxy_view.selectedIndexes()) >= 1:
            # i = self.fpanel.proxy_model.mapToSource(
                # self.fpanel.proxy_view.selectedIndexes()[0]).row()
            # orb.log.debug('  selected row: {}'.format(i))
        idx = self.fpanel.proxy_model.mapToSource(index)
        oid = getattr(self.fpanel.proxy_model.sourceModel().objs[idx.row()],
                      'oid', '')
        rqt = orb.get(oid)
        if rqt:
            self.set_rqt(rqt)
            # if allocated, send signal to ensure that node of
            # the tree is made visible
            item = rqt.allocated_to
            if item:
                dispatcher.send(signal='show allocated_to', item=item)
        else:
            orb.log.debug('  rqt with oid "{}" not found.'.format(oid))
        self.sys_tree.repaint()

    def closeEvent(self, event):
        if self.fpanel.col_moved_view:
            # ensure that final column moves are saved ...
            prefs['rqt_mgr_view'] = self.fpanel.col_moved_view[:]

