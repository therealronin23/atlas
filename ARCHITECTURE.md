# Architecture — Atlas Definitive Candidate

## Convenciones

Este documento usa tres vistas:

- **CURRENT**: lo demostrado en el checkout base
  `c95038c9d7e97ddc6339f38abe6dad09b166f47d` y en observaciones frescas del
  2026-07-27.
- **TARGET**: la arquitectura que debe tener Atlas según operador,
  invariantes y ADR aceptados.
- **TRANSITION**: los boundaries y gates que permiten llegar al objetivo sin
  fingir que ya existe.

`CODE_PRESENT`, `TESTED`, `WIRED`, `RUNTIME_CONFIGURED`, `LIVE_VERIFIED` y
`PRODUCT_ACCEPTED` son estados distintos. La matriz exacta está en
`docs/canon/component_reality_matrix.jsonl`.

## Arquitectura de autoridad

Atlas separa autoridad de conveniencia:

| Autoridad | Dueño | No puede delegarse por accidente |
|---|---|---|
| Identidad e invariantes | Constitución distribuida de ADR-067 | a un modelo, plugin, UI o documento derivado |
| Decisión de producto/constitucional | Operador | a código ya existente o investigación |
| PolicyDecision | Policy/Decider bajo contratos constitucionales | al proveedor que propone la acción |
| Task/Mission durable | boundary pendiente de decisión del operador | a MCP, UI, Hermes o memoria |
| Ejecución | Runtime/executors tras Policy y gates | al planificador o protocolo |
| Memoria por uso | autoridades de ADR-057 hasta decisión final | a un grafo semántico único |
| Evidencia | Merkle/receipts y verificadores | a la misma pieza que produce el claim |
| Estructura actual | grafo estructural fresco + checkout | a GraphRAG o documentación histórica |
| Aceptación | operador | al constructor de la candidata |

## CURRENT

### Capas presentes

1. **Institutional/Governance**
   - `AGENTS.md`, ADRs, PolicyEngine, GateEngine, Decider, Sentinel, Reality y
     evidencia Merkle existen.
   - La autoridad documental sigue distribuida; antes de esta candidata no
     había un registro máquina único.
   - Los tres Deciders soportados tratan sensibilidad alta de forma
     conservadora. El seam de inyección necesitaba un guard constitucional
     común; esta candidata lo endurece sin tocar `governance.json`.

2. **Trunk y Context**
   - El grafo Kuzu/AST, sus chequeos de frescura y el Trunk MCP están
     implementados y probados.
   - El grafo base fue observado `FRESH` en el commit exacto, con 289 módulos
     y 741 aristas de importación. Los cambios de la candidata obligan a
     refrescarlo antes de volver a llamarlo fresco.
   - `.cursor/mcp.json` y el runtime local muestran configuración MCP; eso no
     prueba handshake vivo del worktree candidato.

3. **Cognition y Mission**
   - InferenceHub, Orchestrator, TaskPersistence, proveedores reemplazables y
     el loop agéntico están presentes y probados.
   - Mission/Golden Route/Foundry v0 están wired. Golden Route cubre una ruta
     acotada de construcción y aprobación; no es todavía un producto de
     autoconstrucción general.
   - El dueño final del estado Task y el boundary Mission→Task siguen
     reservados al operador.

4. **Memory y Knowledge**
   - SQLite memory index, BlockMemory, vector stores, distillation, tenancy,
     cifrado, temporalidad y crypto-shred tienen código y pruebas.
   - Gate D estaba configurado en el proceso original. Esa observación no
     prueba cada motor ni el candidato.
   - Knowledge missions, verifier, base, research e ingest están wired; se
     observaron ticks fechados en el runtime original.
   - No existe aún una garantía integral que obligue a destilar memoria
     privada antes de toda publicación a un grafo compartible. Es contrato
     objetivo, no claim implementado.

5. **Self-Build**
   - SelfBuildRunner, Foundry, ColdUpdate, código generativo, worktrees,
     validación y receipts existen.
   - El preflight fresco observó un self-build bloqueado, no una construcción
     exitosa. Auto-apply sigue restringido y opt-in.

