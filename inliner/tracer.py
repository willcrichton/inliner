from tempfile import NamedTemporaryFile
from collections import defaultdict
import sys
import dis

TRACER_FILE_PREFIX = 'inline'


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


class Tracer:
    """
    Executes a program and collects information about loads, stores, and executed lines.
    """

    store_instrs = set(['STORE_NAME', 'STORE_FAST', 'STORE_GLOBAL'])
    read_instrs = set(['LOAD_NAME', 'LOAD_FAST', 'LOAD_GLOBAL'])

    def __init__(self,
                 prog,
                 globls=None,
                 trace_lines=False,
                 trace_reads=False,
                 debug=False):
        self.prog = prog
        self.reads = defaultdict(list)
        self.stores = defaultdict(list)
        self.execed_lines = defaultdict(int)
        self.trace_lines = trace_lines
        self.trace_reads = trace_reads
        self._frame_analyzer = None
        self.globls = globls

    def _trace_fn(self, frame, event, arg):
        if frame.f_code.co_filename != self._fname:
            frame.f_trace = None
            return

        frame.f_trace_opcodes = self.trace_reads
        frame.f_trace_lines = self.trace_lines

        if event == 'opcode':
            if self._frame_analyzer is None:
                self._frame_analyzer = FrameAnalyzer(frame)

            instr = self._frame_analyzer.current_instr()
            name = instr.argval

            if instr.opname in self.store_instrs:
                self.stores[name].append(frame.f_lineno)
            elif instr.opname in self.read_instrs:
                self.reads[name].append(frame.f_lineno)

        elif event == 'line':
            self.execed_lines[frame.f_lineno] += 1

        return self._trace_fn

    def trace(self):
        """
        Execute the provided program.

        In order for introspection tools like inspect.getsource to work on top-level
        objects, we have to actually write the code to a file and compile the code with
        the filename.
        """
        with NamedTemporaryFile(delete=False, prefix=TRACER_FILE_PREFIX) as f:
            f.write(self.prog.encode('utf-8'))
            f.flush()
            self._fname = f.name

            should_trace = self.trace_lines or self.trace_reads
            try:
                prog_bytecode = compile(self.prog, f.name, 'exec')

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
                print(self.prog)
                raise

        return self
