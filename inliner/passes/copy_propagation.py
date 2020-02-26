import ast
from .propagation_pass import PropagationPass
from ..common import robust_eq, is_effect_free, tree_size


class CopyPropagationPass(PropagationPass):
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
    def visit_Assign(self, stmt):
        if len(stmt.targets) == 1 and \
           isinstance(stmt.targets[0], ast.Name) and \
           isinstance(stmt.value, ast.Name):
            k = stmt.targets[0].id

            is_ssa = self.tracer.set_count[k] == self.baseline_execs

            if is_ssa:
                self.assignments.append((k, stmt.value))
                return None

        return stmt
