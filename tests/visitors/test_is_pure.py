from inliner.visitors import is_pure
import libcst as cst


def test_is_pure():
    pure = [
        "x",
        "x + 1",
        "x[0]",
        "x[i*2]",
        "x['a']",
        "{'a': 1}",
        "[1, 2]",
        "a.b"
    ] # yapf: disable

    impure = [
        "f(x)",
        "1 + f(x)",
    ] # yapf: disable

    for expr_str in pure:
        expr = cst.parse_expression(expr_str)
        assert is_pure(expr)

    for expr_str in impure:
        expr = cst.parse_expression(expr_str)
        assert not is_pure(expr)
