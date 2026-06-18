# OSM-026 — Doble copia del log Merkle (proveedor + usuario)

Fecha: 2026-06-17 · Estado: **Absorbida** (2026-06-18) · Origen: `idea avance 3.md` ·
Contexto: ADR-053, `src/atlas/transparency/witness.py`, `log.py`, [[OSM-025]].
Límite honesto: nodos witness independientes = infra de ecosistema pendiente. Paper §6.1.

---

## Contexto

El límite honesto más grande de ADR-053 es **split-view**: un operador malicioso puede
mostrar un log consistente al regulador y otro distinto al usuario, cada uno internamente
válido. La defensa estándar (Certificate Transparency) es una **red de witnesses** que
chismorrean STH firmados — infraestructura que un proveedor solo no despliega. El usuario
propuso una mitigación más simple: que **el usuario tenga su propia copia** del log,
guardada localmente (tipo cookie), como salvaguarda mutua.

## La idea

Dos copias de la misma cadena, una en cada lado:

- **Copia del proveedor**: el log Merkle completo, autoritativo, append-only.
- **Copia del usuario**: su **sub-árbol** (sus secuencias firmadas + los STH que ha visto),
  persistido localmente por el cliente. Es pequeña — solo sus entradas y raíces.

Cada copia es una **vista independiente**. La del usuario está anclada a las firmas de su
propia device-key ([[OSM-025]]): el proveedor no puede fabricarla. Cuando el usuario verifica,
compara su copia local contra lo que el servidor le sirve hoy:

- Si el servidor le muestra un STH inconsistente con uno que el usuario ya guardó → prueba
  de manipulación (consistencia rota, RFC 9162 consistency proof).
- Si falta una de sus secuencias firmadas → omisión (`detect_omission()`).

## Encaje en Atlas

- **Extiende `witness.py`**: hoy el witness es in-process y básico. Esta OSM convierte al
  **propio usuario en un witness de su propia vista** — información que un witness externo de
  CT no tiene (el sujeto sabe qué firmó).
- **Apoya [[OSM-025]]**: la copia local es también el backup que mitiga "pérdida de cuenta =
  pérdida de verificación".
- **Invariante I2**: la doble copia hace el registro de disparos comprobable desde dos lados.

## Correcciones de verificación

- **No cierra split-view por sí sola.** El usuario detecta divergencia *en lo que a él le
  muestran*; no puede saber, solo con su copia, qué vista ve el regulador. Es un **paso
  parcial** hacia la protección split-view, no el cierre. El cierre completo sigue
  requiriendo gossip entre witnesses independientes (RFC 9162).
- El valor real: el sujeto monitorizando su propia secuencia **reduce el requisito de la red
  de witnesses** (pregunta abierta ya planteada en el post de LessWrong). Esto es lo
  defendible y novedoso; afirmar "cierra split-view" sería overclaim.

## Criterios de compuerta

1. **Verificable**: el mecanismo (consistency proof + secuencia firmada local) es RFC 9162
   estándar; la afirmación se acota a "paso parcial", no "cierre".
2. **Coherente**: refuerza ADR-053 sin violar nada.
3. **Probado**: requiere test de que una divergencia de STH entre copia local y servidor se
   detecta (pendiente).
4. **Mantenible**: solo persistencia local en el cliente + reuso de proofs ya implementados.
5. **Sancionado**: PDP.

## Límites honestos

- **Usabilidad**: muy pocos usuarios descargarán y compararán su copia. El valor está en que
  *exista la posibilidad* y en que un auditor/regulador pueda hacerlo en nombre de muchos.
- **Colusión total** (proveedor reescribe ambas vistas antes de que el usuario guarde nada)
  no se detecta; la device-key del usuario es lo que lo impide para sus propias entradas.
- No sustituye witnesses externos; los **complementa** y baja su coste.
