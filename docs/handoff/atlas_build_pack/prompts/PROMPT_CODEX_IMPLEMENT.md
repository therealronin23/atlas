# Prompt para Codex / agente de programación

Objetivo: implementar los contratos y shell base de Atlas OS.

Lee los docs en `docs/atlas-bible/`. Implementa incrementalmente. Mantén tests y validación.

Primero crea validadores para:

```text
schemas/event.schema.json
schemas/node.schema.json
schemas/edge.schema.json
schemas/adapter.schema.json
```

Después crea un reproductor de eventos JSONL.

Después crea UI shell que consume esos eventos.

No reescribas backend core. Añade bridge mínimo.

Cada commit debe indicar qué Gate satisface.
