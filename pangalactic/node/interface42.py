"""
Interface to the "42" Attitude Control System modeling application
"""
import sys
import ruamel_yaml as yaml

from PyQt5.QtCore import Qt, QSize, QVariant
from PyQt5.QtWidgets import (QApplication, QComboBox, QDialog, QFormLayout,
                             QFrame, QMainWindow, QHBoxLayout, QVBoxLayout,
                             QLabel, QScrollArea, QWidget)

from pangalactic.core.uberorb     import orb
from pangalactic.node.buttons     import SizedButton
from pangalactic.node.widgets     import NameLabel
from pangalactic.node.widgets     import (FloatFieldWidget, IntegerFieldWidget,
                                          StringFieldWidget)


class FloatParmWidget(FloatFieldWidget):
    def __init__(self, parent=None, value=None, pid='', i=0):
        super().__init__(parent=parent, value=value)
        self.pid = pid
        self.i = i


class IntParmWidget(IntegerFieldWidget):
    def __init__(self, parent=None, value=None, pid='', i=0):
        super().__init__(parent=parent, value=value)
        self.pid = pid
        self.i = i


class StrParmWidget(StringFieldWidget):
    """
    Parameter field for string-valued (or untyped) parameters.

    Keyword Args:
        parent (QWidget): parent widget
        value (str): initial value of the field
        parm_type (str): datatype; if None, plain string is assumed; if "float"
            or "int", the appropriate "validator" (mask) will be set so that
            only values coercible to that type can be entered
        pid (str): parameter id
        i (int): for array-valued parameters, position of this field's value in
            the array
    """
    def __init__(self, parent=None, value=None, pid='', i=0, parm_type=None,
                 width=None):
        super().__init__(parent=parent, value=value, parm_type=parm_type,
                         width=width)
        self.pid = pid
        self.i = i


