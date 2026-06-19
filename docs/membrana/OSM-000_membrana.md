# OSM-000 — La membrana: ósmosis de conocimiento exterior hacia el núcleo

Fecha: 2026-06-17 · Estado: **Aceptado** (meta-doc; define el mecanismo, no una capacidad) ·
Contexto: ADR-049 (organismo de conocimiento), `src/atlas/immunity/` (sistema inmune),
ADR-041 (UniversalVerifier / ley de entrada), ADR-040 (Decider/PDP), ADR-053/054 (gateway).

---

## Por qué existe esto

ADR-049 dio a Atlas un **organismo de conocimiento**: adquiere→verifica→acumula
información del exterior. Pero adquirir conocimiento no es lo mismo que convertirlo
en **capacidad**. Entre "Atlas ha leído sobre una técnica" y "Atlas la implementa en
su núcleo" hace falta un órgano intermedio: un sitio donde la idea entra, se desarrolla
en aislamiento, se prueba, y **solo cruza al núcleo si se demuestra que lo fortalece**.

Ese órgano es la **membrana**. El proceso de cruzarla es la **ósmosis**: paso selectivo
a través de una membrana semipermeable, sin forzar nada. El sistema absorbe lo que
sube su capacidad y rechaza —documentándolo— lo que no.

Esto NO es un cajón de ideas. Es el complemento de absorción del organismo:

```
   Mundo exterior (papers, chats, CVEs, feeds, MCP, skills)
        │
   [ADR-049: Source → KnowledgeArtifact → verificación capa 1 → columna]
        │   (adquisición + grounding)
        ▼
   ┌─────────────── MEMBRANA (docs/membrana/) ───────────────┐
   │  OSM-XXX  idea en desarrollo aislado                      │
   │     │                                                     │
   │  [compuerta: 5 criterios]  ←── ley de entrada + PDP       │
   │     │                          ▲                          │
   │   cruza?  ── no ──► Rechazado (documentado, queda)        │
   │     │ sí                                                  │
   └─────┼─────────────────────────────────────────────────────┘
         ▼
   Promoción a ADR-0XX canónico → implementación en el núcleo
        │
   El núcleo, ya más capaz, alimenta de vuelta al organismo (ADR-049)
```

## La compuerta: qué debe cumplir una idea para cruzar

Una OSM no se absorbe por ser interesante. Cruza la membrana solo si satisface los
cinco criterios. Son la misma disciplina que ya rige el resto de Atlas, aplicada a la
absorción de conocimiento externo:

