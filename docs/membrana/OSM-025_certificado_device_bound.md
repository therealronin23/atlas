# OSM-025 — Certificado ligado al dispositivo + firma automática por request

Fecha: 2026-06-17 · Estado: **Difusión** (ver [[OSM-000]]) · Origen: `idea avance 3.md` ·
Contexto: ADR-053 (completitud + co-firma), `src/atlas/transparency/client_cosign.py`,
[[OSM-024]] (Osmosis), [[OSM-026]] (doble copia).

---

## Contexto

ADR-053 cierra la completitud con **co-firma del cliente**: cada request lleva una secuencia
monótona firmada por el usuario, y una laguna en esa secuencia es detectable unilateralmente
(`detect_omission()` en `client_cosign.py`). El usuario rechazó la co-firma **manual** por
fricción: nadie va a firmar a mano cada prompt. La pieza a desarrollar es cómo conservar la
garantía de completitud **sin pedir acción consciente** en cada envío.

## La idea

Sustituir la firma manual por una **clave criptográfica ligada al dispositivo** que firma
cada request en silencio, tras un único onboarding:

1. **Onboarding (una vez)**: al hacer login federado (Google/Microsoft/Apple), el dispositivo
   genera un par de claves en hardware seguro y registra la clave pública contra la cuenta.
   El usuario acepta una vez el "modo verificable".
2. **Por request (automático)**: el cliente firma `canonical_JSON({"payload_hash": SHA256(prompt), "seq": n})`
   con la clave privada del dispositivo. Sin gesto del usuario. **No hay timestamp en el
   cuerpo firmado**: el timestamp lo asigna el operador en el `InspectionRecord` (evita
   disputas de reloj entre cliente y servidor). Esto es coherente con `client_cosign.py`.
3. **Servidor (Osmosis)**: verifica la firma con la pública asociada a la cuenta y registra
   la entrada en el log Merkle ligada a esa secuencia. Si inspecciona, la inspección queda
   atada a la misma secuencia.
4. **Verificación**: el usuario descarga su sub-árbol (sus secuencias) y comprueba que no
   hay huecos — la misma garantía de ADR-053, ahora sin fricción.

La cuenta federada aporta **identidad** una sola vez; la clave de dispositivo aporta la
**firma silenciosa por request**. Son dos cosas distintas (ver corrección).

## Encaje en Atlas

- **Reemplaza el frontend de `client_cosign.py`**, no su mecanismo: la secuencia monótona +
  firma sobre hash + `detect_omission()` se conservan intactos. Cambia *quién y cómo* firma:
  de gesto manual a clave de dispositivo.
- **Identidad**: resuelve parcialmente el gap de "binding de identidad" que la carta admite
  como pendiente — con matices (ver límites).
- **Invariante I2**: refuerza que todo disparo quede ligado a una secuencia firmada
  verificable.

## Correcciones de verificación

**El chat dice "Passkey/WebAuthn por request". Es incorrecto y no pasa la compuerta así.**

- WebAuthn/Passkeys firman un **challenge del servidor**, no payloads arbitrarios de la app,
  y **exigen verificación de usuario** (biometría/PIN/touch) por diseño en cada aserción.
  Eso es exactamente la fricción que queremos eliminar.
- La firma **silenciosa por request** corresponde a una **clave ligada al dispositivo** en
  TPM (Windows) / Secure Enclave (Apple) / StrongBox (Android), expuesta como *device-bound
  key* — análoga a Apple App Attest, Android Key Attestation o un certificado de cliente TLS
  anclado en hardware. Esas claves firman datos arbitrarios sin gesto por uso.
- Diseño correcto: **WebAuthn/Passkey solo en el onboarding** (login federado fuerte, una
  vez) → de ahí se aprovisiona una device-bound key que firma cada request en silencio.

## Criterios de compuerta

1. **Verificable**: corregido el error WebAuthn↔device-key; el mecanismo resultante es
   criptográficamente sólido y estándar en industria (banca, gobierno).
2. **Coherente**: conserva el mecanismo de completitud de ADR-053 (no lo viola, lo desfricciona).
3. **Probado**: requiere prototipo de aprovisionamiento de device-key + firma + verificación
   contra el log (pendiente).
4. **Mantenible**: las APIs de hardware son del sistema operativo/navegador, no deps exóticas
   de Atlas. Web puro necesita Web Crypto + fallback software (más débil) — documentado.
5. **Sancionado**: PDP, al promover.

## Límites honestos

- **Web puro es más débil**: sin acceso a hardware, el fallback es clave software, que se
  puede exfiltrar. La garantía fuerte es en desktop/móvil con hardware seguro.
- **No es anónimo**: la clave pública queda asociada a la cuenta federada. Es *binding de
  identidad*, no privacidad de identidad. Aceptable para el caso de cumplimiento; explícito.
- **Pérdida de cuenta = pérdida de verificación**: si el usuario pierde la cuenta federada,
  pierde la capacidad de verificar su log histórico. La doble copia ([[OSM-026]]) mitiga.
- **Rotación de clave** (cambio de dispositivo) debe mantener continuidad de secuencia — no
  trivial; pendiente de diseño.
