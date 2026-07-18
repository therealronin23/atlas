---
title: "Fusión Void→Atlas IDE — inventario completo para sesión fresca"
status: propuesto
date: 2026-07-18
---

# Fusión Void → Atlas IDE — inventario para la sesión que hace el trabajo real

Este documento es material de referencia, NO una decisión tomada. El operador
pidió el inventario completo hoy (2026-07-18, sesión T2.1) y ejecutar la
fusión de verdad en una sesión fresca, con contexto limpio. Todo lo de abajo
está verificado contra código real — repos clonados, commits reales, líneas
de código reales — no asumido.

## 0. Por qué existe este documento

La sesión de hoy conectó el backend de Atlas a un fork de Void (`~/proyectos/
atlas-ide`) de forma nativa (proveedor `atlas` hardcodeado, sin configuración
manual, proceso arrancado por el propio Electron main). Pero el frontend
sigue siendo el de Void de serie — el operador señaló correctamente que
fusionar el pulido real de Void con la identidad real de Atlas (nebulosa,
Mission Console, gramática de color semántica) es un **estudio de UX
completo**, no un parche de CSS al final de una sesión ya muy larga. Y
además: Void lleva congelado desde agosto 2025 — hay que verificar qué se
perdió de 2026 antes de comprometerse a construir sobre esa base sin más.

## 1. Estado real de las bases candidatas (verificado hoy)

### Void (`~/proyectos/atlas-ide`, github.com/voideditor/void)
- **Congelado desde agosto 2025** ("Void is deprecated... last meaningful
  code change to src/ landed August 4, 2025" — verificado en su propio repo
  y en reseñas de terceros).
- TypeScript/Electron, fork de VS Code. Apache-2.0.
- Arquitectura de IA MUY completa: Fast Apply (streaming search/replace),
  EditCodeService, tool-calling con grammars, ~10.000 líneas de React reales
  (`sidebar-tsx` 3.664, `void-settings-tsx` 1.699, `void-onboarding` 660,
  `void-editor-widgets-tsx` 566, `markdown` 1.116, `void-tooltip` 147,
  `quick-edit-tsx` 173).
- Sistema de theming: `--void-*` (capa fina propia) sobre `--vscode-*`
  (cientos de variables, años de trabajo de Microsoft, temas+accesibilidad
  ya resueltos). Esto es reutilizable sin pelear la arquitectura.
- **Compila limpio en esta máquina** (verificado hoy, tras arreglar
  `npm run buildreact` — paso de build de React que Void documenta pero no
  automatiza en `npm run watch`) y **arranca como ventana real** (Electron,
  verificado con procesos reales, no solo logs).
- YA tiene wired hoy: proveedor `atlas` nativo (sin config manual), backend
  auto-arrancado por Electron main (`atlasBackendMainService.ts`).

### Zed (`~/proyectos/atlas-editor-zed`, github.com/zed-industries/zed)
- **Activamente mantenido** — actualizaciones reales en 2026 (auto-compaction
  de agente `/compact`, gestión de skills movida a settings, **proveedores
  LLM + agentes externos + servidores MCP unificados en un solo panel de
  settings** — patrón de UX más moderno que el de Void, disperso en varias
  pestañas). Sandboxing del terminal/fetch del agente. **ACP con elicitations
  habilitadas por defecto** — Zed habla el MISMO protocolo que el
  `AtlasACPAgent` que se construyó hoy (`src/atlas/acp/server.py`) — Zed
  podría invocar a Atlas como agente YA, sin fork, solo configurando un
  cliente ACP externo.
- Rust/GPUI. GPL-3.0. ~16x menos memoria, 2x arranque más rápido que
  Electron (benchmarks 2026).
- `cargo check -p zed` compila limpio en esta máquina (verificado, 21 min).
- Decisión ya tomada hoy (ver memoria de sesión): Void como base para
  arquitectura de IA (más completa, TypeScript más mantenible con ayuda de
  IA); Zed como referencia de rendimiento, no descartado.

### Lo que ha cambiado en 2026 que Void probablemente NO tiene (barrido real, hoy)
Investigación fresca (no asumida) sobre el estado del arte de editores de IA
en 2026, comparado contra el snapshot congelado de Void (ago-2025):

1. **Autonomía extendida / loops largos**: los agentes en 2026 corren
   minutos-horas, no solo intercambios chat cortos — es el cambio definitorio
   del año. Void (ago-2025) está más cerca del modelo "chat con Apply", no
   del modelo "deja al agente trabajar solo mucho tiempo".
2. **Multi-agente en paralelo** (feb-2026, todos los jugadores grandes lo
   enviaron — Cursor soporta hasta 8 agentes en paralelo). **Atlas YA TIENE
   el equivalente de backend** (`ParallelCoder`, aislamiento por git-worktree,
   confirmado hoy en el barrido Cline/Aider/OpenHands) — falta la SUPERFICIE
   de UI para verlo/dirigirlo, ni en Void ni en Atlas hoy.
3. **Computer Use** (control de escritorio/navegador por el agente,
   feb-2026). Ninguna de las dos bases lo tiene de serie en su UI aunque
   Atlas tiene piezas de esto en el `computer-control-mcp` (Xvfb aislado).
4. **Panel unificado de proveedores+agentes+MCP** (Zed lo hizo en 2026; Void
   sigue con el modelo disperso de pestañas separadas). Relevante para cómo
   se diseñe la superficie de "Settings" de Atlas IDE.
