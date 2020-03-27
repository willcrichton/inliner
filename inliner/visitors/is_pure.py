import libcst as cst


class IsPureVisitor(cst.CSTVisitor):

    whitelist = (
        # Constants
        cst.BaseNumber,
        cst.SimpleString,
        cst.Name,
        cst.List,
        cst.Set,
        cst.Tuple,
        cst.Dict,
        cst.Attribute,
        # Operations
        cst.BinaryOperation,
        cst.BaseBinaryOp,
        cst.BaseBooleanOp,
        cst.UnaryOperation,
        cst.BooleanOperation,
        cst.Comparison,
        cst.Subscript,
        cst.BaseSlice,
        cst.Element,
        cst.DictElement,
        cst.SubscriptElement,
        # Whitespace/syntax
        cst.SimpleWhitespace,
        cst.BaseParenthesizableWhitespace,
        cst.LeftCurlyBrace,
        cst.RightCurlyBrace,
        cst.LeftSquareBracket,
        cst.RightSquareBracket,
        cst.LeftParen,
        cst.RightParen,
        cst.Dot,
        cst.Comma)

    def __init__(self):
        self.pure = True

    def on_visit(self, node):
        if not isinstance(node, self.whitelist):
            self.pure = False
        return super().on_visit(node)


def is_pure(node):
    visitor = IsPureVisitor()
    node.visit(visitor)
    return visitor.pure
