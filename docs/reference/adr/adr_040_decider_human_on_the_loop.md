# ADR-040 — Decisor central y modelo human-ON-the-loop (diseño)

- Status: **Proposed** — diseño, sin implementar. Abre el hito de autonomía tras
  cerrar el ciclo MCP (ADR-035/037/038 + registro dinámico) y sellar el lazo
  Hermes (smoke `/api/exec/intent` verde, 2026-05-31).
- Módulo previsto: `src/atlas/core/decider/` (nuevo)
- Depende de / supersede parcialmente: ADR-032/033 (suspensión por mutación +
  aprobación parcial), Gate C (`ApprovalManager`), ADR-036 P2 (integridad de la
  aprobación: atar el OK al hash de la acción), ADR-025 (rollback de ColdUpdate),
  ADR-035 dec.3 (`remove_server`), ADR-037 (taint del loop).
- Línea de rumbo: ver memoria del proyecto *autonomy-direction* y *no-deepen-
  HITL-coupling*. Este ADR es la materialización de esa dirección.

## Contexto

Hoy "hace falta una decisión" (ejecutar una mutación, adoptar un server, aplicar
un patch) se resuelve **hardcodeando al humano**: el loop transiciona a
`AWAITING_APPROVAL`, se persiste, y espera el botón de Telegram/CLI. Ese
acoplamiento está **disperso** en al menos cuatro call-sites del orquestador:

| Call-site (orchestrator.py) | Disparador actual |
|---|---|
| ~730 | `GateFExecutor.requires_approval` |
| ~891 | clasificador marca riesgo alto (`cls.reason`) |
| ~1073 | `command.requires_approval` o `task.sensitivity == "high"` |
| ~1509 | loop agéntico: un turno pide tool(s) **mutate** → suspende el lote |

Cada sitio tiene su propia variante de `suspend → AWAITING_APPROVAL → humano →
resume`. **Cuanto más se esparce, más cara es la cirugía de quitarlo.** El
objetivo de Atlas es **human-out-of-the-loop**: el sistema deja de requerir
validación humana en *cualquier* punto y pasa a ser autónomo y proactivo.

### Modelo resuelto: human-ON-the-loop

No es human-out a secas: el humano queda **sobre** el loop, no dentro.

- El sistema **nunca se bloquea ni pide permiso**. Ante una decisión, **decide**.
- El humano **observa** (telemetría no bloqueante) y **redirige/revierte de forma
  asíncrona** *después*, no antes. Sigue siendo el origen de la intención de alto
  nivel.
- La palanca del humano se mueve de *antes* (aprobar) a *después* (observar +
  redirigir). Esto sube el peso de tres pilares: **invariantes deterministas**,
  **reversibilidad real** y **telemetría/notificación** como canal "on-the-loop".

## El seam: un decisor único e intercambiable

Todos los puntos de decisión se enrutan por una sola abstracción:

```
decide(action, sanctioned_intent, context) -> Allow | Deny
```

- **`Allow | Deny` sin `Escalate` bloqueante.** Ante incertidumbre el decisor
  **decide por política** (fail-safe según el tier de la acción), nunca hace halt
  esperando al humano.
- El humano es **una implementación más** del decisor (y el destino de la
  telemetría), no el camino fijo. Hoy: "preguntar al humano (Telegram)". Mañana:
  "verificador autónomo de coherencia de intención". El pivote futuro es **añadir
  una implementación + flip de config**, no refactorizar N call-sites.

### Por qué esto NO es premature abstraction

La segunda implementación (verificador autónomo) es un **requisito declarado**, no
hipotético. El seam está justificado por la regla de no profundizar el
acoplamiento HITL: concentrar el "quién decide" en un punto hace barato el pivote.

## Arquitectura

```
            ┌──────────────── sanctioned_intent (alto nivel, del humano)
            ▼
[generador]──action──►[Decider.decide(action, intent, ctx)]──► Allow ─► [Executor]
 (cualquier                       │                              │
  call-site)                      └── Deny ─► no ejecuta + telemetría + (re-plan)
                                  │
                                  ▼  (siempre, no bloqueante)
                            [Telemetría on-the-loop] ──► humano observa/redirige async
                                                          └─► revert: remove_server,
                                                              rollback ColdUpdate, Merkle
```

El decisor se compone de **invariantes deterministas** evaluados en runtime. Es la
promoción de "integridad de la aprobación" (ADR-036 P2: atar el OK al hash de la
acción) a **modelo de autorización central**: en vez de gatekeeping humano,
verificación de coherencia entre la `action` generada y la `sanctioned_intent`.

### Por qué deterministas y NO juicio de LLM

Quitar al humano **sube las apuestas del verificador**. Los invariantes que
gobiernan Allow/Deny deben ser **deterministas / policy-based** (como el
rule-classifier que gana al SLM en violaciones constitucionales), **NO** juicio de
un LLM: el juicio LLM es evadible (>78 % de bypass adaptativo que el propio
proyecto cita). El LLM puede *proponer*; nunca *autorizar*.

