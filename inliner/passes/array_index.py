import ast
from .base_pass import BasePass
from ..common import a2s


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

        # Mapping from names to dict literals
        self.dicts = {}

    def visit_Assign(self, assgn):
        super().generic_visit(assgn)

        if len(assgn.targets) == 1 and isinstance(assgn.targets[0], ast.Name):
            # If assigning to an array literal, record the name/value in self.arrays
            name = assgn.targets[0].id
            if isinstance(assgn.value, ast.List):
                self.arrays[name] = assgn.value
            elif isinstance(assgn.value, ast.Dict):
                self.dicts[name] = assgn.value

        return assgn

    def _dict_lookup(self, dct, key):
        return {k.s: v for k, v in zip(dct.keys, dct.values)}[key]

    def visit_Subscript(self, expr):
        # If indexing with a constant value, then get the corresponding element
        if isinstance(expr.slice, ast.Index):
            if isinstance(expr.slice.value, ast.Num):
                const_index = expr.slice.value.n
                if isinstance(expr.value, ast.Name) and \
                   expr.value.id in self.arrays:
                    self.change = True
                    return self.arrays[expr.value.id].elts[const_index]
                elif isinstance(expr.value, ast.List):
                    self.change = True
                    return expr.value.elts[const_index]
            elif isinstance(expr.slice.value, ast.Str):
                const_str = expr.slice.value.s
                try:
                    if isinstance(expr.value, ast.Name) and \
                       expr.value.id in self.dicts:
                        elt = self._dict_lookup(self.dicts[expr.value.id],
                                                const_str)
                        self.change = True
                        return elt
                    elif isinstance(expr.value, ast.Dict):
                        elt = self._dict_lookup(expr.value, const_str)
                        self.change = True
                        return elt
                except KeyError:
                    pass

        self.generic_visit(expr)
        return expr
