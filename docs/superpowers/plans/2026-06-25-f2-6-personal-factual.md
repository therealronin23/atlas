# f2-6 personal/factual (mitad tratable) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Impedir que memorias `personal` contaminen las `factual` mediante un eje de clase explícito en `SqliteMemoryIndex`, recall que por defecto no mezcla, y expiración por-ítem con default por clase + barrido perezoso.

**Architecture:** Todo en `src/atlas/memory/memory_index.py` (reusa migraciones idempotentes, el chokepoint `_rows`, y el soft-retire `retire`/`valid_until_ns` existentes). NO se crea `MemoryManager`. NO se auto-clasifica (el caller declara la clase). Spec: `docs/superpowers/specs/2026-06-25-f2-6-personal-factual-design.md`.

**Tech Stack:** Python 3, sqlite3, mypy strict, pytest.

## Global Constraints

- Tests cubren el cambio (AGENTS.md Regla 7). mypy strict: `MYPYPATH=src python -m mypy src/atlas/memory/memory_index.py`.
- Cero deps nuevas (stdlib + sqlite ya presente).
- `WORK_LEDGER.md` + `docs/backlog.yaml` actualizados en el commit de cierre.
- Retrocompat dura: callers actuales de `upsert`/`recall`/`recall_all` (sin kwargs nuevos) deben seguir funcionando idénticamente. Las filas pre-migración → `memory_class='factual'`, `expires_at NULL`.
- Test cmd: `cd ~/proyectos/atlas-core && source .venv/bin/activate && PYTHONPATH=src python -m pytest ...`
- Valores exactos: `PERSONAL_TTL_S = 90 * 24 * 3600` (90 días). Clases válidas: `"personal"`, `"factual"`. Default de clase: `"factual"`.
- Base del TTL al escribir: `time.time()` (epoch ahora) — equivalente a created_at y evita parsear el ISO string.
- El índice ya filtra por `self._tenant` en `_rows`/`retire`; los filtros nuevos se AND-ean DENTRO de ese filtro.

---

### Task 1: Migración de columnas `memory_class` + `expires_at` + constantes

**Files:**
- Modify: `src/atlas/memory/memory_index.py` (constantes de módulo cerca de `_TENANT_COLUMNS`; nuevo método `_migrate_class_ttl`; llamada en la secuencia de migración ~línea 188)
- Test: `tests/test_memory_class_ttl.py` (nuevo)

**Interfaces:**
- Produces: columnas `memory_class TEXT NOT NULL DEFAULT 'factual'` y `expires_at REAL` en la tabla `records`; constante `PERSONAL_TTL_S`.

- [ ] **Step 1: Test de migración (falla)**

Crear `tests/test_memory_class_ttl.py`:

```python
from __future__ import annotations

from pathlib import Path

from atlas.memory.memory_index import SqliteMemoryIndex, PERSONAL_TTL_S
from atlas.memory.record import GenericRecord


def _cols(idx: SqliteMemoryIndex) -> set[str]:
    return {r[1] for r in idx._conn.execute("PRAGMA table_info(records)")}


def test_migration_adds_class_and_ttl_columns(tmp_path: Path) -> None:
    idx = SqliteMemoryIndex(tmp_path / "m.db")
    cols = _cols(idx)
    assert "memory_class" in cols
    assert "expires_at" in cols


def test_personal_ttl_constant_is_90_days() -> None:
    assert PERSONAL_TTL_S == 90 * 24 * 3600


def test_preexisting_row_defaults_to_factual(tmp_path: Path) -> None:
    # Fila escrita con el esquema base, sin memory_class explícito → factual.
    idx = SqliteMemoryIndex(tmp_path / "m.db")
    idx.upsert(GenericRecord(record_id="r1", text="el agua hierve a 100C"))
    row = idx._conn.execute(
        "SELECT memory_class, expires_at FROM records WHERE id='r1'"
    ).fetchone()
    assert row[0] == "factual"
    assert row[1] is None
```

