import json as _json
import os as _os


def load_json_testcases(name):
    """从同目录的 <name>.json 加载 jsonl 测试数据。"""
    p = _os.path.join(_os.path.dirname(__file__), f"{name}.json")
    with open(p) as f:
        return [_json.loads(line) for line in f]


import pytest

from find_first_in_sorted import find_first_in_sorted


testdata = load_json_testcases(find_first_in_sorted.__name__)


@pytest.mark.parametrize("input_data,expected", testdata)
def test_find_first_in_sorted(input_data, expected):
    assert find_first_in_sorted(*input_data) == expected
