import ast

from ..common import compare_ast
from .base_pass import BasePass


class CleanImportsPass(BasePass):
    """
    Puts all imports at the top of the module and de-duplicates them.

    Example:
      x = 1
      import foo
      import numpy
      y = foo.bar() + x

      >> becomes >>

      import foo
      x = 1
      y = foo.bar() + x
    """
    def __init__(self, inliner):
        super().__init__(inliner)
        self.imports = []

    def generic_visit(self, node):
        # Collect all imports and remove them from the module
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            self.imports.append(node)
            return None

        return super().generic_visit(node)

    def after_visit(self, mod):
        # Use exact AST equality to deduplicate imports
        imports_dedup = [
            imprt for i, imprt in enumerate(self.imports) if not any(
                [compare_ast(imprt, imprt2) for imprt2 in self.imports[i + 1:]])
        ]

        # Add imports back to the top of the module
        mod.body = imports_dedup + mod.body
