import builtins
import inspect
import itertools
import logging as log
import typing

import libcst as cst
import libcst.matchers as m

from .common import (SEP, a2s, get_function_locals, make_assign, make_dict,
                     make_index, make_list, make_string, parse_expr,
                     parse_statement)
from .contexts import ctx_inliner, ctx_pass
from .visitors import (FindAssignments, FindClosedVariables,
                       RemoveFunctoolsWraps, Rename, ReplaceReturn,
                       ReplaceSuper, ReplaceYield, UsedNames, collect_imports)


def bind_arguments(f_ast, call_expr, new_stmts):
    pass_ = ctx_pass.get()

    args_def = f_ast.params
    arg_names = set([arg_def.name.value for arg_def in args_def.params])

    assgn_finder = FindAssignments()
    f_ast.visit(assgn_finder)

    closed_var_finder = FindClosedVariables()
    f_ast.body.visit(closed_var_finder)

    def rename(src, dst):
        nonlocal f_ast
        f_ast = cst.MetadataWrapper(f_ast, unsafe_skip_copy=True).visit(
            Rename(src, dst))

    # Scope a variable name as unique to the function, and update any references
    # to it in the function
    def unique_and_rename(name):
        unique_name = f'{name}{SEP}{f_ast.name.value}'
        rename(name, unique_name)
        return unique_name

    def bind_new_argument(k, v):
        nonlocal f_ast
        # special case: if doing a name copy, e.g. f(x=y), then directly
        # substitute [x -> y] in the inlined function body. Only do this
        # if substitution is legal (x is not assigned or closed).
        # TODO: generalize the != None case
        if isinstance(v, cst.Name) and v.value != 'None' and \
           k not in assgn_finder.names and \
           k not in closed_var_finder.vars:
            rename(k, v.value)
        else:
            # Add a binding from function argument to call argument
            uniq_k = unique_and_rename(k)
            stmt = make_assign(cst.Name(uniq_k), v)
            new_stmts.append(stmt)

    # Rename all variables declared in the function that aren't arguments
    for name in assgn_finder.names:
        if name not in arg_names:
            unique_and_rename(name)

    # If function is called with f(*args)
    star_arg = next(filter(lambda arg: arg.star == '*', call_expr.args), None)
    if star_arg is not None:
        star_arg = star_arg.value

        # Get the length of the star_arg runtime list
        star_arg_obj = pass_.eval(star_arg)

        # Generate an indexing expression for each element of the list
        call_star_args = [
            make_index(star_arg, cst.Integer(str(i)))
            for i in range(len(star_arg_obj))
        ]
    else:
        star_arg = None

    # If function is called with f(**kwargs)
    star_kwarg = next(filter(lambda arg: arg.star == '**', call_expr.args),
                      None)
    if star_kwarg is not None:
        star_kwarg = star_kwarg.value
        star_kwarg_dict = pass_.eval(star_kwarg)
        call_star_kwarg = {
            key: make_index(star_kwarg, make_string(key))
            for key in star_kwarg_dict.keys()
        }

    # Function's anonymous arguments, e.g. f(1, 2) becomes [1, 2]
    call_anon_args = [
        arg.value for arg in call_expr.args
        if arg.keyword is None and arg.star == ''
    ]

    # Function's keyword arguments, e.g. f(x=1, y=2) becomes {'x': 1, 'y': 2}
    call_kwargs = {
        arg.keyword.value: arg.value
        for arg in call_expr.args if arg.keyword is not None and arg.star == ''
    }

    # Match up defaults with variable names.
    #
    # Python convention is that if function has N arguments and K < N defaults, then
    # the defaults correspond to arguments N - K .. N.
    anon_defaults = {
        arg.name.value: arg.default
        for arg in args_def.params if arg.default is not None
    }

    # All keyword-only arguments must have defaults.
    #
    # kwonlyargs occur if a function definition has args AFTER a *args, e.g.
    # the var "y" in `def foo(x, *args, y=1)`
    kw_defaults = {
        arg.name.value: arg.default
        for arg in args_def.kwonly_params
    }

    # For each non-keyword-only argument, match it up with the corresponding
    # syntax from the call expression
    for arg in args_def.params:
        k = arg.name.value

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

        bind_new_argument(k, v)

    # Perform equivalent procedure as above, but for keyword-only arguments
    for arg in args_def.kwonly_params:
        k = arg.name.value

        if k in call_kwargs:
            v = call_kwargs.pop(k)
        elif star_kwarg is not None and k in call_star_kwarg:
            v = call_star_kwarg.pop(k)
        else:
            v = kw_defaults.pop(k)

        bind_new_argument(k, v)

    # If function definition uses *args, then assign it to the remaining anonymous
    # arguments from the call_expr
    if (args_def.star_arg is not cst.MaybeSentinel.DEFAULT
            and not isinstance(args_def.star_arg, cst.ParamStar)):
        k = unique_and_rename(args_def.star_arg.name.value)
        v = call_anon_args[:]
        if star_arg is not None:
            v += call_star_args
        new_stmts.append(make_assign(cst.Name(k), make_list(v)))

    # Similarly for **kwargs in the function definition
    if args_def.star_kwarg is not None:
        k = unique_and_rename(args_def.star_kwarg.name.value)
        items = call_kwargs.items()
        if star_kwarg is not None:
            items = itertools.chain(items, call_star_kwarg.items())
        new_stmts.append(
            make_assign(cst.Name(k),
                        make_dict([(make_string(k), v) for k, v in items])))

    return f_ast


