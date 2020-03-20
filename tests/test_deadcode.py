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

    outp = """
if True:
    x = 1
"""

    run_pass_harness(prog, DeadCodePass, outp, locals())
