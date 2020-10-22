# -*- coding: utf-8 -*-
"""
Requirement Manager
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                             QSizePolicy, QVBoxLayout)

from pangalactic.core.uberorb     import orb
from pangalactic.node.dialogs     import ReqParmDialog
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
    """
    def __init__(self, project=None, width=None, height=None, view=None,
                 req=None, parent=None):
        super().__init__(parent=parent)
        default_view = ['id', 'name', 'req_type', 'level', 'description',
                        'rationale']
        view = view or default_view
        self.req = req
        if project:
            objs = orb.search_exact(cname='Requirement', owner=project)
            title_txt = 'Project Requirements for {}'.format(project.id)
        else:
            objs = orb.search_exact(cname='Requirement')
            title_txt = 'Requirements'
        self.title = QLabel(title_txt)
        self.title.setStyleSheet('font-weight: bold; font-size: 20px')
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)
        main_layout = self.layout()
        main_layout.addWidget(self.title)
        self.content_layout = QHBoxLayout()
        main_layout.addLayout(self.content_layout, stretch=1)
        self.bbox = QDialogButtonBox(
            QDialogButtonBox.Close, Qt.Horizontal, self)
        main_layout.addWidget(self.bbox)
        self.bbox.rejected.connect(self.reject)
        self.fpanel = FilterPanel(objs, view=view, parent=self)
        self.fpanel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.fpanel.proxy_view.clicked.connect(self.on_select_req)
        fpanel_layout = QVBoxLayout()
        fpanel_layout.addWidget(self.fpanel)
        self.content_layout.addLayout(fpanel_layout, stretch=1)
        # TODO:  make project a property; in its setter, enable the checkbox
        # that opens the "allocation panel" (tree)
        if project:
            self.display_allocation_panel(project)
        dispatcher.connect(self.on_edit_req_signal, 'edit requirement')
        dispatcher.connect(self.on_edit_req_parm_signal, 'edit req parm')
        self.editing_parm = False
        width = width or 600
        height = height or 500
        self.resize(width, height)

    @property
    def req(self):
        return self._req

    @req.setter
    def req(self, r):
        self._req = r

    def display_allocation_panel(self, project):
        if getattr(self, 'tree_layout', None):
            self.tree_layout.removeWidget()
        self.sys_tree = SystemTreeView(project, refdes=True, show_allocs=True,
                                       req=self.req)
        self.sys_tree.expandToDepth(2)
        self.sys_tree.clicked.connect(self.on_select_node)
        self.tree_layout = QVBoxLayout()
        self.tree_layout.addWidget(self.sys_tree)
        self.content_layout.addLayout(self.tree_layout)

    def on_select_node(self, index):
        # TODO:  filter requirements by selected PSU/Acu
        # TODO:  enable allocation/deallocation as in wizard if user has
        # edit permission for selected req. (in which case there should appear
        # a checkbox for "enable allocation/deallocation" above the tree;
        # otherwise, filtering behavior (as above) is in effect.
        pass

    def on_edit_req_signal(self, obj=None):
        orb.log.info('* RequirementManager: on_edit_req_signal()')
        if obj:
            is_perf = (obj.req_type == 'performance')
            wizard = ReqWizard(parent=self, req=obj, performance=is_perf)
            if wizard.exec_() == QDialog.Accepted:
                orb.log.info('* req wizard completed.')
            else:
                orb.log.info('* req wizard cancelled...')

    def on_edit_req_parm_signal(self, req=None, parm=None):
        orb.log.info('* RequirementManager: on_edit_req_parm_signal()')
        if req and parm and not self.editing_parm:
            self.editing_parm = True
            dlg = ReqParmDialog(req, parm, parent=self)
            if dlg.exec_() == QDialog.Accepted:
                orb.log.info('* req parm edited.')
                self.editing_parm = False
            else:
                orb.log.info('* req parm editing cancelled.')
                self.editing_parm = False

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
            else:
                orb.log.debug('  req with oid "{}" not found.'.format(oid))


