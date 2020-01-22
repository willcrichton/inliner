import ast
import inspect

from ..common import make_name, SEP, compare_ast, parse_expr, a2s, obj_to_ast, ObjConversionException
from .base_pass import BasePass


class FindObjNew(ast.NodeVisitor):
    def __init__(self, globls):
        self.globls = globls
        self.objs = set()

    def visit_Assign(self, stmt):
        if isinstance(stmt.targets[0], ast.Name):
            name = stmt.targets[0].id
            assert name in self.globls, f'{name} not in globals'
            obj = self.globls[name]

            cls = obj.__class__.__name__
            if compare_ast(stmt.value, parse_expr(f'{cls}.__new__({cls})')):
                self.objs.add(id(obj))

    def visit_FunctionDef(self, fdef):
        pass


class UnsafeToExpand(ast.NodeVisitor):
    def __init__(self, inliner, globls):
        self.unsafe = set()
        self.inliner = inliner
        self.globls = globls

    def visit_Call(self, call):
        for arg in call.args:
            if isinstance(arg, ast.Name):
                self.unsafe.add(arg.id)

        self.generic_visit(call)


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attr_assigns = set()

    def visit_Module(self, mod):
        unsafe = UnsafeToExpand(self.inliner, self.globls)
        unsafe.visit(mod)

        finder = FindObjNew(self.globls)
        finder.visit(mod)

        self.objs_to_inline = {}
        # We find all the objects that need to be inlined by going through
        # the globals of the last trace
        for var, obj in self.globls.items():

            # There is no inspect.isobject or inspect.iscreatedfromclass
            # unfortunately. So we proceed by process of elimination. If
            # an object is neither a class or a module, it must be an object
            # so we register it to be inlined.
            if self.inliner.should_inline(make_name(var), obj, self.globls) and \
               not inspect.isclass(obj) and \
               not inspect.ismodule(obj) and \
               not var in unsafe.unsafe:

                if id(obj) not in self.objs_to_inline and id(
                        obj) in finder.objs:

                    # We heuristically devise a name for the object
                    if hasattr(obj, '__name__'):
                        name = obj.__name__
                    elif hasattr(obj, '__class__'):
                        name = obj.__class__.__name__
                    else:
                        name = 'var'
                    self.objs_to_inline[id(obj)] = self.inliner.fresh(
                        name.lower())

        return super().visit_Module(mod)

    def visit_Attribute(self, attr):
        if isinstance(attr.value, ast.Name):
            name = attr.value.id
            if name in self.globls:
                obj = self.globls[name]
                if id(obj) in self.objs_to_inline:
                    attr_obj = getattr(obj, attr.attr)

                    # If trying to expand Foo.method(), that's an error
                    if inspect.isfunction(attr_obj):
                        raise Exception(
                            "Attempted to expand_self with method remaining: {}"
                            .format(a2s(attr)))

                    # If trying to expand Foo.x where x is only defined on the
                    # class, not the object, then we need to inline the runtime
                    # value directly. We check if a property is only defined
                    # on the class by checking if it's not in __dict__
                    elif attr.attr not in obj.__dict__:
                        try:
                            return obj_to_ast(attr_obj)
                        except ObjConversionException:
                            print('Conversion failed for expression', a2s(attr))
                            raise

                    else:
                        new_name = self.objs_to_inline[id(obj)]
                        self.change = True
                        return make_name(f'{attr.attr}{SEP}{new_name}')

        self.generic_visit(attr)
        return attr

    def visit_Assign(self, stmt):
        if isinstance(stmt.targets[0], ast.Attribute):
            self.attr_assigns.add(a2s(stmt.targets[0]))

        elif isinstance(stmt.targets[0], ast.Name):
            name = stmt.targets[0].id
            assert name in self.globls
            obj = self.globls[name]

            if id(obj) in self.objs_to_inline:
                new_name = self.objs_to_inline[id(obj)]

                cls = obj.__class__.__name__
                if compare_ast(stmt.value, parse_expr(f'{cls}.__new__({cls})')):
                    self.change = True
                    return [
                        ast.Assign(targets=[make_name(f'{new_name}{SEP}{k}')],
                                   value=ast.NameConstant(None))
                        for k in vars(obj).keys()
                    ]
                else:
                    return []

        self.generic_visit(stmt)
        return stmt
