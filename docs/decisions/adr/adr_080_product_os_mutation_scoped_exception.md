# ADR-080 — Excepción acotada a la frontera solo-lectura del puente 7341 (ADC-WO-107)

- **Estado**: aceptado (decisión del operador 2026-07-31, evidencia en
  `docs/canon/decision_dossiers/EDR-ADC-WO-107-bridge-mutation-boundary.md`)
- **Fecha**: 2026-07-31
- **Contexto previo**: ADR-058 (Atlas OS Event Kernel Bridge) y ADR-071
  (apps dedicadas) declaran el puente del puerto 7341 una proyección de
  **solo lectura**. Fase 15 (Product OS, 2026-07-10/11) añadió
  `atlas.api.product_routes` sobre la misma app/puerto — Integration
  Fabric, onboarding adaptativo y el ciclo de vida de Business Core — sin
  que ninguna ADR posterior reconciliara esa expansión con la declaración
  de solo-lectura de ADR-058/071. ADC-WO-107 nombró esta contradicción
  como abierta.

## Decisión

Se reconoce **una excepción acotada, no una revocación general**, a la
frontera solo-lectura de ADR-058/071: las rutas de `product_routes.py`
(Fabric, onboarding, Business Core, Gate Engine) permanecen mutantes por
diseño — son la superficie de producto que Fase 15 construyó
deliberadamente, no una desviación accidental. No se retira ni se
convierte a solo-lectura ninguna de esas rutas.

Se corrige, en cambio, el hallazgo concreto que ADC-WO-107 identificó como
más grave que el ya conocido: `business/core/activate` y
`business/core/reject` aprobaban una decisión de negocio gobernada
**en el mismo proceso del bridge**, sin la separación de proceso que
`permissions/pending/{task_id}/approve` usa para invocar a Orchestrator
(`atlas approve` como subproceso, ADR-058). `BusinessCoreEngine` no es
Orchestrator — OS-R1 (nunca doblar Orchestrator en el bridge, riesgo de
corrupción de la cadena Merkle) no aplica literalmente aquí — pero la
altura de auditoría sí debía igualarse: ambas rutas ahora escriben un
receipt Merkle verificable (`business_core.activated`,
`business_core.activation.rejected`) en la MISMA cadena que el resto de
Atlas (`$ATLAS_HOME/memory/audit`), además del audit trail propio que
`BusinessCoreEngine` ya mantenía vía su Gate Engine y el event store OS.

Las 19 rutas mutantes restantes del inventario de ADC-WO-107 (onboarding,
conexiones, drafts, referencias de credenciales) no aprueban una decisión
gobernada en nombre de un humano — crean o actualizan estado de producto
bajo la autenticación real ya exigida por `authenticate_http`. No
presentan el mismo gap y quedan fuera del alcance de esta ADR.

## Evidencia

1. `src/atlas/api/product_routes.py`: 21 rutas POST catalogadas, inventario
   completo en `EDR-ADC-WO-107-bridge-mutation-boundary.md`.
2. `business/core/activate`/`reject` ahora emiten receipt Merkle
   (`tests/test_os_product_api.py::test_business_core_activate_writes_merkle_receipt`,
   `::test_business_core_reject_writes_merkle_receipt`), verificado con
   `AuditRecord.verify()` sobre la cadena real.
3. `permissions/pending/{task_id}/approve` sigue siendo la única ruta que
   requiere separación de proceso completa, porque es la única que toca
   estado propiedad de Orchestrator (OS-R1).

## Consecuencias

- El puente 7341 deja de ser descrito, sin matices, como "solo lectura":
  la descripción correcta es "solo lectura en el núcleo Atlas (missions,
  events, timeline, graph, permissions), mutante y gobernado en la capa
  de Producto (Fase 15)".
- `docs/canon/open_questions.jsonl` (`OPEN-OPERATOR-API-MUTATION-BOUNDARY`)
  y `docs/canon/implementation_registry.yaml` (`ADC-WO-107`) se actualizan
  en consecuencia.
- Cualquier ruta NUEVA que apruebe/rechace una decisión gobernada en
  nombre de un humano debe justificar por qué no necesita el mismo receipt
  Merkle que `activate`/`reject` ganaron aquí, o añadirlo.

## Reversión

Revertir el commit que añade `merkle_dir`/`merkle` a `create_app` y
`register_product_routes` restaura el estado previo (Business Core sigue
funcionando, solo pierde el receipt Merkle — el event store propio no se
toca). No hay migración de datos: `MerkleLogger` es puramente aditivo
sobre una cadena que ya existía.
