# -*- coding: utf-8 -*-
"""
Startup processes for pangalaxian.
"""
import os, shutil
# import platform
from copy import deepcopy

# pangalactic
from pangalactic.core         import orb
from pangalactic.core         import config, prefs, state
from pangalactic.core.meta    import PGXN_PARAMETERS
from pangalactic.node         import docs, icons, images, ref_db
from pangalactic.node.docs    import images as doc_images


def setup_ref_db_and_version(home, version):
    """
    Add a local sqlite "local.db" file that is pre-populated with all data from
    the "refdata" module, and add a "VERSION" file.

    Args:
        home (str): path to the home directory
        version (str): current version
    """
    # copy sqlite `local.db` file containing pgef ref data to home
    if not os.path.exists(os.path.join(home, 'local.db')):
        ref_db_mod_path = ref_db.__path__[0]
        ref_db_files = set([s for s in os.listdir(ref_db_mod_path)
                            if (not s.startswith('__init__')
                            and not s.startswith('__pycache__'))
                            ])
        if ref_db_files:
            # print('  - copying db file into home dir ...')
            for p in ref_db_files:
                shutil.copy(os.path.join(ref_db_mod_path, p), home)
                # print('  - ref db installed: {p}')
    with open(os.path.join(home, 'VERSION'), 'w') as f:
        f.write(version)


def setup_dirs_and_state(app_name='Pangalaxian'):
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
    default_config = {'app_name': app_name,
                      'logo': 'pangalactic_logo.png',
                      'tall_logo': 'pangalactic_logo.png',
                      'units': 'mks'}
    # orb.log.debug('* default config: {}'.format(str(default_config)))
    # app config will have been loaded -- set any missing config vars using
    # default config
    for item in default_config:
        if item not in config:
            config[item] = default_config[item]
    # NOTE: "app_" items in state are NOT restored when state is loaded from
    # the save state file -- that way "app_" items are ALWAYS set from the
    # current app release.
    if not prefs.get('dashboards'):
        prefs['dashboards'] = {
            'MEL' : 
                ['m[CBE]', 'm[Ctgcy]', 'm[MEV]',
                 'P[CBE]', 'P[Ctgcy]', 'P[MEV]', 'P[peak]',
                 'R_D[CBE]', 'R_D[Ctgcy]', 'R_D[MEV]',
                 'Vendor', 'Cost', 'TRL'],
            'Mass':
                ['m[CBE]', 'm[Ctgcy]', 'm[MEV]'],
            'Power':
                ['P[CBE]', 'P[Ctgcy]', 'P[MEV]', 'P[peak]', 'P[survival]',
                 'Area_active', 'Area_substrate'],
            'Data Rates':
                ['R_D[CBE]', 'R_D[Ctgcy]', 'R_D[MEV]'],
            'Mechanical':
                ['m[CBE]', 'm[Ctgcy]', 'm[MEV]', 'height', 'width', 'depth'],
            'Thermal':
                ['T[operational_max]', 'T[operational_min]', 'T[survival_max]',
                 'T[survival_min]', 'P[CBE]', 'P[Ctgcy]', 'P[MEV]', 'P[peak]',
                 'P[survival]'],
            'System Resources':
                ['m[CBE]', 'm[Ctgcy]', 'm[MEV]', 'm[NTE]', 'm[Margin]',
                 'P[CBE]', 'P[Ctgcy]', 'P[MEV]', 'P[peak]', 'P[NTE]',
                 'P[Margin]', 'R_D[CBE]', 'R_D[Ctgcy]', 'R_D[MEV]',
                 'R_D[NTE]', 'R_D[Margin]']
            }
        prefs['dashboard_names'] = list(prefs['dashboards'].keys())
    # state contains app-specified dashboards (app_dashboards)
    # update prefs from any new app dashboards in state
    app_dbds = state.get('app_dashboards')
    if app_dbds:
        for dash_name in app_dbds:
            if dash_name not in prefs['dashboards']:
                prefs['dashboards'][dash_name] = deepcopy(app_dbds[
                                                            dash_name])
                # append it to dashboard_names
                prefs['dashboard_names'].append(dash_name)
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
    # [1] copy pangalactic image files from 'images' module to orb.image_dir
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
    # [2] copy pangalactic icon files from 'icons' module to orb.icon_dir
    orb.icon_dir = os.path.join(orb.home, 'icons')
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
    # [3] copy pangalactic docs files from 'docs' module to orb.docs_dir
    orb.docs_dir = os.path.join(orb.home, 'docs')
    state['docs_dir'] = os.path.join(orb.home, 'docs')
    docs_files = set()
    # orb.log.debug('* checking for docs in [orb.home]/docs ...')
    if not os.path.exists(state['docs_dir']):
        os.makedirs(state['docs_dir'])
    else:
        docs_files = set(os.listdir(state['docs_dir']))
    # orb.log.debug('  - found %i docs' % len(docs_files))
    docs_mod_path = docs.__path__[0]
    docs_res_files = set([s for s in os.listdir(docs_mod_path)
                          if (not s.startswith('__init__')
                              and not s.startswith('__pycache__')
                              and not s == 'images')
                          ])
    docs_to_copy = docs_res_files - docs_files
    # orb.log.debug('  - docs to be installed: %i' % len(docs_to_copy))
    if docs_to_copy:
        # orb.log.debug('  - copying docs into docs dir ...')
        docs_cpd = []
        for p in docs_to_copy:
            shutil.copy(os.path.join(docs_mod_path, p), state['docs_dir'])
            docs_cpd.append(p)
        # orb.log.debug('  - new docs installed: {}'.format(str(docs_cpd)))
    else:
        # orb.log.debug('  - all docs already installed.')
        pass
    # [4] copy pangalactic docs/images files from 'docs' module to
    # orb.doc_images_dir
    orb.doc_images_dir = os.path.join(orb.home, 'docs', 'images')
    state['doc_images_dir'] = os.path.join(orb.home, 'docs', 'images')
    doc_images_files = set()
    # orb.log.debug('* checking for docs/images in [orb.home]/docs ...')
    if not os.path.exists(state['doc_images_dir']):
        os.makedirs(state['doc_images_dir'])
    else:
        doc_images_files = set(os.listdir(state['doc_images_dir']))
    # orb.log.debug('  - found %i doc images' % len(doc_images_files))
    doc_images_mod_path = doc_images.__path__[0]
    doc_images_res_files = set([s for s in os.listdir(doc_images_mod_path)
                                 if (not s.startswith('__init__')
                                     and not s.startswith('__pycache__'))
                                 ])
    doc_images_to_copy = doc_images_res_files - doc_images_files
    n = len(doc_images_to_copy)
    orb.log.debug(f'  - doc images to be installed: {n}')
    if doc_images_to_copy:
        # orb.log.debug('  - copying doc images into docs/images dir ...')
        doc_images_cpd = []
        for p in doc_images_to_copy:
            shutil.copy(os.path.join(doc_images_mod_path, p),
                        state['doc_images_dir'])
            doc_images_cpd.append(p)
        # n_imgs = len(doc_images_cpd)
        # orb.log.debug(f'  - {n_imgs} new doc images installed.')
    else:
        # orb.log.debug('  - all doc images already installed.')
        pass

