"""
Interface to the "42" Attitude Control System modeling application
"""
import sys

from PyQt5.QtCore import Qt, QSize, QVariant
from PyQt5.QtWidgets import (QApplication, QComboBox, QDialog, QFormLayout,
                             QFrame, QMainWindow, QHBoxLayout, QVBoxLayout,
                             QLabel, QScrollArea, QSizePolicy, QWidget)

from pangalactic.core.uberorb     import orb
from pangalactic.node.widgets     import NameLabel
from pangalactic.node.widgets     import (FloatFieldWidget, IntegerFieldWidget,
                                          StringFieldWidget)


object_types = ['body', 'joint', 'wheel', 'mtb', 'thruster', 'gyro',
                'magnetometer', 'css', 'fss', 'st', 'gps', 'accelerometer']

If42_SC = dict(
  file_section=dict(
    label="42: Spacecraft Description File",
    heading=(
"<<<<<<<<<<<<<<<<<  42: Spacecraft Description File   >>>>>>>>>>>>>>>>>"),
    fields=dict(
      description=dict(label="Description", value="Simple generic S/C",
                        datatype='str'),
      label=dict(label="Label", value='\"S/C\"', datatype='str'),
      sprite_fn=dict(label="Sprite File Name", value="GenScSpriteAlpha.ppm",
                        datatype='str'),
      fsw_id=dict(label="Flight Software Identifier", value="PROTOTYPE_FSW",
                        datatype='str'),
      fsw_sample_t=dict(label="FSW Sample Time, sec", value="0.2",
                        datatype='float'))),
  orbit_parameters_section=dict(
    label="Orbit Parameters",
    heading=(
"************************* Orbit Parameters ****************************"),
    fields=dict(
      orbit=dict(label="Orbit Prop FIXED, EULER_HILL, ENCKE, or COWELL",
                 value="FIXED", datatype='str',
                 selections=["FIXED", "EULER_HILL", "ENCKE", "COWELL"]),
      pos_of=dict(label="Pos of CM or ORIGIN, wrt F", value="CM",
                  datatype='str', selections=["CM", "ORIGIN"]),
      position=dict(label="Pos wrt Formation (m), expressed in F",
                    value=[0.0, 0.0, 0.0], datatype='array'),
      velocity=dict(label="Vel wrt Formation (m/s), expressed in F",
                    value=[0.0, 0.0, 0.0], datatype='array'))),
  initial_attitude_section=dict(
    label="Initial Attitude",
    heading=(
"*************************** Initial Attitude ***************************"),
    fields=dict(
      ang_vel_att_wrt=dict(label="Ang Vel wrt [NL], Att [QA] wrt [NLF]",
                           value="NAN", datatype='str'),
      omega=dict(label="Ang Vel (deg/sec)",
                 value=[0.6, 0.5, 1.0], datatype='array'),
      quaternion=dict(label="Quaternion",
                      value=[0.0, 0.0, 0.0, 1.0], datatype='array'),
      angles=dict(label="Angles (deg) & Euler Sequence",
                  value=[60.0, 50.0, 40.0, 213], datatype='array'))),
  dynamics_flags_section=dict(
    label="Dynamics Flags",
    heading=(
"***************************  Dynamics Flags  ***************************"),
    fields=dict(
      rotation=dict(label="Rotation STEADY, KIN_JOINT, or DYN_JOINT",
                 value="DYN_JOINT", datatype='str',
                 selections=["STEADY", "KIN_JOINT", "DYN_JOINT"]),
      joint_forces=dict(label="Passive Joint Forces and Torques Enabled",
                 value="FALSE", datatype='str', selections=["TRUE", "FALSE"]),
      compute_forces=dict(label="Compute Constraint Forces and Torques",
                 value="FALSE", datatype='str', selections=["TRUE", "FALSE"]),
      mass_props=dict(label="Mass Props referenced to REFPT_CM or REFPT_JOINT",
                 value="REFPT_CM", datatype='str',
                 selections=["REFPT_CM", "REFPT_JOINT"]),
      flex_active=dict(label="Flex Active",
                 value="FALSE", datatype='str', selections=["TRUE", "FALSE"]),
      include_2nd_order=dict(label="Include 2nd Order Flex Terms",
                 value="FALSE", datatype='str', selections=["TRUE", "FALSE"]),
      drag_coefficient=dict(label="Drag Coefficient", value=2.0,
                            datatype='float'))),
  body=dict(
    label="Body Parameters",
    heading=(
"""************************************************************************
************************* Body Parameters ******************************
************************************************************************"""),
    fields=dict(
      number_of_bodies=dict(label="Number of Bodies", value=1,
                            datatype='int',
                            selections=["0", "1", "2", "3", "4", "5", "6", "7",
                                        "8", "9"]),
      )),
  joint=dict(
    label = ("Joint Parameters "
             "(Number of Joints is Number of Bodies minus one)"),
    heading=(
"""************************************************************************
*************************** Joint Parameters ***************************
************************************************************************
         (Number of Joints is Number of Bodies minus one)"""),
    fields={}),
  wheel=dict(
    label="Wheel Parameters",
    heading=(
"*************************** Wheel Parameters ***************************"),
    fields=dict(
      number_of_wheels=dict(label="Number of wheels", value=0,
                            datatype='int',
                            selections=["0", "1", "2", "3", "4", "5", "6", "7",
                                        "8", "9"]),
      )),
  mtb=dict(
    label="MTB Parameters",
    heading=(
"*************************** MTB Parameters ****************************"),
    fields=dict(
      number_of_mtbs=dict(label="Number of MTBs", value=0,
                          datatype='int',
                          selections=["0", "1", "2", "3", "4", "5", "6", "7",
                                        "8", "9"]),
      )),
  thruster=dict(
    label="Thruster Parameters",
    heading=(
"************************* Thruster Parameters **************************"),
    fields=dict(
      number_of_thrusters=dict(label="Number of Thrusters", value=0,
                               datatype='int',
                               selections=["0", "1", "2", "3", "4", "5", "6",
                                           "7", "8", "9"]),
      )),
  gyro=dict(
    label="Gyro",
    heading=(
"******************************* Gyro ************************************"),
    fields=dict(
      number_of_gyro_axes=dict(label="Number of Gyro Axes", value=0,
                               datatype='int',
                               selections=["0", "1", "2", "3", "4", "5", "6",
                                           "7", "8", "9"]),
      )),
  magnetometer=dict(
    label="Magnetometer",
    heading=(
"*************************** Magnetometer ********************************"),
    fields=dict(
      number_of_magnetometer_axes=dict(label="Number of Magnetometer Axes",
                               value=0, datatype='int',
                               selections=["0", "1", "2", "3", "4", "5", "6",
                                           "7", "8", "9"]),
      )),
  css=dict(
    label="Coarse Sun Sensor",
    heading=(
"*********************** Coarse Sun Sensor *******************************"),
    fields=dict(
      number_of_css=dict(label="Number of Coarse Sun Sensors",
                         value=0, datatype='int',
                         selections=["0", "1", "2", "3", "4", "5", "6",
                                     "7", "8", "9"]),
      )),
  fss=dict(
    label="Fine Sun Sensor",
    heading=(
"************************* Fine Sun Sensor *******************************"),
    fields=dict(
      number_of_css=dict(label="Number of Fine Sun Sensors",
                         value=0, datatype='int',
                         selections=["0", "1", "2", "3", "4", "5", "6",
                                     "7", "8", "9"]),
      )),
  st=dict(
    label="Star Tracker",
    heading=(
"************************** Star Tracker *********************************"),
    fields=dict(
      number_of_css=dict(label="Number of Star Trackers",
                         value=0, datatype='int',
                         selections=["0", "1", "2", "3", "4", "5", "6",
                                     "7", "8", "9"]),
      )),
  gps=dict(
    label="GPS",
    heading=(
"****************************** GPS **************************************"),
    fields=dict(
      number_of_css=dict(label="Number of GPS Receivers",
                         value=0, datatype='int',
                         selections=["0", "1", "2", "3", "4", "5", "6",
                                     "7", "8", "9"]),
      )),
  accelerometer=dict(
    label="Accelerometer",
    heading=(
"*************************** Accelerometer *******************************"),
    fields=dict(
      number_of_css=dict(label="Number of Accel Axes",
                         value=0, datatype='int',
                         selections=["0", "1", "2", "3", "4", "5", "6",
                                     "7", "8", "9"]),
      )))


