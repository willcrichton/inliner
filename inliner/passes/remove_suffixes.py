import ast

from .base_pass import BasePass
from ..common import SEP, parse_expr, COMMENT_MARKER, a2s, Comment
from collections import defaultdict


# TODO: this breaks for variables in source-level closures
# e.g. x = 1; def foo(): return x
class RemoveSuffixesPass(BasePass):
    """
    Remove the debug suffixes applied during inlining to avoid name clashes.

    Example:
      x__foo = 1
      x__bar = 2
      assert x__foo + x__bar == 3

      >> becomes >>

      x = 1
      x_2 = 2
      assert x + x_2 == 3
    """
    def __init__(self, inliner):
        super().__init__(inliner)
        self.name_map = {}

    def visit_Name(self, name):
        parts = name.id.split(SEP)
        if len(parts) > 1:
            base = parts[0]
            if name.id not in self.name_map:
                self.name_map[name.id] = self.inliner.fresh(base)
            name.id = self.name_map[name.id]
        return name

    def visit_Expr(self, expr):
        if isinstance(expr.value, ast.Str):
            comment = Comment.from_str(expr.value)

            if comment is not None:
                call = parse_expr(comment.code)
                name_map = self.name_map.copy()
                generated_vars = self.inliner.generated_vars.copy()
                self.name_map = {}
                self.inliner.generated_vars = defaultdict(int)
                self.visit(call)
                self.inliner.generated_vars = generated_vars
                self.name_map = name_map

                return comment.to_stmt()

        self.generic_visit(expr)
        return expr
