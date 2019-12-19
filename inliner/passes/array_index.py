import ast
from .base_pass import BasePass


class ArrayIndexPass(BasePass):
    """
    Inline indexes into array literals.

    Example:
      x = [1, 2]
      y = x[0]

      >> becomes >>

      y = 1

    Example:
      y = [1, 2][0]

      >> becomes >>

      y = 1
    """
    def __init__(self, inliner):
        super().__init__(inliner)

        # Mapping from names to array literals
        self.arrays = {}

    def visit_Assign(self, assgn):
        super().generic_visit(assgn)

        # If assigning to an array literal, record the name/value in self.arrays
        if isinstance(assgn.value, ast.List) and \
           len(assgn.targets) == 1 and isinstance(assgn.targets[0], ast.Name):
            self.arrays[assgn.targets[0].id] = assgn.value

        return assgn

    def visit_Subscript(self, expr):
        # If indexing with a constant value, then get the corresponding element
        if isinstance(expr.slice, ast.Index) and \
           isinstance(expr.slice.value, ast.Num):
            const_index = expr.slice.value.n

            if isinstance(expr.value, ast.Name) and \
               expr.value.id in self.arrays:
                self.change = True
                return self.arrays[expr.value.id].elts[const_index]

            elif isinstance(expr.value, ast.List):
                self.change = True
                return expr.value.elts[const_index]

        self.generic_visit(expr)
        return expr
