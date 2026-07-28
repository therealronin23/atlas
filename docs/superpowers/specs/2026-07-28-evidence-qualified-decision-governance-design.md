# Diseño de gobernanza de decisiones calificadas por evidencia

**Estado:** aprobado por el operador para especificación
**Fecha:** 2026-07-28
**Ámbito:** P00–P12
**No modifica:** `config/governance.json`

## 1. Propósito

Atlas sustituirá el patrón «opción plausible → aprobación del operador» por un
proceso «problema verificable → alternativas comparadas → evidencia →
recomendación → decisión».

El operador conserva la autoridad sobre identidad, apetito de riesgo,
preferencias de producto y cambios constitucionales. El arquitecto de Atlas
asume la responsabilidad de investigar, comparar, medir y recomendar los medios
técnicos. Una preferencia del operador no se utilizará como sustituto de
evidencia técnica, y una comparación técnica no decidirá por sí sola una
cuestión constitucional.

## 2. Alcance

El proceso se aplicará a:

- decisiones nuevas;
- ADR aceptados cuya justificación dependa de supuestos no verificados;
- decisiones históricas recuperadas del corpus;
- elecciones de arquitectura, dependencia, producto, protocolo y operación;
- promoción de investigación o código donante al núcleo;
- decisiones actualmente descritas como aceptadas por conversación.

Los invariantes constitucionales explícitos se revisarán para comprobar
consistencia, aplicabilidad y mecanismos de enforcement, pero no se debilitarán
ni supersederán sin autorización constitucional expresa.

## 3. Principios

1. **Intento y medios son autoridades distintas.** El operador define qué debe
   preservar Atlas; la evidencia determina, en la medida posible, cómo
   materializarlo.
2. **La evidencia local prevalece para el estado actual.** Runtime fresco,
   código, tests y configuración mandan sobre claims históricos.
3. **Las fuentes primarias prevalecen para contratos externos.** Estándares,
   documentación oficial, código upstream y artículos originales preceden a
   resúmenes y comparativas comerciales.
4. **Éxito ajeno no equivale a adecuación local.** Un patrón se adopta solo si
   sus restricciones, escala, coste y modelo de confianza son compatibles con
   Atlas.
5. **Los resultados no comparables se reproducen.** Las cifras obtenidas con
   modelos, datasets, jueces o presupuestos distintos no se ordenan como si
   fueran un benchmark común.
6. **Se busca evidencia refutatoria.** Cada dossier incluye condiciones que
   invalidarían la recomendación.
7. **La ausencia de decisión es visible.** La incertidumbre se clasifica; no se
   oculta con lenguaje concluyente.
8. **La adopción permanece selectiva.** Atlas asimila contratos y capacidades,
   no identidades ni arquitecturas completas por prestigio.

## 4. Estados de decisión

Cada decisión tendrá exactamente uno de estos estados principales:

- `CONSTITUTIONAL`: mandato explícito del operador; requiere ceremonia
  constitucional para cambiar.
- `EVIDENCE_QUALIFIED`: aceptada y respaldada por evidencia suficiente para su
  ámbito actual.
- `PROVISIONAL`: útil para avanzar, pero pendiente de contraste o medición.
- `EXPERIMENT`: autorizada solo para un harness reversible; no es canon de
  producto.
- `REQUIRES_OPERATOR`: la evidencia no resuelve una cuestión constitucional,
  irreversible o de preferencia legítima.
- `BLOCKED`: faltan datos, runtime, secretos o una dependencia previa.
- `REJECTED`: evaluada y descartada con motivo trazable.
- `SUPERSEDED`: reemplazada con alcance y partes preservadas explícitos.

`ACCEPTED` seguirá siendo válido para ADR históricos, pero el registro canónico
deberá indicar si su fundamento está `EVIDENCE_QUALIFIED` o `PROVISIONAL`.

## 5. Dossier mínimo de decisión

Antes de implementar una decisión material se registrará:

