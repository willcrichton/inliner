from inliner import InteractiveInliner
from inliner.targets import FunctionTarget
from inliner.tracer import Tracer
from inliner.common import parse_module

import os
import json


def test_interactive_target_suggestions():
    def prog():
        assert json.dumps({}) == '{}'

    i = InteractiveInliner(prog)
    assert i.target_suggestions() == {
        'json.dumps': {
            'path': json.__file__,
            'use': 'json.dumps'
        },
        'json': {
            'path': json.__file__,
            'use': 'json'
        },
    }


def test_interactive_code_folding():
    def prog():
        if True:
            if False:
                x = 1
            else:
                x = 2
        else:
            x = 3

    i = InteractiveInliner(prog)
    assert i.code_folding() == [2, 6]


def test_interactive_undo():
    def target(x):
        return x + 1

    def prog():
        assert target(1) == 2

    i = InteractiveInliner(prog)
    orig_module = i.module
    i.add_target(FunctionTarget(target))
    assert i.run_pass('inline')

    i.undo()
    assert orig_module.deep_equals(i.module)


def test_interactive_debug():
    def prog():
        assert json.dumps({}) == '{}'

    i = InteractiveInliner(prog)
    i.add_target(FunctionTarget(json.dumps))
    assert i.run_pass('inline')

    debug_str = """
from inliner import InteractiveInliner
from inliner.targets import CursorTarget

def f():
    assert json.dumps({}) == '{}'

i = InteractiveInliner(f)
i.add_target("json.dumps")
i.run_pass("inline")

print(i.code())
i.execute()"""
    print(i.debug())
    assert i.debug() == debug_str.strip()
    Tracer(parse_module(debug_str), globls=globals()).trace()
