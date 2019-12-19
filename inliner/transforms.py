import inspect
import ast
import textwrap
import itertools
from iterextras import unzip
import typing

from .visitors import RemoveFunctoolsWraps, ReplaceYield, UsedGlobals, \
    ReplaceSuper, ReplaceSelf, Rename, FindAssignments, ReplaceReturn, \
    collect_imports
from .common import a2s, parse_stmt, parse_expr, make_name, obj_to_ast, SEP, COMMENT_MARKER


class ContextualTransforms:
    """
    Primary code for performing inlining.

    Inlining code often needs to make reference to either the Inliner object
    or to the global variables generated during the last trace, so we wrap all
    the functions in a ContextualTransforms class that provides access to this
    state.
    """
    def __init__(self, inliner, globls):
        self.inliner = inliner
        self.globls = globls

    def inline_constructor(self, call_obj, call_expr, ret_var):
        """
        Inlines a class constructor.

        Construction has two parts: creating the object with __new__, and
        initializing it with __init__. We insert a __new__ call and then
        inline the __init__ function.

        Example:
          class Foo:
            def __init__(self):
              self.x = 1
          f = Foo()

          >> becomes >>

          f = Foo.__new__(Foo)
          self = f
          self.x = 1
        """
        cls = call_obj.__name__

        # Add an import for the class
        imprt = ast.ImportFrom(module=inspect.getmodule(call_obj).__name__,
                               level=0,
                               names=[ast.alias(name=cls, asname=None)])

        # Create a raw object using __new__
        make_obj = ast.Assign(targets=[make_name(ret_var)],
                              value=parse_expr(f'{cls}.__new__({cls})'))

        # Add the object as an explicit argument to the __init__ function
        call_expr.args.insert(0, make_name(ret_var))

        # Inline the __init__ function
        init_inline = self.inline_function(call_obj.__init__,
                                           call_expr,
                                           ret_var,
                                           cls=call_obj)

        return [imprt, make_obj] + init_inline

    def expand_method(self, call_obj, call_expr, ret_var):
        """
        Replace bound methods with unbound functions.

        Example:
          f = Foo()
          assert f.bar(0) == 1

          >> becomes >>

          f = Foo()
          assert Foo.bar(f, 0) == 1
        """

        call_obj_ast = call_expr.func.value

        # HACK: assume all methods are called syntactically as obj.method()
        # as opposed to x = obj.method; x()
        assert isinstance(call_expr.func, ast.Attribute)

        # Get the object bound to the method
        bound_obj = call_obj.__self__

        # If the method is a classmethod, the method is bound to the class
        if inspect.isclass(bound_obj):
            # The unbound function underlying a classmethod can be accessed
            # through Foo.x.__func__
            clsmethod = ast.Attribute(value=make_name(bound_obj.__name__),
                                      attr=call_expr.func.attr)
            call_expr.func = ast.Attribute(value=clsmethod, attr='__func__')
        else:
            # Rewrite foo.x to Foo.x
            cls = bound_obj.__class__
            call_expr.func = ast.Attribute(value=make_name(cls.__name__),
                                           attr=call_expr.func.attr)

        # Add the object as explicit self parameter
        call_expr.args.insert(0, call_obj_ast)

        # Generate any imports needed
        file_imports = collect_imports(call_obj)
        return self.generate_imports(cls.__name__,
                                     cls,
                                     call_obj=call_obj,
                                     file_imports=file_imports)

    def expand_callable(self, call_expr):
        """
        Expands uses of __call__.

        Example:
          f = Foo()
          assert f() == 1

          >> becomes >>

          f = Foo()
          assert Foo.__call__(f) == 1
        """
        call_expr.func = ast.Attribute(value=call_expr.func, attr='__call__')

    def inline_generator_function(self, call_obj, call_expr, ret_var):
        """
        Inlines generator functions (those using yield).

        There is no easy way to proxy generator semantics/control flow
        without generators, unlike early returns. The simple strategy is to
        eagerly materialize the generator into a list. However, this is both
        inefficient and does not always preserve semantics, e.g. see
        requests.ipynb.

        Example:
          def foo():
            for i in range(10):
              yield i
          for i in foo():
             print(i)

          >> becomes >>
          l = []
          for i in range(10):
            l.append(i)
          for i in l:
            print(i)
        """
        f_ast = parse_stmt(textwrap.dedent(inspect.getsource(call_obj)))

        # Initialize the list
        new_stmts = [parse_stmt(f'{ret_var} = []')]

        # Replace all yield statements by appending to the list
        ReplaceYield(ret_var).visit(f_ast)

        # Then inline the function as normal
        new_stmts.extend(
            self.inline_function(call_obj, call_expr, ret_var, f_ast=f_ast))
        return new_stmts

    def inline_function(self,
                        call_obj,
                        call_expr,
                        ret_var,
                        cls=None,
                        f_ast=None,
                        debug=False):
        new_stmts = [ast.Expr(ast.Str(COMMENT_MARKER + a2s(call_expr).strip()))]

        if f_ast is None:
            f_source = inspect.getsource(call_obj)
            f_source = textwrap.dedent(f_source)

            if debug:
                print('Expanding {}'.format(a2s(call_expr)))

            f_ast = parse_stmt(f_source)

        f_ast.name = self.inliner.fresh(f_ast.name)
        args_def = f_ast.args

        decorators = f_ast.decorator_list
        if len(decorators) > 0:
            if isinstance(decorators[0], ast.Name) and \
               (decorators[0].id == 'property' or decorators[0].id == 'classmethod'):
                pass
            else:
                used_globals = UsedGlobals(call_obj.__globals__)
                used_globals.visit(f_ast)
                used = used_globals.used
                file_imports = collect_imports(call_obj)
                for name, globl in used_globals.used.items():
                    imprt = self.generate_imports(name,
                                                  globl,
                                                  call_obj=call_obj,
                                                  file_imports=file_imports)
                    if imprt is not None:
                        new_stmts.insert(0, imprt)

                f_ast.decorator_list = []
                new_stmts.append(f_ast)

                call_expr.func = ast.Call(func=decorators[0],
                                          args=[make_name(f_ast.name)],
                                          keywords=[])
                new_stmts.append(
                    ast.Assign(targets=[make_name(ret_var)], value=call_expr))
                return new_stmts

        for stmt in f_ast.body:
            RemoveFunctoolsWraps().visit(stmt)

        if len(args_def.args) > 0 and args_def.args[0].arg == 'self' and \
           (cls is not None or
            isinstance(call_expr.func, ast.Attribute) and isinstance(call_expr.func.value, ast.Name)):

            if cls is None:
                cls = self.globls[call_expr.func.value.id]

            ReplaceSuper(cls.__bases__[0]).visit(f_ast)

        if cls is not None:
            ReplaceSelf(cls, self.globls).visit(f_ast)

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
            num_star_args = len(eval(a2s(star_arg), self.globls, self.globls))
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
            star_kwarg_keys = eval(a2s(star_kwarg), self.globls,
                                   self.globls).keys()
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

            stmt = ast.Assign(targets=[make_name(uniq_k)], value=v)
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

            stmt = ast.Assign(targets=[make_name(uniq_k)], value=v)
            new_stmts.append(stmt)

        if args_def.vararg is not None:
            k = unique_and_rename(args_def.vararg.arg)
            v = call_anon_args[:]
            if star_arg is not None:
                v += call_star_args
            new_stmts.append(
                ast.Assign(targets=[make_name(k)], value=ast.List(elts=v)))

        if args_def.kwarg is not None:
            k = unique_and_rename(args_def.kwarg.arg)
            items = call_kwargs.items()
            if star_kwarg is not None:
                items = itertools.chain(items, call_star_kwarg.items())
            kwkeys, kwvalues = unzip(items)
            new_stmts.append(
                ast.Assign(targets=[make_name(k)],
                           value=ast.Dict([ast.Str(s) for s in kwkeys],
                                          kwvalues)))

        # Replace returns with assignment
        f_ast.body.append(parse_stmt("return None"))
        while True:
            replacer = ReplaceReturn(ret_var)
            replacer.visit(f_ast)
            if not replacer.found_return:
                break

        try:
            a2s(f_ast)
        except Exception:
            print(f_ast.name)
            raise

        # Inline function body
        new_stmts.extend(f_ast.body)

        if not self.inliner.is_source_obj(call_obj):
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
                if name == 'self':  # HACK
                    continue
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
                try:
                    mod_value = obj_to_ast(globl)
                    return ast.Assign(targets=[make_name(name)],
                                      value=mod_value)
                except ObjConversionException:
                    return ast.ImportFrom(
                        module=inspect.getmodule(call_obj).__name__,
                        names=[ast.alias(name=name, asname=None)],
                        level=0)

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

    def expand_comprehension(self, comp, ret_var, call_finder):
        forloop = None
        for gen in reversed(comp.generators):
            if forloop is None:
                body = []
                body.extend(
                    self.inline_function(call_finder.call_obj,
                                         call_finder.call_expr,
                                         call_finder.ret_var, self.globls))
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
            return ast.Assign(targets=[make_name(ret_var)], value=value)

        return [
            ast.If(test=ifexp.test,
                   body=[assgn(ifexp.body)],
                   orelse=[assgn(ifexp.orelse)])
        ]

    def expand_with(withstmt):
        assert len(withstmt.items) == 1
        assert withstmt.items[0].optional_vars is None

        enter = parse_expr("None.__enter__()")
        exit_ = parse_expr("None.__exit__()")
        enter.func.value = withstmt.items[0].context_expr
        exit_.func.value = withstmt.items[0].context_expr
        return [enter] + withstmt.body + [exit_]
