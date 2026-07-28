# FastEmbed Compatibility Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline, read-only benchmark that measures the current FastEmbed identity and Spanish semantic ranking without changing Atlas memory behavior.

**Architecture:** A pure `atlas.memory.embedding_benchmark` module owns validated corpus parsing, cosine ranking and report serialization over the existing `Embedder` protocol. A thin script forces FastEmbed offline mode, creates the existing `FastEmbedEmbedder`, and prints an ephemeral JSON report. Fixtures are versioned inputs; no report is persisted automatically.

**Tech Stack:** Python 3.12 standard library, existing `Embedder` protocol and optional FastEmbed extra, pytest, JSON fixtures, argparse.

## Global Constraints

- Do not modify `config/governance.json`, `FastEmbedEmbedder`, `default_embedder`, a persistent store or project dependencies.
- The runner sets `HF_HUB_OFFLINE=1` before model construction and never enables download/network fallback.
- A missing FastEmbed extra is `OPTIONAL_DEPENDENCY_MISSING`; an unavailable local model artifact is `MODEL_ARTIFACT_UNAVAILABLE`.
- The report includes embedder `identity`, `fingerprint`, dimension and schema version but never claims `LIVE_VERIFIED` or authorizes migration.
- Unit tests use static vectors and do not require FastEmbed, a model cache, GPU or network.
- Use TDD: write each test first, observe its intended failure, then write the smallest implementation.
- Update `WORK_LEDGER.md`, `MEMORY.md`, `docs/INDEX.yaml`, the specification and the work-order registry only when the implementation slice actually needs them.

---

## File Structure

- `src/atlas/memory/embedding_benchmark.py`: pure data structures, JSON fixture loader, vector validation, cosine ranking and report serialization.
- `fixtures/fastembed_compatibility_cases.json`: Spanish query/candidate corpus with expected relevant ids and top-k thresholds.
- `scripts/benchmark_fastembed_compatibility.py`: offline CLI boundary; emits one JSON document to stdout and no files.
- `tests/test_embedding_benchmark.py`: deterministic unit coverage plus the optional real FastEmbed integration assertion.
- `docs/superpowers/specs/2026-07-28-fastembed-compatibility-benchmark-design.md`: approved intent and boundaries.
- `WORK_LEDGER.md`, `MEMORY.md`, `docs/INDEX.yaml`, `docs/canon/implementation_registry.yaml`: continuation and canonical traceability updated only with the completed work order.

### Task 1: Build the pure evaluator and strict fixture contract

**Files:**
- Create: `src/atlas/memory/embedding_benchmark.py`
- Create: `tests/test_embedding_benchmark.py`

**Interfaces:**
- Produces `BenchmarkCandidate(id: str, text: str)` and `BenchmarkCase(id: str, query: str, candidates: tuple[BenchmarkCandidate, ...], relevant_ids: frozenset[str], top_k: int)`.
- Produces `RankedCandidate(candidate_id: str, score: float, rank: int)` and `BenchmarkCaseResult(case_id: str, rankings: tuple[RankedCandidate, ...], relevant_rank: int | None, margin: float | None, passed: bool)`.
- Produces `EmbeddingBenchmarkReport(schema_version: str, identity: str, fingerprint: str, dimension: int, cases: tuple[BenchmarkCaseResult, ...], passed: bool)` with `as_dict() -> dict[str, object]`.
- Exposes `load_cases(path: Path) -> tuple[BenchmarkCase, ...]` and `evaluate_cases(embedder: Embedder, cases: Sequence[BenchmarkCase]) -> EmbeddingBenchmarkReport`.
- Raises `BenchmarkInputError(ValueError)` for malformed JSON/cases and `EmbeddingVectorError(ValueError)` for non-finite, empty or mismatched vectors.

- [ ] **Step 1: Write failing evaluator tests**

