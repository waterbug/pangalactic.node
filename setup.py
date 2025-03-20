"""
Setup script for pangalactic.node, containing Pangalaxian, the Pan Galactic
Engineering Framework (PGEF) desktop GUI client.
"""
import os, site
from setuptools import setup, find_packages

VERSION = open('VERSION').read()[:-1]

doc_mod_path = os.path.join('pangalactic', 'node', 'docs')
doc_paths = [os.path.join(doc_mod_path, p)
              for p in os.listdir(doc_mod_path)
              if not p.startswith('__init__') and
              not p.startswith('images')]
doc_img_mod_path = os.path.join('pangalactic', 'node', 'docs', 'images')
doc_img_paths = [os.path.join(doc_img_mod_path, p)
              for p in os.listdir(doc_img_mod_path)
              if not p.startswith('__init__')]
icon_mod_path = os.path.join('pangalactic', 'node', 'icons')
icon_paths = [os.path.join(icon_mod_path, p)
              for p in os.listdir(icon_mod_path)
              if not p.startswith('__init__')]
image_mod_path = os.path.join('pangalactic', 'node', 'images')
image_paths = [os.path.join(image_mod_path, p)
               for p in os.listdir(image_mod_path)
               if not p.startswith('__init__')]
sitepkg_dir = [p for p in site.getsitepackages()
               if p.endswith('site-packages')][0]

long_description = (
    "pangalactic.node contains Pangalaxian, the Pan Galactic Engineering "
    "Framework (PGEF) desktop GUI client.")

setup(
    name='pangalactic.node',
    version=VERSION,
    description="Pangalaxian, the PGEF desktop client",
    long_description=long_description,
    author='Stephen Waterbury',
    author_email='stephen.c.waterbury@nasa.gov',
    maintainer="Stephen Waterbury",
    maintainer_email='waterbug@pangalactic.us',
    license='TBD',
    packages=find_packages(),
    data_files=[
        # doc files
        (os.path.join(sitepkg_dir, doc_mod_path), doc_paths),
        # doc image files
        (os.path.join(sitepkg_dir, doc_img_mod_path), doc_img_paths),
        # icon files
        (os.path.join(sitepkg_dir, icon_mod_path), icon_paths),
        # image files
        (os.path.join(sitepkg_dir, image_mod_path), image_paths)
        ],
    zip_safe=False
)

