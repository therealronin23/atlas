# T0 Núcleo de Sucesión (T0.2 migración + T0.1 atlas handoff) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** La memoria privada del harness migra al sustrato con procedencia, y `atlas handoff` regenera el pack de sucesión desde el sustrato — nunca más packs manuales que se pudren.

**Architecture:** (1) Script one-shot idempotente que lee los .md de memoria del harness (frontmatter tipado) y los ingiere vía `MemoryTrunk.add` (procedencia sha256 automática) con `record_id` estable `harness:<name>`. (2) Módulo puro `atlas.core.handoff` que colecciona fuentes vivas (ledger, actor_roles, AGENTS.md, memorias migradas, reality) y proyecta `docs/handoff/GENERATED/` + `MANIFEST.json` con el HEAD sha; subcomando click `handoff` con `--check` de frescura. Determinista: mismo sustrato → mismos bytes (salvo timestamp en MANIFEST).

**Tech Stack:** Python 3.12, click (patrón existente en `src/atlas/interfaces/cli.py`), `SqliteMemoryIndex`/`MemoryTrunk` existentes, pytest, mypy --strict.

## Global Constraints

- TDD rojo→verde por tarea; tests: `ATLAS_NESTED_TEST_RUN=1 PYTHONPATH=src .venv/bin/python -m pytest <fichero> -q` (JAMÁS la suite completa).
- mypy --strict limpio en todo fichero nuevo/tocado bajo `src/`: `.venv/bin/python -m mypy --strict <fichero>`.
- Sin dependencias nuevas. Sin push. Un commit por tarea. `git diff --cached --stat` ANTES de cada commit (lección: staged ajeno).
- La BD de producción `~/atlas-mcp/memory.db` NO se toca en tests (todo en tmp_path).
- Ficheros generados llevan SIEMPRE la cabecera: `<!-- GENERADO por atlas handoff <ISO-ts> — NO EDITAR A MANO; regenerar con: atlas handoff -->`.
- El texto migrado conserva el original ÍNTEGRO (no resumir: la procedencia es del contenido real).

---

### Task 1: Migración memoria-harness → sustrato (`scripts/migrate_harness_memory.py`)

**Files:**
- Create: `scripts/migrate_harness_memory.py`
- Test: `tests/test_migrate_harness_memory.py`

**Interfaces:**
- Consumes: `MemoryTrunk` (`src/atlas/mcp/memory_trunk.py:40`, `add(text, *, record_id, record_type, memory_class)`); `SqliteMemoryIndex` construido como en `src/atlas/mcp/memory_server.py:198` (`SqliteMemoryIndex(db_path, embedder=default_embedder(), write_gate=gate)`) — el implementador DEBE mirar la función que envuelve esa línea y reutilizarla si es importable; para tests, construir con el embedder stub que ya usen los tests existentes de memoria (buscar `StubEmbedder` en `tests/`).
- Produces: registros con `record_id=f"harness:{name}"`, `record_type="harness-memory"`, texto `"[migrado de memoria-harness 2026-07-16] <description>\n\n<body>"`; clases: `project`/`reference` → `factual`, `feedback` → `personal`, `user` → NO se migra (se reporta "queda en harness").

- [ ] **Step 1: Test rojo** — fixture dir con 3 memorias sintéticas (frontmatter `name/description/metadata.type` = project, feedback, user) + BD tmp; el test invoca `migrate(memory_dir, index)` (import por `importlib` desde `scripts/`, patrón de `tests/test_graphify_failure_guard.py:41-46`) y asserta: 2 migradas con ids `harness:<name>`, la `user` excluida, y `MemoryTrunk(index).recall("<palabra de la description>")[0].record_id == "harness:<name>"`. Segundo assert: ejecutar `migrate` DOS veces no duplica (upsert idempotente por id).

```python
def test_migrate_partitions_and_is_idempotent(tmp_path: Path) -> None:
    mem = tmp_path / "memory"; mem.mkdir()
    (mem / "proj-x.md").write_text(
        "---\nname: proj-x\ndescription: hito del proyecto atlas\n"
        "metadata:\n  type: project\n---\n\ncuerpo proyecto\n", encoding="utf-8")
    (mem / "feed-y.md").write_text(
        "---\nname: feed-y\ndescription: mania del operador sobre docs\n"
        "metadata:\n  type: feedback\n---\n\ncuerpo feedback\n", encoding="utf-8")
    (mem / "user-z.md").write_text(
        "---\nname: user-z\ndescription: dato personal\n"
        "metadata:\n  type: user\n---\n\ncuerpo personal\n", encoding="utf-8")
    index = _test_index(tmp_path / "db.sqlite")  # helper: SqliteMemoryIndex + stub embedder
    report = _mod().migrate(mem, index)
    assert report == {"migrated": 2, "skipped_user": 1, "errors": []}
    report2 = _mod().migrate(mem, index)
    assert report2["migrated"] == 2  # upsert, no duplica
```

