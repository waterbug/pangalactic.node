# -*- coding: utf-8 -*-
"""
Requirement Manager
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                             QSizePolicy, QVBoxLayout)

from pangalactic.core.uberorb     import orb
from pangalactic.node.buttons     import SizedButton
from pangalactic.node.dialogs     import ReqFieldsDialog, ReqParmDialog
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
        default_view = ['id', 'req_level', 'name', 'req_type',
                        'req_compliance', 'description', 'rationale',
                        'justification', 'comment']
        view = view or default_view
        sized_cols = {'id': 0, 'name': 150}
        self.req = req
        self.req_wiz_calls = []
        self.project = project
        rqts = orb.search_exact(cname='Requirement', owner=project)
        title_txt = 'Project Requirements for {}'.format(project.id)
        self.title = QLabel(title_txt)
        self.title.setStyleSheet('font-weight: bold; font-size: 20px')
        main_layout = QVBoxLayout(self)
        # self.setLayout(main_layout)
        # main_layout = self.layout()
        main_layout.addWidget(self.title)
        self.hide_tree_button = SizedButton('Hide Allocations',
                                             color="purple")
        self.hide_tree_button.clicked.connect(self.hide_allocation_panel)
        self.show_tree_button = SizedButton('Show Allocations', color="green")
        self.show_tree_button.clicked.connect(self.display_allocation_panel)
        main_layout.addWidget(self.hide_tree_button)
        main_layout.addWidget(self.show_tree_button)
        self.content_layout = QHBoxLayout()
        main_layout.addLayout(self.content_layout, stretch=1)
        self.bbox = QDialogButtonBox(
            QDialogButtonBox.Close, Qt.Horizontal, self)
        main_layout.addWidget(self.bbox)
        self.bbox.rejected.connect(self.reject)
        # NOTE: now using word wrap and PGEF_COL_WIDTHS
        self.fpanel = FilterPanel(rqts, view=view, sized_cols=sized_cols,
                                  word_wrap=True, parent=self)
        self.fpanel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.fpanel.proxy_view.clicked.connect(self.on_select_req)
        self.fpanel_layout = QVBoxLayout()
        self.fpanel_layout.addWidget(self.fpanel)
        self.content_layout.addLayout(self.fpanel_layout)
        # TODO:  make project a property; in its setter, enable the checkbox
        # that opens the "allocation panel" (tree)
        self.display_allocation_panel()
        dispatcher.connect(self.on_edit_req_signal, 'edit requirement')
        dispatcher.connect(self.on_edit_req_parm_signal, 'edit req parm')
        dispatcher.connect(self.on_edit_req_fields_signal, 'edit req fields')
        self.editing_parm = False
        self.editing_fields = False
        width = width or 600
        height = height or 500
        self.resize(width, height)

    @property
    def req(self):
        return self._req

    @req.setter
    def req(self, r):
        self._req = r

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

    def on_edit_req_signal(self, obj=None, call=0):
        orb.log.info('* RequirementManager: on_edit_req_signal()')
        if obj and call not in self.req_wiz_calls:
            is_perf = (obj.req_type == 'performance')
            wizard = ReqWizard(parent=self, req=obj, performance=is_perf)
            if wizard.exec_() == QDialog.Accepted:
                orb.log.info('* req wizard completed.')
                self.req_wiz_calls.append(call)
            else:
                orb.log.info('* req wizard cancelled...')
                self.req_wiz_calls.append(call)

    def on_edit_req_parm_signal(self, req=None, parm=None):
        orb.log.info('* RequirementManager: on_edit_req_parm_signal()')
        if req and parm and not self.editing_parm:
            self.editing_parm = True
            dlg = ReqParmDialog(req, parm, parent=self)
            if dlg.exec_() == QDialog.Accepted:
                orb.log.info('* req parm edited.')
                self.editing_parm = False
                dlg.close()
            else:
                orb.log.info('* req parm editing cancelled.')
                self.editing_parm = False
                dlg.close()

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
                acu = req.allocated_to_function
                if acu:
                    dispatcher.send(signal='show alloc acu', acu=acu)
            else:
                orb.log.debug('  req with oid "{}" not found.'.format(oid))

