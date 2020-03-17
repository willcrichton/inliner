import libcst as cst
from collections import defaultdict

from ..visitors import StatementInserter
from ..contexts import ctx_inliner


class BasePass(StatementInserter):
    def __init__(self):
        super().__init__()
        self.inliner = ctx_inliner.get()
        self.generated_vars = defaultdict(int)
        self.after_init()

    def after_init(self):
        pass

    def fresh_var(self, prefix):
        """
        Creates a new variable semi-guaranteed to not exist in the program.
        """
        self.generated_vars[prefix] += 1
        count = self.generated_vars[prefix]
        if count == 1:
            return f'{prefix}'
        else:
            return f'{prefix}_{count}'

    def visit_FunctionDef(self, fdef):
        # Don't recurse into inline function definitions
        return False
