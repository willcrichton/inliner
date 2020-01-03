# Inliner
[![Build Status](https://travis-ci.com/willcrichton/inliner.svg?branch=master)](https://travis-ci.com/willcrichton/inliner)

## Setup

### Python package

```
git clone https://github.com/willcrichton/inliner
cd inliner
pip3 install -e .
```

### Jupyter extension

```
pushd inliner_jupyter
npm install
npm run build
popd
```

#### Standard notebook

```
jupyter nbextension install inliner_jupyter --user -s
jupyter nbextension enable inliner_jupyter/dist/notebook --user
```

#### JupyterLab

```
jupyter labextension link inliner_jupyter
```

## Usage

See the [notebooks](https://github.com/willcrichton/inliner/tree/master/notebooks) for example usage.
