import ast
import inspect

from ..common import make_name, SEP
from .base_pass import BasePass


class ExpandSelfPass(BasePass):
    tracer_args = {}

    def __init__(self, inliner):
        super().__init__(inliner)
        self._find_objs_to_inline()

    def _find_objs_to_inline(self):
        self.objs_to_inline = {}
        for var, obj in self.globls.items():
            if self.inliner.should_inline(obj) and not inspect.isclass(obj) and \
               not inspect.ismodule(obj):
                if id(obj) not in self.objs_to_inline:
                    if hasattr(obj, '__name__'):
                        name = obj.__name__
                    elif hasattr(obj, '__class__'):
                        name = obj.__class__.__name__
                    else:
                        name = 'var'
                    self.objs_to_inline[id(obj)] = self.inliner.fresh(
                        name.lower())

    def visit_Attribute(self, attr):
        if isinstance(attr.value, ast.Name):
            name = attr.value.id
            if name in self.globls:
                obj = self.globls[name]
                if id(obj) in self.objs_to_inline:
                    new_name = self.objs_to_inline[id(obj)]
                    self.change = True
                    return make_name(f'{new_name}{SEP}{attr.attr}')

        self.generic_visit(attr)
        return attr

    def visit_Assign(self, stmt):
        if isinstance(stmt.targets[0], ast.Name):
            name = stmt.targets[0].id
            assert name in self.globls
            obj = self.globls[name]

            if id(obj) in self.objs_to_inline:
                new_name = self.objs_to_inline[id(obj)]
                self.change = True
                if isinstance(stmt.value, ast.Call):
                    return [
                        ast.Assign(targets=[make_name(f'{new_name}{SEP}{k}')],
                                   value=ast.NameConstant(None))
                        for k in vars(obj).keys()
                    ]
                else:
                    return []

        self.generic_visit(stmt)
        return stmt
