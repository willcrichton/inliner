import libcst as cst
from collections import defaultdict

from ..common import a2s
from ..contexts import ctx_inliner


class StatementInserter(cst.CSTTransformer):
    statement_types = (cst.SimpleStatementLine, cst.SimpleStatementSuite,
                       cst.BaseCompoundStatement)

    def __init__(self):
        self._current_stmt = []
        self._new_stmts = defaultdict(list)

    def _handle_block(self, old_node, new_node):
        new_block = []
        changed = False
        for old_stmt, new_stmt in zip(old_node.body, new_node.body):
            new_stmts = self._new_stmts.get(old_stmt, None)
            if new_stmts:
                changed = True
                new_block.extend(new_stmts)
            new_block.append(new_stmt)

        if changed:
            return new_node.with_changes(body=new_block)
        else:
            return new_node

    def insert_statements_before_current(self, stmts):
        assert len(self._current_stmt) > 0
        self._new_stmts[self._current_stmt[-1]].extend(stmts)

    def on_visit(self, node):
        if isinstance(node, self.statement_types):
            self._current_stmt.append(node)

        return super().on_visit(node)

    def on_leave(self, old_node, new_node):
        if isinstance(new_node, (cst.IndentedBlock, cst.Module)):
            return self._handle_block(old_node, new_node)

        if isinstance(old_node, self.statement_types):
            self._current_stmt.pop()

        return super().on_leave(old_node, new_node)


class BasePass(StatementInserter):
    def __init__(self):
        super().__init__()
        self.inliner = ctx_inliner.get()
        self.generated_vars = defaultdict(int)
        self.after_init()

    def after_init(self):
        pass

    def fresh_var(self, prefix):
        """
        Creates a new variable semi-guaranteed to not exist in the program.
        """
        self.generated_vars[prefix] += 1
        count = self.generated_vars[prefix]
        if count == 1:
            return f'{prefix}'
        else:
            return f'{prefix}_{count}'

    def visit_FunctionDef(self, fdef):
        # Don't recurse into inline function definitions
        return False