## Decisiones de diseño

| # | Decisión | Recomendado | Alternativa / por qué no |
|---|---|---|---|
| **D1** | Forma del veredicto | **`Allow \| Deny`, sin `Escalate` bloqueante.** Ante duda, Deny+revert para lo irreversible; Allow+telemetría para lo reversible | `Escalate` reintroduce el halt humano = exactamente el acoplamiento que quitamos |
| **D2** | Base de la decisión | **Invariantes deterministas** sobre `(action, sanctioned_intent, context)`. Coherencia intención↔acción + tiering de riesgo + IOC | Juicio LLM: evadible. Solo como *proposer*, nunca *decider* |
| **D3** | Rol del humano | **On-the-loop:** telemetría no bloqueante + capacidad de redirigir/revertir async. Origen de la intención de alto nivel | In-the-loop (gate previo): es el estado actual y temporal que este ADR retira |
| **D4** | Reversibilidad | **Pre-requisito de `Allow` autónomo para acciones mutantes:** debe existir un camino de undo (`remove_server`, rollback ColdUpdate, restauración Merkle). Sin undo ⇒ tratar como irreversible ⇒ política más estricta | Permitir mutaciones irreversibles sin gate ni undo: rompe el "redirigir después" |
| **D5** | Migración de call-sites | **Adaptar `ApprovalManager` como UNA implementación del decisor** (`HumanDecider`) y enrutar los 4 call-sites por `Decider.decide`. Cero cambio de comportamiento en fase 1 (el `HumanDecider` reproduce el flujo actual) | Big-bang rip-and-replace: arriesga el HITL que aún protege lo irreversible |
| **D6** | Flip de autonomía | **Config:** `decider = human \| autonomous \| hybrid(tier)`. `hybrid` decide autónomo lo reversible/bajo-riesgo y deja al `HumanDecider` lo irreversible mientras se endurecen invariantes | Un solo salto a `autonomous`: sin red de seguridad durante el endurecimiento |
| **D7** | Canal on-the-loop | **Telemetría no bloqueante** (Telegram notify + Merkle) en cada `decide`, con `action_hash` para correlación y revert dirigido | Sin telemetría: el humano pierde el "on-the-loop" y la redirección async es ciega |

## Plan de slices (implementación futura)

1. **Seam `Decider` + `HumanDecider`.** Definir `decide(...) -> Verdict` y envolver
   el `ApprovalManager` actual como `HumanDecider` (comportamiento idéntico). Sin
   cambiar call-sites todavía. Tests = paridad con el flujo HITL de hoy.
2. **Enrutar los 4 call-sites** del orquestador por `Decider.decide` en vez de
   `transition(AWAITING_APPROVAL)` directo. Sigue siendo `HumanDecider` ⇒ verde sin
   cambio observable. Esto es la des-dispersión: un solo seam.
3. **`action_hash` + coherencia intención↔acción.** Atar cada veredicto al hash de
   la acción (ADR-036 P2) y registrar telemetría no bloqueante con ese hash.
4. **`AutonomousDecider` (invariantes deterministas).** Tiering + IOC + coherencia,
   fail-safe por política. Sin LLM en el path de autorización. Tests adversariales.
5. **`hybrid(tier)` + flip de config.** Autónomo lo reversible; `HumanDecider` lo
   irreversible. Endurecer invariantes con métricas reales antes de ampliar el tier.
6. **Reversibilidad como invariante.** Verificar que toda mutación auto-`Allow`
   tiene undo registrado; si no, downgrade de política. Cablear revert async.

## Riesgos honestos y no-objetivos

- **No-objetivo: "seguridad total".** La evidencia (>78–85 % bypass adaptativo) lo
  prohíbe. El objetivo es subir el coste del ataque + mantener undo barato.
- **Riesgo: el verificador autónomo se equivoca y no hay halt.** Mitigación: D4
  (reversibilidad obligatoria) + D6 (`hybrid` deja lo irreversible al humano hasta
  que los invariantes estén endurecidos con datos).
- **Riesgo: invariantes con juicio LLM colado.** Prohibido por D2 — el LLM propone,
  no autoriza. Auditar que ningún path de `AutonomousDecider` invoque inferencia.
- **No-objetivo en v1: quitar al `HumanDecider`.** Permanece como implementación y
  como destino de lo irreversible; la transición es por config, no por borrado.

## Estado y siguiente paso

Diseño abierto. El núcleo del modelo está **resuelto** (human-on-the-loop, veredicto
`Allow|Deny` sin `Escalate`, invariantes deterministas, reversibilidad + telemetría
como pilares). Lo táctico —qué invariantes concretos, granularidad del `tier`,
forma exacta de la redirección async— se fija al implementar. El **slice 1** (seam
`Decider` + `HumanDecider` con paridad de comportamiento) es pequeño y de riesgo
cero: no cambia conducta, solo introduce el punto único por donde, más tarde, entra
la autonomía con un flip de config.
