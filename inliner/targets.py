import inspect
import ast
import importlib
from .common import a2s


class InlineTarget:
    """
    A representation of a kind of Python object to be inlined.
    """
    def __init__(self, target):
        self.target = target

    def should_inline(self, code, obj, globls):
        raise NotImplementedError


class ModuleTarget(InlineTarget):
    """
    Inline all objects defined within a module.

    e.g. if target = a.b, then objs defined in a.b or a.b.c will be inlined
    """
    def should_inline(self, code, obj, globls):
        # Check if object is defined in the same module or a submodule
        # of the target.
        module = inspect.getmodule(obj)
        module_parts = module.__name__.split('.')
        target_parts = self.target.__name__.split('.')
        return module_parts[:len(target_parts)] == target_parts


class FunctionTarget(InlineTarget):
    """
    Inline exactly this function
    """
    def should_inline(self, code, obj, globls):
        if inspect.ismethod(obj):
            return obj.__func__ == self.target

        elif inspect.isfunction(obj):
            return obj == self.target

        else:
            return False


class ClassTarget(InlineTarget):
    """
    Inline this class and all of its methods
    """
    def should_inline(self, code, obj, globls):
        # e.g. Target()
        try:
            constructor = self.target == obj or issubclass(self.target, obj)
        except Exception:
            constructor = False

        # e.g. f = Target(); f.foo()
        bound_method = inspect.ismethod(obj) and issubclass(
            self.target, obj.__self__.__class__)

        # e.g. f = Target(); Target.foo(f)
        # https://stackoverflow.com/questions/3589311/get-defining-class-of-unbound-method-object-in-python-3
        if inspect.isfunction(obj):
            if isinstance(code, ast.Attribute):
                try:
                    cls = eval(a2s(code.value), globls, globls)

                    if isinstance(cls, self.target):
                        unbound_method = True
                    else:
                        unbound_method = issubclass(self.target, cls)
                except Exception:
                    unbound_method = False
            else:
                qname = obj.__qualname__.split('.')
                try:
                    attr = eval('.'.join(qname[:-1]), globls, globls)
                    unbound_method = issubclass(self.target, attr)
                except Exception:
                    unbound_method = False
        else:
            unbound_method = False

        # e.g. f = Target(); f()
        dunder_call = isinstance(obj, self.target)

        return constructor or bound_method or unbound_method or dunder_call


def make_target(target):
    if isinstance(target, str):
        try:
            target_obj = importlib.import_module(target)
        except ModuleNotFoundError:
            parts = target.split('.')

            try:
                mod = importlib.import_module('.'.join(parts[:-1]))
                target_obj = getattr(mod, parts[-1])
            except ModuleNotFoundError:
                mod = importlib.import_module('.'.join(parts[:-2]))
                target_obj = getattr(getattr(mod, parts[-2]), parts[-1])
    else:
        target_obj = target

    if inspect.ismodule(target_obj):
        return ModuleTarget(target_obj)
    elif inspect.isfunction(target_obj):
        return FunctionTarget(target_obj)
    elif inspect.isclass(target_obj):
        return ClassTarget(target_obj)
    else:
        raise Exception(
            "Can't make inline target from object: {}".format(target))
