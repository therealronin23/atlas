# OSM-029 — Núcleo de rendimiento en Rust (Merkle + embeddings + monitor)

Fecha: 2026-06-17 · Estado: **Difusión** (ver [[OSM-000]]) · Origen: `idea avance 3.md` ·
Contexto: `src/atlas/transparency/merkle_tree.py`, [[OSM-024]] (latencia en path),
[[OSM-028]] (metadata-monitor), regla 6 de CLAUDE.md (stdlib/lenguaje primero).

---

## Contexto

Un filtro obligatorio en el path ([[OSM-024]]) añade latencia a **todas** las peticiones.
Las partes calientes son el log Merkle (append + proofs) y el metadata-monitor (embeddings +
reglas, [[OSM-028]]). El chat 3 propone reescribir esas partes en Rust por rendimiento y
seguridad de memoria, y aportó código de Merkle y embeddings en Rust.

## La idea

Un núcleo de rendimiento en Rust para las rutas calientes, tras una frontera FFI limpia con
el resto de Atlas (Python):

- **Merkle en Rust**: append incremental + inclusion/consistency proofs, expuesto vía FFI
  (PyO3) al `transparency/` de Python.
- **Embeddings + reglas deterministas en Rust** para el metadata-monitor por causa.
- **Frontera estable**: el Python sigue orquestando (Decider, LessonStore, organismo); Rust
  solo hace el cómputo caliente. No se reescribe Atlas; se acelera un borde.

## Encaje en Atlas

- **`merkle_tree.py`** es hoy el de referencia y es **fiel a RFC 9162** (domain separation
  0x00/0x01, inclusion/consistency, STH). El Rust debe ser un *port que conserva* esa
  fidelidad, no una versión nueva más simple.
- **FFI**: PyO3 mantiene el núcleo Python como dueño de la orquestación; Rust como acelerador.
- **[[OSM-028]]**: los embeddings del monitor son el otro candidato natural a Rust.

## Correcciones de verificación

**El Merkle en Rust del chat 3 es una regresión respecto a lo que ya existe. No se porta tal cual.**

- El `compute_root` del chat recomputa la raíz entera desde las hojas en cada `append` →
  **O(n) por inserción**, O(n²) en agregado. El Python actual hace update incremental.
- No tiene **domain separation** (0x00 hoja / 0x01 nodo) → vulnerable a ataques de
  segunda-preimagen entre hoja y nodo. RFC 9162 lo exige.
- No implementa **inclusion ni consistency proofs** reales — son justo lo que da la
  completitud y la detección de split-view ([[OSM-026]]).
- Conclusión: el port a Rust **debe preservar** domain separation + proofs + update
  incremental del `merkle_tree.py` actual. Acelerar no es simplificar.

## Criterios de compuerta

1. **Verificable**: el Rust debe pasar los **mismos tests** que `merkle_tree.py` (paridad de
   raíces y proofs contra vectores conocidos). Sin paridad, no cruza.
2. **Coherente**: no cambia el modelo de confianza; solo mueve cómputo. Conserva RFC 9162.
3. **Probado**: tests de paridad Python↔Rust + benchmark que demuestre la mejora de latencia
   que justifica la complejidad.
4. **Mantenible**: aquí está el coste real. Rust añade toolchain, build y superficie de
   mantenimiento a un proyecto hoy Python. **Debe justificarse con números** (latencia
   medida en path), no por gusto — regla 6 de CLAUDE.md aplicada a un lenguaje, no una dep.
5. **Sancionado**: PDP, con el benchmark sobre la mesa.

## Límites honestos

- **Coste de mantenimiento de un segundo lenguaje**: real y permanente. Si la latencia en
  Python es aceptable con caching/memoización, **esta OSM no debería cruzar todavía** — es
  optimización prematura hasta tener una demo E2E y un perfil real.
- **Riesgo de divergencia**: dos implementaciones de Merkle (Python + Rust) pueden divergir;
  los tests de paridad son obligatorios y frágiles de mantener.
- **Prioridad**: viabilidad media en valor, alta en coste. Probablemente espera a que el path
  E2E exista y se mida ([[OSM-024]]).
