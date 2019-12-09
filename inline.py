import ast
import astor
import inspect
from collections import defaultdict
from iterextras import unzip
import textwrap
import sys
from astpretty import pprint as pprintast
from pprint import pprint
import dis
from utils import *
import copy
import typing
import os


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


class Inliner:
    def __init__(self, func, modules):
        self.stmts = ast.parse(inspect.getsource(func)).body[0].body
        self.modules = [m.split('.') for m in modules]
        self.counter = 0

    def fresh(self):
        v = 'var{}'.format(self.counter)
        self.counter += 1
        return v

    def is_source_obj(self, obj):
        try:
            if os.path.basename(inspect.getfile(obj))[:6] == 'inline':
                return True
        except TypeError:
            return False

    def should_inline_obj(self, obj):
        module = inspect.getmodule(obj)

        if self.is_source_obj(obj):
            return True

        if module is not None:
            module_parts = module.__name__.split('.')
            return any([
                module_parts[:len(target_mod)] == target_mod
                for target_mod in self.modules
            ])

        return False

    def inline_constructor(self, call_obj, call_expr, ret_var, globls):
        cls = call_obj.__name__
        imprt = ast.ImportFrom(module=inspect.getmodule(call_obj).__name__,
                               level=0,
                               names=[ast.alias(name=cls, asname=None)])
        make_obj = ast.Assign(targets=[ast.Name(id=ret_var)],
                              value=parse_expr(f'{cls}.__new__({cls})'))
        call_expr.args.insert(0, ast.Name(id=ret_var))
        return [imprt, make_obj] + self.inline_function(
            call_obj.__init__, call_expr, ret_var, globls, cls=call_obj)

    def expand_method(self, call_obj, call_expr, ret_var):
        obj = call_expr.func.value
        bound_obj = call_obj.__self__
        if inspect.isclass(bound_obj):
            cls = bound_obj
            call_expr.func = ast.Attribute(value=ast.Attribute(
                value=ast.Name(id=cls.__name__), attr=call_expr.func.attr),
                                           attr='__func__')
        else:
            cls = bound_obj.__class__
            call_expr.func = ast.Attribute(value=ast.Name(id=cls.__name__),
                                           attr=call_expr.func.attr)
        call_expr.args.insert(0, obj)
        return self.generate_imports(cls.__name__, cls)

    def inline_generator_function(self, call_obj, call_expr, ret_var, globls):
        raise Exception("TODO")

    def inline_function(self,
                        call_obj,
                        call_expr,
                        ret_var,
                        globls,
                        cls=None,
                        debug=False):
        new_stmts = [ast.Expr(ast.Str("__comment: " + a2s(call_expr).strip()))]
        is_special_method = hasattr(call_obj, '__objclass__')
        if is_special_method:
            # TODO: make this work for all slot wrappers
            f_source = """
            def _(*args):
                return list(*args)
            """
        else:
            f_source = inspect.getsource(call_obj)
        f_source = textwrap.dedent(f_source)

        if debug:
            print('Expanding {}'.format(a2s(call_expr)))

        f_ast = parse_stmt(f_source)
        args_def = f_ast.args

        if len(args_def.args) > 0 and args_def.args[0].arg == 'self' and \
           isinstance(call_expr.func, ast.Attribute) and \
           isinstance(call_expr.func.value, ast.Name):

            if cls is None:
                cls = globls[call_expr.func.value.id]

            ReplaceSuper(cls.__bases__[0]).visit(f_ast)

        if cls is not None:
            ReplaceSelf(cls, globls).visit(f_ast)

        def make_unique_name(name):
            return f'{name}{SEP}{f_ast.name}'

        args = call_expr.args[:]

        assgn_finder = FindAssignments()
        assgn_finder.visit(f_ast)
        arg_names = set([arg.arg for arg in args_def.args])
        for name in assgn_finder.names:
            if name not in arg_names:
                unique_name = make_unique_name(name)
                renamer = Rename(name, unique_name)
                for stmt in f_ast.body:
                    renamer.visit(stmt)

        if len(call_expr.args) > 0 and \
           isinstance(call_expr.args[-1], ast.Starred):
            star_arg = call_expr.args.pop().value
            num_star_args = len(eval(a2s(star_arg), globls, globls))
            call_star_args = [
                ast.Subscript(value=star_arg, slice=ast.Index(value=ast.Num(i)))
                for i in range(num_star_args)
            ]
        else:
            star_arg = None

        # if call_expr has f(**kwargs)
        star_kwarg = [arg for arg in call_expr.keywords if arg.arg is None]
        star_kwarg = star_kwarg[0].value if len(star_kwarg) > 0 else None

        if star_kwarg is not None:
            star_kwarg_keys = eval(a2s(star_kwarg), globls, globls).keys()
            call_star_kwarg = {
                key: ast.Subscript(value=star_kwarg,
                                   slice=ast.Index(value=ast.Str(key)))
                for key in star_kwarg_keys
            }

        call_anon_args = call_expr.args[:]
        call_kwargs = {
            arg.arg: arg.value
            for arg in call_expr.keywords if arg.arg is not None
        }

        nodefault = len(args_def.args) - len(args_def.defaults)
        anon_defaults = {
            arg.arg: default
            for arg, default in zip(args_def.args[nodefault:],
                                    args_def.defaults)
        }

        # Add argument bindings
        for arg in args_def.args:
            k = arg.arg

            # Get value corresponding to argument name
            if len(call_anon_args) > 0:
                v = call_anon_args.pop(0)
            elif star_arg is not None and len(call_star_args) > 0:
                v = call_star_args.pop(0)
            elif k in call_kwargs:
                v = call_kwargs.pop(k)
            elif star_kwarg is not None and k in call_star_kwarg:
                v = call_star_kwarg.pop(k)
            else:
                v = anon_defaults.pop(k)

            # Rename to unique var name
            uniq_k = make_unique_name(k)
            renamer = Rename(k, uniq_k)
            for stmt in f_ast.body:
                renamer.visit(stmt)

            stmt = ast.Assign(targets=[ast.Name(id=uniq_k)], value=v)
            new_stmts.append(stmt)

        for arg in args_def.kwonlyargs:
            raise Exception("Not yet implemented")

        if args_def.vararg is not None:
            k = args_def.vararg.arg
            v = call_anon_args[:]
            if star_arg is not None:
                v += call_star_args
            new_stmts.append(
                ast.Assign(targets=[ast.Name(id=k)], value=ast.List(v)))

        if args_def.kwarg is not None:
            kwkeys, kwvalues = unzip(call_kwargs.items())
            new_stmts.append(
                ast.Assign(targets=[ast.Name(id=args_def.kwarg.arg)],
                           value=ast.Dict([ast.Str(s) for s in kwkeys],
                                          kwvalues)))

        # Replace returns with assignment
        f_ast.body.append(parse_stmt("return None"))
        while True:
            replacer = ReplaceReturn(ret_var)
            replacer.visit(f_ast)
            if not replacer.found_return:
                break

        # Inline function body
        new_stmts.extend(f_ast.body)

        if not is_special_method and not self.is_source_obj(call_obj):
            used_globals = UsedGlobals(call_obj.__globals__)
            used_globals.visit(f_ast)
            used = used_globals.used

            if call_obj.__closure__ is not None and len(
                    call_obj.__closure__) > 0:
                cell = call_obj.__closure__[0]
                for var, cell in zip(call_obj.__code__.co_freevars,
                                     call_obj.__closure__):
                    used[var] = cell.cell_contents

            imports = []
            for name, globl in used_globals.used.items():
                imprt = self.generate_imports(name, globl)
                if imprt is not None:
                    new_stmts.insert(0, imprt)

        return new_stmts

    def generate_imports(self, name, globl):
        if inspect.ismodule(globl):
            alias = name if globl.__name__ != name else None
            return ast.Import([ast.alias(name=globl.__name__, asname=alias)])
        else:
            mod = inspect.getmodule(globl)
            if mod is None or mod is typing:
                mod_value = obj_to_ast(globl)
                return ast.Assign(targets=[ast.Name(id=name)], value=mod_value)
            elif mod == __builtins__:
                return None
            else:
                return ast.ImportFrom(module=mod.__name__,
                                      names=[ast.alias(name=name, asname=None)],
                                      level=0)

    def expand_comprehension(self, comp, ret_var, call_finder, globls):
        forloop = None
        for gen in reversed(comp.generators):
            if forloop is None:
                body = []
                body.extend(
                    self.inline_function(call_finder.call_obj,
                                         call_finder.call_expr,
                                         call_finder.name, globls))
                append = parse_expr(f'{ret_var}.append()')
                append.args = [comp.elt]
                body.append(ast.Expr(append))
            else:
                body = [forloop]

            forloop = ast.For(target=gen.target,
                              iter=gen.iter,
                              body=body,
                              orelse=[])

        init = parse_stmt(f'{ret_var} = []')

        return [init, forloop]

    def expand_ifexp(self, ifexp, ret_var):
        def assgn(value):
            return ast.Assign(targets=[ast.Name(id=ret_var)], value=value)

        return [
            ast.If(test=ifexp.test,
                   body=[assgn(ifexp.body)],
                   orelse=[assgn(ifexp.orelse)])
        ]

    def make_program(self, comments=False):
        return '\n'.join(
            [a2s(stmt, comments=comments).rstrip() for stmt in self.stmts])

    def stmt_recurse(self, stmts, f, blocks_also=False):
        def aux(stmts):
            new_stmts = []
            for stmt in stmts:
                if isinstance(stmt, ast.If):
                    stmt.body = aux(stmt.body)
                    stmt.orelse = aux(stmt.orelse)
                    new_stmts.extend(f(stmt) if blocks_also else [stmt])
                elif isinstance(stmt, ast.For):
                    stmt.body = aux(stmt.body)
                    new_stmts.extend(f(stmt) if blocks_also else [stmt])
                elif isinstance(stmt, ast.FunctionDef):
                    stmt.body = aux(stmt.body)
                    new_stmts.extend(f(stmt) if blocks_also else [stmt])
                elif isinstance(stmt, ast.With):
                    stmt.body = aux(stmt.body)
                    new_stmts.extend(f(stmt) if blocks_also else [stmt])
                else:
                    new_stmts.extend(f(stmt))

            return new_stmts

        return aux(stmts)

    def inline(self, debug=False):
        # Can't seem to access local variables in a list comprehension?
        # import x; [x.foo() for _ in range(10)]
        # https://github.com/inducer/pudb/issues/103
        # For now, just only use globals
        globls = {}
        try:
            compile_and_exec(self.make_program(), globls)
        except Exception:
            print(self.make_program())
            raise

        change = False

        def check_inline(stmt):
            nonlocal change
            new_stmts = []

            if isinstance(stmt, ast.For):
                new_stmts = check_inline(stmt.iter)
                stmt.iter = new_stmts.pop()
                return new_stmts + [stmt]
            elif isinstance(stmt, (ast.If, ast.FunctionDef, ast.With)):
                return [stmt]

            ifexp_ret_var = self.fresh()
            ifexp_finder = FindIfExp(ifexp_ret_var)
            ifexp_finder.visit(stmt)
            if ifexp_finder.ifexp is not None:
                change = True
                return self.expand_ifexp(ifexp_finder.ifexp,
                                         ifexp_ret_var) + [stmt]
            self.counter -= 1

            comp_ret_var = self.fresh()
            comp_call_finder = FindCall(self.fresh(), globls, globls,
                                        self.should_inline_obj)
            comp_finder = FindComprehension(comp_call_finder, comp_ret_var)
            comp_finder.visit(stmt)
            if comp_finder.comp is not None:
                change = True
                return self.expand_comprehension(comp_finder.comp, comp_ret_var,
                                                 comp_call_finder) + [stmt]
            self.counter -= 2

            ret_var = self.fresh()
            call_finder = FindCall(ret_var, globls, globls,
                                   self.should_inline_obj)
            call_finder.visit(stmt)

            if call_finder.call_expr is not None:
                call_expr = call_finder.call_expr
                call_obj = call_finder.call_obj

                if inspect.ismethod(call_obj):
                    imprt = self.expand_method(call_obj, call_expr, ret_var)
                    if imprt is not None:
                        new_stmts.insert(0, imprt)
                    new_stmts.append(
                        ast.Assign(targets=[ast.Name(id=ret_var)],
                                   value=call_expr))
                elif inspect.isgeneratorfunction(call_obj):
                    new_stmts.extend(
                        self.inline_generator_function(call_obj, call_expr,
                                                       ret_var, globls))
                elif inspect.isfunction(call_obj):
                    new_stmts.extend(
                        self.inline_function(call_obj,
                                             call_expr,
                                             ret_var,
                                             globls,
                                             debug=debug))
                elif inspect.isclass(call_obj):
                    new_stmts.extend(
                        self.inline_constructor(call_obj, call_expr, ret_var,
                                                globls))
                else:
                    raise NotYetImplemented

                change = True
            else:
                self.counter -= 1

            new_stmts.append(stmt)
            return new_stmts

        self.stmts = self.stmt_recurse(self.stmts,
                                       check_inline,
                                       blocks_also=True)
        return change

    def expand_self(self):
        globls = {}
        exec(self.make_program(), globls, globls)

        objs_to_inline = {}
        for var, obj in globls.items():
            if self.should_inline_obj(obj) and not inspect.isclass(obj) and \
               not inspect.ismodule(obj):
                if id(obj) not in objs_to_inline:
                    objs_to_inline[id(obj)] = self.fresh()

        def self_assign(stmt):
            if isinstance(stmt, ast.Assign) and \
               isinstance(stmt.targets[0], ast.Name):
                name = stmt.targets[0].id
                obj = globls[name]

                if id(obj) in objs_to_inline:
                    new_name = objs_to_inline[id(obj)]
                    if isinstance(stmt.value, ast.Call):
                        return [
                            ast.Assign(
                                targets=[ast.Name(id=f'{new_name}{SEP}{k}')],
                                value=ast.NameConstant(None))
                            for k in vars(obj).keys()
                        ]
                    else:
                        return []

            return [stmt]

        self.stmts = self.stmt_recurse(self.stmts, self_assign)

        expander = ExpandObjs(globls, objs_to_inline)
        for stmt in self.stmts:
            expander.visit(stmt)

    def clean_imports(self):
        imports = []
        new_stmts = []

        def collect_imports(stmt):
            nonlocal imports
            if isinstance(stmt, ast.Import) or isinstance(stmt, ast.ImportFrom):
                imports.append(stmt)
                return []
            else:
                return [stmt]

        new_stmts = self.stmt_recurse(self.stmts, collect_imports)

        imports_dedup = [
            imprt for i, imprt in enumerate(imports) if
            not any([compare_ast(imprt, imprt2) for imprt2 in imports[i + 1:]])
        ]

        new_stmts = imports_dedup + new_stmts
        self.stmts = new_stmts

    def unread_vars(self, debug=False):
        prog = self.make_program()
        tracer = Tracer(prog, opcode=True, debug=debug)
        tracer.trace()

        self.stmts = ast.parse(prog).body

        change = False
        new_stmts = []
        for stmt in self.stmts:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and \
               isinstance(stmt.targets[0], ast.Name):
                name = stmt.targets[0].id
                if len(tracer.reads[name]) == 0:
                    change = True
                else:
                    new_stmts.append(stmt)

            elif isinstance(stmt, ast.ImportFrom):
                aliases = [
                    alias for alias in stmt.names
                    if len(tracer.reads[alias.name if alias.
                                        asname is None else alias.asname]) > 0
                ]
                if len(aliases) != len(stmt.names):
                    change = True

                if len(aliases) > 0:
                    stmt.names = aliases
                    new_stmts.append(stmt)
            else:
                new_stmts.append(stmt)
        self.stmts = new_stmts
        return change

    def copy_propagation(self):
        prog = self.make_program()
        tracer = Tracer(prog, opcode=True)
        tracer.trace()

        # TODO: make copy propagation work for nested blocks
        # idea: if tracer.counts == # of block-level executions

        self.stmts = ast.parse(prog).body

        toplevel_assignments = {}
        for stmt in self.stmts:
            if isinstance(stmt, ast.Assign) and \
               len(stmt.targets) == 1 and \
               isinstance(stmt.targets[0], ast.Name):
                k = stmt.targets[0].id
                assert k not in toplevel_assignments
                try:
                    # For some reason, exceptions don't occur until usage of
                    # truth is put into an if statement
                    if robust_eq(tracer.stores[k][0][0],
                                 tracer.stores[k][-1][0]):
                        val_eq = True
                    else:
                        val_eq = False
                except Exception as e:
                    if debug:
                        print('Could not compare for equality:')
                        print('Inital', tracer.initial_values[k])
                        print('Final', tracer.globls[k])
                        print(e)
                        print('=' * 30)
                    val_eq = False

                if tracer.set_count[k] == 1 and val_eq and \
                   isinstance(stmt.value, \
                              (ast.Num, ast.Str, ast.NameConstant, ast.Name, ast.Attribute, ast.Tuple)):
                    toplevel_assignments[k] = stmt

        new_stmts = []
        for i, stmt in enumerate(self.stmts):
            if isinstance(stmt, ast.Assign) and \
               isinstance(stmt.targets[0], ast.Name) and \
               stmt.targets[0].id in toplevel_assignments:
                name = stmt.targets[0].id
                for stmt2 in self.stmts[i + 1:]:
                    replacer = Replace(name, toplevel_assignments[name].value)
                    replacer.visit(stmt2)
            else:
                new_stmts.append(stmt)

        self.stmts = new_stmts

    def lifetimes(self):
        prog = self.make_program()
        tracer = Tracer(prog, opcode=True)
        tracer.trace()

        self.stmts = ast.parse(prog).body

        unused_stores = defaultdict(list)
        for k, stores in tracer.stores.items():
            reads = tracer.reads[k]

            for i, (_, store_line) in enumerate(stores):
                next_possible_stores = [
                    line for _, line in stores[i + 1:] if line > store_line
                ]
                next_store_line = min(next_possible_stores, default=10000000)

                unused = True
                for (_, read_line) in reads:
                    if store_line < read_line and read_line <= next_store_line:
                        unused = False

                if unused:
                    unused_stores[k].append(store_line)

        def remove_unused(stmt):
            if isinstance(stmt, ast.Assign) and \
               len(stmt.targets) == 1 and \
               isinstance(stmt.targets[0], ast.Name):

                # special case for assignments like "x = x"
                if compare_ast(stmt.targets[0], stmt.value):
                    return []

                name = stmt.targets[0].id
                unused_lines = unused_stores[name]

                collect_lineno = CollectLineNumbers()
                collect_lineno.visit(stmt)

                if len(set(unused_lines) & collect_lineno.linenos) > 0:
                    return []

            return [stmt]

        self.stmts = self.stmt_recurse(self.stmts, remove_unused)

    def expand_tuples(self):
        def expand(stmt):
            if isinstance(stmt, ast.Assign) and isinstance(
                    stmt.value, ast.Tuple):
                if len(stmt.targets) > 1:
                    targets = stmt.targets
                elif isinstance(stmt.targets[0], ast.Tuple):
                    targets = stmt.targets[0].elts
                else:
                    return [stmt]

                if all([
                        isinstance(elt,
                                   (ast.Name, ast.Num, ast.Str,
                                    ast.NameConstant, ast.Attribute, ast.Tuple))
                        for elt in stmt.value.elts
                ]):
                    return [
                        ast.Assign(targets=[name], value=elt)
                        for name, elt in zip(targets, stmt.value.elts)
                    ]
            return [stmt]

        self.stmts = self.stmt_recurse(self.stmts, expand)

    def deadcode(self):
        prog = self.make_program()
        try:
            self.stmts = ast.parse(prog).body
        except Exception:
            print(prog)
            raise

        execed_lines = defaultdict(int)

        tracer = Tracer(prog)
        tracer.trace()

        def is_dead(node):
            collect_lineno = CollectLineNumbers()
            collect_lineno.visit(node)
            return sum([tracer.execed_lines[i]
                        for i in collect_lineno.linenos]) == 0

        change = False

        def is_comment(stmt):
            return isinstance(stmt, ast.Expr) and \
                isinstance(stmt.value, ast.Str) and \
                '__comment' in stmt.value.s

        def len_no_comment(stmts):
            return len([s for s in stmts if not is_comment(s)])

        def check_deadcode(stmt):
            nonlocal change

            if is_comment(stmt):
                return [stmt]

            if is_dead(stmt):
                change = True
                return []

            new_stmts = []
            if isinstance(stmt, ast.If):
                # TODO: assumes pure conditions
                if len_no_comment(stmt.body) == 0 or is_dead(stmt.body[0]):
                    change = True
                    new_stmts.extend(stmt.orelse)
                elif len_no_comment(stmt.orelse) == 0 or is_dead(
                        stmt.orelse[0]):
                    change = True
                    new_stmts.extend(stmt.body)
                else:
                    new_stmts.append(stmt)
            elif isinstance(stmt, ast.For):
                if len_no_comment(stmt.body) == 0:
                    change = True
                else:
                    new_stmts.append(stmt)
            elif isinstance(stmt, ast.Expr):
                val = stmt.value
                if isinstance(val, (ast.Name, ast.Str, ast.NameConstant)):
                    change = True
                else:
                    new_stmts.append(stmt)
            elif isinstance(stmt, ast.Try):
                if not is_dead(stmt.handlers[0]):
                    # HUGE HACK: assumes it's safe to replace try/except
                    # with just except block if except block not dead
                    assert len_no_comment(stmt.handlers) == 1
                    assert stmt.handlers[0].name is None
                    change = True
                    new_stmts.extend(stmt.handlers[0].body)
                else:
                    new_stmts.extend(stmt.body)
            elif isinstance(stmt, ast.FunctionDef):
                if len_no_comment(stmt.body) == 0:
                    change = True
                else:
                    new_stmts.append(stmt)
            else:
                new_stmts.append(stmt)

            return new_stmts

        self.stmts = self.stmt_recurse(self.stmts,
                                       check_deadcode,
                                       blocks_also=True)
        return change

    def remove_suffixes(self):
        # TODO: make this robust by avoiding name collisions
        remover = RemoveSuffix()
        for stmt in self.stmts:
            remover.visit(stmt)

    def fixpoint(self, f):
        while f():
            pass