def get_object_parameters(object_type, n):
    """
    Get the parameter data structures for the specified object type and index.
    """
    if object_type == 'body':
        return dict(
        label=f"Body {n}",
        heading=(
f"================================ Body {n} ================================"),
        fields=dict(
          mass=dict(label="Mass", value="100.0", datatype='float'),
          I=dict(label="Moments of Inertia (kg-m^2)",
                 value=[100.0, 200.0, 300.0], datatype='array'),
          PoI=dict(label="Products of Inertia (xy,xz,yz)",
                 value=[0.0, 0.0, 0.0], datatype='array'),
          CoM=dict(label="Location of mass center, m",
                 value=[0.0, 0.0, 0.0], datatype='array'),
          momentum=dict(label="Constant Embedded Momentum (Nms)",
                 value=[0.0, 0.0, 0.0], datatype='array'),
          geom_fname=dict(label="Geometry Input File Name",
                 value="IonCruiser.obj", datatype='str'),
          flex_fname=dict(label="Flex File Name",
                 value="NONE", datatype='str')))
    elif object_type == 'joint':
        name="Joint"
        s1 = "============================== "
        s2 = " ================================"
        return dict(
        label=f"{name} {n}",
        heading=(s1 + f"{name} {n}" + s2),
        fields=dict(
          inner_outer=dict(label="Inner, outer body indices",
                 value=[0, 1], datatype='array'),
          rot_dof=dict(label="RotDOF, Seq, GIMBAL or SPHERICAL",
                 value=[1, 213, "GIMBAL"], datatype='array'),
          trn_dof=dict(label="TrnDOF, Seq",
                 value=[0, 123], datatype='array'),
          rot_dof_locked=dict(label="RotDOF Locked",
                 value=["FALSE", "FALSE", "FALSE"], datatype='array'),
          trn_dof_locked=dict(label="TrnDOF Locked",
                 value=["FALSE", "FALSE", "FALSE"], datatype='array'),
          initial_angles=dict(label="Initial Angles [deg]",
                      value=[0.0, 0.0, 0.0], datatype='array'),
          initial_rates=dict(label="Initial Rates, deg/sec",
                      value=[0.0, 0.0, 0.0], datatype='array'),
          initial_displ=dict(label="Initial Displacements [m]",
                      value=[0.0, 0.0, 0.0], datatype='array'),
          initial_displ_rates=dict(label="Initial Displacement Rates, m/sec",
                      value=[0.0, 0.0, 0.0], datatype='array'),
          bi_to_gi=dict(label="Bi to Gi Static Angles [deg] & Seq",
                      value=[0.0, 0.0, 0.0, 312], datatype='array'),
          go_to_bo=dict(label="Go to Bo Static Angles [deg] & Seq",
                      value=[0.0, 0.0, 0.0, 312], datatype='array'),
          pos_wrt_inner=dict(label="Position wrt inner body origin, m",
                      value=[0.0, 0.0, 0.0], datatype='array'),
          pos_wrt_outer=dict(label="Position wrt outer body origin, m",
                      value=[0.0, 0.0, 0.0], datatype='array'),
          rot_spring=dict(label="Rot Passive Spring Coefficients (Nm/rad)",
                      value=[0.0, 0.0, 0.0], datatype='array'),
          rot_damping=dict(label="Rot Passive Damping Coefficients (Nms/rad)",
                      value=[0.0, 0.0, 0.0], datatype='array'),
          trn_spring=dict(label="Trn Passive Spring Coefficients (N/m)",
                      value=[0.0, 0.0, 0.0], datatype='array'),
          trn_damping=dict(label="Trn Passive Damping Coefficients (Ns/m)",
                      value=[0.0, 0.0, 0.0], datatype='array')))
    elif object_type == 'wheel':
        name = "Wheel"
        s1 = "=============================  "
        s2 = "  ================================"
        return dict(
        label=f"{name} {n}",
        heading=(s1 + f"{name} {n}" + s2),
        fields=dict(
          init_momentum=dict(label="Initial Momentum, N-m-sec",
                value=0.0, datatype='float'),
          wheel_axis_comps=dict(label="Wheel Axis Components, [X, Y, Z]",
                value=[1.0, 0.0, 0.0], datatype='array'),
          max_torque_momentum=dict(
                label="Max Torque (N-m), Momentum (N-m-sec)",
                value=[0.14, 50.0], datatype='array'),
          wheel_rotor_inertia=dict(label="Wheel Rotor Inertia, kg-m^2",
                 value=0.012, datatype='float'),
          static_imbalance=dict(label="Static Imbalance, g-cm",
                 value=0.48, datatype='float'),
          dynamic_imbalance=dict(label="Dynamic Imbalance, g-cm^2",
                 value=13.7, datatype='float'),
          flex_node_index=dict(label="Flex Node Index",
                      value=0, datatype='int')))
    elif object_type == 'mtb':
        name = "MTB"
        s1 = "==============================  "
        s2 = "  ================================="
        return dict(
        label=f"{name} {n}",
        heading=(s1 + f"{name} {n}" + s2),
        fields=dict(
          saturation=dict(label="Saturation (A-m^2)",
                value=100.0, datatype='float'),
          mtb_axis_comps=dict(label="MTB Axis Components, [X, Y, Z]",
                value=[1.0, 0.0, 0.0], datatype='array'),
          flex_node_index=dict(label="Flex Node Index",
                value=0, datatype='int')))
    elif object_type == 'thruster':
        full_name = "Thruster"
        name = "Thr"
        s1 = "==============================  "
        s2 = "  ================================="
        return dict(
        label=f"{full_name} {n}",
        heading=(s1 + f"{name} {n}" + s2),
        fields=dict(
          thrust_force=dict(label="Thrust Force (N)",
                value=1.0, datatype='float'),
          body_thrust_axis=dict(label="Body, Thrust Axis",
                value=[0, -1.0, 0.0, 0.0], datatype='array'),
          location_in_body=dict(label="Location in Body, m",
                value=[1.0, 1.0, 1.0], datatype='array'),
          flex_node_index=dict(label="Flex Node Index",
                      value=0, datatype='int')))
    elif object_type == 'gyro':
        full_name = "Gyro Axis"
        name = "Axis"
        s1 = "============================== "
        s2 = " ==================================="
        return dict(
        label=f"{full_name} {n}",
        heading=(s1 + f"{name} {n}" + s2),
        fields=dict(
          sample_time=dict(label="Sample Time,sec",
                value=0.1, datatype='float'),
          axis_in_body=dict(label="Axis expressed in Body Frame",
                value=[1.0, 0.0, 0.0], datatype='array'),
          max_rate=dict(label="Max Rate, deg/sec",
                value=1000.0, datatype='float'),
          scale_factor_error=dict(label="Scale Factor Error, ppm",
                value=100.0, datatype='float'),
          quantization=dict(label="Quantization, arcsec",
                value=100.0, datatype='float'),
          angle_random_walk=dict(label="Angle Random Walk (deg/rt-hr)",
                value=0.07, datatype='float'),
          bias_stability=dict(
                label="Bias Stability (deg/hr) over timespan (hr)",
                value=[0.1, 1.0], datatype='array'),
          angle_noise=dict(label="Angle Noise, arcsec RMS",
                value=0.1, datatype='float'),
          initial_bias=dict(label="Initial Bias (deg/hr)",
                value=0.1, datatype='float'),
          flex_node_index=dict(label="Flex Node Index",
                      value=0, datatype='int')))
    elif object_type == 'magnetometer':
        full_name = "Magnetometer Axis"
        name = "Axis"
        s1 = "============================== "
        s2 = " ==================================="
        return dict(
        label=f"{full_name} {n}",
        heading=(s1 + f"{name} {n}" + s2),
        fields=dict(
          sample_time=dict(label="Sample Time,sec",
                value=0.1, datatype='float'),
          axis_in_body=dict(label="Axis expressed in Body Frame",
                value=[1.0, 0.0, 0.0], datatype='array'),
          saturation=dict(label="Saturation, Tesla",
                value=60.0E-6, datatype='float'),
          scale_factor_error=dict(label="Scale Factor Error, ppm",
                value=0.0, datatype='float'),
          quantization=dict(label="Quantization, Tesla",
                value=1.0E-6, datatype='float'),
          noise=dict(label="Noise, Tesla RMS",
                value=1.0E-6, datatype='float'),
          flex_node_index=dict(label="Flex Node Index",
                      value=0, datatype='int')))
    elif object_type == 'css':
        full_name = "Coarse Sun Sensor"
        name = "CSS"
        s1 = "============================== "
        s2 = " ===================================="
        return dict(
        label=f"{full_name} {n}",
        heading=(s1 + f"{name} {n}" + s2),
        fields=dict(
          sample_time=dict(label="Sample Time,sec",
                value=0.1, datatype='float'),
          body_axis_in_body=dict(label="Body, Axis expressed in Body Frame",
                value=[0, 1.0, 1.0, 1.0], datatype='array'),
          half_cone_angle=dict(label="Half-cone Angle, deg",
                value=90.0, datatype='float'),
          scale_factor=dict(label="Scale Factor",
                value=1.0, datatype='float'),
          quantization=dict(label="Quantization",
                value=0.001, datatype='float'),
          flex_node_index=dict(label="Flex Node Index",
                      value=0, datatype='int')))
    elif object_type == 'fss':
        full_name = "Fine Sun Sensor"
        name = "FSS"
        s1 = "=============================== "
        s2 = " ==================================="
        return dict(
        label=f"{full_name} {n}",
        heading=(s1 + f"{name} {n}" + s2),
        fields=dict(
          sample_time=dict(label="Sample Time,sec",
                value=0.1, datatype='float'),
          mounting_angles_seq=dict(label="Mounting Angles (deg), Seq in Body",
                value=[70.0, 0.0, 0.0, 231], datatype='array'),
          fov_size=dict(label="X, Y FOV Size, deg",
                value=[32.0, 32.0], datatype='array'),
          noise_equiv_angle=dict(label="Noise Equivalent Angle, deg RMS",
                value=0.1, datatype='float'),
          quantization=dict(label="Quantization, deg",
                value=0.5, datatype='float'),
          flex_node_index=dict(label="Flex Node Index",
                      value=0, datatype='int')))
    elif object_type == 'fss':
        full_name = "Star Tracker"
        name = "ST"
        s1 = "=============================== "
        s2 = " ===================================="
        return dict(
        label=f"{full_name} {n}",
        heading=(s1 + f"{name} {n}" + s2),
        fields=dict(
          sample_time=dict(label="Sample Time,sec",
                value=0.25, datatype='float'),
          mounting_angles_seq=dict(label="Mounting Angles (deg), Seq in Body",
                value=[-90.0, 90.0, 00.0, 321], datatype='array'),
          fov_size=dict(label="X, Y FOV Size, deg",
                value=[8.0, 8.0], datatype='array'),
          sun_earth_moon_excl_angles=dict(
                label="Sun, Earth, Moon Exclusion Angles, deg",
                value=[30.0, 10.0, 10.0], datatype='array'),
          noise_equiv_angle=dict(label="Noise Equivalent Angle, arcsec RMS",
                value=[2.0, 2.0, 20.0], datatype='array'),
          flex_node_index=dict(label="Flex Node Index",
                      value=1, datatype='int')))
    elif object_type == 'gps':
        name = "GPSR"
        s1 = "============================= "
        s2 = " ===================================="
        return dict(
        label=f"{name} {n}",
        heading=(s1 + f"{name} {n}" + s2),
        fields=dict(
          sample_time=dict(label="Sample Time,sec",
                value=0.25, datatype='float'),
          position_noise=dict(label="Position Noise, m RMS",
                value=4.0, datatype='float'),
          velocity_noise=dict(label="Velocity Noise, m/sec RMS",
                value=0.02, datatype='float'),
          time_noise=dict(label="Time Noise, sec RMS",
                value=20.0E-9, datatype='float'),
          flex_node_index=dict(label="Flex Node Index",
                      value=0, datatype='int')))
    elif object_type == 'accelerometer':
        full_name = "Accelerometer Axis"
        name = "Axis"
        s1 = "============================== "
        s2 = " ==================================="
        return dict(
        label=f"{full_name} {n}",
        heading=(s1 + f"{name} {n}" + s2),
        fields=dict(
          sample_time=dict(label="Sample Time,sec",
                value=0.1, datatype='float'),
          position_in_b=dict(label="Position in B[0] (m)",
                      value=[0.5, 1.0, 1.5], datatype='array'),
          axis_in_body_frame=dict(label="Axis expressed in Body Frame",
                      value=[1.0, 0.0, 0.0], datatype='array'),
          max_acceleration=dict(label="Max Acceleration (m/s^2)",
                value=1.0, datatype='float'),
          scale_factor_error=dict(label="Scale Factor Error, ppm",
                value=0.0, datatype='float'),
          quantization=dict(label="Quantization, m/s^2",
                value=0.05, datatype='float'),
          dv_random_walk=dict(label="DV Random Walk (m/s/rt-hr)",
                value=0.0, datatype='float'),
          bias_stability=dict(
                label="Bias Stability (m/s^2) over timespan (hr)",
                value=[0.0, 1.0], datatype='array'),
          dv_noise=dict(label="DV Noise, m/s",
                value=0.0, datatype='float'),
          initial_bias=dict(label="Initial Bias (m/s^2)",
                value=0.5, datatype='float'),
          flex_node_index=dict(label="Flex Node Index",
                      value=0, datatype='int')))


