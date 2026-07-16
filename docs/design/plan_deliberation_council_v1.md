# Cónclave (`deliberation_council`) v1 — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: usa superpowers:subagent-driven-development
> (recomendado) o superpowers:executing-plans para implementar tarea a tarea. Los pasos usan
> checkbox (`- [ ]`).

**Goal:** Un skill de deliberación usable: por defecto juez-único (prosa, cero código nuevo);
escalada real al trío Gemini/Kimi/Mistral sobre `adversarial_panel` cuando la apuesta lo merece.

**Architecture:** Dos fases secuenciales y ambas validables por separado. **Fase A** entrega el
skill de prosa (protocolo de 4 pasos) — software útil ya, sin código. **Fase B** añade el
adaptador `LlmReviewer` que envuelve UN proveedor de `InferenceHub` y se ensambla en un trío de
linajes distintos, con gating por `should_convene` y veredicto `Evidence` (PASS/FAIL/UNKNOWN).

**Tech Stack:** Python 3.12, stdlib + `cryptography` (ya dep), `adversarial_panel.py` (ADR-047),
`inference_hub.py`, `cascade.Difficulty`, `core/verify.Evidence`. SQLite para el side-effect.

## Global Constraints

- Diseño fuente: `docs/design/design_deliberation_council.md`. Estado vivo: `WORK_LEDGER.md`.
- Manías obligatorias: `wire-before-claim` (no declarar "real" sin consumidor no-test + integración),
  `stdlib-over-new-deps` (cero deps nuevas sin ADR), `verify-the-real-case`, Reality First.
- DoD por tarea: tests verdes + mypy strict (`MYPYPATH=src python -m mypy src/atlas/`) + ledger
  actualizado en el mismo commit + nota honesta en CAPABILITIES.md al cerrar la fase.
- El pre-commit hook (`.githooks/pre-commit`) corre `pytest tests/ -q` completo: cada commit exige
  toda la suite verde.
- Comando de test: `PYTHONPATH=src .venv/bin/python -m pytest <ruta> -q`.
- Proveedores del trío (exactos, de `DEFAULT_PROVIDERS`): `gemini_free` (L1, 🇺🇸), `nvidia_kimi`
  (L2, moonshotai/kimi-k2.6, 🇨🇳), `nvidia_mistral_large` (L2, mistralai/mistral-large-3-675b, 🇪🇺).
- Diversidad obligatoria: el panel exige `min_providers>=3` para el trío; sin ello → UNKNOWN.

---

## Fase A — Skill de prosa (MVP juez-único, sin código)

### Task A1: Skill servido (fuente canónica versionada)

**Files:**
- Create: `docs/skills/deliberation_council.md`

**Interfaces:**
- Produces: el documento de skill que sirve el tronco (`SkillStore`) y refleja `.claude/skills`.

- [ ] **Step 1: Escribir el skill** con estas secciones EXACTAS (contenido, no placeholders):
  - Encabezado: nombre `deliberation_council`, alias "Cónclave", una frase de propósito.
  - **Cuándo se activa** (gating, en prosa): decisiones de arquitectura, stack, seguridad,
    irreversibles, o bugs atascados. NO para triviales/mecánicas. Palancas: `council: full|quick|off`.
  - **Protocolo de 4 pasos**: (1) Encuadre = reformular decisión + criterios de éxito + manías en
    juego; (2) Lentes = aplicar SOLO los Sombreros que la decisión pide (Negro riesgos + Verde
    alternativa quirúrgica por defecto; Blanco/Amarillo si aportan) — checklist, no liturgia;
    (3) Escalada = SOLO alto-riesgo/irreversible, convoca el trío (ver Fase B); si no hay
    diversidad mínima → UNKNOWN; (4) Síntesis honesta = mostrar el desacuerdo CRUDO antes de
    resumir; cerrar con recomendación + veredicto PASS/FAIL/UNKNOWN.
  - **Reglas = manías**: enumerar `honesty-over-sycophancy`, `decide-with-facts`,
    `internal-prior-art-first`, `wire-before-claim`, `verify-the-real-case`, Reality First.
  - **Auditoría**: NO tabla de ✅; el veredicto del paso 4 + nota corta de manías en juego.
- [ ] **Step 2: Verificar contenido** — confirmar que las 4 secciones del protocolo, el gating y
  las manías están presentes:
  Run: `grep -c "Encuadre\|Lentes\|Escalada\|Síntesis\|council:" docs/skills/deliberation_council.md`
  Expected: ≥ 5 coincidencias.
