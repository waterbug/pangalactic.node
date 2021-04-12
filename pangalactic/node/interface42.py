"""
Interface to the "42" Attitude Control System modeling application
"""
import sys, os
import ruamel_yaml as yaml

from PyQt5.QtCore import Qt, QSize, QVariant
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (QAction, QApplication, QComboBox, QDialog,
                             QFileDialog, QFormLayout, QFrame, QMainWindow,
                             QMenu, QMessageBox, QPushButton, QHBoxLayout,
                             QVBoxLayout, QLabel, QScrollArea, QWidget)

from pangalactic.core             import state
from pangalactic.core.uberorb     import orb
from pangalactic.core.utils.datetimes  import dtstamp, date2str
from pangalactic.node.buttons     import SizedButton
from pangalactic.node.widgets     import NameLabel
from pangalactic.node.widgets     import (FloatFieldWidget, IntegerFieldWidget,
                                          StringFieldWidget)


class FloatParmWidget(FloatFieldWidget):
    """
    Float Parameter input field.  The superclass, FloatFieldWidget, provides an
    input "validator" that forces the field content to be only numeric strings
    that can be coerced to "float" type.

    Keyword Args:
        parent (QWidget): parent widget
        parm_type (str): datatype of the parameter
        value (str): initial value of the field
        section (str): name of the section in the SC data structure
        pid (str): parameter identifier
        i (int): for array-valued parameters, position of this field's value in
            the array
    """
    def __init__(self, parent=None, value=None, section=None, pid='', i=0):
        super().__init__(parent=parent, value=value)
        self.section = section
        self.pid = pid
        self.i = i


class IntParmWidget(IntegerFieldWidget):
    """
    Integer Parameter input field.  The superclass, IntegerFieldWidget,
    provides an input "validator" that forces the field content to be only
    numeric strings that can be coerced to "int" type.

    Keyword Args:
        parent (QWidget): parent widget
        parm_type (str): datatype of the parameter
        value (str): initial value of the field
        section (str): name of the section in the SC data structure
        pid (str): parameter identifier
        i (int): for array-valued parameters, position of this field's value in
            the array
    """
    def __init__(self, parent=None, value=None, section=None, pid='', i=0):
        super().__init__(parent=parent, value=value)
        self.section = section
        self.pid = pid
        self.i = i


class StrParmWidget(StringFieldWidget):
    """
    Parameter field for string-valued (or untyped) parameters.

    Keyword Args:
        parent (QWidget): parent widget
        value (str): initial value of the field
        section (str): name of the section in the SC data structure
        pid (str): parameter identifier
        i (int): for array-valued parameters, position of this field's value in
            the array
    """
    def __init__(self, parent=None, value=None, section=None, pid='', i=0,
                 width=None):
        width = 200
        super().__init__(parent=parent, value=value, parm_type='str',
                         width=width)
        self.section = section
        self.pid = pid
        self.i = i


def get_widget_class(dtype):
    """
    Return the appropriate parameter field for specified datatype.

    Args:
        dtype (str): datatype; if None, 'str' is assumed
    """
    if dtype == 'float':
        return FloatParmWidget
    elif dtype == 'int':
        return IntParmWidget
    return StrParmWidget


class ParmCombo(QComboBox):
    """
    Combo box for parameters with value "selections" specified.

    Keyword Args:
        parent (QWidget): parent widget
        value (str): initial value of the field
        section (str): name of the section in the SC data structure
        parm_type (str): datatype; if None, plain string is assumed; if "float"
            or "int", the appropriate "validator" (mask) will be set so that
            only values coercible to that type can be entered
        pid (str): parameter identifier
        i (int): for array-valued parameters, position of this field's value in
            the array
    """
    def __init__(self, parent=None, value=None, section=None, pid='', i=0,
                 parm_type=None, width=None):
        super().__init__(parent=parent)
        self.section = section
        self.pid = pid
        self.i = i
        self.parm_type = parm_type

    def set_value(self, value):
        try:
            if self.parm_type == 'bool':
                if value in [True, False]:
                    if value:
                        self.setCurrentText('TRUE')
                    else:
                        self.setCurrentText('FALSE')
                else:
                    self.setCurrentText(str(value))

            else:
                self.setCurrentText(str(value))
        except:
            # value not in list
            pass

    def get_value(self):
        return self.currentText()


component_types = ['body', 'joint', 'wheel', 'mtb', 'thruster', 'gyro',
                   'magnetometer', 'css', 'fss', 'st', 'gps', 'accelerometer']

datatypes = {'str': str, 'float': float, 'int': int, 'bool': str}


