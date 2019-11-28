class X:
    def __init__(self):
        self.x = 1
        self.foo()

    def foo(self):
        self.x = 2


def a():
    obj = X()
    assert obj.x == 2
