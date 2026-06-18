# Reference Implementation — Subject-Enforced Completeness

Reproducible evidence for `docs/paper_subject_enforced_completeness.md`.

```bash
PYTHONPATH=src python docs/demo/completeness_demo.py
```

No network, no AI model, no external services. Uses **Ed25519** device-bound
keys (asymmetric): the subject holds the private key; the operator holds only
the public key. This is what lets the harness *demonstrate* — not merely assume
— that the operator cannot forge the subject's requests.

## The actors

- **`SubjectLedger`** (client): signs each request with the device-bound private
  key, keeps a monotonic counter, and maintains a local replica. On every
  response it runs **six** independent checks (STH signature, append-only
  consistency, input inclusion, input binding, output inclusion, output binding).
  This is the *twin independent log replica* of paper §3.4.
- **`Operator`** (provider infrastructure): the in-path filter + RFC 9162
  transparency log. Behaviour is configurable to misbehave. It holds only the
  subject's public key — it can verify signatures, never produce them.

## Scenarios

| Session | Operator behaviour | Outcome | Paper |
|---|---|---|---|
| A | honest — inspects input + output, commits both | `detect_omission() == []` | §3 |
| B | silently skips input inspection of seq=2 | `== [2]`, detected by subject alone | §3.3 |
| C | fakes an input ack for seq=2 (bogus STH + proof) | rejected at verification; `[2]` surfaces | §3.2 |
| D | rewrites a past log entry at seq=3 | consistency proof fails; tamper caught | §3.4 |
| E | forges a request for a seq never sent | rejected; signature ≠ registered key | §2.3 |
| F | signs a receipt for seq=2 then omits it; seq=4 lost in transit | `attributable_omissions() == [2]`; network loss not accused | §6.8 |
| G | commits input record but omits **output** inspection for seq=2 | check 5 fails; seq=2 in gaps (cascade to subsequent seqs) | §3.2 |

Each scenario asserts its expected outcome; the script exits non-zero on any
deviation, so it is an executable specification.

Session F (OSM-040) closes the plausible-deniability gap: a signed receipt is
the operator admitting it received a request. A receipt without a later
inclusion proof is an *attributable* omission — "the network dropped it" is no
longer a valid excuse. A gap with no receipt (seq=4) is treated as network loss,
not accusation; the subject resends (idempotent by `(seq, payload_hash)`).

## What it does NOT demonstrate (honest limits — paper §6)

- **Split-view (§6.1)**: the subject verifies *its own* view. An operator showing
  a different, internally-consistent log to a regulator is **not** detectable
  here. Closing this needs external witnesses (RFC 9162 §5 gossip), which this
  single-node harness does not model. Sessions C/D show the subject rejecting a
  *malformed* or *non-extending* view — not a fully-formed parallel view.
- **Retroactive compliance (§6.8)**: the in-path timing guarantee (commit before
  the model runs) is an architectural property of the deployment, not something
  this harness proves cryptographically.

## Anchored in the suite

`tests/test_completeness_demo.py` runs all five scenarios and asserts the
expected outcomes, so a regression in the mechanism breaks the build.
