# 13 — Graph Rendering Strategy

## Principio

No existe un único layout para todo Atlas. Cada territorio usa el layout que mejor representa su significado.

## Layouts

```text
Living Knowledge Graph   → force-directed / physics
Execution Pipeline       → hierarchical / Sugiyama / DAG
Research Map             → tree + radial clusters
Memory Vault             → semantic clusters
Audit Timeline           → linear + Merkle branches
Visual Orchestrator      → manual DAG / React Flow style
Coding Dependency View   → dependency graph + blast radius
```

## Living Knowledge Graph

Nodos principales:

```text
User
Memory
Tools
Processes
Artifacts
Runtime/Kernel
Projects
Connected Accounts
```

Comportamiento:

```text
- Reposo: pulso lento
- Pensamiento: conexiones cyan activas
- Aprendizaje: nodo nuevo o conexión más gruesa
- Error: nodo rojo o temblor
- Validación: flash verde
- Aprobación: halo ámbar
```

## Escalabilidad

```text
- Clustering por tipo y proyecto
- Level of detail por zoom
- Ocultar nodos fríos
- Mostrar procedencia bajo demanda
- Layout determinista cuando sea necesario
```

## Herramientas posibles

```text
React Flow    = Visual Orchestrator
Cytoscape.js  = grafos grandes y analíticos
Sigma.js      = grafos explorables
D3/WebGL      = visualizaciones custom
Monaco        = Coding Territory
```
