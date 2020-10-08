from inliner.tracer import Tracer, InsertDummyTransformer, TracerArgs
import libcst as cst


def test_tracer_basic():
    p = """
x = 1
assert x == 1
"""
    t = Tracer(cst.parse_module(p)).trace()
    assert t.globls['x'] == 1


def test_tracer_insert_dummy():
    p = """
for x in range(10):
    if True:
        x = 1
    else:
        x = 2
"""

    mod = cst.parse_module(p)
    mod = mod.visit(InsertDummyTransformer())

    outp = """
for x in range(10):
    __name__
    if True:
        __name__
        x = 1
    else:
        __name__
        x = 2
__name__
"""

    outp_mod = mod.with_changes(body=cst.parse_module(outp).body)
    assert mod.deep_equals(outp_mod)


def test_tracer_exec_counts():
    p = """
if True:
  x = 1
else:
  x = 2"""

    mod = cst.parse_module(p)
    tracer = Tracer(mod, args=TracerArgs(trace_lines=True)).trace()
    exec_counts = tracer.exec_counts()

    def is_execed(n):
        return exec_counts[n] > 0

    assert is_execed(mod)  # module
    assert is_execed(mod.body[0])  # if statement
    assert is_execed(mod.body[0].body)  # then block
    assert is_execed(mod.body[0].body.body[0])  # x = 1
    assert not is_execed(mod.body[0].orelse)  # else
    assert not is_execed(mod.body[0].orelse.body)  # else block
    assert not is_execed(mod.body[0].orelse.body.body[0])  # x = 1


def test_tracer_exec_counts_loop():
    p = """
for x in range(10):
    if x % 2 == 0:
      y = 1
    y = 2
"""

    mod = cst.parse_module(p)
    tracer = Tracer(mod, args=TracerArgs(trace_lines=True)).trace()
    exec_counts = tracer.exec_counts()

    assert exec_counts[mod.body[0]] == 11
    loop_body = mod.body[0].body
    assert exec_counts[loop_body] == 10
    assert exec_counts[loop_body.body[0]] == 10
    assert exec_counts[loop_body.body[0].body] == 5
    assert exec_counts[loop_body.body[1]] == 10
