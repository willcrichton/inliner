import functools
from inliner.targets import CursorTarget

from utils import run_inline_harness


def test_inline_basic():
    def target(x):
        return x + 1

    def prog():
        assert target(1) == 2

    def outp():
        x___target = 1
        if "target_ret" not in globals():
            target_ret = x___target + 1
        assert target_ret == 2

    run_inline_harness(prog, target, outp, locals())


def test_inline_args():
    def target(a, b, c=1, d=2, *args, **kwargs):
        assert (a == 1)
        assert (b == 2)
        assert (c == 2)
        assert (d == 2)
        assert (len(args) == 0)
        assert (kwargs["f"] == 4)

    def prog():
        target(1, b=2, c=2, f=4)

    def outp():
        a___target = 1
        b___target = 2
        c___target = 2
        d___target = 2
        args___target = []
        kwargs___target = {"f": 4}
        assert (a___target == 1)
        assert (b___target == 2)
        assert (c___target == 2)
        assert (d___target == 2)
        assert (len(args___target) == 0)
        assert (kwargs___target["f"] == 4)
        if "target_ret" not in globals():
            target_ret = None
        target_ret

    run_inline_harness(prog, target, outp, locals())


def test_inline_nested():
    def target(x):
        return x + 1

    def prog():
        assert target(target(1)) == 3

    def outp():
        x___target = 1
        if "target_ret" not in globals():
            target_ret = x___target + 1
        x___target_2 = target_ret
        if "target_ret_2" not in globals():
            target_ret_2 = x___target_2 + 1
        assert target_ret_2 == 3

    run_inline_harness(prog, target, outp, locals())


def test_inline_return():
    def target():
        if True:
            x = 1
            return x
            assert False
        assert False
        return 3

    def prog():
        assert target() == 1

    def outp():
        if True:
            x = 1
            if "target_ret" not in globals():
                target_ret = x
            if "target_ret" not in globals():
                assert False
        if "target_ret" not in globals():
            assert False
            if "target_ret" not in globals():
                target_ret = 3
        assert target_ret == 1

    run_inline_harness(prog, target, outp, locals())


def test_inline_class_constructor():
    class Test:
        def __init__(self, x):
            self.x = x

    def prog():
        t = Test(1)
        assert t.x == 1

    def outp():
        Test_ret = Test.__new__(Test)
        self_____init__ = Test_ret
        x_____init__ = 1
        self_____init__.x = x_____init__
        t = Test_ret
        assert t.x == 1

    run_inline_harness(prog, Test, outp, locals())


def test_inline_class_method():
    class Test:
        def __init__(self):
            self.x = 1

        def foo(self, x):
            return x + self.x

    def prog():
        t = Test()
        assert t.foo(1) == 2

    def outp():
        Test_ret = Test.__new__(Test)
        self_____init__ = Test_ret
        self_____init__.x = 1
        t = Test_ret
        self___foo = t
        x___foo = 1
        if "foo_ret" not in globals():
            foo_ret = x___foo + self___foo.x
        assert foo_ret == 2

    run_inline_harness(prog, Test, outp, locals())


def test_inline_class_super():
    class A:
        def __init__(self):
            self.x = 1

    class B(A):
        def __init__(self):
            super().__init__()
            self.y = 1

    def prog():
        b = B()
        assert b.x + b.y == 2

    def outp():
        B_ret = B.__new__(B)
        self_____init__ = B_ret
        A.__init__(self_____init__)
        self_____init__.y = 1
        b = B_ret
        assert b.x + b.y == 2

    run_inline_harness(prog, B, outp, locals())


def test_inline_class_staticmethod():
    class Cls:
        @staticmethod
        def foo(x):
            return x + 1

        @classmethod
        def bar(cls, x):
            return cls.foo(x) + x

    def prog():
        assert Cls.bar(1) == 3

    def outp():
        cls___bar = Cls
        x___bar = 1
        if "bar_ret" not in globals():
            x___foo = x___bar
            if "foo_ret" not in globals():
                foo_ret = x___foo + 1
            bar_ret = foo_ret + x___bar
        assert bar_ret == 3

    run_inline_harness(prog, Cls, outp, locals(), fixpoint=True)


def test_inline_generator():
    def gen():
        for i in range(10):
            yield i

    def prog():
        for i, j in zip(gen(), range(10)):
            assert i == j

    def outp():
        gen_ret = []
        for i in range(10):
            gen_ret.append(i)
        if "gen_ret" not in globals():
            gen_ret = None
        for i, j in zip(gen_ret, range(10)):
            assert i == j

    run_inline_harness(prog, gen, outp, locals())


