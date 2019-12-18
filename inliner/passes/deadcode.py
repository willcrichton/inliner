import ast

from .base_pass import BasePass
from ..visitors import CollectLineNumbers
from ..common import a2s


class DeadcodePass(BasePass):
    tracer_args = {'trace_opcodes': True, 'trace_lines': True}

    def _is_comment(self, node):
        return isinstance(node, ast.Expr) and \
            isinstance(node.value, ast.Str) and \
            node.value.s.startswith('__comment')

    def _len_without_comment(self, stmts):
        return len([s for s in stmts if not self._is_comment(s)])

    def _is_dead(self, node):
        collect_lineno = CollectLineNumbers()
        collect_lineno.visit(node)
        return sum(
            [self.tracer.execed_lines[i] for i in collect_lineno.linenos]) == 0

    def generic_visit(self, node):
        if self._is_comment(node):
            return node

        if isinstance(node, (ast.Assign, ast.Expr)) and self._is_dead(node):
            self.change = True
            return None

        return super().generic_visit(node)

    def visit_If(self, stmt):
        # TODO: assumes pure conditions
        if self._len_without_comment(stmt.body) == 0 or self._is_dead(
                stmt.body[0]):
            self.change = True
            return stmt.orelse
        elif self._len_without_comment(stmt.orelse) == 0 or self._is_dead(
                stmt.orelse[0]):
            self.change = True
            return stmt.body

        self.generic_visit(stmt)
        return stmt

    def visit_For(self, stmt):
        if self._len_without_comment(stmt.body) == 0:
            self.change = True
            return None

        self.generic_visit(stmt)
        return stmt

    def visit_Expr(self, stmt):
        if self._is_comment(stmt):
            return stmt

        if isinstance(stmt.value, (ast.Name, ast.Str, ast.NameConstant)):
            self.change = True
            return None

        self.generic_visit(stmt)
        return stmt

    def visit_Try(self, stmt):
        if not self._is_dead(stmt.handlers[0]):
            # HUGE HACK: assumes it's safe to replace try/except
            # with just except block if except block not dead
            assert self._len_without_comment(stmt.handlers) == 1
            assert stmt.handlers[0].name is None
            self.change = True
            return stmt.handlers[0].body
        else:
            self.change = True
            return stmt.body
