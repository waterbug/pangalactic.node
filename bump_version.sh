#!/bin/sh
runsed VERSION setup.py pangalactic/node/__init__.py conda/win-64/meta.yaml \
    conda/linux-64/meta.yaml pangalactic/node/pangalaxian.py

