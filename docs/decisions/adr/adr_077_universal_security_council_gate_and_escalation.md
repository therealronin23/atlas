# ADR-077 — Cónclave de seguridad universal: rechazo permanente + escalada con informe (Aceptado)

- Estado: **Aceptado** (2026-07-24) — diseño revisado por un Cónclave real
  (4 objeciones concretas incorporadas, ver "Revisión de Cónclave" abajo) e
  **implementado con TDD estricto en 4 piezas**, todas commiteadas en
  `main`: `security_council_gate.py` (escaneo+auditor, fail-closed),
  `security_council_escalation.py` (segunda opinión del trío real),
  `security_council_registry.py` + `Orchestrator.security_council_unblock`
  (rechazo permanente + revocación HITL), wiring real en
  `Orchestrator._consult_decider` (opt-in `ATLAS_SECURITY_COUNCIL_GATE=1`,
  apagado por defecto). 41 tests nuevos, mypy limpio, sin regresiones
  (verificado contra 345 tests de los call-sites del decider).
- Origen: petición explícita del operador (2026-07-24) tras la auditoría de
  ADR-076/ADR-036 que encontró que `RequiresHuman` es hoy inalcanzable en
  producción y que hay reintentos en bucle contra candidatos ya rechazados.
- Extiende: ADR-040 (Decider human-on-the-loop), ADR-075 (vetting continuo MCP,
  cuyo patrón `completed/terminal/retryable` se generaliza aquí), ADR-076
  (encontró el problema que este ADR intenta resolver).
- NO enmienda: la regla constitucional #4 (`sensitivity="high"` → deny/require
  siempre) queda intacta y sin tocar en todos los casos.

## Contexto — qué encontró la auditoría de hoy (verificado, no teórico)

1. **`ATLAS_DECIDER=autonomous` está activo en producción** (confirmado contra
   `/proc/<pid>/environ` del proceso `atlas-core.service` real, no solo el
   `.env` en disco) desde al menos el 2026-07-15.
2. **`AutonomousDecider` nunca devuelve `RequiresHuman`** — solo `Allow` o
   `Deny` (`src/atlas/core/decider/autonomous_decider.py`). Verificado contra
   el log Merkle real (`/home/ronin/atlas/memory/audit/merkle.jsonl`, 8550
   entradas): `task.routed` (la vía que encola algo para revisión humana)
   tiene **2 entradas, ambas de mayo de 2026**. `decider.verdict` (el seam
   autónomo) tiene **603 entradas**, la última de hoy mismo, 534 `allow` / 69
   `deny`. La maquinaria de aprobación humana (`Task.AWAITING_APPROVAL`,
   `EventType.APPROVAL_REQUIRED`, `_persist_pending_approval`) existe, está
   probada, y lleva meses sin ejecutarse ni una vez.
3. **Reintentos en bucle contra un candidato ya conocido como peligroso**:
   `mcp_adopt` para `ai.adeu/adeu` (uno de los 4 candidatos con hallazgo MAJOR
   de semgrep de ADR-075) se deniega correctamente cada vez por la regla
   constitucional #4 — pero se reintenta una y otra vez (6 veces solo hoy) sin
   que nada recuerde "esto ya se evaluó y se rechazó, no lo vuelvas a
   proponer".
4. **`ATLAS_MCP_AUTO_ADOPT` (ADR-076 C) fue bloqueado por un Cónclave real**
   precisamente porque bajar `sensitivity="high"` sin más elimina la única
   barrera ante riesgo semántico no detectable por escaneo estático. Ese
   veredicto sigue vigente y este ADR **no lo revisita** — propone algo
   distinto: no bajar la barra de qué se aprueba, sino arreglar qué pasa
   cuando algo se **rechaza**.

## Investigación — cómo resuelve esto la industria real

- **Automatización de triaje SOC (L1→L2)**: un SOC típico recibe ~11.000
  alertas/día y solo ~22 por analista merecen investigación real. El patrón
  ganador no es "menos alertas" sino **enriquecer + resumir antes de que un
  humano lo vea** — el analista revisa escaladas ya validadas con un resumen
  de investigación adjunto, no la lista cruda.
- **Formato de resumen estructurado que sí se usa en producción** (LanG,
  plataforma de SOC agéntico 2026): severidad, *triage score*, indicadores de
  compromiso principales, fase de la cadena de ataque, y **acción
  recomendada** (escalar / investigar / contener / archivar) — machine-
  parseable, no prosa libre.
- **LLM como auditor ANTES de escalar a humano** es un patrón ya documentado
  (Agent Audit, arXiv:2603.22853; triaje autónomo de alertas con LLM +
  razonamiento aumentado por herramientas) — el LLM no decide solo, produce
  un veredicto estructurado que alimenta la decisión y el informe.
