# -*- coding: utf-8 -*-
"""
PgxnObject (a domain object viewer/editor)
"""
# from collections import OrderedDict
import os, sys
from functools import partial, reduce

from PyQt5.QtCore import pyqtSignal, Qt, QVariant
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (QAction, QComboBox, QDialog, QDialogButtonBox,
                             QFormLayout, QHBoxLayout, QLabel, QMessageBox,
                             QSizePolicy, QSpacerItem, QTabWidget, QToolBar,
                             QVBoxLayout, QWidget)

from pydispatch import dispatcher
from sqlalchemy.orm.collections import InstrumentedList

# pangalactic
try:
    # if an orb has been set, this works
    from pangalactic.core import orb
except:
    # if an orb has not been set, uberorb is set as default
    import pangalactic.core.set_uberorb
    from pangalactic.core import orb
from pangalactic.core import prefs, state
from pangalactic.core.access import get_perms, is_global_admin
from pangalactic.core.clone  import clone
from pangalactic.core.meta import (MAIN_VIEWS, PGEF_DIMENSION_ORDER, PGXN_HIDE,
                                   PGXN_HIDE_PARMS, PGXN_MASK,
                                   PGXN_PLACEHOLDERS, PGXN_VIEWS, PGXN_REQD,
                                   SELECTION_FILTERS)
from pangalactic.core.names       import get_attr_ext_name
from pangalactic.core.parametrics import (add_data_element, add_parameter,
                                          componentz,
                                          data_elementz, de_defz,
                                          delete_parameter,
                                          delete_data_element,
                                          get_parameter_id,
                                          get_dval_as_str, get_pval_as_str,
                                          get_pval, get_pval_from_str,
                                          parameterz, parm_defz, round_to,
                                          set_dval_from_str,
                                          set_pval_from_str)
from pangalactic.core.units           import alt_units, in_si, ureg
from pangalactic.core.utils.datetimes import dtstamp
from pangalactic.core.validation      import validate_all
from pangalactic.node.buttons         import SizedButton
from pangalactic.node.cad.viewer      import Model3DViewer
from pangalactic.node.dialogs         import (CannotFreezeDialog,
                                              CloningDialog,
                                              DocImportDialog,
                                              FreezingDialog,
                                              MiniMelDialog, 
                                              ModelImportDialog,
                                              ModelsAndDocsInfoDialog,
                                              ObjectSelectionDialog,
                                              ValidationDialog)
from pangalactic.node.utils           import (get_all_project_usages,
                                              get_object_title,
                                              extract_mime_data)
from pangalactic.node.widgets         import get_widget, UnitsWidget


PARMS_NBR = 9
DEFAULT_PANELS = ['main', 'info', 'narrative', 'admin']


