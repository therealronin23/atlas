# Atlas Lineage and Engineering Workbench — diseño de simbiosis

- **Estado:** aprobado por el operador
- **Fecha:** 2026-07-28
- **Programas:** P00, P02, P06, P08, P09
- **Autoridad:** directiva del operador en la sesión de convergencia definitiva
- **Objetivo inmediato:** cerrar la recuperación de linajes sin desviar la
  convergencia actual
- **Objetivo de producto:** construir Atlas sobre trabajo existente mediante
  trasplantes, adaptación y puentes gobernados, no mediante reimplementación o
  una mezcla indiscriminada de forks

## 1. Resultado

Atlas conserva una única autoridad de producto en `atlas-core`, pero trata los
repositorios, worktrees, ramas desconectadas y forks locales como un linaje
común de investigación y construcción. Ningún avance sustancial se descarta por
vivir fuera de `main`; tampoco adquiere autoridad solo por existir.

La superficie profesional futura se denomina **Atlas Workbench**. No es un IDE
tradicional centrado en que una persona escriba código. Es una consola de
supervisión para que Atlas:

1. construya mediante agentes;
2. revise cambios incrementalmente;
3. reproduzca y diagnostique fallos;
4. proponga correcciones verificadas;
5. eleve hallazgos al Orchestrator;
6. solicite aprobación antes de efectos;
7. conserve evidencia y aprendizaje.

El editor completo se aprovecha como infraestructura madura para repositorios,
diffs, SCM, pruebas, diagnósticos, Debug Adapter Protocol, extensiones y
correcciones quirúrgicas. Autocompletado propio, tab completion y optimización
para escritura humana continua quedan fuera del objetivo.

## 2. Decisiones vinculantes

1. **Convergencia por linaje, no por topología Git.** Un clon separado puede
   pertenecer al mismo programa Atlas; un worktree no se considera absorbido
   hasta que su valor esté presente o explícitamente clasificado.
2. **Reutilizar antes que reescribir.** Cada capacidad se mueve, porta, envuelve
   o conecta. La reimplementación limpia es el último recurso cuando licencia,
   seguridad o incompatibilidad impiden reutilizar código.
3. **Una implementación canónica.** Los donantes no se convierten en
   autoridades paralelas ni se importan completos por defecto.
4. **Cadena de host, no mezcla horizontal.** La línea prevista es:

   ```text
   Code-OSS actual
       + canalización libre y orientada a privacidad inspirada en VSCodium
       = Atlas Workbench host
           + capacidades portadas de Void
           + ACP y patrones compatibles de Zed
           + contratos gobernados de Atlas Core
   ```

5. **Atlas Core sigue siendo la autoridad.** La Workbench no contiene una
   segunda memoria, política, auditoría, aprobación, inferencia ni ejecución.
6. **La UI es una proyección reemplazable.** Primero se cierran contratos,
   revisión, diagnóstico y eventos; la dirección estética evoluciona después.
7. **Sin autoaplicación encubierta.** Revisar, diagnosticar y proponer puede ser
   automático. Aplicar efectos continúa por Decider, Golden Route, ColdUpdate y
   los invariantes de sensibilidad vigentes.
8. **Los forks futuros usan el mismo proceso de admisión.** Ningún fork nuevo
   entra por copia ad hoc.

## 3. Evidencia local que fundamenta el diseño

### 3.1 Linaje de producto

- `atlas-ide` contiene el baseline Atlas sobre Void.
- `atlas-ide-forward-port` es un worktree del anterior y su HEAD `34803da`
  contiene el estado Atlas más avanzado: provider nativo, lifecycle del coding
  bridge y tests.
- `atlas-codeoss-1.129.1@8a7abeba` es el baseline que se creó para trasladar
  selectivamente el valor de Void a un Code-OSS actual. El trasplante no llegó a
  iniciarse.
- `atlas-editor-zed@c9e8e611` es un baseline limpio de Zed. No contiene commits
  Atlas; aporta ACP, rendimiento, arquitectura agentic y patrones de producto.
