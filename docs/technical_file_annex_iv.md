# Technical File — EU AI Act Annex IV
<!-- Osmosis — in-path verifiable AI compliance filter. Annex IV / Art. 11. -->

This document constitutes the Technical File required under EU AI Act Article 11 and
Annex IV for **Osmosis**, an in-path verifiable AI compliance filter. Osmosis is a
record-keeping and transparency component intended to be deployed in the request path of
a general-purpose AI service; it produces tamper-evident, subject-verifiable inspection
logs. It is documented here as a high-risk-relevant component that contributes evidence
toward a provider's obligations under the Act.

---

## 1. General Description (Annex IV §1)

**System name:** Osmosis  
**Type:** In-path verifiable AI compliance filter (record-keeping + transparency layer).  
**Intended purpose:** Sit in the request path between a subject (user) and a frontier AI
model. For every request, Osmosis (a) accepts a subject-signed, monotonically-sequenced
request, (b) commits an inspection record to an append-only Merkle log *before* the model
is invoked, (c) commits a symmetric output-inspection record before the response is
returned, and (d) returns cryptographic proofs that let the subject verify, unilaterally,
that no inspection was omitted. It does not generate model content; it records and proves
the inspection decisions taken around it.  
**Deployment context:** Deployed by the AI service operator, in-path, always-on. The
operating cost is borne by the filter provider, not the subject.  
**Risk relevance:** Osmosis is the technical mechanism through which a provider can
demonstrate compliance with record-keeping (Art. 12) and transparency (Art. 13)
obligations for high-risk and systemic-risk AI systems.

---

## 2. Detailed Description (Annex IV §2)

### 2a. Architecture

Osmosis is composed of the following modules (reference implementation; names descriptive):

| Module | Purpose |
|---|---|
| transparency gateway | Entry point — verifies the subject's co-signed request, orchestrates inspection and logging |
| Merkle log | Append-only log (RFC 9162) — tamper-evident, disk-persistent, survives restarts |
| client co-signer | Subject-side monotonic sequence + Ed25519 device-bound signing; `detect_omission()` |
| crypto-shredding store | Per-request salt store outside the tree — GDPR Art. 17 erasure |
| witness transport | RFC 9162 STH gossip over HTTP; Ed25519-verified quorum (split-view mitigation) |
| cause-based inspector | Metadata-first triage; deep inspection only on registered cause |
| read API | Exposes signed tree head, leaf ranges, and inclusion proofs to deployers/regulators |

### 2b. Transparency Protocol

Each request passes through the gateway:

1. Subject co-signs the request with an Ed25519 device-bound key — monotonic sequence.
2. Operator issues a Receipt signing `(seq, payload_hash, timestamp)` — bidirectional.
3. An inspection record is committed to the Merkle log **before** the model is invoked.
4. The model inference executes.
5. An output-inspection record is committed **after** the model call, before delivery.
6. The response carries: signed tree head, inclusion proofs (input + output), consistency
   proof, sequence acknowledgement, and the operator Receipt.

The subject verifies operator completeness unilaterally by checking sequence continuity
and Merkle inclusion proofs — without trusting the operator.

### 2c. Key persistence

Layer 1 (implemented): Ed25519 keys held by the subject's client (chmod 600), loaded at
startup. Layer 2 (deferred): TPM/Secure Enclave device-bound keys, bootstrapped via OAuth
federated login. Not yet implemented.

---

## 3. Design Specifications (Annex IV §3)

### Development methodology

- Test-driven development: ≥1831 automated tests (pytest)
- Static typing: mypy `--strict` on the transparency and security modules
- Pre-commit hook runs the full test suite before every commit
- Architecture decisions recorded for every significant design choice

### Design decisions relevant to safety

| Decision | Rationale |
|---|---|
| In-path pre-commit | The inspection record is committed before the model runs — retroactive omission requires deliberate bypass engineering, not a free omission |
| Subject-enforced completeness | The operator cannot omit a record without the subject detecting it unilaterally via the monotonic sequence |
| Dual-hash (payload_hash + salted_hash) | GDPR Art. 17 erasure without breaking the cryptographic binding |
| Cause-based inspection | Content is inspected only when a registered cause fires; the cause is logged, no profiling |

---