component_types = ['body', 'joint', 'wheel', 'mtb', 'thruster', 'gyro',
                   'magnetometer', 'css', 'fss', 'st', 'gps', 'accelerometer']

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
                 selections=["FIXED", "EULER_HILL", "ENCKE", "COWELL"]),
      pos_of=dict(label="Pos of CM or ORIGIN, wrt F", test="CM",
                  datatype='str', selections=["CM", "ORIGIN"]),
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
                 selections=["STEADY", "KIN_JOINT", "DYN_JOINT"]),
      joint_forces=dict(label="Passive Joint Forces and Torques Enabled",
                 test="FALSE", datatype='str', selections=["TRUE", "FALSE"]),
      compute_forces=dict(label="Compute Constraint Forces and Torques",
                 test="FALSE", datatype='str', selections=["TRUE", "FALSE"]),
      mass_props=dict(label="Mass Props referenced to REFPT_CM or REFPT_JOINT",
                 test="REFPT_CM", datatype='str',
                 selections=["REFPT_CM", "REFPT_JOINT"]),
      flex_active=dict(label="Flex Active",
                 test="FALSE", datatype='str', selections=["TRUE", "FALSE"]),
      include_2nd_order=dict(label="Include 2nd Order Flex Terms",
                 test="FALSE", datatype='str', selections=["TRUE", "FALSE"]),
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
    number_of=dict(label="Number of Bodies", value=1,
                   datatype='int',
                   selections=["0", "1", "2", "3", "4", "5", "6", "7",
                               "8", "9"])
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
    number_of=dict(label="Number of Wheels", value=1,
                   datatype='int',
                   selections=["0", "1", "2", "3", "4", "5", "6", "7",
                               "8", "9"])
    ),
  mtb=dict(
    name="MTB",
    label="MTB Parameters",
    header=(
"*************************** MTB Parameters ****************************"),
    number_of=dict(label="Number of MTBs", value=1,
                   datatype='int',
                   selections=["0", "1", "2", "3", "4", "5", "6", "7",
                               "8", "9"])
    ),
  thruster=dict(
    name="Thruster",
    label="Thruster Parameters",
    header=(
"************************* Thruster Parameters **************************"),
    number_of=dict(label="Number of Thrusters", value=1,
                   datatype='int',
                   selections=["0", "1", "2", "3", "4", "5", "6", "7",
                               "8", "9"])
    ),
  gyro=dict(
    name="Gyro",
    label="Gyro",
    header=(
"******************************* Gyro ************************************"),
    number_of=dict(label="Number of Gyros", value=1,
                   datatype='int',
                   selections=["0", "1", "2", "3", "4", "5", "6", "7",
                               "8", "9"])
    ),
  magnetometer=dict(
    name="Magnetometer",
    label="Magnetometer",
    header=(
"*************************** Magnetometer ********************************"),
    number_of=dict(label="Number of Magnetometer Axes", value=1,
                   datatype='int',
                   selections=["0", "1", "2", "3", "4", "5", "6", "7",
                               "8", "9"])
    ),
  css=dict(
    name="Coarse Sun Sensor",
    label="Coarse Sun Sensor",
    header=(
"*********************** Coarse Sun Sensor *******************************"),
    number_of=dict(label="Number of Coarse Sun Sensors", value=1,
                   datatype='int',
                   selections=["0", "1", "2", "3", "4", "5", "6", "7",
                               "8", "9"])
    ),
  fss=dict(
    name="Fine Sun Sensor",
    label="Fine Sun Sensor",
    header=(
"************************* Fine Sun Sensor *******************************"),
    number_of=dict(label="Number of Fine Sun Sensors", value=1,
                   datatype='int',
                   selections=["0", "1", "2", "3", "4", "5", "6", "7",
                               "8", "9"])
    ),
  st=dict(
    name="Star Tracker",
    label="Star Tracker",
    header=(
"************************** Star Tracker *********************************"),
    number_of=dict(label="Number of Star Trackers", value=1,
                   datatype='int',
                   selections=["0", "1", "2", "3", "4", "5", "6", "7",
                               "8", "9"])
    ),
  gps=dict(
    name="GPS",
    label="GPS",
    header=(
"****************************** GPS **************************************"),
    number_of=dict(label="Number of GPS Receivers", value=1,
                   datatype='int',
                   selections=["0", "1", "2", "3", "4", "5", "6", "7",
                               "8", "9"])
    ),
  accelerometer=dict(
    name="Accelerometer",
    label="Accelerometer",
    header=(
"*************************** Accelerometer *******************************"),
    number_of=dict(label="Number of Accel Axes", value=1,
                   datatype='int',
                   selections=["0", "1", "2", "3", "4", "5", "6", "7",
                               "8", "9"])
    )
  )


