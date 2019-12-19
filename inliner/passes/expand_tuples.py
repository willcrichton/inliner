import ast
from .base_pass import BasePass


class ExpandTuplesPass(BasePass):
    """
    Expand tuple assignments to multiple variable assignments.

    Useful for making tuple assignments optimizable by other passes like copy
    propagation.

    Example:
      x, y = (1, 2)

      >> becomes >>

      x = 1
      y = 2
    """
    def visit_Assign(self, stmt):
        if isinstance(stmt.value, ast.Tuple):
            # x, y = tuple
            if len(stmt.targets) > 1:
                targets = stmt.targets
            # (x, y) = tuple
            elif isinstance(stmt.targets[0], ast.Tuple):
                targets = stmt.targets[0].elts
            else:
                return stmt

            self.change = True
            return [
                ast.Assign(targets=[name], value=elt)
                for name, elt in zip(targets, stmt.value.elts)
            ]

        return stmt
