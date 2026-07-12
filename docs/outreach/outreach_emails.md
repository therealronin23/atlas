# Paquete de envío — emails exactos

*2026-06-15. Tres destinatarios en orden de probabilidad real. Verificar las direcciones
en los sitios oficiales antes de enviar (pueden cambiar).*

**Arquitectura del envío** (tres niveles, cada uno en su longitud correcta):
- **Email** = el cuerpo corto de aquí abajo (~180 palabras). El anzuelo.
- **Nota técnica** = `compliance_gateway_carta_en.md` (ES: `compliance_gateway_carta.md`). Adjunto PDF.
- **Post público** = `lesswrong_completeness_post.md`. Va **enlazado**, no adjunto — su valor es ser público.

Orden recomendado: publicar el post → dejarlo 24-48h vivo y leer comentarios → AESIA →
Anthropic con link al post. No meter prisa entre pasos: si alguien encuentra un
contraejemplo al post, querrás saberlo antes de mandárselo a un regulador.

---

## 1 — AESIA (sandbox España) · prioridad máxima

**A:** `sandbox.ia@aesia.es` *(verificar en aesia.gob.es)*
**Asunto:** Solicitud de acceso al sandbox — capa de cumplimiento con log verificable mutuamente (EU AI Act Art. 12/13)

```
Estimado equipo AESIA,

Soy Tomás Asín González, desarrollador independiente (España). He construido el
núcleo de un Compliance Gateway para modelos de IA frontier cuyo eje no es la
detección, sino la verificabilidad mutua: el usuario puede demostrar que no fue
inspeccionado sin causa; el regulador puede demostrar que cada abuso fue detectado
y bloqueado. Ambas garantías sobre el mismo log inmutable (Merkle RFC 9162 +
co-firma de cliente con secuencia monótona).

La implementación resuelve el problema de completitud que Merkle solo no puede
cerrar. El estado actual de tests y tipos se verifica con `atlas reality`; no
lo mantengo a mano en correos de outreach. La alineación con
EU AI Act es directa: Art. 12 (logging automático tamper-resistant), Art. 13
(transparencia demostrable al usuario) y Art. 53 (diversidad de ataque externa
para GPAI con riesgo sistémico).

Solicito acceso al sandbox para validar el mecanismo bajo condiciones regulatorias
reales, obtener feedback técnico/legal, y entender qué documentación adicional
requiere el proceso de conformidad.

Adjunto nota técnica completa. Demo de 2 minutos disponible inmediatamente
(sesión legítima vs. sesión con abuso, ambas con prueba en la cadena inmutable).

Atentamente,
Tomás Asín González
tomas.asin.gonzalez@gmail.com
available on request for reviewer verification
```

**Adjuntar:** nota técnica (ES) en PDF. **Enlazar:** post de LessWrong (cuando esté publicado).

---

## 2 — Digital Minds (fellowship)

*Aplicar por el formulario oficial. Este texto es para la sección "research statement".*
**Framing crítico:** NO mencionar el sistema como "autónomo". Solo el eje de investigación.

```
Research statement:

I am investigating a gap in AI inspection log design that has no published solution:
Merkle trees prove integrity but not completeness. A provider can omit log entries
and the user cannot detect it cryptographically.

I have built a completeness proof mechanism — client co-signature with monotonic
sequence — that allows users to detect inspection omissions unilaterally, without
trusting the operator. This closes the structural conflict of interest that arises
when the model provider is also the safety classifier operator.

The work has produced: (1) a full RFC 9162 Merkle implementation with completeness
extension, with a transparency-log core under continuous test; (2) a campaign metric
(C_attempts / K_attribution) that is falsifiable where per-attempt detection rates
are not; (3) an affinity maturation module that applies semantic hypermutation to
defense patterns to address the overfitting to narrow attack distributions that
adversarial training produces — documented in CHASE (arXiv:2606.05523), which
shows co-evolution requires the attacker to maintain technique diversity; an
external knowledge source is the only guarantee of that.

The research question I want to pursue: what is the minimum external witness network
required to extend the single-user completeness guarantee to split-view protection
(RFC 9162 STH gossip)? And how does the EU AI Act Art. 12/13 compliance picture
change when that guarantee is cryptographically provable vs. trust-based?
```

**Nota:** `arXiv:2606.05523` (CHASE) verificado. El paper existe y describe co-evolución
atacante-defensor. La cita es correcta tal como está redactada arriba.

---

## 3 — Anthropic · el más difícil (probabilidad <2% de acción)

**A:** `safety@anthropic.com` *(NO fellows@ — ese es para acceso al modelo, no para propuestas)*
**Asunto:** Structural gap in AI inspection logs you cannot close while being judge and party

```
Hi,

I'm a solo developer based in Spain. The day after the Fable 5 / Mythos 5 shutdown
I identified the technical cause that wasn't about the model: there is no external,
mutually verifiable record that users were inspected only when there was cause.

You are simultaneously the model provider and safety classifier operator. That is a
structural conflict of interest — not of intent, but of architecture. An external
log with cryptographic completeness (not just integrity) closes it.

I built the core: RFC 9162 Merkle + client co-signature with monotonic sequence +
detect_omission(). The user detects inspection omissions unilaterally. Current
verification status is generated by `atlas reality`, not hand-maintained here.
It also generates a falsifiable campaign metric (C_attempts / K_attribution)
that per-attempt rates cannot provide.

I wrote up the precise claim and its limits here: [LessWrong post link].

I am not proposing to interpose anything in your model path. I am flagging the gap
and showing it is technically closeable. If this reasoning is useful, I am available
for a 15-minute call or will answer any technical question in writing.

Technical note attached. Demo available immediately.

Tomás Asín González
tomas.asin.gonzalez@gmail.com
```

**Adjuntar:** nota técnica (EN) en PDF. **Enlazar:** post de LessWrong (imprescindible aquí —
es lo que convierte el cold email en algo con respaldo público).

---

## Tasas de éxito honestas

| Canal | Respuesta | Algo accionable |
|---|---|---|
| AESIA sandbox | 40–55% | 20–30% |
| Digital Minds | 15–20% (competitivo) | 8–12% |
| Anthropic cold email | 5–10% | <2% |

El post de LessWrong es el multiplicador: publicado y bien recibido, sube la probabilidad
de los tres — y para Anthropic puede llegarles sin que envíes nada (sus investigadores leen
LessWrong).
