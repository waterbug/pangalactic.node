"""
Setup script for pangalactic.node, containing Pangalaxian, the Pan Galactic
Engineering Framework (PGEF) desktop GUI client.
"""
from setuptools import setup, find_packages

VERSION = open('VERSION').read()[:-1]

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
    zip_safe=False
)

