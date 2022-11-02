# -*- coding: utf-8 -*-
"""
Startup processes for pangalaxian.
"""
import os, shutil
# import platform
from copy import deepcopy

# pangalactic
from pangalactic.core         import config, prefs, state
from pangalactic.core.meta    import MODEL_TYPE_PREFS, PGXN_PARAMETERS
from pangalactic.core.uberorb import orb
from pangalactic.node         import icons, images, ref_db


def setup_db_with_ref_data(home):
    # copy sqlite `local.db` file containing pgef ref data to home
    if not os.path.exists(os.path.join(home, 'local.db')):
        ref_db_mod_path = ref_db.__path__[0]
        ref_db_files = set([s for s in os.listdir(ref_db_mod_path)
                            if (not s.startswith('__init__')
                            and not s.startswith('__pycache__'))
                            ])
        if ref_db_files:
            print('  - copying db file into home dir ...')
            for p in ref_db_files:
                shutil.copy(os.path.join(ref_db_mod_path, p), home)
                print('  - ref db installed: {p}')


def setup_dirs_and_state():
    # create "icon_vault" for runtime-generated icons
    orb.icon_vault = os.path.join(orb.vault, 'icons')
    if not os.path.exists(orb.icon_vault):
        os.makedirs(orb.icon_vault, mode=0o755)
    # 'icon_type' is needed for 'load_reference_data()' (etc.) -- it is
    # determined by platform (any saved values will be overwritten).
    # NOTE: [2018-12-12] just go with .png (hopefully won't need to deal with
    # .ico ... cross that bridge when/if we come to it)
    state['icon_type'] = '.png'
    # if (platform.platform().startswith('Windows-10')
        # or platform.platform().startswith('Darwin')):
        # state['icon_type'] = '.png'
    prefs['userid'] =  prefs.get('userid') or 'me'
    prefs['model_types'] =  prefs.get('model_types') or MODEL_TYPE_PREFS

    default_config = {'app_name': 'Pangalaxian',
                      'logo': 'pangalactic_logo.png',
                      'tall_logo': 'pangalactic_logo.png',
                      'units': 'mks'}
    # orb.log.debug('* default config: {}'.format(str(default_config)))
    # app config will have been loaded -- set any missing config vars using
    # default config
    for item in default_config:
        if item not in config:
            config[item] = default_config[item]
    # state contains app-specified dashboards (app_dashboards)
    # NOTE: "app_" items in state are NOT restored when state is loaded from
    # the save state file -- that way "app_" items are ALWAYS set from the
    # current app release.
    app_dbds = state.get('app_dashboards')
    if prefs.get('dashboards'):
        # update prefs from any new app dashboards in state
        if app_dbds:
            for dash_name in app_dbds:
                if dash_name not in prefs['dashboards']:
                    prefs['dashboards'][dash_name] = deepcopy(app_dbds[
                                                                dash_name])
                    # append it to dashboard_names
                    prefs['dashboard_names'].append(dash_name)
    else:
        if app_dbds:
            prefs['dashboards'] = deepcopy(app_dbds)
        else:
            prefs['dashboards'] = {'Mass-Power-Data':
                    ['m_total', 'm', 'P_total', 'P', 'R_total', 'R_D']}
        prefs['dashboard_names'] = list(prefs['dashboards'].keys())
    if not state.get('dashboard_name'):
        state['dashboard_name'] = prefs['dashboard_names'][0]
    # app config will have been loaded -- add any missing default_parameters or
    # default_data_elements using state
    app_parms = state.get('app_default_parms') or []
    if prefs.get('default_parms'):
        # update prefs from any new default_parms in state
        if app_parms:
            for pid in app_parms:
                if pid not in prefs['default_parms']:
                    prefs['default_parms'].append(pid)
    else:
        # create prefs from default_parms in state, if any
        if app_parms:
            prefs['default_parms'] = app_parms[:]
        else:
            prefs['default_parms'] = ['m', 'P', 'R_D', 'Cost']
    app_data_elements = state.get('app_default_data_elements') or []
    if prefs.get('default_data_elements'):
        # update data elements from any new ones in state
        if app_data_elements:
            for deid in app_data_elements:
                if deid not in prefs['default_data_elements']:
                    prefs['default_data_elements'].append(deid)
    else:
        if app_data_elements:
            prefs['default_data_elements'] = app_data_elements[:]
        else:
            prefs['default_data_elements'] = ['Vendor']
    if not prefs.get('editor'):
        prefs['editor'] = {}
    if not prefs['editor'].get('parameters'):
        # parameters: order of parameters in 'parameters' panels
        prefs['editor']['parameters'] = PGXN_PARAMETERS
    # orb.log.debug('* prefs set: {}'.format(str(prefs)))
    # icon and image paths are set relative to home dir (icon_dir is used for
    # standard PanGalactic icons; icons created at runtime are saved into the
    # 'vault' directory, along with other runtime-created files)
    # [1] copy pangalactic image files from 'images' module to image_dir
    orb.image_dir = os.path.join(orb.home, 'images')
    image_files = set()
    # orb.log.debug('* checking for images in [orb.home]/images ...')
    if not os.path.exists(orb.image_dir):
        os.makedirs(orb.image_dir)
    else:
        image_files = set(os.listdir(orb.image_dir))
    # orb.log.debug('  - found %i images' % len(image_files))
    images_mod_path = images.__path__[0]
    image_res_files = set([s for s in os.listdir(images_mod_path)
                           if (not s.startswith('__init__')
                           and not s.startswith('__pycache__'))
                           ])
    images_to_copy = image_res_files - image_files
    # orb.log.debug('  - images to be installed: %i' % len(images_to_copy))
    if images_to_copy:
        # orb.log.debug('  - copying images into images dir ...')
        images_cpd = []
        for p in images_to_copy:
            shutil.copy(os.path.join(images_mod_path, p), orb.image_dir)
            images_cpd.append(p)
        # orb.log.debug('  - new images installed: {}'.format(str(images_cpd)))
    else:
        # orb.log.debug('  - all images already installed.')
        pass
    # [2] copy pangalactic icon files from 'icons' module to icon_dir
    state['icon_dir'] = os.path.join(orb.home, 'icons')
    icon_files = set()
    # orb.log.debug('* checking for icons in [orb.home]/icons ...')
    if not os.path.exists(state['icon_dir']):
        os.makedirs(state['icon_dir'])
    else:
        icon_files = set(os.listdir(state['icon_dir']))
    # orb.log.debug('  - found %i icons' % len(icon_files))
    icons_mod_path = icons.__path__[0]
    icon_res_files = set([s for s in os.listdir(icons_mod_path)
                          if (not s.startswith('__init__')
                          and not s.startswith('__pycache__'))
                          ])
    icons_to_copy = icon_res_files - icon_files
    # orb.log.debug('  - icons to be installed: %i' % len(icons_to_copy))
    if icons_to_copy:
        # orb.log.debug('  - copying icons into icons dir ...')
        icons_cpd = []
        for p in icons_to_copy:
            shutil.copy(os.path.join(icons_mod_path, p), state['icon_dir'])
            icons_cpd.append(p)
        # orb.log.debug('  - new icons installed: {}'.format(str(icons_cpd)))
    else:
        # orb.log.debug('  - all icons already installed.')
        pass

