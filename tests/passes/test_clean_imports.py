from utils import run_pass_harness
from inliner.passes.clean_imports import CleanImportsPass
from pytest import mark


def test_clean_imports_sort():
    def prog():
        import json
        import csv

    def outp():
        import csv
        import json

    run_pass_harness(prog, CleanImportsPass, outp, locals())


def test_clean_imports_redundant():
    def prog():
        import json
        import json

    def outp():
        import json

    run_pass_harness(prog, CleanImportsPass, outp, locals())


def test_clean_imports_move_to_top():
    def prog():
        x = 1
        import json

    def outp():
        import json
        x = 1

    run_pass_harness(prog, CleanImportsPass, outp, locals())


def test_clean_imports_preserve_comments():
    def prog():
        # A
        import json

        # B
        import csv
        if True:
            # C
            import json
            pass

    def outp():
        import csv
        import json
        # A

        # B
        if True:
            # C
            pass

    run_pass_harness(prog, CleanImportsPass, outp, locals())


def test_clean_imports_whitespace():
    def prog():
        import json

        import csv
        x = 1

    def outp():
        import csv
        import json

        x = 1

    run_pass_harness(prog, CleanImportsPass, outp, locals(), fixpoint=True)