- Ninguna fuente real propone "denylist permanente" como término formal, pero
  el principio (idempotencia + no repetir un trabajo ya resuelto) es estándar
  en sistemas distribuidos — y **Atlas ya lo implementó hoy mismo** para el
  vetting de MCP (`classify_stage2_status`, ADR-076 B.2: `completed`/
  `terminal` nunca se reprocesan). Este ADR generaliza ese mismo patrón.

## Diseño propuesto

### 1. Security Council Gate — nueva etapa, delante del Decider existente

Para cualquier `DecisionAction` cuyo `kind` se registre como
"security-gateable" (lista explícita, opt-in por kind — no todos: `mcp_adopt`,
`cold_update_apply`, `offensive_action`, `omega_exec` para empezar), antes de
llegar al Decider actual:

```python
def security_council_gate(action: DecisionAction, artifact: Any) -> CouncilVerdict:
    """Escaneo automatizado + auditor LLM único (hub plano, barato) --
    NO es el Cónclave de 3 proveedores (ese sigue reservado para decisiones
    ADR/irreversibles vía should_convene). Verdict: clean | flagged."""
```

- **Escaneo automatizado** ("antivirus"): reusa lo que YA existe por dominio
  -- semgrep (`candidate_static_scan.py`) para MCP stdio, el escáner CWE
  (`security-audit` CLI) para parches de código, los chequeos IOC/credencial
  que YA vive dentro de `autonomous_decider.py` para acciones ofensivas/OMEGA.
  No se reimplementa nada, se reusa vía el mismo principio de "adopt real, no
  cascarón" de esta casa.
- **Auditor LLM único**: una llamada hostil en hub plano (mismo patrón que
  `LlmReviewer` de `deliberation_council.py`, pero UNA voz, no trío) sobre el
  descriptor/diff/contexto real de la acción concreta.

### 2. Verdict `clean` → sigue el camino de hoy, sin cambios

Pasa al Decider existente (Human o Autonomous) exactamente como ahora. La
regla constitucional #4 sigue aplicando igual. Este ADR no toca ese camino.

### 3. Verdict `flagged` → informe + rechazo permanente + escalada real

```python
@dataclass(frozen=True)
class CouncilVerdict:
    status: Literal["clean", "flagged"]
    report: SecurityReport | None = None  # severidad, checks, IOCs, acción recomendada

@dataclass(frozen=True)
class SecurityReport:
    severity: str          # NONE|MINOR|MAJOR|BLOCKING (reusa Severity existente)
    checks_run: list[str]  # qué escaneos/auditor corrieron
    triggered_by: str      # qué disparó el flag, concreto
    recommended_action: str  # "denegar permanentemente" | "revisar manual" | ...
```

Si `flagged`:

1. **Rechazo permanente**: escribe en un registro nuevo, keyed por
   `action_hash` (ya existe -- `_consult_decider` lo calcula desde ADR-040
   slice 3) -- mismo patrón de `workspace/mcp/rejected_candidates.jsonl` que
   `classify_stage2_status` ya usa para `terminal` en MCP, generalizado a
   `workspace/security_council/rejected.jsonl`. Un intento futuro con el
   MISMO `action_hash` se deniega instantáneo, sin re-correr el gate ni
   re-escalar -- cierra el reintento en bucle de `ai.adeu/adeu`.
2. **Informe adjunto**: el `SecurityReport` completo se persiste junto al
   rechazo -- no un `reason` de una línea, el resumen estructurado completo
   (formato LanG: severidad/checks/disparador/acción recomendada).
3. **Escalada REAL, independiente de `ATLAS_DECIDER`**: dispara
   `Task.AWAITING_APPROVAL` + `EventType.APPROVAL_REQUIRED` +
   `_persist_pending_approval` -- la maquinaria que YA EXISTE y lleva desde
   mayo sin ejecutarse. Esto NO depende de si el Decider activo es Human o
   Autonomous -- el gate de seguridad es una capa ANTERIOR y ortogonal, así
   que por fin esa vía se ejercita de verdad, en ambos modos.

### 4. Generalización explícita — no es una feature de MCP

El gate se registra por `kind`, no está hardcodeado a `mcp_adopt`. Un nuevo
`DecisionAction(kind="lo-que-sea", ...)` solo necesita añadirse a la lista de
kinds gateados para heredar todo esto -- automatización de escaneo +
auditor LLM + rechazo permanente + informe + escalada real, sin duplicar
código por dominio.

## Qué NO cambia (para que quede explícito)

- La regla constitucional #4 sigue igual: `sensitivity="high"` sigue forzando
  Deny/RequiresHuman siempre, en ambos deciders, sin excepción.
- `ATLAS_MCP_AUTO_ADOPT` (ADR-076 C) sigue sin construirse. Este ADR no
  reabre esa pregunta ni la contradice -- pasar el Security Council Gate NO
  basta por sí solo para adoptar nada; solo evita el ruido de reintentos y
  arregla la vía de escalada. La decisión de auto-adoptar sigue bloqueada.
