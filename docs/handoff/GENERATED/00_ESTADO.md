<!-- GENERADO por atlas handoff 2026-07-30T21:12:18.432350+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **2026-07-30 — plan "el montón": F2.6 2/6→5/6, enforcer de cifras real,
  nvidia_mistral_large diagnosticado (410 Gone real, no bug), tick de
  compliance del workbench cableado.**
  **F2.6** (test de sucesión): causa real no era la rúbrica — el driver
  (`gemini_free`, L1 por defecto) se quedaba sin texto en el turno 3.
  Arreglado en dos frentes elegidos por el operador: (1) bug de calibración
  real en item_4 (`historical_language` solo reconocía español; `AGENTS.md`
  usa "SUPERSEDED"/"historical" en inglés — ampliado); (2) scaffolding
  reforzado en `f26_agentic_dispatch.py` (prohíbe terminar vacío, exige
  contestar cada pregunta numerada, exige `GoldenRoute` antes de `Edit` en
  docs rastreados, exige citar rutas exactas) + nivel subido L1→L2. Dos
  corridas reales verificadas: 2/6 → 3/6 → 5/6. Único fallo restante,
  `item_2`: el heurístico no distingue "leer AGENTS.md para conocer la regla
  grafo-primero" de "ignorar la regla" — límite de la rúbrica, NO tocado
  (`f26_grading.py` solo cambió en el fix de item_4, según lo acordado).
  Aparte, aplicado el diff ya preparado a `AGENTS.md` (afirmación falsa de
  auto-regeneración del grafo) — no es el fix de F2.6, corrección de
  exactitud independiente.
  **Enforcer de cifras** (`reality.py:_docs_state`): escaneaba
  `["AGENTS.md","CLAUDE.md","ROADMAP.md"]`, 2 de 3 inexistentes → verde
  vacío. Rediseñado: NO "escanear todo .md" (WORK_LEDGER.md es log
  append-only por diseño, escanearlo lo dejaría "stale" para siempre sin
  señal real) sino los docs cuyo ROL es declarar un resumen único
  (`STATUS.md`, `docs/handoff/GENERATED/00_ESTADO.md`), con regex anclado a
  `N passed` (el genérico `\d+ (tests?|passed|...)` sobre-matcheaba dentro
  del mismo doc: "19 tests" del paquete ZIP, "37 tests" de un hallazgo
  histórico). Contra el repo real: `stale`, 4692 (STATUS.md) vs 4716
  (00_ESTADO.md). Diff de reconciliación de `STATUS.md` preparado
  (scratchpad, NO aplicado — cifra real medida hoy: **4774 passed, 6
  skipped, 27 deselected**, mypy 334 ficheros, suite completa ~10min);
  `00_ESTADO.md` NO se reconcilia a mano (`atlas handoff --help`: "GENERADO
  desde el sustrato... nunca a mano" — confirmado `STALE` vía
  `atlas handoff --check`, se regenera después de reconciliar `STATUS.md`).
  **nvidia_mistral_large**: investigado, NO es bug — 410 Gone real del
  vendor desde 2026-07-23 (confirmado con Merkle: 7 días consecutivos
  muerto). Corregí una lectura mía anterior: el label del Cónclave por
  linaje (no por vendor de hosting) es diseño deliberado y testeado, no un
  fallo de atribución. Patrón ya establecido en el repo (asiento CN pasó por
  esto 2 veces): remapear a un NIM nuevo tras prove-it en vivo, no retirar
  en silencio — remapeo requiere investigación de catálogo aparte, NO
  ejecutado en este plan.
  **`t4-workbench-compliance-review-tick`**: 107 hallazgos acumulados desde
  2026-07-23 (`workspace/mcp/workbench_compliance_findings.jsonl`), nada los
  leía. `summarize_compliance_findings` (`workbench_compliance.py`) cuenta
  total/recientes (ventana 24h) y decide veredicto honesto
  (`no_findings`/`normal`/`elevated`, umbral 20) sin borrar ni mutar el
  fichero. Tick mismo patrón que `provider_status`/`provider_discovery`
  (opt-in, guardia anti-recursión, cadencia 24h, Merkle, cableado en
  `atlas reality`). Corrida real: `total=107, recent=38, verdict=elevated`.
  TDD en las 4 piezas de este frente, RED verificado en cada una. 90 tests
  impactados, 1315 passed/1 skipped, mypy limpio. Suite completa verificada
  aparte (ver arriba): 4774 passed, exit 0.
  **Pedido del operador a mitad de sesión**: alcance de T2.1 excluye Android
  hasta que lo pida explícitamente — los micro-PoC de Flutter/Compose se
  quedan en el tramo Linux, sin medición de teléfono.
  **T2.1 PAUSADA — bloqueo real de hardware, no mío**: al verificar el
  renderer del micro-PoC Flutter, `nvidia-smi` falla ("Driver/library
  version mismatch", kernel 535.309.01 vs NVML 580.173.02, ambas familias
  de paquetes de driver coexistiendo); forzar offload
  (`__NV_PRIME_RENDER_OFFLOAD=1`) da error X real (`BadValue`), no
  fallback silencioso. **El informe de medición existente de Flutter
  (2026-07-23, PASA, 58-61fps) casi seguro midió la iGPU Intel HD 530, no
  la GTX 960M** — veredicto en duda hasta remedir. Requiere `apt` +
  reinicio de la máquina real, fuera de lo que toco sin permiso. Operador
  eligió parar toda la Fase 2 aquí y arreglar el driver por su cuenta;
  próxima acción cuando confirme `nvidia-smi`/`glxinfo -B` con la GPU real.
