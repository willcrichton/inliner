from inliner.passes.base_pass import TrimWhitespace
from utils import run_visitor_harness


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
