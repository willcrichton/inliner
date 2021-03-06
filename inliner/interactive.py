import inspect
import textwrap
from typing import NamedTuple

import libcst as cst
from libcst.metadata import PositionProvider, ScopeProvider, ByteSpanPositionProvider
from intervaltree import IntervalTree

from .common import EvalException, a2s
from .contexts import ctx_inliner
from .inliner import Inliner
from .passes.base_pass import BasePass
from .targets import CursorTarget, InlineTarget
from .tracer import Tracer, TracerArgs


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

        elif node.orelse is not None and self.exec_counts[node.orelse] == 0:
            pos = self.get_metadata(PositionProvider, node.orelse)
            self.unexecuted.append(pos.start.line)

    def on_visit(self, node):
        return super().on_visit(node)


class HistoryEntry:
    def to_code(self, name):
        raise NotImplementedError

    def undo(self, inliner):
        raise NotImplementedError


class RunPassHistory(HistoryEntry):
    prev_module: cst.Module
    pass_: BasePass

    def __init__(self, prev_module, pass_):
        self.prev_module = prev_module
        self.pass_ = pass_

    def to_code(self, name):
        pass_name = self.pass_.name()
        return f'{name}.run_pass("{pass_name}")'

    def undo(self, inliner):
        inliner.module = self.prev_module


class AddTargetHistory(HistoryEntry):
    target: InlineTarget

    def __init__(self, target):
        self.target = target

    def to_code(self, name):
        return f'{name}.add_target({self.target.to_string()})'

    def undo(self, inliner):
        inliner.remove_target(self.target)


class InteractiveInliner(Inliner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.history = []
        self.orig_module = self.module

    def add_target(self, target):
        target = super().add_target(target)
        self.history.append(AddTargetHistory(target=target))

    def run_pass(self, Pass, **kwargs):
        prev_module = self.module
        if isinstance(Pass, str):
            Pass = self._name_to_pass(Pass)
        ret = super().run_pass(Pass, **kwargs)
        if ret:
            self.history.append(
                RunPassHistory(prev_module=prev_module, pass_=Pass))
            self.targets = [
                t for t in self.targets if not isinstance(t, CursorTarget)
            ]
        return ret

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

    def code_viewer(self):
        from .jupyter import CodeViewer
        tracer = Tracer(self.module,
                        globls=self.base_globls,
                        args=TracerArgs(trace_lines=True)).trace()
        counts = tracer.exec_counts()
        positions = cst.MetadataWrapper(self.module, unsafe_skip_copy=True).resolve(ByteSpanPositionProvider)

        tree = IntervalTree()
        for node, count in counts.items():
            if isinstance(node, cst.SimpleWhitespace):
                continue

            pos = positions[node]
            if count == 0 and pos.length > 0:
                tree.addi(pos.start, pos.start+pos.length)
        tree.merge_overlaps()

        return CodeViewer(code=self.code(),
                          dead_code=[[i.begin, i.end] for i in tree])

    def undo(self):
        while (not isinstance(self.history[-1], RunPassHistory)):
            self.history.pop().undo(self)
        self.history.pop().undo(self)

    def debug(self):
        with ctx_inliner.set(self):
            f_body = textwrap.indent(a2s(self.orig_module).rstrip(), ' ' * 4)

            passes = '\n'.join([entry.to_code('i') for entry in self.history])

            return f'''
from inliner import InteractiveInliner
from inliner.targets import CursorTarget

def f():
{f_body}

i = InteractiveInliner(f)
{passes}

print(i.code())
i.execute()
            '''.strip()
