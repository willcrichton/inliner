import dis
import sys
from collections import defaultdict
from tempfile import NamedTemporaryFile
from typing import Any, Dict, NamedTuple, Optional

import libcst as cst
from libcst.metadata import PositionProvider

from .common import parse_statement

TRACER_FILE_PREFIX = 'inline'

ExecCounts = Dict[cst.CSTNode, int]
Globals = Dict[str, Any]


def compile_and_exec(code, globls):
    with NamedTemporaryFile(delete=False, prefix=TRACER_FILE_PREFIX) as f:
        f.write(code.encode('utf-8'))
        f.flush()
        exec(compile(code, f.name, 'exec'), globls, globls)


# https://blog.hakril.net/articles/2-understanding-python-execution-tracer.html
class FrameAnalyzer:
    """
    Disassembles a runtime stack frame.
    """
    def __init__(self, frame):
        self.frame = frame
        self.code = frame.f_code
        self.bytecode = dis.Bytecode(self.code)
        self._instr_lookup = {i.offset: i for i in self.bytecode}

    def current_instr(self):
        return self._instr_lookup[self.frame.f_lasti]


class InsertDummyTransformer(cst.CSTTransformer):
    def __init__(self):
        super().__init__()
        self.node_map = {}
        self.in_function = 0

    def visit_FunctionDef(self, node):
        self.in_function += 1
        return super().visit_FunctionDef(node)

    def leave_FunctionDef(self, original_node, updated_node):
        self.in_function -= 1
        return super().leave_FunctionDef(original_node, updated_node)

    def leave_IndentedBlock(self, original_node, updated_node) -> cst.BaseSuite:
        if self.in_function == 0:
            read_stmt = parse_statement("__name__")
            return updated_node.with_changes(body=[read_stmt] +
                                             list(updated_node.body))
        return updated_node

    def on_leave(self, original_node, updated_node):
        final_node = super().on_leave(original_node, updated_node)
        self.node_map[final_node] = original_node
        return final_node


