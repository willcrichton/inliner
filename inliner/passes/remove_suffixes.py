from libcst.metadata import ScopeProvider, PositionProvider

from .base_pass import BasePass
from ..common import SEP


class RemoveSuffixesPass(BasePass):
    METADATA_DEPENDENCIES = (ScopeProvider, PositionProvider)

    def leave_Name(self, original_node, updated_node):
        if self.get_metadata(ScopeProvider, original_node, None):
            name = updated_node.value
            parts = name.split(SEP)
            if len(parts) > 1:
                base = parts[0]
                if name not in self.name_map:
                    self.name_map[name] = self.fresh_var(base)
                return updated_node.with_changes(value=self.name_map[name])
        return updated_node

    def visit_FunctionDef(self, node):
        super().visit_FunctionDef(node)
        return True

    def visit_Module(self, node):
        self.name_map = {}
        return super().visit_Module(node)
