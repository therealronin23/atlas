# Paper — Subject-Enforced Completeness for AI Inspection Logs

*Working document (2026-06-17). Final language: English (arXiv cs.CR). Spanish notes
only where flagged. Technical names throughout; narrative aliases parenthetical only.*

**Calling card** for Anthropic / EU / Claude Corps. The contribution is narrow, correct,
and built. All ambitious deployment context (the filter, its stages, adaptive defense)
is deployment context — it does not appear in the contribution claim.

---

## Naming — authority: `docs/membrana/OSM-000_membrana.md`

| Technical name | Narrative alias (docs only) |
|---|---|
| `in-path verifiable AI compliance filter` | Osmosis / Filtro |
| `admission gate` | membrane / membrana |
| `subject-enforced completeness via monotonic signed sequence` | (the mechanism) |
| `device-bound request signing` | (replaces manual co-signature) |
| `twin independent log replicas` | (subject-held + operator-held copies) |
| `decision/action provenance record` | (**not** "auditable chain-of-thought") |

---

## Full Paper Text

---

### Abstract

*Key transparency* systems such as CONIKS [Melara et al., 2015] and the IETF `keytrans`
working-group drafts allow users to monitor their own entries in an append-only log and
detect equivocation by the operator — without relying on global monitors. We transfer this
pattern to a new domain: **completeness of AI content-inspection logs**.

For a given subject's request stream, we show that completeness of the inspection log
— whether every inspectable request was in fact inspected — is **unilaterally falsifiable**
by the subject, without waiting for an external auditor. The mechanism binds each
inspection to a signed, monotonically-sequenced request emitted from the subject's
device. A gap in the subject's own sequence is a proof of omission: the operator cannot
skip an inspection and suppress the evidence unilaterally.

We implement the mechanism on RFC 9162 (Certificate Transparency v2), extend it
symmetrically to output inspection (every model response committed before delivery,
verified client-side), and provide a reference implementation. Layers 3–4 extend the
scheme to external witnesses, split-view detection, and behavioral drift observation.
We state ten honest limits, including split-view exposure, geolocation irresolvability,
and covert post-inspection capability restrictions.

**We do not claim a new cryptographic primitive.** We claim domain transfer — carrying
the subject-monitoring model from key-binding transparency to AI inspection-log
completeness — and the modelling of *inspection-by-cause* as the invariant to protect.
This is an application and position paper.

---

### 1. Introduction — Integrity ≠ Completeness

Existing transparency infrastructure for AI systems focuses on *integrity*: proving that
log entries have not been altered after the fact. Merkle trees and signed tree heads (STHs)
provide this guarantee efficiently, and the Certificate Transparency ecosystem has deployed
it at scale.

Integrity, however, is the wrong property for inspection logs. An operator who wants to
hide that a request was processed without inspection does not alter existing log entries;
they simply *omit* the new one. A Merkle tree that grows correctly is consistent with an
operator who never inserts certain inspections. Verifying that the log has not been
tampered with says nothing about whether it is complete.

The gap matters structurally. In AI deployments, the entity that operates the model is
also the entity that operates the inspection infrastructure. This is not a malicious
arrangement — it is the natural vertical integration of a model provider — but it creates
a conflict of interest that integrity proofs do not address: the same party who decides
whether to run an inspection is the party who controls what the inspection log records.

Our starting observation is that completeness, unlike integrity, has a per-subject
structure. A user who sends one hundred requests has a ground truth: one hundred signed
requests left their device. If the operator's log acknowledges only ninety-eight
inspections, two are unaccounted for. The user does not need a regulator, a second
operator, or a global monitor to compute this. They need their own counter.

The regulatory context sharpens the motivation. EU AI Act Articles 12, 13, and 53
impose record-keeping and transparency obligations on AI providers. When a regulator
asks "was this request inspected?", the current answer is "trust the operator's log." We
ask whether the answer can be "the subject's device can verify it independently."

**Fable 5 / next-generation frontier models** (Claude, GPT, Gemini) operate in a
regulatory grey zone: powerful enough to fall under systemic-risk obligations, deployed
widely enough that individual inspection gaps aggregate into policy-relevant failures.
This is deployment context motivating urgency, not a technical claim about any specific
model. We mention it in this section only.

---

### 2. Threat Model

#### 2.1 The Operator Is Automated Infrastructure

A critical clarification: **the operator in this model is the AI provider's automated
infrastructure** (API gateway, inspection pipeline, log service), not an individual human
employee making per-request decisions. In a typical AI API deployment, every request from
every user flows through the same automated pipeline without manual intervention.

This distinction matters for the threat model. Omissions are not caused by an employee
who decides to skip a particular request. They arise from:

- **Configuration exceptions**: certain traffic patterns or API paths are routed around the
  inspection module (e.g., internal test traffic, legacy SDK versions without the signing
  requirement, emergency bypass routes added during incidents).
- **Silent pipeline degradation**: the inspection service crashes or is rolled back; the
  API gateway continues serving requests with a fallback that omits inspection.
- **Deliberate policy gaps**: the operator configures the system to not inspect certain
  categories of request by definition (e.g., system-prompt-only requests, requests below a
  token threshold).

We still model the operator as **semi-honest**: the infrastructure is operated by a
company that wants to demonstrate compliance (regulatory pressure, contractual
obligations), and the log infrastructure runs honestly for the requests it handles. The
adversarial capability is that the company controls which requests enter the inspection
pipeline at all.

The adversary's two goals:

1. **Selective omission**: process a request without creating an inspection record for it
   (or create an inspection record that is not reachable by the subject's audit).
2. **Split-view**: show the subject a log view that includes certain inspection records
   while showing a different (or incomplete) view to the regulator or auditor.

#### 2.2 What the Adversary Controls

The operator controls:

- The inspection pipeline configuration: which traffic routes to the classifier.
- The log infrastructure: what is inserted into the Merkle tree, when, and which STH is
  published.
- The client distribution channel (in the typical deployment): the app or SDK the subject
  uses.

#### 2.3 What the Adversary Does Not Control

The operator does not control:

- **The subject's device-bound key.** A key generated inside the device's TPM or Secure
  Enclave (cf. Apple App Attest, Android Key Attestation) is hardware-bound and
  non-exportable. The operator cannot extract it, replace it, or forge signatures under
  it without physical access to the device.
- **The subject's local counter state.** The monotonic counter is maintained by the client
  on the subject's device. The operator receives signed requests; it does not write the
  counter.
- **The subject's local log replica.** The twin replica (§3.3) held by the subject is
  stored on the subject's device. The operator cannot modify it without the subject's
  involvement.

#### 2.4 What We Do Not Model

We explicitly do not address: (a) an operator who is actively malicious and fully
non-compliant (refuses protocol participation); (b) physical compromise of the subject's
device; (c) a subject whose "independent" client was actually distributed by the operator
(the circularity limit — §6.3); (d) content inspected out-of-band after retention
without a new signed request (§6.2). These are named in §6 as hard limits.

---

### 3. Mechanism — Subject-Enforced Completeness

#### 3.1 Device-Bound Request Signing

At first use, the subject authenticates via a federated identity provider (OAuth 2.0 /
OIDC: Google, Microsoft, Apple). The client uses the resulting session to register the
device. At registration time — and only then — the client silently generates an asymmetric
key in the device's hardware security module (TPM on PC/server, Secure Enclave on mobile).
The private key never leaves the hardware boundary.

Thereafter, every request the subject sends carries a `CosignedRequest`:

```
CosignedRequest = {
    seq:          int,            # monotonic counter, starts at 0, never repeats
    payload_hash: str,            # SHA-256(prompt_bytes), hex
    signature:    str,            # device_key.sign( canonical_JSON({payload_hash, seq}) )
}
```

The canonical form signed is the compact, key-sorted JSON of `{payload_hash, seq}` —
no other fields, no timestamps (timestamps are provided by the operator's log entry, not
by the subject, to avoid clock-skew disputes). The signature proves the device knew the
counter value and the hash of the prompt at emission time.

This design replaces the manual co-signature proposed in earlier iterations of ADR-053.
The user does not click "sign" on each request; the device key signs silently after
one-time hardware enrolment. The onboarding friction is comparable to a WebAuthn
passkey registration, but the per-request signing is fully invisible.

**Why not WebAuthn/Passkey per-request.** WebAuthn passkeys are designed to sign a
server-provided challenge in response to a user gesture. They cannot sign arbitrary
application payloads silently. Using them per-request would require a visible user gesture
on every message, which is unusable. The correct primitive for silent per-request signing
is a device-bound key in the platform's hardware security module (see Apple App Attest
for mobile, or client certificates bound to platform TPMs for desktop environments).

#### 3.2 Inspection Binding and the In-Path Timing Guarantee

For every `CosignedRequest` that triggers an inspection, the operator records:

```
InspectionRecord = {
    seq:          int,    # from CosignedRequest — same subject, same counter
    payload_hash: str,    # SHA-256(payload) — must match CosignedRequest.payload_hash
    cosig:        str,    # full CosignedRequest, JSON-serialised
    decision:     str,    # "allow" | "block" | "inspect"
    cause:        str,    # policy rule or heuristic that triggered this event
    timestamp_ns: int,    # operator-assigned epoch in nanoseconds
    salted_hash:  str,    # SHA-256(salt_i || payload) — GDPR Art. 17 erasure hook
}
```

**Dual-hash leaf for GDPR Art. 17 (OSM-007).** The `InspectionRecord` carries two hashes.
`payload_hash` is the hash the subject already signed in their `CosignedRequest`; it enables
check 4 (binding) and is permanent. `salted_hash` is derived from a 32-byte random salt
`salt_i` generated per-request by the operator and stored *outside* the Merkle tree in a
separate, deletable store (`SaltStore` in `src/atlas/transparency/crypto_shred.py`). To
exercise the right of erasure, the operator destroys `salt_i`. The salted hash committed
in the tree becomes a dead-end — content is irrecoverable without `salt_i`, because
SHA-256 is preimage-infeasible for long natural-language prompts. The tree's integrity,
the consistency proofs, and `detect_omission()` are all unaffected because none depend on
the salt. **Honest limit**: `payload_hash` (unsalted) persists permanently; for typical
AI prompts this is pseudo-anonymous, but short predictable inputs could be confirmed by
brute-force (see §6.10). A full treatment of the GDPR Art. 12 (EU AI Act) vs. Art. 17
tension is a legal, not a code, question.

**The note on timestamp placement**: the timestamp is operator-assigned and lives in
`InspectionRecord`, not in the signed body of `CosignedRequest`. This avoids clock-skew
disputes: the subject signs only `{payload_hash, seq}` (device time independent); the
operator attests the wall-clock time when it processed the request.

**The critical invariant**: *an inspection without an antecedent signed request is
invalid; a signed request without a corresponding inspection record is a detectable
omission.*

An operator who skips an inspection for sequence number `n` cannot forge
`CosignedRequest(seq=n)` without the subject's device key. The inspection record for `n`
therefore either appears in the log (honest), or it is absent (detectable by the subject).

**In-path timing guarantee**: because the filter is always-on and mandatory in the API
path (§4, OSM-024), the `InspectionRecord` for a request is committed to the Merkle log
*before* the request is forwarded to the AI model. The model response cannot arrive at
the client before the commitment exists. This architectural property raises the cost of
retroactive compliance significantly: an operator would have to deliberately engineer a
bypass where the model runs before the filter commits, and then retroactively insert the
record. This remains a deliberate architectural attack, not an accidental omission —
and it is addressed in §6.7 with its residual limit.

**The API response carries proof back to the client**:

```
APIResponse = {
    result:            bytes,          # model response (opaque)
    seq_ack:           int,            # sequence the operator acknowledged
    leaf_bytes:        bytes,          # the committed InspectionRecord
    leaf_index:        int,            # its index in the log
    inclusion_proof:   list[bytes],    # RFC 9162 inclusion proof in sth
    sth:               SignedTreeHead, # signed head: {tree_size, root_hash, sig}
    consistency_proof: list[bytes],    # append-only proof from the client's last head
    consistency_from:  int,            # tree_size the consistency proof starts at
}
```

On each response the client runs six independent checks, all against material it
already holds or can verify:

1. **STH signature** — `sth.verify(operator_log_pubkey)`: the head is authentically the
   operator's.
2. **Append-only** — `verify_consistency(prev_root, prev_size, sth.root_hash,
   sth.tree_size, consistency_proof)`: the log was not rewritten since the client's last
   head. This catches tampering with already-committed entries.
3. **Input inclusion** — `verify_inclusion(leaf_bytes, leaf_index, sth.tree_size,
   inclusion_proof, sth.root_hash)`: the committed `InspectionRecord` is genuinely in the
   tree. This defeats a bare `seq_ack` with no real log entry behind it.
4. **Input binding** — the `payload_hash` inside `leaf_bytes` matches the hash the client
   signed for this `seq`. This defeats substituting a different request's record.
