# 18 — Acceptance Criteria

## Demo mínima real

Debe poder grabarse un vídeo de 60-90 segundos:

1. Abrir Atlas.
2. Ver Living Knowledge Graph.
3. Escribir una intención en Universal Bar.
4. Ver intent.created.
5. Ver Execution Pipeline.
6. Ver eventos en Timeline.
7. Ver cambios en el grafo.
8. Abrir un nodo de memoria/proceso/artefacto.
9. Ver audit.logged.
10. Ver Reality Status.

## Criterios técnicos

```text
- Todos los eventos validan contra event.schema.json.
- Todos los nodos validan contra node.schema.json.
- La UI puede alternar entre simulator y backend real.
- El renderer no contiene lógica de negocio.
- El chat no es home.
- Visual Orchestrator no es home.
- Existe al menos un flujo real conectado a Atlas Core.
```

## Criterios de identidad

```text
- La UI no parece un clon de Cursor.
- La UI no parece un clon de n8n.
- La UI no parece un dashboard de métricas.
- El usuario entiende qué está haciendo Atlas.
- El usuario puede intervenir en pasos relevantes.
```
