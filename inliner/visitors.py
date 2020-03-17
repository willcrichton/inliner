import libcst as cst
import libcst.matchers as m
from libcst.metadata import ExpressionContext
from collections import defaultdict
from collections.abc import Iterable
import inspect

from .common import make_assign, parse_module, parse_statement, parse_expr, a2s, ExpressionContextProvider


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


class UsedNames(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (ExpressionContextProvider, )

    def __init__(self):
        self.names = set()

    def visit_Name(self, name):
        try:
            expr_ctx = self.get_metadata(ExpressionContextProvider, name)
        except KeyError:
            return

        if expr_ctx == ExpressionContext.LOAD:
            self.names.add(name.value)


class Rename(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (ExpressionContextProvider, )

    def __init__(self, src, dst):
        self.src = src
        self.dst = dst

    def visit_FunctionDef(self, fdef):
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

    def leave_Name(self, old_name, new_name):
        try:
            expr_ctx = self.get_metadata(ExpressionContextProvider, old_name)
        except KeyError:
            return new_name

        if expr_ctx == ExpressionContext.LOAD and new_name.value == self.src:
            return new_name.with_changes(value=self.dst)

        return new_name


class ReplaceYield(cst.CSTTransformer):
    def __init__(self, ret_var):
        self.ret_var = ret_var

    def leave_Yield(self, old_expr, new_expr):
        append = parse_expr(f'{self.ret_var}.append()')
        return append.with_changes(args=[cst.Arg(new_expr.value)])


class ReplaceSuper(cst.CSTTransformer):
    def __init__(self, cls):
        self.cls = cls

    def leave_Call(self, _, new_call):
        if m.matches(new_call.func, m.Attribute(value=m.Call(m.Name('super')))):
            return new_call \
                .with_deep_changes(
                    new_call.func, value=cst.Name(self.cls.__name__)) \
                .with_changes(
                    args=[cst.Arg(cst.Name('self'))] + list(new_call.args))

        return new_call


class CollectImports(cst.CSTVisitor):
    def __init__(self, mod):
        self.imprts = {}
        self.mod = mod

    def visit_Import(self, imprt):
        for alias in imprt.names:
            name = alias.asname.name.value if alias.asname is not None else alias.name.value
            self.imprts[name] = cst.Import(names=[alias])

    def visit_ImportFrom(self, imprt):
        for alias in imprt.names:
            name = alias.asname.value if alias.asname is not None else alias.name.value

            level = len(imprt.relative)
            if level > 0:
                parts = self.mod.split('.')
                mod_level = '.'.join(
                    parts[:-level]) if len(parts) > 1 else parts[0]
                if imprt.module is not None:
                    module = parse_expr(f'{mod_level}.{a2s(imprt.module)}')
                else:
                    module = parse_expr(mod_level)
            else:
                module = imprt.module

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
    def leave_FunctionDef(self, _, fdef):
        ftool_pattern = m.Call(
            func=m.Attribute(value=m.Name("functools"), attr=m.Name("wraps")))
        if len(fdef.decorators) == 1:
            dec = fdef.decorators[0].decorator
            if m.matches(dec, ftool_pattern):
                return fdef.with_changes(decorators=[])
        return fdef
