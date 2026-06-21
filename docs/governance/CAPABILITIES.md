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

Pendiente de declarar al avanzar: shadow_model, gossip, behavioral, bwrap_jail (slices 2-5).
