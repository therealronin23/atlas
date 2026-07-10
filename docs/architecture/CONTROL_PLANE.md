# CONTROL_PLANE — Atlas OS UI de gobierno

Dónde el usuario gobierna lo que Atlas puede tocar. En `ui/atlas-shell`
(ADR-059), navegación izquierda, sección "Control Plane".

## Construido (v1)

| Sección | Estado | Efecto real |
| --- | --- | --- |
| Integration Fabric | ✅ | conectores del bridge; test/sync emiten eventos |
| Permissions Matrix | ✅ | gates + probador del evaluador fail-closed en vivo |
| Security Center | ✅ | aprobaciones pendientes + actividad governance |
| Personalización | ✅ | tema/densidad/animaciones (CSS real), confirmación pre-intent, riesgo mínimo del timeline, ocultar simulados — persistido en localStorage |

## Regla de diseño (master prompt §10)

**Cada configuración debe afectar de verdad** a permisos, eventos, memoria,
acciones o representación. Si una setting no puede cablearse a un efecto
observable, NO se añade (nada de settings decorativas). Este criterio está
testeado socialmente: el probador de permisos y los filtros del timeline son
comportamiento, no chrome.

## Pendiente (por fase futura, con este mismo criterio)

Accounts & Identity (necesita conectores reales), Notification Router,
Automation Rules (necesita reglas ejecutables), Model & Provider Router
(la autoridad es InferenceHub — solo representación), Backup/Export,
Developer Console ampliada (ya existe Event Inspector).