- [ ] **Step 3: Commit**
  ```bash
  git add docs/skills/deliberation_council.md
  git commit -m "feat(council): skill de deliberación servido (Fase A1)"
  ```

### Task A2: Espejo operativo `.claude/skills` + registro en catálogo

**Files:**
- Create: `.claude/skills/deliberation_council/SKILL.md` (frontmatter + cuerpo; NO versionado)
- Modify: el YAML de catálogo curado donde se registran skills servidos (mismo patrón que
  `atlas-coding-discipline`): `docs/design/mcp_catalog.yaml` o el curado equivalente.

**Interfaces:**
- Consumes: el contenido de `docs/skills/deliberation_council.md` (A1).
- Produces: skill autoseleccionable por Claude Code (frontmatter `description`) + entrada de
  catálogo `mode: served`.

- [ ] **Step 1: Localizar el patrón de registro** del skill existente:
  Run: `grep -rn "atlas-coding-discipline" docs/design/*.yaml`
  Expected: la entrada de catálogo (kind: skill, mode: served) a copiar como plantilla.
- [ ] **Step 2: Crear el SKILL.md operativo** con frontmatter:
  ```markdown
  ---
  name: deliberation_council
  description: Usar ante decisiones reales (arquitectura, stack, seguridad, irreversibles, bugs
    atascados) para deliberar y presionar puntos ciegos; escala al trío multi-modelo en alto riesgo.
  ---
  ```
  seguido del cuerpo de `docs/skills/deliberation_council.md`.
- [ ] **Step 3: Registrar en el catálogo** una entrada análoga a `atlas-coding-discipline`
  (kind: skill, mode: served, tags: ia-agentes + productividad-meta).
- [ ] **Step 4: Verificar** que el skill aparece vivo:
  Run: `.venv/bin/python -c "from atlas.mcp.skill_store import SkillStore" 2>&1 || echo "ver SkillStore"`
  y confirmar que `list_skills`/`get_skill` lo devuelven (o el equivalente del repo).
- [ ] **Step 5: Commit**
  ```bash
  git add docs/design/*.yaml .claude/skills/deliberation_council/SKILL.md
  git commit -m "feat(council): registro en catálogo + espejo .claude/skills (Fase A2)"
  ```

### Task A3: Versión portable degradada (claude.ai Projects)

**Files:**
- Create: `docs/skills/deliberation_council_portable.md`

- [ ] **Step 1: Escribir la versión copy-pega** = SOLO juez-único (Encuadre + Lentes + Síntesis
  honesta + manías). Declarar EXPLÍCITAMENTE al inicio: "Versión degradada — SIN trío; el web app
  no llega al pool NIM ni a adversarial_panel. Subconjunto, no equivalente."
- [ ] **Step 2: Verificar** la advertencia de degradación:
  Run: `grep -c "SIN trío\|degradada\|subconjunto" docs/skills/deliberation_council_portable.md`
  Expected: ≥ 1.
- [ ] **Step 3: Commit**
  ```bash
  git add docs/skills/deliberation_council_portable.md
  git commit -m "docs(council): versión portable degradada (Fase A3)"
  ```

**Checkpoint Fase A:** el Cónclave juez-único es usable. Validar en uso real ≥1 decisión antes de B.

---

## Fase B — Escalada real al trío (código, TDD)

### Task B1: `LlmReviewer` — Reviewer concreto sobre un proveedor

**Files:**
- Create: `src/atlas/core/deliberation_council.py`
- Test: `tests/test_deliberation_council.py`

**Interfaces:**
- Consumes: `Reviewer` Protocol, `Objection`, `Severity` de `atlas.core.adversarial_panel`;
  `InferenceHub`, `InferenceRequest`, `InferenceResponse`, `Provider`, `InferenceLevel` de
  `atlas.core.inference_hub`.
- Produces: `class LlmReviewer` con `reviewer_id: str`, `provider: str`,
  `review(diff: str, context: str = "") -> Objection`. Constructor:
  `LlmReviewer(reviewer_id: str, provider: str, hub: InferenceHub, level: InferenceLevel)`.
  Mapeo de respuesta → severidad: el prompt pide responder en 1ª línea con
  `NONE|MINOR|MAJOR|BLOCKING`; se parsea a `Severity`; resto = `detail`. Línea no reconocida →
  `Severity.MAJOR` (fail-closed: una objeción ilegible no se trata como "sin objeción").

