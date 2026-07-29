# Construction Plan — Atlas Definitive Candidate

Este plan convierte la arquitectura objetivo en una secuencia ejecutable. Los
work orders máquina, con archivos, pruebas, riesgos y rollback, están en
`docs/canon/implementation_registry.yaml`.

## Regla de ejecución

Un work order se ejecuta solo si:

1. su autoridad fuente está registrada;
2. su programa y owner son claros;
3. el grafo/blast radius está fresco o la limitación queda declarada;
4. no exige una decisión constitucional nueva;
5. no reduce seguridad ni necesita secretos ausentes;
6. tiene test observable, aceptación y rollback;
7. su estado es `READY`.

`REQUIRES_OPERATOR`, `BLOCKED`, `REJECTED` y `SUPERSEDED` nunca se interpretan
como permiso implícito.

## Orden definitivo

```text
R0 Candidata definitiva
  ├─ ADC-WO-000 preservación/baseline
  ├─ ADC-WO-001 fuentes vivas
  ├─ ADC-WO-002 autoridad y registros
  ├─ ADC-WO-003 arquitectura/programas/plan/status
  ├─ ADC-WO-004 gate canónico + CI
  ├─ ADC-WO-005 realidad y claims
  ├─ ADC-WO-007/008/009 guards + MCP + UI
  ├─ ADC-WO-010 linajes y ADR-078
  └─ ADC-WO-006 auditoría/validación/delivery
          │
          ▼ operador acepta o solicita cambios
R1 Boundaries constitucionales
  ├─ ADC-WO-102 Mission/Task
  └─ ADC-WO-103 Memory/Knowledge
          │
          ▼
R2 Atlas Engineering Workbench
  ├─ ADC-WO-108 Cut 1 findings/review/debug
  ├─ ADC-WO-109 Cut 2 convergencia integral desktop
  └─ ADC-WO-110 asimilación ACP/patrones Zed
          │
          ├─ R2A Android dedicado (ADC-WO-111)
          │
          ├─ R3 Hermes/federación (ADC-WO-100, autorizado)
          └─ P12 enforcement (ADC-WO-105, autorizado)
                         │
                         ▼
R4 Hosted completo
                         │ evidencia de límite real
                         ▼
R5 Native Wave 5 (ADC-WO-104, hoy BLOCKED)
```

Los programas siguen activos durante todas las releases. R0–R5 son orden de
entrega, no sustitutos de P00–P12.

## R0 — Atlas Definitive Candidate

### Work orders ejecutables

| Work order | Resultado | Gate de aceptación |
|---|---|---|
| ADC-WO-000 | checkout original preservado, backup/worktree y baseline | bundle y hashes verificados; original intacto |
| ADC-WO-001 | investigación dirty preservada sin promoción; seis candidatos no instalados | toda ruta dirty tiene disposition; índice estricto |
| ADC-WO-002 | autoridad, decisiones atómicas, conflictos, supersesiones y contratos | todos los JSONL parsean; ADR-076/077 completos |
| ADC-WO-003 | ATLAS/VISION/ARCHITECTURE/PROGRAMS/PLAN/STATUS | una entrada; CURRENT/TARGET/TRANSITION; P00–P12 |
| ADC-WO-004 | guard de integridad canónico en tests/CI | TDD rojo→verde; CI sin dependencia nueva |
| ADC-WO-005 | matriz completa y claims vivos corregidos | ningún `LIVE_VERIFIED` sin prueba; harness ≠ producto |
| ADC-WO-007 | guard constitucional high después de cualquier Decider | ningún seam inyectable convierte high en `Allow` |
| ADC-WO-008 | admission y vetting MCP fail-closed sin ejecutar candidatos | argv peligroso bloqueado; clean-unadmitted queda en cuarentena |
| ADC-WO-009 | dependencia UI saneada sin cambiar el runtime objetivo | build y audit exactos; cero advisories |
| ADC-WO-010 | linajes externos y decisión ADR-078 reconciliados | Atlas Core único; host y donors sin claims de integración |
| ADC-WO-117 | intake y binding de patch ColdUpdate fail-closed | rutas permitidas, governance inmutable y bytes aprobados revalidados antes de efecto |
| ADC-WO-118 | validación ColdUpdate aislada por Bwrap | candidato read-only/sin red/entorno explícito; no fallback host ni falsa prueba de build completo |
| ADC-WO-119 | perfil Kuzu de apertura explícito y acotado | ningún constructor directo; opener y rutas de grafo pasan bajo Bwrap de 2 GiB; no se afirma build completo |
| ADC-WO-120 | DNS determinista sólo para tests candidatos con fetcher inyectado | Bwrap sigue sin red; SSRF de producción no cambia; rutas focales reales pasan dentro del jail |
| ADC-WO-006 | auditoría independiente y entrega local | 0 BLOCKING; MAJOR resolubles corregidos; bundles verifican |

