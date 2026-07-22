# PluginManifest v1 — extensiones declarativas staged

- Estado: A2 construido y conectado opcionalmente a `TrialGate`. A3.1
  construido y cableado (2026-07-22): materializador de fuente LOCAL
  (`atlas.mcp.plugin_materializer`, CLI `atlas plugin materialize`) con
  procedencia medida (tree-hash antes/después de copiar, sidecar fuera del
  árbol) y re-escaneo post-copia vía el gate A2. A3.2 construido y cableado
  (2026-07-22): `atlas.mcp.plugin_receipt_broker.PluginReceiptBroker`, sobre
  `Orchestrator.plugin_receipts()` (mismo Merkle/decisor que el resto del
  sistema — sin camino especial para plugins). A3.3 construido y cableado
  (2026-07-22): `atlas.mcp.plugin_activator.PluginActivator` sobre
  `Orchestrator.plugin_activator()` — aplica contribuciones vía symlink
  (fuente única, nunca copia bytes) y revoca/borra staging. **Camino A
  (ADR-072/073) cerrado de punta a punta para fuente LOCAL.** Fuentes
  remotas y tipos ejecutables (condición 5) siguen sin existir por diseño.
  **Consumidor real (2026-07-22, mismo día)**: `SkillStore` extendido
  (`plugins_active_root` opcional, kw-only, `None` = comportamiento idéntico
  al de siempre) para descubrir `<active_root>/<plugin_id>/skill/*.md` bajo
  el namespace `plugin:<plugin_id>/<contribution_id>` — anti-colisión con
  skills nativos del mismo nombre, sirve el DESTINO del symlink (fuente
  única, igual que el resto de la cadena). Cableado en producción en
  `trunk_server.py` (mismo patrón `ATLAS_HOME` que `adopted_servers_path()`
  y ~15 sitios más del repo). `get_skill`/`list_skills` ven plugins
  activados EN VIVO (llaman al store en cada invocación); el registro de
  cada skill como MCP `Prompt` nativo sigue baked-in al arranque del
  servidor (propiedad preexistente del bucle de registro, no nueva: un
  fichero nuevo en `docs/skills/` tampoco aparece como Prompt sin reiniciar)
  — un plugin activado necesita un reinicio del tronco para aparecer en el
  descubrimiento de Prompts, no para `get_skill`/`list_skills`. Prove-it en
  vivo: reconstruí el `SkillStore` EXACTAMENTE como `trunk_server.py` (mismo
  `ATLAS_HOME`), activé un plugin real y `list_skills()`/`get()` lo sirvieron
  sin ningún cambio de proceso. `prompt`/`rule`/`command` se siguen
  aplicando mecánicamente sin que nada los lea — sin consumidor propio
  todavía, honesto.
- Autoridad: [ADR-073](../decisions/adr/adr_073_declarative_plugin_manifest_v1.md).

## Contrato mínimo

Cada árbol staged admite un único `atlas-plugin.json` estricto:

```json
{
  "schema_version": "1.0",
  "plugin_id": "demo-plugin",
  "display_name": "Demo plugin",
  "version": "1.0.0",
  "source": {
    "origin": "local://staging/demo-plugin",
    "revision": "pinned-revision-or-content-id",
    "license": "Apache-2.0"
  },
  "activation": "declarative",
  "permissions": [],
  "contributions": [
    {"contribution_id": "demo-skill", "kind": "skill", "path": "skills/demo.md"}
  ]
}
```

Sólo se aceptan `skill`, `prompt`, `rule` y `command`, todos como Markdown
relativo dentro del árbol. No hay entrypoint de Python/JS, hooks, herramientas,
subagentes, permisos ni red en v1. `schemas/plugin_manifest.schema.json` y
`PluginManifest` rechazan campos extra tanto en raíz como en anidados.

## Flujo A2