- [ ] **Step 1: Escribir el test que falla**
```python
from atlas.core.adversarial_panel import Objection, Severity
from atlas.core.deliberation_council import LlmReviewer
from atlas.core.inference_hub import (
    InferenceHub, InferenceLevel, InferenceRequest, InferenceResponse, Provider,
)


class _FakeHub:
    """Hub falso: devuelve un texto fijo, registra el prompt recibido."""
    def __init__(self, text: str, success: bool = True) -> None:
        self._text = text
        self._success = success
        self.last_request: InferenceRequest | None = None

    def infer(self, request: InferenceRequest) -> InferenceResponse:
        self.last_request = request
        return InferenceResponse(
            text=self._text, provider="p", model="m",
            level=request.level, latency_ms=1, success=self._success,
        )


def test_review_parses_severity_and_detail() -> None:
    hub = _FakeHub("MAJOR\nAsume disponibilidad que no está probada.")
    r = LlmReviewer("kimi", "moonshot", hub, InferenceLevel.L2)
    obj = r.review("¿migrar a GraphQL?", context="200 endpoints")
    assert isinstance(obj, Objection)
    assert obj.severity == Severity.MAJOR
    assert "disponibilidad" in obj.detail
    assert obj.provider == "moonshot"


def test_review_unparseable_first_line_is_major_failclosed() -> None:
    hub = _FakeHub("bla bla sin etiqueta")
    r = LlmReviewer("g", "google", hub, InferenceLevel.L1)
    assert r.review("x").severity == Severity.MAJOR


def test_review_failed_inference_is_unknown_severity_none_blocked() -> None:
    # Una llamada fallida no puede contar como "sin objeción"; fail-closed a MAJOR.
    hub = _FakeHub("", success=False)
    r = LlmReviewer("g", "google", hub, InferenceLevel.L1)
    assert r.review("x").severity == Severity.MAJOR
```
- [ ] **Step 2: Correr el test y verificar que falla**
  Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_deliberation_council.py -q`
  Expected: FAIL (`ModuleNotFoundError: atlas.core.deliberation_council`).
- [ ] **Step 3: Implementación mínima**
```python
"""Cónclave — adaptador de deliberación multi-voz sobre adversarial_panel (ADR-047)."""
from __future__ import annotations

from atlas.core.adversarial_panel import Objection, Reviewer, Severity
from atlas.core.inference_hub import InferenceHub, InferenceLevel, InferenceRequest

_HOSTILE_PROMPT = (
    "Eres un revisor hostil. Ataca esta decisión: ¿qué rompe, qué asume falso, "
    "qué caso límite ignora? Responde en la PRIMERA línea SOLO con una de: "
    "NONE MINOR MAJOR BLOCKING. En las siguientes líneas, la objeción concreta.\n\n"
    "DECISIÓN:\n{diff}\n\nCONTEXTO:\n{context}\n"
)
_SEVERITIES = {s.name: s for s in Severity}


class LlmReviewer:
    """Reviewer concreto: envuelve UN proveedor de InferenceHub con prompt hostil."""

    def __init__(
        self, reviewer_id: str, provider: str, hub: InferenceHub, level: InferenceLevel,
    ) -> None:
        self._id = reviewer_id
        self._provider = provider
        self._hub = hub
        self._level = level

    @property
    def reviewer_id(self) -> str:
        return self._id

    @property
    def provider(self) -> str:
        return self._provider

    def review(self, diff: str, context: str = "") -> Objection:
        resp = self._hub.infer(InferenceRequest(
            prompt=_HOSTILE_PROMPT.format(diff=diff, context=context),
            level=self._level,
        ))
        if not resp.success or not resp.text.strip():
            return Objection(self._id, self._provider, Severity.MAJOR,
                             "revisión no disponible (fail-closed)")
        lines = resp.text.strip().splitlines()
        sev = _SEVERITIES.get(lines[0].strip().upper(), Severity.MAJOR)
        detail = "\n".join(lines[1:]).strip()
        return Objection(self._id, self._provider, sev, detail)
```
- [ ] **Step 4: Correr el test y verificar que pasa**
  Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_deliberation_council.py -q`
  Expected: PASS (3 tests).
