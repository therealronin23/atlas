# ADR-052 — Asimilación completa de Odysseus bajo el sello Atlas

Fecha: 2026-06-15 · Estado: **Propuesto** (programa, no slice único) ·
Contexto: `absorption_master_plan.md` (regla: absorber patrones, no dependencias
incontroladas), Governance L0, capability tokens (ADR-020), AtlasExecutor,
MerkleLogger, Decider (ADR-040), AST Guard / SentinelGate (ADR-038),
BlockMemory (ADR-030), CascadeRouter (ADR-042), VerifiedProducer (ADR-048),
InferenceHub (ADR-016).

---

## Contexto y motivación

Odysseus (PewDiePie / pewdiepie-archdaemon, lanzado 31-may-2026, AGPL-3.0, 50K+
stars en días) demostró algo que Atlas no ha demostrado: **que existe demanda
real de un workspace de IA local y usable**. Es un producto completo —chat,
agente, cookbook de modelos, deep research, compare, documentos, memoria/skills,
email, notas/tareas, calendario, editor de imágenes, PWA móvil, MCP, 2FA,
deployment Docker— pero **sin** arquitectura de seguridad, auditoría ni
gobernanza.

Atlas es lo contrario: arquitectura de seguridad/auditoría/autonomía de primer
nivel, pero **CLI + dashboard básico**, sin features de productividad ni
deployment fácil.

**Decisión del usuario (explícita): asimilación COMPLETA, no parcial.** Queremos
**todo lo que a Atlas le falta de Odysseus, sin perder nada de lo que Atlas es,
tiene, o puede llegar a ser.** Este ADR define cómo hacerlo sin que sea ni un
copia-pega ni una dilución del sello Atlas.

### Lo que NO se negocia (el sello que no se pierde)

Toda feature asimilada se subordina a lo que ya somos. Se conservan, intactos y
por encima de cada feature importada:

Merkle audit · capability tokens · Decider/PDP · AST Guard / SentinelGate ·
self-audit · cold update · self-maintenance · swarm · VerifiedProducer ·
CascadeRouter · UniversalVerifier · BlockMemory · TimeTravel · GhostReplay ·
PII Surrogate · ThermalWatchdog · gobernanza constitucional · local-first /
sin telemetría · sin dependencia runtime de Anthropic/OpenAI/Codex.

Si una feature de Odysseus no puede convivir con estos invariantes, **se
reimplementa hasta que pueda, o no entra**. "Completa" significa cubrir todas las
capacidades, no importar todo el código.

---

## Decisión

Asimilación completa **por asimilación, no por adopción**: se estudia el código
de Odysseus como referencia y se **reimplementa cada capacidad dentro de la
arquitectura de Atlas**, salvo la infraestructura pura (Docker, PWA), que se
adopta tal cual por no ser lógica de negocio.

### La regla de oro de la asimilación

Cada feature asimilada **DEBE** pasar por los cuatro pasos de Atlas. Es la prueba
de admisión:

1. **CapabilityIssuer** — ¿qué permiso mínimo necesita?
2. **AtlasExecutor** — ejecutar con audit.
3. **MerkleLogger** — registrar la acción importante.
4. **Decider/PDP** — ¿aprobado, o escala?

Si una feature no puede expresarse en estos cuatro pasos, no se asimila tal cual:
se rediseña hasta que pueda. Esto es lo que hace que el resultado sea
"Atlas+Odysseus" y no "Odysseus con un logo nuevo".

### Adoptar tal cual (infraestructura, no lógica)

| De Odysseus | Por qué se adopta directo |
|---|---|
| Docker Compose deployment | Infra reproducible; `docker compose up` sustituye venv+pip. No es lógica de negocio. |
| PWA / responsive shell | Capa de presentación; no toca gobernanza. |
| ntfy (push) | Notificación; se cablea detrás de capability token. |
| SearXNG (metasearch self-hosted) | Fuente; se envuelve como `KnowledgeSource` (ADR-049). |

### Reimplementar con el sello (todas las capacidades)

| Capacidad Odysseus | Reimplementación Atlas | Reutiliza |
|---|---|---|
| Chat multi-turn | UI sobre el loop agéntico existente (ADR-031/032/033) | InferenceHub, CascadeRouter |
| Agent (bash/files/web/shell) | Tools detrás de capability tokens + AST Guard | ADR-013b, SentinelGate |
| Cookbook (270+ modelos, VRAM-aware) | Selector de modelos sobre CascadeRouter + health/circuit-breaker | ADR-042, ADR-016 |
| Deep Research (síntesis multi-fuente) | Misión sobre el organismo de conocimiento | ADR-049, VerifiedProducer |
| Compare (blind test side-by-side) | Banco de evaluación | InferenceHub, ADR-019 |
| Documents (editor multi-tab) | Editor con cada guardado sellado | MerkleLogger |
| Memory / Skills | Ya superior: BlockMemory + skills autodescubribles | ADR-030, ADR-049 slice 4 |
| Email (IMAP/SMTP + triage IA) | Conector tras capability tokens; triage como misión | ADR-049 |
| Notes & Tasks | Sobre BlockMemory + kanban existente | ADR-030, ADR-028 |
| Calendar (CalDAV sync) | Conector tras capability tokens | — |
| Image editor (generate/edit/inpaint) | Tool tras capability tokens (API o local) | AtlasExecutor |
| MCP (built-in + custom) | Ya existe, superior: registry + SentinelGate | ADR-035, ADR-038 |
| 2FA / auth | Endurecer auth operativa existente | ADR-034 |

