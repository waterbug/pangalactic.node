# -*- coding: utf-8 -*-
"""
Requirements Wizards
"""
import os
from PyQt5 import QtGui
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QButtonGroup, QComboBox, QDialogButtonBox,
                             QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                             QFrame, QMessageBox, QPlainTextEdit, QPushButton,
                             QRadioButton, QVBoxLayout, QWizard, QWizardPage)

from louie import dispatcher

from pangalactic.core             import config, state
from pangalactic.core.names       import (get_attr_ext_name, get_parm_rel_id,
                                          get_parm_rel_name, get_rel_id,
                                          get_rel_name)
from pangalactic.core.parametrics import parm_defz
from pangalactic.core.uberorb     import orb
from pangalactic.core.utils.datetimes import dtstamp
from pangalactic.core.units       import alt_units
from pangalactic.node.libraries   import LibraryListView
from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.utils       import clone, RqtAllocDelegate
from pangalactic.node.widgets     import PlaceHolder, NameLabel, ValueLabel
from pangalactic.node.systemtree  import SystemTreeView

rqt_wizard_state = {}


class QHLine(QFrame):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.HLine)


class QVLine(QFrame):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.VLine)


class RqtWizard(QWizard):
    """
    Wizard for project requirements (both functional and performance)
    """
    def __init__(self, rqt=None, parent=None, performance=False):
        """
        Initialize Requirements Wizard.

        Args:
            rqt (Requirement): a Requirement object (provided only when wizard
                is being invoked in order to edit an existing requirement.
        """
        super().__init__(parent)
        self.setWizardStyle(QWizard.ClassicStyle)
        self.setTitleFormat(Qt.RichText)
        self.setSubTitleFormat(Qt.RichText)
        included_buttons = [QWizard.Stretch,
                            QWizard.BackButton,
                            QWizard.NextButton,
                            QWizard.FinishButton,
                            QWizard.CancelButton]
        self.setButtonLayout(included_buttons)
        self.button(QWizard.CancelButton).clicked.connect(
                self.on_cancel)
        self.setOptions(QWizard.NoBackButtonOnStartPage)
        self.setSubTitleFormat(Qt.RichText)
        # clear the rqt_wizard_state
        for x in rqt_wizard_state:
            rqt_wizard_state[x] = None
        project_oid = state.get('project')
        proj = orb.get(project_oid)
        self.project = proj
        rqt_wizard_state['req_parameter'] = ''
        self.new_req = True
        if isinstance(rqt, orb.classes['Requirement']):
            self.new_req = False
            rqt_wizard_state['req_oid'] = rqt.oid
            # NOTE: the following state variables take the same values as their
            # counterparts in the attributes of Requirement -- HOWEVER, the
            # state variables 'req_parameter' and 'computable_form_oid' are
            # special cases and are handled differently ...
            for a in [
                'comment',
                'description',
                'justification',
                'rationale',
                'req_compliance',
                'req_constraint_type',
                'req_object',
                'req_level',
                'req_maximum_value',
                'req_minimum_value',
                'req_predicate',
                'req_subject',
                'req_target_value',
                'req_tolerance',
                'req_tolerance_lower',
                'req_tolerance_type',
                'req_tolerance_upper',
                'req_units',
                'validated',
                'verification_method'
                ]:
                rqt_wizard_state[a] = getattr(rqt, a)
            # 'performance' flag indicates req_type:
            #    - True  -> performance requirement
            #    - False -> functional requirement
            rqt_wizard_state['computable_form_oid'] = getattr(
                                                rqt.computable_form, 'oid', '')
            performance = (rqt.req_type == 'performance')
        if not performance:
            rqt_wizard_state['performance'] = False
            self.addPage(RequirementIDPage(self))
            self.addPage(RqtAllocPage(self))
            self.addPage(RqtVerificationPage(self))
            self.addPage(RqtSummaryPage(self))
            self.setWindowTitle('Functional Requirement Wizard')
            self.setGeometry(50, 50, 850, 900);
        else:
            rqt_wizard_state['performance'] = True
            if not self.new_req:
                # if an existing performance requirement, it has a parameter
                # (unless its data is corrupted -- but we sholdn't crash from
                # corrupted data!)
                rel = rqt.computable_form
                if rel:
                    prs = rel.correlates_parameters
                    if prs:
                        pr = prs[0]
                        pd = pr.correlates_parameter
                        rqt_wizard_state['req_parameter'] = pd.id
            self.addPage(RequirementIDPage(self))
            self.addPage(RqtAllocPage(self))
            self.addPage(PerformanceDefineParmPage(self))
            self.addPage(PerformRqtShallPage(self))
            # TODO: make PerformanceMarginCalcPage useful ...
            # self.addPage(PerformanceMarginCalcPage(self))
            self.addPage(RqtVerificationPage(self))
            self.addPage(RqtSummaryPage(self))
            self.setWindowTitle('Performance Requirement Wizard')
            self.setGeometry(50, 50, 850, 750);
        self.setSizeGripEnabled(True)

    def on_cancel(self):
        if self.new_req:
            # if a new Requirement was being created, delete it and all
            # associated objects ...
            req_oid = rqt_wizard_state.get('req_oid')
            rqt = orb.get(req_oid)
            if rqt:
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
                # delete the Requirement object
                orb.delete([rqt])
                dispatcher.send(signal='deleted object', oid=req_oid,
                                cname='Requirement')
        self.reject()

###########################
# General Requirement Pages
###########################

# Includes ID page which includes identifier, name, and summary.

