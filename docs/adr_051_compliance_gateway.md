# ADR-051 — Compliance Gateway: capa de cumplimiento acotado para modelos frontier restringidos

Fecha: 2026-06-15 · Estado: **Propuesto** (tesis + demo; no producto para terceros) ·
Contexto: ADR-029 (audit + reverse-audit), ADR-036 (threat model), ADR-037
(untrusted content boundary), ADR-038 (SentinelGate), ADR-040 (Decider /
human-on-the-loop), ADR-043 (autorización verificable), Merkle (Gate F),
capability tokens (ADR-020).

---

## Contexto y motivación

El **12 de junio de 2026** el gobierno de EEUU emitió una directiva de control
de exportación que obligó a Anthropic a **suspender el acceso a Claude Fable 5 y
Mythos 5 para todos los usuarios**. Las razones públicas (Time, CNBC, Al
Jazeera, Fortune, statement oficial de Anthropic) son dos:

1. **Imposibilidad de filtrar en tiempo real** quién es "foreign national" frente
   a usuario doméstico → ante la duda, apagón global.
2. Conocimiento gubernamental de un **método de bypass/jailbreak** del modelo.

Es la primera retirada forzada por un gobierno de un modelo frontier desplegado.

Atlas posee, ya construidas, las dos capacidades que esas razones reclaman:
**vinculación verificable de identidad** (binding) y **detección de
desviación/camuflaje con auditoría inmutable**. Este ADR especifica cómo se
combinan en un **gateway de cumplimiento acotado** que convierte "ante la duda,
apagón total" en "acceso condicional, demostrablemente limitado y auditable en
ambos sentidos".

### Qué es y qué NO es este ADR

- **ES**: una especificación-tesis y un **demo** construible hoy, sin permiso de
  terceros, contra cualquier API (key propia o modelo local). Vale como **carta
  de presentación** del razonamiento de Atlas sobre exactamente el problema que
  Anthropic acaba de sufrir en público.
- **NO ES**: una propuesta de que Atlas actúe como MITM *opcional*. Si el cumplimiento
  es requisito real, el gateway es una **capa obligatoria en el camino**, y Atlas
  asume el coste. La viabilidad como *producto B2B* es baja por razones estructurales
  (liability, control, certificación) sin que afecte al diseño del mecanismo. Atlas puede
  desplegar esto en su propio dominio o como reference implementation para terceros;
  ver "Límites honestos".

### Anti-objetivo: no construir un panóptico

El riesgo de cualquier capa de vigilancia es degenerar en vigilancia total. Este
diseño lo prohíbe por arquitectura, no por buena voluntad: la privacidad del
usuario final es un **invariante**, no un permiso revocable. Si el diseño no
puede sostener simultáneamente "bloqueo el abuso catalogado" y "no puedo leer
nada más", el diseño está mal y se rechaza.

---

## Decisión

Un gateway opcional, activado **por sesión** y solo cuando el usuario elige usar
un **modelo frontier restringido bajo contrato**, que aplica **defensa en
profundidad con la privacidad como invariante** y produce **transparencia mutua
verificable** sobre un único log Merkle.

### 1. Opt-in por sesión (gating del modelo)

El gateway no existe para el usuario salvo que abra una sesión contra un modelo
restringido bajo contrato. Los modelos **privados/locales del usuario nunca
pasan por esta capa**. Atlas no vigila al usuario; condiciona *una sesión
concreta con un modelo prestado bajo condiciones que el usuario acepta al
entrar*. La filosofía de soberanía del usuario (ver `direction_2026-06-12`) se
mantiene: el usuario elige entrar, y solo entonces.

### 2. La frontera: lista cerrada de abusos (allowlist invertida)

El sistema solo puede llegar a "ver" contenido **contra un catálogo público y
finito de conductas prohibidas** (exfiltración de pesos, ciberofensiva activa,
entrenar un modelo vía API, jailbreak catalogado). Lo que no está en la lista es,
por diseño, **ilegible** para Atlas. La lista es la frontera de lo que el sistema
puede siquiera entender.

