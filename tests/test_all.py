from inliner import Inliner


def basic_schedule(inliner):
    did_inline = False
    while True:
        if not inliner.inline():
            break
        inliner.fixpoint(inliner.deadcode)
        did_inline = True

    assert did_inline

    while True:
        any_pass = any([
            inliner.expand_self(),
            inliner.unread_vars(),
            inliner.lifetimes(),
            inliner.copy_propagation(),
            inliner.simplify_varargs(),
            inliner.expand_tuples()
        ])
        if not any_pass:
            break

    inliner.clean_imports()


def harness(fn, schedule, apis=['api']):
    # Execute the function to make sure it works without inlining
    fn()

    # Then execute with inlining
    try:
        inliner = Inliner(fn, apis)
        schedule(inliner)
        prog = inliner.make_program(comments=True)
        print(prog)
        inliner.execute()
    except Exception:
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


def test_class_property():
    def class_property():
        from api import ClassProperty
        c = ClassProperty()
        assert c.bar == 1

    harness(class_property, basic_schedule)


def test_function_decorator():
    def function_decorator():
        from api import function_decorator
        assert function_decorator(1) == 4

    harness(function_decorator, basic_schedule)


def test_comprehension():
    def comprehension():
        from api import dummy
        l = [dummy() for _ in range(10)]
        assert sum(l) == 10

    harness(comprehension, basic_schedule)


def test_ifexp():
    def ifexp():
        from api import dummy
        n = 1 if dummy() == 1 else 0
        assert n == 1

    harness(ifexp, basic_schedule)


def test_closure():
    import api

    def closure():
        assert api.dummy() == 1

    harness(closure, basic_schedule)


def test_global():
    def globl():
        import api
        assert api.globl() == 1

    harness(globl, basic_schedule)


def test_with():
    def with_():
        import api
        with api.Context(0) as c:
            c.n += 1
        assert c.n == 3

    harness(with_, basic_schedule)


def test_seaborn_boxplot():
    def make_plot():
        import seaborn as sns
        iris = sns.load_dataset('iris')
        sns.boxplot(x=iris.species, y=iris.petal_length)

    harness(make_plot, basic_schedule, apis=['seaborn.categorical'])