class RequirementIDPage(QWizardPage):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Requirement Identification")
        self.setSubTitle("Identify the requirement you are creating...")
        layout = QHBoxLayout()
        logo_path=config.get('tall_logo')
        if logo_path:
            image_path=os.path.join(orb.image_dir, logo_path)
            layout.addWidget(PlaceHolder(image=image_path,parent=self))
        self.setLayout(layout)

    def initializePage(self):
        """
        Page for initial definitions of a requirement. This includes assigning
        a name, description, rationale, parent, and level.
        """
        performance = rqt_wizard_state.get('performance')
        proj_oid = state.get('project') or 'pgefobjects:SANDBOX'
        self.project = orb.get(proj_oid)
        rqt = orb.get(rqt_wizard_state.get('req_oid'))
        if rqt:
            self.rqt = rqt
            new = False
        else:
            # NOTE: requirement id must be generated *after* cloning new reqt.;
            # otherwise, generator will get confused
            req_id = self.project.id + '-TBD'
            self.rqt = clone("Requirement", id=req_id, owner=self.project,
                             level=0, public=True)
            self.rqt.id = orb.gen_req_id(self.rqt)
            orb.save([self.rqt])
            dispatcher.send(signal='new rqt', obj=self.rqt)
            new = True
        dispatcher.connect(self.saved, 'modified object')
        rqt_wizard_state['req_oid'] = self.rqt.oid
        # Where the performance and functional differ
        main_view = []
        required = []
        title_text = None
        if performance:
            main_view = ['id', 'name']
            required = ['name']
            mask = ['id']
            if new:
                title_text = '<h3><font color="blue">'
                title_text += 'New Performance Requirement'
                title_text += '</font></h3>'
        else:
            main_view = ['id', 'name', 'description', 'justification',
                         'rationale', 'comment']
            required = ['name', 'description', 'rationale']
            mask = ['id']
            if new:
                title_text = '<h3><font color="blue">'
                title_text += 'New Functional Requirement'
                title_text += '</font></h3>'
        panels = ['main']
        self.pgxn_obj = PgxnObject(self.rqt, embedded=True, panels=panels,
                                   main_view=main_view, required=required,
                                   # mask=mask, edit_mode=True, new=new,
                                   mask=mask, edit_mode=True,
                                   enable_delete=False, title_text=title_text)
        self.pgxn_obj.toolbar.hide()
        self.pgxn_obj.save_button.clicked.connect(self.saved)
        self.pgxn_obj.save_button.clicked.connect(self.update_levels)
        self.pgxn_obj_cancel_button = self.pgxn_obj.bbox.button(
                                                QDialogButtonBox.Cancel)
        self.pgxn_obj_cancel_button.clicked.connect(self.saved)
        self.pgxn_obj_cancel_button.clicked.connect(self.update_levels)
        self.pgxn_obj.setAttribute(Qt.WA_DeleteOnClose)
        self.wizard().button(QWizard.FinishButton).clicked.connect(
                self.close_pgxn_obj)
        instructions = '<p>The following fields are required:<ul>'
        instructions += '<li><b>name</b>: descriptive name '
        instructions += '(may contain spaces)</li>'
        if not performance:
            instructions += '<li><b>description</b>: Requirement text '
            instructions += 'that contains the shall statement</li>'
            instructions += '<li><b>rational</b>: reason for requirement'
            instructions += '</li>'
        instructions += '<li><b>derived from</b>: Requirement\'s parent'
        instructions += '<li><b>level</b>: The level of the requirement</li>'
        instructions += '</ul>'
        instructions += '<p><i>NOTE:</i> you must click <b>Save</b> '
        instructions += 'to activate the <b>Next</b> button.</p>'
        inst_label = QLabel(instructions)
        self.level_cb = QComboBox()
        self.level_cb.setDisabled(True)
        self.level_cb.addItem('0')
        self.level_cb.addItem('1')
        self.level_layout = QFormLayout()
        self.level_label = QLabel('level: ')
        self.level_layout.addRow(self.level_label, self.level_cb)
        self.level_cb.currentIndexChanged.connect(self.level_select)
        id_panel_layout = QVBoxLayout()
        id_panel_layout.addWidget(inst_label)
        id_panel_layout.addWidget(self.pgxn_obj)
        id_panel_layout.addStretch(1)
        id_panel_layout.addLayout(self.level_layout)
        main_layout = self.layout()
        main_layout.addLayout(id_panel_layout)

    def level_select(self):
        self.rqt.req_level = self.level_cb.currentText()

    def update_levels(self):
        # NOTE: update_levels is triggered when pgxnobject saves, so update
        # rqt_wizard_state to sync with the saved rqt attributes ...
        rqt_wizard_state['description'] = self.rqt.description
        rqt_wizard_state['rationale'] = self.rqt.rationale
        rqt_wizard_state['justification'] = self.rqt.justification
        rqt_wizard_state['comment'] = self.rqt.comment
        self.level_cb.removeItem(1)
        self.level_cb.removeItem(0)
        if self.rqt.parent_requirements:
            parent_levels = [pr.parent_requirement.req_level or 0
                             for pr in self.rqt.parent_requirements]
            try:
                max_level = max(parent_levels)
            except:
                max_level = 0
        else:
            max_level = 0
        self.level_cb.addItem(str(max_level))
        self.level_cb.addItem(str(max_level + 1))
        self.pgxn_obj_cancel_button.clicked.connect(self.saved)
        self.pgxn_obj.save_button.clicked.connect(self.saved)

    def close_pgxn_obj(self):
        if getattr(self,'pgxn_obj', None):
            self.pgxn_obj.close()
            self.pgxn_obj = None

    def saved(self):
        self.completeChanged.emit()

    def isComplete(self):
        orb.log.debug('* RqtID.isComplete()')
        if self.rqt.name:
            return True
        else:
            return False


