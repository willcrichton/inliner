from inliner import Inliner


def basic_schedule(inliner):
    while True:
        if not inliner.inline():
            break
        inliner.fixpoint(inliner.deadcode)

    inliner.expand_self()
    inliner.unread_vars()
    inliner.copy_propagation()
    inliner.clean_imports()


def harness(fn, schedule):
    try:
        inliner = Inliner(fn, ['api'])
        schedule(inliner)
        globls = {}
        exec(inliner.make_program(comments=True), globls, globls)
    except AssertionError:
        print(inliner.make_program(comments=True))
        raise


def test_inline_basic():
    def inline_basic():
        from api import inline_basic
        assert inline_basic(1) == 1
        assert inline_basic(1, flag=False) == 2

    harness(inline_basic, basic_schedule)


def test_function_args():
    def function_args():
        from api import function_args
        function_args(1, b=2, c=2, f=4)

    harness(function_args, basic_schedule)


def test_class_basic():
    def class_basic():
        from api import ClassBasic
        c = ClassBasic(1)
        c.foo(0)

    harness(class_basic, basic_schedule)