- `architecture/doc0-rc2-20260721-185328@d01d4b9` y su sucesora
  `architecture/doc0-rc2-20260721-185644@3284d61` forman un linaje Git
  desconectado de `main`. Incluyen decisiones y capacidades como ACP, coding
  bridge, media, Home Assistant, checkpoints, nebulosa y canon precursor.
- Los worktrees `self-build-item-*` inspeccionados están mayoritariamente
  contenidos en la historia actual; deben registrarse igualmente para probar la
  cobertura y no asumirla por nombre.

### 3.2 Piezas internas ya existentes

Atlas no parte de cero para revisión y diagnóstico:

- `UniversalVerifier` normaliza evidencia `PASS | FAIL | UNKNOWN`.
- `VerifiedProducer` implementa producir → verificar → retar → reflexionar.
- `ValidationRunner` ejecuta pytest y mypy en aislamiento.
- `RootCauseClassifier` separa causa del diff, causa ambiental y desconocido.
- `SelfAuditRunner` diagnostica y genera candidatos.
- `AdversarialPanel` revisa casos de riesgo.
- `ColdUpdateManager`, Golden Route y Decider gobiernan promoción y aplicación.
- EventBus, Merkle y el service runner aportan correlación y operación 24/7.

El hueco es de integración: existen varios tipos locales de `Finding`, el lazo
verificado no está totalmente conectado al worker vivo y los hallazgos de
ingeniería no forman todavía un canal tipado hacia el Orchestrator y la UI.

## 4. Compilación del linaje

### 4.1 Registro único

Se añadirá `docs/canon/product_lineage_registry.jsonl` y se declarará en
`docs/canon/authority_registry.yaml`. No sustituye los registros de componentes,
decisiones o implementación; enlaza una fuente Git concreta con ellos.

Cada registro de fuente contiene:

- `source_id`
- `path`
- `git_common_dir`
- `branch`
- `head`
- `upstream`
- `license`
- `role`
- `authority`
- `substantial_commits`
- `capabilities`
- `canonical_destinations`
- `disposition`
- `evidence`
- `status`

Estados permitidos:

- `INVENTORIED`
- `SEMANTICALLY_COMPARED`
- `PARTIALLY_ASSIMILATED`
- `FULLY_ASSIMILATED`
- `PINNED_REFERENCE`
- `SUPERSEDED_SOURCE`
- `BLOCKED_BY_LICENSE`
- `BLOCKED_BY_DECISION`

El registro no declara `FULLY_ASSIMILATED` hasta que cada capacidad sustancial
esté vinculada a código, prueba, decisión, parking o supersesión.

### 4.2 Operaciones de asimilación

Cada capacidad recibe exactamente una operación:

| Operación | Uso |
| --- | --- |
| `MOVE` | Código Atlas compatible que puede trasladarse conservando autoría |
| `PORT` | Código válido que debe adaptarse a APIs o estructura actuales |
| `WRAP` | Runtime grande que permanece aislado detrás de un adaptador |
| `CONNECT` | Capacidad consumida por ACP, MCP, HTTP o IPC |
| `PIN` | Baseline conservado por SHA, licencia y procedencia |
| `CLEAN_ROOM` | Comportamiento reconstruido solo cuando no existe reutilización legal y segura |
| `REJECT` | Capacidad incompatible, insegura o sin valor probado |

El `implementation_registry.yaml` guarda el work order; la
`component_reality_matrix.jsonl` guarda el estado real; el registro de linaje
solo demuestra de dónde procede.

### 4.3 Comparación semántica

No se hace cherry-pick ciego de historias desconectadas. Para cada commit o
grupo cohesivo:

1. listar ficheros y comportamiento declarado;
2. localizar equivalentes actuales;
3. comparar API, tests y comportamiento;
4. clasificar `YA_PRESENTE`, `MEJOR_EN_MAIN`, `MEJOR_EN_FUENTE`,
   `COMPLEMENTARIO`, `CONFLICTIVO` o `OBSOLETO`;
