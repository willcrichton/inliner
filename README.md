# Inliner
[![Build Status](https://travis-ci.com/willcrichton/inliner.svg?branch=master)](https://travis-ci.com/willcrichton/inliner)
[![PyPI version](https://badge.fury.io/py/inliner.svg)](https://badge.fury.io/py/inliner)
[![npm version](https://badge.fury.io/js/%40wcrichto%2Finliner.svg)](https://badge.fury.io/js/%40wcrichto%2Finliner)

Inliner is a tool that inlines function calls from external libraries in a human-readable way. Inlining can be useful to:

* Understand how individual code paths in a library work, instead of every edge case
* Work around the limitations of a library by tweaking the inlined source code

The inliner has a Python API as well as an interactive GUI that you can use in Jupyter or JupyterLab notebooks.

## Example

As a simple example, consider a library that has this function:

```python
# library.py
def foo(x, edge_case=False):
  if edge_case:
    return x + 1
  else:
    return x * 2

# client.py
from library import foo
x = 2
y = foo(x)
print(y) # 4
```

To understand how `foo` works, you would normally have to read the documentation or source code. But this can be challenging since e.g. here, `foo` has edge cases encoded as parameters with default values.

If you only care about the code paths used in your specific example, then these edge cases only hinder your understanding. The inliner can turn the client code above into a specialized version removing any code from `library`, for example:

```python
def client():
  from library import foo
  x = 2
  y = foo(x)
  print(y) # 4

from inliner import Inliner
i = Inliner(client, ['library'])
i.simplify()
print(i.make_program())
```

The `Inliner` class takes the code snippet as input along with a list of modules to inline. Then `simplify` performs a series of inlining and cleaning passes until reaching a fixpoint, then outputting this program:

```python
x = 2

# foo(x)
foo_ret = x * 2
y = foo_ret
print(y)
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
