#!/usr/bin/env python3
"""Build verified, resumable Graphify semantic checkpoints one source at a time.

Graphify 0.9.11 checkpoints top-level chunks with ``merge_existing=True``.
That is useful for throughput, but a later provider failure can leave a partial
whole-file cache entry and can even mutate another file's existing cache.  This
adapter disables that incremental writer, extracts one complete source at a
time, validates the exact-source fragment, and only then performs one atomic
content-addressed cache write.

The module keeps its core loop dependency-injected so the failure and resume
semantics can be tested without credentials or network access.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


_FATAL_HTTP_STATUSES = frozenset({401, 402, 403, 404, 422, 429})
_HTTP_STATUS_RE = re.compile(r"(?<!\d)(401|402|403|404|408|409|413|422|425|429|500|502|503|504|529)(?!\d)")
_INCOMPLETE_MARKERS = (
    "partial result kept",
    "invalid JSON",
    "still overflows context",
    "cannot be split further",
)
_MAX_DIAGNOSTIC_CHARS = 64 * 1024


@dataclass(frozen=True)
class ExtractionAttempt:
    payload: dict[str, Any]
    diagnostics: str = ""


class TransientProviderError(RuntimeError):
    """A source failed, but other independent sources may still succeed."""


class FatalProviderError(RuntimeError):
    """The provider cannot usefully serve another source in this run."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        safe_message = message.strip() or "provider request cannot continue"
        if status_code is not None and str(status_code) not in safe_message:
            safe_message = f"HTTP {status_code}: {safe_message}"
        super().__init__(safe_message)


class IncompleteExtractionError(RuntimeError):
    """The extraction did not prove complete enough to checkpoint."""


@dataclass(frozen=True)
class ResumeReport:
    completed: tuple[str, ...]
    cached: tuple[str, ...]
    failed: tuple[str, ...]
    fatal_error: str | None = None
    token_logging_failures: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return (
            not self.failed
            and self.fatal_error is None
            and not self.token_logging_failures
        )


class _BoundedTextCapture(io.TextIOBase):
    """Capture provider diagnostics without retaining unbounded response bodies."""

    def __init__(self, limit: int = _MAX_DIAGNOSTIC_CHARS) -> None:
        self._limit = limit
        self._parts: list[str] = []
        self._size = 0

    def writable(self) -> bool:
        return True

    def write(self, value: str) -> int:
        available = max(0, self._limit - self._size)
        if available:
            kept = value[:available]
            self._parts.append(kept)
            self._size += len(kept)
        return len(value)

    def getvalue(self) -> str:
        return "".join(self._parts)


def _relative_source(source: Path, root: Path) -> str:
    resolved_root = root.resolve()
    resolved = source.resolve()
    try:
        return resolved.relative_to(resolved_root).as_posix()
    except ValueError as exc:
        raise ValueError("semantic source escaped repository root") from exc


def _item_matches_source(item: object, *, source: Path, root: Path) -> bool:
    if not isinstance(item, dict):
        return False
    raw = item.get("source_file")
    if not isinstance(raw, str) or not raw:
        return False
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        return candidate.resolve() == source.resolve()
    except OSError:
        return False


def filter_exact_source(
    payload: dict[str, Any], *, source: Path, root: Path
) -> dict[str, Any]:
    """Remove cross-file output and references to nodes that were removed."""

    nodes = [
        item
        for item in (payload.get("nodes") or [])
        if _item_matches_source(item, source=source, root=root)
    ]
    edges = [
        item
        for item in (payload.get("edges") or [])
        if _item_matches_source(item, source=source, root=root)
        and isinstance(item, dict)
    ]

    hyperedges = [
        item
        for item in (payload.get("hyperedges") or [])
        if _item_matches_source(item, source=source, root=root)
        and isinstance(item, dict)
    ]

    filtered: dict[str, Any] = {
        "nodes": nodes,
        "edges": edges,
        "hyperedges": hyperedges,
    }
    for key in (
        "input_tokens",
        "output_tokens",
        "failed_chunks",
        "finish_reason",
        "model",
    ):
        if key in payload:
            filtered[key] = payload[key]
    return filtered


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_statuses(diagnostics: str) -> tuple[int, ...]:
    return tuple(int(match.group(1)) for match in _HTTP_STATUS_RE.finditer(diagnostics))


