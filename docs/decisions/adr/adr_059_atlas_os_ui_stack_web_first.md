# ADR-059 — Atlas OS UI: web-first (Vite+React+TS), Tauri diferido

- Estado: aceptado (2026-07-10)
- Contexto: el build pack (su ADR-0005) propone Tauri+React desde v1.
  Evidencia local: node v18.19.1 (Vite>5 exige node 20+), rustc 1.95
  presente pero compilar Tauri mete webkit2gtk y presión de RAM/disco en una
  máquina con historial earlyoom y /tmp de 4G. El valor v1 es el shell
  reactivo a eventos con contratos reales, no el empaquetado desktop.

## Decisión

1. **`ui/atlas-shell/` = Vite 5 + React 18 + TypeScript**, sin framework de
   estado externo: event store/reducer/projector propios en
   `src/core/` de la shell (dominio fuera de React, pack ADR-0006 KEEP).
2. **Living Knowledge Graph v1 = SVG + `d3-force`** (micro-dependencia).
   Cytoscape/Sigma/WebGL = INVESTIGATE cuando el grafo real de Kuzu (miles de
   nodos) entre en la UI (digest formal requerido).
3. **Servida como web local**: `vite dev` en desarrollo; build estático
   servible por el bridge (127.0.0.1). Tauri queda como wrapper futuro
   explícitamente compatible (la shell no usa APIs de navegador que Tauri no
   tenga) — se re-evalúa con digest cuando el operador decida desktop.
4. **Dependencias npm mínimas y pineadas**: react, react-dom, d3-force,
   vite, typescript, @vitejs/plugin-react. Nada de UI kits pesados; el
   design system es CSS propio (tokens en variables).

## Consecuencias

- Arranca hoy sin upgrade de node ni toolchain Rust en el camino crítico.
- El coste diferido: empaquetado desktop y APIs nativas quedan para una fase
  posterior con su propia decisión.
- Riesgos OS-R4/OS-R5 en el registro.