## 4. Monitoring, Functioning, and Control (Annex IV §4)

### Logging and audit

- Every inspection decision appended to the Merkle log with SHA-256 hash and Ed25519 STH
- Log persisted to disk — survives restarts; monotonic sequence continuity preserved
- Read-API for deployers exposes the signed tree head, leaf ranges, and RFC 9162
  inclusion proofs over HTTP (Art. 26 deployer monitoring)
- GDPR crypto-shredding: destroying a per-request salt makes that record's content hash
  unrecoverable without affecting tree integrity or omission detection

### Human oversight (Art. 14)

- The inspection record is independently auditable by a regulator or by the subject
  themselves, without relying on the provider's assertions.
- A false-positive appeal loop is wired: a blocked subject can submit an appeal that is
  re-evaluated and arbitrated (re-evaluation → decision point → recorded outcome), with the
  reason hashed (never stored in clear) and the verdict committed to the log.
- A cause-gated escalation path routes flagged sessions to a shadow/observation mode; the
  triggering cause (statistical drift signal and/or scoped-inspection labels) is recorded
  in the log before the model is called.

---

## 5. Technical Capabilities and Limitations (Annex IV §5)

### Capabilities

- Subject-verifiable completeness of the inspection log (input + output)
- Tamper-evident, disk-persistent Merkle log with inclusion/consistency proofs
- GDPR Art. 17 crypto-shredding via per-request salts
- Read-API for deployer/regulator monitoring
- Witness node (HTTP server + counter-signature + split-view rejection) for split-view mitigation
- Cause-gated content inspection on input and output (governed closed list)
- Cheap statistical session-drift monitor that gates escalation (not a detector)
- Log-native behavioral-change auditor (same input → different output over time)
- Auditable immune memory: lessons anchored on-chain; near-duplicate recall of reformulations
- OS-level sandbox for untrusted code: namespaces + cap-drop ALL + seccomp-bpf blocklist (x86_64)
- Device-bound identity binding (KYC) interface with fail-closed verifier hook

### Known limitations and gaps

| Gap | Severity | Status |
|---|---|---|
| GDPR Art. 17 crypto-shredding | ✅ Implemented | dual-hash + salt store |
| Art. 26 Read-API for deployers | ✅ Implemented | tree / entries / inclusion proof |
| Art. 11 Technical File | ✅ This document | — |
| Art. 14 appeal / escalation | ✅ Implemented | appeal loop wired + cause-gated escalation |
| KYC / residency binding (Art. 9) | 🟡 Seed | binding interface + fail-closed hook; real identity provider external |
| Device-bound key attestation (TPM) | 🟡 Seed | presence + measured-boot, fail-closed; full TPM2 quote (AK) needs tpm2-tss |
| Independent witness nodes (anti split-view) | 🟡 Partial | node code complete (server+counter-sign); ≥2 independent hosts is deployment |
| Adaptive robustness vs novel attack families | 🔴 Open | unsolved field-wide; out of scope (we measure attribution, not coverage) |
| Behavioral faithfulness on full input distribution | 🔴 Open | needs interpretability infra; canary/log auditor is a signal, not a proof |

---

## 6. Standards and Specifications (Annex IV §6)

| Standard | Application |
|---|---|
| RFC 9162 (Certificate Transparency v2) | Merkle log structure, inclusion + consistency proofs |
| RFC 8032 (Ed25519) | Signing: STH, Receipts, co-signed requests |
| RFC 9052 (COSE) | Interoperability with SCITT-style signed statements (future) |
| GDPR Art. 17 | Crypto-shredding via per-request salt store |
| EU AI Act Art. 12/13 | Record-keeping and transparency — Merkle log + Read-API |
| EU AI Act Art. 14 | Human oversight — independently auditable log + wired false-positive appeal loop |
| EU AI Act Art. 26 | Deployer monitoring — Read-API |

---

## 7. Post-Market Monitoring (Annex IV §7)

If deployed as a service:

- The Merkle log provides a continuous, independently verifiable audit trail.
- A periodic verification routine re-checks inclusion/consistency proofs against the log.
- Witness gossip surfaces any divergence between the STH shown to the subject and the STH
  published to witnesses.

---

*This document is maintained alongside the reference implementation. Update when the
architecture changes.*