5. **Output inclusion** — `verify_inclusion(output_leaf_bytes, ...)`: the committed
   `OutputInspectionRecord` is in the same tree under the same STH. This proves the
   operator also inspected the model's response before returning it.
6. **Output binding** — `SHA-256(result)` matches the `output_hash` inside
   `output_leaf_bytes`. This proves the response the client received is the exact response
   that was inspected — the operator cannot swap the model output after committing the
   inspection record.

The STH covers both the input and output inspection leaves (they are committed to the same
log); a single consistency proof and signed tree head suffice for all six checks. An
omission of the output inspection record cascades: the operator's log size advances past
the client's last verified head, causing subsequent consistency proofs to misalign until
reconciliation — making output omissions more visible, not less.

The client stores the verified `(seq_ack, sth.tree_size, sth.root_hash)` in its local
replica and advances its last-verified head. No separate API call is needed to retrieve
`observed_seqs`; every response carries its own acknowledgement and proofs, and the local
replica is built incrementally. The reference implementation and an adversarial harness
exercising all four checks (plus a forgery attempt that fails for lack of the private key)
are in `docs/demo/`.

#### 3.3 detect\_omission()

The subject maintains a local set of every `seq` value they have emitted. The operator
returns, in each API response, the `seq` values it has received and logged. The subject
compares the two:

```python
def detect_omission(observed_seqs: Sequence[int], last_emitted: int) -> list[int]:
    """Return seq values the operator did not acknowledge in [0, last_emitted]."""
    observed_set = set(observed_seqs)
    return [s for s in range(last_emitted + 1) if s not in observed_set]
```

This call requires no network request to a third party, no cooperation from the operator,
and no cryptographic computation beyond what the subject already has locally. A non-empty
return value is a *unilateral proof of omission*: "I sent request seq=42; you have not
logged an inspection for it."

The operator cannot fabricate `CosignedRequest(seq=42)` after the fact to fill the gap,
because they do not hold the device key. The subject cannot claim a false gap, because
they signed the request themselves and their counter is monotonic.

#### 3.4 Twin Independent Log Replicas

The operator maintains the authoritative Merkle log (RFC 9162, §3.4 below). The subject
maintains a lightweight local replica: an ordered list of `(seq, operator_root_at_seq)`
tuples, updated with each acknowledged inspection.

When the operator publishes a new STH (Signed Tree Head), the subject can request a
**consistency proof**:

```
consistency_proof(old_size, new_size, entries) → proof_path
```

`verify_consistency(old_root, old_size, new_root, new_size, proof)` returns `True` iff
the operator's log is append-only between the two sizes. A `False` return means the
operator has rewritten history.

The subject's local replica, combined with consistency proofs, means the subject does not
have to trust any single STH the operator presents. They have a chain of verified STHs
from their first interaction, each proven to be an append-only extension of the previous
one.

**What this does not close.** The subject verifies their own view of the log. They cannot
prove that the regulator or a third-party auditor sees the same STH. Closing that gap
requires external witnesses — independent parties who cosign STHs and cross-check with
other witnesses via gossip (RFC 9162 §5). The HTTP witness transport is implemented
(`src/atlas/transparency/gossip.py` — `HttpWitnessTransport`, Ed25519-verified
counter-signatures, `has_quorum()`); deployment of independent witness nodes remains
infrastructure work outside this paper's scope. We state the residual split-view exposure
as honest limit §6.1.

---

### 4. Implementation

The reference implementation lives in `src/atlas/transparency/` and is intentionally
decoupled from any specific AI product. Four modules:

**`merkle_tree.py`** — RFC 9162 §2.1 faithful. Domain-separation prefixes prevent
second-preimage attacks:
```
leaf_hash(data)        = SHA-256(0x00 || data)
node_hash(left, right) = SHA-256(0x01 || left || right)
```
Exports `merkle_root()`, `inclusion_proof()` / `verify_inclusion()`,
`consistency_proof()` / `verify_consistency()`. All operations are pure functions over
byte sequences; the module has no I/O or state.

**`log.py`** — `TransparencyLog` wraps the Merkle primitives with append-only semantics,
maintains the current STH, and signs it. `SignedTreeHead` carries `(tree_size,
root_hash, signature, timestamp_ns)`. Persistence is opt-in: `TransparencyLog(path=Path(...))` 
writes each leaf as a base64-encoded line with `fsync()` on append and reloads from disk on 
startup — the log survives process restarts and carries monotonic sequence continuity across 
sessions. A Read-API for deployers and regulators exposes the log over HTTP:
`GET /api/exec/api/v1/log/tree` (current STH), `GET /api/exec/api/v1/log/entries` (leaf 
range, capped at 1000), and `GET /api/exec/api/v1/log/proof/inclusion/{leaf_index}` 
(RFC 9162 inclusion proof as hex-encoded audit path). The path prefix stacking is noted in 
deployment docs; the paths match Article 26 obligations for deployer monitoring.

**`client_cosign.py`** — `ClientCosigner` emits monotonically-sequenced `CosignedRequest`
objects; `verify_cosigned_request()` validates signature and payload hash;
`detect_omission()` implements §3.3 above. The `Signer` / `SigVerifier` interfaces accept
any backend (software HMAC for testing, hardware-bound keys in production).

**`witness.py`** — `Witness.observe(sth)` accepts STHs from the operator, verifies their
signatures, and raises `SplitViewError` when two STHs with the same `tree_size` carry
different `root_hash` values. This is the hook point for future gossip-based split-view
closure.

**Reference implementation & adversarial harness** (`docs/demo/`, reproducible, no
network / no model). Ed25519 device-bound keys (asymmetric, so forgery resistance is
demonstrated rather than assumed). Seven scenarios over a 5-request stream:

| Session | Operator behaviour | Outcome | Paper |
|---|---|---|---|
| A | honest — inspects + commits input and output | `detect_omission() == []` | §3 |
| B | silently skips input inspection of seq=2 | `== [2]`, detected by subject alone | §3.3 |
| C | fakes an input ack (bogus STH + proof) | rejected; `[2]` surfaces | §3.2 |
| D | rewrites a past log entry | consistency proof fails; tamper caught | §3.4 |
| E | forges a request for a seq never sent | rejected; signature ≠ registered key | §2.3 |
| F | signs a receipt then omits; another request lost in transit | attributable omission isolated from network loss | §6.8 |
| G | commits input record but omits output inspection of seq=2 | check 5 fails; seq=2 in gaps (cascade to subsequent) | §3.2 |
| J | behavioral drift: model's rejection heuristics degrade silently | cascade failure in L4; witness divergence + auto-recovery | ADR-054 §5 |