1. **Verificable** — la afirmación que sostiene la idea pasa la capa 1 (ley de entrada,
   ADR-041): está fundamentada, no alucinada. Este criterio existe porque ya nos mordió:
   papers reales citados con afirmaciones falsas (CHASE, "Evolutionary Prompt
   Optimization") son exactamente lo que la membrana debe parar. Verificar que el paper
   existe **y** que dice lo que creemos que dice es parte de la compuerta, no un trámite.
2. **Coherente** — no viola los invariantes del gateway (I1–I5, ADR-054) ni el rumbo del
   proyecto: autonomía total + verificación de coherencia de intención sobre todos los
   generadores; el humano es un decisor intercambiable (PDP), no un acople fijo.
3. **Probado** — existe una demostración en aislamiento (tests) de que la capacidad hace
   lo que dice. Sin prueba, la idea sigue en difusión, no en la compuerta.
4. **Mantenible** — sin dependencias exóticas no justificadas (regla 6 de CLAUDE.md:
   stdlib primero; cualquier dep nueva se argumenta contra su alternativa stdlib).
5. **Sancionado** — el PDP (Decider, ADR-040) aprueba la promoción. La membrana propone;
   el decisor sanciona. Nunca se absorbe nada sin pasar por el punto de decisión.

## Ciclo de vida de una OSM (estados osmóticos)

| Estado | Significado |
|---|---|
| **Suspensión** | Idea registrada en el medio, fuera de la membrana. Identificada, aún sin desarrollar. |
| **Difusión** | En desarrollo activo como `OSM-XXX`: contexto, diseño, encaje en Atlas, límites. |
| **En membrana** | Desarrollada y bajo prueba contra los cinco criterios de la compuerta. |
| **Absorbida** | Cruzó. Promovida a `ADR-0XX` canónico e implementada en el núcleo. |
| **Rechazada** | No cruzó. Se documenta por qué y se queda como registro (el rechazo también es conocimiento). |

Numeración: `OSM-XXX` secuencial, **separada** de la secuencia canónica `ADR-0XX`.
Una OSM no es una decisión de arquitectura todavía — es una candidata. Al absorberse
recibe su número `ADR-0XX` y ahí queda registrado el cruce (`OSM-XXX → ADR-0XX`).

## Registro de candidatos (en suspensión)

Extraídos de los dos chats de exploración (`idea avance.md`, `idea avance 2.md`),
una pieza por entrada. Viabilidad = facilidad de cruce hoy, no valor.

| OSM | Pieza | Destino (capa/módulo) | Viabilidad | Estado |
|---|---|---|---|---|
| 001 | Métrica de campaña real (C_attempts, similitud embedding/Jaccard, K_attribution) | Capa 4 / gateway | alta | Suspensión |
| 002 | PPA — polimorfismo de estructura del system prompt | Capa 2 | alta | Suspensión |
| 003 | SessionSalt — randomización de hiperparámetros por sesión + registro en log | Capa 2 | alta | Suspensión |
| 004 | LLM Salting — rotación del refusal direction | Capa 2 | **bloqueada** (requiere activaciones; API externa) | Suspensión |
| 005 | Capa 3 señuelo — `ArtifactKind.DECOY` + generador de honeypots | Capa 3 | media | Suspensión |
| 006 | Persistencia y escala del log (append-only durable, compaction, pruning, memoización de subárboles, test 100k) | transparency | alta | Suspensión |
| [007](OSM-007_privacy_dp_log_crypto_shredding.md) | Privacy/DP del log — crypto-shredding (Merkle inmutable vs. GDPR Art. 17) | transparency | alta | **Difusión** |
| 008 | STRIDE threat model del gateway | seguridad | alta | Suspensión |
| 009 | Red-team simulado (VerifiedProducer vs bypass + omisión) | lab / immunity | alta | Suspensión |
| 010 | Anti-replay en co-firmas | transparency | alta | Suspensión |
| 011 | Mutador dual (semántico + character-level) para affinity maturation | immunity / Capa 5 | media | Suspensión |
| 012 | Co-evolución red-team: PromptFuzz-SC (fuzzing dual-space) | lab / panel adversarial | media | Suspensión |
| 013 | Co-evolución red-team: ACE-Safety / GS-MCTS (búsqueda MCTS de estrategias) | lab / panel adversarial | media | Suspensión |
| 014 | Defensa multimodal (`AttestedInspector`→imágenes + hash en Merkle) | transparency / inspector | baja (Atlas es texto hoy) | Suspensión |
| 015 | Capa ZK — circuito Halo2 de co-firma (inclusión + política sin revelar payload) | transparency | baja (horizonte) | Suspensión |
| 016 | Capa ZK — zRA / ZKSA attestation (reemplaza HMAC software) | transparency / attestation | baja (horizonte) | Suspensión |
| 017 | Capa ZK — PIRANHAS agregación recursiva zk-SNARK | transparency | baja (horizonte) | Suspensión |
| 018 | Capa ZK — Nova folding / IVC (agregación incremental de pruebas) | transparency | baja (horizonte) | Suspensión |
| 019 | ZKP de métrica de campaña (probar C_attempts ≥ K sin revelar prompts) | Capa 4 + ZK | baja (horizonte) | Suspensión |
| 020 | Hardware attestation roadmap (AMD SEV-SNP / AWS Nitro) | attestation | baja (infra) | Suspensión |
| 021 | Binding de identidad (WebAuthn / KYC-lite) | gateway / identidad | baja (legal+operativo) | Suspensión |
| 022 | Integración frontier API sin MITM (proxy + co-firma client-side) | interfaces | media | Suspensión |
| 023 | Modelo de despliegue + benchmarks de overhead (latencia de log/co-firma) | operacional | media | Suspensión |

Multi-tenancy del log **no** es candidata de membrana: es la siguiente decisión de
núcleo real → entra directa como `ADR-055`, no como ósmosis.

### Ola del chat 3 — Osmosis Filter (en Difusión)

De `idea avance 3.md`. Reorientación de producto: el gateway pasa a ser una capa de
cumplimiento **server-side, en el path, obligatoria**. OSM-024 es el padre; el resto son sus
mecanismos. Desarrolladas (cada una en su archivo), no ya en Suspensión.

| OSM | Pieza | Destino (capa/módulo) | Viabilidad | Estado |
|---|---|---|---|---|
| [024](OSM-024_osmosis_filter_server_side.md) | Osmosis Filter: capa de cumplimiento server-side obligatoria | gateway / transparency | media (incentivo de adopción) | **En membrana** (gateway implementado; enforcement no-bypass = política de producto pendiente) |
| [025](OSM-025_certificado_device_bound.md) | Certificado device-bound + firma automática por request | transparency / identidad | media (Layer 1 deployada; Layer 2 TPM deferred) | **En membrana** (Layer 1 Absorbida en ADR-053; Layer 2 diseño completo, cero código) |
| [026](OSM-026_doble_copia_merkle.md) | Doble copia del log Merkle (proveedor + usuario) | transparency / witness | alta | **Absorbida** (2026-06-18; nodos witness = infra pendiente) |
| [027](OSM-027_bucle_apelacion_falsos_positivos.md) | Bucle de apelación de falsos positivos con aprendizaje | governance / immunity | alta | Difusión (LessonStore + PDP existen; cableado del bucle appeal pendiente) |
| [028](OSM-028_inspeccion_por_causa_metadata_first.md) | Inspección por causa: metadata-monitor-first | Capa 1 / inspector | media | **En membrana** (`AttestedInspector` + `cause=` field en gateway implementados; monitor metadata-first completo pendiente) |
| [029](OSM-029_nucleo_rendimiento_rust.md) | Núcleo de rendimiento en Rust (Merkle + embeddings) | transparency | baja (coste de 2º lenguaje; prematura sin perfil) | Difusión |
| [030](OSM-030_posicionamiento_escudo_legal.md) | Posicionamiento de escudo legal + encaje EU AI Act | narrativa / carta | media (hipótesis jurídica sin abogado) | Difusión |

### Barrido de completitud (2026-06-17) — piezas rescatadas de los 3 chats

Repaso sistemático de `idea avance.md` / `2.md` / `3.md` para no dejar nada. Estas
piezas estaban en los chats pero no en el registro. Entran en Suspensión (sin desarrollar).

| OSM | Pieza | Destino (capa/módulo) | Viabilidad | Estado |
|---|---|---|---|---|
| 031 | SPARK / PRIVÉ — atestación de swarm anónima (familia ZK con [[OSM-016]]/[[OSM-017]]) | transparency / attestation | baja (horizonte; verificar paper antes de citar) | Suspensión |
| 032 | Rate-limiting / anti-spam del log (un atacante podría llenarlo — DoS del log) | transparency | alta | Suspensión |
| 033 | Dynamic System Prompt Rewriting por sesión (reformular instrucciones de seguridad) | Capa 2 | media (solapa con [[OSM-002]]/[[OSM-011]]) | Suspensión |
| 034 | Graded Responder + modo consentimiento pre-emptivo (estilo Netflix; consentimiento co-firmado en metadata sospechosa) | gateway / governance | media | Suspensión |
| 035 | Witness network externo (RFC 9162 STH gossip) — cierre real de split-view que [[OSM-026]] solo mitiga | transparency / ecosistema | baja (infra de ecosistema, no single-node) | Suspensión |
| 036 | Reproducible builds / atestación de build (confianza en filtro open-source) | build / attestation | media (distinto de [[OSM-020]] hardware) | Suspensión |
| 037 | JSON parsing robusto del LLM (json_repair / Instructor) | immunity / llm_scorer | — | **Rechazada**: ya se eligió stdlib `re`+`json`; dep nueva no justificada (regla 6 CLAUDE.md). El rechazo es conocimiento: queda documentado. |

### Segundo barrido (2026-06-17) — pieza núcleo rescatada

| OSM | Pieza | Destino (capa/módulo) | Viabilidad | Estado |
|---|---|---|---|---|
| [038](OSM-038_token_kyc_residencia.md) | Interfaz de token KYC/residencia (no hacer KYC, exigirlo y verificarlo) — **export-control, razón del apagón de Fable 5** | gateway / identidad | media-baja (legal+operativo) | **Difusión** |

Nota: el problema export-control aparece en los chats (`foreign national` ×13, `export` ×26,
`cambio de IP` ×4) pero no estaba como pieza propia. Empareja con [[OSM-021]] (identidad),
[[OSM-025]] (cert device-bound) y [[OSM-034]] (consentimiento Netflix-style). Refinada por el
barrido Gemini: separar *hacer* KYC (legal) de *exigir* un token KYC (código en el path).

### Pieza derivada de la sesión (2026-06-17)

| OSM | Pieza | Destino (capa/módulo) | Viabilidad | Estado |
|---|---|---|---|---|
| 039 | *decision/action provenance record* — registrar decisión/acción/causa (allow/block/inspect + por qué), atado a la petición firmada. **NO** chain-of-thought | transparency | alta | Suspensión |

Corrección que origina la 039: registrar el *razonamiento* del modelo (chain-of-thought)
como verdad-terreno es un claim mortal — el CoT puede ser racionalización post-hoc
(faithfulness). Se registra el **acto**, no el **pensamiento**.

### Barrido Gemini (2026-06-17) — contraste de auditoría externa

Auditoría de Gemini (`Gemini-Auditoría Técnica y Regulatoria de Atlas.md`). Señal/ruido
≈ 30/70. La membrana **filtra**: lo verificado y nuevo entra; lo basado en artefactos
archivados/inexistentes se rechaza (y el rechazo se documenta — también es conocimiento).
Cada punto se contrastó contra el código y los docs reales.

**Absorbido (válido tras contraste):**

| OSM | Pieza | Por qué entra |
|---|---|---|
| [007](OSM-007_privacy_dp_log_crypto_shredding.md) ↑Difusión | crypto-shredding (GDPR Art. 17) | Tensión Merkle-inmutable vs. derecho al olvido real; ya guardábamos hash, no texto, pero el hash de baja entropía es reidentificable. Salt por petición lo cierra. |
| [040](OSM-040_protocolo_red_race_conditions.md) nueva | race conditions de red | El demo es síncrono; un hueco de `seq` por fallo de red es hoy indistinguible de omisión maliciosa → negación plausible. Nuevo y válido. Alimenta paper §6.9. |
| [038](OSM-038_token_kyc_residencia.md) ↑Difusión | interfaz token KYC | Afina §6.5: Atlas no *hace* KYC, pero puede *exigir y verificar* un token de residencia y rechazar en el path. Eso sí es código. |
| 041 (Suspensión, abajo) | canal de transparencia al usuario (Art. 13) | Recurre 3× en Gemini (#7/#15/#29): criptografía en backend ≠ transparencia regulatoria; falta canal/UI que surface `detect_omission()` al humano. |

**Rechazado (ruido — basado en artefactos que no son el diseño real):**

- **"Filtro Osmosis basado en Regex es una muralla de papel" + solución DeBERTa/ONNX**:
  `content_filter.py` **no existe** (solo en `.venv/litellm/`); `antivirus.py`/`membrane.py`
  citados están **archivados** en `docs/archive/vscode_session_2026-06-17/` (trabajo divergente
  de VS Code, ya descartado). El diseño real es [[OSM-028]] (metadata-first + embeddings +
  reglas deterministas), que **nunca** fue regex-only. El *principio* (semántico > regex) ya
  está en OSM-028; no hay cruzada que hacer.
- **"No hay rollback transaccional" (#28)**: falso. ADR-040 ya tiene `RevertRegistry`
  (`src/atlas/core/decider/revert_registry.py`).
- **"Capability-based security necesaria" (#23/#26)**: Atlas ya lo tiene (capability tokens,
  `AtlasExecutor`, AST Guard). "Traductor de intención antes del kernel" = ADR-041
  UniversalVerifier, ya es el rumbo.
- **HMAC vs Ed25519 en README (#10)**: ya resuelto — el README dice Ed25519 (verificado).
- **device-bound = archivos en disco (#27)**: ya es límite §6.3 + [[OSM-025]] (hardware seguro).
- **Git/worktree loop, self-audit estancado (#9/#16/#17)**: descartado por el usuario (proceso
  de fondo conocido, ver [[project-loop-activated-2026-06-14]]).
- **seL4/agentic-OS, model drift, UX orgánica, latencia del Decider (#24/#25/#29)**: mezclan
  Atlas-OS con el filtro/paper (el usuario lo notó). Válidos para el roadmap de Atlas, fuera
  del alcance del paper de completitud. El #24 (inspección async/out-of-band) **rompería** la
  garantía de timing in-path (§3.2) — se documenta como tensión de diseño, no mejora.

**Idea estrella de Gemini, sobrevendida**: inyectar `sth_root` en el system prompt y que el
modelo lo haga eco para forzar orden temporal por criptografía (anti-retroactivo §6.8).
Buena dirección pero (a) requiere que el proveedor del modelo coopere → choca con la
circularidad §6.3; (b) los LLM hacen eco poco fiable de hex exacto; (c) el ancla probaría
"existió commit", no "hubo inspección real". Queda como future work, no como cierre.

### Pieza del barrido Gemini (2026-06-17)

| OSM | Pieza | Destino (capa/módulo) | Viabilidad | Estado |
|---|---|---|---|---|
| 041 | Canal de transparencia al usuario (Art. 13): surface el veredicto de `detect_omission()` + alertas de integridad a un humano (UI/notificación/interrupción), no solo en tests | interfaces / gateway | media (producto/UI) | Suspensión |

Origen: Gemini #7/#15/#29 (convergen). Criptografía sin interfaz no es transparencia
regulatoria. Empareja con [[OSM-027]] (bucle de apelación, ya tiene interacción de usuario).

### Sesión 2026-06-17 — capa 2 + defensa activa

| OSM | Pieza | Destino (capa/módulo) | Viabilidad | Estado |
|---|---|---|---|---|
| capa 2 (integrada) | Inspección simétrica de output: `OutputInspectionRecord` committed antes de devolver el resultado; checks 5+6 en `SubjectLedger.ingest()`; Session G en demo | `client_cosign.py` / transparency | alta | **Absorbida** (implementada 2026-06-17; ADR-053) |
| [042](OSM-042_shadow_model_active_defense.md) | Shadow model: defensa activa con honeypot pasivo/activo + red team dual-use. Detectado ataque → modelo sombra (Haiku) sustituye al real sin que el atacante lo note. Mismo componente como atacante sintético (red team periódico). | `src/atlas/security/shadow_model.py` + `red_team.py` | media-alta | **Difusión** (diseño 2026-06-17; implementación pendiente) |

### Sesión 2026-06-19 — CLOSE-NOW batch (autobuild lean) + triaje

Verificación previa contra código real antes de construir (decide-con-hechos):

| OSM | Pieza | Estado nuevo | Nota |
|---|---|---|---|
| 010 | Anti-replay en co-firmas | **Absorbida** | `ReplayError` + `_committed` en `gateway.py`; guard fail-closed antes de append/modelo. Cierra el claim §6.8 (idempotent retry → no hojas duplicadas) a nivel gateway. |
| 006 | Test de escala del log | **Absorbida** | `tests/test_transparency_scale.py` (10k entradas; inclusion+consistency verifican). Diseño escala a 100k+. |
| 039 | provenance record (decision/action/cause) | **Absorbida** (ya existía) | `InspectionRecord.decision` + `.cause` ya presentes; no era trabajo, solo verificación. |
| 008 | STRIDE threat model | **Cubierto** | Ya existe `docs/adr_036_threat_model.md`; extender al filtro Osmosis si hace falta, no reconstruir. |
| 032 | Rate-limit / anti-spam del log | **Difusión (aparcado)** | No over-engineering: improductivo *sin consumidor*. Su valor está en el wiring al gateway → fase de hardening/demo, no como util huérfano. |

### Sesión 2026-06-18 — promociones verificadas contra código real

Verificación previa: `PYTHONPATH=src python3 -c "import X"` para cada módulo antes de
promocionar. Ninguna promoción se basa solo en docs.

| OSM | Pieza | Código real | Promoción | Nota |
|---|---|---|---|---|
| [007](OSM-007_privacy_dp_log_crypto_shredding.md) | Crypto-shredding GDPR Art. 17 | `transparency/crypto_shred.py` → `SaltStore`, `InspectionRecord.salted_hash` wired | `En membrana` → **Absorbida** → ADR-053 | GDPR GAP-1 cerrado. `payload_hash` permanente (binding); `salted_hash` erasable. 12 tests en `test_crypto_shred.py`. |
| [026](OSM-026_doble_copia_merkle.md) | Twin log replicas: proveedor + sujeto | `transparency/log.py` → `path=` persistente + fsync; `transparency/gossip.py` → `HttpWitnessTransport` + `has_quorum(min_witnesses=2)` Ed25519-verified | `Difusión` → **Absorbida** | Límite honesto: nodos witness independientes = infra de ecosistema, no código. Split-view parcialmente mitigado. Paper §6.1. |
| [040](OSM-040_protocolo_red_race_conditions.md) | Semántica de red: retry vs. omisión atribuible | `transparency/client_cosign.py` → `attributable_omissions(receipted, observed)` + `OperatorReceipt` | `Difusión` → **Absorbida** → ADR-053 | Session F del demo. `tests/test_network_reconciliation.py`. Paper §6.8. |
| [042](OSM-042_shadow_model_active_defense.md) | Shadow model + honeypot cableado al gateway | `security/shadow_model.py` (`ShadowRouter`, `ShadowModel`, `ShadowMode`); `TransparencyGateway.__init__` acepta `shadow_router` + `shadow_model` | `Difusión` → **Absorbida** | Session H del demo. Tests de integración en `test_transparency_gateway.py`. |
| [054](OSM-054_behavioral_drift_detection.md) | Behavioral drift detection: 3 ángulos (delta, consistency, shadow) | `security/behavioral.py` → `BehavioralMonitor`, `BehavioralDelta`, `shadow_divergence`, `detect_covert_change` | `Difusión` → **En membrana** | Código existe y funciona; problema de investigación abierto (no detection guarantee). Paper §6.11 + Session J demo. No promover a Absorbida hasta que paper cierre los límites formalmente. |

---

## Glosario técnico (purga de nombres — autoridad de todo el proyecto)

Regla: **nombre técnico primario; el inventado solo como alias interno.** Un nombre inventado
presentado como término establecido induce alucinación de prior art en cualquier IA/revisor.

| Inventado | Nombre técnico (primario) | Alias |
|---|---|---|
| Filtro Osmosis | *in-path verifiable AI compliance filter* | Osmosis |
| membrana | *admission gate* (compuerta de admisión selectiva) | membrane |
| organismo de conocimiento | *external knowledge ingestion & verification pipeline* | — |
| afinidad maduración | *defense-pattern mutation & selection* (inspirado en affinity maturation, término real) | — |
| antivirus inmune | *adaptive defense layer* | (se elimina) |
| co-firma manual | *device-bound request signing* | co-firma |
| doble copia | *twin independent log replicas* (subject-held + operator-held) | — |
| (CoT auditable) | *decision/action provenance record* | — |
| métrica de campaña | *per-campaign cost metric* (C_attempts / K_attribution) | — |

## Arquitectura por etapas (filtro de ósmosis físico → producto)

Una *admission gate* (mecanismo único), dos usos: petición y conocimiento. Tres etapas:

| Etapa | Nombre técnico | Qué hace | OSM |
|---|---|---|---|
| 1 — Admisión | *request admission gate* | barrera selectiva del prompt: metadata-first → causa → inspección acotada | 028, 038, 034 |
| 2 — Defensa activa | *adaptive defense layer* | polimorfismo, señuelo, *defense-pattern mutation & selection* + *knowledge admission gate* (aprendizaje colectivo) | 002, 003, 005, 011, OSM-000 |
| 3 — Auditoría verificable | *transparency & attestation layer* | log Merkle/SHA RFC 9162, *device-bound signing*, *twin replicas*, screening de residencia, anomalía→consentimiento/KYC | 024, 025, 026, 030, 035, 039 |

## Decisiones de la sesión (2026-06-17) — para no perder el rumbo

- **Reorientación**: la carta de presentación es el **paper de completitud** (`docs/paper_subject_enforced_completeness.md`) + **demo**. El filtro/etapas son diseño de fondo, no la contribución.
- **Novedad estrecha**: aplicar el monitoreo-por-el-sujeto (patrón de CONIKS / Key Transparency) a *logs de inspección de IA* + *binding a la petición*. No reclamar el mecanismo en sí.
- **Fable 5 / export-control = contexto, no claim** (residencia no es resoluble en código).
- **Hablar del filtro, no de Atlas**, en todo lo público.

## Cómo entra material nuevo

Todo lo que llegue del exterior y merezca desarrollo entra como una OSM en **Suspensión**,
con una pieza por entrada. Se desarrolla (Difusión), se somete a la compuerta (En membrana),
y cruza o se rechaza. El registro de arriba es el punto de partida, no el techo: crece.
