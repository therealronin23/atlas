"""Regression tests for the local Graphify/Neo4j operator path.

These tests run copied shell scripts in an isolated temporary repository.  They
must never source the real ``.env`` or contact the live Neo4j instance.
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"


def _clean_env(**overrides: str) -> dict[str, str]:
    graphify_spec = importlib.util.find_spec("graphify")
    graphify_pythonpath = (
        str(Path(graphify_spec.origin).resolve().parent.parent)
        if graphify_spec is not None and graphify_spec.origin is not None
        else ""
    )
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": graphify_pythonpath,
    }
    env.update(overrides)
    return env


def _copy_script(tmp_path: Path, name: str) -> Path:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    destination = scripts_dir / name
    destination.write_text((SCRIPTS / name).read_text(encoding="utf-8"), encoding="utf-8")
    destination.chmod(0o755)
    return destination


def _run(
    script: Path,
    tmp_path: Path,
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script), *args],
        cwd=tmp_path,
        env=env or _clean_env(),
        capture_output=True,
        text=True,
        timeout=20,
    )


@pytest.mark.parametrize(
    "name",
    [
        "health-check.sh",
        "install-knowledge-hooks.sh",
        "neo4j-backup.sh",
        "neo4j-import.sh",
        "neo4j-rag-query.sh",
        "run-graphify-quality-pipeline.sh",
        "update-knowledge-graph.sh",
        "update-knowledge-graph-rag.sh",
    ],
)
def test_knowledge_stack_shell_scripts_parse(name: str) -> None:
    result = subprocess.run(
        ["bash", "-n", str(SCRIPTS / name)],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr


def test_graphify_ignores_generated_paper_derivatives_but_keeps_markdown_source() -> None:
    ignored = {
        line.strip()
        for line in (REPO_ROOT / ".graphifyignore").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    base = "docs/outreach/paper/paper_subject_enforced_completeness"
    assert f"{base}.pdf" in ignored
    assert f"{base}.html" in ignored
    assert f"{base}.md" not in ignored


def _prepare_fake_graphify_repo(tmp_path: Path, script_name: str) -> tuple[Path, Path]:
    script = _copy_script(tmp_path, script_name)
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "activate").write_text("# isolated no-op activate\n", encoding="utf-8")
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "graph.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "graphify-out" / "manifest.json").write_text(
        "{}\n", encoding="utf-8"
    )

    calls = tmp_path / "graphify-out" / "graphify-calls.txt"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    graphify = fake_bin / "graphify"
    graphify.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s|%s\\n' \"${PYTHONHASHSEED:-}\" \"$*\" >> \"$GRAPHIFY_CALLS\"\n"
        "if [ -n \"${GRAPHIFY_RETRIES_FILE:-}\" ]; then "
        "printf '%s\\n' \"${GRAPHIFY_MAX_RETRIES:-}\" > \"$GRAPHIFY_RETRIES_FILE\"; fi\n"
        "if [ -n \"${GRAPHIFY_TIMEOUT_FILE:-}\" ]; then "
        "printf '%s\\n' \"${GRAPHIFY_API_TIMEOUT:-}\" > \"$GRAPHIFY_TIMEOUT_FILE\"; fi\n"
        "if [ -n \"${GRAPHIFY_ENDPOINT_FILE:-}\" ]; then "
        "printf '%s\\n' \"${OPENAI_BASE_URL:-}\" > \"$GRAPHIFY_ENDPOINT_FILE\"; fi\n"
        "if [ \"${1:-}\" = 'extract' ]; then\n"
        "  if [ -n \"${GRAPHIFY_MANIFEST_STATE_FILE:-}\" ]; then\n"
        "    if [ -e graphify-out/manifest.json ]; then printf 'present\\n'; else printf 'absent\\n'; fi > \"$GRAPHIFY_MANIFEST_STATE_FILE\"\n"
        "  fi\n"
        "  python3 - <<'PY'\n"
        "from pathlib import Path\n"
        "from graphify.detect import detect, save_manifest\n"
        "root = Path('.').resolve()\n"
        "result = detect(root)\n"
        "save_manifest(result['files'], manifest_path='graphify-out/manifest.json', kind='both', root=root)\n"
        "PY\n"
        "  printf '%s\\n' \"${GRAPHIFY_GRAPH_REPLACEMENT:-{\\\"nodes\\\":[],\\\"links\\\":[]}}\" > graphify-out/graph.json\n"
        "  if [ -n \"${GRAPHIFY_CREATE_CACHE_ENTRY:-}\" ]; then mkdir -p \"$(dirname \"$GRAPHIFY_CREATE_CACHE_ENTRY\")\"; printf '{}\\n' > \"$GRAPHIFY_CREATE_CACHE_ENTRY\"; fi\n"
        "  if [ -n \"${GRAPHIFY_MUTATE_AFTER_EXTRACT_FILE:-}\" ]; then printf 'changed after snapshot\\n' > \"$GRAPHIFY_MUTATE_AFTER_EXTRACT_FILE\"; fi\n"
        "fi\n"
        "if [ \"${1:-}\" = 'cluster-only' ]; then\n"
        "  printf '%s\\n' '{\"communities\":{}}' > graphify-out/.graphify_analysis.json\n"
        "  printf '%s\\n' '{}' > graphify-out/.graphify_labels.json\n"
        "fi\n"
        "if [ \"${1:-}\" = '--version' ]; then printf 'graphify 0.9.11\\n'; fi\n",
        encoding="utf-8",
    )
    graphify.chmod(0o755)
    if script_name == "update-knowledge-graph-rag.sh":
        adapter = tmp_path / "scripts" / "graphify_obsidian_export.py"
        adapter.write_text(
            "import os\n"
            "from pathlib import Path\n"
            "Path(os.environ['GRAPHIFY_CALLS']).open('a', encoding='utf-8').write('0|obsidian-adapter\\n')\n",
            encoding="utf-8",
        )
    return script, calls


@pytest.mark.parametrize(
    ("script_name", "args"),
    [
        ("update-knowledge-graph.sh", ()),
        ("update-knowledge-graph-rag.sh", ("--code-only",)),
    ],
)
def test_code_only_refresh_uses_graphify_0911_subcommands_and_stable_seed(
    tmp_path: Path,
    script_name: str,
    args: tuple[str, ...],
) -> None:
    script, calls_path = _prepare_fake_graphify_repo(tmp_path, script_name)
    env = _clean_env(
        PATH=f"{tmp_path / 'fake-bin'}:{os.environ.get('PATH', '')}",
        GRAPHIFY_CALLS=str(calls_path),
    )

    result = _run(script, tmp_path, *args, env=env)

    assert result.returncode == 0, result.stderr
    calls = calls_path.read_text(encoding="utf-8").splitlines()
    assert "0|update ." in calls, calls
    assert "0|cluster-only . --no-label --no-viz" in calls, calls
    assert not any(". --update" in call or ". --cluster-only" in call for call in calls)


def test_semantic_refresh_fails_closed_when_graphify_rebuild_lock_is_held(
    tmp_path: Path,
) -> None:
    fcntl = pytest.importorskip("fcntl")
    script, calls_path = _prepare_fake_graphify_repo(
        tmp_path, "update-knowledge-graph-rag.sh"
    )
    lock_path = tmp_path / "graphify-out" / ".rebuild.lock"
    with lock_path.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = _run(
            script,
            tmp_path,
            "--backend",
            "ollama",
            env=_clean_env(
                PATH=f"{tmp_path / 'fake-bin'}:{os.environ.get('PATH', '')}",
                GRAPHIFY_CALLS=str(calls_path),
                GRAPHIFY_LOCK_TIMEOUT="0",
            ),
        )

    assert result.returncode != 0
    assert "rebuild lock" in result.stderr.lower()
    calls = calls_path.read_text(encoding="utf-8").splitlines()
    assert not any("extract " in call for call in calls), calls


def test_semantic_refresh_reconciles_code_before_export(tmp_path: Path) -> None:
    script, calls_path = _prepare_fake_graphify_repo(
        tmp_path, "update-knowledge-graph-rag.sh"
    )
    diagnostics = tmp_path / "graphify-out"
    retries_path = diagnostics / "graphify-retries.txt"
    timeout_path = diagnostics / "graphify-timeout.txt"
    endpoint_path = diagnostics / "graphify-endpoint.txt"
    manifest_state_path = diagnostics / "graphify-manifest-state.txt"
    result = _run(
        script,
        tmp_path,
        "--backend",
        "openai",
        "--model",
        "meta/llama-3.3-70b-instruct",
        "--api-timeout",
        "123",
        env=_clean_env(
            PATH=f"{tmp_path / 'fake-bin'}:{os.environ.get('PATH', '')}",
            GRAPHIFY_CALLS=str(calls_path),
            GRAPHIFY_LOCK_TIMEOUT="1",
            GRAPHIFY_RETRIES_FILE=str(retries_path),
            GRAPHIFY_API_TIMEOUT="999",
            GRAPHIFY_TIMEOUT_FILE=str(timeout_path),
            GRAPHIFY_ENDPOINT_FILE=str(endpoint_path),
            GRAPHIFY_MANIFEST_STATE_FILE=str(manifest_state_path),
            NVIDIA_API_KEY="synthetic-nvidia-key",
            OPENAI_API_KEY="synthetic-different-openai-key",
        ),
    )

    assert result.returncode == 0, result.stderr
    calls = calls_path.read_text(encoding="utf-8").splitlines()
    extract_index = next(i for i, call in enumerate(calls) if "extract ." in call)
    cluster_call = next(call for call in calls if "cluster-only ." in call)
    export_index = calls.index("0|obsidian-adapter")
    assert extract_index < export_index
    assert "0|update ." not in calls
    assert manifest_state_path.read_text(encoding="utf-8").strip() == "absent"
    assert "--no-label" in cluster_call
    assert "--backend" not in cluster_call
    # Advisory flock files must keep a stable inode. Unlinking while a holder
    # or waiter still references the old inode lets a third process acquire a
    # newly-created inode and rebuild concurrently.
    assert (tmp_path / "graphify-out" / ".rebuild.lock").exists()
    assert 'rm -f "$GRAPHIFY_REBUILD_LOCK"' not in script.read_text(
        encoding="utf-8"
    )
    assert retries_path.read_text(encoding="utf-8").strip() == "1"
    assert timeout_path.read_text(encoding="utf-8").strip() == "123"
    assert endpoint_path.read_text(encoding="utf-8").strip() == (
        "https://integrate.api.nvidia.com/v1"
    )


def test_semantic_refresh_restores_last_publication_when_source_drifts(
    tmp_path: Path,
) -> None:
    script, calls_path = _prepare_fake_graphify_repo(
        tmp_path, "update-knowledge-graph-rag.sh"
    )
    graph_path = tmp_path / "graphify-out" / "graph.json"
    manifest_path = tmp_path / "graphify-out" / "manifest.json"
    previous_graph = graph_path.read_bytes()
    previous_manifest = manifest_path.read_bytes()
    drift_file = tmp_path / "changed-during-extract.md"
    cache_dir = tmp_path / "graphify-out" / "cache" / "semantic"
    cache_dir.mkdir(parents=True)
    existing_cache = cache_dir / ("a" * 64 + ".json")
    failed_run_cache = cache_dir / ("b" * 64 + ".json")
    existing_cache.write_text("{}\n", encoding="utf-8")

    result = _run(
        script,
        tmp_path,
        "--backend",
        "ollama",
        env=_clean_env(
            PATH=f"{tmp_path / 'fake-bin'}:{os.environ.get('PATH', '')}",
            GRAPHIFY_CALLS=str(calls_path),
            GRAPHIFY_LOCK_TIMEOUT="1",
            GRAPHIFY_GRAPH_REPLACEMENT=(
                '{"nodes":[{"id":"candidate"}],"links":[]}'
            ),
            GRAPHIFY_CREATE_CACHE_ENTRY=str(failed_run_cache),
            GRAPHIFY_MUTATE_AFTER_EXTRACT_FILE=str(drift_file),
        ),
    )

    assert result.returncode == 75
    assert "source tree drifted" in result.stderr
    assert graph_path.read_bytes() == previous_graph
    assert manifest_path.read_bytes() == previous_manifest
    assert existing_cache.is_file()
    assert not failed_run_cache.exists()
    assert not (tmp_path / "graphify-out" / ".semantic-publish.backup").exists()
    assert not (tmp_path / "graphify-out" / ".semantic-publish.preparing").exists()
    calls = calls_path.read_text(encoding="utf-8").splitlines()
    assert "0|obsidian-adapter" not in calls
    assert not any("export neo4j" in call for call in calls)


def test_obsidian_adapter_caps_filenames_to_real_filesystem_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = SCRIPTS / "graphify_obsidian_export.py"
    spec = importlib.util.spec_from_file_location("graphify_obsidian_export", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_filesystem_name_max", lambda _directory: 143)

    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    full_label = "semantic-label-" + "x" * 300
    graph_path = graph_dir / "graph.json"
    graph_path.write_text(
        json.dumps(
            {
                "directed": False,
                "multigraph": False,
                "graph": {},
                "nodes": [
                    {
                        "id": "long-node",
                        "label": full_label,
                        "file_type": "document",
                        "community": 0,
                    }
                ],
                "links": [],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "vault"

    notes = module.export_obsidian(graph_path, output)

    assert notes >= 1
    assert all(len(path.name.encode("utf-8")) <= 143 for path in output.iterdir())
    node_notes = [
        path
        for path in output.glob("*.md")
        if not path.name.startswith("_COMMUNITY_")
    ]
    assert len(node_notes) == 1
    assert f"# {full_label}" in node_notes[0].read_text(encoding="utf-8")
    assert (output / "graph.canvas").is_file()

    user_note = output / "my-operator-note.md"
    user_note.write_text("human annotation\n", encoding="utf-8")
    orphan = output / "obsolete-generated-note.md"
    orphan.write_text(
        "---\nsource_file: \"old.py\"\ntype: \"code\"\n"
        "tags:\n  - graphify/code\n---\n# obsolete\n",
        encoding="utf-8",
    )

    replaced_notes = module.export_obsidian(
        graph_path,
        output,
        replace_generated=True,
    )

    assert replaced_notes >= 1
    assert user_note.read_text(encoding="utf-8") == "human annotation\n"
    assert not orphan.exists()
    assert not list(tmp_path.glob(".vault.backup-*"))


def test_semantic_refresh_normalizes_legacy_openai_api_base(
    tmp_path: Path,
) -> None:
    script, calls_path = _prepare_fake_graphify_repo(
        tmp_path, "update-knowledge-graph-rag.sh"
    )
    endpoint_path = tmp_path / "graphify-endpoint.txt"

    result = _run(
        script,
        tmp_path,
        "--backend",
        "openai",
        "--model",
        "openai/gpt-oss-120b",
        env=_clean_env(
            PATH=f"{tmp_path / 'fake-bin'}:{os.environ.get('PATH', '')}",
            GRAPHIFY_CALLS=str(calls_path),
            GRAPHIFY_ENDPOINT_FILE=str(endpoint_path),
            OPENAI_API_KEY="synthetic-nvidia-key",
            OPENAI_API_BASE="https://integrate.api.nvidia.com/v1",
        ),
    )

    assert result.returncode == 0, result.stderr
    assert endpoint_path.read_text(encoding="utf-8").strip() == (
        "https://integrate.api.nvidia.com/v1"
    )


def test_quality_plan_routes_nvidia_model_when_openai_key_is_also_set(
    tmp_path: Path,
) -> None:
    script = _copy_script(tmp_path, "run-graphify-quality-pipeline.sh")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "activate").write_text(
        "# isolated no-op activate\n", encoding="utf-8"
    )

    result = _run(
        script,
        tmp_path,
        "--backend",
        "openai",
        "--model",
        "meta/llama-3.3-70b-instruct",
        "--print-plan",
        env=_clean_env(
            NVIDIA_API_KEY="synthetic-nvidia-key",
            OPENAI_API_KEY="synthetic-different-openai-key",
        ),
    )

    assert result.returncode == 0, result.stderr
    assert "endpoint=https://integrate.api.nvidia.com/v1" in result.stdout


def test_quality_pipeline_rejects_ignored_non_root_target(tmp_path: Path) -> None:
    script = _copy_script(tmp_path, "run-graphify-quality-pipeline.sh")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "activate").write_text(
        "# isolated no-op activate\n", encoding="utf-8"
    )

    result = _run(script, tmp_path, "--path", "docs", "--print-plan")

    assert result.returncode == 2
    assert "only supports --path ." in result.stderr


@pytest.mark.parametrize(
    ("args", "label"),
    [
        (("--max-invalid-json", "not-a-number"), "max-invalid-json"),
        (("--min-nodes", "-1"), "min-nodes"),
        (("--api-timeout", "0"), "api-timeout"),
        (("--max-workers", "0"), "max-workers"),
        (("--max-partial-results", "-1"), "max-partial-results"),
    ],
)
def test_quality_pipeline_rejects_invalid_numeric_controls_before_work(
    tmp_path: Path, args: tuple[str, str], label: str
) -> None:
    script = _copy_script(tmp_path, "run-graphify-quality-pipeline.sh")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "activate").write_text(
        "# isolated no-op activate\n", encoding="utf-8"
    )

    result = _run(script, tmp_path, *args, "--print-plan")

    assert result.returncode == 2
    assert f"--{label}" in result.stderr


def test_quality_report_counts_only_current_run_and_does_not_double_count(
    tmp_path: Path,
) -> None:
    script = _copy_script(tmp_path, "run-graphify-quality-pipeline.sh")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "activate").write_text(
        "# isolated no-op activate\n", encoding="utf-8"
    )
    graph_dir = tmp_path / "graphify-out"
    log_dir = graph_dir / "logs"
    log_dir.mkdir(parents=True)
    log_path = log_dir / "pipeline.log"
    log_path.write_text(
        "--- run started 2026-07-15T00:00:00Z backend=old model=old ---\n"
        + "[graphify] LLM returned invalid JSON, skipping chunk\n" * 12,
        encoding="utf-8",
    )

    rag = tmp_path / "scripts" / "update-knowledge-graph-rag.sh"
    rag.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$*\" > \"$RAG_ARGS_FILE\"\n"
        "mkdir -p graphify-out\n"
        "printf '%s\\n' '{\"nodes\":[{\"id\":\"current\",\"community\":7},{\"id\":\"peer\",\"community\":7}],\"links\":[{\"source\":\"current\",\"target\":\"peer\"}]}' > graphify-out/graph.json\n"
        "touch graphify-out/cypher.txt graphify-out/GRAPH_REPORT.md\n"
        "echo '[graphify extract] semantic cache: 7 hit / 2 miss'\n"
        "echo '[graphify] LLM returned invalid JSON, skipping chunk'\n",
        encoding="utf-8",
    )
    rag.chmod(0o755)
    (tmp_path / "scripts" / "graphify_failure_guard.py").write_text(
        "# isolated no-op guard\n", encoding="utf-8"
    )

    result = _run(
        script,
        tmp_path,
        "--max-retries",
        "2",
        "--strict",
        "--min-nodes",
        "1",
        "--max-invalid-json",
        "1",
        env=_clean_env(RAG_ARGS_FILE=str(tmp_path / "rag-args.txt")),
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(
        (graph_dir / "quality-report.json").read_text(encoding="utf-8")
    )
    assert report["invalid_json_count"] == 1
    assert report["semantic_cache_hits"] == 7
    assert report["semantic_cache_misses"] == 2
    assert report["semantic_cache_provenance"] == "mixed_or_unverified"
    assert report["node_count"] == 2
    assert report["edge_count"] == 1
    assert report["community_count"] == 1
    assert report["graph_id_validation_status"] == "checked"
    assert report["legacy_file_id_count"] == 0
    assert stat.S_IMODE(log_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(log_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(
        (graph_dir / "quality-report.json").stat().st_mode
    ) == 0o600
    assert "--max-retries 2" in (tmp_path / "rag-args.txt").read_text(
        encoding="utf-8"
    )


def test_quality_strict_rejects_raw_graph_without_communities(
    tmp_path: Path,
) -> None:
    script = _copy_script(tmp_path, "run-graphify-quality-pipeline.sh")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "activate").write_text(
        "# isolated no-op activate\n", encoding="utf-8"
    )
    rag = tmp_path / "scripts" / "update-knowledge-graph-rag.sh"
    rag.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "mkdir -p graphify-out\n"
        "printf '%s\\n' '{\"nodes\":[{\"id\":\"a\"},{\"id\":\"b\"}],\"edges\":[{\"source\":\"a\",\"target\":\"b\"}]}' > graphify-out/graph.json\n"
        "touch graphify-out/cypher.txt graphify-out/GRAPH_REPORT.md\n",
        encoding="utf-8",
    )
    rag.chmod(0o755)
    (tmp_path / "scripts" / "graphify_failure_guard.py").write_text(
        "# isolated no-op guard\n", encoding="utf-8"
    )

    result = _run(script, tmp_path, "--strict", "--min-nodes", "1")

    assert result.returncode != 0
    report = json.loads(
        (tmp_path / "graphify-out" / "quality-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["community_count"] == 0
    assert "community_count=0 for a non-empty connected graph" in (
        report["quality_gate_violations"]
    )


def test_quality_legacy_id_check_ignores_non_file_mcp_nodes_on_line_one(
    tmp_path: Path,
) -> None:
    script = _copy_script(tmp_path, "run-graphify-quality-pipeline.sh")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "activate").write_text(
        "# isolated no-op activate\n", encoding="utf-8"
    )
    rag = tmp_path / "scripts" / "update-knowledge-graph-rag.sh"
    graph = {
        "nodes": [
            {
                "id": "cursor_mcp",
                "label": "mcp.json",
                "source_file": ".cursor/mcp.json",
                "source_location": "L1",
                "_origin": "ast",
                "metadata": {"mcp_kind": "mcp_config_file"},
            },
                {
                    "id": "mcp_command_workspacefolder_venv_bin_python",
                "label": "${workspaceFolder}/.venv/bin/python",
                "source_file": ".cursor/mcp.json",
                "source_location": "L1",
                "_origin": "ast",
                    "metadata": {"mcp_kind": "mcp_command"},
                },
                {
                    "id": "scripts_capability_route_hook_py_scripts_capability_route_hook",
                    "label": "capability_route_hook.py",
                    "source_file": "scripts/capability_route_hook.py",
                    "source_location": "L1",
                    "_origin": "ast",
                },
                {
                    "id": "scripts_capability_route_hook_sh_scripts_capability_route_hook",
                    "label": "capability_route_hook.sh",
                    "source_file": "scripts/capability_route_hook.sh",
                    "source_location": "L1",
                    "_origin": "ast",
                },
        ],
        "links": [],
    }
    rag.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "mkdir -p graphify-out\n"
        f"printf '%s\\n' '{json.dumps(graph)}' > graphify-out/graph.json\n"
        "touch graphify-out/cypher.txt graphify-out/GRAPH_REPORT.md\n",
        encoding="utf-8",
    )
    rag.chmod(0o755)
    (tmp_path / "scripts" / "graphify_failure_guard.py").write_text(
        "# isolated no-op guard\n", encoding="utf-8"
    )

    result = _run(script, tmp_path, "--strict", "--min-nodes", "1")

    assert result.returncode == 0, result.stderr
    report = json.loads(
        (tmp_path / "graphify-out" / "quality-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["legacy_file_id_count"] == 0


def test_quality_strict_rejects_actual_legacy_file_node_id(tmp_path: Path) -> None:
    script = _copy_script(tmp_path, "run-graphify-quality-pipeline.sh")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "activate").write_text(
        "# isolated no-op activate\n", encoding="utf-8"
    )
    rag = tmp_path / "scripts" / "update-knowledge-graph-rag.sh"
    graph = {
        "nodes": [
            {
                "id": "orchestrator",
                "label": "orchestrator.py",
                "source_file": "src/atlas/core/orchestrator.py",
                "source_location": "L1",
                "_origin": "ast",
            }
        ],
        "links": [],
    }
    rag.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "mkdir -p graphify-out\n"
        f"printf '%s\\n' '{json.dumps(graph)}' > graphify-out/graph.json\n"
        "touch graphify-out/cypher.txt graphify-out/GRAPH_REPORT.md\n",
        encoding="utf-8",
    )
    rag.chmod(0o755)
    (tmp_path / "scripts" / "graphify_failure_guard.py").write_text(
        "# isolated no-op guard\n", encoding="utf-8"
    )

    result = _run(script, tmp_path, "--strict", "--min-nodes", "1")

    assert result.returncode != 0
    report = json.loads(
        (tmp_path / "graphify-out" / "quality-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["legacy_file_id_count"] == 1
    assert "legacy_file_id_count=1 > 0" in report["quality_gate_violations"]


def test_quality_strict_rejects_failed_semantic_chunks(tmp_path: Path) -> None:
    script = _copy_script(tmp_path, "run-graphify-quality-pipeline.sh")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "activate").write_text(
        "# isolated no-op activate\n", encoding="utf-8"
    )
    rag = tmp_path / "scripts" / "update-knowledge-graph-rag.sh"
    rag.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "mkdir -p graphify-out\n"
        "printf '%s\\n' '{\"nodes\":[{\"id\":\"partial\"}],\"edges\":[],\"communities\":[]}' > graphify-out/graph.json\n"
        "touch graphify-out/cypher.txt graphify-out/GRAPH_REPORT.md\n"
        "echo '[graphify] chunk 1/1 failed: synthetic provider failure'\n",
        encoding="utf-8",
    )
    rag.chmod(0o755)
    (tmp_path / "scripts" / "graphify_failure_guard.py").write_text(
        "# isolated no-op guard\n", encoding="utf-8"
    )

    result = _run(script, tmp_path, "--strict", "--min-nodes", "1")

    assert result.returncode == 78
    report = json.loads(
        (tmp_path / "graphify-out" / "quality-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["status"] == "quality_threshold_aborted"
    assert "failed_chunk_count=1>0" in (
        tmp_path / "graphify-out" / "logs" / "pipeline.log"
    ).read_text(encoding="utf-8")


def test_quality_strict_purges_cache_entries_created_by_failed_run(
    tmp_path: Path,
) -> None:
    script = _copy_script(tmp_path, "run-graphify-quality-pipeline.sh")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "activate").write_text(
        "# isolated no-op activate\n", encoding="utf-8"
    )
    cache_dir = tmp_path / "graphify-out" / "cache" / "semantic"
    cache_dir.mkdir(parents=True)
    existing = cache_dir / ("a" * 64 + ".json")
    created_during_failure = cache_dir / ("b" * 64 + ".json")
    existing.write_text("{}\n", encoding="utf-8")
    rag = tmp_path / "scripts" / "update-knowledge-graph-rag.sh"
    rag.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"printf '{{}}\\n' > '{created_during_failure}'\n"
        "echo '[graphify] chunk 2/3 failed: synthetic provider failure'\n",
        encoding="utf-8",
    )
    rag.chmod(0o755)
    (tmp_path / "scripts" / "graphify_failure_guard.py").write_text(
        "# isolated no-op guard\n", encoding="utf-8"
    )

    result = _run(script, tmp_path, "--strict", "--min-nodes", "1")

    assert result.returncode == 78
    assert existing.is_file()
    assert not created_during_failure.exists()
    assert not list((tmp_path / "graphify-out" / "logs").glob(".semantic-cache-baseline.*"))
    report = json.loads(
        (tmp_path / "graphify-out" / "quality-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["purged_failed_run_cache_entries"] == 1


def test_quality_strict_stops_provider_work_when_a_threshold_is_impossible(
    tmp_path: Path,
) -> None:
    script = _copy_script(tmp_path, "run-graphify-quality-pipeline.sh")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "activate").write_text(
        "# isolated no-op activate\n", encoding="utf-8"
    )
    marker = tmp_path / "must-not-finish"
    rag = tmp_path / "scripts" / "update-knowledge-graph-rag.sh"
    rag.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "mkdir -p graphify-out\n"
        "printf '%s\\n' '{\"nodes\":[{\"id\":\"partial\"}],\"edges\":[],\"communities\":[]}' > graphify-out/graph.json\n"
        "echo '[graphify] chunk 1/2 failed: synthetic provider failure'\n"
        "sleep 5\n"
        "touch \"$FAILFAST_MARKER\"\n",
        encoding="utf-8",
    )
    rag.chmod(0o755)
    (tmp_path / "scripts" / "graphify_failure_guard.py").write_text(
        "# isolated no-op guard\n", encoding="utf-8"
    )

    result = _run(
        script,
        tmp_path,
        "--strict",
        "--min-nodes",
        "1",
        env=_clean_env(FAILFAST_MARKER=str(marker)),
    )

    assert result.returncode == 78
    assert not marker.exists()
    report = json.loads(
        (tmp_path / "graphify-out" / "quality-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report == {
        "exit_code": 78,
        "status": "quality_threshold_aborted",
            "finished_at": report["finished_at"],
            "purged_failed_run_cache_entries": 0,
            "purged_invalid_cache_entries": 0,
        "purged_partial_cache_entries": 0,
        "quality_counters": {
            "failed_chunk_count": 1,
            "graph_validation_warning_count": 0,
            "hollow_response_count": 0,
            "invalid_json_count": 0,
            "partial_result_count": 0,
        },
    }


def test_quality_strict_rejects_hollow_semantic_responses(tmp_path: Path) -> None:
    script = _copy_script(tmp_path, "run-graphify-quality-pipeline.sh")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "activate").write_text(
        "# isolated no-op activate\n", encoding="utf-8"
    )
    rag = tmp_path / "scripts" / "update-knowledge-graph-rag.sh"
    rag.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "mkdir -p graphify-out\n"
        "printf '%s\\n' '{\"nodes\":[{\"id\":\"partial\"}],\"edges\":[],\"communities\":[]}' > graphify-out/graph.json\n"
        "touch graphify-out/cypher.txt graphify-out/GRAPH_REPORT.md\n"
        "echo '[graphify] hollow response for synthetic chunk'\n",
        encoding="utf-8",
    )
    rag.chmod(0o755)
    (tmp_path / "scripts" / "graphify_failure_guard.py").write_text(
        "# isolated no-op guard\n", encoding="utf-8"
    )

    result = _run(script, tmp_path, "--strict", "--min-nodes", "1")

    assert result.returncode == 78
    report = json.loads(
        (tmp_path / "graphify-out" / "quality-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["status"] == "quality_threshold_aborted"
    assert "hollow_response_count=1>0" in (
        tmp_path / "graphify-out" / "logs" / "pipeline.log"
    ).read_text(encoding="utf-8")


def test_quality_pipeline_allows_hollow_response_that_graphify_will_bisect(
    tmp_path: Path,
) -> None:
    script = _copy_script(tmp_path, "run-graphify-quality-pipeline.sh")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "activate").write_text(
        "# isolated no-op activate\n", encoding="utf-8"
    )
    rag = tmp_path / "scripts" / "update-knowledge-graph-rag.sh"
    rag.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "mkdir -p graphify-out\n"
        "printf '%s\\n' '{\"nodes\":[{\"id\":\"recovered\"}],\"edges\":[],\"communities\":[]}' > graphify-out/graph.json\n"
        "touch graphify-out/cypher.txt graphify-out/GRAPH_REPORT.md\n"
        "echo '[graphify] openai returned a hollow response (content=no nodes/edges); treating as truncation so adaptive retry can bisect the chunk.'\n"
        "echo '[graphify extract] chunk 1/1 done'\n",
        encoding="utf-8",
    )
    rag.chmod(0o755)
    (tmp_path / "scripts" / "graphify_failure_guard.py").write_text(
        "# isolated no-op guard\n", encoding="utf-8"
    )

    result = _run(script, tmp_path, "--strict", "--min-nodes", "1")

    assert result.returncode == 0, result.stderr
    report = json.loads(
        (tmp_path / "graphify-out" / "quality-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["hollow_response_count"] == 0
    assert report["quality_gate"] == "passed"


def test_quality_pipeline_rejects_and_purges_truncated_partial_cache(
    tmp_path: Path,
) -> None:
    script = _copy_script(tmp_path, "run-graphify-quality-pipeline.sh")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "activate").write_text(
        "# isolated no-op activate\n", encoding="utf-8"
    )
    source = tmp_path / "docs" / "large.md"
    source.parent.mkdir()
    source.write_text("large semantic source\n", encoding="utf-8")
    cache_dir = tmp_path / "graphify-out" / "cache" / "semantic"
    cache_dir.mkdir(parents=True)
    cached = cache_dir / ("a" * 64 + ".json")
    cached.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "partial",
                        "source_file": "docs/large.md",
                    }
                ],
                "edges": [],
                "hyperedges": [],
            }
        ),
        encoding="utf-8",
    )
    rag = tmp_path / "scripts" / "update-knowledge-graph-rag.sh"
    rag.write_text(
        "#!/usr/bin/env bash\n"
        "echo \"[graphify] single-file chunk $PARTIAL_SOURCE truncated at max_completion_tokens — partial result kept\"\n"
        "sleep 5\n",
        encoding="utf-8",
    )
    rag.chmod(0o755)
    (tmp_path / "scripts" / "graphify_failure_guard.py").write_text(
        "# isolated no-op guard\n", encoding="utf-8"
    )

    result = _run(
        script,
        tmp_path,
        "--strict",
        env=_clean_env(PARTIAL_SOURCE=str(source)),
    )

    assert result.returncode == 78
    assert not cached.exists()
    report = json.loads(
        (tmp_path / "graphify-out" / "quality-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["quality_counters"]["partial_result_count"] == 1
    assert report["purged_partial_cache_entries"] == 1


def test_quality_pipeline_rejects_and_purges_invalid_cached_confidence(
    tmp_path: Path,
) -> None:
    script = _copy_script(tmp_path, "run-graphify-quality-pipeline.sh")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "activate").write_text(
        "# isolated no-op activate\n", encoding="utf-8"
    )
    cache_dir = tmp_path / "graphify-out" / "cache" / "semantic"
    cache_dir.mkdir(parents=True)
    cached = cache_dir / ("b" * 64 + ".json")
    cached.write_text(
        json.dumps(
            {
                "nodes": [],
                "edges": [
                    {
                        "source": "a",
                        "target": "b",
                        "confidence": "EXTRACTED|INFERRED",
                    }
                ],
                "hyperedges": [],
            }
        ),
        encoding="utf-8",
    )
    rag = tmp_path / "scripts" / "update-knowledge-graph-rag.sh"
    rag.write_text(
        "#!/usr/bin/env bash\n"
        "echo \"[graphify] Extraction warning (1 issues): invalid confidence\"\n"
        "sleep 5\n",
        encoding="utf-8",
    )
    rag.chmod(0o755)
    (tmp_path / "scripts" / "graphify_failure_guard.py").write_text(
        "# isolated no-op guard\n", encoding="utf-8"
    )

    result = _run(script, tmp_path, "--strict")

    assert result.returncode == 78
    assert not cached.exists()
    report = json.loads(
        (tmp_path / "graphify-out" / "quality-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["quality_counters"]["graph_validation_warning_count"] == 1
    assert report["purged_invalid_cache_entries"] == 1


def test_quality_report_cannot_reuse_a_previous_success_after_pipeline_failure(
    tmp_path: Path,
) -> None:
    script = _copy_script(tmp_path, "run-graphify-quality-pipeline.sh")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "activate").write_text(
        "# isolated no-op activate\n", encoding="utf-8"
    )
    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    report_path = graph_dir / "quality-report.json"
    report_path.write_text(
        '{"status":"passed","node_count":999}\n', encoding="utf-8"
    )
    rag = tmp_path / "scripts" / "update-knowledge-graph-rag.sh"
    rag.write_text("#!/usr/bin/env bash\nexit 42\n", encoding="utf-8")
    rag.chmod(0o755)
    (tmp_path / "scripts" / "graphify_failure_guard.py").write_text(
        "# isolated no-op guard\n", encoding="utf-8"
    )

    result = _run(script, tmp_path)

    assert result.returncode == 42
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "pipeline_failed"
    assert report["exit_code"] == 42
    assert "node_count" not in report


@pytest.mark.parametrize(
    ("model", "provider_env", "expected_provider"),
    [
        (
            "meta/llama-3.3-70b-instruct",
            {"NVIDIA_API_KEY": "synthetic-nvidia-key"},
            "nvidia",
        ),
        (
            "llama-3.3-70b-versatile",
            {
                "OPENAI_API_KEY": "synthetic-groq-key",
                "OPENAI_BASE_URL": "https://api.groq.com/openai/v1",
            },
            "groq",
        ),
    ],
)
def test_quality_pipeline_records_response_reported_tokens_for_resolved_provider(
    tmp_path: Path,
    model: str,
    provider_env: dict[str, str],
    expected_provider: str,
) -> None:
    script = _copy_script(tmp_path, "run-graphify-quality-pipeline.sh")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "activate").write_text(
        "# isolated no-op activate\n", encoding="utf-8"
    )
    rag = tmp_path / "scripts" / "update-knowledge-graph-rag.sh"
    rag.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "mkdir -p graphify-out\n"
        "printf '%s\\n' '{\"nodes\":[{\"id\":\"current\"}],\"edges\":[],\"communities\":[]}' > graphify-out/graph.json\n"
        "touch graphify-out/cypher.txt graphify-out/GRAPH_REPORT.md\n"
        "echo '[graphify extract] tokens: 1,200 in / 34 out, est. cost: synthetic'\n",
        encoding="utf-8",
    )
    rag.chmod(0o755)
    (tmp_path / "scripts" / "graphify_failure_guard.py").write_text(
        "# isolated no-op guard\n", encoding="utf-8"
    )
    ledger_calls = tmp_path / "ledger-calls.txt"
    tracker = tmp_path / "scripts" / "token-tracker.sh"
    tracker.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$LEDGER_CALLS\"\n",
        encoding="utf-8",
    )
    tracker.chmod(0o755)

    result = _run(
        script,
        tmp_path,
        "--backend",
        "openai",
        "--model",
        model,
        env=_clean_env(
            LEDGER_CALLS=str(ledger_calls),
            **provider_env,
        ),
    )

    assert result.returncode == 0, result.stderr
    assert ledger_calls.read_text(encoding="utf-8").strip() == (
        f"log {expected_provider} 1234 {model}"
    )
    report = json.loads(
        (tmp_path / "graphify-out" / "quality-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["input_tokens"] == 1200
    assert report["output_tokens"] == 34
    assert report["token_ledger"] == {
        "provider": expected_provider,
        "status": "recorded",
        "total_tokens": 1234,
    }


@pytest.mark.parametrize(
    "name",
    [
        "install-knowledge-stack.sh",
        "neo4j-backup.sh",
        "neo4j-import.sh",
        "neo4j-rag-query.sh",
        "update-knowledge-graph-rag.sh",
    ],
)
def test_help_is_successful(name: str, tmp_path: Path) -> None:
    script = _copy_script(tmp_path, name)
    if name == "update-knowledge-graph-rag.sh":
        venv_bin = tmp_path / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        (venv_bin / "activate").write_text("# isolated no-op activate\n", encoding="utf-8")

    result = _run(script, tmp_path, "--help")

    assert result.returncode == 0, result.stderr
    assert "Usage:" in result.stderr


def test_neo4j_query_uses_label_parameter_and_read_only_timeout(tmp_path: Path) -> None:
    script = _copy_script(tmp_path, "neo4j-rag-query.sh")
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    args_path = tmp_path / "cypher-args.txt"
    query_path = tmp_path / "cypher-query.txt"
    cypher_shell = fake_bin / "cypher-shell"
    cypher_shell.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$@\" > \"$CYPHER_ARGS\"\n"
        "cat > \"$CYPHER_QUERY\"\n",
        encoding="utf-8",
    )
    cypher_shell.chmod(0o755)
    attack = "x') MATCH (n) DETACH DELETE n //"
    env = _clean_env(
        PATH=f"{fake_bin}:{os.environ.get('PATH', '')}",
        NEO4J_PASSWORD="synthetic-test-password",
        CYPHER_ARGS=str(args_path),
        CYPHER_QUERY=str(query_path),
    )

    result = _run(script, tmp_path, attack, env=env)

    assert result.returncode == 0, result.stderr
    query = query_path.read_text(encoding="utf-8")
    arguments = args_path.read_text(encoding="utf-8")
    assert "n.label" in query
    assert "$pattern" in query
    assert attack not in query
    assert "--access-mode\nread" in arguments
    assert "--transaction-timeout\n10s" in arguments
    assert "-P\n" in arguments


def test_neo4j_import_wrapper_uses_atomic_json_importer(tmp_path: Path) -> None:
    script = _copy_script(tmp_path, "neo4j-import.sh")
    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    (graph_dir / "graph.json").write_text(
        '{"directed": true, "multigraph": false, "nodes": [], "links": []}\n',
        encoding="utf-8",
    )
    (tmp_path / "scripts" / "neo4j-import-batch.py").write_text(
        "# isolated fixture\n",
        encoding="utf-8",
    )
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    args_path = tmp_path / "python-args.txt"
    python = venv_bin / "python"
    python.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$@\" > \"$PYTHON_ARGS\"\n",
        encoding="utf-8",
    )
    python.chmod(0o755)

    result = _run(
        script,
        tmp_path,
        env=_clean_env(
            NEO4J_PASSWORD="synthetic-test-password",
            PYTHON_ARGS=str(args_path),
        ),
    )

    assert result.returncode == 0, result.stderr
    arguments = args_path.read_text(encoding="utf-8").splitlines()
    assert arguments == [
        "scripts/neo4j-import-batch.py",
        "graphify-out/graph.json",
        "--replace",
    ]


def test_neo4j_bootstrap_binds_loopback_without_exposing_password(tmp_path: Path) -> None:
    script = _copy_script(tmp_path, "install-knowledge-stack.sh")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "activate").write_text("# isolated no-op activate\n", encoding="utf-8")
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    docker_calls = tmp_path / "docker-calls.txt"
    docker = fake_bin / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$@\" >> \"$DOCKER_CALLS\"\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    password = "synthetic-secret-that-must-not-be-printed"

    result = _run(
        script,
        tmp_path,
        "--start-neo4j",
        env=_clean_env(
            PATH=f"{fake_bin}:{os.environ.get('PATH', '')}",
            DOCKER_CALLS=str(docker_calls),
            NEO4J_PASSWORD=password,
        ),
    )

    assert result.returncode == 0, result.stderr
    calls = docker_calls.read_text(encoding="utf-8")
    assert "127.0.0.1:7474:7474" in calls
    assert "127.0.0.1:7687:7687" in calls
    assert password not in calls
    assert password not in result.stdout
    assert password not in result.stderr


def test_neo4j_operator_sources_have_no_default_password() -> None:
    for name in (
        "install-knowledge-stack.sh",
        "neo4j-backup.sh",
        "neo4j-interactive.py",
    ):
        text = (SCRIPTS / name).read_text(encoding="utf-8")
        assert "atlasneo4j" not in text, f"default Neo4j password in {name}"


def test_neo4j_backup_is_fail_closed_and_restarts_running_container() -> None:
    text = (SCRIPTS / "neo4j-backup.sh").read_text(encoding="utf-8")
    assert "set -euo pipefail" in text
    assert "--to-stdout" in text
    assert "trap " in text
    assert "docker stop" in text
    assert "docker start" in text
    assert "Backup may not have completed" not in text
    assert "Could not copy backup" not in text


def test_hook_installer_honours_configured_hooks_path(tmp_path: Path) -> None:
    script = _copy_script(tmp_path, "install-knowledge-hooks.sh")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "core.hooksPath", ".githooks"],
        cwd=tmp_path,
        check=True,
    )
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "graphify").symlink_to(REPO_ROOT / ".venv" / "bin" / "graphify")

    result = _run(script, tmp_path)

    assert result.returncode == 0, result.stderr
    post_commit = tmp_path / ".githooks" / "post-commit"
    post_checkout = tmp_path / ".githooks" / "post-checkout"
    assert post_commit.is_file()
    assert post_checkout.is_file()
    assert "# graphify-hook-start" in post_commit.read_text(encoding="utf-8")
    assert "# graphify-checkout-hook-start" in post_checkout.read_text(encoding="utf-8")


def test_hook_installer_help_has_no_side_effects(tmp_path: Path) -> None:
    script = _copy_script(tmp_path, "install-knowledge-hooks.sh")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    calls = tmp_path / "graphify-calls.txt"
    graphify = venv_bin / "graphify"
    graphify.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$GRAPHIFY_CALLS\"\n"
        "if [ \"${1:-}\" = '--version' ]; then printf 'graphify 0.9.11\\n'; fi\n",
        encoding="utf-8",
    )
    graphify.chmod(0o755)

    result = _run(
        script,
        tmp_path,
        "--help",
        env=_clean_env(GRAPHIFY_CALLS=str(calls)),
    )

    assert result.returncode == 0, result.stderr
    assert "Usage:" in result.stderr
    assert not calls.exists()
    assert not (tmp_path / ".githooks").exists()


def _load_batch_import_module() -> ModuleType:
    path = SCRIPTS / "neo4j-import-batch.py"
    spec = importlib.util.spec_from_file_location("neo4j_import_batch", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sample_graph_export() -> dict[str, object]:
    return {
        # Graphify 0.9.11 exports a NetworkX graph with this flag false while
        # still preserving source/target order for every relationship.
        "directed": False,
        "multigraph": False,
        "nodes": [
            {
                "id": "one",
                "label": "contains;a;semicolon",
                "file_type": "code",
                "metadata": {"not_a_neo4j_scalar": True},
                "_origin": "ast",
            },
            {"id": "two", "label": "Two", "file_type": "concept"},
        ],
        "links": [
            {
                "source": "one",
                "target": "two",
                "relation": "calls",
                "confidence": "EXTRACTED",
            }
        ],
    }


class _FakeResult:
    def __init__(self, record: dict[str, int] | None = None) -> None:
        self.record = record

    def consume(self) -> None:
        return None

    def single(self, *, strict: bool = False) -> dict[str, int]:
        assert strict
        assert self.record is not None
        return self.record


class _RecordingTransaction:
    def __init__(self, counts: tuple[int, int] = (2, 1)) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.counts = counts

    def run(self, query: str, **parameters: object) -> _FakeResult:
        self.calls.append((query, parameters))
        if "RETURN count(n) AS nodes" in query:
            return _FakeResult(
                {"nodes": self.counts[0], "relationships": self.counts[1]}
            )
        return _FakeResult()


class _RecordingSession:
    def __init__(self, transaction: _RecordingTransaction) -> None:
        self.transaction = transaction

    def __enter__(self) -> _RecordingSession:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute_write(self, callback: object, *args: object) -> object:
        return callback(self.transaction, *args)


class _RecordingDriver:
    def __init__(self, counts: tuple[int, int] = (2, 1)) -> None:
        self.transaction = _RecordingTransaction(counts)

    def session(self) -> _RecordingSession:
        return _RecordingSession(self.transaction)


def test_graph_import_uses_parameterized_unwind_batches() -> None:
    module = _load_batch_import_module()
    driver = _RecordingDriver()
    graph = _sample_graph_export()

    actual = module.import_graph(driver, graph, replace=True, batch_size=100)

    assert actual == (2, 1)
    calls = driver.transaction.calls
    assert any("MATCH (n) DETACH DELETE n" in query for query, _ in calls)
    data_calls = [(query, params) for query, params in calls if "UNWIND $rows" in query]
    assert len(data_calls) == 3
    all_queries = "\n".join(query for query, _ in data_calls)
    assert "GraphifyNode:Code" in all_queries
    assert "GraphifyNode:Concept" in all_queries
    assert "[r:CALLS]" in all_queries
    assert "contains;a;semicolon" not in all_queries
    assert any(
        row["props"]["label"] == "contains;a;semicolon"
        for _, params in data_calls
        for row in params["rows"]
        if "props" in row
    )
    verification_queries = [
        query for query, _ in calls if "RETURN count(n) AS nodes" in query
    ]
    assert verification_queries
    assert all("CALL () {" in query for query in verification_queries)


def test_graph_import_rejects_unsafe_identifiers() -> None:
    module = _load_batch_import_module()
    graph = _sample_graph_export()
    graph["links"][0]["relation"] = "CALLS`) DETACH DELETE n"

    with pytest.raises(ValueError, match="unsafe relationship type"):
        module.import_graph(_RecordingDriver(), graph, replace=True, batch_size=100)


def test_batch_import_requires_explicit_password(tmp_path: Path) -> None:
    graph = tmp_path / "graph.json"
    graph.write_text('{"nodes": [], "links": []}\n', encoding="utf-8")
    env = _clean_env(NEO4J_URI="bolt://127.0.0.1:1")
    env.pop("NEO4J_PASSWORD", None)

    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "neo4j-import-batch.py"), str(graph)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 2
    assert "NEO4J_PASSWORD is required" in result.stderr


def test_graph_import_rolls_back_on_count_mismatch() -> None:
    module = _load_batch_import_module()

    with pytest.raises(RuntimeError, match="does not match"):
        module.import_graph(
            _RecordingDriver(counts=(1, 0)),
            _sample_graph_export(),
            replace=True,
            batch_size=100,
        )


def test_operator_scripts_do_not_embed_the_local_neo4j_password() -> None:
    for name in ("health-check.sh", "neo4j-import-batch.py"):
        text = (SCRIPTS / name).read_text(encoding="utf-8")
        assert "atlasneo4j" not in text, f"hard-coded Neo4j password in {name}"


def test_redteam_tools_are_declared_as_conflicting_isolated_extras() -> None:
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = config["project"]["optional-dependencies"]

    assert "redteam" not in extras
    assert extras["redteam-garak"] == [
        "garak>=0.15,<0.16",
        "torch>=2.6",
    ]
    assert extras["redteam-pyrit"] == ["pyrit>=0.14,<0.15"]
    assert [
        {"extra": "redteam-garak"},
        {"extra": "redteam-pyrit"},
    ] in config["tool"]["uv"]["conflicts"]
    assert config["tool"]["uv"]["sources"]["torch"] == [
        {"index": "torch-cpu", "extra": "redteam-garak"}
    ]
    assert {
        "name": "torch-cpu",
        "url": "https://download.pytorch.org/whl/cpu",
        "explicit": True,
    } in config["tool"]["uv"]["index"]