6. **Integración**
   - Integration Fabric, ACP, MCP Registry/Trunk, supply-chain scanner,
     PluginManifest local, admission, materialización, recibos y activación
     están presentes y probados.
   - El scanner produce evidencia, no permiso.
   - ADR-076 A/B están implementados como ticks opt-in para stage1/stage2
     acotado, no para las etapas 3–6 completas. En el proceso observado
     reseed estaba apagado y vetting encendido.
   - ADR-076 C está rechazado. No hay un camino soportado de auto-adopción
     remota ejecutable; el histórico `MaintenanceAdopter` no puede convertir
     un `high` en permiso bajo los Deciders soportados.

7. **Security, Operations y Recovery**
   - aislamiento por capas, AST Guard, Authorization, GateEngine, supply-chain
     checks, ShadowRouter, DriftTripwire, Security Council, health, doctor,
     audit, snapshots y rollback tienen implementaciones reales con distinto
     grado de wiring.
   - Gate D y Security Council estaban configurados en el proceso original.
     No se observó una acción gateada fresca que demuestre el flujo completo.
   - ADR-077 no encola universalmente `Task.AWAITING_APPROVAL`; unblock es una
     ceremonia explícita y auditada, pero la identidad humana no está
     criptográficamente demostrada por el string `actor`.

8. **Product OS**
   - `ui/atlas-shell` es un arnés React. El backend ofrece fixtures/simulación
     para `/graph` y `/intent`.
   - NebulaGraph es la vista usada; LivingGraph existe pero no tiene
     importadores. El snapshot público no incluye commit, fecha ni esquema.
   - Universal Bar declara pipeline simulado v1.
   - El bridge 7341 tiene POST mutantes pese al boundary read-only de
     ADR-058/071. Es código real pero autoridad `CONTRADICTED`; la transición
     no puede normalizarlo sin la decisión `ADC-WO-107`.
   - Mission Console proyecta estado real acotado; no es dueño de Mission.
   - ADR-078 acepta Atlas Engineering Workbench como primer producto y
     CodeOSS/VSCodium como línea host de escritorio. Esa decisión no importa
     todavía código de producto ni convierte un repositorio externo en core.
   - Void es fuente de capacidades/prototipos y Zed es donante ACP/de patrones;
     ambos requieren extracción trazable, adaptación y contratos Atlas.
   - Presence Engine, Liquid UI y la proyección Android son objetivo, no
     renderer final.

9. **Hermes y nodos**
   - Hermes Kanban/atlas-twin tiene código, tests y wiring; el REST legado fue
     retirado.
   - El preflight fresco vio mock/no configurado/no live. Heartbeats y
     despliegues anteriores son historia.
   - NodeIdentity está probado pero sin transporte/control-plane productivo.
   - ACP está probado y expuesto por CLI; no quedó un transporte real vivo.

10. **Substrate y Membrane**
    - Hosted Linux es el sustrato operativo.
    - Native (seL4/Genode/NT/WASM) es investigación bloqueada por Wave 5.
    - Membrane/Osmosis conserva su vocabulario y corpus. ADR-074 promueve una
      fase de OSM-042; no convierte el programa completo en enforcement.

### Runtime observado

El 2026-07-27, sobre el checkout original:

- `atlas reality --json`, `atlas audit --verify`, `atlas doctor` y
  `atlas health` terminaron con código 0;
- Merkle verificó 10.012 registros;
- el grafo estructural base estaba fresco;
- el navegador y Chromium estaban disponibles;
- MCP tenía dos servidores habilitados en configuración, sin prueba viva;
- Hermes estaba en mock/no configurado;
- no había proveedores externos en el entorno del comando;
- el proceso original tenía Gate D, research, project graph, self-build,
  vetting MCP y Security Council configurados; reseed y cold auto-apply
  estaban apagados.

Una variable en `/proc` prueba configuración del proceso, no comportamiento
integrado ni aceptación de producto. Tras editar el worktree, estas
observaciones siguen siendo evidencia del **baseline**, no del commit final.

## TARGET

### Capas objetivo