def _safe_failure_reason(diagnostics: str) -> tuple[bool, str]:
    statuses = _safe_statuses(diagnostics)
    lower = diagnostics.casefold()
    fatal_keyword = any(
        marker in lower
        for marker in (
            "quota exhausted",
            "insufficient credit",
            "insufficient balance",
            "invalid api key",
            "invalid_api_key",
            "no api key",
            "missing api key",
            "api key not configured",
            "authentication failed",
            "model_not_found",
            "unsupported model",
        )
    )
    fatal_status = next(
        (status for status in statuses if status in _FATAL_HTTP_STATUSES), None
    )
    fatal = fatal_status is not None or fatal_keyword
    if fatal_status is not None:
        return True, f"provider request failed (HTTP {fatal_status})"
    if statuses:
        return fatal, f"provider request failed (HTTP {statuses[0]})"
    if fatal_keyword:
        return True, "provider credentials, quota, billing, or model rejected"
    return False, "provider request failed"


def _validate_checkpoint_payload(payload: dict[str, Any]) -> None:
    if not any(payload.get(key) for key in ("nodes", "edges", "hyperedges")):
        raise IncompleteExtractionError("extraction returned no exact-source records")
    try:
        from graphify.semantic_cleanup import validate_semantic_fragment
        from graphify.validate import validate_extraction
    except ModuleNotFoundError as exc:
        if exc.name != "graphify" and not (exc.name or "").startswith("graphify."):
            raise
        # The dependency-injected loop is intentionally unit-testable without
        # the optional operator stack. Runtime extraction imports Graphify
        # separately, so this fallback cannot mask an incomplete live install.
        errors = []
        for key in ("nodes", "edges", "hyperedges"):
            records = payload.get(key, [])
            if not isinstance(records, list) or not all(
                isinstance(record, dict) for record in records
            ):
                errors.append(f"{key} must be a list of objects")
    else:
        errors = [
            error
            for error in validate_extraction(payload)
            # Semantic relations may intentionally target an entity defined by a
            # different source/cache entry. Their own source_file is still exact;
            # full-corpus validation resolves those endpoints after cache merge.
            if "does not match any node id" not in error
        ]
        errors.extend(validate_semantic_fragment(payload))
    if errors:
        raise IncompleteExtractionError(
            f"semantic fragment validation failed ({len(errors)} error(s))"
        )


def is_verified_cache_payload(
    payload: object, *, source: Path, root: Path
) -> bool:
    """Return true only for a non-empty, valid cache entry for this source."""

    if not isinstance(payload, dict):
        return False
    filtered = filter_exact_source(payload, source=source, root=root)
    try:
        _validate_checkpoint_payload(filtered)
    except IncompleteExtractionError:
        return False
    return True


def ensure_safe_cache_path(root: Path) -> Path:
    """Create the semantic cache only through real directories under root."""

    root = root.resolve()
    current = root
    for component in ("graphify-out", "cache", "semantic"):
        current = current / component
        if os.path.lexists(current):
            if current.is_symlink() or not current.is_dir():
                raise OSError("unsafe semantic cache path")
            continue
        current.mkdir(mode=0o700)
        if current.is_symlink() or not current.is_dir():
            raise OSError("unsafe semantic cache path")
    return current


