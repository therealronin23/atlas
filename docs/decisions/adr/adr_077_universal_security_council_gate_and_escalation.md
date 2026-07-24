# ADR-077 — Cónclave de seguridad universal: rechazo permanente + escalada con informe (Propuesto)

- Estado: **Propuesto** — diseño completo, sin código todavía. Recomienda una
  revisión de Cónclave ligera antes de implementar (ver "Antes de construir"),
  no por debilitar un invariante (no toca ninguno) sino porque envuelve el
  seam del Decider para TODOS los `kind`, superficie amplia.
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

## Antes de construir

Aunque este diseño no relaja ningún invariante, sí envuelve el seam del
Decider para múltiples `kind` a la vez -- superficie amplia. Recomendado:
una revisión de Cónclave (no necesariamente con el gating de `irreversible=True`
de ADR-076 C, dado que esto es aditivo/más estricto, no una relajación) antes
de escribir el primer commit, para que quede en acta que el diseño se validó
antes de tocar el seam que gobierna adopción/parcheo/acciones ofensivas.

## Ficheros críticos (si se aprueba)

- `src/atlas/core/decider/decider.py` — nuevo `CouncilVerdict`/`SecurityReport`
- Nuevo `src/atlas/core/decider/security_council_gate.py`
- `src/atlas/core/orchestrator.py` — envolver `_consult_decider` para kinds
  gateados
- `workspace/security_council/rejected.jsonl` — registro de rechazo permanente
  (runtime, gitignored, mismo patrón que `workspace/mcp/*.jsonl`)
- Reusar: `atlas.mcp.candidate_static_scan` (semgrep), CLI `security-audit`
  (CWE), IOC/credential checks ya en `autonomous_decider.py`,
  `Task.AWAITING_APPROVAL`/`EventType.APPROVAL_REQUIRED`/
  `_persist_pending_approval` (ya existen, hoy inertes)

## Verificación end-to-end (si se aprueba)

1. TDD por pieza: `SecurityReport`/`CouncilVerdict` → gate genérico → registro
   de rechazo permanente → wiring en `_consult_decider`.
2. Caso real: reproducir `ai.adeu/adeu` (ya tiene hallazgo MAJOR real de
   ADR-075) contra el gate nuevo -- confirmar `flagged`, informe generado,
   escalada disparada UNA vez, y que un segundo intento con el mismo
   `action_hash` no vuelve a correr el escaneo ni a re-escalar.
3. Confirmar que bajo `ATLAS_DECIDER=autonomous` la escalada SÍ llega a
   `Task.AWAITING_APPROVAL` (hoy no llega nunca) -- este es el criterio de
   éxito central del ADR.
