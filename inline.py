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


class ExpandSelf(ast.NodeTransformer):
    def visit_Attribute(self, attr):
        if isinstance(attr.value, ast.Name) and \
           attr.value.id[:4] == 'self':
            return ast.Name(id=f'{attr.attr}__{attr.value.id}')
        return attr


class Replace(ast.NodeTransformer):
    def __init__(self, src, dst):
        self.src = src
        self.dst = dst

    def generic_visit(self, node):
        if compare_ast(node, self.src):
            return dst
        else:
            return node


class Rename(ast.NodeTransformer):
    def __init__(self, src, dst):
        self.src = src
        self.dst = dst

    def visit_Name(self, name):
        if name.id == self.src:
            name.id = self.dst
        return name


class BulkReplace(ast.NodeTransformer):
    def __init__(self, bindings):
        self.bindings = bindings

    def visit_Name(self, name):
        if name.id in self.bindings:
            return self.bindings[name.id]
        else:
            return name


class FindAssignments(ast.NodeVisitor):
    def __init__(self):
        self.names = set()

    def visit_Assign(self, assgn):
        for t in assgn.targets:
            if isinstance(t, ast.Name):
                self.names.add(t.id)


class FindVarUse(ast.NodeVisitor):
    def __init__(self):
        self.names = set()

    def visit_Name(self, name):
        self.names.add(name.id)


class FindCall(ast.NodeTransformer):
    def __init__(self, name, globls, locls):
        self.call_obj = None
        self.call_expr = None
        self.name = name
        self.globls = globls
        self.locls = locls

    def visit_Call(self, call_expr):
        try:
            call_obj = eval(a2s(call_expr.func), self.globls, self.locls)
        except Exception:
            print('ERROR', a2s(call_expr))
            raise

        module = inspect.getmodule(call_obj)

        if module is not None:
            module_parts = module.__name__.split('.')
            if module_parts[0:2] == ['seaborn', 'categorical'] or \
               module_parts[0] == 'test':

                if self.call_expr is not None:
                    raise Exception("Multiple valid call expr")

                self.call_expr = call_expr
                self.call_obj = call_obj
                return ast.Name(id=self.name)

        return call_expr


class ReplaceReturn(ast.NodeTransformer):
    def __init__(self, name):
        self.name = name

    def visit_Return(self, stmt):
        if_stmt = parse_stmt(
            textwrap.dedent("""
        if "{name}" not in locals() and "{name}" not in globals():
            {name} = None
        """.format(name=self.name)))
        if_stmt.body[0].value = stmt.value
        return if_stmt


class ReplaceSelf(ast.NodeTransformer):
    def __init__(self, cls):
        self.cls = ast.Name(id=cls.__name__)

    def visit_Call(self, expr):
        if isinstance(expr.func, ast.Attribute) and \
            isinstance(expr.func.value, ast.Name) and \
            expr.func.value.id == 'self':
            expr.args.insert(0, ast.Name(id='self'))
            expr.func.value = self.cls
        return expr


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


class CollectLineNumbers(ast.NodeVisitor):
    def __init__(self):
        self.linenos = set()

    def generic_visit(self, node):
        if hasattr(node, 'lineno'):
            self.linenos.add(node.lineno)
        super().generic_visit(node)