```python
def test_evaluate_cases_ranks_the_relevant_candidate_and_binds_identity() -> None:
    embedder = StaticEmbedder(
        {"consulta": [1.0, 0.0], "relevante": [0.9, 0.1], "ruido": [0.0, 1.0]}
    )
    case = BenchmarkCase(
        id="semantic-rank",
        query="consulta",
        candidates=(BenchmarkCandidate("relevant", "relevante"), BenchmarkCandidate("noise", "ruido")),
        relevant_ids=frozenset({"relevant"}),
        top_k=1,
    )

    report = evaluate_cases(embedder, (case,))

    assert report.passed is True
    assert report.identity == "static:v1"
    assert report.cases[0].relevant_rank == 1
    assert report.cases[0].rankings[0].candidate_id == "relevant"
```

```python
def test_evaluate_cases_rejects_non_finite_or_dimension_mismatched_vectors() -> None:
    case = valid_case()

    with pytest.raises(EmbeddingVectorError, match="finite"):
        evaluate_cases(StaticEmbedder.with_query([float("nan"), 0.0]), (case,))

    with pytest.raises(EmbeddingVectorError, match="dimension"):
        evaluate_cases(StaticEmbedder.with_candidate([1.0, 0.0, 0.0]), (case,))
```

```python
def test_evaluate_cases_breaks_score_ties_by_candidate_id_and_reports_margin() -> None:
    case = BenchmarkCase(
        id="tie-break",
        query="consulta",
        candidates=(BenchmarkCandidate("b", "empate-b"), BenchmarkCandidate("a", "empate-a")),
        relevant_ids=frozenset({"a"}),
        top_k=1,
    )
    embedder = StaticEmbedder({"consulta": [1.0, 0.0], "empate-a": [1.0, 0.0], "empate-b": [1.0, 0.0]})

    result = evaluate_cases(embedder, (case,)).cases[0]

    assert [ranked.candidate_id for ranked in result.rankings] == ["a", "b"]
    assert result.margin == 0.0
```

```python
def test_load_cases_rejects_invalid_top_k(tmp_path: Path) -> None:
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([{"id": "bad", "query": "q", "candidates": [{"id": "a", "text": "a"}], "relevant_ids": ["a"], "top_k": 0}]))

    with pytest.raises(BenchmarkInputError, match="top_k"):
        load_cases(path)
```

```python
def test_load_cases_rejects_unknown_relevant_id(tmp_path: Path) -> None:
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([{"id": "bad", "query": "q", "candidates": [{"id": "a", "text": "a"}], "relevant_ids": ["missing"], "top_k": 1}]))

    with pytest.raises(BenchmarkInputError, match="relevant"):
        load_cases(path)
```

- [ ] **Step 2: Run the tests to prove the absent contract**

Run: `PYTHONPATH=src python -m pytest tests/test_embedding_benchmark.py -q`

Expected: collection fails because `atlas.memory.embedding_benchmark` does not exist.

- [ ] **Step 3: Implement the smallest pure module**

```python
def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise EmbeddingVectorError("vector dimension mismatch")
    if not left or not all(math.isfinite(value) for value in (*left, *right)):
        raise EmbeddingVectorError("vectors must be non-empty and finite")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        raise EmbeddingVectorError("vectors must have non-zero norm")
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)
```

Implement strict JSON validation before embedding. Sort rankings with `(-score, candidate_id)` so ties are deterministic. Pass a case when at least one `relevant_id` ranks at or above `top_k`; compute `margin` as the best relevant score minus the best non-relevant score when both exist.

- [ ] **Step 4: Run the focused module tests**

Run: `PYTHONPATH=src python -m pytest tests/test_embedding_benchmark.py -q`

Expected: PASS with no FastEmbed import or network access.

- [ ] **Step 5: Commit the evaluator slice**

```bash
git add src/atlas/memory/embedding_benchmark.py tests/test_embedding_benchmark.py
git commit -m "feat(memory): add embedding compatibility evaluator"
```

### Task 2: Add the versioned corpus and offline runner

**Files:**
- Create: `fixtures/fastembed_compatibility_cases.json`
- Create: `scripts/benchmark_fastembed_compatibility.py`
- Modify: `tests/test_embedding_benchmark.py`