def get_component_headers(component_type, n):
    """
    Get the header data structures for the specified component type section.
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
        full_name = "Thruster"
        name = "Thr"
        s1 = "==============================  "
        s2 = "  ================================="
        return dict(label=f"{full_name} {n}",
                    header=f"{s1}{name} {n}{s2}")
    elif component_type == 'gyro':
        full_name = "Gyro Axis"
        name = "Axis"
        s1 = "============================== "
        s2 = " ==================================="
        return dict(label=f"{full_name} {n}",
                    header=f"{s1}{name} {n}{s2}")
    elif component_type == 'magnetometer':
        full_name = "Magnetometer Axis"
        name = "Axis"
        s1 = "============================== "
        s2 = " ==================================="
        return dict(label=f"{full_name} {n}",
                    header=f"{s1}{name} {n}{s2}")
    elif component_type == 'css':
        full_name = "Coarse Sun Sensor"
        name = "CSS"
        s1 = "============================== "
        s2 = " ===================================="
        return dict(label=f"{full_name} {n}",
                    header=f"{s1}{name} {n}{s2}")
    elif component_type == 'fss':
        full_name = "Fine Sun Sensor"
        name = "FSS"
        s1 = "=============================== "
        s2 = " ==================================="
        return dict(label=f"{full_name} {n}",
                    header=f"{s1}{name} {n}{s2}")
    elif component_type == 'st':
        full_name = "Star Tracker"
        name = "ST"
        s1 = "=============================== "
        s2 = " ===================================="
        return dict(label=f"{full_name} {n}",
                    header=f"{s1}{name} {n}{s2}")
    elif component_type == 'gps':
        name = "GPSR"
        s1 = "============================= "
        s2 = " ===================================="
        return dict(label=f"{name} {n}",
                    header=f"{s1}{name} {n}{s2}")
    elif component_type == 'accelerometer':
        full_name = "Accelerometer Axis"
        name = "Axis"
        s1 = "============================== "
        s2 = " ==================================="
        return dict(label=f"{full_name} {n}",
                    header=f"{s1}{name} {n}{s2}")


def gen_sc_data_structure():
    data = {}
    for section in SC:
        data[section] = {}
        number_of = {}
        if section not in component_types:
            for pid in SC[section]:
                data[section][pid] = ''
        else:
            # component section -- number of components must be set
            number_of[section] = 0
            for pid in SC[section]:
                data[section][pid] = ''
    return data


class SC_Form(QWidget):
    """
    A widget that provides a form for the specification of a 42 SC (Spacecraft)
    model, with the initial goal of generating the SC input file to 42.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
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
                        for i in range(len(parm_props['value'])):
                            w = FloatParmWidget(pid=pid, i=i, width=60,
                                                parent=self)
                            w.textEdited.connect(self.update_data)
                            widgets.append(w)
                            hbox.addWidget(w)
                        self.form.addRow(parm_label, hbox)
                    else:
                        if parm_props.get('selections'):
                            # if field has selectable values ("selections"),
                            # represent it with a combo box
                            widget = QComboBox()
                            for val in parm_props['selections']:
                                widget.addItem(val, QVariant())
                                widget.activated.connect(
                                                    self.set_selected_value)
                        else:
                            if parm_props.get('datatype') == 'float':
                                widget = FloatParmWidget(pid=pid, parent=self)
                            elif parm_props.get('datatype') == 'int':
                                widget = IntParmWidget(pid=pid, parent=self)
                            elif parm_props.get('datatype') == 'str':
                                widget = StrParmWidget(pid=pid, width=200,
                                                       parent=self)
                            widget.textEdited.connect(self.update_data)
                        self.form.addRow(parm_label, widget)
            else:
                # special case for component sections:
                # the combo box selects the number of components of that type
                # -- each will get a button that invokes a ParameterDialog that
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
                    widget = QComboBox()
                    for val in parm_props['selections']:
                        widget.addItem(val, QVariant())
                    widget.activated.connect(
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
        save_cancel_box = QHBoxLayout()
        self.save_button = SizedButton('Save')
        self.save_button.clicked.connect(self.save)
        self.cancel_button = SizedButton('Cancel')
        self.cancel_button.clicked.connect(self.cancel)
        save_cancel_box.addStretch(1)
        save_cancel_box.addWidget(self.save_button)
        save_cancel_box.addWidget(self.cancel_button)
        self.form.addRow(save_cancel_box)

    def update_data(self, evt):
        widget = self.sender()
        pid = widget.pid
        i = widget.i
        val = widget.get_value()
        print(f'* parm "{pid}" (i={i}) set to {val}')

    def set_number_of_components(self, evt):
        """
        Set the number of components of the type corresponding to the combo box
        in which the number was selected -- this will populate the relevant
        button box with a button for each component, which will invoke a
        ParameterDialog for that component.
        """
        widget = self.sender()
        if hasattr(widget, 'component_type'):
            comp_type = widget.component_type
            number = int(widget.currentText())
            # orb.log.debug(f'component type to set number of: {comp_type}')
            # orb.log.debug(f'number: {number}')
            button_box = (self.widgets.get(widget.component_type) or {}).get(
                                                              'button_box')
            if button_box:
                # try:
                n = button_box.count()
                # orb.log.debug(f'{n} widgets in {comp_type} button box.')
                for idx in reversed(range(n)):
                    # orb.log.debug(f'removing item at {idx}')
                    item = button_box.takeAt(idx)
                    if item is not None:
                        w = item.widget()
                        if w:
                            w.close()
                        button_box.removeItem(item)
                if number == 0:
                    placeholder = NameLabel(f'0 {comp_type} objects specified')
                    placeholder.setStyleSheet("QLabel {font-size: 14px;"
                                              "font-weight: bold;"
                                              "color:purple}")
                    placeholder.setAttribute(Qt.WA_DeleteOnClose)
                    button_box.addWidget(placeholder)
                else:
                    for i in range(number):
                        button = SizedButton(f'{comp_type} {i}')
                        button.clicked.connect(self.parm_dialog)
                        button_box.addWidget(button)
                button_box.addStretch(1)
            if comp_type == "body":
                # number of joints is always 1 less than the number of bodies
                button_box = (self.widgets.get("joint") or {}).get(
                                                            'button_box')
                if button_box:
                    # try:
                    n = button_box.count()
                    # orb.log.debug(f'{n} widgets in joint button box.')
                    for idx in reversed(range(n)):
                        # orb.log.debug(f'removing item at {idx}')
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
                    else:
                        for i in range(number - 1):
                            button = SizedButton(f'joint {i}')
                            button.clicked.connect(self.parm_dialog)
                            button_box.addWidget(button)
                    button_box.addStretch(1)
        else:
            orb.log.debug('could not determine sender.')

    def set_selected_value(self, evt):
        pass

    def parm_dialog(self):
        button = self.sender()
        txt = button.text()
        component_type, n = txt.split(' ')
        print(f'* button "{txt}" was clicked.')
        print(f'  ... to invoke parm dlg for ({component_type}, {n})')
        dlg = ParameterDialog(component_type, int(n), parent=self)
        dlg.show()

    def save(self):
        # orb.log.info('* saving 42 data ...')
        print('* saving 42 data ...')
        # TODO: a file dialog ...
        f = open('/home/waterbug/SC42.yaml', 'w')
        f.write(yaml.safe_dump(self.data, default_flow_style=False))
        f.close()

    def cancel(self):
        # orb.log.info('* cancelling 42 data ...')
        print('* cancelling 42 data ...')


class ParameterDialog(QDialog):
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
        headers = get_component_headers(component_type, n)
        form = QFormLayout()
        form.setFieldGrowthPolicy(form.FieldsStayAtSizeHint)
        self.setLayout(form)
        section_label = QLabel(headers.get('label', 'missing label'), self)
        section_label.setTextFormat(Qt.RichText)
        section_label.setStyleSheet("QLabel {font-size: 16px;"
                                    "font-weight: bold; color: purple}")
        section_label.setFrameStyle(QFrame.Box | QFrame.Plain)
        section_label.setLineWidth(1)
        # Maybe YAGNI ...
        # self.widgets = {}
        # self.widgets['section_label'] = section_label
        # self.widgets['widgets'] = {}
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
                for i in range(len(parm_props['value'])):
                    w = FloatParmWidget(pid=pid, i=i, parent=self)
                    w.textEdited.connect(self.update_data)
                    widgets.append(w)
                    hbox.addWidget(w)
                form.addRow(parm_label, hbox)
            else:
                if parm_props.get('selections'):
                    widget = QComboBox()
                    widget.activated.connect(self.set_selection)
                    for val in parm_props['selections']:
                        widget.addItem(val, QVariant())
                else:
                    widget = StrParmWidget(pid=pid, parent=self, width=60)
                    widget.textEdited.connect(self.update_data)
                form.addRow(parm_label, widget)

    def set_selection(self, evt):
        pass

    def update_data(self, evt):
        pass


class SC_Window(QMainWindow):
    """
    Window containing the 42 SC (Spacecraft) Model forms.
    """
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.forms = SC_Form()
        central_layout = QVBoxLayout()
        central_widget = QWidget()
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.forms)
        central_layout.addWidget(self.scroll_area, 1)
        central_widget.setLayout(central_layout)
        self.setCentralWidget(central_widget)

    def sizeHint(self):
        return QSize(850, 900)


def output():
    f = open('/home/waterbug/SC42.yaml', 'w')
    f.write(yaml.safe_dump(SC_File, default_flow_style=False))
    f.close()


if __name__ == '__main__':
    """Script mode for testing."""
    app = QApplication(sys.argv)
    window = SC_Window()
    window.show()
    # dlg = ParameterDialog('joint', '0')
    # dlg.show()
    sys.exit(app.exec_())

