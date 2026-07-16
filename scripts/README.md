# Atlas Core — scripts

Este directorio mezcla utilidades operativas permanentes, verificadores y
artefactos históricos. La presencia de un script no demuestra que el servicio
correspondiente esté instalado ni vivo. Antes de operar, consultar:

```bash
PYTHONPATH=src atlas reality --json
```

## Rutas operativas vigentes

| Script | Alcance real |
| --- | --- |
| `install_atlas_systemd.sh` | Instala la unidad local de Atlas. No demuestra que quede sana: verificar después con `atlas reality --run-checks`. |
| `install_hermes_agent_vps.sh` | Provisionador root del Hermes-Agent oficial fijado a una versión y commit auditados. Consume un JSON `0600`, instala usuario dedicado y una unidad endurecida. No ejecuta una inferencia ni envía Telegram. |
| `deploy_hermes_vps_oneshot.sh` | Prepara el JSON mínimo desde `.env` y llama al provisionador mediante una relación SSH/Tailscale ya confiable. Los secretos viajan en fichero `0600`, no por argumentos. |
| `verify_twin_pairing.sh` | Prueba de solo lectura del servicio fijado y del canal firmado Hermes→Atlas. No prueba proveedor ni entrega Telegram. |
| `hermes_skill_atlas_twin/` | Skill canónica de Hermes para `/api/exec/{health,intent,shell,file,browser,audit}`. Restringe el origen a loopback/red privada/Tailscale, desactiva proxy y redirects y acota respuestas. |
| `update-knowledge-graph.sh` | Refresco estructural Graphify de bajo coste y exportación Obsidian/Cypher. |
| `update-knowledge-graph-rag.sh` | Construcción GraphRAG semántica con backend explícito y exportación para Neo4j. |
| `run-graphify-quality-pipeline.sh` | Publicación semántica canónica: full scan serializado, quality gate estricto, limpieza segura de cache y contabilidad local de uso reportado. |
| `graphify_obsidian_export.py` | Export Obsidian transaccional para el `NAME_MAX` real; conserva notas humanas y reemplaza solo derivados Graphify validados. |
| `neo4j-import.sh` | Importa el Cypher generado; requiere credenciales/configuración Neo4j explícitas. |
| `neo4j-rag-query.sh` | Consulta de validación sobre un Neo4j ya importado. |
| `prepare-notebooklm.sh` | Empaqueta informe y documentos para una carga manual a NotebookLM. |
| `token-tracker.sh` | Ledger local de tokens reportados por respuestas; no consulta facturación ni infiere llamadas omitidas. |
| `audit_complete.py` | Recoge evidencia local de auditoría; no sustituye pruebas vivas externas. |
| `twin_e2e_smoke.py` | En modo local verifica el contrato aislado, no el VPS. `--live` reutiliza el cliente twin endurecido contra un Atlas privado/Tailscale. |

El despliegue Hermes requiere valores explícitos en `.env`:

- `VPS_HOST` se pasa al wrapper como variable de proceso y debe ser Tailscale o
  MagicDNS con clave de host SSH ya enrolada.
- `TELEGRAM_BOT_TOKEN` y `TELEGRAM_ALLOWED_USERS` pertenecen a Hermes.
- `HERMES_MODEL_PROVIDER` es `custom:groq` u `openrouter`, con
  `HERMES_MODEL` y la clave del proveedor seleccionado.
- `ATLAS_DASHBOARD_URL` debe ser un origen privado/Tailscale sin credenciales.
- `HERMES_API_KEY` debe contener al menos 32 bytes; el wrapper puede generarla
  y guardarla localmente sin imprimirla.

Después del provisionado, la única afirmación autorizada por
`verify_twin_pairing.sh` es que el binario/servicio y el canal firmado cumplen
sus comprobaciones. Para declarar proveedor o Telegram vivos hacen falta sus
respectivas pruebas reales y actuales.

## Compatibilidad, no despliegue nativo

- `hermes_smoke.py`, `operational_smoke.py` y `hermes_local.sh` ejercitan el
  antiguo contrato REST `HermesRestAdapter`. No verifican el Hermes-Agent
  oficial ni deben usarse como evidencia del twin nativo.
- `hermes_skill_atlas_audit/` es un envoltorio de compatibilidad que delega en
  `hermes_skill_atlas_twin/`; no es una segunda implementación del transporte.

## Retirados de forma fail-closed

`install_hermes_vps.sh`, `reconfigure_hermes_vps.sh` y
`hermes_unlock_skills.sh` terminan con código 64. Se conservan como rutas
reconocibles para que una automatización antigua falle con una explicación en
vez de desplegar como root, modificar configuración sin validación o relajar
permisos.

