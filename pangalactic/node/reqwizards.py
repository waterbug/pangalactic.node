# -*- coding: utf-8 -*-
"""
Requirements Wizards
"""
import os
from PyQt5 import QtGui
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QButtonGroup, QComboBox, QFormLayout, QHBoxLayout,
                             QLabel, QLineEdit, QFrame, QMenu, QMessageBox,
                             QPlainTextEdit, QPushButton, QRadioButton,
                             QVBoxLayout, QWizard, QWizardPage)

from louie import dispatcher

from pangalactic.core             import config, state
from pangalactic.core.uberorb     import orb
from pangalactic.core.units       import in_si, alt_units
from pangalactic.node.filters     import FilterPanel
from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.utils       import clone
from pangalactic.node.widgets     import NameLabel, PlaceHolder, ValueLabel
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
        # try:
        seq = max([int(idv[0].split('.')[1]) for idv in project_idvs]) + 1
        # except:
            # orb.log.info('* gen_req_id: could not parse reqt ids.')
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
    def __init__(self, parent=None, performance=False):
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

        if not performance:
            self.addPage(RequirementIDPage(self))
            self.addPage(ReqAllocPage(self))
            self.addPage(ReqVerificationPage(self))
            self.addPage(ReqSummaryPage(self))
            self.setWindowTitle('Functional Requirement Wizard')
            self.setGeometry(50, 50, 850, 900);
        else:
            self.addPage(RequirementIDPage(self))
            self.addPage(ReqAllocPage(self))
            self.addPage(PerformanceDefineParmPage(self))
            self.addPage(PerformReqBuildShallPage(self))
            self.addPage(PerformanceMarginCalcPage(self))
            self.addPage(ReqVerificationPage(self))
            self.addPage(ReqSummaryPage(self))
            req_wizard_state['perform'] = True
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
        self.pgxn_obj = PgxnObject(self.req, embedded=True,
                        panels=panels, main_view=main_view,required=required,
                        mask=mask, edit_mode=True,new=True,
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
        req_wizard_state['ver_type'] = 'Specify Verification Method Later'

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

        layout.addWidget(inst_label)
        layout.addWidget(test_button)
        layout.addWidget(analysis_button)
        layout.addWidget(inspection_button)
        layout.addWidget(later_button)
        self.button_group.buttonClicked.connect(self.button_clicked)
        self.setLayout(layout)

    def button_clicked(self):
        req_wizard_state['ver_type'] = self.button_group.checkedButton().text()


class ReqDisciplinePage(QWizardPage):
    """
    Page to tag the requirement with a discipline to which it is relevant.
    """

    def __init__(self, parent=None):
        super(ReqDisciplinePage, self).__init__(parent=parent)
        req_wizard_state['discipline'] = None

    def initializePage(self):
        if self.title():
            return;

        self.setTitle("Requirement Discipline Allocation")
        self.setSubTitle("Specify the Discipline, if known, "
                         "which will inherit the requirement...")

        disciplines = orb.get_by_type('Discipline')
        label = 'Discipline'
        self.discipline_panel = FilterPanel(disciplines, label=label,
                parent=self)
        self.discipline_view = self.discipline_panel.proxy_view
        self.discipline_view.clicked.connect(self.discipline_selected)
        self.discipline_view.clicked.connect(self.completeChanged)
        hbox = QHBoxLayout()
        hbox.addWidget(self.discipline_panel)
        main_layout = QVBoxLayout()
        main_layout.addLayout(hbox)
        self.discipline_label = NameLabel('Selected Discipline:')
        self.discipline_label.setVisible(False)
        self.discipline_value_label = ValueLabel('')
        self.discipline_value_label.setVisible(False)
        discipline_layout = QHBoxLayout()
        discipline_layout.addWidget(self.discipline_label)
        discipline_layout.addWidget(self.discipline_value_label)
        discipline_layout.addStretch(1)
        main_layout.addLayout(discipline_layout)
        self.setLayout(main_layout)

    def discipline_selected(self, clicked_index):
        mapped_row = self.discipline_panel.proxy_model.mapToSource(
                                                clicked_index).row()
        req_wizard_state['discipline'] = self.discipline_panel.objs[mapped_row]

        discipline = req_wizard_state.get('discipline')
        discipline_name = getattr(discipline, 'name', '[not set]')
        orb.log.debug('  ... which is "{}"'.format(discipline_name))
        if discipline:
            self.discipline_label.setVisible(True)
            self.discipline_value_label.setText(discipline_name)
            self.discipline_value_label.setVisible(True)

    def isComplete(self):
        return True


class ReqAllocPage(QWizardPage):
    """
    Page to allocate the requirement to a project, to the role of a system in a
    project, or to the "function" (identified by reference designator) of a
    component or subsystem of a system.
    """

    def __init__(self,parent=None):
        super(ReqAllocPage, self).__init__(parent)
        layout = QVBoxLayout()
        self.setLayout(layout)

    def initializePage(self):
        if self.title():
            return;
        project_oid = state.get('project')
        proj = orb.get(project_oid)
        self.project = proj
        self.sys_tree = SystemTreeView(self.project, refdes=True)
        self.sys_tree.expandAll()
        dispatcher.connect(self.select_node, 'sys node selected')
        req_wizard_state['function'] = None
        self.setTitle("Requirement Allocation")
        self.setSubTitle("Specify the function / subsystem, if known, "
                         "which will satisfy the requirement...")
        layout = self.layout()
        layout.addWidget(self.sys_tree)
        self.setLayout(layout)
        # default unless one is selected below
        req_wizard_state['function'] = self.project.id

    def select_node(self, link=None):
        if not link:
            return
        req = orb.get(req_wizard_state.get('req_oid'))
        if not req:
            orb.log.info('* requirement not found')
            return
        # TODO: generate an id (look in utils for methods)
        if hasattr(link, 'system'):
            stuff = orb.search_exact(requirement=req, supported_by=link)
            if stuff:
                # TODO: Give nice little message to the user
                pass
            fn_name = link.system_role
            sr_id = 'SYSTEM-REQ-' + req.id + '-for-system-' + fn_name
            sr_name = ' '.join(['System Requirement', req.name,
                                'allocation to system', fn_name])
            new_obj = clone('SystemRequirement', requirement=req,
                            supported_by=link, id=sr_id, name=sr_name)

        elif hasattr(link, 'component'):
            stuff = orb.search_exact(allocated_requirement=req, satisfied_by=link)
            if stuff:
                # TODO: Give nice little message to the user
                pass
            fn_name = link.reference_designator
            alloc_id = 'REQ-ALLOCATION-' + req.id + '-to-subsystem-' + fn_name
            alloc_name = ' '.join(['Allocation of Requirement', req.name, 
                                   'to subsystem', fn_name])
            new_obj = clone('RequirementAllocation', allocated_requirement=req,
                            satisfied_by=link, id=alloc_id, name=alloc_name)

        # TODO: get the selected name/product so it can be used in the shall
        # statement.
        req_wizard_state['function'] = fn_name
        orb.save([new_obj])

class ReqSummaryPage(QWizardPage):
    """
    Page to view a summary before saving the new Requirement.
    """
    def __init__(self, parent=None):
        super(ReqSummaryPage, self).__init__(parent)
        layout = QVBoxLayout()
        form = QFormLayout()
        self.allocation_label = 'Functional Allocation:'
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
        self.setTitle('New Requirement Summary')
        self.setSubTitle('Confirm all the information is correct...')
        function = req_wizard_state.get('function')
        ver_method = req_wizard_state.get('ver_type')
        # check if the user is allocating later,
        # will display not specified if not specified.
        if not function:
            function = "Not Specified"
        self.allocation.setText(function)
        self.verification.setText(ver_method)
        requirement = orb.get(req_wizard_state.get('req_oid'))
        panels = ['main','info']
        self.pgxn_obj = PgxnObject(requirement, panels=panels,
                edit_mode=False, mask=all_req_fields, required=[],
                view=all_req_fields, embedded=True, new=False)
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
        req_wizard_state['val_type'] = None
        req_wizard_state['tolerance'] = None
        req_wizard_state['dim'] = None

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
            req_wizard_state['tolerance'] = None

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
    Drag and drop way the build the shall statement and also fills in the
    rationale.
    """

    def __init__(self, parent=None):
        super(PerformReqBuildShallPage, self).__init__(parent)
        layout = QVBoxLayout()
        self.setLayout(layout)
        req_wizard_state['shall'] = None
        req_wizard_state['rationale'] = None

    def initializePage(self):
        layout = self.layout()
        req_wizard_state['num1'] = None
        req_wizard_state['num2'] = None
        req_wizard_state['first_num'] = None
        req_wizard_state['second_num'] = None
        req_wizard_state['tol_num'] = None

        if self.title():

            # remove from first hbox
            self.allocate_label.hide()
            self.shall_hbox_top.removeWidget(self.allocate_label)
            self.allocate_label.parent = None
            self.text_box1.hide()
            self.shall_hbox_top.removeWidget(self.text_box1)
            self.text_box1.parent = None
            self.shall_cb.hide()
            self.shall_hbox_top.removeWidget(self.shall_cb)
            self.shall_cb.parent = None

            # remove from middle hbox
            self.text_box2.hide()
            self.shall_hbox_middle.removeWidget(self.text_box2)
            self.text_box2.parent = None
            if self.t_shall:
                self.t_shall.hide()
                self.shall_hbox_middle.removeWidget(self.t_shall)
                self.t_shall.parent = None
                self.num1.hide()
                self.shall_hbox_bottom.removeWidget(self.num1)
                self.num1.parent = None
                self.units.hide()
                self.shall_hbox_bottom.removeWidget(self.units)
                self.units.parent = None
            else:
                self.num1.hide()
                self.shall_hbox_middle.removeWidget(self.num1)
                self.num1.parent = None
                self.units.hide()
                self.shall_hbox_middle.removeWidget(self.units)
                self.units.parent = None

            if self.first_num:
                self.first_num.hide()
                self.shall_hbox_middle.removeWidget(self.first_num)
                self.first_num.parent = None
                self.second_num.hide()
                self.shall_hbox_middle.removeWidget(self.second_num)
                self.second_num.parent = None
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
                self.tol_num.hide()
                self.shall_hbox_middle.removeWidget(self.tol_num)
                self.tol_num.parent = None

            if self.range_label:
                self.range_label.hide()
                self.shall_hbox_middle.removeWidget(self.range_label)
                self.range_label.parent = None
                self.num2.hide()
                self.shall_hbox_middle.removeWidget(self.num2)
                self.num2.parent = None

            # remove from bottom hbox
            self.text_box3.hide()
            self.shall_hbox_bottom.removeWidget(self.text_box3)
            self.text_box3.parent = None

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
            self.rationale.hide()
            self.rationale_layout.removeWidget(self.rationale)
            self.rationale.parent = None
            layout.removeItem(self.rationale_layout)
            self.rationale_layout.parent = None
            self.preview_button.hide()
            self.preview_form.removeWidget(self.preview_button)
            self.preview_button.parent = None
            self.preview_label.hide()
            self.preview_form.removeWidget(self.preview_label)
            self.preview_label.parent = None
            layout.removeItem(self.preview_form)
            self.preview_form.parent = None

        self.setTitle('Shall Construction and Rationale')
        self.setSubTitle('Construct the shall statement using the instructions'
                    ' below, and then provide the requirements rationale...')

        # different shall cb options
        shall_general = ['shall', 'shall be', 'shall have']
        max_shall = ['less than', 'not exceed', 'at most', 'maximum of']
        min_shall = ['greater than', 'more than', 'at least', 'minimum of']

        # button with label to access instructions
        inst_button = QPushButton('Instructions')
        inst_button.clicked.connect(self.instructions)
        inst_button.setMaximumSize(150,35)
        inst_label = QLabel('View Instructions:')
        self.inst_form = QFormLayout()
        self.inst_form.addRow(inst_label, inst_button)

        # gets the type from the previous page, tells if the type is max, min,
        # single, or range value(s)
        num_type = req_wizard_state.get('val_type')

        # sets the list of options for
        # the combobox. This has the max_shall
        # or min_shall if it is a maximum or
        # minimum value type and it will be
        # none if it is single value or range.
        shall_cb_options = None
        if num_type == 'maximum':
            shall_cb_options = max_shall
        elif num_type == 'minimum':
            shall_cb_options = min_shall

        # shall type combobox
        self.t_shall = None
        self.shall_cb = QComboBox()
        for shall in shall_general:
            self.shall_cb.addItem(shall)

        # fill in the shall
        if num_type == 'maximum' or num_type=='minimum':
            self.t_shall = QComboBox()
            for option in shall_cb_options:
                self.t_shall.addItem(option)
            self.t_shall.currentIndexChanged.connect(self.completeChanged)

        self.shall_cb.setMaximumSize(120, 25)

        if self.t_shall:
            self.t_shall.setMaximumSize(150,25)

        # premade labels text (non-editable labels)
        allocate = req_wizard_state.get('function')
        self.allocate_label = QComboBox()
        self.allocate_label.addItem(allocate)
        self.allocate_label.addItem("The " + allocate)
        self.allocate_label.setMaximumSize(175,25)

        # line edit(s) for number entry
        # TODO: make either one num entry unless it is range then make two.
        doubleValidator = QtGui.QDoubleValidator()
        self.num1 = QLineEdit()
        self.num1.setValidator(doubleValidator)
        self.num1.setPlaceholderText('number')
        self.num1.setMaximumSize(75,25)
        self.num1.textChanged.connect(self.num_entered)
        self.num1.textChanged.connect(self.completeChanged)
        self.num2 = None
        self.range_label = None
        if num_type == 'range':
            self.num2 = QLineEdit()
            self.num2.setValidator(doubleValidator)
            self.num2.setPlaceholderText('number')
            self.num2.setMaximumSize(75, 25)
            self.num2.textChanged.connect(self.num_entered)
            self.num2.textChanged.connect(self.completeChanged)
            self.range_label = QLabel('to')
            self.range_label.setMaximumSize(20, 25)

        self.plus_minus_cb1 = QComboBox()
        self.plus_minus_cb2 = QComboBox()
        self.tolerance = req_wizard_state.get('tolerance')
        self.first_num = None
        self.plus_minus_label = None
        self.tol_num = None
        if self.tolerance:
            if self.tolerance == 'Asymmetric Tolerance':
                plus = '+'
                or_plus = 'or +'
                minus = '-'
                or_minus = ' or -'
                self.plus_minus_cb1.addItem(plus)
                self.plus_minus_cb1.addItem(minus)
                self.plus_minus_cb2.addItem(or_plus)
                self.plus_minus_cb2.addItem(or_minus)
                self.first_num = QLineEdit()
                self.first_num.setValidator(doubleValidator)
                self.first_num.setMaximumSize(50,25)
                self.first_num.textChanged.connect(self.num_entered)
                self.first_num.textChanged.connect(self.completeChanged)
                self.second_num = QLineEdit()
                self.second_num.setValidator(doubleValidator)
                self.second_num.setMaximumSize(50,25)
                self.second_num.textChanged.connect(self.num_entered)
                self.second_num.textChanged.connect(self.completeChanged)

            elif self.tolerance == 'Symmetric Tolerance':
                self.plus_minus_label = QLabel('+/-')
                self.plus_minus_label.setMaximumSize(30,25)
                self.tol_num = QLineEdit()
                self.tol_num.setValidator(doubleValidator)
                self.tol_num.setMaximumSize(75,25)
                self.tol_num.setPlaceholderText('number')
                self.tol_num.textChanged.connect(self.num_entered)
                self.tol_num.textChanged.connect(self.completeChanged)

        # units combo box.
        # TODO: fill in units based on the dimension selected.
        self.units = QComboBox()
        key = req_wizard_state.get('dim')
        units_list = alt_units.get(key, None)
        if units_list:
            for unit in units_list:
                self.units.addItem(unit)
        else:
            self.units.addItem(in_si[key])
        # labels for the overall groups
        # for organization of the page
        shall_label = QLabel('Shall Statement:')
        add_comp_label = QLabel('Additional Shall Statement'
                                            ' Components: ')
        add_comp_label.setMaximumSize(300,25)
        self.rationale_label = QLabel('Rationale: ')

        # lines for spacers inside
        # the widget.
        self.line_top= QHLine()
        self.line_top.setFrameShadow(QFrame.Sunken)
        self.line_middle = QHLine()
        self.line_middle.setFrameShadow(QFrame.Sunken)
        self.line_bottom = QHLine()
        self.line_bottom.setFrameShadow(QFrame.Sunken)

        # rationale plain text edit
        self.rationale = QPlainTextEdit()
        self.rationale.textChanged.connect(self.completeChanged)

        # TODO: populate the shall statement -- this should be tied to a drop
        # event, change of shall type, num entry, and units change

        # Boxes for additional text that are in the shall statement
        self.text_box1 = QLineEdit()
        self.text_box2 = QLineEdit()
        self.text_box3 = QLineEdit()
        text_boxes = [self.text_box1, self.text_box2, self.text_box3]

        # fill sub layouts
        self.shall_hbox_top = QHBoxLayout()
        self.shall_hbox_middle = QHBoxLayout()
        self.shall_hbox_bottom = QHBoxLayout()

        self.shall_vbox = QVBoxLayout()

        # fill grid
        self.shall_hbox_top.addWidget(self.allocate_label)
        self.shall_hbox_top.addWidget(self.text_box1)
        self.shall_hbox_top.addWidget(self.shall_cb)
        self.shall_hbox_middle.addWidget(self.text_box2)
        # if self.t_shall returns true then
        # it is a maximum or a minumum otherwise
        # it is a single value or a range
        if self.t_shall:
            self.shall_hbox_middle.addWidget(self.t_shall)
            self.shall_hbox_bottom.addWidget(self.num1)
            self.shall_hbox_bottom.addWidget(self.units)
        else:
            self.shall_hbox_middle.addWidget(self.num1)
            if self.tolerance == 'Asymmetric Tolerance':
                self.shall_hbox_middle.addWidget(self.plus_minus_cb1)
                self.shall_hbox_middle.addWidget(self.first_num)
                self.shall_hbox_middle.addWidget(self.plus_minus_cb2)
                self.shall_hbox_middle.addWidget(self.second_num)
                self.shall_hbox_middle.addWidget(self.units)
            elif self.tolerance == 'Symmetric Tolerance':
                self.shall_hbox_middle.addWidget(self.plus_minus_label)
                self.shall_hbox_middle.addWidget(self.tol_num)
                self.shall_hbox_middle.addWidget(self.units)

            elif self.num2:
                self.shall_hbox_middle.addWidget(self.range_label)
                self.shall_hbox_middle.addWidget(self.num2)
                self.shall_hbox_middle.addWidget(self.units)

        self.shall_hbox_bottom.addWidget(self.text_box3)

        for box in text_boxes:
            box.setStyleSheet("QLineEdit {background-color: #EEEEEE}")
            box.setReadOnly(True)
            box.setContextMenuPolicy(Qt.CustomContextMenu)
            box.customContextMenuRequested.connect(self.contextMenu)
            box.setPlaceholderText("right click to add text")
            box.textChanged.connect(self.completeChanged)

        # fill vbox
        self.shall_vbox.addWidget(shall_label)
        self.shall_vbox.addLayout(self.shall_hbox_top)
        self.shall_vbox.addLayout(self.shall_hbox_middle)
        self.shall_vbox.addLayout(self.shall_hbox_bottom)
        self.shall_vbox.setContentsMargins(0,40,0,40)

        # rationale layout
        self.rationale_layout = QHBoxLayout()
        self.rationale_layout.addWidget(self.rationale_label)
        self.rationale_layout.addWidget(self.rationale)
        self.rationale_layout.setContentsMargins(0,40,0,40)

        # button with label to access instructions
        self.preview_button = QPushButton('preview')
        self.preview_button.clicked.connect(self.preview)
        self.preview_button.setMaximumSize(150,35)
        self.preview_label = QLabel('Preview Shall Statement and Rationale:')
        self.preview_form = QFormLayout()
        self.preview_form.addRow(self.preview_label, self.preview_button)

        # fill the page, main layout
        layout.addLayout(self.inst_form)
        layout.addWidget(self.line_top)
        layout.addLayout(self.shall_vbox)
        layout.addWidget(self.line_bottom)
        layout.addLayout(self.rationale_layout)
        layout.addLayout(self.preview_form)

    def num_entered(self):
        req_wizard_state['num1'] = self.num1.text()
        if self.num2:
            req_wizard_state['num2'] = self.num2.text()
        if self.first_num:
            req_wizard_state['first_num'] = self.first_num.text()
            req_wizard_state['second_num'] = self.second_num.text()
        if self.tol_num:
            req_wizard_state['tol_num'] = self.tol_num.text()


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
        self.selected_widget.textChanged.connect(self.completeChanged)
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

                if (w != self.text_box3 and w != self.units and
                        w != self.plus_minus_cb1 and w != self.plus_minus_cb2
                        and w != self.plus_minus_label):
                    shall_prev += ' '
        shall_prev += '.'
        if req_wizard_state.get('shall') and req_wizard_state.get('rationale'):
            shall_rat = "Shall Statement: \n" + req_wizard_state['shall']
            shall_rat +="\n Rationale: \n" + req_wizard_state['rationale']
        else:
            shall_rat = "Shall statement and rationale have not been entered."
        QMessageBox.question(self, 'preview', shall_rat, QMessageBox.Ok)

    def isComplete(self):
        """
        Check that num, rationale, and all added text are filled.  Make shall
        nested for loop to go through the different entries.  In the shall use
        columnCount and rowCount.
        """
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
                if hasattr(w, 'currentText'):
                    req_wizard_state['shall'] += w.currentText()
                elif w == self.plus_minus_label or w == self.range_label:
                    req_wizard_state['shall'] += w.text()
                elif not w.isReadOnly():
                    req_wizard_state['shall'] += w.text()

                if (w != self.text_box3 and w != self.units and
                        w != self.plus_minus_cb1 and w != self.plus_minus_cb2
                        and w != self.plus_minus_label):
                    req_wizard_state['shall'] += ' '
        if req_wizard_state['shall'] == '':
            return False
        req_wizard_state['shall'] += '.'
        req_wizard_state['rationale'] = self.rationale.toPlainText()
        if not req_wizard_state['rationale']:
            return False
        # TODO: get the project
        # assign description and rationale
        requirement = orb.get(req_wizard_state.get('req_oid'))
        requirement.description = req_wizard_state['shall']
        requirement.rationale = req_wizard_state['rationale']
        if not req_wizard_state.get('num1'):
            return False
        if self.first_num:
            if (not req_wizard_state.get('first_num') or
                    not req_wizard_state.get('second_num')):
                return False
        if self.tol_num:
            if not req_wizard_state.get('tol_num'):
                return False
        if self.num2:
            if not req_wizard_state.get('num2'):
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
        up_layout = QHBoxLayout()
        bottom_layout = QHBoxLayout()
        up_layout.addWidget(upper_left_cb)
        up_layout.addWidget(subtraction_label)
        up_layout.addWidget(upper_right_cb)
        bottom_layout.addWidget(bottom_left_cb)
        bottom_layout.addWidget(mult_label)
        bottom_layout.addWidget(bottom_right_cb)
        self.layout = self.layout()
        self.layout.setSpacing(20)
        self.layout.addLayout(up_layout)
        self.layout.addWidget(line)
        self.layout.addLayout(bottom_layout)

    def isComplete(self):
        return True

class QHLine(QFrame):
    def __init__(self):
        super(QHLine, self).__init__()
        self.setFrameShape(QFrame.HLine)

