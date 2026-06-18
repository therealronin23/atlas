# Technical File — EU AI Act Annex IV
<!-- ADR-055 / GAP-3 — generated 2026-06-18 -->

This document constitutes the Technical File required under EU AI Act Article 11
and Annex IV for Atlas Core as a high-risk AI system component.

---

## 1. General Description (Annex IV §1)

**System name:** Atlas Core  
**Version:** see `src/atlas/version.py`  
**Intended purpose:** Autonomous AI agent runtime with verifiable decision provenance.
Deployed as a personal AI assistant (single user, local deployment). Not deployed
as a general-purpose AI service to third parties.  
**Risk classification:** Provider self-assessment — high-risk features present
(autonomous code execution, agentic decision-making). Subject to Art. 6 + Annex III
where applicable.

---

## 2. Detailed Description (Annex IV §2)

### 2a. Architecture

Atlas Core is a Python-based AI agent with the following primary modules:

| Module | Purpose |
|---|---|
| `core/orchestrator.py` | Central dispatcher — classifies intent, routes to capabilities |
| `core/inference_hub.py` | LLM inference abstraction — local/remote providers |
| `transparency/gateway.py` | Subject-enforced completeness — signs every inference in/out |
| `transparency/log.py` | Append-only Merkle log (RFC 9162) — tamper-evident audit trail |
| `security/executor.py` | Code execution — ASTGuard + BwrapJail OS jail |
| `security/shadow_model.py` | Adaptive defense — honeypot/shadow routing |
| `core/decider/` | Decision point — autonomous / human / hybrid modes |

### 2b. Transparency Protocol (ADR-053)

Each inference request passes through `TransparencyGateway.call()`:

1. Subject cosigns request with Ed25519 (`ClientCosigner`) — monotonic seq
2. Operator issues Receipt signing `(seq, payload_hash, timestamp)` — bidirectional
3. `InspectionRecord` committed to Merkle log **before** model call
4. Model inference executes
5. `OutputInspectionRecord` committed **after** model call
6. `APIResponse` returned with: STH, inclusion proofs (input + output),
   consistency proof, seq_ack, Receipt

Subject can verify operator completeness unilaterally by checking seq continuity
and Merkle inclusion proofs — without trusting the operator.

### 2c. Key persistence

Layer 1 (implemented): Ed25519 keys in `~/.atlas/*.bin` (chmod 600), loaded at startup.  
Layer 2 (deferred — OSM-025): TPM/Secure Enclave device-bound keys, bootstrapped
via OAuth federated login. Not yet implemented.

---

## 3. Design Specifications (Annex IV §3)

### Development methodology

- Test-driven development: ≥1831 automated tests (pytest)
- Static typing: mypy `--strict` on transparency and security modules
- Pre-commit hook runs full test suite before every commit
- ADR (Architecture Decision Records) for every significant design choice

### Design decisions relevant to safety

| Decision | Rationale |
|---|---|
| Fail-closed code execution (ADR-055) | Without bwrap, Python execution blocked entirely — no insecure fallback |
| Subject-enforced completeness (ADR-053) | Operator cannot omit records without subject detecting it unilaterally |
| Dual-hash (payload_hash + salted_hash) | GDPR Art. 17 erasure without breaking cryptographic binding |
| PDP decider pattern (ADR-040) | Human oversight is one implementation of the decision point, not hardcoded |

---

## 4. Monitoring, Functioning, and Control (Annex IV §4)

### Logging and audit

- Every decision appended to Merkle log with SHA-256 hash, Ed25519 STH
- Log persisted to disk (`TransparencyLog(path=...)`) — survives restarts
- Read-API for deployers: `GET /api/exec/api/v1/log/{tree,entries,proof/inclusion/{i}}`
- GDPR crypto-shredding: `SaltStore.shred(seq)` makes per-user hashes unrecoverable

### Human oversight (Art. 14)

- `ATLAS_DECIDER=autonomous` — fully autonomous mode (current default)
- `ATLAS_DECIDER=human` — every action requires human approval
- `ATLAS_DECIDER=hybrid` — autonomous below risk threshold, human above
- **GAP noted:** Art. 14 compliance requires documented escalation procedure for
  autonomous mode. The PDP interface (`core/decider/`) supports this but no
  default escalation policy is configured.

---

## 5. Technical Capabilities and Limitations (Annex IV §5)

### Capabilities

- Local LLM inference (Nemotron, LiteLLM adapter)
- Code generation and sandboxed execution (BwrapJail)
- Autonomous self-maintenance (ADR-039) — proposes diffs, applies after validation
- Transparency log with Merkle inclusion proofs verifiable by subject
- Shadow routing (OSM-042) — adaptive defense against adversarial inputs

### Known limitations and gaps

| Gap | Severity | Status |
|---|---|---|
| GAP-1 GDPR Art. 17 — SaltStore wired | ✅ Closed | 2026-06-18 |
| GAP-2 Art. 26 — Read-API for deployers | ✅ Closed | 2026-06-18 |
| GAP-3 Art. 11 — This Annex IV file | ✅ This document | 2026-06-18 |
| GAP-4 KYC interface — Art. 9 risk mgmt | 🟡 Partial | Membrane hook defined, not implemented |
| Art. 14 escalation policy in autonomous mode | 🔴 Open | PDP exists, policy undefined |
| Witness network real transport (anti-split-view) | ✅ Closed | 2026-06-18 |
| Seccomp-bpf allowlist (ADR-055 Slice 2) | 🟡 Deferred | Requires libseccomp (external dep) |
| OSM-025 Capa 2 TPM key attestation | 🟡 Deferred | Design complete, no code |

---

## 6. Standards and Specifications (Annex IV §6)

| Standard | Application |
|---|---|
| RFC 9162 (Certificate Transparency v2) | Merkle log structure and inclusion proofs |
| Ed25519 (RFC 8032) | Signing: STH, Receipts, CosignedRequests |
| GDPR Art. 17 | Crypto-shredding via SaltStore |
| EU AI Act Art. 12/13 | Logging and transparency — Merkle log + Read-API |
| EU AI Act Art. 14 | Human oversight — PDP decider (partial) |
| EU AI Act Art. 15 | Robustness — BwrapJail, ShadowRouter, behavioral detection |

---

## 7. Post-Market Monitoring (Annex IV §7)

Post-market monitoring is not applicable to the current deployment scope (single-user
personal assistant, no third-party deployment). If deployed as a service:

- Merkle log provides continuous audit trail
- `audit_sample` daemon runs periodic verification against log
- Self-maintenance pipeline (ADR-039) monitors for CVEs via OSV.dev

---

*This document is maintained alongside the codebase. Update when architecture changes.
Source of truth for code state: `atlas reality --json`.*
