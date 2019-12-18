import ast
from collections import defaultdict

from .base_pass import BasePass
from ..visitors import CollectLineNumbers


class LifetimesPass(BasePass):
    tracer_args = {'trace_opcodes': True}

    def __init__(self, inliner):
        super().__init__(inliner)
        self._find_unused_stores()

    def _find_unused_stores(self):
        self.unused_stores = defaultdict(list)
        for k, stores in self.tracer.stores.items():
            reads = self.tracer.reads[k]

            for i, (_, store_line) in enumerate(stores):
                next_possible_stores = [
                    line for _, line in stores[i + 1:] if line > store_line
                ]
                next_store_line = min(next_possible_stores, default=10000000)

                unused = True
                for (_, read_line) in reads:
                    if store_line < read_line and read_line <= next_store_line:
                        unused = False

                if unused:
                    self.unused_stores[k].append(store_line)

    def visit_Assign(self, stmt):
        if len(stmt.targets) == 1 and \
           isinstance(stmt.targets[0], ast.Name):

            name = stmt.targets[0].id
            unused_lines = self.unused_stores[name]

            collect_lineno = CollectLineNumbers()
            collect_lineno.visit(stmt)

            if len(set(unused_lines) & collect_lineno.linenos) > 0:
                self.change = True
                return None

        return stmt