- [ ] **Step 2: Correr — falla**

Run: `PYTHONPATH=src python -m pytest tests/test_memory_class_ttl.py -v`
Expected: FAIL (ImportError `PERSONAL_TTL_S` o columnas ausentes).

- [ ] **Step 3: Añadir constantes + migración**

En `memory_index.py`, cerca de `_TENANT_COLUMNS`:

```python
PERSONAL_TTL_S = 90 * 24 * 3600  # 90 días; default de expiración para clase 'personal'

_CLASS_TTL_COLUMNS = {
    "memory_class": "TEXT NOT NULL DEFAULT 'factual'",
    "expires_at": "REAL",
}
```

Añadir el método (espejo de `_migrate_tenant`):

```python
    def _migrate_class_ttl(self) -> None:
        """Añade memory_class (personal/factual) y expires_at (idempotente).
        Filas existentes → 'factual' sin expiración (lo seguro/objetivo)."""
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(records)")}
        for col, decl in _CLASS_TTL_COLUMNS.items():
            if col not in existing:
                try:
                    self._conn.execute(f"ALTER TABLE records ADD COLUMN {col} {decl}")
                    if col == "memory_class":
                        self._conn.execute(
                            "UPDATE records SET memory_class='factual' "
                            "WHERE memory_class IS NULL"
                        )
                except Exception:
                    pass  # carrera de init concurrente: seguro ignorar
        self._conn.commit()
```

Llamarlo en la secuencia de migración (tras `self._migrate_tenant()`, ~línea 188):

```python
        self._migrate_class_ttl()
```

- [ ] **Step 4: Correr — pasa**

Run: `PYTHONPATH=src python -m pytest tests/test_memory_class_ttl.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/atlas/memory/memory_index.py tests/test_memory_class_ttl.py
git commit -m "feat(memory): migración memory_class + expires_at (f2-6)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `upsert` acepta `memory_class` + `expires_at` con default por clase

**Files:**
- Modify: `src/atlas/memory/memory_index.py` (`upsert`, ~líneas 319-360: firma + INSERT/ON CONFLICT)
- Test: `tests/test_memory_class_ttl.py`

**Interfaces:**
- Consumes: columnas de Task 1, `PERSONAL_TTL_S`.
- Produces: `upsert(record, *, merkle_leaf_hash=None, merkle_leaf_index=None, valid_from_ns=None, supersedes=None, memory_class="factual", expires_at=None)`.

- [ ] **Step 1: Tests (fallan)**

Añadir a `tests/test_memory_class_ttl.py`:

```python
import time


def test_upsert_personal_derives_ttl(tmp_path: Path) -> None:
    idx = SqliteMemoryIndex(tmp_path / "m.db")
    before = time.time()
    idx.upsert(GenericRecord(record_id="p1", text="me gusta el café"), memory_class="personal")
    row = idx._conn.execute(
        "SELECT memory_class, expires_at FROM records WHERE id='p1'"
    ).fetchone()
    assert row[0] == "personal"
    assert row[1] is not None
    # expires_at ≈ now + PERSONAL_TTL_S
    assert before + PERSONAL_TTL_S <= row[1] <= time.time() + PERSONAL_TTL_S + 5


def test_upsert_factual_has_no_expiry(tmp_path: Path) -> None:
    idx = SqliteMemoryIndex(tmp_path / "m.db")
    idx.upsert(GenericRecord(record_id="f1", text="París es la capital de Francia"),
               memory_class="factual")
    row = idx._conn.execute("SELECT expires_at FROM records WHERE id='f1'").fetchone()
    assert row[0] is None


