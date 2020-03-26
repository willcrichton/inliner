from utils import run_pass_harness
from inliner.passes.remove_suffixes import RemoveSuffixesPass


def test_remove_suffixes_basic():
    def prog():
        x___foo = 1

        def foo___bar():
            y___foo.x___foo = 1

    def outp():
        x = 1

        def foo():
            y.x___foo = 1

    run_pass_harness(prog, RemoveSuffixesPass, outp, locals())
