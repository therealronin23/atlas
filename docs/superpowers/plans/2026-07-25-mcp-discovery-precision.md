# MCP Discovery Precision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce noise in `docs/design/mcp_catalog_classified.yaml`'s `candidato` pipeline by adding a GitHub star-count floor, threading the original broad "seed" interest through to a new LLM quality-and-relevance judge, and letting the operator seed the discovery loop with hand-picked URLs — then reset the ~2824 noisy legacy candidates once the new pipeline is live.

**Architecture:** Four additive pieces layered on the existing discovery chain (`TopicExpander` → `PanoramaScout` → `research_digest.py` → `mcp_catalog_classified.yaml`). No changes to `adopt_mcp_server` or `sensitivity="high"`. `research_digest.py` stays a pure function (no LLM, no network) — the new LLM judgment lives in a separate injectable module mirroring `security_council_gate.py`'s `scan_fn`/`audit_fn` pattern.

**Tech Stack:** Python 3.12, pytest, `atlas.core.inference_hub.InferenceHub`, existing `SSRFBridge`/`MerkleLogger` collaborators, PyYAML round-trip.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-25-mcp-discovery-precision-design.md` — follow exactly; do not touch `adopt_mcp_server` or `sensitivity="high"`.
- `research_digest.py` MUST remain free of network calls and LLM calls (its own docstring invariant) — new fields only, no new imports of `inference_hub`.
- All new/changed env flags follow the existing `ATLAS_*` naming and default-safe-off convention used elsewhere in `.env` (e.g. `ATLAS_MCP_RESEED`).
- Curated sources are restricted to `github.com/<owner>/<repo>` URLs for now (matches `research_digest.py`'s existing `source == "github"`-only rule) — directory/aggregator sites (tododeia.com, etc.) are for the operator's own browsing, not machine-ingestible entries.
- Piece 4 (cleanup script) is manual-only, never wired into the scheduler.
- Order of landing: Tasks 1-9 (pieces 1-3) merged and running in production BEFORE Task 10 (piece 4) is ever executed — the daemon already runs `ATLAS_MCP_RESEED=1`/`ATLAS_MCP_VETTING=1`, so wiping candidates before the new pipeline ships would let the old noisy logic refill the catalog.
- Every task ends green on `pytest -q -m "not computer_use"` for its own new/changed test file, plus `mypy` clean on touched files.

---

### Task 1: `Finding.seed` — parse the `- seed:` line in `research_digest.py`

**Files:**
- Modify: `src/atlas/core/self_maintenance/research_digest.py` (the `Finding` dataclass at line 48-56, `_SEED_PREFIX` constant near line 44, `parse_findings` at line 59-98)
- Test: `tests/test_research_digest.py`

**Interfaces:**
- Produces: `Finding.seed: str` (default `""`), parsed from an optional `- seed: <text>` line following `- tema:`/`- url:`/`- extracto:` in a report section. Consumed by Task 8.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_research_digest.py` (near the existing `test_parse_findings_real_format`):

```python
def test_parse_findings_captures_optional_seed_line() -> None:
    text = textwrap.dedent(
        """\
        ### [github] acme/mempalace
        - tema: temporal knowledge graph
        - seed: memoria de agentes de IA
        - url: https://github.com/acme/mempalace
        - extracto: a memory tool
        """
    )
    findings = parse_findings(text)
    assert len(findings) == 1
    assert findings[0].seed == "memoria de agentes de IA"


def test_parse_findings_seed_defaults_to_empty_when_absent() -> None:
    findings = parse_findings(_REAL_REPORT_FRAGMENT)
    assert all(f.seed == "" for f in findings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_research_digest.py -k seed -v`
Expected: FAIL — `Finding.__init__() got an unexpected keyword argument 'seed'` or `AttributeError: 'Finding' object has no attribute 'seed'`.

- [ ] **Step 3: Write minimal implementation**

In `src/atlas/core/self_maintenance/research_digest.py`, add the prefix constant next to the others (around line 44):

```python
_SEED_PREFIX = "- seed:"
```

Add `seed: str = ""` to the `Finding` dataclass (after `topic: str`):

```python
@dataclass(frozen=True)
class Finding:
    """Un hallazgo ya parseado de un informe ``research_*.md``."""

    source: str
    title: str
    url: str
    topic: str
    excerpt: str
    seed: str = ""
```

In `parse_findings`, add the seed line to `flush()` and to the line-matching branch:

```python
    def flush() -> None:
        nonlocal current
        if current is not None and current.get("source") and current.get("title"):
            findings.append(
                Finding(
                    source=current.get("source", ""),
                    title=current.get("title", ""),
                    url=current.get("url", ""),
                    topic=current.get("topic", ""),
                    excerpt=current.get("excerpt", ""),
                    seed=current.get("seed", ""),
                )
            )
        current = None
```

```python
        elif stripped.startswith(_SEED_PREFIX):
            current["seed"] = stripped[len(_SEED_PREFIX):].strip()
```
(add this `elif` branch alongside the existing `_TEMA_PREFIX`/`_URL_PREFIX`/`_EXTRACTO_PREFIX` checks)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_research_digest.py -v`
Expected: all PASS (existing tests + 2 new ones)

- [ ] **Step 5: Commit**

```bash
git add src/atlas/core/self_maintenance/research_digest.py tests/test_research_digest.py
git commit -m "feat(discovery): parse optional seed line in research_digest Finding"
```

---

### Task 2: `PanoramaFinding.seed` + `topic_seeds` wiring in `PanoramaScout`

**Files:**
- Modify: `src/atlas/core/self_maintenance/panorama_scout.py` (`PanoramaFinding` dataclass, `PanoramaScout.__init__`, `discover`, `_search_github`, `_search_hackernews`, `_search_arxiv`)
- Test: `tests/test_panorama_scout.py`

**Interfaces:**
- Consumes: nothing new from other tasks.
- Produces: `PanoramaFinding.seed: str` (default `""`); `PanoramaScout(topic_seeds: dict[str, str] | None = None)` — maps a query string to the broad seed interest that generated it. Consumed by Task 5 (facade wiring) and Task 8 (aggregation).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_panorama_scout.py`:

```python
class TestSeedThreading:
    def test_finding_carries_seed_from_topic_seeds_map(self, merkle) -> None:
        body = _github_body(
            _repo("acme/mempalace", "https://github.com/acme/mempalace", "desc"),
        )
        scout = PanoramaScout(
            merkle=merkle,
            bridge=SSRFBridge(),
            fetch=lambda u: body,
            topics=["memory palace"],
            topic_seeds={"memory palace": "memoria de agentes de IA"},
        )
        findings = scout.discover()
        assert len(findings) == 1
        assert findings[0].seed == "memoria de agentes de IA"

    def test_finding_seed_empty_when_topic_not_in_map(self, merkle) -> None:
        body = _github_body(
            _repo("acme/mempalace", "https://github.com/acme/mempalace", "desc"),
        )
        scout = PanoramaScout(
            merkle=merkle,
            bridge=SSRFBridge(),
            fetch=lambda u: body,
            topics=["memory palace"],
        )
        findings = scout.discover()
        assert findings[0].seed == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_panorama_scout.py -k seed -v`
Expected: FAIL — `TypeError: PanoramaScout.__init__() got an unexpected keyword argument 'topic_seeds'`

- [ ] **Step 3: Write minimal implementation**

Add `seed: str = ""` to `PanoramaFinding` (after `topic: str`) and to `to_dict()`:

```python
@dataclass
class PanoramaFinding:
    topic: str
    source: str
    title: str
    url: str
    excerpt: str
    seed: str = ""
    discovered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "source": self.source,
            "title": self.title,
            "url": self.url,
            "excerpt": self.excerpt,
            "seed": self.seed,
            "discovered_at": self.discovered_at,
        }
```

In `PanoramaScout.__init__`, add the param and store it:

```python
    def __init__(
        self,
        *,
        merkle: MerkleLogger,
        bridge: SSRFBridge,
        fetch: Callable[[str], str],
        topics: list[str],
        max_results_per_topic: int = 5,
        topic_seeds: dict[str, str] | None = None,
    ) -> None:
        self._merkle = merkle
        self._bridge = bridge
        self._fetch = fetch
        self._topics = topics
        self._max_results = max_results_per_topic
        self._topic_seeds = topic_seeds or {}
```

In each of `_search_github`, `_search_hackernews`, `_search_arxiv`, add `seed=self._topic_seeds.get(topic, "")` to every `PanoramaFinding(...)` construction (3 call sites total, one per method).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_panorama_scout.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/atlas/core/self_maintenance/panorama_scout.py tests/test_panorama_scout.py
git commit -m "feat(discovery): thread seed interest through PanoramaFinding"
```

---

### Task 3: GitHub star-count floor in `PanoramaScout._search_github`

**Files:**
- Modify: `src/atlas/core/self_maintenance/panorama_scout.py` (`PanoramaScout.__init__`, `_search_github`)
- Test: `tests/test_panorama_scout.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `PanoramaScout(min_stars: int = 0)` — when `> 0`, appends `stars:>=N` to the GitHub search query. Consumed by Task 5 (facade wiring, reads `ATLAS_MCP_DISCOVERY_MIN_STARS`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_panorama_scout.py`:

```python
class TestMinStarsFilter:
    def test_min_stars_appends_qualifier_to_github_query(self, merkle) -> None:
        captured_urls: list[str] = []

        def fetch(u: str) -> str:
            captured_urls.append(u)
            return _github_body()

        scout = PanoramaScout(
            merkle=merkle,
            bridge=SSRFBridge(),
            fetch=fetch,
            topics=["memory palace"],
            min_stars=5,
        )
        scout.discover()
        assert any("stars%3A%3E%3D5" in u or "stars:>=5" in u for u in captured_urls)

    def test_zero_min_stars_omits_qualifier(self, merkle) -> None:
        captured_urls: list[str] = []

        def fetch(u: str) -> str:
            captured_urls.append(u)
            return _github_body()

        scout = PanoramaScout(
            merkle=merkle,
            bridge=SSRFBridge(),
            fetch=fetch,
            topics=["memory palace"],
        )
        scout.discover()
        assert all("stars" not in u for u in captured_urls)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_panorama_scout.py -k min_stars -v`
Expected: FAIL — `TypeError: PanoramaScout.__init__() got an unexpected keyword argument 'min_stars'`

- [ ] **Step 3: Write minimal implementation**

Extend `__init__` (same signature block touched in Task 2):

```python
        min_stars: int = 0,
    ) -> None:
        ...
        self._min_stars = min_stars
```

In `_search_github`, build the query with the qualifier folded into the searched text (GitHub's repo search treats `stars:>=N` as a query qualifier, so it must be part of `q=`, not a separate param):

```python
    def _search_github(self, topic: str) -> list[PanoramaFinding]:
        query = topic
        if self._min_stars > 0:
            query = f"{topic} stars:>={self._min_stars}"
        url = (
            f"{_GITHUB_SEARCH_URL}?q={quote_plus(query)}"
            f"&sort=updated&order=desc&per_page={self._max_results}"
        )
```

(replace the existing `url = (...)` block; everything below it in the method is unchanged)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_panorama_scout.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/atlas/core/self_maintenance/panorama_scout.py tests/test_panorama_scout.py
git commit -m "feat(discovery): add min-stars floor to GitHub search query"
```

---

### Task 4: `_render_research_report` emits the `- seed:` line

**Files:**
- Modify: `src/atlas/core/orchestrator_parts/maintenance_facade.py` (`_render_research_report`, line 116-141)
- Test: `tests/test_maintenance_facade_research_report.py` (new file — `_render_research_report` currently has no dedicated test file; grep confirms no `test_.*render_research_report` exists)

**Interfaces:**
- Consumes: `PanoramaFinding.seed` (Task 2).
- Produces: report text with a `- seed: <text>` line after `- tema:` whenever `finding.seed` is non-empty. Consumed by Task 1's parser (already built) once real reports flow through it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_maintenance_facade_research_report.py`:

```python
"""Tests for _render_research_report's optional seed line (2026-07-25)."""
from __future__ import annotations

from atlas.core.orchestrator_parts.maintenance_facade import _render_research_report
from atlas.core.self_maintenance.panorama_scout import PanoramaFinding


def test_render_includes_seed_line_when_present() -> None:
    finding = PanoramaFinding(
        topic="temporal knowledge graph",
        source="github",
        title="acme/mempalace",
        url="https://github.com/acme/mempalace",
        excerpt="a tool",
        seed="memoria de agentes de IA",
    )
    text = _render_research_report("2026-07-25", ["memoria de agentes de IA"], ["temporal knowledge graph"], [finding])
    lines = text.splitlines()
    tema_idx = next(i for i, l in enumerate(lines) if l.startswith("- tema:"))
    assert lines[tema_idx + 1] == "- seed: memoria de agentes de IA"


def test_render_omits_seed_line_when_absent() -> None:
    finding = PanoramaFinding(
        topic="temporal knowledge graph",
        source="github",
        title="acme/mempalace",
        url="https://github.com/acme/mempalace",
        excerpt="a tool",
    )
    text = _render_research_report("2026-07-25", ["x"], ["temporal knowledge graph"], [finding])
    assert "- seed:" not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_maintenance_facade_research_report.py -v`
Expected: FAIL — `AssertionError` (the seed line is never written today)

- [ ] **Step 3: Write minimal implementation**

In `_render_research_report`, inside the `for finding in findings:` loop, insert the seed line right after the `- tema:` line:

```python
    for finding in findings:
        lines.append(f"### [{finding.source}] {finding.title}")
        lines.append(f"- tema: {finding.topic}")
        if getattr(finding, "seed", ""):
            lines.append(f"- seed: {finding.seed}")
        lines.append(f"- url: {finding.url}")
        if finding.excerpt:
            lines.append(f"- extracto: {finding.excerpt}")
        lines.append("")
```

(`getattr` guards against any other caller still passing a plain object without `.seed` — cheap safety, not a new invariant)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_maintenance_facade_research_report.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/atlas/core/orchestrator_parts/maintenance_facade.py tests/test_maintenance_facade_research_report.py
git commit -m "feat(discovery): render seed line in research report output"
```

---

### Task 5: Wire `expand_detailed` + `min_stars` env var into `maintenance_research_tick`

**Files:**
- Modify: `src/atlas/core/orchestrator_parts/maintenance_facade.py` (`maintenance_research_tick`, line 844-940)
- Test: `tests/test_maintenance_research_tick.py` (check exact existing filename first — if a test already covers this tick, extend it instead of creating new)

**Interfaces:**
- Consumes: `TopicExpander.expand_detailed` (already exists), `PanoramaScout(topic_seeds=..., min_stars=...)` (Tasks 2-3).
- Produces: `maintenance_research_tick()` return dict unchanged in shape; report on disk now carries seeds.

- [ ] **Step 1: Check for an existing test file**

Run: `ls tests/ | grep -i research_tick`

If a file like `tests/test_maintenance_research_tick.py` exists, open it and follow its existing fixture pattern (fake `hub`, fake `LessonStore`, tmp `docs/inbox`) for the new test below. If none exists, create `tests/test_maintenance_research_tick.py` following the fixture style of `tests/test_mcp_reseed_tick.py` (same facade, same `Orchestrator`-construction pattern).

- [ ] **Step 2: Write the failing test**

```python
def test_research_tick_report_contains_seed_lines(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_RESEARCH", "1")
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))
    # ... build Orchestrator/facade per existing fixture conventions in this file ...
    result = facade.maintenance_research_tick()
    assert result["status"] == "ran"
    report_path = tmp_path / "docs" / "inbox" / f"research_{result_today}.md"
    text = report_path.read_text(encoding="utf-8")
    # at least one finding must carry its originating seed through
    if "### [" in text:
        assert "- seed:" in text
```

(fill in the `# ...` construction block by copying the exact `Orchestrator`/facade/fake-fetch/fake-hub setup already used by the sibling tick tests in this same file or in `tests/test_mcp_reseed_tick.py` — do not invent a different fixture shape)

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_maintenance_research_tick.py -k seed_lines -v`
Expected: FAIL — no `- seed:` in output (facade still calls `expand()`, not `expand_detailed()`)

- [ ] **Step 4: Write minimal implementation**

In `maintenance_research_tick`, replace:

```python
        expander = TopicExpander(hub=hub, merkle=orch._merkle)
        queries = expander.expand(seeds, queries_per_seed=4)

        scout = PanoramaScout(
            merkle=orch._merkle,
            bridge=orch._ssrf_bridge,
            fetch=_egress_fetch_text,
            topics=queries,
            max_results_per_topic=4,
        )
```

with:

```python
        expander = TopicExpander(hub=hub, merkle=orch._merkle)
        expansions = expander.expand_detailed(seeds, queries_per_seed=4)
        queries: list[str] = []
        topic_seeds: dict[str, str] = {}
        seen: set[str] = set()
        for expansion in expansions:
            for q in expansion.queries:
                if q not in seen:
                    seen.add(q)
                    queries.append(q)
                    topic_seeds[q] = expansion.seed

        min_stars_env = os.environ.get("ATLAS_MCP_DISCOVERY_MIN_STARS", "5").strip()
        try:
            min_stars = int(min_stars_env)
        except ValueError:
            min_stars = 5

        scout = PanoramaScout(
            merkle=orch._merkle,
            bridge=orch._ssrf_bridge,
            fetch=_egress_fetch_text,
            topics=queries,
            max_results_per_topic=4,
            topic_seeds=topic_seeds,
            min_stars=min_stars,
        )
```

(this reproduces `expand()`'s exact dedupe-preserving-order behavior manually, since `expand_detailed` returns per-seed lists that must be flattened the same way)

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_maintenance_research_tick.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/atlas/core/orchestrator_parts/maintenance_facade.py tests/test_maintenance_research_tick.py
git commit -m "feat(discovery): wire expand_detailed + min-stars env into research tick"
```

---

### Task 6: `curated_sources.py` — load operator-submitted URLs as findings

**Files:**
- Create: `src/atlas/core/self_maintenance/curated_sources.py`
- Create: `docs/knowledge/curated_sources.yaml` (starter file, see Step 3)
- Test: `tests/test_curated_sources.py`