def test_upsert_explicit_expires_at_wins(tmp_path: Path) -> None:
    idx = SqliteMemoryIndex(tmp_path / "m.db")
    idx.upsert(GenericRecord(record_id="p2", text="x"), memory_class="personal",
               expires_at=123.0)
    row = idx._conn.execute("SELECT expires_at FROM records WHERE id='p2'").fetchone()
    assert row[0] == 123.0
```

- [ ] **Step 2: Correr — falla**

Run: `PYTHONPATH=src python -m pytest tests/test_memory_class_ttl.py -k upsert -v`
Expected: FAIL (`upsert() got an unexpected keyword argument 'memory_class'`).

- [ ] **Step 3: Extender `upsert`**

Añadir los dos kwargs a la firma (tras `supersedes`):

```python
        memory_class: str = "factual",
        expires_at: float | None = None,
```

Justo antes de construir el INSERT (tras calcular `vfrom`), derivar el expiry efectivo:

```python
        eff_expires_at = expires_at
        if eff_expires_at is None and memory_class == "personal":
            eff_expires_at = time.time() + PERSONAL_TTL_S
```

En el `INSERT INTO records (...)`, añadir las dos columnas y sus valores. La lista de columnas pasa a incluir `memory_class, expires_at` y los `VALUES (...)` sus dos placeholders. En el `ON CONFLICT(id) DO UPDATE SET` añadir:

```python
                memory_class=excluded.memory_class,
                expires_at=excluded.expires_at,
```

Y añadir `memory_class` y `eff_expires_at` a la tupla de parámetros del execute, en el orden correcto de las columnas. (El implementador alinea el orden columnas↔valores↔params; no cambiar el resto del INSERT.)

- [ ] **Step 4: Correr — pasa**

Run: `PYTHONPATH=src python -m pytest tests/test_memory_class_ttl.py -v`
Expected: PASS (todos). Y regresión rápida del módulo:
Run: `PYTHONPATH=src python -m pytest tests/ -k memory_index -q`
Expected: PASS (callers existentes de upsert sin kwargs → factual, sin romper).

- [ ] **Step 5: mypy + commit**

Run: `MYPYPATH=src python -m mypy src/atlas/memory/memory_index.py`
Expected: Success.

```bash
git add src/atlas/memory/memory_index.py tests/test_memory_class_ttl.py
git commit -m "feat(memory): upsert acepta memory_class + expires_at con default por clase (f2-6)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: recall filtra por clase (default factual) + excluye expirados

**Files:**
- Modify: `src/atlas/memory/memory_index.py` (`_rows` ~línea ~580; `recall` ~588; `recall_all` ~612)
- Test: `tests/test_memory_class_ttl.py`

**Interfaces:**
- Consumes: columnas + upsert de Tasks 1-2.
- Produces: `_rows(include_superseded=False, *, memory_class="factual", now_epoch=None)`; `recall(query_text, *, include_superseded=False, now_ns=None, memory_class=None)`; `recall_all(query_text, k=5, *, include_superseded=False, now_ns=None, memory_class=None)`. Default `memory_class=None` ⇒ trata como `"factual"`.

- [ ] **Step 1: Tests (fallan)**

Añadir a `tests/test_memory_class_ttl.py`:

