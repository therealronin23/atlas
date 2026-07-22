# PluginManifest v1 — extensiones declarativas staged

- Estado: A2 construido y conectado opcionalmente a `TrialGate`; sin activador
  runtime ni materializador remoto por defecto.
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
   red implícita después de fijar revisión/contenido.
2. Reescaneo tras materializar y tras cualquier validación que toque bytes.
3. Recibo Merkle que ligue `record_id`, manifest, procedencia y decisión; broker
   de aprobación humana para `review` o sensibilidad alta.
4. Activador reversible que consuma sólo ese recibo, aplique contribuciones
   declarativas y permita revocar/borrar staging sin tocar el árbol principal.
5. Los tipos ejecutables requieren un ADR posterior con sandbox/AST Guard y no
   entran como extensión de este contrato.