```text
┌──────────────────────────────────────────────────────────────┐
│ Product OS: Prime, Linux/Android apps, Liquid Workbenches   │
│ Intención · explicación · aprobación · observación           │
└──────────────────────────────┬───────────────────────────────┘
                               │ Atlas APIs
┌──────────────────────────────▼───────────────────────────────┐
│ Institutional Kernel: identidad, capacidades, Policy, gates │
│ Mission/Task authority · contracts · human authority         │
└─────────────┬────────────────┬────────────────┬───────────────┘
              │                │                │
┌─────────────▼──────┐ ┌──────▼────────┐ ┌─────▼─────────────┐
│ Trunk + Context    │ │ Cognition      │ │ Memory/Knowledge │
│ structural graph  │ │ models/agents  │ │ continuity/truth │
│ bounded packets   │ │ plans/reviews  │ │ provenance       │
└─────────────┬──────┘ └──────┬────────┘ └─────┬─────────────┘
              └────────────────┼────────────────┘
                               │ proposed action
┌──────────────────────────────▼───────────────────────────────┐
│ Security + Runtime + Recovery                               │
│ authorization · isolation · execution · receipts · rollback │
└─────────────┬───────────────────────────────┬────────────────┘
              │                               │
┌─────────────▼────────────┐       ┌──────────▼───────────────┐
│ MCP/ACP/A2A/integrations │       │ Hermes/federated nodes   │
│ gateways, never owners   │       │ proposals, scoped leases │
└─────────────┬────────────┘       └──────────┬───────────────┘
              └───────────────────────────────┘
                               │
                   Hosted substrate first
                   Native only after Wave 5

Evidence, Reality, evaluation and bilateral audit cross every layer.
Foundry builds isolated candidates alongside this flow.
```

### Interfaces y boundaries

| Boundary | Entrada | Salida | Autoridad y fallo |
|---|---|---|---|
| Product→Mission | intención, contexto visible | Mission propuesta | UI no escribe verdad durable por su cuenta |
| Trunk→Cognition | `ContextPacket` acotado y reproducible | contexto para plan/review | grafo fresco; fuentes y sensibilidad explícitas |
| Cognition→Policy | acción tipada, riesgo, descriptor, artefacto | Allow/Deny/RequiresHuman | el modelo no concede permisos |
| Policy→Runtime | decisión final + capability lease | invocación acotada | high nunca se convierte en Allow autónomo |
| Runtime→Evidence | resultado, error, timeout, rollback | receipt/Merkle/event | todo efecto queda atribuible |
| Memory→Knowledge | memoria clasificada y destilada | claim con procedencia | datos privados no se copian directamente |
| Research→Admission | fuente, licencia, scan, ensayo | candidato aceptable o rechazo | research nunca activa |
| Protocol→Core | petición autenticada y normalizada | API Atlas | MCP/ACP/A2A no poseen Task/Policy/Memory |
| Hermes→Atlas | propuesta y contexto del par | decisión Atlas | sin expansión implícita de permisos |
| Foundry→Promotion | candidato, diff, pruebas, riesgos | decisión independiente | proposer no se auto-promociona |
| Membrane→Core | hallazgo bilateral verificable | propuesta/ADR o señal | investigación no se vuelve enforcement sola |

### Modelos y agentes

- InferenceHub selecciona proveedores locales o externos por capacidad,
  sensibilidad, coste, disponibilidad y modo térmico.
- Los proveedores son sustituibles; no almacenan autoridad durable.
- Orchestrator coordina, pero el objetivo es reducir mezcla de autoridad:
  Task, Policy, Runtime y Evidence tendrán dueños explícitos.
- Un agente propone y usa capabilities acotadas. No adquiere herramientas por
  texto, no cambia política y no se concede leases.
- Deliberation Council queda para decisiones irreversibles/ADR; Security
  Council hace triaje por acción. Ninguno rebaja rule 4.

### Memoria y conocimiento

- ADR-057 sigue rigiendo por caso de uso hasta una decisión final.
- El target separa memoria operativa, memoria de bloques, índices vectoriales,
  grafo estructural, grafo semántico, vault y Evidence.
- Toda promoción registra fuente, claim, tiempo, sensibilidad, transformación,
  confianza, contradicciones y política de borrado.
