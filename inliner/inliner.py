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
from .targets import *
from .passes.base_pass import CancelPass


class Inliner:
    def __init__(self, source, targets, globls=None):
        source_is_func = inspect.isfunction(source)
        if source_is_func:
            if globls is None and hasattr(source, '__globals__'):
                globls = {**source.__globals__, **get_function_locals(source)}

            source = inspect.getsource(source)
        else:
            assert isinstance(source, str)

        mod = ast.parse(textwrap.dedent(source))
        if len(mod.body) == 1 and isinstance(mod.body[0], ast.FunctionDef) and \
           source_is_func:
            body = mod.body[0].body
        else:
            body = mod.body
        self.module = ast.Module(body=body)

        self.globls = globls.copy() if globls is not None else {}

        self.generated_vars = defaultdict(int)
        self._target_strs = []
        self.targets = []
        for target in targets:
            self.add_target(target)

        self.history = [(copy.deepcopy(self.module), None)]

        finder = FindAssignments()
        finder.visit(self.module)
        self.toplevel_vars = finder.names

        for pass_ in PASSES:
            name = self._make_pass_name(pass_.__name__)
            fn = partial(self.run_pass, pass_)
            fn.__name__ = name
            setattr(self, name, fn)

        self.profiling_data = defaultdict(list)
        self._tracer_cache = None

        self.num_inlined = 0
        self.length_inlined = 0

    def _make_pass_name(self, name):
        # Split "TheFooPass" into ["The", "Foo", "Pass"]
        parts = re.findall('.[^A-Z]*', name)

        # Drop "Pass"
        parts = parts[:-1]

        # Make "the_foo"
        return '_'.join([s.lower() for s in parts])

    def add_target(self, target):
        if isinstance(target, str):
            self._target_strs.append(target)
        self.targets.append(make_target(target))

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

    def should_inline(self, code, obj, globls):
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
            if target.should_inline(code, obj, globls):
                return True

        return False

    def run_pass(self, Pass, **kwargs):
        start = now()
        try:
            pass_ = Pass(self)
            change = pass_.run(**kwargs)
        except CancelPass:
            self.module = copy.deepcopy(self.history[-1][0])
            return False
        except Exception:
            self.module = copy.deepcopy(self.history[-1][0])
            raise
        end = now() - start

        if Pass.tracer_args is not None and not change:
            self._tracer_cache = (Pass.tracer_args, pass_.tracer)
        else:
            self._tracer_cache = None

        self.profiling_data[Pass.__name__].append(end)
        self.history.append(
            (copy.deepcopy(self.module), self._make_pass_name(Pass.__name__)))

        return change

    def undo(self):
        self.history.pop()
        self.module = copy.deepcopy(self.history[-1][0])

    def make_program(self, comments=True):
        return a2s(self.module, comments=comments).rstrip()

    def fixpoint(self, f):
        change = False
        while f():
            change = True
            pass
        return change

    def inlinables(self):
        tracer = self.execute()
        collector = CollectInlinables(tracer.globls)
        collector.visit(self.module)
        return collector.inlinables

    def simplify(self):
        while True:
            if not self.inline():
                break
            self.fixpoint(self.deadcode)

        while True:
            any_pass = any([
                self.lifetimes(),
                self.expand_self(),
                self.copy_propagation(),
                self.value_propagation(),
                self.simplify_varargs(),
                self.expand_tuples()
            ])
            if not any_pass:
                break

        self.clean_imports()
        self.remove_suffixes()

    def stats(self):
        return {
            'functions_inlined': self.num_inlined,
            'orig_lines': self.length_inlined,
            'cur_lines': len(self.make_program().split('\n'))
        }

    def execute(self):
        return Tracer(self.make_program(comments=False), self.globls).trace()

    def debug(self):
        f_body = textwrap.indent(a2s(self.history[0][0]).rstrip(), ' ' * 4)

        targets = ', '.join(['"{}"'.format(t) for t in self._target_strs])

        passes = '\n'.join(
            ['i.{}()'.format(passname) for _, passname in self.history[1:]])

        return '''
from inliner import Inliner

def f():
{f_body}

i = Inliner(f, [{targets}])
{passes}

prog = i.make_program()
print(prog)
i.execute()
        '''.format(f_body=f_body, targets=targets, passes=passes)
