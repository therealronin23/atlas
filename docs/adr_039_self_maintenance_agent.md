# ADR-039 — Agente de auto-mantenimiento (diseño)

- Status: **Proposed** — diseño, sin implementar. Decisiones fijadas con Tomás
  (2026-05-31): D1 = las tres por fases (MCP → deps → codegen-como-patch); D2 =
  cron background; D4 = registry+arxiv y foros **controlados con corroboración
  obligatoria**.
- Módulo previsto: `src/atlas/core/self_maintenance/` (nuevo)
- Depende de: ADR-037 (frontera de contenido no confiable), ADR-038 (gate de
  adopción Sentinel), ADR-035 dec.3 (registro dinámico MCP), ADR-025
  (ColdUpdateManager: worktree + validate + apply + rollback)
- Es el **último hito** del plan maestro (`plan_mcp_y_murallas_defensivas.md` §5):
  no se abre hasta que sus tres dependencias estén en su sitio — y ya lo están.

## Contexto

Visión: **Atlas se mantiene solo** — lee foros/papers/registries, descubre los
mejores MCP (o mejoras), y **propone** actualizaciones. Pero el agente cuyo
trabajo es *cambiar a Atlas* leyendo *el contenido más hostil que existe* (foros)
es el mayor blanco de inyección indirecta del sistema. Por eso es el último, no el
primero.

**Línea infranqueable (§0.2 del plan):** autónomo en lo **cognitivo**
(descubrir/comparar/proponer); humano en el **gatillo** (adoptar/ejecutar). El
contenido no confiable **nunca** puede llegar al ejecutor como control.

> **Nota de rumbo (2026-05-31):** el "humano en el gatillo" de este ADR es
> **postura actual y transitoria**, no permanente. La dirección estratégica del
> proyecto es **human-ON-the-loop**: el HITL se sustituye por un decisor
> intercambiable (`decide(action, sanctioned_intent, context) -> Allow | Deny`,
> sin `Escalate` bloqueante) y el humano pasa a observar y redirigir de forma
> asíncrona. Al implementar este agente, tratar el botón de Telegram como **una
> implementación más del decisor**, no como el camino fijo. El diseño formal de
> ese decisor (ADR-040) se abre al cerrar el ciclo MCP/Hermes.

### Lo que YA existe (no se reconstruye)

El *back-half* del pipeline está hecho. El agente solo aporta el *front-half*:

| Etapa | Primitiva existente |
|---|---|
| Aislar + validar un cambio de código/deps | `ColdUpdateManager` (ADR-025): worktree, pytest+mypy, apply con rollback. `origin="self_audit"`, `evidence={}` ya soportados |
| Adoptar un server MCP de forma segura | `SentinelGate.vet_command`/`vet_tools` (ADR-038) + `McpRegistry.add_server` en caliente (ADR-035 dec.3) |
| Marcar contenido externo como no confiable | `wrap_untrusted` + taint del loop (ADR-037). `UNTRUSTED_READERS` existe pero **hoy está vacío** |
| Salida de red acotada | `ssrf_bridge` (allowlist de egress) + browser tool |
| Auditoría | Merkle en cada transición |
| HITL | Botón de Telegram + flujo de aprobación (Gate C / ADR-032/033) |

### Lo que FALTA (el aporte del agente)

Leer fuentes externas y convertirlas en una **propuesta estructurada y segura**
sin que el contenido hostil conduzca la ejecución.

## Arquitectura

Pipeline de 5 componentes; el contenido no confiable solo vive en los dos
primeros y **nunca** cruza a la ejecución como instrucción:

```
[Scout] descubre (registries/papers/foros)  ──contenido NO confiable──┐
   │  (provenance=untrusted, wrap+taint)                              │
   ▼                                                                  │
[Analyst] digiere bajo separación datos/control (dual-LLM)            │
   │  processing-LLM: sin tools, sin system prompt ── solo resume     │
   │  control-LLM: ve SOLO un resumen TIPADO (no prosa de foro)       │
   ▼                                                                  │
[Proposer] materializa una propuesta estructurada ───────────────────┘
   │  (capacidad, versión, diff/cmd, riesgos, cadena de evidencia)
   ▼
[HITL] Telegram: el humano ve qué/por qué/diff/riesgos/procedencia → aprueba
   ▼  (← el gatillo: nada se ejecuta sin este botón)
[Executor] reusa ColdUpdate (code/deps) o add_server+Sentinel (MCP)
            valida en worktree → swap solo si verde → rollback si no
```