SC = dict(
   metadata=dict(
      description=dict(label="Description", test="Simple generic S/C",
                        datatype='str'),
      label=dict(label="Label", test='\"S/C\"', datatype='str'),
      sprite_fn=dict(label="Sprite File Name", test="GenScSpriteAlpha.ppm",
                        datatype='str'),
      fsw_id=dict(label="Flight Software Identifier", test="PROTOTYPE_FSW",
                        datatype='str'),
      fsw_sample_t=dict(label="FSW Sample Time, sec", test="0.2",
                        datatype='float')),
  orbit=dict(
      orbit=dict(label="Orbit Prop FIXED, EULER_HILL, ENCKE, or COWELL",
                 test="FIXED", datatype='str',
                 selections=["FIXED", "EULER_HILL", "ENCKE", "COWELL"],
                 default="FIXED"),
      pos_of=dict(label="Pos of CM or ORIGIN, wrt F", test="CM",
                  datatype='str', selections=["CM", "ORIGIN"],
                  default="CM"),
      position=dict(label="Pos wrt Formation (m), expressed in F",
                    test=[0.0, 0.0, 0.0], datatype='array',
                    postypes=['float', 'float', 'float']),
      velocity=dict(label="Vel wrt Formation (m/s), expressed in F",
                    test=[0.0, 0.0, 0.0], datatype='array',
                    postypes=['float', 'float', 'float'])),
  initial_attitude=dict(
      ang_vel_att_wrt=dict(label="Ang Vel wrt [NL], Att [QA] wrt [NLF]",
                           test="NAN", datatype='str'),
      omega=dict(label="Ang Vel (deg/sec)",
                 test=[0.6, 0.5, 1.0], datatype='array',
                 postypes=['float', 'float', 'float']),
      quaternion=dict(label="Quaternion",
                      test=[0.0, 0.0, 0.0, 1.0], datatype='array',
                      postypes=['float', 'float', 'float', 'float']),
      angles=dict(label="Angles (deg) & Euler Sequence",
                  test=[60.0, 50.0, 40.0, 213], datatype='array',
                  postypes=['float', 'float', 'float', 'int'])),
  dynamics_flags=dict(
      rotation=dict(label="Rotation STEADY, KIN_JOINT, or DYN_JOINT",
                 test="DYN_JOINT", datatype='str',
                 selections=["STEADY", "KIN_JOINT", "DYN_JOINT"],
                 default="FIXED"),
      joint_forces=dict(label="Passive Joint Forces and Torques Enabled",
                 test="FALSE", datatype='str', selections=["TRUE", "FALSE"],
                 default="FALSE"),
      compute_forces=dict(label="Compute Constraint Forces and Torques",
                 test="FALSE", datatype='str', selections=["TRUE", "FALSE"]),
      mass_props=dict(label="Mass Props referenced to REFPT_CM or REFPT_JOINT",
                 test="REFPT_CM", datatype='str',
                 selections=["REFPT_CM", "REFPT_JOINT"],
                 default="REFPT_CM"),
      flex_active=dict(label="Flex Active",
                 test="FALSE", datatype='str', selections=["TRUE", "FALSE"],
                 default="FALSE"),
      include_2nd_order=dict(label="Include 2nd Order Flex Terms",
                 test="FALSE", datatype='str', selections=["TRUE", "FALSE"],
                 default="FALSE"),
      drag_coefficient=dict(label="Drag Coefficient", test=2.0,
                            datatype='float')),
  components=dict(
    body=dict(
      mass=dict(label="Mass", test="100.0", datatype='float'),
      I=dict(label="Moments of Inertia (kg-m^2)",
             test=[100.0, 200.0, 300.0], datatype='array',
             postypes=['float', 'float', 'float']),
      PoI=dict(label="Products of Inertia (xy,xz,yz)",
             test=[0.0, 0.0, 0.0], datatype='array',
             postypes=['float', 'float', 'float']),
      CoM=dict(label="Location of mass center, m",
             test=[0.0, 0.0, 0.0], datatype='array',
             postypes=['float', 'float', 'float']),
      momentum=dict(label="Constant Embedded Momentum (Nms)",
             test=[0.0, 0.0, 0.0], datatype='array',
             postypes=['float', 'float', 'float']),
      geom_fname=dict(label="Geometry Input File Name",
             test="IonCruiser.obj", datatype='str'),
      flex_fname=dict(label="Flex File Name",
             test="NONE", datatype='str')),
    joint=dict(
      inner_outer=dict(label="Inner, outer body indices",
             test=[0, 1], datatype='array',
             postypes=['int', 'int']),
      rot_dof=dict(label="RotDOF, Seq, GIMBAL or SPHERICAL",
             test=[1, 213, "GIMBAL"], datatype='array',
             postypes=['int', 'int', 'str']),
      trn_dof=dict(label="TrnDOF, Seq",
             test=[0, 123], datatype='array',
             postypes=['int', 'int']),
      rot_dof_locked=dict(label="RotDOF Locked",
             test=["FALSE", "FALSE", "FALSE"], datatype='array',
             postypes=['bool', 'bool', 'bool']),
      trn_dof_locked=dict(label="TrnDOF Locked",
             test=["FALSE", "FALSE", "FALSE"], datatype='array',
             postypes=['bool', 'bool', 'bool']),
      initial_angles=dict(label="Initial Angles [deg]",
                  test=[0.0, 0.0, 0.0], datatype='array',
                  postypes=['float', 'float', 'float']),
      initial_rates=dict(label="Initial Rates, deg/sec",
                  test=[0.0, 0.0, 0.0], datatype='array',
                  postypes=['float', 'float', 'float']),
      initial_displ=dict(label="Initial Displacements [m]",
                  test=[0.0, 0.0, 0.0], datatype='array',
                  postypes=['float', 'float', 'float']),
      initial_displ_rates=dict(label="Initial Displacement Rates, m/sec",
                  test=[0.0, 0.0, 0.0], datatype='array',
                  postypes=['float', 'float', 'float']),
      bi_to_gi=dict(label="Bi to Gi Static Angles [deg] & Seq",
                  test=[0.0, 0.0, 0.0, 312], datatype='array',
                  postypes=['float', 'float', 'float', 'int']),
      go_to_bo=dict(label="Go to Bo Static Angles [deg] & Seq",
                  test=[0.0, 0.0, 0.0, 312], datatype='array',
                  postypes=['float', 'float', 'float', 'int']),
      pos_wrt_inner=dict(label="Position wrt inner body origin, m",
                  test=[0.0, 0.0, 0.0], datatype='array',
                  postypes=['float', 'float', 'float']),
      pos_wrt_outer=dict(label="Position wrt outer body origin, m",
                  test=[0.0, 0.0, 0.0], datatype='array',
                  postypes=['float', 'float', 'float']),
      rot_spring=dict(label="Rot Passive Spring Coefficients (Nm/rad)",
                  test=[0.0, 0.0, 0.0], datatype='array',
                  postypes=['float', 'float', 'float']),
      rot_damping=dict(label="Rot Passive Damping Coefficients (Nms/rad)",
                  test=[0.0, 0.0, 0.0], datatype='array',
                  postypes=['float', 'float', 'float']),
      trn_spring=dict(label="Trn Passive Spring Coefficients (N/m)",
                  test=[0.0, 0.0, 0.0], datatype='array',
                  postypes=['float', 'float', 'float']),
      trn_damping=dict(label="Trn Passive Damping Coefficients (Ns/m)",
                  test=[0.0, 0.0, 0.0], datatype='array',
                  postypes=['float', 'float', 'float'])),
    wheel=dict(
      init_momentum=dict(label="Initial Momentum, N-m-sec",
            test=0.0, datatype='float'),
      wheel_axis_comps=dict(label="Wheel Axis Components, [X, Y, Z]",
            test=[1.0, 0.0, 0.0], datatype='array',
            postypes=['float', 'float', 'float']),
      max_torque_momentum=dict(
            label="Max Torque (N-m), Momentum (N-m-sec)",
            test=[0.14, 50.0], datatype='array',
            postypes=['float', 'float']),
      wheel_rotor_inertia=dict(label="Wheel Rotor Inertia, kg-m^2",
             test=0.012, datatype='float'),
      static_imbalance=dict(label="Static Imbalance, g-cm",
             test=0.48, datatype='float'),
      dynamic_imbalance=dict(label="Dynamic Imbalance, g-cm^2",
             test=13.7, datatype='float'),
      flex_node_index=dict(label="Flex Node Index",
                  test=0, datatype='int')),
    mtb=dict(
      saturation=dict(label="Saturation (A-m^2)",
            test=100.0, datatype='float'),
      mtb_axis_comps=dict(label="MTB Axis Components, [X, Y, Z]",
            test=[1.0, 0.0, 0.0], datatype='array',
            postypes=['float', 'float', 'float']),
      flex_node_index=dict(label="Flex Node Index",
            test=0, datatype='int')),
    thruster=dict(
      thrust_force=dict(label="Thrust Force (N)",
            test=1.0, datatype='float'),
      body_thrust_axis=dict(label="Body, Thrust Axis",
            test=[0, -1.0, 0.0, 0.0], datatype='array',
            postypes=['int', 'float', 'float', 'float']),
      location_in_body=dict(label="Location in Body, m",
            test=[1.0, 1.0, 1.0], datatype='array',
            postypes=['float', 'float', 'float']),
      flex_node_index=dict(label="Flex Node Index",
                  test=0, datatype='int')),
    gyro=dict(
      sample_time=dict(label="Sample Time,sec",
            test=0.1, datatype='float'),
      axis_in_body=dict(label="Axis expressed in Body Frame",
            test=[1.0, 0.0, 0.0], datatype='array',
            postypes=['float', 'float', 'float']),
      max_rate=dict(label="Max Rate, deg/sec",
            test=1000.0, datatype='float'),
      scale_factor_error=dict(label="Scale Factor Error, ppm",
            test=100.0, datatype='float'),
      quantization=dict(label="Quantization, arcsec",
            test=100.0, datatype='float'),
      angle_random_walk=dict(label="Angle Random Walk (deg/rt-hr)",
            test=0.07, datatype='float'),
      bias_stability=dict(
            label="Bias Stability (deg/hr) over timespan (hr)",
            test=[0.1, 1.0], datatype='array',
            postypes=['float', 'float']),
      angle_noise=dict(label="Angle Noise, arcsec RMS",
            test=0.1, datatype='float'),
      initial_bias=dict(label="Initial Bias (deg/hr)",
            test=0.1, datatype='float'),
      flex_node_index=dict(label="Flex Node Index",
                  test=0, datatype='int')),
    magnetometer=dict(
      sample_time=dict(label="Sample Time,sec",
            test=0.1, datatype='float'),
      axis_in_body=dict(label="Axis expressed in Body Frame",
            test=[1.0, 0.0, 0.0], datatype='array',
            postypes=['float', 'float', 'float']),
      saturation=dict(label="Saturation, Tesla",
            test=60.0E-6, datatype='float'),
      scale_factor_error=dict(label="Scale Factor Error, ppm",
            test=0.0, datatype='float'),
      quantization=dict(label="Quantization, Tesla",
            test=1.0E-6, datatype='float'),
      noise=dict(label="Noise, Tesla RMS",
            test=1.0E-6, datatype='float'),
      flex_node_index=dict(label="Flex Node Index",
                  test=0, datatype='int')),
    css=dict(
      sample_time=dict(label="Sample Time,sec",
            test=0.1, datatype='float'),
      body_axis_in_body=dict(label="Body, Axis expressed in Body Frame",
            test=[0, 1.0, 1.0, 1.0], datatype='array',
            postypes=['int', 'float', 'float', 'float']),
      half_cone_angle=dict(label="Half-cone Angle, deg",
            test=90.0, datatype='float'),
      scale_factor=dict(label="Scale Factor",
            test=1.0, datatype='float'),
      quantization=dict(label="Quantization",
            test=0.001, datatype='float'),
      flex_node_index=dict(label="Flex Node Index",
                  test=0, datatype='int')),
    fss=dict(
      sample_time=dict(label="Sample Time,sec",
            test=0.1, datatype='float'),
      mounting_angles_seq=dict(label="Mounting Angles (deg), Seq in Body",
            test=[70.0, 0.0, 0.0, 231], datatype='array',
            postypes=['float', 'float', 'float', 'int']),
      fov_size=dict(label="X, Y FOV Size, deg",
            test=[32.0, 32.0], datatype='array',
            postypes=['float', 'float']),
      noise_equiv_angle=dict(label="Noise Equivalent Angle, deg RMS",
            test=0.1, datatype='float'),
      quantization=dict(label="Quantization, deg",
            test=0.5, datatype='float'),
      flex_node_index=dict(label="Flex Node Index",
            test=0, datatype='int')),
    st=dict(
      sample_time=dict(label="Sample Time,sec",
            test=0.25, datatype='float'),
      mounting_angles_seq=dict(label="Mounting Angles (deg), Seq in Body",
            test=[-90.0, 90.0, 00.0, 321], datatype='array',
            postypes=['float', 'float', 'float', 'int']),
      fov_size=dict(label="X, Y FOV Size, deg",
            test=[8.0, 8.0], datatype='array',
            postypes=['float', 'float']),
      sun_earth_moon_excl_angles=dict(
            label="Sun, Earth, Moon Exclusion Angles, deg",
            test=[30.0, 10.0, 10.0], datatype='array',
            postypes=['float', 'float', 'float']),
      noise_equiv_angle=dict(label="Noise Equivalent Angle, arcsec RMS",
            test=[2.0, 2.0, 20.0], datatype='array',
            postypes=['float', 'float', 'float']),
      flex_node_index=dict(label="Flex Node Index",
                  test=1, datatype='int')),
    gps=dict(
      sample_time=dict(label="Sample Time,sec",
            test=0.25, datatype='float'),
      position_noise=dict(label="Position Noise, m RMS",
            test=4.0, datatype='float'),
      velocity_noise=dict(label="Velocity Noise, m/sec RMS",
            test=0.02, datatype='float'),
      time_noise=dict(label="Time Noise, sec RMS",
            test=20.0E-9, datatype='float'),
      flex_node_index=dict(label="Flex Node Index",
                  test=0, datatype='int')),
    accelerometer=dict(
      sample_time=dict(label="Sample Time,sec",
            test=0.1, datatype='float'),
      position_in_b=dict(label="Position in B[0] (m)",
            test=[0.5, 1.0, 1.5], datatype='array',
            postypes=['float', 'float', 'float']),
      axis_in_body_frame=dict(label="Axis expressed in Body Frame",
            test=[1.0, 0.0, 0.0], datatype='array',
            postypes=['float', 'float', 'float']),
      max_acceleration=dict(label="Max Acceleration (m/s^2)",
            test=1.0, datatype='float'),
      scale_factor_error=dict(label="Scale Factor Error, ppm",
            test=0.0, datatype='float'),
      quantization=dict(label="Quantization, m/s^2",
            test=0.05, datatype='float'),
      dv_random_walk=dict(label="DV Random Walk (m/s/rt-hr)",
            test=0.0, datatype='float'),
      bias_stability=dict(
            label="Bias Stability (m/s^2) over timespan (hr)",
            test=[0.0, 1.0], datatype='array',
            postypes=['float', 'float']),
      dv_noise=dict(label="DV Noise, m/s",
            test=0.0, datatype='float'),
      initial_bias=dict(label="Initial Bias (m/s^2)",
            test=0.5, datatype='float'),
      flex_node_index=dict(label="Flex Node Index",
            test=0, datatype='int')))
    )


