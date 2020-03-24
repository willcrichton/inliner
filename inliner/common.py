import re
import textwrap

import libcst as cst
from libcst.metadata import ExpressionContext
from libcst.metadata import \
    ExpressionContextProvider as _ExpressionContextProvider
from libcst.metadata import ScopeProvider as _ScopeProvider
from libcst.metadata.expression_context_provider import \
    ExpressionContextVisitor
from libcst.metadata.scope_provider import ScopeVisitor

from .contexts import ctx_inliner

SEP = "___"


class ExpressionContextProvider(_ExpressionContextProvider):
    def visit_IndentedBlock(self, node: cst.IndentedBlock) -> None:
        node.visit(ExpressionContextVisitor(self, ExpressionContext.LOAD))


class ScopeProvider(_ScopeProvider):
    def visit_FunctionDef(self, node):
        visitor = ScopeVisitor(self)
        node.visit(visitor)
        visitor.infer_accesses()


class EvalException(Exception):
    pass


def a2s(node):
    return ctx_inliner.get().module.code_for_node(node).strip()


def make_assign(lhs, rhs):
    return cst.SimpleStatementLine(
        [cst.Assign(targets=[cst.AssignTarget(lhs)], value=rhs)])


def make_string(s):
    escaped = s.replace('"', '\"')
    return cst.SimpleString(f'"{escaped}\"')


def make_index(arr, idx):
    return cst.Subscript(
        value=arr, slice=[cst.SubscriptElement(slice=cst.Index(value=idx))])


def make_list(elts):
    return cst.List(elements=[cst.Element(value=elt) for elt in elts])


def make_dict(items):
    return cst.Dict(
        elements=[cst.DictElement(key=k, value=v) for k, v in items])


def get_function_locals(f):
    if hasattr(f, '__closure__') and \
       f.__closure__ is not None and \
       len(f.__closure__) > 0:
        return {
            var: cell.cell_contents
            for var, cell in zip(f.__code__.co_freevars, f.__closure__)
        }

    return {}


def dedent(s):
    no_backtick = re.sub(r'\\\n', '', s)

    # If a program has lines that don't match the top-level indent, e.g.
    # because of a multiline string, then indent the string to match top-level
    lines = no_backtick.strip('\n').split('\n')
    indent = textwrap._leading_whitespace_re.search(lines[0])
    assert indent is not None, no_backtick
    indent = indent.group(1)
    for i, line in enumerate(lines):
        if not line.startswith(indent):
            lines[i] = indent + line

    return textwrap.dedent('\n'.join(lines))


def parse_module(s):
    return cst.parse_module(dedent(s).strip())


def parse_statement(s):
    return cst.parse_statement(dedent(s).strip())


def parse_expr(s):
    return cst.parse_expression(dedent(s).strip())
