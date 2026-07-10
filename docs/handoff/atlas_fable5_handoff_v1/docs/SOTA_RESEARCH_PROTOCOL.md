# Atlas OS — SOTA Research Protocol

## Cuándo investigar

Investigar en internet cuando haya duda sobre:

- API real de un producto.
- Licencia de un repo.
- Estado actual de un framework.
- Seguridad de una integración.
- Papers recientes.
- Buenas prácticas de UX.
- Riesgos legales/ToS.
- Protocolos como MCP, A2A, AG-UI.
- Productos como OpenHands, NotebookLM, Claude Code, Cursor, n8n, etc.

## Fuentes preferidas

1. Documentación oficial.
2. Repos oficiales.
3. Papers/arXiv.
4. Issues/PRs relevantes.
5. Blogs técnicos de los autores.
6. Noticias reputadas solo para contexto.

## Output obligatorio

Guardar en:

```text
docs/research/YYYY-MM-DD_topic.md
```

Con esta estructura:

```text
# Topic
Date:
Question:
Sources:
Findings:
Atlas implications:
Risks:
Decision:
Follow-up tickets:
```

## Regla de superioridad

Toda fuente externa se procesa así:

```text
SOURCE → PRIMITIVE → LIMITATION → ATLAS REINTERPRETATION → SUPERIORITY TEST → IMPLEMENTATION PATH
```
