# Diseño — Enriquecimiento del catálogo (Pieza 1 de la línea "capacidades usables")

<!-- Doc interno de diseño (nombres internos OK). 2026-06-25. Plan→DISEÑO.
     Estado vivo en WORK_LEDGER.md. Refinado por el Cónclave (3 rondas, trío 3/3). -->

## Contexto y objetivo

El catálogo tiene 700+ entradas sembradas que son **solo nombres** (`name + kind + procedencia`,
sin `purpose`). Nadie —ni un humano ni un modelo— puede saber qué hace "3D_Generative_Artist" ni
cuándo usarlo. **Objetivo de la Pieza 1:** convertir nombres → **descripción-afirmada + señal de
popularidad**, tirando metadatos de la FUENTE de cada entrada. **Enriquecer ≠ verificar.**

Es la base de la línea (Pieza 2 = trial-en-jaula + escáneres adoptados; Pieza 3 = routing hook).
Todo lo demás necesita esto primero.

## Principio: tres ejes ortogonales (nunca confundir)

Lección del Cónclave: tres cosas distintas, tres campos, ninguno se disfraza de otro.
1. **Qué AFIRMA que hace** → `purpose` (de la fuente) + `purpose_claimed: true` (sin verificar).
2. **Cuánto lo avala el mundo** → `signal` (`{stars, downloads, rating}`) — un PRIOR, no un estado.
3. **Si FUNCIONA de verdad** → `status` (candidato/verificado/instalado) — **NO se toca en Pieza 1**.

`wire-before-claim` intacto: enriquecer rellena claims etiquetados; el `status` sigue `candidato`.
La popularidad influye en triaje/confianza, **nunca** en estado.

## Alcance (Pieza 1 — qué SÍ y qué NO)

**SÍ:** para entradas cuya procedencia resuelve a una fuente con metadatos por-entrada (repo
GitHub o paquete npm), tirar: descripción → `purpose` (etiquetado `purpose_claimed`), y popularidad
→ `signal`. Idempotente. No ejecuta nada (solo fetch de metadatos).

**NO (Pieza 1):** NO verifica · NO ejecuta candidatos · NO cambia `status` · NO borra nada · NO
toca el routing. **Gap honesto declarado:** sub-ítems de awesome-lists (un nombre suelto en una
lista) y caracterización de prompts (leer el texto del prompt) quedan FUERA de Pieza 1 — requieren
resolver cada nombre a su repo / un paso de caracterización; se anotan como deuda, no se fingen.

## Modelo de datos (campos nuevos en la entrada del catálogo)

```yaml
# entrada existente: {name, kind, subsector, purpose?, tags, status, source?, ...}
# Pieza 1 añade/rellena:
purpose: "<descripción de la fuente>"      # solo si estaba vacío
purpose_claimed: true                       # afirmado, sin verificar (se quita al verificar)
signal: {stars: 1234, downloads: 400000, rating: 4.8}   # campos presentes según la fuente
```
Sin nuevo enum de estado. `signal` es un dict con las claves que la fuente provea (parcial OK).

## Componentes (unidades pequeñas, interfaces claras)

- **`src/atlas/mcp/enrichment.py`**:
  - `Enrichment` (dataclass): `purpose_claimed: str`, `signal: dict[str, int | float]`.
  - `EnrichmentFetcher` (Protocol): `fetch(source: str, name: str) -> Enrichment | None`.
    Devuelve None si la fuente no da metadatos para esa entrada.
  - `GithubEnrichment`: repo GitHub → `description` + `stargazers_count`. HTTP fetcher INYECTABLE
    (mismo patrón que los seeders existentes), `api.github.com` allowlisted vía gate SSRF.
  - `NpmEnrichment`: paquete npm → `description` + downloads. Fetcher inyectable, `registry.npmjs.org`
    + `api.npmjs.org` allowlisted.
  - `enrich_entry(entry: dict, fetcher: EnrichmentFetcher) -> dict`: rellena `purpose` SOLO si vacío
    (+ `purpose_claimed=true`) y `signal`; **deja `status` intacto**. Idempotente (re-enriquecer no
    duplica ni pisa un purpose ya verificado).
- **`scripts/mcp_enrich.py`**: recorre los candidatos con procedencia resoluble, aplica
  `enrich_entry` con el fetcher real, reporta cuántos enriquecidos / sin-metadatos / fuente-caída,
  y reescribe los YAML sembrados. `--offline`/dry-run = solo reporta. Fuentes caídas se aíslan
  (una fuente que falla no aborta el resto).

## Flujo

1. `mcp_enrich.py` carga las entradas sembradas con `source`.
2. Por entrada: resuelve el tipo de fuente (github/npm) → llama al fetcher → `Enrichment | None`.
3. `enrich_entry` mezcla: `purpose` (si vacío) + `purpose_claimed` + `signal`. `status` sin tocar.
4. Reescribe YAML; reporta cobertura por dominio + por estado de enriquecimiento.

## Manejo de errores / casos límite

- Fuente caída / 404 / rate-limit → `fetch` devuelve None, se aísla, se cuenta como "sin-metadatos"
  (no se inventa descripción). `wire-before-claim`.
- Entrada con `purpose` ya presente (p.ej. los `verificado` nuestros) → NO se pisa.
- Fuente sin tipo resoluble (awesome-list sub-ítem) → se salta, se cuenta como deuda.
- SSRF: todo fetch pasa por el gate y allowlist de dominios existentes.

## Tests (TDD)

- `enrich_entry` rellena purpose+claimed+signal con un fetcher fake; **`status` inalterado**.
- `enrich_entry` NO pisa un `purpose` ya existente.
- `enrich_entry` con `fetch`→None deja la entrada igual (sin purpose inventado).
- `GithubEnrichment` parsea description+stars de un payload fake (sin red; fetcher inyectado).
- `NpmEnrichment` parsea description+downloads de un payload fake.
- Idempotencia: enriquecer dos veces = mismo resultado.
- Live (importorskip / fuera de suite): un repo real devuelve stars>0 — smoke, no test de suite.

## Honestidad de capacidades (anotar al cerrar)

`enrichment` = **real** (código + consumidor `mcp_enrich.py` + tests) para fuentes github/npm.
Cobertura PARCIAL declarada: awesome-list sub-ítems y prompts NO cubiertos en Pieza 1.

## Definition of done

Tests verdes + mypy strict + `WORK_LEDGER.md` actualizado en el mismo commit + nota en
`CAPABILITIES.md` (real/parcial) + gap honesto declarado. Sin tocar `status` de ninguna entrada.

## Fuera de Pieza 1 — la línea (orden por dependencia)

- **Pieza 2** — trial-en-jaula per-kind (promueve a `probado-en-jaula`, NO a confiado; corre
  contenido) + escáneres adoptados por-primitivo (envueltos, no forkeados; prove-it'd) + barrido por
  saneamiento graduado (candidato rancio → cuarentena → delete, nunca de una pasada).
- **Pieza 3** — routing hook `UserPromptSubmit` que consume el catálogo ya enriquecido/verificado.
