# Seguridad — Uso y Ejemplos

Este documento explica cómo usar los nuevos módulos de seguridad (`Antivirus`,
`Membrane`, `ContentFilter`) y muestra ejemplos de configuración para
`governance.json` y variables de entorno.

## Ejemplos de uso (Python)

- Escanear un archivo con `Antivirus`:

```python
from atlas.security import Antivirus
from pathlib import Path

av = Antivirus()
clean = av.scan(Path("/tmp/uploaded_script.py"))
if not clean:
    print("Malware detectado: rechazar ejecución")
```

- Proteger un payload con `Membrane`:

```python
from atlas.security import Membrane
from atlas.transparency.merkle_tree import MerkleLogger
from atlas.core.decider import Decider

logger = MerkleLogger()  # instancia real desde el runtime
decider = Decider()      # usa la implementación de Decider del proyecto
mem = Membrane(decider=decider, logger=logger)

payload = b"print('hello world')"
context = {"task_id": "local-123", "user": "dev"}
if mem.protect(payload, context):
    print("Payload aprobado para ejecución")
else:
    print("Payload bloqueado por la membrana")
```

- Usar `ContentFilter` directamente:

```python
from atlas.security import ContentFilter

cf = ContentFilter()
if cf.is_blocked(b"rm -rf / # malicious"):
    print(cf.block_reason(b"rm -rf / # malicious"))
```

## Ejemplo `governance.json`

Incluye un bloque `signatures` con patrones simples (base64/plaintext).

```json
{
  "signatures": [
    "malware-example-signature",
    "evil_binary_pattern"
  ],
  "security": {
    "antivirus": {
      "scan_on_upload": true,
      "fail_open": false
    }
  }
}
```

- `signatures` puede ser lista de cadenas simples; en producción se
  recomienda integrar YARA o ClamAV y sincronizar firmas desde un feed.

## Variables de entorno

- `ATLAS_AV_DISABLE=1` — desactiva el escaneo antivirus (solo entornos de prueba).
- `ATLAS_PIPELINE_GATE_D=1` — activa el pipeline que puede ejecutar la
  membrana como parte del flujo de ejecución (opt-in).

## Integración en el flujo de aprobación

- Recomendado: llamar a `Membrane.protect()` durante la fase de pre-ejecución
  del orquestador (antes de otorgar permisos a `AtlasExecutor`).
- Registrar siempre los resultados en `MerkleLogger` con acciones como:
  `membrane.inspection`, `membrane.blocked`, `antivirus.detection`.

## Tests y CI

- Añadir los tests de seguridad a la suite de CI (`pytest tests/test_security_*.py`).
- Ejecutar `PYTHONPATH=src python -m pytest tests -q` en el pipeline.

## Notas operacionales

- No habilitar `ATLAS_AV_DISABLE` en entornos productivos.
- Las firmas en `governance.json` deben controlarse por revisión y auditoría.
- Para detección avanzada, integrar un motor de heurística ML separado y
  enriquecer el Merkle log con metadatos de la detección.