```yaml
id:
program:
question:
decision_class:
constitutional_constraints:
current_reality:
alternatives:
  - null_change
  - candidate
primary_sources:
local_evidence:
independent_evidence:
vendor_claims:
comparison_dimensions:
recommendation:
confidence:
known_unknowns:
falsifiers:
revisit_triggers:
security_effect:
privacy_effect:
operational_cost:
dependency_effect:
licensing_effect:
rollback:
operator_decision_required:
status:
```

Las alternativas incluirán siempre no cambiar nada y, cuando sea viable, una
opción incremental. El dossier no asignará puntuaciones numéricas universales:
primero aplicará invariantes como filtros duros y después comparará dimensiones
explícitas. Esto evita precisión ficticia y permite cambiar prioridades sin
reescribir la evidencia.

## 6. Jerarquía de evidencia

Para afirmaciones técnicas se utilizará, en este orden:

1. evidencia fresca del checkout y runtime de Atlas;
2. especificaciones y estándares normativos;
3. documentación y código oficial del sistema comparado;
4. investigación original con metodología inspeccionable;
5. reproducciones independientes;
6. mediciones propias de Atlas;
7. claims de proveedor claramente etiquetados;
8. analogías y opinión experta.

Una fuente inferior puede complementar, pero no contradecir silenciosamente una
fuente superior. Varias copias del mismo texto cuentan como una fuente.

## 7. Flujo de decisión

1. Definir la pregunta y el boundary afectado.
2. Separar restricciones constitucionales de preferencias revisables.
3. Capturar la realidad local y el coste de no actuar.
4. Identificar entre dos y cuatro alternativas, incluida la alternativa nula.
5. Buscar sistemas exitosos y fallidos con problemas comparables.
6. Normalizar las condiciones de comparación.
7. Ejecutar un benchmark o spike local cuando las fuentes no sean comparables.
8. Formular recomendación, confianza, falsificadores y rollback.
9. Someter al operador solo la parte que requiera su autoridad.
10. Registrar la decisión y enlazar ADR, work order, código, tests y runtime.
11. Reabrir automáticamente el dossier cuando se active un `revisit_trigger`.

## 8. Arquitectura de registros

La implantación añadirá una autoridad canónica descubrible:

- `docs/canon/evidence_registry.jsonl`: fuentes externas y evidencia local
  normalizadas;
- `docs/canon/decision_evidence_matrix.jsonl`: enlace entre decisión,
  alternativas, evidencia, confianza y estado;
- `docs/canon/decision_dossiers/`: dossiers legibles y versionados;
- schema bajo `schemas/` para validar los registros;
- comprobación CI de identificadores, referencias, estados y fuentes rotas.

Estos registros complementarán `decision_registry.jsonl`; no crearán una
segunda autoridad de decisiones. El registro de decisiones seguirá siendo el
índice de disposición, y la matriz de evidencia explicará su fundamento.

## 9. Disposiciones técnicas iniciales

La primera auditoría ha encontrado cinco formulaciones que deben permanecer
provisionales hasta que su ADR y sus tests reflejen la recomendación revisada.

### 9.1 Mission, Task y efectos

- Aplicar historial durable solo a Mission, Task, comandos, aprobaciones y
  recibos; no imponer event sourcing a todo Atlas.
- Usar SQLite embebido como límite transaccional local y proyecciones
  reconstruibles.
- Mantener inicialmente el journal de rollback compatible con el SQLite local;
  WAL exigirá una versión libre del defecto de reset documentado upstream y una
  prueba de recuperación.
- Tratar los efectos externos como `at-least-once`: exigir idempotency key,
  consulta de estado o reconciliación. No declarar `exactly-once` fuera del
  límite transaccional controlado.
- Encadenar eventos y recibos con la autoridad Merkle existente.

### 9.2 Plano de consulta y control

- Mantener el puerto 7341 como proyección de consulta compatible.
- Separar el plano de comandos por contrato y autoridad, no necesariamente por
  un segundo puerto TCP.
- Preferir IPC local para el Workbench de escritorio; un transporte remoto
  futuro reutilizará el mismo contrato tras emparejamiento explícito.
