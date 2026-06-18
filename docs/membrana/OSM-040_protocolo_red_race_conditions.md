# OSM-040 — Semántica de red del protocolo: race conditions, retry vs. omisión

Fecha: 2026-06-17 · Estado: **Absorbida** → ADR-053 (2026-06-18) ·
Origen: auditoría Gemini 2026-06-17 (punto válido tras contraste) · Contexto: ADR-053,
`src/atlas/transparency/client_cosign.py` (`detect_omission`), `docs/demo/completeness_demo.py`,
paper §3.3.

---

## Contexto

El demo y el paper modelan el protocolo de forma **síncrona y en memoria**: el sujeto
emite, el operador responde, no hay fallos. La auditoría de Gemini señaló — y al
contrastarlo es **válido y nuevo** — que en producción la red introduce ambigüedad que el
diseño actual no resuelve:

> `detect_omission()` devuelve un hueco en la secuencia. Pero un hueco puede tener **dos
> causas indistinguibles** hoy: (a) el operador omitió la inspección, o (b) la petición
> nunca llegó / falló por timeout / el cliente crasheó antes de recibir el ack.

Si el sujeto no puede distinguir omisión maliciosa de fallo de red, la "prueba unilateral
de omisión" pierde fuerza: el operador puede atribuir cualquier omisión real a "se cayó la
red". Es un ataque de **negación plausible vía ruido de red**.

## La idea

Definir la semántica de secuencia bajo fallo, de modo que un hueco sea atribuible:

1. **Reserva antes de emitir**: el cliente incrementa `seq` y **persiste localmente la
   intención de enviar** (seq + payload_hash + timestamp de envío) ANTES de la llamada de
   red. Así el cliente siempre sabe qué seqs *intentó* emitir, aunque la respuesta nunca
   llegue.
2. **Reconciliación al reconectar**: tras un fallo, el cliente re-consulta al operador por
   el estado de los seqs pendientes (¿los recibiste y registraste?). El operador responde
   con prueba de inclusión (registrado) o ausencia (no llegó).
3. **Idempotencia por seq**: reenviar el mismo `(seq, payload_hash)` es idempotente — el
   operador no crea una segunda hoja; devuelve la prueba de la existente. Un seq nunca se
   reutiliza para un payload distinto (lo garantiza la firma sobre `{payload_hash, seq}`).
4. **Clasificación del hueco**:
   - hueco + el cliente tiene prueba de envío + el operador no exhibe inclusión ni "no
     recibido" coherente → **omisión atribuible al operador**.
   - hueco + el cliente nunca completó el envío (sin ack de red) → **fallo de red**, no
     omisión. El cliente reenvía (idempotente).

## Encaje en Atlas

- **Extiende `detect_omission()`**: hoy compara `observed_seqs` vs. `last_emitted`. Necesita
  un tercer conjunto: `confirmed_sent` (seqs con ack de red). El hueco solo es omisión si
  `seq ∈ confirmed_sent ∧ seq ∉ observed_seqs`.
- **Extiende `APIResponse` / añade un endpoint de reconciliación**: el cliente debe poder
  preguntar "¿estado de seq=n?" y recibir inclusión-o-ausencia firmada.
- **Invariante I2**: refuerza que todo disparo quede registrado **y** que la ausencia de
  registro sea atribuible.

## Correcciones de verificación

- **No elimina la negación plausible, la acota.** Un operador puede seguir alegando fallo
  de red para seqs que el cliente no logró confirmar a nivel de red. Lo que cierra es el
  caso `confirmed_sent ∧ no_inclusion`: ahí la red ya no es excusa. Declararlo así, no como
  "resuelve las race conditions".
- **La idempotencia exige que el operador no trate dos veces el mismo seq como dos
  inspecciones.** Si lo hace, infla el log; hay que testear que reenvío = misma hoja.

## Estado de implementación (2026-06-17)

**Núcleo implementado** en `src/atlas/transparency/client_cosign.py`:
- `Receipt` (acuse firmado, fase 1) + `verify_receipt()`.
- `attributable_omissions(receipted_seqs, observed_seqs)` — omisión atribuible =
  recibo válido sin inclusión.
- Idempotencia por `(seq, payload_hash)` ejercitada en tests.

Tests: `tests/test_network_reconciliation.py` (10 casos: verificación de recibo, recibo
manipulado/mal-firmado rechazado, atribución, idempotencia, reúso de seq detectado) +
Session F en `docs/demo/completeness_demo.py` (recibo-sin-inclusión seq=2 atribuible;
pérdida-en-tránsito seq=4 NO acusada). Alimenta paper §6.8.

## Criterios de compuerta

1. **Verificable**: la semántica (recibo firmado + dedup por id) es estándar en sistemas
   distribuidos (at-least-once + dedup). La afirmación se acota a "acota la negación
   plausible", no la elimina. ✅ probado.
2. **Coherente**: refuerza I2; no viola completitud (opera sobre seq, no contenido). ✅
3. **Probado**: ✅ 10 tests + Session F del demo.
4. **Mantenible**: ✅ reusa Ed25519 del repo; sin deps nuevas; mypy limpio.
5. **Sancionado**: PDP (pendiente — núcleo listo para evaluación de cruce).

## Límites honestos

- **No cierra la negación plausible para seqs sin ack de red.** El operador conserva esa
  zona gris; solo se cierra para lo que el cliente confirmó haber entregado.
- **Persistencia local del cliente**: si el cliente pierde su registro de `confirmed_sent`
  (reinstala, cambia de dispositivo), pierde la base para atribuir. La doble copia
  ([[OSM-026]]) y la device-key ([[OSM-025]]) mitigan parcialmente.
- **Esta pieza alimenta un nuevo límite honesto del paper (§6.9)**: el demo es síncrono;
  la atribución bajo fallo de red es trabajo de protocolo, no demostrado aún.