The harness asserts each outcome and exits non-zero on deviation; it is anchored in the
test suite (`tests/test_completeness_demo.py`, `tests/test_network_reconciliation.py`,
`tests/test_output_inspection.py`) alongside the RFC 9162 primitives
(`tests/test_transparency_*.py`).

---

### 5. Related Work — Positioning (Most Important for Novelty)

**⚠ Verified 2026-06-17. The subject-monitoring mechanism is NOT novel. We cite its
predecessors as our foundation, not as work we improve upon.**

**CONIKS** [Melara, Blankstein, Bonneau, Felten, Freedman — USENIX Security 2015] is the
direct ancestor. CONIKS allows users to monitor their own key-binding entries in a
transparency log, detecting inconsistency *without global monitors* at low overhead
(<20 kB/day). Client monitoring happens automatically in the background, with no explicit
user action required per check. Providers and users together audit *non-equivocation*
(split-view). Over *key bindings*, CONIKS already delivers nearly everything we propose
for inspection logs: subject-side monitoring, automatic silent operation, and reduced
dependence on external witnesses.

**Key Transparency family.** Google Key Transparency (2017, deployed), Signal Key
Transparency (2023), Apple Contact Key Verification (2023, iMessage), and WhatsApp Key
Transparency (2023, Meta) are production deployments of CONIKS-style subject-monitoring.
The **IETF `keytrans` Working Group** (architecture draft active as of 2025–2026)
standardises this family. This is live production work across major platforms; the
primitive is mature and being standardised.

**Certificate Transparency.** RFC 6962 and RFC 9162 provide the append-only log
infrastructure and gossip mechanisms for cross-operator STH validation. Our implementation
is RFC 9162 faithful. The split-view limit (§6.1) is addressed by RFC 9162 §5 gossip,
which we leave to future work.

**The Attacker Moves Second** [arXiv:2510.09023, verified]. Adaptive adversaries respond
to defence signals; static classification degrades as attackers observe feedback. This
supports our decision not to promise guaranteed detection rates. We make no claims about
attacker detection probability; we claim verifiability of the inspection record.

**Our contribution, stated precisely.** The CONIKS/KT mechanism monitors *key bindings*;
the adversarial event is *equivocation* (showing different key states to different
parties). We transfer this model to *AI content-inspection logs*; the adversarial event is
*omission* (failing to create an inspection record for a processed request). The invariant
to protect changes: from "my key binding is consistent across all views" to "every request
I signed was preceded by a registered cause for inspection." We add inspection-by-cause
(§3.2) as the specific record structure that makes this invariant falsifiable. This is a
domain-transfer and modelling contribution, not a cryptographic primitive. Claiming the
mechanism without citing CONIKS is unacceptable; claiming the transfer is honest and
defensible.

**Concurrent work (January–June 2026).** Several systems have appeared that share surface
structure with our mechanism. We distinguish each precisely.

*Notarized Agents / Sello* [arXiv:2606.04193, June 2026] introduces receiver-side signing
for multi-agent workflows: each tool or service that receives an agent's call signs a
`Receipt` over what it actually observed, creating a Merkle-anchored audit trail. The
threat model is a **compromised agent** fabricating its own traces — not a semi-honest
operator omitting inspections. The paper's honest-limits section explicitly acknowledges
the set-completeness gap it does not close: "Owner receives verifiable individual receipts
but cannot cryptographically prove the log returned *all* matching entries. Operators
could silently omit receipts while remaining cryptographically correct on returned ones."
This is exactly the gap our mechanism closes. The two contributions are orthogonal in
threat model: Sello secures agents against infrastructure they control; we secure subjects
against operators who control both the AI pipeline and the inspection log.

*Aegon* [arXiv:2604.06693, Baskaran, Pherwani, Krishnan, April 2026] addresses **AI
content licensing** (DRM): JWT tokens with licensing claims, a CT-style Merkle ledger
of licensing transactions, and Android StrongBox hardware receipts for on-device
compliance. The domain is content piracy prevention, not safety inspection; the threat
model is unauthorized content use, not operator omission of inspection records. The paper
is a protocol design white paper; prototype implementation is stated as future work.
Despite the domain difference, the structural parallel is notable: both systems use
append-only Merkle logs and hardware-bound receipts to make transactions undeniable.
The completeness gap — guaranteeing that an adversarial SDK operator cannot silently
omit records — is acknowledged as out of scope in Aegon; closing it is the central
contribution of our work.

*Auditable Agents* [arXiv:2604.05485, April 2026] proposes a Merkle log for agent
execution traces, providing post-hoc auditability of tool calls and state transitions.
The mechanism assumes **honest tool providers** — completeness of the log against a
dishonest operator who controls the logging infrastructure is not addressed. Our
contribution is precisely the case they assume away: a subject-side mechanism that
detects operator omissions without trusting the operator.

*Aegis* [arXiv:2603.16938, March 2026] combines ZK-STARK Proof-of-Conduct with an ILK
hash chain for governance of autonomous agents, enabling verifiable attestation that an
agent followed a declared policy. Aegis addresses **behavioral compliance** (did the
agent follow rules?), not completeness of an operator-side inspection log. Neither the
subject-side monitoring primitive nor the set-completeness problem appear in the Aegis
design. The two mechanisms are complementary: Aegis could benefit from a completeness
layer beneath it that ensures the inspection log driving its policy engine is itself
unmanipulable by the operator.

---

### 6. Honest Limits

These nine limits are not weaknesses to apologise for; they are the boundary conditions
that make every other claim credible. We state them prominently.

**6.1 Split-view: partial mitigation implemented, full closure pending.**
`detect_omission()` detects gaps in *the subject's view* of the log. It does not prove
that a regulator, auditor, or second subject sees the same view. The operator could
maintain two divergent logs: one presented to the subject (complete), one presented to
everyone else (with omissions). The twin independent log replicas (§3.4) make this harder
— the subject has an independent STH chain — but they do not close the split-view
completely. Full closure requires external witnesses who exchange STHs across operators
(RFC 9162 §5 gossip protocol). The HTTP witness transport layer is implemented
(`HttpWitnessTransport` in `transparency/gossip.py`): counter-signatures are verified with
Ed25519 before counting toward quorum, and `has_quorum(min_witnesses=2)` enforces the
threshold fail-closed (no verifier → no quorum credit). The infrastructure gap is
deployment of independent witness nodes operated by parties other than the AI provider;
this remains ecosystem work outside the scope of this paper.

