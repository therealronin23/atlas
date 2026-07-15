---
name: atlas-twin
description: Use Atlas Core capabilities from Hermes through the signed, audited twin channel.
---

# Atlas twin

Usa esta skill cuando una petición necesite consultar o actuar en Atlas Core.
El cliente incluido construye la firma HMAC, genera un nonce nuevo, desactiva
proxies y rechaza redirecciones. No sustituyas el cliente por `curl` ni
construyas la firma a mano.

Antes de la primera operación de una conversación, comprueba el canal:

```bash
python3 "${HERMES_SKILL_DIR}/atlas_twin.py" health
```

No afirmes que Atlas está conectado si `health` no devuelve JSON con
`"ok": true`. Un fallo de red no autoriza a inventar el estado de Atlas.

## Operaciones

Delegar una intención completa al pipeline de Atlas:

```bash
python3 "${HERMES_SKILL_DIR}/atlas_twin.py" intent "resume el estado real del proyecto"
```

Ejecutar un comando permitido por la gobernanza de Atlas:

```bash
python3 "${HERMES_SKILL_DIR}/atlas_twin.py" shell git status --short
```

Leer o escribir dentro de las rutas autorizadas de Atlas:

```bash
python3 "${HERMES_SKILL_DIR}/atlas_twin.py" file-read tmp/informe.txt
python3 "${HERMES_SKILL_DIR}/atlas_twin.py" file-write tmp/informe.txt --data "contenido"
```

Usar el navegador local de Atlas:

```bash
python3 "${HERMES_SKILL_DIR}/atlas_twin.py" browser navigate https://example.com
python3 "${HERMES_SKILL_DIR}/atlas_twin.py" browser extract h1
python3 "${HERMES_SKILL_DIR}/atlas_twin.py" browser screenshot comprobacion
```

Registrar una acción propia de Hermes en la cadena Merkle compartida:

```bash
python3 "${HERMES_SKILL_DIR}/atlas_twin.py" audit skill.run \
  --result success --risk moderate --payload '{"skill":"weather"}'
```

Las denegaciones de Atlas son definitivas. No intentes rodear un `403`, no
rebajes el riesgo declarado y no repitas automáticamente una operación con
efectos externos. El secreto `HERMES_API_KEY` nunca debe aparecer en una
respuesta, argumento, log o payload.
