# Auditoría + premortem — ADR-051 (Compliance Gateway) y ADR-052 (Odysseus)

Fecha: 2026-06-15 · Tipo: auditoría completa, formato premortem
("ya fracasó como ecosistema en operación: ¿qué lo mató?") · Tono: honesto,
sin sycophancy (a petición explícita del usuario).

> Veredicto en una línea: **la idea está bien planteada como tesis y como carta,
> pero como ECOSISTEMA tiene un fallo de raíz sin resolver (la completitud del
> log) y una tensión posiblemente irreductible (lista pública vs. detección
> eficaz). No está "casi lista": le falta la pieza que sostiene todo lo demás.**

---

## A. Lo que está BIEN planteado (no es cortesía, es verdad)

1. **El opt-in por sesión** salva la coherencia filosófica. Sin él, esto era el
   panóptico que el propio usuario rechazó. Con él, es defendible.
2. **La lista cerrada como frontera de legibilidad** es la decisión de diseño más
   fuerte: acota el daño por construcción, no por promesa.
3. **La transparencia que corta en dos sentidos** es un eje de comunicación
   genuinamente original y es ADN de Atlas.
4. **El timing y el grounding son reales** — el apagón de Fable 5/Mythos 5
   (12-jun-2026) está verificado; la idea ataca exactamente sus dos causas.

Eso es real. Ahora lo que la mataría.

---

## B. El fallo de raíz (CRÍTICO — sin esto, el resto da igual)

### B1. Merkle prueba integridad, NO completitud. El log puede mentir por omisión.

El eje entero ("el usuario puede demostrar que no fue espiado de más") asume que
**toda** inspección quedó registrada. Pero un Merkle sellado solo prueba que lo
que *está* en el log no se alteró. **No prueba que no falte nada.** Un operador
del gateway malicioso (o comprometido) simplemente **no registra** la inspección
que hizo a escondidas, y el árbol sigue siendo válido. El usuario no puede
distinguir "no me inspeccionaron" de "me inspeccionaron y no lo apuntaron".

**La promesa central, tal como está escrita, es falsa.** Esto no es un detalle:
es la viga maestra.

Cómo se arregla (y por qué sube el coste 10×):
- O el **cliente del usuario co-firma cada request**, de modo que la *ausencia* de
  un registro correspondiente sea detectable (el usuario tiene su propia mitad).
- O el log es un **transparency log estilo Certificate Transparency** con
  *witnesses* independientes y gossip, de forma que la omisión sea detectable por
  terceros. Esto exige descentralizar el log → ya no es "un binario de Atlas".

Hasta resolver B1, la frase de venta no se puede decir sin mentir. Y un revisor
agudo en Anthropic la rompe en 10 segundos.

### B2. ¿Quién opera el gateway? El triángulo de confianza no está resuelto.

El diseño necesita un operador del gateway+log que **no sea** ni el usuario ni el
proveedor ni el estado:
- Si lo opera el **proveedor** → el usuario no puede confiar en la completitud (B1).
- Si lo opera el **estado** → es el panóptico.
- Si lo opera el **usuario** → el proveedor/regulador no puede confiar en que se
  aplica de verdad.

