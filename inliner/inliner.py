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
import copy
import re
from timeit import default_timer as now
from functools import wraps, partial

from .common import *
from .visitors import *
from .tracer import *
from .passes import *


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
    def __init__(self, source, targets, globls=None):
        if not isinstance(source, str):
            if globls is None and hasattr(source, '__globals__'):
                globls = {**source.__globals__, **get_function_locals(source)}

            source = inspect.getsource(source)

        mod = ast.parse(textwrap.dedent(source))
        if len(mod.body) == 1 and isinstance(mod.body[0], ast.FunctionDef):
            body = mod.body[0].body
        else:
            body = mod.body
        self.module = ast.Module(body=body)

        self.globls = globls.copy() if globls is not None else {}

        self.generated_vars = defaultdict(int)
        self.targets = []
        for target in targets:
            self.add_target(target)

        self.history = [(copy.deepcopy(self.module), None)]

        finder = FindAssignments()
        finder.visit(self.module)
        self.toplevel_vars = finder.names

        def make_pass_name(name):
            # Split "TheFooPass" into ["The", "Foo", "Pass"]
            parts = re.findall('.[^A-Z]*', name)

            # Drop "Pass"
            parts = parts[:-1]

            # Make "the_foo"
            return '_'.join([s.lower() for s in parts])

        for pass_ in PASSES:
            name = make_pass_name(pass_.__name__)
            fn = partial(self.run_pass, pass_)
            fn.__name__ = name
            setattr(self, name, fn)

        self.profiling_data = defaultdict(list)
        self._tracer_cache = None

    def _make_target(self, target):
        if isinstance(target, str):
            return ModuleTarget(target)
        elif inspect.isfunction(target):
            return FunctionTarget(target)
        elif inspect.isclass(target):
            return ClassTarget(target)
        elif isinstance(target, InlineTarget):
            return target
        else:
            raise Exception(
                "Can't make inline target from object: {}".format(target))

    def add_target(self, target):
        target = self._make_target(target)
        self.targets.append(target)

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

        Requires that the executed code was run through the tracer.
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

        # Don't inline builtins (they don't have source)
        if inspect.isbuiltin(obj):
            return False

        # Don't inline objects without a module
        if module is None:
            return False

        for target in self.targets:
            if target.should_inline(obj):
                return True

        return False

    def run_pass(self, Pass):
        start = now()
        try:
            pass_ = Pass(self)
            change = pass_.run()
        except Exception:
            self.module = copy.deepcopy(self.history[-1][0])
            raise
        end = now() - start

        if Pass.tracer_args is not None and not change:
            self._tracer_cache = (Pass.tracer_args, pass_.tracer)
        else:
            self._tracer_cache = None

        self.profiling_data[Pass.__name__].append(end)
        self.history.append((copy.deepcopy(self.module), Pass.__name__))

        return change

    def undo(self):
        self.history.pop()
        self.module = copy.deepcopy(self.history[-1][0])

    def make_program(self, comments=False):
        return a2s(self.module, comments=comments).rstrip()

    def fixpoint(self, f):
        change = False
        while f():
            change = True
            pass
        return change

    def modules(self):
        tracer = self.execute()
        collector = CollectModules(tracer.globls)
        collector.visit(self.module)
        return collector.modules

    def autoschedule(self):
        while True:
            if not self.inline():
                break
            self.fixpoint(self.deadcode)

        while True:
            any_pass = any([
                self.unread_vars(),
                self.lifetimes(),
                self.expand_self(),
                self.copy_propagation(),
                self.simplify_varargs(),
                self.expand_tuples()
            ])
            if not any_pass:
                break

        self.clean_imports()
        self.remove_suffixes()

    def execute(self):
        return Tracer(self.make_program(), self.globls).trace()
