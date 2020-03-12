import ast
from .base_pass import BasePass
from ..visitors import Replace


class FindVarsInComprehensions(ast.NodeVisitor):
    def __init__(self):
        self._in_comprehension = False
        self.vars = set()

    def generic_visit(self, node):
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp)):
            self._in_comprehension = True
            ret = super().generic_visit(node)
            self._in_comprehension = False
            return ret
        else:
            return super().generic_visit(node)

    def visit_Name(self, name):
        if self._in_comprehension:
            self.vars.add(name.id)


class PropagationPass(BasePass):
    tracer_args = {'trace_opcodes': True, 'trace_lines': True}

    def __init__(self, inliner):
        super().__init__(inliner)
        self.assignments = []

    def propagate(self, name, value):
        replacer = Replace(name, value)
        for stmt in self.block_remaining:
            replacer.visit(stmt)
