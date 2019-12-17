class A:
    def __init__(self):
        self.foo = 1

class B(A):
    def __init__(self, x):
        super().__init__()
        self.foo += x