class ExecCountsVisitor(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (PositionProvider, )

    def __init__(self, tracer):
        super().__init__()
        self.tracer = tracer
        self.exec_counts = {}

    def get_exec_counts(self, node):
        if node is None:
            return [0]

        pos = self.get_metadata(PositionProvider, node)
        lines = list(range(pos.start.line, pos.end.line + 1))
        return [self.tracer.execed_lines.get(line, 0) for line in lines]

    def visit_If(self, node):
        self.exec_counts[node] = max(
            max(self.get_exec_counts(node.test)),
            max(self.get_exec_counts(node.body)),
            max(self.get_exec_counts(node.orelse)))

    def on_visit(self, node) -> bool:
        if isinstance(node, (cst.Module, cst.IndentedBlock)):
            first_stmt_count = self.get_exec_counts(node.body[0])
            self.exec_counts[node] = max(first_stmt_count)
        else:
            exec_counts = self.get_exec_counts(node)
            self.exec_counts[node] = max(exec_counts)
        return super().on_visit(node)


class UnusedVarsVisitor(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (PositionProvider, )

    def __init__(self, tracer):
        super().__init__()
        self.tracer = tracer
        self.unused_lines = set()
        self.unused_vars = {}
        self.get_unused_lines()

    def get_unused_lines(self):
        for k, writes in self.tracer.writes.items():
            reads = self.tracer.reads[k]

            for i, cur_write in enumerate(writes):
                next_possible_writes = [
                    next_write.line for next_write in writes[i + 1:]
                    if next_write.line > cur_write.line
                ]
                next_write_line = min(next_possible_writes, default=sys.maxsize)

                unused = True
                for read in reads:
                    if (cur_write.line < read.line and
                            read.line <= next_write_line) or read.in_closure:
                        unused = False

                if unused:
                    self.unused_lines.add(cur_write.line)

    def get_is_unused(self, node):
        pos = self.get_metadata(PositionProvider, node)
        lines = list(range(pos.start.line, pos.end.line + 1))
        return any([line in self.unused_lines for line in lines])

    def on_visit(self, node) -> bool:
        self.unused_vars[node] = self.get_is_unused(node)
        return super().on_visit(node)


class TracerArgs(NamedTuple):
    trace_lines: bool = False
    trace_reads: bool = False
    debug: bool = False


class IOEvent(NamedTuple):
    line: int
    in_closure: bool


class Tracer:
    """
    Executes a program and collects information about loads, writes, and executed lines.
    """

    write_instrs = set(['STORE_NAME', 'STORE_FAST', 'STORE_GLOBAL'])
    read_instrs = set(['LOAD_NAME', 'LOAD_FAST', 'LOAD_GLOBAL'])
    globls: Globals

    def __init__(self,
                 module,
                 globls: Optional[Globals] = None,
                 args: Optional[TracerArgs] = None,
                 cache: bool = True):
        if args is None:
            args = TracerArgs()
        self.module = module
        transformer = InsertDummyTransformer()
        self.transformed_module = self.module.visit(transformer)
        self.node_map = transformer.node_map
        self.reads = defaultdict(list)
        self.writes = defaultdict(list)
        self.execed_lines = defaultdict(int)
        self.trace_lines = args.trace_lines
        self.trace_reads = args.trace_reads
        self._frame_analyzers = {}
        self.globls = globls.copy() if globls is not None else {}

    def _trace_fn(self, frame, event, arg):
        if frame.f_code.co_filename != self._fname:
            frame.f_trace = None
            return

        frame.f_trace_opcodes = self.trace_reads
        frame.f_trace_lines = self.trace_lines or self.trace_reads

        if event == 'opcode':
            if frame not in self._frame_analyzers:
                self._frame_analyzers[frame] = FrameAnalyzer(frame)
            analyzer = self._frame_analyzers[frame]

            instr = analyzer.current_instr()
            name = instr.argval

            in_closure = frame.f_code.co_name != '<module>'
            if instr.opname in self.write_instrs:
                self.writes[name].append(
                    IOEvent(line=frame.f_lineno, in_closure=in_closure))
            elif instr.opname in self.read_instrs:
                self.reads[name].append(
                    IOEvent(line=frame.f_lineno, in_closure=in_closure))

        elif event == 'line':
            self.execed_lines[frame.f_lineno] += 1

        return self._trace_fn

    def exec_counts(self) -> ExecCounts:
        assert self.trace_lines, "Tracer was not executed with trace_lines=True"

        visitor = ExecCountsVisitor(self)

        # unsafe_skip_copy to ensure that nodes in map are pointer-equivalent
        # to input mod
        wrapper = cst.MetadataWrapper(self.transformed_module,
                                      unsafe_skip_copy=True)
        wrapper.visit(visitor)

        exec_counts = visitor.exec_counts
        return {
            self.node_map[k]: v
            for k, v in exec_counts.items() if k in self.node_map
        }

    def unused_vars(self):
        assert self.trace_reads, "Tracer was not executed with trace_reads=True"
        visitor = UnusedVarsVisitor(self)

        # unsafe_skip_copy to ensure that nodes in map are pointer-equivalent
        # to input mod
        wrapper = cst.MetadataWrapper(self.transformed_module,
                                      unsafe_skip_copy=True)
        wrapper.visit(visitor)

        unused_vars = visitor.unused_vars
        return {
            self.node_map[k]: v
            for k, v in unused_vars.items() if k in self.node_map
        }

    def trace(self):
        """
        Execute the provided program.

        In order for introspection tools like inspect.getsource to work on top-level
        objects, we have to actually write the code to a file and compile the code with
        the filename.
        """
        with NamedTemporaryFile(delete=False, prefix=TRACER_FILE_PREFIX) as f:
            prog = self.transformed_module.code
            f.write(prog.encode('utf-8'))
            f.flush()
            self._fname = f.name

            should_trace = self.trace_lines or self.trace_reads
            try:
                prog_bytecode = compile(prog, f.name, 'exec')

                if should_trace:
                    sys.settrace(self._trace_fn)

                # Can't seem to access local variables in a list comprehension?
                # import x; [x.foo() for _ in range(10)]
                # https://github.com/inducer/pudb/issues/103
                # For now, just only use globals
                exec(prog_bytecode, self.globls, self.globls)

                if should_trace:
                    sys.settrace(None)
            except Exception:
                print(prog)
                raise

        return self