class PgxnForm(QWidget):
    """
    A form for viewing/editing object attributes.

    Attributes:
        obj (Identifiable or subtype):  the object to be viewed or edited
        form_type (str): one of [parameters|data|main|info|narrative|admin]
        pgxo (PgxnObject):  PgxnObject instance of which this is a subwidget
        schema (dict):  the schema of the object to be viewed or edited
        view (list):  names of the fields to be shown (a subset of
            self.schema['field_names'])
        mask (list of str):  list of fields to be displayed as read-only
        all_idvs (list of tuples):  list of current (`id`, `version`) values to
            avoid
    """

    obj_modified = pyqtSignal(str)     # arg: oid

    def __init__(self, obj, form_type, pgxo=None, edit_mode=False, view=None,
                 requireds=None, main_view=None, mask=None, unmask=None,
                 noctgcy=None, seq=None, idvs=None, placeholders=None,
                 data_panel_contents=None, parent=None):
        """
        Initialize.

        Args:
            obj (Identifiable or subtype): the object to be viewed or edited
            form_type (str): one of [parameters|data|main|info|narrative|admin]

        Keyword Args:
            pgxo (PgxnObject):  PgxnObject instance of which this is a
                subwidget
            edit_mode (bool):  if True, open in edit mode; otherwise, view mode
            view (list):  names of the fields to be shown (a subset of
                self.schema['field_names'])
            requireds (list of str):  ids of required fields
            main_view (list):  names of the fields to put on the 'main' panel
            mask (list of str):  list of fields to be displayed as read-only
                (default: None)
            unmask (list of str):  list of fields to be editable which are not
                editable by default (default: None)
            noctgcy (list of str): list of parameter ids for which
                contingencies should not be included in the form
            seq (int):  sequence number of parameter or data panel in
                pgxnobject
            idvs (list of tuples):  list of current (`id`, `version`) values to
                avoid
            placeholders (dict of str):  a dict mapping field names to
                placeholder strings
            data_panel_contents (list of lists of str): a list of lists of the
                data elements to go on each data panel (derived in PgxnObject
                based on the number of data elements that are large text
                fields)
            parent (QWidget): parent widget
        """
        # orb.log.info('* [pgxnf] PgxnForm()')
        super().__init__(parent=parent)
        self.obj = obj
        self.pgxo = pgxo
        self._edit_mode = edit_mode
        self.all_idvs = idvs or []
        requireds = requireds or []
        self.noctgcy = noctgcy or []
        cname = obj.__class__.__name__
        if cname == 'HardwareProduct':
            # id's are auto-generated for HardwareProduct instances
            if mask and isinstance(mask, list):
                mask.insert('id', 0)
            else:
                mask = ['id']
        schema = orb.schemas.get(cname)
        field_names = [n for n in schema.get('field_names')
                       if n not in PGXN_MASK.get(cname, PGXN_HIDE)]
        # if form_type is "data", accept drops of data element ids -- drops of
        # parameter ids are only accepted by the ParameterForm subclass
        if form_type == 'data':
            self.setAcceptDrops(True)
            self.accepted_mime_types = set([
                             "application/x-pgef-data-element-definition"])
        # get default placeholders; override them with the specified
        # placeholders, if any
        ph_defaults = PGXN_PLACEHOLDERS
        if placeholders:
            ph_defaults.update(placeholders)
        placeholders = ph_defaults
        self.d_widgets = {}
        self.d_widget_values = {}
        self.d_widget_actions = {}
        self.p_widgets = {}
        self.p_widget_values = {}
        self.p_widget_actions = {}
        self.u_widgets = {}
        self.u_widget_values = {}
        self.previous_units = {}
        self.editable_widgets = {}
        view = view or []
        self.parm_dims = []
        required_note = False
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        form.setObjectName(form_type+'_form')
        # [1] use the fields specified in MAIN_VIEWS for the class to
        # set up a "main" form with the most important fields for the user
        # to see -- this can be overridden by the 'view' parameter; if the
        # class does not appear in MAIN_VIEWS, a main form will just contain
        # all fields that are not in the default views as specified in
        # PGXN_VIEWS for the "info" and "admin" forms.
        other = (PGXN_VIEWS['info']
                 + PGXN_VIEWS['narrative']
                 + PGXN_VIEWS['admin'])
        if main_view:
            pgxn_main_view = main_view
        elif cname in MAIN_VIEWS:
            pgxn_main_view = MAIN_VIEWS[cname]
        else:
            pgxn_main_view = [f for f in field_names if f not in other]
        # orb.log.info(f'  [pgxnf] main_view: {pgxn_main_view}')
        if form_type == 'parameters':
            # special case for parameters panel:  ignore the widget
            # population process implemented in the "for field_name" loop
            # used for the other panels
            # orb.log.info('* [pgxnf] building "parameters" form ...')
            dim_label = QLabel('Dimension:')
            dim_label.setStyleSheet('font-size: 16px; font-weight: bold;')
            self.dim_select = QComboBox()
            self.dim_select.setStyleSheet('font-size: 14; font-weight: bold;')
            self.dim_select.setSizeAdjustPolicy(0)  # size to fit contents
            current_parm_dim = state.get('current_parm_dim')
            # base_ids = orb.get_ids(cname='ParameterDefinition')
            base_ids = list(parm_defz)
            contingencies = [get_parameter_id(p, 'Ctgcy') for p in base_ids]
            parmz = parameterz.get(obj.oid) or {}
            # honor the sort order in "default_parms" if any are present, then
            # add the rest in alphabetical sort order
            pids = []
            for pid in (prefs.get('default_parms') or []):
                if pid in parmz:
                    pids.append(pid)
            for pid in sorted(list(parmz), key=str.lower):  # case-independent
                if pid not in pids:
                    pids.append(pid)
            # orb.log.debug(f'  - [pgxnf] self.noctgcy: {self.noctgcy}')
            if self.noctgcy:
                for pid in self.noctgcy:
                    c_pid = get_parameter_id(pid, 'Ctgcy')
                    if c_pid in pids:
                        # orb.log.debug(f'  - [pgxnf] removing "{c_pid}"')
                        pids.remove(c_pid)
            # orb.log.debug(f'* [pgxnf] parameters of this object: {pids}')
            # a parameter is editable if:
            # (1) not defined as "computed" OR
            # (2) a "contingency" parameter [NOTE: this may change in the
            #     future for computed contingencies]
            editables = [pid for pid in pids
                         if (not parm_defz[pid].get('computed')
                             or pid in contingencies)]
            if pids:
                # orb.log.info('* [pgxnf] parameters found: {}'.format(
                                                            # str(pids)))
                dims = set([parm_defz[pid]['dimensions']
                            for pid in pids if pid not in contingencies])
                # txt = f'selecting dims from: {PGEF_DIMENSION_ORDER}'
                # orb.log.info(f'* [pgxnf] {txt}')
                for dim in PGEF_DIMENSION_ORDER:
                    if dim in dims:
                        label = PGEF_DIMENSION_ORDER[dim]
                        self.parm_dims.append(dim)
                        self.dim_select.addItem(label, QVariant)
                # orb.log.info(f'* [pgxnf] dimensions found: {self.parm_dims}')
                if self.parm_dims and (current_parm_dim not in self.parm_dims):
                    current_parm_dim = self.parm_dims[0]
                    state['current_parm_dim'] = self.parm_dims[0]
                self.dim_select.setCurrentText(
                                        PGEF_DIMENSION_ORDER[current_parm_dim])
                self.dim_select.activated.connect(self.on_dim_select)
                form.addRow(dim_label, self.dim_select)
                spacer = QSpacerItem(200, 10)
                form.setItem(1, QFormLayout.SpanningRole, spacer)
                computed_note = False
                editables = [pid for pid in pids if pid in editables]
                computeds = [pid for pid in pids if pid not in editables]
                p_ordering = [pid for pid in editables + computeds
                              if pid not in contingencies]
                # orb.log.info('  [pgxnf] parameter ordering: {}'.format(
                                                            # str(p_ordering)))
                if current_parm_dim in [None, '']:
                    relevant_pids = [pid for pid in pids
                          if parm_defz[pid]['dimensions'] in [None, '']]
                else:
                    relevant_pids = [pid for pid in pids
                          if parm_defz[pid]['dimensions'] == current_parm_dim]
                # orb.log.info(f'* [pgxnf] relevant params: {relevant_pids}')
                pids_on_panel = [pid for pid in p_ordering
                                 if pid in relevant_pids]
                # orb.log.info(f'* [pgxnf] params on panel: {pids_on_panel}')
                # NOTE: not using 'seq' for parameters now, but set it anyway
                seq = None
                for pid in pids_on_panel:
                    field_name = pid
                    pd = parm_defz[pid]
                    ext_name = pd.get('name', '') or '[unknown]'
                    # parm types are 'float', 'int', 'bool', or 'text'
                    parm_type = pd.get('range_datatype', 'float')
                    units = ''
                    if parm_type in ['int', 'float']:
                        # units only apply to numeric types and are set to
                        # the user's preferred units
                        dimensions = pd.get('dimensions', '')
                        if prefs.get('units'):
                            units = prefs['units'].get(dimensions)
                        if not units:
                            # if preferred units are not set, use base units
                            units = in_si.get(dimensions) or ''
                        unit_choices = alt_units.get(dimensions)
                        if unit_choices:
                            units_widget = UnitsWidget(field_name, units,
                                                       unit_choices)
                            units_widget.currentTextChanged.connect(
                                                            self.on_set_units)
                        else:
                            units_widget = QLabel(units)
                    else:
                        units_widget = None
                    # field_type 'parameter' -> StringFieldWidget for edit mode
                    field_type = 'parameter'
                    # p is editable if its pid is in 'editables'
                    editable = (self.edit_mode and pid in editables)
                    definition = (pd.get('description', '')
                                  or 'unknown definition')
                    # NOTE: get_pval_as_str will convert the stored value from
                    # base units to the units specified (using get_pval)
                    str_val = get_pval_as_str(self.obj.oid, pid, units=units)
                    widget, label = get_widget(field_name, field_type,
                                               value=str_val,
                                               external_name=ext_name,
                                               editable=editable,
                                               tooltip=definition,
                                               parm_field=True,
                                               parm_type=parm_type)
                    # float parms should have contingency parms -- if so, the
                    # contingency parm will have an entry in parm_defz ...
                    c_pd = None
                    c_widget = None
                    if pid not in self.noctgcy:
                        c_pid = get_parameter_id(pid, 'Ctgcy')
                        c_pd = parm_defz.get(c_pid)
                    if c_pd and (pid not in self.noctgcy):
                        c_ext_name = c_pd.get('name', '') or '[unknown]'
                        c_units = '%'
                        c_units_widget = QLabel(c_units)
                        c_definition = (c_pd.get('description', '')
                                        or 'unknown definition')
                        c_str_val = get_pval_as_str(self.obj.oid, c_pid,
                                                    units=units)
                        c_widget, c_label = get_widget(c_pid, 'parameter',
                                                      value=c_str_val,
                                                      external_name=c_ext_name,
                                                      editable=editable,
                                                      tooltip=c_definition,
                                                      parm_field=True,
                                                      parm_type='float')
                    if widget:
                        # *** this is EXTREMELY verbose, even for debugging!
                        # orb.log.debug('  [pgxnf]'
                               # ' - got widget (%s) and label, "%s"' % (
                                                 # str(widget),
                                                 # str(label.text())))
                        self.p_widgets[pid] = widget
                        self.u_widgets[pid] = units_widget
                        # use "stringified" values because that's what is in
                        # the form field
                        self.u_widget_values[pid] = units
                        self.previous_units[pid] = units
                        self.p_widget_values[pid] = str_val
                        widget.setSizePolicy(QSizePolicy.Minimum,
                                             QSizePolicy.Minimum)
                        if pid not in editables:
                            label.setStyleSheet(
                                'QLabel {font-size: 15px; font-weight: bold; '
                                'color: purple} QToolTip {'
                                'font-weight: normal; color: black; '
                                'font-size: 12px; border: 2px solid;}')
                            computed_note = True
                        if self.edit_mode:
                            del_action = QAction('delete', label)
                            if hasattr(parent, 'on_del_parameter'):
                                del_action.triggered.connect(
                                    partial(parent.on_del_parameter, pid=pid))
                            label.addAction(del_action)
                            label.setContextMenuPolicy(Qt.ActionsContextMenu)
                        value_layout = QHBoxLayout()
                        value_layout.addWidget(widget)
                        # units_widget is None for non-numeric parameters
                        if units_widget:
                            value_layout.addWidget(units_widget)
                        if c_widget:
                            self.p_widgets[c_pid] = c_widget
                            self.u_widgets[c_pid] = c_units_widget
                            self.u_widget_values[c_pid] = '%'
                            self.previous_units[c_pid] = '%'
                            c_parm = parmz.get(c_pid) or {}
                            self.p_widget_values[c_pid] = str(c_parm)
                            c_widget.setSizePolicy(QSizePolicy.Minimum,
                                                   QSizePolicy.Minimum)
                            value_layout.addWidget(c_label)
                            value_layout.addWidget(c_widget)
                            value_layout.addWidget(c_units_widget)
                        form.addRow(label, value_layout)
                        # orb.log.debug('* [pgxnf] size hint: %s' % str(
                                                    # widget.sizeHint()))
                if computed_note:
                    form.addRow(QWidget(), QLabel())
                    cnote = QLabel("* computed parameter\n  (read-only)")
                    cnote.setStyleSheet('font-weight: bold;color: purple')
                    form.addRow(cnote)
            else:
                # orb.log.info('* [pgxnf] no parameters found.')
                label = QLabel('No parameters have been specified yet.')
                label.setStyleSheet('font-weight: bold')
                form.addRow(label)
            self.setLayout(form)
            # end of "parameters" form initialization
            return
        elif form_type == 'data':
            # special case for data panel:  ignore the widget
            # population process implemented in the "for field_name" loop
            # used for the other panels
            # orb.log.info('* [pgxnf] building "data" form ...')
            de_dict = data_elementz.get(obj.oid) or {}
            # prune out any undefined de's
            if de_dict:
                undefined_des = []
                for deid in de_dict:
                    if deid not in de_defz:
                        undefined_des.append(deid)
                if undefined_des:
                    for deid in undefined_des:
                        del de_dict[deid]
            deids = sorted(list(de_dict))
            if deids:
                # orb.log.info('* [pgxnf] data elements found: {}'.format(
                                                            # str(deids)))
                if seq is None:
                    # orb.log.debug('  seq is None; only one "data" page.')
                    deids_on_panel = deids
                else:
                    # orb.log.debug('  seq is {}'.format(str(seq)))
                    # NOTE:  'seq' is a 1-based sequence
                    # orb.log.debug('  data elements found: {}'.format(
                                                        # str(deids)))
                    deids_on_panel = data_panel_contents[seq-1]
                    # orb.log.debug('  data elements on this panel: {}'.format(
                                                        # str(deids_on_panel)))
                for deid in deids_on_panel:
                    # orb.log.debug('* getting data element "{}"'.format(deid))
                    field_name = deid
                    ded = de_defz[deid]
                    ext_name = ded.get('label') or ded.get('name', 'unknown')
                    # parm types are 'float', 'int', 'bool', or 'text'
                    de_type = ded.get('range_datatype', 'str')
                    # field_type 'parameter' -> StringFieldWidget for edit mode
                    # NOTE: use 'parameter' field type for data elements too
                    field_type = 'parameter'
                    editable = self.edit_mode
                    definition = (ded.get('description', '')
                                  or 'unknown definition')
                    str_val = get_dval_as_str(self.obj.oid, deid)
                    # orb.log.debug('  value: "{}"'.format(str_val))
                    widget, label = get_widget(field_name, field_type,
                                               value=str_val,
                                               external_name=ext_name,
                                               editable=editable,
                                               tooltip=definition,
                                               de_field=True,
                                               de_type=de_type)
                    if widget:
                        # *** this is EXTREMELY verbose, even for debugging!
                        # orb.log.debug('  [pgxnf]'
                               # ' - got widget (%s) and label, "%s"' % (
                                                 # str(widget),
                                                 # str(label.text())))
                        self.d_widgets[deid] = widget
                        # use "stringified" values because that's what is in
                        # the form field
                        self.d_widget_values[deid] = str_val
                        widget.setSizePolicy(QSizePolicy.Minimum,
                                             QSizePolicy.Minimum)
                        if self.edit_mode:
                            del_action = QAction('delete', label)
                            if hasattr(parent, 'on_del_de'):
                                del_action.triggered.connect(
                                        partial(parent.on_del_de, deid=deid))
                            label.addAction(del_action)
                            label.setContextMenuPolicy(Qt.ActionsContextMenu)
                        value_layout = QHBoxLayout()
                        value_layout.addWidget(widget)
                        form.addRow(label, value_layout)
                        # orb.log.debug('* [pgxnf] size hint: %s' % str(
                                                    # widget.sizeHint()))
            else:
                # orb.log.info('* [pgxnf] no data elements found.')
                label = QLabel('No data elements have been specified yet.')
                label.setStyleSheet('font-weight: bold')
                form.addRow(label)
            self.setLayout(form)
            # end of "data" form initialization
            return
        elif form_type == 'main':
            form_view = pgxn_main_view
        # [2] set up the "info" tab to contain all fields not in the "main",
        # "narrative", or "admin" forms (specified in PGXN_VIEWS).
        elif form_type == 'info':
            # default_info picks fields in the order they appear in
            # PGXN_VIEWS['info']
            default_info = [f for f in PGXN_VIEWS['info']
                            if f in field_names and
                               f not in PGXN_VIEWS['narrative'] and
                               f not in PGXN_VIEWS['admin'] and
                               f not in pgxn_main_view]
            residual_view = [f for f in field_names
                             if f not in default_info and
                                f not in PGXN_VIEWS['narrative'] and
                                f not in PGXN_VIEWS['admin'] and
                                f not in pgxn_main_view]
            form_view = default_info + residual_view
        # [3] set up the "admin" tab with the fields specified for it in
        # PGXN_VIEWS.
        elif form_type == 'narrative':
            form_view = [f for f in PGXN_VIEWS['narrative']
                        if f not in pgxn_main_view]
        else:  # "admin" tab
            form_view = [f for f in PGXN_VIEWS['admin']
                        if f not in pgxn_main_view]
        # orb.log.info(f'  [pgxnf] form_type: {form_type}')
        # if a view is specified, it restricts the fields displayed
        if view:
            this_view = [f for f in form_view if f in view]
        else:
            this_view = [f for f in form_view if f in field_names]
        if not requireds:
            # if no custom requireds are specified, use PGXN_REQD
            requireds = PGXN_REQD.get(cname) or []
        reqd_fields = [f for f in field_names if f in requireds]
        # don't create panel if it will have no fields
        # orb.log.info(f'  [pgxnf] view: {this_view}')
        if not this_view:
            return None
        for field_name in this_view:
            field_type = schema['fields'][field_name]['field_type']
            if field_type == 'object':
                val = getattr(obj, field_name, None)
            else:
                # TODO: explicitly set a default value of the correct type
                val = getattr(obj, field_name, '')
            # external_name will be shown on the label in the user
            # interface
            external_name = get_attr_ext_name(cname, field_name)
            obj_pk = getattr(obj, 'oid')
            max_length = schema['fields'][field_name].get('max_length', 80)
            nullable = schema['fields'][field_name].get('null')
            choices = schema['fields'][field_name].get('choices')
            definition = schema['fields'][field_name].get('definition')
            if self.edit_mode:
                editable = schema['fields'][field_name].get('editable')
                if mask and field_name in mask:
                    editable = False
                if unmask and field_name in unmask:
                    editable = True
            else:
                editable = False
            related_cname = schema['fields'][field_name].get('related_cname')
            # NOTE: this should be uncommented if needed for debugging
            # orb.log.debug('* [pgxnf] get_widget("{}", {})'.format(
                                                        # field_name,
                                                        # str(field_type)))
            widget, label = get_widget(field_name, field_type, value=val,
                                   editable=editable, nullable=nullable,
                                   maxlen=max_length, obj_pk=obj_pk,
                                   external_name=external_name,
                                   related_cname=related_cname,
                                   placeholder=placeholders.get(field_name),
                                   choices=choices, tooltip=definition)
            if widget:
                # orb.log.debug('  [pgxnf]'
                              # ' - got widget (%s) and label, "%s"' % (
                                                     # str(widget),
                                                     # str(label.text())))
                if editable:
                    self.editable_widgets[field_name] = widget
                widget.setSizePolicy(QSizePolicy.Minimum,
                                     QSizePolicy.Minimum)
                if editable and field_name in reqd_fields:
                    text = label.text() + ' **'
                    label.setText(text)
                    required_note = True
                form.addRow(label, widget)
                # orb.log.debug('* [pgxnf] widget size hint: %s' % str(
                                                        # widget.sizeHint()))
                if related_cname:
                    if editable:
                        widget.clicked.connect(self.on_select_related)
                    elif val is not None:
                        widget.clicked.connect(self.on_view_related)
            # else:
                # orb.log.debug('  [pgxnf] - no widget returned.')
        if required_note:
            form.addRow(QWidget(), QLabel())
            rnote = QLabel("** required fields\n  (cannot be empty or None)")
            rnote.setStyleSheet('font-weight: bold;color: purple')
            form.addRow(rnote)
        self.setSizePolicy(QSizePolicy.Minimum,
                           QSizePolicy.Minimum)
        self.setLayout(form)

    @property
    def edit_mode(self):
        if self.pgxo is not None:
            return self.pgxo.edit_mode
        else:
            return self._edit_mode

    def dragEnterEvent(self, event):
        mime_formats = set(event.mimeData().formats())
        orb.log.info("* dragEnterEvent: mime types {}".format(
                     str(mime_formats)))
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
        # NOTE: 'x-pgef-data-element-definition' may be deprecated in favor of
        # 'x-pgef-data-element-id' (just a string) in the future ...
        if self.edit_mode and event.mimeData().hasFormat(
            "application/x-pgef-data-element-definition"):
            # orb.log.info("* [pgxnf] dropEvent: got data element")
            data = extract_mime_data(event,
                             "application/x-pgef-data-element-definition")
            icon, ded_oid, deid, de_name, ded_cname = data
            obj_des = data_elementz.get(self.obj.oid) or {}
            orb.log.debug(f'* DE drop event: "{de_name}" ("{deid}")')
            if deid not in obj_des:
                event.setDropAction(Qt.CopyAction)
                event.accept()
                add_data_element(self.obj.oid, deid)
                self.obj.modifier = orb.get(state.get('local_user_oid'))
                self.obj.mod_datetime = dtstamp()
                orb.save([self.obj])
                dispatcher.send(signal='modified object', obj=self.obj)
                self.obj_modified.emit(self.obj.oid)
                self.pgxo.build_from_object()
            else:
                event.ignore()
                # orb.log.info(f"* DE drop event: ignoring '{de_name}' -- "
                             # "we already got one, it's verra nahss!")

    def on_set_units(self):
        # orb.log.info('* [pgxnf] setting units ...')
        units_widget = self.sender()
        new_units = units_widget.get_value()
        # orb.log.debug('            new units: "{}"'.format(new_units))
        pid = units_widget.field_name
        parm_widget = self.p_widgets.get(pid)
        if self.edit_mode and hasattr(parm_widget, 'get_value'):
            # in edit mode, get value (str) from editable field and convert it
            str_val = parm_widget.get_value()
            pval = get_pval_from_str(self.obj.oid, pid, str_val)
            applicable_units = self.previous_units[pid]
            Q_ = ureg.Quantity
            quant = Q_(pval, ureg.parse_expression(applicable_units))
            new_quant = quant.to(new_units)
            new_str_val = str(round_to(new_quant.magnitude))
        else:
            # view mode or read-only parm -> get cached parameter value and
            # convert it to the requested units for display
            new_str_val = get_pval_as_str(self.obj.oid, pid, units=new_units)
        if hasattr(parm_widget, 'set_value'):
            parm_widget.set_value(new_str_val)
        elif hasattr(parm_widget, 'setText'):
            parm_widget.setText(new_str_val)
        self.previous_units[pid] = new_units

    def on_select_related(self):
        orb.log.info('* [pgxnf] select related object ...')
        widget = self.sender()
        # obj = widget.get_value()
        # TODO:  if None, give option to create a new object
        # orb.log.debug('  [pgxo] current object: %s' % str(obj))
        cname = widget.related_cname
        field_name = widget.field_name
        # SELECTION_FILTERS define the set of valid objects for this field
        objs = []
        if SELECTION_FILTERS.get(field_name):
            fltrs = SELECTION_FILTERS[field_name]
            for cname in fltrs:
                objs += orb.get_by_type(cname)
        else:
            objs = orb.get_all_subtypes(cname)
        if objs:
            # orb.log.debug('  [pgxo] object being edited: {}'.format(
                                                            # self.obj.oid))
            if self.obj in objs:
                # exclude the object being edited from the selections
                # orb.log.debug('            removing it from selectables ...')
                objs.remove(self.obj)
            required_fields = PGXN_REQD.get(cname) or []
            with_none = not (field_name in required_fields)
            objs.sort(key=lambda x: getattr(x, 'id', '') or '')
            dlg = ObjectSelectionDialog(objs, with_none=with_none, parent=self)
            if dlg.exec_():
                new_oid = dlg.get_oid()
                new_obj = orb.get(new_oid)
                widget.set_value(new_obj)
        else:
            # TODO:  pop-up message about no objects being available
            pass

    def on_view_related(self):
        # orb.log.info('* [pgxo] view related object ...')
        widget = self.sender()
        # TODO: handle get_value() for M2M and ONE2M relationships
        # (InstrumentedList)
        obj = widget.get_value()
        # orb.log.debug('* [pgxo]   object: %s' % str(obj))
        # TODO:  if editable, bring up selection list of possible values
        # or, if none, give option to create a new object (with pgxnobject)
        # NOTE: get_value() may return a sqlalchemy "InstrumentedList" -- in
        # that case ignore it because it will cause a crash
        if obj and not isinstance(obj, InstrumentedList):
            self.new_window = PgxnObject(obj)
            # show() -> non-modal dialog
            self.new_window.show()

    def on_dim_select(self, index):
        """
        Handle "activate" event from the "dim_select" combo box that sets the
        dimensional parameter panel -- i.e. switch to another dimensional
        parameter panel.
        """
        if self.edit_mode:
            # if in edit mode, save parameters before the switch or edits will
            # be lost ...
            for p_id in self.p_widgets:
                # if p is computed, its widget is a label (no 'get_value')
                # DO NOT MODIFY values
                if hasattr(self.p_widgets[p_id], 'get_value'):
                    str_val = self.p_widgets[p_id].get_value()
                    # u_cur -> current units setting
                    # (None if can't modify, which also means base units)
                    u_cur = None
                    if hasattr(self.u_widgets[p_id], 'currentText'):
                        u_cur = self.u_widgets[p_id].currentText()
                        # orb.log.debug('  - units widget set to {}'.format(
                                                                    # u_cur))
                    # set parameter values for ALL editable
                    # parameters (faster/simpler than checking for mods)
                    # orb.log.debug('  - setting {} to {} {}'.format(
                                  # p_id, str_val, u_cur))
                    set_pval_from_str(self.obj.oid, p_id, str_val,
                                      units=u_cur)
        state['current_parm_dim'] = self.parm_dims[index]
        if hasattr(self.pgxo, 'build_from_object'):
            self.pgxo.build_from_object()


