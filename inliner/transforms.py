import inspect
import ast
import textwrap
import itertools
from iterextras import unzip
import typing

from .visitors import RemoveFunctoolsWraps, ReplaceYield, UsedGlobals, \
    ReplaceSuper, Rename, FindAssignments, ReplaceReturn, \
    FindAssignment, collect_imports
from .common import a2s, parse_stmt, parse_expr, make_name, obj_to_ast, SEP, FunctionComment


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

        if call_obj.__init__ is not object.__init__:
            # Inline the __init__ function
            init_inline = self.inline_function(call_obj.__init__,
                                               call_expr,
                                               ret_var,
                                               cls=call_obj)
        else:
            init_inline = []

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

    def inline_imported_object(self, imprt, source_name, imported_name):
        if isinstance(imprt, ast.ImportFrom):
            assert imprt.level == 0
            exec(f'import {imprt.module}', self.globls, self.globls)
            mod_obj = eval(imprt.module, self.globls, self.globls)
        else:
            assert False, "TODO"

        mod_ast = ast.parse(open(inspect.getsourcefile(mod_obj)).read())
        finder = FindAssignment(source_name)
        finder.visit(mod_ast)

        if finder.assgn is not None:
            file_imports = collect_imports(mod_obj)
            assgn = ast.Assign(targets=[make_name(imported_name)],
                               value=finder.assgn)
            return list(file_imports.values()) + [assgn]
        else:
            assert False, "TODO"

    def _expand_decorators(self, new_stmts, f_ast, call_expr, call_obj,
                           ret_var):
        """
        Expand decorator calls to an inlined function.

        Example:
          @foo
          def bar(x):
            return x + 1
          assert bar(1) == 2

          >> becomes >>

          def bar(x):
            return x + 1
          assert foo(bar(1)) == 2
        """
        decorators = f_ast.decorator_list

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

        # TODO: what if decorator has arguments?
        call_expr.func = ast.Call(func=decorators[0],
                                  args=[make_name(f_ast.name)],
                                  keywords=[])
        new_stmts.append(
            ast.Assign(targets=[make_name(ret_var)], value=call_expr))

    def _replace_super(self, f_ast, cls, call_expr, call_obj, new_stmts):
        # If we don't know what the class is, e.g. in Foo.method(foo), then
        # eval the LHS of the attribute, e.g. Foo here
        if cls is None:
            if isinstance(call_expr.func, ast.Attribute):
                cls = eval(a2s(call_expr.func.value), self.globls, self.globls)
            else:
                cls = eval(a2s(call_expr.func), self.globls,
                           self.globls).__class__

        # Add import for base class
        base = cls.__bases__[0]
        file_imports = collect_imports(call_obj)
        new_stmts.insert(
            0,
            self.generate_imports(base.__name__,
                                  base,
                                  call_obj=call_obj,
                                  file_imports=file_imports))

        # HACK: we're assuming super() always refers to the first base class,
        # but it actually depends on the specific method being called and the MRO.
        # THIS IS UNSOUND with multiple inheritance (and potentially even with
        # basic subtype polymorphism?)
        ReplaceSuper(base).visit(f_ast)

    def _bind_arguments(self, f_ast, call_expr, new_stmts):
        args_def = f_ast.args

        # Scope a variable name as unique to the function, and update any references
        # to it in the function
        def unique_and_rename(name):
            unique_name = f'{name}{SEP}{f_ast.name}'
            renamer = Rename(name, unique_name)
            for stmt in f_ast.body:
                renamer.visit(stmt)
            return unique_name

        args = call_expr.args[:]

        # Rename all variables declared in the function that aren't arguments
        assgn_finder = FindAssignments()
        assgn_finder.visit(f_ast)
        arg_names = set([arg.arg for arg in args_def.args])
        for name in assgn_finder.names:
            if name not in arg_names:
                unique_and_rename(name)

        # If function is called with f(*args)
        if len(call_expr.args) > 0 and \
           isinstance(call_expr.args[-1], ast.Starred):
            star_arg = call_expr.args.pop().value

            # Get the length of the star_arg runtime list
            star_arg_obj = eval(a2s(star_arg), self.globls, self.globls)

            # Generate an indexing expression for each element of the list
            call_star_args = [
                ast.Subscript(value=star_arg, slice=ast.Index(value=ast.Num(i)))
                for i in range(len(star_arg_obj))
            ]
        else:
            star_arg = None

        # If function is called with f(**kwargs)
        star_kwarg = [arg for arg in call_expr.keywords if arg.arg is None]
        star_kwarg = star_kwarg[0].value if len(star_kwarg) > 0 else None
        if star_kwarg is not None:
            star_kwarg_dict = eval(a2s(star_kwarg), self.globls, self.globls)
            call_star_kwarg = {
                key: ast.Subscript(value=star_kwarg,
                                   slice=ast.Index(value=ast.Str(key)))
                for key in star_kwarg_dict.keys()
            }

        # Function's anonymous arguments, e.g. f(1, 2) becomes [1, 2]
        call_anon_args = call_expr.args[:]

        # Function's keyword arguments, e.g. f(x=1, y=2) becomes {'x': 1, 'y': 2}
        call_kwargs = {
            arg.arg: arg.value
            for arg in call_expr.keywords if arg.arg is not None
        }

        # Match up defaults with variable names.
        #
        # Python convention is that if function has N arguments and K < N defaults, then
        # the defaults correspond to arguments N - K .. N.
        nodefault = len(args_def.args) - len(args_def.defaults)
        anon_defaults = {
            arg.arg: default
            for arg, default in zip(args_def.args[nodefault:],
                                    args_def.defaults)
        }

        # All keyword-only arguments must have defaults.
        #
        # kwonlyargs occur if a function definition has args AFTER a *args, e.g.
        # the var "y" in `def foo(x, *args, y=1)`
        kw_defaults = {
            arg.arg: default
            for arg, default in zip(args_def.kwonlyargs, args_def.kw_defaults)
        }

        # For each non-keyword-only argument, match it up with the corresponding
        # syntax from the call expression
        for arg in args_def.args:
            k = arg.arg

            # First, match with anonymous arguments
            if len(call_anon_args) > 0:
                v = call_anon_args.pop(0)

            # Then use *args if it exists
            elif star_arg is not None and len(call_star_args) > 0:
                v = call_star_args.pop(0)

            # Then use keyword arguments
            elif k in call_kwargs:
                v = call_kwargs.pop(k)

            # Then use **kwargs if it exists
            elif star_kwarg is not None and k in call_star_kwarg:
                v = call_star_kwarg.pop(k)

            # Otherwise use the default value
            else:
                v = anon_defaults.pop(k)

            # Add a binding from function argument to call argument
            uniq_k = unique_and_rename(k)
            stmt = ast.Assign(targets=[make_name(uniq_k)], value=v)
            new_stmts.append(stmt)

        # Perform equivalent procedure as above, but for keyword-only arguments
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

        # If function definition uses *args, then assign it to the remaining anonymous
        # arguments from the call_expr
        if args_def.vararg is not None:
            k = unique_and_rename(args_def.vararg.arg)
            v = call_anon_args[:]
            if star_arg is not None:
                v += call_star_args
            new_stmts.append(
                ast.Assign(targets=[make_name(k)], value=ast.List(elts=v)))

        # Similarly for **kwargs in the function definition
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

    def _get_nonlocal_vars(self, f_ast, call_obj):
        used_globals = UsedGlobals(call_obj.__globals__)
        used_globals.visit(f_ast)
        used = used_globals.used

        if call_obj.__closure__ is not None and len(call_obj.__closure__) > 0:
            for var, cell in zip(call_obj.__code__.co_freevars,
                                 call_obj.__closure__):
                used[var] = cell.cell_contents

        return used

    def inline_function(self,
                        call_obj,
                        call_expr,
                        ret_var,
                        cls=None,
                        f_ast=None,
                        debug=False):
        if debug:
            print('Inlining {}'.format(a2s(call_expr)))

        # Start by adding the call expression as a comment
        new_stmts = [
            FunctionComment(code=a2s(call_expr), header=True).to_stmt()
        ]

        if f_ast is None:
            # Get the source code for the function
            try:
                f_source = inspect.getsource(call_obj)
            except TypeError:
                print('Failed to get source of {}'.format(a2s(call_expr)))
                raise

            # We have to "dedent" it if the source code is not at the top level
            # (e.g. a class method)
            f_source = textwrap.dedent(f_source)
            self.inliner.length_inlined += len(f_source.split('\n'))

            # Then parse the function into an AST
            f_ast = parse_stmt(f_source)

        # Give the function a fresh name so it won't conflict with other calls to
        # the same function
        f_ast.name = self.inliner.fresh(f_ast.name)

        # If function has decorators, deal with those first. Just inline decorator call
        # and stop there.
        decorators = f_ast.decorator_list
        assert len(decorators) <= 1
        if len(decorators) == 1:
            d = decorators[0]
            builtin_decorator = (
                isinstance(d, ast.Name)
                and (d.id in ['property', 'classmethod', 'staticmethod']))
            derived_decorator = (isinstance(d, ast.Attribute)
                                 and (d.attr in ['setter']))
            if not (builtin_decorator or derived_decorator):
                self._expand_decorators(new_stmts, f_ast, call_expr, call_obj,
                                        ret_var)
                return new_stmts

        # If we're inlining a decorator, we need to remove @functools.wraps calls
        # to avoid messing up inspect.getsource
        for stmt in f_ast.body:
            RemoveFunctoolsWraps().visit(stmt)

        # If the function is a method (which we proxy by first arg being named "self"),
        # then we need to replace uses of special "super" keywords.
        args_def = f_ast.args
        if len(args_def.args) > 0 and args_def.args[0].arg == 'self':
            self._replace_super(f_ast, cls, call_expr, call_obj, new_stmts)

        # Add bindings from arguments in the call expression to arguments in function def
        self._bind_arguments(f_ast, call_expr, new_stmts)

        # Add an explicit return None at the end to reify implicit return
        f_ast.body.append(parse_stmt("return None"))

        # Iteratively replace all return statements with conditional assignments to
        # the ret_var. See ReplaceReturn in visitors.py for how this works.
        while True:
            replacer = ReplaceReturn(ret_var)
            replacer.visit(f_ast)
            if not replacer.found_return:
                break

        # Inline function body
        new_stmts.extend(f_ast.body)
        # new_stmts.append(
        #     FunctionComment(code=a2s(call_expr), header=False).to_stmt())

        # If we're inlining a function not defined in the top-level source, then
        # add imports for all the nonlocal (global + closure) variables
        if not self.inliner.is_source_obj(call_obj):
            used = self._get_nonlocal_vars(f_ast, call_obj)
            file_imports = collect_imports(call_obj)
            for name, value in used.items():
                if name == 'self':  # HACK
                    continue
                imprt = self.generate_imports(name,
                                              value,
                                              call_obj=call_obj,
                                              file_imports=file_imports)
                if imprt is not None:
                    new_stmts.insert(0, imprt)

        return new_stmts

    def generate_imports(self, name, globl, call_obj, file_imports):
        """
        Generate an import statement for a (name, runtime object) pair.


        """
        if name in file_imports:
            return file_imports[name]

        # If we're importing a module, then add an import directly
        if inspect.ismodule(globl):
            # Add an alias if the imported name is different from the module name
            alias = name if globl.__name__ != name else None
            return ast.Import([ast.alias(name=globl.__name__, asname=alias)])
        else:
            # Get module where global is defined
            mod = inspect.getmodule(globl)

            # TODO: When is mod None?
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

            # Can't import builtins
            elif mod == __builtins__:
                return None

            # If the value is a class or function, then import it from the defining
            # module
            elif inspect.isclass(globl) or inspect.isfunction(globl):
                return ast.ImportFrom(module=mod.__name__,
                                      names=[ast.alias(name=name, asname=None)],
                                      level=0)

            # Otherwise import it from the module using the global
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

    def expand_with(self, withstmt):
        assert len(withstmt.items) == 1
        item = withstmt.items[0]

        if item.optional_vars is not None:
            assert isinstance(item.optional_vars, ast.Name)
            name = item.optional_vars.id
        else:
            name = self.inliner.fresh('withctx')

        init = ast.Assign(targets=[make_name(name)], value=item.context_expr)
        enter = parse_stmt(f'{name}.__enter__()')
        exit_ = parse_stmt(f'{name}.__exit__()')
        return [init, enter] + withstmt.body + [exit_]