n_bodies_selections = [str(n) for n in range(17)]
n_thrusters_selections = [str(n) for n in range(17)]


SC_File = dict(
  metadata=dict(
    name="Spacecraft",
    label="42: Spacecraft Description File",
    header=(
"<<<<<<<<<<<<<<<<<  42: Spacecraft Description File   >>>>>>>>>>>>>>>>>")),
  orbit=dict(
    name="Orbit",
    label="Orbit Parameters",
    header=(
"************************* Orbit Parameters ****************************")),
  initial_attitude=dict(
    name="Initial Attitude",
    label="Initial Attitude",
    header=(
"*************************** Initial Attitude ***************************")),
  dynamics_flags=dict(
    name="Dynamics Flags",
    label="Dynamics Flags",
    header=(
"***************************  Dynamics Flags  ***************************")),
  body=dict(
    name="Body",
    label="Body Parameters",
    header=(
"""************************************************************************
************************* Body Parameters ******************************
************************************************************************"""),
    number_of=dict(label="Number of Bodies", test=1,
                   datatype='int',
                   selections=n_bodies_selections,
                   default="1")
    ),
  joint=dict(
    name="Joint",
    label = ("Joint Parameters "
             "(Number of Joints is Number of Bodies minus one)"),
    header=(
"""************************************************************************
*************************** Joint Parameters ***************************
************************************************************************
         (Number of Joints is Number of Bodies minus one)"""),
    number_of={},
    ),
  wheel=dict(
    name="Wheel",
    label="Wheel Parameters",
    header=(
"*************************** Wheel Parameters ***************************"),
    number_of=dict(label="Number of wheels", test=1,
                   datatype='int',
                   selections=["0", "1", "2", "3", "4", "5", "6", "7",
                               "8", "9"])
    ),
  mtb=dict(
    name="MTB",
    label="MTB Parameters",
    header=(
"**************************** MTB Parameters ****************************"),
    number_of=dict(label="Number of MTBs", test=1,
                   datatype='int',
                   selections=["0", "1", "2", "3", "4", "5", "6", "7",
                               "8", "9"])
    ),
  thruster=dict(
    name="Thruster",
    label="Thruster Parameters",
    header=(
"************************* Thruster Parameters **************************"),
    number_of=dict(label="Number of Thrusters", test=1,
                   datatype='int',
                   selections=n_thrusters_selections)
    ),
  gyro=dict(
    name="Gyro",
    label="Gyro",
    header=(
"******************************* Gyro ***********************************"),
    number_of=dict(label="Number of Gyro Axes", test=1,
                   datatype='int',
                   selections=["0", "1", "2", "3", "4", "5", "6", "7",
                               "8", "9"])
    ),
  magnetometer=dict(
    name="Magnetometer",
    label="Magnetometer",
    header=(
"*************************** Magnetometer *******************************"),
    number_of=dict(label="Number of Magnetometer Axes", test=1,
                   datatype='int',
                   selections=["0", "1", "2", "3", "4", "5", "6", "7",
                               "8", "9"])
    ),
  css=dict(
    name="Coarse Sun Sensor",
    label="Coarse Sun Sensor",
    header=(
"*********************** Coarse Sun Sensor ******************************"),
    number_of=dict(label="Number of Coarse Sun Sensors", test=1,
                   datatype='int',
                   selections=["0", "1", "2", "3", "4", "5", "6", "7",
                               "8", "9"])
    ),
  fss=dict(
    name="Fine Sun Sensor",
    label="Fine Sun Sensor",
    header=(
"************************* Fine Sun Sensor ******************************"),
    number_of=dict(label="Number of Fine Sun Sensors", test=1,
                   datatype='int',
                   selections=["0", "1", "2", "3", "4", "5", "6", "7",
                               "8", "9"])
    ),
  st=dict(
    name="Star Tracker",
    label="Star Tracker",
    header=(
"************************** Star Tracker ********************************"),
    number_of=dict(label="Number of Star Trackers", test=1,
                   datatype='int',
                   selections=["0", "1", "2", "3", "4", "5", "6", "7",
                               "8", "9"])
    ),
  gps=dict(
    name="GPS",
    label="GPS",
    header=(
"****************************** GPS *************************************"),
    number_of=dict(label="Number of GPS Receivers", test=1,
                   datatype='int',
                   selections=["0", "1", "2", "3", "4", "5", "6", "7",
                               "8", "9"])
    ),
  accelerometer=dict(
    name="Accelerometer",
    label="Accelerometer",
    header=(
"*************************** Accelerometer ******************************"),
    number_of=dict(label="Number of Accel Axes", test=1,
                   datatype='int',
                   selections=["0", "1", "2", "3", "4", "5", "6", "7",
                               "8", "9"])
    )
  )


