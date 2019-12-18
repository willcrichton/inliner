import ast
from .base_pass import BasePass
from ..common import robust_eq
from ..visitors import Replace

MAX_TREESIZE = 10  # TODO: good value for this?


class ShouldCopyPropagate(ast.NodeVisitor):
    def __init__(self):
        self.size = 0
        self.has_call = False

    def should_propagate(self, name, generated_vars):
        return (name.split('_')[0] in generated_vars) or \
            (self.size <= MAX_TREESIZE and not self.has_call)

    def generic_visit(self, node):
        self.size += 1
        super().generic_visit(node)

    def visit_Call(self, node):
        self.has_call = True
        self.generic_visit(node)


class CopyPropagationPass(BasePass):
    tracer_args = {'trace_opcodes': True, 'trace_lines': True}

    def __init__(self, inliner):
        super().__init__(inliner)
        self.assignments = []
        self.baseline_execs = 1

    def after_visit(self, mod):
        for i, (name, value) in enumerate(self.assignments):
            replacer = Replace(name, value)
            replacer.visit(mod)
            for j, (name2, value2) in enumerate(self.assignments[i + 1:]):
                self.assignments[i + 1 + j] = (name2, replacer.visit(value2))

        self.change = len(self.assignments) > 0

    def visit_For(self, loop):
        loop_iters = self.tracer.execed_lines[loop.lineno] - 1
        if loop_iters > 0:
            self.baseline_execs *= loop_iters
            self.generic_visit(loop)
            self.baseline_execs /= loop_iters
        return loop

    def visit_Assign(self, stmt):
        if len(stmt.targets) == 1 and \
           isinstance(stmt.targets[0], ast.Name):
            k = stmt.targets[0].id
            try:
                val_eq = len(self.tracer.reads[k]) == 0 or \
                   bool(robust_eq(self.tracer.reads[k][0][0],
                                  self.tracer.reads[k][-1][0]))
            except Exception as e:
                print('WARNING: could not compare for equality on key `{}`:'.
                      format(k))
                print('Inital', str(self.tracer.reads[k][0][0])[:100])
                print('Final', str(self.tracer.reads[k][-1][0])[:100])
                print(e)
                print('=' * 30)

                val_eq = False

            can_propagate = val_eq or \
                len(self.tracer.reads[k]) == self.baseline_execs or \
                isinstance(stmt.value, ast.Name)

            should_prop = ShouldCopyPropagate()
            should_prop.visit(stmt.value)

            if self.tracer.set_count[k] == self.baseline_execs and \
               can_propagate and \
               should_prop.should_propagate(k, self.inliner.generated_vars):
                self.assignments.append((k, stmt.value))
                return None

        return stmt