- Todo comando incluirá identidad autenticada, `idempotency_key`,
  `expected_version`, sensibilidad, motivo y modo dry-run cuando proceda.
- La admisión persiste intención; un controlador gobernado ejecuta efectos y
  publica estado/recibo. La UI nunca se convierte en autoridad de Task, Policy
  o Memory.

### 9.3 Memory y Knowledge

- Conservar las capas canónicas por caso de uso: memoria durable de registros,
  memoria siempre en contexto e índice semántico especializado.
- Separar mantenimiento/consolidación de memoria del agente primario.
- Permitir promoción low/medium únicamente con procedencia, destilación,
  sensibilidad, reglas de corroboración y evaluación reproducible.
- Mantener los claims extraídos semánticamente como hipótesis hasta su
  verificación.
- Propagar eliminación por lineage: retirar derivados de fuente única y
  recalcular confianza/procedencia de claims corroborados independientemente.

### 9.4 Atlas Engineering Workbench

- Code OSS será el upstream funcional actualizable.
- VSCodium aportará la metodología de compilación, branding soberano,
  desactivación de telemetría y distribución; no se modelará como un segundo
  editor que deba fusionarse.
- Void será una fuente versionada de capacidades AI y UX que se portarán
  selectivamente; su fork completo no será la base mantenida.
- ACP será el contrato preferido para interoperabilidad editor–agente.
- Zed aportará ACP y patrones de interacción. La importación de código requerirá
  revisión de licencia y no contaminará límites incompatibles.
- Atlas Core conservará autoridad; extensiones y hosts serán clientes no
  confiables que proponen comandos.

### 9.5 Revisión, diagnóstico y debugging

- `EngineeringFinding` será el modelo canónico interno, expresivo para
  lifecycle, evidencia, riesgo, ownership y aprobación.
- SARIF 2.1 será el formato de interoperabilidad y baseline para análisis
  estático, con fingerprints estables.
- LSP alimentará diagnósticos de lenguaje; DAP representará sesiones y eventos
  de depuración; OpenTelemetry correlacionará excepciones y trazas runtime.
- Un adaptador no podrá promover automáticamente un hallazgo a hecho, ni un
  hallazgo a corrección. El orquestador triagea; Policy/Gates autorizan efectos.
- El ciclo de vida distinguirá `OPEN`, `ACKNOWLEDGED`, `ACCEPTED_RISK`,
  `FALSE_POSITIVE`, `FIX_PROPOSED`, `FIX_VERIFIED`, `RESOLVED` y `REGRESSED`.

## 10. Auditoría P00–P12

La revisión se ejecutará por dependencias, no por orden editorial:

1. P00, P01 y P09: autoridad, kernel, seguridad y gates.
2. P02 y P03: contexto, Mission/Task y cognition runtime.
3. P04 y P05: memoria, conocimiento e investigación.
4. P06 y P07: Foundry, supply chain, MCP, ACP y plugins.
5. P08 y P11: Workbench, Android y substrate.
6. P10 y P12: distribución, Hermes, Membrane y Osmosis.

Cada lote actualizará disposiciones y producirá work orders ejecutables. Un
programa no bloqueará otro salvo dependencia real.

La implantación se dividirá en especificaciones y planes independientes:

1. registros, schemas y checks de trazabilidad;
2. revisión P00/P01/P09 y boundary durable Mission/Task;
3. revisión P02/P03 y plano de comandos;
4. revisión P04/P05 y promoción Memory/Knowledge;
5. revisión P06/P07 y asimilación/protocolos;
6. revisión P08/P11 y arquitectura del Workbench;
7. revisión P10/P12 y distribución bilateral;
8. harness de evaluación y revalidación periódica.

Solo el primer lote implementa el mecanismo transversal. Cada lote posterior
tendrá spec, plan, tests y commits propios.

## 11. Evidencia inicial

### 11.1 Checkout de Atlas

