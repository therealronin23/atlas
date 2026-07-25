# Diseño — Discovery multisource con admisión graduada

## Contexto

El descubrimiento normal solo inyectaba repositorios de GitHub. Eso impedía que
la documentación oficial de proveedores y los registros independientes fueran
material utilizable por Atlas. La solución no puede convertir una lista de URLs
en permisos de ejecución ni volver a crear un catálogo masivo sin evidencia.

## Decisión

`docs/knowledge/curated_sources.yaml` pasa a ser un manifiesto versionado de
editores y fuentes. Cada editor declara los dominios exactos que controla; cada
fuente declara tipo, URL, tema y propósito. El cargador acepta exclusivamente
HTTPS, un editor declarado, y un host exacto del editor. El manifiesto es la
autoridad declarativa de la fuente; la allowlist exacta de `SSRFBridge` es una
segunda frontera independiente y debe contener cada dominio declarado.

El tick descarga únicamente texto limitado desde fuentes que también superen el
`SSRFBridge`; elimina markup y lo deja como hallazgo `official`. Es material de
investigación/knowledge, no un instalador. GitHub sigue aportando candidatos
por búsqueda temática con señal graduada; el registro MCP oficial continúa por
su re-seed estructurado. Un hallazgo oficial no se convierte por sí solo en un
MCP candidato: debe resolverse a un artefacto concreto y pasar el pipeline
existente de dedupe, quality gate, vetting y trial.

## Política graduada

- Fuentes primarias: documentación y registros operados por el editor. Aportan
  conocimiento y corroboración.
- Ecosistema verificable: GitHub, PyPI, npm y crates. Aportan artefactos solo
  con identidad resoluble, licencia/actividad/señal evaluadas por el gate.
- Investigación y seguridad: arXiv, Hugging Face, OSV/NVD/OpenSSF. Aportan
  evidencia o riesgos; nunca habilitan adopción.
- Comunidad/noticias: descubrimiento débil. Solo genera hipótesis que exigen
  corroboración primaria posterior.

No se fija un umbral universal de estrellas o descargas: la calidad se pondera
por procedencia, mantenedor, actividad, licencia, relevancia, duplicación y
resultado de vetting. El LLM puede filtrar relevancia, pero un fallo suyo cierra
la promoción, no la seguridad.

## Fases

`fuente` → `hallazgo` → `candidato` → `vetting` → `probado-en-jaula` →
`verificado`/`instalado`. La última transición sigue siendo HITL para MCPs
remotos conforme a ADR-076. Un rechazo entra al Security Council; el Council
es una segunda opinión y no una autorización para eludir el humano.

## Fuera de alcance

No se descarga ni ejecuta código de terceros, no se modifica
`adopt_mcp_server`, y no se abre subdominios comodín ni red privada.
