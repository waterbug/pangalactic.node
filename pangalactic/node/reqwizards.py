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

# from louie import dispatcher

from pangalactic.core             import config, state
from pangalactic.core.uberorb     import orb
from pangalactic.core.units       import in_si, alt_units
from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.utils       import clone
from pangalactic.node.widgets     import PlaceHolder, ValueLabel
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
        included_buttons = [QWizard.Stretch,
                            QWizard.BackButton,
                            QWizard.NextButton,
                            QWizard.FinishButton,
                            QWizard.CancelButton]
        self.setButtonLayout(included_buttons)
        self.setOptions(QWizard.NoBackButtonOnStartPage)
        # clear the req_wizard_state
        for x in req_wizard_state:
            req_wizard_state[x] = None
        project_oid = state.get('project')
        proj = orb.get(project_oid)
        self.project = proj
        if isinstance(req, orb.classes['Requirement']):
            req_wizard_state['req_oid'] = req.oid
            for a in ['description',
                      'min_max_text',
                      'rationale',
                      'shall_text',
                      'req_constraint_type',
                      'req_dimensions',
                      'req_level',
                      'req_maximum_value',
                      'req_minimum_value',
                      'req_target_value',
                      'req_tolerance',
                      'req_tolerance_lower',
                      'req_tolerance_type',
                      'req_tolerance_upper',
                      'validated',
                      'verification_method',
                      ]:
                req_wizard_state[a] = getattr(req, a)
            # 'performance' flag indicates requirement_type:
            #    - True  -> performance requirement
            #    - False -> functional requirement
            performance = (req.requirement_type == 'performance')
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
            self.addPage(RequirementIDPage(self))
            self.addPage(ReqAllocPage(self))
            self.addPage(PerformanceDefineParmPage(self))
            self.addPage(PerformReqBuildShallPage(self))
            self.addPage(PerformanceMarginCalcPage(self))
            self.addPage(ReqVerificationPage(self))
            self.addPage(ReqSummaryPage(self))
            self.setWindowTitle('Performance Requirement Wizard')
            self.setGeometry(50, 50, 850, 750);

        self.setSizeGripEnabled(True)

###########################
# General Requirement Pages
###########################

# Includes ID page which uses a flag, verification, and summary. May include
# allocation.

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
        id_panel_layout.addLayout(self.level_layout)
        main_layout = self.layout()
        main_layout.addLayout(id_panel_layout)

    def level_select(self):
        self.req.req_level = self.level_cb.currentText()

    def update_levels(self):
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
            self.pgxn_obj.edit_button.clicked.connect(self.update_levels)
            self.level_cb.setDisabled(False)
            # self.update_levels
            self.req.req_level = self.req.req_level or 0
            if not req_wizard_state.get('performance'):
                self.req.requirement_type = 'functional'
            else:
                self.req.requirement_type = 'performance'
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
        self.req = orb.get(req_wizard_state.get('req_oid'))
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
        self.req.verification_method = req_wizard_state['verification_method']
        orb.save([self.req])