Resultado proyectado (de los propios cálculos del usuario): promedio ~8.6 frente
a Odysseus 6.0 y Atlas-hoy 6.8 — porque suma las features de Odysseus **sin**
restar la seguridad/auditoría/autonomía de Atlas.

---

## El riesgo que este ADR reconoce de frente

El propio `absorption_master_plan.md` advierte: "absorb patterns, not
uncontrolled dependencies" y "no runtime dependency on Anthropic/Codex/OpenAI".
La asimilación **completa** tensiona esa regla. Se gestiona así:

- **Esfuerzo**: asimilar todo es, por estimación del propio usuario, ~510% de
  esfuerzo para una persona. Este ADR lo hace **programa multi-fase**, no sprint.
  Cada capacidad es su propio slice con su propia puerta de admisión (la regla de
  oro). No se abre un slice nuevo hasta cerrar el anterior con sus 4 pasos.
- **Desincronización con upstream**: no se hace fork vivo. Se asimila por
  reimplementación; Odysseus es referencia, no dependencia. No hay merge que
  mantener.
- **Dilución del sello**: la regla de oro es el guardián. Una feature sin los 4
  pasos no entra. La revisión de cada slice verifica explícitamente Merkle +
  capability + Decider antes de marcar la capacidad como asimilada.
- **YAGNI dentro de "completo"**: "completo" = todas las *capacidades*, no toda
  variante cosmética. Se asimila la capacidad; se descartan los detalles que no
  aportan (p. ej. una skin concreta).

---

## Consecuencias

- Atlas pasaría de "CLI usable solo por su autor" a "producto usable por alguien
  que no es el autor" — la métrica que `idea.md` identifica como el verdadero
  primer caso de éxito.
- Atlas conserva su diferenciador único (la combinación que nadie más tiene) y le
  añade la usabilidad que Odysseus probó que el mercado quiere.
- Coste real: programa largo. Honesto: para una persona es la apuesta más cara
  del proyecto. Se mitiga con fases estrictas y la disciplina de no abrir slice
  nuevo sin cerrar el anterior.

## Plan por fases (orden de dependencia)

- **Fase 0 — Infra**: Docker deploy + PWA shell + auth/2FA endurecida. (Adoptar.)
- **Fase 1 — Núcleo usable**: Chat UI + dashboard sobre el loop agéntico +
  Cookbook básico sobre CascadeRouter. Primera versión "usable por otro".
- **Fase 2 — Productividad I**: Notes & Tasks + Documents (sobre BlockMemory +
  Merkle). Cada guardado/edición sellado.
- **Fase 3 — Conectores**: Email (triage) + Calendar, ambos tras capability
  tokens. Deep Research como misión del organismo de conocimiento.
- **Fase 4 — Avanzado**: Compare (banco eval) + Image editor.
- **Puerta de cada fase**: regla de oro verificada (capability + executor +
  Merkle + Decider) + tests + sin dependencia runtime de APIs cerradas.

> Nota de coherencia con ADR-051: si la Fase 1 expone modelos restringidos, el
> Compliance Gateway (ADR-051) es la capa de admisión por sesión. Los dos ADRs
> componen: 052 da las capacidades; 051 las condiciona cuando el modelo es
> prestado bajo contrato.

> Nota de coherencia con ADR-054 (stack de defensa, bidireccional):
> - **Fase 3 (Deep Research sobre ADR-049) cierra R2 de ADR-054.** El organismo
>   de conocimiento que sintetiza fuentes externas para Deep Research ES el mismo
>   mecanismo que inyecta diversidad de ataque en el sistema inmune. No son dos
>   proyectos; son el mismo ADR-049 con dos consumidores. Completar Fase 3 cierra
>   el riesgo de colapso de diversidad sin trabajo adicional.
> - **Fase 4 (Compare / banco de evaluación) cierra I4 de ADR-054.** El banco de
>   evaluación ciego (lado a lado sobre InferenceHub) es el instrumento que hace
>   falsable la métrica de campaña C_attempts/K_attribution: ejecutar intentos de
>   bypass contra variantes de defensa y medir cuántos necesita cada configuración.
>   Sin Compare, I4 es retórica; con Compare, es medible.
> - **SearXNG (Fase 0) como fuente de técnicas de jailbreak.** El mismo conector
>   KnowledgeSource que alimenta Deep Research puede alimentar el panel adversarial
>   (ADR-048) con técnicas nuevas del exterior sin infraestructura adicional.