def get_component_headers(component_type, n):
    """
    Get the header data structures for the specified component type section in
    the SC file.  This function is only used when generating the 42 input file.
    """
    if component_type == 'body':
        s1 = "================================ "
        s2 = " ================================"
        return dict(label=f"Body {n}",
                    header=f"{s1}Body {n}{s2}")
    elif component_type == 'joint':
        name="Joint"
        s1 = "============================== "
        s2 = " ================================"
        return dict(label=f"{name} {n}",
                    header=f"{s1}{name} {n}{s2}")
    elif component_type == 'wheel':
        name = "Wheel"
        s1 = "=============================  "
        s2 = "  ================================"
        return dict(label=f"{name} {n}",
                    header=f"{s1}{name} {n}{s2}")
    elif component_type == 'mtb':
        name = "MTB"
        s1 = "==============================  "
        s2 = "  ================================="
        return dict(label=f"{name} {n}",
                    header=f"{s1}{name} {n}{s2}")
    elif component_type == 'thruster':
        name = "Thr"
        s1 = "==============================  "
        s2 = "  ================================="
        return dict(label=f"{name} {n}",
                    header=f"{s1}{name} {n}{s2}")
    elif component_type == 'gyro':
        name = "Axis"
        s1 = "============================== "
        s2 = " ==================================="
        return dict(label=f"{name} {n}",
                    header=f"{s1}{name} {n}{s2}")
    elif component_type == 'magnetometer':
        name = "Axis"
        s1 = "============================== "
        s2 = " ==================================="
        return dict(label=f"{name} {n}",
                    header=f"{s1}{name} {n}{s2}")
    elif component_type == 'css':
        name = "CSS"
        s1 = "============================== "
        s2 = " ===================================="
        return dict(label=f"{name} {n}",
                    header=f"{s1}{name} {n}{s2}")
    elif component_type == 'fss':
        name = "FSS"
        s1 = "=============================== "
        s2 = " ==================================="
        return dict(label=f"{name} {n}",
                    header=f"{s1}{name} {n}{s2}")
    elif component_type == 'st':
        name = "ST"
        s1 = "=============================== "
        s2 = " ===================================="
        return dict(label=f"{name} {n}",
                    header=f"{s1}{name} {n}{s2}")
    elif component_type == 'gps':
        name = "GPSR"
        s1 = "============================= "
        s2 = " ===================================="
        return dict(label=f"{name} {n}",
                    header=f"{s1}{name} {n}{s2}")
    elif component_type == 'accelerometer':
        name = "Axis"
        s1 = "============================== "
        s2 = " ==================================="
        return dict(label=f"{name} {n}",
                    header=f"{s1}{name} {n}{s2}")


def gen_sc_data_structure():
    data = {}
    # fill in default values for non-component sections
    for section in SC:
        if section != 'components':
            data[section] = {}
            # TODO:  add default values
            # for pid in SC[section]:
                # data[section][pid] = ''
    # component sections contain a list of components of the specified type
    data['components'] = {}
    for component_type in SC['components']:
        data['components'][component_type] = []
    return data


