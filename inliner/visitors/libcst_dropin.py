import libcst as cst
from libcst.metadata import ExpressionContext
from libcst.metadata import \
    ExpressionContextProvider as ExpressionContextProvider
from libcst.metadata import ScopeProvider as ScopeProvider
from libcst.metadata.expression_context_provider import \
    ExpressionContextVisitor
from libcst.metadata.scope_provider import ScopeVisitor

from .insert_statements import \
    InsertStatementsVisitor as _InsertStatementsVisitor
from libcst.codemod import CodemodContext


class ExpressionContextProviderBlock(ExpressionContextProvider):
    def visit_IndentedBlock(self, node: cst.IndentedBlock) -> None:
        node.visit(ExpressionContextVisitor(self, ExpressionContext.LOAD))


class ScopeProviderFunction(ScopeProvider):
    def visit_FunctionDef(self, node):
        visitor = ScopeVisitor(self)
        node.visit(visitor)
        visitor.infer_accesses()


class InsertStatementsVisitor(_InsertStatementsVisitor):
    def __init__(self):
        super().__init__(CodemodContext())
