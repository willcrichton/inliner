import ast

from .base_pass import BasePass
from ..common import a2s


class SimplifyVarargsPass(BasePass):
    tracer_args = {}

    def visit_Call(self, call):
        kwarg = [(i, kw.value) for i, kw in enumerate(call.keywords)
                 if kw.arg is None]
        if len(kwarg) == 1:
            i, kwarg = kwarg[0]

            try:
                kwarg_obj = eval(a2s(kwarg), self.globls, self.globls)
            except Exception:
                print('ERROR', a2s(call))
                raise

            if len(kwarg_obj) == 0:
                del call.keywords[i]
                self.change = True

        return call
