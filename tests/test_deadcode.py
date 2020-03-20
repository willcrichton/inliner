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