**Interfaces:**
- Fixture is a JSON array of `BenchmarkCase` input objects. It contains at least three Spanish semantic ranking cases, each with two candidates, one relevant id and `top_k: 1`.
- `main(argv: Sequence[str] | None = None) -> int` accepts `--cases PATH`, prints exactly one JSON result and returns `0` for a passing measured report, `5` for `COMPATIBILITY_THRESHOLD_NOT_MET`, `2` for `OPTIONAL_DEPENDENCY_MISSING`, `3` for `MODEL_ARTIFACT_UNAVAILABLE`, `4` for `INVALID_BENCHMARK_INPUT`, and `1` for another explicit measurement failure.
- `main()` sets `os.environ["HF_HUB_OFFLINE"] = "1"` before constructing `FastEmbedEmbedder`.

- [ ] **Step 1: Write failing fixture and runner tests**

```python
def test_versioned_fixture_has_three_valid_spanish_cases() -> None:
    cases = load_cases(FIXTURE_PATH)

    assert len(cases) >= 3
    assert all(case.top_k == 1 and len(case.candidates) >= 2 for case in cases)
```

```python
def test_runner_forces_offline_before_constructing_fastembed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    observed: dict[str, str | None] = {}

    class OfflineProbe:
        def __init__(self) -> None:
            observed["offline"] = os.environ.get("HF_HUB_OFFLINE")

    class FakeReport:
        passed = True

        def as_dict(self) -> dict[str, object]:
            return {"passed": True}

    monkeypatch.setattr(runner, "FastEmbedEmbedder", OfflineProbe)
    monkeypatch.setattr(runner, "evaluate_cases", lambda _embedder, _cases: FakeReport())

    assert runner.main([]) == 0
    assert observed["offline"] == "1"
```

```python
def test_runner_classifies_missing_optional_extra(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    class MissingFastEmbed:
        def __init__(self) -> None:
            raise RuntimeError("fastembed no instalado")

    monkeypatch.setattr(runner, "FastEmbedEmbedder", MissingFastEmbed)

    assert runner.main([]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "OPTIONAL_DEPENDENCY_MISSING"
```

```python
def test_runner_returns_nonzero_when_measurement_misses_its_threshold(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class ThresholdMiss:
        passed = False

        def as_dict(self) -> dict[str, object]:
            return {"passed": False}

    monkeypatch.setattr(runner, "FastEmbedEmbedder", lambda: object())
    monkeypatch.setattr(runner, "evaluate_cases", lambda _embedder, _cases: ThresholdMiss())

    assert runner.main([]) == 5
    assert json.loads(capsys.readouterr().out)["status"] == "COMPATIBILITY_THRESHOLD_NOT_MET"
```

```python
@pytest.mark.skipif(
    not (_HAS_FASTEMBED and os.environ.get("ATLAS_RUN_FASTEMBED_COMPAT") == "1"),
    reason="requiere fastembed, artefacto local y opt-in explícito",
)
def test_cached_fastembed_satisfies_versioned_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    report = evaluate_cases(FastEmbedEmbedder(), load_cases(FIXTURE_PATH))

    assert report.passed is True
```

The runner seam is mocked only to prove process-environment ordering and classified degradation; semantic ranking remains covered through the real pure evaluator tests. The real FastEmbed test remains opt-in so ordinary CI never needs a model cache or network.

- [ ] **Step 2: Run the tests to prove the runner/fixture are absent**

Run: `PYTHONPATH=src python -m pytest tests/test_embedding_benchmark.py -q`

Expected: FAIL because the fixture and runner module do not exist.

- [ ] **Step 3: Add the corpus and minimal CLI**

```python
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    args = parser.parse_args(argv)
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        cases = load_cases(args.cases)
    except BenchmarkInputError as exc:
        return _emit_error("INVALID_BENCHMARK_INPUT", str(exc), 4)
    try:
        embedder = FastEmbedEmbedder()
    except RuntimeError as exc:
        status = "OPTIONAL_DEPENDENCY_MISSING" if "fastembed no instalado" in str(exc) else "MODEL_ARTIFACT_UNAVAILABLE"
        return _emit_error(status, str(exc), 2 if status == "OPTIONAL_DEPENDENCY_MISSING" else 3)
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
```

