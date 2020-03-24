import libcst as cst
import libcst.matchers as m
import inspect

from ..tracer import TracerArgs
from ..common import SEP, parse_expr, a2s, EvalException
from .base_pass import BasePass

obj_new_pattern = m.Assign(
    targets=[m.AssignTarget(m.Name())],
    value=m.Call(func=m.Attribute(value=m.Name(), attr=m.Name("__new__"))))


class FindSafeObjsToConvert(cst.CSTVisitor):
    def __init__(self, pass_):
        self.pass_ = pass_
        self.whitelist = set()
        self.blacklist = set()

    def visit_Assign(self, node):
        if m.matches(node, obj_new_pattern):
            name = node.targets[0].target.value
            if name in self.pass_.globls:
                obj = self.pass_.globls[name]
                self.whitelist.add(id(obj))

    def visit_Attribute(self, node):
        try:
            obj = self.pass_.eval(node)
            if inspect.ismethod(obj):
                self.blacklist.add(id(obj.__self__))
        except EvalException:
            pass

    def visit_FunctionDef(self, node):
        return False


class RecordToVarsPass(BasePass):
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

    tracer_args = TracerArgs()

    def visit_Module(self, node):
        super().visit_Module(node)

        finder = FindSafeObjsToConvert(self)
        node.visit(finder)
        safe_objs = finder.whitelist - finder.blacklist

        # We find all the objects that need to be inlined by going through
        # the globals of the last trace
        self.objs_to_inline = {}
        for var, obj in self.globls.items():

            # There is no inspect.isobject or inspect.iscreatedfromclass
            # unfortunately. So we proceed by process of elimination. If
            # an object is neither a class or a module, it must be an object
            # so we register it to be inlined.
            if (not inspect.isclass(obj) and not inspect.ismodule(obj)
                    and id(obj) in safe_objs
                    and id(obj) not in self.objs_to_inline):

                self.objs_to_inline[id(obj)] = self.fresh_var(var)

    def leave_Assign(self, original_node, updated_node):
        if m.matches(original_node, obj_new_pattern):
            var = original_node.targets[0].target.value
            if var in self.globls and id(
                    self.globls[var]) in self.objs_to_inline:
                return cst.RemoveFromParent()

        return updated_node

    def leave_Attribute(self, original_node, updated_node):
        attr = updated_node
        attr_name = attr.attr.value
        if m.matches(attr.value, m.Name()):
            name = attr.value.value
            if name in self.globls:
                obj = self.globls[name]
                if id(obj) in self.objs_to_inline:
                    attr_obj = getattr(obj, attr_name)

                    assert not inspect.isfunction(
                        attr_obj
                    ), f'Cannot convert class {name} with un-inlined method {a2s(attr)}'

                    if attr_name not in obj.__dict__:
                        cls_name = obj.__class__.__name__
                        return parse_expr(f'{cls_name}.{attr_name}')

                    else:
                        new_name = self.objs_to_inline[id(obj)]
                        return cst.Name(f'{attr_name}{SEP}{new_name}')

        return updated_node