class SC_Form(QWidget):
    """
    A widget that provides a form for the specification of a 42 SC (Spacecraft)
    model, with the initial goal of generating the SC input file to 42.
    """
    def __init__(self, embedded=True, parent=None):
        super().__init__(parent)
        self.embedded = embedded
        if embedded:
            self.log = orb.log.debug
            self.home = orb.home
        else:
            self.log = print
            self.home = ''
        self.data = gen_sc_data_structure()
        self.form = QFormLayout()
        self.form.setFieldGrowthPolicy(self.form.FieldsStayAtSizeHint)
        self.setLayout(self.form)
        self.widgets = {}
        for section in SC_File:
            label_text = SC_File[section].get('label', 'missing label')
            section_label = QLabel(label_text, self)
            section_label.setTextFormat(Qt.RichText)
            section_label.setStyleSheet("QLabel {font-size: 16px;"
                                        "font-weight: bold; color: purple}")
            section_label.setFrameStyle(QFrame.Box | QFrame.Plain)
            section_label.setLineWidth(1)
            self.widgets[section] = {}
            self.widgets[section]['section_label'] = section_label
            self.form.addRow(section_label)
            if section not in component_types:
                # non-component section
                for pid, parm_props in SC[section].items():
                    parm_label_text = parm_props.get('label',
                                                     '[missing label]')
                    parm_label = NameLabel(parm_label_text)
                    parm_label.setTextFormat(Qt.RichText)
                    parm_label.setStyleSheet("QLabel {font-size: 14px;"
                                              "font-weight: bold}")
                    if parm_props['datatype'] == 'array':
                        # if array-valued, add an hbox to contain sub-fields
                        hbox = QHBoxLayout()
                        widgets = []
                        # array parameters have a list of widgets
                        self.widgets[section][pid] = widgets
                        for i in range(len(parm_props['postypes'])):
                            postype = parm_props['postypes'][i]
                            w_class = get_widget_class(postype)
                            w = w_class(section=section, pid=pid, i=i,
                                        parent=self)
                            w.textEdited.connect(self.update_data)
                            widgets.append(w)
                            hbox.addWidget(w)
                        self.form.addRow(parm_label, hbox)
                    else:
                        if parm_props.get('selections'):
                            # if field has selectable values ("selections"),
                            # represent it with a combo box
                            widget = ParmCombo(section=section, pid=pid,
                                               parent=self)
                            for val in parm_props['selections']:
                                widget.addItem(val, QVariant())
                            widget.activated.connect(self.update_data)
                            # set initial default value
                            self.data[section][pid] = widget.get_value()
                        else:
                            dtype = parm_props.get('datatype')
                            w_class = get_widget_class(dtype)
                            widget = w_class(section=section,
                                             pid=pid, parent=self)
                            widget.textEdited.connect(self.update_data)
                        self.widgets[section][pid] = widget
                        self.form.addRow(parm_label, widget)
            else:
                # special case for component sections:
                # the combo box selects the number of components of that type
                # -- each will get a button that invokes a ComponentDialog that
                # contains the fields / parameters for that component type
                parm_props = SC_File[section].get('number_of')
                parm_label_text = parm_props.get('label',
                                                 '[missing label]')
                parm_label = NameLabel(parm_label_text)
                parm_label.setTextFormat(Qt.RichText)
                parm_label.setStyleSheet("QLabel {font-size: 14px;"
                                          "font-weight: bold}")
                if parm_props.get('selections'):
                    # if field has selectable values ("selections"),
                    # represent it with a combo box
                    # NOTE: only component section that does NOT have
                    # "selection" is the Joint section
                    widget = QComboBox()
                    self.widgets[section]['number_of'] = widget
                    for val in parm_props['selections']:
                        widget.addItem(val, QVariant())
                    widget.currentIndexChanged.connect(
                                        self.set_number_of_components)
                    widget.component_type = section
                    self.form.addRow(parm_label, widget)
                if not self.widgets[section].get('button_box'):
                    name = SC_File[section].get('name', 'Unknown Name')
                    placeholder = NameLabel(f'0 {name} objects specified')
                    placeholder.setStyleSheet("QLabel {font-size: 14px;"
                                              "font-weight: bold;"
                                              "color:purple}")
                    placeholder.setAttribute(Qt.WA_DeleteOnClose)
                    button_box = QHBoxLayout()
                    button_box.addWidget(placeholder)
                    button_box.addStretch(1)
                    button_panel = QWidget()
                    button_panel.setLayout(button_box)
                    self.widgets[section]['button_box'] = button_box
                    self.form.addRow(button_panel)
        # NOTE: now using menus instead of Save/Cancel buttons
        # save_cancel_box = QHBoxLayout()
        # self.save_button = SizedButton('Save')
        # self.save_button.clicked.connect(self.save)
        # self.cancel_button = SizedButton('Cancel')
        # self.cancel_button.clicked.connect(self.cancel)
        # save_cancel_box.addStretch(1)
        # save_cancel_box.addWidget(self.save_button)
        # save_cancel_box.addWidget(self.cancel_button)
        # self.form.addRow(save_cancel_box)
        if self.data:
            self.update_form_from_data()

    def update_data(self, evt):
        """
        Update the data from the value set in a widget.
        """
        widget = self.sender()
        section = widget.section
        pid = widget.pid
        i = widget.i
        val = widget.get_value()
        self.log(f'* parm "{pid}" (i={i}) in section "{section}" set to {val}')
        if SC[section][pid]['datatype'] == 'array':
            # coerce to the positional datatype
            postypes = SC[section][pid]['postypes']
            if not self.data[section].get(pid):
                self.data[section][pid] = []
                # for now, add default "empty string" values
                # TODO:  set default values for arrays ...
                for dt in postypes:
                    self.data[section][pid].append('')
            dtype = datatypes.get(postypes[i]) or str
            self.data[section][pid][i] = dtype(val)
        else:
            dtype = datatypes.get(SC[section][pid].get('datatype')) or str
            self.data[section][pid] = dtype(val)

    def update_form_from_data(self):
        self.log('* updating SC form from data ...')
        sections = [s for s in SC if s != 'components']
        for comp_type in component_types:
            comp_objs = self.data['components'].get(comp_type)
            combo_box = self.widgets[comp_type].get('number_of')
            if combo_box:
                n = len(comp_objs)
                self.log(f'* setting number of {comp_type} to {n} ...')
                combo_box.setCurrentText(str(n))
        for section in sections:
            for pid in self.widgets[section]:
                if pid in self.data[section]:
                    # self.log(f'  updating "{pid}"')
                    widget = self.widgets[section][pid]
                    if isinstance(widget, list):
                        # array-valued parameter
                        for i, w in enumerate(widget):
                            w.set_value(self.data[section][pid][i])
                    elif hasattr(widget, 'set_value'):
                        widget.set_value(self.data[section][pid])
                    else:
                        # unknown type of widget ...
                        self.log(f'* "{pid}" value not accessible, widget is ')
                        self.log('  not array type nor has "set_value" ...')

    def set_number_of_components(self, evt):
        """
        Set the number of components of the type corresponding to the combo box
        in which the number was selected -- this will populate the relevant
        button box with a button for each component, which will invoke a
        ComponentDialog for that component.
        """
        widget = self.sender()
        data = self.data
        if hasattr(widget, 'component_type'):
            comp_type = widget.component_type
            number = int(widget.currentText())
            # self.log(f'component type to set number of: {comp_type}')
            # self.log(f'number: {number}')
            button_box = (self.widgets.get(comp_type) or {}).get('button_box')
            if button_box:
                # try:
                n = button_box.count()
                # self.log(f'{n} widgets in {comp_type} button box.')
                # remove any existing buttons ...
                for idx in reversed(range(n)):
                    # self.log(f'removing item at {idx}')
                    item = button_box.takeAt(idx)
                    if item is not None:
                        w = item.widget()
                        if w:
                            w.close()
                        button_box.removeItem(item)
                # add zero or more new buttons ...
                if number == 0:
                    placeholder = NameLabel(f'0 {comp_type} objects specified')
                    placeholder.setStyleSheet("QLabel {font-size: 14px;"
                                              "font-weight: bold;"
                                              "color:purple}")
                    placeholder.setAttribute(Qt.WA_DeleteOnClose)
                    button_box.addWidget(placeholder)
                    data['components'][comp_type] = []
                else:
                    if len(data['components'][comp_type]) > number:
                        # if number is less than components defined in the
                        # data, trim the data down to number
                        data['components'][comp_type] = data[
                                        'components'][comp_type][:number]
                    for i in range(number):
                        button = SizedButton(f'{comp_type} {i}')
                        button.clicked.connect(self.comp_dialog)
                        button_box.addWidget(button)
                        if len(data['components'][comp_type]) <= i:
                            # add an empty dict for each component that doesn't
                            # have one
                            data['components'][comp_type].append({})
                button_box.addStretch(1)
            # special case for "body": add "joint" buttons if appropriate ...
            if comp_type == "body":
                # number of joints is always 1 less than the number of bodies
                button_box = (self.widgets.get("joint") or {}).get(
                                                            'button_box')
                if button_box:
                    # try:
                    n = button_box.count()
                    # self.log(f'{n} widgets in joint button box.')
                    for idx in reversed(range(n)):
                        # self.log(f'removing item at {idx}')
                        item = button_box.takeAt(idx)
                        if item is not None:
                            w = item.widget()
                            if w:
                                w.close()
                            button_box.removeItem(item)
                    if number < 2:
                        placeholder = NameLabel('0 joint objects specified')
                        placeholder.setStyleSheet("QLabel {font-size: 14px;"
                                                  "font-weight: bold;"
                                                  "color:purple}")
                        placeholder.setAttribute(Qt.WA_DeleteOnClose)
                        button_box.addWidget(placeholder)
                        data['components']['joint'] = []
                    else:
                        if len(data['components']['joint']) > number - 1:
                            # if number - 1 is less than joints defined in the
                            # data, trim the joint data down to number - 1
                            data['components']['joint'] = data[
                                            'components']['joint'][:number - 1]
                        for i in range(number - 1):
                            button = SizedButton(f'joint {i}')
                            button.clicked.connect(self.comp_dialog)
                            button_box.addWidget(button)
                            if len(data['components']['joint']) <= i:
                                # add an empty dict for each joint that doesn't
                                # have one
                                data['components']['joint'].append({})
                    button_box.addStretch(1)
        else:
            self.log('could not determine sender.')

    def comp_dialog(self):
        button = self.sender()
        txt = button.text()
        comp_type, n = txt.split(' ')
        self.log(f'* button "{txt}" was clicked.')
        self.log(f'  ... to invoke parm dlg for ({comp_type}, {n})')
        dlg = ComponentDialog(comp_type, int(n), parent=self)
        dlg.show()

    def save(self):
        """
        Save the 42 SC model data to a yaml file.
        """
        self.log('* saving 42 model data to file ...')
        self.log('* 42 model data:')
        self.log(str(self.data))
        dtstr = date2str(dtstamp())
        if not state.get('last_42_path'):
            state['last_42_path'] = self.home
        file_path = os.path.join(state['last_42_path'],
                                 'SC42-' + dtstr + '.yaml')
        fpath, filters = QFileDialog.getSaveFileName(
                                    self, 'Save model data to file',
                                    file_path,
                                    "YAML Files (*.yaml)")
        if fpath:
            self.log(f'  - file selected: "{fpath}"')
            state['last_42_path'] = os.path.dirname(fpath)
            f = open(fpath, 'w')
            f.write(yaml.safe_dump(self.data, default_flow_style=False))
            f.close()

    def load(self):
        """
        Load a 42 SC model data from a yaml file.
        """
        self.log('* loading 42 SC model data from yaml ...')
        raw_data = None
        message = ''
        if not state.get('last_42_path'):
            state['last_42_path'] = ''
        dialog = QFileDialog(self, 'Open File',
                             state['last_42_path'],
                             "YAML Files (*.yaml)")
        fpath = ''
        if dialog.exec_():
            fpaths = dialog.selectedFiles()
            if fpaths:
                fpath = fpaths[0]
            dialog.close()
        if fpath:
            state['last_42_path'] = os.path.dirname(fpath)
            self.log('  file path: {}'.format(fpath))
            try:
                f = open(fpath)
                raw_data = f.read()
                f.close()
            except:
                message = "File '%s' could not be opened." % fpath
                popup = QMessageBox(
                            QMessageBox.Warning,
                            "Error in file path", message,
                            QMessageBox.Ok, self)
                popup.show()
                return
        else:
            # no file was selected
            return
        if raw_data:
            try:
                self.data = yaml.safe_load(raw_data)
            except:
                message = "An error was encountered."
                popup = QMessageBox(
                            QMessageBox.Warning,
                            "Error in Data Import", message,
                            QMessageBox.Ok, self)
                popup.show()
                return
        # TODO:  need a "clear" function to clear previous data ...
        self.update_form_from_data()

    # BROKEN:  must be reorganized to use the section "marker" lines to
    # identify sections and then to identify parameters by their position (line
    # sequence) within the section ...
    def import_file(self):
        """
        Import data from a standard 42 Spacecraft Description (SC) File.
        """
        self.log('* importing data from 42 SC file ...')
        # re-initialize internal data structure
        self.data = None
        self.data = gen_sc_data_structure()
        self.update_form_from_data()
        raw_data = None
        message = ''
        if not state.get('last_42_path'):
            state['last_42_path'] = ''
        dialog = QFileDialog(self, 'Open File',
                             state['last_42_path'],
                             ".txt files (*.txt)")
        fpath = ''
        if dialog.exec_():
            fpaths = dialog.selectedFiles()
            if fpaths:
                fpath = fpaths[0]
            dialog.close()
        if fpath:
            state['last_path'] = os.path.dirname(fpath)
            self.log('  file path: {}'.format(fpath))
            try:
                f = open(fpath)
                raw_data = f.readlines()
                f.close()
            except:
                message = "File '%s' could not be opened." % fpath
                popup = QMessageBox(
                            QMessageBox.Warning,
                            "Error in file path", message,
                            QMessageBox.Ok, self)
                popup.show()
                return
        else:
            # no file was selected
            return
        if raw_data:
            # parse all raw data into label-value pairs ...
            parsed_data = {}
            for line in raw_data:
                if '!' in line:
                    raw_value, raw_label = line.split('!')
                    parsed_data[raw_label] = raw_value.rstrip().lstrip()
            # look for exact "label"
            sections = [s for s in SC.keys() if s != 'components']
            for section in sections:
                self.log(f'  - finding parameters of section "{section}" ...')
                for pid in SC[section]:
                    label = SC[section][pid].get('label')
                    datatype = SC[section][pid].get('datatype')
                    for raw_label, raw_value in parsed_data.items():
                        if label in raw_label:
                            if datatype == 'array':
                                values = raw_value.split()
                                postypes = SC[section][pid].get('postypes')
                                for k, v in enumerate(values):
                                    postype = postypes[k] 
                                    dtype = datatypes.get(postype) or str
                                    values[k] = dtype(v)
                                self.data[section][pid] = values
                                self.log(f'    {pid} = {values}')
                            else:
                                dtype = datatypes.get(datatype) or str
                                value = raw_value.rstrip().lstrip()
                                self.data[section][pid] = dtype(value)
                                if datatype == 'str':
                                    self.log(f'    {pid} = "{value}"')
                                else:
                                    self.log(f'    {pid} = {value}')
            # locations maps comp_type to location of its section label in the
            # file, for use in scanning for instances of the component type
            locations = {}
            number_of_joints = 0
            for comp_type in component_types:
                self.log(f'  - searching for component "{comp_type}" ...')
                n = 0
                if comp_type == 'joint':
                    # joint is the only one without a "number of" specified,
                    # since it is 1 less than the number of bodies, and when
                    # the number of bodies is updated in the form, that will
                    # set the number of joints also
                    if number_of_joints:   # set from number of bodies
                        n = number_of_joints
                else:
                    parm_props = SC_File[comp_type].get('number_of')
                    n_of_label = parm_props.get('label')
                    for i, line in enumerate(raw_data):
                    # for raw_label, raw_value in parsed_data.items():
                        if n_of_label in line and '!' in line:
                            raw_value, raw_label = line.split('!')
                            n = int(raw_value.rstrip().lstrip())
                            # n_comps[comp_type] = n
                            self.log(f'    number of {comp_type}(s) = {n}')
                            locations[comp_type] = i
                            if comp_type == 'body' and n > 1:
                                number_of_joints = n - 1
                            break
                # begin scanning for instances at the location where the
                # component type section begins ...
                begin = locations.get(comp_type) or 0
                for j in range(n):
                    # NOTE: if n > 1, initial parse of raw data is invalid for
                    # this component type because it will only contain the
                    # parameters of the last component of that type!
                    # So: iterate over the raw_data again, looking for the
                    # sections for each component of this type ... and now we
                    # have to note the position of each section in the data ...
                    # NOTE: in 42, the component "instance" sections for gyro,
                    # magnetometer, and accelerometer are all called "Axis n",
                    # so begin scanning for that label at the position of that
                    # component type section and break as soon as it is found.
                    this_component = {}
                    comp_headers = get_component_headers(comp_type, j)
                    comp_label = comp_headers.get('label')
                    for m, line in enumerate(raw_data[begin:]):
                        if comp_label in line:
                            self.log(f'    "{comp_label}" is at line {m}')
                            comp_start = begin + m + 1
                            break
                    # parse the "component j" section ...
                    comp_end = comp_start + len(SC['components'][comp_type])
                    for line in raw_data[comp_start : comp_end]:
                        raw_value, raw_label = line.split('!')
                        for pid in SC['components'][comp_type]:
                            label = SC['components'][comp_type][pid].get(
                                                                    'label')
                            datatype = SC['components'][comp_type][pid].get(
                                                                    'datatype')
                            if label in raw_label:
                                if datatype == 'array':
                                    values = raw_value.split()
                                    postypes = SC['components'][comp_type][
                                                        pid].get('postypes')
                                    for k, v in enumerate(values):
                                        postype = postypes[k]
                                        dtype = datatypes.get(postype) or str
                                        values[k] = dtype(v)
                                    this_component[pid] = values
                                    self.log(f'    {pid} = {values}')
                                else:
                                    dtype = datatypes.get(datatype) or str
                                    value = raw_value.rstrip().lstrip()
                                    this_component[pid] = dtype(value)
                                    if datatype == 'str':
                                        self.log(f'    {pid} = "{value}"')
                                    else:
                                        self.log(f'    {pid} = {value}')
                    self.data['components'][comp_type].append(this_component)
            self.update_form_from_data()
        else:
            self.log('* could not find any data in file.')

    def write_file(self):
        """
        Write model data to a standard 42 Spacecraft Description (SC) File.
        """
        self.log('* preparing to write model data to 42 SC file ...')
        self.log('* 42 data:')
        self.log(str(self.data))
        dtstr = date2str(dtstamp())
        if not state.get('last_42_path'):
            state['last_42_path'] = self.home
        file_path = os.path.join(state['last_42_path'],
                                 'SC42-' + dtstr + '.txt')
        fpath, filters = QFileDialog.getSaveFileName(
                                    self, 'Write model data to 42 SC File',
                                    file_path,
                                    "Text Files (*.txt)")
        if fpath:
            self.log(f'  - file selected: "{fpath}"')
            state['last_42_path'] = os.path.dirname(fpath)
            output = ''
            for section, props in SC_File.items():
                self.log(f'* writing section "{section}" ...')
                if section not in component_types:
                    output += props['header'] + '\n'
                    for pid, parm_props in SC[section].items():
                        label = parm_props.get('label')
                        self.log(f'  parameter "{pid}" ("{label}")')
                        if parm_props['datatype'] == 'array':
                            # create a string of '  '-delimited values
                            vals = [str(v) for v in self.data[section][pid]]
                            val = '  '.join(vals)
                        else:
                            val = str(self.data[section][pid])
                        val_part = '{:<30}'.format(val)
                        output += val_part + '! ' + label + '\n'
                else:
                    output += props['header'] + '\n'
                    if section != 'joint':
                        n_label = SC_File[section]['number_of']['label']
                        number_of = len(self.data['components'][section])
                        n_str = '{:<30}'.format(number_of)
                        output += n_str + '! ' + n_label + '\n'
                    for i, comp in enumerate(self.data['components'][section]):
                        comp_h = get_component_headers(section, i)
                        output += comp_h.get('header') + '\n'
                        for pid, pprops in SC['components'][section].items():
                            label = pprops.get('label')
                            self.log(f'  parameter "{pid}" ("{label}")')
                            if pprops['datatype'] == 'array':
                                # create a string of '  '-delimited values
                                pval = comp[pid]
                                vals = [str(v) for v in pval]
                                val = '  '.join(vals)
                            else:
                                val = comp[pid]
                            val_part = '{:<30}'.format(val)
                            output += val_part + '! ' + label + '\n'
            with open(fpath, 'w') as f:
                f.write(output)


