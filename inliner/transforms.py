import logging as log
import inspect
import libcst as cst
from iterextras import unzip

from .contexts import ctx_inliner, ctx_pass
from .common import a2s, SEP, make_assign, make_string, make_list, make_dict, parse_statement
from .visitors import FindAssignments, FindClosedVariables, Rename, ReplaceReturn


def bind_arguments(f_ast, call_expr, new_stmts):
    inliner = ctx_inliner.get()

    args_def = f_ast.params

    args = call_expr.args[:]
    arg_names = set([arg_def.name.value for arg_def in args_def.params])

    assgn_finder = FindAssignments()
    f_ast.visit(assgn_finder)

    closed_var_finder = FindClosedVariables()
    f_ast.body.visit(closed_var_finder)

    def rename(src, dst):
        nonlocal f_ast
        f_ast = f_ast.with_changes(body=f_ast.body.visit(Rename(src, dst)))

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
        if isinstance(v, cst.Name) and \
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
        star_arg_obj = inliner._eval(star_arg)

        # Generate an indexing expression for each element of the list
        call_star_args = [
            make_index(star_arg, cst.Num(i)) for i in range(len(star_arg_obj))
        ]
    else:
        star_arg = None

    # If function is called with f(**kwargs)
    star_kwarg = next(filter(lambda arg: arg.star == '**', call_expr.args),
                      None)
    if star_kwarg is not None:
        star_kwarg = star_kwarg.value
        star_kwarg_dict = inliner._eval(star_kwarg)
        call_star_kwarg = {
            key: make_index(star_kwarg, make_string(key))
            for key in star_kwarg_dict.keys()
        }

    # Function's anonymous arguments, e.g. f(1, 2) becomes [1, 2]
    call_anon_args = [
        arg.value for arg in call_expr.args if arg.keyword is None
    ]

    # Function's keyword arguments, e.g. f(x=1, y=2) becomes {'x': 1, 'y': 2}
    call_kwargs = {
        arg.keyword.value: arg.value
        for arg in call_expr.args if arg.keyword is not None
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
    if args_def.star_arg is not cst.MaybeSentinel.DEFAULT:
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


def inline_function(call_obj,
                    call_expr,
                    ret_var,
                    cls=None,
                    f_ast=None,
                    add_comments=True,
                    is_toplevel=False):
    log.debug('Inlining {}'.format(a2s(call_expr)))

    inliner = ctx_inliner.get()
    pass_ = ctx_pass.get()

    new_stmts = []

    if f_ast is None:
        # Get the source code for the function
        try:
            f_source = inspect.getsource(call_obj)
        except TypeError:
            print('Failed to get source of {}'.format(a2s(call_expr)))
            raise

        # Record statistics about length of inlined source
        inliner.length_inlined += len(f_source.split('\n'))

        # Then parse the function into an AST
        f_ast = parse_statement(f_source)

    # Give the function a fresh name so it won't conflict with other calls to
    # the same function
    f_ast = f_ast.with_changes(name=cst.Name(pass_.fresh_var(f_ast.name.value)))

    # TODO
    # # If function has decorators, deal with those first. Just inline decorator call
    # # and stop there.
    # decorators = f_ast.decorator_list
    # assert len(decorators) <= 1
    # if len(decorators) == 1:
    #     d = decorators[0]
    #     builtin_decorator = (
    #         isinstance(d, ast.Name)
    #         and (d.id in ['property', 'classmethod', 'staticmethod']))
    #     derived_decorator = (isinstance(d, ast.Attribute)
    #                          and (d.attr in ['setter']))
    #     if not (builtin_decorator or derived_decorator):
    #         self._expand_decorators(new_stmts, f_ast, call_expr, call_obj,
    #                                 ret_var)
    #         return new_stmts

    # TODO
    # # If we're inlining a decorator, we need to remove @functools.wraps calls
    # # to avoid messing up inspect.getsource
    # for stmt in f_ast.body:
    #     RemoveFunctoolsWraps().visit(stmt)

    # TODO
    # # If the function is a method (which we proxy by first arg being named "self"),
    # # then we need to replace uses of special "super" keywords.
    # args_def = f_ast.args
    # if len(args_def.params) > 0 and args_def.params[0].arg == 'self':
    #     self._replace_super(f_ast, cls, call_expr, call_obj, new_stmts)

    # Add bindings from arguments in the call expression to arguments in function def
    f_ast = bind_arguments(f_ast, call_expr, new_stmts)

    # Add an explicit return None at the end to reify implicit return
    f_body = f_ast.body
    if not is_toplevel and not isinstance(f_body.body[-1].body[0], cst.Return):
        print(f_body.body)
        f_ast = f_ast.with_deep_changes(f_body,
                                        body=list(f_body.body) +
                                        [parse_statement("return None")])

    # Iteratively replace all return statements with conditional assignments to
    # the ret_var. See ReplaceReturn in visitors.py for how this works.
    while True:
        replacer = ReplaceReturn(ret_var)
        f_ast = f_ast.visit(replacer)
        if not replacer.found_return:
            break

    # Inline function body
    new_stmts.extend(f_ast.body.body)

    if add_comments:
        # Add header comment to first statement
        header_comment = cst.Comment(f'# {a2s(call_expr)}')
        first_stmt = new_stmts[0]
        new_stmts[0] = first_stmt.with_changes(leading_lines=[
            cst.EmptyLine(),
            cst.EmptyLine(comment=header_comment)
        ] + list(first_stmt.leading_lines))

    # TODO
    # # If we're inlining a function not defined in the top-level source, then
    # # add imports for all the nonlocal (global + closure) variables
    # if not self.inliner.is_source_obj(call_obj):
    #     used = self._get_nonlocal_vars(f_ast, call_obj)
    #     file_imports = collect_imports(call_obj)
    #     for name, value in used.items():
    #         if name == 'self':  # HACK
    #             continue
    #         imprt = self.generate_imports(name,
    #                                       value,
    #                                       call_obj=call_obj,
    #                                       file_imports=file_imports)
    #         if imprt is not None:
    #             new_stmts.insert(0, imprt)

    return new_stmts
