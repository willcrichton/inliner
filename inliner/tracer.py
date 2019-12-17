import dis
import sys
from collections import defaultdict
from copy import deepcopy
from tempfile import NamedTemporaryFile


FILE_PREFIX = 'inline'
def compile_and_exec(code, globls):
    with NamedTemporaryFile(delete=False, prefix=FILE_PREFIX) as f:
        f.write(code.encode('utf-8'))
        f.flush()
        exec(compile(code, f.name, 'exec'), globls)


# https://blog.hakril.net/articles/2-understanding-python-execution-tracer.html
class FrameAnalyzer:
    def __init__(self, frame):
        self.frame = frame
        self.code = frame.f_code
        self.bytecode = dis.Bytecode(self.code)
        self.cur_i = self.frame.f_lasti

    def current_instr(self):
        return [i for i in self.bytecode if i.offset == self.cur_i][0]

    def next_instr(self):
        return [i for i in self.bytecode if i.offset > self.cur_i][0]


class ValueUnknown:
    pass


class Tracer:
    def __init__(self, prog, opcode=False, debug=False):
        self.prog = prog
        self.reads = defaultdict(list)
        self.stores = defaultdict(list)
        self.set_count = defaultdict(int)
        self.execed_lines = defaultdict(int)
        self.opcode = opcode
        self.globls = {}
        self._last_store = None
        self.debug = debug

    def get_value(self, frame, name):
        # Lookup value in relevant store
        if name in frame.f_locals:
            value = frame.f_locals[name]
        elif name in frame.f_locals:
            value = frame.f_globals[name]
        else:
            value = ValueUnknown()

        # Attempt to copy the value if possible
        try:
            value = deepcopy(value)
        except Exception:
            pass

        return value

    def _trace_fn(self, frame, event, arg):
        if self.opcode and frame.f_code.co_filename == '__inline':
            frame.f_trace_opcodes = True
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
        elif event == 'line':
            if frame.f_code.co_filename == '__inline':
                self.execed_lines[frame.f_lineno] += 1
        return self._trace_fn

    def trace(self):
        try:
            prog_bytecode = compile(self.prog, '__inline', 'exec')
            sys.settrace(self._trace_fn)
            exec(prog_bytecode, self.globls, self.globls)
            sys.settrace(None)
        except Exception:
            print(self.prog)
            raise