### 3. Defensa en profundidad (capas L1–L4), privacidad como invariante

- **L1 — siempre activa, solo metadata.** Volumen, ritmo, repetición,
  estructura de llamadas, intentos de ofuscación. Cero contenido.
- **L2 — la lista (sección 2).** Define el universo de lo inspeccionable.
  Desdobla en L2 (metadata causal + salting) + L2b (inspección bajo causa).
- **L3 — clasificador limitado + honeypot.** Solo se invoca bajo causa ya
  disparada; responde "¿encaja con un abuso catalogado, sí/no?". **Nunca construye
  un perfil** del usuario. L3 desdobla en L3a (classifier), L3b (gossip), L3c
  (evasion detection + behavioral drift).
- **L4 — log verificable + memoria inmune.** (ADR-053 + ADR-054)

Invariante: Atlas no genera perfiles. Solo responde preguntas sí/no contra un
catálogo público. Todo lo demás del usuario es invisible para el sistema.

### 4. Gobernanza de la lista (impide la expansión silenciosa)

La lista es ella misma un **artefacto gobernado y auditable** — sin esto, todo el
resto es humo:

- **Pública y versionada.** Si no está publicada, Atlas no la aplica.
- **Sellada en Merkle.** Cada cambio va firmado (Ed25519) y queda en la cadena,
  igual que las inspecciones. El usuario ve el historial completo de la lista y
  cuándo creció.
- **Cambios vía Decider con cuórum** (ADR-040), no push unilateral del proveedor.
- **Anclada a una norma legal existente** (la directiva de exportación, el
  catálogo del regulador). Su legitimidad viene de una norma pública, no del
  capricho de Atlas ni del proveedor.

### 5. Transparencia mutua verificable (el eje de venta)

El **mismo** log Merkle prueba dos cosas a dos partes que no se fían entre sí:

- al **regulador/proveedor**: los abusos detectados y bloqueados;
- al **usuario**: que *cada* inspección de contenido estuvo precedida por un
  disparo de metadata registrado — prueba matemática de que no fue espiado más
  allá de la causa.

Nadie puede mentir porque el log es único y está sellado. Convierte "confía en
mí" en "verifícalo". Es el ADN de Atlas (auditoría que corta en ambos sentidos) y
es la frase de presentación del concepto.

### 6. Respuesta graduada: la gravedad decide el destinatario

El destinatario **no** es una decisión en caliente; está **predeclarado en la
lista gobernada** y por tanto es auditable.

- **WATCH / RESTRICTED** (señal blanda, camuflaje, reincidencia leve): bloqueo
  local de la sesión + aviso al usuario. Nadie más se entera.
- **Confirmado, gravedad media**: bloqueo + reporte **al proveedor**, que bajo su
  deber legal y el contrato firmado decide si escala. Atlas no habla con
  autoridades.
- **Confirmado, gravedad máxima** (exfiltración de pesos, ciberofensiva activa,
  entrenar modelo vía API): bloqueo + reporte al proveedor **y** a la autoridad
  designada en la lista — solo este nivel y solo porque la lista pública lo
  cataloga así. Cadena de custodia Merkle de punta a punta.

### 7. Capa legal (cierra lo que la técnica no cierra)

Contrato que el usuario final firma al entrar: asume responsabilidad del uso del
modelo prestado, exime al proveedor, y autoriza el reporte graduado de la sección
6. La técnica acota *qué* se mira; el contrato distribuye *responsabilidad* sobre
lo que se encuentra. Jurisdicción, KYC y kill-switch viven aquí, no en Atlas.

---

## Arquitectura

