import json as _json
import os as _os


def load_json_testcases(name):
    """从同目录的 <name>.json 加载 jsonl 测试数据。"""
    p = _os.path.join(_os.path.dirname(__file__), f"{name}.json")
    with open(p) as f:
        return [_json.loads(line) for line in f]


import pytest

from longest_common_subsequence import longest_common_subsequence


testdata = load_json_testcases(longest_common_subsequence.__name__)


@pytest.mark.parametrize("input_data,expected", testdata)
def test_longest_common_subsequence(input_data, expected):
    assert longest_common_subsequence(*input_data) == expected
