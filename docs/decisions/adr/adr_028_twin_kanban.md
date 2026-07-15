# ADR-028 — Puente kanban Atlas→Hermes

- **Estado:** Aceptado; revisado el 2026-07-16
- **Depende de:** ADR-026 y ADR-027

## Contexto

El canal firmado resuelve Hermes→Atlas. Para trabajo saliente y durable Atlas
usa la interfaz kanban del Hermes oficial. Las observaciones de mayo sobre
otras interfaces upstream pertenecen a aquellas versiones y no se proyectan
sobre la versión actual sin volver a investigarla.

## Decisión

`src/atlas/hermes/kanban_bridge.py` invoca `hermes kanban` mediante uno de dos
transportes explícitos:

- `local`: integración local/compatibilidad.
- `ssh`: destino `usuario@host` privado o Tailscale, host key estricta, sin
  contraseña ni interacción, y ejecución remota degradada a usuario `hermes`
  con `HOME=/var/lib/hermes`.

No hay destino por defecto, IP pública hardcodeada ni `/root/.hermes`. El
binario remoto debe ser una ruta absoluta segura; el provisionado usa
`/opt/hermes-agent/.venv/bin/hermes`.

## Frontera

- Acciones permitidas: `boards`, `create`, `list`, `show`, `comment`,
  `complete`, `stats` y `archive`.
- Nunca se usa `shell=True`; los argumentos remotos se forman con quoting
  estándar y se rechazan NULs.
- stdout/stderr se capturan en fichero temporal y se acotan a 1 MiB.
- Cada invocación se registra en Merkle. Títulos, cuerpos y comentarios no se
  copian al ledger: se guarda número de argumentos y SHA-256 para reducir fuga
  de contenido.
- Fallos de transporte levantan excepción para activar degradación; una salida
  no cero vuelve como resultado inspeccionable.

## Estado de verificación

Las formas de los subcomandos usadas por el adapter se contrastaron con el
código fuente fijado de Hermes `0.18.2` y se cubren con runner inyectado. Eso no
equivale a una conexión viva con un VPS. `atlas reality` solo marca el canal
como `configured` si el transporte es válido y, en SSH, existe un destino
privado/Tailscale seguro; nunca lo marca `ready` por variables de entorno.

## Futuro

Otra superficie upstream solo reemplazará este puente si aporta evidencia
mejor de seguridad, durabilidad y operabilidad. La migración deberá mantener
la autoridad de Atlas y una ruta reversible; no se adoptará por novedad.
