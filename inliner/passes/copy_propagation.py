import ast
from .base_pass import BasePass
from ..common import robust_eq, is_effect_free, tree_size
from ..visitors import Replace

MAX_TREESIZE = 10  # TODO: good value for this?


class CopyPropagationPass(BasePass):
    """
    Copies values read once into their point of use.

    Copy propagation has two components: CAN a value be propagated, and
    SHOULD it be.

    * CAN: copy propagation is challenging in the presence of an effect. Most
           definitions cannot be trivially inlined. For now, I define a
           variable assignment can be safely propagated if any are true:
      - the variable is not modified during its execution, i.e.
        its value on the first read is equal to the last read
      - it's read exactly once (or generally N times, under a loop with
        N iterations)
      - the assignment is a direct alias, e.g. x = y

    * SHOULD: even if a propagation is safe, arbitrarily inlining values
              can make the code difficult to read. Variables are useful
              tools to break up long segments of code. So I use a few
              heuristics to determine whether a syntax object can be inlined.
      - The size of its syntax tree is less than MAX_TREESIZE nodes
      - The variable must be one that was generated during inlining, not from
        the original script

    Example:
      x = {'a': 1}
      y = x['a']
      assert y == 1

      >> becomes >>

      assert {'a': 1}['a'] == 1

    Example:
      sum = 0
      for i in range(10):
        x = i * 10
        sum += x

      >> becomes >>

      sum = 0
      for i in range(10):
        sum += i * 10
    """

    tracer_args = {'trace_opcodes': True, 'trace_lines': True}

    def __init__(self, inliner):
        super().__init__(inliner)
        self.assignments = []
        self.baseline_execs = 1

    def visit_With(self, stmt):
        # For now, don't do any propagation on assignments within with blocks
        # to avoid moving statements outside the block
        return stmt

    def visit_Assign(self, stmt):
        if len(stmt.targets) == 1 and \
           isinstance(stmt.targets[0], ast.Name):
            k = stmt.targets[0].id

            # Attempt to determine whether the variable's value changed
            # during tracing. robust_eq is... marginally robust.
            try:
                val_eq = len(self.tracer.reads[k]) == 0 or \
                   bool(robust_eq(self.tracer.reads[k][0][0],
                                  self.tracer.reads[k][-1][0]))
            except Exception as e:
                # TODO: do some better kind of logging here
                print('WARNING: could not compare for equality on key `{}`:'.
                      format(k))
                print('Inital', str(self.tracer.reads[k][0][0])[:100])
                print('Final', str(self.tracer.reads[k][-1][0])[:100])
                print(e)
                print('=' * 30)

                val_eq = False

            can_propagate = (val_eq or
                len(self.tracer.reads[k]) == self.baseline_execs or
                isinstance(stmt.value, ast.Name)) and \
                is_effect_free(stmt.value)

            should_propagate = k not in self.inliner.toplevel_vars and \
                tree_size(stmt.value) <= MAX_TREESIZE

            if self.tracer.set_count[k] == self.baseline_execs and \
               can_propagate and should_propagate:
                self.assignments.append((k, stmt.value))
                return None

        return stmt

    def after_visit(self, mod):
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
