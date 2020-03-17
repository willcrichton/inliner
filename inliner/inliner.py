import inspect
import libcst as cst
import os

from .passes.inline import InlinePass
from .contexts import ctx_inliner, ctx_pass
from .common import a2s, get_function_locals, parse_module, EvalException
from .targets import make_target
from .tracer import Tracer, TRACER_FILE_PREFIX


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

    def is_source_obj(self, obj):
        """
        Checks if runtime object was defined in the inliner source.

        Requires that the executed code was run through the tracer.
        """
        try:
            srcfile = inspect.getfile(obj)
            if os.path.basename(srcfile).startswith(TRACER_FILE_PREFIX):
                return True
        except TypeError:
            pass

        return False

    def should_inline(self, code):
        """
        Checks whether an AST node is something to be inlined.
        """

        obj = self._eval(code)
        module = inspect.getmodule(obj)

        # Unconditionally inline objects defined in the source
        if self.is_source_obj(obj):
            return True

        # Don't inline builtins (they don't have source)
        if inspect.isbuiltin(obj):
            return False

        # Don't inline objects without a module
        if module is None:
            return False

        for target in self.targets:
            if target.should_inline(code, obj):
                return True

        return False

    def run_pass(self, Pass, **kwargs):
        self.cur_globls = self.base_globls.copy()
        Tracer(self.module.code, globls=self.cur_globls).trace()

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

    def _eval(self, code):
        if isinstance(code, cst.CSTNode):
            code = a2s(code)
        assert isinstance(code, str)

        try:
            return eval(code, self.cur_globls, self.cur_globls)
        except Exception as e:
            raise EvalException(e)
