import ast
import inspect

from ..common import make_name, SEP
from .base_pass import BasePass


class ExpandSelfPass(BasePass):
    """
    Replaces all class instances with variables.

    Once an object's methods have been fully inlined, the object is essentially
    a fancy dictionary. We can inline the dictionary by converting each key
    to a unique variable name. Then we can replace object assignments by copying
    every variable individually.

    See ContextualTransforms.inline_constructor for how objects are inlined
    in the first place.

    Example:
      foo = Foo.__new__(Foo)
      foo.x = 1
      bar = foo
      assert bar.x == 1

      >> becomes >>

      foo_x = 1
      bar_x = foo_x
      assert bar_x == 1
    """

    tracer_args = {}

    def __init__(self, inliner):
        super().__init__(inliner)
        self._find_objs_to_inline()

    def _find_objs_to_inline(self):
        self.objs_to_inline = {}
        # We find all the objects that need to be inlined by going through
        # the globals of the last trace
        for var, obj in self.globls.items():

            # There is no inspect.isobject or inspect.iscreatedfromclass
            # unfortunately. So we proceed by process of elimination. If
            # an object is neither a class or a module, it must be an object
            # so we register it to be inlined.
            if self.inliner.should_inline(obj) and \
               not inspect.isclass(obj) and \
               not inspect.ismodule(obj):

                if id(obj) not in self.objs_to_inline:

                    # We heuristically devise a name for the object
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
