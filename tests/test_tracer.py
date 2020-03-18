from inliner.tracer import Tracer, IsExecutedProvider
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

    class Visitor(cst.CSTVisitor):
        METADATA_DEPENDENCIES = (IsExecutedProvider, )

    t = Tracer(p, trace_lines=True).trace()
    provider = IsExecutedProvider(t)
    cst.MetadataWrapper(cst.parse_module(p)).visit(provider)
