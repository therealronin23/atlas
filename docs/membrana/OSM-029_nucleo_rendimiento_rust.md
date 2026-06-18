# OSM-029 — Núcleo de rendimiento en Rust (Merkle + embeddings + monitor)

Fecha: 2026-06-17 · Estado: **Difusión** (prematura sin perfil; ver criterio de activación) ·
Origen: `idea avance 3.md` · Contexto: `src/atlas/transparency/merkle_tree.py`, [[OSM-024]]
(latencia en path), [[OSM-028]] (metadata-monitor), regla 6 de CLAUDE.md (stdlib primero).

---

## Contexto

Un filtro obligatorio en el path ([[OSM-024]]) añade latencia a **todas** las peticiones.
Las partes calientes candidatas son el log Merkle (append + proofs) y el metadata-monitor
(embeddings + reglas, [[OSM-028]]). El chat 3 propone reescribir esas partes en Rust.

**Esta OSM está en Difusión indefinida hasta que se active el criterio de abajo.**
El coste de un segundo lenguaje (toolchain, build, superficie de mantenimiento permanente)
solo se justifica con números reales sobre un path E2E que hoy no existe. Especificar el
port antes de tener el perfil es diseño orientado a estética, no a evidencia.

## Criterio de activación

Esta OSM no avanza a "En membrana" hasta que se cumplan **las dos condiciones**:

1. **Existe una demo E2E del path completo** ([[OSM-024]] wired): usuario → co-firma →
   gateway → log Merkle → modelo → respuesta + proof. Sin E2E no hay qué perfilar.
2. **El perfil muestra cuello de botella real**: `p95_latency > 50ms` en el Merkle o el
   monitor bajo carga representativa (≥100 rps sostenidos). Si el Python es suficiente con
   caching/memoización de subárboles (OSM-006), esta OSM **no cruza nunca**.

Alternativa a evaluar primero: **OSM-006** (persistencia + memoización de subárboles en
Python puro). Si cierra el problema de latencia sin Rust, esta OSM se archiva.

## La idea (condicional a activación)

Un núcleo de rendimiento en Rust para las rutas calientes, tras una frontera FFI limpia:

- **Merkle en Rust**: append incremental O(log n) + inclusion/consistency proofs, expuesto
  vía PyO3. Mismo modelo que `merkle_tree.py` actual — no una versión simplificada.
- **Embeddings + reglas deterministas en Rust** para el metadata-monitor ([[OSM-028]]):
  cosine similarity de vectores densos, evaluación de reglas booleanas sobre metadata.
- **Frontera estable**: Python sigue orquestando (Decider, LessonStore, organismo); Rust
  solo hace el cómputo caliente. No se reescribe Atlas.

## Correcciones de verificación (obligatorias si se activa)

**El Merkle del chat 3 es una regresión. No se porta tal cual.**

- `compute_root` del chat recomputa toda la raíz en cada append → O(n) por inserción.
  El Python actual hace update incremental O(log n).
- Sin **domain separation** (0x00 hoja / 0x01 nodo) → segunda-preimagen posible.
  RFC 9162 lo exige. El port lo hereda obligatoriamente.
- Sin **inclusion ni consistency proofs** — son lo que da completitud y split-view
  detection ([[OSM-026]]). El port los implementa o no cruza.

**Tests de paridad obligatorios**: el Rust debe producir raíces y proofs idénticas a las
del Python para los mismos vectores de entrada. Sin paridad bit-a-bit, no cruza la compuerta.

## Estructura propuesta (si se activa)

```
src/atlas/transparency/
    merkle_rs/           # crate Rust
        Cargo.toml
        src/lib.rs       # PyO3 bindings: merkle_root, inclusion_proof, verify_inclusion,
                         #                consistency_proof, verify_consistency
    merkle_tree.py       # permanece como referencia + fallback si bwrap no tiene Rust
    _merkle_backend.py   # selector: intenta importar merkle_rs; fallback a merkle_tree
```

`_merkle_backend.py` garantiza que el fallback Python sigue funcionando si el crate Rust
no está compilado — crítico para CI sin toolchain Rust y para el test suite.

## Criterios de compuerta

1. **Verificable**: tests de paridad Python↔Rust contra vectores conocidos (RFC 9162 test
   vectors + los existentes en `tests/test_transparency_merkle_tree.py`).
2. **Coherente**: conserva RFC 9162 (domain separation, proofs). No regresa el modelo de
   confianza.
3. **Probado**: paridad + benchmark que demuestre mejora ≥2× en p95 bajo carga de activación.
   Sin benchmark, sin cruce.
4. **Mantenible**: `_merkle_backend.py` con fallback Python. CI sin Rust debe seguir verde.
   El coste de mantenimiento del crate se justifica en el benchmark.
5. **Sancionado**: PDP, con benchmark sobre la mesa. No antes.

## Límites honestos

- **Optimización prematura**: sin E2E y sin perfil, esta OSM no debería existir en el código.
  Existe en la membrana como registro de la idea y de *por qué no se hace todavía*.
- **Coste permanente**: Rust añade toolchain, build y divergencia de implementación.
  Si OSM-006 (memoización Python) cierra el gap, esta OSM se archiva sin pena.
- **Dos implementaciones divergen**: los tests de paridad son obligatorios y frágiles de
  mantener a medida que evoluciona el protocolo. Cada cambio en `merkle_tree.py` requiere
  cambio paralelo en el crate.
