# Inspection logs need completeness, not just integrity — and the inspected party can enforce it

*Draft for LessWrong / Alignment Forum. ~1,800 words.*

---

## The claim, up front

When a model provider says "we only inspect your content when there is cause," there is
currently no way for you — the user — to verify it. Not because they are necessarily
lying, but because the record of inspections lives entirely on their side. A tamper-evident
log (Merkle, RFC 9162) does **not** fix this, because tamper-evidence proves *integrity*
(what is in the log was not altered) and not *completeness* (nothing that should be in the
log is missing).

For inspection logs specifically, completeness is the property that matters, because the
threat is **omission**, not alteration. An operator who wants to inspect you quietly does
not edit the log — they simply never write the entry.

The narrow point of this post: for the **subject's own stream of requests**, completeness
is enforceable without trusting the operator, by binding each inspection to a request the
subject co-signs with a strictly monotonic counter. A gap in your own sequence is something
you can detect unilaterally. This converts an unfalsifiable question ("did you log
everything?") into a falsifiable one ("is my own sequence contiguous in the log?").

I want to state precisely what this does and — more importantly — what it does **not** do,
because the gap between those two is where most "verifiable AI" claims quietly fail.

---

## Why integrity ≠ completeness

Transparency logs (Certificate Transparency is the mature example) give you two
cryptographic guarantees:

- **Inclusion**: "this specific entry is in the log." (Merkle inclusion proof.)
- **Consistency**: "the log only ever grew; nothing already published was removed or
  reordered." (Merkle consistency proof.)

Neither is completeness. A log can be perfectly append-only and tamper-evident while the
operator simply declines to write down events they would rather not disclose. Completeness
*relative to real-world actions* is, in general, not achievable by a log alone — a log
cannot force a party to record an action it wants to hide.

The CT community knows this: it is why CT needs **gossip** between monitors and witnesses.
A malicious log can otherwise present one append-only view to auditors and a different one
to victims (the "split-view" attack), each internally consistent. Append-only-ness is
necessary, not sufficient. So "use a Merkle log" imports a tool that solves integrity and
quietly assumes it solves completeness. It does not.

---

## The structural reason this is not a fixable bug for the provider

Consider who runs the safety classifier. For frontier models today, the model provider is
**also** the operator of the safety classifier that inspects user content. That is a
structural conflict of interest — not an accusation of bad faith, an observation about
architecture. When the same party (a) holds the content, (b) decides when to inspect it,
and (c) owns the only record of those inspections, then "we only inspect with cause" is a
claim the user can never check. The party cannot, by construction, provide the user
verifiability about its own discretionary behavior.

This is the part I think is underappreciated in alignment-adjacent discussions of
monitoring and oversight. We talk a great deal about whether the *classifier* is accurate.
We talk much less about whether the *user* can verify the classifier was even invoked, and
only when claimed. The second question is independent of, and arguably prior to, the first.

---

## A mechanism for the subject's own stream

Here is the modest, precise contribution. It does not solve completeness in general (that
is impossible). It solves it for one well-defined case: **the subject's own requests**.

Make every request the user sends carry:

1. a **monotonic counter** (strictly increasing, per user), and
2. the user's **signature** over (counter, request).

Require, by protocol, that any inspection record the operator writes must reference the
co-signed request that triggered it. The user keeps their own counter.

Now the operator faces a bind for *that user's* traffic:

- If they inspect content tied to request *n*, they must log an entry referencing the
  co-signed request *n*. The user can later request an inclusion proof for *n* and check
  the entry is present.
- The user monitors their **own** sequence. If their requests went 1, 2, 3, 4 and the log
  only shows 1, 2, 4, the user sees the gap — in *their own counter* — and can prove it,
  because they hold the signed request *3* the operator failed to include.

The shift is small but real: completeness of the operator's inspections, *with respect to a
given user's request stream*, becomes **unilaterally falsifiable by that user**. They do
not have to trust the operator's good faith or even the operator's other auditors. They
check the contiguity of a sequence they themselves generated.

I implemented this on top of a full RFC 9162 Merkle log (inclusion + consistency proofs)
as a `detect_omission()` over the user's co-signed sequence. The point of mentioning the
implementation is only that the mechanism is concrete and not hand-waving; it is not the
interesting part. The interesting part is the framing: *bind the record to something the
inspected party controls, and you move omission-detection from trust to proof.*

---

## What this does NOT give you (this is the important section)

I want to be explicit about the boundaries, because every one of these is a place where a
careless version of this claim would be wrong.

1. **It does not give split-view protection.** A malicious operator can still show one
   consistent log to the regulator and a different consistent log to the user. The user
   detects omissions *within the view shown to them*; they cannot, alone, detect that a
   different view exists. Closing this requires external witnesses gossiping signed tree
   heads — exactly the CT story. That network is not something a single party can deploy,
   and I have not deployed it. This is the largest honest gap.

2. **It does not protect against out-of-band inspection.** The guarantee binds inspection
   to requests *in the request path*. If an operator stores your content and inspects it
   later without a fresh co-signed request, this mechanism says nothing. The protection is
   for undisclosed inspection in the path, not for everything an operator could ever do
   with retained data.

3. **It does not detect jailbreaks, and is not a defense against adaptive attackers.**
   This is a completely separate problem. The state of the art is that adaptive attacks
   defeat most deployed defenses — Nasr, Carlini, Tramèr et al., *The Attacker Moves
   Second* (arXiv:2510.09023), broke 12 recent defenses at >90% success despite their
   near-zero reported vulnerability. The
   honest reframing I have settled on is to stop measuring per-attempt detection (which
   collapses against a re-optimizing adversary) and instead measure per-campaign cost: how
   many co-signed attempts a campaign needed before it succeeded, and whether the series is
   attributable. That metric is falsifiable where per-attempt rates are not — but it
   presumes the completeness log above, and it is a measurement, not a wall.

4. **It does not solve identity binding.** Knowing *that* a user co-signed says nothing
   about *who* they are. The whole export-control problem (distinguishing foreign nationals,
   the stated reason behind real frontier-model shutdowns) is operational and legal. Code
   does not touch it.

If you remove any of these caveats, the claim becomes false. I would rather the post be
boring and correct than exciting and wrong.

---

## Why this connects to the EU AI Act

Briefly, because it is concrete and because it changes the picture from "trust us" to
"prove it." Two articles of Regulation (EU) 2024/1689 are directly relevant:

- **Art. 12 (record-keeping)** requires automatic, tamper-resistant logs with a retention
  minimum. A co-signed append-only Merkle log satisfies the integrity half directly. The
  completeness mechanism above adds something the article gestures at but most
  implementations will not provide: the *subject* can check the record is not selectively
  thinned.
- **Art. 13 (transparency)** requires the user be able to understand when and why the
  system acted on them. "The user can cryptographically detect undisclosed inspection of
  their own stream" is a strong reading of that requirement — stronger than any trust-based
  logging I am aware of in production.

I am not claiming this discharges those obligations. Conformity assessment, notified
bodies, external audit — none of that is here. I am claiming the *technical* mechanism for
the part these articles most directly point at is buildable and exists.

---

## Open questions I would genuinely like input on

1. **The minimum witness network.** Split-view is the real gap. What is the smallest /
   weakest set of external witnesses that meaningfully raises the cost of a split view for
   an inspection log, given that the *subjects themselves* are already monitoring their own
   sequences? Subjects monitoring their own streams is information CT monitors do not have;
   does it reduce the witness requirement?

2. **Out-of-band inspection.** Is there a clean protocol-level way to bind *retained-data*
   inspection to a fresh artifact the subject can monitor, without requiring the subject to
   be online? Or is this fundamentally outside what append-only logging can reach?

3. **Is the campaign metric the right reframing?** Moving from per-attempt detection to
   per-campaign cost feels right against adaptive adversaries, but I have not seen it
   formalized and I would like to know if someone has, or why it is a bad idea.

I think the integrity-vs-completeness distinction is the kind of thing that is obvious once
stated and easy to skate past when reaching for "just use a Merkle log." The subject-side
enforceability is a small idea. Small ideas that are actually correct are the ones I would
rather contribute than large ones that are not.

---

*I am an independent developer. The transparency-log core and a short demo (a legitimate
session whose log proves zero content inspections, vs. a session with cataloged abuse
detected and recorded, both on the same chain) are available to anyone who wants to test
the mechanism. The most useful response to this post is a counterexample: a case where the
inspected party believes their sequence is contiguous but the operator has still inspected
them undetected, inside the scope I claimed (in-path, single-view). If that case exists, I
want to know — it is the whole point of posting before building further.*
