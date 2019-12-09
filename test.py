class Foo:
    def __init__(self):
        self.x = 1


def fun(a, b, c=1, d=2, *args, **kwargs):
    assert (a == 1)
    assert (b == 2)
    assert (c == 2)
    assert (d == 2)
    assert (len(args) == 0)
    assert (kwargs['f'] == 4)


def a():
    fun(1, b=2, c=2, f=4)