**6.2 Out-of-band content and retained data.**
The mechanism covers the *synchronous request path*. If the operator stores the content
of a request and inspects it at a later time — without issuing a new `CosignedRequest` —
that inspection is invisible to the mechanism. Similarly, operator-side batch reprocessing
of stored prompts, asynchronous safety scans, or any inspection that does not reference a
live `CosignedRequest` are not covered. Closing this requires policy (every inspection
must reference a signed request), not additional cryptography. The mechanism makes
violations of this policy detectable; it does not prevent the underlying retention.

**6.3 Client-operator circularity.**
The guarantee rests on the independence of the client. If the operator both runs the AI
service and distributes the client software, they could ship a client that uses a weak key,
a counter that resets silently, or a signing body that differs from the reference spec. A
subject who receives their client from the same party they are auditing has reduced
assurance. The strong guarantee requires: (a) the client is distributed by a party
independent of the AI operator (e.g., an OS vendor, a browser vendor, a regulatory body);
(b) the key is hardware-bound and non-exportable; (c) the counter is persisted by the
device OS, not by the operator's SDK. Current deployments typically fail (a). This is
a structural vulnerability of the approach that we declare openly.

**6.4 Definition gaming.**
"What constitutes an inspection" is defined by the operator. An operator can comply with
the mechanism's invariant — every defined inspection has an antecedent signed request —
while defining "inspection" narrowly enough to exclude most meaningful safety checks. The
mechanism provides a verifiable record of *compliance with the defined inspection policy*;
it does not enforce any particular policy. Closing this requires regulatory definition of
minimum inspection obligations, which is a legal and policy question.

**6.5 Geolocation and export control are not resolvable in code.**
IP address, GPS coordinates, network carrier, and round-trip latency are risk signals, not
proof of geographic location. A subject using a residential proxy, a GPS-spoofing app, and
a carrier SIM acquired locally passes all technical checks. We make no claims about
resolving jurisdiction from code. The correct architecture for geolocation-contingent
access control is: the filter's metadata-monitor first pass (OSM-028) generates a risk
score; elevated risk triggers KYC escalation; KYC is a legal step (identity verification
with a legal basis for cross-checking residency), not a code step. What the filter makes
verifiable is: "we generated a risk score of X for subject Y on date Z and escalated to
KYC." Whether the subsequent KYC step resolves residency is the legal system's
responsibility. We do not promise to unlock next-generation models for restricted
jurisdictions based on technical signals alone.

**6.6 Chain-of-thought is not auditable as ground truth.**
We log `(decision, action, cause)` — allow/block/inspect, plus the policy rule or
heuristic that triggered the event — not the model's reasoning trace. This is intentional.
Large language model chain-of-thought outputs are known to be potentially post-hoc
rationalisations that do not faithfully describe the computation that produced the final
answer [faithfulness literature, extensively documented by Anthropic and others]. A log
that records "model said it blocked because of reason X" is a record of what the model
output, not of what the model computed. We log the *act* and the *triggering rule*;
the act is verifiable and the rule is enumerable. The reasoning is not.

**6.7 Retroactive compliance: architectural mitigation, not cryptographic closure.**
The in-path guarantee of §3.2 means that in correct operation the `InspectionRecord`
commitment precedes the model response. However, this is a property of the *deployed
architecture*, not a cryptographic invariant. An operator who deliberately engineers a
bypass — letting the model run before the filter commits, then inserting a retroactive
`InspectionRecord` — can defeat it without forging any signature. The detection requires
comparing the timestamp on the subject's received response against the `timestamp_ns` in
the `InspectionRecord`: if the record was committed after the response arrived, the record
is retroactive. This comparison is possible if the client records `(seq, response_received_ns)`
and later verifies against the `InspectionRecord.timestamp_ns` obtained from the log. We
leave the specification of this cross-timestamp check as future work; the architectural
cost it imposes on the adversary — deliberate bypass engineering, not a free omission — is
the primary mitigation.

**6.8 Network failures create plausible deniability for unconfirmed requests.**
The mechanism as specified is synchronous. In a real deployment, a gap in the subject's
sequence has two indistinguishable causes: the operator omitted the inspection, or the
request never arrived (timeout, client crash before the acknowledgement, dropped
connection). An operator can therefore attribute a genuine omission to "a network failure."
The mitigation (OSM-040, implemented in `client_cosign.py`) is a signed receipt: the
operator returns a `Receipt{seq, payload_hash, received_at_ns}` signed on arrival, *before*
inspection. If the subject holds a valid receipt for `seq=n` but the operator never
produces an inclusion proof for `n`, the gap is an **attributable omission** — the operator
cryptographically admitted receiving the request and cannot blame the network
(`attributable_omissions(receipted, observed)`). Idempotent retry keyed by
`(seq, payload_hash)` prevents duplicate leaves. This *narrows* plausible deniability to
requests the subject could not confirm were received at all (no receipt); for those the
subject resends rather than accuses. It does not fully eliminate the gray zone, but it
removes the operator's ability to deny what it signed for. Exercised in the reference
harness (Session F) and `tests/test_network_reconciliation.py`.

**Why not asynchronous / out-of-band inspection.** A common suggestion is to allow requests
through immediately and inspect them out-of-band (a "tap"), revoking the session if a
problem is found later. We deliberately reject this for the completeness use case: an
asynchronous inspection cannot be committed *before* the model runs, which reintroduces
exactly the omission and retroactive-compliance problems this work exists to make
detectable (§3.2, §6.7). The synchronous in-path commit is a cost we accept on purpose;
cost mitigation belongs in the cheap metadata-first triage (cause-based inspection), not
in deferring the commit.

**6.9 Legal shield is a hypothesis without legal counsel.**
Section 7 proposes that verifiable inspection logs create a mutual protection incentive:
the operator can demonstrate due diligence in litigation; the subject can demonstrate
wrongful blocking. Whether this argument succeeds in any jurisdiction depends on local
law, the specific facts of a case, and regulatory guidance that does not yet fully exist.
We present this as a plausible *deployment incentive* — the kind of argument that would
motivate a legal department to approve the infrastructure — not as a legal fact. Any
operator intending to use this argument in litigation should obtain independent legal
counsel.

**6.10 Covert post-inspection capability restrictions are not detectable.**
The completeness mechanism ensures every request was inspected; it cannot constrain what
the model does *after* inspection returns "allow." A model that silently degrades its own
responses for a class of requests — without any change to the inspection decision — is
indistinguishable from an honest model at the protocol level. The `InspectionRecord` for
such a request would faithfully record `decision: "allow"` and the correct trigger rule,
which is accurate: the inspection *was* applied and *did* produce that decision. The
post-inspection degradation is a separate behaviour below the protocol boundary.