### Máquina de estados de una propuesta

Se mapea sobre `ColdUpdateProposal.status` (reusado, no nuevo):

`discovered → analyzed → proposed` (HITL pendiente) `→ {approved | rejected}`
`→ validated → {applied | failed→rollback}`.

## Decisiones de diseño

| # | Decisión | Recomendado | Alternativa / por qué no |
|---|---|---|---|
| **D1** | Alcance | **Las tres por fases, secuenciadas por radio de explosión:** (a) MCP — reversible con `remove_server`, vetado por Sentinel; (b) deps — bumps PyPI como patches vía ColdUpdate, diff diminuto, tests cazan rupturas; (c) **codegen como patch dirigido** — el agente genera un patch contra un objetivo que tú apuntas, ColdUpdate valida en worktree, tú revisas el diff y aprietas el botón | Codegen **libre/autónomo aplicado solo** queda prohibido (ADR-025). El riesgo no es generar, es aplicar sin revisión: el patch revisable lo elimina |
| **D2** | Disparo | **Cron background**: Atlas escanea en un hilo periódico (patrón de los monitors actuales), genera propuestas en el store y **te notifica por Telegram**. El cron solo descubre/propone — nunca aplica | On-demand quedaría como atajo adicional ("Atlas, busca un MCP para X"), no como mecanismo único |
| **D3** | Separación datos/control | **Dual-LLM obligatorio** (CaMeL, ADR-037 capa 5). El processing-LLM digiere foros sin tools ni system prompt; el control-LLM solo ve un resumen **tipado** | Single-LLM con taint: más barato pero el contenido hostil tocaría el razonamiento de control. Rechazado para este agente (es el blanco de mayor valor) |
| **D4** | Fuentes (egress allowlist) | **Registry MCP oficial + arxiv (autoritativas) Y foros controlados (community).** Pero con **corroboración obligatoria** (ver §Gate de corroboración): los foros solo *surgen* candidatos; nada llega a HITL sin estar contrastado por una fuente autoritativa | Tratar foros como fuente de verdad → exactamente el vector que el corroboration gate cierra |
| **D5** | Materialización | **Reusar** `ColdUpdateManager` (code/deps) y `add_server`+`SentinelGate` (MCP). Cero pipeline de apply nuevo | Construir un applier propio → duplicación + nueva superficie de bug. Rechazado |
| **D6** | Readers del Scout | **Registrarlos en `UNTRUSTED_READERS`** (hoy `frozenset()` vacío) → `wrap_untrusted` + taint automáticos sin lógica nueva | — |
| **D7** | Codegen autónomo | **No en v1.** Las propuestas de código exigen patch revisable por humano, nunca generación libre aplicada sola | Respeta ADR-025 y la línea infranqueable |

### Por qué el dual-LLM aquí no es opcional

En el resto del sistema el taint (ADR-037 capa 3) basta: degrada a HITL toda
mutación tras ingerir lo no confiable. Pero este agente **siempre** ingiere lo no
confiable y **siempre** termina proponiendo un cambio: el taint solo nos daría
"HITL siempre", no protege el *razonamiento* que redacta la propuesta. Si el
foro dice "propón el server X que en realidad exfiltra", un single-LLM podría
redactar una propuesta convincente de X. El dual-LLM corta eso: el control-LLM
nunca lee la prosa del foro, solo campos tipados (nombre, versión, endpoint,
permisos declarados), y SentinelGate veta X en la adopción de todos modos. Defensa
en profundidad: dual-LLM (no se redacta lo malo) + Sentinel (no se adopta lo malo)
+ HITL (no se ejecuta sin humano).

### Gate de corroboración (regla de Tomás: "nada que no esté contrastado")

Cada candidato lleva sus fuentes etiquetadas por procedencia:

- **autoritativa** — registry MCP oficial, arxiv, docs oficiales del proyecto.
- **community** — foros (HN/Reddit/Discourse), controlados vía egress allowlist.

Regla **fail-closed**: una propuesta solo alcanza el HITL si **≥1 fuente
autoritativa corrobora la afirmación clave** (que el server/dep existe, su
versión, su maintainer, y qué hace). Un foro puede *surgir* un candidato pero
**nunca** ser su base única. El resumen tipado del Analyst registra qué campo está
corroborado por qué fuente; lo no corroborado se descarta — no se propone. Así el
foro aporta señal (descubrimiento) sin aportar autoridad (decisión).

