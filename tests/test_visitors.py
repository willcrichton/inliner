from inliner.passes.base_pass import TrimWhitespace
from inliner.visitors import rename
from utils import run_visitor_harness, assert_code_equals, func_to_module


def test_trim_whitespace():
    # yapf: disable
    def inp():
        # hello


        world

        if True:


            # ok


            pass

        """multi
        line"""
        """"""

    # yapf: disable
    def outp():
        # hello

        world

        if True:

            # ok

            pass

        """multi"""
        """"""

    run_visitor_harness(inp, outp, TrimWhitespace())


def test_rename():
    def inp():
        x = 1
        if x:
            y = [x for _ in range(10)]
            z = [x for x in range(10)]

        def foo(x):
            return x

        def bar(y=x):
            return x

    def outp():
        w = 1
        if w:
            y = [w for _ in range(10)]
            z = [x for x in range(10)]

        def foo(x):
            return x

        def bar(y=w):
            return w

    generated_outp = rename(func_to_module(inp), "x", "w")
    assert_code_equals(func_to_module(outp), generated_outp)
