import libcst as cst
import libcst.matchers as m
import inspect

from .base_pass import BasePass
from ..common import a2s, EvalException, get_function_locals, parse_statement, parse_expr
from .. import transforms


class InlinePass(BasePass):
    def __init__(self, add_comments=True):
        super().__init__()
        self.add_comments = add_comments

    def _inline(self, ret_var, call, func_obj):
        if inspect.isgeneratorfunction(func_obj):
            new_stmts = transforms.inline_generator(
                func_obj, call, ret_var, add_comments=self.add_comments)
        elif inspect.isfunction(func_obj):
            new_stmts = transforms.inline_function(
                func_obj, call, ret_var, add_comments=self.add_comments)
        elif inspect.isclass(func_obj):
            new_stmts = transforms.inline_constructor(
                func_obj, call, ret_var, add_comments=self.add_comments)
        elif inspect.ismethod(func_obj):
            new_stmts = transforms.inline_method(func_obj,
                                                 call,
                                                 ret_var,
                                                 add_comments=self.add_comments)
        else:
            raise NotImplemented

        self.insert_statements_before_current(new_stmts)

    def _func_name(self, func):
        if m.matches(func, m.Name()):
            return func.value
        elif m.matches(func, m.Attribute()):
            return func.attr.value
        else:
            return 'func'

    def _should_inline(self, func, func_obj):
        # If a function was generated by a higher-order function, we can't
        # directly inline it, must be inlined through the generator. This
        # is detected by checking if the function object has a closure.
        if not self.inliner.is_source_obj(func_obj):
            closure = get_function_locals(func_obj)
            if len(closure) > 0 and \
               not (len(closure) == 1
                    and next(iter(closure.keys())) == '__class__'):
                fdef = parse_statement(inspect.getsource(func_obj))

                if len(fdef.decorators) == 0:
                    return False

        # Can't inline the output of a higher order function directly
        not_higher_order = not m.matches(func, m.Call())

        return not_higher_order and self.inliner.should_inline(func)

    def leave_Call(self, _, call):
        func = call.func

        try:
            func_obj = self.inliner._eval(func)
        except EvalException as e:
            return call

        if self._should_inline(func, func_obj):
            func_name = self._func_name(func)
            ret_var = self.fresh_var(f'{func_name}_ret')

            self._inline(ret_var, call, func_obj)

            return cst.Name(ret_var)

        return call

    def _is_property(self, node):
        assert isinstance(node, cst.Attribute)

        # for example, foo.x where the class of foo has @property def x()
        try:
            # get the runtime object for foo
            prop_obj = self.inliner._eval(node.value)
        except Exception:
            # if we can't find it, ignore
            return None

        # if foo should be inlined, and it is an instance of a class,
        # and the class has the attribute, and the attribute is a property
        attr_str = node.attr.value
        if self.inliner.should_inline(node.value) and \
           hasattr(prop_obj, '__class__') and \
           hasattr(prop_obj.__class__, attr_str):
            prop = getattr(prop_obj.__class__, attr_str)
            if isinstance(prop, property):
                return (prop, prop_obj)

        return None

    # Classes using @property have accessors that are actually calling
    # functions. This visitor looks for uses of @property.
    def leave_Attribute(self, _, attr):
        ret = self._is_property(attr)
        if ret is not None:
            (prop, prop_obj) = ret
            # foo.x is same as Foo.x.fget(foo), so we treat the property
            # as a function call so we can pass it to the function inliner
            func_obj = prop.fget
            call = parse_expr("{}.{}_getter({})".format(
                prop_obj.__class__.__name__, attr.attr.value, a2s(attr.value)))

            # TODO: need to generate an import for
            # prop_obj.__class__.__name__

            ret_var = self.fresh_var(attr.attr.value)

            self._inline(ret_var, call, func_obj)

            return cst.Name(ret_var)

        return attr

    def _is_property_fset(self, assgn):
        return m.matches(assgn,
                         m.Assign(targets=[m.AssignTarget(m.Attribute())]))

    def visit_Assign(self, assgn):
        # Don't allow visitor to recurse onto LHS of a property assignment
        if self._is_property_fset(assgn):
            return False

    # Also check for @property assignments, e.g. t.x = 1 where this calls
    # a setter
    def leave_Assign(self, _, assgn):
        if self._is_property_fset(assgn):
            target = assgn.targets[0].target
            ret = self._is_property(target)
            if ret is not None:
                (prop, prop_obj) = ret

                func_obj = prop.fset
                call = parse_expr("{}.{}_setter({}, {})".format(
                    prop_obj.__class__.__name__, target.attr.value,
                    a2s(target.value), a2s(assgn.value)))

                ret_var = self.fresh_var(target.attr.value)

                self._inline(ret_var, call, func_obj)

                return cst.RemovalSentinel.REMOVE

        return assgn

    def on_visit(self, node):
        if isinstance(node, cst.BaseComp):
            return False

        return super().on_visit(node)
