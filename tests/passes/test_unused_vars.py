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


def test_unused_vars_multiple_assign():
    def prog():
        y = 1
        y = y + 1
        x = 1
        x = 2
        assert x + y == 4

    def outp():
        y = 1
        y = y + 1
        x = 2
        assert x + y == 4

    run_pass_harness(prog, UnusedVarsPass, outp, locals())


def test_unused_vars_closure():
    def prog():
        def a():
            return x + b()

        x = 1

        def b():
            return 1

        def c():
            return a()

        assert a() == 2

    def outp():
        def a():
            return x + b()

        x = 1

        def b():
            return 1

        assert a() == 2

    run_pass_harness(prog, UnusedVarsPass, outp, locals())


def test_unused_vars_comprehension():
    def prog():
        x = 1
        z = [x + y for y in range(10)]
        assert z[0] == 1

    def outp():
        x = 1
        z = [x + y for y in range(10)]
        assert z[0] == 1

    run_pass_harness(prog, UnusedVarsPass, outp, locals())
