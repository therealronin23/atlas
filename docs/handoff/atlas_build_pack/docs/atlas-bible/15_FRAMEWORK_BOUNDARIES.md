# 15 — Framework Boundaries

## Regla principal

Ningún framework externo define Atlas.

## Rol de cada herramienta

```text
LangGraph       = backend opcional para workflows con estado
LangChain       = utilidades, tools, chains, retrieval
CrewAI          = templates de crews/equipos de agentes
AutoGen         = nodo opcional de conversación multiagente
React Flow      = canvas visual del Visual Orchestrator
Cytoscape/Sigma = renderizado de grafos
Tauri           = shell desktop
React           = renderer v1
Monaco          = editor de código
Aider           = adapter de coding
Claude Code     = adapter/harness externo
Codex           = adapter/harness externo
Cursor          = fuente/importación/contexto, no dependencia central
Odysseus        = inspiración workspace/importable, no base de Atlas
```

## Antiacoplamiento

Si mañana una herramienta desaparece, Atlas debe seguir existiendo.
