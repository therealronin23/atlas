# 14 — Tech Stack Decisions

## Decisión base

```text
Frontend Shell v1: Tauri + React + TypeScript
Graph/Canvas: React Flow + Cytoscape/Sigma según territorio
Editor: Monaco
Backend Bridge: FastAPI/WebSocket
Core: Python existente de Atlas
Future Renderer: sustituible
```

## Por qué no Slint como primera opción

Slint/Rust puede ser interesante como renderer nativo futuro, pero ahora reduce velocidad para construir grafos complejos, editor, visual builder, paneles ricos y ecosistema UI.

## Por qué no Electron

Electron funciona, pero Tauri encaja mejor con soberanía local, peso bajo y bridge con backend local.

## Por qué no LangGraph como kernel

LangGraph puede ejecutar ciertos workflows, pero el kernel de Atlas debe ser propio y basado en eventos.

## Por qué React Flow solo para Orchestrator

React Flow es bueno para canvas manual tipo workflow. El Living Knowledge Graph necesita comportamiento más orgánico y escalable; puede usar Cytoscape, Sigma o custom WebGL.

## Regla final

Elegimos stack para construir, no para definir la identidad.