class ParameterForm(PgxnForm):
    """
    A form for viewing/editing object parameters.

    Attributes:
        obj (Identifiable or subtype):  the object to be viewed or edited
        pgxo (PgxnObject):  PgxnObject instance of which this is a subwidget
        schema (dict):  the schema of the object to be viewed or edited
        edit_mode (bool):  a property derived from the edit mode of the 'pgxo'
        view (list):  names of the fields to be shown (a subset of
            self.schema['field_names'])
        mask (list of str):  list of fields to be displayed as read-only
    """
    def __init__(self, obj, pgxo=None, view=None, mask=None, noctgcy=None,
                 seq=None, edit_mode=False, parent=None):
        """
        Initialize.

        Args:
            obj (Identifiable or subtype):  the object to be viewed or edited

        Keyword Args:
            view (list):  names of the fields to be shown (a subset of
                self.schema['field_names'])
            mask (list of str):  list of fields to be displayed as read-only
                (default: None)
            noctgcy (list of str): list of parameter ids for which
                contingencies should not be included in the form
            edit_mode (bool):  if True, open in edit mode; otherwise, view mode
        """
        super().__init__(obj, 'parameters', pgxo=pgxo, view=view, mask=mask,
                         edit_mode=edit_mode, noctgcy=noctgcy, seq=seq,
                         parent=parent)
        self.obj = obj
        self.pgxo = pgxo
        self._edit_mode = edit_mode
        self.noctgcy = noctgcy
        self.seq = None
        self.setAcceptDrops(True)
        self.accepted_mime_types = set([
                             "application/x-pgef-parameter-definition",
                             "application/x-pgef-parameter-id"])

    def dragEnterEvent(self, event):
        mime_formats = set(event.mimeData().formats())
        # orb.log.info("* dragEnterEvent: mime types {}".format(
                     # str(mime_formats)))
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
        orb.log.info("* dropEvent: got data")
        ### NOTE: 'x-pgef-parameter-definition' will be deprecated in favor of
        ### 'x-pgef-parameter-id' (just a string)
        if self.edit_mode and event.mimeData().hasFormat(
            "application/x-pgef-parameter-definition"):
            data = extract_mime_data(event,
                                     "application/x-pgef-parameter-definition")
            icon, pd_oid, pd_id, pd_name, pd_cname = data
            obj_parms = parameterz.get(self.obj.oid) or {}
            if pd_id not in obj_parms:
                orb.log.info("* Parameter drop event: got '%s'" % pd_name)
                event.setDropAction(Qt.CopyAction)
                event.accept()
                add_parameter(self.obj.oid, pd_id)
                dispatcher.send(signal='parm added',
                                oid=self.obj.oid, pid=pd_id)
                self.pgxo.build_from_object()
            else:
                event.ignore()
                # orb.log.debug("* Parameter drop event: ignoring '%s' -- "
                             # "we already got one, it's verra nahss!"
                             # % pd_name)
        if self.edit_mode and event.mimeData().hasFormat(
            "application/x-pgef-parameter-id"):
            pid = extract_mime_data(event, "application/x-pgef-parameter-id")
            obj_parms = parameterz.get(self.obj.oid) or {}
            if pid not in obj_parms:
                orb.log.info(f'* Parameter drop event: got "{pid}"')
                event.setDropAction(Qt.CopyAction)
                event.accept()
                add_parameter(self.obj.oid, pid)
                dispatcher.send(signal='parm added',
                                oid=self.obj.oid, pid=pid)
                self.pgxo.build_from_object()
            else:
                event.ignore()
                # orb.log.info(f'* Parameter drop event: ignoring "{pid}" -- '
                             # "we already got one, it's verra nahss!")
        else:
            event.ignore()