5. portar únicamente el delta sustancial ausente;
6. ejecutar tests de equivalencia y registrar la disposición.

## 5. Atlas Workbench

### 5.1 Host

La Workbench se construirá sobre una versión fijada de Code-OSS. La
canalización de VSCodium se usa como referencia para builds libres, eliminación
de telemetría, configuración de producto, branding, update y Open VSX.
VSCodium no se trata como un segundo árbol de editor que deba mezclarse con
Void.

El código Atlas del host se concentra en límites explícitos, preferentemente
`src/vs/workbench/contrib/atlas/**` más los mínimos registros necesarios en el
host. Un informe de blast radius controla cuántos puntos upstream toca cada
port.

### 5.2 Donante Void

`atlas-ide-forward-port@34803da` es la autoridad sobre el delta Void. Sus piezas
se trasladan por grupos:

1. coding bridge y lifecycle;
2. chat y tool-calling;
3. edit/apply/diff;
4. checkpoints;
5. componentes de revisión reutilizables;
6. superficies Atlas necesarias.

Cada grupo debe compilar y pasar contract tests antes del siguiente. No se
arrastra el frontend completo de Void como una segunda aplicación.

### 5.3 Donante Zed

Zed permanece separado cuando su licencia o stack Rust/GPUI harían del
trasplante una dependencia desproporcionada. La preferencia es:

1. usar Atlas como agente ACP en Zed para validar interoperabilidad;
2. convertir capacidades observadas en requisitos y contract tests;
3. reutilizar componentes separados con licencia compatible cuando existan;
4. usar implementación limpia solo si el valor está probado y no hay una
   frontera de protocolo suficiente.

No se copia código GPL dentro de la superficie MIT/Apache sin una decisión
constitucional de licencia.

### 5.4 Superficies iniciales

La primera Workbench muestra únicamente:

- misiones y estado del Orchestrator;
- revisiones y hallazgos;
- incidentes y sesiones de diagnóstico;
- diff y corrección propuesta;
- tests, trazas y runtime health;
- evidencia, receipts y aprobaciones;
- editor convencional para cambios quirúrgicos.

No incluye como trabajo Atlas nuevo:

- autocompletado;
- tab completion;
- una capa propia de IntelliSense;
- edición colaborativa;
- una reescritura de SCM, DAP o Test Explorer;
- pulido estético profundo antes de cerrar el flujo real.

## 6. Plano de revisión y diagnóstico

### 6.1 Contrato `EngineeringFinding`

Se introduce un contrato único y serializable para proyectar hallazgos sin
reemplazar los tipos internos especializados.

Campos mínimos:

- `id`
- `run_id`
- `task_id`
- `repository`
- `base_revision`
- `candidate_revision`
- `source`
- `category`
- `severity`
- `status`
- `summary`
- `detail`
- `locations`
- `evidence`
- `reproduction`
- `suggested_action`
- `patch_ref`
- `dedupe_key`
- `created_at`
- `updated_at`

Severidades:

- `INFO`
- `MINOR`
- `MAJOR`
- `BLOCKING`

Estados:

- `OPEN`
- `ACKNOWLEDGED`
- `FIX_PROPOSED`
- `RESOLVED`
- `DISMISSED`
- `BLOCKED`

El esquema público vive en `schemas/engineering_finding.schema.json`. Los tipos
existentes (`SelfAuditFinding`, findings de seguridad, Evidence, ValidationReport)
entran por adaptadores; no se reescriben.

### 6.2 `EngineeringReviewCoordinator`

El coordinador es composición, no un nuevo verificador. Recibe:

- repositorio;
- base y candidate SHA;
- diff;
- alcance y criterios de aceptación;
- task/mission ID.

Ejecuta de barato a caro:

1. forma y alcance del diff;
2. AST, lint, typing y tests focalizados;
3. seguridad, secretos, dependencias y políticas;
4. grafo estructural y contratos;
5. revisores model-driven solo para huecos no cubiertos;
6. normalización, severidad y deduplicación.

