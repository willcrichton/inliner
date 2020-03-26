from inliner import Inliner
from inliner.common import parse_module, parse_statement
from inliner.targets import make_target

import libcst as cst
import inspect


def func_to_module(f):
    func = parse_statement(inspect.getsource(f))
    return cst.Module(body=func.body.body)


def run_visitor_harness(inp, outp, visitor):
    inp = func_to_module(inp)
    target_outp = func_to_module(outp)
    generated_outp = cst.MetadataWrapper(inp).visit(visitor)

    target_code = target_outp.code
    generated_code = generated_outp.code
    if generated_code != target_code:
        print('GENERATED')
        print(generated_code)
        print('=' * 30)
        print('TARGET')
        print(target_code)
        print('=' * 30)
        assert False


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
    generated_code = i.module.code
    target_code = outp_module.code
    if generated_code != target_code:
        print('GENERATED')
        print(generated_code)
        print('=' * 30)
        print('TARGET')
        print(target_code)
        print('=' * 30)
        assert False

    # Make sure we don't violate any assertions in generated code
    exec(i.module.code, locls, locls)


def run_inline_harness(prog, target, outp, locls, **kwargs):
    targets = [make_target(t) for t in target] if isinstance(
        target, list) else [make_target(target)]

    def method(i):
        for t in targets:
            i.add_target(t)

        def inner():
            return i.run_pass('inline')

        return inner

    return run_pass_harness(prog, method, outp, locls, **kwargs)


def run_optimize_harness(prog, target, outp, locls):
    targets = [make_target(t) for t in target] if isinstance(
        target, list) else [make_target(target)]

    def method(i):
        for t in targets:
            i.add_target(t)

        def inner():
            return i.run_pass('inline') | i.optimize()

        return inner

    return run_pass_harness(prog, method, outp, locls, fixpoint=True)