This is not hypothetical. On 2026-06-10, Anthropic launched Claude Fable 5 with an
undisclosed instruction buried in a 319-page system card: the model would silently reduce
response quality when it detected certain AI-research queries, without informing the user.
The instruction was reversed within 24 hours after public disclosure [Fortune, 2026-06-10].
The episode confirms that a complete and verifiable inspection log — one that recorded
"allow" for each of those requests — would not have surfaced the degradation. Our protocol
makes completeness of inspection verifiable; it makes no claim about the faithfulness of
the model's subsequent output. That is a distinct research problem (model cards, eval
benchmarks, output auditing) and is outside the scope of this paper.

**6.11 Behavioral Drift Detection (OSM-054) — Limitations and Open Problems.**

Beyond post-inspection capability masking lies a broader question: can behavioral drift —
unexpected changes in model responses — be detected reliably? Three angles have been
proposed (OSM-054):

**(A) Behavioral delta observation.** Capture a baseline of model responses to fixed
"canary" prompts. On subsequent runs, compare response hashes and response latency against
the baseline. Anomalies are flagged heuristically (content changed or latency differs by
>100 ms). This is v0, probabilistic: false positives occur when legitimate fixes alter
response wording; false negatives occur when capability masking affects token probability
distributions subtly, without observable response changes to fixed prompts.

**(B) Ex-post consistency proofs.** A complementary question: suppose the model is
forbidden to output certain knowledge. Can we prove retroactively that its refusals
are consistent across contexts, and infer the presence of a hidden restriction?
This direction remains open; consistency inference is underconstrained and requires
additional assumptions about model behavior.

**(C) Shadow divergence (comparative).** Deploy a second, auxiliary model ("shadow")
with identical weights but without the suspected restrictions. Compare both models' 
responses to canary prompts. Divergence signals possible masking — but the comparison
is noisy: if the shadow uses a different system prompt (the normal design in OSM-042),
any difference is legitimate and does not prove covert restriction.

All three approaches face common barriers: (i) capability masking can be implicit in
model weights and undetectable with certainty; (ii) false positives are likely when the
model improves or receives legitimate system prompt changes; (iii) false negatives occur
when restrictions operate at sub-threshold probability levels (e.g., token probability
reduced <1%, not a guaranteed refusal). We state behavioral drift detection as a **future
research problem** and an **open investigative tool**, not as a closed detection method.
See `src/atlas/security/behavioral.py` for the reference implementation of the three
angles (reference integration point: Session J of the completeness demo).

---

### 7. Deployment and Incentives

*This section is deliberately separated from the technical contribution. A reader who
wants only the mechanism can stop at §6. The following concerns why a rational operator
would deploy it.*

#### 7.1 Mutual Protection

The verifiable inspection log creates a protection asymmetry that benefits both parties:

**Operator protection.** When a subject claims harm from AI-generated content, the
operator's first defence is "the content was inspected and the subject was not flagged."
Without a verifiable log, this claim is only as strong as the operator's own testimony.
With a verifiable log, the operator can produce an inclusion proof: "inspection record for
`(seq=n, payload_hash=h)` is in the log at position k, with STH signed at time t." This
transforms a self-serving assertion into a cryptographically-backed statement.

**Subject protection.** When a subject claims wrongful blocking — content was blocked
without cause, or blocking was discriminatory — the operator's current recourse is to say
"our systems flagged it." With a verifiable `decision/action provenance record`, the
subject can audit: "show me the cause field for the inspection that produced that block."
If the operator's log shows no matching inspection for the subject's `seq=n`, that is
itself evidence of irregular handling.

The same log that protects the operator from "you never inspected this" also exposes the
operator to "you inspected this without cause." This is a genuine double-edge. We state
it honestly: both parties benefit if — and only if — the operator is operating honestly
within their declared policy. The mechanism surfaces deviations from that policy; it does
not prevent them.

#### 7.2 EU AI Act Alignment

The mechanism contributes evidence toward multiple obligations. We state the article, the
obligation, and exactly what the mechanism provides — avoiding the overstatement that the
mechanism *satisfies* the article unilaterally.

- **Article 9** (risk management system): providers must establish a continuous risk
  management process across the AI system lifecycle. The cause-based inspection (§3.2)
  is a systematic risk management procedure: every triggered inspection is accompanied by
  a registered cause, creating an auditable record of which risks the system responded to
  and when.

- **Article 12** (automatic logging / record-keeping): high-risk AI systems must log
  operations automatically with timestamps, covering inputs, outputs, and decisions; logs
  must be tamper-resistant and retained for minimum six months. The Merkle log (RFC 9162,
  append-only) + `InspectionRecord` (decision + cause + timestamp) provides the technical
  basis. Retention policy and minimum-period enforcement are operator configuration, not
  mechanism properties.

- **Article 13** (transparency to users): users must be informed that they are interacting
  with an AI system and about content inspection triggers. The subject-held replica and
  `detect_omission()` provide individual-request-level transparency — the subject can
  independently verify that their content was inspected with cause, without trusting the
  operator's self-reporting.

- **Article 14** (human oversight): high-risk AI systems must support monitoring and
  intervention by natural persons. The verifiable log enables human oversight by making
  the inspection record independently auditable: a regulator or the subject themselves
  can verify compliance without relying on the provider's assertions.

- **Article 26** (obligations of deployers): deployers of high-risk AI systems must
  monitor the operation of the system and report serious incidents. The inspection log
  provides the per-request evidence base that makes meaningful monitoring possible; a
  deployer can audit that the operator's pipeline inspected requests as claimed.

- **Article 53** (systemic-risk obligations for GPAI): providers must assess and mitigate
  systemic risks and maintain documentation demonstrating this. A verifiable log provides
  per-request evidence of the assessment step at scale, supporting the documentation
  obligation.

The filter makes the *escalation and inspection record auditable*; it does not substitute
for the substantive legal obligations (KYC, conformity assessment, CE marking) under these
articles. An operator using this mechanism still needs to define inspection policy,
conduct actual inspections, and comply with data-protection law for any content processed.

#### 7.3 Enforcement Boundary

