# -*- coding: utf-8 -*-
"""
Requirement Manager
"""
import os, sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog,
                             QHBoxLayout, QLabel, QMessageBox, QSizePolicy,
                             QVBoxLayout)

from pangalactic.core             import prefs, state
from pangalactic.core.access      import get_perms
from pangalactic.core.meta        import MAIN_VIEWS, STANDARD_VIEWS
from pangalactic.core.uberorb     import orb
from pangalactic.core.utils.datetimes import dtstamp, date2str
from pangalactic.core.utils.reports import write_objects_to_xlsx
from pangalactic.node.buttons     import SizedButton
from pangalactic.node.dialogs     import (NotificationDialog, ReqFieldsDialog,
                                          ReqParmDialog, SelectColsDialog)
from pangalactic.node.filters     import FilterPanel
from pangalactic.node.systemtree  import SystemTreeView
from pangalactic.node.reqwizards  import ReqWizard

# Louie
from louie import dispatcher


class RequirementManager(QDialog):
    """
    Manager of Requirements. :)

    Note that the actions in the FilterPanel are handled there, sending signals
    to invoke the ReqWizard for editing a requirement, etc.

    Keyword Args:
        project (Project):  sets a project context
        sized_cols (dict):  mapping of col names to widths
    """
    def __init__(self, project=None, width=None, height=None, view=None,
                 req=None, parent=None):
        super().__init__(parent=parent)
        default_view = prefs.get('req_mgr_view')
        default_view = default_view or MAIN_VIEWS['Requirement']
        self.view = view or default_view
        prefs['req_mgr_view'] = self.view
        sized_cols = {'id': 0, 'name': 150}
        self.req = req
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
        self.hide_tree_button = SizedButton('Hide Allocations',
                                             color="purple")
        self.hide_tree_button.clicked.connect(self.hide_allocation_panel)
        self.show_tree_button = SizedButton('Show Allocations', color="green")
        self.show_tree_button.clicked.connect(self.display_allocation_panel)
        top_layout = QHBoxLayout()
        top_layout.addWidget(self.select_cols_button)
        top_layout.addWidget(self.export_tsv_button)
        top_layout.addWidget(self.export_excel_button)
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
        self.fpanel = FilterPanel(self.rqts, view=self.view,
                                  sized_cols=sized_cols, word_wrap=True,
                                  parent=self)
        self.fpanel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.fpanel.proxy_view.clicked.connect(self.on_select_req)
        self.fpanel.reqwizard_action.triggered.connect(self.edit_requirement)
        self.fpanel.req_parms_action.triggered.connect(self.edit_req_parms)
        self.fpanel.req_fields_action.triggered.connect(self.edit_req_fields)
        self.fpanel.req_delete_action.triggered.connect(self.delete_req)
        self.fpanel_layout = QVBoxLayout()
        self.fpanel_layout.addWidget(self.fpanel)
        self.content_layout.addLayout(self.fpanel_layout)
        dispatcher.connect(self.on_modified_object, 'modified object')
        # TODO:  make project a property; in its setter, enable the checkbox
        # that opens the "allocation panel" (tree)
        self.display_allocation_panel()
        width = width or 600
        height = height or 500
        self.resize(width, height)

    @property
    def req(self):
        return self._req

    @req.setter
    def req(self, r):
        self._req = r

    def select_cols(self):
        """
        [Handler for 'Customize Columns' button]  Display the SelectColsDialog.
        """
        orb.log.debug('* select_cols() ...')
        std_view = STANDARD_VIEWS['Requirement']
        all_cols = std_view[:]
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
            prefs['req_mgr_view'] = new_view[:]
            self.view = new_view[:]
            orb.log.debug('  self.view: {}'.format(str(self.view)))
            self.fpanel.set_view(self.view)
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
        state_path = state.get('req_tsv_last_path') or ''
        suggested_fpath = os.path.join(state_path, fname)
        fpath, filters = QFileDialog.getSaveFileName(
                                    self, 'Write to tsv File',
                                    suggested_fpath, '(*.tsv)')
        if fpath:
            orb.log.debug(f'  - file selected: "{fpath}"')
            fpath = str(fpath)   # extra-cautious :)
            f = open(fpath, 'w')
            state['req_tsv_last_path'] = os.path.dirname(fpath)
            orb.log.debug(f'  - cols: "{self.view}"')
            data = ''
            for rqt in self.rqts:
                data = '\n'.join('\t'.join(str(getattr(rqt, a))
                                           for a in self.view)
                                 for rqt in self.rqts)
            f.write(data)
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
        state_path = state.get('req_excel_last_path') or ''
        suggested_fpath = os.path.join(state_path, fname)
        fpath, filters = QFileDialog.getSaveFileName(
                                    self, 'Write to .xlsx File',
                                    suggested_fpath, '(*.xlsx)')
        if fpath:
            orb.log.debug(f'  - file selected: "{fpath}"')
            state['req_excel_last_path'] = os.path.dirname(fpath)
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

    def on_modified_object(self, obj=None, cname=None):
        if obj in self.fpanel.objs:
            self.fpanel.refresh()

    def edit_requirement(self):
        orb.log.debug('* edit_requirement()')
        req = None
        if len(self.fpanel.proxy_view.selectedIndexes()) >= 1:
            i = self.fpanel.proxy_model.mapToSource(
                self.fpanel.proxy_view.selectedIndexes()[0]).row()
            # orb.log.debug('  at selected row: {}'.format(i))
            oid = getattr(self.fpanel.proxy_model.sourceModel().objs[i], 'oid', '')
            if oid:
                req = orb.get(oid)
        if req:
            if 'modify' in get_perms(req):
                is_perf = (req.req_type == 'performance')
                wizard = ReqWizard(parent=self, req=req, performance=is_perf)
                if wizard.exec_() == QDialog.Accepted:
                    orb.log.info('* req wizard completed.')
                else:
                    orb.log.info('* req wizard cancelled...')
            else:
                message = "Not Authorized"
                popup = QMessageBox(QMessageBox.Warning, 'Not Authorized',
                                    message, QMessageBox.Ok, self)
                popup.show()

    def edit_req_parms(self):
        orb.log.debug('* edit_req_parms()')
        req = None
        if len(self.fpanel.proxy_view.selectedIndexes()) >= 1:
            i = self.fpanel.proxy_model.mapToSource(
                self.fpanel.proxy_view.selectedIndexes()[0]).row()
            orb.log.debug('  at selected row: {}'.format(i))
            oid = getattr(self.fpanel.proxy_model.sourceModel().objs[i],
                          'oid', '')
            if oid:
                req = orb.get(oid)
        if req:
            if not req.req_type == 'performance':
                message = "Not a performance requirement -- no parameters."
                popup = QMessageBox(QMessageBox.Warning, 'No Parameter',
                                    message, QMessageBox.Ok, self)
                popup.show()
            elif 'modify' in get_perms(req):
                parm = None
                if req.req_constraint_type == 'maximum':
                    parm = 'req_maximum_value'
                elif req.req_constraint_type == 'minimum':
                    parm = 'req_minimum_value'
                elif req.req_constraint_type == 'single_value':
                    parm = 'req_target_value'
                if parm:
                    dlg = ReqParmDialog(req, parm, parent=self)
                    dlg.req_parm_mod.connect(self.on_req_parm_mod)
                    if dlg.exec_() == QDialog.Accepted:
                        orb.log.info('* req parm edited.')
                        dlg.close()
                    else:
                        orb.log.info('* req parm editing cancelled.')
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

    def on_req_parm_mod(self, oid):
        self.fpanel.mod_object(oid)

    def edit_req_fields(self):
        orb.log.debug('* edit_req_fields()')
        req = None
        if len(self.fpanel.proxy_view.selectedIndexes()) >= 1:
            i = self.fpanel.proxy_model.mapToSource(
                self.fpanel.proxy_view.selectedIndexes()[0]).row()
            # orb.log.debug('  at selected row: {}'.format(i))
            oid = getattr(self.fpanel.proxy_model.sourceModel().objs[i],
                          'oid', '')
            if oid:
                req = orb.get(oid)
        if req:
            if 'modify' in get_perms(req):
                dlg = ReqFieldsDialog(req, parent=self)
                if dlg.exec_() == QDialog.Accepted:
                    orb.log.info('* req fields edited.')
                    dlg.close()
                else:
                    orb.log.info('* req fields editing cancelled.')
                    dlg.close()
            else:
                message = "Not Authorized"
                popup = QMessageBox(QMessageBox.Warning, 'Not Authorized',
                                    message, QMessageBox.Ok, self)
                popup.show()

    def delete_req(self):
        orb.log.debug('* delete_req()')
        req = None
        if len(self.fpanel.proxy_view.selectedIndexes()) >= 1:
            i = self.fpanel.proxy_model.mapToSource(
                self.fpanel.proxy_view.selectedIndexes()[0]).row()
            orb.log.debug('  at selected row: {}'.format(i))
            oid = getattr(self.fpanel.proxy_model.sourceModel().objs[i],
                          'oid', '')
            if oid:
                req = orb.get(oid)
        if req:
            if 'delete' not in get_perms(req):
                message = "Not Authorized"
                popup = QMessageBox(QMessageBox.Warning, 'Not Authorized',
                                    message, QMessageBox.Ok, self)
                popup.show()
                return
            req_oid = req.oid
            # delete any related Relation and ParameterRelation objects
            rel = req.computable_form
            if rel:
                # pr_oid = req_wizard_state.get('pr_oid')
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
            # remove the req object from the filter panel
            self.fpanel.remove_object(req_oid)
            # delete the Requirement object
            orb.delete([req])
            dispatcher.send(signal='deleted object', oid=req_oid,
                            cname='Requirement')
            orb.delete([req])
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
                                       show_allocs=True, req=self.req)
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
        # edit permission for selected req. (in which case there should appear
        # a checkbox for "enable allocation/deallocation" above the tree;
        # otherwise, filtering behavior (as above) is in effect.
        pass

    # def on_edit_req_parm_signal(self, req=None, parm=None):
        # orb.log.info('* RequirementManager: on_edit_req_parm_signal()')
        # if req and parm and not self.editing_parm:
            # self.editing_parm = True
            # dlg = ReqParmDialog(req, parm, parent=self)
            # if dlg.exec_() == QDialog.Accepted:
                # orb.log.info('* req parm edited.')
                # self.editing_parm = False
                # dlg.close()
            # else:
                # orb.log.info('* req parm editing cancelled.')
                # self.editing_parm = False
                # dlg.close()

    def on_edit_req_fields_signal(self, req=None):
        orb.log.info('* RequirementManager: on_edit_req_fields_signal()')
        if req and not self.editing_fields:
            self.editing_fields = True
            dlg = ReqFieldsDialog(req, parent=self)
            if dlg.exec_() == QDialog.Accepted:
                orb.log.info('* req fields edited.')
                self.editing_fields = False
                dlg.close()
            else:
                orb.log.info('* req fields editing cancelled.')
                self.editing_fields = False
                dlg.close()

    def set_req(self, r):
        self.sys_tree.req = r

    def on_select_req(self):
        orb.log.debug('* RequirementManager: on_select_req() ...')
        if len(self.fpanel.proxy_view.selectedIndexes()) >= 1:
            i = self.fpanel.proxy_model.mapToSource(
                self.fpanel.proxy_view.selectedIndexes()[0]).row()
            orb.log.debug('  selected row: {}'.format(i))
            oid = getattr(self.fpanel.proxy_model.sourceModel().objs[i],
                          'oid', '')
            req = orb.get(oid)
            if req:
                self.set_req(req)
                # if allocated to an acu, send signal to ensure that node of
                # the tree is made visible -- not necessary if allocated to a
                # "system", since tree will be expanded to at least 1 level
                acu = req.allocated_to
                if acu:
                    dispatcher.send(signal='show alloc acu', acu=acu)
            else:
                orb.log.debug('  req with oid "{}" not found.'.format(oid))

