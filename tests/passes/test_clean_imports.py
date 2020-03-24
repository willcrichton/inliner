from utils import run_pass_harness
from inliner.passes.clean_imports import CleanImportsPass


def test_clean_imports_sort():
    def prog():
        import json
        import csv

    outp = """
import csv
import json
"""

    run_pass_harness(prog, CleanImportsPass, outp, locals())


def test_clean_imports_redundant():
    def prog():
        import json
        import json

    outp = """
import json
"""

    run_pass_harness(prog, CleanImportsPass, outp, locals())


def test_clean_imports_move_to_top():
    def prog():
        x = 1
        import json

    outp = """
import json
x = 1
"""

    run_pass_harness(prog, CleanImportsPass, outp, locals())
