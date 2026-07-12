"""
eval_longmemeval.py — Adaptador LongMemEval_S para SqliteMemoryIndex.

Mide Recall@k (¿aparece la sesión de respuesta en el top-k recuperado?)
para los tres modos de retrieval (cosine / hybrid / temporal) sin necesitar LLM.

Esto es la medición Q1 del veredicto del Cónclave 2026-06-25: el baseline
externo que valida si el retrieval de Atlas funciona en un benchmark real,
con sesiones de conversación reales y preguntas en inglés diversas.

Estructura de los datos (longmemeval_s_cleaned.json):
  [
    {
      "question_id": str,
      "question_type": str,  # single-session-user | multi-session | temporal-reasoning | ...
      "question": str,
      "question_date": str,  # ISO date
      "answer": str,
      "answer_session_ids": [str],       # sesiones que contienen la respuesta
      "haystack_session_ids": [str],     # todas las sesiones del haystack
      "haystack_sessions": [[{role, content}, ...]],  # contenido de cada sesión
      "haystack_dates": [str],           # fecha de cada sesión
    },
    ...
  ]

Uso:
    python scripts/eval_longmemeval.py \\
        --data data/longmemeval/longmemeval_s_cleaned.json \\
        [--n 50] [--k 5] [--mode cosine|hybrid|temporal|all] [--seed 42]
"""

from __future__ import annotations

import argparse
import json
import random
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Callable

from atlas.immunity.lesson_recaller import RecallResult
from atlas.memory.embeddings import default_embedder
from atlas.memory.memory_index import SqliteMemoryIndex, rrf_fuse
from atlas.memory.record import GenericRecord


# ---------------------------------------------------------------------------
# Retriever types
# SampleCtx: optional per-sample metadata (question_date_ns, etc.) for
# retrievers that can exploit it (temporal-as_of, multihop).
# ---------------------------------------------------------------------------

import dataclasses


@dataclasses.dataclass
class SampleCtx:
    question_date_ns: int | None = None  # parsed from sample["question_date"]


Retriever = Callable[[SqliteMemoryIndex, str, int, SampleCtx], list[RecallResult]]


def _cosine(idx: SqliteMemoryIndex, query: str, k: int, ctx: SampleCtx) -> list[RecallResult]:
    return idx.recall_all(query, k=k)


def _hybrid(idx: SqliteMemoryIndex, query: str, k: int, ctx: SampleCtx) -> list[RecallResult]:
    n = max(k * 2, 10)
    cosine = idx.recall_all(query, k=n)
    try:
        lexical = idx.recall_lexical(query, k=n)
    except RuntimeError:
        lexical = []
    fused = rrf_fuse([[r.lesson_id for r in cosine], [r.lesson_id for r in lexical]])[:k]
    cmap = {r.lesson_id: r.score for r in cosine}
    return [RecallResult(lesson_id=rid, score=cmap.get(rid, 0.0), matched=True) for rid in fused]


def _temporal(idx: SqliteMemoryIndex, query: str, k: int, ctx: SampleCtx) -> list[RecallResult]:
    """Cosine + valid_from filter. No as_of: all sessions valid → same as cosine."""
    return idx.recall_temporal(query, k=k)


def _temporal_aof(idx: SqliteMemoryIndex, query: str, k: int, ctx: SampleCtx) -> list[RecallResult]:
    """Temporal with as_of=question_date: only sessions BEFORE the question date.

    This tests whether knowing the question timestamp helps temporal-reasoning
    questions: "What was my job in 2023?" should exclude sessions after 2023.
    """
    return idx.recall_temporal(query, k=k, as_of_ns=ctx.question_date_ns)


def _multihop(idx: SqliteMemoryIndex, query: str, k: int, ctx: SampleCtx) -> list[RecallResult]:
    """Multi-hop recall: expand seed results via co-citation / link following.

    Designed for multi-session questions that span multiple conversations.
    k is ignored (recall_multihop uses hops=2 internally).
    """
    results = idx.recall_multihop(query, hops=2)
    return results[:k]


def _hybrid_multihop(idx: SqliteMemoryIndex, query: str, k: int, ctx: SampleCtx) -> list[RecallResult]:
    """Hybrid + multihop fused: best of both for multi-session questions."""
    n = max(k * 2, 10)
    cosine = idx.recall_all(query, k=n)
    try:
        lexical = idx.recall_lexical(query, k=n)
    except RuntimeError:
        lexical = []
    multihop = idx.recall_multihop(query, hops=2)
    all_rankings = [
        [r.lesson_id for r in cosine],
        [r.lesson_id for r in lexical],
        [r.lesson_id for r in multihop],
    ]
    fused = rrf_fuse(all_rankings)[:k]
    cmap = {r.lesson_id: r.score for r in cosine}
    return [RecallResult(lesson_id=rid, score=cmap.get(rid, 0.0), matched=True) for rid in fused]


