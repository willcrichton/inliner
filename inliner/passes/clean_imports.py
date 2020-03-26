import libcst as cst
from isort import SortImports

from .base_pass import BasePass


class CleanImportsPass(BasePass):
    """
    Puts all imports at the top of the module and de-duplicates them.

    Example:
      x = 1
      import foo
      import numpy
      y = foo.bar() + x

      >> becomes >>

      import foo
      x = 1
      y = foo.bar() + x
    """
    def __init__(self):
        super().__init__()
        self.imports = []

    def leave_Import(self, original_node, updated_node):
        self.imports.append(original_node)
        return cst.RemoveFromParent()

    def leave_ImportFrom(self, original_node, updated_node):
        self.imports.append(original_node)
        return cst.RemoveFromParent()

    def leave_Module(self, original_node, updated_node):
        final_node = super().leave_Module(original_node, updated_node)
        imports_str = cst.Module(
            body=[cst.SimpleStatementLine([i]) for i in self.imports]).code
        sorted_imports = cst.parse_module(
            SortImports(file_contents=imports_str).output)

        # Add imports back to the top of the module
        new_body = sorted_imports.body + list(final_node.body)

        return final_node.with_changes(body=new_body)
