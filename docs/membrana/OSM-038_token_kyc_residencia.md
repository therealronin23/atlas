# OSM-038 — Interfaz de token KYC / residencia (sin hacer el KYC, solo exigirlo)

Fecha: 2026-06-17 · Estado: **Difusión** (elevada y refinada desde Suspensión por el barrido
Gemini; ver [[OSM-000]]) · Origen: registro OSM-000 (export-control, razón del apagón de
Fable 5) + refinamiento Gemini 2026-06-17 · Contexto: paper §6.5 (residencia no resoluble
en código), `src/atlas/security/` (membrana), [[OSM-021]] (identidad), [[OSM-025]]
(device-bound), [[OSM-034]] (consentimiento Netflix-style).

---

## Contexto

El paper §6.5 declara, correctamente, que **la residencia/export-control no es resoluble
en código**: IP/GPS/operadora/RTT son señales de riesgo, no prueba; un proxy residencial +
GPS spoofeado las pasa. La conclusión actual: KYC = legal, no código.

La auditoría de Gemini afinó el punto y, tras contrastarlo, **el matiz es válido**: aunque
Atlas no deba *hacer* el KYC, dejar el gateway sin **interfaz para exigirlo** lo convierte
en un producto incompleto. Si el apagón de Fable 5 fue por export-control, un gateway que
no puede *rechazar* peticiones sin prueba de residencia no resuelve el caso que motiva todo.

La distinción clave: **hacer KYC** (legal, externo) vs. **exigir y verificar un token de
KYC ya emitido** (criptográfico, en el path). Lo segundo sí es código.

## La idea

La membrana expone una interfaz para **aceptar y verificar un token de residencia/KYC
emitido por un proveedor externo** (Onfido, Sumsub, eIDAS, un IdP gubernamental), sin
realizar la verificación de identidad ella misma:

1. **Onboarding**: el sujeto pasa el KYC con un proveedor acreditado (fuera de Atlas). El
   proveedor emite un **token firmado** que atesta "residencia verificada en jurisdicción
   X, válido hasta fecha Y" — sin revelar la identidad completa (claim mínimo).
2. **Por petición (o por sesión)**: el `CosignedRequest` puede acompañarse de ese token. La
   membrana **verifica la firma del proveedor** contra su clave pública conocida y comprueba
   vigencia + jurisdicción permitida.
3. **Rechazo criptográfico**: si la política exige residencia y el token falta o no verifica,
   la membrana **rechaza la petición en el path** y registra la causa (`blocked:
   no-residency-proof`) en el log. Es una decisión auditable, no un bloqueo opaco.

Atlas no establece la ubicación; **delega la atestación y solo verifica la prueba**. El log
hace la decisión de rechazo verificable (encaja con [[OSM-030]] escudo legal).

## Encaje en Atlas

- **Capa 1 / membrana**: el chequeo de token es una compuerta de admisión más, antes de la
  inspección por causa ([[OSM-028]]).
- **`Decider` (ADR-040)**: "falta token de residencia" es un input al PDP, no un hardcode —
  coherente con el rumbo de decisor intercambiable.
- **Invariante I2**: el rechazo por residencia se registra con causa, como cualquier disparo.

## Correcciones de verificación

- **No resuelve export-control; lo hace exigible y auditable.** Un atacante con un token KYC
  fraudulento (obtenido con identidad robada) sigue pasando — eso es problema del proveedor
  de KYC, no del gateway. Declararlo: Atlas verifica *la prueba*, no *la verdad subyacente*.
- **No prometer desbloquear Fable 5.** Esta pieza da al proveedor el mecanismo para *exigir*
  prueba de residencia de forma verificable; si eso satisface al regulador es decisión legal,
  no técnica. Mantener el §6.5 del paper intacto: residencia no resoluble en código.
- El token debe ser **minimal-disclosure** (residencia + vigencia, no identidad completa)
  para no convertir el gateway en un honeypot de datos personales (choca con [[OSM-007]]).

## Criterios de compuerta

1. **Verificable**: verificar una firma de token contra una clave pública conocida es
   criptografía estándar. La afirmación se acota a "verifica la prueba, no la verdad".
2. **Coherente**: respeta §6.5 (no establece ubicación); coordina con [[OSM-007]]
   (minimal-disclosure) y [[OSM-025]] (identidad).
3. **Probado**: test de que sin token válido la petición se rechaza con causa registrada, y
   con token válido pasa. Pendiente.
4. **Mantenible**: verificación de JWT/VC firmado; sin deps exóticas (clave pública + verify).
5. **Sancionado**: la política de qué jurisdicciones se exigen pasa por PDP (I5).

## Límites honestos

- **Token fraudulento**: si el KYC subyacente fue burlado, el token verifica igual. Atlas no
  puede detectarlo. El riesgo se traslada al proveedor de KYC, no se elimina.
- **Legal+operativo**: integrar un proveedor de KYC real (acreditación, contratos, eIDAS) es
  trabajo de producto/legal, no de esta OSM. Aquí solo está la interfaz de verificación.
- **Privacidad**: un token mal diseñado filtra identidad. Exigir minimal-disclosure y
  coordinar con [[OSM-007]] para no retener el token en claro en el log.
