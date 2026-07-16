# MEMORY

Lecciones operativas que explican el porqué de las reglas vivas. El estado vive en
`WORK_LEDGER.md`; los detalles de diseño viven en `docs/design/`.

- `absorb-without-cloning`: Atlas asimila capacidades externas de Cursor, Codex,
  Claude Code, MemGPT/MemPalace u otros sistemas sin convertirse en un fork ni
  aceptar su techo.
- `dependency-floor-honesty`: los bumps de floor aceptados en `pyproject.toml`
  se documentan como compatibilidad existente, no como dependencias nuevas.
- `adversarial-audit-no-assumptions`: ante una auditoría amplia, investigar lo
  dudoso, usar grafos y evidencia viva, corregir dentro del alcance y separar
  siempre “configurado”, “probado en aislamiento” y “verificado en vivo”.
- `graph-rebuild-single-writer`: una extracción GraphRAG larga debe compartir
  el lock del hook estructural, rechazar si el árbol deriva antes de exportar y
  juzgar calidad solo con el tramo de log de su corrida actual; el timeout por
  petición debe combinarse con un número explícito y acotado de reintentos. Un
  grafo fresco no vuelve fresco al proceso MCP: su SHA de arranque también debe
  coincidir o la conexión se reinicia. Calidad estricta significa cero chunks
  fallidos y cero respuestas huecas salvo excepción explícita y cuantificada.
- `semantic-full-scan-before-publish`: en Graphify 0.9.11, `extract` incremental
  puede publicar solo el delta y amputar el grafo. La ruta semántica retira el
  manifest de forma transaccional para forzar detección completa, conserva el
  anterior ante fallo y no publica si faltan manifest, export o quality gate.
  Un resultado truncado/parcial nunca se conserva como hit futuro: se rechaza y
  se purga su entrada de cache cuando puede atribuirse con seguridad. Como
  Graphify checkpointa por chunk pero cachea por fichero, la transacción guarda
  las claves previas y elimina todas las nacidas durante un fallo/interrupción;
  “alguna slice produjo datos” no demuestra completitud del fichero. Un shrink
  de clustering solo se fuerza tras demostrar full scan, snapshot estable, IDs
  canónicos y cobertura comunitaria exacta; el mensaje de éxito upstream no es
  evidencia suficiente.
- `semantic-coverage-human-owned`: un error o una respuesta del LLM puede
  generar una candidatura de exclusión, nunca editar `.graphifyignore` por
  defecto. Los monitores no matan procesos por coincidencia global ni cambian
  de proveedor de forma implícita.
- `filesystem-limits-are-runtime-facts`: no asumir `NAME_MAX=255` ni que un
  export incremental limpia derivados. Obsidian se construye en un directorio
  temporal con el límite real, conserva notas humanas, valida cobertura y hace
  swap atómico; un export parcial no reemplaza el vault vivo.
- `cost-ledger-is-not-billing`: un contador local solo acredita llamadas que
  registraron uso real devuelto por el proveedor. Cero registros no significa
  cero consumo; presupuestos desconocidos se muestran como desconocidos y las
  etiquetas derivables no justifican llamadas LLM sin contabilidad.
  Un cache semántico sin identidad de prompt/modelo se declara mixto o no
  verificable; sirve para descubrir hipótesis, no para probar estructura.
- `live-evidence-must-replace-placeholders`: si un diagnóstico ejecuta checks,
  debe proyectar su resultado en todos los resúmenes derivados antes de calcular
  el estado global; conservar `unknown` tras medir es una contradicción, no una
  cautela.
- `local-agent-config-is-secret-by-default`: configuraciones de clientes de
  agentes pueden mezclar credenciales, rutas absolutas y permisos amplios. Solo
  se versionan adaptadores/hook portables; el config real se ignora, se restringe
  a 0600 y cualquier credencial expuesta se rota fuera del repo.
- `distill-private-sources-before-graphing`: un export conversacional bruto puede
  tener valor histórico y a la vez filtrar URLs firmadas, duplicar decisiones
  descartadas y degradar GraphRAG. Se conserva privado; solo la destilación
  verificable entra en Git y en el grafo semántico.
- `tracked-surface-requires-ci`: si una superficie versionada tiene su propio
  lock/build, la suite Python no la representa. Su runtime mínimo, instalación
  exacta, auditoría de dependencias y build deben estar declarados y ejecutarse
  en CI.
