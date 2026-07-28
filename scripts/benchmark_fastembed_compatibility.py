"""Run the versioned FastEmbed compatibility corpus without network access."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import NoReturn, Sequence

from atlas.memory.embedding_benchmark import (
    BenchmarkInputError,
    EmbeddingVectorError,
    evaluate_cases,
    load_cases,
)
from atlas.memory.embeddings import FastEmbedEmbedder


DEFAULT_CASES = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "fastembed_compatibility_cases.json"
)


class _RunnerArgumentError(ValueError):
    """Raised instead of letting argparse print usage and terminate the process."""


class _RunnerArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _RunnerArgumentError(message)


def _emit_error(status: str, message: str, exit_code: int) -> int:
    print(json.dumps({"error": message, "status": status}, ensure_ascii=False, sort_keys=True))
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    """Evaluate one local FastEmbed space against the versioned corpus."""
    parser = _RunnerArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    try:
        args = parser.parse_args(argv)
    except _RunnerArgumentError as exc:
        return _emit_error("INVALID_BENCHMARK_INPUT", str(exc), 4)

    previous_offline = os.environ.get("HF_HUB_OFFLINE")
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        try:
            cases = load_cases(args.cases)
        except BenchmarkInputError as exc:
            return _emit_error("INVALID_BENCHMARK_INPUT", str(exc), 4)
        try:
            embedder = FastEmbedEmbedder()
        except RuntimeError as exc:
            status = (
                "OPTIONAL_DEPENDENCY_MISSING"
                if "fastembed no instalado" in str(exc)
                else "MODEL_ARTIFACT_UNAVAILABLE"
            )
            return _emit_error(
                status,
                str(exc),
                2 if status == "OPTIONAL_DEPENDENCY_MISSING" else 3,
            )
        except Exception as exc:
            return _emit_error("MODEL_ARTIFACT_UNAVAILABLE", str(exc), 3)
        try:
            report = evaluate_cases(embedder, cases)
        except EmbeddingVectorError as exc:
            return _emit_error("MEASUREMENT_FAILED", str(exc), 1)
        except Exception as exc:
            return _emit_error("MEASUREMENT_FAILED", str(exc), 1)
        status = "MEASURED" if report.passed else "COMPATIBILITY_THRESHOLD_NOT_MET"
        print(json.dumps({"status": status, **report.as_dict()}, ensure_ascii=False, sort_keys=True))
        return 0 if report.passed else 5
    finally:
        if previous_offline is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = previous_offline


if __name__ == "__main__":
    raise SystemExit(main())