class PgxnObject(QDialog):
    """
    Object viewer/editor.

    Attributes:
        obj (Identifiable or subtype):  the object to be viewed or edited
        schema (dict):  the schema of the object to be viewed or edited
        edit_mode (bool):  if True, open in edit mode; otherwise, view mode
        component (bool):  if True, embedded in component modeler window
            (special behavior when deleting object, not used in other
            embedded modes)
        ded_disallowed_names (list of str):  a property containing all current
            parameter and data element ids and names, used in validating the
            contents of the "id" and "name" fields for a DataElementDefinition
        embedded (bool):  if True, PgxnObject is embedded in another widget
        enable_delete (bool):  flag indicating whether a "Delete" button
            should be displayed when in edit mode (deletes object)
        go_to_tab (int):  index of the tab to go to when rebuilding
        view (list):  names of the fields to be shown (a subset of
            self.schema['field_names'])
        view_only (bool):  flag indicating that edit mode is unavailable
            (default: False)
        mask (list of str):  list of fields to be displayed as read-only
        required (list of str):  list of fields that must not be null
        noctgcy (list of str): list of parameter ids for which contingencies
            should not be included in the form
        tabs (QTabWidget):  widget holding the interface's tabbed "pages"
    """

    activity_edited = pyqtSignal(str)  # arg: oid
    obj_modified = pyqtSignal(str)     # arg: oid

    def __init__(self, obj, component=False, embedded=False,
                 edit_mode=False, enable_delete=True, view=None,
                 main_view=None, mask=None, required=None, panels=None,
                 go_to_panel='main', new=False, test=False, title_text=None,
                 modal_mode=False, view_only=False, noctgcy=None, parent=None,
                 **kw):
        """
        Initialize the dialog.

        Args:
            obj (Identifiable or subtype):  the object to be viewed or edited

        Keyword Args:
            component (bool):  if True, embedded in component modeler window
                (special behavior for deleting object, not used in other
                embedded modes)
            embedded (bool):  if True, PgxnObject is embedded in another widget
            edit_mode (bool):  if True, open in edit mode; otherwise, view mode
            enable_delete (bool):  flag indicating whether a "Delete" button
                should be displayed when in edit mode (deletes object)
            view (list):  names of all the fields to be shown (a subset of
                self.schema['field_names'])
            main_view (list):  names of the fields to put on the 'main' panel
            mask (list of str):  list of fields to be displayed as read-only
                (default: None)
            required (list of str):  list of fields that must not be null
                (default: None) -- if None, the fields specified for the
                object's class in PGXN_REQD are used
            panels (list of str or None):  list of names of panels to include
                in the interface ('main', 'info', 'narrative', 'admin',
                'parameters', 'data'); if None, all panels
            go_to_panel (str or None):  name of panel to show initially in the
                interface (one of 'main', 'info', 'narrative', 'admin') -- NOTE
                that this will only work if the object has no parameters; if
                None (the default), the panel shown will be the 'main' panel
            new (bool):  flag for new object
            test (bool):  flag for "test mode"
            modal_mode (bool):  flag indicating whether dialog should be modal
                -- modal_mode is intended only for very small dialogs that
                close upon saving (i.e., do not go into "view" mode)
            view_only (bool):  flag indicating that edit mode is unavailable
                (default: False)
            noctgcy (list of str): list of parameter ids for which
                contingencies should not be included in the form
            parent (QWidget): parent widget of this dialog (default: None)
        """
        super().__init__(parent=parent)
        if not obj:
            return
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.obj          = obj
        self.new          = new
        self.component    = component
        self.embedded     = embedded
        # check perms, even if edit_mode is True
        perms = get_perms(obj)
        self.edit_mode    = False
        if (new or ('modify' in perms)) and edit_mode:
            self.edit_mode = True
        self.view_only    = view_only
        self.mode_widgets = {}
        self.mode_widgets['view'] = set()
        self.mode_widgets['edit'] = set()
        self.modal_mode    = modal_mode
        self.enable_delete = enable_delete
        self.go_to_tab     = 0
        if panels and go_to_panel in panels:
            self.go_to_tab = panels.index(go_to_panel)
        elif go_to_panel in DEFAULT_PANELS:
            self.go_to_tab = DEFAULT_PANELS.index(go_to_panel)
        self.view         = view or []
        self.main_view    = main_view or []
        self.panels       = panels or []
        self.noctgcy      = noctgcy
        self.required     = required
        self.tabs         = QTabWidget()
        self.tabs.tabBarClicked.connect(self.on_set_tab)
        self.cname        = obj.__class__.__name__
        if self.cname == 'Project' and not self.new:
            # id for an existing project cannot be modified
            self.mask = ['id']
        else:
            self.mask = mask
        self.schema       = orb.schemas.get(self.cname)
        self.title_text   = title_text
        self.ded_id_modified = False
        self.ded_name_modified = False
        # all_idvs is used in validating 'id' + 'version' uniqueness ...
        self.all_idvs = orb.get_idvs(cname=self.cname)
        obj_idv = (self.obj.id, getattr(obj, 'version', ''))
        if not self.new and obj_idv in self.all_idvs:
            # if not a new object, remove its (id, version) from all_idvs
            self.all_idvs.remove(obj_idv)
        if not self.schema:
            # TODO:  more intelligent error handling
            orb.log.info('* [pgxo] oops, no schema found for "%s"!' %
                                                                    self.cname)
            return
        # In case the object has been deleted on the server but is hanging
        # around, replace it with the TBD object ...
        if self.obj.oid in (state.get('deleted_oids') or []):
            self.obj = orb.get('pgefobjects:TBD')
        # orb.log.info('* [pgxo] object oid: "%s"' % self.obj.oid)
        # orb.log.info('  [pgxo] object id: "%s"' % self.obj.id)
        # orb.log.info('  [pgxo] object version: "%s"' % getattr(
                                                        # self.obj, 'version',
                                                        # '[not applicable]'))
        # orb.log.info('  [pgxo] cname: "%s"' % self.cname)
        self.build_from_object()
        if state.get('pgxno_oids'):
            state['pgxno_oids'].append(self.obj.oid)
        else:
            state['pgxno_oids'] = [self.obj.oid]
        dispatcher.connect(self.on_parameters_recomputed,
                           'parameters recomputed')
        dispatcher.connect(self.on_update_pgxno, 'update pgxno')
        # listen for "new object" in case it is a related Acu
        dispatcher.connect(self.on_new_object, 'new object')

    def build_from_object(self):
        """
        Build tabbed forms from the supplied object
        """
        # orb.log.debug('* [pgxo] build_from_object()')
        self.setWindowTitle('Object Viewer / Editor')
        # set min width so text fields don't get truncated
        self.setMinimumWidth(550)
        need_title_box = False
        # self.setMinimumHeight(300)
        # destroy the existing stuff, if necessary ...
        if not getattr(self, 'vbox', None):
            self.vbox = QVBoxLayout()
        if not getattr(self, 'title_box', None):
            # orb.log.debug('* [pgxo] no title_box layout -- adding ...')
            self.title_box = QHBoxLayout()
            need_title_box = True
        if getattr(self, 'title', None):
            self.title_text = get_object_title(self.obj, new=self.new)
            # use try/except in case self.title's C++ obj got deleted ...
            try:
                self.title.setText(self.title_text)
            except:
                orb.log.debug('* [pgxo] update of title failed, new title ...')
                self.title = QLabel()
                self.title.setAttribute(Qt.WA_DeleteOnClose)
                self.title.setSizePolicy(QSizePolicy.Minimum,
                                         QSizePolicy.Minimum)
                self.title.setText(self.title_text)
                self.title_box.addWidget(self.title)
                self.title_box.addStretch(1)
        else:
            # orb.log.debug('* [pgxo] no title label -- adding ...')
            self.title = QLabel()
            self.title.setAttribute(Qt.WA_DeleteOnClose)
            self.title.setSizePolicy(QSizePolicy.Minimum,
                                     QSizePolicy.Minimum)
            self.title_text = get_object_title(self.obj, new=self.new)
            self.title.setText(self.title_text)
            self.title_box.addWidget(self.title)
            self.title_box.addStretch(1)
        if not getattr(self, 'class_label', None):
            # orb.log.debug('* [pgxo] no class_label -- adding ...')
            self.class_label = SizedButton(self.cname, color='green')
            self.title_box.addWidget(self.class_label, alignment=Qt.AlignRight)
        if need_title_box:
            self.vbox.addLayout(self.title_box)
        tab_names = ['main', 'info', 'narrative', 'admin']
        if self.panels:
            self.tab_names = [name for name in tab_names if name in self.panels]
        else:
            self.tab_names = tab_names
        cname = self.obj.__class__.__name__
        # insert parameter panels if appropriate
        n_of_parm_panels = 1
        if ((not self.panels or (self.panels and 'parameters' in self.panels))
            and orb.is_a(self.obj, 'Modelable')
            and not cname in PGXN_HIDE_PARMS):
            # All subclasses of Modelable except the ones in PGXN_HIDE_PARMS
            # get a 'parameters' panel
            self.tab_names.insert(0, 'parameters')
        # insert data panels if appropriate
        if ((not self.panels or (self.panels and 'data' in self.panels))
            and orb.is_a(self.obj, 'Modelable')
            and not cname in PGXN_HIDE_PARMS):
            # All subclasses of Modelable except the ones in PGXN_HIDE_PARMS
            # get a 'data' panel
            # First find the data elements to be displayed for this object ...
            de_dict = data_elementz.get(self.obj.oid) or {}
            # honor the ordering of data elements in "default_data_elements",
            # for any that are present, then add the rest in sort order
            deids = []
            for deid in (state.get('default_data_elements') or []):
                if deid in de_dict:
                    deids.append(deid)
            for deid in sorted(list(de_dict)):
                if deid not in deids:
                    deids.append(deid)
            # orb.log.debug('  [pgxo] data elements: {}'.format(deids))
            data_panel_contents = []
            # only allow PARMS_NBR - 3 data elements on first data panel before
            # beginning the pagination algorithm ...
            if len(deids) > PARMS_NBR - 3:
                # pre-define the contents of the data panels ...
                des = []
                n = 0
                for deid in deids:
                    de_type = (de_defz.get(deid) or {}).get('range_datatype')
                    if de_type == 'text':
                        n += 2
                    else:
                        n += 1
                    if n < PARMS_NBR:
                        des.append(deid)
                    else:
                        data_panel_contents.append(des)
                        des = [deid]
                        n = 1
                    # if we get to the end, make sure to include the last one
                    if deid == deids[-1] and des not in data_panel_contents:
                        data_panel_contents.append(des)
                # number of allowed data elements on a panel depends on how
                # many of the data elements are "text" (large text fields)
                n_of_data_panels = len(data_panel_contents)
                # orb.log.debug('  [pgxo] data panels: {}'.format(
                                                        # n_of_data_panels))
                for i in range(n_of_data_panels):
                    self.tab_names.insert(n_of_parm_panels + i, f'data_{i+1}')
            else:
                self.tab_names.insert(n_of_parm_panels, 'data')
        # destroy button box and current tab pages, if they exist
        if hasattr(self, 'bbox'):
            self.bbox.hide()
            self.vbox.removeWidget(self.bbox)
            self.bbox.parent = None
            for tab_name in self.tab_names:
                if hasattr(self, tab_name+'_tab'):
                    tab = getattr(self, tab_name+'_tab')
                    tab.parent = None
            # NOTE: TBD whether the whole tab widget needs to be removed -- for
            # now, just clear the pages
            self.tabs.clear()
        # create new tab pages
        # TODO:  make tab pages scrollable, just in case
        self.editable_widgets = {}
        self.d_widgets = {}
        self.d_widget_values = {}
        self.d_widget_actions = {}
        self.p_widgets = {}
        self.p_widget_values = {}
        self.p_widget_actions = {}
        self.u_widgets = {}
        self.u_widget_values = {}
        self.previous_units = {}
        perms = get_perms(self.obj)
        for tab_name in self.tab_names:
            # The purpose of the tabs is to split the class's fields up so it
            # is not necessary to scroll at all.
            # TODO:  wrap tabs if necessary
            # The basic algorithm is steps [1], [2], and [3] below ...
            # TODO:  a 'prefs' capability to override MAIN_VIEWS.
            if tab_name.startswith('parameters'):
                sufs = ('1', '2', '3', '4', '5', '6', '7', '8', '9')
                if tab_name.endswith(sufs):
                    n = int(tab_name[-1])
                else:
                    n = None
                parm_form = ParameterForm(self.obj, pgxo=self, view=self.view,
                                          mask=self.mask, noctgcy=self.noctgcy,
                                          seq=n, parent=self)
                parm_form.obj_modified.connect(self.on_object_mod)
                setattr(self, tab_name+'_tab', parm_form)
            elif tab_name.startswith('data'):
                sufs = ('1', '2', '3', '4', '5', '6', '7', '8', '9')
                if tab_name.endswith(sufs):
                    n = int(tab_name[-1])
                else:
                    n = None
                pgxn_form = PgxnForm(self.obj, 'data', pgxo=self,
                                     view=self.view, mask=self.mask, seq=n,
                                     noctgcy=self.noctgcy,
                                     data_panel_contents=data_panel_contents,
                                     parent=self)
                pgxn_form.obj_modified.connect(self.on_object_mod)
                setattr(self, tab_name+'_tab', pgxn_form)
            else:
                pgxn_form = PgxnForm(self.obj, tab_name, pgxo=self,
                                     view=self.view, main_view=self.main_view,
                                     mask=self.mask, noctgcy=self.noctgcy,
                                     idvs=self.all_idvs,
                                     requireds=self.required, parent=self)
                pgxn_form.obj_modified.connect(self.on_object_mod)
                setattr(self, tab_name+'_tab', pgxn_form)
            this_tab = getattr(self, tab_name+'_tab')
            self.editable_widgets.update(this_tab.editable_widgets)
            self.d_widgets.update(this_tab.d_widgets)
            self.d_widget_values.update(this_tab.d_widget_values)
            self.d_widget_actions.update(this_tab.d_widget_actions)
            self.p_widgets.update(this_tab.p_widgets)
            self.p_widget_values.update(this_tab.p_widget_values)
            self.p_widget_actions.update(this_tab.p_widget_actions)
            self.u_widgets.update(this_tab.u_widgets)
            self.u_widget_values.update(this_tab.u_widget_values)
            self.previous_units.update(this_tab.previous_units)
            # orb.log.debug('* [pgxo] adding tab: %s' % tab_name)
            self.tabs.addTab(this_tab, tab_name)
        if self.embedded:
            if self.edit_mode:
                # Cancel button cancels edits and switches to view mode
                self.bbox = QDialogButtonBox(QDialogButtonBox.Cancel)
                if hasattr(self, 'edit_button'):
                    # if switching to edit mode, don't need 'Edit' button
                    try:
                        self.bbox.removeButton(self.edit_button)
                    except:
                        # C++ object went away?
                        pass
                self.save_button = self.bbox.addButton('Save',
                                                   QDialogButtonBox.ActionRole)
                # -------------------------------------------------------------
                # NOTE: for now, disallow deletions when offline -- this may
                # change in the future but implications can be complex.
                # -------------------------------------------------------------
                if ('delete' in perms and self.enable_delete and
                    state.get('connected')):
                    self.delete_button = self.bbox.addButton('Delete',
                                                   QDialogButtonBox.ActionRole)
            else:
                self.bbox = QDialogButtonBox()
                if (not self.view_only and 'modify' in perms
                    and not getattr(self.obj, 'frozen', False)):
                        self.edit_button = self.bbox.addButton('Edit',
                                                   QDialogButtonBox.ActionRole)
        else:
            # not embedded -> external dialog
            self.modal_mode = True
            # orb.log.debug('* [pgxo] external window: always modal mode)')
            if self.edit_mode:
                # orb.log.debug('  [pgxo] setting up edit mode ...')
                # Cancel button cancels edits and switches to view mode
                self.bbox = QDialogButtonBox(QDialogButtonBox.Cancel)
                # when not embedded, only show "Save and Close" -- a save()
                # will often cause refreshes that force pgxnobject to close.
                # self.save_button = self.bbox.addButton('Save',
                                               # QDialogButtonBox.ActionRole)
                self.save_and_close_button = self.bbox.addButton(
                                               'Save and Close',
                                               QDialogButtonBox.ActionRole)
                # -------------------------------------------------------------
                # NOTE: for now, disallow deletions when offline -- this may
                # change in the future but implications can be complex.
                # -------------------------------------------------------------
                if ('delete' in perms and self.enable_delete
                    and state.get('connected')):
                    self.delete_button = self.bbox.addButton('Delete',
                                               QDialogButtonBox.ActionRole)
            else:
                # orb.log.debug('            setting up view mode ...')
                self.bbox = QDialogButtonBox()
                # orb.log.debug('            checking perms ...')
                if (not self.view_only and 'modify' in perms
                    and not getattr(self.obj, 'frozen', False)):
                    # orb.log.debug('            "modify" in perms --')
                    # orb.log.debug('            adding "edit" button ...')
                    self.edit_button = self.bbox.addButton('Edit',
                                               QDialogButtonBox.ActionRole)
            self.close_button = self.bbox.addButton(QDialogButtonBox.Close)
            self.close_button.clicked.connect(self.on_close)
        self.vbox.addWidget(self.tabs)
        self.vbox.setStretch(1, 1)
        self.vbox.addWidget(self.bbox)
        self.create_connections()
        # orb.log.debug('* [pgxo] editable_widgets: {}'.format(
                                        # str(list(self.editable_widgets))))
        # orb.log.debug('* [pgxo] parameter_widgets: {}'.format(
                                        # str(list(self.p_widgets))))
        # epw = [pid for pid in self.p_widgets
               # if hasattr(self.p_widgets[pid], 'get_value')]
        # orb.log.debug(f'* [pgxo] editable parameter_widgets: {epw}')
        if ('id' in self.editable_widgets
            and self.cname == 'DataElementDefinition'):
            self.id_widget = self.editable_widgets['id']
            self.id_widget.textEdited.connect(self.on_ded_id_edited)
        if ('name' in self.editable_widgets
            and self.cname == 'DataElementDefinition'):
            self.name_widget = self.editable_widgets['name']
            self.name_widget.textEdited.connect(self.on_ded_name_edited)
        # self.adjustSize()
        if len(self.tab_names) > 7:
            # if there are more than 7 tabs, add width for each extra tab
            new_width = 500 + 80 * (len(self.tab_names) - 7)
            self.resize(new_width, self.height())
        self.set_current_tab()
        self.setLayout(self.vbox)
        if not getattr(self, 'toolbar', None):
            self.init_toolbar()
        if not getattr(self, 'main_panel', None):
            self.main_panel = QWidget()
        self.vbox.addWidget(self.main_panel)
        self.update()

    def on_object_mod(self, oid):
        self.obj_modified.emit(oid)
        dispatcher.send(signal='modified object', obj=self.obj)

    def init_toolbar(self):
        self.toolbar = QToolBar('Tools')
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        if isinstance(self.obj, orb.classes['HardwareProduct']):
            self.freeze_action = self.create_action('Freeze',
                                    slot=self.freeze, icon='freeze_16',
                                    tip='Freeze this object',
                                    modes=['edit', 'view'])
            self.frozen_action = self.create_action('Frozen',
                                    slot=self.frozen, icon='frozen_16',
                                    tip='This object is frozen',
                                    modes=['edit', 'view'])
            self.thaw_action = self.create_action('Thaw',
                                    slot=self.thaw, icon='thaw_16',
                                    tip='Thaw this object',
                                    modes=['edit', 'view'])
            self.where_used_action = self.create_action('Where\nUsed',
                            slot=self.show_where_used, icon='system',
                            tip='Assemblies in which this object occurs ...',
                            modes=['edit', 'view'])
            self.project_usage_action = self.create_action('Project\nUsage',
                            slot=self.show_projects_using, icon='favicon',
                            tip='Projects using this product ...',
                            modes=['edit', 'view'])
            # only users who can modify an object can 'freeze' it
            self.toolbar.addAction(self.freeze_action)
            self.freeze_action.setVisible(False)
            self.toolbar.addAction(self.frozen_action)
            if self.obj.frozen:
                orb.log.debug('            object is frozen.')
                self.frozen_action.setVisible(True)
            else:
                orb.log.debug('            object is NOT frozen.')
                self.frozen_action.setVisible(False)
            self.toolbar.addAction(self.thaw_action)
            self.thaw_action.setVisible(False)
            self.toolbar.addAction(self.where_used_action)
            self.toolbar.addAction(self.project_usage_action)
            perms = get_perms(self.obj)
            # orb.log.debug('            user perms: {}'.format(str(perms)))
            if 'modify' in perms:
                if self.obj.frozen:
                    self.freeze_action.setVisible(False)
                else:
                    # orb.log.debug('            object is NOT frozen.')
                    self.frozen_action.setVisible(False)
                    self.freeze_action.setVisible(True)
                # only users who can modify an object can create a new version
                # self.new_version_action = self.create_action('new version',
                                    # slot=self.on_new_version, icon='new_part',
                                    # tip='Create new version by cloning',
                                    # modes=['edit', 'view'])
                # self.toolbar.addAction(self.new_version_action)
            if (self.obj.frozen and state.get('connected') and
                is_global_admin(orb.get(state.get('local_user_oid')))):
                # only a global admin can "thaw"
                self.thaw_action.setVisible(True)
            self.clone_action = self.create_action('Clone',
                                    slot=self.on_clone, icon='clone_16',
                                    tip='Clone this object',
                                    modes=['edit', 'view'])
            self.toolbar.addAction(self.clone_action)
            self.clone_action.setEnabled(True)
        if isinstance(self.obj, (orb.classes['HardwareProduct'],
                                 orb.classes['Software'],
                                 orb.classes['Model'],
                                 orb.classes['Requirement'],
                                 )):
            self.models_and_docs_info_action = self.create_action(
                            "Models\nand Docs",
                            slot=self.models_and_docs_info,
                            icon="info",
                            tip="Show info on related Models and Documents")
            self.toolbar.addAction(self.models_and_docs_info_action)
            self.models_and_docs_info_action.setVisible(False)
            # can only add models or docs if the user has "modify" permissions
            # for the object
            if 'add models' in get_perms(self.obj):
                # orb.log.debug('* user has "add models" permission.')
                self.add_model_action = self.create_action(
                                "Add\nModel",
                                slot=self.add_model,
                                icon="lander",
                                tip="Upload a Model File")
                self.toolbar.addAction(self.add_model_action)
                self.add_model_action.setVisible(True)
            else:
                orb.log.debug('* user does not have "add models" permission.')
            if 'add docs' in get_perms(self.obj):
                # orb.log.debug('* user has "add docs" permission.')
                self.add_doc_action = self.create_action(
                                "Add\nDocument",
                                slot=self.add_doc,
                                icon="new_doc",
                                tip="Upload a Document File")
                self.toolbar.addAction(self.add_doc_action)
                self.add_doc_action.setVisible(True)
            else:
                orb.log.debug('* user does not have "add docs" permission.')
            if sys.platform != 'darwin':
                # cad viewer currently not working on Mac
                self.view_cad_action = self.create_action(
                                        "View CAD",
                                        slot=self.display_step_models,
                                        icon="box",
                                        tip="View CAD Model (from STEP File)")
                self.toolbar.addAction(self.view_cad_action)
                self.view_cad_action.setVisible(False)
            # =================================================================
            # check for existence of models, and then MCAD models, to determine
            # whether to make "models_and_docs_info_action" and "view_cad_action"
            # visible or not ...
            models = self.get_models()
            if models or self.obj.doc_references:
                # orb.log.debug('* pgxno: object has models or docs ...')
                if hasattr(self, 'models_and_docs_info_action'):
                    try:
                        self.models_and_docs_info_action.setVisible(True)
                    except:
                        # oops, C++ object got deleted
                        pass
                # NOTE: a given product may have more than one MCAD model --
                # e.g., a fully detailed model and one or more "simplified"
                # models -- so the "view cad" action should display a dialog
                # with info about all the MCAD models ...
                mcad_models = models.get('MCAD')
                if mcad_models:
                    # orb.log.debug('* pgxno: MCAD model(s) found ...')
                    step_fpaths = [orb.get_mcad_model_file_path(m)
                                   for m in mcad_models]
                    if step_fpaths and hasattr(self, 'view_cad_action'):
                        # orb.log.debug('  STEP file(s) found.')
                        try:
                            self.view_cad_action.setVisible(True)
                        except:
                            # oops, C++ object got deleted
                            pass
                    else:
                        # orb.log.debug('  no STEP files found.')
                        pass
            else:
                # orb.log.debug('* pgxno: object has no models or docs ...')
                if hasattr(self, 'models_and_docs_info_action'):
                    try:
                        self.models_and_docs_info_action.setVisible(False)
                    except:
                        # oops, C++ object got deleted
                        pass
            # =================================================================
        if (isinstance(self.obj, orb.classes['HardwareProduct'])
            and self.obj.oid in componentz):
            # the "Mini MEL" action only makes sense for white box objects
            self.mini_mel_action = self.create_action('Mini\nMEL',
                                    slot=self.display_mini_mel, icon='data',
                                    tip='Generate a mini-MEL for this object',
                                    modes=['edit', 'view'])
            self.toolbar.addAction(self.mini_mel_action)
        self.vbox.insertWidget(0, self.toolbar)

    def create_action(self, text, slot=None, icon=None, tip=None,
                      checkable=False, modes=None):
        action = QAction(text, self)
        if icon is not None:
            icon_file = icon + state.get('icon_type', '.png')
            icon_dir = state.get('icon_dir', os.path.join(orb.home, 'icons'))
            icon_path = os.path.join(icon_dir, icon_file)
            action.setIcon(QIcon(icon_path))
        if tip is not None:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        if slot is not None:
            action.triggered.connect(slot)
        if checkable:
            action.setCheckable(True)
        if modes:
            # modes in which action applies: 'view', 'edit'; default: 'view'
            for mode in modes:
                self.mode_widgets[mode].add(action)
            else:
                self.mode_widgets['view'].add(action)
        return action

    def get_models(self):
        """
        Returns a dict mapping "Model.type_of_model" (ModelType) id to the
        models of that type for all models of self.obj.
        """
        model_instances = getattr(self.obj, 'has_models', [])
        model_dict = {}
        if model_instances:
            for m in model_instances:
                mtype_id = getattr(m.type_of_model, 'id', 'UNKNOWN')
                if mtype_id in model_dict:
                    model_dict[mtype_id].append(m)
                else:
                    model_dict[mtype_id] = [m]
        return model_dict

    def add_model(self, model_type_id=None):
        dlg = ModelImportDialog(of_thing=self.obj, model_type_id=model_type_id,
                                parent=self)
        dlg.show()

    def add_doc(self, model_type_id=None):
        dlg = DocImportDialog(rel_obj=self.obj, parent=self)
        dlg.show()

    def models_and_docs_info(self):
        """
        Display a dialog with information about all available models and
        documents related to the currently selected product.
        """
        if (self.obj and
            (getattr(self.obj, 'has_models', []) or
             getattr(self.obj, 'doc_references', []))):
            # orb.log.debug('* pgxno: models and docs info dlg ...')
            dlg = ModelsAndDocsInfoDialog(self.obj, parent=self)
            dlg.show()
        else:
            orb.log.debug('* pgxno: object has no models or docs.')

    def display_step_models(self):
        """
        Display the STEP models associated with the current self.subject (a
        Modelable instance, which may or may not have a STEP model). If there
        is only one, simply open a Model3DViewer with that one; if more than
        one, open a dialog with information about all and offer to display a
        selected one.
        """
        # TODO: display a dialog if multiple STEP models ...
        # ... if only one, just display it in the viewer ...
        models = self.get_models()
        mcad_models = models.get("MCAD")
        fpath = ''
        fpaths = []
        if mcad_models:
            # orb.log.debug('  MCAD models found:')
            for m in mcad_models:
                # orb.log.debug(f'      - model: "{m.id}"')
                fpath = orb.get_mcad_model_file_path(m)
                fpaths.append(fpath)
                if fpath:
                    orb.log.debug(f'        step file path: {fpath}')
                else:
                    orb.log.debug('        no step file found.')
                orb.log.debug(f'      - {fpath}')
            # orb.log.debug(f'  fpaths: {fpaths}')
        else:
            orb.log.debug('  no MCAD models found.')
            return
        if fpaths:
            fpath = fpaths[0]
            # orb.log.debug(f'  step file: "{fpath}"')
        try:
            if fpath:
                viewer = Model3DViewer(fpath=fpath, parent=self)
                viewer.show()
        except:
            orb.log.debug('  CAD model not found or not in STEP format.')
            pass

    def freeze(self, remote=False):
        """
        Freeze a Product, making it read-only.  NOTE: this action should only
        be accessible to users who have 'modify' permission on the Product.
        """
        orb.log.debug('* freeze called ...')
        if not orb.is_a(self.obj, 'Product'):
            orb.log.debug('  object is not a Product, cannot be frozen.')
            return
        if self.obj.frozen:
            orb.log.debug('  object is already frozen.')
            return
        if not state.get('connected'):
            orb.log.debug('  not connected -- cannot freeze.')
            return
        user = orb.get(state.get('local_user_oid'))
        global_admin = is_global_admin(user)
        # check whether object is white box or black box
        if self.obj.oid in componentz:
            orb.log.debug('  white box, checking for non-frozen components ..')
            # white box -- all components must be frozen
            bom = orb.get_bom_from_compz(self.obj)
            not_frozens = [obj for obj in bom if not obj.frozen]
            if not_frozens:
                orb.log.debug('  non-frozens found, checking permissions ..')
                if global_admin:
                    # if global admin, offer to recursively freeze all
                    # non-frozen components of this object ...
                    dlg = FreezingDialog(self.obj, not_frozens, parent=self)
                    if dlg.exec_():
                        orb.log.debug('  - dialog accepted.')
                        orb.log.debug('    freezing item and components ...')
                        self.freeze_action.setVisible(False)
                        self.frozen_action.setVisible(True)
                        self.obj.frozen = True
                        for obj in not_frozens:
                            obj.frozen = True
                        # only a global admin can "thaw"
                        self.thaw_action.setVisible(True)
                        oids = [self.obj.oid] + [o.oid for o in not_frozens]
                        dispatcher.send(signal="freeze", oids=oids)
                        self.build_from_object()
                        return
                    else:
                        orb.log.debug('  - dialog cancelled -- no freeze.')
                else:
                    # if not global admin, check whether user has edit
                    # permission for all not_frozens -- if so, offer to
                    # recursively freeze all non-frozen components; if not,
                    # notify that object cannot be frozen.
                    cannot_freezes = [o for o in not_frozens
                                      if 'modify' not in get_perms(o)]
                    if cannot_freezes:
                        dlg = CannotFreezeDialog(self.obj, cannot_freezes,
                                                 parent=self)
                        if dlg.exec_():
                            orb.log.debug('  - cannot freeze, accepted.')
                    else:
                        dlg = FreezingDialog(self.obj, not_frozens,
                                             parent=self)
                        if dlg.exec_():
                            orb.log.debug('  - dialog accepted.')
                            orb.log.debug('    freezing item and components.')
                            self.freeze_action.setVisible(False)
                            self.frozen_action.setVisible(True)
                            self.obj.frozen = True
                            for obj in not_frozens:
                                obj.frozen = True
                            # only a global admin can "thaw"
                            self.thaw_action.setVisible(False)
                            oids = [self.obj.oid] + [o.oid
                                                     for o in not_frozens]
                            dispatcher.send(signal="freeze", oids=oids)
                            self.build_from_object()
                            return
                        else:
                            orb.log.debug('  - dialog cancelled -- no freeze.')
            else:
                orb.log.debug('  all components are frozen ...')
                perms = get_perms(self.obj)
                if 'modify' in perms:
                    orb.log.debug(f'  freezing {self.obj.id}')
                    self.freeze_action.setVisible(False)
                    self.frozen_action.setVisible(True)
                    self.obj.frozen = True
                    if global_admin:
                        # only a global admin can "thaw"
                        self.thaw_action.setVisible(True)
                    dispatcher.send(signal="freeze", oids=[self.obj.oid])
                    self.build_from_object()
                else:
                    orb.log.debug('  user does not have permission to freeze.')
        else:
            # black box -- only look at this Product's permissions
            perms = get_perms(self.obj)
            if 'modify' in perms:
                orb.log.debug(f'  freezing {self.obj.id}')
                self.freeze_action.setVisible(False)
                self.frozen_action.setVisible(True)
                self.obj.frozen = True
                if global_admin:
                    # only a global admin can "thaw"
                    self.thaw_action.setVisible(True)
                dispatcher.send(signal="freeze", oids=[self.obj.oid])
                self.build_from_object()
            else:
                orb.log.debug('  user does not have permission to freeze.')

    def on_remote_frozen(self, frozen_oids=None):
        """
        Handle "remote: frozen" signal, sent by pangalaxian handler of pubsub
        "freeze completed" message.  When this message is sent, the frozen
        objects have already been committed as frozen by the pangalaxian
        handler.
        """
        orb.log.debug('* pgxnobj received "remote: frozen" signal')
        if isinstance(frozen_oids, list):
            orb.log.debug(f'  for oids: {str(frozen_oids)}')
            orb.log.debug(f'  my obj oid: {self.obj.oid}')
        else:
            orb.log.debug('  bad format or no oids.')
            return
        if self.obj.oid in frozen_oids:
            orb.log.debug('  aha, my object is in there ...')
            # refresh our "obj" from the database
            oid = self.obj.oid
            self.obj = orb.get(oid)
            html = f'<b>{self.obj.name}</b> [{self.obj.id}] '
            html += 'has been <b>frozen</b>.'
            notice = QMessageBox(QMessageBox.Information, 'Frozen',
                                 html, QMessageBox.Ok, self)
            if notice.exec_():
                orb.log.debug('  notice accepted.')
                self.freeze_action.setVisible(False)
                self.frozen_action.setVisible(True)
                user = orb.get(state.get('local_user_oid'))
                if is_global_admin(user):
                    self.thaw_action.setVisible(True)
                if ((not self.edit_mode) and hasattr(self, 'edit_button')
                     and hasattr(self, 'bbox')):
                    try:
                        self.bbox.removeButton(self.edit_button)
                    except:
                        # C++ object went away?
                        # pass
                        orb.log.debug('  removeButton failed for edit button.')
                orb.log.debug('  attempting self.update()...')
                try:
                    self.update()
                    orb.log.debug('  ... succeeded.')
                except:
                    # C++ obj got deleted
                    orb.log.debug('  ... failed.')

    def on_remote_thawed(self, oids=None):
        """
        Handle "remote: thawed" signal, sent by pangalaxian handler of pubsub
        "thawed" message.  When this message is sent, the thawed objects have
        already been committed as thawed by the pangalaxian handler.
        """
        orb.log.debug('* pgxnobj received "remote: thawed" signal on:')
        orb.log.debug(f'  {str(oids)}')
        orb.log.debug(f'  my obj oid: {self.obj.oid}')
        oids = oids or []
        if self.obj.oid in oids:
            orb.log.debug('  aha, my object is in there ...')
            # refresh our "obj" from the database
            oid = self.obj.oid
            self.obj = orb.get(oid)
            html = f'<b>{self.obj.name}</b> [{self.obj.id}] '
            html += 'has been <b>thawed</b>.'
            notice = QMessageBox(QMessageBox.Information, 'Thawed',
                                 html, QMessageBox.Ok, self)
            if notice.exec_():
                orb.log.debug('  notice accepted.')
                self.frozen_action.setVisible(False)
                self.thaw_action.setVisible(False)
                perms = get_perms(self.obj)
                if 'modify' in perms:
                    self.freeze_action.setVisible(True)
                    edit_button = getattr(self, 'edit_button', None) or None
                    if ((edit_button is None) or
                         not (edit_button in self.bbox.buttons())):
                        self.edit_button = self.bbox.addButton('Edit',
                                               QDialogButtonBox.ActionRole)
                        self.edit_button.clicked.connect(self.on_edit)
                orb.log.debug('  attempting self.update()...')
                try:
                    self.update()
                    orb.log.debug('  ... succeeded.')
                except:
                    # C++ obj got deleted
                    orb.log.debug('  ... failed.')

    def frozen(self):
        pass

    def thaw(self):
        """
        Thaw a frozen Product.  NOTE: this action is only accessible to a
        Global Administrator.
        """
        # TODO:  if the Product is used in any frozen assemblies, require that
        # the assemblies be thawed first.
        orb.log.debug('* thaw action called ...')
        # notice = None
        thaw_permitted = False
        if (orb.is_a(self.obj, 'Product')
            and self.obj.frozen):
            if getattr(self.obj, 'where_used', None):
                assemblies = [acu.assembly for acu in self.obj.where_used]
                frozens = [a for a in assemblies if a.frozen]
                if frozens:
                    orb.log.debug('  used in one or more frozen assembly ...')
                    orb.log.debug('  thaw confirmation required.')
                    txt = 'Warning: thawing this Product may violate CM and\n'
                    txt += 'should only be used for essential corrections.\n'
                    txt += 'It is used as a component in the following '
                    txt += 'frozen assemblies:'
                    notice = QMessageBox(QMessageBox.Warning, 'Caution!', txt,
                                         QMessageBox.Ok | QMessageBox.Cancel,
                                         self)
                    text = '<p><ul>{}</ul></p>'.format('\n'.join(
                               ['<li><b>{}</b><br>({})</li>'.format(
                               a.name, a.id) for a in assemblies if a]))
                    notice.setInformativeText(text)
                    if notice.exec_():
                        orb.log.debug('  thaw confirmed ...')
                        thaw_permitted = True
                else:
                    thaw_permitted = True
            else:
                thaw_permitted = True
        else:
            orb.log.debug('  not a Product or not frozen; cannot thaw.')
        if thaw_permitted:
            orb.log.debug('  thawing ...')
            self.freeze_action.setVisible(True)
            self.frozen_action.setVisible(False)
            self.thaw_action.setVisible(False)
            self.obj.frozen = False
            dispatcher.send(signal="thaw", oids=[self.obj.oid])
            self.build_from_object()

    def show_where_used(self):
        """
        Display the names of assemblies in which the object occurs as a
        component.
        """
        # orb.log.debug('* pgxno: show_where_used()')
        info = ''
        all_comps = set(reduce(lambda x,y: x+y, componentz.values()))
        all_comp_oids = [comp.oid for comp in all_comps]
        # orb.log.debug(f'  all comp oids found ({len(all_comp_oids)})')
        if self.obj.oid in all_comp_oids:
            # orb.log.debug(f'  obj oid ({self.obj.oid}) found in all_comp_oids')
            assmb_oids = [oid for oid in componentz
                          if self.obj.oid in
                          [comp.oid for comp in componentz[oid]]]
            # orb.log.debug(f'  assembly oids where used: {assmb_oids}')
            assemblies = [orb.get(oid) for oid in set(assmb_oids)]
            # assmb_ids = [a.id for a in assemblies]
            # orb.log.debug(f'  assembly ids where used: {assmb_ids}')
            txt = 'This product is used as a component '
            txt += 'in the following assemblies:'
            assmb_info = '<p><b>Assemblies:</b></p>'
            assmb_info += '<p><ul>{}</ul></p>'.format('\n'.join(
                       ['<li><b>{}</b><br>({})</li>'.format(
                       a.name, a.id) for a in assemblies if a]))
            txt += assmb_info
        else:
            txt = 'This product is not used in any assemblies.'
        notice = QMessageBox(QMessageBox.Information, 'Where Used',
                             txt, QMessageBox.Ok, self)
        notice.setInformativeText(info)
        notice.show()

        # ====================================================================
        # ORM (sqlalchemy) based implementation
        # ====================================================================
        # where_used = getattr(self.obj, 'where_used', None)
        # if where_used:
            # assemblies = set([acu.assembly for acu in self.obj.where_used])
            # # if assemblies and len(assemblies) > 0:
            # txt = 'This product is used as a component '
            # txt += 'in the following assemblies:'
            # assmb_info = '<p><b>Assemblies:</b></p>'
            # assmb_info += '<p><ul>{}</ul></p>'.format('\n'.join(
                       # ['<li><b>{}</b><br>({})</li>'.format(
                       # a.name, a.id) for a in assemblies if a]))

        # projects_using = getattr(self.obj, 'projects_using_system', None)
        # if projects_using:
            # txt = 'This product is used as a top-level system '
            # txt += 'in the following project(s):'
            # p_ids = [psu.project.id for psu in self.obj.projects_using_system]
            # proj_info = '<p><b>A Top Level System in Projects:</b></p>'
            # proj_info += '<p><ul>{}</ul></p>'.format('\n'.join(
                                      # ['<li><b>{}</b></li>'.format(p_id) for
                                      # p_id in p_ids]))
        # if where_used and projects_using:
            # txt = 'This product is used as a component '
            # txt += 'in the following assemblies and '
            # txt += 'as a top-level system '
            # txt += 'in the following project(s):'
            # info = assmb_info + proj_info
        # elif where_used:
            # info = assmb_info
        # elif projects_using:
            # info = proj_info
        # else:
            # txt = 'This product is not used in any assemblies or projects.'
        # notice = QMessageBox(QMessageBox.Information, 'Where Used',
                             # txt, QMessageBox.Ok, self)
        # notice.setInformativeText(info)
        # notice.show()
        # ====================================================================

    def show_projects_using(self):
        info = ''
        projects = get_all_project_usages(self.obj)
        if getattr(self.obj, 'projects_using_system', None):
            system_in_projects = set(psu.project for psu
                                     in self.obj.projects_using_system)
            projects |= system_in_projects
        if projects:
            p_ids = [project.id for project in projects]
            proj_info = '<p><ul>{}</ul></p>'.format('\n'.join(
                                      ['<li><b>{}</b></li>'.format(p_id) for
                                      p_id in p_ids]))
            txt = 'This product is used as a component '
            txt += 'or system in the following project(s):'
            info = proj_info
        else:
            txt = 'This product is not used in any projects.'
        notice = QMessageBox(QMessageBox.Information, 'Project Usage',
                             txt, QMessageBox.Ok, self)
        notice.setInformativeText(info)
        notice.show()

    def on_clone(self):
        """
        Handle 'clone' action.
        """
        orb.log.debug('* [pgxo] on_clone()')
        new_obj = None
        if orb.is_a(self.obj, 'Product'):
            if self.obj.components:
                # if the product has components, bring up the cloning dlg. with
                # options to create white box or black box clone ...
                orb.log.debug('  - components -> show dialog ...')
                dlg = CloningDialog(self.obj, parent=self)
                if dlg.exec_():
                    # orb.log.debug('  - dialog accepted.')
                    new_obj = getattr(dlg, 'new_obj', None)
                    orb.log.debug(f'    got clone [a]: "{new_obj.id}"')
            else:
                orb.log.debug('  - black box -> cloning ...')
                new_obj = clone(self.obj, id='new-id', version='1',
                                version_sequence=1)
                orb.log.debug(f'    got black box clone [b]: "{new_obj.id}"')
        else:
            new_obj = clone(self.obj, id='new-id')
        if new_obj and not isinstance(new_obj, orb.classes['HardwareProduct']):
            # if not a HardwareProduct, just replace the current object in the
            # viewer with the clone ...
            self.obj = new_obj
            self.build_from_object()
            self.on_edit()
        elif (new_obj and isinstance(new_obj, orb.classes['HardwareProduct'])
              and not self.component):
            # if a HardwareProduct and not in "component mode", call close(),
            # because component mode will be triggered and the embedded editor
            # will be used ...
            try:
                self.close()
            except:
                # we lost our C++ object
                pass

    def display_mini_mel(self):
        """
        Display a "Mini MEL" for the current object when 'Mini MEL' action is
        selected.
        """
        try:
            dlg = MiniMelDialog(self.obj, parent=self)
            dlg.show()
        except:
            orb.log.debug('* MiniMEL encountered an exception.')

    def on_new_version(self):
        """
        Respond to 'new version' action by cloning the current object using the
        same 'id' and incremented version.  NOTE: only applicable to subclasses
        of 'Product' -- "new version" menu option will not be displayed
        otherwise.
        """
        if not orb.is_a(self.obj, 'Product'):
            msg = '"{}" is not a Product -> not versionable.'.format(
                                                            self.obj.id)
            orb.log.debug('* [pgxo] on_new_version(): {}'.format(msg))
            return
        if not isinstance(self.obj.version_sequence, int):
            self.obj.version_sequence = 1
        ver_seq = self.obj.version_sequence + 1
        new_obj = clone(self.obj, id=self.obj.id, version_sequence=ver_seq)
        orb.save([new_obj])
        self.obj = new_obj
        self.go_to_tab = 3
        self.build_from_object()
        self.on_edit()

    @property
    def ded_disallowed_names(self):
        """
        List of lower-case versions of all "id" and "name" attributes of all
        current ParameterDefinitions and DataElementDefinitions.
        """
        names = list(parm_defz) + list(de_defz)
        names += [pd['name'] for pd in parm_defz.values()]
        names += [ded['name'] for ded in de_defz.values()]
        return [n.lower() for n in names]

    def set_current_tab(self):
        if hasattr(self, 'tabs'):
            if (getattr(self, 'tab_names', None)
                and self.go_to_tab < len(self.tab_names)):
                # tab_name = self.tab_names[self.go_to_tab]
                # orb.log.debug(f'* [pgxo] setting tab to "{tab_name}"')
                self.tabs.setCurrentIndex(self.go_to_tab)

    def on_parameters_recomputed(self):
        """
        Handler for dispatcher signal "parameters recomputed" -- updates all
        computed parameter values.
        """
        # orb.log.debug('* [pxo] got "parameters recomputed" signal ...')
        # for update of parameters / data elements
        # (note that obj may have been deleted)
        if self.obj:
            self.on_update_pgxno(mod_oids=[self.obj.oid])

    def old_on_parameters_recomputed(self):
        # orb.log.debug('* [pxo] got "parameters recomputed" signal ...')
        # [1] find all computed parameters
        parmz = parameterz.get(self.obj.oid) or {}
        pids = sorted(list(parmz), key=str.lower)  # case-independent sort
        computeds = [pid for pid in pids if parm_defz[pid].get('computed')]
        # if computeds:
            # orb.log.debug(' + found: {}'.format(str(computeds)))
        # else:
            # orb.log.debug(' + no computed parameters found.')
        # [2] find their fields and update them ...
        for pid in computeds:
            parm_widget = self.p_widgets.get(pid)
            # if parm_widget:
                # orb.log.debug(f' + found parm_widget for "{pid}"')
            # else:
                # orb.log.debug(f' + got no parm_widget for "{pid}"')
            units_widget = self.u_widgets.get(pid)
            try:
                units = units_widget.get_value()
            except:
                # C++ obj got deleted
                units = None   # use base units
            str_val = get_pval_as_str(self.obj.oid, pid, units=units)
            # orb.log.debug(f' + got str val of "{str_val}" for "{pid}"')
            if hasattr(parm_widget, 'setText'):
                # if pid == 'm[CBE]':
                    # orb.log.debug(' + parm widget has "setText()"')
                    # orb.log.debug(' + setting m[CBE] to: {str_val}')
                try:
                    parm_widget.setText(str_val)
                except:
                    # C++ obj got deleted
                    continue
        try:
            self.update()
        except:
            # C++ obj got deleted
            pass

    def on_new_object(self, obj=None, cname=''):
        if (obj and isinstance(obj, orb.classes['Acu'])
            # only add mini mel action if embedded -- crashes otherwise
            and getattr(self, 'embedded', False)
            and obj.assembly.oid == self.obj.oid
            and not hasattr(self, 'mini_mel_action')):
            self.mini_mel_action = self.create_action('Mini\nMEL',
                                    slot=self.display_mini_mel, icon='data',
                                    tip='Generate a mini-MEL for this object',
                                    modes=['edit', 'view'])
            self.toolbar.addAction(self.mini_mel_action)

    def on_update_pgxno(self, mod_oids=None):
        """
        Handler for dispatcher signal "update pgxno" -- updates all
        parameter and data element values.
        """
        # orb.log.debug('* [pxo] got "update pgxno" signal')
        # oids_list = str(mod_oids)
        # orb.log.debug(f'        on oids {oids_list}')
        # first check whether our object still exists in the db ...
        oid = getattr(self.obj, 'oid', None)
        if oid:
            self.obj = orb.get(oid)
            if not self.obj:
                return
        else:
            return
        if self.obj.oid in (mod_oids or []):
            oid = self.obj.oid
            self.obj = orb.get(oid)
            # NOTE: ugh, can't update title because its C++ obj got deleted
            # [0] make sure title is correct
            # title_text = get_object_title(self.obj)
            # self.title.setText(title_text)
            # [1] find all parameters
            parmz = parameterz.get(self.obj.oid) or {}
            pids = sorted(list(parmz), key=str.lower)  # case-independent sort
            # [2] find their fields and update them ...
            for pid in pids:
                parm_widget = self.p_widgets.get(pid)
                # if parm_widget:
                    # orb.log.debug(f' + found parm_widget for "{pid}"')
                # else:
                    # orb.log.debug(f' + got no parm_widget for "{pid}"')
                if not parm_widget:
                    continue
                units_widget = self.u_widgets.get(pid)
                try:
                    units = units_widget.get_value()
                except:
                    # C++ obj got deleted
                    units = None   # use base units
                str_val = get_pval_as_str(self.obj.oid, pid, units=units)
                # orb.log.debug(f' + got str val of "{str_val}" for "{pid}"')
                if hasattr(parm_widget, 'setText'):
                    # if pid == 'm[CBE]':
                        # orb.log.debug(' + parm widget has "setText()"')
                        # orb.log.debug(' + setting m[CBE] to: {str_val}')
                    try:
                        parm_widget.setText(str_val)
                    except:
                        # C++ obj got deleted
                        continue
            # try:
                # orb.log.debug('- calling self.update() for pgxno ...')
                # self.update()
            # except:
                # # C++ obj got deleted
                # orb.log.debug('  caught exception!')
                # pass

    def on_ded_id_edited(self):
        """
        Handler for textEdited signal from the "id" field for
        DataElementDefinition.
        """
        self.ded_id_modified = True
        id_val = self.id_widget.text()
        # orb.log.debug(f'* [pgxo] id = "{id_val}"')
        if id_val.lower() in self.ded_disallowed_names:
            self.id_widget.setStyleSheet('color: red')
        else:
            self.id_widget.setStyleSheet('color: green')

    def on_ded_name_edited(self):
        """
        Handler for textEdited signal from the "name" field for
        DataElementDefinition.
        """
        self.ded_name_modified = True
        name = self.name_widget.text()
        # orb.log.debug(f'* [pgxo] name = "{name}"')
        if name.lower() in self.ded_disallowed_names:
            self.name_widget.setStyleSheet('color: red')
        else:
            self.name_widget.setStyleSheet('color: green')

    def on_close(self):
        self.close()

    def create_connections(self):
        if hasattr(self, 'edit_button'):
            try:
                self.edit_button.clicked.connect(self.on_edit)
            except:
                # C++ object may have been deleted
                pass
        if hasattr(self, 'save_button'):
            try:
                self.save_button.clicked.connect(self.on_save)
            except:
                # C++ object may have been deleted
                pass
        if hasattr(self, 'save_and_close_button'):
            try:
                self.save_and_close_button.clicked.connect(
                                        self.on_save_and_close)
            except:
                # C++ object may have been deleted
                pass
        if hasattr(self, 'delete_button'):
            try:
                self.delete_button.clicked.connect(self.on_delete)
            except:
                # C++ object may have been deleted
                pass
        try:
            self.bbox.rejected.connect(self.cancel)
        except:
            # C++ object may have been deleted
            pass

    def on_edit(self):
        # orb.log.info('* [pgxo] switching to edit mode ...')
        self.edit_mode = True
        self.build_from_object()

    def on_set_tab(self, index):
        # orb.log.debug(f'* [pgxno] on_set_tab({index})')
        self.go_to_tab = index

    def on_delete(self):
        orb.log.info('* [pgxo] delete action selected ...')
        if not state.get('connected'):
            txt = 'This Product cannot be deleted:\n'
            txt += 'you are offline.'
            notice = QMessageBox(QMessageBox.Warning, 'Cannot Delete', txt,
                                 QMessageBox.Ok, self)
            notice.show()
            return
        if getattr(self.obj, 'where_used', None):
            txt = 'This Product cannot be deleted:\n'
            txt += 'it is a component in the following assemblies:'
            notice = QMessageBox(QMessageBox.Warning, 'Cannot Delete', txt,
                                 QMessageBox.Ok, self)
            assemblies = [acu.assembly for acu in self.obj.where_used]
            text = '<p><ul>{}</ul></p>'.format('\n'.join(
                           ['<li><b>{}</b><br>(oid: "{}")</li>'.format(
                           a.name, a.oid) for a in assemblies if a]))
            notice.setInformativeText(text)
            notice.show()
            return
        elif getattr(self.obj, 'projects_using_system', None):
            txt = 'This Product cannot be deleted:\n'
            txt += 'it is being used as a system in the following project(s):'
            notice = QMessageBox(QMessageBox.Warning, 'Cannot Delete', txt,
                                 QMessageBox.Ok, self)
            p_ids = [psu.project.id for psu in self.obj.projects_using_system]
            notice.setInformativeText('<p><ul>{}</ul></p>'.format('\n'.join(
                                      ['<li><b>{}</b></li>'.format(p_id) for
                                      p_id in p_ids])))
            notice.show()
            return
        elif getattr(self.obj, 'created_objects', None):
            txt = 'This Person cannot be deleted:\n'
            txt += 'they have created object(s) which must be deleted first:'
            notice = QMessageBox(QMessageBox.Warning, 'Cannot Delete', txt,
                                 QMessageBox.Ok, self)
            ids = [obj.id for obj in self.obj.created_objects]
            notice.setInformativeText('<p><ul>{}</ul></p>'.format('\n'.join(
                                      ['<li><b>{}</b></li>'.format(obj_id)
                                       for obj_id in ids])))
            notice.show()
            return
        txt = ('This will permanently delete the object -- '
               'are you really really sure?')
        confirm_dlg = QMessageBox(QMessageBox.Question, 'Delete?', txt,
                                  QMessageBox.Yes | QMessageBox.No)
        response = confirm_dlg.exec_()
        if response == QMessageBox.Yes:
            obj_oid = self.obj.oid
            cname = self.obj.__class__.__name__
            # -----------------------------------------------------------------
            # orb.delete will add serialized object to trash
            orb.delete([self.obj])
            dispatcher.send(signal='deleted object', oid=obj_oid, cname=cname)
            # if not in component mode, we should close ...
            if not self.component:
                try:
                    self.close()
                except:
                    # lost our C++ object
                    pass

    def on_del_parameter(self, pid=None):
        delete_parameter(self.obj.oid, pid)
        # NOTE: delete_parameter() sends dispatcher signal "parm del", which
        # triggers pgxn to call rpc vger.del_parm()
        self.build_from_object()

    def on_del_de(self, deid=None):
        delete_data_element(self.obj.oid, deid)
        # NOTE: delete_data_element() sends dispatcher signal "de del", which
        # triggers pgxn to call rpc vger.del_de()
        self.build_from_object()

    def cancel(self):
        if self.edit_mode:
            txt = '* [pgxo] unsaved edits cancelled, rolling back...'
            orb.log.info(txt)
            # orb.db.rollback()
            self.edit_mode = False
            self.build_from_object()

    def closeEvent(self, event):
        txt = '* [pgxo] closing.'
        orb.log.info(txt)
        # orb.db.rollback()
        if (state.get('pgxno_oids') and
            getattr(self, 'obj', None) and
            getattr(self.obj, 'oid', None) and
            self.obj.oid in state['pgxno_oids']):
            state['pgxno_oids'].remove(self.obj.oid)
        self.close()

    # TODO:  remove -- wasn't doing anything!
    # def update_save_progress(self, name=''):
        # try:
            # if getattr(self, 'progress_dialog', None):
                # self.progress_value += 1
                # self.progress_dialog.setValue(self.progress_value)
                # self.progress_dialog.setLabelText(
                    # 'parameters cached for: {}'.format(name))
        # except:
            # # oops -- my C++ object probably got deleted
            # pass

    def on_save_and_close(self):
        self.closing = True
        self.on_save()

    def on_save(self):
        orb.log.info('* [pgxo] saving ...')
        self.edit_mode = False
        # uniqueness checks are done only for id's and names of:
        # [1] DataElementDefinitions
        # [2] Ports
        cname = self.obj.__class__.__name__
        if cname == 'DataElementDefinition':
            if 'id' in self.editable_widgets and self.ded_id_modified:
                self.id_widget = self.editable_widgets['id']
                id_value = self.id_widget.text()
                if id_value.lower() in self.ded_disallowed_names:
                    msg = f'The id "{id_value}" is already being used.'
                    notice = QMessageBox(QMessageBox.Warning, 'Duplicate ID',
                                         msg, QMessageBox.Ok, self)
                    notice.show()
                    return
            # also check for name collision with parameters or data elements
            if 'name' in self.editable_widgets and self.ded_name_modified:
                self.name_widget = self.editable_widgets['name']
                name_value = self.name_widget.text()
                if name_value.lower() in self.ded_disallowed_names:
                    msg = f'The name "{name_value}" is already being used.'
                    notice = QMessageBox(QMessageBox.Warning, 'Duplicate Name',
                                         msg, QMessageBox.Ok, self)
                    notice.show()
                    return
        elif cname == 'Port':
            # Port ids/names are only required to be unique within the context
            # of their parent product (the "of_product" attribute)
            parent_product = self.obj.of_product
            sibling_ids = []
            sibling_names = []
            if parent_product and 'id' in self.editable_widgets:
                sibling_ids = [port.id for port in parent_product.ports
                               if port.oid != self.obj.oid]
                self.id_widget = self.editable_widgets['id']
                id_value = self.id_widget.text()
                if id_value in sibling_ids:
                    sib_ids_txt = ', '.join([i for i in sibling_ids])
                    msg = f'The id "{id_value}" has a duplicate within\n'
                    msg += f'its parent object ("{parent_product.id}");\n'
                    msg += f'port ids are: {sib_ids_txt}.'
                    notice = QMessageBox(QMessageBox.Warning, 'Duplicate ID',
                                         msg, QMessageBox.Ok, self)
                    notice.show()
                    return
            if parent_product and 'name' in self.editable_widgets:
                sibling_names = [port.name for port in parent_product.ports
                                 if port.oid != self.obj.oid]
                self.name_widget = self.editable_widgets['name']
                name_value = self.name_widget.text()
                if name_value in sibling_names:
                    sib_names_txt = ', '.join([n for n in sibling_names])
                    msg = f'The name "{name_value}" has a duplicate within\n'
                    msg += f'its parent object ("{parent_product.id}");\n'
                    msg += f'port names are: {sib_names_txt}.'
                    notice = QMessageBox(QMessageBox.Warning, 'Duplicate Name',
                                         msg, QMessageBox.Ok, self)
                    notice.show()
                    return
        epw = [pid for pid in self.p_widgets
               if hasattr(self.p_widgets[pid], 'get_value')]
        if (not self.editable_widgets) and epw:
            # only editable fields are parameters -- send "parms set" signal
            # and return ...
            pmods = {}
            for p_id in self.p_widgets:
                # only non-computed parm widgets have 'get_value'
                if hasattr(self.p_widgets[p_id], 'get_value'):
                    str_val = self.p_widgets[p_id].get_value()
                    set_pval_from_str(self.obj.oid, p_id, str_val)
                    pmods[p_id] = get_pval(self.obj.oid, p_id)
            pdict = {self.obj.oid : pmods}
            parent = self.parent()
            if parent:
                parent.setFocus()
            if getattr(self, 'closing', False):
                orb.log.debug('  [pgxo] saving and closing ...')
                # reset 'closing'
                self.closing = False
                dispatcher.send("parms set", parms=pdict)
                self.close()
                return
            else:
                orb.log.debug('  [pgxo] saved -- rebuilding ...')
                self.build_from_object()
                dispatcher.send("parms set", parms=pdict)
                return
        fields_dict = {}
        for name in self.editable_widgets:
            fields_dict[name] = self.editable_widgets[name].get_value()
        required = self.required or PGXN_REQD.get(cname)
        # orb.log.info('  validating against idvs:')
        # orb.log.info('  {}'.format(str(self.all_idvs)))
        msg_dict = validate_all(fields_dict, cname, self.schema, self.view,
                                required=required, idvs=self.all_idvs,
                                html=True)
        if list(msg_dict.keys()):   # one or more field values are invalid
            orb.log.debug('  validation errors: {}'.format(str(msg_dict)))
            # TODO:  validation dialog
            dlg = ValidationDialog(msg_dict)
            if dlg.exec_():
                return
        NOW = dtstamp()
        for name, val in fields_dict.items():
            setattr(self.obj, name, val)
            orb.log.debug('  [pgxo] - {}: {}'.format(
                          name, val.__repr__()))
        # NOTE:  for new objects, save *ALL* parameters (they are new
        # also); for existing objects, save only modified parameters
        # if parameterz.get(self.obj.oid) and self.new:
        if self.new:
            for p_id in self.p_widgets:
                # only non-computed parm widgets have 'get_value'
                if hasattr(self.p_widgets[p_id], 'get_value'):
                    str_val = self.p_widgets[p_id].get_value()
                    set_pval_from_str(self.obj.oid, p_id, str_val)
            for deid in self.d_widgets:
                if hasattr(self.d_widgets[deid], 'get_value'):
                    str_val = self.d_widgets[deid].get_value()
                    set_dval_from_str(self.obj.oid, deid, str_val)
        # elif parameterz.get(self.obj.oid):
        else:
            # if object is *not* new, save any modified data elements and
            # parameters
            for deid in self.d_widgets:
                # orb.log.debug('  - data element: "{}"'.format(deid))
                if hasattr(self.d_widgets[deid], 'get_value'):
                    str_val = self.d_widgets[deid].get_value()
                    # orb.log.debug('    writing val: "{}"'.format(str_val))
                    set_dval_from_str(self.obj.oid, deid, str_val)
            for p_id in self.p_widgets:
                # if p is computed, its widget is a label (no 'get_value')
                # DO NOT MODIFY values
                if hasattr(self.p_widgets[p_id], 'get_value'):
                    str_val = self.p_widgets[p_id].get_value()
                    # u_cur -> current units setting
                    # (None if can't modify, which also means base units)
                    u_cur = None
                    if hasattr(self.u_widgets[p_id], 'currentText'):
                        u_cur = self.u_widgets[p_id].currentText()
                        # orb.log.debug('  - units widget set to {}'.format(
                                                                    # u_cur))
                    # set parameter values for ALL editable
                    # parameters (faster/simpler than checking for mods)
                    orb.log.debug('  - setting {} to {} {}'.format(
                                  p_id, str_val, u_cur))
                    set_pval_from_str(self.obj.oid, p_id, str_val,
                                      units=u_cur)
        user_obj = orb.get(state.get('local_user_oid'))
        if self.new:
            self.obj.creator = user_obj
            self.obj.create_datetime = NOW
        self.obj.modifier = user_obj
        self.obj.mod_datetime = NOW
        # for instances of HardwareProduct, the last step is to generate
        # an 'id': even if it is an existing object, its 'id' might change
        # depending on its 'owner' and 'product_type' ... if the
        # current id incorporates the owner.id and
        # product_type.abbreviation in the correct format and is unique,
        # gen_product_id will simply return it unaltered.
        if isinstance(self.obj, orb.classes['HardwareProduct']):
            generated_id = orb.gen_product_id(self.obj)
            if not self.obj.id == generated_id:
                self.obj.id = generated_id
        orb.save([self.obj])
        if self.new:
            if cname == 'Project':
                # orb.log.debug('  [pgxo] send "new project" signal')
                dispatcher.send(signal="new project", obj=self.obj)
            else:
                # generic new object signal
                # orb.log.debug('  [pgxo] sending "new object" signal')
                dispatcher.send(signal="new object", obj=self.obj,
                                cname=cname)
            # for new ProductType instances, create a
            # 'DisciplineProductType' relating them to the
            # catch-all "Engineering" discipline so they will be included
            # in the "ALL" product types filter ...
            if cname == 'ProductType':
                eng_discipline = orb.get(
                                    'pgefobjects:Discipline.engineering')
                dpt = clone('DisciplineProductType',
                            id='engineering_to_'+self.obj.id,
                            used_in_discipline=eng_discipline,
                            relevant_product_type=self.obj)
                orb.save([dpt])
        else:
            orb.log.debug('  [pgxo] sending "modified object" signal ...')
            dispatcher.send(signal="modified object", obj=self.obj,
                            cname=cname)
            self.obj_modified.emit(self.obj.oid)
            if orb.is_a(self.obj, 'Activity'):
                # NOTE: this includes 'Mission' subclass of Activity
                self.activity_edited.emit(self.obj.oid)
        parent = self.parent()
        if parent:
            parent.setFocus()
        if getattr(self, 'closing', False):
            orb.log.debug('  [pgxo] saving and closing ...')
            # reset 'closing'
            self.closing = False
            self.close()
        else:
            orb.log.debug('  [pgxo] saved -- rebuilding ...')
            self.build_from_object()
        # if state.get('mode') in ['system', 'component']:
            # dispatcher.send(signal='update product modeler', obj=self.obj)

    def on_select_related(self):
        orb.log.info('* [pgxo] selecting related object ...')
        widget = self.sender()
        # obj = widget.get_value()
        # TODO:  if None, give option to create a new object (with pgxnobject)
        # orb.log.debug('  [pgxo] current object: {}'.format(obj.oid))
        cname = widget.related_cname
        field_name = widget.field_name
        # SELECTION_FILTERS define the set of valid objects for this field
        objs = []
        if SELECTION_FILTERS.get(field_name):
            fltrs = SELECTION_FILTERS[field_name]
            for cname in fltrs:
                objs += orb.get_by_type(cname)
        else:
            objs = orb.get_all_subtypes(cname)
        if objs:
            # orb.log.debug('  [pgxo] object being edited: {}'.format(
                                                            # self.obj.oid))
            if self.obj in objs:
                # exclude the object being edited from the selections
                # orb.log.debug('            removing it from selectables ...')
                objs.remove(self.obj)
            # orb.log.debug('  [pgxo] selectable objects:')
            # for o in objs:
                # orb.log.debug('            {}'.format(o.id))
            required_fields = PGXN_REQD.get(cname) or []
            with_none = not (field_name in required_fields)
            dlg = ObjectSelectionDialog(objs, with_none=with_none, parent=self)
            if dlg.exec_():
                new_oid = dlg.get_oid()
                new_obj = orb.get(new_oid)
                widget.set_value(new_obj)
        else:
            # TODO:  pop-up message about no objects being available
            pass

    def on_view_related(self):
        orb.log.info('* [pgxo] view related object ...')
        widget = self.sender()
        obj = widget.get_value()
        orb.log.debug('* [pgxo] "{}"'.format(obj.id))
        # TODO:  if editable, bring up selection list of possible values
        # or, if none, give option to create a new object (with pgxnobject)
        if obj:
            self.new_window = PgxnObject(obj)
            # show() -> non-modal dialog
            self.new_window.show()


