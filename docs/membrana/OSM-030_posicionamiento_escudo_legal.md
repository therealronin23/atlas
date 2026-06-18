# OSM-030 — Posicionamiento de escudo legal + encaje EU AI Act

Fecha: 2026-06-17 · Estado: **Difusión** (narrativa; alimenta la carta; ver [[OSM-000]]) ·
Origen: `idea avance 3.md` · Contexto: ADR-051 (Compliance Gateway),
`docs/eu_ai_act_mapping.md`, `docs/compliance_gateway_carta_en.md`, [[OSM-024]].
Pieza de narrativa: el motor de adopción del filtro es legal/regulatorio, no técnico.

---

## Contexto

El obstáculo de adopción de [[OSM-024]] es que el proveedor percibe el filtro como aumento
de *liability*: "si registro cada inspección y se la pruebo al usuario, me pueden demandar
por cada bloqueo". Esta OSM da la vuelta al argumento: un log verificable **defiende** al
proveedor en litigios. Sin este reencuadre, el motor de adopción es solo regulatorio (EU AI
Act obliga → adoptas). Con él, el motor es también económico (te protege → quieres adoptarlo).

El incidente Fable 5 (junio 2026) es el caso de uso real: el apagón ocurrió precisamente
porque no había forma de demostrar quién usa el modelo ni que no se abusa de él. El log
verificable es exactamente la prueba que faltaba — no para el usuario, sino para el regulador
y el tribunal.

## El argumento del escudo legal

**Para el proveedor — defensa en litigios por daño atribuido al modelo:**

Un usuario demanda al proveedor alegando que el modelo generó contenido dañino. Sin un log
verificable, la defensa del proveedor es: "nuestros sistemas inspeccionaron y el usuario no
fue flaggeado" — afirmación propia, no verificable. Con el log:

- El proveedor produce una **prueba de inclusión Merkle**: `InspectionRecord(seq=n,
  decision="allow", cause="policy:safe_content_v3", timestamp_ns=...)` en la posición k
  del árbol, con STH firmado.
- Esa prueba es verificable por el tribunal sin depender del testimonio del proveedor.
- Si el usuario intentó manipular el modelo (ataque documentado en el log con `cause=
  "campaign:jailbreak_attempt"`), el proveedor tiene la secuencia firmada que lo prueba.

**Para el proveedor — defensa ante regulador (EU AI Act Art. 12):**

La prueba de inclusión Merkle es exactamente el "registro automático, resistente a
manipulaciones, con timestamp" que exige Art. 12. La diferencia con un log propietario:
este log es **verificable por el regulador sin depender del proveedor**, lo que convierte
"cumplimos Art. 12" en algo demostrable, no en una declaración.

**Para el usuario — defensa ante bloqueo arbitrario:**

El usuario puede auditar la `cause` de su bloqueo: "bloqueo por causa X" vs. "bloqueo sin
registro de causa". Un bloqueo sin `InspectionRecord` en el log — detectable por el propio
usuario vía `detect_omission()` — es evidencia de manejo irregular. Esto convierte el
mecanismo técnico en una vía de recurso real ([[OSM-027]] lo implementa).

## El doble filo (honesto)

El mismo log que defiende al proveedor también lo expone:

- Inspecciones sin causa registrada son detectables por el usuario.
- Un patrón discriminatorio en las causas (mismos prompts bloqueados para ciertos grupos)
  es ahora auditable.
- Un proveedor que hoy opera con opacidad deliberada preferirá no adoptar el filtro hasta
  que la regulación lo obligue — este es el segmento que no es cliente hasta EU AI Act.

El argumento honesto no es "el log siempre protege al proveedor"; es "el log protege al
proveedor que opera de buena fe y expone al que no". Ese es exactamente el incentivo
correcto para que la regulación funcione.

## Encaje EU AI Act — mapa de artículos