class ComponentDialog(QDialog):
    """
    Dialog to display a form for specifying the parameters of a component in a
    42 model.

    Args:
        component_type (str): type of component -- the initial set of
            "component types" are:  body, joint, wheel, mtb, thruster, gyro,
            magnetometer, css, fss, st, gps, and accelerometer.
        n (int): in a model containing multiple instances of the specified
            component type, the index of the component whose parameters are to
            be specified
    """
    def __init__(self, component_type, n, parent=None):
        super().__init__(parent=parent)
        if parent.embedded:
            self.log = orb.log.debug
        else:
            self.log = print
        self.comp_type = component_type
        self.idx = n
        self.data = parent.data
        form = QFormLayout()
        form.setFieldGrowthPolicy(form.FieldsStayAtSizeHint)
        self.setLayout(form)
        comp_type_name = SC_File[component_type]['name']
        label_text = f'{comp_type_name} {n} Parameters'
        section_label = QLabel(label_text, self)
        section_label.setTextFormat(Qt.RichText)
        section_label.setStyleSheet("QLabel {font-size: 16px;"
                                    "font-weight: bold; color: purple}")
        section_label.setFrameStyle(QFrame.Box | QFrame.Plain)
        section_label.setLineWidth(1)
        self.widgets = {}
        form.addRow(section_label)
        for pid, parm_props in SC['components'][component_type].items():
            txt = parm_props.get('label', '[missing label]')
            parm_label = NameLabel(txt)
            parm_label.setTextFormat(Qt.RichText)
            parm_label.setStyleSheet("QLabel {font-size: 14px;"
                                      "font-weight: bold}")
            if parm_props['datatype'] == 'array':
                # if array-valued, add an hbox to contain the sub-fields
                hbox = QHBoxLayout()
                widgets = []
                self.widgets[pid] = widgets
                for i in range(len(parm_props['postypes'])):
                    postype = parm_props['postypes'][i]
                    w_class = get_widget_class(postype)
                    w = w_class(section=component_type, pid=pid, i=i,
                                parent=self)
                    w.textEdited.connect(self.update_data)
                    widgets.append(w)
                    hbox.addWidget(w)
                form.addRow(parm_label, hbox)
            else:
                if parm_props.get('selections'):
                    widget = ParmCombo(section=component_type, pid=pid,
                                       parent=self)
                    widget.activated.connect(self.update_data)
                    for val in parm_props['selections']:
                        widget.addItem(val, QVariant())
                    # set initial default value
                    self.data['components'][
                                    component_type][pid] = widget.get_value()
                else:
                    w_class = get_widget_class(parm_props['datatype'])
                    widget = w_class(section=component_type, pid=pid,
                                     parent=self)
                    widget.textEdited.connect(self.update_data)
                self.widgets[pid] = widget
                form.addRow(parm_label, widget)
        if self.data:
            self.update_form_from_data()

    # NOTE: this was just for testing the combo box
    # def set_selection(self, evt):
        # cb = self.sender()
        # raw_val = cb.currentText()
        # self.log('* selection set to "{raw_val}"')

    def update_data(self, evt):
        widget = self.sender()
        comp_type = self.comp_type
        idx = self.idx
        pid = widget.pid
        i = widget.i
        val = widget.get_value()
        msg = f'* parm "{pid}" (i={i}) in section "{comp_type}[{idx}]" '
        msg += f'set to {val}'
        self.log(msg)
        if SC['components'][comp_type][pid]['datatype'] == 'array':
            # coerce to the positional datatype
            postypes = SC['components'][comp_type][pid]['postypes']
            if not self.data['components'][comp_type][idx].get(pid):
                self.data['components'][comp_type][idx][pid] = []
                # for now, add default "empty string" values
                # TODO:  set default values for arrays ...
                for dt in postypes:
                    self.data['components'][comp_type][idx][pid].append('')
            dtype = datatypes.get(postypes[i]) or str
            self.data['components'][comp_type][idx][pid][i] = dtype(val)
        else:
            dtype = datatypes.get(SC['components'][comp_type][pid].get(
                                                                'datatype'))
            dtype = dtype or str
            self.data['components'][comp_type][idx][pid] = dtype(val)

    def update_form_from_data(self):
        self.log('* updating component form from data ...')
        idx = self.idx
        for pid in self.widgets:
            if self.data['components'][self.comp_type][idx]:
                if pid in self.data['components'][self.comp_type][idx]:
                    # self.log(f'  updating "{pid}"')
                    widget = self.widgets[pid]
                    if isinstance(widget, list):
                        # array-valued parameter
                        for i, w in enumerate(widget):
                            w.set_value(self.data['components'][
                                        self.comp_type][idx][pid][i])
                    elif hasattr(widget, 'set_value'):
                        # set_value() works for all fields, including ParmCombo
                        widget.set_value(self.data['components'][
                                         self.comp_type][idx][pid])


