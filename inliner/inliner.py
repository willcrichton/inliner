import inspect
import libcst as cst

from .passes.inline import InlinePass
from .contexts import ctx_inliner, ctx_pass
from .common import a2s, get_function_locals, parse_module
from .targets import make_target


class Inliner:
    def __init__(self, program, globls=None):
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

        self.length_inlined = 0

    def run_pass(self, Pass, **kwargs):
        orig_module = self.module
        with ctx_inliner.set(self):
            pass_ = Pass(**kwargs)
            with ctx_pass.set(pass_):
                self.module = cst.MetadataWrapper(self.module).visit(pass_)

        return not orig_module.deep_equals(self.module)

    def inline(self, targets, **kwargs):
        self.targets = [make_target(t) for t in targets]
        return self.run_pass(InlinePass, **kwargs)

    def optimize(self, passes):
        pass

    def fixpoint(self, f, *args, **kwargs):
        while True:
            if not f(*args, **kwargs):
                return
