# -*- coding: utf-8 -*-
"""
PgxnObject (a domain object viewer/editor)
"""
# from collections import OrderedDict
import math, os
from functools import partial

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (QAction, QApplication, QDialog, QDialogButtonBox,
                             QFormLayout, QHBoxLayout, QLabel, QMessageBox,
                             QSizePolicy, QTabWidget, QToolBar, QVBoxLayout,
                             QWidget)

from louie      import dispatcher
from sqlalchemy import ForeignKey
from sqlalchemy.orm.collections import InstrumentedList

# pangalactic
from pangalactic.core import state
from pangalactic.core.access import get_perms
from pangalactic.core.meta import (MAIN_VIEWS, PGXN_HIDE, PGXN_HIDE_PARMS,
                                   PGXN_MASK, PGXN_PARAMETERS,
                                   PGXN_PLACEHOLDERS, PGXN_VIEWS, PGXN_REQD,
                                   SELECTABLE_VALUES, SELECTION_FILTERS)
from pangalactic.core.parametrics import (add_parameter, delete_parameter,
                                          get_parameter_id, get_pval_as_str,
                                          get_pval_from_str, parameterz,
                                          parm_defz, set_pval_from_str)
from pangalactic.core.uberorb     import orb
from pangalactic.core.units       import alt_units, ureg
from pangalactic.core.utils.meta  import (get_attr_ext_name,
                                          get_parameter_definition_oid)
from pangalactic.core.utils.datetimes import dtstamp
from pangalactic.core.validation  import validate_all
from pangalactic.node.utils       import (clone, get_object_title,
                                          extract_mime_data)
from pangalactic.node.widgets     import get_widget, UnitsWidget
from pangalactic.node.dialogs     import (ObjectSelectionDialog,
                                          ProgressDialog,
                                          ValidationDialog)


DATATYPES = SELECTABLE_VALUES['range_datatype']
PARMS_NBR = 12
DEFAULT_PANELS = ['main', 'info', 'narrative', 'admin']


