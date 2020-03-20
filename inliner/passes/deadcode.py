import libcst as cst

from .base_pass import BasePass
from ..tracer import get_execed_map


class DeadCodePass(BasePass):
    tracer_args = {'trace_lines': True}

    def visit_Module(self, mod):
        super().visit_Module(mod)
        self.execed_map = get_execed_map(mod, self.tracer)

    def on_leave(self, original_node, updated_node):
        final_node = super().on_leave(original_node, updated_node)

        if (isinstance(final_node, cst.BaseStatement)
                and not self.execed_map[original_node]):
            print(original_node)
            return cst.RemoveFromParent()

        return final_node
