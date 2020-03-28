import libcst as cst
import libcst.matchers as m
from libcst.metadata import ScopeProvider, PositionProvider
from collections import defaultdict

from .base_pass import BasePass


class PropagationPass(BasePass):
    METADATA_DEPENDENCIES = (ScopeProvider, PositionProvider)

    def propagate(self, scopes, name, value):
        for scope in scopes:
            for access in scope.accesses[name]:
                self._to_propagate[access.node] = value

    def visit_FunctionDef(self, node):
        super().visit_FunctionDef(node)
        return True

    def leave_Name(self, original_node, updated_node):
        return self._to_propagate.get(original_node, updated_node)

    def visit_Module(self, node):
        super().visit_Module(node)
        self._to_propagate = {}
        self._scope_children = defaultdict(list)

        all_scopes = set(self.metadata[ScopeProvider].values())
        for scope in all_scopes:
            cur_scope = scope
            self._scope_children[cur_scope].append(cur_scope)
            while cur_scope != cur_scope.parent:
                self._scope_children[cur_scope.parent].append(scope)
                cur_scope = cur_scope.parent


class CopyPropagationPass(PropagationPass):
    rhs_patterns = [m.Name(), m.Attribute(value=m.Name(), attr=m.Name())]

    def leave_Assign(self, original_node, updated_node):
        if any([
                m.matches(
                    updated_node,
                    m.Assign(targets=[m.AssignTarget(m.Name())], value=pattern))
                for pattern in self.rhs_patterns
        ]):
            var = original_node.targets[0].target
            scope = self.get_metadata(ScopeProvider, var)
            children = self._scope_children[scope]

            if len(scope.assignments[var]) == 1:
                valid_scopes = [scope] + [
                    child
                    for child in children if len(child.assignments[var]) == 0
                ]
                self.propagate(valid_scopes, var, updated_node.value)
                return cst.RemoveFromParent()

        return updated_node