class RqtVerificationPage(QWizardPage):
    """
    Page for selecting the verification method for the requirement.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        self.setLayout(layout)

    def initializePage(self):
        if self.title():
            return
        self.setTitle('Requirement Verification Method')
        self.setSubTitle('Select a verification method for the requirement...')
        instructions = '<p>Select the verification method which will be used'
        instructions += ' for this requirement.<br>'
        instructions += 'If you are unsure select \'Specify Verification Method'
        instructions += ' Later\''
        inst_label = QLabel(instructions)
        layout = self.layout()
        self.verif_method_buttons = QButtonGroup()

        test_button = QRadioButton("Test")
        analysis_button = QRadioButton("Analysis")
        inspection_button = QRadioButton("Inspection")
        later_button = QRadioButton("Specify Verification Method Later")
        later_button.setChecked(True)
        self.verif_method_buttons.addButton(test_button)
        self.verif_method_buttons.addButton(analysis_button)
        self.verif_method_buttons.addButton(inspection_button)
        self.verif_method_buttons.addButton(later_button)
        verification_method = rqt_wizard_state.get('verification_method',
                                          'Specify Verification Method Later')
        if verification_method:
            if verification_method == "Test":
                test_button.setChecked(True)
            elif verification_method == "Analysis":
                analysis_button.setChecked(True)
            elif verification_method == "Inspection":
                inspection_button.setChecked(True)
            elif verification_method == "Specify Verification Method Later":
                later_button.setChecked(True)
        layout.addWidget(inst_label)
        layout.addWidget(test_button)
        layout.addWidget(analysis_button)
        layout.addWidget(inspection_button)
        layout.addWidget(later_button)
        self.verif_method_buttons.buttonClicked.connect(
                                                self.set_verification_method)
        self.setLayout(layout)

    def set_verification_method(self):
        rqt_wizard_state['verification_method'
                        ] = self.verif_method_buttons.checkedButton().text()


class RqtAllocPage(QWizardPage):
    """
    Page to allocate the requirement to a project, a system role, or a
    function (identified by reference designator) within a system
    architecture.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

    def initializePage(self):
        self.rqt = orb.get(rqt_wizard_state.get('req_oid'))
        if not self.rqt:
            # TODO: if reqt cant be found, show messsage (page is useless then)
            orb.log.info('* RqtAllocPage: requirement not found')
        if self.title():
            return;
        self.setTitle("Requirement Allocation")
        self.setSubTitle("To specify the system or function "
                         "that will satisfy the requirement, "
                         "<b>CLICK</b> on a tree node.")
        project_oid = state.get('project')
        proj = orb.get(project_oid)
        self.project = proj
        self.sys_tree = SystemTreeView(self.project, refdes=True,
                                       show_allocs=True, rqt=self.rqt)
        self.sys_tree.setItemDelegate(RqtAllocDelegate())
        self.sys_tree.expandToDepth(1)
        self.sys_tree.setExpandsOnDoubleClick(False)
        self.sys_tree.clicked.connect(self.on_select_node)
        main_layout = self.layout()
        content_layout = QHBoxLayout()
        main_layout.addLayout(content_layout, stretch=1)
        tree_layout = QVBoxLayout()
        tree_layout.addWidget(self.sys_tree)
        summary_layout = QVBoxLayout()
        self.summary = QLabel()
        summary_layout.addWidget(self.summary, stretch=1,
                                 alignment=Qt.AlignTop)
        content_layout.addLayout(tree_layout)
        content_layout.addLayout(summary_layout)
        self.update_summary()
        alloc = getattr(self.rqt, 'allocated_to', None)
        allocation = 'None'
        if alloc:
            if hasattr(alloc, 'component'):
                allocation = alloc.reference_designator
            elif hasattr(alloc, 'system'):
                allocation = alloc.system_role
            else:
                allocation = alloc.id + ' project'
        rqt_wizard_state['allocation'] = allocation

    def on_select_node(self, index):
        link = None
        allocated_item = 'None'
        mapped_i = self.sys_tree.proxy_model.mapToSource(index)
        link = self.sys_tree.source_model.get_node(mapped_i).link
        cname = self.sys_tree.source_model.get_node(mapped_i).cname
        if (not link and not (cname == 'Project')) or not self.rqt:
            orb.log.debug('  node is not link or project (or no self.rqt).')
            return
            # DEPRECATED attribute 'system_requirements'
            # if self.rqt in link.system_requirements:
                # # if this is an existing allocation, remove it
                # self.rqt.allocated_to_system = None
            # else:
                # self.rqt.allocated_to_system = link
                # # if allocating to system, remove any allocation to function
                # if self.rqt.allocated_to_function:
                    # self.rqt.allocated_to_function = None
            # allocated_item = link.system_role
        if cname == 'Project':
            if self.rqt.allocated_to is self.project:
                # if allocated, de-allocate
                self.rqt.allocated_to = None
            else:
                self.rqt.allocated_to = self.project
                allocated_item = self.project.id + ' project'
        else:
            if self.rqt.allocated_to is link:
                # if allocated, de-allocate
                self.rqt.allocated_to = None
            else:
                self.rqt.allocated_to = link
                if hasattr(link, 'system'):
                    allocated_item = link.system_role
                elif hasattr(link, 'component'):
                    allocated_item = link.reference_designator
        # the expandToDepth is needed to make it repaint to show the allocation
        # node as yellow-highlighted
        self.sys_tree.expandToDepth(1)
        self.sys_tree.scrollTo(index)
        # TODO: get the selected name/product so it can be used in the shall
        # statement.
        rqt_wizard_state['allocation'] = allocated_item
        self.update_summary()

    def update_summary(self):
        """
        Update the summary of current allocations.
        """
        msg = '<h3>Requirement Allocation:</h3><ul><li><b>'
        alloc = self.rqt.allocated_to
        if alloc:
            if hasattr(alloc, 'system'):
                msg += '<font color="green">'
                msg += alloc.system_role
                msg += '</font>'
            elif hasattr(alloc, 'component'):
                msg += '<font color="green">'
                msg += alloc.reference_designator
                msg += '</font>'
            elif hasattr(alloc, 'id'):
                # Project
                msg += '<font color="green">'
                msg += alloc.id
                msg += '</font>'
            else:
                msg += "None"
        msg += '</b></li></ul>'
        self.summary.setText(msg)

    def validatePage(self):
        """
        Method called when the Next button is clicked.  Here we are using it to
        do the db-intensive stuff.
        """
        orb.log.debug('* validatePage() called for RqtAllocPage')
        # TODO:  test to ensure this fully works
        self.rqt.mod_datetime = dtstamp()
        self.rqt.modifier = orb.get(state.get('local_user_oid'))
        orb.save([self.rqt])
        # Qt api requires validatePage() to return a boolean
        return True