`graphify-monitor-and-switch.sh` y `graphify-autoremediation.sh` también
terminan con código 64. Mataban procesos por coincidencia global, decidían
proveedores implícitamente y razonaban sobre logs/artefactos acumulados. La
ruta sustituta es una única ejecución deliberada y serializada de
`run-graphify-quality-pipeline.sh --strict`.

Los arreglos puntuales de mayo están en
`scripts/archive/2026-05-hermes-debugging/`. Son evidencia histórica y no deben
re-ejecutarse.

## Grafos

Graphify estructural es la ruta diaria. GraphRAG consume un backend LLM y debe
ejecutarse de forma deliberada. Un fichero exportado no basta: validar después
los conteos y, para Neo4j, ejecutar una consulta real. Si el grafo del proyecto
no coincide con `HEAD`, las consultas estructurales del tronco fallan cerradas
hasta que se regenere en un estado versionado coherente. `graph_overview`
compara además el SHA con el que arrancó el proceso MCP: `SERVER_STALE` exige
reconectar/reiniciar ese servidor aunque la base Kuzu ya esté actualizada.

La ruta semántica comparte `graphify-out/.rebuild.lock` con los hooks. Espera
hasta 900 segundos por defecto (ajustable con `GRAPHIFY_LOCK_TIMEOUT`) y falla
cerrada si no obtiene exclusividad. Graphify 0.9.11 publica solo el delta cuando
encuentra un manifest incremental; por eso el wrapper retira ese manifest de
forma transaccional durante la extracción, fuerza un escaneo completo y lo
restaura si la corrida falla. Antes de extraer toma un snapshot SHA-256 del
corpus detectado y lo repite antes de exportar; cualquier deriva restaura
también el último graph/report/Cypher
publicado. El quality gate cuenta errores por línea
y solo desde el último marcador de corrida: el historial se conserva para el
guard de reincidencia, pero no contamina el veredicto presente. Cada petición
LLM admite un reintento por defecto (`--max-retries` /
`GRAPHIFY_MAX_RETRIES`); así el timeout no se multiplica silenciosamente por
los seis reintentos upstream. En modo `--strict`, cualquier fragmento fallido
o respuesta hueca rechaza por defecto la publicación; solo una excepción
deliberada y cuantificada mediante `--max-failed-chunks` o
`--max-hollow-responses` puede relajar esos límites. Los resultados truncados
marcados como parciales y las advertencias de schema/confidence también
rechazan; sus entradas de cache se purgan solo cuando la atribución es segura.
Además, la transacción captura las claves semánticas antes de extraer: si un
chunk falla después de que otra slice del mismo fichero haya hecho checkpoint,
un fallo/señal/deriva elimina las claves nuevas y preserva el baseline. Una
transacción interrumpida se reconcilia al adquirir de nuevo el lock, de modo que
un fragmento incompleto no puede reaparecer como hit verde.
Una comprobación propia valida IDs de nodos de fichero AST sin el falso positivo
que la heurística upstream produce sobre comandos MCP ubicados en `L1`.
Como `cluster-only` 0.9.11 ignora el `False` de su shrink guard, la ruta solo
fuerza su candidato después de verificar full scan, snapshot estable, IDs y
cobertura exacta de comunidades; strict rechaza aristas sin comunidades.
El informe pasa por
estados `running`, `pipeline_failed`, `quality_threshold_aborted`,
`quality_gate_failed` o `passed`, de modo que un aborto no hereda un verde
anterior. Logs e informe son privados; el modo estricto termina su propio grupo
de procesos en cuanto un umbral ya no puede cumplirse.

El vault Obsidian se reconstruye en un directorio temporal. El adaptador calcula
`PC_NAME_MAX` en el filesystem real, exige al menos una nota por nodo canónico,
preserva notas no generadas y sustituye el vault con rename/rollback. No deja
notas Graphify huérfanas ni acepta symlinks o colisiones con contenido humano.

Graphify 0.9.11 no expone el uso de tokens de las llamadas que renombran
comunidades. Por eso la ruta canónica usa etiquetas deterministas
`--no-label`; sí recoge `input/output` de la extracción semántica y los registra
en `token-tracker.sh` cuando el proveedor de facturación puede resolverse. El
failure guard conserva contadores y propone exclusiones, pero solo modifica
`.graphifyignore` con `--apply-ignore` explícito y rutas relativas seguras. El
cache semántico upstream no está versionado por prompt/modelo: si hay hits, el
quality report marca su procedencia `mixed_or_unverified`; el backend/modelo de
la corrida solo describe los misses extraídos en ella.
