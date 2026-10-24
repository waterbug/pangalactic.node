#!/bin/sh
runsed VERSION pyproject.toml \
    pangalactic/node/__init__.py \
    conda/win-64/meta.yaml \
    conda/linux-64/meta.yaml \
    pangalactic/node/pangalaxian.py

