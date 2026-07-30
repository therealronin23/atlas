<!-- GENERADO por atlas handoff 2026-07-30T09:36:51.488754+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **2026-07-30 — cierre de sesión: README real, drift al preflight, churn de
  INDEX.yaml eliminada, y salida autónoma del daemon integrada.**
  **README** (`bf7cd1e`): de stub de 8 líneas a puerta de entrada real.
  Deliberadamente SIN cifras de tests (AGENTS.md lo prohíbe y el número se
  movió 4515→4716 en una sesión): lleva los comandos para derivarlas. Cada
  afirmación verificada antes de escribir; dos sobre-afirmaciones propias
  cazadas y corregidas antes del commit (decía "cableados al pre-commit",
  falso; y un encabezado "Licencia" sin fichero LICENSE). Excluida a
  propósito la tesis del auditor externo ("aparato de auditoría que contiene
  un runtime", "nadie más tiene detección bidireccional"): plausible y NO
  medida contra el SOTA, así que meterla habría sido el defecto que el propio
  README denuncia. Sus hechos observables sí entran, como descripción.
  **`component_wiring_drift` cableado a `PreflightGate`** (`bf7cd1e`):
  corrección de una infra-afirmación mía. `ecosystem_map_drift` YA corría en
  el preflight desde MAXIMUS Cycle 13 —lo describí como "a mano", falso— y
  `component_wiring_drift` genuinamente no estaba, porque
  `_run_sanitation()` devuelve un dict EXPLÍCITO de claves: añadir un
  detector a `sanitation_audit.py` no llega al gate solo. El preflight corre
  antes de cada ciclo de autoconstrucción, así que es la colocación de mayor
  valor: el lazo no se propone cambios mientras el canon miente sobre qué
  está cableado. El test afirma el conjunto exacto de claves, que es lo que
  fuerza a cablear el próximo a propósito.
  **Churn permanente de `docs/INDEX.yaml` eliminada:** tiene DOS escritores
  —`docs_triage.py` (`width=4096`, lo corre el daemon) y
  `docs_index_audit.py` (default 80)— y cada alternancia reformateaba el
  fichero entero. Medido: el alta de UN doc produjo **31 líneas de diff, de
  las cuales 1 era el cambio real**. Unificado a `width=4096` y verificado
  idempotente (escribir con uno y luego con el otro ya no produce diff).
  **Salida autónoma del daemon integrada:** `docs/knowledge/research_2026-07-30.md`
  (666 líneas, 113 hallazgos desde 3 semillas expandidas a 12 consultas),
  dado de alta como `propuesto` por la regla determinista de triage. Es el
  lazo research→acción funcionando sin intervención.
  **LÍMITE HONESTO, no resuelto:** un run previo de la suite mostró UNA `F`
  al 97% y se cortó por timeout antes de nombrarla. El run completo posterior
  dio **4716 passed, 0 failed, exit 0**, así que NO reprodujo y no puedo
  identificarla. Descartados por aislamiento: índice/triage (17), preflight
  (7), los otros dos que afirman sobre `sanitation_findings` (45), workbench
  (44) — todos verdes. Descartado también que el daemon estuviera escribiendo
  (cero ficheros del repo tocados en la ventana). Queda como **flaky sin
  identificar**, registrado en vez de dado por arreglado.
  **Regresión medida del bucle de desarrollo:** la suite pasó de ~370s a
  **520-564s** porque los tests del preflight ejercitan
  `component_wiring_drift` de verdad (11,3s por invocación: `graph_server`
  abre la BD Kuzu por consulta, su diseño). Deuda declarada; el arreglo es
  batchear las consultas al grafo, no mockear el contrato.
  Estado final: `check_canon` **PASS** (2103 registros),
  `docs_index_audit --strict` exit 0, suite **4716 passed**, mypy **333**
  ficheros.
  **Próxima acción:** sesión nueva. Pendientes del operador sin tocar:
  ADC-WO-107 (bridge 7341), ADC-WO-124 (admisión desktop), F2.6 necesita
  `claude setup-token`, y el batching del grafo si la suite molesta.