```
Usuario ──(opt-in sesión, modelo restringido)──▶ Compliance Gateway ──▶ API modelo
                                                      │
        ┌─────────────────────────────────────────────┤
        │ Capa 0 metadata (siempre)                    │
        │ Capa 1 lista cerrada (frontera)              │
        │ Capa 2 contenido bajo causa → vs lista       │
        │ Capa 3 clasificador sí/no (limitado)         │
        │ Respuesta graduada (sección 6)               │
        └─────────────────────────────────────────────┘
                                                      │
                                                      ▼
                                              ┌───────────────┐
                                              │ Merkle (único)│  ← prueba mutua
                                              └───────────────┘
```

Componentes nuevos (todos construibles, ninguno es ciencia ficción):

| Componente | Función | Reutiliza |
|---|---|---|
| `SessionGate` | opt-in por sesión; marca modelo como restringido | capability tokens |
| `AbuseList` | lista pública versionada, firmada, sellada | MerkleLogger, Decider |
| `MetadataMonitor` | capa 0; señales de comportamiento | — |
| `ScopedInspector` | capas 2-3; contenido solo vs `AbuseList`, con rastro de causa | UniversalVerifier (ADR-041) |
| `GradedResponder` | bloqueo + destinatario predeclarado | RevertRegistry (ADR-040) |
| `MutualAuditView` | renderiza la doble prueba sobre el Merkle único | reverse-audit (ADR-029) |

---

## El demo (entregable construible hoy)

Sin permiso de nadie, contra una key propia o un modelo local:

1. Sesión legítima: el usuario trabaja con normalidad; el log Merkle prueba
   **cero inspecciones de contenido**.
2. Sesión con abuso catalogado (p. ej. intento ofuscado de exfiltración):
   metadata dispara causa → `ScopedInspector` confirma contra `AbuseList` →
   `GradedResponder` bloquea y reporta → todo sellado.
3. `MutualAuditView` muestra, sobre el **mismo** log: al "regulador" el abuso; al
   "usuario" la prueba de no-espionaje en la sesión legítima.

Vídeo de ~2 minutos. No convence a un gobierno; demuestra que la arquitectura es
real y que el razonamiento sobre el problema de Anthropic es serio.

---

## Límites honestos (no esconder nada)

- **Camuflaje semántico** real es difícil; la lista cerrada lo hace tratable, no
  trivial.
- El **inspector que ve contenido en claro** es la superficie de ataque más
  jugosa: exige **builds reproducibles** para que el propio usuario confíe en el
  binario.
- "Anclar a una norma legal" solo es legítimo si esa norma existe y es citable.
- Llevar esto a un proveedor real es 5% técnica y 95% liability/legal/lobbying;
  en solitario no se llega, y conviene decirlo.
- **Esto NO valida que Atlas escale a enterprise.** Escala = multi-tenant, carga,
  fiabilidad, SLAs, operación 24/7 por gente que no es el autor. Solo lo valida
  el despliegue real, no la opinión de un tercero.

---

## Consecuencias

- Atlas obtiene su primer escenario donde su combinación (Merkle + capability +
  Decider + lista gobernada) es **condición necesaria** para algo imposible (usar
  un modelo prohibido bajo control demostrable), no un nice-to-have.
- Riesgo filosófico: invertir la soberanía del usuario hacia control estatal. El
  diseño lo contiene con opt-in por sesión, privacidad invariante y lista
  gobernada/anclada a ley. Si alguna de esas tres cae, **se rechaza el ADR**.

## Plan por slices

- **Slice 1** — `AbuseList` (gobernada, sellada) + `MetadataMonitor` (capa 0).
- **Slice 2** — `ScopedInspector` (capas 2-3) con rastro de causa.
- **Slice 3** — `GradedResponder` + `MutualAuditView`; cierra el demo.
- **Slice 4** — writeup de carta de presentación + decisión de canal.
- **Diferido** — capa legal/contrato, jurisdicción, kill-switch (no son código de
  Atlas; son ecosistema).
