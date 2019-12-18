import ast

from ..common import compare_ast
from .base_pass import BasePass


class CleanImportsPass(BasePass):
    tracer_args = None

    def __init__(self, inliner):
        super().__init__(inliner)
        self.imports = []

    def generic_visit(self, node):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            self.imports.append(node)
            return None

        return super().generic_visit(node)

    def after_visit(self, mod):
        imports_dedup = [
            imprt for i, imprt in enumerate(self.imports) if not any(
                [compare_ast(imprt, imprt2) for imprt2 in self.imports[i + 1:]])
        ]

        mod.body = imports_dedup + mod.body