```python
def _seed_mixed(idx: SqliteMemoryIndex) -> None:
    idx.upsert(GenericRecord(record_id="f1", text="la fotosíntesis ocurre en los cloroplastos"),
               memory_class="factual")
    idx.upsert(GenericRecord(record_id="p1", text="creo que la fotosíntesis es sobrevalorada"),
               memory_class="personal")


def test_recall_default_returns_only_factual(tmp_path: Path) -> None:
    idx = SqliteMemoryIndex(tmp_path / "m.db")
    _seed_mixed(idx)
    ids = {r.lesson_id for r in idx.recall_all("fotosíntesis", k=10)}
    assert "f1" in ids
    assert "p1" not in ids  # personal NO se mezcla por defecto


def test_recall_personal_returns_only_personal(tmp_path: Path) -> None:
    idx = SqliteMemoryIndex(tmp_path / "m.db")
    _seed_mixed(idx)
    ids = {r.lesson_id for r in idx.recall_all("fotosíntesis", k=10, memory_class="personal")}
    assert ids == {"p1"}


def test_recall_excludes_expired(tmp_path: Path) -> None:
    idx = SqliteMemoryIndex(tmp_path / "m.db")
    idx.upsert(GenericRecord(record_id="old", text="preferencia caduca"),
               memory_class="personal", expires_at=1.0)  # epoch lejano en el pasado
    ids = {r.lesson_id for r in idx.recall_all("preferencia", k=10, memory_class="personal")}
    assert "old" not in ids


def test_contamination_does_not_affect_factual_recall(tmp_path: Path) -> None:
    idx = SqliteMemoryIndex(tmp_path / "m.db")
    idx.upsert(GenericRecord(record_id="f1", text="el sol está a 150M km de la Tierra"),
               memory_class="factual")
    before = {r.lesson_id for r in idx.recall_all("distancia al sol", k=10)}
    for i in range(5):
        idx.upsert(GenericRecord(record_id=f"bias{i}", text="el sol está cerquísima"),
                   memory_class="personal")
    after = {r.lesson_id for r in idx.recall_all("distancia al sol", k=10)}
    assert before == after  # las personales no contaminan el recall factual
```

- [ ] **Step 2: Correr — falla**

Run: `PYTHONPATH=src python -m pytest tests/test_memory_class_ttl.py -k "recall or contamination" -v`
Expected: FAIL (`recall_all() got an unexpected keyword argument 'memory_class'`).

- [ ] **Step 3: Filtrar en `_rows` y propagar el param**

Reescribir `_rows` para filtrar clase + expiry (manteniendo el filtro de tenant y superseded):

```python
    def _rows(
        self, include_superseded: bool = False, *,
        memory_class: str = "factual", now_epoch: float | None = None,
    ) -> list[tuple[str, list[float]]]:
        now = now_epoch if now_epoch is not None else time.time()
        sql = "SELECT id, vector FROM records WHERE tenant=?"
        params: list[object] = [self._tenant]
        if not include_superseded:
            sql += " AND valid_until_ns IS NULL"
        sql += " AND memory_class=?"
        params.append(memory_class)
        sql += " AND (expires_at IS NULL OR expires_at > ?)"
        params.append(now)
        sql += " ORDER BY ordinal"
        cur = self._conn.execute(sql, tuple(params))
        return [(rid, _unpack(blob)) for rid, blob in cur.fetchall()]
```

En `recall` y `recall_all`, añadir el kwarg `memory_class: str | None = None` y resolverlo a factual por defecto al llamar a `_rows`:

```python
        cls = memory_class if memory_class is not None else "factual"
        rows = self._rows(include_superseded, memory_class=cls)
```

(Sustituir la llamada actual `self._rows(include_superseded)` por la de arriba en ambos métodos.)

- [ ] **Step 4: Correr — pasa**

Run: `PYTHONPATH=src python -m pytest tests/test_memory_class_ttl.py -v && PYTHONPATH=src python -m pytest tests/ -k "memory" -q`
Expected: PASS (incluye no-regresión de los tests de memoria existentes: todo lo viejo es factual → recall default los sigue devolviendo).

- [ ] **Step 5: mypy + commit**