class ParameterSpecDialog(QDialog):
    """
    A dialog to edit parameters for a HW Library item.

    Args:
        oid (str): oid of the item whose spec is to be edited
        pid (str): base id of the parameters to be edited
    """
    def __init__(self, oid, pid, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Power Parameters")
        item = orb.get(oid)
        if not item:
            # TODO: popup to say item was not found
            return
        self.parm_form = ParameterForm(item, pid=pid, edit_mode=True)
        # OK and Cancel buttons
        vbox = QVBoxLayout()
        vbox.addWidget(self.parm_form)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        self.buttons.accepted.connect(self.on_save)
        self.buttons.rejected.connect(self.reject)
        vbox.addWidget(self.buttons)
        self.setLayout(vbox)

    def on_save(self):
        # TODO: get parms from form
        parms = {}
        dispatcher.send("update parameters", parms)
        self.accept()


# ==========================================================================
# This would need to be modified to work with fastorb ...
# ==========================================================================
if __name__ == '__main__':
    """
    Cmd line invocation for testing / prototyping
    """
    from PyQt5.QtWidgets import QApplication
    from pangalactic.core.serializers import deserialize
    from pangalactic.core.test.utils import create_test_project
    from pangalactic.core.test.utils import create_test_users
    app = QApplication(sys.argv)
    # ***************************************
    # Test using ref and test data
    # ***************************************
    if len(sys.argv) < 2:
        print(' * You must specify a home directory for the orb *')
        sys.exit()
    home = sys.argv[1]
    orb.start(home, console=True, debug=True)
    test_part = orb.get('test:computer')
    if not test_part:
        deserialize(orb, create_test_users() + create_test_project())
        test_part = orb.get('test:computer')
    # HardwareProduct = orb.classes['HardwareProduct']
    # test_part = HardwareProduct(oid='fusionworld:mrfusion.000',
            # id='mrfusion.000', id_ns='fusionworld', name='Mr. Fusion v.000',
            # security_mask=0, description='Fusion Power Source, MF Series',
            # comment='Omni-Fuel, Compact Semi-Portable Fusion Power Module')
    # window = PgxnObject(test_part)
    window = ParameterForm(test_part, edit_mode=True)
    window.show()
    sys.exit(app.exec_())