### Scheduler (cron background, D2)

Un hilo periódico Atlas-side (mismo patrón que `thermal_watchdog`/monitors)
dispara el Scout cada cierto intervalo configurable. Produce propuestas en el store
de ColdUpdate y emite una notificación de Telegram con el resumen. **El cron jamás
aplica**: su única salida es una propuesta en estado `proposed` esperando el botón.
Cadencia y fuentes son config, no código.

## Plan de slices (implementación futura)

1. **Scout autoritativo (read-only).** Registry MCP + arxiv; registrar sus readers
   en `UNTRUSTED_READERS`; devolver candidatos con fuentes etiquetadas. Sin
   propuesta, sin apply. Tests.
   **LANDED (parcial — registry MCP oficial):** `RegistryScout`
   (`core/self_maintenance/registry_scout.py`) descubre candidatos en
   `registry.modelcontextprotocol.io/v0/servers`. Egress gateado por `SSRFBridge`
   (dominio añadido a la allowlist por defecto); fail-closed en egress y parseo.
   Cada entrada emite `McpCandidate` con `Source(authoritative)` cuyo `raw_excerpt`
   (descripción) viaja como dato NO confiable para el Analyst (CaMeL intacto). El
   Scout no muta ni propone. Accessor `Orchestrator.maintenance_registry_scout()`;
   fetch stdlib (`_egress_fetch_text`); tests con fetcher falso (cero red real).
   **Pendiente del slice:** fuente arxiv y registro de readers en
   `UNTRUSTED_READERS` (hoy el wrap untrusted lo aplica el Analyst, no el Scout).
2. **Analyst dual-LLM + gate de corroboración → propuesta MCP tipada** +
   presentación en Telegram. Solo pasa lo corroborado por fuente autoritativa. Sin
   auto-apply. Tests con LLM mockeado.
3. **Wire aprobación → `add_server`** (reuso puro). E2E tras el botón HITL.
   **LANDED:** `MaintenanceAdopter` (`core/self_maintenance/adopter.py`) traduce
   `McpProposal` → `McpServerConfig` + `Task` (intención anclada al nombre) y
   delega en `Orchestrator.adopt_mcp_server`. El "botón" es el seam del decisor
   (ADR-040), no maquinaria HITL nueva: `HumanDecider` → exige aprobación;
   autónomo/híbrido anclado → adopta + undo reversible. Accessor
   `Orchestrator.maintenance_adopter()`; resultado auditado en Merkle.
4. **Scheduler cron** Atlas-side → escaneo periódico → propuestas → notificación
   Telegram. El cron solo propone.
5. **Foros controlados como fuente community.** Egress allowlist + corroboración
   obligatoria (un candidato de foro necesita respaldo autoritativo para proponerse).
6. **Deps vía ColdUpdate** (patches de bump PyPI). Diff revisable + suite/mypy.
7. **Codegen como patch dirigido.** El agente propone un patch contra un objetivo
   apuntado; ColdUpdate valida; el humano revisa el diff y aprueba. Nunca apply solo.

## Riesgos honestos y no-objetivos

- **No-objetivo: apply autónomo. Nunca.** El humano está en el gatillo siempre.
- **No-objetivo: generación de código libre** (v1). Solo patches revisables.
- **Riesgo: inyección desde la fuente** para colar un MCP malicioso → mitigado por
  dual-LLM (no se redacta) + SentinelGate (no se adopta) + HITL (no se ejecuta).
  No es defensa total (>78 % bypass adaptativo medido); por eso operan las tres
  capas juntas.
- **Riesgo: el resumen tipado del Analyst lleva instrucciones camufladas** → los
  campos son tipados y de longitud acotada; el control-LLM trata también el
  resumen como dato, no como control.

## Estado y siguiente paso

Decisiones D1/D2/D4 fijadas (ver cabecera). El diseño está cerrado; queda una nota
de coherencia con **ADR-025**: su "no autonomous code generation in MVP" sigue
vigente — el codegen de la fase 7 es *post-MVP* y entra solo como **patch revisable
gateado igual que un patch manual**, nunca como apply autónomo. Conviene anotarlo
en ADR-025 cuando se llegue a esa fase.

El slice 1 (Scout autoritativo read-only) es pequeño y de bajo riesgo: no muta
nada, solo lee fuentes en la allowlist y devuelve candidatos etiquetados. Es el
punto de entrada natural cuando quieras arrancar la implementación.