```text
raíz staged explícita
  → comprobar containment canónico / sin symlinks
  → SupplyChainScanner (terminal y acotado)
  → validar atlas-plugin.json + hashes observados
  → vetar cada contribución Markdown sin ejecutarla
  → admit | review | block
  → TrialGate opcional: sólo admit sugiere probado-en-jaula
```

`record_id` pertenece al árbol observado; `manifest_sha256` y hashes de cada
contribución se comparan de nuevo antes de devolver admisión. Un contenido
cambiado, una contribución no escaneada o una ruta que atraviesa un enlace
simbólico bloquean. `review` no se promociona automáticamente.

## Límites deliberados

- A2 no descarga, clona, instala ni activa un plugin.
- `TrialGate` sin `plugin_admission_gate` y `plugin_root_resolver` omite el
  plugin; un `npx`, URL o Git limpio no cuenta como trial.
- `installer.execute()` bloquea efectos de terceros aunque el argv pase
  SentinelGate. La admisión no es una autorización de ejecución.
- El manifest declara procedencia, pero A2 todavía no verifica firma, lockfile,
  CVE, revisión remota ni autenticidad de la fuente.

## A3 — condiciones antes de activación

1. Materializador explícito a un directorio nuevo bajo staging, sin hooks ni
   red implícita después de fijar revisión/contenido. — HECHO para fuente
   LOCAL (2026-07-22, `plugin_materializer.py`; sin red/subprocess por
   construcción, test lo fija). Fetchers remotos: ADR posterior.
2. Reescaneo tras materializar y tras cualquier validación que toque bytes.
   — HECHO para el flujo del materializador (admisión ligada al árbol staged).
3. Recibo Merkle que ligue `record_id`, manifest, procedencia y decisión; broker
   de aprobación humana para `review` o sensibilidad alta. — HECHO
   (2026-07-22, `plugin_receipt_broker.py`): NO reinventa HITL — un veredicto
   `review` de A2 se traduce a `sensitivity="high"` sobre el `Decider`
   protocol ya existente (ADR-040). `HumanDecider` lo suspende siempre
   (`pending_approval`, resuelto por `atlas plugin receipt approve/decline`,
   fuera del seam — mismo patrón que `atlas update approve`);
   `AutonomousDecider` lo deniega siempre (invariante 2, regla constitucional
   #4) — un `review` nunca se promueve solo porque nadie miró, bajo ningún
   modo de decisor. Un `admit` emite recibo `issued` de inmediato bajo
   cualquier decisor (emitir un recibo no otorga capacidad: `mutating=False`,
   la activación real de A3.3 consultará el decisor de nuevo con su propio
   `mutating=True`). Un `block` nunca llega al broker: `request()` rechaza
   explícito.
4. Activador reversible que consuma sólo ese recibo, aplique contribuciones
   declarativas y permita revocar/borrar staging sin tocar el árbol principal.
   — HECHO (2026-07-22, `plugin_activator.py`): re-verifica `tree_sha256` Y
   `manifest_sha256` del recibo contra el árbol staged EN CADA punto de
   confianza (`activate()` y de nuevo en `approve_activation()` — dos
   ventanas TOCTOU distintas), nunca confía en el recibo como cheque en
   blanco. Aplica cada contribución como symlink dentro de
   `<workspace>/plugins/active/<plugin_id>/<kind>/<contribution_id>.md`
   (fuente única, igual que `SkillStore`: nunca copia bytes). Activar
   consulta el `Decider` de nuevo (`mutating=True, requires_approval=True`,
   propio de `approve_activation()`/`revoke()` — NO reutiliza el veredicto
   del recibo: un `admit`/aprobación de A2 fue evidencia, nunca permiso de
   instalación). `revoke()` NO consulta al decisor (retirar capacidad no
   necesita permiso) y por defecto borra staging (`--keep-staging` para no
   hacerlo); nunca toca nada fuera de `active_root`/`staged_root`
   (verificado con un canario en los tests).
5. Los tipos ejecutables requieren un ADR posterior con sandbox/AST Guard y no
   entran como extensión de este contrato.
