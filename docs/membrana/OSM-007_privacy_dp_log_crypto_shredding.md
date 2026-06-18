# OSM-007 — Privacidad del log: crypto-shredding (Merkle inmutable vs. GDPR Art. 17)

Fecha: 2026-06-17 · Estado: **Absorbida** → ADR-053 (2026-06-18) ·
ver [[OSM-000]]) · Origen: registro OSM-000 (chats 1-2) + auditoría Gemini 2026-06-17 ·
Contexto: ADR-053, `src/atlas/transparency/crypto_shred.py` (nuevo),
`src/atlas/transparency/client_cosign.py` (`InspectionRecord.salted_hash`),
`src/atlas/security/pii_surrogate.py` (ADR-023), [[OSM-026]] (doble copia).

---

## Contexto

El log Merkle es append-only e inmutable: esa es su virtud (completitud, no-reescritura).
Es también una trampa frente al **derecho de supresión** (GDPR Art. 17): no puedes borrar
una hoja sin destruir la raíz y romper la validación de todas las demás entradas del lote.

La auditoría de Gemini (2026-06-17) lo planteó como bloqueante. **Contrastado, está
parcialmente mitigado ya**, pero queda un flanco real:

- **Mitigado:** el `InspectionRecord` **no guarda texto claro**. Guarda `payload_hash`
  (SHA-256) y `cosig` (que a su vez contiene el hash, no el prompt). Verificado en
  `client_cosign.py`. El árbol nunca contiene el contenido del usuario.
- **Flanco real:** un SHA-256 de un prompt de **baja entropía** es vulnerable a fuerza
  bruta / rainbow tables. Si alguien sospecha el contenido, puede confirmarlo recomputando
  el hash. Para datos personales identificables, eso es reidentificación.

## La idea

**Crypto-shredding**: el árbol nunca contiene un hash directamente reidentificable. Cada
hoja referencia `H(salt_i || payload)` con un **salt aleatorio por petición** guardado
fuera del árbol (en almacén relacional convencional, borrable).

- El árbol Merkle se mantiene matemáticamente intacto (la cadena no se toca nunca).
- Para ejercer el derecho de supresión: se **destruye el salt** de esa petición. El hash
  en el árbol queda huérfano — matemáticamente imposible de reconstruir o reidentificar.
- La completitud (`detect_omission()` por `seq`) **no depende del salt**: opera sobre la
  secuencia monótona firmada, no sobre el contenido. Borrar el salt no abre huecos.

## Resolución del binding — diseño dual-hash

El bloqueante técnico estaba en el check 4 de `APIResponse`: el cliente verifica que su
`payload_hash` (SHA-256 simple del payload, que firmó) aparece literal en los bytes de la
hoja. Si la hoja guardara solo el hash salteado, el check fallaría.

**Solución: hoja dual-hash.** La hoja Merkle contiene AMBOS:

```
payload_hash  = SHA-256(payload)         # lo que el cliente firmó; permanente
salted_hash   = SHA-256(salt_i || payload)  # derivado con salt aleatorio externo
```

- `payload_hash` persiste para siempre en el árbol (check 4 del cliente sigue igual).
- `salted_hash` está en la hoja (cubierto por la integridad Merkle) pero el salt vive fuera.
- **Derecho de supresión**: destruir `salt_i` en el `SaltStore` → `salted_hash` queda como
  dead-end; contenido irrecuperable sin tocar el árbol ni romper ninguna prueba.

## Encaje en Atlas

- **`src/atlas/transparency/crypto_shred.py`** (nuevo): `SaltedEntry` + `SaltStore`.
  Sin dependencias nuevas — solo `hashlib` y `os` de stdlib. ✅ CLAUDE.md regla 6.
- **`src/atlas/transparency/client_cosign.py`**: `InspectionRecord` gana campo
  `salted_hash: str = ""` (vacío por defecto — retrocompatible). `to_bytes()` lo
  incluye siempre en el JSON canónico.
- **Reusa el patrón existente**: `pii_surrogate.py` (ADR-023) ya hace sustitución con
  secret_salt. Aquí el salt es aleatorio por petición y su propósito es destrucción, no
  coherencia — mismo primitivo, distinto objetivo.
- **`detect_omission()`**: no se modifica; opera sobre `seq` monótono, nunca sobre
  contenido. Borrar el salt no crea ni tapa huecos. ✅
- **Invariante I3** (no perfilar contenido): refuerza I3 — contenido irrecuperable tras
  supresión del salt.

## Correcciones de verificación

- **No es "no guardamos nada del usuario".** Guardamos `payload_hash`, `salted_hash` y
  metadatos (decision, cause, seq, timestamp_ns). Los metadatos pueden ser datos personales
  por patrón de uso. El crypto-shredding cubre el contenido, no todos los metadatos.
- **Tensión binding resuelta** (ver sección anterior): la hoja dual-hash mantiene
  `payload_hash` para el check 4, añade `salted_hash` para privacidad. El salt vive
  fuera — no en el árbol.

## Criterios de compuerta

1. **Verificable**: el mecanismo (hash salteado + destrucción de salt) es estándar
   (crypto-shredding, usado en GDPR-compliant storage). La afirmación se acota: cubre
   contenido, no todos los metadatos. ✅
2. **Coherente**: refuerza I3; tensión de binding resuelta con diseño dual-hash. ✅
3. **Probado**: 12 tests en `tests/test_crypto_shred.py` — verifican (a) distinción de
   hashes, (b) idempotencia de `register`/`shred`, (c) irrecuperabilidad post-shred,
   (d) check 4 del cliente pasa con y sin salted_hash, (e) `detect_omission()` sin
   afectar. ✅
4. **Mantenible**: stdlib (`hashlib`, `os`); sin deps nuevas; retrocompatible (campo
   `salted_hash=""` por defecto). ✅
5. **Sancionado**: PDP, al promover.

## Límites honestos

- **`payload_hash` persiste permanentemente** en el árbol. Para prompts largos de lenguaje
  natural es pseudo-anónimo (SHA-256 no invertible en la práctica). Para prompts cortos o
  predecibles puede ser confirmable por fuerza bruta. Declarar este límite en paper §6.
- **Metadatos no cubiertos**: seq, timestamps y causa pueden reidentificar por patrón de
  uso. Crypto-shredding cubre el contenido, no los metadatos.
- **Custodia del salt**: un salt filtrado antes de la supresión anula la protección.
  En producción el SaltStore requiere control de acceso separado del log Merkle.
- **Tensión legal GDPR vs. EU AI Act Art. 12**: el AI Act exige retención de logs mínimo
  6 meses; el GDPR permite supresión antes. Son dos reglamentos en tensión — no resoluble
  solo en código; crypto-shredding hace el contenido irrecuperable sin eliminar la entrada
  de log (posible compromiso aceptable, pero requiere validación legal).
