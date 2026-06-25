# Diseño — f2-6 (mitad tratable): separación personal/factual

<!-- Spec de brainstorming. 2026-06-25. Reencuadrado por el Cónclave (council, 2026-06-25):
     f2-6 literal = FAIL (apunta a MemoryManager inexistente + implica clasificación automática =
     muro 1c medido-no-usable). Este spec = la MITAD TRATABLE. Estado vivo en WORK_LEDGER.md. -->

Item de backlog: `f2-6-personalization-vs-contamination` (`docs/backlog.yaml`).

## Objetivo

Impedir que las memorias **personales** (sesgo/preferencia del usuario, deseable para personalizar)
**contaminen** las memorias **factuales** (conocimiento objetivo). Concretamente: una frontera de
clase persistida en el índice, un recall que por defecto no mezcla, y expiración diferenciada por
clase. Sin clasificador automático (ver §"Por qué no auto-clasificar").

## Alcance (lo tratable) y NO-alcance (el muro)

- **SÍ:** eje de clase explícito + filtrado de recall + TTL por-ítem con default por clase + barrido
  perezoso. Todo reusando `SqliteMemoryIndex`; NO se crea un `MemoryManager` (no existe; f2-6 literal
  apuntaba a un módulo inexistente — mismo error que tuvo f2-4).
- **NO (muro explícito):** clasificación *automática* personal/factual. El caller **declara** la clase
  al escribir; no se infiere del texto. Ver §"Por qué no auto-clasificar".

## Por qué no auto-clasificar (la decisión central, no un detalle)

Auto-clasificar exigiría un detector que, dado el *texto* de una memoria, juzgue "sesgo subjetivo"
vs "hecho objetivo" — un juicio semántico/pragmático, no léxico.

**Ya se midió un problema de forma idéntica en este repo y falló.** El muro 1c atacó "intención vs
tema" con un detector contrastivo sobre embeddings: separación ×2-3 pero **~33% de falsos positivos
en la frontera** → veredicto "no es detector usable"
(`docs/reference/reports/immune_intent_vs_topic_contrastive.md`). Personal-vs-factual es la misma
naturaleza (subjetivo vs objetivo), no capturable de forma fiable por embeddings + umbral.

**Aquí el fallo es PEOR que no clasificar.** ~33% de error fronterizo ⇒ ~1 de cada 3 memorias dudosas
mal etiquetada. Una memoria *personal mal clasificada como factual* **contamina el almacén factual** —
justo lo que f2-6 existe para impedir. Un clasificador no fiable da falsa confianza mientras filtra
contaminación: activamente dañino.

**El etiquetado explícito SÍ es fiable** porque usa **procedencia conocida**, no inferencia: una
preferencia declarada por el usuario → `personal`; un hecho ingerido por el pipeline knowledge-src
(url+fecha+hash) → `factual`. No se adivina; se declara. Cero error de clasificación.

**La puerta no se cierra (matiz honesto):** lo medido-inservible fue el detector *barato*
(embeddings/contrastivo). Un LLM-como-juez podría batirlo, pero (a) es caro (LLM por escritura), (b)
no está medido aquí, (c) hasta un LLM contamina con su tasa de error. `wire-before-claim`: no se
construye hasta medir que bate al etiquetado explícito. El diseño no lo impide — `memory_class` es un
campo que un clasificador futuro podría *poblar* como hook opcional, midiendo antes su error.

## Modelo de datos (columnas nuevas en `SqliteMemoryIndex`, migración idempotente)

- `memory_class TEXT NOT NULL DEFAULT 'factual'` — valores `personal | factual`. Eje dedicado,
  ortogonal a `record_type` (analytic/empirical/episodic, que se queda como está). Migración: filas
  existentes → `factual` (lo seguro/objetivo; nada es personal hasta declararlo).
