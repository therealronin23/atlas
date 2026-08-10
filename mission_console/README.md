# Mission Console

UI de misiones de Atlas. Habla con el **Atlas OS Bridge** (ADR-058) en
`127.0.0.1:7341`. Dart/Flutter en exclusiva por ADR-085.

**Nunca usa datos de ejemplo.** Si el bridge no está levantado, la app lo dice y
explica cómo arrancarlo, en vez de pintar una maqueta que no significa nada. Es
el criterio de aceptación de `t7-f3` y la disciplina del resto del repositorio:
evidencia o silencio, nunca decorado. Hay un test que lo fija
(`test/widget_test.dart`).

## Arrancar

```bash
# 1. el runtime, en otra terminal
PYTHONPATH=src .venv/bin/python -m atlas.interfaces.cli os-bridge

# 2. la consola
cd mission_console && flutter run -d linux
```

Otro puerto o un bridge con token, sin recompilar a mano:

```bash
flutter run -d linux \
  --dart-define=ATLAS_BRIDGE=http://127.0.0.1:7341 \
  --dart-define=ATLAS_BRIDGE_TOKEN=...
```

## Qué enseña

| Pantalla | Contra qué |
|---|---|
| Lista + contadores por estado | `GET /missions` — los agregados `by_state`/`by_risk` son los del SERVIDOR, no un recuento del cliente |
| Detalle, evidencia, siguiente acción | `GET /missions/{id}` |
| Aprobar / rechazar | `POST /missions/{id}/approve` · `/reject`, tras confirmación |
| Panel de eventos en vivo | `WS /events` — reenvía los últimos 50 y luego hace streaming |

El filtro arranca en `awaiting_human_approval` a propósito: el 2026-08-10 el
runtime servía **293 misiones** de las que **6** pedían decisión y 203 estaban
rechazadas. Una lista plana entierra las que importan.

## Dos decisiones que conviene no deshacer sin leer esto

**Sin dependencias de terceros.** Sólo `dart:io` y `dart:convert` — ni `http` ni
`web_socket_channel`. El bridge escucha en loopback y habla JSON y WebSocket
planos, que la stdlib cubre. Menos superficie que auditar en un cliente que
maneja aprobaciones de misiones.

**El WebSocket manda cabecera `Origin`, y es obligatorio.**
`_validate_websocket_origin` del bridge cierra con 1008 si falta: es su defensa
contra CSWSH. Un cliente de escritorio no la manda por su cuenta.

Ese detalle apareció **ejecutando la app contra el runtime real**: los tests
pasaban, la lista de misiones cargaba perfecta, y el panel lateral decía "el
bridge cerró el stream de eventos". Contra un mock no habría salido nunca — la
misma lección que este repositorio lleva una semana cobrándose en otros sitios.

## Verificación

```bash
flutter analyze && flutter test
flutter build linux --release
```

Comprobado el 2026-08-10 contra el runtime vivo: 293 misiones, contadores
cuadrando con el bridge, evidencia real de validación en el detalle (`983
passed`, mypy limpio) y 23 eventos llegando por el WebSocket.
