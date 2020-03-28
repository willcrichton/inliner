import inspect

import libcst as cst

from .common import EvalException, a2s, get_function_locals, parse_module
from .contexts import ctx_inliner, ctx_pass
from .passes import (PASSES, CleanImportsPass, CopyPropagationPass,
                     DeadCodePass, InlinePass, RecordToVarsPass,
                     RemoveSuffixesPass, UnusedVarsPass)
from .targets import make_target


class Inliner:
    def __init__(self, program, globls=None, targets=None, add_comments=True):
        if type(program) is not str:
            assert inspect.isfunction(program)
            if globls is None and hasattr(program, '__globals__'):
                globls = {**program.__globals__, **get_function_locals(program)}
            source = inspect.getsource(program)
            mod = parse_module(source)
            mod = mod.with_changes(body=mod.body[0].body.body)
        else:
            source = program
            mod = parse_module(source)

        self.module = mod
        self.base_globls = globls.copy() if globls is not None else {}
        self.cur_globls = self.base_globls.copy()

        self.add_comments = add_comments
        self.length_inlined = 0
        self.targets = targets if targets is not None else []

    def _name_to_pass(self, name):
        return next(p for p in PASSES if p.name() == name)

    def run_pass(self, Pass, **kwargs):
        orig_module = self.module
        with ctx_inliner.set(self):
            if isinstance(Pass, str):
                Pass = self._name_to_pass(Pass)
            pass_ = Pass(**kwargs)

            with ctx_pass.set(pass_):
                self.module = pass_.execute(self.module)

        return not orig_module.deep_equals(self.module)

    def add_target(self, target):
        target = make_target(target)
        self.targets.append(target)
        return target

    def remove_target(self, target):
        self.targets.remove(target)

    def optimize(self, passes=None):
        if passes is None:
            passes = [
                InlinePass,
                DeadCodePass,
                CopyPropagationPass,
                UnusedVarsPass,
                CleanImportsPass,
            ]

        def run_passes():
            any_change = False
            for Pass in passes:
                any_change |= self.run_pass(Pass)
            return any_change

        return (self.fixpoint(run_passes) | self.run_pass(RecordToVarsPass)
                | self.fixpoint(run_passes) | self.run_pass(RemoveSuffixesPass))

    def fixpoint(self, f, *args, **kwargs):
        any_change = False
        while True:
            changed = f(*args, **kwargs)
            any_change |= any_change
            if not changed:
                return any_change

    def code(self):
        return self.module.code

    def eval(self, code, globls=None):
        if isinstance(code, cst.CSTNode):
            code = a2s(code)
        assert isinstance(code, str)

        globls = globls.copy() if globls is not None else self.base_globls

        try:
            return eval(code, globls, globls)
        except Exception as e:
            raise EvalException(e)

    def execute(self):
        globls = self.base_globls.copy()
        exec(self.module.code, globls, globls)
