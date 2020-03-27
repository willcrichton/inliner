import libcst as cst

from libcst.metadata import ExpressionContext
import libcst.matchers as m
from .libcst_dropin import ExpressionContextProviderBlock

from typing import Optional


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


class FindUsedNames(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (ExpressionContextProviderBlock, )

    def __init__(self):
        self.names = set()

    def visit_Name(self, node) -> None:
        try:
            expr_ctx = self.get_metadata(ExpressionContextProviderBlock, node)
        except KeyError:
            return

        if expr_ctx == ExpressionContext.LOAD:
            self.names.add(node.value)
