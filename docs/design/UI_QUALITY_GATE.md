# UI Quality Gate (Fase 15)

Fuente: `docs/handoff/atlas_product_os_liquid_ui_pack_v1/design/UI_QUALITY_GATE.md`,
adoptado como criterio real de aceptación para cualquier superficie de
producto de Atlas (no solo la nativa futura).

## Rechazar una UI si

- parece dashboard/SaaS card-soup;
- parece un "Jarvis barato" (HUD decorativo sin estado real detrás);
- parece plantilla de React genérica;
- los nodos/elementos no tienen significado (decoración pura);
- el movimiento es decorativo, no comunica estado;
- no muestra objetivo activo, sector, estado, riesgo, evidencia, inspector,
  timeline o Gate cuando la acción es peligrosa;
- la paleta de comandos permite saltarse permisos;
- el móvil es el escritorio comprimido sin adaptación;
- falta soporte de `prefers-reduced-motion`.

## Cada pantalla debe poder responder

1. ¿Dónde estoy?
2. ¿Qué objetivo está activo?
3. ¿Qué está haciendo Atlas ahora mismo?
4. ¿Qué datos está usando?
5. ¿Qué riesgo existe?
6. ¿Qué acción puede pasar después?
7. ¿Puedo simular/pausar/cancelar/rechazar?
8. ¿Puedo ver evidencia y auditoría?

## Aplicación en este repo (2026-07-10)

- **`ui/atlas-shell/` es un arnés de validación**, no la UX final de Atlas
  (ver `ui/atlas-shell/README.md`). No se aplica este gate como criterio de
  aceptación de producto sobre el shell; se usa solo para no romper su
  utilidad como panel de pruebas de endpoints/eventos/conectores.
- La superficie de producto real (nativa — Flutter, Compose Multiplatform o
  Qt6/QML, ver `DECISION_STACK_T21.md`; la mención previa a "Slint/wgpu" en
  esta línea quedó superada por la medición real de T2.1, ninguno de los
  tres candidatos evaluados es Slint) queda diferida; cuando se construya,
  este documento es su checklist de aceptación obligatoria.

## Esquema real de `ui_quality_gate_results.json` (2026-07-30)

El fixture del pack (`fixtures/ui/ui_quality_gate_results.json`) es un
placeholder de demo de 2 líneas (`{"passed": false, "reason": "demo
fixture..."}`), sin desglose por pregunta. Esquema real, con un archivo
por pantalla evaluada, junto al propio prototipo/pantalla:

```json
{
  "screen": "<id de la pantalla o del ítem de backlog>",
  "stack": "<flutter|compose|qt|...>",
  "evaluated_at": "<ISO 8601>",
  "passed": <bool — true solo si las 8 preguntas están respondidas Y ningún ítem de rechazo aplica>,
  "reason": "<una frase, el motivo del passed/failed>",
  "questions": {
    "donde_estoy": {"answered": <bool>, "detail": "<por qué sí/no>"},
    "objetivo_activo": {"answered": <bool>, "detail": "..."},
    "accion_actual": {"answered": <bool>, "detail": "..."},
    "datos_usados": {"answered": <bool>, "detail": "..."},
    "riesgo": {"answered": <bool>, "detail": "..."},
    "accion_siguiente": {"answered": <bool>, "detail": "..."},
    "control_usuario": {"answered": <bool>, "detail": "..."},
    "evidencia_auditoria": {"answered": <bool>, "detail": "..."}
  },
  "rejection_checklist": {
    "dashboard_card_soup": <bool>,
    "jarvis_barato_hud_decorativo": <bool>,
    "plantilla_generica": <bool>,
    "nodos_sin_significado": <bool>,
    "movimiento_decorativo": <bool>,
    "paleta_comandos_salta_permisos": <bool>,
    "movil_sin_adaptar": <bool | "not_applicable">,
    "falta_reduced_motion": <bool>
  }
}
```

Un `true` en cualquier ítem de `rejection_checklist` significa "este
problema SÍ está presente" (coincide con el rechazo) — no es un check que
pasa, es una alarma que se dispara.

**Aplicado por primera vez a los tres micro-PoCs de T2.1** (2026-07-30,
`prototypes/atlas_ui/{flutter,compose,qt}_micropoc/ui_quality_gate_results.json`):
los tres dan `passed: false` — **por diseño, no por defecto de calidad**.
Los micro-PoCs son bancos de pruebas técnicos de una sola pantalla (glow +
partículas + fps + WS), nunca se propusieron como pantallas de producto:
no hay objetivo activo, riesgo, Gate, evidencia ni control de
usuario porque ninguno de esos conceptos existe todavía en el bridge que
consumen. El glow y las partículas SÍ disparan
`jarvis_barato_hud_decorativo` y `movimiento_decorativo` con honestidad —
son decoración pura, medida así a propósito (el objetivo de esa sesión era
fps/RAM/GPU, no UX). Los tres resultados son idénticos entre sí porque los
tres implementan la MISMA pantalla de referencia — este gate no
diferencia entre candidatos en esta ronda, queda probado y listo para
aplicarse de verdad cuando se construyan las ~20 pantallas de producto
sobre el stack que gane el Cónclave final.
