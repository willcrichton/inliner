import ast
import inspect
from collections import defaultdict
from iterextras import unzip
import textwrap
import os
import typing
from pprint import pprint
from astpretty import pprint as pprintast
import itertools

from .common import *
from .visitors import *
from .tracer import *

from .passes.clean_imports import CleanImportsPass
from .passes.copy_propagation import CopyPropagationPass
from .passes.deadcode import DeadcodePass
from .passes.expand_self import ExpandSelfPass
from .passes.expand_tuples import ExpandTuplesPass
from .passes.inline import InlinePass
from .passes.lifetimes import LifetimesPass
from .passes.unread_vars import UnreadVarsPass


class InlineTarget:
    """
    A representation of a kind of Python object to be inlined.
    """
    def __init__(self, target):
        self.target = target

    def should_inline(self, obj):
        raise NotImplementedError


class ModuleTarget(InlineTarget):
    """
    Inline all objects defined within a module.

    e.g. if target = a.b, then objs defined in a.b or a.b.c will be inlined
    """
    def should_inline(self, obj):
        # Check if object is defined in the same module or a submodule
        # of the target.
        module = inspect.getmodule(obj)
        module_parts = module.__name__.split('.')
        target_parts = self.target.split('.')
        return module_parts[:len(target_parts)] == target_parts


class FunctionTarget(InlineTarget):
    """
    Inline exactly this function
    """
    def should_inline(self, obj):
        if inspect.ismethod(obj):
            # Get the class from the instance bound to the method
            cls = obj.__self__.__class__

            # Check if the class has the target method, and the runtime
            # object is the same
            cls_has_method = hasattr(cls, self.target.__name__)
            if cls_has_method:
                method_same_as_target = getattr(
                    cls, self.target.__name__) == self.target
                return method_same_as_target

            return False

        elif inspect.isfunction(obj):
            # If it's a normal function, then directly compare for function
            # equality
            return obj == self.target


class ClassTarget(InlineTarget):
    """
    Inline this class and all of its methods
    """
    def should_inline(self, obj):
        # e.g. target()
        try:
            constructor = self.target == obj or issubclass(obj, self.target)
        except Exception:
            constructor = False

        # e.g. f = target(); f.foo()
        bound_method = inspect.ismethod(obj) and isinstance(
            obj.__self__, self.target)

        # e.g. f = target(); target.foo(f)
        # https://stackoverflow.com/questions/3589311/get-defining-class-of-unbound-method-object-in-python-3
        if inspect.isfunction(obj):
            qname = obj.__qualname__.split('.')
            unbound_method = len(
                qname) > 1 and qname[-2] == self.target.__name__
        else:
            unbound_method = False

        # e.g. f = target(); f()
        dunder_call = isinstance(obj, self.target)

        return constructor or bound_method or unbound_method or dunder_call


class Inliner:
    def __init__(self, source, inline_targets):
        if not isinstance(source, str):
            source = inspect.getsource(source)
        mod = ast.parse(textwrap.dedent(source))
        if len(mod.body) == 1 and isinstance(mod.body[0], ast.FunctionDef):
            body = mod.body[0].body
        else:
            body = mod.body
        self.module = ast.Module(body=body)

        self.generated_vars = defaultdict(int)
        self.inline_targets = [
            self.make_inline_target(target) for target in inline_targets
        ]

    def make_inline_target(self, target):
        if isinstance(target, str):
            return ModuleTarget(target)
        elif inspect.isfunction(target):
            return FunctionTarget(Target)
        elif inspect.isclass(target):
            return ClassTarget(target)
        elif isinstance(target, InlineTarget):
            return target
        else:
            raise Exception(
                "Can't make inline target from object: {}".format(target))

    def fresh(self, prefix='var'):
        """
        Creates a new variable semi-guaranteed to not exist in the program.
        """
        self.generated_vars[prefix] += 1
        count = self.generated_vars[prefix]
        if count == 1:
            return f'{prefix}'
        else:
            return f'{prefix}_{count}'

    def is_source_obj(self, obj):
        """
        Checks if runtime object was defined in the inliner source.

        Requires that the executed code was run through tracer.compile_and_exec
        """
        try:
            if os.path.basename(inspect.getfile(obj)).startswith(FILE_PREFIX):
                return True
        except TypeError:
            pass

        return False

    def should_inline(self, obj):
        """
        Checks whether a runtime object is something to be inlined.
        """
        module = inspect.getmodule(obj)

        # Unconditionally inline objects defined in the source
        if self.is_source_obj(obj):
            return True

        # Don't inline objects without a module
        if module is None:
            return False

        for target in self.inline_targets:
            if target.should_inline(obj):
                return True

        return False

    def make_program(self, comments=False):
        return a2s(self.module, comments=comments).rstrip()

    def inline(self, debug=False):
        return InlinePass(self).run()

    def expand_self(self):
        return ExpandSelfPass(self).run()

    def clean_imports(self):
        return CleanImportsPass(self).run()

    def unread_vars(self, debug=False):
        return UnreadVarsPass(self).run()

    def copy_propagation(self):
        return CopyPropagationPass(self).run()

    def lifetimes(self):
        return LifetimesPass(self).run()

    def expand_tuples(self):
        return ExpandTuplesPass(self).run()

    def deadcode(self):
        return DeadcodePass(self).run()

    def simplify_kwargs(self):
        prog = self.make_program()
        tracer = Tracer(prog, trace_opcodes=True)
        tracer.trace()
        mod = ast.parse(prog)

        collector = CollectArrayLiterals()
        collector.visit(mod)

        InlineArrayIndex(collector.arrays).visit(mod)
        SimplifyKwargs(tracer.globls).visit(mod)

    def remove_suffixes(self):
        # TODO: make this robust by avoiding name collisions
        remover = RemoveSuffix()
        remover.visit(self.module)
        return True

    def fixpoint(self, f):
        while f():
            pass
