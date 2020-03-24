import inspect
import libcst as cst
from typing import NamedTuple, Optional, List
import textwrap
from libcst.metadata import PositionProvider

from .passes.base_pass import BasePass
from .passes.inline import InlinePass
from .tracer import Tracer, TracerArgs
from .inliner import Inliner
from .common import EvalException, a2s, ScopeProvider
from .contexts import ctx_inliner
from .targets import InlineTarget


def object_path(obj):
    mod = inspect.getmodule(obj)

    if mod is not None and hasattr(mod, '__file__'):
        mod_name = mod.__name__
        if inspect.ismodule(obj):
            name = mod_name
        elif inspect.isclass(obj):
            name = mod_name + '.' + obj.__name__
        elif inspect.isfunction(obj):
            name = mod_name + '.' + obj.__qualname__
        elif inspect.ismethod(obj):
            name = mod_name + '.' + obj.__qualname__
        else:
            name = None

        return name

    return None


class CollectTargetSuggestions(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (ScopeProvider, )

    def __init__(self, inliner, globls):
        self.inliner = inliner
        self.globls = globls
        self.suggestions = {}

    def _visit(self, node):

        try:
            obj = self.inliner.eval(node, self.globls)
        except EvalException:
            return

        name = object_path(obj)
        mod = inspect.getmodule(obj)

        if name is not None and name not in self.suggestions:
            self.suggestions[name] = {'path': mod.__file__, 'use': a2s(node)}

    def visit_Name(self, node):
        try:
            self.get_metadata(ScopeProvider, node)
            self._visit(node)
        except KeyError:
            pass

    def visit_Attribute(self, node):
        self._visit(node)


class FindUnexecutedBlocks(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (PositionProvider, )

    def __init__(self, tracer):
        self.exec_counts = tracer.exec_counts()
        self.unexecuted = []

    def visit_If(self, node):
        if self.exec_counts[node.body] == 0:
            pos = self.get_metadata(PositionProvider, node)
            self.unexecuted.append(pos.start.line)

        elif self.exec_counts[node.orelse] == 0:
            pos = self.get_metadata(PositionProvider, node.orelse)
            self.unexecuted.append(pos.start.line)


class HistoryEntry(NamedTuple):
    module: cst.Module
    pass_: Optional[BasePass]
    targets: Optional[List[InlineTarget]] = None

    def to_code(self, inliner):
        pass_name = self.pass_.name()
        if self.pass_ is InlinePass:
            assert self.targets is not None
            targets_str = ','.join([f'"{t.to_string()}"' for t in self.targets])
            return f'{inliner}.{pass_name}(targets=[{targets_str}])'
        else:
            return f'{inliner}.{pass_name}()'


class InteractiveInliner(Inliner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.history = [HistoryEntry(module=self.module, pass_=None)]

    def target_suggestions(self):
        with ctx_inliner.set(self):
            globls = Tracer(self.module, globls=self.base_globls).trace().globls
            collector = CollectTargetSuggestions(self, globls)
            cst.MetadataWrapper(self.module).visit(collector)
            return collector.suggestions

    def code_folding(self):
        tracer = Tracer(self.module,
                        globls=self.base_globls,
                        args=TracerArgs(trace_lines=True)).trace()
        finder = FindUnexecutedBlocks(tracer)
        cst.MetadataWrapper(self.module, unsafe_skip_copy=True).visit(finder)
        return sorted(finder.unexecuted)

    def inline(self, targets=[], **kwargs):
        ret = super().inline(targets, **kwargs)
        self.history.append(
            HistoryEntry(module=self.module, pass_=InlinePass, targets=targets))
        return ret

    def run_pass(self, Pass, **kwargs):
        ret = super().run_pass(Pass, **kwargs)
        if Pass is not InlinePass:
            self.history.append(HistoryEntry(module=self.module, pass_=Pass))
        return ret

    def undo(self):
        self.history.pop()
        assert len(self.history) > 0
        self.module = self.history[-1].module

    def debug(self):
        with ctx_inliner.set(self):
            f_body = textwrap.indent(
                a2s(self.history[0].module).rstrip(), ' ' * 4)

            passes = '\n'.join(
                [entry.to_code('i') for entry in self.history[1:]])

            return f'''
from inliner import Inliner

def f():
{f_body}

i = Inliner(f)
{passes}

print(i.code())
i.execute()
            '''.strip()
