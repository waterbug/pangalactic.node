#!/usr/bin/env python
"""
Wrapper module for pangalaxian, used in creating a self-contained PyInstaller
bundle for deployment.
"""
import argparse, os, shutil, sys

import pangalactic.node
from pangalactic.core import __version__ as app_version
from pangalactic.node import docs
from pangalactic.node.test import data as test_data_mod
from pangalactic.node.test import vault as model_files_mod


def main():
    from pangalactic.core import config, state
    from pangalactic.node.pangalaxian import run
    # NOTE: pangalactic.core.test[data|vault] and pangalactic.core.ontology
    # need to be imported here so that the data files in those modules can be
    # accessed when running the "pyinstaller" installed version.
    import pangalactic.core.ontology
    import pangalactic.core.test.data
    import pangalactic.core.test.vault
    app_config = {}
    app_config['app_base_name'] = 'pangalaxian'
    release_mode = "dev"
    # config:  localized settings; user can edit
    # default configuration:
    if release_mode == 'dev':
        app_config['app_name'] = 'pangalaxian_dev'
        # dev host
        app_config['host'] = 'localhost'
        app_config['port'] = 8080
    elif release_mode == 'test':
        app_config['app_name'] = 'pangalaxian_test'
        # dev host
        app_config['host'] = 'localhost'
        app_config['port'] = 8080
    else:
        app_config['app_name'] = 'pangalaxian'
        # production host
        app_config['host'] = 'localhost'
        app_config['port'] = 8080
    # self_signed_cert -> the server's cert is self-signed, so it must be
    # present in the home directory as the server_cert.pem file; if the
    # server has a CA-signed cert, server_cert.pem will be ignored if present
    app_config['self_signed_cert'] = False
    # map from LDAP search dialog field display names to "dir_info" fields
    app_config['ldap_schema'] = {'email': 'oid',
                                 'userid': 'id',
                                 'first Name': 'first_name',
                                 'last Name': 'last_name'}
    # these state items are used to populate default prefs, and can later be
    # reverted to ...
    # 2018-03-26: per MDL, add h, w, d to default parameters
    # 2021-03-16: per MDL, add Temp. parms to default parameters
    state['app_default_parms'] = [
            'm', 'm[CBE]', 'm[Ctgcy]', 'm[MEV]',
            'P', 'P[CBE]', 'P[Ctgcy]', 'P[MEV]',
            'P[peak]', 'P[standby]', 'P[survival]',
            'T[operational_max]', 'T[operational_min]',
            'T[survival_max]', 'T[survival_min]',
            'R_D', 'R_D[CBE]', 'R_D[Ctgcy]', 'R_D[MEV]',
            'height', 'width', 'depth', 'Cost']
    state['app_default_data_elements'] = [
            'Vendor'
            ]
    state['default_schema_name'] = 'MEL'
    state['p_defaults'] = {'m[ctgcy]': '0.30',
                           'P[ctgcy]': '0.30',
                           'R[ctgcy]': '0.30'}
    state['de_defaults'] = {}
    # download url (internal to GSFC network)
    state['app_download_url'] = 'https://pangalactic.us'
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--debug", action="store_true",
                        help="debug mode")
    parser.add_argument("-t", "--test", action="store_true",
                        help="test mode")
    parser.add_argument("-u", "--unencrypted", action="store_true",
                        help="use unencrypted transport (no tls)")
    parser.add_argument('--auth', dest='auth', type=str, default='cryptosign',
                        help='authentication method: "ticket" or "cryptosign" '
                             '[default: "cryptosign" (pubkey auth)]')
    args = parser.parse_args()
    # use True for DEBUG default setting (SCW 2018-12-23) ...
    DEBUG = config.get('debug', True) or args.debug
    # use True for TEST to load test data (SCW 2025-01-19) ...
    TEST = config.get('test', False) or args.test
    # use tls unless testing in a non-secure env
    TLS = config.get('tls', True)
    if args.unencrypted:
        # cmd line arg overrides config
        TLS = False
    # create a pgxn home directory in the user's home dir
    app_home_dir = ''
    if sys.platform == 'win32':
        user_home = os.path.join(os.environ.get('USERPROFILE'))
        if os.path.exists(user_home):
            if TEST:
                app_home_dir = os.path.join(user_home, 'pgxn_home_test')
            else:
                # for dev release, make home dir 'pgxn_home_dev'
                # for production release, make home dir 'pgxn_home'
                app_home_dir = os.path.join(user_home, 'pgxn_home_dev')
    else:
        # Linux or OSX
        user_home = os.environ.get('HOME')
        if user_home:
            if TEST:
                # if TEST mode, make home dir 'pgxn_home_test'
                app_home_dir = os.path.join(user_home, 'pgxn_home_test')
            else:
                # for dev release, make home dir 'pgxn_home_dev'
                # for production release, make home dir 'pgxn_home'
                app_home_dir = os.path.join(user_home, 'pgxn_home_dev')
    # if all else fails, create 'pgxn_home' inside the current directory --
    # not desirable because 'pgxn_home' holds user data that needs to
    # persist when a new version of the client is "installed", which typically
    # destroys the current directory.  TODO:  generate warnings if this option
    # is used.
    if not app_home_dir:
        app_home_dir = os.path.join(os.getcwd(), 'pgxn_home_dev')
    if not os.path.exists(app_home_dir):
        os.makedirs(app_home_dir, mode=0o755)
    if not os.path.exists(app_home_dir):
        os.makedirs(app_home_dir)
    # update empty 'config' with app_config ... anything in this config can be
    # overridden by user edits to the config file (loaded by Pangalaxian)
    config.update(app_config)
    ##########################################################################
    # The following steps [1]-[7] copy files into known locations within the
    # "pgxn_home"/"pgxn_home_dev" directory -- a bit messy, but it works
    ##########################################################################
    # [1] copy test model files from test/vault into the home "vault" directory
    vault_dir = os.path.join(app_home_dir, 'vault')
    current_model_files = set()
    if os.path.exists(vault_dir):
        current_model_files = set(os.listdir(vault_dir))
    else:
        os.makedirs(vault_dir, mode=0o755)
    model_files_mod_path = model_files_mod.__path__[0]
    module_model_files = set([s for s in os.listdir(model_files_mod_path)
                              if (not s.startswith('__init__')
                              and not s.startswith('__pycache__'))
                              ])
    model_files_to_copy = module_model_files - current_model_files
    if model_files_to_copy:
        for p in model_files_to_copy:
            shutil.copy(os.path.join(model_files_mod_path, p), vault_dir)
    # [2] copy server_cert.pem file from test/vault into the home directory:
    #     - 'server_cert.pem' for production
    server_cert_path = os.path.join(model_files_mod_path,
                                    'server_cert.pem')
    server_cert_target = os.path.join(app_home_dir, 'server_cert.pem')
    if (os.path.exists(server_cert_path) and
        not os.path.exists(server_cert_target)):
        shutil.copyfile(server_cert_path, server_cert_target)
    # [3] copy doc files from pgxn_docs_path** into the home directory
    #     ** NOTE: pgxn_docs_path will only exist if pangalaxian has been
    #     installed
    #     (a) as a conda package or
    #     (b) as a pyinstaller dist
    #     ... i.e., it is not part of the pangalaxian python package but is copied
    #     into the pangalaxian module by running setup.py, conda, or pyinstaller)
    pgxn_docs_path = docs.__path__[0]
    node_mod_path = pangalactic.node.__path__[0]
    docs_dir = os.path.join(app_home_dir, 'docs')
    if os.path.exists(pgxn_docs_path):
        if os.path.exists(docs_dir):
            current_doc_files = set(os.listdir(docs_dir))
            pgxn_doc_files = set([s for s in os.listdir(pgxn_docs_path)
                              if (not s.startswith('__init__')
                              and not s.startswith('__pycache__'))
                              ])
            docs_to_copy = pgxn_doc_files - current_doc_files
            for d in docs_to_copy:
                shutil.copy(os.path.join(pgxn_docs_path, d), docs_dir)
        else:
            # if 'docs' dir does not exist in pgxn_home, the entire doc tree
            # is copied over to create it (e.g., if home/doc is removed, it
            # will be "refreshed" ... a possible way to update the distributed
            # docs ...)
            shutil.copytree(pgxn_docs_path, docs_dir)
    # [4] if we are running on Windows and pyinstaller installed us, there will
    #     be a 'casroot' directory that contains files needed by pythonocc --
    #     copy them to home and set "CASROOT" env var ...
    if sys.platform == 'win32':
        casroot_path = os.path.join(node_mod_path, 'casroot')
        casroot_home = os.path.join(app_home_dir, 'casroot')
        if os.path.exists(casroot_path):
            # copy all casroot files to casroot_home dir at startup
            if os.path.exists(casroot_home):
                # if casroot_home already exists, remove it so it can be
                # recreated
                shutil.rmtree(casroot_home, ignore_errors=True)
            shutil.copytree(casroot_path, casroot_home)
            os.environ['CASROOT'] = casroot_home
    # [5] copy test data files from test/data into the "test_data" directory
    test_data_dir = os.path.join(app_home_dir, 'test_data')
    current_test_files = set()
    if os.path.exists(test_data_dir):
        current_test_files = set(os.listdir(test_data_dir))
    else:
        os.makedirs(test_data_dir, mode=0o755)
    data_mod_path = test_data_mod.__path__[0]
    data_files = set([s for s in os.listdir(data_mod_path)
                              if (not s.startswith('__init__')
                              and not s.startswith('__pycache__'))
                              ])
    data_to_copy = data_files - current_test_files
    if data_to_copy:
        for p in data_to_copy:
            shutil.copy(os.path.join(data_mod_path, p), test_data_dir)
    # output logging to console if either TEST or DEBUG is True
    console = TEST or DEBUG
    base_name = app_config['app_base_name']
    run(app_home=app_home_dir, app_base_name=base_name,
        app_version=app_version, release_mode=release_mode, splash_image=None,
        debug=DEBUG, console=console, auth_method=args.auth, use_tls=TLS)

if __name__ == '__main__':
    main()

