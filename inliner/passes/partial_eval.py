import ast

from .base_pass import BasePass
from ..common import a2s, obj_to_ast, compare_ast


class ShouldEval(ast.NodeVisitor):
    def __init__(self):
        self.should = True

    def generic_visit(self, node):

        whitelist = (ast.Num, ast.Str, ast.List, ast.Tuple, ast.Dict,
                     ast.NameConstant, ast.Name, ast.Load, ast.UnaryOp,
                     ast.BinOp, ast.BoolOp, ast.Compare, ast.Attribute,
                     ast.Subscript, ast.Index, ast.Slice, ast.ExtSlice, ast.Eq,
                     ast.NotEq, ast.Is, ast.In, ast.Add, ast.Sub, ast.Mult,
                     ast.Div, ast.And, ast.Or)

        if not isinstance(node, whitelist):
            self.should = False

        return super().generic_visit(node)


class PartialEvalPass(BasePass):
    def generic_visit(self, node):
        should_eval = ShouldEval()
        should_eval.visit(node)

        if should_eval.should:
            try:
                src = a2s(node)
                ret = eval(src, {}, {})
                retnode = obj_to_ast(ret)
                return retnode
            except Exception:
                pass

        super().generic_visit(node)
        return node
