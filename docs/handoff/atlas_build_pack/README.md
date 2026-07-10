# Atlas OS Build Pack

Este paquete convierte la investigación del chat en una base ejecutable para construir Atlas OS como producto final-compatible, no como prototipo desechable.

## Cómo usarlo

1. Copia `docs/atlas-bible/` al repositorio de Atlas.
2. Copia `schemas/` y `fixtures/` a la raíz del repo.
3. Entrega `prompts/PROMPT_FABLE5_ATLAS_BUILD.md` al agente constructor.
4. No empieces por pantallas sueltas. Empieza por validar:
   - `schemas/event.schema.json`
   - `schemas/node.schema.json`
   - `fixtures/events/demo_first_run.jsonl`
   - `fixtures/graph/initial_graph.json`

## Orden de construcción

```text
Constitución
↓
Event Canon
↓
Graph Schema
↓
Reality Simulator
↓
Frontend Shell final-compatible
↓
Backend Bridge
↓
Connected Accounts
↓
Visual Orchestrator
↓
Territories
↓
Hardening
```

## Principio central

Atlas no es un chat, no es un clon de Cursor, no es un clon de n8n y no es un dashboard. Atlas es un entorno operativo cognitivo donde conocimiento, memoria, ejecución, herramientas, usuario y auditoría se representan como estado vivo.
