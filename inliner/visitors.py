import libcst as cst
import libcst.matchers as m
from collections import defaultdict
from collections.abc import Iterable

from .common import make_assign, parse_statement, a2s


class RemoveEmptyBlocks(cst.CSTTransformer):
    statement_types = (cst.SimpleStatementLine, cst.SimpleStatementSuite,
                       cst.BaseCompoundStatement)

    block_types = (cst.IndentedBlock, cst.Module)

    def on_leave(self, old_node, new_node):
        new_node = super().on_leave(old_node, new_node)
        if isinstance(new_node,
                      (cst.SimpleStatementLine, cst.SimpleStatementSuite)):
            if len(new_node.body) == 0:
                return cst.RemovalSentinel.REMOVE

        elif isinstance(new_node, cst.BaseCompoundStatement):
            if len(new_node.body.body) == 0:
                return cst.RemovelSentinel.REMOVE

        return new_node


class StatementInserter(RemoveEmptyBlocks):
    def __init__(self):
        self._new_stmts = []

    def insert_statements_before_current(self, stmts):
        self._new_stmts[-1].extend(stmts)

    def on_visit(self, node):
        if isinstance(node, self.block_types):
            self._new_stmts.append([])

        return super().on_visit(node)

    def on_leave(self, old_node, new_node):
        new_node = super().on_leave(old_node, new_node)

        if isinstance(old_node, self.block_types):
            assert type(old_node) is type(new_node)
            new_node = new_node.with_changes(body=self._new_stmts.pop())

        elif isinstance(old_node, self.statement_types):
            if new_node is not cst.RemovalSentinel.REMOVE:
                self._new_stmts[-1].append(new_node)

        return new_node


class ReplaceReturn(StatementInserter):
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.return_blocks = set()
        self.if_wrapper = parse_statement(f"""
if "{name}" not in globals():
    pass
""")

    def _build_if(self, body):
        return self.if_wrapper.with_deep_changes(self.if_wrapper.body,
                                                 body=body)

    def leave_Return(self, _, ret):
        # A naked return (without a value) will have ret.value = None
        value = ret.value if ret.value is not None else cst.Name('None')
        if_stmt = self._build_if([make_assign(cst.Name(self.name), value)])
        self.insert_statements_before_current([if_stmt])
        return ret

    def visit_FunctionDef(self, fdef):
        return False

    def on_leave(self, old_node, new_node):
        new_node = super().on_leave(old_node, new_node)

        if isinstance(new_node, self.block_types):
            cur_stmts = new_node.body

            while True:
                change = False
                N = len(cur_stmts)
                for i in reversed(range(N)):
                    stmt = cur_stmts[i]
                    is_return = m.matches(stmt,
                                          m.SimpleStatementLine([m.Return()]))
                    is_return_block = isinstance(stmt, cst.BaseCompoundStatement) and \
                        stmt.body in self.return_blocks

                    if is_return or is_return_block:
                        change = True

                        [cur_stmts, block] = [cur_stmts[:i], cur_stmts[i + 1:]]

                        if is_return_block:
                            self.return_blocks.remove(stmt.body)
                            cur_stmts.append(stmt)

                        if i < N - 1:
                            cur_stmts.append(self._build_if(block))

                        break

                if not change:
                    break

            new_node = new_node.with_changes(body=cur_stmts)
            self.return_blocks.add(new_node)
        return new_node


class FindAssignments(cst.CSTVisitor):
    def __init__(self):
        self.names = set()

    def visit_Assign(self, assgn):
        for t in assgn.targets:
            if m.matches(t, m.Name()):
                self.names.add(t.value)


class FindClosedVariables(cst.CSTVisitor):
    closure_nodes = (cst.FunctionDef, cst.ListComp, cst.DictComp)

    def __init__(self):
        self.vars = set()
        self.in_closure = 0

    def visit_Name(self, name):
        if self.in_closure > 0:
            self.vars.add(name.value)

    def on_visit(self, node):
        if isinstance(node, self.closure_nodes):
            self.in_closure += 1

    def on_leave(self, node):
        if isinstance(node, self.closure_nodes):
            self.in_closure -= 1


class Rename(cst.CSTTransformer):
    def __init__(self, src, dst):
        self.src = src
        self.dst = dst

    def visit_FunctionDef(self, fdef):
        if fdef.name.value != self.src:
            for arg in args.args:
                arg_names.add(arg.arg)
            if args.vararg is not None:
                arg_names.add(args.vararg.arg)
            if args.kwarg is not None:
                arg_names.add(args.kwarg.arg)

            return self.src not in arg_names

    def leave_FunctionDef(self, _, fdef):
        if fdef.name.value == self.src:
            return fdef.with_changes(name=cst.Name(self.dst))
        return fdef

    def leave_Name(self, _, name):
        if name.value == self.src:
            return name.with_changes(value=self.dst)
        return name
