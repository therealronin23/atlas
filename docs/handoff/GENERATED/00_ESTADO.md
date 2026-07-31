<!-- GENERADO por atlas handoff 2026-07-31T23:57:03.593637+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **2026-08-01 (tarde) — LangGraph CERRADO, matriz de absorción completa, y DOS
  autocorrecciones mías sobre diagnósticos que había dado por buenos.**
  **LangGraph (`23f3699`)**: última fila con cero código. Al medir contra el
  código real, el "StateGraph sketch" no hacía falta — `VALID_TRANSITIONS`
  (`contracts.py:49`) **ya es** un grafo dirigido de `TaskStatus` con aristas
  guardadas (`transition()` lanza ante una no declarada); la ramificación
  condicional vive en los ejecutores; y los checkpoints se absorbieron de Cline
  en julio. Nuestra tabla es ESTÁTICA a propósito: aristas mutables en caliente
  no sostendrían el invariante. Cerrado como **no-goal razonado**, sin adoptar
  el paquete. **La matriz de absorción queda CERRADA.**
  **Bug de clase, TERCERA vez**: `kanban_bridge` leía `HERMES_*` de `os.environ`
  sin cargar nunca el `.env`. Desde un proceso limpio resolvía transporte `ssh`
  y reventaba, con la config real diciendo `local`. Arreglado en import + test.
  **Autocorrección 1 — Hermes A/B/C**: la tarea `critical` de 564 h NO es un
  fallo del sistema. Su cuerpo dice *"la descripción actual es un placeholder
  ('title' y 'body'), indica el objetivo específico"*: **es Hermes preguntando
  al operador**, y sale `skipped_nonspawnable` porque espera una respuesta
  humana, no un worker. Y las tres de servidor **no se pueden completar como
  están escritas**: el cuerpo es literalmente `"cuando yo no este, monitoriza
  servidor C"`, sin definir qué servidor, y el único que hubo (el VPS) está de
  baja. La causa del crash de C está en su log: *"worker exited cleanly (rc=0)
  without calling kanban_complete or kanban_block — protocol violation"* — corrió
  y salió bien, pero nunca cerró el bucle. **Decidir qué son A/B/C es del
  operador**; no se tocan.
  **Autocorrección 2 — lecciones**: dije que había que "unificar la ruta del
  LessonStore". **Habría sido el arreglo equivocado.** Las 21 lecciones de
  `<repo>/workspace/lessons` están **trackeadas por git**: el split es
  DELIBERADO — curadas y versionadas frente a runtime del daemon. Unificar haría
  que cada lección aprendida en caliente ensuciara el árbol, que es el incidente
  "9 YAML regenerados" que ya cita `self_build_runner`. El problema medido sigue
  en pie, mejor enunciado: **el daemon no VE ninguna de las 21 curadas** porque
  su recaller sólo lee el almacén de runtime (vacío). El arreglo es **lectura de
  ambos**, escritura sólo en runtime. Sigue bloqueando el envejecido.
  **Política de esta tanda** (orden del operador): economizar tokens, delegar en
  Atlas para medir su eficacia, y actuar de mentor. Delegar arreglos de 4 líneas
  cuesta más que hacerlos; la delegación real se reserva para el Cónclave.