5. **Ventanas de contexto muy grandes** como expectativa base (1M tokens
   citado como ejemplo) — no es una feature de UI, pero cambia qué tipo de
   interacciones son razonables mostrar en pantalla (menos "gestión manual de
   contexto", más "todo el repo cabe").

### Candidatos adicionales de fork detectados en el barrido (no clonados, solo catalogados)
Por si "hace falta forkear más", del mismo barrido: **Trae** (ByteDance, fork
de VS Code, activamente desarrollado, versión standalone lanzada
31-mar-2026 — su CLI companion `Trae-Agent` ya es open source) y **Gram**
(fork de Zed que QUITA la IA — interesante como referencia inversa, no como
candidato). **Windsurf** es "el AI IDE más pulido activo en 2026" según una
fuente, pero es de código CERRADO — no forkeable, descartado por diseño.
Ninguno de estos se ha clonado ni auditado en profundidad todavía — queda
para la sesión fresca decidir si merece la pena.

## 2. Inventario de superficies que Atlas necesita (capa 2 — componentes)

Por cada capacidad real de Atlas (ya construida o ya decidida), qué hace
falta en la UI y si hay un patrón de Void/Zed reutilizable:

| Capacidad Atlas | Estado backend | Patrón reutilizable | Construcción nueva necesaria |
|---|---|---|---|
| Chat / conversación con Atlas | ✅ `coding-bridge` + proveedor `atlas` nativo (hoy) | `sidebar-tsx` de Void (3.664 líneas, chat real) — YA FUNCIONA de fábrica con el proveedor atlas | Solo re-tema (Capa 1), no nueva UI |
| Grafo de dependencias / nebulosa | ✅ real, 4206 nodos, Three.js validado (T2.1 previo) | Ninguno en Void/Zed — ámbos son editores de texto, no visualizadores de grafo 3D | SÍ, componente nuevo — pero se reutiliza el motor Three.js ya construido, se porta a un panel React siguiendo los patrones de Void (mismo nivel de acabado) |
| Mission Console (misiones, aprobación, receipts) | ✅ backend real (`/missions`, ColdUpdateManager) | Ninguno directo — se parece más a un dashboard que a un editor | SÍ, nuevo — inspirarse en `void-settings-tsx` para la estructura de formularios/paneles |
| Integration Fabric (estilo n8n) | 🟡 backend mock-first existente | Ninguno en Void/Zed | SÍ, nuevo — mayor esfuerzo de todos, es un editor visual de flujos |
| Generación imagen/vídeo | ✅ real hoy (`image_gen_tool.py`, `video_gen_tool.py`, fal.ai) | El chat de Void ya renderiza imágenes en mensajes — comprobar si basta o hace falta galería propia | Probablemente reutilizable con extensión menor |
| Casa inteligente | ✅ real hoy (`home_assistant_tool.py`) | Ninguno — necesita UI de control (toggles, sliders) | SÍ, nuevo — pequeño, tipo panel de settings |
| ACP (Atlas como agente invocable) | ✅ real hoy (`src/atlas/acp/server.py`) | Zed YA CONSUME ACP nativamente — probar Atlas desde Zed sin tocar código, solo configurar | Ninguna — es al revés, Atlas se conecta A Zed, no Zed a Atlas |
| Multi-agente en paralelo (visible) | ✅ backend (`ParallelCoder`) | Ninguno de serie en Void/Zed hoy (patrón 2026 muy reciente, aún no en editores forkeables) | SÍ, nuevo — pero backend ya resuelto, "solo" falta visualizarlo |
| Memoria/lecciones (LessonStore, ciclo de vida de hoy) | ✅ real | Ninguno directo | SÍ, nuevo — un browser/timeline de lecciones |
| Auditoría Merkle | ✅ real (todo el repo la usa) | Ninguno | SÍ, nuevo — un visor de log verificable |
| Settings unificado (proveedores+agentes+MCP) | 🟡 parcial (proveedor atlas cableado hoy) | Zed lo resolvió mejor que Void en 2026 — mirar su patrón antes de copiar el de Void sin más | Adaptar, no copiar ciego |

## 3. Lo que la sesión fresca debe decidir (no decidido aquí a propósito)

1. ¿Se ejecuta la Capa 1 (tema) primero como quick win, o se hace el
   rediseño de superficies completo antes de tocar CSS?
2. ¿Se audita Trae en profundidad como tercer candidato de fork, dado que es
   el único de los nuevos que es open source Y activamente desarrollado Y
   fork de VS Code (mismo stack que Void, coste de aprendizaje bajo)?
3. ¿El patrón de settings unificado de Zed (proveedores+agentes+MCP en un
   panel) se adapta dentro de Void, o es una señal de que Zed merece más
   peso del que se le dio hoy?
4. Orden real de construcción de las superficies nuevas (tabla de arriba) —
   probablemente grafo/nebulosa primero (ya validado, solo portar) y
   Integration Fabric al final (el más caro).

## 4. Estado técnico dejado listo hoy (no requiere repetir trabajo)

- `~/proyectos/atlas-ide`: Void compila limpio, proveedor `atlas` nativo
  cableado (`modelCapabilities.ts`, `voidSettingsTypes.ts`,
  `voidSettingsService.ts`, `sendLLMMessage.impl.ts`, `refreshModelService.ts`,
  `sendLLMMessageChannel.ts` — todos los mapas exhaustivos por proveedor
  completados, un bug real preexistente de Void corregido de paso
  — `new Error()` con firma incorrecta en `refreshModelService.ts`).
  `atlasBackendMainService.ts` nuevo: arranca `atlas coding-bridge` como
  hijo del proceso principal de Electron, sin configuración manual.
- `~/proyectos/atlas-editor-zed`: compila limpio, referencia de rendimiento.
- `~/proyectos/atlas-forks/{cline,aider,openhands,vercel-mcp-adapter}`:
  clonados, backend ya auditado (ver `absorption_master_plan.md`) — el
  frontend de Cline (componentes React del webview) sigue sin explorar,
  candidato real para la Capa 2 de este mismo documento.