class RqtSummaryPage(QWizardPage):
    """
    Page to view a summary before saving the Requirement.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        form = QFormLayout()
        self.labels = {}
        self.fields = {}
        for a in ['id', 'name', 'description', 'justification', 'rationale',
                  'allocation', 'verification_method']:
            self.labels[a] = NameLabel(get_attr_ext_name('Requirement', a))
            self.fields[a] = ValueLabel('')
            form.addRow(self.labels[a], self.fields[a])
        layout.addLayout(form)
        self.setLayout(layout)
        self.updateGeometry()

    def initializePage(self):
        if not self.title():
            self.setTitle('Requirement Summary')
            self.setSubTitle('Confirm all the information is correct...')
        self.rqt = orb.get(rqt_wizard_state.get('req_oid'))
        allocation = rqt_wizard_state.get('allocation', 'No Allocation')
        self.fields['allocation'].setText(allocation)
        for a in ['id', 'name']:
             self.fields[a].setText(getattr(self.rqt, a, '[Not Specified]'))
        for a in ['description', 'justification', 'rationale',
                  'verification_method']:
             self.fields[a].setText(rqt_wizard_state.get(a, '[Not Specified]'))
        self.wizard().button(QWizard.FinishButton).clicked.connect(self.finish)

    def finish(self):
        # assign description, rationale, etc. ...
        self.rqt.description = rqt_wizard_state['description']
        self.rqt.rationale = rqt_wizard_state['rationale']
        self.rqt.justification = rqt_wizard_state['justification']
        self.rqt.req_target_value = rqt_wizard_state.get('req_target_value')
        self.rqt.req_maximum_value = rqt_wizard_state.get('req_maximum_value')
        self.rqt.req_minimum_value = rqt_wizard_state.get('req_minimum_value')
        if self.rqt.req_constraint_type == 'single value':
            if not self.rqt.req_target_value:
                return False
            if (self.rqt.req_tolerance_type == 'Symmetric Tolerance'
                and self.rqt.req_tolerance is None):
                return False
            elif (self.rqt.req_tolerance_lower is None
                  or self.rqt.req_tolerance_upper is None):
                # Asymmetric Tolerance requires upper and lower tols
                return False
        elif (self.rqt.req_constraint_type == 'maximum'
              and self.rqt.req_maximum_value is None):
            return False
        elif (self.rqt.req_constraint_type == 'minimum'
              and self.rqt.req_minimum_value is None):
            return False
        self.rqt.computable_form = orb.get(
                                       rqt_wizard_state.get('computable_form_oid'))
        self.rqt.req_constraint_type = rqt_wizard_state.get('req_constraint_type')
        self.rqt.req_tolerance_type = rqt_wizard_state.get('req_tolerance_type')
        self.rqt.verification_method = rqt_wizard_state.get('verification_method')
        self.rqt.req_target_value = rqt_wizard_state.get('req_target_value')
        self.rqt.req_units = rqt_wizard_state.get('req_units')
        self.rqt.req_maximum_value = rqt_wizard_state.get('req_maximum_value')
        self.rqt.req_minimum_value = rqt_wizard_state.get('req_minimum_value')
        self.rqt.req_tolerance = rqt_wizard_state.get('req_tolerance')
        self.rqt.req_tolerance_lower = rqt_wizard_state.get('req_tolerance_lower')
        self.rqt.req_tolerance_upper = rqt_wizard_state.get('req_tolerance_upper')
        self.rqt.req_subject = rqt_wizard_state.get('req_subject')
        self.rqt.req_predicate = rqt_wizard_state.get('req_predicate')
        self.rqt.req_object = rqt_wizard_state.get('req_object')
        self.rqt.mod_datetime = dtstamp()
        self.rqt.modifier = orb.get(state.get('local_user_oid'))
        orb.save([self.rqt])
        dispatcher.send(signal='modified object', obj=self.rqt)


###############################
# Performance Requirement Pages
###############################

# Includes PerformanceDefineParmPage, PerformRqtShallPage, and in the future,
# PerformanceMarginCalcPage (margin calculation).

class PerformanceDefineParmPage(QWizardPage):
    """
    Page to add some definitions to the value part so it can be used for
    creating the "shall statement" (Requirement.description) on the next page.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout()
        self.setLayout(layout)

    def initializePage(self):
        if self.title():
            return
        self.rqt = orb.get(rqt_wizard_state.get('req_oid'))
        project_oid = state.get('project')
        proj = orb.get(project_oid)
        self.project = proj
        self.setTitle('Parameter Selection')
        subtxt = 'To select a performance parameter, '
        subtxt += "<b>DOUBLE-CLICK</b> on the parameter."
        self.setSubTitle(subtxt)

        # The inner layouts
        self.parm_layout = QVBoxLayout()
        type_form = QFormLayout()

        # Parameter list from which to select the performance parameter being
        # constrained by the requirement.
        # NOTE: if this page is initialized with an existing requirement that
        # has an associated parameter, that parameter should be displayed as
        # having been selected in this list -- that will be done at the end of
        # this initializePage() function ...
        self.parm_list = LibraryListView('ParameterDefinition',
                                         include_subtypes=False,
                                         draggable=False, parent=self)
        self.parm_list.setSelectionBehavior(LibraryListView.SelectRows)
        self.parm_list.setSelectionMode(LibraryListView.SingleSelection)
        self.parm_list.clicked.connect(self.on_select_parm)
        self.parm_layout.addWidget(self.parm_list)

        # vertical line that will be used as a spacer between parameter
        # selection and the selection of the type of constraint.
        line = QVLine()
        line.setFrameShadow(QFrame.Sunken)

        # radio buttons for the  type specification including the label and the
        # form for the single value button to specify if it will use asymmetric
        # or symmetric tolerance.
        # TODO: handle single value, store in rqt_wizard_state
        self.single_form = QFormLayout()
        type_label = QLabel('Type: ')
        self.min_button = QRadioButton('minimum')
        self.max_button = QRadioButton('maximum')
        self.single_button = QRadioButton('single value')
        self.range_button = QRadioButton('range')
        self.single_cb = QComboBox()
        self.single_cb.addItem('Symmetric Tolerance')
        self.single_cb.addItem('Asymmetric Tolerance')
        self.single_cb.currentIndexChanged.connect(self.tolerance_changed)
        self.single_form.addRow(self.single_button, self.single_cb)
        self.single_cb.setDisabled(True)

        # Add to the button group and handle the button clicked
        self.constraint_buttons = QButtonGroup()
        self.constraint_buttons.addButton(self.min_button)
        self.constraint_buttons.addButton(self.max_button)
        self.constraint_buttons.addButton(self.single_button)
        self.constraint_buttons.addButton(self.range_button)
        constraint_type = rqt_wizard_state.get('req_constraint_type')
        if constraint_type:
            if constraint_type == 'minimum':
                self.min_button.setChecked(True)
            elif constraint_type == 'maximum':
                self.max_button.setChecked(True)
            elif constraint_type == 'single value':
                self.single_button.setChecked(True)
                tolerance_type = rqt_wizard_state.get('req_tolerance_type')
                if tolerance_type:
                    self.single_cb.setDisabled(False)
                    self.single_cb.setCurrentText(tolerance_type)
            elif constraint_type == 'range':
                self.range_button.setChecked(True)
        self.constraint_buttons.buttonClicked.connect(self.set_constraint_type)
        self.constraint_buttons.buttonClicked.connect(self.completeChanged)

        # create and add buttons to a vertical box layout
        radio_button_layout = QVBoxLayout()
        radio_button_layout.addWidget(self.min_button)
        radio_button_layout.addWidget(self.max_button)
        radio_button_layout.addLayout(self.single_form)
        radio_button_layout.addWidget(self.range_button)

        # add radio_button_layout to the main type layout.
        type_form.addRow(type_label, radio_button_layout)

        # set inner layout spacing
        self.parm_layout.setContentsMargins(20, 20, 20, 20)
        type_form.setContentsMargins(20, 20, 20, 20)

        # set main layout and add the layouts to it.
        layout = self.layout()
        layout.setSpacing(30)
        layout.addLayout(self.parm_layout)
        layout.addWidget(line)
        layout.addLayout(type_form)

        # check if we received an existing requirement with a parameter ...
        # if so, select it and call on_select_parm()
        rel = orb.get(rqt_wizard_state.get('computable_form_oid'))
        self.pd = None
        if rel:
            parm_rels = rel.correlates_parameters
            if parm_rels:
                self.pd = parm_rels[0].correlates_parameter
        if self.pd and self.pd in self.parm_list.model().objs:
            rqt_wizard_state['req_parameter'] = self.pd.id
            row = self.parm_list.model().objs.index(self.pd)
            i = self.parm_list.model().index(row, 0)
            self.parm_list.setCurrentIndex(i)
            self.on_select_parm(i)

    def on_select_parm(self, index):
        # if we are already showing a selected ParameterDefinition, remove it:
        if (hasattr(self, 'parm_pgxnobj') and
            hasattr(self, 'parm_layout')):
            self.parm_layout.removeWidget(self.parm_pgxnobj)
            # NOTE:  WA_DeleteOnClose kills the "ghost pgxnobject" bug
            self.parm_pgxnobj.setAttribute(Qt.WA_DeleteOnClose)
            self.parm_pgxnobj.parent = None
            self.parm_pgxnobj.close()
            self.parm_pgxnobj = None
        if len(self.parm_list.selectedIndexes()) == 1:
            i = self.parm_list.selectedIndexes()[0].row()
            self.pd = self.parm_list.model().objs[i]
            orb.log.info('* on_select_parm:  {}'.format(self.pd.id))
            # display the selected ParameterDefinition...
            main_view = ['id', 'name', 'description']
            panels = ['main']
            self.parm_pgxnobj = PgxnObject(self.pd, embedded=True,
                                   panels=panels, main_view=main_view,
                                   edit_mode=False, enable_delete=False)
            self.parm_pgxnobj.toolbar.hide()
            self.parm_layout.addWidget(self.parm_pgxnobj)

    def tolerance_changed(self):
        tol_type = self.single_cb.currentText()
        rqt_wizard_state['req_tolerance_type'] = tol_type

    def set_constraint_type(self):
        """
        Set the constraint type. This also enables and disables the combobox
        for the symmetric and asymmetric options with the single value button.
        """
        b = self.constraint_buttons.checkedButton()
        const_type = b.text()
        if const_type:
            rqt_wizard_state['req_constraint_type'] = const_type
        else:
            rqt_wizard_state['req_constraint_type'] = None
        if b == self.single_button:
            self.single_cb.setDisabled(False)
            rtt = self.single_cb.currentText()
            rqt_wizard_state['req_tolerance_type'] = rtt
        else:
            self.single_cb.setDisabled(True)

    def validatePage(self):
        """
        Method called when the Next button is clicked.  Here we are using it to
        do the db-intensive stuff.
        """
        orb.log.debug('* validatePage() called for PerformanceDefineParmPage')
        # a pd has been selected; create a ParameterRelation instance that
        # points to a Relation ('referenced_relation') and for which the
        # 'correlates_parameter' is the pd.  Set the Relation's oid as the
        # rqt_wizard_state['computable_form_oid'] -- the Relation will be the
        # Requirement's 'computable_form' attribute value.
        # First, check for any existing Relation and ParameterRelation:
        cf_oid = rqt_wizard_state.get('computable_form_oid')
        if cf_oid:
            # if any are found, destroy them ...
            cf = orb.get(cf_oid)
            if cf:
                if cf.correlates_parameters:
                    for pr in cf.correlates_parameters:
                        orb.delete([pr])
                orb.delete([cf])
        relid = get_rel_id(self.rqt.id, 'computable-form')
        relname = get_rel_name(self.rqt.name, 'Computable Form')
        rel = clone("Relation", id=relid, name=relname)
        orb.log.debug(f'  - computable form created: {relid}')
        # set Relation as requirement's 'computable_form'
        self.rqt.computable_form = rel
        prid = get_parm_rel_id(self.rqt.id, self.pd.id)
        prname = get_parm_rel_name(self.rqt.name, self.pd.name)
        pr = clone("ParameterRelation", id=prid, name=prname,
                   correlates_parameter=self.pd, referenced_relation=rel)
        orb.log.debug(f'  - parm rel created: {prid}')
        # rqt_wizard_state['pr_oid'] = pr.oid
        rqt_wizard_state['computable_form_oid'] = rel.oid
        rqt_wizard_state['req_parameter'] = self.pd.id
        orb.save([self.rqt])  # calls db.commit(), which commits rel & pr objs
        # Qt api requires validatePage() to return a boolean
        return True

    def isComplete(self):
        """
        Check if both dimension and type have been specified
        """
        # if (not rqt_wizard_state.get('computable_form_oid')
            # or not rqt_wizard_state.get('req_constraint_type')):
            # return False
        if (getattr(self, 'pd', None) and
            rqt_wizard_state.get('req_constraint_type')):
            return True
        return False


