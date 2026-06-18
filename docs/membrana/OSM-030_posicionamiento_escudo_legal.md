# OSM-030 — Posicionamiento de escudo legal + encaje EU AI Act

Fecha: 2026-06-17 · Estado: **Difusión** (ver [[OSM-000]]) · Origen: `idea avance 3.md` ·
Contexto: ADR-051 (Compliance Gateway), `docs/eu_ai_act_mapping.md`, `compliance_gateway_carta.md`,
[[OSM-024]] (Osmosis en path). Pieza de narrativa: alimenta la futura carta reescrita.

---

## Contexto

El obstáculo de adopción de un filtro obligatorio en el path ([[OSM-024]]) es que el
proveedor lo percibe como pérdida de control y aumento de *liability*: "si registro cada
inspección y se la pruebo al usuario, me pueden demandar por cada bloqueo". El usuario dio la
vuelta al argumento: un log verificable **defiende** al proveedor en litigios. Esta OSM
desarrolla ese reencuadre como el motor de adopción real (el técnico no basta).

## La idea

El log de completitud no es solo transparencia hacia el usuario; es **prueba forense a favor
del proveedor**:

- Ante una demanda por daño atribuido al modelo, el proveedor demuestra con la cadena: *este
  daño no fue el modelo actuando libremente, sino un usuario que intentó manipularlo de forma
  fraudulenta, fue detectado y bloqueado* — con secuencia firmada ([[OSM-025]]), causa
  registrada ([[OSM-028]]) y acción, todo inmutable.
- Reconvierte "liability" en **blindaje**: el bloqueo registrado es evidencia de diligencia
  debida, no de censura arbitraria.
- Encaja con el incidente Fable 5: el apagón por export-controls ocurrió por **no poder
  demostrar** quién usa el modelo ni que no se abusa. Un log verificable es exactamente la
  prueba que faltaba.

## Encaje en Atlas

- **Reescribe el "por qué os lo envío" de la carta**: de "os señalo un gap altruista" a "os
  doy una defensa legal + cumplimiento regulatorio". Decisión ya tomada: Osmosis gana el pitch.
- **`eu_ai_act_mapping.md`**: Art. 12 (record-keeping tamper-resistant) y Art. 13
  (transparencia demostrable) pasan de "cumplimos esto" a "esto os protege". Art. 53
  (red-teaming systemic risk) se apoya en el organismo de conocimiento (ADR-049).
- No toca código; es la columna narrativa del producto.

## Correcciones de verificación

- **No soy abogado y el proyecto tampoco.** El argumento de escudo legal es plausible y
  fuerte, pero es una hipótesis jurídica, no un hecho verificado. La OSM debe redactarse como
  *"argumento a validar con asesoría legal"*, no como afirmación de que protege. La compuerta
  #1 (verificable) aquí significa: no afirmar consecuencias legales como ciertas.
- Evitar el overclaim que el premortem del propio chat 3 señaló: el valor es el reencuadre de
  incentivos, no una garantía de inmunidad legal.

## Criterios de compuerta

1. **Verificable**: el mecanismo técnico (log inmutable + secuencia firmada + causa) es real
   y probado; la *consecuencia legal* se marca como hipótesis a validar, no como hecho.
2. **Coherente**: alineado con ADR-051 y el mapping EU AI Act existente.
3. **Probado**: "prueba" aquí es un caso de uso narrado + validación por asesoría legal real
   (pendiente), no un test de código.
4. **Mantenible**: es documentación/narrativa; coste de mantenimiento bajo.
5. **Sancionado**: el usuario, como decisión de posicionamiento (ya tomada).

## Límites honestos

- **Hipótesis jurídica sin abogado**: el peso legal real depende de jurisdicción y de
  asesoría que no tenemos. No prometer protección.
- **Incentivo de doble filo**: el mismo log que defiende al proveedor también expone sus
  decisiones de inspección. Algunos proveedores preferirán opacidad hasta que la regulación
  les obligue — el premortem lo dice.
- **No resuelve identidad/KYC**: el escudo legal asume binding de identidad ([[OSM-025]]),
  que es parcial (no anónimo, pero no KYC real).