class PgxnForm(QWidget):
    """
    A form for viewing/editing object attributes.

    Attributes:
        obj (Identifiable or subtype):  the object to be viewed or edited
        schema (dict):  the schema of the object to be viewed or edited
        edit_mode (bool):  if True, open in edit mode; otherwise, view mode
        view (list):  names of the fields to be shown (a subset of
            self.schema['field_names'])
        mask (list of str):  list of fields to be displayed as read-only
    """
    def __init__(self, obj, form_type, edit_mode=False, view=None,
                 main_view=None, mask=None, unmask=None, seq=None, idvs=None,
                 placeholders=None, parent=None):
        """
        Initialize.

        Args:
            obj (Identifiable or subtype):  the object to be viewed or edited
            form_type (str):  one of [parameters|main|info|narrative|admin]

        Keyword Args:
            edit_mode (bool):  if True, open in edit mode; otherwise, view mode
            view (list):  names of the fields to be shown (a subset of
                self.schema['field_names'])
            main_view (list):  names of the fields to put on the 'main' panel
            mask (list of str):  list of fields to be displayed as read-only
                (default: None)
            unmask (list of str):  list of fields to be editable which are not
                editable by default (default: None)
            seq (int):  sequence number of parameter panel in pgxnobject
            idvs (list of tuples):  list of current (`id`, `version`) values to
                avoid
            placeholders (dict of str):  a dict mapping field names to
                placeholder strings
            parent (QWidget): parent widget
        """
        super(PgxnForm, self).__init__(parent=parent)
        self.edit_mode = edit_mode
        self.obj = obj
        self.all_idvs = idvs or []
        cname = obj.__class__.__name__
        schema = orb.schemas.get(cname)
        field_names = [n for n in schema.get('field_names')
                       if n not in PGXN_MASK.get(cname, PGXN_HIDE)]
        # get default placeholders; override them with the specified
        # placeholders, if any
        ph_defaults = PGXN_PLACEHOLDERS
        if placeholders:
            ph_defaults.update(placeholders)
        placeholders = ph_defaults
        self.p_widgets = {}
        self.p_widget_values = {}
        self.p_widget_actions = {}
        self.u_widgets = {}
        self.u_widget_values = {}
        self.previous_units = {}
        self.editable_widgets = {}
        view = view or []
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
        if form_type == 'parameters':
            # special case for parameters panel:  ignore the widget
            # population process implemented in the "for field_name" loop
            # used for the other panels
            orb.log.info('* [pgxnobj] building "parameters" form ...')
            # Special case for parameters form ...
            idvs = orb.get_idvs(cname='ParameterDefinition')
            variables = [idv[0] for idv in idvs]
            contingencies = [get_parameter_id(idv[0], 'Ctgcy') for idv in idvs]
            parmz = parameterz.get(obj.oid, {})
            pids = [p for p in parmz if p in variables or p in contingencies]
            if pids:
                orb.log.info('* [pgxnobj] parameters found: {}'.format(
                                                            str(pids)))
                computed_note = False
                # order parameters -- editable (non-computed) parameters first
                pref_editables = [pid for pid in PGXN_PARAMETERS
                                  if pid in pids]
                np_editables = [pid for pid in pids
                                if pid not in PGXN_PARAMETERS]
                editables = pref_editables + np_editables
                ##############################################################
                ### New Parameter paradigm (SCW 2019-03-25) ##################
                # 1. by default, only base ("variable") parameters are shown
                # 2. "computeds" shown only when a relevant "context" is set
                # (to be implemented)
                ##############################################################
                ### Put ... computeds ... BECK! (SCW 2019-09-04) #############
                ### (Per request of Patrick and Rachel)
                ##############################################################
                pref_computeds = [pid for pid in PGXN_PARAMETERS
                                  if pid in parmz
                                  and parm_defz.get(pid)
                                  and parm_defz[pid].get('computed')]
                np_computeds = [pid for pid in parmz
                                if parm_defz.get(pid)
                                and parm_defz[pid].get('computed')
                                and pid not in PGXN_PARAMETERS]
                computeds = pref_computeds + np_computeds
                # computeds = []
                p_ordering = [pid for pid in editables + computeds
                              if pid not in contingencies]
                orb.log.info('  [pgxnobj] parameter ordering: {}'.format(
                                                            str(p_ordering)))
                if seq is None:
                    orb.log.debug('  seq is None; all parameters on one page.')
                    pids_on_panel = p_ordering
                else:
                    orb.log.debug('  seq is {}'.format(str(seq)))
                    # NOTE:  'seq' is a 1-based sequence
                    orb.log.debug('  parameters found: {}'.format(
                                                        str(pids)))
                    pids_on_panel = p_ordering[
                                            (seq-1)*PARMS_NBR : seq*PARMS_NBR]
                    orb.log.debug('  parameters on this panel: {}'.format(
                                                          str(pids_on_panel)))
                for pid in pids_on_panel:
                    field_name = pid
                    parm = parmz[pid] or {}
                    pd = parm_defz[pid]
                    ext_name = pd.get('name', '') or '[unknown]'
                    units = parm.get('units', '')
                    dimensions = pd.get('dimensions', '')
                    unit_choices = alt_units.get(dimensions)
                    if unit_choices:
                        units_widget = UnitsWidget(field_name, units,
                                                   unit_choices)
                        units_widget.currentTextChanged.connect(
                                                            self.on_set_units)
                    else:
                        units_widget = QLabel(units)
                    # field_type 'parameter' -> StringFieldWidget for edit mode
                    field_type = 'parameter'
                    # parm types are 'float', 'int', 'bool', or 'text'
                    parm_type = pd.get('range_datatype', 'float')
                    # if 'computed', p is not editable
                    editable = (edit_mode and not pd.get('computed'))
                    definition = (pd.get('description', '')
                                  or 'unknown definition')
                    # NOTE: get_pval_as_str will convert the stored value from
                    # base units to the units specified (using get_pval)
                    str_val = get_pval_as_str(orb, self.obj.oid, pid,
                                              units=units)
                    widget, label = get_widget(field_name, field_type,
                                               value=str_val,
                                               external_name=ext_name,
                                               editable=editable,
                                               tooltip=definition,
                                               parm_field=True,
                                               parm_type=parm_type)
                    # float parms should have contingency parms -- if so, the
                    # contingency parm will have an entry in parm_defz ...
                    c_pid = get_parameter_id(pid, 'Ctgcy')
                    c_pd = parm_defz.get(c_pid)
                    c_widget = None
                    if c_pd:
                        c_ext_name = c_pd.get('name', '') or '[unknown]'
                        c_units = '%'
                        c_units_widget = QLabel(c_units)
                        c_definition = (c_pd.get('description', '')
                                        or 'unknown definition')
                        c_str_val = get_pval_as_str(orb, self.obj.oid, c_pid,
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
                        # orb.log.debug('  [pgxnobj]'
                               # ' - got widget (%s) and label, "%s"' % (
                                                 # str(widget),
                                                 # str(label.text())))
                        self.p_widgets[pid] = widget
                        self.u_widgets[pid] = units_widget
                        # use "stringified" values because that's what is in
                        # the form field
                        self.u_widget_values[pid] = units
                        self.previous_units[pid] = units
                        self.p_widget_values[pid] = str(parm.get('value', ''))
                        widget.setSizePolicy(QSizePolicy.Minimum,
                                             QSizePolicy.Minimum)
                        if pd.get('computed'):
                            text = label.text() + ' *'
                            label.setText(text)
                            label.setStyleSheet(
                                'QLabel {font-size: 15px; font-weight: bold; '
                                'color: purple} QToolTip {'
                                'font-weight: normal; color: black; '
                                'font-size: 12px; border: 2px solid;}')
                            computed_note = True
                        if edit_mode:
                            del_action = QAction('delete', label)
                            del_action.triggered.connect(
                                    partial(parent.on_del_parameter, pid=pid))
                            label.addAction(del_action)
                            label.setContextMenuPolicy(Qt.ActionsContextMenu)
                        value_layout = QHBoxLayout()
                        value_layout.addWidget(widget)
                        value_layout.addWidget(units_widget)
                        if c_widget:
                            self.p_widgets[c_pid] = c_widget
                            self.u_widgets[c_pid] = c_units_widget
                            self.u_widget_values[c_pid] = '%'
                            self.previous_units[c_pid] = '%'
                            c_parm = parmz.get(c_pid) or {}
                            self.p_widget_values[c_pid] = str(c_parm.get(
                                                                'value', ''))
                            c_widget.setSizePolicy(QSizePolicy.Minimum,
                                                   QSizePolicy.Minimum)
                            value_layout.addWidget(c_label)
                            value_layout.addWidget(c_widget)
                            value_layout.addWidget(c_units_widget)
                        form.addRow(label, value_layout)
                        # orb.log.debug('* [pgxnobj] size hint: %s' % str(
                                                    # widget.sizeHint()))
                if computed_note:
                    form.addRow(QWidget(), QLabel())
                    cnote = QLabel("* computed parameter\n  (read-only)")
                    cnote.setStyleSheet('font-weight: bold;color: purple')
                    form.addRow(cnote)
            else:
                orb.log.info('* [pgxnobj] no parameters found.')
                label = QLabel('No parameters have been specified yet.')
                label.setStyleSheet('font-weight: bold')
                form.addRow(label)
            self.setLayout(form)
            # end of "parameters" form initialization
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
        # if a view is specified, it restricts the fields displayed
        if view:
            this_view = [f for f in form_view if f in view]
        else:
            this_view = [f for f in form_view if f in field_names]
        # don't create panel if it will have no fields
        if not this_view:
            return None
        for field_name in this_view:
            field_type = schema['fields'][field_name]['field_type']
            if field_type == ForeignKey:
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
            if edit_mode:
                editable = schema['fields'][field_name].get('editable')
                if mask and field_name in mask:
                    editable = False
                if unmask and field_name in unmask:
                    editable = True
            else:
                editable = False
            related_cname = schema['fields'][field_name].get('related_cname')
            # NOTE: this should be uncommented if needed for debugging
            # orb.log.debug('* [pgxnobj] get_widget(%s, %s, ...)' % (
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
                # orb.log.debug('  [pgxnobj]'
                               # ' - got widget (%s) and label, "%s"' % (
                                                     # str(widget),
                                                     # str(label.text())))
                # setting the value when widget is initialized now ...
                # widget.set_value(val)
                if editable:
                    self.editable_widgets[field_name] = widget
                widget.setSizePolicy(QSizePolicy.Minimum,
                                     QSizePolicy.Minimum)
                form.addRow(label, widget)
                # orb.log.debug('* [pgxnobj] widget size hint: %s' % str(
                                                        # widget.sizeHint()))
                if related_cname:
                    if editable:
                        widget.clicked.connect(self.on_select_related)
                    elif val is not None:
                        widget.clicked.connect(self.on_view_related)
                # if editable and field_name == 'id':
                    # widget.textChanged.connect(self.on_id_text_changed)
        self.setSizePolicy(QSizePolicy.Minimum,
                           QSizePolicy.Minimum)
        self.setLayout(form)

    def on_set_units(self):
        orb.log.info('* [pgxnobj] setting units ...')
        units_widget = self.sender()
        new_units = units_widget.get_value()
        orb.log.debug('            new units: "{}"'.format(new_units))
        pid = units_widget.field_name
        parm_widget = self.p_widgets.get(pid)
        if self.edit_mode and hasattr(parm_widget, 'get_value'):
            # in edit mode, get value (str) from editable field and convert it
            str_val = parm_widget.get_value()
            pval = get_pval_from_str(orb, self.obj.oid, pid, str_val)
            applicable_units = self.previous_units[pid]
            quant = pval * ureg.parse_expression(applicable_units)
            new_quant = quant.to(new_units)
            new_str_val = str(new_quant.magnitude)
        else:
            # view mode or read-only parm -> get cached parameter value and
            # convert it to the requested units for display
            new_str_val = get_pval_as_str(orb, self.obj.oid, pid,
                                          units=new_units)
        if hasattr(parm_widget, 'set_value'):
            parm_widget.set_value(new_str_val)
        elif hasattr(parm_widget, 'setText'):
            parm_widget.setText(new_str_val)
        self.previous_units[pid] = new_units

    def on_select_related(self):
        orb.log.info('* [pgxnobj] select related object ...')
        widget = self.sender()
        obj = widget.get_value()
        # TODO:  if None, give option to create a new object (with pgxnobject)
        orb.log.debug('  [pgxnobj] current object: %s' % str(obj))
        cname = widget.related_cname
        field_name = widget.field_name
        # SELECTION_FILTERS define the set of valid objects for this field
        objs = []
        if SELECTION_FILTERS.get(field_name):
            fltrs = SELECTION_FILTERS[field_name]
            for cname in fltrs:
                if fltrs[cname]:
                    objs += orb.select(cname, **fltrs[cname])
                else:
                    objs += orb.get_by_type(cname)
        else:
            objs = orb.get_all_subtypes(cname)
        if objs:
            orb.log.debug('  [pgxnobj] object being edited: {}'.format(
                                                            self.obj.oid))
            if self.obj in objs:
                # exclude the object being edited from the selections
                orb.log.debug('            removing it from selectables ...')
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
        orb.log.info('* [pgxnobj] view related object ...')
        widget = self.sender()
        # TODO: handle get_value() for M2M and ONE2M relationships
        # (InstrumentedList)
        obj = widget.get_value()
        orb.log.debug('* [pgxnobj]   object: %s' % str(obj))
        # TODO:  if editable, bring up selection list of possible values
        # or, if none, give option to create a new object (with pgxnobject)
        # NOTE: get_value() may return a sqlalchemy "InstrumentedList" -- in
        # that case ignore it because it will cause a crash
        if obj and not isinstance(obj, InstrumentedList):
            self.new_window = PgxnObject(obj)
            # show() -> non-modal dialog
            self.new_window.show()

    # def on_id_text_changed(self, text):
        # # UNCOMMENT THIS FOR INTENSIVE DEBUGGING ONLY
        # # orb.log.debug(' - id value entered: "{}" ...'.format(text))
        # match_text = ''
        # valid = True
        # if text in self.all_ids:
            # match_text = text
            # valid = False
        # else:
            # # find shortest containing id
            # starters = [s for s in self.all_ids if s.startswith(text)]
            # if starters:
                # match_text = reduce(
                           # lambda u, v: u if len(u) < len(v) else v, starters)
        # if hasattr(self, 'popup'):
            # try:
                # self.popup.close()
            # except:
                # pass  # (C++ object was deleted)
        # if match_text:
            # dlg = IdValidationPopup(match_text, valid=valid,
                                    # parent=self.editable_widgets['id'])
            # dlg.show()
            # self.popup = dlg
            # QTimer.singleShot(200, dlg.close)


class ParameterForm(PgxnForm):
    """
    A form for viewing/editing object parameters.

    Attributes:
        obj (Identifiable or subtype):  the object to be viewed or edited
        schema (dict):  the schema of the object to be viewed or edited
        edit_mode (bool):  if True, open in edit mode; otherwise, view mode
        view (list):  names of the fields to be shown (a subset of
            self.schema['field_names'])
        mask (list of str):  list of fields to be displayed as read-only
    """
    def __init__(self, obj, pgxo=None, edit_mode=False, view=None, mask=None,
                 seq=None, parent=None):
        """
        Initialize.

        Args:
            obj (Identifiable or subtype):  the object to be viewed or edited

        Keyword Args:
            edit_mode (bool):  if True, open in edit mode; otherwise, view mode
            view (list):  names of the fields to be shown (a subset of
                self.schema['field_names'])
            mask (list of str):  list of fields to be displayed as read-only
                (default: None)
            seq (int):  sequence number of parameter panel in pgxnobject
        """
        super(ParameterForm, self).__init__(obj, 'parameters',
            edit_mode=edit_mode, view=view, mask=mask, seq=seq, parent=parent)
        self.obj = obj
        self.pgxo = pgxo
        self.seq = seq
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        mime_formats = list(event.mimeData().formats())
        orb.log.info("* dragEnterEvent: mime types {}".format(str(mime_formats)))
        if event.mimeData().hasFormat(
                                "application/x-pgef-parameter-definition"):
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(
                                "application/x-pgef-parameter-definition"):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        orb.log.info("* dropEvent: got data")
        if self.pgxo.edit_mode and event.mimeData().hasFormat(
            "application/x-pgef-parameter-definition"):
            # if the dropped object is not a ParameterDefinition, the drop
            # event is ignored
            data = extract_mime_data(event,
                                     "application/x-pgef-parameter-definition")
            icon, pd_oid, pd_id, pd_name, pd_cname = data
            obj_parms = parameterz.get(self.obj.oid) or {}
            if pd_id not in obj_parms:
                orb.log.info("* Parameter drop event: got '%s'" % pd_name)
                event.setDropAction(Qt.CopyAction)
                event.accept()
                add_parameter(orb, self.obj.oid, pd_id)
                self.obj.modifier = orb.get(state.get('local_user_oid'))
                self.obj.mod_datetime = dtstamp()
                orb.save([self.obj])
                dispatcher.send(signal='modified object', obj=self.obj)
                self.pgxo.build_from_object()
            else:
                event.ignore()
                orb.log.info("* Parameter drop event: ignoring '%s' -- "
                             "we already got one, it's verra nahss!)"
                             % pd_name)
        else:
            event.ignore()


class PgxnObject(QDialog):
    """
    Object viewer/editor.

    Attributes:
        obj (Identifiable or subtype):  the object to be viewed or edited
        schema (dict):  the schema of the object to be viewed or edited
        edit_mode (bool):  if True, open in edit mode; otherwise, view mode
        enable_delete (bool):  flag indicating whether a "Delete" button
            should be displayed when in edit mode (deletes object)
        go_to_tab (int):  index of the tab to go to when rebuilding
        view (list):  names of the fields to be shown (a subset of
            self.schema['field_names'])
        view_only (bool):  flag indicating that edit mode is unavailable
            (default: False)
        mask (list of str):  list of fields to be displayed as read-only
        required (list of str):  list of fields that must not be null
        tabs (QTabWidget):  widget holding the interface's tabbed "pages"
    """
    def __init__(self, obj, embedded=False, edit_mode=False,
                 enable_delete=True, view=None, main_view=None, mask=None,
                 required=None, panels=None, go_to_panel=None, new=False,
                 test=False, modal_mode=False, view_only=False, parent=None,
                 **kw):
        """
        Initialize the dialog.

        Args:
            obj (Identifiable or subtype):  the object to be viewed or edited

        Keyword Args:
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
                'parameters'); if None, all panels
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
            parent (QWidget): parent widget of this dialog (default: None)
        """
        super(PgxnObject, self).__init__(parent=parent)
        self.obj          = obj
        self.new          = new
        self.embedded     = embedded
        self.edit_mode    = edit_mode
        self.view_only    = view_only
        self.mode_widgets = {}
        self.mode_widgets['view'] = set()
        self.mode_widgets['edit'] = set()
        self.modal_mode    = modal_mode
        self.enable_delete = enable_delete
        self.go_to_tab     = 0
        if go_to_panel and panels:
            if go_to_panel in panels:
                self.go_to_tab = panels.index(go_to_panel)
        elif go_to_panel in DEFAULT_PANELS:
            self.go_to_tab = DEFAULT_PANELS.index(go_to_panel)
        self.view         = view or []
        self.main_view    = main_view or []
        self.panels       = panels or []
        self.mask         = mask
        self.required     = required
        self.tabs         = QTabWidget()
        self.cname        = obj.__class__.__name__
        self.schema       = orb.schemas.get(self.cname)
        # all_idvs is for use in validating 'id' + 'version' for uniqueness ...
        self.all_idvs = orb.get_idvs(cname=self.cname)
        obj_idv = (self.obj.id, getattr(obj, 'version', ''))
        if not self.new and obj_idv in self.all_idvs:
            # if not a new object, remove its (id, version) from all_idvs
            self.all_idvs.remove(obj_idv)
        self.progress_value = 0
        dispatcher.connect(self.update_save_progress, 'obj parms cached')
        if not self.schema:
            # TODO:  more intelligent error handling
            orb.log.info('* [pgxnobj] oops, no schema found for "%s"!' %
                                                                    self.cname)
            return
        orb.log.info('* [pgxnobj] object oid: "%s"' % self.obj.oid)
        orb.log.info('* [pgxnobj] object id: "%s"' % self.obj.id)
        orb.log.info('* [pgxnobj] object version: "%s"' % getattr(
                                                        self.obj, 'version',
                                                        '[not applicable]'))
        orb.log.info('* [pgxnobj] cname: "%s"' % self.cname)
        self.setWindowTitle('Object Viewer / Editor')
        # set min width so text fields don't get truncated
        self.setMinimumWidth(500)
        # self.setMinimumHeight(300)
        self.vbox = QVBoxLayout()
        self.title = QLabel()
        self.title.setSizePolicy(QSizePolicy.Minimum,
                                 QSizePolicy.Minimum)
        self.vbox.addWidget(self.title)
        self.build_from_object()
        self.main_panel = QWidget()
        self.setLayout(self.vbox)
        self.init_toolbar()
        # self.setCentralWidget(self.main_panel)
        self.vbox.addWidget(self.main_panel)

    def init_toolbar(self):
        # self.toolbar = self.addToolBar('Tools')
        self.toolbar = QToolBar('Tools')
        if isinstance(self.obj, orb.classes['Product']):
            self.freeze_action = self.create_action('freeze',
                                    slot=self.freeze, icon='freeze_16',
                                    tip='Freeze this object',
                                    modes=['edit', 'view'])
            self.frozen_action = self.create_action('frozen',
                                    slot=self.frozen, icon='frozen_16',
                                    tip='This object is frozen',
                                    modes=['edit', 'view'])
            self.thaw_action = self.create_action('thaw',
                                    slot=self.thaw, icon='thaw_16',
                                    tip='Thaw this object',
                                    modes=['edit', 'view'])
            self.where_used_action = self.create_action('where used',
                                    slot=self.show_where_used, icon='system',
                                    tip='Show where this object is used ...',
                                    modes=['edit', 'view'])
            self.toolbar.addAction(self.freeze_action)
            self.toolbar.addAction(self.frozen_action)
            self.toolbar.addAction(self.thaw_action)
            self.toolbar.addAction(self.where_used_action)
            perms = get_perms(self.obj)
            orb.log.debug('            user perms: {}'.format(str(perms)))
            if self.obj.frozen:
                orb.log.debug('            object is frozen.')
                self.frozen_action.setVisible(True)
                self.freeze_action.setVisible(False)
                if 'delete' in perms:
                    # if perms include "delete", can also "thaw"
                    self.thaw_action.setVisible(True)
            else:
                orb.log.debug('            object is NOT frozen.')
                self.frozen_action.setVisible(False)
                self.thaw_action.setVisible(False)
                if 'delete' in perms:
                    # if perms include "delete", can also "freeze"
                    self.freeze_action.setVisible(True)
        self.clone_action = self.create_action('clone',
                                slot=self.on_clone, icon='clone_16',
                                tip='Clone this object',
                                modes=['edit', 'view'])
        self.toolbar.addAction(self.clone_action)
        # NOTE: viewer may be reactivated later ...
        # self.viewer_action = self.create_action('viewer',
                                # slot=self.open_viewer, icon='view_16',
                                # tip='View models of this object',
                                # modes=['edit', 'view'])
        # self.toolbar.addAction(self.viewer_action)
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

    def freeze(self):
        if (isinstance(self.obj, orb.classes['Product'])
            and not self.obj.frozen):
            self.freeze_action.setVisible(False)
            self.frozen_action.setVisible(True)
            self.thaw_action.setVisible(True)
            self.obj.frozen = True
            orb.save([self.obj])
            self.build_from_object()

    def frozen(self):
        pass

    def thaw(self):
        if (isinstance(self.obj, orb.classes['Product'])
            and self.obj.frozen):
            self.freeze_action.setVisible(True)
            self.frozen_action.setVisible(False)
            self.thaw_action.setVisible(False)
            self.obj.frozen = False
            orb.save([self.obj])
            self.build_from_object()

    def show_where_used(self):
        if hasattr(self.obj, 'where_used'):
            assemblies = set([acu.assembly for acu in self.obj.where_used])
            if assemblies:
                txt = 'This is a component in the following assemblies:'
            else:
                txt = 'This is not used in any assemblies.'
            notice = QMessageBox(QMessageBox.Information, 'Where Used', txt,
                                 QMessageBox.Ok, self)
            if assemblies and len(assemblies) > 0:
                info = '<p><ul>{}</ul></p>'.format('\n'.join(
                               ['<li><b>{}</b><br>(id: {})</li>'.format(
                               a.name, a.id, a.oid) for a in assemblies if a]))
                notice.setInformativeText(info)
            notice.show()

    def on_clone(self):
        """
        Respond to 'clone' action by cloning the current object.
        """
        # TODO:  dialog with choice of: (1) clone to version or (2) clone to cp
        new_obj = clone(self.obj, id='new-id', derived_from=self.obj)
        orb.save([new_obj])
        self.obj = new_obj
        self.go_to_tab = 2
        self.build_from_object()
        self.on_edit()

    def build_from_object(self):
        """
        Build tabbed forms from the supplied object
        """
        title_text = get_object_title(self.obj, new=self.new)
        self.title.setText(title_text)
        tab_names = ['main', 'info', 'narrative', 'admin']
        if self.panels:
            tab_names = [n for n in tab_names if n in self.panels]
        cname = self.obj.__class__.__name__
        if ((not self.panels or (self.panels and 'parameters' in self.panels))
            and isinstance(self.obj, orb.classes['Modelable'])
            and not cname in PGXN_HIDE_PARMS):
            # All subclasses of Modelable except the ones in PGXN_HIDE_PARMS
            # get a 'parameters' panel
            # First find the parameters to be displayed for this object ...
            idvs = orb.get_idvs(cname='ParameterDefinition')
            # variables = [idv[0] for idv in idvs]
            contingencies = [get_parameter_id(idv[0], 'Contingency') for idv in idvs]
            parmz = parameterz.get(self.obj.oid, {})
            # contingencies are not used in calculating the number of
            # parameters on the panel, since they do not have separate rows
            pids = [p for p in parmz if p not in contingencies]
            if len(pids) > PARMS_NBR:
                n_of_parms = len(pids)
                # allow PARMS_NBR parameters to a panel ...
                n_of_parm_panels = int(math.ceil(
                                       float(n_of_parms)/float(PARMS_NBR)))
                for i in range(n_of_parm_panels):
                    tab_names.insert(i, 'parms_{}'.format(i+1))
            else:
                tab_names.insert(0, 'parms')
        # destroy button box and current tab pages, if they exist
        if hasattr(self, 'bbox'):
            self.bbox.hide()
            self.vbox.removeWidget(self.bbox)
            self.bbox.parent = None
            for tab_name in tab_names:
                if hasattr(self, tab_name+'_tab'):
                    tab = getattr(self, tab_name+'_tab')
                    tab.parent = None
            # NOTE: TBD whether the whole tab widget needs to be removed -- for
            # now, just clear the pages
            self.tabs.clear()
        # create new tab pages
        # TODO:  make tab pages scrollable, just in case
        self.editable_widgets = {}
        self.p_widgets = {}
        self.p_widget_values = {}
        self.p_widget_actions = {}
        self.u_widgets = {}
        self.u_widget_values = {}
        self.previous_units = {}
        perms = get_perms(self.obj)
        for tab_name in tab_names:
            # The purpose of the tabs is to split the class's fields up so it
            # is not necessary to scroll at all.
            # TODO:  add more tabs if necessary
            # The basic algorithm is steps [1], [2], and [3] below ...
            # TODO:  a 'prefs' capability to override MAIN_VIEWS.
            if tab_name.startswith('parms'):
                sufs = ('1', '2', '3', '4', '5', '6', '7', '8', '9')
                if tab_name.endswith(sufs):
                    n = int(tab_name[-1])
                else:
                    n = None
                setattr(self, tab_name+'_tab',
                        ParameterForm(self.obj, pgxo=self,
                        edit_mode=self.edit_mode, view=self.view,
                        mask=self.mask, seq=n, parent=self))
            else:
                setattr(self, tab_name+'_tab',
                        PgxnForm(self.obj, tab_name, edit_mode=self.edit_mode,
                                 view=self.view, main_view=self.main_view,
                                 mask=self.mask, idvs=self.all_idvs,
                                 parent=self))
            this_tab = getattr(self, tab_name+'_tab')
            self.editable_widgets.update(this_tab.editable_widgets)
            self.p_widgets.update(this_tab.p_widgets)
            self.p_widget_values.update(this_tab.p_widget_values)
            self.p_widget_actions.update(this_tab.p_widget_actions)
            self.u_widgets.update(this_tab.u_widgets)
            self.u_widget_values.update(this_tab.u_widget_values)
            self.previous_units.update(this_tab.previous_units)
            orb.log.debug('* [pgxnobj] adding tab: %s' % tab_name)
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
                if 'delete' in perms and self.enable_delete:
                    self.delete_button = self.bbox.addButton('Delete',
                                                   QDialogButtonBox.ActionRole)
            else:
                self.bbox = QDialogButtonBox()
                if (not self.view_only and 'modify' in perms
                    and not getattr(self.obj, 'frozen', False)):
                        self.edit_button = self.bbox.addButton('Edit',
                                                   QDialogButtonBox.ActionRole)
                if (state.get('connected') and
                    isinstance(self.obj, orb.classes['ManagedObject']) and
                    not isinstance(self.obj,
                                   orb.classes['ParameterDefinition'])):
                    self.cloaking_button = self.bbox.addButton('Cloaking',
                                                   QDialogButtonBox.ActionRole)
        else:
            # not embedded -> external dialog
            self.modal_mode = True
            orb.log.debug('* [pgxnobj] external window: always modal mode)')
            if self.edit_mode:
                orb.log.debug('            setting up edit mode ...')
                # Cancel button cancels edits and switches to view mode
                self.bbox = QDialogButtonBox(QDialogButtonBox.Cancel)
                self.save_button = self.bbox.addButton('Save',
                                               QDialogButtonBox.ActionRole)
                self.save_and_close_button = self.bbox.addButton(
                                               'Save and Close',
                                               QDialogButtonBox.ActionRole)
                if 'delete' in perms and self.enable_delete:
                    self.delete_button = self.bbox.addButton('Delete',
                                               QDialogButtonBox.ActionRole)
                # if hasattr(self, 'edit_button'):
                    # # if switching to edit mode, don't need 'Edit' button
                    # try:
                        # self.bbox.removeButton(self.edit_button)
                    # except:
                        # # C++ object went away?
                        # pass
            else:
                orb.log.debug('            setting up view mode ...')
                self.bbox = QDialogButtonBox()
                orb.log.debug('            checking perms ...')
                if (not self.view_only and 'modify' in perms
                    and not getattr(self.obj, 'frozen', False)):
                    orb.log.debug('            "modify" in perms --')
                    orb.log.debug('            adding "edit" button ...')
                    self.edit_button = self.bbox.addButton('Edit',
                                               QDialogButtonBox.ActionRole)
                if (state.get('connected') and
                    isinstance(self.obj, orb.classes['ManagedObject']) and
                    not isinstance(self.obj,
                               orb.classes['ParameterDefinition'])):
                    self.cloaking_button = self.bbox.addButton('Cloaking',
                                               QDialogButtonBox.ActionRole)
            self.close_button = self.bbox.addButton(QDialogButtonBox.Close)
            self.close_button.clicked.connect(self.on_close)
        self.vbox.addWidget(self.tabs)
        self.vbox.setStretch(1, 1)
        self.vbox.addWidget(self.bbox)
        self.create_connections()
        self.tabs.setCurrentIndex(self.go_to_tab)
        self.adjustSize()

    def on_close(self):
        self.close()

    def sizeHint(self):
        if getattr(self, 'tabs'):
            # tool bar height fudged as 80 ...
            return QSize(self.tabs.sizeHint().width(),
                         self.tabs.sizeHint().height() + 100)
        else:
            return QSize(self.sizeHint().width(),
                         self.sizeHint().height() + 100)

    def create_connections(self):
        if hasattr(self, 'edit_button'):
            self.edit_button.clicked.connect(self.on_edit)
        if hasattr(self, 'save_button'):
            self.save_button.clicked.connect(self.on_save)
        if hasattr(self, 'save_and_close_button'):
            self.save_and_close_button.clicked.connect(self.on_save_and_close)
        if hasattr(self, 'delete_button'):
            self.delete_button.clicked.connect(self.on_delete)
        if hasattr(self, 'cloaking_button'):
            self.cloaking_button.clicked.connect(self.on_cloaking)
        self.bbox.rejected.connect(self.cancel)

    def on_edit(self):
        orb.log.info('* [pgxnobj] switching to edit mode ...')
        self.go_to_tab = self.tabs.currentIndex()
        self.edit_mode = True
        self.build_from_object()

    def on_delete(self):
        orb.log.info('* [pgxnobj] delete action selected ...')
        if getattr(self.obj, 'where_used', None):
            txt = 'This Product cannot be deleted:\n'
            txt += 'it is a component in the following assemblies:'
            notice = QMessageBox(QMessageBox.Warning, 'Cannot Delete', txt,
                                 QMessageBox.Ok, self)
            assemblies = [acu.assembly for acu in self.obj.where_used]
            text = '<p><ul>{}</ul></p>'.format('\n'.join(
                           ['<li><b>{}</b><br>(id: {})</li>'.format(
                           a.name, a.id, a.oid) for a in assemblies]))
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
        txt = ('This will permanently delete the object -- '
               'are you really really sure?')
        confirm_dlg = QMessageBox(QMessageBox.Question, 'Delete?', txt,
                                  QMessageBox.Yes | QMessageBox.No)
        response = confirm_dlg.exec_()
        if response == QMessageBox.Yes:
            obj_oid = self.obj.oid
            cname = self.obj.__class__.__name__
            # orb.delete will add serialized object to trash
            orb.delete([self.obj])
            # the 'deleted object' signal will notify the repository to delete
            # the object from the repository and pangalaxian will remove it
            # from the state['syced_oids'] list.
            dispatcher.send(signal='deleted object', oid=obj_oid, cname=cname)
            if not self.embedded:
                orb.log.info('* [pgxnobj] non-embedded mode, exiting ...')
                self.close()

    def on_del_parameter(self, pid=None):
        delete_parameter(orb, self.obj.oid, pid)
        self.obj.modifier = orb.get(state.get('local_user_oid'))
        self.obj.mod_datetime = dtstamp()
        orb.save([self.obj])
        dispatcher.send(signal='modified object', obj=self.obj)
        self.build_from_object()

    def on_cloaking(self):
        orb.log.info('* [pgxnobj] sending "cloaking" signal ...')
        dispatcher.send(signal='cloaking', oid=self.obj.oid)

    def cancel(self):
        if self.edit_mode:
            txt = '* [pgxnobj] unsaved edits cancelled, rolling back...'
            orb.log.info(txt)
            orb.db.rollback()
            self.edit_mode = False
            self.build_from_object()

    def closeEvent(self, event):
        txt = '* [pgxnobj] unsaved edits cancelled, rolling back...'
        orb.log.info(txt)
        orb.db.rollback()
        self.close()

    def update_save_progress(self, name=''):
        try:
            if getattr(self, 'progress_dialog', None):
                self.progress_value += 1
                self.progress_dialog.setValue(self.progress_value)
                self.progress_dialog.setLabelText(
                    'parameters cached for: {}'.format(name))
        except:
            # oops -- my C++ object probably got deleted
            pass

    def on_save_and_close(self):
        self.closing = True
        self.on_save()

    def on_save(self):
        orb.log.info('* [pgxnobj] saving ...')
        cname = self.obj.__class__.__name__
        fields_dict = {}
        for name in self.editable_widgets:
            fields_dict[name] = self.editable_widgets[name].get_value()
        required = self.required or PGXN_REQD.get(cname)
        msg_dict = validate_all(fields_dict, cname, self.schema, self.view,
                                required=required, idvs=self.all_idvs,
                                html=True)
        if list(msg_dict.keys()):   # one or more field values are invalid
            orb.log.debug('  validation errors: {}'.format(str(msg_dict)))
            # TODO:  validation dialog
            dlg = ValidationDialog(msg_dict)
            if dlg.exec_():
                return
        caching_parameters = False
        if (isinstance(self.obj, orb.classes['Modelable'])
            and not isinstance(self.obj, orb.classes['ParameterDefinition'])):
            caching_parameters = True
            progress_max = orb.get_count('Modelable') + 3
            self.progress_dialog = ProgressDialog(title='Save',
                                              label='Saving...',
                                              maximum=progress_max,
                                              parent=self)
            self.progress_dialog.setAttribute(Qt.WA_DeleteOnClose)
        else:
            self.progress_dialog = None
        NOW = dtstamp()
        if caching_parameters:
            self.progress_dialog.setValue(1)
        if cname == 'ParameterDefinition' and self.new:
            new_id = str(self.editable_widgets['id'].get_value())
            # create a new blank PD and destroy the temp one
            temp_obj = self.obj
            self.obj = clone('ParameterDefinition', id=new_id,
                             oid=get_parameter_definition_oid(new_id))
            orb.db.delete(temp_obj)
            for name, val in fields_dict.items():
                setattr(self.obj, name, val)
                orb.log.info('  [pgxnobj] - {}: {}'.format(
                                            name, val.__repr__()))
            user_obj = orb.get(state.get('local_user_oid'))
            self.obj.creator = user_obj
            self.obj.modifier = user_obj
            self.obj.create_datetime = NOW
            self.obj.mod_datetime = NOW
            orb.save([self.obj])
            QApplication.processEvents()
            parent = self.parent()
            if parent:
                parent.setFocus()
            orb.log.debug('  [pgxnobj] sending "new object" signal')
            dispatcher.send(signal="new object", obj=self.obj,
                            cname=cname)
        else:
            for name, val in fields_dict.items():
                setattr(self.obj, name, val)
                orb.log.debug('  [pgxnobj] - {}: {}'.format(
                              name, val.__repr__()))
            # NOTE:  for new objects, save *ALL* parameters (they are new
            # also); for existing objects, save only modified parameters
            # if parameterz.get(self.obj.oid) and self.new:
            if self.new:
                for p_id in self.p_widgets:
                    # only non-computed parm widgets have 'get_value'
                    if hasattr(self.p_widgets[p_id], 'get_value'):
                        str_val = self.p_widgets[p_id].get_value()
                        set_pval_from_str(orb, self.obj.oid, p_id, str_val)
            # elif parameterz.get(self.obj.oid):
            else:
                # if object is *not* new, save any modified parameters
                for p_id in self.p_widgets:
                    # if p is computed, its widget is a label (no 'get_value')
                    # DO NOT MODIFY units/values ... but:
                    # TODO:  set display units for all related parameters (same
                    #        variable) when user sets it for any one of them.
                    #        *AND* set it in user prefs for that parameter.
                    if hasattr(self.p_widgets[p_id], 'get_value'):
                        str_val = self.p_widgets[p_id].get_value()
                        # u_cur -> current units setting
                        # (None if can't modify, which also means base units)
                        u_cur = None
                        if hasattr(self.u_widgets[p_id], 'currentText'):
                            u_cur = self.u_widgets[p_id].currentText()
                            # orb.log.debug('  - units widget set to {}'.format(
                                                                        # u_cur))
                        # set parameter values/units for ALL editable
                        # parameters (faster/simpler than checking for mods)
                        # orb.log.debug('  - setting {} to {} {}'.format(
                                      # p_id, str_val, u_cur))
                        set_pval_from_str(orb, self.obj.oid, p_id, str_val,
                                          units=u_cur)
            if caching_parameters:
                self.progress_dialog.setValue(2)
            user_obj = orb.get(state.get('local_user_oid'))
            if self.new:
                self.obj.creator = user_obj
                self.obj.create_datetime = NOW
            self.obj.modifier = user_obj
            self.obj.mod_datetime = NOW
            if caching_parameters:
                self.progress_value = 3
                self.progress_dialog.setValue(self.progress_value)
            orb.save([self.obj])
            if self.new:
                if cname == 'Project':
                    orb.log.debug('  [pgxnobj] send "new project" signal')
                    dispatcher.send(signal="new project", obj=self.obj)
                else:
                    # generic new object signal
                    orb.log.debug('  [pgxnobj] sending "new object" signal')
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
                orb.log.debug('  [pgxnobj] send "modified object" signal')
                dispatcher.send(signal="modified object", obj=self.obj,
                                cname=cname)
                if isinstance(self.obj, orb.classes['Activity']):
                    dispatcher.send(signal="modified activity",
                                    activity=self.obj)
            if caching_parameters:
                QApplication.processEvents()
                self.progress_dialog.setValue(progress_max)
                self.progress_dialog.done(0)
                self.progress_value = 0
            parent = self.parent()
            if parent:
                parent.setFocus()
        if getattr(self, 'closing', False):
            orb.log.debug('  [pgxnobj] saving and closing ...')
            # reset 'closing'
            self.closing = False
            self.close()
        else:
            orb.log.debug('  [pgxnobj] saved -- rebuilding ...')
            self.edit_mode = False
            self.build_from_object()
        if state.get('mode') in ['system', 'component']:
            dispatcher.send(signal='update product modeler', obj=self.obj)

    def on_select_related(self):
        orb.log.info('* [pgxnobj] select related object ...')
        widget = self.sender()
        obj = widget.get_value()
        # TODO:  if None, give option to create a new object (with pgxnobject)
        orb.log.debug('  [pgxnobj] current object: {}'.format(obj.oid))
        cname = widget.related_cname
        field_name = widget.field_name
        # SELECTION_FILTERS define the set of valid objects for this field
        objs = []
        if SELECTION_FILTERS.get(field_name):
            fltrs = SELECTION_FILTERS[field_name]
            for cname in fltrs:
                if fltrs[cname]:
                    objs += orb.select(cname, **fltrs[cname])
                else:
                    objs += orb.get_by_type(cname)
        else:
            objs = orb.get_all_subtypes(cname)
        if objs:
            orb.log.debug('  [pgxnobj] object being edited: {}'.format(
                                                            self.obj.oid))
            if self.obj in objs:
                # exclude the object being edited from the selections
                orb.log.debug('            removing it from selectables ...')
                objs.remove(self.obj)
            orb.log.debug('  [pgxnobj] selectable objects:')
            for o in objs:
                orb.log.debug('            {}'.format(o.id))
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
        orb.log.info('* [pgxnobj] view related object ...')
        widget = self.sender()
        obj = widget.get_value()
        orb.log.debug('* [pgxnobj]   object: %s' % str(obj))
        # TODO:  if editable, bring up selection list of possible values
        # or, if none, give option to create a new object (with pgxnobject)
        if obj:
            self.new_window = PgxnObject(obj)
            # show() -> non-modal dialog
            self.new_window.show()


if __name__ == '__main__':
    """
    Cmd line invocation for testing / prototyping
    """
    import sys
    from pangalactic.node.serializers import deserialize
    from pangalactic.test.utils4test import create_test_project
    from pangalactic.test.utils4test import create_test_users
    app = QApplication(sys.argv)
    # ***************************************
    # Test using ref and test data
    # ***************************************
    if len(sys.argv) < 2:
        print(' * You must specify a home directory for the orb *')
        sys.exit()
    home = sys.argv[1]
    orb.start(home, console=True, debug=True)
    deserialize(orb, create_test_users() + create_test_project())
    HardwareProduct = orb.classes['HardwareProduct']
    test_part = HardwareProduct(oid='fusionworld:mrfusion.000',
            id='mrfusion.000', id_ns='fusionworld', name='Mr. Fusion v.000',
            security_mask=0, description='Fusion Power Source, MF Series',
            comment='Omni-Fuel, Compact Semi-Portable Fusion Power Module')
    h2g2 = orb.get('hog0')
    if h2g2:
        test_part = h2g2
    admin = orb.get('pgefobjects:admin')
    pgana = orb.get('pgefobjects:PGANA')
    window = PgxnObject(test_part)
    window.show()
    sys.exit(app.exec_())

