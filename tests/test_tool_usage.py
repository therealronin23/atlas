import json
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
        assert json.load(f) == {'tool_name': {'external': 1}}

def test_record_same_tool_name(tmp_path_fixture):
    store_path = tmp_path_fixture / 'tool_usage.json'
    counter = ToolUsageCounter(store_path)
    counter.record('tool_name')
    counter.record('tool_name')
    with open(store_path, 'r') as f:
        assert json.load(f) == {'tool_name': {'external': 2}}

def test_record_different_tool_names(tmp_path_fixture):
    store_path = tmp_path_fixture / 'tool_usage.json'
    counter = ToolUsageCounter(store_path)
    counter.record('tool_name1')
    counter.record('tool_name2')
    with open(store_path, 'r') as f:
        assert json.load(f) == {'tool_name1': {'external': 1}, 'tool_name2': {'external': 1}}

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
        assert json.load(f) == {'tool_name': {'external': 1}}


def test_record_defaults_to_external_origin(tmp_path_fixture):
    store_path = tmp_path_fixture / 'tool_usage.json'
    counter = ToolUsageCounter(store_path)
    counter.record('tool_name')
    assert counter.counts() == {'tool_name': {'external': 1}}


def test_record_self_audit_origin_kept_separate(tmp_path_fixture):
    store_path = tmp_path_fixture / 'tool_usage.json'
    counter = ToolUsageCounter(store_path)
    counter.record('tool_name', origin='self_audit')
    assert counter.counts() == {'tool_name': {'self_audit': 1}}


def test_same_tool_different_origins_accumulate_separately(tmp_path_fixture):
    store_path = tmp_path_fixture / 'tool_usage.json'
    counter = ToolUsageCounter(store_path)
    counter.record('tool_name', origin='external')
    counter.record('tool_name', origin='external')
    counter.record('tool_name', origin='self_audit')
    assert counter.counts() == {'tool_name': {'external': 2, 'self_audit': 1}}


def test_external_counts_ignores_self_audit(tmp_path_fixture):
    store_path = tmp_path_fixture / 'tool_usage.json'
    counter = ToolUsageCounter(store_path)
    counter.record('tool_a', origin='external')
    counter.record('tool_a', origin='self_audit')
    counter.record('tool_a', origin='self_audit')
    counter.record('tool_b', origin='self_audit')
    assert counter.external_counts() == {'tool_a': 1}


def test_migrates_old_flat_format_on_read(tmp_path_fixture):
    store_path = tmp_path_fixture / 'tool_usage.json'
    store_path.write_text(json.dumps({'legacy_tool': 5}), encoding='utf-8')
    counter = ToolUsageCounter(store_path)
    assert counter.counts() == {'legacy_tool': {'external': 5}}


def test_migration_persists_new_format_on_disk(tmp_path_fixture):
    store_path = tmp_path_fixture / 'tool_usage.json'
    store_path.write_text(json.dumps({'legacy_tool': 5}), encoding='utf-8')
    counter = ToolUsageCounter(store_path)
    counter.record('legacy_tool')
    with open(store_path, 'r') as f:
        on_disk = json.load(f)
    assert on_disk == {'legacy_tool': {'external': 6}}