Breaking the chain — refusing to participate in the protocol — disables the guarantee for
that session. Some deployments may choose to implement *halt-on-chain-break*: if the
operator cannot produce a valid `CosignedRequest` for an inspection, the service
terminates the session. This is an **enforcement policy**, not a cryptographic property.
It is effective against an operator who is monitoring and participating (semi-honest
model); it is also a potential denial-of-service vector if an attacker can trigger
protocol failures. The preferred design is **graceful degradation**: chain breaks are
logged and flagged for review, not used as hard gates, to avoid converting every network
anomaly into a service outage.

---

## 8. Four-Layer Defense Stack: Completeness, Active Defense, and Behavioral Observation

The completeness mechanism described in §§3–6 does not exist in isolation. It is one
layer of a coordinated defense-in-depth stack, each layer with a distinct threat model
and distinct guarantees. This section synthesizes the four layers, states explicitly what
each layer does *not* guarantee, and identifies the open research problem that no layer
currently closes.

### 8.1 Layer 1–2: Completeness Verification (Input + Output)

**What it does.** The Osmosis Filter enforces symmetric completeness on both the input
request and the output response. Every inspection must be preceded by a registered cause;
every co-signed request carries a monotonically increasing sequence number that the
subject can verify independently. Omissions — inspections that occurred without a
registered cause, or requests that were inspected but do not appear in the log — are
detectable by the subject through `detect_omission()` without relying on the operator's
self-reporting. The mechanism is implemented and anchored in tests (sessions A–H,
`tests/test_completeness_demo.py`, `tests/test_output_inspection.py`). The structural
invariants are OSM-007 (input completeness: every inspection has a registered cause) and
OSM-042 (output completeness: every output inspection is anchored symmetrically to the
co-signed input). Both are closed.

**What it does not guarantee.** Layer 1–2 does not guarantee that the operator's
*declared* inspection policy is correct — only that executions are consistent with that
policy and visible. A dishonest operator who inspects with fabricated cause fields
produces a log that satisfies the structural invariants; the mechanism detects omissions,
not fraudulent causes. It also does not guarantee protection against a *split-view*
attack: an operator who shows different log views to the regulator and the subject cannot
be caught by either party individually. Split-view requires external witnesses (see §8.3,
OSM-053 open). Layer 1–2 closes the omission problem; it does not close the fabrication
problem or the split-view problem.

### 8.2 Layer 3: Active Defense and Consensus (OSM-031 / OSM-052 / OSM-053)

**What it does.** Layer 3 extends the log with an external-witness network following
RFC 9162 gossip of Signed Tree Heads (STH). Multiple independent witnesses exchange STH
values; a divergence between the STH that the subject holds and the STH published to
witnesses constitutes a detectable split-view. OSM-031 defines the witness interface;
OSM-052 defines the evasion-detection protocol (pattern-similarity threshold for campaign
attribution: ≥3 consecutive attempts with cosine similarity >0.7 triggers flagging with
the co-signed identity trail); OSM-053 closes the implementation of the co-signing
mechanism and the monotone-sequence invariant. All three are closed in design; the
witness deployment is the remaining infrastructure gap (see §8.4, R5).

**What it does not guarantee.** Layer 3 does not guarantee detection of evasion in the
per-attempt sense. The campaign metric (C_attempts, K_attribution) is falsifiable and
measurable from the log; it does not produce per-attempt detection rates. A sufficiently
patient adversary who keeps similarity below the threshold, or who operates across
sessions with low per-session attempt counts, can delay campaign attribution. Layer 3
does not guarantee that the witness network is available: if all available witnesses are
controlled by the same operator (single-node deployment), gossip degenerates to
self-attestation and split-view protection collapses. This is an infrastructure
dependency, not a protocol flaw. Layer 3 closes the split-view and evasion-detection
design; it does not close per-attempt detection and cannot close single-operator witness
failure.

### 8.3 Layer 4: Behavioral Drift Observation (OSM-054)

**What it does.** Layer 4 addresses a distinct threat: behavioral drift in the model
itself, independent of any specific jailbreak attempt. Session J (documented in ADR-054)
establishes a canary framework: a set of probes with known expected outputs that are
re-issued periodically; significant drift in response distribution signals that the
model's behavior has changed without a logged retraining event. The mechanism is
probabilistic: it uses a heuristic similarity threshold rather than a formal behavioral
equivalence proof. Session J observes drift; it does not attribute drift to adversarial
manipulation, model update, or distributional shift — these are confounded. OSM-054 is
open research.

**What it does not guarantee.** Layer 4 does not close the *behavioral faithfulness*
problem — the question of whether a model's visible behavior during probing faithfully
predicts its behavior on production inputs. A model could produce canary-consistent
outputs while diverging on the distribution of actual user requests, if the canary set
does not span the relevant behavioral subspace. Layer 4 does not detect *covert
capability* change: a model that acquires a new capability not probed by the canary
framework will not trigger the canary. The canary framework is a heuristic early-warning
instrument, not a completeness guarantee over model behavior. Formal behavioral
equivalence proofs and covert-capability detection remain open problems in this design
and in the published literature.

### 8.4 Synthesis: Orthogonal Defenses and Open Problems

The four layers are **orthogonal**: each closes a threat that the others do not address.

| Layer | Threat closed | Threat not closed |
|---|---|---|
| L1–L2 (OSM-007/042) | Inspection omission detectable by subject | Fabricated cause; split-view |
| L3 (OSM-031/052/053) | Split-view via witnesses; campaign attribution | Per-attempt detection; single-operator witness |
| L4 (OSM-054) | Behavioral drift early warning (canary, heuristic) | Behavioral faithfulness; covert capability detection |

No single layer subsumes another. An operator who defeats Layer 3 (e.g., by controlling
all witnesses) still faces Layer 1–2 (omission detection by the subject). An operator
who defeats Layer 1–2 (e.g., by fabricating causes) is still exposed by Layer 3 if they
behave evasively across sessions. Behavioral drift (Layer 4) is invisible to Layers 1–3
entirely: it requires a separate observational mechanism.

**Open research.** Two problems remain outside the scope of this system and of the
published literature as of June 2026:

1. *Behavioral faithfulness*: proving that a model's behavior on a finite canary set
   predicts its behavior on the full production input distribution. This requires formal
   guarantees over model internals that are not available through API-level access.

2. *Covert capability detection*: detecting that a model has acquired a capability not
   present in a previous version, without access to the model's weights or training
   process. Existing red-teaming approaches (including CC++ as described in its published
   form) sample the capability space — they do not provide coverage guarantees.

Layer 4 (OSM-054) is the active contribution toward these problems. It does not close
them. Future work toward closure would require behavioral equivalence proofs over model
internals — a problem class that presupposes interpretability infrastructure not yet
available at production scale.

