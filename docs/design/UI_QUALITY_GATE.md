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
- La superficie de producto real (nativa, Slint/wgpu o equivalente) queda
  diferida; cuando se construya, este documento es su checklist de
  aceptación obligatoria — `fixtures/ui/ui_quality_gate_results.json` del
  pack es el formato de referencia para automatizar la comprobación.
