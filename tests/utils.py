from inliner import Inliner
from inliner.common import parse_module, parse_statement
import inspect


def run_pass_harness(prog, pass_, outp, locls, fixpoint=False):
    i = Inliner(prog, globls=locls, add_comments=False)

    if not inspect.isfunction(pass_):
        method = lambda: i.run_pass(pass_)
    else:
        method = pass_(i)

    if fixpoint:
        i.fixpoint(method)
    else:
        method()

    if inspect.isfunction(outp):
        outp_module = i.module.with_changes(
            body=parse_statement(inspect.getsource(outp)).body.body)
    else:
        outp_module = i.module.with_changes(body=parse_module(outp).body)

    # Print debug information if unexpected output
    if not outp_module.deep_equals(i.module):
        print('GENERATED')
        print(i.module.code)
        print('=' * 30)
        print('TARGET')
        print(outp_module.code)
        assert False

    # Make sure we don't violate any assertions in generated code
    exec(i.module.code, locls, locls)
