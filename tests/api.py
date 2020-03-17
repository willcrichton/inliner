import json


def use_json():
    assert json.dumps({}) == '{}'


def f():
    return 1


def nested_reference():
    return f()