class ReqAllocPage(QWizardPage):
    """
    Page to allocate the requirement to a project, to the role of a system in a
    project, or to the "function" (identified by reference designator) of a
    component or subsystem of a system.
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
        self.setSubTitle("Specify the project system(s) or function(s), "
                         "if known, which will satisfy the requirement...\n"
                         "[left-click on one or more a tree node(s) "
                         "to allocate]")
        project_oid = state.get('project')
        proj = orb.get(project_oid)
        self.project = proj
        self.sys_tree = SystemTreeView(self.project, refdes=True,
                                       show_allocs=True, req=self.req)
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
        # TODO: replace this with the allocation summary
        req_wizard_state['function'] = self.project.id

    def on_select_node(self, index):
        link = None
        fn_name = 'None'
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
            fn_name = link.system_role
        elif hasattr(link, 'component'):
            if self.req in link.allocated_requirements:
                # if this is an existing allocation, remove it
                self.req.allocated_to_function = None
            else:
                self.req.allocated_to_function = link
                # if allocating to function, remove any allocation to system
                if self.req.allocated_to_system:
                    self.req.allocated_to_system = None
            fn_name = link.reference_designator
        self.sys_tree.clearSelection()
        # TODO: get the selected name/product so it can be used in the shall
        # statement.
        req_wizard_state['function'] = fn_name
        orb.save([self.req])
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
    Page to view a summary before saving the new Requirement.
    """
    def __init__(self, parent=None):
        super(ReqSummaryPage, self).__init__(parent)
        layout = QVBoxLayout()
        form = QFormLayout()
        self.allocation_label = 'Allocation:'
        self.verification_label = 'Verification method:'
        self.allocation = ValueLabel('')
        self.verification = ValueLabel('')
        form.addRow(self.allocation_label, self.allocation)
        form.addRow(self.verification_label, self.verification)
        layout.addLayout(form)
        self.setLayout(layout)

    def initializePage(self):
        main_layout = self.layout()
        if self.title():
            main_layout.removeWidget(self.pgxn_obj)
            self.pgxn_obj.close()
        else:
            self.setTitle('New Requirement Summary')
            self.setSubTitle('Confirm all the information is correct...')
        function = req_wizard_state.get('function', 'No Allocation')
        self.allocation.setText(function)
        verification_method = req_wizard_state.get('verification_method',
                                                   'Not Specified')
        self.verification.setText(verification_method)
        requirement = orb.get(req_wizard_state.get('req_oid'))
        panels = ['main']
        # main_view = ['id', 'name', 'description', 'rationale', 'comment']
        self.pgxn_obj = PgxnObject(requirement, panels=panels, edit_mode=False,
                                   # main_view=main_view, required=[],
                                   embedded=True, view_only=True, new=False)
        self.pgxn_obj.toolbar.hide()
        main_layout.addWidget(self.pgxn_obj)

##############################
# Functional Requirement Pages
##############################