**Interfaces:**
- Consumes: `PanoramaFinding` (Task 2), `research_digest._GITHUB_REPO_RE`-equivalent extraction (duplicated here as a private regex to avoid a cross-module import cycle — `research_digest.py` does not import from `self_maintenance` submodules today).
- Produces: `load_curated_findings(path: Path) -> list[PanoramaFinding]`. Consumed by Task 7.

- [ ] **Step 1: Write the failing test**

Create `tests/test_curated_sources.py`:

```python
"""Tests for src/atlas/core/self_maintenance/curated_sources.py."""
from __future__ import annotations

from pathlib import Path

import yaml

from atlas.core.self_maintenance.curated_sources import load_curated_findings


def test_missing_file_returns_empty_list(tmp_path: Path) -> None:
    assert load_curated_findings(tmp_path / "nope.yaml") == []


def test_loads_github_url_as_finding(tmp_path: Path) -> None:
    path = tmp_path / "curated_sources.yaml"
    path.write_text(
        yaml.safe_dump(
            {"sources": [{"url": "https://github.com/vercel-labs/agent-skills", "note": "Vercel skills registry"}]}
        ),
        encoding="utf-8",
    )
    findings = load_curated_findings(path)
    assert len(findings) == 1
    f = findings[0]
    assert f.source == "github"
    assert f.title == "vercel-labs/agent-skills"
    assert f.url == "https://github.com/vercel-labs/agent-skills"
    assert f.excerpt == "Vercel skills registry"
    assert f.topic == "curated: Vercel skills registry"


def test_non_github_url_is_skipped(tmp_path: Path) -> None:
    path = tmp_path / "curated_sources.yaml"
    path.write_text(
        yaml.safe_dump({"sources": [{"url": "https://tododeia.com/community", "note": "directory site"}]}),
        encoding="utf-8",
    )
    assert load_curated_findings(path) == []


def test_malformed_yaml_fails_closed_to_empty(tmp_path: Path) -> None:
    path = tmp_path / "curated_sources.yaml"
    path.write_text("not: [valid, yaml:", encoding="utf-8")
    assert load_curated_findings(path) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_curated_sources.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'atlas.core.self_maintenance.curated_sources'`

- [ ] **Step 3: Write minimal implementation**

Create `src/atlas/core/self_maintenance/curated_sources.py`:

```python
"""Fuentes curadas por el operador -- URLs sueltas que el operador ya vetó al
traerlas (registro MCP de Vercel, un repo que vio en otro sitio) y quiere que
compitan en el MISMO embudo de descubrimiento que los hallazgos automáticos
de ``PanoramaScout`` (decisión explícita del operador, 2026-07-25: sin atajo
de confianza).

Restricción deliberada: solo URLs ``github.com/<owner>/<repo>`` -- mismo
requisito que ``research_digest.digest_findings`` (``source == "github"`` es
lo único que cuenta). Sitios directorio/agregador (tododeia.com y similares)
son para que el operador los explore él mismo y traiga repos concretos, no
entradas que la máquina pueda digerir directamente.

Fail-closed: fichero ausente o YAML malformado -> lista vacía, nunca excepción
propagada (esto es un input opcional del operador, no una ruta crítica)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from atlas.core.self_maintenance.panorama_scout import PanoramaFinding

_GITHUB_REPO_RE = re.compile(r"github\.com/([\w.-]+/[\w.-]+?)(?:\.git)?(?:[/?#]|\s|$)", re.IGNORECASE)


def load_curated_findings(path: Path) -> list[PanoramaFinding]:
    """Lee ``path`` (formato ``{sources: [{url, note}]}``) y devuelve un
    ``PanoramaFinding`` por cada URL de GitHub válida. URLs no-GitHub se
    omiten silenciosamente (no son candidatos digeribles hoy)."""
    if not path.is_file():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return []
    sources = data.get("sources", []) if isinstance(data, dict) else []
    findings: list[PanoramaFinding] = []
    for entry in sources:
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url", "")).strip()
        note = str(entry.get("note", "")).strip()
        m = _GITHUB_REPO_RE.search(url)
        if not m:
            continue
        findings.append(
            PanoramaFinding(
                topic=f"curated: {note}" if note else "curated",
                source="github",
                title=m.group(1),
                url=url,
                excerpt=note,
            )
        )
    return findings
```

Create the starter `docs/knowledge/curated_sources.yaml`:

```yaml
# Fuentes curadas por el operador -- se leen en cada ciclo de
# maintenance_research_tick y compiten en el MISMO embudo de vetting que
# los hallazgos automáticos (research_digest.py), sin atajo de confianza.
# Solo URLs github.com/<owner>/<repo> -- ver curated_sources.py docstring.
sources: []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_curated_sources.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/atlas/core/self_maintenance/curated_sources.py tests/test_curated_sources.py docs/knowledge/curated_sources.yaml
git commit -m "feat(discovery): load operator-curated GitHub URLs as findings"
```

---

### Task 7: Wire curated findings into `maintenance_research_tick`

**Files:**
- Modify: `src/atlas/core/orchestrator_parts/maintenance_facade.py` (`maintenance_research_tick`)
- Test: `tests/test_maintenance_research_tick.py` (extend, same file as Task 5)