La clave de deduplicación combina repositorio, revisión, regla, ubicación y
mensaje normalizado. Una revisión incremental solo procesa el delta desde la
última revisión aceptada y conserva la resolución de hallazgos anteriores.

### 6.3 `DiagnosticCoordinator`

Ante un fallo:

1. captura comando, salida, entorno no secreto, SHA, diff y correlación;
2. reproduce en worktree aislado;
3. clasifica `INTRODUCED_REGRESSION`, `PRE_EXISTING`, `ENVIRONMENTAL`,
   `OPTIONAL_DEPENDENCY_MISSING`, `RUNTIME_UNAVAILABLE`, `FLAKY` o `UNKNOWN`;
4. consulta grafo, historial y memoria de fallos;
5. genera hipótesis ordenadas por evidencia;
6. permite que `VerifiedProducer` produzca una corrección candidata;
7. valida la corrección;
8. emite un `EngineeringFinding`;
9. propone por ColdUpdate cuando corresponde.

Un diagnóstico que no puede reproducirse queda `UNKNOWN`; no fabrica una causa.

### 6.4 Eventos y Orchestrator

Se añaden dos eventos:

- `engineering.finding`
- `engineering.review_completed`

Reglas:

- `BLOCKING` y `MAJOR` se registran en Merkle y se elevan al Orchestrator.
- `MINOR` e `INFO` quedan visibles y agrupados, sin interrumpir por defecto.
- Un hallazgo puede producir una propuesta, nunca aplicar una.
- Sensibilidad alta conserva HITL o denegación.
- La caída de la UI no pierde el hallazgo: la autoridad es el ledger/runtime de
  Atlas, no el panel.

La UI consume una proyección de solo lectura. Aceptar o aplicar usa las rutas
gobernadas ya existentes, no un endpoint privilegiado nuevo.

## 7. Flujos canónicos

### 7.1 Revisión incremental

```text
commit/worktree candidate
  → diff desde último SHA revisado
  → verificadores deterministas
  → revisión contextual
  → EngineeringFinding[]
  → dedupe/estado previo
  → Orchestrator + Workbench
```

### 7.2 Depuración automática

```text
test/runtime failure
  → captura correlacionada
  → reproducción aislada
  → RootCauseClassifier
  → hipótesis + evidencia
  → VerifiedProducer (opcional)
  → validación
  → finding/propuesta
  → Orchestrator
```

### 7.3 Asimilación de un fork

```text
source@SHA
  → licencia/procedencia
  → inventario de capacidades
  → comparación semántica
  → MOVE | PORT | WRAP | CONNECT | PIN | CLEAN_ROOM | REJECT
  → contract tests
  → estado real y trazabilidad
```

## 8. Seguridad, licencias y fallos

- Código externo es no confiable hasta pasar supply-chain, análisis estático y
  trial gobernado.
- Un port que deja de aplicar por drift upstream falla de forma visible; no
  modifica silenciosamente el host.
- El último baseline compilable queda fijado para rollback.
- Las extensiones usan Open VSX o fuentes cuya licencia permita el uso; no se
  asume acceso legal al Visual Studio Marketplace.
- Los secretos no entran en findings, prompts, logs o UI.
- La Workbench no ejecuta herramientas por fuera de Atlas Core.
- Un bridge ausente degrada la UI a estado no operativo/solo lectura; nunca cae
  a ejecución directa.
- Hallazgos model-driven son hipótesis hasta recibir Evidence.
- Findings rechazados pueden alimentar aprendizaje solo con disposición y
  procedencia; no se convierten automáticamente en reglas.

## 9. Pruebas y aceptación

### 9.1 Linaje

- Todos los worktrees/repositorios Atlas locales aparecen en el registro.
- Cada commit sustancial tiene disposición y destino.
- Historias desconectadas se comparan por contenido y comportamiento.
- `atlas-ide` y `atlas-ide-forward-port` no se importan como duplicados.

### 9.2 Revisión

- Revisión completa e incremental producen resultados deterministas cuando solo
  intervienen verificadores deterministas.