- [ ] **Step 5: mypy + commit**
  ```bash
  MYPYPATH=src .venv/bin/python -m mypy src/atlas/core/deliberation_council.py
  git add src/atlas/core/deliberation_council.py tests/test_deliberation_council.py
  git commit -m "feat(council): LlmReviewer sobre un proveedor (Fase B1)"
  ```

### Task B2: `build_trio_reviewers` — ensamblar los 3 linajes

**Files:**
- Modify: `src/atlas/core/deliberation_council.py`
- Test: `tests/test_deliberation_council.py`

**Interfaces:**
- Produces: `build_trio_reviewers(providers: list[Provider] | None = None) -> list[LlmReviewer]`.
  Selecciona de `DEFAULT_PROVIDERS` (o `providers`) los `name` `gemini_free`, `nvidia_kimi`,
  `nvidia_mistral_large`; cada reviewer recibe un `InferenceHub(providers=[p])` de UN solo
  proveedor (así `infer` llama solo a ese) y su `level`. `provider` del reviewer = el `name`.

- [ ] **Step 1: Escribir el test que falla**
```python
def test_build_trio_has_three_distinct_providers() -> None:
    from atlas.core.deliberation_council import build_trio_reviewers
    trio = build_trio_reviewers()
    assert len(trio) == 3
    provs = {r.provider for r in trio}
    assert provs == {"gemini_free", "nvidia_kimi", "nvidia_mistral_large"}
```
- [ ] **Step 2: Correr y verificar fallo**
  Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_deliberation_council.py::test_build_trio_has_three_distinct_providers -q`
  Expected: FAIL (`build_trio_reviewers` no existe).
- [ ] **Step 3: Implementación**
```python
from atlas.core.inference_hub import DEFAULT_PROVIDERS, Provider

_TRIO_NAMES = ("gemini_free", "nvidia_kimi", "nvidia_mistral_large")


def build_trio_reviewers(providers: list[Provider] | None = None) -> list[LlmReviewer]:
    pool = {p.name: p for p in (providers or DEFAULT_PROVIDERS)}
    out: list[LlmReviewer] = []
    for name in _TRIO_NAMES:
        p = pool.get(name)
        if p is None:
            continue  # honesto: si falta un proveedor, el trío queda incompleto → UNKNOWN aguas abajo
        out.append(LlmReviewer(name, name, InferenceHub(providers=[p]), p.level))
    return out
```
- [ ] **Step 4: Correr y verificar paso**
  Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_deliberation_council.py -q`
  Expected: PASS (4 tests).
- [ ] **Step 5: mypy + commit**
  ```bash
  MYPYPATH=src .venv/bin/python -m mypy src/atlas/core/deliberation_council.py
  git add src/atlas/core/deliberation_council.py tests/test_deliberation_council.py
  git commit -m "feat(council): build_trio_reviewers (Fase B2)"
  ```

### Task B3: `convene_for_decision` — gating + panel + veredicto

**Files:**
- Modify: `src/atlas/core/deliberation_council.py`
- Test: `tests/test_deliberation_council.py`

**Interfaces:**
- Consumes: `should_convene`, `AdversarialPanel`, `Severity` (adversarial_panel);
  `Difficulty` (`atlas.router.cascade`); `Evidence`, `Verdict` (`atlas.core.verify`).
- Produces:
  `convene_for_decision(decision: str, context: str = "", *, difficulty: Difficulty,
   risk: str, irreversible: bool = False, reviewers: list[Reviewer] | None = None) -> Evidence | None`.
  Devuelve `None` si `should_convene` dice que NO (gating: lo trivial no quema modelos);
  si sí, corre `AdversarialPanel(reviewers or build_trio_reviewers(), min_providers=3).verify(...)`.

