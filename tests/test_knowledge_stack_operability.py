"""Regression tests for the local Graphify/Neo4j operator path.

These tests run copied shell scripts in an isolated temporary repository.  They
must never source the real ``.env`` or contact the live Neo4j instance.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"


def _clean_env(**overrides: str) -> dict[str, str]:
    env = {"PATH": os.environ.get("PATH", "")}
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


def _prepare_fake_graphify_repo(tmp_path: Path, script_name: str) -> tuple[Path, Path]:
    script = _copy_script(tmp_path, script_name)
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "activate").write_text("# isolated no-op activate\n", encoding="utf-8")
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "graph.json").write_text("{}\n", encoding="utf-8")

    calls = tmp_path / "graphify-calls.txt"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    graphify = fake_bin / "graphify"
    graphify.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s|%s\\n' \"${PYTHONHASHSEED:-}\" \"$*\" >> \"$GRAPHIFY_CALLS\"\n"
        "if [ \"${1:-}\" = '--version' ]; then printf 'graphify 0.9.11\\n'; fi\n",
        encoding="utf-8",
    )
    graphify.chmod(0o755)
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
