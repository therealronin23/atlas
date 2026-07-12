# atlas-shell — arnés de validación (no la UX final de Atlas)

Este shell (Vite + React + TS, ADR-059) existe para conducir y verificar en
un navegador real el Backend Bridge (`atlas os-bridge`, 127.0.0.1:7341):
eventos, timeline, grafo de fixture, conectores mock, gates y — desde
Fase 15 — Integration Fabric y Business Core.

## Qué es

- Panel de pruebas visual para endpoints/WS/fixtures durante el desarrollo.
- Verificación de que el bridge funciona de extremo a extremo con un
  navegador real conduciéndolo (no solo tests).

## Qué NO es

Según `atlas_product_os_liquid_ui_pack_v1` (`tasks/DO_NOT_DO.md`,
`context/WHAT_WE_REJECT_FROM_FABLE.md`) y ADR-060/061:

- No es la interfaz final de Atlas.
- No es un HUD "Jarvis"; no se pule visualmente como producto terminado.
- El grafo SVG+d3-force no es la identidad visual de Atlas — es una
  proyección de depuración del grafo real.

La superficie de producto real (Cognitive Surface nativa, candidatas
Slint/wgpu) queda diferida a una fase posterior con su propia decisión.
Ver `docs/design/UI_QUALITY_GATE.md` para el criterio de aceptación que
esa superficie SÍ deberá pasar quen se construya.

## Cómo arrancarlo

```bash
cd ~/proyectos/atlas-core && source .venv/bin/activate
PYTHONPATH=src atlas os-bridge            # terminal 1 (127.0.0.1:7341)
cd ui/atlas-shell && npm run dev          # terminal 2 (127.0.0.1:5173)
```