def resume_sources(
    sources: Iterable[Path],
    *,
    root: Path,
    provider: str,
    model: str,
    is_cached: Callable[[Path], bool],
    extract_one: Callable[
        [Path, Callable[[int, int, dict[str, Any]], None]], ExtractionAttempt
    ],
    checkpoint: Callable[[Path, dict[str, Any]], None],
    log_tokens: Callable[[str, int, str], None],
) -> ResumeReport:
    """Resume independent sources and never discard a prior verified result."""

    root = root.resolve()
    completed: list[str] = []
    cached: list[str] = []
    failed: list[str] = []
    token_logging_failures: list[str] = []
    fatal_error: str | None = None

    for source in sources:
        source = source.resolve()
        relative = _relative_source(source, root)
        if is_cached(source):
            cached.append(relative)
            continue
        if source.is_symlink() or not source.is_file():
            failed.append(relative)
            continue

        before = _file_digest(source)
        observed_chunks: set[tuple[int, int]] = set()
        incomplete_chunk = False
        unrecorded_tokens = 0

        def on_chunk_done(index: int, total: int, result: dict[str, Any]) -> None:
            nonlocal incomplete_chunk, unrecorded_tokens
            identity = (index, total)
            if identity in observed_chunks:
                return
            observed_chunks.add(identity)
            input_tokens = result.get("input_tokens", 0)
            output_tokens = result.get("output_tokens", 0)
            if (
                isinstance(input_tokens, int)
                and not isinstance(input_tokens, bool)
                and input_tokens >= 0
                and isinstance(output_tokens, int)
                and not isinstance(output_tokens, bool)
                and output_tokens >= 0
            ):
                total_tokens = input_tokens + output_tokens
                if total_tokens:
                    try:
                        log_tokens(provider, total_tokens, model)
                    except Exception:
                        unrecorded_tokens += total_tokens
                        if relative not in token_logging_failures:
                            token_logging_failures.append(relative)
            else:
                incomplete_chunk = True
            if result.get("finish_reason", "stop") != "stop":
                incomplete_chunk = True

        try:
            attempt = extract_one(source, on_chunk_done)
        except FatalProviderError as exc:
            failed.append(relative)
            fatal_error = str(exc)
            break
        except (TransientProviderError, OSError, RuntimeError):
            failed.append(relative)
            continue

        if not isinstance(attempt, ExtractionAttempt):
            failed.append(relative)
            continue
        diagnostics = attempt.diagnostics
        if any(marker in diagnostics for marker in _INCOMPLETE_MARKERS):
            failed.append(relative)
            continue
        payload = attempt.payload
        if not isinstance(payload, dict) or payload.get("failed_chunks", 0):
            fatal, reason = _safe_failure_reason(diagnostics)
            failed.append(relative)
            if fatal:
                fatal_error = reason
                break
            continue
        fatal, reason = _safe_failure_reason(diagnostics)
        if diagnostics and fatal:
            failed.append(relative)
            fatal_error = reason
            break
        if incomplete_chunk or not observed_chunks:
            failed.append(relative)
            continue
        try:
            if _file_digest(source) != before:
                raise IncompleteExtractionError("source changed during extraction")
            filtered = filter_exact_source(payload, source=source, root=root)
            _validate_checkpoint_payload(filtered)
            filtered["_atlas_usage"] = {
                "unrecorded_tokens": unrecorded_tokens,
            }
            checkpoint(source, filtered)
        except (IncompleteExtractionError, OSError, ValueError):
            failed.append(relative)
            continue
        completed.append(relative)

    return ResumeReport(
        completed=tuple(completed),
        cached=tuple(cached),
        failed=tuple(failed),
        fatal_error=fatal_error,
        token_logging_failures=tuple(dict.fromkeys(token_logging_failures)),
    )


def _semantic_sources(
    root: Path,
    *,
    detect_fn: Callable[[Path], dict[str, Any]] | None = None,
) -> list[Path]:
    if detect_fn is None:
        from graphify.detect import detect

        detect_fn = detect

    detection = detect_fn(root)
    files = detection.get("files") or {}
    values = (
        list(files.get("document") or [])
        + list(files.get("paper") or [])
        + list(files.get("image") or [])
    )
    sources = [Path(value).resolve() for value in values]
    return sorted(set(sources), key=lambda path: _relative_source(path, root))


def _effective_provider(backend: str) -> str:
    """Attribute only endpoints whose provider identity is unambiguous."""

    backend = backend.casefold()
    endpoint = ""
    if backend == "openai":
        endpoint = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    elif backend == "claude":
        endpoint = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    elif backend == "gemini":
        endpoint = os.environ.get(
            "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com"
        )
    elif backend == "ollama":
        endpoint = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
    try:
        parsed = urlsplit(endpoint)
    except ValueError:
        return "unattributed"
    host = (parsed.hostname or "").casefold()
    if parsed.scheme == "https" and host == "integrate.api.nvidia.com":
        return "nvidia"
    if parsed.scheme == "https" and host == "api.groq.com":
        return "groq"
    if parsed.scheme == "https" and host == "openrouter.ai":
        return "openrouter"
    if parsed.scheme == "https" and host == "api.openai.com":
        return "openai"
    if backend == "claude" and parsed.scheme == "https" and host == "api.anthropic.com":
        return "anthropic"
    if backend == "gemini" and parsed.scheme == "https" and host == "generativelanguage.googleapis.com":
        return "gemini"
    if backend == "ollama" and host in {"127.0.0.1", "::1", "localhost"}:
        return "ollama"
    return "unattributed"


