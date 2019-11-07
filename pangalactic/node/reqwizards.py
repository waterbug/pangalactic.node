# -*- coding: utf-8 -*-
"""
Requirements Wizards
"""
from builtins import str
from builtins import range
import os
from PyQt5 import QtGui
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QButtonGroup, QComboBox, QDialogButtonBox,
                             QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                             QFrame, QMenu, QMessageBox, QPlainTextEdit,
                             QPushButton, QRadioButton, QVBoxLayout, QWizard,
                             QWizardPage)

from louie import dispatcher

from pangalactic.core             import config, state
from pangalactic.core.parametrics import parm_defz
from pangalactic.core.uberorb     import orb
from pangalactic.core.utils.datetimes import dtstamp
from pangalactic.core.utils.meta  import get_attr_ext_name
from pangalactic.core.units       import alt_units
from pangalactic.node.libraries   import LibraryListView
from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.utils       import clone, ReqAllocDelegate
from pangalactic.node.widgets     import PlaceHolder, NameLabel, ValueLabel
from pangalactic.node.systemtree  import SystemTreeView

req_wizard_state = {}

all_req_fields=['id', 'name', 'description', 'rationale', 'id_ns', 'version',
                'iteration', 'version_sequence','owner', 'abbreviation',
                'frozen', 'derived_from' ,'public', 'req_level', 'validated']


def gen_req_id(project, version=None, ancestor_reqt=None):
    """
    Generate the `id` attribute for a new requirement. (NOTE:  this function
    assumes that the requirement has already been saved and is therefore
    included in the count of requirements for the project). The format of the
    returned `id` is as follows:

        project_id.seq[.version]

    Args:
        project (Project):  a Project instance

    Keyword Args:
        version (str):  a version string or number
        ancestor_reqt (Requirement):  the previous version of this requirement
    """
    orb.log.info('* gen_req_id:  generating a new requirement "id".')
    # TODO:  if version is not 0, use seq number of ancestor requirement version
    if (ancestor_reqt and
        isinstance(ancestor_reqt, orb.classes['Requirement'])):
        parts = ancestor_reqt.id.split('.')
        if len(parts) == 3:
            if version is not None and version:
                # if a version is specified, use it
                version = str(version)
            else:
                # if a version is not specified, try to increment
                ancestor_version = parts[2]
                try:
                    version = int(ancestor_version) + 1
                except:
                    orb.log.info('  - ancestor version not integer; using 0.')
            seq = parts[1]
        else:
            orb.log.info('  - ancestor reqt. has malformed "id".')
    else:
        if version is not None and version:
            version = str(version)
        idvs = orb.get_idvs('Requirement')
        # NOTE:  must check that idv[0] is not None (i.e. id is not assigned)
        project_idvs = [idv for idv in idvs
                        if idv[0] and (idv[0].split('.'))[0] == project.id]
        if project_idvs:
            seq = max([int(idv[0].split('.')[1]) for idv in project_idvs]) + 1
        else:
            seq = 1
    new_id = build_req_id(project, seq, version)
    orb.log.info('* gen_req_id: generated reqt. id: {}'.format(new_id))
    return new_id

def build_req_id(project, seq, version):
    # TODO:  versioning system TBD
    if version:
        version = str(version)
    else:
        version = '0'
    return '.'.join([project.id, str(seq), version])


class QHLine(QFrame):
    def __init__(self):
        super(QHLine, self).__init__()
        self.setFrameShape(QFrame.HLine)


class QVLine(QFrame):
    def __init__(self):
        super(QVLine, self).__init__()
        self.setFrameShape(QFrame.VLine)


class ReqWizard(QWizard):
    """
    Wizard for project requirements (both functional and performance)
    """
    def __init__(self, req=None, parent=None, performance=False):
        """
        Initialize Requirements Wizard.

        Args:
            req (Requirement): a Requirement object (provided only when wizard
                is being invoked in order to edit an existing requirement.
        """
        super(ReqWizard, self).__init__(parent)
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
        # clear the req_wizard_state
        for x in req_wizard_state:
            req_wizard_state[x] = None
        project_oid = state.get('project')
        proj = orb.get(project_oid)
        self.project = proj
        req_wizard_state['req_parameter'] = ''
        self.new_req = True
        if isinstance(req, orb.classes['Requirement']):
            self.new_req = False
            req_wizard_state['req_oid'] = req.oid
            # NOTE: the following state variables take the same values as their
            # counterparts in the attributes of Requirement -- HOWEVER, the
            # state variables 'req_parameter' and 'computable_form_oid' are
            # special cases and are handled differently ...
            for a in [
                'comment',
                'description',
                'rationale',
                'req_constraint_type',
                'req_epilog',
                'req_level',
                'req_maximum_value',
                'req_minimum_value',
                'req_min_max_phrase',
                'req_predicate',
                'req_shall_phrase',
                'req_subject',
                'req_target_value',
                'req_tolerance',
                'req_tolerance_lower',
                'req_tolerance_type',
                'req_tolerance_upper',
                'req_units',        # units for performance values
                'validated',
                'verification_method'
                ]:
                req_wizard_state[a] = getattr(req, a)
            # 'performance' flag indicates req_type:
            #    - True  -> performance requirement
            #    - False -> functional requirement
            req_wizard_state['computable_form_oid'] = getattr(
                                                req.computable_form, 'oid', '')
            performance = (req.req_type == 'performance')
        if not performance:
            req_wizard_state['performance'] = False
            self.addPage(RequirementIDPage(self))
            self.addPage(ReqAllocPage(self))
            self.addPage(ReqVerificationPage(self))
            self.addPage(ReqSummaryPage(self))
            self.setWindowTitle('Functional Requirement Wizard')
            self.setGeometry(50, 50, 850, 900);
        else:
            req_wizard_state['performance'] = True
            if not self.new_req:
                # if an existing performance requirement, it has a parameter
                # (unless its data is corrupted -- but we sholdn't crash from
                # corrupted data!)
                rel = req.computable_form
                if rel:
                    prs = rel.correlates_parameters
                    if prs:
                        pr = prs[0]
                        pd = pr.correlates_parameter
                        req_wizard_state['req_parameter'] = pd.id
            self.addPage(RequirementIDPage(self))
            self.addPage(ReqAllocPage(self))
            self.addPage(PerformanceDefineParmPage(self))
            self.addPage(PerformReqBuildShallPage(self))
            # TODO: make PerformanceMarginCalcPage useful ...
            # self.addPage(PerformanceMarginCalcPage(self))
            self.addPage(ReqVerificationPage(self))
            self.addPage(ReqSummaryPage(self))
            self.setWindowTitle('Performance Requirement Wizard')
            self.setGeometry(50, 50, 850, 750);
        self.setSizeGripEnabled(True)

    def on_cancel(self):
        if self.new_req:
            # if a new Requirement was being created, delete it and all
            # associated objects ...
            req_oid = req_wizard_state.get('req_oid')
            req = orb.get(req_oid)
            if req:
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
                # delete the Requirement object
                orb.delete([req])
                dispatcher.send(signal='deleted object', oid=req_oid,
                                cname='Requirement')
        self.reject()