- `src/atlas/core/contracts.py`
- `src/atlas/core/orchestrator_parts/task_persistence.py`
- `src/atlas/api/server.py`
- `src/atlas/memory/memory_index.py`
- `docs/decisions/adr/adr_057_memory_canonical_by_use_case.md`
- `docs/decisions/adr/adr_058_atlas_os_event_kernel_bridge.md`
- `docs/decisions/adr/adr_069_mission_layer_v0_foundry.md`
- `docs/decisions/adr/adr_071_dedicated_apps_supersede_web_first_ux.md`
- `docs/decisions/adr/adr_078_atlas_workbench_lineage_convergence.md`

### 11.2 Fuentes primarias externas

- [Temporal durable execution](https://docs.temporal.io/)
- [AWS Step Functions workflow types](https://docs.aws.amazon.com/step-functions/latest/dg/choosing-workflow-type.html)
- [Azure Durable Task orchestrations](https://learn.microsoft.com/en-us/azure/durable-task/common/durable-task-orchestrations?tabs=python)
- [Microsoft Event Sourcing pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing)
- [Microsoft CQRS pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs)
- [SQLite atomic commit](https://sqlite.org/atomiccommit.html)
- [SQLite write-ahead logging](https://sqlite.org/wal.html)
- [Kubernetes controllers](https://kubernetes.io/docs/concepts/architecture/controller/)
- [Kubernetes API concepts](https://kubernetes.io/docs/reference/using-api/api-concepts/)
- [W3C PROV-O](https://www.w3.org/TR/prov-o/)
- [Microsoft GraphRAG methods](https://microsoft.github.io/graphrag/index/methods/)
- [LongMemEval](https://arxiv.org/abs/2410.10813)
- [LoCoMo](https://arxiv.org/abs/2402.17753)
- [VSCodium upstream and build model](https://github.com/VSCodium/vscodium)
- [Void maintenance status](https://github.com/voideditor/void)
- [Agent Client Protocol architecture](https://agentclientprotocol.com/get-started/architecture)
- [Zed External Agents](https://zed.dev/docs/ai/external-agents)
- [Zed licensing](https://github.com/zed-industries/zed)
- [OASIS SARIF 2.1](https://docs.oasis-open.org/sarif/sarif/v2.1.0/os/sarif-v2.1.0-os.html)
- [Language Server Protocol](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.18/specification/)
- [Debug Adapter Protocol](https://microsoft.github.io/debug-adapter-protocol/)
- [OpenTelemetry exception conventions](https://opentelemetry.io/docs/specs/semconv/exceptions/exceptions-logs/)

Estas referencias justifican la línea inicial, pero no sustituyen los dossiers
ni los benchmarks de cada decisión.

## 12. Validación

La implementación del proceso será aceptable cuando:

- todos los ADR tengan fundamento clasificado;
- las decisiones conversacionales relevantes estén enlazadas o reclasificadas;
- ningún `EVIDENCE_QUALIFIED` carezca de fuente primaria o evidencia local;
- los claims cuantitativos indiquen metodología y comparabilidad;
- los registros pasen schema validation y controles de referencias;
- todo work order material enlace su dossier;
- CI detecte referencias rotas, estados ilegales y evidencia ausente;
- los benchmarks registren versión, dataset, modelo, configuración y semilla
  cuando aplique;
- `config/governance.json` permanezca intacto.

## 13. Rollback

La gobernanza nueva es documental y aditiva. Puede revertirse eliminando los
registros y checks introducidos por sus commits sin migrar datos de runtime.
Las decisiones técnicas resultantes conservarán rollback propio. Revertir el
framework no convertirá automáticamente decisiones provisionales en
evidence-qualified.

## 14. Fuera de alcance

Este diseño no:

- aprueba por sí mismo dependencias nuevas;
- cambia los invariantes constitucionales;
- implementa todavía Mission/Task, el control plane o el Workbench;
- declara fiables benchmarks de proveedores sin reproducción;
- convierte investigación externa en canon;
- autoriza código GPL dentro de componentes con distribución incompatible.