- Kuzu estructural y GraphRAG semántico no se mezclan: uno demuestra
  estructura; el otro ayuda a formular hipótesis.

### Seguridad, observabilidad y recuperación

- autorización estructural post-veredicto para invariantes que ningún Decider
  puede anular;
- capability leases con alcance, TTL, revocación y audiencia;
- sandbox por riesgo, no un wrapper nominal;
- secretos bajo autoridad dedicada;
- evaluación antes de promoción y shadow antes de tráfico;
- Reality agrega evidencia sin presentar `overall=ok` como “todo está vivo”;
- Merkle, receipts, logs estructurados y métricas enlazan misión→decisión→efecto;
- snapshots, rollback y modo seguro no dependen del modelo que falló.

### Producto, despliegue y nodos

- ADR-071 fija apps dedicadas Linux/Android. ADR-078 refina desktop: Atlas
  Engineering Workbench usa una línea CodeOSS/VSCodium como host, asimila
  capacidades de Void y patrones/ACP de Zed, y mantiene Atlas Core como única
  autoridad.
- Android continúa como proyección dedicada obligatoria, pero no comparte por
  decreto el host desktop: se diseñará cuando Surface API y Workbench contracts
  sean estables.
- Hosted Linux entrega primero el Product OS y los servicios.
- Los nodos anuncian identidad y capacidades firmadas; la federación usa
  leases y revocación.
- Native solo empieza cuando se demuestre una limitación de Hosted y se
  aprueben amenaza, recursos, portabilidad, migración y rollback.

## TRANSITION

### Secuencia

1. **Cerrar autoridad y evidencia**: registros, estados atómicos, CI canónico,
   claims corregidos y guard constitucional.
2. **Fijar ownership**: decisiones del operador sobre Mission/Task, memoria,
   y enforcement Osmosis.
3. **Consolidar contratos**: APIs y schemas explícitos entre Institutional
   Kernel, Trunk, Cognition, Runtime, Memory y Evidence.
4. **Corte 1, plano interno**: construir `EngineeringFinding`, revisión de
   código y diagnóstico automático que alimenten al orquestador.
5. **Corte 2, Workbench integral**: mover y adaptar capacidades CodeOSS,
   VSCodium y Void, sumar los contratos/patrones útiles de Zed y construir los
   puentes Atlas. El alcance se diseñará como conjunto completo y cohesivo, no
   como un slice mínimo por defecto.
6. **Proyección Android**: diseñar y construir una superficie dedicada sobre
   contratos estabilizados, sin fingir que el host desktop la resuelve.
7. **Distribución verificada**: pairing Hermes/nodos con credenciales y
   autoridad del operador.
8. **Evaluar Native**: solo tras gates de Wave 5; no por calendario.

### Compatibilidad y migración

- No se reescribe historia ni se cambia `governance.json`.
- Las APIs actuales permanecen hasta que un ADR defina sustitución y
  compatibilidad.
- Los stores conservan autoridades de ADR-057; no hay migración automática
  entre memoria y conocimiento.
- `atlas-shell` sigue disponible como arnés durante la construcción del
  Workbench y no se convierte en su base de autoridad.
- Los repositorios CodeOSS/VSCodium, Void y Zed son fuentes versionadas: toda
  asimilación conserva procedencia, licencia, adaptación y rollback.
- MCP remoto ejecutable sigue scan→vetting→trial→Decider/HITL→receipt.
- El adaptador mock de Hermes permanece como degradación segura.

### Gates de transición

- autoridad fuente y supersesión explícitas;
- graph/blast radius fresco o limitación declarada;
- tests focalizados, suite completa y mypy;
- AST Guard y supply-chain cuando aplique;
- no regresión de high sensitivity;
- evaluación adversarial independiente;
- rollback ensayable;
- evidencia runtime fechada para cualquier `LIVE_VERIFIED`;
- aceptación explícita del operador para cambios constitucionales,
  producto final, pairing externo, Osmosis no-bypass y Wave 5.

El orden operativo, los work orders y las decisiones pendientes están en
`PLAN.md`; los criterios permanentes por programa están en `PROGRAMS.md`.
