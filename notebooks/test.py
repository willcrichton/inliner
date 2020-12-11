class A:
    def __init__(self, flag):
        self.flag = flag

    def foo(self, x):
        if self.flag:
            return x + 1
        else:
            return x * 2