def test_inline_generator_method():
    class Cls:
        def gen(self):
            for i in range(10):
                yield i

    def prog():
        c = Cls()
        for i, j in zip(c.gen(), range(10)):
            assert i == j

    def outp():
        Cls_ret = Cls.__new__(Cls)
        c = Cls_ret
        gen_ret = []
        self___gen = c
        for i in range(10):
            gen_ret.append(i)
        if "gen_ret" not in globals():
            gen_ret = None
        for i, j in zip(gen_ret, range(10)):
            assert i == j

    run_inline_harness(prog, Cls, outp, locals())


def test_inline_import():
    import api

    def prog():
        api.use_json()

    def outp():
        import json
        assert json.dumps({}) == '{}'
        if "use_json_ret" not in globals():
            use_json_ret = None
        use_json_ret

    run_inline_harness(prog, api, outp, locals())


def test_inline_import_same_file():
    from api import nested_reference

    def prog():
        assert nested_reference() == 1

    def outp():
        from api import f
        if "nested_reference_ret" not in globals():
            nested_reference_ret = f()
        assert nested_reference_ret == 1

    run_inline_harness(prog, nested_reference, outp, locals())


def test_inline_property():
    class Target:
        def __init__(self):
            self.foo = 1

        @property
        def bar(self):
            return self.foo

        @bar.setter
        def bar(self, foo):
            self.foo = foo

    def prog():
        t = Target()
        assert t.bar == 1
        t.bar = 2
        assert t.bar == 2

    def outp():
        Target_ret = Target.__new__(Target)
        self_____init__ = Target_ret
        self_____init__.foo = 1
        t = Target_ret
        self___bar_2 = t
        if "bar" not in globals():
            bar = self___bar_2.foo
        assert bar == 1
        self___bar_4 = t
        foo___bar_4 = 2
        self___bar_4.foo = foo___bar_4
        if "bar_3" not in globals():
            bar_3 = None
        self___bar_6 = t
        if "bar_5" not in globals():
            bar_5 = self___bar_6.foo
        assert bar_5 == 2

    run_inline_harness(prog, Target, outp, locals())


def test_inline_decorator():
    def dec_test(f):
        @functools.wraps(f)
        def newf(*args, **kwargs):
            return f(*args, **kwargs) + 2

        return newf

    @dec_test
    def function_decorator(x):
        return x + 1

    def prog():
        assert function_decorator(1) == 4

    # yapf: disable
    def outp():
        def function_decorator(x):
            return x + 1
        f___dec_test = function_decorator
        def newf(*args, **kwargs):
            return f___dec_test(*args, **kwargs) + 2

        if "dec_test_ret" not in globals():
            dec_test_ret = newf
        args___newf = [1]
        kwargs___newf = {}
        if "dec_test_ret_ret" not in globals():
            x___function_decorator = args___newf[0]
            if "f___dec_test_ret" not in globals():
                f___dec_test_ret = x___function_decorator + 1
            dec_test_ret_ret = f___dec_test_ret + 2
        function_decorator_ret = dec_test_ret_ret
        assert function_decorator_ret == 4

    run_inline_harness(prog, [function_decorator, dec_test],
                       outp,
                       locals(),
                       fixpoint=True)


def test_inline_comprehension_noop():
    def target(x):
        return x + 1

    def prog():
        l = [target(i) for i in range(3)]
        assert sum(l) == 6

    # target SHOULD NOT be inlined, since that would be unsafe
    # before comprehension is expanded
    def outp():
        l = [target(i) for i in range(3)]
        assert sum(l) == 6

    run_inline_harness(prog, target, outp, locals())


def test_inline_preserve_comments():
    def target():
        # hello world
        pass  # yep

    def prog():
        # oh no
        target()

    def outp():
        # oh no
        # hello world
        pass  # yep
        if "target_ret" not in globals():
            target_ret = None
        target_ret

    run_inline_harness(prog, target, outp, locals())


def test_inline_cursor():
    def target():
        pass

    def prog():
        # first line
        target()

    def outp():
        # first line
        pass
        if "target_ret" not in globals():
            target_ret = None
        target_ret

    run_inline_harness(prog, CursorTarget((2, 0)), outp, locals())


def test_inline_source_function():
    def dummy_target():
        pass

    def prog():
        def actual_target():
            pass
        actual_target()

    def outp():
        def actual_target():
            pass
        pass
        if "actual_target_ret" not in globals():
            actual_target_ret = None
        actual_target_ret

    run_inline_harness(prog, dummy_target, outp, locals())
