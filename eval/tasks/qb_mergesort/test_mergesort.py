import json as _json
import os as _os


def load_json_testcases(name):
    """从同目录的 <name>.json 加载 jsonl 测试数据。"""
    p = _os.path.join(_os.path.dirname(__file__), f"{name}.json")
    with open(p) as f:
        return [_json.loads(line) for line in f]


import pytest

from mergesort import mergesort


testdata = load_json_testcases(mergesort.__name__)


@pytest.mark.parametrize("input_data,expected", testdata)
def test_mergesort(input_data, expected):
    assert mergesort(*input_data) == expected
