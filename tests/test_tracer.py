from inliner.tracer import Tracer, get_execed_map
import libcst as cst


def test_tracer_basic():
    p = """
x = 1
assert x == 1
"""
    t = Tracer(p).trace()
    assert t.globls['x'] == 1


def test_tracer_lines():
    p = """
if True:
  x = 1
else:
  x = 2"""

    t = Tracer(p, trace_lines=True).trace()
    assert dict(t.execed_lines) == {3: 1}


def test_tracer_executed_provider():
    p = """
if True:
  x = 1
else:
  x = 2"""

    mod = cst.parse_module(p)
    is_execed = get_execed_map(mod, Tracer(p, trace_lines=True).trace())

    assert is_execed[mod]  # module
    assert is_execed[mod.body[0]]  # if statement
    assert is_execed[mod.body[0].body]  # then block
    assert is_execed[mod.body[0].body.body[0]]  # x = 1
    assert not is_execed[mod.body[0].orelse]  # else
    assert not is_execed[mod.body[0].orelse.body]  # else block
    assert not is_execed[mod.body[0].orelse.body.body[0]]  # x = 1
