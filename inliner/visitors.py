import ast
import copy
import inspect

from .common import *


class FindFunctions(ast.NodeVisitor):
    def __init__(self):
        self.fns = []

    def visit_FunctionDef(self, fdef):
        self.fns.append(fdef.name)
        self.generic_visit(fdef)


class ExpandObjs(ast.NodeTransformer):
    def __init__(self, globls, objs_to_inline):
        self.globls = globls
        self.objs_to_inline = objs_to_inline

    def visit_Attribute(self, attr):
        if isinstance(attr.value, ast.Name):
            name = attr.value.id
            if name in self.globls:
                obj = self.globls[name]
                if id(obj) in self.objs_to_inline:
                    new_name = self.objs_to_inline[id(obj)]
                    return ast.Name(id=f'{new_name}{SEP}{attr.attr}')
        else:
            self.generic_visit(attr)

        return attr


class Rename(ast.NodeTransformer):
    def __init__(self, src, dst):
        self.src = src
        self.dst = dst

    def visit_FunctionDef(self, fdef):
        if fdef.name == self.src:
            fdef.name = self.dst
            self.generic_visit(fdef)
        else:
            args = fdef.args
            arg_names = set()

            for arg in args.args:
                arg_names.add(arg.arg)
            if args.vararg is not None:
                arg_names.add(args.vararg.arg)
            if args.kwarg is not None:
                arg_names.add(args.kwarg.arg)

            if self.src not in arg_names:
                self.generic_visit(fdef)
        return fdef

    def visit_Name(self, name):
        if name.id == self.src:
            name.id = self.dst
        return name


class Replace(ast.NodeTransformer):
    def __init__(self, name, value):
        self.name = name
        self.value = value
        self.replaced = False

    def visit_Name(self, name):
        if name.id == self.name:
            self.replaced = True
            return self.value
        else:
            return name


class FindAssignments(ast.NodeVisitor):
    def __init__(self):
        self.names = set()

    def visit_Assign(self, assgn):
        for t in assgn.targets:
            if isinstance(t, ast.Name):
                self.names.add(t.id)


class FindCall(ast.NodeTransformer):
    def __init__(self, name, globls, locls, should_inline_obj):
        self.call_obj = None
        self.call_expr = None
        self.name = name
        self.globls = globls
        self.locls = locls
        self.should_inline_obj = should_inline_obj

    def visit_Call(self, call_expr):
        try:
            call_obj = eval(a2s(call_expr.func), self.globls, self.locls)
        except Exception:
            print('ERROR', a2s(call_expr))
            raise

        if self.should_inline_obj(call_obj):
            if self.call_expr is not None:
                raise Exception("Multiple valid call expr")

            self.call_expr = call_expr
            self.call_obj = call_obj
            return ast.Name(id=self.name)
        else:
            self.generic_visit(call_expr)

        return call_expr


class FindProperty(ast.NodeTransformer):
    def __init__(self, ret_var, globls, should_inilne_obj):
        self.prop_obj = None
        self.prop_expr = None
        self.ret_var = ret_var
        self.globls = globls

    def visit_Attribute(self, attr):
        try:
            prop_obj = eval(a2s(attr.value), self.globls, self.globls)
        except Exception:
            print('ERROR', a2s(attr.value))
            raise

        # TODO: inline property
        if self.should_inline_obj(prop_obj):
            self.prop_obj = prop_obj
            self.prop_expr = attr


class ReplaceReturn(ast.NodeTransformer):
    def __init__(self, name):
        self.name = name
        self.toplevel = True
        self.found_return = False
        self.if_wrapper = parse_stmt(
            textwrap.dedent("""
        if "{name}" not in locals() and "{name}" not in globals():
            pass
            """.format(name=self.name)))

    def visit_Return(self, stmt):
        if_stmt = copy.deepcopy(self.if_wrapper)
        if_stmt.body[0] = ast.Assign(targets=[ast.Name(id=self.name)],
                                     value=stmt.value)
        self.found_return = True
        return if_stmt

    def visit_FunctionDef(self, fdef):
        # no recurse to avoid messing up inline functions
        if self.toplevel:
            self.toplevel = False
            self.generic_visit(fdef)
        return fdef

    def generic_visit(self, node):
        for field, old_value in ast.iter_fields(node):
            if isinstance(old_value, list):
                new_values = []
                for i, cur_value in enumerate(old_value):
                    if isinstance(cur_value, ast.AST):
                        value = self.visit(cur_value)

                        if self.found_return:
                            new_values.append(value)
                            if i < len(old_value) - 1:
                                if_stmt = copy.deepcopy(self.if_wrapper)
                                if_stmt.body = old_value[i + 1:]
                                new_values.append(if_stmt)
                            break

                        if value is None:
                            continue
                        elif not isinstance(value, ast.AST):
                            new_values.extend(value)
                            continue

                    new_values.append(value)
                old_value[:] = new_values
            elif isinstance(old_value, ast.AST):
                new_node = self.visit(old_value)
                if new_node is None:
                    delattr(node, field)
                else:
                    setattr(node, field, new_node)

        return node


class ReplaceYield(ast.NodeTransformer):
    def __init__(self, ret_var):
        self.ret_var = ret_var

    def visit_Yield(self, expr):
        append = parse_expr(f'{self.ret_var}.append()')
        append.args.append(expr.value)
        return append


class ReplaceSelf(ast.NodeTransformer):
    def __init__(self, cls, globls):
        self.cls = cls
        self.globls = globls

    def visit_Call(self, expr):
        if isinstance(expr.func, ast.Attribute) and \
            isinstance(expr.func.value, ast.Name) and \
            expr.func.value.id == 'self':

            expr.func.value = ast.Name(id=self.cls.__name__)

            # If the method being called is bound when directly accessing
            # it on the class, it's probably a @classmethod, and we shouldn't
            # add `self` as an argument
            if not inspect.ismethod(getattr(self.cls, expr.func.attr)):
                expr.args.insert(0, ast.Name(id='self'))

        return expr


class ReplaceSuper(ast.NodeTransformer):
    def __init__(self, cls):
        self.cls = cls

    def visit_Call(self, call):
        if isinstance(call.func, ast.Attribute) and \
           isinstance(call.func.value, ast.Call) and \
           isinstance(call.func.value.func, ast.Name) and \
           call.func.value.func.id == 'super':
            call.func.value = ast.Name(id=self.cls.__name__)
            call.args.insert(0, ast.Name(id='self'))
        self.generic_visit(call)
        return call


class UsedGlobals(ast.NodeVisitor):
    def __init__(self, globls):
        self.globls = globls
        self.used = {}

    def visit_Name(self, name):
        if name.id in self.globls:
            self.used[name.id] = self.globls[name.id]


class FindComprehension(ast.NodeTransformer):
    def __init__(self, find_call, ret_var):
        self.find_call = find_call
        self.ret_var = ret_var
        self.comp = None

    def visit_ListComp(self, comp):
        self.find_call.visit(comp)
        if self.find_call.call_expr is not None:
            self.comp = comp
            return ast.Name(id=self.ret_var)
        else:
            return comp


class FindIfExp(ast.NodeTransformer):
    def __init__(self, ret_var):
        self.ret_var = ret_var
        self.ifexp = None

    def visit_IfExp(self, ifexp):
        self.ifexp = ifexp
        return ast.Name(id=self.ret_var)


class CollectLineNumbers(ast.NodeVisitor):
    def __init__(self):
        self.linenos = set()

    def generic_visit(self, node):
        if hasattr(node, 'lineno'):
            self.linenos.add(node.lineno)
        super().generic_visit(node)
