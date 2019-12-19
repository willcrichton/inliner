import ast
from .base_pass import BasePass


# TODO: is this redundant with lifetimes?
class UnreadVarsPass(BasePass):
    tracer_args = {'trace_opcodes': True}

    def visit_Assign(self, stmt):
        if len(stmt.targets) == 1 and \
           isinstance(stmt.targets[0], ast.Name):
            name = stmt.targets[0].id
            if len(self.tracer.reads[name]) == 0:
                self.change = True
                return None

        return stmt

    def visit_ImportFrom(self, stmt):
        aliases = [
            alias for alias in stmt.names
            if len(self.tracer.reads[alias.name if alias.
                                     asname is None else alias.asname]) > 0
        ]

        if len(aliases) != len(stmt.names):
            self.change = True
            return None

        if len(aliases) > 0:
            stmt.names = aliases
            return stmt

    def visit_FunctionDef(self, stmt):
        if len(self.tracer.reads[stmt.name]) == 0:
            self.change = True
            return None

        return stmt