### Cambios de implementación autorizados

- reforzar el seam constitucional para que ningún Decider inyectado convierta
  sensibilidad alta en `Allow`;
- aplicar el mismo guard al ReceiptBroker de plugins;
- hacer fail-closed el vetting de llamadas/snapshots de terceros y revocar en
  runtime un MCP que falle su re-vet o presente drift;
- imponer la allowlist/digest de los patches ColdUpdate antes de worktree,
  validación, aprobación, apply, tier-1 o rollback, sin ampliar los efectos
  autorizados;
- ejecutar pytest/mypy de candidatos ColdUpdate dentro de Bwrap read-only y
  fail-closed, sin promover su compatibilidad focal a build completo;
- fijar el perfil Kuzu de aplicación (mapa máximo y buffer pool explícitos)
  antes de ejecutar grafos o índices dentro de un candidato; el límite físico
  del runner y el receipt completo continúan como gates separados;
- corregir comentarios/metadata que afirman auto-adopción, producto web-first,
  activación inexistente o datos vivos sin procedencia;
- añadir validator y gate CI de canon;
- no añadir dependencias ni modificar `config/governance.json`.

### Aceptación R0

- suite Python y mypy sin regresiones introducidas;
- UI compila; la incompatibilidad de Node local y advisories se clasifican con
  evidencia exacta;
- audit/reality se vuelven a ejecutar y no se hereda liveness del baseline;
- ADR-076 C sigue rechazado/ausente;
- ADR-077 sigue opt-in y rule 4 queda estructuralmente protegida;
- Hermes no se marca live;
- Native Wave 5 sigue bloqueada;
- revisión adversarial no deja BLOCKING;
- commits atómicos, diff final, bundle y ZIP documental verifican.

### Rollback R0

Cada commit revierte un work order cohesivo. El checkout original no se toca.
La rama completa puede abandonarse eliminando únicamente el worktree y la
rama después de la revisión; el bundle previo conserva toda la historia.

## R1 — Boundaries constitucionales

### Lote de decisión A: Mission y Task

El operador elige el dueño durable de Task y el contrato Mission→Task. La
decisión debe fijar:

- state machine, idempotencia y único writer;
- Policy/approval persistence;
- compatibilidad con el ledger y APIs actuales;
- migración, doble lectura temporal y rollback;
- qué parte sigue perteneciendo al Orchestrator.

Hasta entonces: no hay migración y las APIs actuales permanecen.

### Lote de decisión B: Memory y Knowledge

El operador fija owners y promotion paths para SQLite, BlockMemory, Kuzu,
vault, semantic graph y Evidence:

- privacidad, tenancy y sensibilidad;
- distillation antes de compartir;
- temporalidad y contradicción;
- borrado de derivados/crypto-shred;
- export, migración y rollback.

Hasta entonces: ADR-057 por caso de uso; cero promoción automática nueva.

### Aceptación R1

ADRs aceptados, schemas versionados, contract tests, migración ensayada y
rollback demostrado. Sin owner único, R1 no se declara completo.

## R2 — Atlas Engineering Workbench

ADR-078 cierra dos decisiones: el primer producto es Atlas Engineering
Workbench y el host desktop parte de la línea CodeOSS/VSCodium. Void aporta
capacidades precursoras y Zed aporta ACP/patrones seleccionados; Atlas Core
conserva estado, autoridad y contratos.

