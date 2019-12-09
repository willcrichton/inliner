from inliner import Inliner


def inline_basic():
    from api import foo
    assert foo(1) == 1
    assert foo(1, flag=False) == 2


def test_inline_basic():
    inliner = Inliner(inline_basic, ['api'])
    inliner.inline()
    inliner.fixpoint(inliner.deadcode)

    globls = {}
    exec(inliner.make_program(comments=True), globls, globls)