class If42Forms(QWidget):
    """
    A widget that provides forms for the specification of a 42 model, with the
    initial goal of generating the input files to 42.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.form = QFormLayout()
        self.form.setFieldGrowthPolicy(self.form.FieldsStayAtSizeHint)
        self.setLayout(self.form)
        self.widgets = {}
        for section, props in If42_SC.items():
            section_label = QLabel(props.get('label', 'missing label'), self)
            section_label.setTextFormat(Qt.RichText)
            section_label.setStyleSheet("QLabel {font-size: 16px;"
                                        "font-weight: bold; color: purple}")
            section_label.setFrameStyle(QFrame.Box | QFrame.Plain)
            section_label.setLineWidth(1)
            self.widgets[section] = {}
            self.widgets[section]['section_label'] = section_label
            self.widgets[section]['widgets'] = {}
            self.form.addRow(section_label)
            for field, field_props in props['fields'].items():
                field_label_text = field_props.get('label', '[missing label]')
                field_label = NameLabel(field_label_text)
                field_label.setTextFormat(Qt.RichText)
                field_label.setStyleSheet("QLabel {font-size: 14px;"
                                          "font-weight: bold}")
                if field_props['datatype'] == 'array':
                    # if array-valued, add an hbox to contain the sub-fields
                    hbox = QHBoxLayout()
                    widgets = []
                    for i in range(len(field_props['value'])):
                        w = StringFieldWidget(parent=self, width=80)
                        widgets.append(w)
                        hbox.addWidget(w)
                    self.form.addRow(field_label, hbox)
                else:
                    if field_props.get('selections'):
                        widget = QComboBox()
                        for val in field_props['selections']:
                            widget.addItem(val, QVariant())
                        # TODO: a more elegant way of identifying "Number of"
                        if section in object_types:
                            # special case for model "component" sections
                            # TODO: add a button for each component of this
                            # type, which will bring up a ParameterDialog
                            # object_type = props.get('object_type', 'unknown')
                            widget.object_type = section
                            widget.activated.connect(
                                                self.set_number_of_components)
                        else:
                            widget.activated.connect(self.set_selection)
                    else:
                        if field_props.get('datatype') in ['float', 'int']:
                            widget = StringFieldWidget(parent=self, width=80)
                        elif field_props.get('datatype') == 'str':
                            widget = StringFieldWidget(parent=self, width=200)
                    self.form.addRow(field_label, widget)
            # if props.get('object_type'):
            if section in object_types:
                self.widgets[section]

    def set_number_of_components(self, evt):
        widget = self.sender()
        if hasattr(widget, 'object_type'):
            number = int(widget.currentText())
            print(f'object type to set number of: {widget.object_type}')
            print(f'number: {number}')
        else:
            print('could not determine sender.')

    def set_selection(self, evt):
        pass


class ParameterDialog(QDialog):
    """
    Dialog to display a form for specifying the parameters of an object in a 42
    model.

    Args:
        object_type (str): type of object -- the initial set of "object types"
            are:  body, joint, wheel, mtb, thruster, gyro, magnetometer, css,
            fss, st, gps, and accelerometer.
        n (int): in a model containing multiple instances of the specified
            object type, the index of the object whose parameters are to be
            specified
    """
    def __init__(self, object_type, n, parent=None):
        super().__init__(parent=parent)
        section = get_object_parameters(object_type, n)
        form = QFormLayout()
        form.setFieldGrowthPolicy(form.FieldsStayAtSizeHint)
        self.setLayout(form)
        self.widgets = {}
        section_label = QLabel(section.get('label', 'missing label'), self)
        section_label.setTextFormat(Qt.RichText)
        section_label.setStyleSheet("QLabel {font-size: 16px;"
                                    "font-weight: bold; color: purple}")
        section_label.setFrameStyle(QFrame.Box | QFrame.Plain)
        section_label.setLineWidth(1)
        self.widgets = {}
        self.widgets['section_label'] = section_label
        self.widgets['widgets'] = {}
        form.addRow(section_label)
        for field, field_props in section['fields'].items():
            txt = field_props.get('label', '[missing label]')
            field_label = NameLabel(txt)
            field_label.setTextFormat(Qt.RichText)
            field_label.setStyleSheet("QLabel {font-size: 14px;"
                                      "font-weight: bold}")
            if field_props['datatype'] == 'array':
                # if array-valued, add an hbox to contain the sub-fields
                hbox = QHBoxLayout()
                widgets = []
                for i in range(len(field_props['value'])):
                    w = StringFieldWidget(parent=self, width=80)
                    widgets.append(w)
                    hbox.addWidget(w)
                form.addRow(field_label, hbox)
            else:
                if field_props.get('selections'):
                    widget = QComboBox()
                    widget.activated.connect(self.set_selection)
                    for val in field_props['selections']:
                        widget.addItem(val, QVariant())
                else:
                    widget = StringFieldWidget(parent=self, width=80)
                form.addRow(field_label, widget)

    def set_selection(self, evt):
        pass


class If42Window(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.forms = If42Forms()
        central_layout = QVBoxLayout()
        central_widget = QWidget()
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.forms)
        central_layout.addWidget(self.scroll_area, 1)
        central_widget.setLayout(central_layout)
        self.setCentralWidget(central_widget)

    def sizeHint(self):
        return QSize(850, 900)


if __name__ == '__main__':
    """Script mode for testing."""
    app = QApplication(sys.argv)
    window = If42Window()
    window.show()
    # dlg = ParameterDialog('joint', '0')
    # dlg.show()
    sys.exit(app.exec_())

