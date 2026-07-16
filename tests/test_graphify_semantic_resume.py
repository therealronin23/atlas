"""Unit contract for resumable, per-source Graphify semantic checkpoints.

These tests deliberately inject every side effect.  They never invoke a model,
read live credentials, or write Graphify's real cache.
"""

from __future__ import annotations

import importlib.util
import builtins
import os
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "graphify_semantic_resume.py"


def _module() -> ModuleType:
    assert SCRIPT_PATH.is_file(), (
        "missing resumable Graphify implementation: "
        "scripts/graphify_semantic_resume.py"
    )
    spec = importlib.util.spec_from_file_location(
        "graphify_semantic_resume_under_test", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _payload(source: str, *, input_tokens: int = 11, output_tokens: int = 7) -> dict[str, Any]:
    stem = Path(source).stem
    return {
        "nodes": [
            {
                "id": f"{stem}_node",
                "label": stem,
                "file_type": "document",
                "source_file": source,
            }
        ],
        "edges": [],
        "hyperedges": [],
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "failed_chunks": 0,
        "finish_reason": "stop",
    }


def _source_files(tmp_path: Path, *names: str) -> list[Path]:
    files: list[Path] = []
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {path.stem}\n", encoding="utf-8")
        files.append(path)
    return files


def test_successful_file_checkpoints_survive_failure_and_rerun_only_retries_miss(
    tmp_path: Path,
) -> None:
    m = _module()
    sources = _source_files(tmp_path, "docs/a.md", "docs/b.md", "docs/c.md")
    cached: dict[str, dict[str, Any]] = {}
    first_calls: list[str] = []

    def is_cached(path: Path) -> bool:
        return path.relative_to(tmp_path).as_posix() in cached

    def checkpoint(path: Path, payload: dict[str, Any]) -> None:
        cached[path.relative_to(tmp_path).as_posix()] = payload

    def first_extract(
        path: Path, on_chunk_done: Callable[[int, int, dict[str, Any]], None]
    ) -> Any:
        relative = path.relative_to(tmp_path).as_posix()
        first_calls.append(relative)
        if relative == "docs/b.md":
            raise m.TransientProviderError("HTTP 504")
        payload = _payload(relative)
        on_chunk_done(1, 1, payload)
        return m.ExtractionAttempt(payload=payload, diagnostics="")

    first = m.resume_sources(
        sources,
        root=tmp_path,
        provider="nvidia",
        model="test-model",
        is_cached=is_cached,
        extract_one=first_extract,
        checkpoint=checkpoint,
        log_tokens=lambda _provider, _tokens, _model: None,
    )

    assert first_calls == ["docs/a.md", "docs/b.md", "docs/c.md"]
    assert first.completed == ("docs/a.md", "docs/c.md")
    assert first.failed == ("docs/b.md",)
    assert set(cached) == {"docs/a.md", "docs/c.md"}

    retry_calls: list[str] = []

    def retry_extract(
        path: Path, on_chunk_done: Callable[[int, int, dict[str, Any]], None]
    ) -> Any:
        relative = path.relative_to(tmp_path).as_posix()
        retry_calls.append(relative)
        payload = _payload(relative)
        on_chunk_done(1, 1, payload)
        return m.ExtractionAttempt(payload=payload, diagnostics="")

    retry = m.resume_sources(
        sources,
        root=tmp_path,
        provider="nvidia",
        model="test-model",
        is_cached=is_cached,
        extract_one=retry_extract,
        checkpoint=checkpoint,
        log_tokens=lambda _provider, _tokens, _model: None,
    )

    assert retry_calls == ["docs/b.md"]
    assert retry.completed == ("docs/b.md",)
    assert retry.cached == ("docs/a.md", "docs/c.md")
    assert retry.failed == ()
    assert set(cached) == {"docs/a.md", "docs/b.md", "docs/c.md"}


def test_injected_resume_loop_does_not_require_graphify_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    m = _module()
    source = _source_files(tmp_path, "docs/a.md")[0]
    real_import = builtins.__import__

    def blocked_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "graphify" or name.startswith("graphify."):
            raise ModuleNotFoundError("graphify intentionally absent", name=name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    report = m.resume_sources(
        [source],
        root=tmp_path,
        provider="unattributed",
        model="test-model",
        is_cached=lambda _source: False,
        extract_one=lambda _path, callback: (
            callback(1, 1, _payload("docs/a.md"))
            or m.ExtractionAttempt(_payload("docs/a.md"))
        ),
        checkpoint=lambda _source, _payload: None,
        log_tokens=lambda _provider, _tokens, _model: None,
    )

    assert report.complete is True


def test_filter_exact_source_drops_foreign_records_but_keeps_cross_file_links(
    tmp_path: Path,
) -> None:
    m = _module()
    source = _source_files(tmp_path, "docs/a.md")[0]
    payload = {
        "nodes": [
            {"id": "local_1", "source_file": "docs/a.md"},
            {"id": "local_2", "source_file": "docs/a.md"},
            {"id": "foreign", "source_file": "docs/b.md"},
        ],
        "edges": [
            {
                "source": "local_1",
                "target": "local_2",
                "source_file": "docs/a.md",
            },
            {
                "source": "local_1",
                "target": "foreign",
                "source_file": "docs/a.md",
            },
            {
                "source": "local_1",
                "target": "local_2",
                "source_file": "docs/b.md",
            },
        ],
        "hyperedges": [
            {
                "id": "kept_hyperedge",
                "nodes": ["local_1", "local_2"],
                "source_file": "docs/a.md",
            },
            {
                "id": "dangling_hyperedge",
                "nodes": ["local_1", "foreign"],
                "source_file": "docs/a.md",
            },
        ],
        "input_tokens": 9,
        "output_tokens": 4,
        "failed_chunks": 0,
        "finish_reason": "stop",
    }

    filtered = m.filter_exact_source(payload, source=source, root=tmp_path)

    assert [node["id"] for node in filtered["nodes"]] == ["local_1", "local_2"]
    assert len(filtered["edges"]) == 2
    assert filtered["edges"][0]["source"] == "local_1"
    assert filtered["edges"][0]["target"] == "local_2"
    assert [edge["id"] for edge in filtered["hyperedges"]] == [
        "kept_hyperedge",
        "dangling_hyperedge",
    ]
    assert filtered["input_tokens"] == 9
    assert filtered["output_tokens"] == 4


@pytest.mark.parametrize(
    "diagnostics",
    [
        (
            "[graphify] single-file chunk docs/a.md truncated at "
            "max_completion_tokens — partial result kept"
        ),
        "[graphify] LLM returned invalid JSON, skipping chunk docs/a.md",
    ],
)
def test_partial_or_invalid_diagnostics_are_not_checkpointed(
    tmp_path: Path, diagnostics: str
) -> None:
    m = _module()
    source = _source_files(tmp_path, "docs/a.md")[0]
    checkpoints: list[str] = []

    def extract(
        path: Path, on_chunk_done: Callable[[int, int, dict[str, Any]], None]
    ) -> Any:
        payload = _payload("docs/a.md")
        on_chunk_done(1, 1, payload)
        return m.ExtractionAttempt(payload=payload, diagnostics=diagnostics)

    report = m.resume_sources(
        [source],
        root=tmp_path,
        provider="nvidia",
        model="test-model",
        is_cached=lambda _path: False,
        extract_one=extract,
        checkpoint=lambda path, _payload: checkpoints.append(path.name),
        log_tokens=lambda _provider, _tokens, _model: None,
    )

    assert checkpoints == []
    assert report.completed == ()
    assert report.failed == ("docs/a.md",)
    assert report.fatal_error is None


def test_fatal_provider_error_stops_subsequent_calls(tmp_path: Path) -> None:
    m = _module()
    sources = _source_files(tmp_path, "docs/a.md", "docs/b.md", "docs/c.md")
    calls: list[str] = []

    def extract(
        path: Path, _on_chunk_done: Callable[[int, int, dict[str, Any]], None]
    ) -> Any:
        relative = path.relative_to(tmp_path).as_posix()
        calls.append(relative)
        raise m.FatalProviderError("daily quota exhausted", status_code=429)

    report = m.resume_sources(
        sources,
        root=tmp_path,
        provider="gemini",
        model="test-model",
        is_cached=lambda _path: False,
        extract_one=extract,
        checkpoint=lambda _path, _payload: pytest.fail("must not checkpoint"),
        log_tokens=lambda _provider, _tokens, _model: None,
    )

    assert calls == ["docs/a.md"]
    assert report.completed == ()
    assert report.failed == ("docs/a.md",)
    assert report.fatal_error is not None
    assert "429" in report.fatal_error


def test_chunk_callback_logs_actual_tokens_per_file_even_if_later_file_fails(
    tmp_path: Path,
) -> None:
    m = _module()
    sources = _source_files(tmp_path, "docs/a.md", "docs/b.md")
    logged: list[tuple[str, int, str]] = []

    def extract(
        path: Path, on_chunk_done: Callable[[int, int, dict[str, Any]], None]
    ) -> Any:
        relative = path.relative_to(tmp_path).as_posix()
        if relative == "docs/a.md":
            payload = _payload(relative, input_tokens=13, output_tokens=5)
            on_chunk_done(1, 1, payload)
            return m.ExtractionAttempt(payload=payload, diagnostics="")
        payload = _payload(relative, input_tokens=3, output_tokens=2)
        on_chunk_done(1, 1, payload)
        raise m.TransientProviderError("HTTP 504 after usage was reported")

    report = m.resume_sources(
        sources,
        root=tmp_path,
        provider="nvidia",
        model="meta/test-model",
        is_cached=lambda _path: False,
        extract_one=extract,
        checkpoint=lambda _path, _payload: None,
        log_tokens=lambda provider, tokens, model: logged.append(
            (provider, tokens, model)
        ),
    )

    assert logged == [
        ("nvidia", 18, "meta/test-model"),
        ("nvidia", 5, "meta/test-model"),
    ]
    assert report.completed == ("docs/a.md",)
    assert report.failed == ("docs/b.md",)


def test_cached_payload_must_be_nonempty_valid_and_exact_source(
    tmp_path: Path,
) -> None:
    m = _module()
    source = _source_files(tmp_path, "docs/a.md")[0]

    assert not m.is_verified_cache_payload({}, source=source, root=tmp_path)
    assert not m.is_verified_cache_payload(
        _payload("docs/other.md"), source=source, root=tmp_path
    )
    assert m.is_verified_cache_payload(
        _payload("docs/a.md"), source=source, root=tmp_path
    )


def test_cached_payload_accepts_valid_local_projection_with_cross_file_links(
    tmp_path: Path,
) -> None:
    m = _module()
    source = _source_files(tmp_path, "docs/a.md")[0]
    payload = _payload("docs/a.md")
    payload["nodes"].append(
        {
            "id": "foreign_node",
            "label": "foreign",
            "file_type": "document",
            "source_file": "docs/b.md",
        }
    )
    payload["edges"].append(
        {
            "source": "a_node",
            "target": "foreign_node",
            "relation": "references",
            "confidence": "EXTRACTED",
            "source_file": "docs/a.md",
        }
    )

    assert m.is_verified_cache_payload(payload, source=source, root=tmp_path)


def test_cached_payload_can_be_hyperedge_only_when_source_is_exact(
    tmp_path: Path,
) -> None:
    m = _module()
    source = _source_files(tmp_path, "docs/a.md")[0]
    payload = {
        "nodes": [],
        "edges": [],
        "hyperedges": [
            {
                "id": "cross_file_group",
                "label": "Cross-file group",
                "nodes": ["external_a", "external_b"],
                "relation": "participate_in",
                "confidence": "EXTRACTED",
                "source_file": "docs/a.md",
            }
        ],
    }

    assert m.is_verified_cache_payload(payload, source=source, root=tmp_path)


def test_cache_path_rejects_symlink_before_checkpointing(tmp_path: Path) -> None:
    m = _module()
    outside = tmp_path / "outside"
    outside.mkdir()
    graphify_out = tmp_path / "graphify-out"
    graphify_out.symlink_to(outside, target_is_directory=True)

    with pytest.raises(OSError, match="unsafe semantic cache path"):
        m.ensure_safe_cache_path(tmp_path)


def test_any_fatal_status_stops_even_after_an_earlier_transient() -> None:
    m = _module()

    fatal, reason = m._safe_failure_reason(
        "slice one failed HTTP 504; slice two failed HTTP 429"
    )

    assert fatal is True
    assert "429" in reason


def test_missing_api_key_is_fatal() -> None:
    m = _module()

    fatal, reason = m._safe_failure_reason("No API key configured for backend")

    assert fatal is True
    assert "credential" in reason


def test_semantic_source_discovery_includes_images(
    tmp_path: Path,
) -> None:
    m = _module()
    image = _source_files(tmp_path, "docs/diagram.png")[0]
    detector = lambda _root: {
            "files": {
                "document": [],
                "paper": [],
                "image": [str(image)],
            }
        }

    assert m._semantic_sources(tmp_path, detect_fn=detector) == [image]


def test_report_write_does_not_follow_predictable_temporary_symlink(
    tmp_path: Path,
) -> None:
    m = _module()
    report = tmp_path / "report.json"
    outside = tmp_path / "outside.json"
    outside.write_text("sentinel\n", encoding="utf-8")
    predictable = report.with_name(f".{report.name}.{os.getpid()}.tmp")
    predictable.symlink_to(outside)

    m._write_report(report, {"status": "ok"})

    assert outside.read_text(encoding="utf-8") == "sentinel\n"
    assert report.is_file()
    assert not report.is_symlink()


def test_token_logging_failure_is_checkpointed_as_unrecorded_and_incomplete(
    tmp_path: Path,
) -> None:
    m = _module()
    source = _source_files(tmp_path, "docs/a.md")[0]
    checkpoints: list[dict[str, Any]] = []

    def extract(
        _path: Path, on_chunk_done: Callable[[int, int, dict[str, Any]], None]
    ) -> Any:
        payload = _payload("docs/a.md", input_tokens=9, output_tokens=3)
        on_chunk_done(1, 1, payload)
        return m.ExtractionAttempt(payload=payload, diagnostics="")

    report = m.resume_sources(
        [source],
        root=tmp_path,
        provider="nvidia",
        model="test-model",
        is_cached=lambda _path: False,
        extract_one=extract,
        checkpoint=lambda _path, payload: checkpoints.append(payload),
        log_tokens=lambda _provider, _tokens, _model: (_ for _ in ()).throw(
            RuntimeError("ledger unavailable")
        ),
    )

    assert report.completed == ("docs/a.md",)
    assert report.complete is False
    assert report.token_logging_failures == ("docs/a.md",)
    assert checkpoints[0]["_atlas_usage"] == {"unrecorded_tokens": 12}