- `expires_at REAL` (epoch, nullable) — **por-ítem**, pero el **default lo da la clase** al escribir si
  el caller no lo pasa: `personal → created_at_epoch + PERSONAL_TTL_S`; `factual → NULL` (sin
  expiración). El caller puede pasar un `expires_at`/`ttl_s` explícito que tiene prioridad sobre el
  default de clase.
- Constante de módulo: `PERSONAL_TTL_S = 90 * 24 * 3600` (90 días; constante, diseñada-para-ajustar).

## API

- `upsert(record, ..., memory_class: str = "factual", expires_at: float | None = None)` — persiste la
  clase; si `expires_at is None` y `memory_class == "personal"`, deriva el default; si `factual`, NULL.
  Retrocompat: callers actuales (sin estos kwargs) → factual sin expiración (comportamiento de hoy).
- `recall(query, ..., memory_class: str | None = None)`:
  - `None` (default) → **solo factual**, excluyendo expirados. Retrocompatible (todo lo viejo es factual).
  - `"personal"` → solo personal, excluyendo expirados.
  - (no se acepta "mezclar todo en un ranking único" — esa es la contaminación que se evita).
- `recall_split(query, ...) -> tuple[list[RecallResult], list[RecallResult]]` — devuelve
  `(factual, personal)` en **buckets separados**, ambos excluyendo expirados. Para callers que quieren
  personalización + hechos sin mezclar el ranking. No cambia el tipo de retorno de `recall`.
- `expire_stale() -> int` — retira (vía el mecanismo de retiro/shred existente, NO uno nuevo) los ítems
  con `expires_at <= now`. **On-demand, sin daemon/scheduler.** Devuelve el nº retirado.
- Todos los caminos de recall filtran `expires_at <= now` en caliente (un ítem vencido no aparece
  aunque `expire_stale` no se haya llamado aún).

## Interacciones (respetar lo existente)

- **Tenant (f2-5):** la clase es ortogonal al `tenant`; todos los filtros nuevos se aplican DENTRO del
  filtro de tenant existente. Un test cubre clase × tenant.
- **WriteGate (f2-4/f2-11):** ortogonal; `memory_class` no cambia la evaluación de procedencia.
- **Cifrado/shred (f2-2/f2-9):** `expire_stale` reusa el retiro existente (que ya destruye la clave en
  shred); no se inventa borrado nuevo.

## Tests (verify-the-real-case)

- **No-mezcla:** escribir N personal (sesgadas) + M factual con el mismo tema; `recall(query)` default
  NO devuelve ninguna personal; `recall(query, memory_class='personal')` devuelve solo personal;
  `recall_split` las separa en dos buckets.
- **Contaminación sintética:** inyectar personal que "contradice" un factual del mismo tema → el recall
  factual default es idéntico con y sin las personales (no las ve).
- **TTL:** personal con `expires_at` pasado NO aparece en recall y `expire_stale()` lo retira (cuenta);
  factual sin expiry persiste; `expires_at` explícito del caller gana sobre el default de clase.
- **Migración:** una fila escrita antes de la columna → `memory_class='factual'`, recuperable por
  recall default.
- **Tenant:** personal del tenant A no aparece en `recall(memory_class='personal')` del tenant B.

## Definition of done (estándar del repo)

Tests verdes + mypy strict + `WORK_LEDGER.md` actualizado en el mismo commit + `docs/backlog.yaml`
(`f2-6 status: done` con nota de que es la mitad tratable; el clasificador automático queda como muro
registrado) + nota en este spec. `wire-before-claim`: no se declara "separación lograda" sin los tests
de contaminación verdes.

## Fuera de alcance (registrado, no construido)

- **Clasificador automático personal/factual** = muro (1c). Posible follow-up SOLO como investigación
  medida: ¿un LLM-juez bate al etiquetado explícito sin contaminar? No antes de medir.
- Caller-side: que el pipeline knowledge-src marque `factual` y la captura de preferencias marque
  `personal` es cableado del *caller*, no de este índice — follow-up de wiring (como f2-7/f2-8/f2-11).
