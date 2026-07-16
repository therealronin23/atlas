# ADR-059 — Atlas OS UI: web-first (Vite+React+TS), Tauri diferido

- Estado: aceptado (2026-07-10), enmendado (2026-07-16)
- Contexto original: el build pack (su ADR-0005) proponía Tauri+React desde
  v1. La máquina tenía Node 18.19.1, por lo que Vite 5 permitía entregar el
  shell reactivo sin introducir el upgrade de Node ni la presión de compilar
  Tauri/webkit2gtk en una máquina con historial earlyoom y `/tmp` de 4G.
- Evidencia de la enmienda: el host usa Node 22.22.2; el lock de Vite 5
  acumulaba 13 avisos npm aplicables (1 alto, 10 moderados, 2 bajos), mientras
  que Vite 7.3.6 + `@vitejs/plugin-react` 5.1.4 produce build limpio y
  `npm audit` sin vulnerabilidades. Mantener Vite 5 ya no reduce complejidad:
  conserva deuda y deja la superficie JS fuera de CI.

## Decisión

1. **`ui/atlas-shell/` = Vite 7 + React 18 + TypeScript**, sin framework de
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
5. **Toolchain reproducible**: Node 22.22.2 se fija en `.node-version`, el
   contrato rechaza Node anterior a 22.12.0 y npm queda declarado en
   `packageManager`. CI ejecuta instalación exacta, auditoría y build.

## Consecuencias

- Node 22 pasa a ser requisito explícito solo para el shell; el runtime Python
  de Atlas y el toolchain Rust siguen desacoplados.
- El lock npm y el build dejan de depender de verificación manual local.
- El coste diferido: empaquetado desktop y APIs nativas quedan para una fase
  posterior con su propia decisión.
- OS-R4 queda cerrado; OS-R5 continúa abierto porque Tauri sigue diferido y la
  presión de recursos del host no desaparece con el upgrade.
