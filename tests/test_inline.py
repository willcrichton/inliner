from inliner import Inliner
from inliner.common import parse_module
from inliner.targets import make_target
from inliner.passes.inline import InlinePass
import difflib
import inspect


def harness(prog, target, outp, locls):
    i = Inliner(prog)
    i.inline([make_target(target)], add_comments=False)
    outp_module = i.module.with_changes(body=parse_module(outp).body)

    # Print debug information if unexpected output
    if not outp_module.deep_equals(i.module):
        print('GENERATED')
        print(i.module.code)
        print('=' * 30)
        print('TARGET')
        print(outp_module.code)
        assert False

    # Make sure we don't violate any assertions
    exec(i.module.code, locls, locls)


def test_basic():
    def target(x):
        return x + 1

    def prog():
        assert target(1) == 2

    outp = """
x___target = 1
if "target_ret" not in globals():
    target_ret = x___target + 1
assert target_ret == 2
"""

    harness(prog, target, outp, locals())


def test_args():
    def target(a, b, c=1, d=2, *args, **kwargs):
        assert (a == 1)
        assert (b == 2)
        assert (c == 2)
        assert (d == 2)
        assert (len(args) == 0)
        assert (kwargs["f"] == 4)

    def prog():
        target(1, b=2, c=2, f=4)

    outp = """
a___target = 1
b___target = 2
c___target = 2
d___target = 2
args___target = []
kwargs___target = {"f": 4}
assert (a___target == 1)
assert (b___target == 2)
assert (c___target == 2)
assert (d___target == 2)
assert (len(args___target) == 0)
assert (kwargs___target["f"] == 4)
if "target_ret" not in globals():
    target_ret = None
target_ret
"""

    harness(prog, target, outp, locals())


def test_nested():
    def target(x):
        return x + 1

    def prog():
        assert target(target(1)) == 3

    outp = """
x___target = 1
if "target_ret" not in globals():
    target_ret = x___target + 1
if "target_ret_2" not in globals():
    target_ret_2 = target_ret + 1
assert target_ret_2 == 3
"""

    harness(prog, target, outp, locals())


def test_return():
    def target():
        if True:
            x = 1
            return x
            assert False
        assert False
        return 3

    def prog():
        assert target() == 1

    outp = """
if True:
  x = 1
  if "target_ret" not in globals():
    target_ret = x
  if "target_ret" not in globals():
    assert False
if "target_ret" not in globals():
  assert False
  if "target_ret" not in globals():
    target_ret = 3
assert target_ret == 1
"""

    harness(prog, target, outp, locals())


def test_class_constructor():
    class Test:
        def __init__(self, x):
            self.x = x

    def prog():
        t = Test(1)
        assert t.x == 1

    outp = """
Test_ret = Test.__new__(Test)
x_____init__ = 1
Test_ret.x = x_____init__
t = Test_ret
assert t.x == 1
"""

    harness(prog, Test, outp, locals())


def test_class_method():
    class Test:
        def __init__(self):
            self.x = 1

        def foo(self, x):
            return x + self.x

    def prog():
        t = Test()
        assert t.foo(1) == 2

    outp = """
Test_ret = Test.__new__(Test)
Test_ret.x = 1
t = Test_ret
x___foo = 1
if "foo_ret" not in globals():
    foo_ret = x___foo + t.x
assert foo_ret == 2
"""

    harness(prog, Test, outp, locals())


def test_class_super():
    class A:
        def __init__(self):
            self.x = 1

    class B(A):
        def __init__(self):
            super().__init__()
            self.y = 1

    def prog():
        b = B()
        assert b.x + b.y == 2

    outp = """
B_ret = B.__new__(B)
A.__init__(B_ret)
B_ret.y = 1
b = B_ret
assert b.x + b.y == 2
"""

    harness(prog, B, outp, locals())


def test_generator():
    def gen():
        for i in range(10):
            yield i

    def prog():
        for i, j in zip(gen(), range(10)):
            assert i == j

    outp = """
gen_ret = []
for i in range(10):
    gen_ret.append(i)
if "gen_ret" not in globals():
    gen_ret = None
for i, j in zip(gen_ret, range(10)):
    assert i == j
"""

    harness(prog, gen, outp, locals())
