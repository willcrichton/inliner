from utils import run_pass_harness
from inliner.passes.record_to_vars import RecordToVarsPass


def test_record_to_vars_noop():
    class Cls:
        pass

    def prog():
        c = Cls()
        c.x = 1
        assert c.x == 1

    def outp():
        c = Cls()
        c.x = 1
        assert c.x == 1

    run_pass_harness(prog, RecordToVarsPass, outp, locals())


def test_record_to_vars_basic():
    class Cls:
        pass

    def prog():
        c = Cls.__new__(Cls)
        c.x = 1
        assert c.x == 1

    def outp():
        x___c = 1
        assert x___c == 1

    run_pass_harness(prog, RecordToVarsPass, outp, locals())