- [ ] **Step 1: Escribir el test que falla**
```python
def test_convene_returns_none_when_gating_says_skip() -> None:
    from atlas.router.cascade import Difficulty
    from atlas.core.deliberation_council import convene_for_decision
    out = convene_for_decision(
        "renombrar variable", difficulty=Difficulty.EASY, risk="low", irreversible=False,
    )
    assert out is None


def test_convene_runs_panel_on_high_risk() -> None:
    from atlas.router.cascade import Difficulty
    from atlas.core.adversarial_panel import Objection, Severity
    from atlas.core.verify import Verdict
    from atlas.core.deliberation_council import convene_for_decision

    class _Rev:
        def __init__(self, pid: str, prov: str, sev: Severity) -> None:
            self._id, self._prov, self._sev = pid, prov, sev
        @property
        def reviewer_id(self) -> str: return self._id
        @property
        def provider(self) -> str: return self._prov
        def review(self, diff: str, context: str = "") -> Objection:
            return Objection(self._id, self._prov, self._sev, "obj")

    trio = [_Rev("a", "p1", Severity.NONE), _Rev("b", "p2", Severity.NONE),
            _Rev("c", "p3", Severity.NONE)]
    ev = convene_for_decision(
        "¿migrar a GraphQL?", difficulty=Difficulty.HARD, risk="high", reviewers=trio,
    )
    assert ev is not None and ev.verdict == Verdict.PASS


def test_convene_unknown_when_diversity_insufficient() -> None:
    from atlas.router.cascade import Difficulty
    from atlas.core.adversarial_panel import Objection, Severity
    from atlas.core.verify import Verdict
    from atlas.core.deliberation_council import convene_for_decision

    class _Rev:
        @property
        def reviewer_id(self) -> str: return "a"
        @property
        def provider(self) -> str: return "same"  # mismo provider x2 → < 3 distintos
        def review(self, diff: str, context: str = "") -> Objection:
            return Objection("a", "same", Severity.NONE, "")

    ev = convene_for_decision(
        "x", difficulty=Difficulty.HARD, risk="high", reviewers=[_Rev(), _Rev()],
    )
    assert ev is not None and ev.verdict == Verdict.UNKNOWN
```
- [ ] **Step 2: Correr y verificar fallo**
  Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_deliberation_council.py -q`
  Expected: FAIL (`convene_for_decision` no existe).
- [ ] **Step 3: Implementación**
```python
from atlas.core.adversarial_panel import AdversarialPanel, Reviewer, should_convene
from atlas.core.verify import Evidence
from atlas.router.cascade import Difficulty


def convene_for_decision(
    decision: str,
    context: str = "",
    *,
    difficulty: Difficulty,
    risk: str,
    irreversible: bool = False,
    reviewers: list[Reviewer] | None = None,
) -> Evidence | None:
    if not should_convene(difficulty, risk, irreversible=irreversible):
        return None
    panel = AdversarialPanel(reviewers or build_trio_reviewers(), min_providers=3)
    return panel.verify(decision, context)
```
- [ ] **Step 4: Correr y verificar paso**
  Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_deliberation_council.py -q`
  Expected: PASS (7 tests).
- [ ] **Step 5: mypy + commit**
  ```bash
  MYPYPATH=src .venv/bin/python -m mypy src/atlas/core/deliberation_council.py
  git add src/atlas/core/deliberation_council.py tests/test_deliberation_council.py
  git commit -m "feat(council): convene_for_decision con gating + diversidad (Fase B3)"
  ```

### Task B4: Side-effect de registro (destilación, mínimo)

**Files:**
- Modify: `src/atlas/core/deliberation_council.py`
- Test: `tests/test_deliberation_council.py`

**Interfaces:**
- Produces: `record_synthesis(recorder, decision: str, evidence: Evidence) -> None` — escribe el
  veredicto + razonamiento legible vía un `recorder` inyectable (Protocol con un único método
  `record(text: str) -> None`). Mantener inyectable evita acoplar a la firma concreta de
  `LessonStore` en v1 (se cablea al recorder real cuando se valide; `wire-before-claim`).

- [ ] **Step 1: Escribir el test que falla**
```python
def test_record_synthesis_writes_verdict_and_reason() -> None:
    from atlas.core.verify import Evidence, Verdict
    from atlas.core.deliberation_council import record_synthesis

    class _Rec:
        def __init__(self) -> None: self.entries: list[str] = []
        def record(self, text: str) -> None: self.entries.append(text)

    rec = _Rec()
    ev = Evidence(verdict=Verdict.FAIL, reason="Kimi: asume X falso")
    record_synthesis(rec, "¿migrar a GraphQL?", ev)
    assert len(rec.entries) == 1
    assert "FAIL" in rec.entries[0] and "GraphQL" in rec.entries[0]
```
- [ ] **Step 2: Correr y verificar fallo**
  Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_deliberation_council.py -q`
  Expected: FAIL.
- [ ] **Step 3: Implementación**
```python
from typing import Protocol


