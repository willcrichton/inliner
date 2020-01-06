# Inliner
[![Build Status](https://travis-ci.com/willcrichton/inliner.svg?branch=master)](https://travis-ci.com/willcrichton/inliner)
[![PyPI version](https://badge.fury.io/py/inliner.svg)](https://badge.fury.io/py/inliner)
[![npm version](https://badge.fury.io/js/%40wcrichto%2Finliner.svg)](https://badge.fury.io/js/%40wcrichto%2Finliner)

## Setup

```bash
pip3 install inliner

# Jupyter notebook extension (optional)
jupyter nbextension enable inliner/notebook

# JupyterLab extension (optional)
jupyter labextension install @wcrichto/inliner
```

### From source

```bash
git clone https://github.com/willcrichton/inliner
cd inliner
pip3 install -e .

pushd inliner_jupyter
npm install
npm run prepublishOnly
popd

jupyter nbextension install inliner_jupyter --user -s
jupyter nbextension enable inliner_jupyter/dist/notebook --user

jupyter labextension link inliner_jupyter
```

## Usage

See the [notebooks](https://github.com/willcrichton/inliner/tree/master/notebooks) for example usage.
