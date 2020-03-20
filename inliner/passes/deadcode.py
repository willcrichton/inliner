import libcst as cst

from .base_pass import BasePass


class DeadCodePass(BasePass):
    tracer_args = {'trace_lines': True}

    def visit_Module(self, mod):
        super().visit_Module(mod)
        self.exec_counts = self.tracer.exec_counts()
        self.block_execs = [1]  # Module was executed once

    def visit_IndentedBlock(self, node):
        super().visit_IndentedBlock(node)
        # Record the number of times the current IndentedBlock was executed
        self.block_execs.append(self.exec_counts[node])

    def leave_IndentedBlock(self, original_node, updated_node):
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
            self.insert_statements_before_current(updated_node.orelse.body.body)
            super().leave_If(original_node, updated_node)
            return cst.RemoveFromParent()

        return super().leave_If(original_node, updated_node)

    def on_leave(self, original_node, updated_node):
        final_node = super().on_leave(original_node, updated_node)

        if (isinstance(final_node, cst.BaseStatement)
                and self.exec_counts[original_node] == 0):
            return cst.RemoveFromParent()

        return final_node