| Artículo | Obligación | Lo que aporta el log |
|---|---|---|
| Art. 9 (gestión de riesgos) | Sistema continuo de evaluación de riesgos | Cada `InspectionRecord(cause=...)` es un acto de evaluación registrado. |
| Art. 12 (registro automático) | Log tamper-resistant con timestamp, ≥6 meses | Log Merkle append-only + `timestamp_ns` + STH firmado. Sin techo de retención. |
| Art. 13 (transparencia al usuario) | Usuario informado de inspección y sus causas | `detect_omission()` + `cause` field auditables unilateralmente por el usuario. |
| Art. 14 (supervisión humana) | Sistema auditable por personas | Read-API (`GET /api/exec/api/v1/log/...`) + inclusion proofs verificables por regulador. |
| Art. 26 (obligaciones del deployer) | Monitorizar operación e informar incidentes | Read-API da al deployer la base de evidencia por petición. |
| Art. 53 (riesgo sistémico GPAI) | Evaluar y mitigar riesgos sistémicos; documentar | Evidencia por petición a escala; `cause` + `decision` permiten análisis de patrones. |

**Lo que el mecanismo NO hace** (honesto, para no overclaimar ante regulador):
- No substituye la evaluación de conformidad (CE marking, Art. 43).
- No hace KYC ni verifica residencia ([[OSM-038]] es el hook; no es código hoy).
- No garantiza que la política de inspección sea correcta — solo que se aplica de forma
  verificable y consistente.
- No es asesoría legal. El argumento de "escudo legal" es una hipótesis plausible, no una
  garantía jurídica. Cualquier operador que quiera usarlo en litigios necesita abogado propio.

## Encaje en la carta (compliance_gateway_carta_en.md)

La carta ya adopta el pitch Osmosis (siempre-encendida, en el path, coste asumido por el
filtro). Esta OSM es el desarrollo del argumento económico detrás de ese pitch: el filtro
no es un coste regulatorio que Anthropic asume — es una inversión en blindaje legal + señal
de mercado hacia reguladores. Los dos párrafos del "por qué os lo enviamos" en la carta
mapean directamente a esta OSM:

1. "señalamos el gap que no podéis cerrar solos" → el conflicto de interés estructural
   (juez y parte) que el log externo cierra.
2. "os damos el razonamiento, no el producto" → el argumento de escudo legal + EU AI Act
   es el razonamiento que convence a un departamento legal, no solo a un equipo de seguridad.

## Correcciones de verificación

- **Hipótesis jurídica**: todas las consecuencias legales se marcan como "plausible" o
  "argumento a validar", nunca como hecho verificado. La compuerta #1 (verificable) se
  aplica al mecanismo técnico, no a la consecuencia legal.
- **Overclaim del doble filo**: no presentar el escudo como unilateral. El paper (§6.9)
  ya lo dice: "both parties benefit if and only if the operator is operating honestly".
  La carta lo reitera.

## Criterios de compuerta

1. **Verificable**: el mecanismo técnico (log Merkle + proofs + cause field) es real y
   probado. Las consecuencias legales son hipótesis marcadas como tales.
2. **Coherente**: alineado con paper §7.1 (mutual protection), §7.2 (EU AI Act alignment).
3. **Probado**: "prueba" es coherencia interna con los artículos del EU AI Act listados
   arriba + validación por asesoría legal (pendiente, no bloqueante para arXiv).
4. **Mantenible**: documentación/narrativa; 0 deps de código.
5. **Sancionado**: posicionamiento de producto; decisión del usuario (ya tomada: Osmosis gana).

## Límites honestos

- **No soy abogado**: consecuencias legales = hipótesis plausible, no garantía.
- **Doble filo real**: el log también expone al proveedor que opera de mala fe. No suavizar
  este punto — es la característica, no el defecto.
- **Incentivo de adopción no resuelto en código**: ningún ADR ni OSM obliga a un proveedor
  externo a adoptar el filtro. El motor es regulatorio (EU AI Act) + económico (escudo legal).
  La adopción es negociación de producto, no implementación técnica.
- **KYC sigue abierto**: el escudo legal asume que el sujeto tiene identidad verificable
  ([[OSM-025]] Layer 1 = clave de dispositivo, no KYC real). Para casos de export-control
  (razón real del apagón de Fable 5), [[OSM-038]] es el hook pendiente.
