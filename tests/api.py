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
