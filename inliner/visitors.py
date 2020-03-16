import libcst as cst
import libcst.matchers as m

from .common import make_assign, parse_statement


class ReplaceReturn(cst.CSTTransformer):
    def __init__(self, name):
        self.name = name
        self.toplevel = True
        self.found_return = False
        self.if_wrapper = parse_statement(f"""
if "{name}" not in globals():
    pass
""")

    def leave_SimpleStatementLine(self, _, stmt):
        ret = stmt.body[0]
        if m.matches(ret, m.Return()):
            # A naked return (without a value) will have ret.value = None
            value = ret.value if ret.value is not None else cst.Name('None')
            if_stmt = self.if_wrapper.with_deep_changes(
                self.if_wrapper.body,
                body=[make_assign(cst.Name(self.name), value)])
            self.found_return = True
            return if_stmt
        return stmt

    def visit_FunctionDef(self, fdef):
        # no recurse to avoid messing up inline functions
        if self.toplevel:
            self.toplevel = False
            return True
        return False

    # TODO
    # def generic_visit(self, node):
    #     for field, old_value in ast.iter_fields(node):
    #         # if we're iterating over assignment targets, don't try to introduce
    #         # if statements between targets
    #         if isinstance(old_value, list) and field not in ['targets']:
    #             new_values = []
    #             for i, cur_value in enumerate(old_value):
    #                 if isinstance(cur_value, ast.AST):
    #                     value = self.visit(cur_value)

    #                     stmt_types = (ast.For, ast.If, ast.With,
    #                                   ast.FunctionDef, ast.Assign, ast.While)
    #                     if isinstance(node, stmt_types) and self.found_return:
    #                         new_values.append(value)
    #                         if i < len(old_value) - 1:
    #                             if_stmt = copy.deepcopy(self.if_wrapper)
    #                             if_stmt.body = old_value[i + 1:]
    #                             new_values.append(if_stmt)
    #                         break

    #                     if value is None:
    #                         continue
    #                     elif not isinstance(value, ast.AST):
    #                         new_values.extend(value)
    #                         continue

    #                 new_values.append(value)
    #             old_value[:] = new_values
    #         elif isinstance(old_value, ast.AST):
    #             new_node = self.visit(old_value)
    #             if new_node is None:
    #                 delattr(node, field)
    #             else:
    #                 setattr(node, field, new_node)

    #     return node


class FindAssignments(cst.CSTVisitor):
    def __init__(self):
        self.names = set()

    def visit_Assign(self, assgn):
        for t in assgn.targets:
            if m.matches(t, m.Name()):
                self.names.add(t.value)


class FindClosedVariables(cst.CSTVisitor):
    closure_nodes = (cst.FunctionDef, cst.ListComp, cst.DictComp)

    def __init__(self):
        self.vars = set()
        self.in_closure = 0

    def visit_Name(self, name):
        if self.in_closure > 0:
            self.vars.add(name.value)

    def on_visit(self, node):
        if isinstance(node, self.closure_nodes):
            self.in_closure += 1

    def on_leave(self, node):
        if isinstance(node, self.closure_nodes):
            self.in_closure -= 1


class Rename(cst.CSTTransformer):
    def __init__(self, src, dst):
        self.src = src
        self.dst = dst

    def visit_FunctionDef(self, fdef):
        if fdef.name.value != self.src:
            for arg in args.args:
                arg_names.add(arg.arg)
            if args.vararg is not None:
                arg_names.add(args.vararg.arg)
            if args.kwarg is not None:
                arg_names.add(args.kwarg.arg)

            return self.src not in arg_names

    def leave_FunctionDef(self, _, fdef):
        if fdef.name.value == self.src:
            return fdef.with_changes(name=cst.Name(self.dst))
        return fdef

    def leave_Name(self, _, name):
        if name.value == self.src:
            return name.with_changes(value=self.dst)
        return name
