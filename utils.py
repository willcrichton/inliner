import dis
import astor
import ast
import itertools
from iterextras import unzip
import sys
from collections import defaultdict
from copy import deepcopy
from pprint import pprint
import pandas as pd
import numpy as np
import typing
from tempfile import NamedTemporaryFile
from astor.code_gen import SourceGenerator
from astor.source_repr import split_lines
import textwrap
import re

SEP = '___'


def compile_and_exec(code, globls):
    with NamedTemporaryFile(delete=False, prefix='inline') as f:
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


class FindFunctions(ast.NodeVisitor):
    def __init__(self):
        self.fns = []

    def visit_FunctionDef(self, fdef):
        self.fns.append(fdef.name)
        self.generic_visit(fdef)


class RemoveSuffix(ast.NodeTransformer):
    def visit_Name(self, name):
        parts = name.id.split(SEP)
        if len(parts) > 1:
            name.id = parts[0]
        return name


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

        # finder = FindFunctions()
        # for stmt in ast.parse(prog).body:
        #     finder.visit(stmt)

        # self.fns = finder.fns

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


COMMENTS = False


class SourceGeneratorWithComments(SourceGenerator):
    def visit_Str(self, node):
        global COMMENTS
        if COMMENTS and \
           '__comment' in node.s:
            s = node.s[10:]
            call = parse_expr(textwrap.dedent(s))
            RemoveSuffix().visit(call)
            s = a2s(call)
            indent = self.indent_with * self.indentation
            comment = '\n'.join([f'{indent}# {part}'
                                 for part in s.split('\n')][:-1])
            self.write('#\n' + comment)
        else:
            super().visit_Str(node)


def a2s(a, comments=False):
    global COMMENTS
    COMMENTS = comments
    outp = astor.to_source(a,
                           source_generator_class=SourceGeneratorWithComments)
    return re.sub(r'^\s*#\s*\n', '\n', outp, flags=re.MULTILINE)


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
    elif isinstance(obj, (typing._GenericAlias, typing._SpecialForm)):
        # TODO: types
        # issue was in pandas, where importing pandas._typing.Axis would
        # resolve module to typing, attempt to do "from typing import Axis"
        return ast.NameConstant(None)
    elif callable(obj):
        return ast.NameConstant(None)
    else:
        raise ObjConversionException(f"No converter for {obj}")


def can_convert_obj_to_ast(obj):
    try:
        obj_to_ast(obj)
        return True
    except ObjConversionException:
        return False


def robust_eq(obj1, obj2):
    if isinstance(obj1, pd.DataFrame) or isinstance(obj1, pd.Series):
        return obj1.equals(obj2)
    elif isinstance(obj1, np.ndarray):
        return np.array_equal(obj1, obj2)
    elif isinstance(obj1, tuple) or isinstance(obj1, list):
        return all(map(lambda t: robust_eq(*t), zip(obj1, obj2)))
    else:
        return obj1 == obj2