- Un finding resuelto no reaparece sin evidencia nueva.
- Severidad `BLOCKING` alcanza el Orchestrator y Merkle.
- Un revisor caído produce `UNKNOWN`, no `PASS`.
- Ningún finding aplica un patch.

### 9.3 Diagnóstico

- Regresión introducida, fallo preexistente, ambiental y flaky tienen fixtures
  separadas.
- La reproducción ocurre en aislamiento.
- Root cause desconocida permanece desconocida.
- Una corrección propuesta pasa pruebas focalizadas y suite aplicable.
- Fallo de validación bloquea la propuesta.

### 9.4 Workbench

- Compila desde instalación reproducible.
- Abre un repositorio.
- Se conecta a Atlas Core mediante versión negociada.
- Muestra una misión, un finding y una validación reales.
- Permite revisar un diff y solicitar la ruta de aprobación.
- Perder el backend produce degradación honesta.
- Un smoke E2E cubre cambio → revisión → finding → propuesta → aprobación →
  receipt sin autoaplicación.

## 10. Secuencia de entrega

### Corte 0 — cierre del inciso en la candidata actual

1. registrar todos los linajes;
2. comparar capacidades precursoras contra la candidata;
3. corregir canon, matrices y work orders;
4. portar únicamente código Atlas sustancial ausente y seguro;
5. cerrar Sentinel, mypy y la validación pendiente;
6. finalizar la Atlas Definitive Candidate.

El trasplante completo del host no bloquea este corte: queda diseñado,
trazado y ejecutable, pero no se introducen decenas de miles de ficheros en una
candidata que aún no está verde.

### Corte 1 — plano interno de ingeniería

1. contrato `EngineeringFinding`;
2. adaptadores sobre verificadores existentes;
3. ReviewCoordinator y DiagnosticCoordinator;
4. eventos, persistencia y routing al Orchestrator;
5. API de proyección y contract tests.

### Corte 2 — Atlas Workbench

1. host Code-OSS fijado;
2. canalización libre y orientada a privacidad tipo VSCodium;
3. integración amplia y progresiva de las capacidades aprovechables de Void;
4. asimilación ACP y de capacidades/patrones relevantes de Zed;
5. superficies empresariales de revisión, diagnóstico, aprobación y operación;
6. E2E, packaging y ciclo de actualización del producto.

El Corte 2 no queda constitucionalmente limitado a un port «acotado» o a una
demostración mínima. Su ambición es una base de producto completa y profesional.
El alcance exacto, la secuencia interna y qué capacidades se integran, adaptan o
descartan se decidirán al diseñar ese corte; esta decisión solo impide que esa
amplitud bloquee el cierre seguro de la candidata actual.

### Corte 3 — evolución

- reviewers adicionales;
- debugging de runtime distribuido;
- visualización avanzada;
- mejora estética gradual;
- nuevos forks admitidos por el mismo contrato.

## 11. No objetivos de esta decisión

- seleccionar hoy todos los forks futuros;
- copiar interfaces propietarias;
- convertir Zed entero en dependencia;
- declarar Atlas Workbench producto aceptado antes del E2E;
- optimizar la escritura humana de código;
- reemplazar herramientas maduras de Code-OSS;
- relajar ADR-071 para convertir la web experimental en UX final;
- resolver estilo visual definitivo antes del proceso interno.

## 12. Criterio de éxito

La simbiosis está correctamente planteada cuando:

1. todo trabajo precursor sustancial es localizable y tiene disposición;
2. ninguna capacidad se reescribe sin demostrar por qué no puede reutilizarse;
3. Atlas Core conserva todas las autoridades;
4. revisión y diagnóstico alcanzan al Orchestrator mediante evidencia tipada;
5. la Workbench proyecta procesos reales y no estados simulados;
6. cambiar de host futuro no obliga a reconstruir el plano interno;
7. el desarrollo puede continuar desde una arquitectura ordenada sin volver a
   investigar qué quedó abandonado.
