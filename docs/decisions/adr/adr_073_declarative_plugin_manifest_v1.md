# ADR-073 — PluginManifest v1 es declarativo, staged y no ejecutable

- **Estado**: aceptado (A2; sin activador runtime por diseño)
- **Fecha**: 2026-07-20
- **Contexto previo**: ADR-063 Gate Engine; ADR-072 escaneo de admisión;
  invariantes 1, 4, 6 y 8 de `AGENTS.md`.

## Contexto

El grafo vivo muestra que `atlas.mcp.installer` sólo alimentaba a
`TrialGate`, y que este no tenía importadores de producción. Aun así, ambos
podían tratar un argv limpio de `npx`/Git como trial positivo, y `execute()`
podía delegar ese argv al runner. Eso no acredita los bytes que descargará un
gestor de paquetes, ni su procedencia, ni una decisión humana; era una falsa
frontera de cadena de suministro.

La investigación de Cline/OpenHands confirmó que cargar plugins o reanudar
referencias remotas mutables antes de una admisión gobernada reproduce justo el
riesgo que Atlas debe evitar. A1 ya aporta evidencia de un árbol local, pero
faltaba un contrato que limite qué clase de plugin puede existir antes de
diseñar un ejecutor completo.

## Decisión

1. `atlas-plugin.json` / `PluginManifest` v1 describe sólo contribuciones
   Markdown declarativas (`skill`, `prompt`, `rule`, `command`). Exige origen,
   revisión y licencia declarados; rechaza campos extra, paths absolutos o con
   escape, tipos ejecutables, permisos y activación distinta de `declarative`.
2. `PluginAdmissionGate` acepta exclusivamente un hijo de un `staging_root`
   explícito y canónico. Rechaza raíces que atraviesen un symlink antes de
   enumerar. Vincula manifest y contribuciones al SHA del `SupplyChainReport`;
   cualquier cambio posterior al escaneo bloquea.
3. Un reporte de supply chain `block`/`partial`/`failed` bloquea el plugin;
   `review` se propaga como revisión humana, sin promoción. El texto Markdown
   declarado pasa el veto estático existente sin interpretarse ni ejecutarse.
4. `TrialGate` puede recibir de forma explícita el gate y un resolver de raíz
   staged. Sólo entonces puede sugerir `candidato → probado-en-jaula` para un
   plugin `admit`. Sin staging, plugins y otros tipos remotos se omiten; un
   argv limpio ya no es una prueba de terceros.
5. `installer.execute()` queda fail-closed para todo efecto de terceros. A2
   no introduce un bypass ni pretende simular aprobación Merkle/HITL.

## Alternativas descartadas

- **Cargar un módulo Python/JS desde el manifest**: descartado. Haría que
  validar el manifest ejecutase código no admitido y heredaría el modelo de
  plugin remoto mutable de los sistemas investigados.
- **Conservar promoción por argv vetado**: descartado. SentinelGate puede
  detectar smuggling conocido, no acreditar contenido descargado o licencia,
  procedencia, scripts de ciclo de vida y cambios posteriores.
- **Añadir ahora un descargador/registrador de plugins**: descartado hasta A3;
  es un efecto externo que necesita staging inmutable, recibo Merkle, broker de
  aprobación y una transición reversible.

## Consecuencias

- Un PluginManifest v1 útil es seguro por ser limitado: no puede aportar
  herramientas, hooks, subagentes ni código ejecutable. Es una capacidad real
  de extensiones declarativas, no una promesa de marketplace arbitrario.
- A3 deberá materializar fuentes en staging sin ejecutar hooks, fijar contenido
  y procedencia, volver a escanear después de toda mutación, registrar la
  decisión/activación en Merkle y exigir aprobación humana donde aplique.
- Hasta A3 no existe consumidor runtime por defecto ni activación de plugin;
  `probado-en-jaula` sigue siendo evidencia de trial, no `verificado` ni
  permiso de instalación.
