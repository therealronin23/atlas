# ADR-071 — La UX final de Atlas son APLICACIONES DEDICADAS multi-plataforma (supersede ADR-059 para la UX)

- **Estado**: aceptado (decisión N3 del OPERADOR, 2026-07-17, verbal y
  registrada íntegra en el plan `docs/superpowers/plans/2026-07-17-t21-mission-console-viva.md`)
- **Fecha**: 2026-07-17
- **Contexto previo**: ADR-059 (UI web-first Vite+React, Tauri diferido),
  decisión sellada del plan maestro §4 ("UI = evolución de la Mission
  Console"), D11 (shell = arnés de validación).

## Decisión (del operador, literal — no re-litigar)

1. La UX real de Atlas se construye como **aplicaciones dedicadas** en cada
   plataforma: *"quiero que funcione en cualquier plataforma, pero con
   aplicación dedicada comunicada entre ellas, una web no"*. Dicho DESPUÉS de
   que el driver defendiera la base web; el operador la descartó
   explícitamente.
2. Plataformas mínimas duras: **Linux desktop (el portátil del operador) +
   Android** (respuesta del operador 2026-07-17 a la única pregunta pendiente
   del plan: su móvil es Android).
3. Carácter: **cinematográfico** — los 9 mockups del operador
   (`docs/design/ui/references/`) + `DIRECCION_ESTETICA.md` son la referencia
   de carácter (no spec al píxel).
4. La consola web actual la rechazó el operador: *"es una puta mierda… súper
   genérica y se ve que está generada por ia"*.

## Qué queda superseded y qué NO

- **ADR-059 queda superseded PARA LA UX FINAL**: la web deja de ser el
  destino. NO queda derogado como arnés: `ui/atlas-shell/` **vuelve a su rol
  D11 original** (arnés de validación del backend); no se invierte ni un
  minuto más en su estética. Su contrato de datos (`src/core/api.ts` —
  health/graph/events/reality/memoria + WS) es el mapa de lo que el núcleo ya
  expone y las apps dedicadas consumirán.
- La decisión "UI = evolución de la Mission Console" del plan maestro §4
  queda **superseded por el operador** (2026-07-17).
- **El backend NO cambia** por esta ola: API server 7341 read-only + eventos
  ya existen. La ruta de aprobación desde app dedicada JAMÁS abre el bridge a
  escritura (diseño N2/Cónclave aparte; receipt en Merkle).

## Restricciones que hereda la elección de stack (investigación obligatoria)

1. Linux desktop + Android de primera clase, **un solo código** (el operador
   no programa; el mantenimiento lo harán IAs — dos codebases = deriva doble).
2. Capacidad cinematográfica real: motion 60fps, shaders/efectos, tipografía
   fina, latencia percibida nula.
3. Honestidad de render: si el stack elegido usa webview por dentro (p.ej.
   Tauri), decirlo SIN esconderlo y demostrar con prototipo que no se siente
   web — la frontera la marca el operador viendo prototipos instalados.
4. Viabilidad de build en ESTA máquina (historial earlyoom, `/tmp` 4G —
   advertencia ya registrada en ADR-059 sobre compilar webkit2gtk).
5. Elección final de stack: benchmark + Cónclave (N2, dependencia nueva), no
   opinión. Entregable previo: 2-3 prototipos INSTALABLES comparables por el
   operador en su portátil y su Android.

## Consecuencias

- T2.2 (Knowledge view Kuzu) y T2.3 (Visual Orchestrator, ADR-066) se
  construirán sobre el stack que salga elegido aquí.
- El corte de la ola T2.1: el operador aprueba una misión real de la ruta
  dorada desde una app dedicada (idealmente el móvil) y el receipt queda en
  Merkle.
