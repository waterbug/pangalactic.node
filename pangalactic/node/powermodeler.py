#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PowerModeler tool for modeling power modes of a mission system.
"""
import numpy as np

import sys, os
# from functools import reduce

# Louie
from pydispatch import dispatcher

from PyQt5.QtCore import Qt, QSize, QVariant
from PyQt5.QtGui import QBrush, QIcon, QFont, QPen
# from PyQt5.QtGui import QGraphicsProxyWidget
from PyQt5.QtWidgets import (QApplication, QComboBox, QDialog, QFileDialog,
                             QHBoxLayout, QScrollArea, QSizePolicy, QWidget,
                             QVBoxLayout, QWidgetAction, QMessageBox)

# PythonQwt
import qwt
from qwt.text import QwtText

# pangalactic
try:
    # if an orb has been set (uberorb or fastorb), this works
    from pangalactic.core             import orb, state
except:
    # if an orb has not been set, uberorb is set by default
    import pangalactic.core.set_uberorb
    from pangalactic.core             import orb, state
# from pangalactic.core.access      import get_perms
from pangalactic.core.names           import get_link_name, pname_to_header
from pangalactic.core.parametrics import (get_pval,
                                          get_modal_context,
                                          get_modal_power,
                                          init_mode_defz,
                                          mode_defz,
                                          round_to)
from pangalactic.core.utils.datetimes import dtstamp, date2str
from pangalactic.core.utils.reports import write_power_modes_to_xlsx
from pangalactic.core.validation  import get_level_count
from pangalactic.node.activities  import (ModeDefinitionDashboard,
                                          SystemSelectionView)
from pangalactic.node.dialogs     import DefineModesDialog, PlotDialog
# from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.widgets     import ColorLabel, CustomSplitter

LABEL_COLORS = [Qt.darkRed, Qt.darkGreen, Qt.blue, Qt.darkBlue, Qt.cyan,
                Qt.darkCyan, Qt.magenta, Qt.darkMagenta]
# -----------------------------------------------------
# Qt's predefined QColor objects:
# -----------------------------------------------------
# Qt::white         3 White (#ffffff)
# Qt::black         2 Black (#000000)
# Qt::red           7 Red (#ff0000)
# Qt::darkRed      13 Dark red (#800000)
# Qt::green         8 Green (#00ff00)
# Qt::darkGreen    14 Dark green (#008000)
# Qt::blue          9 Blue (#0000ff)
# Qt::darkBlue     15 Dark blue (#000080)
# Qt::cyan         10 Cyan (#00ffff)
# Qt::darkCyan     16 Dark cyan (#008080)
# Qt::magenta      11 Magenta (#ff00ff)
# Qt::darkMagenta  17 Dark magenta (#800080)
# Qt::yellow       12 Yellow (#ffff00)
# Qt::darkYellow   18 Dark yellow (#808000)
# Qt::gray          5 Gray (#a0a0a4)
# Qt::darkGray      4 Dark gray (#808080)
# Qt::lightGray     6 Light gray (#c0c0c0)
# Qt::transparent  19 a transparent black value (i.e., QColor(0, 0, 0, 0))
# Qt::color0        0 0 pixel value (for bitmaps)
# Qt::color1        1 1 pixel value (for bitmaps)
# orange (not Qt for that):  QColor(255, 140, 0)
# -----------------------------------------------------


def flatten_subacts(act, all_subacts=None):
    """
    For an activity that contains more than one level of sub-activities,
    return all levels of sub-activities in a single list in the order of their
    occurrance.

    Args:
        act (Activity): the specified activity

    Keyword Args:
        all_subacts (list of Activity): the flattened list of sub-activities
    """
    all_subacts = all_subacts or []
    subacts = getattr(act, 'sub_activities', []) or []
    if subacts:
        subacts.sort(key=lambda x: x.sub_activity_sequence or 0)
        # orb.log.debug(f"  domain: {names}")
        # oids = [a.oid for a in subacts]
        for i, a in enumerate(subacts):
            a_subacts = getattr(a, 'sub_activities', []) or []
            if a_subacts:
                flatten_subacts(a, all_subacts=all_subacts)
            else:
                all_subacts.append(a)
            if i == len(subacts) - 1:
                return all_subacts
    else:
        return all_subacts


class PowerModeler(QWidget):
    def __init__(self, subject=None, initial_usage=None, parent=None):
        """
        Initialize the tool.

        Keyword Args:
            subject (Activity): (optional) a subject Activity in the context of
                which power modes are being modeled
            initial_usage (Acu or PSU): initial usage (Acu or
                ProjectSystemUsage) context
            parent (QWidget):  parent widget
        """
        subject_name = getattr(subject, 'name', 'no name')
        usage_id = getattr(initial_usage, 'id', 'no id')
        argstr = f'subject="{subject_name}", initial_usage={usage_id}'
        orb.log.debug(f'* PowerModeler({argstr})')
        super().__init__(parent=parent)
        self.subject = subject
        self._usage = initial_usage
        if not mode_defz.get(self.project.oid):
            init_mode_defz(self.project.oid)
        self.sys_select_tree = SystemSelectionView(self.project,
                                                   refdes=True,
                                                   usage=self.usage)
        self.sys_select_tree.setSizePolicy(QSizePolicy.Preferred,
                                           QSizePolicy.MinimumExpanding)
        self.sys_select_tree.setObjectName('Sys Select Tree')
        self.sys_select_tree.setMinimumWidth(450)
        self.sys_select_tree.setMinimumHeight(600)
        # -- create expansion level select -----------------
        comp = None
        level_count = 0
        if self._usage:
            if isinstance(self._usage, orb.classes['ProjectSystemUsage']):
                comp = self._usage.system
            elif isinstance(self._usage, orb.classes['Acu']):
                comp = self._usage.component
            if comp is not None:
                level_count = get_level_count(comp)
        else:
            orb.log.debug("  no usage found")
        orb.log.debug(f"* level count = {level_count}")
        self.expansion_select = QComboBox()
        self.expansion_select.setStyleSheet(
                                        'font-weight: bold; font-size: 14px')
        if level_count and level_count >= 1:
            for n in range(2, level_count + 1):
                self.expansion_select.addItem(f'{n} levels', QVariant())
        self.expansion_select.currentIndexChanged.connect(
                                                self.set_select_tree_expansion)
        # -- set initial tree expansion level ---------------------------------
        # orb.log.debug("* setting initial tree expansion level ...")
        # default is to show 2 levels of assembly: project/system/subsystem ...
        # ("project" node doesn't count as it's not an "assembly level")
        if 'conops_tree_expansion' not in state:
            state['conops_tree_expansion'] = {}
        if self.project.oid not in state['conops_tree_expansion']:
            state['conops_tree_expansion'][self.project.oid] = 2
        levels_to_show = state['conops_tree_expansion'][self.project.oid]
        # combo index 0 is "2 levels", so index = level - 2
        self.set_select_tree_expansion(levels_to_show - 2)
        # ---------------------------------------------------------------------
        self.sys_select_tree.setExpandsOnDoubleClick(False)
        self.sys_select_tree.clicked.connect(self.on_item_clicked)
        sys_tree_panel = QWidget()
        sys_tree_panel_scroll_area = QScrollArea()
        sys_tree_panel_scroll_area.setMaximumWidth(500)
        sys_tree_panel_scroll_area.setWidget(sys_tree_panel)
        sys_tree_panel.setMinimumWidth(450)
        sys_tree_panel.setMaximumWidth(500)
        sys_tree_panel.setMinimumHeight(900)
        sys_tree_layout = QVBoxLayout()
        sys_tree_panel.setLayout(sys_tree_layout)
        sys_tree_title = f'{self.project.id} Mission Systems'
        sys_tree_title_widget = ColorLabel(sys_tree_title, element='h2')
        sys_tree_layout.addWidget(sys_tree_title_widget,
                                  alignment=Qt.AlignTop)
        sys_tree_layout.addWidget(self.expansion_select)
        sys_tree_layout.addWidget(self.sys_select_tree,
                                  stretch=1)
        # ====================================================================
        self.mode_dash = ModeDefinitionDashboard(parent=self,
                                                 activity=self.subject)
        self.main_splitter = CustomSplitter()
        self.main_splitter.addWidget(sys_tree_panel_scroll_area)
        self.main_splitter.addWidget(self.mode_dash)
        main_layout = QHBoxLayout()
        self.setLayout(main_layout)
        main_layout.addWidget(self.main_splitter, stretch=1)
        # ====================================================================
        dispatcher.connect(self.on_activity_got_focus, "activity focused")
        # ===================================================================
        # TODO: power modes should get a signal from TimelineModeler AFTER it
        # has processed "remote new or mod acts", and should respond to THAT
        # signal rather than directly to "remote new or mod acts" ...
        # ===================================================================
        # dispatcher.connect(self.on_remote_mod_acts, "remote new or mod acts")
        # ===================================================================
        dispatcher.connect(self.on_new_timeline, "new timeline")
        dispatcher.connect(self.on_set_no_compute, "set no compute")
        dispatcher.connect(self.on_remote_mode_defs, "modes published")
        dispatcher.connect(self.graph, "power graph")
        dispatcher.connect(self.output_excel, "output excel")

    @property
    def project(self):
        proj = orb.get(state.get('project'))
        if not proj:
            proj = orb.get('pgefobjects:SANDBOX')
        return proj

    @property
    def usage(self):
        if self._usage:
            return self._usage
        elif self.project.systems:
            self._usage = self.project.systems[0]
        else:
            TBD = orb.get('pgefobjects:TBD')
            self._usage = TBD
        return self._usage

    @usage.setter
    def usage(self, val):
        if isinstance(val, (orb.classes['ProjectSystemUsage'],
                            orb.classes['Acu'])):
            self._usage = val
            dispatcher.send(signal="powermodeler usage set", usage=val)
        else:
            usage_id = getattr(val, 'id', '(no id)')
            orb.log.debug(f'* powermodeler: invalid usage set, "{usage_id}".')

    def create_action(self, text, slot=None, icon=None, tip=None,
                      checkable=False):
        action = QWidgetAction(self)
        if icon is not None:
            icon_file = icon + state.get('icon_type', '.png')
            icon_dir = state.get('icon_dir', os.path.join(orb.home, 'icons'))
            icon_path = os.path.join(icon_dir, icon_file)
            action.setIcon(QIcon(icon_path))
        if tip is not None:
            action.setToolTip(tip)
            # action.setStatusTip(tip)
        if slot is not None:
            action.triggered.connect(slot)
        if checkable:
            action.setCheckable(True)
        return action

    def set_select_tree_expansion(self, index=None):
        # orb.log.debug(f'* set_select_tree_expansion({index})')
        if index is None:
            index = state.get('conops_tree_expansion', {}).get(
                                                self.project.oid) or 0
        try:
            self.expansion_select.setCurrentIndex(index)
            level = index + 2
            self.sys_select_tree.expandToDepth(level - 1)
            state['conops_tree_expansion'][self.project.oid] = level
            # orb.log.debug(f'* tree expanded to level {level}')
        except:
            orb.log.debug('* conops tree expansion failed ...')
            orb.log.debug('  sys_select_tree C++ obj probably gone.')
            # no big deal ...
            pass

    def on_item_clicked(self, index):
        """
        Respond to selection of a tree item.

        Args:
            index (): index of the selected node.
        """
        orb.log.debug("* PowerModeler.on_item_clicked()")
        # n = len(self.sys_select_tree.selectedIndexes())
        # orb.log.debug(f"  {n} items are selected.")
        self.sys_select_tree.expand(index)
        mapped_i = self.sys_select_tree.proxy_model.mapToSource(index)
        link = self.sys_select_tree.source_model.get_node(mapped_i).link
        name = get_link_name(link)
        orb.log.debug(f"  - clicked item usage is {name}")
        TBD = orb.get('pgefobjects:TBD')
        product = None
        # attr = '[none]'
        if isinstance(link, orb.classes['ProjectSystemUsage']):
            if link.system:
                product = link.system
                # attr = '[system]'
        elif isinstance(link, orb.classes['Acu']):
            if link.component and link.component is not TBD:
                product = link.component
                # attr = '[component]'
        # orb.log.debug(f"  - product {attr} is {product.name}")
        if not product.components:
            # [1] usage's product does not have components -> notify user
            # clear current selection
            self.sys_select_tree.clearSelection()
            popup = QMessageBox(
                  QMessageBox.Critical,
                  "No Components",
                  'This item has no components, so it cannot\n'
                  'be expanded or have a "computed" power mode.',
                  QMessageBox.Ok, self)
            popup.show()
        else:
            # [2] usage's product has components:
            project_mode_defz = mode_defz[self.project.oid]
            computed_list = project_mode_defz.get('computed', [])
            # all_comp_acu_oids = reduce(lambda x,y: x+y,
                # [list(project_mode_defz['components'].get(sys_oid, {}).keys())
                 # for sys_oid in sys_dict], [])
            if link.oid in computed_list:
                # [a] in sys_dict -> make it the subject's usage
                # orb.log.debug("  - link oid is in sys_dict")
                # set as subject's usage
                self.usage = link
                # signal to mode_dash to set this link as its usage ...
                # orb.log.debug('    sending "powermodeler set usage" signal ...')
                dispatcher.send(signal='powermodeler set usage', usage=link)
            else:
                orb.log.debug('  - link oid is NOT in the "computed" list')
                # [b] not in computed_list:
                # -- notify the user and ask if they want to
                # define modes for it ...
                dlg = DefineModesDialog(usage=link)
                if dlg.exec_() == QDialog.Accepted:
                    orb.log.debug('    calling add_usage() ..."')
                    self.add_usage(index)
                    self.usage = link
                else:
                    # deselect
                    self.sys_select_tree.clearSelection()

    def add_usage(self, index):
        """
        If the item (aka "link" or "node") selected in the assembly tree does
        not exist in the the mode_defz "systems" table, add it, and if it has
        components, add them to the mode_defz "components" table and add the
        item oid to the mode_defz "computed" list.

        If the item already exists in the "systems" table, switch to it as the
        current selected usage and deselect the previously selected usage.
        """
        orb.log.debug('* PowerModeler: add_usage()')
        orb.log.debug('  - updating mode_defz ...')
        mapped_i = self.sys_select_tree.proxy_model.mapToSource(index)
        link = self.sys_select_tree.source_model.get_node(mapped_i).link
        # link might be None -- allow for that
        if not hasattr(link, 'oid'):
            orb.log.debug('  - link has no oid, ignoring ...')
            return
        # name = get_link_name(link)
        project_mode_defz = mode_defz[self.project.oid]
        sys_dict = project_mode_defz['systems']
        comp_dict = project_mode_defz['components']
        computed_list = project_mode_defz['computed']
        # acts = getattr(link, 'activities', [])
        # act_oids = [act.oid for act in acts]
        in_comp_dict = False
        if link.oid not in computed_list:
            # selected link is NOT in computed_list:
            # [1] if it is in comp_dict and
            #     [a] it has components itself, remove its comp_dict entry,
            #         add it to sys_dict (also create comp_dict items for its
            #         components), and add its oid to computed_list
            #     [b] it has no components, ignore the operation because it is
            #         already included in comp_dict and adding it to sys_dict
            #         would not have any effect on modes calculations
            # [2] if it it is NOT in comp_dict, add it to sys_dict (creating
            #     comp_dict items for any components) and if it has components
            #     add it to computed_list
            has_components = False
            if ((hasattr(link, 'system')
                 and link.system.components) or
                (hasattr(link, 'component')
                 and link.component.components)):
                has_components = True
            for syslink_oid in comp_dict:
                if link.oid in comp_dict[syslink_oid]:
                    in_comp_dict = True
                    # [1] link is in comp_dict ...
                    orb.log.debug(' - item was in comp_dict ...')
                    if has_components:
                        orb.log.debug('   has components')
                        # [a] it has components -> remove it from comp_dict,
                        #     add it to sys_dict and computed_list
                        orb.log.debug('   removing from comp_dict ...')
                        del comp_dict[syslink_oid][link.oid]
                        sys_dict[link.oid] = {}
                        orb.log.debug('   adding to computed_list ...')
                        computed_list.append(link.oid)
                    else:
                        # [b] if it has no components, ignore the operation
                        # since it is already included as a component and
                        # adding it as a system would change nothing
                        has_components = False
                        if link.oid in computed_list:
                            computed_list.remove(link.oid)
                        orb.log.debug(' - item has no components')
                        orb.log.debug('   -- operation ignored.')
            if not in_comp_dict:
                # [2] neither in sys_dict NOR in comp_dict -- add it *if* it
                #     exists ... in degenerate case it may be None (no oid)
                orb.log.debug('   item is not in sys_dict or comp_dict')
                if hasattr(link, 'oid'):
                    sys_dict[link.oid] = {}
                    if has_components:
                        orb.log.debug('   has components')
                        orb.log.debug('   adding to computed_list ...')
                        # its mode context will be computed ...
                        computed_list.append(link.oid)
        if in_comp_dict and has_components:
            # if this usage was in the comp_dict and it has components, it has
            # now been added to the sys_dict -- make it the subject usage ...
            self.usage = link
        elif link.oid in sys_dict:
            # if this usage was in the sys_dict, make it the subject usage ...
            self.usage = link
        dispatcher.send(signal='modes edited', oid=self.project.oid)
        # signal to the mode_dash to set this link as its usage
        dispatcher.send(signal='powermodeler set usage', usage=link)

    def on_set_no_compute(self, link_oid=None):
        """
        Remove the usage oid from the "computed" list in mode_defz.
        """
        # ---------------------------------------------------------------------
        # Old docstring:
        # If the item (aka "link" or "node") in the assembly tree exists in the
        # "systems" table, remove it and remove its components from the
        # "components" table, and if it is a component of an item in the
        # "systems" table, add it back to the "components" table, and change its
        # "level" from "[computed]" to a specifiable level value.
        # ---------------------------------------------------------------------
        # TODO: implement as a context menu action ...
        # acts = getattr(self.usage, 'activities', [])
        link = orb.get(link_oid)
        # link might be None -- allow for that
        if not hasattr(link, 'oid'):
            # orb.log.debug('  - link has no oid, ignoring ...')
            return
        # name = get_link_name(link)
        project_mode_defz = mode_defz[self.project.oid]
        sys_dict = project_mode_defz['systems']
        # comp_dict = project_mode_defz['components']
        computed_list = project_mode_defz['computed']
        if link.oid in computed_list:
            computed_list.remove(link.oid)
            # -----------------------------------------------------------------
            # if link is current usage, unset it (toggle) ...
            cur_usage_oid = getattr(self.usage, 'oid', '') or ''
            if cur_usage_oid == link.oid:
                if sys_dict:
                    new_usage_oid = list(sys_dict)[0]
                    self.usage = orb.get(new_usage_oid)
                elif self.project.systems:
                    self.usage = self.project.systems[0]
            dispatcher.send(signal='modes edited', oid=self.project.oid)

    def resizeEvent(self, event):
        """
        Reimplementation of resizeEvent to capture width and height in a state
        variable.

        Args:
            event (Event): the Event instance
        """
        state['model_window_size'] = (self.width(), self.height())
        super().resizeEvent(event)

    def on_new_timeline(self, subject=None):
        """
        Respond to a new timeline scene having been set, such as resulting from
        an activity block drill-down.

        Keyword Args:
            subject (Activity): the Activity that is the subject of the new
                timeline.
        """
        orb.log.debug('* powermodeler: "new timeline" signal received --')
        orb.log.debug('  setting the new subject ..."')
        self.subject = subject

    def on_activity_got_focus(self, act):
        """
        Do something when an activity gets focus ...

        Args:
            act (Activity): the Activity instance that got focus
        """
        pass

    def on_delete_activity(self, oid=None, cname=None, remote=False):
        """
        Handler for dispatcher signals "delete activity" (sent by an event
        block when it is removed) and "deleted object" (sent by pangalaxian).
        Refreshes the activity tables. The signals are also handled by the
        TimelineWidget.

        Keyword Args:
            oid (str): oid of the deleted activity
            cname (str): class name of the deleted object
            remote (bool): True if the operation was initiated remotely
        """
        self.rebuild_table()

    def on_remote_mode_defs(self):
        """
        Handle dispatcher "modes published" signal.
        """
        orb.log.debug('* received "modes published" signal')
        # collapse and re-expand tree to refresh it
        tree_expansion_level = state.get('conops_tree_expansion', {}).get(
                                            self.project.oid) or 2
        depth = tree_expansion_level + 1
        self.sys_select_tree.collapseAll()
        self.sys_select_tree.expandToDepth(depth)

    def power_time_function(self, project=None, act=None, context="CBE",
                            time_units="minutes", subtimelines=True):
        """
        Return a function that computes system net power value as a function of
        time. Note that the time variable "t" in the returned function can be a
        scalar (float) variable or can be array-like (list, etc.).

        Keyword Args:
            project (Project): restrict to the specified project
            act (Activity): restrict to the specified activity (defaults to the
                Mission if act is None)
            ontext (str): "CBE" (Current Best Estimate) or "MEV" (Maximum
                Estimated Value)
            time_units (str): units of time to be used (default: minutes)
            subtimelines (bool):  whether to include sub-activity timelines
                (e.g. for cyclic activities, like orbits) explicitly in the
                graph (default: True)
        """
        orb.log.debug("* ConOpsModeler.power_time_function()")
        if self.usage:
            if isinstance(self.usage, orb.classes['ProjectSystemUsage']):
                comp = self.usage.system
            elif isinstance(self.usage, orb.classes['Acu']):
                comp = self.usage.component
        else:
            orb.log.debug("  no usage: zero function")
            f = (lambda t: 0.0)
            return f
        if isinstance(act, orb.classes['Activity']):
            subacts = act.sub_activities
            if subacts:
                names = [a.name for a in subacts]
                orb.log.debug(f"  domain: {names}")
                subacts.sort(key=lambda x: x.sub_activity_sequence or 0)
                if subtimelines:
                    all_acts = flatten_subacts(act)
                    t_seq = [0.0]
                    for i, a in enumerate(all_acts):
                        # t_seq.append(t_seq[i] + get_pval(a.oid, 'duration',
                                                         # units=time_units))
                        t_seq.append(t_seq[i] + orb.get_duration(a,
                                                             units=time_units))
                else:
                    all_acts = subacts
                    t_seq = [get_pval(a.oid, 't_start', units=time_units)
                             for a in subacts]
                def f_scalar(t):
                    a = all_acts[-1]
                    for i in range(len(all_acts) - 1):
                        if (t_seq[i] <= t) and (t < t_seq[i+1]):
                            a = all_acts[i]
                    modal_context = get_modal_context(project.oid,
                                                      self.usage.oid,
                                                      a.oid)
                    # orb.log.debug(f'  modal context: {modal_context}')
                    p_cbe_val = get_modal_power(project.oid,
                                                self.usage.oid, comp.oid,
                                                a.oid, modal_context)
                    if context == "CBE":
                        # orb.log.debug('  context: CBE')
                        # orb.log.debug(f'  P[cbe]: {p_cbe_val}')
                        return p_cbe_val
                    else:
                        # context == "MEV"
                        # orb.log.debug('  context: MEV')
                        ctgcy = get_pval(comp.oid, 'P[Ctgcy]')
                        factor = 1.0 + ctgcy
                        # NOTE: round_to automatically uses user pref for
                        # numeric precision
                        p_mev_val = round_to(p_cbe_val * factor)
                        # orb.log.debug(f'  P[mev]: {p_mev_val}')
                        return p_mev_val
                def f(t):
                    if isinstance(t, float):
                        return f_scalar
                    else:
                        # t is array-like: return a list function
                        return [f_scalar(x) for x in t]
            else:
                # no subactivities -> 1 mode -> constant function
                # orb.log.debug('  no subactivities ...')
                modal_context = get_modal_context(project.oid,
                                                  self.usage.oid,
                                                  a.oid)
                # orb.log.debug(f'  modal context: {modal_context}')
                p_cbe_val = get_modal_power(project.oid, self.usage.oid,
                                            comp.oid, self.act.oid,
                                            modal_context)
                if context == "CBE":
                    # orb.log.debug('  context: CBE')
                    # orb.log.debug(f'  P[cbe]: {p_cbe_val}')
                    f = (lambda t: p_cbe_val)
                else:
                    # orb.log.debug('  context: MEV')
                    ctgcy = get_pval(comp.oid, 'P[Ctgcy]')
                    factor = 1.0 + ctgcy
                    # NOTE: round_to automatically uses user pref for numeric
                    # precision; no need to specify "n" keyword arg ...
                    p_mev_val = round_to(p_cbe_val * factor)
                    # orb.log.debug(f'  P[mev]: {p_mev_val}')
                    f = (lambda t: p_mev_val)
        else:
            orb.log.debug("  no activity: zero function")
            f = (lambda t: 0.0)
        return f

    def energy_time_integral(self, act=None):
        """
        Compute system net energy consumption as a function of time.

        Keyword Args:
            act (Activity): a specified activity over which to integrate, or
                over the Mission if none is specified
        """
        pass

    def graph(self):
        """
        Output a graph of power vs. time for the current system during the
        current subject activity.
        """
        orb.log.debug('* graph()')
        project = orb.get(state.get('project'))
        orb.log.debug(f"  project: {project.id}")
        if self.usage:
            orb.log.debug(f"  usage: {self.usage.id}")
        else:
            orb.log.debug("  no usage set; returning.")
        if isinstance(self.usage, orb.classes['Acu']):
            comp = self.usage.component
        else:
            # PSU
            comp = self.usage.system
        orb.log.debug(f"  system: {comp.name}")
        mission = orb.select('Mission', owner=project)
        act = self.subject or mission
        orb.log.debug(f"  activity: {act.name}")
        subacts = act.sub_activities
        # TODO:  allow time_units to be specified ...
        time_units = "minutes"
        p_cbe_dict = {}
        p_mev_dict = {}
        # super_acts maps start_times to activities that have sub_activities
        # (i.e. "super acts")
        super_acts = {}
        p_orbital_average = 0
        # p_averages maps "super_act" name to its p_average
        p_averages = {}
        if subacts:
            # default is to break out all sub-activity timelines
            # ("subtimelines") -- this can be made configurable in the future
            subtimelines = True
            orb.log.debug('  durations of sub_activities:')
            if subtimelines:
                all_acts = flatten_subacts(act)
            else:
                all_acts = subacts
            for a in all_acts:
                d = orb.get_duration(a, units=time_units)
                orb.log.debug(f'  {a.name}: {d}')
                modal_context = get_modal_context(project.oid, self.usage.oid,
                                                  a.oid)
                orb.log.debug(f'  modal context: {modal_context}')
                p_cbe_val = get_modal_power(project.oid, self.usage.oid,
                                            comp.oid, a.oid, modal_context)
                orb.log.debug(f'  P[cbe]: {p_cbe_val}')
                p_cbe_dict[a.oid] = p_cbe_val
                ctgcy = get_pval(comp.oid, 'P[Ctgcy]')
                factor = 1.0 + ctgcy
                # NOTE: round_to automatically uses user pref for numeric
                # precision; no need to specify "n" keyword arg ...
                p_mev_val = round_to(p_cbe_val * factor)
                orb.log.debug(f'  P[mev]: {p_mev_val}')
                p_mev_dict[a.oid] = p_mev_val
        total_duration = orb.get_duration(act, units=time_units)
        t_units = time_units or 'seconds'
        d_text = f'  duration of {act.name}: {total_duration} {t_units}'
        orb.log.debug(d_text)
        max_val = max(list(p_mev_dict.values()))
        plot = qwt.QwtPlot(f"{comp.name} Power vs. Time")
        plot.setFlatStyle(False)
        plot.setAxisTitle(qwt.QwtPlot.xBottom, f"time ({time_units})")
        plot.setAxisTitle(qwt.QwtPlot.yLeft, "Power (Watts)")
        # set y-axis to begin at 0 and end 60% above max
        plot.setAxisScale(qwt.QwtPlot.xBottom, 0.0, total_duration)
        plot.setAxisScale(qwt.QwtPlot.yLeft, 0.0, 1.6 * max_val)
        f_cbe = self.power_time_function(context="CBE", project=project,
                                         act=act, time_units=time_units)
        f_mev = self.power_time_function(context="MEV", project=project,
                                         act=act, time_units=time_units)
        t_array = np.linspace(0, total_duration, 400)
        # orb.log.debug(f'  {t_array}')
        orb.log.debug(f'  f_cbe: {f_cbe(t_array)}')
        qwt.QwtPlotCurve.make(t_array, f_cbe(t_array), "P[cbe]", plot,
                              z=1.0, linecolor="blue", linewidth=2,
                              antialiased=True)
        qwt.QwtPlotCurve.make(t_array, f_mev(t_array), "P[mev]", plot,
                              z=1.0, linecolor="red", linewidth=2,
                              antialiased=True)
        last_label_y = 0
        if subtimelines:
            t_seq = [0.0]
            for i, a in enumerate(all_acts):
                t_seq.append(t_seq[i] + orb.get_duration(a, units=time_units))
        for i, a in enumerate(all_acts):
            if subtimelines:
                t_start = t_seq[i]
                t_end = t_seq[i+1]
            else:
                t_start = get_pval(a.oid, 't_start', units=time_units)
                t_end = get_pval(a.oid, 't_end', units=time_units)
            super_act = a.sub_activity_of
            if super_act is not act and super_act not in super_acts.values():
                super_acts[t_start] = a.sub_activity_of
            # insert a vertical line for t_start of each activity
            qwt.QwtPlotMarker.make(
                xvalue=t_start,
                linestyle=qwt.QwtPlotMarker.VLine,
                width=2.0,
                z=0.0,
                color="green",
                plot=plot
            )
            # insert a label for each activity (aka "mode")
            p_cbe_val = p_cbe_dict[a.oid]
            p_mev_val = p_mev_dict[a.oid]
            name = pname_to_header(a.name, 'Activity', width=20)
            label_txt = f'  {name}  '
            label_txt += f'\n P[cbe] = {p_cbe_val} Watts '
            label_txt += f'\n P[mev] = {p_mev_val} Watts '
            pen = QPen(Qt.black, 1)
            white_brush = QBrush(Qt.white)
            name_label = QwtText.make(text=label_txt, weight=QFont.Bold,
                                      borderpen=pen, borderradius=3.0,
                                      brush=white_brush)
            if p_cbe_val < .5 * max_val:
                if last_label_y == .65 * max_val:
                    y_label = .9 * max_val
                else:
                    y_label = .65 * max_val
            else:
                if last_label_y == .15 * max_val:
                    y_label = .35 * max_val
                else:
                    y_label = .15 * max_val
            last_label_y = y_label
            # -----------------------------------------------------------------
            # x-positioning and alignment of labels ...
            # -----------------------------------------------------------------
            if (t_end - t_start > .2 * total_duration):
                # sufficiently long activity/mode: center-align the label and
                # position it in the middle of the interval
                x_label = (t_start + t_end) / 2
                align_label = Qt.AlignCenter
            elif (t_end >= total_duration
                  and (t_end - t_start < .3 * total_duration)):
                # activity/mode near the end of the timeline: left-align the
                # label and position its right side at the end of the timeline
                x_label = total_duration
                align_label = Qt.AlignLeft
            else:
                # activity/mode is short and is not close to the end of the
                # timeline: right-align the label and position its left side at
                # the start of the activity/mode
                x_label = t_start
                align_label = Qt.AlignRight
            # -----------------------------------------------------------------
            qwt.QwtPlotMarker.make(
                xvalue=x_label,
                yvalue=y_label,
                align=align_label,
                z=3.0,
                label=name_label,
                plot=plot
                )
        # insert markers for the super-activities ...
        plot.resize(1400, 650)
        j = 1
        plot.updateLayout()
        canvas_map = plot.canvasMap(2)
        canvas_map.setScaleInterval(0.0, total_duration)
        canvas_map.setPaintInterval(0, 1400)
        # orb.log.debug(f'  canvas_map: {type(canvas_map)}')
        # label all "super activities" (most importantly, cycles)
        for t_start, super_act in super_acts.items():
            # compute peak and average power
            e_total = 0
            p_peak = 0
            for a in super_act.sub_activities:
                a_dur = orb.get_duration(a, units=time_units)
                # yes, this gives energy in weird units like Watt-minutes but
                # doesn't matter because just using to calculate avg. power
                a_p_cbe = p_cbe_dict.get(a.oid)
                if a_p_cbe is None:
                    orb.log.debug(f'  act "{a.name}" not in p_cbe_dict')
                    # artificially set to zero for now ...
                    a_p_cbe = 0
                a_p_mev = p_mev_dict.get(a.oid)
                if a_p_mev is None:
                    orb.log.debug(f'  act "{a.name}" not in p_mev_dict')
                    # artificially set to zero for now ...
                    a_p_mev = 0
                e_total += a_dur * a_p_cbe
                if a_p_mev > p_peak:
                    p_peak = a_p_mev
            dur = orb.get_duration(super_act, units=time_units)
            t_end = t_start + dur
            # NOTE: round_to automatically uses user pref for numeric
            # precision; no need to specify "n" keyword arg ...
            p_average = None
            try:
                p_average = round_to(e_total / dur)
            except:
                # dur was 0? ignore
                pass
            p_averages[super_act.name] = p_average
            label_txt = f'  {super_act.name}  \n'
            label_txt += f' Peak Power: {p_peak} Watts '
            if p_average is not None:
                label_txt += f'\n Average Power: {p_average} Watts '
            pen = QPen(LABEL_COLORS[j], 1)
            white_brush = QBrush(Qt.white)
            sa_name_label = QwtText.make(text=label_txt, weight=QFont.Bold,
                                         pointsize=12, borderpen=pen,
                                         borderradius=0.0, brush=white_brush)
            y_label = (1.45 - .15 * j) * max_val
            orb.log.debug(f'  super act: {super_act.name}')
            orb.log.debug(f'      begins at: {t_start} {time_units}')
            duration_pixels = canvas_map.transform_scalar(dur)
            orb.log.debug(f'      (duration: {duration_pixels} pixels)')
            symbol_size = QSize(int(duration_pixels), 10)
            symbol_brush = QBrush(LABEL_COLORS[j])
            rect_symbol = qwt.QwtSymbol.make(pen=pen, brush=symbol_brush,
                                             style=qwt.QwtSymbol.Rect,
                                             size=symbol_size)
            qwt.QwtPlotMarker.make(
                xvalue=(t_start + t_end) / 2,
                yvalue=y_label,
                z=4.0,
                label=sa_name_label,
                symbol=rect_symbol,
                plot=plot
                )
            j += 1
        # compute power average over all activities ...
        overall_avg = None
        if total_duration:
            # only evaluate if total_duration is non-zero ...
            overall_avg = round_to(sum([((p_cbe_dict.get(a.oid) or 0) * (
                                      orb.get_duration(a, units=time_units)))
                                      for a in all_acts]) / total_duration)
        title_label_txt = f'  {act.name}  \n'
        title_label_txt += f' Peak Power: {max_val} Watts '
        if overall_avg is not None:
            title_label_txt += f'\n Average Power: {overall_avg} Watts '
        pen = QPen(Qt.darkRed, 5)
        white_brush = QBrush(Qt.white)
        title_label = QwtText.make(text=title_label_txt, weight=QFont.Bold,
                                   pointsize=14, borderpen=pen,
                                   borderradius=0.0, brush=white_brush)
        y_label = 1.45 * max_val
        qwt.QwtPlotMarker.make(
            xvalue=.01 * total_duration,
            align=Qt.AlignRight,
            yvalue=y_label,
            z=4.0,
            label=title_label,
            plot=plot
            )
        # plot.resize(1400, 650)
        dlg = PlotDialog(plot, title="Power vs Time", parent=self)
        if dlg.exec_() == QDialog.Accepted:
            mode_defz[project.oid]['p_peak'] = max_val
            # TODO: re-evaluate what is wanted for average -- e.g., mission
            # average, orbital average, etc. ...
            # NOTE:  to do a "true" average over the entire mission, we must
            # have some idea of how many orbits are expected, or equivaleently
            # some estimate of the total time to be spent in an orbit (if there
            # is an orbital activity), since that will presumably be heavily
            # weighted in the overall "average power" ...
            # Thus in the meantime, if there is an orbital average use it as
            # mission average, since it is probably the best approximation ...
            if 'Orbit' in super_act.name:
                p_orbital_average = p_average
            p_average = p_orbital_average or p_average
            mode_defz[project.oid]['p_average'] = p_average
            dispatcher.send(signal="modes edited", oid=project.oid)

    def output_excel(self):
        orb.log.debug('* output_excel()')
        project = orb.get(state.get('project'))
        orb.log.debug(f"  project: {project.id}")
        if self.usage:
            orb.log.debug(f"  usage: {self.usage.id}")
        else:
            orb.log.debug("  no usage set; returning.")
            return
        if isinstance(self.usage, orb.classes['Acu']):
            comp = self.usage.component
        else:
            # PSU
            comp = self.usage.system
        orb.log.debug(f"  system: {comp.name}")
        mission = orb.select('Mission', owner=project)
        activity = self.subject or mission
        orb.log.debug(f"  activity: {activity.name}")
        dtstr = date2str(dtstamp())
        if not state.get('last_power_modes_excel_path'):
            if state.get('last_path'):
                state['last_power_modes_excel_path'] = state['last_path']
            else:
                state['last_power_modes_excel_path'] = orb.home
        suggest_fname = os.path.join(
                          state['last_power_modes_excel_path'],
                          project.id + '-Power-Modes-' + dtstr + '.xlsx')
        fpath, _ = QFileDialog.getSaveFileName(
                        self, 'Open File', suggest_fname,
                        "Excel Files (*.xlsx)")
        if fpath:
            state['last_power_modes_excel_path'] = os.path.dirname(fpath)
            write_power_modes_to_xlsx(activity, self.usage, file_path=fpath)
            orb.log.debug('  file written.')
            # try to start Excel with file if on Win or Mac ...
            if sys.platform == 'win32':
                try:
                    os.system(f'start excel.exe "{fpath}"')
                except:
                    orb.log.debug('  could not start Excel')
            elif sys.platform == 'darwin':
                try:
                    cmd = f'open -a "Microsoft Excel.app" "{fpath}"'
                    os.system(cmd)
                except:
                    orb.log.debug('  unable to start Excel')

    def closeEvent(self, event):
        """
        Things to do when this window is closed.
        """
        state["conops"] = False


if __name__ == '__main__':
    from pangalactic.node.startup import (setup_ref_db_and_version,
                                          setup_dirs_and_state)
    from pangalactic.core import __version__
    home = '/home/waterbug/cattens_home_dev'
    # orb.start(home='junk_home', debug=True)
    setup_ref_db_and_version(home, __version__)
    orb.start(home=home, console=True, debug=True)
    setup_dirs_and_state()
    app = QApplication(sys.argv)
    mw = PowerModeler()
    mw.show()
    sys.exit(app.exec_())