class PerformRqtShallPage(QWizardPage):
    """
    Finalize the "shall statement" (Requirement.description) and add the
    rationale and justification.  The 3 components of the shall statement are:
    [1] req_subject:  'name' attribute of 'allocated_to'
    [2] req_predicate:  'shall be' + phrase generated based on
    'req_constraint_type' (e.g. "less than", etc.)
    [3] req_object:  parameter value(s) and units in a form based on the
    'req_constraint_type'.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        self.setLayout(layout)

    def initializePage(self):
        self.rqt = orb.get(rqt_wizard_state.get('req_oid'))
        layout = self.layout()
        if self.title():
            # # remove from first hbox
            self.subj_pred_label.hide()
            self.shall_hbox.removeWidget(self.subj_pred_label)
            self.subj_pred_label.parent = None
            # remove from middle hbox
            if getattr(self, 'target_value', None):
                self.target_value.hide()
                self.shall_hbox.removeWidget(self.target_value)
                self.target_value.parent = None
                if getattr(self, 'lower_limit', None):
                    self.minus_label.hide()
                    self.shall_hbox.removeWidget(self.minus_label)
                    self.minus_label.parent = None
                    self.lower_limit.hide()
                    self.shall_hbox.removeWidget(self.lower_limit)
                    self.lower_limit.parent = None
                    self.plus_label.hide()
                    self.shall_hbox.removeWidget(self.plus_label)
                    self.plus_label.parent = None
                    self.upper_limit.hide()
                    self.shall_hbox.removeWidget(self.upper_limit)
                    self.upper_limit.parent = None
                    self.units.hide()
                    self.shall_hbox.removeWidget(self.units)
                    self.units.parent = None
                if getattr(self, 'plus_minus_label', None):
                    self.plus_minus_label.hide()
                    self.shall_hbox.removeWidget(self.plus_minus_label)
                    self.plus_minus_label.parent = None
                    self.tol_val_field.hide()
                    self.shall_hbox.removeWidget(self.tol_val_field)
                    self.tol_val_field.parent = None
                    self.units.hide()
                    self.shall_hbox.removeWidget(self.units)
                    self.units.parent = None
            if getattr(self, 'minimum_value', None):
                self.minimum_value.hide()
                self.shall_hbox.removeWidget(self.minimum_value)
                self.minimum_value.parent = None
                self.units.hide()
                self.shall_hbox.removeWidget(self.units)
                self.units.parent = None
            if getattr(self, 'maximum_value', None):
                self.maximum_value.hide()
                self.shall_hbox.removeWidget(self.maximum_value)
                self.maximum_value.parent = None
                self.units.hide()
                self.shall_hbox.removeWidget(self.units)
                self.units.parent = None
            if getattr(self, 'range_label', None):
                self.range_label.hide()
                self.shall_hbox.removeWidget(self.range_label)
                self.range_label.parent = None
                self.maximum_value.hide()
                self.shall_hbox.removeWidget(self.maximum_value)
                self.maximum_value.parent = None
                self.minimum_value.hide()
                self.shall_hbox.removeWidget(self.minimum_value)
                self.minimum_value.parent = None
                self.units.hide()
                self.shall_hbox.removeWidget(self.units)
                self.units.parent = None
            # remove from bottom hbox

            self.shall_vbox.removeItem(self.shall_hbox)
            self.shall_hbox.parent = None
            layout.removeItem(self.instructions_form)
            self.instructions_form.parent = None
            self.line_top.hide()
            layout.removeWidget(self.line_top)
            self.line_top.parent = None
            layout.removeItem(self.shall_vbox)
            self.shall_vbox.parent= None
            self.line_middle.hide()
            layout.removeWidget(self.line_middle)
            self.line_middle.parent = None
            self.rationale_label.hide()
            self.rationale_layout.removeWidget(self.rationale_label)
            self.rationale_label.parent = None
            self.rationale_field.hide()
            self.rationale_layout.removeWidget(self.rationale_field)
            self.rationale_field.parent = None
            layout.removeItem(self.rationale_layout)
            self.rationale_layout.parent = None
            self.line_bottom.hide()
            layout.removeWidget(self.line_bottom)
            self.line_bottom.parent = None
            self.justification_label.hide()
            self.justification_layout.removeWidget(self.justification_label)
            self.justification_label.parent = None
            self.justification_field.hide()
            self.justification_layout.removeWidget(self.justification_field)
            self.justification_field.parent = None
            layout.removeItem(self.justification_layout)
            self.justification_layout.parent = None
            self.preview_button.hide()
            self.preview_form.removeWidget(self.preview_button)
            self.preview_button.parent = None
            self.save_button.hide()
            self.preview_form.removeWidget(self.save_button)
            self.save_button.parent = None
            layout.removeItem(self.preview_form)
            self.preview_form.parent = None

        self.setTitle('Shall Statement, Rationale, and Justification')
        self.setSubTitle('Inspect the "shall statement" and provide the '
                         'rationale ...')

        # button to pop up instructions
        inst_button = QPushButton('Instructions')
        inst_button.clicked.connect(self.instructions)
        inst_button.setMaximumSize(150,35)
        inst_label = QLabel('View Instructions:')
        self.instructions_form = QFormLayout()
        self.instructions_form.addRow(inst_label, inst_button)

        # 'req_constraint_type' was set on the previous page
        # as max, min, single, or range value(s)
        constraint_type = rqt_wizard_state.get('req_constraint_type')
        # if max or min, set up min-max combo
        double_validator = QtGui.QDoubleValidator()
        max_text = 'shall not exceed'
        min_text = 'shall not be less than'
        if constraint_type == 'maximum':
            rqt_wizard_state['req_predicate'] = max_text
            self.maximum_value = QLineEdit()
            self.maximum_value.setValidator(double_validator)
            self.maximum_value.setMaximumSize(75, 25)
            maximum_value = rqt_wizard_state.get('req_maximum_value', '')
            if maximum_value:
                self.maximum_value.setText(str(maximum_value))
            else:
                self.maximum_value.setPlaceholderText('maximum')
            self.maximum_value.textChanged.connect(self.num_entered)
        elif constraint_type == 'minimum':
            rqt_wizard_state['req_predicate'] = min_text
            self.minimum_value = QLineEdit()
            self.minimum_value.setValidator(double_validator)
            self.minimum_value.setMaximumSize(75, 25)
            minimum_value = rqt_wizard_state.get('req_minimum_value', '')
            if minimum_value:
                self.minimum_value.setText(str(minimum_value))
            else:
                self.minimum_value.setPlaceholderText('minimum')
            self.minimum_value.textChanged.connect(self.num_entered)

        # line editor(s) for number entry
        # TODO: make one numeric entry unless it is range then make two.
        self.maximum_value = None
        self.range_label = None
        self.minimum_value = None
        self.target_value = None
        if constraint_type in ['range', 'maximum', 'minimum']:
            if constraint_type in ['range', 'minimum']:
                self.minimum_value = QLineEdit()
                self.minimum_value.setValidator(double_validator)
                self.minimum_value.setMaximumSize(100, 25)
                minimum_value = rqt_wizard_state.get('req_minimum_value', '')
                if minimum_value:
                    self.minimum_value.setText(str(minimum_value))
                else:
                    self.minimum_value.setPlaceholderText('minimum')
                self.minimum_value.textChanged.connect(self.num_entered)
            if constraint_type == 'range':
                rqt_wizard_state['req_predicate'] = "shall be in the range"
                self.range_label = QLabel('to')
                self.range_label.setMaximumSize(20, 25)
            if constraint_type in ['range', 'maximum']:
                self.maximum_value = QLineEdit()
                self.maximum_value.setValidator(double_validator)
                self.maximum_value.setMaximumSize(100, 25)
                maximum_value = rqt_wizard_state.get('req_maximum_value', '')
                if maximum_value:
                    self.maximum_value.setText(str(maximum_value))
                else:
                    self.maximum_value.setPlaceholderText('maximum')
                self.maximum_value.textChanged.connect(self.num_entered)
        else:
            # constraint_type is "single value"
            rqt_wizard_state['req_predicate'] = "shall equal"
            self.target_value = QLineEdit()
            self.target_value.setValidator(double_validator)
            target_value = rqt_wizard_state.get('req_target_value', '')
            self.target_value.setPlaceholderText('target value')
            if target_value:
                self.target_value.setText(str(target_value))
            self.target_value.setMaximumSize(100, 25)
            self.target_value.textChanged.connect(self.num_entered)
        self.minus_label = None
        self.plus_label = None
        self.lower_limit = None
        self.upper_limit = None
        self.plus_minus_label = None
        self.tol_val_field = None
        tolerance_type = rqt_wizard_state.get('req_tolerance_type')
        if tolerance_type:
            if tolerance_type == 'Asymmetric Tolerance':
                self.minus_label = QLabel('-')
                self.minus_label.setMaximumSize(30, 25)
                self.plus_label = QLabel('+')
                self.plus_label.setMaximumSize(30, 25)
                self.lower_limit = QLineEdit()
                self.lower_limit.setValidator(double_validator)
                self.lower_limit.setMaximumSize(120, 25)
                self.lower_limit.setPlaceholderText('lower tolerance')
                self.lower_limit.setText(
                        str(rqt_wizard_state.get('req_tolerance_lower', '')))
                self.lower_limit.textChanged.connect(self.num_entered)
                self.upper_limit = QLineEdit()
                self.upper_limit.setValidator(double_validator)
                self.upper_limit.setMaximumSize(120, 25)
                self.upper_limit.setPlaceholderText('upper tolerance')
                self.upper_limit.setText(
                        str(rqt_wizard_state.get('req_tolerance_upper', '')))
                self.upper_limit.textChanged.connect(self.num_entered)
            elif tolerance_type == 'Symmetric Tolerance':
                self.plus_minus_label = QLabel('+/-')
                self.plus_minus_label.setMaximumSize(30, 25)
                self.tol_val_field = QLineEdit()
                self.tol_val_field.setValidator(double_validator)
                self.tol_val_field.setMaximumSize(100, 25)
                self.tol_val_field.setPlaceholderText('tolerance')
                self.tol_val_field.setText(
                            str(rqt_wizard_state.get('req_tolerance', '')))
                self.tol_val_field.textChanged.connect(self.num_entered)

        # subject (allocated item / parameter)
        allocated_item = '[unallocated]'
        alloc = self.rqt.allocated_to
        if alloc:
            if hasattr(alloc, 'component'):
                allocated_item = alloc.reference_designator
            elif hasattr(alloc, 'system'):
                allocated_item = alloc.system_role
            elif hasattr(alloc, 'id'):
                allocated_item = alloc.id
        parm_name = '[parameter not selected]'
        pid = rqt_wizard_state.get('req_parameter')
        if pid:
            pd_dict = parm_defz.get(pid)
            if pd_dict:
                parm_name = pd_dict['name']
        rqt_wizard_state['req_subject'] = ' '.join([allocated_item, parm_name])
        alloc_parm = ' '.join([allocated_item, parm_name,
                         rqt_wizard_state.get('req_predicate', '[shall be]')])
        self.subj_pred_label = ValueLabel(alloc_parm)

        # units
        self.units = QComboBox()
        units_list = []
        rel = orb.get(rqt_wizard_state.get('computable_form_oid'))
        if rel:
            parm_rels = rel.correlates_parameters
            if parm_rels:
                pd = parm_rels[0].correlates_parameter
                if pd:
                    units_list = alt_units.get(pd.dimensions, None)
        if units_list:
            for unit in units_list:
                self.units.addItem(unit)
        else:
            self.units.addItem('No units found.')
        current_units = rqt_wizard_state.get('req_units')
        if current_units and current_units in units_list:
            self.units.setCurrentText(current_units)
            rqt_wizard_state['req_units'] = current_units
        elif units_list:
            rqt_wizard_state['req_units'] = self.units.currentText()
        self.units.currentTextChanged.connect(self.on_set_units)
        # labels for the overall groups for organization of the page
        shall_label = QLabel('Shall Statement:')
        self.rationale_label = QLabel('Rationale: ')
        self.justification_label = QLabel('Justification: ')

        # lines for spacers inside the widget.
        self.line_top= QHLine()
        self.line_top.setFrameShadow(QFrame.Sunken)
        self.line_middle = QHLine()
        self.line_middle.setFrameShadow(QFrame.Sunken)
        self.line_bottom = QHLine()
        self.line_bottom.setFrameShadow(QFrame.Sunken)

        # rationale plain text edit
        self.rationale_field = QPlainTextEdit()
        self.rationale_field.setPlainText(
                                    rqt_wizard_state.get('rationale', ''))

        # justification plain text edit
        self.justification_field = QPlainTextEdit()
        self.justification_field.setPlainText(
                                    rqt_wizard_state.get('justification', ''))

        # shall statement
        self.shall_hbox = QHBoxLayout()
        self.shall_vbox = QVBoxLayout()
        self.shall_hbox.addWidget(self.subj_pred_label)
        if constraint_type in ['maximum', 'minimum']:
            if self.minimum_value:
                self.shall_hbox.addWidget(self.minimum_value)
            elif self.maximum_value:
                self.shall_hbox.addWidget(self.maximum_value)
            self.shall_hbox.addWidget(self.units)
        else:
            if self.target_value:
                self.shall_hbox.addWidget(self.target_value)
                if tolerance_type == 'Asymmetric Tolerance':
                    self.shall_hbox.addWidget(self.minus_label)
                    self.shall_hbox.addWidget(self.lower_limit)
                    self.shall_hbox.addWidget(self.plus_label)
                    self.shall_hbox.addWidget(self.upper_limit)
                    self.shall_hbox.addWidget(self.units)
                elif tolerance_type == 'Symmetric Tolerance':
                    self.shall_hbox.addWidget(self.plus_minus_label)
                    self.shall_hbox.addWidget(self.tol_val_field)
                    self.shall_hbox.addWidget(self.units)
            else:
                # constraint type is "range"
                self.shall_hbox.addWidget(self.minimum_value)
                self.shall_hbox.addWidget(self.range_label)
                self.shall_hbox.addWidget(self.maximum_value)
                self.shall_hbox.addWidget(self.units)
        self.shall_vbox.addWidget(shall_label)
        self.shall_vbox.addLayout(self.shall_hbox)
        self.shall_vbox.setContentsMargins(0,40,0,40)

        # rationale layout
        self.rationale_layout = QHBoxLayout()
        self.rationale_layout.addWidget(self.rationale_label)
        self.rationale_layout.addWidget(self.rationale_field)
        self.rationale_layout.setContentsMargins(0,40,0,40)

        # justification layout
        self.justification_layout = QHBoxLayout()
        self.justification_layout.addWidget(self.justification_label)
        self.justification_layout.addWidget(self.justification_field)
        self.justification_layout.setContentsMargins(0,40,0,40)

        self.preview_form = QFormLayout()

        # save button
        self.save_button = QPushButton('Save')
        self.save_button.clicked.connect(self.completeChanged)
        self.save_button.setMaximumSize(150,35)
        self.preview_form.addRow(self.save_button)

        # preview button
        self.preview_button = QPushButton('Preview')
        self.preview_button.clicked.connect(self.preview)
        self.preview_button.setMaximumSize(150,35)
        self.preview_form.addRow(self.preview_button)

        # main layout
        layout.addLayout(self.instructions_form)
        layout.addWidget(self.line_top)
        layout.addLayout(self.shall_vbox)
        layout.addWidget(self.line_middle)
        layout.addLayout(self.rationale_layout)
        layout.addWidget(self.line_bottom)
        layout.addLayout(self.justification_layout)
        layout.addLayout(self.preview_form)

    def num_entered(self):
        if self.target_value:
            tv_txt = self.target_value.text()
            try:
                rqt_wizard_state['req_target_value'] = float(tv_txt)
            except:
                # field was empty or bad value
                pass
        if self.maximum_value:
            max_txt = self.maximum_value.text()
            try:
                rqt_wizard_state['req_maximum_value'] = float(max_txt)
            except:
                # field was empty or bad value
                pass
        if self.minimum_value:
            min_txt = self.minimum_value.text()
            try:
                rqt_wizard_state['req_minimum_value'] = float(min_txt)
            except:
                # field was empty or bad value
                pass
        if self.lower_limit:
            lower_txt = self.lower_limit.text()
            try:
                rqt_wizard_state['req_tolerance_lower'] = float(lower_txt)
            except:
                # field was empty or bad value
                pass
            upper_txt = self.upper_limit.text()
            try:
                rqt_wizard_state['req_tolerance_upper'] = float(upper_txt)
            except:
                # field was empty or bad value
                pass
        if self.tol_val_field:
            tol_txt = self.tol_val_field.text()
            try:
                rqt_wizard_state['req_tolerance'] = float(tol_txt)
            except:
                # field was empty or bad value
                pass

    def on_set_units(self):
        orb.log.info('* reqwizard setting units ...')
        new_units = str(self.units.currentText())
        orb.log.debug('  new units: "{}"'.format(new_units))
        rqt_wizard_state['req_units'] = new_units

    def instructions(self):
        instructions = "In the shall statement (<b>description</b>) area "
        instructions += "input the required fields (which fields are required "
        instructions += "depends on selections from previous page)"
        instructions += "<ul><li><b>Minimum and Maximum</b>: Input the number "
        instructions += "that is the maximum or minimum value.</li>"
        instructions += "<li><b>Single Value with Asymmetric Tolerance</b>: "
        instructions += "Input the initial value and the two associated "
        instructions += " tolerance values (be sure to select the "
        instructions += "appropriate sign (+/-).</li><li><b>Single Value with "
        instructions += "Symmetric Tolerance</b>: Input the intial value with "
        instructions += "the associated tolerance.</li><li><b>Range</b>: input "
        instructions += "the values for the range.</li></ul> The already "
        instructions += "existing fields are required for the shall statement, "
        instructions += "and may be adjusted view text or drop down menu. In "
        instructions += "some places between the pre-existing fields there "
        instructions += "are greyed-out textboxes, and there, if desired, "
        instructions += "additional text can be added for a more descriptive "
        instructions += "shall statement."
        QMessageBox.question(self, 'instructions', instructions,
                             QMessageBox.Ok)

    def preview(self):
        if (rqt_wizard_state.get('description')
            and rqt_wizard_state.get('rationale')):
            shall_rat = "Shall Statement:\n{}".format(
                                        rqt_wizard_state['description'])
            shall_rat +="\n\nRationale:\n{}".format(
                                        rqt_wizard_state['rationale'])
        else:
            shall_rat = "Shall statement and rationale have not been saved."
        QMessageBox.question(self, 'preview', shall_rat, QMessageBox.Ok)

    def isComplete(self):
        """
        Check that target_value, maximum_value (optional), minimum_value
        (optional), rationale, and all text fields are filled.
        """
        # numbers are saved to state as they are typed ... text fields are
        # saved to state here (to avoid impact on user feel)
        description = ''
        items = []
        for i in range(self.shall_hbox.count()):
            items.append(self.shall_hbox.itemAt(i))
        for item in items:
            if item:
                w = item.widget()
                if description:
                    # if already some stuff, add a space before next stuff ...
                    description += ' '
                if hasattr(w, 'currentText'):
                    description += w.currentText()
                elif hasattr(w, 'text'):
                    # this applies to subj_pred_label
                    description += w.text()
                elif w in [self.plus_minus_label, self.minus_label,
                           self.plus_label, self.range_label]:
                    description += w.text()
                elif hasattr(w, 'isReadOnly') and not w.isReadOnly():
                    description += w.text()
        if description == '':
            return False
        description = ' '.join(description.split()) + '.'
        rqt_wizard_state['description'] = description
        # predicate excludes the value + units, so that if description needs to
        # be regenerated, it can be assembled as
        #     req_subject + req_predicate
        #     + str(req_maximum_value or req_minimum_value or req_target_value)
        #     + units
        constraint_type = rqt_wizard_state.get('req_constraint_type')
        units = rqt_wizard_state.get('req_units', '[no units]') or ''
        if constraint_type == 'maximum':
            req_obj = str(rqt_wizard_state.get('req_maximum_value', ''))
            req_obj += ' ' + units
        elif constraint_type == 'minimum':
            req_obj = str(rqt_wizard_state.get('req_minimum_value', ''))
            req_obj += ' ' + units
        elif constraint_type == 'single value':
            req_obj = str(rqt_wizard_state.get('req_target_value', ''))
            # TODO:  add tolerances
            # tol_type = rqt_wizard_state.get('req_tolerance_type')
            req_obj += ' ' + units
        elif constraint_type == 'range':
            # TODO:  deal with "range" better
            req_obj = str(rqt_wizard_state.get('req_minimum_value', ''))
            req_obj += ' to '
            req_obj += str(rqt_wizard_state.get('req_maximum_value', ''))
        else:
            # if not constraint_type, pretend it's "maximum"
            # TODO: something better ...
            req_obj = str(rqt_wizard_state.get('req_maximum_value', ''))
            req_obj += ' ' + units
        rqt_wizard_state['req_object'] = req_obj
        rqt_wizard_state[
                 'justification'] = self.justification_field.toPlainText()
        rqt_wizard_state['rationale'] = self.rationale_field.toPlainText()
        if not rqt_wizard_state.get('rationale'):
            return False
        # TODO: get the project
        return True


class PerformanceMarginCalcPage(QWizardPage):
    """
    For the user to assign a parameter to a performance requirement.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        self.setLayout(layout)

    def initializePage(self):
        if self.title():
            return
        rqt_wizard_state['marg_calc'] = None
        self.setTitle('Set Margin Calculation')
        self.setSubTitle('Use the drop downs below to set'
                         ' the margin calculation...')
        # Combo boxes
        upper_left_cb = QComboBox()
        upper_right_cb = QComboBox()
        bottom_left_cb = QComboBox()
        bottom_right_cb = QComboBox()
        upper_left_cb.addItem('expected')
        upper_right_cb.addItem('expected')
        upper_left_cb.addItem('requirement')
        upper_right_cb.addItem('requirement')
        bottom_left_cb.addItem('expected')
        bottom_right_cb.addItem('expected')
        bottom_left_cb.addItem('requirement')
        bottom_right_cb.addItem('requirement')
        bottom_left_cb.addItem('1')
        bottom_right_cb.addItem('1')
        bottom_left_cb.addItem('other')
        bottom_right_cb.addItem('other')
        # math labels
        subtraction_label = QLabel(' - ')
        mult_label = QLabel(' x ')
        line = QHLine()
        top_layout = QHBoxLayout()
        bottom_layout = QHBoxLayout()
        top_layout.addWidget(upper_left_cb)
        top_layout.addWidget(subtraction_label)
        top_layout.addWidget(upper_right_cb)
        bottom_layout.addWidget(bottom_left_cb)
        bottom_layout.addWidget(mult_label)
        bottom_layout.addWidget(bottom_right_cb)
        self.layout = self.layout()
        self.layout.setSpacing(20)
        self.layout.addLayout(top_layout)
        self.layout.addWidget(line)
        self.layout.addLayout(bottom_layout)

    def isComplete(self):
        return True

