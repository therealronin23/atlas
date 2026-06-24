# CAPABILITIES — manifiesto de honestidad (anti-overclaim)

Estado REAL de cada capacidad declarada. Regla `wire-before-claim`: nada se vende por
encima de su sustancia. Estados: **real** (código + consumidor + integración) ·
**andamiaje-software** (código real, pero no entrega la garantía que su nombre implica) ·
**no-cableado** (construido + unit-testeado, sin consumidor) · **no-existe** (solo en docs).

Actualizar al cerrar cada nodo. Última pasada: 2026-06-21.

| Capacidad | Estado | Nota honesta |
|---|---|---|
| Cadena Merkle / log de transparencia | **real** | núcleo, consumido por gateway/store; tests reales |
| `SqliteMemoryIndex` + abstracción + olvido (Fase 1) | **real** | motor cableado al inquilino de seguridad; ciclo de vida testeado |
| Drift tripwire (`drift.py`) | **real** | alimenta `confidence` del gateway (OSM-042) |
| ScopedInspector (OSM-028) | **real** | gobernado por causa, cableado al gateway |
| TPM / attestation (`attestation.py`) | **andamiaje-software** | HMAC-SHA256, NO raíz de confianza por hardware; documentado como software-only |
| WitnessServer (anti-split-view HTTP) | **no-cableado** → cuarentena 2026-06-21 | construido + testeado, 0 consumidores. Rescatar si se ensambla la red de ≥2 witnesses |
| LogBehavioralAuditor (OSM-031) | **no-cableado** → cuarentena 2026-06-21 | construido + testeado, 0 consumidores |
| KycBinding (operator KYC, EU AI Act GAP-4) | **no-cableado** → cuarentena 2026-06-21 | construido + testeado, 0 consumidores |
| ContentFilter / "antivirus" | **no-existe** | concepto en `docs/membrana/`, sin código ni tests. NO afirmar que existe |
| Transferencia cross-family (detección de intención) | **muro (tipo-3)** | coseno reconoce tema, no intención; contrastive sube el gap pero FP fronterizo ~33%. NO es detector usable |

| Capa de afinidad/maduración (affinity_maturation, scorers, llm_scorer) | **no-cableado** → cuarentena F3 2026-06-21 | es la DETECCIÓN que 1c midió que reconoce tema, no intención; 0 consumidores |
| gossip/witness (split-view RFC 9162) | **no-cableado** → cuarentena F3 | exige ≥2 operadores independientes (no existen); 0 consumidores |
| security_worker / fuzzing / red_team (en src) | **fuera de sitio** → cuarentena F3 | red-team en src viola ADR-056 (dev-only); security_worker sin uso |
| Lazo de aprendizaje AUDITABLE (live_loop + teacher_debate) | **cableado + probado** | test de integración end-to-end (gateway escala→GatedLessonRecorder→TeacherDebate→LessonStore→Merkle verify_chain). Funcional/probado; valor PLENO solo con tráfico vivo. Es procedencia auditable, NO detección |
| Knowledge missions (`knowledge/mission` + `knowledge/run.py`) | **cableado + funcional** | `run_mission()` consumidor no-test + integración (ingesta+verificación reales, camino feliz y rechazo). Funcional de verdad ya |
| Cónclave (`deliberation_council`) v2.0 — deliberación multi-voz | **cableado + probado (juez-único real; trío fiable 3/3 en vivo)** | maquinaria real (LlmReviewer+trío+gating+veredicto sobre adversarial_panel). v2.0 subió el trío de ~1/3 a **3/3 voces útiles** (smoke vivo 2026-06-24 post-fixes): Fix 0 `gemini_free`→`gemini-2.5-flash` (3.5-flash daba 503 crónico, era config no transitorio), Fix 1 reintento ante transitorios en `inference_hub` (allowlist 503/500/timeout/conn), Fix 2 parseo anclado a 1ª línea (Kimi ya no pierde detalle). Disponibilidad POR-LLAMADA; diseño fail-closed → fallo de un proveedor = MAJOR, no "sin objeción". Límite conocido: Kimi+Mistral comparten infra NIM (fallo correlacionado) → v2.0.5 fallback no-NIM. Side-effect de destilación = recorder inyectable (no cableado al LessonStore real aún) |

Pendiente de declarar al avanzar: shadow_model, behavioral, bwrap_jail (slices 2-5).
Deuda Cónclave: ✅ parseo del detalle de Kimi (v2.0) · ✅ reintento ante transitorios (v2.0) · pendiente: cablear `record_synthesis` al recorder real (teacher_debate/LessonStore) · v2.0.5 fallback de slot por-linaje (fallo correlacionado NIM).
