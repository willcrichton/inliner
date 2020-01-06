import ast
from collections import defaultdict

from ..tracer import Tracer


class RemoveEmptyBlocks(ast.NodeTransformer):
    def generic_visit(self, node):
        super().generic_visit(node)

        if hasattr(node, 'body') and \
           ((isinstance(node.body, list) and len(node.body) == 0) or \
            node.body is None):
            return None
        return node


class BasePass(ast.NodeTransformer):
    tracer_args = None

    def __init__(self, inliner):
        self.inliner = inliner

        if self.tracer_args is not None:
            if inliner._tracer_cache is not None and \
               self.tracer_args == inliner._tracer_cache[0]:
                tracer = inliner._tracer_cache[1]
            else:
                prog = inliner.make_program(comments=False)
                tracer = Tracer(prog, inliner.globls, **self.tracer_args)
                tracer.trace()
                inliner.module = ast.parse(prog)

            self.tracer = tracer
            self.globls = tracer.globls

        self.change = False

    def after_visit(self, mod):
        pass

    def visit_Module(self, mod):
        self.generic_visit(mod)
        RemoveEmptyBlocks().visit(mod)
        self.after_visit(mod)
        return mod

    def visit_FunctionDef(self, fdef):
        # Don't recurse into inline function definitions
        return fdef

    def run(self, **kwargs):
        self.args = defaultdict(lambda: None)
        for k, v in kwargs.items():
            self.args[k] = v

        self.visit(self.inliner.module)

        return self.change
