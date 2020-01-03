import dis
import sys
from collections import defaultdict
from tempfile import NamedTemporaryFile
from .common import try_copy

FILE_PREFIX = 'inline'


def compile_and_exec(code, globls):
    """

    """
    with NamedTemporaryFile(delete=False, prefix=FILE_PREFIX) as f:
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
        self.cur_i = self.frame.f_lasti

    def current_instr(self):
        for i in self.bytecode:
            if i.offset == self.cur_i:
                return i

    def next_instr(self):
        for i in self.bytecode:
            if i.offset > self.cur_i:
                return i


class ValueUnknown:
    pass


class Tracer:
    """
    Executes a program and collects information about loads, stores, and executed lines.
    """
    def __init__(self,
                 prog,
                 globls=None,
                 trace_lines=False,
                 trace_opcodes=False,
                 debug=False):
        self.prog = prog
        self.reads = defaultdict(list)
        self.stores = defaultdict(list)
        self.set_count = defaultdict(int)
        self.execed_lines = defaultdict(int)
        self.trace_opcodes = trace_opcodes
        self.trace_lines = trace_lines
        self._last_store = None
        self.debug = debug
        self.globls = globls.copy() #{k: try_copy(v) for k, v in globls.items()}

    def get_value(self, frame, name):
        # Lookup value in relevant store
        if name in frame.f_locals:
            value = frame.f_locals[name]
        elif name in frame.f_globals:
            value = frame.f_globals[name]
        else:
            value = ValueUnknown()

        # Attempt to copy the value if possible
        return try_copy(value)

    def _trace_fn(self, frame, event, arg):
        if self.trace_opcodes and \
           frame.f_code.co_filename == self._fname:
            frame.f_trace_opcodes = True
        else:
            frame.f_trace_opcodes = False

        if self.trace_lines and \
           frame.f_code.co_filename == self._fname:
            frame.f_trace_lines = True
        else:
            frame.f_trace_lines = False

        if event == 'opcode':
            # The effect of a store appearing in f_locals/globals seems
            # to only happen after f_lasti advances beyond the STORE_NAME
            # so we have to cache the effect and check for it later
            if self._last_store is not None:
                name, lineno = self._last_store
                self.stores[name].append((self.get_value(frame, name), lineno))
                self._last_store = None

            instr = FrameAnalyzer(frame).current_instr()
            name = instr.argval

            if self.debug:
                print(instr.opname, str(instr.argval)[:30])

            if instr.opname in ['STORE_NAME', 'STORE_FAST', 'STORE_GLOBAL']:
                self._last_store = (name, frame.f_lineno)
                self.set_count[name] += 1
            elif instr.opname in ['LOAD_NAME', 'LOAD_FAST', 'LOAD_GLOBAL']:
                self.reads[name].append((self.get_value(frame,
                                                        name), frame.f_lineno))

        elif event == 'line' and frame.f_code.co_filename == self._fname:
            self.execed_lines[frame.f_lineno] += 1

        return self._trace_fn

    def trace(self):
        """
        Execute the provided program.

        In order for introspection tools like inspect.getsource to work on top-level
        objects, we have to actually write the code to a file and compile the code with
        the filename.
        """
        with NamedTemporaryFile(delete=False, prefix=FILE_PREFIX) as f:
            f.write(self.prog.encode('utf-8'))
            f.flush()
            self._fname = f.name

            should_trace = self.trace_lines or self.trace_opcodes
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
