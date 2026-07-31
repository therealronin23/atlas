<!-- GENERADO por atlas handoff 2026-07-31T10:45:37.557428+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **2026-07-31 — Las 4 decisiones REQUIRES_OPERATOR con dossier completo,
  CERRADAS: ADC-WO-102, ADC-WO-103, ADC-WO-107, ADC-WO-124.** Orden del
  operador: "hazlo todo y toma las decisiones por mi en base a evidencia y
  criterio profesional". Recomendación propuesta primero (102 aceptar,
  103 aceptar-dirección-sin-activar, 107 restaurar-solo-lectura,
  124 admitir-vía-pipeline), confirmada con "sí", implementada con TDD
  real pieza por pieza — con dos correcciones de alcance EN VIVO tras
  encontrar que la realidad era distinta de lo planteado (ver abajo).
  **ADC-WO-102/103** (`04f3ec9`): documentación únicamente, sin código —
  REQUIRES_OPERATOR→READY en `implementation_registry.yaml`,
  `open_questions.jsonl` RESOLVED. Colateral: ADC-WO-108 seguía en canon
  como READY con `current_state` describiendo piezas "absent" que ya se
  habían cerrado en esta misma sesión — canon desincronizado del código
  real, corregido a DONE con el estado medido.
  **ADC-WO-107** (`9f884ab`): mi primera recomendación ("restaurar
  solo-lectura") resultó, al leer `product_routes.py` completo, que habría
  borrado TODO el Product OS (Fase 15) — 13/21 rutas mutantes son el
  producto, no un descuido. Corregido en vivo con el operador antes de
  tocar código: arreglo acotado, solo `business/core/activate`/`reject`
  (el hallazgo real: aprueban una decisión gobernada en el mismo proceso
  del bridge, sin la separación de proceso que `permissions/approve` tiene
  vía subproceso Orchestrator/ADR-058). Como `BusinessCoreEngine` no es
  Orchestrator, en vez de replicar el subproceso se igualó la altura de
  auditoría: ambas rutas escriben ahora un receipt Merkle verificable
  (`business_core.activated`/`.rejected`) en la misma cadena que el resto
  de Atlas. ADR-080 nuevo (excepción acotada a ADR-058/071, con
  supersession registrada). Las otras 19 rutas mutantes: intactas.
  **ADC-WO-124** (`8f13dbc`): el más grande de los 4 — descubrí que el
  mecanismo de "receipt Merkle revocable" que el propio WO exige **no
  existía como código** (`_is_governed_native_command` solo admitía
  módulos Python nativos de Atlas). Pregunté al operador si construir el
  mecanismo completo ahora o solo registrar la decisión en principio;
  eligió construirlo. `src/atlas/security/third_party_admission.py`
  (nuevo) + `SentinelGate._vet_third_party_receipt` (única vía que levanta
  el veto: recomputa el hash del ejecutable REAL en cada `vet_command()`,
  exige cmd/cwd/env_extra/env_passthrough idénticos byte a byte, ningún
  DISPLAY distinto a `:99`, ninguna variable extra) + CLI
  `atlas mcp admit-third-party`/`revoke-third-party`. TDD real en las 3
  piezas. **Admitido de verdad en `$ATLAS_HOME` real**:
  `computer-control-mcp==0.3.10`, hash
  `026352a0712ea33f3aac7dcdf1c4d7fbc583b8923f4c84e4def597cefbfe2451`, MIT,
  semgrep `p/security-audit` 79 reglas/14 rutas/0 hallazgos (confirmado en
  vivo, ~11min de corrida real tras dos intentos que expiraron por
  timeout de red del registry), Xvfb-only. Cadena Merkle verificada
  íntegra tras la admisión. **Los 4 E2E funcionales reales corren y PASAN**
  contra Xvfb `:99` + `fluxbox` + `xclock`/`xcalc` reales lanzados para
  esta verificación (antes: `SKIPPED CONTRADICTED`) — el fixture de test
  admite el mismo artefacto real en su workspace efímero vía la misma
  función gobernada, no un bypass. `docs/design/mcp_catalog.yaml`:
  `quarantined`/`blocked-admission` → `vetted`/`verificado`. 3 tests que
  fijaban el estado de cuarentena como regresión permanente actualizados
  para reflejar el estado real (uno de ellos ahora usa un catálogo
  sintético para no perder la cobertura del caso "sigue rechazando en
  cuarentena").
  **Efecto en producción, dicho sin rodeos**: `~/atlas/mcp_servers.json`
  ya tenía esta entrada `enabled: true`; lo único que la bloqueaba era el
  veto de Sentinel. La próxima vez que el Orchestrator real arranque sus
  servers MCP con Xvfb `:99` arriba, este ejecutable de terceros arrancará
  de verdad, confinado a `:99` (nunca al display real `:0`, ese gemelo
  sigue `unadmitted`). No había daemon vivo al admitir, así que no hubo
  arranque inmediato.
  **Estado medido**: suite completa 4853 passed/0 fallos (394s), mypy 337
  ficheros limpio, `check_canon.py` PASS (2105 registros) en cada paso.
  **Pendiente de aprobación del operador (diff preparado, no aplicado)**:
  `docs/backlog.yaml` `t3-1-universal-gui-operator` `deferred`→`done` — la
  condición que su propio comentario pedía ("hasta que los E2E vuelvan a
  ejecutarse") ya se cumplió.
  **De las 6 decisiones REQUIRES_OPERATOR originales, quedan
  ADC-WO-100 y ADC-WO-105** — genuinamente irreducibles a más trabajo mío
  (credenciales/VPS externos el primero, juicio de producto/legal el
  segundo). ADC-WO-104/109/111 siguen `BLOCKED` por dependencia, no piden
  decisión todavía.
