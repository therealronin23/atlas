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
| `neo4j-import.sh` | Importa el Cypher generado; requiere credenciales/configuración Neo4j explícitas. |
| `neo4j-rag-query.sh` | Consulta de validación sobre un Neo4j ya importado. |
| `prepare-notebooklm.sh` | Empaqueta informe y documentos para una carga manual a NotebookLM. |
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

Los arreglos puntuales de mayo están en
`scripts/archive/2026-05-hermes-debugging/`. Son evidencia histórica y no deben
re-ejecutarse.

## Grafos

Graphify estructural es la ruta diaria. GraphRAG consume un backend LLM y debe
ejecutarse de forma deliberada. Un fichero exportado no basta: validar después
los conteos y, para Neo4j, ejecutar una consulta real. Si el grafo del proyecto
no coincide con `HEAD`, las consultas estructurales del tronco fallan cerradas
hasta que se regenere en un estado versionado coherente.
