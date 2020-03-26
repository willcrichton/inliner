import libcst as cst
import libcst.matchers as m
from typing import List, Union

from .base_pass import BasePass
from ..tracer import TracerArgs, ExecCounts
from ..visitors import is_pure


class DeadCodePass(BasePass):
    tracer_args = TracerArgs(trace_lines=True)
    exec_counts: ExecCounts
    block_execs: List[int]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.exec_counts = {}

    def visit_Module(self, node) -> None:
        super().visit_Module(node)
        assert self.tracer is not None
        self.exec_counts = self.tracer.exec_counts()
        self.block_execs = [1]  # Module was executed once

    def visit_IndentedBlock(self, node) -> None:
        super().visit_IndentedBlock(node)
        # Record the number of times the current IndentedBlock was executed
        self.block_execs.append(self.exec_counts[node])

    def leave_IndentedBlock(self, original_node, updated_node) -> cst.BaseSuite:
        final_node = super().leave_IndentedBlock(original_node, updated_node)
        # Pop the execution stack when we leave an IndentedBlock
        self.block_execs.pop()
        return final_node

    def leave_If(self, original_node, updated_node):
        then_branch_count = self.exec_counts[original_node.body]

        # If then was always taken, just return then branch
        if then_branch_count == self.block_execs[-1]:
            self.insert_statements_before_current(updated_node.body.body)
            super().leave_If(original_node, updated_node)
            return cst.RemoveFromParent()

        # If else was always taken, just return else branch
        elif updated_node.orelse is not None and then_branch_count == 0:
            self.insert_statements_before_current(
                self.reattach_comments(updated_node.orelse,
                                       list(updated_node.orelse.body.body)))
            self.dont_keep_comments()
            super().leave_If(original_node, updated_node)
            return cst.RemoveFromParent()

        return super().leave_If(original_node, updated_node)

    def leave_Try(self, original_node, updated_node
                  ) -> Union[cst.BaseStatement, cst.RemovalSentinel]:
        for original_handler, updated_handler in zip(original_node.handlers,
                                                     updated_node.handlers):
            if self.exec_counts[original_handler.body] > 0:
                self.insert_statements_before_current(updated_handler.body.body)
                super().leave_Try(original_node, updated_node)
                return cst.RemoveFromParent()

        self.insert_statements_before_current(updated_node.body.body)

        super().leave_Try(original_node, updated_node)
        return cst.RemoveFromParent()

    def leave_Expr(self, original_node, updated_node):
        final_node = super().leave_Expr(original_node, updated_node)
        if is_pure(final_node.value):
            if m.matches(final_node, m.Expr(m.SimpleString())):
                s = final_node.value.value
                if s.startswith('"""'):
                    return final_node
            return cst.RemoveFromParent()
        return final_node

    def on_leave(self, original_node, updated_node):
        final_node = super().on_leave(original_node, updated_node)

        if (isinstance(final_node, cst.BaseStatement) and not m.matches(
                final_node,
                m.SimpleStatementLine(body=[m.Expr(m.SimpleString())]))
                and self.exec_counts[original_node] == 0):
            return cst.RemoveFromParent()

        return final_node
