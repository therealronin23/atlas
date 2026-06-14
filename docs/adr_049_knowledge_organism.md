# ADR-049 — Organismo de conocimiento: adquisición, verificación y acumulación

Fecha: 2026-06-14 · Estado: **Aceptado** (slice 1 completo; ver diferidos) ·
Contexto: ADR-041 (UniversalVerifier), ADR-044 (LessonStore), ADR-045/046
(swarm), ADR-047 (panel adversarial + grounding), ADR-035 (cliente MCP).

---

## Contexto y motivación

Hasta la fecha, Atlas mejora a partir de su propio historial: lecciones de
fallos internos (LessonStore), propuestas de cambio sobre su propio código
(ColdUpdate), verificación de sus propios artefactos (UniversalVerifier). Es
un sistema **introspectivo**.

El paso siguiente es convertirlo en un **organismo de conocimiento vivo**: Atlas
adquiere información del mundo exterior —de miles de APIs públicas, MCP,
skills, feeds, herramientas, registros— la verifica con el mismo motor que ya
tiene (capa 1), la acumula por dominio, y la usa en dos direcciones:

1. **Misiones hacia afuera** — responder preguntas de cualquier dominio con
   conocimiento fundamentado, no alucinado. La persona es una misión, no un
   sistema separado.
2. **Retroalimentación hacia adentro** — el conocimiento externo mejora al
   propio Atlas: plugins nuevos, skills disponibles, vulnerabilidades en sus
   deps, patrones de arquitectura, mejoras de sus propios productores. Si algo
   amplía o mejora el sistema → propuesta automática; si hay duda → escalar al
   PDP (decider intercambiable, no fijado al humano).

**Alcance del "mejorarse a sí mismo":** no solo CVEs de deps. Todo lo que
amplíe la capacidad de Atlas entra en el ciclo: herramientas MCP recién
publicadas que Atlas puede registrar, skills del ecosistema que Atlas puede
cargar, cambios de API en fuentes que Atlas ya usa, patrones de código que
la comunidad ha identificado como mejores, versiones de sus propias dependencias.
La columna de conocimiento es el conducto; la diferencia entre "dato de dominio"
y "señal de auto-mejora" la establece el `SelfImprovementBridge`, extensible
por tipo de artefacto.

Las "personas" (agente inmobiliario, experto en ciberseguridad ofensiva) no son
sistemas separados. Son **misiones encima de esta columna genérica**: la
columna es siempre la misma, la misión elige el dominio y los filtros.

La ventaja diferencial frente a un RAG genérico: Atlas ya tiene un motor de
verificación (capa 1, ley de entrada). Por eso su conocimiento es **verificado
y fundamentado**. El grounding —hash del raw + proveniencia de la fuente— hace
que cada pieza de conocimiento lleve consigo la evidencia de que fue
comprobada, no ingerida a ciegas.

---

## Arquitectura

```
Mundo exterior
      │
  [Source]  ← KnowledgeSource Protocol (HttpApiSource, futuro: OsvDepSource,
      │         conector MCP, feeds RSS, etc.)
      ▼
  [KnowledgeArtifact]  ← ArtifactKind.KNOWLEDGE; lleva raw + hash + source
      │
  [KnowledgeVerifier]  ← grounding: hash integridad + comprobación de
      │                   proveniencia; falla si el raw fue alterado
      ▼
  [KnowledgeBase]  ← ley de entrada: solo lo verificado persiste (JSONL
      │              por dominio, append-only); espejo de LessonStore
      ▼
  [Mission]  ← filtra la base por dominio/etiquetas; MissionRunner.run_once
      │        ejecuta un ciclo fetch→verify→store→query
      │
      ├── respuesta de dominio (ciberseguridad, inmobiliario, etc.)
      │
      └── [SelfImprovementBridge]  ← detecta findings que afectan al propio
              │                      código de Atlas (deps, patterns internos)
              ▼
         señal al self-maintenance loop (ColdUpdate / audit)
```

El flujo es unidireccional excepto en el puente de auto-mejora, que cierra el
ciclo: el mundo exterior alimenta la introspección.

---

## Tabla de decisiones

| # | Decisión | Elección | Por qué |
|---|---|---|---|
| 1 | Alcance de la columna | Genérica multi-dominio, no scraper de un uso | Reutilizable para cualquier misión; el dominio es un parámetro, no la arquitectura |
| 2 | Primera fuente | API CVE/OSV.dev (gratuita, sin auth) | Fiable, alimenta la persona de ciberseguridad, leer-únicamente, sin riesgo operacional |
| 3 | Grounding | Proveniencia + hash del raw en cada artefacto | Conocimiento verificado: cada pieza lleva evidencia; distingue datos reales de generados |
| 4 | Ley de entrada en KnowledgeBase | Solo lo verificado por KnowledgeVerifier entra | Espejo de LessonStore: la base nunca contiene basura sin verificar |
| 5 | Egress HTTP | SSRFBridge fail-closed (muralla existente) | Reutiliza la protección del ADR-037; no se añade nueva superficie |
| 6 | Fetcher | Inyectable; stdlib `urllib` primero | Testeable sin red (mock); cumple regla stdlib-first; se puede sustituir sin cambiar la columna |
| 7 | Persistencia | JSONL por dominio, append-only | Simple, sin dependencias, particionado; coherente con LessonStore |
| 8 | Personas/misiones | Misiones encima de la columna, no sistemas separados | La columna es el invariante; la misión aporta dominio, fuentes y filtros |
| 9 | Retroalimentación interna | SelfImprovementBridge como puente explícito | El conocimiento externo afecta al código propio sin acoplar la columna al self-maintenance |

