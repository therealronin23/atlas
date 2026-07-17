# T2.1 — La UX real de Atlas: APLICACIONES DEDICADAS multi-plataforma

**Para el driver que lea esto**: plan reformulado ÍNTEGRO el 2026-07-17 por
orden directa del operador. Sustituye todo encuadre anterior de esta ola.

## La intención del operador, literal (NO reinterpretar)

1. *"es una puta mierda, no se parece en nada a lo que yo quiero. es súper
   genérica y se ve que está generada por ia"* — sobre la consola actual.
2. *"buscaba algo definitivo y profesional, pero no sé el que, habría que
   investigar"*.
3. Convivencia: **"donde yo esté, incluido el móvil"**.
4. Carácter: **"cinematográfico (JARVIS, mis 9 mockups)"**.
5. **"quiero que funcione en cualquier plataforma, pero con aplicación
   dedicada comunicada entre ellas, una web no"** — dicho DESPUÉS de que el
   driver defendiera la base web; el operador la descartó explícitamente.

## Decisiones N3 que el operador tomó aquí (registradas, no re-litigar)

- **D11 REABIERTA**: el shell deja de ser "arnés de validación"; la UX real
  se construye por fin.
- **"UI = evolución de la Mission Console (no reescritura)" — decisión
  sellada del plan maestro §4 — QUEDA SUPERSEDED por el operador**
  (2026-07-17): la UX final son aplicaciones dedicadas, no la web actual.
- **ADR-059 ("UI web-first") queda superseded para la UX final** — la ola
  debe formalizarlo en un ADR corto (ADR-071 propuesto) al arrancar.

## Lo que significa (interpretación del driver — confirmar barato al arrancar)

- **"Aplicación dedicada"**: icono propio, se instala, arranca sola, se
  siente nativa. NO una pestaña, NO una PWA, NO "abre el navegador".
- **"Comunicadas entre ellas"**: el mismo Atlas vivo en todas — apruebas una
  misión en el móvil y el escritorio lo refleja al instante. Todas hablan con
  el núcleo Atlas (hoy: el portátil). Fuera de casa: canal privado (el
  proyecto ya conoce Tailscale, ver playbook Hermes) — ley de elasticidad:
  "si delega fuera, privacidad siempre".
- **"Cualquier plataforma"**: mínimo duro = Linux desktop (el portátil del
  operador) + su móvil. PREGUNTA PENDIENTE (una sola, al arrancar): ¿qué
  móvil — Android, iPhone, ambos?
- **Matiz honesto que la investigación debe poner sobre la mesa**: hay stacks
  de "app dedicada" que por dentro renderizan con webview (Tauri) y stacks de
  render 100% nativo (Flutter, Qt). Si la investigación acaba recomendando
  uno con webview, decirlo SIN esconderlo y mostrar que no se siente web —
  el operador rechazó la experiencia-web, y la frontera exacta la marca él
  viendo prototipos, no leyendo specs.

## ~~BLOQUEANTE #1~~ — RESUELTO: la dirección estética YA vive en el repo

El operador depositó los 9 mockups el 2026-07-17 (mismo día):
`docs/design/ui/references/mockup-01..09.{png,jpg}` + destilado textual en
`docs/design/ui/references/DIRECCION_ESTETICA.md` (lenguaje visual, mapa
mockup→backend real, reglas anti-genérico). Caveat del operador: *"falta
pulir muchísimo el ux"* — los mockups dan CARÁCTER, no spec (son concept-art
con pseudo-texto). Lo primero que hace un implementador de UI: MIRAR los 9
mockups; el destilado es para quien no renderice imágenes.

## Investigación OBLIGATORIA antes de elegir stack (el operador la pidió)

Manía investigar-antes-de-decidir: barrer SOTA con enjambre + Cónclave.
Requisitos duros que filtran candidatos (Flutter, Tauri v2, Qt/QML, Kotlin
Multiplatform/Compose, React Native, …):

1. Linux desktop de primera clase + móvil de primera clase.
2. Capacidad cinematográfica REAL: motion 60fps, shaders/efectos, tipografía
   fina, latencia percibida nula. (Aquí Flutter y Qt suelen brillar; medir.)
3. Un solo código para todas las plataformas (economía: el operador no
   programa y el mantenimiento lo harán IAs — dos codebases = deriva doble).
4. Comunicación con el núcleo: el bridge 7341 read-only + ruta dorada para
   aprobar (la aprobación JAMÁS abre el bridge a escritura — N2/Cónclave al
   diseñar ese camino; receipt en Merkle).
5. Sincronía entre dispositivos (estado de misiones en vivo; WebSocket/
   event-stream ya existe en el API server).

**Entregable de la investigación: 2-3 prototipos INSTALABLES** (aunque sean
20 pantallas falsas con motion real) que el operador pueda abrir en SU
portátil y SU móvil y comparar. El operador elige carácter y sensación; el
driver elige tecnología con benchmark, no con opinión (regla de oro: al
operador jamás el CÓMO técnico).

## Qué pasa con lo ya construido

- `ui/atlas-shell/` (1.930 líneas TSX cableadas al API real) **vuelve a su
  rol D11 original: arnés de validación del backend**. No se invierte ni un
  minuto más en su estética. Su valor real: el contrato de datos
  (`src/core/api.ts` — health/graph/events/reality/memoria + WS) es el mapa
  de qué expone ya el núcleo; las apps dedicadas consumirán eso mismo.
- El backend NO cambia por esta ola: API server + eventos ya existen.

## El corte de la ola (evidencia observable, sin cambios)

**El operador aprueba una misión real de la ruta dorada desde una app
dedicada** (idealmente desde el móvil, en el sofá), y el receipt queda en
Merkle. Ni más features ni menos.

## Estándares y economía (sellados, sin cambios)

Doble estándar `frontend-design:frontend-design` (carácter, nada de AI slop)
+ `agent-skills:frontend-ui-engineering` (estados, accesibilidad, responsive).
Implementación Sonnet; criterio/auditoría en el modelo caro. Cónclave para
la elección final de stack (es N2 con coste real de dependencia nueva).

## Después de esta ola

T2.2 Knowledge view (grafo Kuzu navegable) y T2.3 Visual Orchestrator
(ADR-066) — sobre el MISMO stack que salga elegido aquí.
