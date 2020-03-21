import libcst as cst
import libcst.matchers as m
from libcst.codemod import CodemodContext
from libcst.metadata import ExpressionContext
from collections import defaultdict
from collections.abc import Iterable
import inspect
from typing import Union, Optional, Dict

from .insert_statements import InsertStatementsVisitor
from .common import make_assign, parse_module, parse_statement, parse_expr, a2s, ExpressionContextProvider


class RemoveEmptyBlocks(InsertStatementsVisitor):
    def __init__(self):
        super().__init__(CodemodContext())

    def leave_If(self, original_node,
                 updated_node) -> Union[cst.BaseStatement, cst.RemovalSentinel]:
        if (updated_node.orelse is not None
                and len(updated_node.orelse.body.body) == 0):
            updated_node = updated_node.with_changes(orelse=None)

        return super().leave_If(original_node, updated_node)

    def on_leave(self, original_node, updated_node):
        final_node = super().on_leave(original_node, updated_node)

        if isinstance(final_node,
                      (cst.SimpleStatementLine, cst.SimpleStatementSuite)):
            if len(final_node.body) == 0:
                return cst.RemoveFromParent()

        elif isinstance(final_node, cst.BaseCompoundStatement):
            if len(final_node.body.body) == 0:
                return cst.RemoveFromParent()

        return final_node


class ReplaceReturn(RemoveEmptyBlocks):
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


class FindAssignments(cst.CSTVisitor):
    def __init__(self):
        self.names = set()

    def visit_Assign(self, node) -> Optional[bool]:
        for t in node.targets:
            if m.matches(t, m.Name()):
                self.names.add(t.value)


class FindClosedVariables(cst.CSTVisitor):
    closure_nodes = (cst.FunctionDef, cst.ListComp, cst.DictComp)

    def __init__(self):
        self.vars = set()
        self.in_closure = 0

    def visit_Name(self, node) -> Optional[bool]:
        if self.in_closure > 0:
            self.vars.add(node.value)
        return super().visit_Name(node)

    def on_visit(self, node) -> bool:
        if isinstance(node, self.closure_nodes):
            self.in_closure += 1
        return super().on_visit(node)

    def on_leave(self, original_node) -> None:
        if isinstance(original_node, self.closure_nodes):
            self.in_closure -= 1
        return super().on_leave(original_node)


class UsedNames(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (ExpressionContextProvider, )

    def __init__(self):
        self.names = set()

    def visit_Name(self, node) -> None:
        try:
            expr_ctx = self.get_metadata(ExpressionContextProvider, node)
        except KeyError:
            return

        if expr_ctx == ExpressionContext.LOAD:
            self.names.add(node.value)


class Rename(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (ExpressionContextProvider, )

    def __init__(self, src, dst):
        self.src = src
        self.dst = dst

    def visit_FunctionDef(self, node) -> Optional[bool]:
        fdef = node
        if fdef.name.value != self.src:
            params = fdef.params
            arg_names = set()
            for arg in params.params:
                arg_names.add(arg.name.value)
            if params.star_arg is not None:
                arg_names.add(params.star_arg.name.value)
            if params.star_kwarg is not None:
                arg_names.add(params.star_kwarg.name.value)

            return self.src not in arg_names

    def leave_Name(self, original_node, updated_node) -> cst.BaseExpression:
        try:
            expr_ctx = self.get_metadata(ExpressionContextProvider,
                                         original_node)
        except KeyError:
            return updated_node

        if expr_ctx == ExpressionContext.LOAD and updated_node.value == self.src:
            return updated_node.with_changes(value=self.dst)

        return updated_node


class ReplaceYield(cst.CSTTransformer):
    def __init__(self, ret_var):
        self.ret_var = ret_var

    def leave_Yield(self, original_node, updated_node) -> cst.BaseExpression:
        append = parse_expr(f'{self.ret_var}.append()')
        return append.with_changes(args=[cst.Arg(updated_node.value)])


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


class CollectImports(cst.CSTVisitor):
    imprts: Dict[str, cst.BaseSmallStatement]
    mod: str

    def __init__(self, mod):
        self.imprts = {}
        self.mod = mod

    def visit_Import(self, node) -> None:
        for alias in node.names:
            name = alias.asname.name.value if alias.asname is not None else alias.name.value
            self.imprts[name] = cst.Import(names=[alias])

    def visit_ImportFrom(self, node) -> None:
        for alias in node.names:
            name = alias.asname.value if alias.asname is not None else alias.name.value

            level = len(node.relative)
            if level > 0:
                parts = self.mod.split('.')
                mod_level = '.'.join(
                    parts[:-level]) if len(parts) > 1 else parts[0]
                if node.module is not None:
                    module = parse_expr(f'{mod_level}.{a2s(node.module)}')
                else:
                    module = parse_expr(mod_level)
            else:
                module = node.module

            self.imprts[name] = cst.ImportFrom(module=module, names=[alias])


def collect_imports(obj):
    mod = inspect.getmodule(obj)
    if mod is None:
        return []

    import_collector = CollectImports(mod=mod.__name__)
    obj_mod = parse_module(open(inspect.getsourcefile(obj)).read())
    obj_mod.visit(import_collector)
    return import_collector.imprts


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