---

## Slice 1 — HECHO

Todos los componentes son Python puro, sin dependencias nuevas.

| Pieza | Archivo | Qué hace |
|---|---|---|
| T1 | `src/atlas/core/verify.py` | `ArtifactKind.KNOWLEDGE` registrado en el verificador universal |
| T2 | `src/atlas/knowledge/artifact.py` | `KnowledgeArtifact`: contenedor con raw, hash, fuente, dominio, etiquetas |
| T3 | `src/atlas/knowledge/sources.py` | `KnowledgeSource` Protocol + `HttpApiSource` (fetcher inyectable) |
| T4 | `src/atlas/knowledge/sources.py` | `OsvDepSource`: fuente CVE/OSV.dev para deps del proyecto |
| T5 | `src/atlas/knowledge/verifier.py` | `KnowledgeVerifier`: grounding (hash + proveniencia) sobre `KnowledgeArtifact` |
| T6 | `src/atlas/knowledge/base.py` | `KnowledgeBase`: ley de entrada; persiste JSONL por dominio |
| T7 | `src/atlas/knowledge/mission.py` | `Mission` + `MissionRunner.run_once`: ciclo fetch→verify→store→query |
| T8 | `src/atlas/knowledge/self_improvement.py` | `SelfImprovementBridge`: detecta findings relevantes al código de Atlas |

---

## Diferido (explícito)

Los siguientes puntos se reconocen como necesarios pero se posponen
deliberadamente para no bloquear el slice 1. Orden sugerido de valor:

### Slice 2 — Version-range matching (SelfImprovementBridge)

El bridge actual emite TODAS las vulns históricas de un paquete sin comparar
la versión instalada contra los rangos `affected`/`fixed` de OSV. Resultado:
ruido (fastapi 0.136.3 marcada con un GHSA fixed en 0.65.2). El filtro de
relevancia real: si `installed_version` cae dentro de un rango
`[introduced, fixed)` del OSV payload → finding genuino; si no → descartar.
Implementar `_version_in_range(installed: str, ranges: list[dict]) -> bool`
en `self_improvement.py` usando `packaging.version` (ya transitiva).

### Slice 3 — Daemon hacia afuera + cableado al self-maintenance loop

- **`ATLAS_KNOWLEDGE_SCHEDULER`** gated daemon en `AtlasServiceRunner` (mismo
  patrón que swarm/audit_sample): ejecuta misiones en segundo plano, cadencia
  configurable.
- **Cableado vivo del SelfImprovementBridge** — `SelfRelevantFinding` →
  propuesta ColdUpdate (dep-bump o parche de config) vía el scheduler real.
  Primer caso concreto: CVE con `fixed_version` conocida → `DepBumpProposal`.
  Si hay duda → decider (PDP intercambiable). Si es claro (severidad alta +
  fixed_version conocida + version-range confirma afectación) → propuesta
  automática.

### Slice 4 — MCP como fuente + Skills autodescubribles

- **MCP como fuente de conocimiento** — envolver herramientas MCP (ADR-035)
  como `KnowledgeSource`; Atlas puede registrar herramientas externas recién
  publicadas que amplíen sus capacidades. Cuando la columna detecta un MCP
  nuevo relevante → propuesta de integración al self-maintenance loop.
- **Skills autodescubribles** — el ecosistema de skills puede ser un dominio
  de conocimiento. Atlas rastrea skills disponibles, las compara con las
  instaladas, y propone incorporar las que amplíen su capacidad.

### Slice 5 — Conectores de dominio + personas

- **Feeds RSS/Atom, NVD, EPSS** — más señales de seguridad sin deps nuevas.
- **Datos inmobiliarios** — idealista/fotocasa (scraping + parsing);
  primer caso de misión de dominio no-seguridad.
- **Misiones concretas de dominio** — persona inmobiliario (precios,
  registros, alertas) y persona ciberseguridad ofensiva (CVEs activos,
  exploits, advisories); la columna las aloja sin cambio de arquitectura.
- **Reporte por Telegram** — notificar findings al twin Hermes (canal ya
  existe; integración con misión).

### Slice 6 — Skills por dominio que mejoran con el tiempo

- KnowledgeBase acumulada como contexto de grounding para los productores
  (ADR-048): cada productor recibe el fragmento de KB relevante como contexto
  antes de generar → cierra el ciclo conocimiento → calidad de generación.
- Grounding bidireccional: los artefactos generados por los productores
  referencian la KB que los fundamentó (trazabilidad de vuelta a fuente).
