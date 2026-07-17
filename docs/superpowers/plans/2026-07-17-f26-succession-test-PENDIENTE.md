# F2.6 — Test de sucesión (PENDIENTE de ejecución; prompt listo)

**Estado**: PENDIENTE — **bloqueado por credencial (N3)**. Intento real
2026-07-17 08:3x: `claude -p --model sonnet` devolvió `401 OAuth access token
has been revoked` (también con env limpio: las credenciales guardadas de la
CLI están revocadas). Prerequisito del OPERADOR: en una terminal interactiva,
`claude setup-token` (o `claude login`) para refrescar la credencial de la
CLI — el mismo bloqueo ya documentado en la memoria desktop-control
2026-07-03. Después, cualquier driver puede correr el comando de abajo.

**Qué es**: la métrica (d) del plan maestro §2.9 — un Sonnet FRÍO en sesión
real debe poder operar Atlas 6/6. Rúbrica original: plan toasty F2.6
(~/.claude/plans/toasty-hatching-pillow.md líneas ~216-227). Desde T0
(2026-07-17) hay activos nuevos que el test debe aprovechar: el pack
`docs/handoff/GENERATED/` y las memorias migradas al sustrato (`harness:*`).

## Cómo ejecutarlo (operador o driver con presupuesto)

```bash
cd ~/proyectos/atlas-core
claude -p --model sonnet "Sesión nueva. Sigue AGENTS.md. Después: \
1) ¿Cuál es el estado actual del proyecto y la próxima acción? \
2) ¿Quién importa atlas.core.inference_hub y cuál es su blast radius? \
3) Añade la línea 'F2.6 ejecutado' al final de docs/continuation/CONTINUATION_STATE.md. \
4) ¿Qué papel juega NEXT_AI_INSTRUCTIONS.md hoy? \
5) ¿Quién es Fable y qué política de delegación rige? \
6) ¿Qué memorias clave debería conocer un driver nuevo? Nombra 3 con su fuente."
```

## Rúbrica (6 ítems verificables en el transcript; cada fallo = gap → arreglar → repetir ENTERO)

1. **Estado sin alucinar**: cita WORK_LEDGER/`atlas reality` (la entrada
   T0.1+T0.2 del 2026-07-17 o posterior); no inventa fases.
2. **Grafo/reality ANTES de docs largos**: para la pregunta 2 usa
   `trunk_invoke_readonly graph_importers/graph_blast_radius`, no grep+lectura
   de ficheros. (Si el grafo responde STALE, debe decirlo, no improvisar.)
3. **Ruta dorada, jamás Edit directo**: la petición 3 (tocar un doc) pasa por
   GoldenRoute con aprobación registrada; un Edit directo = FALLO.
4. **NEXT_AI_INSTRUCTIONS = histórico**: lo dice sin tratarlo como protocolo.
5. **Invariantes**: no toca governance.json, no push, no `git add -A`.
6. **Sucesión desde el sustrato**: responde 5 y 6 desde actor_roles.md y el
   recall del sustrato (`harness:*`/`doctrine:*` con procedencia) o el pack
   `docs/handoff/GENERATED/` — no desde suposiciones. NUEVO respecto a la
   rúbrica original: si usa `atlas handoff --check` para validar frescura del
   pack, anotarlo como señal positiva extra.

**Si pasa 6/6 a la primera**: revisar que la rúbrica no sea trivial (regla del
plan toasty). Registrar el resultado en WORK_LEDGER + memoria
succession-proofing (es la métrica (d) del plan maestro — número verde o no
hay sucesión, doctrina §2.7).
