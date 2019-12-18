import ast
import inspect

from .base_pass import BasePass
from ..common import a2s, parse_expr, make_name
from ..transforms import ContextualTransforms


class FindCall(ast.NodeTransformer):
    def __init__(self, inliner, globls):
        self.call_obj = None
        self.call_expr = None
        self.inliner = inliner
        self.globls = globls
        self.ret_var = None

    def visit_Attribute(self, attr):
        try:
            prop_obj = eval(a2s(attr.value), self.globls, self.globls)
        except Exception:
            #print('ERROR', a2s(attr.value))
            return attr
            #raise

        if self.inliner.should_inline(prop_obj) and \
           hasattr(prop_obj, '__class__') and \
           hasattr(prop_obj.__class__, attr.attr):
            prop = getattr(prop_obj.__class__, attr.attr)
            if isinstance(prop, property):
                self.call_obj = prop.fget
                self.call_expr = parse_expr("{}_getter({})".format(
                    attr.attr, a2s(attr.value)))
                self.ret_var = self.inliner.fresh('prop_{}'.format(attr.attr))
                return make_name(self.ret_var)

        self.generic_visit(attr)
        return attr

    def get_func_name(self, func):
        if isinstance(func, ast.Name):
            return func.id
        elif isinstance(func, ast.Attribute):
            return func.attr
        else:
            return 'func'

    def visit_Call(self, call_expr):
        try:
            call_obj = eval(a2s(call_expr.func), self.globls, self.globls)
        except Exception:
            # print('ERROR', a2s(call_expr))
            return call_expr
            #raise

        if self.inliner.should_inline(call_obj):
            if self.call_expr is not None:
                print(a2s(call_expr).strip())
                raise Exception("Multiple valid call expr")

            self.call_expr = call_expr
            self.call_obj = call_obj

            func_name = self.get_func_name(call_expr.func)
            self.ret_var = self.inliner.fresh(f'{func_name}_ret')
            return make_name(self.ret_var)

        self.generic_visit(call_expr)
        return call_expr


class FindComprehension(ast.NodeTransformer):
    def __init__(self, find_call, ret_var):
        self.find_call = find_call
        self.ret_var = ret_var
        self.comp = None

    def visit_ListComp(self, comp):
        self.find_call.visit(comp)
        if self.find_call.call_expr is not None:
            self.comp = comp
            return make_name(self.ret_var)
        else:
            return comp


class FindIfExp(ast.NodeTransformer):
    def __init__(self, inliner):
        self.inliner = inliner
        self.ifexp = None
        self.ret_var = None

    def visit_IfExp(self, ifexp):
        self.ifexp = ifexp
        self.ret_var = self.inliner.fresh('ifexp')
        return make_name(self.ret_var)


class InlinePass(BasePass):
    tracer_args = {}

    def __init__(self, inliner):
        super().__init__(inliner)
        self.fns = ContextualTransforms(self.inliner, self.globls)

    def visit_For(self, stmt):
        self.generic_visit(stmt)

        mod = ast.Module([stmt.iter])
        self.visit(mod)
        return mod.body[:-1] + [stmt]

    def visit_With(self, stmt):
        self.generic_visit(stmt)

        context = eval(a2s(stmt.items[0].context_expr), self.globls,
                       self.globls)
        if self.inliner.should_inline(context):
            return self.fns.expand_with(stmt)
        else:
            return [stmt]

    def generic_visit(self, node):
        if isinstance(node, (ast.Assert, ast.Assign, ast.Expr)):
            return self._inline(node)

        return super().generic_visit(node)

    def _inline(self, stmt):
        new_stmts = []

        ifexp_finder = FindIfExp(self.inliner)
        ifexp_finder.visit(stmt)
        if ifexp_finder.ifexp is not None:
            self.change = True
            return self.fns.expand_ifexp(ifexp_finder.ifexp,
                                         ifexp_finder.ret_var) + [stmt]

        comp_ret_var = self.inliner.fresh('comp')
        comp_call_finder = FindCall(self.inliner, self.globls)
        comp_finder = FindComprehension(comp_call_finder, comp_ret_var)
        comp_finder.visit(stmt)
        if comp_finder.comp is not None:
            self.change = True
            return self.fns.expand_comprehension(comp_finder.comp, comp_ret_var,
                                                 comp_call_finder) + [stmt]

        call_finder = FindCall(self.inliner, self.globls)
        call_finder.visit(stmt)

        if call_finder.call_expr is not None:
            ret_var = call_finder.ret_var
            call_expr = call_finder.call_expr
            call_obj = call_finder.call_obj

            if inspect.ismethod(call_obj):
                imprt = self.fns.expand_method(call_obj, call_expr, ret_var)
                if imprt is not None:
                    new_stmts.insert(0, imprt)
                new_stmts.append(
                    ast.Assign(targets=[make_name(ret_var)], value=call_expr))

            elif inspect.isgeneratorfunction(call_obj):
                new_stmts.extend(
                    self.fns.inline_generator_function(call_obj, call_expr,
                                                       ret_var))

            elif inspect.isfunction(call_obj):
                new_stmts.extend(
                    self.fns.inline_function(call_obj, call_expr, ret_var))

            elif inspect.isclass(call_obj):
                new_stmts.extend(
                    self.fns.inline_constructor(call_obj, call_expr, ret_var))

            elif hasattr(call_obj, '__call__'):
                self.fns.expand_callable(call_expr)
                new_stmts.append(
                    ast.Assign(targets=[make_name(ret_var)], value=call_expr))

            else:
                print(call_obj, type(call_obj), a2s(call_expr).strip())
                raise NotYetImplemented

            self.change = True

        new_stmts.append(stmt)
        return new_stmts
