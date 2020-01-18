import ast

from .base_pass import BasePass
from ..visitors import CollectLineNumbers
from ..common import a2s, COMMENT_MARKER


class DeadcodePass(BasePass):
    """
    Eliminated un-executed code paths.

    Dead code elimination uses a runtime trace to determine whether a node
    in the AST was actually executed. For example, if an if/else only ever
    visits the else branch, we can eliminate the if branch.

    To determine whether code was executed, the Python tracing facilities
    tell us whether a line of code in the source file was executed during a
    trace. For a given syntax object, we can compute the set of line numbers
    it spans, and check if any of the lines were executed.

    Example:
      flag = False
      if flag:
        x = 1
      else:
        x = 2

      >> becomes >>

      flag = False
      x = 2
    """
    tracer_args = {'trace_opcodes': True, 'trace_lines': True}

    def _is_comment(self, node):
        return isinstance(node, ast.Expr) and \
            isinstance(node.value, ast.Str) and \
            node.value.s.startswith(COMMENT_MARKER)

    def _len_without_comment(self, stmts):
        # We never treat comments as dead code, so a dead block can end up
        # with only comments. Hence we need to count statements while
        # excluding comments.
        return len([s for s in stmts if not self._is_comment(s)])

    def _exec_count(self, node):
        collect_lineno = CollectLineNumbers()
        collect_lineno.visit(node)
        return max(
            [self.tracer.execed_lines[i] for i in collect_lineno.linenos])

    def _is_dead(self, node):
        return self._exec_count(node) == 0

    def visit_Assign(self, node):
        if self._is_dead(node):
            self.change = True
            return None

        return node

    def visit_If(self, stmt):
        # TODO: assumes pure conditions
        if self._len_without_comment(stmt.body) == 0 or self._is_dead(
                stmt.body[0]):
            self.change = True
            return stmt.orelse
        elif self._len_without_comment(stmt.orelse) == 0 or self._is_dead(
                stmt.orelse[0]):
            # TODO: need to check execution counts
            if False:
                test_count = self._exec_count(stmt.test)
                body_count = self._exec_count(stmt.body[0])

                if test_count == body_count:
                    self.change = True
                    return stmt.body
            else:
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

    def visit_Expr(self, node):
        if self._is_comment(node):
            return node

        if self._is_dead(node):
            self.change = True
            return None

        # TODO: should generalize this to is effect free
        if isinstance(node.value, (ast.Name, ast.Str, ast.NameConstant)):
            self.change = True
            return None

        return node

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