class SynthesisRecorder(Protocol):
    def record(self, text: str) -> None: ...


def record_synthesis(recorder: SynthesisRecorder, decision: str, evidence: Evidence) -> None:
    reason = f" — {evidence.reason}" if evidence.reason else ""
    recorder.record(f"[{evidence.verdict.name}] {decision}{reason}")
```
- [ ] **Step 4: Correr y verificar paso**
  Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_deliberation_council.py -q`
  Expected: PASS (8 tests).
- [ ] **Step 5: mypy + commit**
  ```bash
  MYPYPATH=src .venv/bin/python -m mypy src/atlas/core/deliberation_council.py
  git add src/atlas/core/deliberation_council.py tests/test_deliberation_council.py
  git commit -m "feat(council): record_synthesis (side-effect inyectable, Fase B4)"
  ```

### Task B5: Smoke en vivo (separado de la suite) + honestidad de capacidades

**Files:**
- Create: `scripts/council_smoke.py`
- Modify: `docs/governance/CAPABILITIES.md`, `WORK_LEDGER.md`

**Interfaces:**
- Consumes: `build_trio_reviewers`, `convene_for_decision`, `Difficulty`.

- [ ] **Step 1: Escribir el smoke** que convoca el trío REAL sobre una decisión de ejemplo y
  reporta el veredicto + qué proveedores respondieron y cuáles dieron 404/error. NO se añade a
  `tests/` (requiere secretos/red; patrón `inference_smoke.py`). Carga `.env`.
```python
"""Smoke en vivo del Cónclave: requiere GEMINI_API_KEY + NVIDIA_API_KEY. No es test de suite."""
from atlas.core.deliberation_council import build_trio_reviewers, convene_for_decision
from atlas.router.cascade import Difficulty

if __name__ == "__main__":
    trio = build_trio_reviewers()
    print(f"trío ensamblado: {[r.provider for r in trio]}")
    ev = convene_for_decision(
        "¿UUID o BIGINT para user IDs de un SaaS con 10M usuarios?",
        context="decisión irreversible, afecta años",
        difficulty=Difficulty.HARD, risk="high", reviewers=trio,
    )
    assert ev is not None
    print(f"veredicto: {ev.verdict.name}")
    for c in ev.checks:
        print(f"  - {c.name}: {'PASS' if c.passed else 'OBJETA'} | {c.detail[:120]}")
```
- [ ] **Step 2: Ejecutar el smoke** (manual, con secretos):
  Run: `PYTHONPATH=src .venv/bin/python scripts/safe_dotenv.py .env -- .venv/bin/python scripts/council_smoke.py`
  Expected: imprime el trío y un veredicto; anotar qué proveedor dio 404 si lo hay
  (memoria `nvidia-nim-frontier-models.md`).
- [ ] **Step 3: Anotar honestamente en CAPABILITIES.md** una fila:
  `| Cónclave (deliberation_council) | <real|andamiaje según smoke> | juez-único real; trío real solo si los 3 proveedores responden vivos (smoke) |`.
- [ ] **Step 4: Actualizar el ledger** — marcar v1 ✅ con el resultado del smoke; v2 sigue ⏸.
- [ ] **Step 5: Commit**
  ```bash
  git add scripts/council_smoke.py docs/governance/CAPABILITIES.md WORK_LEDGER.md
  git commit -m "feat(council): smoke en vivo del trío + honestidad de capacidades (Fase B5)"
  ```

---

## Self-Review (cobertura del spec)

- Protocolo 4 pasos → A1 (prosa) + B1–B4 (escalada real). ✅
- Gating adaptativo → A1 (prosa) + B3 (`should_convene`). ✅
- Reglas = manías → A1 + Global Constraints. ✅
- Trío de 3 linajes + diversidad obligatoria → B2 + B3 (`min_providers=3`→UNKNOWN). ✅
- Veredicto honesto PASS/FAIL/UNKNOWN → B3 (vía `AdversarialPanel`). ✅
- Dos consumidores (yo + Atlas) → A1 (docs/skills servido) + A2 (.claude/skills). ✅
- Copy-pega degradada honesta → A3. ✅
- Side-effect de destilación → B4 (inyectable; recorder real al validar). ✅
- v2 (reinicio de loop, debate por rondas, sucesión) → FUERA de este plan, por diseño. ✅
- DoD (tests + mypy + ledger + CAPABILITIES) → en cada tarea + B5. ✅
