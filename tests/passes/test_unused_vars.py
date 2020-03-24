from utils import run_pass_harness
from inliner.passes.unused_vars import UnusedVarsPass


def test_unused_vars_noop():
    def prog():
        x = 1
        assert x == 1

    def outp():
        x = 1
        assert x == 1

    run_pass_harness(prog, UnusedVarsPass, outp, locals())


def test_unused_vars_basic():
    def prog():
        x = 1
        assert True

    def outp():
        assert True

    run_pass_harness(prog, UnusedVarsPass, outp, locals())


def test_unused_vars_copy():
    def prog():
        x = 1
        y = x

    def outp():
        x = 1

    run_pass_harness(prog, UnusedVarsPass, outp, locals())


def test_unused_vars_impure():
    def f():
        pass

    def prog():
        x = f()

    def outp():
        x = f()

    run_pass_harness(prog, UnusedVarsPass, outp, locals())