def _safe_model(value: str, backend: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._:/+-]+", "_", value.strip())[:160]
    return cleaned or f"{backend}-default"


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise OSError("unsafe semantic resume report")
    fd, raw_temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(raw_temporary)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        path.chmod(0o600)
    finally:
        if fd >= 0:
            os.close(fd)
        temporary.unlink(missing_ok=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--backend", required=True)
    parser.add_argument("--model", default="")
    parser.add_argument("--token-budget", type=int, default=4000)
    parser.add_argument(
        "--source-timeout",
        type=int,
        default=int(os.environ.get("GRAPHIFY_RESUME_SOURCE_TIMEOUT", "300")),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("graphify-out/semantic-resume-report.json"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.token_budget <= 0 or args.source_timeout <= 0:
        print(
            "ERROR: --token-budget and --source-timeout must be positive integers.",
            file=sys.stderr,
        )
        return 2
    os.umask(0o077)
    root = args.root.resolve()
    provider = _effective_provider(args.backend)
    model = _safe_model(args.model, args.backend)

    from graphify.cache import load_cached, save_cached
    from graphify.llm import extract_corpus_parallel

    try:
        ensure_safe_cache_path(root)
    except OSError:
        print("ERROR: unsafe semantic cache path.", file=sys.stderr)
        return 73
    sources = _semantic_sources(root)

    def log_tokens(provider_name: str, tokens: int, model_name: str) -> None:
        if provider_name == "unattributed":
            raise RuntimeError("provider could not be attributed safely")
        tracker = root / "scripts" / "token-tracker.sh"
        result = subprocess.run(
            [str(tracker), "log", provider_name, str(tokens), model_name],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("local token ledger rejected the record")

    reconciliation_failures: list[str] = []

    def is_cached(path: Path) -> bool:
        loaded = load_cached(path, root, kind="semantic")
        if not is_verified_cache_payload(loaded, source=path, root=root):
            return False
        assert isinstance(loaded, dict)
        marker = loaded.get("_atlas_checkpoint")
        if not isinstance(marker, dict) or marker.get("usage_recorded") is not False:
            return True
        relative = _relative_source(path, root)
        unrecorded = marker.get("unrecorded_tokens")
        if (
            not isinstance(unrecorded, int)
            or isinstance(unrecorded, bool)
            or unrecorded <= 0
        ):
            reconciliation_failures.append(relative)
            return True
        try:
            log_tokens(provider, unrecorded, model)
            updated = dict(loaded)
            updated_marker = dict(marker)
            updated_marker["usage_recorded"] = True
            updated_marker["unrecorded_tokens"] = 0
            updated_marker["usage_reconciled_at"] = datetime.now(
                timezone.utc
            ).isoformat()
            updated["_atlas_checkpoint"] = updated_marker
            ensure_safe_cache_path(root)
            save_cached(path, updated, root, kind="semantic")
            verified = load_cached(path, root, kind="semantic")
            if not isinstance(verified, dict):
                raise OSError("usage reconciliation checkpoint missing")
        except (OSError, RuntimeError, subprocess.SubprocessError):
            reconciliation_failures.append(relative)
        return True

    def extract_one(
        path: Path,
        on_chunk_done: Callable[[int, int, dict[str, Any]], None],
    ) -> ExtractionAttempt:
        capture = _BoundedTextCapture()
        previous = os.environ.get("GRAPHIFY_NO_INCREMENTAL_CACHE")
        previous_alarm = signal.getsignal(signal.SIGALRM)
        signal.signal(
            signal.SIGALRM,
            lambda _signum, _frame: (_ for _ in ()).throw(
                TimeoutError("semantic source timeout")
            ),
        )
        signal.setitimer(signal.ITIMER_REAL, args.source_timeout)
        os.environ["GRAPHIFY_NO_INCREMENTAL_CACHE"] = "1"
        try:
            try:
                with contextlib.redirect_stderr(capture):
                    payload = extract_corpus_parallel(
                        [path],
                        backend=args.backend,
                        model=args.model or None,
                        root=root,
                        token_budget=args.token_budget,
                        max_concurrency=1,
                        # Graphify's adaptive merge omits the parent attempt's token
                        # usage. Disable it here so the local ledger remains honest;
                        # a truncated source is retried later with a different plan.
                        max_retry_depth=0,
                        on_chunk_done=on_chunk_done,
                    )
            except TimeoutError:
                payload = {"nodes": [], "edges": [], "hyperedges": [], "failed_chunks": 1}
                capture.write("[atlas graphify resume] semantic source timeout\n")
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_alarm)
            if previous is None:
                os.environ.pop("GRAPHIFY_NO_INCREMENTAL_CACHE", None)
            else:
                os.environ["GRAPHIFY_NO_INCREMENTAL_CACHE"] = previous
        return ExtractionAttempt(payload=payload, diagnostics=capture.getvalue())

    checkpoint_metadata = {
        "version": 1,
        "provider": provider,
        "model": model,
    }

    def checkpoint(path: Path, payload: dict[str, Any]) -> None:
        ensure_safe_cache_path(root)
        persisted = dict(payload)
        usage = persisted.pop("_atlas_usage", {})
        unrecorded = usage.get("unrecorded_tokens", 0) if isinstance(usage, dict) else 0
        if not isinstance(unrecorded, int) or isinstance(unrecorded, bool) or unrecorded < 0:
            raise IncompleteExtractionError("invalid token-usage checkpoint")
        persisted["_atlas_checkpoint"] = {
            **checkpoint_metadata,
            "source": _relative_source(path, root),
            "complete": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "usage_recorded": unrecorded == 0,
            "unrecorded_tokens": unrecorded,
        }
        save_cached(path, persisted, root, kind="semantic")
        loaded = load_cached(path, root, kind="semantic")
        if not is_verified_cache_payload(loaded, source=path, root=root):
            raise IncompleteExtractionError("checkpoint verification failed")
        print(f"[atlas graphify resume] checkpointed {_relative_source(path, root)}")

    report = resume_sources(
        sources,
        root=root,
        provider=provider,
        model=model,
        is_cached=is_cached,
        extract_one=extract_one,
        checkpoint=checkpoint,
        log_tokens=log_tokens,
    )
    if reconciliation_failures:
        report = ResumeReport(
            completed=report.completed,
            cached=report.cached,
            failed=report.failed,
            fatal_error=report.fatal_error,
            token_logging_failures=tuple(
                dict.fromkeys(
                    (*report.token_logging_failures, *reconciliation_failures)
                )
            ),
        )
    status = "complete" if report.complete else "incomplete"
    if report.token_logging_failures:
        status += "_with_unrecorded_usage"
    report_payload = {
        **asdict(report),
        "status": status,
        "provider": provider,
        "model": model,
        "source_count": len(sources),
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        _write_report(args.report, report_payload)
    except OSError:
        print("ERROR: could not write the private semantic resume report.", file=sys.stderr)
        return 73

    print(
        "[atlas graphify resume] "
        f"sources={len(sources)} cached={len(report.cached)} "
        f"checkpointed={len(report.completed)} failed={len(report.failed)} "
        f"provider={provider}"
    )
    for relative in report.failed:
        print(f"[atlas graphify resume] incomplete {relative}")
    if report.token_logging_failures:
        print(
            "[atlas graphify resume] WARNING: actual usage could not be recorded "
            f"for {len(report.token_logging_failures)} source(s).",
            file=sys.stderr,
        )
    if report.fatal_error:
        print(
            f"[atlas graphify resume] stopped: {report.fatal_error}",
            file=sys.stderr,
        )
    return 0 if report.complete else 78


if __name__ == "__main__":
    raise SystemExit(main())