class MenuButton(QPushButton):
    """
    A button to serve as a toolbar menu in the SC42Window.
    """
    def __init__(self, text, icon=None, tooltip='', actions=None, parent=None):
        """
        Args:
            text (str):  text of button

        Keyword Args:
            icon (QIcon):  an icon for the button
            tooltip (str):  text of tooltip
            actions (iterable of QAction):  items for the menu
        """
        super().__init__(parent=parent)
        self.setText(text)
        if icon:
            self.setIcon(icon)
        if tooltip:
            self.setToolTip(tooltip)
        menu = QMenu(self)
        if actions and hasattr(actions, '__iter__'):
            for action in actions:
                menu.addAction(action)
        self.setMenu(menu)


class SC42Window(QMainWindow):
    """
    Window containing the 42 SC (Spacecraft) Model forms.
    """
    def __init__(self, width=None, height=None, embedded=True, parent=None):
        super().__init__(parent=parent)
        self.w = width or 850
        self.h = height or 900
        self.forms = SC_Form(embedded=embedded)
        central_layout = QVBoxLayout()
        central_widget = QWidget()
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.forms)
        central_layout.addWidget(self.scroll_area, 1)
        central_widget.setLayout(central_layout)
        self.setCentralWidget(central_widget)
        self._create_actions()
        self.init_toolbar()

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
        return action

    def _create_actions(self):
        self.load_model_action = self.create_action(
                                    "Load a saved model...",
                                    slot=self.forms.load)
        self.import_file_action = self.create_action(
                                    "Import a model from a 42 SC file...",
                                    slot=self.forms.import_file)
        self.save_model_action = self.create_action(
                                    "Save model...",
                                    slot=self.forms.save)
        self.write_file_action = self.create_action(
                                    "Write model to a 42 SC file...",
                                    slot=self.forms.write_file)

    def init_toolbar(self):
        self.toolbar = self.addToolBar("Actions")
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        import_actions = [self.load_model_action,
                          self.import_file_action]
        import_button = MenuButton('Imports',
                                   tooltip='Import Data or Objects',
                                   actions=import_actions, parent=self)
        self.toolbar.addWidget(import_button)
        export_actions = [self.save_model_action,
                          self.write_file_action]
        export_button = MenuButton('Exports',
                                   tooltip='Export Data or Objects',
                                   actions=export_actions, parent=self)
        self.toolbar.addWidget(export_button)

    def sizeHint(self):
        return QSize(self.w, self.h)


if __name__ == '__main__':
    """Script mode for testing."""
    app = QApplication(sys.argv)
    window = SC42Window(embedded=False)
    window.show()
    # dlg = ComponentDialog('joint', '0')
    # dlg.show()
    sys.exit(app.exec_())