# Will only be different if they want the allocation different

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
        layout = QVBoxLayout()
        self.setLayout(layout)

    def initializePage(self):
        self.req = orb.get(req_wizard_state.get('req_oid'))
        if not self.req:
            # TODO: if reqt cant be found, show messsage (page is useless then)
            orb.log.info('* Perf...Page: requirement not found')
        if self.title():
            return

        self.setTitle('Dimension and Type')
        self.setSubTitle('Seclect the dimension of the performance parameter'
                         ' and the type value it will be...')

        # The inner layouts
        dim_layout = QFormLayout()
        type_layout = QFormLayout()

        # Combo box to select the dimension of the requirement.
        # TODO: fill the cb with the dimension options
        dim_label = QLabel('Dimension: ')
        self.dim_cb = QComboBox()
        # dimmension goes here
        for dims in in_si:
            self.dim_cb.addItem(dims)
        dim_layout.addRow(dim_label, self.dim_cb)
        self.dim_cb.currentTextChanged.connect(self.dim_changed)
        self.dim_cb.currentTextChanged.connect(self.completeChanged)

        # vertical line that will be used as a spacer between dimension
        # selection and the selection of the type.
        line = QHLine()
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
        type_layout.addRow(type_label, radio_button_layout)

        # set inner layout spacing
        dim_layout.setContentsMargins(100, 40, 100, 40)
        type_layout.setContentsMargins(100,40,0,40)

        # set main layout and add the layouts to it.
        layout = self.layout()
        layout.setSpacing(30)
        layout.addLayout(dim_layout)
        layout.addWidget(line)
        layout.addLayout(type_layout)

    def tolerance_changed(self):
        tol_type = self.single_cb.currentText()
        req_wizard_state['req_tolerance_type'] = tol_type
        self.req.req_tolerance_type = tol_type
        orb.save([self.req])

    def dim_changed(self):
        dim = self.dim_cb.currentText()
        if dim:
            req_wizard_state['req_dimensions'] = dim
            self.req.req_dimensions = dim
        else:
            req_wizard_state['req_dimensions'] = None
            self.req.req_dimensions = None
        orb.save([self.req])

    def set_constraint_type(self):
        """
        Set the constraint type. This also enables and disables the combobox
        for the symmetric and asymmetric options with the single value button.
        """
        b = self.constraint_buttons.checkedButton()
        const_type = b.text()
        if const_type:
            req_wizard_state['req_constraint_type'] = const_type
            self.req.req_constraint_type = const_type
        else:
            req_wizard_state['req_constraint_type'] = None
            self.req.req_constraint_type = None
        if b == self.single_button:
            self.single_cb.setDisabled(False)
            rtt = self.single_cb.currentText()
            req_wizard_state['req_tolerance_type'] = rtt
            self.req.req_tolerance_type = rtt
        else:
            self.single_cb.setDisabled(True)
        orb.save([self.req])

    def isComplete(self):
        """
        Check if both dimension and type have been specified
        """
        if (not req_wizard_state.get('req_dimensions')
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
            self.allocate_label.hide()
            self.shall_hbox_top.removeWidget(self.allocate_label)
            self.allocate_label.parent = None
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
        shall_text = req_wizard_state.get('shall_text')
        if shall_text:
            self.shall_cb.setCurrentText(shall_text)
        self.shall_cb.currentIndexChanged.connect(self.set_shall_text)

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
                    self.maximum_value.setText(maximum_value)
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
                    self.minimum_value.setText(minimum_value)
                else:
                    self.minimum_value.setPlaceholderText('minimum')
                self.minimum_value.textChanged.connect(self.num_entered)
            self.min_max_cb = QComboBox()
            for opt in min_max_cb_options:
                self.min_max_cb.addItem(opt)
            min_max_text = req_wizard_state.get('min_max_text')
            if min_max_text:
                self.min_max_cb.setCurrentText(min_max_text)
            self.min_max_cb.currentIndexChanged.connect(self.set_min_max_text)
            self.min_max_cb.setMaximumSize(150,25)

        # premade labels text (non-editable labels)
        allocate = req_wizard_state.get('function')
        self.allocate_label = QComboBox()
        self.allocate_label.addItem(allocate)
        self.allocate_label.addItem("The " + allocate)
        self.allocate_label.setMaximumSize(175,25)

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
                    self.minimum_value.setText(minimum_value)
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
                    self.maximum_value.setText(maximum_value)
                else:
                    self.maximum_value.setPlaceholderText('maximum')
                self.maximum_value.textChanged.connect(self.num_entered)
        else:
            self.target_value = QLineEdit()
            self.target_value.setValidator(double_validator)
            target_value = req_wizard_state.get('req_target_value', '')
            self.target_value.setPlaceholderText('target value')
            if target_value:
                self.target_value.setText(target_value)
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
                        req_wizard_state.get('req_tolerance_lower', ''))
                self.lower_limit.textChanged.connect(self.num_entered)
                self.upper_limit = QLineEdit()
                self.upper_limit.setValidator(double_validator)
                self.upper_limit.setMaximumSize(120, 25)
                self.upper_limit.setPlaceholderText('upper tolerance')
                self.upper_limit.setText(
                        req_wizard_state.get('req_tolerance_upper', ''))
                self.upper_limit.textChanged.connect(self.num_entered)
            elif tolerance_type == 'Symmetric Tolerance':
                self.plus_minus_label = QLabel('+/-')
                self.plus_minus_label.setMaximumSize(30, 25)
                self.tol_val_field = QLineEdit()
                self.tol_val_field.setValidator(double_validator)
                self.tol_val_field.setMaximumSize(100, 25)
                self.tol_val_field.setPlaceholderText('tolerance')
                self.tol_val_field.setText(
                            req_wizard_state.get('req_tolerance', ''))
                self.tol_val_field.textChanged.connect(self.num_entered)

        # units combo box.
        self.units = QComboBox()
        dims = req_wizard_state.get('req_dimensions')
        units_list = alt_units.get(dims, None)
        if units_list:
            for unit in units_list:
                self.units.addItem(unit)
        else:
            self.units.addItem(in_si[dims])
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
        subject = req_wizard_state.get('subject')
        if subject:
            self.subject_field.setReadOnly(False)
            self.subject_field.setText(subject)
        else:
            self.subject_field.setReadOnly(True)
        self.predicate_field = QLineEdit()
        predicate = req_wizard_state.get('predicate')
        if predicate:
            self.predicate_field.setReadOnly(False)
            self.predicate_field.setText(predicate)
        else:
            self.predicate_field.setReadOnly(True)
        self.epilog_field = QLineEdit()
        epilog = req_wizard_state.get('epilog')
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
        self.shall_hbox_top.addWidget(self.allocate_label)
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

    def set_shall_text(self):
        req_wizard_state['shall_text'] = self.shall_cb.currentText()

    def set_min_max_text(self):
        req_wizard_state['min_max_text'] = self.min_max_cb.currentText()
        self.req.min_max_text = self.min_max_cb.currentText()
        orb.save([self.req])

    def num_entered(self):
        if self.target_value:
            tv_txt = self.target_value.text()
            try:
                req_wizard_state['req_target_value'] = float(tv_txt)
                self.req.req_target_value = float(tv_txt)
            except:
                # field was empty or bad value
                pass
        if self.maximum_value:
            max_txt = self.maximum_value.text()
            try:
                req_wizard_state['req_maximum_value'] = float(max_txt)
                self.req.req_maximum_value = float(max_txt)
            except:
                # field was empty or bad value
                pass
        if self.minimum_value:
            min_txt = self.minimum_value.text()
            try:
                req_wizard_state['req_minimum_value'] = float(min_txt)
                self.req.req_minimum_value = float(min_txt)
            except:
                # field was empty or bad value
                pass
        if self.lower_limit:
            lower_txt = self.lower_limit.text()
            try:
                req_wizard_state['req_tolerance_lower'] = float(lower_txt)
                self.req.req_tolerance_lower = float(lower_txt)
            except:
                # field was empty or bad value
                pass
            upper_txt = self.upper_limit.text()
            try:
                req_wizard_state['req_tolerance_upper'] = float(upper_txt)
                self.req.req_tolerance_upper = float(upper_txt)
            except:
                # field was empty or bad value
                pass
        if self.tol_val_field:
            tol_txt = self.tol_val_field.text()
            try:
                req_wizard_state['req_tolerance'] = float(tol_txt)
                self.req.req_tolerance = float(tol_txt)
            except:
                # field was empty or bad value
                pass
        orb.save([self.req])

    def contextMenu(self, event):
        self.selected_widget = self.sender()
        if self.selected_widget.isReadOnly():
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
        shall_prev = ''
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
                elif not w.isReadOnly():
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
        req_wizard_state['subject'] = self.subject_field.text()
        req_wizard_state['predicate'] = self.predicate_field.text()
        req_wizard_state['epilog'] = self.epilog_field.text()
        req_wizard_state['description'] = ''
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
                if req_wizard_state.get('description'):
                    # if already some stuff, add a space before next stuff ...
                    req_wizard_state['description'] += ' '
                if hasattr(w, 'currentText'):
                    req_wizard_state['description'] += w.currentText()
                elif w in [self.plus_minus_label, self.minus_label,
                           self.plus_label, self.range_label]:
                    req_wizard_state['description'] += w.text()
                elif hasattr(w, 'isReadOnly') and not w.isReadOnly():
                    req_wizard_state['description'] += w.text()
        if req_wizard_state['description'] == '':
            return False
        req_wizard_state['description'] = req_wizard_state[
                                                'description'].strip() + '.'
        req_wizard_state['rationale'] = self.rationale_field.toPlainText()
        if not req_wizard_state.get('rationale'):
            return False
        # TODO: get the project
        # assign description and rationale
        requirement = orb.get(req_wizard_state.get('req_oid'))
        requirement.description = req_wizard_state['description']
        requirement.rationale = req_wizard_state['rationale']
        requirement.req_target_value = req_wizard_state.get(
                                                        'req_target_value')
        requirement.req_maximum_value = req_wizard_state.get(
                                                        'req_maximum_value')
        requirement.req_minimum_value = req_wizard_state.get(
                                                        'req_minimum_value')
        if requirement.req_constraint_type == 'single value':
            if not requirement.req_target_value:
                return False
            if (requirement.req_tolerance_type == 'Symmetric Tolerance'
                and requirement.req_tolerance is None):
                return False
            elif (requirement.req_tolerance_lower is None
                  or requirement.req_tolerance_upper is None):
                # Asymmetric Tolerance requires upper and lower tols
                return False
        elif (requirement.req_constraint_type == 'maximum'
              and requirement.req_maximum_value is None):
            return False
        elif (requirement.req_constraint_type == 'minimum'
              and requirement.req_minimum_value is None):
            return False
        orb.save([requirement])
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

class QHLine(QFrame):
    def __init__(self):
        super(QHLine, self).__init__()
        self.setFrameShape(QFrame.HLine)

