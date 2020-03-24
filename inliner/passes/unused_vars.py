import libcst as cst
import libcst.matchers as m

from .base_pass import BasePass
from ..tracer import TracerArgs
from ..visitors import is_pure


class UnusedVarsPass(BasePass):
    tracer_args = TracerArgs(trace_reads=True)

    def visit_Module(self, node):
        super().visit_Module(node)
        self.unused_vars = self.tracer.unused_vars()

    def leave_Assign(self, original_node, updated_node):
        if m.matches(original_node,
                     m.Assign(targets=[m.AssignTarget(m.Name())])):
            if self.unused_vars[original_node] and is_pure(updated_node.value):
                return cst.RemoveFromParent()
        return updated_node

    def leave_FunctionDef(self, original_node, updated_node):
        final_node = super().leave_FunctionDef(original_node, updated_node)
        if self.unused_vars[original_node]:
            return cst.RemoveFromParent()
        return final_node
