import ast
import copy
from iterextras import unzip

from .base_pass import BasePass, CancelPass
from ..common import a2s, parse_stmt, make_name, SEP


class SimplifyVarargsPass(BasePass):
    """
    Expand/inline usage of *args and **kwargs.

    If a dictionary is being used as keyword arguments to a function,
    this pass attempts to turn each key of the dictionary into a standalone
    variable so it can be optimized by e.g. copy propagation.

    Example:
      kwargs = {'x': 1}
      foo(**kwargs)

      >> becomes >>

      foo(x=1)
    """

    tracer_args = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.inlined_kwarg = set()

    def _is_vararg(self, node):
        # HEURISTIC: assume that all dictionaries starting with "args"
        # or "kwargs" are used for keyword arguments
        return isinstance(node, ast.Name) and \
            any([node.id.startswith(prefix) for prefix in ['args', 'kwargs', 'kws']])

    def visit_Expr(self, stmt):
        # find expressions like dict.update(...)
        if isinstance(stmt.value, ast.Call) and \
           isinstance(stmt.value.func, ast.Attribute) and \
           len(stmt.value.args) > 0 and \
           stmt.value.func.attr == 'update':

            try:
                dict_obj = eval(a2s(stmt.value.func.value), self.globls,
                                self.globls)
            except Exception:
                raise

            # Expand dict.update(x=2) into dict['x'] = 2
            dict_ast = stmt.value.func.value
            arg = stmt.value.args[0]
            if isinstance(dict_obj, dict) and \
               isinstance(arg, ast.Call) and \
               isinstance(arg.func, ast.Name) and \
               arg.func.id == 'dict':
                new_stmts = []
                for kw in arg.keywords:
                    assgn = parse_stmt(f'x["{kw.arg}"] = x')
                    assgn.targets[0].value = dict_ast
                    assgn.value = kw.value
                    new_stmts.append(assgn)

                self.change = True

                # Recursively visit the expansion to continue turning
                # dictionary into variables
                return [self.visit(stmt) for stmt in new_stmts]

        self.generic_visit(stmt)
        return stmt

    def visit_Assign(self, stmt):
        if self._is_vararg(stmt.targets[0]):
            # x = dict(foo='bar', ...)
            if isinstance(stmt.value, ast.Call) and \
               isinstance(stmt.value.func, ast.Name) and \
               stmt.value.func.id == 'dict':
                keys, vals = unzip([(kw.arg, kw.value)
                                    for kw in stmt.value.keywords])
                stmt.value = ast.Dict([ast.Str(k) for k in keys], vals)

                self.change = True
                return self.visit(stmt)

            # x = {'foo': 'bar', ...}
            elif isinstance(stmt.value, ast.Dict) and len(stmt.value.keys) > 0:
                name = stmt.targets[0].id
                new_stmts = [parse_stmt(f'{name} = {{}}')]
                for k, v in zip(stmt.value.keys, stmt.value.values):
                    assgn = parse_stmt(f'{name}[_] = _')
                    assgn.targets[0].slice.value = k
                    assgn.value = v
                    new_stmts.append(assgn)

                self.change = True
                return [self.visit(stmt) for stmt in new_stmts]

        self.generic_visit(stmt)
        return stmt

    def visit_Subscript(self, sub):
        # x['foo'] => foo___x
        if self._is_vararg(sub.value) and \
           isinstance(sub.slice, ast.Index) and \
           isinstance(sub.slice.value, ast.Str):
            return make_name(f'{sub.slice.value.s}{SEP}{sub.value.id}')

        self.generic_visit(sub)
        return sub

    def visit_Call(self, call):
        if len(call.args) > 0 and isinstance(call.args[-1], ast.Starred):
            star_arg = call.args[-1].value

            try:
                star_obj = eval(a2s(star_arg), self.globls, self.globls)
            except Exception:
                # print('ERROR', a2s(call))
                # TODO: log a warning?
                # list comprehension issue: [f(*c) for c in whatever]
                return call

            call.args.pop()
            self.change = True

            for i in range(len(star_obj)):
                call.args.append(
                    ast.Subscript(value=star_arg, slice=ast.Index(ast.Num(i))))

        kwarg = [(i, kw.value) for i, kw in enumerate(call.keywords)
                 if kw.arg is None]

        if len(kwarg) == 1:
            i, kwarg = kwarg[0]

            try:
                kwarg_obj = eval(a2s(kwarg), self.globls, self.globls)
            except Exception:
                print('ERROR', a2s(call))
                raise

            if isinstance(kwarg, ast.Name):
                # HACK: in case where kwarg is reused and modified,
                # e.g. kw = {}; foo(**kw); kw['x'] = 1; bar(**kw);
                # then our compilation strategy is unsound. For now,
                # just check if **kw is used twice
                if kwarg.id in self.inlined_kwarg:
                    raise CancelPass
                self.inlined_kwarg.add(kwarg.id)

            self.change = True
            del call.keywords[i]

            # Add a keyword argument for each key in kwargs, e.g.
            # kwargs = {'x': 1}; f(**kwargs) => f(x=kwargs['x'])
            for k in kwarg_obj.keys():
                idx_expr = ast.Subscript(value=kwarg,
                                         slice=ast.Index(ast.Str(k)))
                call.keywords.append(ast.keyword(arg=k, value=idx_expr))

        self.generic_visit(call)
        return call
