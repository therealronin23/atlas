import json
import os
import pytest
from pathlib import Path
from atlas.mcp.tool_usage import ToolUsageCounter

@pytest.fixture
def tmp_path_fixture(tmp_path):
    return tmp_path

def test_record_inexistent_file(tmp_path_fixture):
    store_path = tmp_path_fixture / 'tool_usage.json'
    counter = ToolUsageCounter(store_path)
    counter.record('tool_name')
    with open(store_path, 'r') as f:
        assert json.load(f) == {'tool_name': 1}

def test_record_same_tool_name(tmp_path_fixture):
    store_path = tmp_path_fixture / 'tool_usage.json'
    counter = ToolUsageCounter(store_path)
    counter.record('tool_name')
    counter.record('tool_name')
    with open(store_path, 'r') as f:
        assert json.load(f) == {'tool_name': 2}

def test_record_different_tool_names(tmp_path_fixture):
    store_path = tmp_path_fixture / 'tool_usage.json'
    counter = ToolUsageCounter(store_path)
    counter.record('tool_name1')
    counter.record('tool_name2')
    with open(store_path, 'r') as f:
        assert json.load(f) == {'tool_name1': 1, 'tool_name2': 1}

def test_counts_inexistent_file(tmp_path_fixture):
    store_path = tmp_path_fixture / 'tool_usage.json'
    counter = ToolUsageCounter(store_path)
    assert counter.counts() == {}

def test_counts_corrupt_file(tmp_path_fixture):
    store_path = tmp_path_fixture / 'tool_usage.json'
    with open(store_path, 'w') as f:
        f.write('invalid json')
    counter = ToolUsageCounter(store_path)
    assert counter.counts() == {}

def test_record_corrupt_file(tmp_path_fixture):
    store_path = tmp_path_fixture / 'tool_usage.json'
    with open(store_path, 'w') as f:
        f.write('invalid json')
    counter = ToolUsageCounter(store_path)
    counter.record('tool_name')
    with open(store_path, 'r') as f:
        assert json.load(f) == {'tool_name': 1}