# -*- coding: utf-8 -*-
"""
Master Equipment List (MEL) Manager

NOTE:  for NASA mission and system proposals, the MEL is the definitive summary
of logistical data required for cost estimation.
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                             QSizePolicy, QVBoxLayout)

from pangalactic.core.uberorb     import orb
from pangalactic.core.utils.mel   import mel_schema, gen_mel, read_mel
from pangalactic.node.dialogs     import ReqParmDialog
from pangalactic.node.filters     import FilterPanel
from pangalactic.node.systemtree  import SystemTreeView
from pangalactic.node.melwizards  import ReqWizard

# Louie
from louie import dispatcher


class MelManager(QDialog):
    """
    Widget used to capture data for the Master Equipment List (MEL).

    Note that the actions in the incorported FilterPanel are handled there,
    sending dispatcher signals to invoke actions as necessary.

    The MEL data structure is maintained as a list of dicts and serialized to a
    yaml file.

    Keyword Args:
        project (Project):  sets a project context
    """
    def __init__(self, project=None, width=None, height=None, view=None,
                 mel=None, parent=None):
        super(MelManager, self).__init__(parent=parent)
        # TODO: MEL default view TBD ...
        default_view = list(mel_schema['field_names'].keys())
        view = view or default_view
        if project:
            objs = read_mel(orb, project.id) or mel or []
            title_txt = 'MEL for {}'.format(project.id)
        else:
            objs = mel or []
            title_txt = 'MEL'
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
        self.fpanel = FilterPanel(objs, view=view, schema=mel_schema,
                                  parent=self)
        self.fpanel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.fpanel.proxy_view.clicked.connect(self.on_select_subsystem)
        fpanel_layout = QVBoxLayout()
        fpanel_layout.addWidget(self.fpanel)
        self.content_layout.addLayout(fpanel_layout, stretch=1)
        width = width or 600
        height = height or 500
        self.resize(width, height)

    def on_select_node(self, index):
        # TODO:  filter requirements by selected PSU/Acu
        # TODO:  enable allocation/deallocation as in wizard if user has
        # edit permission for selected mel. (in which case there should appear
        # a checkbox for "enable allocation/deallocation" above the tree;
        # otherwise, filtering behavior (as above) is in effect.
        pass

    def set_mel(self, r):
        self.sys_tree.req = r

    def on_select_subsystem(self):
        orb.log.debug('* RequirementManager: on_select_subsystem() ...')
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
                orb.log.debug('  subsystem with oid "{}" not found.'.format(
                                                                        oid))

