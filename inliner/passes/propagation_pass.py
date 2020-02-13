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

    def after_visit(self, mod):
        #### TODO: iirc issue in detectron2 was that comprehensions are implicit closures,
        # and if a variable is captured in a closure then its read isn't logged.
        # option 1: detect if variable is in a closure?
        # option 2: extend tracer to closures defined in main program. <-- ideal but harder

        # finder = FindVarsInComprehensions()
        # finder.visit(mod)
        # assignments = [(name, value) for name, value in self.assignments
        #                if name not in finder.vars]

        # Once we have collected the copyable assignments, go through and
        # replace every usage of them
        for i, (name, value) in enumerate(self.assignments):
            replacer = Replace(name, value)
            replacer.visit(mod)

            # Have to update not just the main AST, but also any copyable
            # assignments that might reference copies. For example:
            #
            # x = 1
            # y = x
            # z = y
            #
            # After copying x, self.assignments will still have y = x, so
            # a naive copy of y = x into z will then produce the program z = x
            # with no definition of x.
            for j, (name2, value2) in enumerate(self.assignments[i + 1:]):
                self.assignments[i + 1 + j] = (name2, replacer.visit(value2))

        self.change = len(self.assignments) > 0
