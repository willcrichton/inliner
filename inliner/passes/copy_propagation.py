import libcst as cst
import libcst.matchers as m
from libcst.metadata import ScopeProvider, PositionProvider

from .base_pass import BasePass


class PropagationPass(BasePass):
    METADATA_DEPENDENCIES = (ScopeProvider, PositionProvider)

    def __init__(self):
        super().__init__()
        self._to_propagate = {}

    def propagate(self, scope, name, value):
        for access in scope.accesses[name]:
            self._to_propagate[access.node] = value

    def visit_FunctionDef(self, node):
        super().visit_FunctionDef(node)
        return True

    def leave_Name(self, original_node, updated_node):
        return self._to_propagate.get(original_node, updated_node)


class CopyPropagationPass(PropagationPass):
    def leave_Assign(self, original_node, updated_node):
        if m.matches(
                updated_node,
                m.Assign(targets=[m.AssignTarget(m.Name())], value=m.Name())):
            var = original_node.targets[0].target
            scope = self.get_metadata(ScopeProvider, var)

            # Only safe to propagate if var is not reassigned in same scope
            if len(scope.assignments[var]) == 1:
                self.propagate(scope, var, updated_node.value)
                return cst.RemoveFromParent()

        return updated_node