def replace_super(f_ast, cls, call, func_obj, new_stmts):
    pass_ = ctx_pass.get()

    # If we don't know what the class is, e.g. in Foo.method(foo), then
    # eval the LHS of the attribute, e.g. Foo here
    if cls is None:
        if m.matches(call.func, m.Attribute()):
            cls = pass_.eval(call.func.value)
        else:
            cls = pass_.eval(call.func).__class__

    # TODO: support multiple inheritance
    # Add import for base class
    assert len(cls.__bases__) == 1
    base = cls.__bases__[0]
    file_imports = collect_imports(func_obj)
    imprt = generate_import(base.__name__, base, func_obj, file_imports)
    if imprt is not None:
        new_stmts.insert(0, imprt)

    return f_ast.visit(ReplaceSuper(base))


def generate_imports_for_nonlocals(f_ast, func_obj, call):
    used_names = UsedNames()
    cst.MetadataWrapper(f_ast.body).visit(used_names)

    closure = {**func_obj.__globals__, **get_function_locals(func_obj)}
    file_imports = collect_imports(func_obj)

    imports = [
        generate_import(name, closure[name], func_obj, file_imports)
        for name in used_names.names if name in closure
    ]
    imports = [i for i in imports if i]

    return imports


def inline_decorators(f_ast, call, func_obj, ret_var):
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
    decorators = f_ast.decorators

    # TODO
    # used_globals = UsedGlobals(func_obj.__globals__)
    # used_globals.visit(f_ast)
    # used = used_globals.used
    # file_imports = collect_imports(func_obj)
    # for name, globl in used_globals.used.items():
    #     imprt = self.generate_imports(name,
    #                                   globl,
    #                                   func_obj=func_obj,
    #                                   file_imports=file_imports)
    #     if imprt is not None:
    #         new_stmts.insert(0, imprt)

    f_ast = f_ast.with_changes(decorators=[])

    new_call = call.with_changes(
        func=cst.Call(func=decorators[0].decorator, args=[cst.Arg(f_ast.name)]))

    return [f_ast, make_assign(cst.Name(ret_var), new_call)]


def inline_function(func_obj,
                    call,
                    ret_var,
                    cls=None,
                    f_ast=None,
                    is_toplevel=False):
    log.debug('Inlining {}'.format(a2s(call)))

    inliner = ctx_inliner.get()
    pass_ = ctx_pass.get()

    if f_ast is None:
        # Get the source code for the function
        try:
            f_source = inspect.getsource(func_obj)
        except TypeError:
            print('Failed to get source of {}'.format(a2s(call)))
            raise

        # Record statistics about length of inlined source
        inliner.length_inlined += len(f_source.split('\n'))

        # Then parse the function into an AST
        f_ast = parse_statement(f_source)

    # Give the function a fresh name so it won't conflict with other calls to
    # the same function
    f_ast = f_ast.with_changes(name=cst.Name(pass_.fresh_var(f_ast.name.value)))

    # TODO
    # If function has decorators, deal with those first. Just inline decorator call
    # and stop there.
    decorators = f_ast.decorators
    assert len(decorators) <= 1  # TODO: deal with multiple decorators
    if len(decorators) == 1:
        d = decorators[0].decorator
        builtin_decorator = (
            isinstance(d, cst.Name)
            and (d.value in ['property', 'classmethod', 'staticmethod']))
        derived_decorator = (isinstance(d, cst.Attribute)
                             and (d.attr.value in ['setter']))
        if not (builtin_decorator or derived_decorator):
            return inline_decorators(f_ast, call, func_obj, ret_var)

    # # If we're inlining a decorator, we need to remove @functools.wraps calls
    # # to avoid messing up inspect.getsource
    f_ast = f_ast.with_changes(body=f_ast.body.visit(RemoveFunctoolsWraps()))

    new_stmts = []

    # If the function is a method (which we proxy by first arg being named "self"),
    # then we need to replace uses of special "super" keywords.
    args_def = f_ast.params
    if len(args_def.params) > 0:
        first_arg_is_self = m.matches(args_def.params[0],
                                      m.Param(m.Name('self')))
        if first_arg_is_self:
            f_ast = replace_super(f_ast, cls, call, func_obj, new_stmts)

    # Add bindings from arguments in the call expression to arguments in function def
    f_ast = bind_arguments(f_ast, call, new_stmts)

    # Add an explicit return None at the end to reify implicit return
    f_body = f_ast.body
    last_stmt_is_return = m.matches(f_body.body[-1],
                                    m.SimpleStatementLine([m.Return()]))
    if (not is_toplevel and  # If function return is being assigned
            cls is None and  # And not an __init__ fn
            not last_stmt_is_return):
        f_ast = f_ast.with_deep_changes(f_body,
                                        body=list(f_body.body) +
                                        [parse_statement("return None")])

    # Replace returns with if statements
    f_ast = f_ast.with_changes(body=f_ast.body.visit(ReplaceReturn(ret_var)))

    # Inline function body
    new_stmts.extend(f_ast.body.body)

    # Create imports for non-local variables
    imports = generate_imports_for_nonlocals(f_ast, func_obj, call)
    new_stmts = imports + new_stmts

    if inliner.add_comments:
        # Add header comment to first statement
        call_str = a2s(call)
        header_comment = [
            cst.EmptyLine(comment=cst.Comment(f'# {line}'))
            for line in call_str.splitlines()
        ]
        first_stmt = new_stmts[0]
        new_stmts[0] = first_stmt.with_changes(
            leading_lines=[cst.EmptyLine(indent=False)] + header_comment +
            list(first_stmt.leading_lines))

    return new_stmts


