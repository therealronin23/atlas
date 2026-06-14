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

El paso siguiente es convertirlo en un **organismo de conocimiento**: Atlas
adquiere información del mundo exterior, la verifica con el mismo motor de
verificación que ya tiene (capa 1), la acumula por dominio en una base
persistente, y la usa en dos direcciones:

1. **Misiones hacia afuera** — responder preguntas de dominio (ciberseguridad,
   inmobiliario, cualquier área) con conocimiento fundamentado, no alucinado.
2. **Retroalimentación hacia adentro** — el conocimiento externo vuelve al
   self-maintenance loop: un CVE de una dependencia propia es a la vez
   información de dominio y señal de auto-mejora.

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
deliberadamente para no bloquear el slice 1.

- **Daemon hacia afuera** — proceso que ejecuta misiones en segundo plano;
  requiere gating igual que swarm/audit_sample para no abrir superficie sin
  supervisión.
- **Reporte por Telegram** — notificar findings al twin Hermes (canal ya
  existe; requiere integración con la misión).
- **MCP como fuente de conocimiento** — el cliente MCP (ADR-035) puede
  envolver herramientas externas como fuentes; diferido para no añadir
  complejidad antes de validar la columna básica.
- **Misiones concretas de dominio** — persona inmobiliario (precios, registros)
  y persona ciberseguridad ofensiva (CVEs activos, exploits); el slice 1 deja
  la columna lista para alojarlas.
- **Cableado vivo del SelfImprovementBridge** — conectar la señal de
  `SelfImprovementBridge` al loop de `ColdUpdate`/audit en ejecución; ahora
  el puente existe pero la señal no llega al scheduler real.
- **Más conectores** — feeds RSS/Atom, APIs públicas de seguridad (NVD, EPSS),
  datos regulatorios, mercados inmobiliarios; la columna es agnóstica, solo
  hace falta implementar el Protocol.
- **Skills por dominio que mejoran con el tiempo** — usar la KnowledgeBase
  acumulada como contexto de grounding para los productores (ADR-048); cierra
  el ciclo conocimiento → calidad de generación.