```bash
MYPYPATH=src python -m mypy src/atlas/memory/memory_index.py
git add src/atlas/memory/memory_index.py tests/test_memory_class_ttl.py
git commit -m "feat(memory): recall filtra por clase (default factual) y excluye expirados (f2-6)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: `recall_split` — buckets factual/personal separados

**Files:**
- Modify: `src/atlas/memory/memory_index.py` (nuevo método tras `recall_all`)
- Test: `tests/test_memory_class_ttl.py`

**Interfaces:**
- Consumes: `recall_all` con `memory_class` de Task 3.
- Produces: `recall_split(query_text, k=5, *, include_superseded=False, now_ns=None) -> tuple[list[RecallResult], list[RecallResult]]` → `(factual, personal)`.

- [ ] **Step 1: Test (falla)**

```python
def test_recall_split_separates_buckets(tmp_path: Path) -> None:
    idx = SqliteMemoryIndex(tmp_path / "m.db")
    _seed_mixed(idx)
    factual, personal = idx.recall_split("fotosíntesis", k=10)
    assert {r.lesson_id for r in factual} == {"f1"}
    assert {r.lesson_id for r in personal} == {"p1"}
```

- [ ] **Step 2: Correr — falla**

Run: `PYTHONPATH=src python -m pytest tests/test_memory_class_ttl.py -k split -v`
Expected: FAIL (`'SqliteMemoryIndex' object has no attribute 'recall_split'`).

- [ ] **Step 3: Implementar**

```python
    def recall_split(
        self, query_text: str, k: int = 5, *,
        include_superseded: bool = False, now_ns: int | None = None,
    ) -> tuple[list[RecallResult], list[RecallResult]]:
        """Recall en buckets SEPARADOS (factual, personal) — nunca mezclados en un
        ranking único. Para personalización + hechos sin contaminar el ranking factual."""
        factual = self.recall_all(
            query_text, k, include_superseded=include_superseded,
            now_ns=now_ns, memory_class="factual",
        )
        personal = self.recall_all(
            query_text, k, include_superseded=include_superseded,
            now_ns=now_ns, memory_class="personal",
        )
        return factual, personal
```

- [ ] **Step 4: Correr — pasa**

Run: `PYTHONPATH=src python -m pytest tests/test_memory_class_ttl.py -k split -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atlas/memory/memory_index.py tests/test_memory_class_ttl.py
git commit -m "feat(memory): recall_split — buckets factual/personal separados (f2-6)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: `expire_stale` — barrido perezoso (soft-retire de expirados)

**Files:**
- Modify: `src/atlas/memory/memory_index.py` (nuevo método tras `retire`)
- Test: `tests/test_memory_class_ttl.py`

**Interfaces:**
- Consumes: `retire` (soft-retire vía `valid_until_ns`) y las columnas de Task 1.
- Produces: `expire_stale(*, now_ns: int | None = None) -> int` (nº retirados).

- [ ] **Step 1: Test (falla)**

```python
def test_expire_stale_retires_expired_and_counts(tmp_path: Path) -> None:
    idx = SqliteMemoryIndex(tmp_path / "m.db")
    idx.upsert(GenericRecord(record_id="dead", text="caduca"),
               memory_class="personal", expires_at=1.0)
    idx.upsert(GenericRecord(record_id="live", text="vive"),
               memory_class="personal", expires_at=time.time() + 10_000)
    n = idx.expire_stale()
    assert n == 1
    # 'dead' quedó soft-retired (valid_until_ns no NULL); 'live' sigue vigente.
    dead = idx._conn.execute(
        "SELECT valid_until_ns FROM records WHERE id='dead'").fetchone()
    live = idx._conn.execute(
        "SELECT valid_until_ns FROM records WHERE id='live'").fetchone()
    assert dead[0] is not None
    assert live[0] is None
    # idempotente: 2ª pasada no retira nada.
    assert idx.expire_stale() == 0
```

- [ ] **Step 2: Correr — falla**

Run: `PYTHONPATH=src python -m pytest tests/test_memory_class_ttl.py -k expire_stale -v`
Expected: FAIL (`no attribute 'expire_stale'`).

- [ ] **Step 3: Implementar (reusa el soft-retire de `retire`)**