class Inliner:
    def __init__(self, stmts):
        self.stmts = stmts
        self.counter = 0

    def fresh(self):
        v = 'var{}'.format(self.counter)
        self.counter += 1
        return v

    def inline_constructor(self, call_obj, call_expr, ret_var):
        #         self.new_stmts.append(ast.Assign(
        #             targets=[ast.Name(id=ret_var)], value=ast.parse("DotMap()").body[0].value))
        cls = call_obj.__name__
        make_obj = ast.Assign(targets=[ast.Name(id=ret_var)],
                              value=parse_expr(f'{cls}.__new__({cls})'))
        call_expr.args.insert(0, ast.Name(id=ret_var))
        return [make_obj] + self.inline_function(
            call_obj.__init__, call_expr, ret_var, cls=call_obj)

    def expand_method(self, call_obj, call_expr, ret_var):
        obj = call_expr.func.value
        cls = call_obj.__self__.__class__
        call_expr.func = ast.Attribute(value=ast.Name(id=cls.__name__),
                                       attr=call_expr.func.attr)
        call_expr.args.insert(0, obj)

    def inline_function(self,
                        call_obj,
                        call_expr,
                        ret_var,
                        cls=None,
                        debug=False):
        new_stmts = []
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

        args = call_expr.args[:]
        kwargs = {arg.arg: arg.value for arg in call_expr.keywords}

        nodefault = len(args_def.args) - len(args_def.defaults)

        if cls is not None:
            ReplaceSelf(cls).visit(f_ast)

        def make_unique_name(name):
            return f'{name}__{f_ast.name}'

        assgn_finder = FindAssignments()
        assgn_finder.visit(f_ast)
        arg_names = set([arg.arg for arg in args_def.args])
        for name in assgn_finder.names:
            if name not in arg_names:
                unique_name = make_unique_name(name)
                Rename(name, unique_name).visit(f_ast)

        # Add argument bindings
        for i, (arg, default) in enumerate(
                zip(args_def.args,
                    [None for _ in range(nodefault)] + args_def.defaults)):
            k = arg.arg

            # Get value corresponding to argument name
            if i < len(call_expr.args):
                v = call_expr.args[i]
            else:
                v = kwargs.pop(k) if k in kwargs else default

            # Rename to unique var name
            uniq_k = make_unique_name(k)
            Rename(k, uniq_k).visit(f_ast)

            new_stmts.append(ast.Assign(targets=[ast.Name(id=uniq_k)], value=v))

        # TODO: make this work for *args

        if args_def.kwarg is not None:
            kwkeys, kwvalues = unzip(kwargs.items())
            new_stmts.append(
                ast.Assign(targets=[ast.Name(id=args_def.kwarg.arg)],
                           value=ast.Dict([ast.Str(s) for s in kwkeys],
                                          kwvalues)))

        # Replace returns with assignment
        f_ast.body.append(parse_stmt("return None"))
        ReplaceReturn(ret_var).visit(f_ast)

        # Inline function body
        new_stmts.extend(f_ast.body)

        if not is_special_method:
            used_globals = UsedGlobals(call_obj.__globals__)
            used_globals.visit(f_ast)
            imports = []
            for name, globl in used_globals.used.items():
                if inspect.ismodule(globl):
                    alias = name if globl.__name__ != name else None
                    new_stmts.insert(
                        0,
                        ast.Import(
                            [ast.alias(name=globl.__name__, asname=alias)]))
                else:
                    mod = inspect.getmodule(globl)
                    if mod is None:
                        mod_value = obj_to_ast(globl)
                        new_stmts.insert(
                            0,
                            ast.Assign(targets=[ast.Name(id=name)],
                                       value=mod_value))
                    elif mod == __builtins__:
                        pass
                    else:
                        new_stmts.insert(
                            0,
                            ast.ImportFrom(
                                module=mod.__name__,
                                names=[ast.alias(name=name, asname=None)],
                                level=0))

        return new_stmts

    def expand_comprehension(self, comp, ret_var, call_finder):
        forloop = None
        for gen in reversed(comp.generators):
            if forloop is None:
                body = []
                body.extend(
                    self.inline_function(call_finder.call_obj,
                                         call_finder.call_expr,
                                         call_finder.name))
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
        ast
        return [init, forloop]

    def make_program(self):
        return '\n'.join([a2s(stmt).strip() for stmt in self.stmts])

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
            exec(self.make_program(), globls, globls)
        except Exception:
            print(self.make_program())
            raise

        change = False

        def check_inline(stmt):
            nonlocal change
            new_stmts = []

            comp_ret_var = self.fresh()
            comp_call_finder = FindCall(self.fresh(), globls, globls)
            comp_finder = FindComprehension(comp_call_finder, comp_ret_var)
            comp_finder.visit(stmt)
            if comp_finder.comp is not None:
                change = True
                new_stmts.extend(
                    self.expand_comprehension(comp_finder.comp, comp_ret_var,
                                              comp_call_finder))
                new_stmts.append(stmt)
                return new_stmts
            self.counter -= 2

            ret_var = self.fresh()
            call_finder = FindCall(ret_var, globls, globls)
            call_finder.visit(stmt)

            if call_finder.call_expr is not None:
                call_expr = call_finder.call_expr
                call_obj = call_finder.call_obj

                if inspect.ismethod(call_obj):
                    # print('expand_method', a2s(call_expr))
                    self.expand_method(call_obj, call_expr, ret_var)
                    new_stmts.append(
                        ast.Assign(targets=[ast.Name(id=ret_var)],
                                   value=call_expr))
                elif inspect.isfunction(call_obj):
                    # print('inline_function', a2s(call_expr))
                    new_stmts.extend(
                        self.inline_function(call_obj,
                                             call_expr,
                                             ret_var,
                                             debug=debug))
                elif inspect.isclass(call_obj):
                    new_stmts.extend(
                        self.inline_constructor(call_obj, call_expr, ret_var))
                else:
                    raise NotYetImplemented

                change = True
            else:
                self.counter -= 1

            new_stmts.append(stmt)
            return new_stmts

        self.stmts = self.stmt_recurse(self.stmts, check_inline)
        return change

    # def simplify(self):
    #     new_stmts = []
    #     change = False
    #     for i, stmt in enumerate(self.stmts):
    #         if isinstance(stmt, ast.Assign):

    #         use_finder = FindVarUse()
    #         for stmt2 in self.stmts[i + 1:]:
    #             use_finder.visit(stmt2)

    #         unused = False
    #         for var in assgn_finder.names:
    #             if var not in use_finder.names:
    #                 unused = True
    #                 break

    #         if not unused:
    #             new_stmts.append(stmt)
    #         else:
    #             print(
    #             change = True

    #     self.stmts = new_stmts
    #     return change

    def expand_self(self):
        expander = ExpandSelf()
        for stmt in self.stmts:
            expander.visit(stmt)

    def clean_imports(self):
        imports = []
        new_stmts = []
        for i, stmt in enumerate(self.stmts):
            if isinstance(stmt, ast.Import) or isinstance(stmt, ast.ImportFrom):
                imports.append(stmt)
            else:
                new_stmts.append(stmt)

        imports_dedup = [
            imprt for i, imprt in enumerate(imports) if
            not any([compare_ast(imprt, imprt2) for imprt2 in imports[i + 1:]])
        ]

        new_stmts = imports_dedup + new_stmts
        self.stmts = new_stmts

    def test(self):
        prog = self.make_program()
        tracer = Tracer(prog, opcode=True)
        tracer.trace()

        self.stmts = ast.parse(prog).body

        toplevel_assignments = set()
        for stmt in self.stmts:
            if isinstance(stmt, ast.Assign) and \
               len(stmt.targets) == 1 and \
               isinstance(stmt.targets[0], ast.Name):
                toplevel_assignments.add(stmt.targets[0].id)

        only_once_vars = set(
            [name for name, count in tracer.set_count.items() if count == 1])
        new_bindings = {
            name: obj_to_ast(tracer.globls[name])
            for name in only_once_vars
            if can_convert_obj_to_ast(tracer.globls[name])
            and name in toplevel_assignments
        }

        new_stmts = []
        replacer = BulkReplace(new_bindings)
        for stmt in self.stmts:
            if isinstance(stmt, ast.Assign) and \
               isinstance(stmt.targets[0], ast.Name) and \
               stmt.targets[0].id in new_bindings:
                pass
            else:
                replacer.visit(stmt)
                new_stmts.append(stmt)

        self.stmts = new_stmts

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

        def check_deadcode(stmt):
            nonlocal change

            new_stmts = []
            if is_dead(stmt):
                change = True
                return []

            if isinstance(stmt, ast.If):
                # TODO: assumes pure conditions
                if len(stmt.body) == 0 or is_dead(stmt.body[0]):
                    change = True
                    new_stmts.extend(stmt.orelse)
                elif len(stmt.orelse) == 0 or is_dead(stmt.orelse[0]):
                    change = True
                    new_stmts.extend(stmt.body)
                else:
                    new_stmts.append(stmt)
            elif isinstance(stmt, ast.For):
                if len(stmt.body) == 0:
                    change = True
                else:
                    new_stmts.append(stmt)
            elif isinstance(stmt, ast.Expr):
                val = stmt.value
                if isinstance(val, ast.Name) or isinstance(
                        val, ast.Str) or isinstance(val, ast.NameConstant):
                    change = True
                else:
                    new_stmts.append(stmt)
            elif isinstance(stmt, ast.Try):
                if not is_dead(stmt.handlers[0]):
                    # HUGE HACK: assumes it's safe to replace try/except
                    # with just except block if except block not dead
                    assert len(stmt.handlers) == 1
                    assert stmts.handlers[0].name is None
                    change = True
                    new_stmts.extend(stmts.handlers[0].body)
                else:
                    new_stmts.append(stmt)
            elif isinstance(stmt, ast.FunctionDef):
                if len(stmt.body) == 0:
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

    def fixpoint(self, f):
        while f():
            pass