def _temporal_decay(idx: SqliteMemoryIndex, query: str, k: int, ctx: SampleCtx) -> list[RecallResult]:
    """Cosine re-rankeado con decay exponencial por antigüedad (half-life 90 días)."""
    import math
    import time as _time
    n = max(k * 3, 15)
    base = idx.recall_all(query, k=n)
    if not base:
        return []
    now_ns = _time.time_ns()
    half_life_ns = 90 * 86_400 * 1_000_000_000
    placeholders = ",".join("?" * len(base))
    rows = dict(idx._conn.execute(
        f"SELECT id, COALESCE(valid_from_ns, 0) FROM records WHERE id IN ({placeholders})",
        [r.lesson_id for r in base],
    ).fetchall())
    rescored = []
    for r in base:
        age_ns = max(0, now_ns - rows.get(r.lesson_id, 0))
        decay = math.pow(0.5, age_ns / half_life_ns)
        rescored.append(RecallResult(lesson_id=r.lesson_id, score=r.score * decay, matched=True))
    rescored.sort(key=lambda r: r.score, reverse=True)
    return rescored[:k]


def _hybrid_temporal(idx: SqliteMemoryIndex, query: str, k: int, ctx: SampleCtx) -> list[RecallResult]:
    """Hybrid (cosine+lexical RRF) re-rankeado con el decay de _temporal_decay."""
    fused = _hybrid(idx, query, max(k * 2, 10), ctx)
    if not fused:
        return []
    decayed = _temporal_decay(idx, query, max(k * 2, 10), ctx)
    dmap = {r.lesson_id: r.score for r in decayed}
    rescored = [
        RecallResult(lesson_id=r.lesson_id, score=dmap.get(r.lesson_id, r.score * 0.5), matched=True)
        for r in fused
    ]
    rescored.sort(key=lambda r: r.score, reverse=True)
    return rescored[:k]


RETRIEVERS: dict[str, Retriever] = {
    "cosine": _cosine,
    "hybrid": _hybrid,
    "temporal": _temporal,
    "temporal_aof": _temporal_aof,
    "multihop": _multihop,
    "hybrid_multihop": _hybrid_multihop,
    "temporal_decay": _temporal_decay,
    "hybrid_temporal": _hybrid_temporal,
}


# ---------------------------------------------------------------------------
# Ingestion helpers
# ---------------------------------------------------------------------------

def _session_text(messages: list[dict[str, str]]) -> str:
    """Convert a session (list of {role, content}) to a single text block."""
    parts = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        parts.append(f"[{role}] {content}")
    return "\n".join(parts)


def _ingest_sample(
    idx: SqliteMemoryIndex,
    session_ids: list[str],
    sessions: list[list[dict[str, str]]],
    dates: list[str],
) -> None:
    """Insert each session as one memory record with its date as valid_from."""
    import time as _time

    for sid, session, date_str in zip(session_ids, sessions, dates):
        text = _session_text(session)
        if not text.strip():
            continue
        # Parse date → ns. LongMemEval dates are "YYYY-MM-DD HH:MM:SS" or similar.
        try:
            import datetime
            dt = datetime.datetime.fromisoformat(date_str.replace(" ", "T"))
            valid_from_ns = int(dt.timestamp() * 1_000_000_000)
        except Exception:
            valid_from_ns = _time.time_ns()

        record = GenericRecord(record_id=sid, text=text, created_at=date_str)
        idx.upsert(record, valid_from_ns=valid_from_ns)  # tenant isolation not needed for eval


# ---------------------------------------------------------------------------
# Evaluation core
# ---------------------------------------------------------------------------

def recall_at_k(
    retrieved_ids: list[str],
    relevant_ids: set[str],
) -> float:
    """1.0 if any relevant ID is in the retrieved set, else 0.0 (binary recall)."""
    return 1.0 if relevant_ids & set(retrieved_ids) else 0.0


def _parse_date_ns(date_str: str) -> int | None:
    """Parse LongMemEval date string to nanoseconds, or None on failure."""
    import datetime
    try:
        dt = datetime.datetime.fromisoformat(date_str.replace(" ", "T"))
        return int(dt.timestamp() * 1_000_000_000)
    except Exception:
        return None