###########################
# General Requirement Pages
###########################

# Includes ID page which includes identifier, name, and summary.

class RequirementIDPage(QWizardPage):

    def __init__(self, parent=None):
        super(RequirementIDPage, self).__init__(parent)
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
        performance = req_wizard_state.get('performance')
        proj_oid = state.get('project')
        self.project = orb.get(proj_oid)
        req = orb.get(req_wizard_state.get('req_oid'))
        if req:
            self.req = req
            new = False
        else:
            # NOTE: requirement id must be generated before cloning new reqt.;
            # otherwise, generator will get confused
            req_id = gen_req_id(self.project)
            self.req = clone("Requirement", id=req_id, owner=self.project,
                             public=True)
            orb.save([self.req])
            new = True
        req_wizard_state['req_oid'] = self.req.oid
        # Where the performance and functional differ
        main_view = []
        required = []
        if performance:
            main_view = ['id', 'name']
            required = ['name']
            mask = ['id']
        else:
            main_view = ['id', 'name', 'description', 'rationale', 'comment']
            required = ['name', 'description', 'rationale']
            mask = ['id']
        panels = ['main']
        self.pgxn_obj = PgxnObject(self.req, embedded=True, panels=panels,
                                   main_view=main_view, required=required,
                                   mask=mask, edit_mode=True, new=new,
                                   enable_delete=False)
        self.pgxn_obj.toolbar.hide()
        self.pgxn_obj.save_button.clicked.connect(self.completeChanged)
        self.pgxn_obj.save_button.clicked.connect(self.update_levels)
        self.pgxn_obj_cancel_button = self.pgxn_obj.bbox.button(
                                                QDialogButtonBox.Cancel)
        self.pgxn_obj_cancel_button.clicked.connect(self.update_levels)
        self.pgxn_obj_cancel_button.clicked.connect(self.completeChanged)
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
        self.req.req_level = self.level_cb.currentText()

    def update_levels(self):
        # NOTE: update_levels is triggered when pgxnobject saves, so update
        # req_wizard_state to sync with the saved req attributes ...
        req_wizard_state['description'] = self.req.description
        req_wizard_state['rationale'] = self.req.rationale
        req_wizard_state['comment'] = self.req.comment
        self.level_cb.removeItem(1)
        self.level_cb.removeItem(0)
        if self.req.parent_requirements:
            parent_levels = [pr.parent_requirement.req_level or 0
                             for pr in self.req.parent_requirements]
            try:
                max_level = max(parent_levels)
            except:
                max_level = 0
        else:
            max_level = 0
        self.level_cb.addItem(str(max_level))
        self.level_cb.addItem(str(max_level + 1))
        if hasattr(self.pgxn_obj, 'edit_button'):
            self.pgxn_obj.edit_button.clicked.connect(self.completeChanged)
        self.pgxn_obj_cancel_button.clicked.connect(self.completeChanged)
        self.pgxn_obj.save_button.clicked.connect(self.completeChanged)

    def close_pgxn_obj(self):
        if getattr(self,'pgxn_obj', None):
            self.pgxn_obj.close()
            self.pgxn_obj = None

    def isComplete(self):
        if self.pgxn_obj.edit_mode:
            self.pgxn_obj_cancel_button.clicked.connect(self.update_levels)
            self.pgxn_obj.save_button.clicked.connect(self.update_levels)
            self.level_cb.setDisabled(True)
            return False
        else:
            if hasattr(self.pgxn_obj, 'edit_button'):
                self.pgxn_obj.edit_button.clicked.connect(self.update_levels)
            self.level_cb.setDisabled(False)
            # self.update_levels
            self.req.req_level = self.req.req_level or 0
            req_wizard_state['req_level'] = self.req.req_level
            if not req_wizard_state.get('performance'):
                self.req.req_type = 'functional'
            else:
                self.req.req_type = 'performance'
            orb.save([self.req])
            return True


