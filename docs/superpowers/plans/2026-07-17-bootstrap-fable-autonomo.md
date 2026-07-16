# BOOTSTRAP — sesión autónoma de construcción (escrito por Fable 5, 2026-07-16 noche)

**Para el driver que lea esto** (Fable, Sonnet, Opus, Codex — da igual): el operador
te ha lanzado con este fichero como misión. Todo lo que necesitas está en el repo;
NO re-derives contexto, NO releas el ledger entero, NO preguntes al operador nada
que no sea N3 (ver escalera). Modo: autónomo, perfeccionista-con-evidencia,
continuo (sin "¿sigo?").

## Orden de lectura (y NADA más)

1. `AGENTS.md` (leyes de operación — ya lo carga el hook de sesión).
2. Este fichero entero.
3. `docs/design/atlas_master_plan.md` §2 (anti-dispersión) y §3 (escalera N0-N3).
4. `docs/design/fable5_build_doctrine.md` §2bis (los fallos del driver anterior —
   los traes de fábrica; §3 son las trampas de malinterpretación activas).
5. El plan de la tarea en curso (abajo). El resto de los 666 docs: SOLO si una
   tarea te manda a uno concreto.

## Misión de la sesión, en orden estricto

1. **Ejecutar `docs/superpowers/plans/2026-07-16-t0-succession-core.md`** (3
   tareas TDD: migración memoria-harness→sustrato, `atlas handoff`, primera
   ejecución real). Modo: implementadores Sonnet frescos por tarea
   (subagent-driven), tú auditas el diff y commiteas. Revisión por tarea:
   a tu juicio según tamaño del diff — la revisión final de rama al acabar
   la ola es OBLIGATORIA (un revisor, brief cerrado, hallazgos con
   fichero:línea).
2. **T5.1 smoke diario de proveedores**: recon de
   `src/atlas/core/inference_hub.py:402` (30 min máx) → escribe mini-plan
   (mismo formato del plan T0) → ejecútalo. Objetivo: el daemon detecta un
   proveedor muerto antes que un humano; presupuesto fail-closed NO (eso es
   T5.3), solo detección.
3. **`atlas handoff` real + commit de los generados** (Task 3 del plan T0 lo
   cubre — verifica que quedó hecho, no lo dupliques).
4. **F2.6 test de sucesión** SOLO si el presupuesto de la sesión va sano
   (<50% consumido al llegar aquí): sesión real `claude -p --model sonnet`
   con la rúbrica de 6 ítems (está en el plan toasty, sección F2.6, en
   `/home/ronin/.claude/plans/toasty-hatching-pillow.md`). Si no hay
   presupuesto: deja el prompt del test escrito en
   `docs/superpowers/plans/` y márcalo pendiente.
5. **Cierre**: WORK_LEDGER (1 entrada), memoria de sesión actualizada
   (`~/.claude/.../memory/toasty-campaign-status-2026-07-16.md` → añade el
   resultado de esta ola), y propuesta de siguiente ola (T2.1 consola mínima
   + T0.5b digestión) en 10 líneas al operador. NADA más.

## Reglas duras (violarlas = parar y anotar)

- **Economía**: implementación en Sonnet, mecánico en Haiku, tú solo criterio.
  Cláusula de cruce: 2 fallos consecutivos de un delegado → cambia de táctica
  (otro modelo, otro corte, o hazlo tú si es pequeño). Si hay incidencia en
  status.claude.com, NO insistas con agentes: espera con timer.
- **Evidencia**: nada se declara hecho sin salida de comando pegada. Los tests
  se corren DIRIGIDOS (`ATLAS_NESTED_TEST_RUN=1 PYTHONPATH=src
  .venv/bin/python -m pytest <fichero> -q`), jamás la suite completa.
- **Git**: `git diff --cached --stat` ANTES de cada commit (hay historial de
  arrastrar staged ajeno). Un commit por tarea. JAMÁS push. JAMÁS commitear
  "Diseño UI Atlas.md".
- **Decisiones**: N0/N1 las tomas y las registras (1 línea en
  `.superpowers/sdd/progress.md`); N2 → Cónclave o, si no está disponible,
  decide TÚ con recomendación escrita y márcala revisable; N3 (dinero,
  credenciales, privacidad, docs raíz, prioridad entre tramos) → PARA y
  pregunta al operador. Al operador JAMÁS le preguntes el CÓMO técnico.
- **Dispersión**: >3 decisiones N2 imprevistas en una tarea → STOP, anota el
  hallazgo en el progress ledger, re-corta la tarea. No "sigas tirando".
- **BD de producción** (`~/atlas/memory/kuzu/`, `~/atlas-mcp/memory.db`): los
  tests JAMÁS las tocan; la migración real (Task 3) usa `--apply` solo tras
  dry-run revisado por ti.
- **Perfeccionista ≠ dorado**: perfección es evidencia y honestidad en el
  alcance del plan, no features extra. YAGNI. Si ves algo fuera de alcance
  que merece arreglo, chip/spawn_task o nota en el ledger — no lo hagas.

## Formato del informe final al operador

Commits (hash + título) · evidencia clave (3-5 líneas de salidas reales) ·
qué quedó pendiente y POR QUÉ · decisiones N1/N2 tomadas (lista de 1 línea
c/u) · consumo aproximado. Sin celebraciones: estado, no ánimo.

## Contexto mínimo que no está en los docs

- El daemon quedó ACTIVE (2026-07-16 15:50, unit con hardening reinstalado).
- La campaña toasty (F1-F5) está SELLADA — no la reabras.
- Hay 12 fuentes graphify largas sin resolver (decisión del operador
  pendiente: Groq/ignorar/aceptar 98.3%) — NO es tu misión salvo que el
  operador lo pida.
- Los scripts monitor/capture/autoremediation de graphify están RETIRADOS
  (stubs exit 64) — no los "arregles".
- El operador NO programa: sus mensajes describen intención, no specs; los
  ejemplos que dé son ejemplos (ley §2.1 del plan maestro).