def inline_constructor(func_obj, call, ret_var):
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
    cls_name = func_obj.__name__

    # # Add an import for the class
    # cls_module = inspect.getmodule(func_obj).__name__
    # imprt = cst.parse_statement(f'from {cls_module} import {cls_name}')

    # Create a raw object using __new__
    make_obj = make_assign(
        cst.Name(ret_var),
        cst.parse_expression(f'{cls_name}.__new__({cls_name})'))

    # Add the object as an explicit argument to the __init__ function
    call = call.with_changes(args=[cst.Arg(cst.Name(ret_var))] +
                             list(call.args))

    if func_obj.__init__ is not object.__init__:
        # Inline the __init__ function
        init_inline = inline_function(func_obj.__init__,
                                      call,
                                      ret_var,
                                      cls=func_obj)
    else:
        init_inline = []

    return [make_obj] + init_inline


def inline_method(func_obj, call, ret_var):
    """
    Replace bound methods with unbound functions.

    Example:
      f = Foo()
      assert f.bar(0) == 1

      >> becomes >>

      f = Foo()
      assert Foo.bar(f, 0) == 1
    """

    # HACK: assume all methods are called syntactically as obj.method()
    # as opposed to x = obj.method; x()
    assert isinstance(call.func, cst.Attribute)

    method_name = call.func.attr.value

    # Get the object bound to the method
    bound_obj = func_obj.__self__

    # If the method is a classmethod, the method is bound to the class
    if inspect.isclass(bound_obj):
        new_func = f'{bound_obj.__name__}.{method_name}.__func__'
    else:
        new_func = f'{bound_obj.__class__.__name__}.{method_name}'

    new_func = parse_expr(new_func)

    # Add the object as explicit self parameter
    new_call = call.with_changes(func=new_func,
                                 args=[cst.Arg(call.func.value)] +
                                 list(call.args))

    return inline_function(func_obj.__func__, new_call, ret_var)


def inline_generator(func_obj, call, ret_var):
    """
    Inlines generators (those using yield).

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
    f_ast = parse_statement(inspect.getsource(func_obj))

    # Initialize the list
    new_stmts = [parse_statement(f'{ret_var} = []')]

    # Replace all yield statements by appending to the list
    f_ast = f_ast.visit(ReplaceYield(ret_var))

    # Then inline the function as normal
    new_stmts.extend(inline_function(func_obj, call, ret_var, f_ast=f_ast))
    return new_stmts


def generate_import(name, obj, func_obj, file_imports):
    """
    Generate an import statement for a (name, runtime object) pair.
    """
    inliner = ctx_inliner.get()

    # HACK? is this still needed?
    if name == 'self':
        return None

    # If the name is already in scope, don't need to import it
    if name in inliner.base_globls:
        # TODO: name conflicts? e.g. host imports json as x, and
        # another module imports foo as x
        return None

    # If the name appears directly in an import statement in the object's file,
    # then use that import
    if name in file_imports:
        return cst.SimpleStatementLine([file_imports[name]])

    # If we're importing a module, then add an import directly
    if inspect.ismodule(obj):
        mod_name = obj.__name__
        return parse_statement(f'import {mod_name} as {name}'
                               if name != mod_name else f'import {mod_name}')
    else:
        # Get module where global is defined
        mod = inspect.getmodule(obj)

        # TODO: When is mod None?
        if mod is None or mod is typing:
            return None

        # Can't import builtins
        elif mod is __builtins__ or mod is builtins:
            return None

        # If the value is a class or function, then import it from the defining
        # module
        elif inspect.isclass(obj) or inspect.isfunction(obj):
            return parse_statement(f'from {mod.__name__} import {name}')

        # Otherwise import it from the module using the global
        elif func_obj is not None:
            func_mod_name = inspect.getmodule(func_obj).__name__
            return parse_statement(f'from {func_mod_name} import {name}')
