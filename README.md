# Inliner
[![Build Status](https://travis-ci.com/willcrichton/inliner.svg?branch=master)](https://travis-ci.com/willcrichton/inliner)
[![PyPI version](https://badge.fury.io/py/inliner.svg)](https://badge.fury.io/py/inliner)
[![npm version](https://badge.fury.io/js/%40wcrichto%2Finliner.svg)](https://badge.fury.io/js/%40wcrichto%2Finliner)

Inliner is a tool to make it easier to understand how a library works through code examples. As a simple example, consider a library that has this function:

```python
# library.py
def foo(x, edge_case=False):
  if edge_case:
    return x + 1
  else:
    return x * 2

# client.py
from library import foo
y = foo(2)
```

To understand how `foo` works, you would normally have to read the documentation or source code. But here, `foo` has edge cases encoded as parameters with default values. If you only care about the code paths used in your specific example, then you can ignore the unused branches. The inliner can transform this code into:

```python
# client.py
x = 2
y = x * 2
```

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
