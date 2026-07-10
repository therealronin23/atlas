# Audit Postmortem 2026-06-13

Auditoría fría con evidencia propia (no narración heredada), tras las capas 1–2
y su cableado. Qué es verdad, qué no sabía, qué corrijo.

## Hechos verificados (comandos locales)

- `pytest tests/ -q` → **1044 passed, 26 deselected**.
- `mypy src/atlas/` → limpio, **108 source files**.
- Merkle vivo (`atlas reality`): cadena **ok**, **1029 records**, íntegra.
- Docs: **frescos**, sin counts contradictorios (reality kernel operativo).
- Servicio `atlas-core.service`: vivo, PID 3943348, sostiene `.writer.lock`
  desde el reinicio 22:59. **Cero `cold_update.applied` desde el reinicio** →
  working tree limpio mantenido.
- Higiene: 0 `except: pass`, 0 TODO/FIXME reales en `src/`.
- Sentinel desde el reinicio: vetó 1 tool de credenciales (HITL requerido),
  bloqueó 2 tools por drift de hash, manejó 2 servers MCP externos que cerraron
  stdout al arrancar. **Comportamiento correcto, no bugs** — la frontera de
  confianza externa está defendida.

## Creencia falsa corregida

**Afirmé** (sesión previa) que el primer `cascade.route` real aparecería cuando
el cron autónomo pasara por el codegen. **Es falso.** Verificado:

- `CodegenProposer.propose_patch` (donde se cableó la cascada, commit `2294ae3`)
  **no tiene ningún caller en `src/`** — solo los tests lo invocan.
- El CLI **no expone** codegen ni cascada (0 referencias en `cli.py`).
- El `maintenance_scheduler` autónomo hace registry-scout → analyst → adopter
  (MCP) + ciclo de bumps de deps. **No invoca codegen.**
- El self-audit autónomo usa `PatchGenerator` (plantillas deterministas, sin
  LLM ni cascada), un mecanismo distinto.

### Causa raíz

La capa 2 se cableó al path de codegen *human-initiated* ("el humano apunta el
objetivo", por diseño de `CodegenProposer`), pero ese path **no tiene entrada
en producción**: ni CLI, ni trigger autónomo. Además, `MerkleWriterLock` +
"no CLI contra workspace vivo" impiden dispararlo a mano con el servicio
corriendo. **El consumidor real de la capa 2 es la capa 3** (workers en
worktrees aislados), como ya declaraba el roadmap. No hay `cascade.route`
autónomo que esperar hasta entonces.

### Consecuencia para el diseño de la capa 4

El lado **consumidor** del LessonStore (Analyst/codegen cargan lecciones como
contexto) presupone que esos productores corren — y hoy no son alcanzables. El
lado **store + verificador** (capturar lecciones verificadas) sí aporta valor
inmediato. Por eso esta iteración construye el núcleo verificable y **difiere
el cableado de consumidores a la capa 3**, donde codegen tendrá contexto de
ejecución aislado.

## Riesgos residuales

- Capa 2 verificada por tests pero inalcanzable en operación hasta la capa 3.
  No es un bug: es que su consumidor no existe aún. Documentado aquí y en el
  anexo de ADR-042.
- La auditoría autónoma de 24h sigue sin haber corrido un ciclo completo (5
  intentos fallidos el 2026-06-12; unidad systemd creada pero no instalada,
  por decisión del operador).
- Servers MCP externos siguen siendo programas externos; Sentinel reduce el
  riesgo de adopción pero la salida sigue siendo no confiable.

## Correcciones aplicadas en esta sesión

- Postmortem (este documento) con la creencia falsa nombrada, no solo lo
  arreglado.
- Anexo a ADR-042: capa 2 alcanzable solo vía capa 3; no hay cascade.route
  autónomo esperado.
- Núcleo de capa 4 (LessonStore) additivo y verificable, con consumidores y
  seeding-real diferidos explícitamente.
