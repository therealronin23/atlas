# ADR-068 — F5/F6 reencuadradas como núcleo de autoconstrucción, no verticales de negocio

- Estado: aceptado (2026-07-11)
- Contexto: ADR-066 parkeó Fase 5 (Visual Orchestrator Territory) y Fase 6
  (Coding+Research Territories) sin fecha de reapertura. El operador (con
  segunda opinión de otra IA, Codex) plantea que para un Atlas que se
  autoconstruye, F6 no es un "nice to have" de producto — es la superficie
  que le falta a Atlas para depender menos de herramientas externas
  (Claude Code, Fable) para programarse a sí mismo. Y que F5, reinterpretada
  (no como clon de n8n), sería la superficie para ver/controlar/auditar los
  workflows dinámicos que Atlas ya ejecuta hoy sin superficie visible.

## Decisión

1. **Se corrige el ENCUADRE, no el parking.** F5/F6 siguen sin
   implementarse hoy — ADR-066 sigue vigente en cuanto a "no construir
   ahora". Lo que cambia es cómo se las nombra y prioriza cuando SÍ se
   retomen:
   - Vieja F5 ("Visual Orchestrator Territory", canvas genérico tipo n8n)
     → reencuadrada como **Dynamic Workflow Control Surface**: una vista
     de auditoría/control sobre workflows que Atlas YA ejecuta (fase
     actual, subagente, herramientas usadas, ficheros tocados, tests,
     gates, riesgo, coste, reintentos, rollback) — no un editor visual de
     flujos nuevos.
   - Vieja F6 ("Coding+Research Territories", Monaco+árbol de
     investigación genérico) → reencuadrada como **Coding + Research
     Workbench para autoconstrucción**: repo reader, diff viewer, test/
     mypy/build runner, commit planner, rollback plan, panel de delegación
     de agentes, ledger de autobuild, log de decisiones de Cónclave.
   - Ambas están al servicio de que **Atlas se construya a sí mismo**, no
     de un producto vertical de negocio.
2. **Esto NO reordena el trabajo de verticales de negocio por delante de
   nada** — los verticales (restaurante, gestoría, legal, sanidad, CRM/ERP
   completos) siguen exactamente donde estaban: después, sin fecha.
3. **Esto NO autoriza empezar a implementar ninguna de las dos superficies
   hoy.** Reencuadrar la intención no es lo mismo que scopear la
   implementación. Antes de escribir código de UI para cualquiera de las
   dos, hace falta un spec de alcance real (qué pantallas, qué estados,
   qué endpoints) — trabajo que se pospone explícitamente por escasez de
   tiempo real de esta sesión, no por falta de prioridad futura.

## Consecuencias

- `docs/continuation/KNOWN_RISKS.md` y `CONTINUATION_STATE.md` deben
  reflejar este reencuadre para que la próxima sesión (con o sin más
  contexto) entienda por qué F5/F6 no son "trabajo de producto opcional"
  sino candidatas a núcleo de autoconstrucción, aunque sigan sin
  implementarse.
- Si se retoma F5/F6, el nombre correcto para el trabajo es `DYNAMIC_
  WORKFLOW_CONTROL_SURFACE` y `CODING_RESEARCH_WORKBENCH`, no "Visual
  Orchestrator"/"Coding Territory" — para que quede claro desde el nombre
  que no son clones genéricos de herramientas externas.
- Este ADR no supersede a ADR-066 (el parking en sí sigue vigente); lo
  complementa explicando CÓMO debe entenderse el trabajo el día que se
  reabra.

## Actualización — primera porción real enviada (misma sesión, 2026-07-11)

Tras esta decisión, el operador pidió explícitamente construir: se envió
una primera porción REAL y acotada de `Dynamic Workflow Control Surface`,
no la superficie completa:

- `GET /self-build/summary` (nuevo, `src/atlas/api/server.py`) — lectura
  READ-ONLY de `atlas-cold-updates/proposals.json` (el ledger real de
  `ColdUpdateManager`, ADR-025). Nunca instancia `ColdUpdateManager` (su
  `__init__` barre worktrees, efecto lateral de escritura) — mismo patrón
  que `_memory_summary()`.
- `AutobuildLedger.tsx` (nuevo, `ui/atlas-shell`) — vista real que muestra
  229 propuestas reales del lazo de autoconstrucción: 184 rechazadas, 15
  fallidas, 12 aplicadas, 12 propuestas, 6 validadas; 227 de `self_audit`,
  2 de `swarm`. Verificado en navegador real contra el bridge real (no
  build only): datos reales, cero requests fallidos.
- Esto NO es la superficie completa descrita en el reencuadre de arriba
  (faltan: control de fase/subagente en vivo, ficheros tocados, tests
  ejecutados, botón de rollback). Es un primer corte vertical real,
  suficiente para responder "¿qué ha propuesto Atlas construirse a sí
  mismo?" con datos, no con fe.

## Actualización 2 — detalle de propuesta: ficheros, tests, siguiente paso (misma sesión, 2026-07-11)

Segundo corte, sobre el mismo endpoint/ledger, cerrando 2 de los 4 huecos
listados arriba:

- `GET /self-build/proposal/{id}` (nuevo) — detalle de una propuesta:
  parsea el `.patch` real en disco (`--- a/` / `+++ b/`) para listar
  **ficheros tocados**; expone `validation` real (pytest/mypy, pass/fail,
  duración) cuando existe; calcula `next_action` — el comando CLI real
  (`atlas update validate|approve|apply <id>`) que un humano correría a
  continuación, **nunca ejecutado desde el bridge** (ADR-058 es read-only;
  ColdUpdateManager no se instancia aquí tampoco).
- `AutobuildLedger.tsx` — cada propuesta de la lista es ahora clicable y
  abre un panel de detalle con lo anterior. Verificado en navegador real
  contra bridge real: ficheros tocados correctos
  (`src/atlas/core/orchestrator_parts/maintenance_facade.py` para una
  propuesta real), validación real de un `applied` (982 tests, mypy
  limpio), `next_action` correcto por estado.
- **Sigue sin existir "botón de rollback" ni "fase/subagente en vivo"** —
  el primero se descartó deliberadamente (ejecutar mutaciones desde el
  bridge read-only rompería ADR-058 y necesitaría PolicyEngine/Gate Engine
  de por medio, no existe ese camino todavía); el segundo no tiene fuente
  de datos real (el ledger es un registro de propuestas ya creadas, no un
  stream de fases en curso).
- **Hallazgo real al verificar en vivo**: el mismo intent ("Cablear el
  vault Obsidian al tick del grafo — graph_note_neighborhood sirve vacío")
  aparece repetido en la lista de "últimas 50" con timestamps de hoy
  (11/7): 11:56, 18:29, 20:00, 21:18, 22:21 — aproximadamente cada 1-2
  horas, siempre en estado `proposed`, siempre tocando el mismo fichero
  (`maintenance_facade.py`), nunca avanza a `validated`. El lazo de
  autoconstrucción está reintentando la misma propuesta sin converger.
  Esto ya no es solo "un dato curioso" (como se anotó en la actualización
  anterior) — es un patrón activo y visible AHORA MISMO en el ledger real,
  candidato real a investigación (¿por qué no se valida nunca? ¿el
  validador falla en silencio? ¿el intent se recrea porque el problema de
  origen sigue sin resolverse?). No investigado en esta sesión por
  alcance — queda nombrado explícitamente para la próxima.
