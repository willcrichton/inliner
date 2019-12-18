import ast
from .base_pass import BasePass


class ExpandTuplesPass(BasePass):
    tracer_args = None

    def visit_Assign(self, stmt):
        if isinstance(stmt.value, ast.Tuple):
            if len(stmt.targets) > 1:
                targets = stmt.targets
            elif isinstance(stmt.targets[0], ast.Tuple):
                targets = stmt.targets[0].elts
            else:
                return stmt

            if all([
                    isinstance(elt,
                               (ast.Name, ast.Num, ast.Str, ast.NameConstant,
                                ast.Attribute, ast.Tuple))
                    for elt in stmt.value.elts
            ]):
                self.change = True
                return [
                    ast.Assign(targets=[name], value=elt)
                    for name, elt in zip(targets, stmt.value.elts)
                ]

        return stmt