- El Cónclave de 3 proveedores (`deliberation_council`) sigue reservado para
  decisiones ADR/irreversibles. El auditor LLM de este gate es deliberadamente
  MÁS barato y de una sola voz -- es triaje rutinario por acción, no
  deliberación de gobernanza.

## Revisión de Cónclave (2026-07-24) — incorporada, no bloqueó

Convocado (`scripts/council_adr077_design_review.py`, red real) pidiendo
mejora de diseño, no veredicto binario. **2 voces reales** (`gemini_free`
BLOCKING, `nvidia_mistral_large` MAJOR con 5 puntos concretos) más
`nvidia_glm` que falló la llamada y quedó registrado fail-closed (no es una
tercera objeción sustantiva -- honestidad de diversidad, mismo criterio que
ADR-075). El operador ya había decidido construir esto ("revisión para
mejorar, luego implementamos") -- las 4 objeciones accionables se incorporan
al diseño de abajo, no bloquean la implementación:

1. **Un solo LLM auditor no tiene diversidad cognitiva** (Mistral): puede
   pasar por alto ataques *out-of-distribution* que semgrep no cubre (ej.
   manipulación de `sys.path`). **Incorporado**: el auditor único es solo el
   PRIMER paso (barato, cubre el volumen). Si devuelve `flagged` O
   `uncertain`, escala automáticamente al trío real de `deliberation_council`
   (ya construido, ya gateado por `should_convene`) antes de que el rechazo
   se vuelva permanente -- segunda opinión real solo donde importa, sin pagar
   el coste del trío en cada acción.
2. **Fail-open no especificado = BLOCKING** (ambas voces): el diseño original
   no decía qué pasa si el escaneo o el LLM fallan. **Incorporado**: fail-closed
   explícito y testeado -- cualquier timeout/excepción/proveedor caído en
   CUALQUIER etapa produce `flagged`, nunca `clean` (mismo principio I6 de
   ADR-075: "lo no-analizable se rechaza").
3. **`action_hash` puede bloquear actualizaciones legítimas + sin revocación**
   (Mistral): verificado contra `decider.py:68-83` -- el hash incluye
   `descriptor` (texto libre del caller), que en la práctica YA suele portar
   versión (confirmado contra el log real: `"click 8.4.1 8.4.2..."`), pero no
   está garantizado por el tipo. **Incorporado**: (a) el registro de un `kind`
   en el gate exige que su `descriptor` porte entropía suficiente para
   distinguir intentos legítimamente distintos -- test que lo verifica, no
   solo convención; (b) nuevo comando `atlas security-council unblock <hash>`
   (HITL explícito, logueado en Merkle) para revocar un rechazo permanente
   que resulte falso positivo -- el diseño original no tenía ninguna vía de
   apelación.
4. **Tratar todos los `kind` por igual subestima el riesgo** (Mistral):
   `offensive_action` puede tener consecuencias externas irreversibles;
   `omega_exec` ya tiene snapshot+undo. **Incorporado**: `offensive_action`
   con veredicto `flagged` escala SIEMPRE al trío real (nunca se conforma con
   el auditor único, sea cual sea su verdict); `omega_exec`/`cold_update_apply`/
   `mcp_adopt` siguen el flujo de dos niveles estándar (único → trío solo si
   flagged/uncertain).
5. **Informes que nadie revisa, repite el problema de `pending_review.jsonl`**
   (Mistral): **Incorporado**: reusa `TelegramBot.notify_all()`
   (`src/atlas/interfaces/telegram_bot.py:398`, ya cableado y en producción)
   para empujar el `SecurityReport` en tiempo real cuando `severity` es
   `MAJOR`/`BLOCKING` -- no otro JSONL más al que nadie vuelve.

## Diseño final (tras la revisión)

Los mismos 4 componentes del diseño original (gate delante del Decider,
verdict clean/flagged, rechazo permanente + informe + escalada, generalizado
por `kind`), con las 5 correcciones de arriba incorporadas: auditor de dos
niveles (único → trío real si flagged/uncertain, o siempre-trío para
`offensive_action`), fail-closed explícito y testeado, entropía de
`descriptor` exigida + comando de revocación HITL, y notificación real vía
Telegram en vez de un JSONL pasivo.

## Antes de construir

Diseño revisado por Cónclave real (arriba) -- las objeciones concretas están
incorporadas. No se convoca una segunda ronda: el operador ya decidió
proceder a implementación tras esta revisión.

## Ficheros críticos

- `src/atlas/core/decider/decider.py` — nuevo `CouncilVerdict`/`SecurityReport`
- Nuevo `src/atlas/core/decider/security_council_gate.py` — gate de dos
  niveles (auditor único → trío real si `flagged`/`uncertain`/fallo),
  fail-closed explícito
- `src/atlas/core/orchestrator.py` — envolver `_consult_decider` para kinds
  gateados; nuevo método `security_council_unblock(action_hash)` (HITL,
  Merkle-logueado)
- `src/atlas/interfaces/cli.py` — nuevo subcomando
  `security-council unblock <hash>`
- `workspace/security_council/rejected.jsonl` — registro de rechazo permanente
  (runtime, gitignored, mismo patrón que `workspace/mcp/*.jsonl`)
- Reusar: `atlas.mcp.candidate_static_scan` (semgrep), CLI `security-audit`
  (CWE), IOC/credential checks ya en `autonomous_decider.py`,
  `deliberation_council.build_trio_reviewers`/`convene_for_decision` (segunda
  opinión real), `TelegramBot.notify_all` (escalada real, no JSONL pasivo),
  `Task.AWAITING_APPROVAL`/`EventType.APPROVAL_REQUIRED`/
  `_persist_pending_approval` (ya existen, hoy inertes)

## Verificación end-to-end

1. TDD por pieza: `SecurityReport`/`CouncilVerdict` → auditor único → escalada
   a trío real (flagged/uncertain) → registro de rechazo permanente + entropía
   de `descriptor` → comando `unblock` → wiring en `_consult_decider`.
2. Fail-closed explícito: test que fuerza timeout/excepción en el escaneo Y
   en el auditor único, cada uno por separado -- ambos deben producir
   `flagged`, nunca `clean` por defecto.
3. Caso real: reproducir `ai.adeu/adeu` (ya tiene hallazgo MAJOR real de
   ADR-075) contra el gate nuevo -- confirmar `flagged`, informe generado,
   notificación Telegram disparada, escalada disparada UNA vez, y que un
   segundo intento con el mismo `action_hash` no vuelve a correr el escaneo
   ni a re-escalar.
4. `offensive_action` con `flagged` del auditor único: confirmar que escala
   SIEMPRE al trío real, nunca se resuelve solo con la primera pasada.
5. Confirmar que bajo `ATLAS_DECIDER=autonomous` el veredicto `RequiresHuman`
   SÍ se produce y llega a cada call-site (hoy no llega nunca) -- este es el
   criterio de éxito central del ADR.
6. `security-council unblock <hash>`: confirmar que revoca el rechazo
   permanente, queda logueado en Merkle, y un intento posterior con ese hash
   vuelve a correr el gate normalmente (no queda "desbloqueado para
   siempre" sin pasar por el gate otra vez).

## Implementación real (2026-07-24) -- 2 precisiones honestas sobre el diseño

Las 4 piezas se implementaron con TDD estricto (`security_council_gate.py`,
`security_council_escalation.py`, `security_council_registry.py` +
`Orchestrator.security_council_unblock`, wiring en `_consult_decider`). Dos
detalles que la implementación forzó a precisar respecto al diseño original:

1. **`Task.AWAITING_APPROVAL` NO se dispara para los 4 kinds gateados.**
   Verificado leyendo el código real: esa maquinaria es específica del
   pipeline `gate_f`/`handle_intent` (task-oriented). `mcp_adopt`,
   `cold_update_apply`, `offensive_action`, `omega_exec` se llaman desde
   métodos que solo devuelven un string ante `RequiresHuman` (ej.
   `adopt_mcp_server`: `"requiere aprobación humana para adoptar el
   server"`) -- ningún `Task` se encola. `gate_f` queda FUERA del gate a
   propósito (su HITL ya pasa por esa máquina). Lo que sí se logró y es el
   fix real: `RequiresHuman` ahora se PRODUCE para estos 4 kinds bajo
   cualquier decisor (antes, bajo autónomo, nunca se producía) -- la
   visibilidad humana llega vía el informe en Merkle
   (`security_council.flagged`) + notificación Telegram en tiempo real, no
   vía cola de `Task`. Convertir estos 4 call-sites a task-oriented con cola
   de aprobación visible en UI es una ampliación futura, fuera de este ADR.
2. **El gate es opt-in (`ATLAS_SECURITY_COUNCIL_GATE=1`, apagado por
   defecto)** -- no estaba en el diseño revisado por el Cónclave, se añadió
   durante la implementación al encontrar una regresión real: los 4 kinds
   gateados ya tenían tests existentes que no esperaban un pre-gate, y en
   entorno sin claves LLM el auditor fallaba cerrado y cambiaba veredictos
   Allow/Deny existentes a RequiresHuman. Mismo criterio que toda capacidad
   nueva de esta sesión (`ATLAS_MCP_RESEED`/`ATLAS_MCP_VETTING`): nada
   cambia de comportamiento hasta que el operador lo enciende explícito.