### Cut 1 — plano de ingeniería

`ADC-WO-108` define `EngineeringFinding` y prepara evidencia de revisión de
código y diagnóstico automático para una futura ruta gobernada al orquestador.
Debe producir alertas tipadas, deduplicables, atribuibles y accionables sin
conceder a la UI permiso de ejecución.

El primer subcorte (2026-07-29) ya fija el schema v1, journal append-only,
deduplicación, adaptación de self-audit, composición determinista del
`UniversalVerifier` y un `EngineeringDiagnosticCoordinator`. Este último captura
un `ValidationReport` existente, compone el `RootCauseClassifier` inyectado,
normaliza la clasificación y persiste sólo evidencia estructurada segura, no
salida cruda ni texto libre del clasificador.
Puede existir antes de un owner durable Mission/Task porque no posee Task ni
produce efectos. Un publisher opt-in ya registra finding/review metadata en
Merkle antes de emitir eventos tipados al `EventBus`; tampoco crea Tasks ni
llama al Orchestrator. Hipótesis de grafo/historial/memoria,
producción/validación de correcciones y wiring de runtime, Orchestrator y
proyección siguen ausentes y no se infieren
como implementados. `EngineeringReviewBaselineStore` ya fija una base sólo tras un
`PASS` con reviewers y una referencia explícita de aceptación; conserva el
snapshot de lifecycle previo, exige que el llamador verifique ancestry y no
convierte un resultado verde en promoción automática. El preparador incremental
verifica ancestry contra objetos Git y calcula el delta con diff externo y
textconv deshabilitados, sin ejecutar código candidato ni tocar el worktree; el
runner pasa ese request al coordinador existente sólo cuando hay delta pendiente.
El normalizador incremental compara únicamente `dedupe_key` opacas e idénticas
con el snapshot aceptado: una ausencia queda `NOT_REOBSERVED`, nunca se infiere
como `RESOLVED`, ni se escribe el journal.
`EngineeringReproductionRunner` reproduce sólo targets pytest validados desde
commits inmutables en un worktree efímero del mismo repositorio y jail Bwrap de
solo lectura/sin red. Es fail-closed si falta Merkle o el jail; sus outputs son
efímeros y no entran en la cadena ni en un finding sin el sanitizador diagnóstico.
Sólo una ejecución completada y recibida puede proyectarse en memoria al
`ValidationReport` ya consumido por el coordinador de diagnóstico.

### Cut 2 — convergencia desktop integral

`ADC-WO-109` mueve/adapta el trabajo útil de CodeOSS/VSCodium y Void, y
`ADC-WO-110` integra las piezas ACP/patrones de Zed mediante puentes Atlas. El
alcance exacto se fijará al diseñar el work order, pero la intención aprobada
es un corte completo y cohesivo, no un prototipo acotado por defecto. Reutilizar
precede a reescribir; toda pieza conserva procedencia, licencia y estrategia de
actualización.

`atlas-shell` sigue siendo arnés de validación durante la transición. Business
Core y Compliance Gateway permanecen líneas futuras; no se eliminan.

### Gates R2

- journey end-to-end con datos no simulados;
- autoridad de Task/Memory ya cerrada;
- API surface no posee verdad durable;
- lineage/provenance y licencias verificadas;
- estrategia upstream/forward-port y rollback demostrada;
- findings/review/debug llegan al orquestador por contratos versionados;
- UX/accessibility/offline;
- threat model, telemetry y restore;
- aceptación explícita del operador.

## R2A — Proyección Android

`ADC-WO-111` conserva el hard target Android de ADR-071. Se abre después de
estabilizar Surface API y los contratos del Workbench; una base desktop no se
declara solución móvil. Requiere ADR de arquitectura, journey propio, offline,
seguridad, actualización y rollback.

## R3 — Hermes y distribución

`ADC-WO-100` requiere credenciales y autoridad externa del operador. Orden:

1. identidad y lease;
2. pairing autenticado;
3. propuesta Hermes;
4. decisión Atlas;
5. receipt y timeout;
6. revoke/disconnect;
7. rollback a local/mock.

