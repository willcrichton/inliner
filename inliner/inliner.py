import ast
import inspect
from collections import defaultdict
from iterextras import unzip
import textwrap
import os
import typing
from pprint import pprint
from astpretty import pprint as pprintast

from .common import *
from .visitors import *
from .tracer import FrameAnalyzer, Tracer, compile_and_exec


class Inliner:
    def __init__(self, func, modules):
        self.stmts = ast.parse(textwrap.dedent(
            inspect.getsource(func))).body[0].body
        self.modules = [m.split('.') for m in modules]
        self.generated_vars = defaultdict(int)

    def fresh(self, prefix='var'):
        self.generated_vars[prefix] += 1
        count = self.generated_vars[prefix]
        if count == 1:
            return f'{prefix}'
        else:
            return f'{prefix}_{count}'

    def return_var(self, var):
        self.generated_vars[var.split('_')[0]] -= 1

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

        file_imports = collect_imports(call_obj)
        return self.generate_imports(cls.__name__,
                                     cls,
                                     call_obj=call_obj,
                                     file_imports=file_imports)

    def inline_generator_function(self, call_obj, call_expr, ret_var, globls):
        f_ast = parse_stmt(textwrap.dedent(inspect.getsource(call_obj)))

        new_stmts = [parse_stmt(f'{ret_var} = []')]
        ReplaceYield(ret_var).visit(f_ast)

        new_stmts.extend(
            self.inline_function(call_obj,
                                 call_expr,
                                 ret_var,
                                 globls,
                                 f_ast=f_ast))
        return new_stmts

    def inline_function(self,
                        call_obj,
                        call_expr,
                        ret_var,
                        globls,
                        cls=None,
                        f_ast=None,
                        debug=False):
        new_stmts = [ast.Expr(ast.Str("__comment: " + a2s(call_expr).strip()))]
        is_special_method = hasattr(call_obj, '__objclass__')

        if f_ast is None:
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

        def unique_and_rename(name):
            unique_name = f'{name}{SEP}{f_ast.name}'
            renamer = Rename(name, unique_name)
            for stmt in f_ast.body:
                renamer.visit(stmt)
            return unique_name

        args = call_expr.args[:]

        assgn_finder = FindAssignments()
        assgn_finder.visit(f_ast)
        arg_names = set([arg.arg for arg in args_def.args])
        for name in assgn_finder.names:
            if name not in arg_names:
                unique_and_rename(name)

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

        kw_defaults = {
            arg.arg: default
            for arg, default in zip(args_def.kwonlyargs, args_def.kw_defaults)
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
            uniq_k = unique_and_rename(k)

            stmt = ast.Assign(targets=[ast.Name(id=uniq_k)], value=v)
            new_stmts.append(stmt)

        for arg in args_def.kwonlyargs:
            k = arg.arg

            if k in call_kwargs:
                v = call_kwargs.pop(k)
            elif star_kwarg is not None and k in call_star_kwarg:
                v = call_star_kwarg.pop(k)
            else:
                v = kw_defaults.pop(k)

            uniq_k = unique_and_rename(k)

            stmt = ast.Assign(targets=[ast.Name(id=uniq_k)], value=v)
            new_stmts.append(stmt)

        if args_def.vararg is not None:
            k = unique_and_rename(args_def.vararg.arg)
            v = call_anon_args[:]
            if star_arg is not None:
                v += call_star_args
            new_stmts.append(
                ast.Assign(targets=[ast.Name(id=k)], value=ast.List(elts=v)))

        if args_def.kwarg is not None:
            k = unique_and_rename(args_def.kwarg.arg)
            kwkeys, kwvalues = unzip(call_kwargs.items())
            new_stmts.append(
                ast.Assign(targets=[ast.Name(id=k)],
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

            file_imports = collect_imports(call_obj)

            for name, globl in used_globals.used.items():
                imprt = self.generate_imports(name,
                                              globl,
                                              call_obj=call_obj,
                                              file_imports=file_imports)
                if imprt is not None:
                    new_stmts.insert(0, imprt)

        return new_stmts

    def generate_imports(self, name, globl, call_obj, file_imports):
        if name in file_imports:
            return file_imports[name]

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
            elif inspect.isclass(globl) or inspect.isfunction(globl):
                return ast.ImportFrom(module=mod.__name__,
                                      names=[ast.alias(name=name, asname=None)],
                                      level=0)
            elif call_obj is not None:
                return ast.ImportFrom(
                    module=inspect.getmodule(call_obj).__name__,
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
                expr = ast.Expr(stmt.iter)
                new_stmts = check_inline(expr)
                stmt.iter = expr.value
                return new_stmts[:-1] + [stmt]
            elif isinstance(stmt, (ast.If, ast.FunctionDef, ast.With)):
                return [stmt]

            ifexp_finder = FindIfExp(self.fresh)
            ifexp_finder.visit(stmt)
            if ifexp_finder.ifexp is not None:
                change = True
                return self.expand_ifexp(ifexp_finder.ifexp,
                                         ifexp_finder.ret_var) + [stmt]

            comp_ret_var = self.fresh('comp')
            comp_call_finder = FindCall(self.fresh, globls, globls,
                                        self.should_inline_obj)
            comp_finder = FindComprehension(comp_call_finder, comp_ret_var)
            comp_finder.visit(stmt)
            if comp_finder.comp is not None:
                change = True
                return self.expand_comprehension(comp_finder.comp, comp_ret_var,
                                                 comp_call_finder) + [stmt]

            call_finder = FindCall(self.fresh, globls, globls,
                                   self.should_inline_obj)
            call_finder.visit(stmt)

            if call_finder.call_expr is not None:
                ret_var = call_finder.ret_var
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
                    if hasattr(obj, '__name__'):
                        name = obj.__name__
                    elif hasattr(obj, '__class__'):
                        name = obj.__class__.__name__
                    else:
                        name = 'var'
                    objs_to_inline[id(obj)] = self.fresh(name.lower())

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

        self.stmts = ast.parse(prog).body

        collector = CollectCopyableAssignments(tracer, self.generated_vars)
        self.stmts = [collector.visit(stmt) for stmt in self.stmts]
        self.stmts = [stmt for stmt in self.stmts if stmt is not None]

        for i, (name, value) in enumerate(collector.assignments):
            replacer = Replace(name, value)
            for stmt in self.stmts:
                replacer.visit(stmt)
            for j, (name2, value2) in enumerate(collector.assignments[i + 1:]):
                collector.assignments[i + 1 + j] = (name2,
                                                    replacer.visit(value2))

        return len(collector.assignments) > 0

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

    def simplify_kwargs(self):
        prog = self.make_program()
        tracer = Tracer(prog, opcode=True)
        tracer.trace()
        self.stmts = ast.parse(prog).body

        simplifier = SimplifyKwargs(tracer.globls)
        for stmt in self.stmts:
            simplifier.visit(stmt)

    def fixpoint(self, f):
        while f():
            pass
