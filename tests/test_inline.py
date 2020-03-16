from inliner import Inliner
from inliner.common import parse_module
from inliner.targets import FunctionTarget
from inliner.passes.inline import InlinePass
import difflib


def harness(prog, target, outp):
    i = Inliner(prog)
    i.inline([FunctionTarget(target)], add_comments=False)
    outp_module = parse_module(outp)
    if not outp_module.deep_equals(i.module):
        print('GENERATED')
        print(i.module.code)
        print('=' * 30)
        print('TARGET')
        print(outp_module.code)
        assert False
    exec(i.module.code)


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

    harness(prog, target, outp)


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

    harness(prog, target, outp)


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

    harness(prog, target, outp)
