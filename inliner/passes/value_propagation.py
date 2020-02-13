import ast
from .propagation_pass import PropagationPass
from ..common import robust_eq, is_effect_free, tree_size

MAX_TREESIZE = 10  # TODO: good value for this?


class ValuePropagationPass(PropagationPass):
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

            var_is_ssa = self.tracer.set_count[k] == self.baseline_execs
            # TODO: use val_eq? check if variable use syntactically occurs once in program?
            can_propagate_value = len(
                self.tracer.reads[k]) == self.baseline_execs
            value_is_pure = is_effect_free(stmt.value)
            value_not_name = not isinstance(stmt.value, ast.Name)
            can_propagate_var = var_is_ssa and can_propagate_value and value_is_pure \
                and value_not_name

            should_propagate_var = k not in self.inliner.toplevel_vars and \
                tree_size(stmt.value) <= MAX_TREESIZE

            if can_propagate_var and should_propagate_var:
                self.assignments.append((k, stmt.value))
                return None

        return stmt
