import functools


def dummy():
    return 1


def inline_basic(x, flag=True):
    if flag:
        return x
    else:
        return x + 1


def function_args(a, b, c=1, d=2, *args, **kwargs):
    assert (a == 1)
    assert (b == 2)
    assert (c == 2)
    assert (d == 2)
    assert (len(args) == 0)
    assert (kwargs['f'] == 4)


class ClassBasic:
    def __init__(self, x):
        self.x = x + 1
        self.flag = True
        self.bar()

    def foo(self, x):
        assert self.x + x == 2

    def bar(self):
        assert self.flag


class ClassProperty:
    def __init__(self):
        self.foo = 1

    @property
    def bar(self):
        return self.foo

    @bar.setter
    def bar(self, foo):
        self.foo = foo


def dec_test(f):
    @functools.wraps(f)
    def newf(*args, **kwargs):
        return f(*args, **kwargs) + 2

    return newf


@dec_test
def function_decorator(x):
    return x + 1


GLOBL = 1


def globl():
    return GLOBL


class Context:
    def __init__(self, n):
        self.n = n

    def __enter__(self):
        self.n += 1
        return self

    def __exit__(self, *args):
        self.n += 1
