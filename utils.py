import dis
import astor
import ast
import itertools
from iterextras import unzip
import sys
from collections import defaultdict


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


class Tracer:
    def __init__(self, prog, opcode=False):
        self.prog = prog
        self.set_count = defaultdict(int)
        self.execed_lines = defaultdict(int)
        self.opcode = opcode
        self.globls = {}

    def _trace_fn(self, frame, event, arg):
        if self.opcode and frame.f_code.co_filename == 'inline':
            frame.f_trace_opcodes = True
        if event == 'opcode':
            instr = FrameAnalyzer(frame).current_instr()
            if instr.opname == 'STORE_NAME':
                self.set_count[instr.argval] += 1
        elif event == 'line':
            if frame.f_code.co_filename == 'inline':
                self.execed_lines[frame.f_lineno] += 1
        return self._trace_fn

    def trace(self):
        try:
            prog_bytecode = compile(self.prog, 'inline', 'exec')
        except Exception:
            print(self.prog)
            raise
        sys.settrace(self._trace_fn)
        exec(prog_bytecode, self.globls, self.globls)
        sys.settrace(None)


a2s = astor.to_source


def parse_stmt(s):
    return ast.parse(s).body[0]


def parse_expr(s):
    return parse_stmt(s).value


# https://stackoverflow.com/questions/3312989/elegant-way-to-test-python-asts-for-equality-not-reference-or-object-identity
def compare_ast(node1, node2):
    if type(node1) is not type(node2):
        return False
    if isinstance(node1, ast.AST):
        for k, v in vars(node1).items():
            if k in ('lineno', 'col_offset', 'ctx'):
                continue
            if not compare_ast(v, getattr(node2, k)):
                return False
        return True
    elif isinstance(node1, list):
        return all(itertools.starmap(compare_ast, zip(node1, node2)))
    else:
        return node1 == node2


class ObjConversionException(Exception):
    pass


def obj_to_ast(obj):
    if isinstance(obj, tuple):
        return ast.Tuple(elts=tuple(map(obj_to_ast, obj)))
    elif isinstance(obj, dict):
        k, v = unzip([(obj_to_ast(k), obj_to_ast(v)) for k, v in obj.items()])
        return ast.Dict(k, v)
    elif isinstance(obj, list):
        return ast.List(list(map(obj_to_ast, obj)))
    elif isinstance(obj, type):
        return ast.Name(id=obj.__name__)
    elif isinstance(obj, int):
        return ast.Num(obj)
    elif isinstance(obj, str):
        return ast.Str(obj)
    elif obj is None:
        return ast.NameConstant(None)
    else:
        raise ObjConversionException(f"No converter for {obj}")


def can_convert_obj_to_ast(obj):
    try:
        obj_to_ast(obj)
        return True
    except ObjConversionException:
        return False