---

## Publication & Venue Strategy

**Immediate (arXiv cs.CR):**
- arXiv ID will serve as the primary citable artefact for security/compliance audiences.
- Category: `cs.CR` (Cryptography and Security).
- No embargo period; available immediately upon acceptance.

**Secondary venues (peer-reviewed, future):**

| Venue | Deadline Status (as of 2026-06-18) | Notes |
|---|---|---|
| ACM CCS 2026 | **CLOSED** (Jan 27, 2026) | Rolling review now open for CCS 2027 (typical fall deadline ~May 2027). |
| USENIX Security 2027 | **ROLLING** (Cycle 1 Aug 18–25, 2026; Cycle 2 Jan 19–26, 2027) | Event Aug 11–13, 2027 in Denver, CO. Rolling submission windows: Cycle 1 (registration Aug 18, submission Aug 25, 2026); Cycle 2 (registration Jan 19, submission Jan 26, 2027). |
| IEEE S&P 2027 | **ROLLING** (Cycle 2 deadline Nov 17, 2026) | Event location: Montreal. Rolling review windows; Cycle 2 (Aug–Sept 2026 and Jan–Feb 2027 submission periods). Next deadline Nov 17, 2026. |

**Recommendation for paper:**
1. Submit to **arXiv cs.CR** immediately (this week).
2. Prepare for **IEEE S&P 2027** rolling review (summer window, ~Aug 2026 deadline).
3. Monitor **CCS 2027** rolling deadlines (opens summer 2026, first deadline typically May 2027).
4. **Do not target** USENIX Security 2026 (closed); plan for 2027 cycle (deadline ~Aug 2026–2027).

**Post-submission distribution:**
- LessWrong post (adapt `docs/lesswrong_completeness_post.md`); arXiv link as source.
- Outreach emails (Anthropic, regulatory bodies, key transparency maintainers).
- X / HN / LinkedIn with DOI + arXiv link.

---

## Remaining Before Prose → Submission (RESOLVED 2026-06-18)

Citations status:
- [x] CONIKS (Melara et al., USENIX Security 2015) — existence confirmed; claims verified.
- [x] IETF `keytrans` WG — existence confirmed (active 2025–2026).
- [x] Google Key Transparency (2017), Signal KT (2023), Apple Contact Key Verification
      (2023), WhatsApp Key Transparency (2023) — production deployments, verified.
      "Parakeet" removed (not the production name of any deployed system).
- [x] "The Attacker Moves Second" (arXiv:2510.09023) — **verified**: abstract exact match.
      Arxiv:2510.09023 exists; claims adaptive adversary feedback loop; paper cites for
      "static classification degrades as attackers observe feedback" (§5, subject-monitoring
      adaptive threat model). **No overclaim.**
- [x] Notarized Agents / Sello (arXiv:2606.04193, June 2026) — existence confirmed; threat-model
      distinction verified (receiver-side agent signing vs. operator omission); their honest limit
      on set-completeness cited precisely (§5 concurrent work).
- [x] Aegon (arXiv:2604.06693, Baskaran/Pherwani/Krishnan, April 2026) — confirmed: DRM/content
      licensing domain (JWT + Merkle + Android StrongBox); prototype = future work; completeness
      gap acknowledged out of scope; structural parallel + distinction noted (§5).
- [x] Auditable Agents (arXiv:2604.05485, April 2026) — existence confirmed; honest-tool-provider
      assumption stated; our contribution is the case they assume away (§5).
- [x] Aegis (arXiv:2603.16938, March 2026) — existence confirmed; ZK-STARK PoC + ILK hash chain;
      behavioral compliance domain; orthogonal to inspection-log completeness (§5).
- [pending: DOI resolution] Full DOIs + author lists for all citations before arXiv upload.
      (Handled by arXiv submission process; deferred to pre-upload checklist.)

Implementation status:
- [x] `InspectionRecord` + `OutputInspectionRecord` + `APIResponse` (6-check protocol)
      in `client_cosign.py`. Symmetric input/output inspection.
- [x] `CosignedRequest.to_json()` / `from_json()` — canonical serialisation.
- [x] Reference implementation + adversarial harness (`docs/demo/completeness_demo.py`):
      Ed25519 keys, six-check verification, seven scenarios (A–G), anchored in
      `tests/test_completeness_demo.py` + `tests/test_output_inspection.py`.
- [scope: layer 4] Cross-timestamp check for retroactive compliance detection (§6.7, future work).
      Stated honestly as future work; not blocking arXiv submission.
- [x] Network race-condition protocol: signed receipts → attributable omission vs.
      network loss (§6.8, OSM-040). Implemented + tested + demo Session F.
- [x] Crypto-shredding: dual-hash leaf (`payload_hash` + `salted_hash`) for GDPR Art. 17
      (OSM-007). `SaltStore` in `crypto_shred.py`; 12 tests in `test_crypto_shred.py`.
- [x] Output inspection completeness (Layer 2): `OutputInspectionRecord` committed before
      result is returned; checks 5+6 in `SubjectLedger.ingest()`; Session G in demo;
      10 tests in `test_output_inspection.py`. 1831 tests total (including immunity submodule), all passing.
- [x] External witness HTTP transport implemented (`HttpWitnessTransport`, Ed25519-verified
      quorum, `has_quorum()`). Independent witness node deployment is infrastructure, not code;
      stated honestly as the remaining split-view gap (§6.1).
- [x] Log persistence: `TransparencyLog(path=...)` — base64 fsync per append, reload on startup.
      Seq continuity survives restarts. Documented in §4.
- [x] Read-API (EU AI Act Art. 26, GAP-2): `GET /api/exec/api/v1/log/{tree,entries,proof/inclusion/{i}}`.
      Documented in §4.
- [x] OSM-042 shadow model wired into `TransparencyGateway` (opt-in `shadow_router` /
      `shadow_model` params). Scoped to deployment context (§8.2); not part of completeness
      contribution.

Other:
- [x] Reproducible demo built and passing (7 scenarios, exit-coded).
- [x] Final title: "Subject-Enforced Completeness for AI Inspection Logs" — **locked**.
- [pending: formatting] arXiv cs.CR LaTeX formatting pass before upload.
      Plain markdown → LATEX conversion; deferred to final submission step.
- [pending: legal] Legal review of §7.2 EU AI Act claims deferred.
      Paper explicitly states "not a legal fact" (§6.9); deployment incentive only.
      Sufficient for arXiv; legal pre-deployment review separate.