Use `Path(__file__).resolve().parents[1] / "fixtures" / "fastembed_compatibility_cases.json"` for the default. Do not add `--output`, network flags, persistence, migration or approval behavior.

- [ ] **Step 4: Run focused tests and the offline local runner**

Run: `PYTHONPATH=src python -m pytest tests/test_embedding_benchmark.py -q`

Expected: PASS; the real FastEmbed integration case is skipped unless its package, local artifact and explicit opt-in are all present.

Run: `PYTHONPATH=src HF_HUB_OFFLINE=1 python scripts/benchmark_fastembed_compatibility.py`

Expected: one JSON document with `status="MEASURED"`, identity/fingerprint/dimension and no `LIVE_VERIFIED`; a measured threshold miss is explicit with exit `5`; other classified failures exit `1`–`4`.

- [ ] **Step 5: Commit the runner slice**

```bash
git add fixtures/fastembed_compatibility_cases.json scripts/benchmark_fastembed_compatibility.py tests/test_embedding_benchmark.py
git commit -m "feat(memory): add offline FastEmbed compatibility benchmark"
```

### Task 3: Register the measured validation harness without promoting a decision

**Files:**
- Modify: `docs/canon/implementation_registry.yaml`
- Modify: `WORK_LEDGER.md`
- Modify: `MEMORY.md`
- Modify: `docs/INDEX.yaml`
- Modify: `docs/superpowers/specs/2026-07-28-fastembed-compatibility-benchmark-design.md`

**Interfaces:**
- Adds `ADC-WO-115` under P04 with status `DONE` only after the runner and tests pass.
- Records `VALIDATION_HARNESS`/`ATLAS_MEASUREMENT` semantics without adding `LIVE_VERIFIED`, `EVIDENCE_QUALIFIED`, a dependency decision or a memory migration claim.

- [ ] **Step 1: Add the completed work order and live continuation record**

Register the evidence, source decision, current/target state, files, test commands, risks, rollback and acceptance. State precisely that the measured output is a validation harness and that pin/model/rebuild remain separate. Update the design status to implemented only after the runner command has emitted a classified result. No new validator behavior is needed because the existing work-order gate validates the complete record.

- [ ] **Step 2: Run canon, index and full regression gates**

Run: `PYTHONPATH=src python scripts/check_canon.py`

Expected: PASS.

Run: `PYTHONPATH=src python scripts/docs_index_audit.py --write && PYTHONPATH=src python scripts/docs_index_audit.py --strict`

Expected: PASS with no missing/orphan/stale entries.

Run: `PYTHONPATH=src python -m pytest tests/test_embedding_benchmark.py tests/test_fastembed_embedder.py tests/test_embedding_identity.py -q`

Expected: PASS; any optional FastEmbed absence is explicitly skipped/classified.

Run: `MYPYPATH=src python -m mypy src/atlas/memory/embedding_benchmark.py`

Expected: `Success: no issues found`.

- [ ] **Step 3: Commit the governed evidence slice**

```bash
git add docs/canon/implementation_registry.yaml WORK_LEDGER.md MEMORY.md docs/INDEX.yaml docs/superpowers/specs/2026-07-28-fastembed-compatibility-benchmark-design.md
git commit -m "canon(memory): register embedding compatibility evidence"
```

## Plan Self-Review

- Spec coverage: Task 1 covers pure ranking/identity and vector rejection; Task 2 covers offline runner, fixture and classified degradation; Task 3 covers canonical traceability and non-promotion.
- No placeholder scan: every task names concrete files, signatures, commands, expected outcomes and commit boundaries.
- Type consistency: Tasks 2 and 3 consume `load_cases`, `evaluate_cases`, `EmbeddingBenchmarkReport` and the exceptions defined in Task 1.
- Scope: no production memory migration, dependency pin or model reconfiguration is included.
