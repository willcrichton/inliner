from utils import run_pass_harness
from inliner.passes.deadcode import DeadCodePass


def test_deadcode_noop():
    def prog():
        x = 1

    outp = "x = 1"

    run_pass_harness(prog, DeadCodePass, outp, locals())


def test_deadcode_if():
    def prog():
        if True:
            x = 1
        else:
            y = 1

    outp = "x = 1"

    run_pass_harness(prog, DeadCodePass, outp, locals())


def test_deadcode_else():
    def prog():
        if False:
            x = 1
        else:
            y = 1

    outp = "y = 1"

    run_pass_harness(prog, DeadCodePass, outp, locals())


def test_deadcode_for_if_always():
    def prog():
        for i in range(10):
            if True:
                x = 1
            else:
                y = 1

    outp = """
for i in range(10):
    x = 1
"""

    run_pass_harness(prog, DeadCodePass, outp, locals())


def test_deadcode_for_if_sometimes():
    def prog():
        for i in range(10):
            if i % 2 == 1:
                x = 1
            else:
                y = 1

    outp = """
for i in range(10):
    if i % 2 == 1:
        x = 1
    else:
        y = 1
"""

    run_pass_harness(prog, DeadCodePass, outp, locals())


def test_deadcode_for_if_never():
    def prog():
        for i in range(10):
            if False:
                x = 1
            else:
                y = 1

    outp = """
for i in range(10):
    y = 1
"""

    run_pass_harness(prog, DeadCodePass, outp, locals())


def test_deadcode_try_except():
    def prog():
        try:
            raise KeyError()
        except KeyError:
            x = 1

    outp = "x = 1"

    run_pass_harness(prog, DeadCodePass, outp, locals())


def test_deadcode_try_noexcept():
    def prog():
        try:
            x = 1
        except KeyError:
            pass

    outp = "x = 1"

    run_pass_harness(prog, DeadCodePass, outp, locals())


def test_deadcode_pure_expr():
    import json

    def f():
        return 1

    def prog():
        # impure
        x = 1
        f()
        x + f()
        # pure
        x
        x + 1
        {'a': 1}
        [0][0]
        json.loads
        ((1))

    def outp():
        # impure
        x = 1
        f()
        x + f()
        # pure

    run_pass_harness(prog, DeadCodePass, outp, locals())


def test_deadcode_keep_comments():
    def prog():
        # hello world
        """don't remove me"""
        # please remove me
        if False:
            # and remove me
            pass
        # please keep me
        else:
            # and keep me
            pass

    def outp():
        # hello world
        """don't remove me"""
        # please keep me
        # and keep me
        pass

    run_pass_harness(prog, DeadCodePass, outp, locals())