class ReqVerificationPage(QWizardPage):
    """
    Page for selecting the verification method for the requirement.
    """
    def __init__(self, parent=None):
        super(ReqVerificationPage, self).__init__(parent)
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
        verification_method = req_wizard_state.get('verification_method',
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
        req_wizard_state['verification_method'
                        ] = self.verif_method_buttons.checkedButton().text()


class ReqAllocPage(QWizardPage):
    """
    Page to allocate the requirement to a project, a system role, or a
    function (identified by reference designator) within a system
    architecture.
    """

    def __init__(self, parent=None):
        super(ReqAllocPage, self).__init__(parent)
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

    def initializePage(self):
        self.req = orb.get(req_wizard_state.get('req_oid'))
        if not self.req:
            # TODO: if reqt cant be found, show messsage (page is useless then)
            orb.log.info('* ReqAllocPage: requirement not found')
        if self.title():
            return;
        self.setTitle("Requirement Allocation")
        self.setSubTitle("Specify the system or function "
                         "that will satisfy the requirement "
                         "(<b>DOUBLE-CLICK</b> on a tree node).")
        project_oid = state.get('project')
        proj = orb.get(project_oid)
        self.project = proj
        self.sys_tree = SystemTreeView(self.project, refdes=True,
                                       show_allocs=True, req=self.req)
        self.sys_tree.setItemDelegate(ReqAllocDelegate())
        self.sys_tree.expandToDepth(2)
        self.sys_tree.setExpandsOnDoubleClick(False)
        self.sys_tree.doubleClicked.connect(self.on_select_node)
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
        allocation = 'The '
        if getattr(self.req, 'allocated_to_function', None):
            allocation += self.req.allocated_to_function.reference_designator
        elif getattr(self.req, 'allocated_to_system', None):
            allocation += self.req.allocated_to_system.system_role
        else:
            allocation += self.project.id + ' project'
        req_wizard_state['allocation'] = allocation

    def on_select_node(self, index):
        link = None
        allocated_item = ''
        if len(self.sys_tree.selectedIndexes()) == 1:
            i = self.sys_tree.selectedIndexes()[0]
            mapped_i = self.sys_tree.proxy_model.mapToSource(i)
            # NOTE: might want to use obj -- getting it indirectly below for
            # Acu as "assembly"
            # obj = self.sys_tree.source_model.get_node(mapped_i).obj
            link = self.sys_tree.source_model.get_node(mapped_i).link
        if not link or not self.req:
            return
        if hasattr(link, 'system'):
            if self.req in link.system_requirements:
                # if this is an existing allocation, remove it
                self.req.allocated_to_system = None
            else:
                self.req.allocated_to_system = link
                # if allocating to system, remove any allocation to function
                if self.req.allocated_to_function:
                    self.req.allocated_to_function = None
            allocated_item = link.system_role
        elif hasattr(link, 'component'):
            if self.req in link.allocated_requirements:
                # if this is an existing allocation, remove it
                self.req.allocated_to_function = None
            else:
                self.req.allocated_to_function = link
                # if allocating to function, remove any allocation to system
                if self.req.allocated_to_system:
                    self.req.allocated_to_system = None
            allocated_item = link.reference_designator
        self.sys_tree.clearSelection()
        # TODO: get the selected name/product so it can be used in the shall
        # statement.
        allocation = 'The '
        if allocated_item:
            allocation += allocated_item
        else:
            allocation += self.project.id + ' project'
        req_wizard_state['allocation'] = allocation
        self.req.mod_datetime = dtstamp()
        self.req.modifier = orb.get(state.get('local_user_oid'))
        orb.save([self.req])
        dispatcher.send(signal='modified object', obj=self.req)
        self.update_summary()

    def update_summary(self):
        """
        Update the summary of current allocations.
        """
        msg = '<h3>Requirement Allocation:</h3><ul><li><b>'
        if self.req.allocated_to_system:
            msg += '<font color="green">'
            msg += self.req.allocated_to_system.system_role
            msg += '</font>'
        elif self.req.allocated_to_function:
            msg += '<font color="green">'
            msg += self.req.allocated_to_function.reference_designator
            msg += '</font>'
        else:
            msg += '[None]'
        msg += '</b></li></ul>'
        self.summary.setText(msg)
        self.sys_tree.expandToDepth(1)


class ReqSummaryPage(QWizardPage):
    """
    Page to view a summary before saving the Requirement.
    """
    def __init__(self, parent=None):
        super(ReqSummaryPage, self).__init__(parent)
        layout = QVBoxLayout()
        form = QFormLayout()
        self.labels = {}
        self.fields = {}
        for a in ['id', 'name', 'description', 'rationale', 'allocation',
                  'verification_method']:
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
        self.req = orb.get(req_wizard_state.get('req_oid'))
        allocation = req_wizard_state.get('allocation', 'No Allocation')
        self.fields['allocation'].setText(allocation)
        for a in ['id', 'name']:
             self.fields[a].setText(getattr(self.req, a, '[Not Specified]'))
        for a in ['description', 'rationale', 'verification_method']:
             self.fields[a].setText(req_wizard_state.get(a, '[Not Specified]'))
        self.wizard().button(QWizard.FinishButton).clicked.connect(self.finish)

    def finish(self):
        # assign description, rationale, etc. ...
        self.req.description = req_wizard_state['description']
        self.req.rationale = req_wizard_state['rationale']
        self.req.req_target_value = req_wizard_state.get('req_target_value')
        self.req.req_maximum_value = req_wizard_state.get('req_maximum_value')
        self.req.req_minimum_value = req_wizard_state.get('req_minimum_value')
        if self.req.req_constraint_type == 'single value':
            if not self.req.req_target_value:
                return False
            if (self.req.req_tolerance_type == 'Symmetric Tolerance'
                and self.req.req_tolerance is None):
                return False
            elif (self.req.req_tolerance_lower is None
                  or self.req.req_tolerance_upper is None):
                # Asymmetric Tolerance requires upper and lower tols
                return False
        elif (self.req.req_constraint_type == 'maximum'
              and self.req.req_maximum_value is None):
            return False
        elif (self.req.req_constraint_type == 'minimum'
              and self.req.req_minimum_value is None):
            return False
        self.req.computable_form = orb.get(
                                       req_wizard_state.get('computable_form_oid'))
        self.req.req_constraint_type = req_wizard_state.get('req_constraint_type')
        self.req.req_tolerance_type = req_wizard_state.get('req_tolerance_type')
        self.req.verification_method = req_wizard_state.get('verification_method')
        self.req.req_target_value = req_wizard_state.get('req_target_value')
        self.req.req_maximum_value = req_wizard_state.get('req_maximum_value')
        self.req.req_minimum_value = req_wizard_state.get('req_minimum_value')
        self.req.req_tolerance = req_wizard_state.get('req_tolerance')
        self.req.req_tolerance_lower = req_wizard_state.get('req_tolerance_lower')
        self.req.req_tolerance_upper = req_wizard_state.get('req_tolerance_upper')
        self.req.req_min_max_phrase = req_wizard_state.get('req_min_max_phrase')
        self.req.req_shall_phrase = req_wizard_state.get('req_shall_phrase')
        self.req.req_subject = req_wizard_state.get('req_subject')
        self.req.req_predicate = req_wizard_state.get('req_predicate')
        self.req.req_epilog = req_wizard_state.get('req_epilog')
        self.req.mod_datetime = dtstamp()
        self.req.modifier = orb.get(state.get('local_user_oid'))
        orb.save([self.req])
        dispatcher.send(signal='modified object', obj=self.req)


###############################
# Performance Requirement Pages
###############################

# Includes PerformanceDefineParm, desciption add/preview page, margin
# calculation.

class PerformanceDefineParmPage(QWizardPage):
    """
    Page to add some definitions to the value part so it can be used for
    creating the "shall statement" (Requirement.description) on the next page.
    """

    def __init__(self, parent=None):
        super(PerformanceDefineParmPage, self).__init__(parent)
        layout = QHBoxLayout()
        self.setLayout(layout)

    def initializePage(self):
        if self.title():
            return
        self.req = orb.get(req_wizard_state.get('req_oid'))
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
        self.parm_list.doubleClicked.connect(self.on_select_parm)
        self.parm_layout.addWidget(self.parm_list)

        # vertical line that will be used as a spacer between parameter
        # selection and the selection of the type of constraint.
        line = QVLine()
        line.setFrameShadow(QFrame.Sunken)

        # radio buttons for the  type specification including the label and the
        # form for the single value button to specify if it will use asymmetric
        # or symmetric tolerance.
        # TODO: handle single value, store in req_wizard_state
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
        constraint_type = req_wizard_state.get('req_constraint_type')
        if constraint_type:
            if constraint_type == 'minimum':
                self.min_button.setChecked(True)
            elif constraint_type == 'maximum':
                self.max_button.setChecked(True)
            elif constraint_type == 'single value':
                self.single_button.setChecked(True)
                tolerance_type = req_wizard_state.get('req_tolerance_type')
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
        rel = orb.get(req_wizard_state.get('computable_form_oid'))
        pd = None
        if rel:
            parm_rels = rel.correlates_parameters
            if parm_rels:
                pd = parm_rels[0].correlates_parameter
        if pd and pd in self.parm_list.model().objs:
            req_wizard_state['req_parameter'] = pd.id
            row = self.parm_list.model().objs.index(pd)
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
            pd = self.parm_list.model().objs[i]
            orb.log.info('* on_select_parm:  {}'.format(pd.id))
            # a pd has been selected; create a ParameterRelation instance that
            # points to a Relation ('referenced_relation') and for which the
            # 'correlates_parameter' is the pd.  Set the Relation's oid as the
            # req_wizard_state['computable_form_oid'] -- the Relation will be the
            # Requirement's 'computable_form' attribute value.
            # First, check for any existing Relation and ParameterRelation:
            cf_oid = req_wizard_state.get('computable_form_oid')
            if cf_oid:
                # if any are found, destroy them ...
                cf = orb.get(cf_oid)
                if cf:
                    if cf.correlates_parameters:
                        for pr in cf.correlates_parameters:
                            orb.delete([pr])
                    orb.delete([cf])
            relid = self.req.id + '_computable_form'
            relname = self.req.name + ' Computable Form'
            rel = clone("Relation", id=relid, name=relname,
                        owner=self.project, public=True)
            # set Relation as requirement's 'computable_form'
            self.req.computable_form = rel
            prid = self.req.id + '_parm_rel'
            prname = self.req.name + ' Parameter Relation'
            pr = clone("ParameterRelation", id=prid, name=prname,
                       correlates_parameter=pd, referenced_relation=rel,
                       owner=self.project, public=True)
            # req_wizard_state['pr_oid'] = pr.oid
            req_wizard_state['computable_form_oid'] = rel.oid
            req_wizard_state['req_parameter'] = pd.id
            orb.save([self.req])  # also commits the rel and pr objects to db
            # display the selected ParameterDefinition...
            main_view = ['id', 'name', 'description']
            panels = ['main']
            self.parm_pgxnobj = PgxnObject(pd, embedded=True,
                                   panels=panels, main_view=main_view,
                                   edit_mode=False, enable_delete=False)
            self.parm_pgxnobj.toolbar.hide()
            self.parm_layout.addWidget(self.parm_pgxnobj)

    def tolerance_changed(self):
        tol_type = self.single_cb.currentText()
        req_wizard_state['req_tolerance_type'] = tol_type

    def set_constraint_type(self):
        """
        Set the constraint type. This also enables and disables the combobox
        for the symmetric and asymmetric options with the single value button.
        """
        b = self.constraint_buttons.checkedButton()
        const_type = b.text()
        if const_type:
            req_wizard_state['req_constraint_type'] = const_type
        else:
            req_wizard_state['req_constraint_type'] = None
        if b == self.single_button:
            self.single_cb.setDisabled(False)
            rtt = self.single_cb.currentText()
            req_wizard_state['req_tolerance_type'] = rtt
        else:
            self.single_cb.setDisabled(True)

    def isComplete(self):
        """
        Check if both dimension and type have been specified
        """
        if (not req_wizard_state.get('computable_form_oid')
            or not req_wizard_state.get('req_constraint_type')):
            return False
        return True


class PerformReqBuildShallPage(QWizardPage):
    """
    Build the "shall statement" (Requirement.description) and fill in the
    rationale.
    """

    def __init__(self, parent=None):
        super(PerformReqBuildShallPage, self).__init__(parent)
        layout = QVBoxLayout()
        self.setLayout(layout)

    def initializePage(self):
        self.req = orb.get(req_wizard_state.get('req_oid'))
        layout = self.layout()
        if self.title():
            # remove from first hbox
            self.allocation_label.hide()
            self.shall_hbox_top.removeWidget(self.allocation_label)
            self.allocation_label.parent = None
            self.subject_field.hide()
            self.shall_hbox_top.removeWidget(self.subject_field)
            self.subject_field.parent = None
            self.shall_cb.hide()
            self.shall_hbox_top.removeWidget(self.shall_cb)
            self.shall_cb.parent = None
            # remove from middle hbox
            self.predicate_field.hide()
            self.shall_hbox_middle.removeWidget(self.predicate_field)
            self.predicate_field.parent = None
            if getattr(self, 'min_max_cb', None):
                self.min_max_cb.hide()
                self.shall_hbox_middle.removeWidget(self.min_max_cb)
                self.min_max_cb.parent = None
            if getattr(self, 'target_value', None):
                self.target_value.hide()
                self.shall_hbox_middle.removeWidget(self.target_value)
                self.target_value.parent = None
                if getattr(self, 'lower_limit', None):
                    self.minus_label.hide()
                    self.shall_hbox_middle.removeWidget(self.minus_label)
                    self.minus_label.parent = None
                    self.lower_limit.hide()
                    self.shall_hbox_middle.removeWidget(self.lower_limit)
                    self.lower_limit.parent = None
                    self.plus_label.hide()
                    self.shall_hbox_middle.removeWidget(self.plus_label)
                    self.plus_label.parent = None
                    self.upper_limit.hide()
                    self.shall_hbox_middle.removeWidget(self.upper_limit)
                    self.upper_limit.parent = None
                    self.units.hide()
                    self.shall_hbox_middle.removeWidget(self.units)
                    self.units.parent = None
                if getattr(self, 'plus_minus_label', None):
                    self.plus_minus_label.hide()
                    self.shall_hbox_middle.removeWidget(self.plus_minus_label)
                    self.plus_minus_label.parent = None
                    self.tol_val_field.hide()
                    self.shall_hbox_middle.removeWidget(self.tol_val_field)
                    self.tol_val_field.parent = None
                    self.units.hide()
                    self.shall_hbox_middle.removeWidget(self.units)
                    self.units.parent = None
            if getattr(self, 'minimum_value', None):
                self.minimum_value.hide()
                self.shall_hbox_middle.removeWidget(self.minimum_value)
                self.minimum_value.parent = None
                self.units.hide()
                self.shall_hbox_middle.removeWidget(self.units)
                self.units.parent = None
            if getattr(self, 'maximum_value', None):
                self.maximum_value.hide()
                self.shall_hbox_middle.removeWidget(self.maximum_value)
                self.maximum_value.parent = None
                self.units.hide()
                self.shall_hbox_middle.removeWidget(self.units)
                self.units.parent = None
            if self.range_label:
                self.range_label.hide()
                self.shall_hbox_middle.removeWidget(self.range_label)
                self.range_label.parent = None
                self.maximum_value.hide()
                self.shall_hbox_middle.removeWidget(self.maximum_value)
                self.maximum_value.parent = None
                self.minimum_value.hide()
                self.shall_hbox_middle.removeWidget(self.minimum_value)
                self.minimum_value.parent = None
                self.units.hide()
                self.shall_hbox_middle.removeWidget(self.units)
                self.units.parent = None
            # remove from bottom hbox
            self.epilog_field.hide()
            self.shall_hbox_bottom.removeWidget(self.epilog_field)
            self.epilog_field.parent = None

            self.shall_vbox.removeItem(self.shall_hbox_top)
            self.shall_hbox_top.parent = None
            self.shall_vbox.removeItem(self.shall_hbox_middle)
            self.shall_hbox_middle.parent = None
            self.shall_vbox.removeItem(self.shall_hbox_bottom)
            self.shall_hbox_bottom.parent = None
            layout.removeItem(self.inst_form)
            self.inst_form.parent = None
            self.line_top.hide()
            layout.removeWidget(self.line_top)
            self.line_top.parent = None
            layout.removeItem(self.shall_vbox)
            self.shall_vbox.parent= None
            self.line_bottom.hide()
            layout.removeWidget(self.line_bottom)
            self.line_bottom.parent = None
            self.rationale_label.hide()
            self.rationale_layout.removeWidget(self.rationale_label)
            self.rationale_label.parent = None
            self.rationale_field.hide()
            self.rationale_layout.removeWidget(self.rationale_field)
            self.rationale_field.parent = None
            layout.removeItem(self.rationale_layout)
            self.rationale_layout.parent = None
            self.preview_button.hide()
            self.preview_form.removeWidget(self.preview_button)
            self.preview_button.parent = None
            self.save_button.hide()
            self.preview_form.removeWidget(self.save_button)
            self.save_button.parent = None
            layout.removeItem(self.preview_form)
            self.preview_form.parent = None

        self.setTitle('Shall Construction and Rationale')
        self.setSubTitle('Construct the "shall statement" using the '
                         'instructions below, and then provide the '
                         'requirements rationale ...')

        # different shall cb options
        shall_options = ['shall', 'shall be', 'shall have']
        max_options = ['less than', 'not exceed', 'at most', 'maximum of']
        min_options = ['greater than', 'more than', 'at least', 'minimum of']

        # button with label to access instructions
        inst_button = QPushButton('Instructions')
        inst_button.clicked.connect(self.instructions)
        inst_button.setMaximumSize(150,35)
        inst_label = QLabel('View Instructions:')
        self.inst_form = QFormLayout()
        self.inst_form.addRow(inst_label, inst_button)

        # shall options combobox
        self.shall_cb = QComboBox()
        for opt in shall_options:
            self.shall_cb.addItem(opt)
        self.shall_cb.setMaximumSize(120, 25)
        shall_phrase = req_wizard_state.get('req_shall_phrase')
        if shall_phrase in shall_options:
            self.shall_cb.setCurrentIndex(shall_options.index(shall_phrase))
        self.shall_cb.currentIndexChanged.connect(self.set_shall_phrase)

        min_max_cb_options = None
        self.min_max_cb = None
        # gets the type from the previous page, says if the type is max, min,
        # single, or range value(s)
        constraint_type = req_wizard_state.get('req_constraint_type')
        # if constraint_type is 'minimum' or 'maximum', set up min-max combo
        double_validator = QtGui.QDoubleValidator()
        if constraint_type in ['maximum', 'minimum']:
            if constraint_type == 'maximum':
                min_max_cb_options = max_options
                self.maximum_value = QLineEdit()
                self.maximum_value.setValidator(double_validator)
                self.maximum_value.setMaximumSize(75, 25)
                maximum_value = req_wizard_state.get('req_maximum_value', '')
                if maximum_value:
                    self.maximum_value.setText(str(maximum_value))
                else:
                    self.maximum_value.setPlaceholderText('maximum')
                self.maximum_value.textChanged.connect(self.num_entered)
            elif constraint_type == 'minimum':
                min_max_cb_options = min_options
                self.minimum_value = QLineEdit()
                self.minimum_value.setValidator(double_validator)
                self.minimum_value.setMaximumSize(75, 25)
                minimum_value = req_wizard_state.get('req_minimum_value', '')
                if minimum_value:
                    self.minimum_value.setText(str(minimum_value))
                else:
                    self.minimum_value.setPlaceholderText('minimum')
                self.minimum_value.textChanged.connect(self.num_entered)
            self.min_max_cb = QComboBox()
            for opt in min_max_cb_options:
                self.min_max_cb.addItem(opt)
            min_max_phrase = req_wizard_state.get('req_min_max_phrase')
            if min_max_phrase in min_max_cb_options:
                self.min_max_cb.setCurrentIndex(
                                    min_max_cb_options.index(min_max_phrase))
            self.min_max_cb.currentIndexChanged.connect(
                                    self.set_min_max_phrase)
            self.min_max_cb.setMaximumSize(150,25)

        allocated_item = '[unallocated]'
        acu = self.req.allocated_to_function
        psu = self.req.allocated_to_system
        if acu:
            allocated_item = acu.reference_designator
        elif psu:
            allocated_item = psu.system_role
        parm_name = '[parameter not selected]'
        pid = req_wizard_state.get('req_parameter')
        if pid:
            pd_dict = parm_defz.get(pid)
            if pd_dict:
                parm_name = pd_dict['name']
        alloc_parm = ' '.join([allocated_item, parm_name])
        # premade labels text (non-editable labels)
        # self.allocation_label = QComboBox()
        # self.allocation_label.addItem(allocated_item)
        # self.allocation_label.addItem("The " + allocated_item)
        # self.allocation_label.setMaximumSize(175,25)
        self.allocation_label = ValueLabel(alloc_parm)

        # line edit(s) for number entry
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
                minimum_value = req_wizard_state.get('req_minimum_value', '')
                if minimum_value:
                    self.minimum_value.setText(str(minimum_value))
                else:
                    self.minimum_value.setPlaceholderText('minimum')
                self.minimum_value.textChanged.connect(self.num_entered)
            if constraint_type == 'range':
                self.range_label = QLabel('to')
                self.range_label.setMaximumSize(20, 25)
            if constraint_type in ['range', 'maximum']:
                self.maximum_value = QLineEdit()
                self.maximum_value.setValidator(double_validator)
                self.maximum_value.setMaximumSize(100, 25)
                maximum_value = req_wizard_state.get('req_maximum_value', '')
                if maximum_value:
                    self.maximum_value.setText(str(maximum_value))
                else:
                    self.maximum_value.setPlaceholderText('maximum')
                self.maximum_value.textChanged.connect(self.num_entered)
        else:
            self.target_value = QLineEdit()
            self.target_value.setValidator(double_validator)
            target_value = req_wizard_state.get('req_target_value', '')
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
        tolerance_type = req_wizard_state.get('req_tolerance_type')
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
                        str(req_wizard_state.get('req_tolerance_lower', '')))
                self.lower_limit.textChanged.connect(self.num_entered)
                self.upper_limit = QLineEdit()
                self.upper_limit.setValidator(double_validator)
                self.upper_limit.setMaximumSize(120, 25)
                self.upper_limit.setPlaceholderText('upper tolerance')
                self.upper_limit.setText(
                        str(req_wizard_state.get('req_tolerance_upper', '')))
                self.upper_limit.textChanged.connect(self.num_entered)
            elif tolerance_type == 'Symmetric Tolerance':
                self.plus_minus_label = QLabel('+/-')
                self.plus_minus_label.setMaximumSize(30, 25)
                self.tol_val_field = QLineEdit()
                self.tol_val_field.setValidator(double_validator)
                self.tol_val_field.setMaximumSize(100, 25)
                self.tol_val_field.setPlaceholderText('tolerance')
                self.tol_val_field.setText(
                            str(req_wizard_state.get('req_tolerance', '')))
                self.tol_val_field.textChanged.connect(self.num_entered)

        # units combo box.
        self.units = QComboBox()
        units_list = []
        rel = orb.get(req_wizard_state.get('computable_form_oid'))
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
        self.units.currentTextChanged.connect(self.on_set_units)
        # labels for the overall groups for organization of the page
        shall_label = QLabel('Shall Statement:')
        add_comp_label = QLabel('Additional Shall Statement'
                                            ' Components: ')
        add_comp_label.setMaximumSize(300,25)
        self.rationale_label = QLabel('Rationale: ')

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
                                    req_wizard_state.get('rationale', ''))

        # optional text components of the shall statement (description)
        self.subject_field = QLineEdit()
        subject = req_wizard_state.get('req_subject')
        if subject:
            self.subject_field.setReadOnly(False)
            self.subject_field.setText(subject)
        else:
            self.subject_field.setReadOnly(True)
        self.predicate_field = QLineEdit()
        predicate = req_wizard_state.get('req_predicate')
        if predicate:
            self.predicate_field.setReadOnly(False)
            self.predicate_field.setText(predicate)
        else:
            self.predicate_field.setReadOnly(True)
        self.epilog_field = QLineEdit()
        epilog = req_wizard_state.get('req_epilog')
        if epilog:
            self.epilog_field.setReadOnly(False)
            self.epilog_field.setText(epilog)
        else:
            self.epilog_field.setReadOnly(True)
        text_boxes = [self.subject_field, self.predicate_field,
                      self.epilog_field]

        # fill sub layouts
        self.shall_hbox_top = QHBoxLayout()
        self.shall_hbox_middle = QHBoxLayout()
        self.shall_hbox_bottom = QHBoxLayout()

        self.shall_vbox = QVBoxLayout()

        # fill grid
        self.shall_hbox_top.addWidget(self.allocation_label)
        self.shall_hbox_top.addWidget(self.subject_field)
        self.shall_hbox_top.addWidget(self.shall_cb)
        self.shall_hbox_middle.addWidget(self.predicate_field)
        # if self.min_max_cb tests True, then it is a maximum or a minumum;
        # otherwise it is a single value or a range
        if self.min_max_cb:
            self.shall_hbox_middle.addWidget(self.min_max_cb)
            if self.minimum_value:
                self.shall_hbox_middle.addWidget(self.minimum_value)
            elif self.maximum_value:
                self.shall_hbox_middle.addWidget(self.maximum_value)
            self.shall_hbox_middle.addWidget(self.units)
        else:
            if self.target_value:
                self.shall_hbox_middle.addWidget(self.target_value)
                if tolerance_type == 'Asymmetric Tolerance':
                    self.shall_hbox_middle.addWidget(self.minus_label)
                    self.shall_hbox_middle.addWidget(self.lower_limit)
                    self.shall_hbox_middle.addWidget(self.plus_label)
                    self.shall_hbox_middle.addWidget(self.upper_limit)
                    self.shall_hbox_middle.addWidget(self.units)
                elif tolerance_type == 'Symmetric Tolerance':
                    self.shall_hbox_middle.addWidget(self.plus_minus_label)
                    self.shall_hbox_middle.addWidget(self.tol_val_field)
                    self.shall_hbox_middle.addWidget(self.units)
            else:
                # constraint type is "range"
                self.shall_hbox_middle.addWidget(self.minimum_value)
                self.shall_hbox_middle.addWidget(self.range_label)
                self.shall_hbox_middle.addWidget(self.maximum_value)
                self.shall_hbox_middle.addWidget(self.units)

        self.shall_hbox_bottom.addWidget(self.epilog_field)

        for box in text_boxes:
            box.setStyleSheet("QLineEdit {background-color: #EEEEEE}")
            box.setContextMenuPolicy(Qt.CustomContextMenu)
            box.customContextMenuRequested.connect(self.contextMenu)
            box.setPlaceholderText("right click to add text")
            # box.textChanged.connect(self.completeChanged)

        # fill vbox
        self.shall_vbox.addWidget(shall_label)
        self.shall_vbox.addLayout(self.shall_hbox_top)
        self.shall_vbox.addLayout(self.shall_hbox_middle)
        self.shall_vbox.addLayout(self.shall_hbox_bottom)
        self.shall_vbox.setContentsMargins(0,40,0,40)

        # rationale layout
        self.rationale_layout = QHBoxLayout()
        self.rationale_layout.addWidget(self.rationale_label)
        self.rationale_layout.addWidget(self.rationale_field)
        self.rationale_layout.setContentsMargins(0,40,0,40)

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

        # fill the page, main layout
        layout.addLayout(self.inst_form)
        layout.addWidget(self.line_top)
        layout.addLayout(self.shall_vbox)
        layout.addWidget(self.line_bottom)
        layout.addLayout(self.rationale_layout)
        layout.addLayout(self.preview_form)

    def set_shall_phrase(self):
        req_wizard_state['req_shall_phrase'] = self.shall_cb.currentText()

    def set_min_max_phrase(self):
        req_wizard_state['req_min_max_phrase'] = self.min_max_cb.currentText()

    def num_entered(self):
        if self.target_value:
            tv_txt = self.target_value.text()
            try:
                req_wizard_state['req_target_value'] = float(tv_txt)
            except:
                # field was empty or bad value
                pass
        if self.maximum_value:
            max_txt = self.maximum_value.text()
            try:
                req_wizard_state['req_maximum_value'] = float(max_txt)
            except:
                # field was empty or bad value
                pass
        if self.minimum_value:
            min_txt = self.minimum_value.text()
            try:
                req_wizard_state['req_minimum_value'] = float(min_txt)
            except:
                # field was empty or bad value
                pass
        if self.lower_limit:
            lower_txt = self.lower_limit.text()
            try:
                req_wizard_state['req_tolerance_lower'] = float(lower_txt)
            except:
                # field was empty or bad value
                pass
            upper_txt = self.upper_limit.text()
            try:
                req_wizard_state['req_tolerance_upper'] = float(upper_txt)
            except:
                # field was empty or bad value
                pass
        if self.tol_val_field:
            tol_txt = self.tol_val_field.text()
            try:
                req_wizard_state['req_tolerance'] = float(tol_txt)
            except:
                # field was empty or bad value
                pass

    def on_set_units(self):
        orb.log.info('* [reqwizard] setting units ...')
        units_widget = self.sender()
        new_units = str(units_widget.currentText())
        orb.log.debug('            new units: "{}"'.format(new_units))
        req_wizard_state['req_units'] = new_units
        # parm_id = units_widget.field_name
        # parm_widget = self.p_widgets.get(parm_id)
        # if self.edit_mode and hasattr(parm_widget, 'get_value'):
            # # in edit mode, get value (str) from editable field and convert it
            # str_val = parm_widget.get_value()
            # pval = get_pval_from_str(orb, self.obj.oid, parm_id, str_val)
            # applicable_units = self.previous_units[parm_id]
            # quant = pval * ureg.parse_expression(applicable_units)
            # new_quant = quant.to(new_units)
            # new_str_val = str(new_quant.magnitude)
        # else:
            # # view mode or read-only parm -> get cached parameter value and
            # # convert it to the requested units for display
            # new_str_val = get_pval_as_str(orb, self.obj.oid, parm_id,
                                          # units=new_units)
        # if hasattr(parm_widget, 'set_value'):
            # parm_widget.set_value(new_str_val)
        # elif hasattr(parm_widget, 'setText'):
            # parm_widget.setText(new_str_val)
        # self.previous_units[parm_id] = new_units

    def contextMenu(self, event):
        self.selected_widget = self.sender()
        if (hasattr(self.selected_widget, 'isReadOnly')
            and self.selected_widget.isReadOnly()):
            menu = QMenu(self)
            menu.addAction("insert text", self.enableTextInsert)
            menu.exec_(QtGui.QCursor.pos())
        else:
            menu = QMenu(self)
            menu.addAction("do not insert text", self.disableTextInsert)
            menu.exec_(QtGui.QCursor.pos())

    def enableTextInsert(self):
        self.selected_widget.setReadOnly(False)
        self.selected_widget.setStyleSheet(
                                "QLineEdit {background-color: White}")
        self.selected_widget.setPlaceholderText("")

    def disableTextInsert(self):
        self.selected_widget.setReadOnly(True)
        self.selected_widget.setStyleSheet(
                                "QLineEdit {background-color: #EEEEEE}")
        # self.selected_widget.textChanged.connect(self.completeChanged)
        self.selected_widget.setText('')

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
        shall_prev = self.allocation_label.text()
        items = []
        for i in range(self.shall_hbox_top.count()):
            items.append(self.shall_hbox_top.itemAt(i))
        for i in range(self.shall_hbox_middle.count()):
            items.append(self.shall_hbox_middle.itemAt(i))
        for i in range(self.shall_hbox_bottom.count()):
            items.append(self.shall_hbox_bottom.itemAt(i))
        for item in items:
            if item:
                w = item.widget()
                if hasattr(w, 'currentText'):
                    shall_prev += w.currentText()
                elif w == self.plus_minus_label or w == self.range_label:
                    shall_prev += w.text()
                elif hasattr(w, 'isReadOnly') and not w.isReadOnly():
                    shall_prev += w.text()
                if (w != self.epilog_field and w != self.units and
                        w != self.minus_label and w != self.plus_label
                        and w != self.plus_minus_label):
                    shall_prev += ' '
        shall_prev += '.'
        if (req_wizard_state.get('description')
            and req_wizard_state.get('rationale')):
            shall_rat = "Shall Statement:\n{}".format(
                                        req_wizard_state['description'])
            shall_rat +="\n\nRationale:\n{}".format(
                                        req_wizard_state['rationale'])
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
        req_wizard_state['req_subject'] = self.subject_field.text()
        req_wizard_state['req_predicate'] = self.predicate_field.text()
        req_wizard_state['req_epilog'] = self.epilog_field.text()
        description = ''
        items = []
        for i in range(self.shall_hbox_top.count()):
            items.append(self.shall_hbox_top.itemAt(i))
        for i in range(self.shall_hbox_middle.count()):
            items.append(self.shall_hbox_middle.itemAt(i))
        for i in range(self.shall_hbox_bottom.count()):
            items.append(self.shall_hbox_bottom.itemAt(i))
        for item in items:
            if item:
                w = item.widget()
                if description:
                    # if already some stuff, add a space before next stuff ...
                    description += ' '
                if hasattr(w, 'currentText'):
                    description += w.currentText()
                elif hasattr(w, 'text'):
                    # this applies to allocation_label
                    description += w.text()
                elif w in [self.plus_minus_label, self.minus_label,
                           self.plus_label, self.range_label]:
                    description += w.text()
                elif hasattr(w, 'isReadOnly') and not w.isReadOnly():
                    description += w.text()
        if description == '':
            return False
        description = ' '.join(description.split()) + '.'
        req_wizard_state['description'] = description
        req_wizard_state['rationale'] = self.rationale_field.toPlainText()
        if not req_wizard_state.get('rationale'):
            return False
        # TODO: get the project
        return True


class PerformanceMarginCalcPage(QWizardPage):
    """
    For the user to assign a parameter to a performance requirement.
    """

    def __init__(self, parent=None):
        super(PerformanceMarginCalcPage, self).__init__(parent)
        layout = QVBoxLayout()
        self.setLayout(layout)

    def initializePage(self):
        if self.title():
            return
        req_wizard_state['marg_calc'] = None
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