```python
    def expire_stale(self, *, now_ns: int | None = None) -> int:
        """Barrido perezoso (on-demand, sin daemon): soft-retira los ítems con
        expires_at <= now. Reusa la semántica de retire (valid_until_ns)."""
        now = time.time()
        ts = now_ns if now_ns is not None else time.time_ns()
        rows = self._conn.execute(
            "SELECT id FROM records WHERE tenant=? AND valid_until_ns IS NULL "
            "AND expires_at IS NOT NULL AND expires_at <= ?",
            (self._tenant, now),
        ).fetchall()
        for (rid,) in rows:
            self._conn.execute(
                "UPDATE records SET valid_until_ns=? WHERE id=? AND valid_until_ns IS NULL "
                "AND tenant=?",
                (ts, rid, self._tenant),
            )
        self._conn.commit()
        if rows:
            self._audit("memory.expired_swept", {"count": len(rows), "at_ns": ts})
        return len(rows)
```

- [ ] **Step 4: Correr — pasa**

Run: `PYTHONPATH=src python -m pytest tests/test_memory_class_ttl.py -v`
Expected: PASS (toda la suite del archivo).

- [ ] **Step 5: mypy + commit**

```bash
MYPYPATH=src python -m mypy src/atlas/memory/memory_index.py
git add src/atlas/memory/memory_index.py tests/test_memory_class_ttl.py
git commit -m "feat(memory): expire_stale — barrido perezoso de expirados (f2-6)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Tenant × clase + cierre DoD

**Files:**
- Modify: `tests/test_memory_class_ttl.py` (test de aislamiento clase×tenant), `WORK_LEDGER.md`, `docs/backlog.yaml`

**Interfaces:**
- Consumes: todo lo anterior.

- [ ] **Step 1: Test clase × tenant (falla si algo no respeta tenant)**

```python
def test_personal_isolated_by_tenant(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    a = SqliteMemoryIndex(db, tenant="A")
    b = SqliteMemoryIndex(db, tenant="B")
    a.upsert(GenericRecord(record_id="pa", text="secreto de A"), memory_class="personal")
    ids_b = {r.lesson_id for r in b.recall_all("secreto", k=10, memory_class="personal")}
    assert "pa" not in ids_b  # B no ve lo personal de A
```

(Si el constructor de `SqliteMemoryIndex` usa otro nombre para el kwarg de tenant, ajústalo al real — verificar con grep `def __init__`.)

- [ ] **Step 2: Correr — pasa**

Run: `PYTHONPATH=src python -m pytest tests/test_memory_class_ttl.py -v`
Expected: PASS.

- [ ] **Step 3: Suite completa + mypy global**

Run: `PYTHONPATH=src python -m pytest tests/ -q && MYPYPATH=src python -m mypy src/atlas/`
Expected: suite verde, mypy Success. (Anotar el conteo real.)

- [ ] **Step 4: Actualizar ledger + backlog**

En `docs/backlog.yaml`, `f2-6-personalization-vs-contamination` → `status: done` con nota: "mitad tratable hecha (memory_class explícito + recall no-mezcla + recall_split + TTL por-clase + expire_stale, N tests). Muro registrado: clasificador automático NO construido (1c)."

En `WORK_LEDGER.md`, marcar f2-6 en la línea de Fase 2: `🧱 2.6 personalización-vs-contaminación` → `✅ 2.6 (mitad tratable; clasificador automático = muro 1c registrado)`.

- [ ] **Step 5: Commit de cierre**

```bash
git add WORK_LEDGER.md docs/backlog.yaml tests/test_memory_class_ttl.py
git commit -m "docs(memory): cierra f2-6 mitad tratable (ledger + backlog)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Notas de cierre

- Rama `feat/f2-6-personal-factual` lista para merge/PR tras Task 6 (decidir con el usuario; no auto-push).
- Follow-ups registrados (NO en este plan): wiring caller-side (knowledge-src → factual, captura de preferencias → personal); investigación medida "¿LLM-juez bate al etiquetado explícito?" (el muro).
