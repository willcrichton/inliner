import libcst as cst
import os
import inspect
from collections import defaultdict

from ..common import a2s, EvalException
from ..visitors import RemoveEmptyBlocks
from ..contexts import ctx_inliner
from ..tracer import Tracer, TRACER_FILE_PREFIX


class BasePass(RemoveEmptyBlocks):
    tracer_args = None

    def __init__(self):
        super().__init__()
        self.inliner = ctx_inliner.get()
        self.generated_vars = defaultdict(int)

        if self.tracer_args is not None:
            self.tracer = Tracer(self.inliner.module.code,
                                 globls=self.inliner.base_globls,
                                 **self.tracer_args).trace()

        self.after_init()

    def after_init(self):
        pass

    def eval(self, code):
        if isinstance(code, cst.CSTNode):
            code = a2s(code)
        assert isinstance(code, str)

        try:
            return eval(code, self.tracer.globls, self.tracer.globls)
        except Exception as e:
            raise EvalException(e)

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

        obj = self.eval(code)
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

        for target in self.inliner.targets:
            if target.should_inline(code, obj):
                return True

        return False

    def fresh_var(self, prefix):
        """
        Creates a new variable semi-guaranteed to not exist in the program.
        """
        self.generated_vars[prefix] += 1
        count = self.generated_vars[prefix]
        if count == 1:
            return f'{prefix}'
        else:
            return f'{prefix}_{count}'

    def visit_FunctionDef(self, fdef):
        super().visit_FunctionDef(fdef)
        # Don't recurse into inline function definitions
        return False
