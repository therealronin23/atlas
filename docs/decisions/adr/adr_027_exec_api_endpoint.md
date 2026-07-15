# ADR-027 — Canal firmado `/api/exec/*` para Hermes

- **Estado:** Aceptado; revisado el 2026-07-16
- **Depende de:** ADR-020 (capacidades), ADR-026 (twin)

## Contexto

Hermes necesita pedir acciones a Atlas sin obtener acceso directo al proceso,
al workspace o a un shell general. La frontera debe autenticar cada petición,
impedir replay y reutilizar la autorización y auditoría de Atlas.

## Decisión

El dashboard puede montar estas rutas `POST`:

| Ruta | Función |
| --- | --- |
| `/api/exec/health` | Comprueba el estado de Atlas mediante el mismo canal firmado. El cuerpo exacto es `{}`. |
| `/api/exec/intent` | Entrega una intención al orquestador. |
| `/api/exec/shell` | Ejecuta comando y argumentos permitidos por Atlas. |
| `/api/exec/file` | Lee o escribe un fichero dentro de las fronteras autorizadas. |
| `/api/exec/browser` | `navigate`, `extract` o `screenshot` mediante el browser controlado. |
| `/api/exec/audit` | Añade a la cadena de Atlas un recibo de una acción originada en Hermes. |

No existe una ruta `/computer` ni acciones browser `click/type` en este
contrato actual.

## Autenticación y replay

Cada petición incluye:

- `X-Hermes-Timestamp`: fecha ISO-8601 con zona, dentro de 300 segundos.
- `X-Hermes-Nonce`: 16–128 caracteres seguros y no usados previamente.
- `X-Hermes-Signature`: HMAC-SHA256 hexadecimal de
  `timestamp + "\n" + nonce + "\n" + cuerpo_exacto`.

`HERMES_API_KEY` debe contener al menos 32 bytes. Un secreto ausente o débil
produce 503. Los nonces aceptados se reclaman atómicamente en SQLite dentro del
workspace, con fichero `0600`; repetir uno produce 401 aunque la firma sea
válida. Firma y comparación son sobre los bytes recibidos, no sobre JSON
re-serializado.

## Autorización y auditoría

Autenticarse no concede una capacidad. Cada acción pasa por los componentes de
permisos, aprobación, contención y ejecución de Atlas. Éxitos, fallos y
rechazos se registran en Merkle; el identificador de clave es un prefijo del
hash del secreto, nunca el secreto.

`/audit` fuerza `agent=hermes_vps` y prefijo `hermes.` para no confundir un
recibo externo con una acción nativa. El recibo afirma que Hermes reportó una
acción; no demuestra por sí solo que el efecto externo ocurriera.

## Cliente canónico

`scripts/hermes_skill_atlas_twin/atlas_twin.py` es la única implementación
Hermes-side autorizada. Es stdlib-only y:

- acepta solo orígenes loopback, privados o Tailscale sin credenciales/ruta;
- ignora proxies ambientales y rechaza redirects;
- limita timeout, tamaño de respuesta y escritura;
- lee `.env` como datos desde fichero regular no-symlink y sin permisos de
  grupo/otros;
- solo permite el conjunto fijo de endpoints anterior.

La skill `atlas-audit` histórica delega en este cliente; no mantiene otro
transporte.

## Límites

- La aplicación no crea por sí misma una red privada: bind, firewall y
  Tailscale siguen siendo responsabilidad del despliegue.
- No hay rate limiting propio en esta capa. Nonce, permisos y red reducen el
  riesgo, pero un secreto robado permitiría presión autenticada hasta rotarlo.
- “Contrato probado en tests” y “Atlas alcanzable desde el VPS” son evidencias
  distintas y se informan por separado.