**Interfaces:**
- Consumes: `load_curated_findings` (Task 6).
- Produces: `findings` list in the tick now includes curated entries alongside `scout.discover()` results.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_maintenance_research_tick.py`:

```python
def test_research_tick_includes_curated_findings(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_RESEARCH", "1")
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))
    curated_path = tmp_path / "docs" / "knowledge" / "curated_sources.yaml"
    curated_path.parent.mkdir(parents=True, exist_ok=True)
    curated_path.write_text(
        "sources:\n  - url: https://github.com/vercel-labs/agent-skills\n    note: Vercel skills\n",
        encoding="utf-8",
    )
    # ... same Orchestrator/facade fixture as Task 5 ...
    result = facade.maintenance_research_tick()
    report_path = tmp_path / "docs" / "inbox" / f"research_{result['seeds'] and today}.md"
    text = report_path.read_text(encoding="utf-8")
    assert "vercel-labs/agent-skills" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_maintenance_research_tick.py -k curated -v`
Expected: FAIL — curated entry absent from report

- [ ] **Step 3: Write minimal implementation**

In `maintenance_research_tick`, after `findings = scout.discover()`, add:

```python
        from atlas.core.self_maintenance.curated_sources import load_curated_findings

        curated_path = self._project_root() / "docs" / "knowledge" / "curated_sources.yaml"
        findings = findings + load_curated_findings(curated_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_maintenance_research_tick.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/atlas/core/orchestrator_parts/maintenance_facade.py tests/test_maintenance_research_tick.py
git commit -m "feat(discovery): include curated sources in research tick findings"
```

---

### Task 8: Aggregate seeds into `CandidateSuggestion` in `research_digest.py`

**Files:**
- Modify: `src/atlas/core/self_maintenance/research_digest.py` (`_Aggregate` dataclass, `CandidateSuggestion` dataclass, `digest_findings`)
- Test: `tests/test_research_digest.py`

**Interfaces:**
- Consumes: `Finding.seed` (Task 1).
- Produces: `CandidateSuggestion.seeds: tuple[str, ...]` — the distinct non-empty seeds across all findings aggregated into this candidate. Consumed by Task 9 (quality gate `JudgeContext`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_research_digest.py`:

```python
def test_digest_findings_aggregates_seeds_across_reports() -> None:
    report_a = textwrap.dedent(
        """\
        ### [github] acme/mempalace
        - tema: temporal knowledge graph
        - seed: memoria de agentes de IA
        - url: https://github.com/acme/mempalace
        """
    )
    report_b = textwrap.dedent(
        """\
        ### [github] acme/mempalace
        - tema: agent memory benchmark
        - seed: memoria de agentes de IA
        - url: https://github.com/acme/mempalace
        """
    )
    suggestions = digest_findings([report_a, report_b], [], _TAXONOMY)
    assert len(suggestions) == 1
    assert suggestions[0].seeds == ("memoria de agentes de IA",)


def test_digest_findings_seeds_empty_when_none_present() -> None:
    suggestions = digest_findings([_REAL_REPORT_FRAGMENT, _REAL_REPORT_FRAGMENT], [], _TAXONOMY)
    assert all(s.seeds == () for s in suggestions)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_research_digest.py -k seeds -v`
Expected: FAIL — `AttributeError: 'CandidateSuggestion' object has no attribute 'seeds'`

- [ ] **Step 3: Write minimal implementation**

Add `seeds: set[str] = field(default_factory=set)` to `_Aggregate`:

```python
@dataclass
class _Aggregate:
    url: str = ""
    topics: set[str] = field(default_factory=set)
    reports: set[int] = field(default_factory=set)
    excerpts: list[str] = field(default_factory=list)
    seeds: set[str] = field(default_factory=set)
```

Add `seeds: tuple[str, ...] = ()` to `CandidateSuggestion` (after `evidence`):

```python
@dataclass(frozen=True)
class CandidateSuggestion:
    name: str
    url: str
    sector: str
    kind: str
    evidence: tuple[str, ...]
    status: str = "candidato"
    seeds: tuple[str, ...] = ()
```

In `digest_findings`'s aggregation loop, capture the seed:

```python
            if finding.topic:
                agg.topics.add(finding.topic)
            agg.reports.add(report_idx)
            if finding.excerpt:
                agg.excerpts.append(finding.excerpt)
            if finding.seed:
                agg.seeds.add(finding.seed)
```

And when building the suggestion, pass it through:

```python
        suggestions.append(
            CandidateSuggestion(
                name=name,
                url=agg.url,
                sector=sector,
                kind=kind,
                evidence=evidence,
                seeds=tuple(sorted(agg.seeds)),
            )
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_research_digest.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/atlas/core/self_maintenance/research_digest.py tests/test_research_digest.py
git commit -m "feat(discovery): aggregate originating seeds into CandidateSuggestion"
```

---

### Task 9: `mcp_discovery_quality_gate.py` — dual-anchor LLM judge

**Files:**
- Create: `src/atlas/core/self_maintenance/mcp_discovery_quality_gate.py`
- Test: `tests/test_mcp_discovery_quality_gate.py`

**Interfaces:**
- Consumes: `CandidateSuggestion` (Task 8, needs `.seeds`), `CatalogEntry` (existing, from `atlas.mcp.catalog`).
- Produces: `QualityVerdict`, `JudgeFn`, `build_llm_judge_fn(hub) -> JudgeFn`, `summarize_catalog_capabilities(catalog: list[CatalogEntry]) -> str`, `run_quality_gate(suggestions: list[CandidateSuggestion], *, capability_summary: str, judge_fn: JudgeFn) -> list[CandidateSuggestion]`. Consumed by Task 10.

- [ ] **Step 1: Write the failing test**

Create `tests/test_mcp_discovery_quality_gate.py`:

```python
"""Tests for mcp_discovery_quality_gate.py (2026-07-25) -- veredicto de
calidad/relevancia ancla-doble (seed original + huecos reales de Atlas)
antes de que un CandidateSuggestion llegue al catálogo. Fail-closed: un
fallo del juez excluye el candidato, no lo aprueba por defecto."""
from __future__ import annotations

from atlas.core.self_maintenance.mcp_discovery_quality_gate import (
    QualityVerdict,
    run_quality_gate,
    summarize_catalog_capabilities,
)
from atlas.core.self_maintenance.research_digest import CandidateSuggestion
from atlas.mcp.catalog import CatalogEntry


def _candidate(name: str, seeds: tuple[str, ...] = ()) -> CandidateSuggestion:
    return CandidateSuggestion(
        name=name, url=f"https://github.com/{name}", sector="s", kind="tool",
        evidence=("tema:x",), seeds=seeds,
    )


def test_passes_when_real_and_relevant() -> None:
    def judge(candidate, context):
        return QualityVerdict(real_mantenido=True, relevante_al_seed=True, cubre_hueco_real=True, motivo="ok")

    result = run_quality_gate([_candidate("acme/good")], capability_summary="s: 1", judge_fn=judge)
    assert len(result) == 1


def test_excluded_when_not_real_mantenido() -> None:
    def judge(candidate, context):
        return QualityVerdict(real_mantenido=False, relevante_al_seed=True, cubre_hueco_real=False, motivo="toy repo")

    result = run_quality_gate([_candidate("acme/toy")], capability_summary="s: 1", judge_fn=judge)
    assert result == []


def test_excluded_when_not_relevant() -> None:
    def judge(candidate, context):
        return QualityVerdict(real_mantenido=True, relevante_al_seed=False, cubre_hueco_real=False, motivo="off-topic")

    result = run_quality_gate([_candidate("acme/offtopic")], capability_summary="s: 1", judge_fn=judge)
    assert result == []


def test_kept_even_without_gap_when_real_and_relevant() -> None:
    """cubre_hueco_real NO es gate -- solo señal para el humano revisor."""
    def judge(candidate, context):
        return QualityVerdict(real_mantenido=True, relevante_al_seed=True, cubre_hueco_real=False, motivo="redundant but fine")

    result = run_quality_gate([_candidate("acme/redundant")], capability_summary="s: 1", judge_fn=judge)
    assert len(result) == 1


def test_judge_exception_fails_closed_excludes_candidate() -> None:
    def crashing_judge(candidate, context):
        raise RuntimeError("LLM caído")

    result = run_quality_gate([_candidate("acme/x")], capability_summary="s: 1", judge_fn=crashing_judge)
    assert result == []


def test_judge_receives_seed_in_context() -> None:
    seen_context = {}

    def judge(candidate, context):
        seen_context["seed"] = context.seed
        return QualityVerdict(real_mantenido=True, relevante_al_seed=True, cubre_hueco_real=True, motivo="ok")

    run_quality_gate(
        [_candidate("acme/x", seeds=("memoria de agentes de IA",))],
        capability_summary="s: 1",
        judge_fn=judge,
    )
    assert seen_context["seed"] == "memoria de agentes de IA"


def test_summarize_catalog_capabilities_counts_by_sector_installed_and_verified() -> None:
    catalog = [
        CatalogEntry(name="a", sector="conocimiento-memoria", sector_label="Conocimiento", kind="mcp",
                     purpose="", source="", install="", status="instalado", tags=[], mode="connected"),
        CatalogEntry(name="b", sector="conocimiento-memoria", sector_label="Conocimiento", kind="mcp",
                     purpose="", source="", install="", status="verificado", tags=[], mode="connected"),
        CatalogEntry(name="c", sector="conocimiento-memoria", sector_label="Conocimiento", kind="mcp",
                     purpose="", source="", install="", status="candidato", tags=[], mode="connected"),
    ]
    summary = summarize_catalog_capabilities(catalog)
    assert "conocimiento-memoria" in summary
    assert "2" in summary  # instalado + verificado, candidato no cuenta
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_mcp_discovery_quality_gate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'atlas.core.self_maintenance.mcp_discovery_quality_gate'`

- [ ] **Step 3: Write minimal implementation**

Create `src/atlas/core/self_maintenance/mcp_discovery_quality_gate.py`:

```python
"""Veredicto de calidad/relevancia para candidatos de descubrimiento MCP
(2026-07-25) -- pieza 3b de la spec de precisión del discovery. Se ejecuta
DESPUÉS de ``research_digest.digest_findings`` (que sigue puro, sin LLM) y
ANTES de ``append_candidates_to_catalog``. Mismo patrón de inyección que
``security_council_gate.py``: ``judge_fn`` inyectable, ``build_llm_judge_fn``
para producción, fail-closed -- un fallo del juez excluye el candidato, no
lo aprueba por defecto (nada se pierde permanentemente: reaparece si vuelve
a tener señal en un ciclo futuro).

El juicio compara contra DOS anclas: el seed amplio original que generó el
hallazgo (no la query corta expandida -- evita el circular "tree traversal"
-> java-bst), y un resumen compacto de lo que Atlas ya tiene instalado, para
que el humano que revise ``vetted`` sepa si el candidato llena un hueco real
o es redundante. ``cubre_hueco_real`` NO es un gate duro -- solo evidencia
registrada; los gates duros son ``real_mantenido`` y ``relevante_al_seed``."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable

from atlas.core.self_maintenance.research_digest import CandidateSuggestion
from atlas.mcp.catalog import CatalogEntry

_COUNTED_STATUSES = {"instalado", "verificado"}


@dataclass(frozen=True)
class JudgeContext:
    seed: str
    capability_summary: str


@dataclass(frozen=True)
class QualityVerdict:
    real_mantenido: bool
    relevante_al_seed: bool
    cubre_hueco_real: bool
    motivo: str = ""


JudgeFn = Callable[[CandidateSuggestion, JudgeContext], QualityVerdict]


def summarize_catalog_capabilities(catalog: list[CatalogEntry]) -> str:
    """Resumen compacto ``sector: N`` de lo ya ``instalado``/``verificado``
    (candidato no cuenta) -- ancla de "huecos reales" para el juez."""
    counts: Counter[str] = Counter(
        entry.sector for entry in catalog if entry.status in _COUNTED_STATUSES
    )
    if not counts:
        return "Atlas no tiene aún nada instalado/verificado en el catálogo."
    return "; ".join(f"{sector}: {n}" for sector, n in sorted(counts.items()))


_JUDGE_PROMPT = (
    "Eres un evaluador de calidad de candidatos de catálogo para un sistema "
    "de IA local (Atlas). Responde en las primeras 3 líneas, EXACTAMENTE en "
    "este formato (SI o NO literal, sin puntuación extra):\n"
    "REAL: SI|NO\n"
    "RELEVANTE: SI|NO\n"
    "HUECO: SI|NO\n"
    "Después, en una línea más, explica brevemente por qué.\n\n"
    "CANDIDATO: {name} ({url})\n"
    "INTERÉS AMPLIO que originó la búsqueda: {seed}\n"
    "LO QUE ATLAS YA TIENE instalado/verificado por sector: {capability_summary}\n\n"
    "REAL = ¿es un proyecto real y mantenido, no un toy de un solo commit?\n"
    "RELEVANTE = ¿sirve genuinamente para el interés amplio de arriba (no solo "
    "coincidencia de palabras sueltas)?\n"
    "HUECO = ¿llena algo que Atlas no tiene ya cubierto?\n"
)


def build_llm_judge_fn(hub: Any) -> JudgeFn:
    """Construye el juez LLM único (barato) a partir de un ``InferenceHub``
    ya configurado -- una sola llamada por candidato ya deduplicado."""

    def judge(candidate: CandidateSuggestion, context: JudgeContext) -> QualityVerdict:
        from atlas.core.inference_hub import InferenceRequest

        prompt = _JUDGE_PROMPT.format(
            name=candidate.name, url=candidate.url,
            seed=context.seed or "(sin seed registrado)",
            capability_summary=context.capability_summary,
        )
        resp = hub.infer(InferenceRequest(prompt=prompt))
        if not resp.success or not resp.text.strip():
            raise RuntimeError("juez LLM sin respuesta")
        lines = [l.strip() for l in resp.text.strip().splitlines() if l.strip()]

        def _flag(prefix: str) -> bool:
            for line in lines:
                if line.upper().startswith(prefix):
                    return "SI" in line.upper()
            return False

        real = _flag("REAL")
        relevante = _flag("RELEVANTE")
        hueco = _flag("HUECO")
        motivo = lines[3] if len(lines) > 3 else resp.text.strip()
        return QualityVerdict(
            real_mantenido=real, relevante_al_seed=relevante, cubre_hueco_real=hueco, motivo=motivo,
        )

    return judge


def run_quality_gate(
    suggestions: list[CandidateSuggestion], *, capability_summary: str, judge_fn: JudgeFn
) -> list[CandidateSuggestion]:
    """Filtra ``suggestions`` -- gate duro: ``real_mantenido AND
    relevante_al_seed``. ``cubre_hueco_real`` nunca excluye, solo queda
    disponible en el ``motivo`` para el humano que revise ``vetted``.
    Fail-closed: una excepción del juez excluye ESE candidato, no lo aprueba."""
    kept: list[CandidateSuggestion] = []
    for candidate in suggestions:
        seed = candidate.seeds[0] if candidate.seeds else ""
        context = JudgeContext(seed=seed, capability_summary=capability_summary)
        try:
            verdict = judge_fn(candidate, context)
        except Exception:  # noqa: BLE001 -- fail-closed, no fail-open
            continue
        if verdict.real_mantenido and verdict.relevante_al_seed:
            kept.append(candidate)
    return kept
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_mcp_discovery_quality_gate.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/atlas/core/self_maintenance/mcp_discovery_quality_gate.py tests/test_mcp_discovery_quality_gate.py
git commit -m "feat(discovery): add dual-anchor LLM quality gate for MCP candidates"
```

---

### Task 10: Wire the quality gate into `maintenance_knowledge_ingest_tick`

**Files:**
- Modify: `src/atlas/core/orchestrator_parts/maintenance_facade.py` (`maintenance_knowledge_ingest_tick`, digestion block at line 1164-1192)
- Test: `tests/test_mcp_vetting_tick.py` or a new `tests/test_maintenance_knowledge_ingest_tick.py` if the digestion block has no dedicated test today (check first)

**Interfaces:**
- Consumes: `run_quality_gate`, `build_llm_judge_fn`, `summarize_catalog_capabilities` (Task 9).
- Produces: `digested` count in the tick's payload now reflects post-gate suggestions only.

- [ ] **Step 1: Check for existing coverage**

Run: `grep -rn "digest_findings\|append_candidates_to_catalog" tests/*.py`

Open whichever test file already exercises `maintenance_knowledge_ingest_tick`'s digestion step and extend it; if none, create `tests/test_maintenance_knowledge_ingest_tick.py` following the same `Orchestrator` construction pattern used by `tests/test_mcp_vetting_tick.py`.

- [ ] **Step 2: Write the failing test**

```python
def test_ingest_tick_excludes_candidates_rejected_by_quality_gate(tmp_path, monkeypatch) -> None:
    # Arrange: a research report with a candidate that appears twice (passes
    # digest_findings signal), and a fake InferenceHub whose response always
    # says REAL: NO (so the gate must reject it).
    # ... build root layout: docs/design/mcp_catalog.yaml, mcp_catalog_classified.yaml,
    #     docs/knowledge/research_2026-07-25.md with 2 sections for the same repo ...
    monkeypatch.setenv("ATLAS_KNOWLEDGE_INGEST", "1")
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))
    # inject a fake hub on the Orchestrator that always returns "REAL: NO\nRELEVANTE: SI\nHUECO: NO\nno"
    result = facade.maintenance_knowledge_ingest_tick()
    assert result["digested_candidates"] == 0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_maintenance_knowledge_ingest_tick.py -k quality_gate -v`
Expected: FAIL — `digested_candidates` is `1`, not `0` (gate not wired yet)

- [ ] **Step 4: Write minimal implementation**

In the digestion `try` block inside `maintenance_knowledge_ingest_tick`, insert the gate call between `digest_findings` and `append_candidates_to_catalog`:

```python
                suggestions = digest_findings(
                    reports, catalog, load_taxonomy(catalog_path)
                )
                if suggestions:
                    from atlas.core.inference_hub import InferenceHub
                    from atlas.core.self_maintenance.mcp_discovery_quality_gate import (
                        build_llm_judge_fn, run_quality_gate, summarize_catalog_capabilities,
                    )

                    gate_hub = self._orch._inference_hub or InferenceHub(mode="auto")
                    suggestions = run_quality_gate(
                        suggestions,
                        capability_summary=summarize_catalog_capabilities(catalog),
                        judge_fn=build_llm_judge_fn(gate_hub),
                    )
                if suggestions and classified_path.is_file():
                    digested = append_candidates_to_catalog(suggestions, classified_path)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_maintenance_knowledge_ingest_tick.py -v`
Expected: all PASS

- [ ] **Step 6: Run the full existing suite for this area to check no regression**

Run: `.venv/bin/python -m pytest tests/test_research_digest.py tests/test_panorama_scout.py tests/test_mcp_vetting_tick.py tests/test_mcp_reseed_tick.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add src/atlas/core/orchestrator_parts/maintenance_facade.py tests/test_maintenance_knowledge_ingest_tick.py
git commit -m "feat(discovery): wire quality gate into knowledge ingest tick before catalog append"
```

---

### Task 11: `scripts/mcp_catalog_reset_candidates.py` — one-time cleanup (manual only)

**Files:**
- Create: `scripts/mcp_catalog_reset_candidates.py`
- Test: `tests/test_mcp_catalog_reset_candidates.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (standalone script operating directly on the YAML structure).
- Produces: `filter_out_candidates(data: dict) -> tuple[dict, int]` (pure, testable) + a thin CLI `main()` with `--dry-run` (default) / `--apply`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_mcp_catalog_reset_candidates.py`:

```python
"""Tests for scripts/mcp_catalog_reset_candidates.py (piece 4, manual-only
cleanup -- run ONCE after the discovery-precision pipeline is in production,
never wired into the scheduler)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "mcp_catalog_reset_candidates.py"
_spec = importlib.util.spec_from_file_location("mcp_catalog_reset_candidates", _SCRIPT_PATH)
assert _spec and _spec.loader
reset_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reset_mod)


def test_filter_out_candidates_removes_only_candidato_status() -> None:
    data = {
        "sectors": {
            "s1": {
                "label": "S1",
                "entries": [
                    {"name": "a", "status": "instalado"},
                    {"name": "b", "status": "candidato"},
                    {"name": "c", "status": "verificado"},
                    {"name": "d", "status": "candidato"},
                ],
            }
        }
    }
    filtered, removed_count = reset_mod.filter_out_candidates(data)
    names = [e["name"] for e in filtered["sectors"]["s1"]["entries"]]
    assert names == ["a", "c"]
    assert removed_count == 2


def test_filter_out_candidates_preserves_sectors_with_no_candidates() -> None:
    data = {"sectors": {"s1": {"label": "S1", "entries": [{"name": "a", "status": "instalado"}]}}}
    filtered, removed_count = reset_mod.filter_out_candidates(data)
    assert filtered == data
    assert removed_count == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_mcp_catalog_reset_candidates.py -v`
Expected: FAIL — script file does not exist yet, `spec_from_file_location` returns a spec with no loader / import error

- [ ] **Step 3: Write minimal implementation**

Create `scripts/mcp_catalog_reset_candidates.py`:

```python
#!/usr/bin/env python3
"""Barrido de limpieza MANUAL (pieza 4, spec 2026-07-25-mcp-discovery-
precision-design.md): vacía los candidatos del pipeline de discovery VIEJO
(sin filtro de estrellas ni juicio LLM) de docs/design/mcp_catalog_classified.yaml,
preservando intactas las entradas ya instaladas/verificadas.

NUNCA se ejecuta automáticamente -- correrlo antes de que las piezas 1-3
(fuentes curadas, filtro de estrellas, veredicto LLM ancla-doble) estén en
producción dejaría al daemon (ATLAS_MCP_RESEED/ATLAS_MCP_VETTING) rellenando
el catálogo otra vez con la lógica vieja.

Uso:
    .venv/bin/python scripts/mcp_catalog_reset_candidates.py \\
        docs/design/mcp_catalog_classified.yaml --dry-run   # solo cuenta
    .venv/bin/python scripts/mcp_catalog_reset_candidates.py \\
        docs/design/mcp_catalog_classified.yaml --apply     # escribe de verdad
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml


def filter_out_candidates(data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Devuelve una copia de ``data`` sin entradas ``status == 'candidato'``
    en ningún sector, y cuántas se quitaron en total. No muta ``data``."""
    removed = 0
    sectors = data.get("sectors", {})
    new_sectors: dict[str, Any] = {}
    for sector_name, block in sectors.items():
        entries = block.get("entries", [])
        kept = [e for e in entries if e.get("status") != "candidato"]
        removed += len(entries) - len(kept)
        new_block = dict(block)
        new_block["entries"] = kept
        new_sectors[sector_name] = new_block
    new_data = dict(data)
    new_data["sectors"] = new_sectors
    return new_data, removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("classified_path", type=Path)
    parser.add_argument("--apply", action="store_true", help="Escribe de verdad (default: dry-run, solo cuenta)")
    args = parser.parse_args(argv)

    data = yaml.safe_load(args.classified_path.read_text(encoding="utf-8")) or {}
    filtered, removed = filter_out_candidates(data)

    print(f"Candidatos a eliminar: {removed}")
    if not args.apply:
        print("Dry-run (sin --apply): no se ha escrito nada.")
        return 0

    args.classified_path.write_text(
        yaml.safe_dump(filtered, allow_unicode=True, sort_keys=False), encoding="utf-8",
    )
    print(f"Escrito. {removed} candidatos eliminados de {args.classified_path}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_mcp_catalog_reset_candidates.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/mcp_catalog_reset_candidates.py tests/test_mcp_catalog_reset_candidates.py
git commit -m "feat(discovery): add manual one-time candidate-reset cleanup script"
```

**Note for the operator (not a plan step):** do NOT run this script with `--apply` until Tasks 1-10 are merged and the daemon has been restarted (`systemctl --user restart atlas-core.service`) so it's running the new pipeline. Running it earlier just lets the old noisy logic refill the catalog on the next reseed/vetting tick.

---

## Final Verification (after all 11 tasks)

- [ ] Run the full suite: `.venv/bin/python -m pytest -q -m "not computer_use"` — expect the pre-existing 4484 passed count plus all new tests, 0 failures.
- [ ] Run `mypy` on every touched file: `.venv/bin/mypy src/atlas/core/self_maintenance/research_digest.py src/atlas/core/self_maintenance/panorama_scout.py src/atlas/core/self_maintenance/curated_sources.py src/atlas/core/self_maintenance/mcp_discovery_quality_gate.py src/atlas/core/orchestrator_parts/maintenance_facade.py scripts/mcp_catalog_reset_candidates.py`
- [ ] Update `docs/design/atlas_ecosystem_map.md` and `docs/INDEX.yaml` for the new modules (repo convention — checked by `sanitation_audit`).
- [ ] Update `WORK_LEDGER.md` with a summary entry.
