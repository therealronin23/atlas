# ADR-029 — Búsqueda de auditoría y recibos inversos de Hermes

- **Estado:** Aceptado; revisado el 2026-07-16
- **Depende de:** ADR-024, ADR-027 y ADR-028

## Decisión A: búsqueda sobre el ledger

`atlas search` construye un índice SQLite FTS5 efímero desde los registros
Merkle existentes. No introduce una segunda autoridad persistente. Los
términos se convierten a frases seguras; si SQLite no incluye FTS5, se degrada
a coincidencia AND por substring con la misma forma de resultado.

## Decisión B: recibo Hermes→Atlas

`POST /api/exec/audit` usa la autenticación completa de ADR-027: timestamp,
nonce persistente y HMAC sobre los bytes exactos. Valida:

- `action` no vacío;
- `result` en `success`, `failure`, `blocked`, `pending`, `refused`;
- `risk_level` en `safe`, `moderate`, `high`, `critical`;
- `payload` como objeto JSON.

El servidor fuerza `agent=hermes_vps` y convierte la acción a namespace
`hermes.*`. Devuelve el recibo encadenado de Atlas.

## Autoridad y semántica

Atlas sigue siendo el único ledger. Un recibo demuestra que Atlas recibió y
encadenó una declaración autenticada con el secreto Hermes; no prueba por sí
mismo el efecto que Hermes declara. No se importa historia anterior ni se
mantiene una cadena paralela.

La antigua skill `scripts/hermes_skill_atlas_audit/` permanece solo como
compatibilidad y ejecuta la skill canónica `atlas-twin`. Si Atlas está offline,
el cliente falla de forma visible; el llamador decide si una respuesta puede
continuar, pero no debe fingir que existe recibo.