"Atlas" puede ser el *rol* de árbitro neutral, pero **alguien tiene que
ejecutarlo**, y ese alguien hereda todo el poder. El ADR no nombra a ese actor.
Sin un operador neutral creíble (con attestation remota verificable, no "confía
en mi binario"), no hay ecosistema, solo hay un demo.

---

## C. Fallos graves (cada uno puede hundirlo por separado)

### C1. Lista pública vs. detección eficaz: tensión posiblemente irreductible.
Una lista **pública** es la condición de la privacidad (no hay reglas secretas)
PERO es también el **mapa de evasión** para el atacante. Y ADR-036 ya documenta
en este mismo repo que las defensas SOTA tienen **>78–85% de bypass bajo ataque
adaptativo**. Es decir: contra un adversario serio (justo el que motivó el bloqueo
gubernamental), la detección acotada **falla la mayoría de las veces**. El gateway
da *garantías de privacidad fuertes* y *garantías de detección débiles*. Para un
regulador, "bloqueo el 15–20% de los abusos sofisticados" no levanta un veto de
seguridad nacional. Hay que decir esto explícitamente, no esconderlo tras "el
camuflaje semántico es difícil".

### C2. Binding de identidad técnicamente ingenuo.
IP estática + MAC: la MAC no cruza L3 (inútil sobre internet), la IP es dinámica y
proxyable, y esto rompe el uso legítimo (móvil, NAT, CGNAT). La causa real del
apagón ("no sabemos quién es foreign national") **no** la resuelve binding de red;
la resuelve **KYC + attestation**, que es legal/operativo, no un campo en Atlas.
El ADR lo difiere a "ecosistema" pero es justamente la mitad del problema que dice
resolver.

### C3. Falso positivo = daño a un inocente, con reporte a una autoridad.
En gravedad máxima, un FP reporta a una persona inocente a un regulador. Dado C1
(detección débil) y el volumen de un ecosistema, los FP son inevitables. ¿Quién
asume ese daño? El contrato exime al **proveedor**, pero ¿expone al **operador**
del gateway? Sin seguro de liability y un proceso de apelación auditable, el primer
FP grave es un incidente legal que cierra el proyecto.

### C4. Jurisdicción cruzada del reporte.
Usuario alemán → modelo US → autoridad US. Reportar datos de un ciudadano UE a una
agencia extranjera choca con GDPR/transferencias internacionales. "Diferido a
ecosistema" no basta: define si el reporte es siquiera legal antes de prometerlo.

---

## D. Fallos de ADR-052 (Odysseus) — el postmortem es distinto

### D1. "Completo + solo + sin perder el sello" = elige dos. No tres.
El propio ADR cifra el esfuerzo en ~510% para una persona, y luego propone
"multi-fase". **Secuenciar no reduce el total**, solo lo estira. La conclusión
honesta que el ADR evita: para un solo desarrollador, "asimilación completa con
calidad y sello intactos" no cabe en un horizonte realista. Lo que mata esto no
es la arquitectura: es la **fatiga** (el propio `idea.md` estimaba 80% de
probabilidad de abandono en el escenario "asimilar TODO"). El ADR registra el
riesgo pero no lo neutraliza; "fases estrictas" es disciplina, no capacidad.

### D2. Cada feature asimilada es superficie de ataque permanente.
Email, calendar, image editor, shell tools: cada uno amplía la superficie que
luego hay que asegurar, auditar y mantener *para siempre*. Más features tira en
dirección contraria a la identidad "seguridad primero" de Atlas. "Completo"
maximiza precisamente lo que Atlas presume de minimizar.

### D3. AGPL-3.0 — contaminación legal.
"Estudiar como referencia y reimplementar" es seguro. Pero el límite entre
"inspirarse" y "obra derivada" es borroso, y si entra una línea de Odysseus,
**AGPL-3.0 aplica a Atlas** — que hoy es repo privado con push directo a main.
Una asimilación "completa" maximiza el riesgo de cruzar esa línea sin darte
cuenta. Hace falta una regla de aislamiento explícita (clean-room) o aceptar
AGPL conscientemente.

---

## E. Lo que falta del planteamiento (respuesta directa a "¿falta algo?")

Sí, faltan cinco piezas, y dos son estructurales:

1. **[Estructural] Modelo de completitud del log** (B1) — sin esto la tesis es
   falsa. Es lo primero.
2. **[Estructural] Operador neutral + attestation remota** (B2) — quién ejecuta
   el árbitro y cómo se verifica sin confiar en él.
3. Modelo económico del ecosistema: **quién paga** por operar el gateway. Sin
   operador sostenible, no hay ecosistema.
4. Bootstrapping de confianza: **certificación de terceros** (años, dinero). El
   problema del huevo y la gallina de "¿por qué confiar en este árbitro?".
5. Métricas de eficacia honestas: tasa de detección real frente a adversario
   adaptativo (C1), no "detecta camuflaje".

---

## F. Veredicto del premortem

**Causa de muerte más probable, por orden:**
1. La promesa de transparencia se demuestra falsa por omisión (B1) en la primera
   revisión técnica seria → pérdida de credibilidad.
2. Detección demasiado débil contra el adversario real (C1) → el regulador no
   levanta el veto → el caso de uso desaparece.
3. (ADR-052) abandono por fatiga antes de la Fase 1 usable (D1).

**Qué NO lo mata:** la arquitectura de Atlas, que es sólida. El problema nunca fue
la ingeniería; es que el ecosistema requiere resolver completitud + operador
neutral + eficacia, y dos de esos tres no son código que escribas solo.

**Recomendación honesta:**
- ADR-051: viable y valioso **como tesis/carta** (abrir conversación con
  Anthropic sobre tu forma de pensar). Como **ecosistema operativo**, primero
  resuelve B1 y B2 en papel; sin eso, construir slices es construir sobre arena.
- ADR-052: si lo quieres "completo", asúmelo como **multi-año con riesgo de
  abandono alto**, o redefine "completo" como "todas las capacidades a calidad
  beta, sello intacto, sin fecha". Una de las dos. "Completo + ya + perfecto" no
  existe para una persona.

El planteamiento no está mal. Está **incompleto en su viga maestra**, y eso es
distinto de "casi listo". La buena noticia: las dos piezas que faltan (completitud
del log, operador neutral) son problemas conocidos con soluciones conocidas
(transparency logs, attestation) — caras, pero no inventadas de cero.