- [ ] **Step 2: Verificar rojo** — `pytest tests/test_migrate_harness_memory.py -q` → FAIL (script no existe).
- [ ] **Step 3: Implementación mínima** — parseo de frontmatter SIN yaml-lib nueva (split por `---` + parseo línea a línea de `name:`, `description:`, `type:` bajo `metadata:`; hay PyYAML en el venv si ya lo importa el repo — verificar con grep antes de usarlo). CLI argparse: `--memory-dir` (default la ruta real del harness), `--db` (default `~/atlas-mcp/memory.db`), `--apply` (sin él = dry-run que solo imprime el reporte — default honesto).
- [ ] **Step 4: Verificar verde** + `mypy --strict scripts/migrate_harness_memory.py`.
- [ ] **Step 5: Commit** — `git diff --cached --stat` primero; `feat: migración memoria-harness al sustrato (T0.2, dry-run por defecto)`.

### Task 2: Generador `atlas handoff` (`src/atlas/core/handoff.py` + subcomando)

**Files:**
- Create: `src/atlas/core/handoff.py`
- Modify: `src/atlas/interfaces/cli.py` (añadir `@cli.command()` tras `reality`, patrón líneas 613-641)
- Test: `tests/test_handoff.py`

**Interfaces:**
- Consumes: Task 1 (registros `record_type="harness-memory"` en el índice); `WORK_LEDGER.md`, `AGENTS.md`, `docs/design/actor_roles.md`, `docs/design/atlas_master_plan.md` del repo.
- Produces: `generate_handoff(repo_root: Path, index: SqliteMemoryIndex | None, out_dir: Path) -> dict[str, str]` (mapa fichero→sha256 del contenido); escribe `00_ESTADO.md` (bloque WHERE más reciente del ledger, delimitado desde `## WHERE` hasta la segunda entrada `- **`), `01_QUIEN_ES_QUIEN.md` (actor_roles íntegro), `02_INVARIANTES.md` (AGENTS.md íntegro), `03_MEMORIA_CLAVE.md` (lista `name — description` de TODOS los registros harness-memory del índice, orden alfabético; si `index is None` → sección literal `FUENTE NO DISPONIBLE: sustrato`), `04_PLAN.md` (master plan íntegro), `MANIFEST.json` (`{"head_sha", "generated_at", "files": {name: sha256}}`). Fail-CERRADO: fuente ausente → sección `FUENTE NO DISPONIBLE: <cual>`, jamás omisión silenciosa.
- CLI: `atlas handoff` regenera; `atlas handoff --check` NO escribe: compara `MANIFEST.json["head_sha"]` con HEAD y sale 1 con mensaje si difieren (0 si igual o si no hay manifest previo → mensaje "nunca generado").

- [ ] **Step 1: Test rojo** — repo fixture en tmp (git init + WORK_LEDGER con 2 entradas WHERE + AGENTS.md + actor_roles + master plan mínimos) + índice con 1 registro harness-memory; `generate_handoff` → asserta: 6 ficheros, cabecera GENERADO en los 5 .md, `00_ESTADO.md` contiene la 1ª entrada y NO la 2ª, `03_MEMORIA_CLAVE.md` contiene el name del registro, MANIFEST con head_sha real del fixture. Determinismo: segunda llamada → mismos sha256 en `files`.
- [ ] **Step 2: Verificar rojo.**
- [ ] **Step 3: Implementación** — funciones puras por sección (una función por fichero generado, testables solas); el subcomando click construye el índice SOLO si la BD default existe (si no, `index=None`).
- [ ] **Step 4: Test del `--check`** (rojo→verde): tras generar, `git commit --allow-empty` en el fixture → `--check` exit 1 con "STALE".
- [ ] **Step 5: Verde total + mypy** — `pytest tests/test_handoff.py -q` y `mypy --strict src/atlas/core/handoff.py`.
- [ ] **Step 6: Commit** — `feat: atlas handoff — pack de sucesión generado desde el sustrato (T0.1)`.

### Task 3: Primera ejecución real + ingesta de los docs de autoridad

**Files:**
- Modify: ninguno (ejecución + verificación)

- [ ] **Step 1:** `python scripts/migrate_harness_memory.py` (dry-run) → revisar reporte → `--apply`. Evidencia: `atlas` recall de 2 memorias clave devuelve contenido con procedencia.
- [ ] **Step 2:** Ingerir también `atlas_master_plan.md` y `fable5_build_doctrine.md` como `record_type="doctrine"` (mismo script, flag `--extra-doc <path>` — añadirlo en Task 1 si trivial, si no aquí a mano vía MemoryTrunk).
- [ ] **Step 3:** `atlas handoff` real → inspeccionar `docs/handoff/GENERATED/` → commit de los generados + nota en WORK_LEDGER (1 entrada: T0.1+T0.2 cerradas con evidencia).

## Siguientes planes (NO en este)

- **T5.1 smoke de proveedores**: plan corto propio tras recon de `InferenceHub` (src/atlas/core/inference_hub.py:402) — no se especifica a ciegas.
- **T0.3 onboarding + F2.6**: depende de que T0.1/T0.2 estén vivas; el test de sucesión usa el pack generado.
- **T2.1 Mission Console mínima**: plan propio con frontend-design + frontend-ui-engineering (doble estándar sellado).
