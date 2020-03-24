import libcst as cst
import os
import inspect
from collections import defaultdict
from typing import Dict, Any, Optional, cast, DefaultDict
import re

from ..common import a2s, EvalException
from ..visitors import RemoveEmptyBlocks
from ..contexts import ctx_inliner
from ..tracer import Tracer, TRACER_FILE_PREFIX, TracerArgs


class BasePass(RemoveEmptyBlocks):
    tracer_args: Optional[TracerArgs] = None
    tracer: Optional[Tracer]
    generated_vars: DefaultDict[str, int]

    def __init__(self) -> None:
        super().__init__()
        self.inliner = ctx_inliner.get()
        self.generated_vars = defaultdict(int)
        self.tracer = None

    def eval(self, code):
        return self.inliner.eval(
            code, self.tracer.globls if self.tracer_args is not None else None)

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

    def visit_FunctionDef(self, node) -> bool:
        super().visit_FunctionDef(node)
        # Don't recurse into inline function definitions
        return False

    def visit_Module(self, node) -> None:
        super().visit_Module(node)
        if self.tracer_args:
            self.tracer = Tracer(node, self.inliner.base_globls,
                                 self.tracer_args).trace()
            self.globls = self.tracer.globls

    @classmethod
    def name(cls) -> str:
        # Get class name
        name = cls.__name__

        # Split "TheFooPass" into ["The", "Foo", "Pass"]
        parts = re.findall('.[^A-Z]*', name)

        # Drop "Pass"
        parts = parts[:-1]

        # Make "the_foo"
        return '_'.join([s.lower() for s in parts])
