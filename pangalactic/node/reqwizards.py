# -*- coding: utf-8 -*-
"""
Requirements Wizards
"""
from builtins import str
from builtins import range
import os
from PyQt5 import QtGui
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QButtonGroup, QComboBox, QFormLayout, QHBoxLayout,
                             QLabel, QLineEdit, QFrame, QMenu, QMessageBox,
                             QPlainTextEdit, QPushButton, QRadioButton,
                             QVBoxLayout, QWizard, QWizardPage)

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
                'frozen', 'derived_from' ,'public', 'level', 'validated']


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
            req_wizard_state['ver_method'] = req.verification_method
            performance = (req.requirement_type == 'performance')
        if not performance:
            req_wizard_state['perform'] = False
            self.addPage(RequirementIDPage(self))
            self.addPage(ReqAllocPage(self))
            self.addPage(ReqVerificationPage(self))
            self.addPage(ReqSummaryPage(self))
            self.setWindowTitle('Functional Requirement Wizard')
            self.setGeometry(50, 50, 850, 900);
        else:
            req_wizard_state['perform'] = True
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
        perform = req_wizard_state.get('perform')
        proj_oid = state.get('project')
        self.project = orb.get(proj_oid)
        req = orb.get(req_wizard_state.get('req_oid'))
        if req:
            self.req = req
        else:
            # NOTE: requirement id must be generated before cloning new reqt.;
            # otherwise, generator will get confused
            req_id = gen_req_id(self.project)
            self.req = clone("Requirement", id=req_id, owner=self.project,
                             public=True)
            orb.save([self.req])
        req_wizard_state['req_oid'] = self.req.oid
        # Where the perform and functional differ
        main_view = []
        required = []
        if perform:
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
                                   mask=mask, edit_mode=True, new=True,
                                   enable_delete=False)
        self.pgxn_obj.toolbar.hide()
        self.pgxn_obj.save_button.clicked.connect(self.completeChanged)
        self.pgxn_obj.save_button.clicked.connect(self.update_levels)
        self.pgxn_obj.bbox.clicked.connect(self.update_levels)
        self.pgxn_obj.bbox.clicked.connect(self.completeChanged)
        self.pgxn_obj.setAttribute(Qt.WA_DeleteOnClose)
        self.wizard().button(QWizard.FinishButton).clicked.connect(
                self.close_pgxn_obj)
        instructions = '<p>The following fields are required:<ul>'
        instructions += '<li><b>name</b>: descriptive name '
        instructions += '(may contain spaces)</li>'
        if not perform:
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
        self.req.level = self.level_cb.currentText()

    def update_levels(self):
        self.level_cb.removeItem(1)
        self.level_cb.removeItem(0)
        if self.req.derived_from:
            parent_level = self.req.derived_from.level
            self.level_cb.addItem(str(parent_level))
            self.level_cb.addItem(str(parent_level+1))
        else:
            self.level_cb.addItem(str(0))
            self.level_cb.addItem(str(1))
        if hasattr(self.pgxn_obj, 'edit_button'):
            self.pgxn_obj.edit_button.clicked.connect(self.completeChanged)
        self.pgxn_obj.bbox.clicked.connect(self.completeChanged)
        self.pgxn_obj.save_button.clicked.connect(self.completeChanged)

    def close_pgxn_obj(self):
        if getattr(self,'pgxn_obj', None):
            self.pgxn_obj.close()
            self.pgxn_obj = None

    def isComplete(self):

        self.pgxn_obj.bbox.clicked.connect(self.update_levels)
        self.pgxn_obj.save_button.clicked.connect(self.update_levels)
        if self.pgxn_obj.edit_mode:
            self.level_cb.setDisabled(True)
            return False
        self.level_cb.setDisabled(False)
        self.pgxn_obj.edit_button.clicked.connect(self.update_levels)
        self.req.level = self.req.level or 0
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
        self.button_group = QButtonGroup()

        test_button = QRadioButton("Test")
        analysis_button = QRadioButton("Analysis")
        inspection_button = QRadioButton("Inspection")
        later_button = QRadioButton("Specify Verification Method Later")
        later_button.setChecked(True)
        self.button_group.addButton(test_button)
        self.button_group.addButton(analysis_button)
        self.button_group.addButton(inspection_button)
        self.button_group.addButton(later_button)
        ver_method = req_wizard_state.get('ver_method',
                                          'Specify Verification Method Later')
        if ver_method:
            if ver_method == "Test":
                test_button.setChecked(True)
            elif ver_method == "Analysis":
                analysis_button.setChecked(True)
            elif ver_method == "Inspection":
                inspection_button.setChecked(True)
            elif ver_method == "Specify Verification Method Later":
                later_button.setChecked(True)
        layout.addWidget(inst_label)
        layout.addWidget(test_button)
        layout.addWidget(analysis_button)
        layout.addWidget(inspection_button)
        layout.addWidget(later_button)
        self.button_group.buttonClicked.connect(self.button_clicked)
        self.setLayout(layout)

    def button_clicked(self):
        req_wizard_state['ver_method'] = self.button_group.checkedButton().text()


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
        if self.title():
            return;
        self.req = orb.get(req_wizard_state.get('req_oid'))
        if not self.req:
            # TODO: if reqt cant be found, show messsage (page is useless then)
            orb.log.info('* requirement not found')
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
                # TODO: dialog offering to remove the allocation
                pass
            else:
                self.req.allocated_to_system = link
            fn_name = link.system_role
        elif hasattr(link, 'component'):
            if self.req in link.allocated_requirements:
                # TODO: dialog offering to remove the allocation
                pass
            else:
                self.req.allocated_to_function = link
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
        msg = '<h3>Requirement Allocation:</h3><b>'
        if self.req.allocated_to_system:
            msg += self.req.allocated_to_system.system_role
        elif self.req.allocated_to_function:
            msg += self.req.allocated_to_function.reference_designator
        else:
            msg += '[None]'
        msg += '</b>'
        self.summary.setText(msg)


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
        ver_method = req_wizard_state.get('ver_method', 'Not Specified')
        self.verification.setText(ver_method)
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
    creating the shall statement on the next page.
    """

    def __init__(self, parent=None):
        super(PerformanceDefineParmPage, self).__init__(parent)
        layout = QVBoxLayout()
        self.setLayout(layout)

    def initializePage(self):
        if self.title():
            return

        self.setTitle('Dimension and Type')
        self.setSubTitle('Seclect the dimension of the performance parameter'
                         ' and the type value it will be...')

        # The inner layouts
        dim_layout = QFormLayout()
        type_layout = QFormLayout()
        type_layout.single_val_layout = QHBoxLayout()

        # Combo box to select the dimension of the requirement.
        # TODO: fill the cb with the dimension options
        dim_label = QLabel('Dimension: ')
        self.dim_cb = QComboBox()
        # dimmension goes here
        for key in in_si:
            self.dim_cb.addItem(key)
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
        self.sing_form = QFormLayout()
        type_label = QLabel('Type: ')
        self.min_button = QRadioButton('minimum')
        self.max_button = QRadioButton('maximum')
        self.sing_button = QRadioButton('single value')
        self.range_button = QRadioButton('range')
        self.sing_cb = QComboBox()
        self.sing_cb.addItem('Symmetric Tolerance')
        self.sing_cb.addItem('Asymmetric Tolerance')
        self.sing_cb.currentIndexChanged.connect(self.tolerance_changed)
        self.sing_form.addRow(self.sing_button, self.sing_cb)
        self.sing_cb.setDisabled(True)

        # Add to the button group and handle the button clicked
        self.button_group = QButtonGroup()
        self.button_group.addButton(self.min_button)
        self.button_group.addButton(self.max_button)
        self.button_group.addButton(self.sing_button)
        self.button_group.addButton(self.range_button)
        val_type = req_wizard_state.get('val_type')
        if val_type:
            if val_type == 'minimum':
                self.min_button.setChecked(True)
            elif val_type == 'maximum':
                self.max_button.setChecked(True)
            elif val_type == 'single value':
                self.sing_button.setChecked(True)
                tolerance = req_wizard_state.get('tolerance')
                if tolerance:
                    self.sing_cb.setDisabled(False)
                    self.sing_cb.setCurrentText(tolerance)
            elif val_type == 'range':
                self.range_button.setChecked(True)
        self.button_group.buttonClicked.connect(self.button_changed)
        self.button_group.buttonClicked.connect(self.completeChanged)

        # create and add buttons to a vertical box layout
        type_layout.radio_button_layout = QVBoxLayout()
        type_layout.radio_button_layout.addWidget(self.min_button)
        type_layout.radio_button_layout.addWidget(self.max_button)
        type_layout.radio_button_layout.addLayout(self.sing_form)
        type_layout.radio_button_layout.addWidget(self.range_button)

        # add radio_button_layout to the main type layout.
        type_layout.addRow(type_label, type_layout.radio_button_layout)

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
        req_wizard_state['tolerance'] = self.sing_cb.currentText()

    def dim_changed(self):
        req_wizard_state['dim'] = self.dim_cb.currentText()

    def button_changed(self):
        """
        Handle the selection in the type button selection. Also enables and
        disables the combobox for the symmetric and asymmetric options with the
        single value button.
        """
        b = self.button_group.checkedButton()
        req_wizard_state['val_type'] = b.text()
        if b == self.sing_button:
            self.sing_cb.setDisabled(False)
            req_wizard_state['tolerance'] = self.sing_cb.currentText()
        else:
            self.sing_cb.setDisabled(True)

    def isComplete(self):
        """
        Check if both dimension and type have been specified
        """
        if not req_wizard_state.get('dim'):
            return False
        if not req_wizard_state.get('val_type'):
            return False
        return True


class PerformReqBuildShallPage(QWizardPage):
    """
    Build the shall statement and fill in the rationale.
    """

    def __init__(self, parent=None):
        super(PerformReqBuildShallPage, self).__init__(parent)
        layout = QVBoxLayout()
        self.setLayout(layout)

    def initializePage(self):
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
            if self.min_max_cb:
                self.min_max_cb.hide()
                self.shall_hbox_middle.removeWidget(self.min_max_cb)
                self.min_max_cb.parent = None
                self.base_val.hide()
                self.shall_hbox_bottom.removeWidget(self.base_val)
                self.base_val.parent = None
                self.units.hide()
                self.shall_hbox_bottom.removeWidget(self.units)
                self.units.parent = None
            else:
                self.base_val.hide()
                self.shall_hbox_middle.removeWidget(self.base_val)
                self.base_val.parent = None
                self.units.hide()
                self.shall_hbox_middle.removeWidget(self.units)
                self.units.parent = None
            if self.lower_limit:
                self.lower_limit.hide()
                self.shall_hbox_middle.removeWidget(self.lower_limit)
                self.lower_limit.parent = None
                self.upper_limit.hide()
                self.shall_hbox_middle.removeWidget(self.upper_limit)
                self.upper_limit.parent = None
                self.plus_minus_cb1.hide()
                self.shall_hbox_middle.removeWidget(self.plus_minus_cb1)
                self.plus_minus_cb1.parent = None
                self.plus_minus_cb2.hide()
                self.shall_hbox_middle.removeWidget(self.plus_minus_cb2)
                self.plus_minus_cb2.parent = None
            if self.plus_minus_label:
                self.plus_minus_label.hide()
                self.shall_hbox_middle.removeWidget(self.plus_minus_label)
                self.plus_minus_label.parent = None
                self.tol_val_field.hide()
                self.shall_hbox_middle.removeWidget(self.tol_val_field)
                self.tol_val_field.parent = None
            if self.range_label:
                self.range_label.hide()
                self.shall_hbox_middle.removeWidget(self.range_label)
                self.range_label.parent = None
                self.max_val.hide()
                self.shall_hbox_middle.removeWidget(self.max_val)
                self.max_val.parent = None
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
        self.setSubTitle('Construct the shall statement using the instructions'
                    ' below, and then provide the requirements rationale...')

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
        shall_opt = req_wizard_state.get('shall_opt')
        if shall_opt:
            self.shall_cb.setCurrentText(shall_opt)
        self.shall_cb.currentIndexChanged.connect(self.set_shall_opt)

        min_max_cb_options = None
        self.min_max_cb = None
        # gets the type from the previous page, says if the type is max, min,
        # single, or range value(s)
        val_type = req_wizard_state.get('val_type')
        # if val_type is 'minimum' or 'maximum', set up min-max combo
        if val_type in ['maximum', 'minimum']:
            if val_type == 'maximum':
                min_max_cb_options = max_options
            elif val_type == 'minimum':
                min_max_cb_options = min_options
            self.min_max_cb = QComboBox()
            for opt in min_max_cb_options:
                self.min_max_cb.addItem(opt)
            min_max_opt = req_wizard_state.get('min_max_opt')
            if min_max_opt:
                self.min_max_cb.setCurrentText(min_max_opt)
            self.min_max_cb.currentIndexChanged.connect(self.set_min_max_opt)
            self.min_max_cb.setMaximumSize(150,25)

        # premade labels text (non-editable labels)
        allocate = req_wizard_state.get('function')
        self.allocate_label = QComboBox()
        self.allocate_label.addItem(allocate)
        self.allocate_label.addItem("The " + allocate)
        self.allocate_label.setMaximumSize(175,25)

        # line edit(s) for number entry
        # TODO: make one numeric entry unless it is range then make two.
        doubleValidator = QtGui.QDoubleValidator()
        self.base_val = QLineEdit()
        self.base_val.setValidator(doubleValidator)
        base_val = req_wizard_state.get('base_val', '')
        self.base_val.setPlaceholderText('number')
        if base_val:
            self.base_val.setText(base_val)
        self.base_val.setMaximumSize(75,25)
        self.base_val.textChanged.connect(self.num_entered)
        if val_type == 'range':
            # if range, base_val is reinterpreted as min value
            self.base_val.setPlaceholderText('min. value')
            self.max_val = QLineEdit()
            self.max_val.setValidator(doubleValidator)
            self.max_val.setMaximumSize(75, 25)
            max_val = req_wizard_state.get('max_val', '')
            if max_val:
                self.max_val.setText(max_val)
            else:
                self.max_val.setPlaceholderText('max. value')
            self.max_val.textChanged.connect(self.num_entered)
            self.range_label = QLabel('to')
            self.range_label.setMaximumSize(20, 25)
        else:
            self.max_val = None
            self.range_label = None
        self.plus_minus_cb1 = QComboBox()
        self.plus_minus_cb2 = QComboBox()
        self.lower_limit = None
        self.plus_minus_label = None
        self.tol_val_field = None
        tolerance = req_wizard_state.get('tolerance')
        if tolerance:
            if tolerance == 'Asymmetric Tolerance':
                plus = '+'
                or_plus = 'or +'
                minus = '-'
                or_minus = ' or -'
                self.plus_minus_cb1.addItem(plus)
                self.plus_minus_cb1.addItem(minus)
                self.plus_minus_cb2.addItem(or_plus)
                self.plus_minus_cb2.addItem(or_minus)
                self.lower_limit = QLineEdit()
                self.lower_limit.setValidator(doubleValidator)
                self.lower_limit.setMaximumSize(50,25)
                self.lower_limit.setPlaceholderText('lower limit')
                self.lower_limit.setText(
                                req_wizard_state.get('lower_limit', ''))
                self.lower_limit.textChanged.connect(self.num_entered)
                self.upper_limit = QLineEdit()
                self.upper_limit.setValidator(doubleValidator)
                self.upper_limit.setMaximumSize(50,25)
                self.upper_limit.setPlaceholderText('upper limit')
                self.upper_limit.setText(
                                req_wizard_state.get('upper_limit', ''))
                self.upper_limit.textChanged.connect(self.num_entered)
            elif tolerance == 'Symmetric Tolerance':
                self.plus_minus_label = QLabel('+/-')
                self.plus_minus_label.setMaximumSize(30,25)
                self.tol_val_field = QLineEdit()
                self.tol_val_field.setValidator(doubleValidator)
                self.tol_val_field.setMaximumSize(75,25)
                self.tol_val_field.setPlaceholderText('tolerance')
                self.tol_val_field.setText(req_wizard_state.get('tol_val', ''))
                self.tol_val_field.textChanged.connect(self.num_entered)

        # units combo box.
        self.units = QComboBox()
        key = req_wizard_state.get('dim')
        units_list = alt_units.get(key, None)
        if units_list:
            for unit in units_list:
                self.units.addItem(unit)
        else:
            self.units.addItem(in_si[key])
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

        # optional text components of the shall statement
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
            self.shall_hbox_bottom.addWidget(self.base_val)
            self.shall_hbox_bottom.addWidget(self.units)
        else:
            self.shall_hbox_middle.addWidget(self.base_val)
            if tolerance == 'Asymmetric Tolerance':
                self.shall_hbox_middle.addWidget(self.plus_minus_cb1)
                self.shall_hbox_middle.addWidget(self.lower_limit)
                self.shall_hbox_middle.addWidget(self.plus_minus_cb2)
                self.shall_hbox_middle.addWidget(self.upper_limit)
                self.shall_hbox_middle.addWidget(self.units)
            elif tolerance == 'Symmetric Tolerance':
                self.shall_hbox_middle.addWidget(self.plus_minus_label)
                self.shall_hbox_middle.addWidget(self.tol_val_field)
                self.shall_hbox_middle.addWidget(self.units)
            elif self.max_val:
                self.shall_hbox_middle.addWidget(self.range_label)
                self.shall_hbox_middle.addWidget(self.max_val)
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

    def set_shall_opt(self):
        req_wizard_state['shall_opt'] = self.shall_cb.currentText()

    def set_min_max_opt(self):
        req_wizard_state['min_max_opt'] = self.min_max_cb.currentText()

    def num_entered(self):
        req_wizard_state['base_val'] = self.base_val.text()
        if self.max_val:
            req_wizard_state['max_val'] = self.max_val.text()
        if self.lower_limit:
            req_wizard_state['lower_limit'] = self.lower_limit.text()
            req_wizard_state['upper_limit'] = self.upper_limit.text()
        if self.tol_val_field:
            req_wizard_state['tol_val'] = self.tol_val_field.text()

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
        instructions = "In the shall statement area input the required "
        instructions += "fields (these vary on selections from previous page "
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
        instructions += "shall statement. <br>NOTE: <b>DO NOT</b> add a "
        instructions += "period in the last text box as this will be added "
        instructions += "anyways."
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
                        w != self.plus_minus_cb1 and w != self.plus_minus_cb2
                        and w != self.plus_minus_label):
                    shall_prev += ' '
        shall_prev += '.'
        if req_wizard_state.get('shall') and req_wizard_state.get('rationale'):
            shall_rat = "Shall Statement:\n{}".format(
                                        req_wizard_state['shall'])
            shall_rat +="\n\nRationale:\n{}".format(
                                        req_wizard_state['rationale'])
        else:
            shall_rat = "Shall statement and rationale have not been saved."
        QMessageBox.question(self, 'preview', shall_rat, QMessageBox.Ok)

    def isComplete(self):
        """
        Check that base_val, max_val (optional), rationale, and all text
        fields are filled.
        """
        # numbers are saved to state as they are typed ... text fields are
        # saved to state here (to avoid impact on user feel)
        req_wizard_state['subject'] = self.subject_field.text()
        req_wizard_state['predicate'] = self.predicate_field.text()
        req_wizard_state['epilog'] = self.epilog_field.text()
        req_wizard_state['shall'] = ''
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
                if req_wizard_state.get('shall'):
                    # if already some stuff, add a space before next stuff ...
                    req_wizard_state['shall'] += ' '
                if hasattr(w, 'currentText'):
                    req_wizard_state['shall'] += w.currentText()
                elif w == self.plus_minus_label or w == self.range_label:
                    req_wizard_state['shall'] += w.text()
                elif not w.isReadOnly():
                    req_wizard_state['shall'] += w.text()
                # if (w != self.epilog_field and w != self.units and
                        # w != self.plus_minus_cb1 and w != self.plus_minus_cb2
                        # and w != self.plus_minus_label):
                    # req_wizard_state['shall'] += ' '
        if req_wizard_state['shall'] == '':
            return False
        req_wizard_state['shall'] = req_wizard_state['shall'].strip() + '.'
        req_wizard_state['rationale'] = self.rationale_field.toPlainText()
        if not req_wizard_state.get('rationale'):
            return False
        # TODO: get the project
        # assign description and rationale
        requirement = orb.get(req_wizard_state.get('req_oid'))
        requirement.description = req_wizard_state['shall']
        requirement.rationale = req_wizard_state['rationale']
        if not req_wizard_state.get('base_val'):
            return False
        if self.lower_limit:
            if (not req_wizard_state.get('lower_limit') or
                not req_wizard_state.get('upper_limit')):
                return False
        if self.tol_val_field:
            if not req_wizard_state.get('tol_val'):
                return False
        if self.max_val:
            if not req_wizard_state.get('max_val'):
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