def evaluate_sample(
    sample: dict,
    retrievers: dict[str, Retriever],
    k: int,
    use_hybrid: bool,
) -> dict[str, float]:
    """Run all retrievers on one sample, return {mode: recall@k}."""
    session_ids = sample["haystack_session_ids"]
    sessions = sample["haystack_sessions"]
    dates = sample.get("haystack_dates", ["2024-01-01"] * len(session_ids))
    answer_session_ids = set(sample["answer_session_ids"])
    question = sample["question"]

    ctx = SampleCtx(question_date_ns=_parse_date_ns(sample.get("question_date", "")))

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "lme.db"
        # Embedder gobernado por env (ATLAS_EMBEDDER) — 3ª aparición del bug
        # 'embedder ignora el env' (2026-07-10): sin esto el eval medía
        # SIEMPRE el stub dim=64 (0.30/0.36) por el default de la clase,
        # y el número histórico con fastembed no era reproducible.
        idx = SqliteMemoryIndex(
            str(db_path), embedder=default_embedder(), lexical_index=use_hybrid
        )
        _ingest_sample(idx, session_ids, sessions, dates)  # no tenant for eval isolation

        results = {}
        for mode, retriever in retrievers.items():
            retrieved = retriever(idx, question, k, ctx)
            retrieved_ids = [r.lesson_id for r in retrieved]
            results[mode] = recall_at_k(retrieved_ids, answer_session_ids)
        return results


# ---------------------------------------------------------------------------
# Aggregate reporting
# ---------------------------------------------------------------------------

def run_evaluation(
    data: list[dict],
    modes: list[str],
    k: int,
    n: int | None,
    seed: int,
) -> dict:
    random.seed(seed)
    subset = random.sample(data, n) if n and n < len(data) else data

    use_hybrid = any(m in modes for m in ("hybrid", "hybrid_multihop"))
    active_retrievers = {m: RETRIEVERS[m] for m in modes}

    # Per-type accumulators
    per_type: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    overall: dict[str, list[float]] = defaultdict(list)

    print(f"Evaluating {len(subset)} samples, k={k}, modes={modes} …")
    t0 = time.time()

    for i, sample in enumerate(subset, 1):
        qtype = sample.get("question_type", "unknown")
        scores = evaluate_sample(sample, active_retrievers, k, use_hybrid)
        for mode, score in scores.items():
            per_type[qtype][mode].append(score)
            overall[mode].append(score)
        if i % 10 == 0:
            elapsed = time.time() - t0
            print(f"  {i}/{len(subset)} ({elapsed:.0f}s)")

    elapsed = time.time() - t0

    # Aggregate
    def mean(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    result = {
        "n": len(subset),
        "k": k,
        "elapsed_s": round(elapsed, 1),
        "overall": {mode: round(mean(scores), 4) for mode, scores in overall.items()},
        "per_type": {
            qtype: {mode: round(mean(scores), 4) for mode, scores in mode_scores.items()}
            for qtype, mode_scores in sorted(per_type.items())
        },
        "counts_per_type": {qtype: len(list(mode_scores.values())[0])
                            for qtype, mode_scores in per_type.items()},
    }
    return result


def print_report(result: dict) -> None:
    print()
    print("=" * 60)
    print(f"LongMemEval_S  Recall@{result['k']}  (n={result['n']}, {result['elapsed_s']}s)")
    print("=" * 60)

    modes = list(result["overall"].keys())
    col = 12
    hdr = f"{'Type':<32}" + "".join(f"{m:>{col}}" for m in modes)
    print(hdr)
    print("-" * len(hdr))

    for qtype, scores in result["per_type"].items():
        n = result["counts_per_type"][qtype]
        label = f"{qtype} (n={n})"
        row = f"{label:<32}" + "".join(f"{scores.get(m, 0):>{col}.4f}" for m in modes)
        print(row)

    print("-" * len(hdr))
    overall = result["overall"]
    row = f"{'OVERALL':<32}" + "".join(f"{overall.get(m, 0):>{col}.4f}" for m in modes)
    print(row)
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="LongMemEval_S retrieval baseline for Atlas")
    parser.add_argument("--data", default="data/longmemeval/longmemeval_s_cleaned.json")
    parser.add_argument("--n", type=int, default=None, help="Sample size (default: all 500)")
    parser.add_argument("--k", type=int, default=5, help="Top-k for retrieval (default: 5)")
    parser.add_argument("--mode", default="all", help="cosine|hybrid|temporal|all")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--json-out", help="Optional path to write JSON result")
    args = parser.parse_args()

    with open(args.data) as f:
        data = json.load(f)

    if args.mode == "all":
        modes = ["cosine", "hybrid", "temporal", "temporal_aof", "multihop", "hybrid_multihop"]
    elif args.mode == "baseline":
        modes = ["cosine", "hybrid", "temporal"]
    else:
        modes = [m.strip() for m in args.mode.split(",")]
        for m in modes:
            if m not in RETRIEVERS:
                parser.error(f"Unknown mode: {m}. Choose from: {list(RETRIEVERS.keys())}")

    result = run_evaluation(data, modes=modes, k=args.k, n=args.n, seed=args.seed)
    print_report(result)

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2))
        print(f"JSON saved to {args.json_out}")


if __name__ == "__main__":
    main()
