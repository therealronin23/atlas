<!-- GENERADO por atlas handoff 2026-07-31T00:12:53.280453+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **2026-07-30/31 — T2.1 los 3 candidatos medidos, dos causas raíz del
  Cónclave arregladas, ADC-WO-108 despertado (1/5).**
  **T2.1 REANUDADA Y CERRADA en su tramo Linux**: el operador arregló el
  driver NVIDIA (paquetes 535 fuera) y, con permiso explícito, cambió a
  `prime-select nvidia` + reinicio. Los tres candidatos medidos en la GTX
  960M REAL: Qt 3.68s build/~1.2s arranque/60-61fps/134MB; Flutter
  31.58s/~1.5s/53-61/186MB; Compose 89.8s/~8.1s/53-61/282MB. Los tres PASA.
  **Corrección medida**: el informe de Flutter de 2026-07-23 (58-61fps) había
  medido la iGPU Intel, no la dGPU. Hallazgo permanente: forzar la dGPU vía
  PRIME offload en modo `on-demand` **revienta GTK3 con segfault real**
  (`systemd-coredump`); solo `prime-select nvidia` fijo funciona. Matiz
  honesto de Qt: `MultiEffect` (su ventaja estética citada) exige Qt 6.5+ y
  los repos de esta máquina solo dan 6.4.2 — NO verificable aquí.
  `UI_QUALITY_GATE` pasó de fixture-demo de 2 líneas a esquema real (8
  preguntas + checklist de rechazo) aplicado a los tres; los tres dan
  `passed:false` POR DISEÑO (bancos de prueba de una pantalla, no producto).
  **Cónclave: DOS causas raíz, ambas medidas.** (1) `nvidia_glm` no devuelve
  error, SE CUELGA (probe aislado, exit 124 a los 150s) — y
  `INFER_REQUEST_TIMEOUT_S` era tope POR INTENTO, no presupuesto total, así
  que un colgado costaba 120s×3=360s; con el panel recorriendo reviewers EN
  SERIE, hasta 18min. Arreglado con presupuesto total: **360s → 123.0s
  medido**. (2) El fallback de linaje estaba CONSTRUIDO pero INALCANZABLE en
  2 de 3 asientos: `_walk_chain` filtra por nivel de forma dura y
  `build_trio_reviewers` pedía siempre `primary.level` (US L0→L1, CN L2→L0;
  solo EU coincidía). Los 4 tests previos verificaban qué proveedores lleva
  el hub, ninguno que se llegara a ellos al LLAMAR — wire-before-claim.
  **Medido: el asiento CN pasó de `reachable=False` a `reachable=True`.**
  **Regresión real cazada de paso**: `inference_hub.py` perdió su
  `load_dotenv()` en `5da5f5f` (2026-07-16) como efecto colateral no
  mencionado de un refactor a import perezoso de litellm; ~2 semanas sin que
  nada lo notara. Restaurarlo destapó dos fugas de aislamiento en tests (un
  test "aislado" hacía una llamada REAL a Gemini) y los 3 flags de tick de
  esta sesión sin scrubbear en `conftest.py`.
  **ADC-WO-108 (único WO `READY` del canon) 1/5**: `src/atlas/engineering/`
  eran 2209 líneas de producción + 1868 de tests con CERO callers — completo,
  testeado y dormido. Cableado el tick de Orchestrator componiendo lo que ya
  existía (baselines+preparer+coordinator+store, verificador
  `UnifiedDiffVerifier`), no otro verificador. Corrida real sobre el delta
  del repo: `verdict: pass`. Proyectado en `atlas reality`.
  **Corrección a trabajo mío del mismo día**: mi enforcer de cifras escaneaba
  `docs/handoff/GENERATED/00_ESTADO.md`, que es la proyección LITERAL del
  bloque `## WHERE` de este ledger — incoherente con excluir el ledger. Ya
  solo mira `STATUS.md`.
  **Estado medido ahora**: suite completa **4807 passed, 6 skipped, 27
  deselected** (exit 0, 475s); mypy **334 ficheros** limpio; Merkle íntegra.
  `cold_update` sigue `degraded` y NO es estado rancio: sus 20 fallos son la
  firma exacta de la regresión `e93734c` (sandbox anidado + tests que
  necesitan red, dentro de un BwrapJail sin red) — seguirá así hasta que eso
  tenga solución arquitectónica.
  **Próxima acción**: ADC-WO-108 2/5 (eventos runtime al EventBus, Merkle
  ANTES que bus), luego 3/5 proyección read-only en API (estrictamente sin
  verbos mutantes: ADC-WO-107 es REQUIRES_OPERATOR), 4/5 hipótesis
  graph/history/memory, 5/5 producción de correcciones (jamás aplica un
  parche desde un finding; sale por ColdUpdate/GoldenRoute).
  **Pendiente del operador**: 3 diffs propuestos en scratchpad (STATUS.md
  cifras, `backlog.yaml`, decisión nº10 ADC-WO-124 que falta en
  `OPERATOR_DECISIONS_REQUIRED.md`). Android sigue EXCLUIDO por orden
  expresa.
