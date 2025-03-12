# -*- coding: utf-8 -*-
"""
Unit tests for pangalactic.node modules
"""
import os
import unittest

# set the orb
import pangalactic.core.set_uberorb

# pangalactic
# from pangalactic.core.parametrics import (compute_margin,
                                          # compute_requirement_margin,
                                          # deserialize_des,
                                          # deserialize_parms,
                                          # # get_duration,
                                          # get_dval, data_elementz,
                                          # get_pval, parameterz,
                                          # # get_modal_powerstate_value,
                                          # load_parmz, load_data_elementz,
                                          # init_mode_defz, mode_defz,
                                          # load_mode_defz, save_mode_defz,
                                          # recompute_parmz,
                                          # # PowerState,
                                          # rqt_allocz, round_to,
                                          # serialize_des,
                                          # serialize_parms,
                                          # save_parmz, save_data_elementz)
from pangalactic.core              import orb, prefs
from pangalactic.core.serializers  import deserialize
from pangalactic.core.test.utils   import (create_test_users,
                                           create_test_project)
from pangalactic.node.powermodeler import flatten_subacts
from pangalactic.node.startup      import setup_ref_db_and_version

prefs['default_data_elements'] = ['TRL', 'Vendor', 'reference_missions']
prefs['default_parms'] = [
    'm',
    'm[CBE]',
    'm[Ctgcy]',
    'm[MEV]',
    'P',
    'P[CBE]',
    'P[Ctgcy]',
    'P[MEV]',
    'P[peak]',
    'P[survival]',
    'R_D',
    'R_D[CBE]',
    'R_D[Ctgcy]',
    'R_D[MEV]',
    'T[operational_max]',
    'T[operational_min]',
    'T[survival_max]',
    'T[survival_min]',
    'Cost',
    'height',
    'width',
    'depth']
app_home = 'pangalaxian_test'
app_home_path = os.path.join(os.getcwd(), app_home)
if not os.path.exists(app_home_path):
    os.makedirs(app_home_path, mode=0o755)
home = app_home_path
this_version = 'test'
setup_ref_db_and_version(home, this_version)
orb.start(home=home)
serialized_test_objects = create_test_users()
serialized_test_objects += create_test_project()
deserialize(orb, serialized_test_objects)


class NodeTest(unittest.TestCase):
    maxDiff = None

    def test_00_flatten_subacts(self):
        """
        CASE:  flatten a nested set of activities
        """
        h2g2 = orb.get('H2G2')
        mission = orb.select('Mission', owner=h2g2)
        value = flatten_subacts(mission)
        act1 = orb.select('Activity', name='Launch')
        act2 = orb.select('Activity', name='Calibration')
        act3 = orb.select('Activity', name='Propulsion')
        act4 = orb.select('Activity', name='Science Data Acquisition')
        act5 = orb.select('Activity', name='Science Data Xmit')
        expected = [act1, act2, act3, act4, act5]
        self.assertEqual(expected, value)

