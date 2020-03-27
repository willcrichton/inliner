from typing import Union

import libcst as cst
import libcst.matchers as m
from .libcst_dropin import InsertStatementsVisitor
from ..common import parse_expr, parse_statement, make_assign


class ReplaceReturn(InsertStatementsVisitor):
    statement_types = (cst.SimpleStatementLine, cst.SimpleStatementSuite,
                       cst.BaseCompoundStatement)

    block_types = (cst.IndentedBlock, cst.Module)

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

    def leave_Return(self, original_node, updated_node
                     ) -> Union[cst.BaseSmallStatement, cst.RemovalSentinel]:
        ret = updated_node
        # A naked return (without a value) will have ret.value = None
        value = ret.value if ret.value is not None else cst.Name('None')
        if_stmt = self._build_if([make_assign(cst.Name(self.name), value)])
        self.insert_statements_before_current([if_stmt])
        return ret

    def visit_FunctionDef(self, node) -> bool:
        super().visit_FunctionDef(node)
        return False

    def on_leave(self, old_node, new_node):
        new_node = super().on_leave(old_node, new_node)

        if isinstance(new_node, self.block_types):
            cur_stmts = new_node.body

            any_change = False
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
                        any_change = True
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
            if any_change:
                self.return_blocks.add(new_node)
        return new_node


class ReplaceYield(cst.CSTTransformer):
    def __init__(self, ret_var):
        self.ret_var = ret_var

    def leave_Yield(self, original_node, updated_node) -> cst.BaseExpression:
        append = parse_expr(f'{self.ret_var}.append()')
        yield_val = updated_node.value

        # If original expr was "yield a, b" then yield_val compiles to
        # "a, b" (i.e. no parens) which errors if directly inserted into
        # foo.append(a, b). So we ensure that the tuple has parentheses.
        if m.matches(yield_val, m.Tuple()):
            yield_val = yield_val.with_changes(lpar=[cst.LeftParen()],
                                               rpar=[cst.RightParen()])

        return append.with_changes(args=[cst.Arg(yield_val)])


class ReplaceSuper(cst.CSTTransformer):
    def __init__(self, cls):
        self.cls = cls

    def leave_Call(self, original_node, updated_node) -> cst.BaseExpression:
        if m.matches(updated_node.func,
                     m.Attribute(value=m.Call(m.Name('super')))):
            return updated_node \
                .with_deep_changes(
                    updated_node.func, value=cst.Name(self.cls.__name__)) \
                .with_changes(
                    args=[cst.Arg(cst.Name('self'))] + list(updated_node.args))

        return updated_node


class RemoveFunctoolsWraps(cst.CSTTransformer):
    def leave_FunctionDef(self, original_node,
                          updated_node) -> cst.BaseStatement:
        fdef = updated_node
        ftool_pattern = m.Call(
            func=m.Attribute(value=m.Name("functools"), attr=m.Name("wraps")))
        if len(fdef.decorators) == 1:
            dec = fdef.decorators[0].decorator
            if m.matches(dec, ftool_pattern):
                return fdef.with_changes(decorators=[])
        return fdef