No se hace deploy, pairing ni smoke externo con secretos ausentes. Un VPS
histórico no satisface este release.

## R4 — Hosted y Osmosis

Hosted consolida packaging, services, resource/thermal policy, Product OS y
recovery. P12 requiere una decisión separada:

- gateway opcional con garantías limitadas; o
- enforcement no-bypass con amenaza, disponibilidad, bypass tests y rollback.

ADR-074 solo cubre su slice activo; no decide el guarantee profile general.

## R5 — Native Wave 5

`ADC-WO-104` permanece `BLOCKED`. Para abrirlo deben existir conjuntamente:

- limitación Hosted medible que Native resuelve;
- threat model aceptado;
- presupuesto de hardware/personas;
- evidencia de portabilidad;
- API Runtime↔Prime estable;
- plan de migración y rollback ensayable;
- autorización explícita del operador.

La “Ola 5” de benchmarks del 2026-07-23 fue una campaña distinta. Su tooling
se construyó, pero no existen resultados live del judge que respondan la
pregunta empírica; tampoco autoriza Native.

## Deuda y trabajo diferido

| Deuda | Programa | Estado y siguiente acción |
|---|---|---|
| Context packs vacíos | P02 | diseñar schema tras boundaries R1 |
| Graph candidato no refrescado | P02 | regenerar contra commit final antes de claim estructural fresco |
| Destilación privada→shared no universal | P04/P05 | contrato y pipeline después del ADR de memoria |
| LivingGraph sin importadores | P08 | decidir integrar o archivar; no llamarlo productivo |
| Snapshot UI sin provenance/freshness | P08 | añadir schema/commit/date o mantener label fixture |
| Plano findings/review/debug | P03/P08/P09 | contract/journal, ReviewCoordinator, diagnóstico, reproducción Bwrap auditada, publisher Merkle/EventBus, baseline explícito y normalización observacional de diff/review code+tests presentes; faltan hipótesis de grafo/historial/memoria, wiring runtime/Orchestrator y proyección gobernada (`ADC-WO-108`) |
| Workbench desktop integral | P08 | ADC-WO-109/110, después de boundaries R1 |
| Proyección Android | P08/P11 | ADC-WO-111, tras estabilizar Surface API/Workbench |
| Security Council no encola Task universalmente | P03/P09 | depende de Mission/Task boundary |
| Unblock con actor no criptográfico | P01/P09 | incluir identidad/ceremonia en ADR futuro |
| Hermes/pairing/node identity no live | P10 | ADC-WO-100 |
| Judge vs baseline sin run real | P09 | ejecutar solo con presupuesto/autoridad de proveedor |
| Membrane enforcement profile | P12 | ADC-WO-105 |
| Native | P11 | ADC-WO-104 bloqueado |

## Decisiones reservadas al operador

1. Mission/Task authority.
2. Memory/Knowledge authority y promotion map.
3. Alcance exacto y ADRs de boundary del Cut 2 integral, sin reabrir su
   naturaleza ni el producto/host ya aceptados.
4. Arquitectura de la proyección Android cuando sus dependencias estén listas.
5. Cualquier cambio a high-sensitivity/human control.
6. Credenciales y pairing Hermes externo.
7. Guarantee profile de Osmosis.
8. Apertura de Native Wave 5.
9. Autorizar los POST mutantes del bridge 7341 mediante un nuevo boundary o
   restaurar el contrato read-only de ADR-058/071 (`ADC-WO-107`).

Los defaults fail-closed están registrados en
`docs/canon/open_questions.jsonl`. Una decisión sobre un lote no bloquea trabajo
seguro de otros programas.

## Disciplina por work order

1. cargar instrucciones y context pack;
2. confirmar fuente y blast radius;
3. escribir prueba que demuestre el gap;
4. implementar el cambio mínimo;
5. pruebas focalizadas y mypy;
6. docs/status/ledger;
7. diff y auditoría de seguridad;
8. commit atómico;
9. verificación independiente;
10. receipt, aceptación y rollback.

Una release no se cierra por calendario ni por número de commits. Se cierra
cuando sus gates producen evidencia y las limitaciones restantes están
clasificadas sin marketing.
