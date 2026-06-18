# Conditional and Auditable Access to Frontier Restricted Models

*Technical proposal / cover note. Author: Atlas project (solo developer).
June 2026. Accompanies ADR-051, ADR-053, ADR-054.*

**Suggested email subject:** Technical proposal: conditional and auditable access to frontier models (post-Fable 5 / Mythos 5 shutdown)
**Suggested recipient:** fellows@anthropic.com (External Researcher Access Program)

> **In one line:** Anthropic cannot give users proof that it inspects their content
> only when there is cause — it is both judge and party. An external log with
> verifiable *completeness* (not just integrity) can. The core already works; this
> is the seed, not the product.

---

## The problem, in your own terms

On June 12, 2026, an export control directive forced Anthropic to suspend Fable 5 and
Mythos 5 for all users. The two public reasons:

1. No way to **distinguish foreign nationals in real time** — when in doubt, full shutdown.
2. A known **bypass / jailbreak method** for the model.

The shutdown did not happen because the model is dangerous to everyone. It happened
because **there was no way to guarantee who uses it or to demonstrate that it is not
being abused**. The problem is not the model; it is the absence of a verifiable identity
layer + demonstrable compliance.

---

## The observation that concerns you directly

There is a structural gap you cannot close by construction:

Anthropic is **simultaneously** the model provider and the safety classifier operator
(CC++). That means when you say "we only inspect content when there is cause", the user
has no way to verify it. Not because you are lying — but because the inspection log is
in your hands and yours alone. The conflict of interest is not one of intent; it is
structural.

An external system with a mutually verifiable log closes exactly that gap — the one you
cannot close while being both judge and party.

---

## The proposal, in one sentence

A bounded compliance layer that converts "when in doubt, full shutdown" into
**"conditional access with demonstrable attack cost and verifiable audit by both parties"**
— including the party that needs it most: the user.

---

## Why detection is not the axis (honesty first)

The state of the art in June 2026 is clear: no system — including the best one in
production, which is yours (CC++) — claims robustness against an adversary who adapts
their attack to the specific defense. *The Attacker Moves Second* (arXiv:2510.09023)
demonstrated this formally: adaptive attacks defeat >90% of existing defenses.

**This proposal does not promise to detect the jailbreak. It promises to raise the
cost of the campaign and make it verifiably undeniable.** Those are distinct objectives
and the second one is achievable; the first is not, for anyone, today.

---

## The two contributions that exist in no deployed system

### 1. Mutual log verifiability

A single immutable log (Merkle, RFC 9162) proves two things to two parties who do not
trust each other:

- To the **regulator / provider**: every detected and blocked abuse.
- To the **user**: that *every* inspection of their content was preceded by a
  registered cause — proof they were not inspected beyond what was necessary.

The technical key: Merkle proves integrity (what is there was not altered), but NOT
completeness (it does not prove nothing is missing). This system solves the completeness
problem via **client co-signature with monotonic sequence**: a gap in the sequence is
detectable by the user themselves. The operator cannot inspect without registering
because the log entry is tied to a co-signed request whose sequence the client monitors.

Honest limit: split-view protection (showing different logs to regulator and user)
requires external witnesses (RFC 9162 STH gossip). That network is not deployed — it
is the next level of the ecosystem. The implemented guarantee today is omission detection
by the user themselves, which is already something no published system offers.

Implemented: `src/atlas/transparency/`, 97 transparency-core tests
(1452 in the full suite), mypy strict clean (ADR-053).

### 2. Falsifiable campaign metric (what CC++ does not have by design)

CC++ measures per-attempt. That has a fundamental limit: the adaptive adversary
re-optimizes between attempts and rates collapse. This system measures per campaign:

- **C_attempts**: co-signed attempts recorded before the first bypass success —
  observable directly from the log, no inference required.
- **K_attribution**: ≥3 consecutive attempts with pattern similarity >0.7 →
  campaign flagged with co-signed identity.
- **Falsifiable criterion**: the defense was effective if the attacker needed
  C_attempts ≥ K_attribution before bypass. If the bypass occurs on attempt 1,
  the layer failed — and the log proves it.

No deployed system has this metric because none has the user-verifiable completeness
log that makes it possible.

**June 2026 update — immunity module operational:** `src/atlas/immunity/` implements
affinity maturation on layer 5: semantic hypermutation of defense patterns (not lexical
noise) + clonal selection with LLM scoring + promotion via Decider (invariant I5).
31 tests. The mutation is conceptual — reformulations that preserve defensive semantics
while introducing genuine diversity. Adversarial training tends to overfit to narrow
attack distributions; CHASE (arXiv:2606.05523) addresses this with co-evolution,
but requires the attacker to maintain technique diversity — which only an external
source can guarantee.

---

## Alignment with EU AI Act (August 2026)

Three articles of Regulation (EU) 2024/1689 are directly relevant to you as a
GPAI provider with systemic risk:

- **Art. 12 (Record-keeping)**: The ADR-053 core is the most direct technical mechanism
  for complying with this article — automatic, tamper-resistant log, verifiable by both
  parties, append-only design with indefinite retention. The law requires a minimum of
  6 months; the architecture has no ceiling.
- **Art. 13 (Transparency)**: Mutual verifiability (the user detects inspection omissions
  unilaterally, without trusting the operator) transforms "take our word for it" into
  "the user can prove it". That is exactly what the article requires: that the user
  knows *when* and *why* their content was inspected.
- **Art. 53 (Systemic risk — red-teaming)**: The knowledge organism (ADR-049) + affinity
  maturation inject external attack diversity before it reaches real traffic. CC++ can
  only learn from your own traffic; an external organism injects techniques that
  self-play would never generate. This is the structural mitigation that closes the
  overfitting to narrow attack distributions that self-play produces by construction —
  documented in CHASE (arXiv:2606.05523).

No published paper or production system combines all three.

---

## The complete system: five layers, honesty about each one

| Layer | What it does | Honest limit |
|---|---|---|
| 1. Filter (CC++-style) | cuts noise and known attacks | high bypass against adaptive adversary |
| 2. Session polymorphism | randomizes decoding hyperparameters per session (FlexLLM); invalidates precomputed jailbreaks; salt recorded in log | no activation access (external API): weaker than salting the rejection direction directly |
| 3. Decoy (only after confirmed cause) | generates forensic evidence; inverts certainty burden on attacker | fails against verifiable probe in executable domain; valuable for the cause it generates, not for fooling a serious adversary |
| 4. **Verifiable campaign log** | makes the series of attempts undeniable; C_attempts/K_attribution metric; raises campaign cost | does not detect individual attempts |
| 5. **Immune memory + external diversity** | learns from each exposure; knowledge organism injects real external attacks | not sterilizing against truly novel attack; diversity injection still pending wiring |

**On layer 5 and why it matters specifically for you:** adversarial training tends
to overfit to narrow attack distributions — the defender stagnates on what it has
already seen. CHASE (arXiv:2606.05523) addresses this with attacker-defender
co-evolution, but requires the attacker to maintain technique diversity. CC++ has this problem by construction:
it learns from your traffic, but if new attacks do not appear in that traffic, it does
not know them until they arrive. A knowledge organism that injects external attack
techniques (papers, feeds, CVEs) before they reach real traffic is the structural
mitigation. No published paper has this because none has a knowledge organism connected
to its immune system.

---

## What this is NOT

- I am not proposing to interpose an external binary in your model's path. That would
  be operationally unacceptable and I know it.
- I am not claiming guaranteed detection. No one can guarantee it today.
- This is not an enterprise-validated product. It is the architecture, the built core
  (ADR-053, 1452 tests), and the ADRs for the remaining layers.
- I did not resolve identity binding (real KYC for foreign nationals). That is
  operational and legal, not code.
- The witness network is not deployed: split-view protection is future ecosystem,
  not today's demo.

---

## Why I am sending this

Not to sell a product. For two concrete things:

**1. To signal the gap that exists and that you cannot close alone.**
The structural conflict of interest (you are simultaneously provider and classifier)
makes it impossible for you to offer users verifiability about your own inspections.
It is not a problem of intent — it is architectural. An externally verifiable system
is the only solution to that problem, and that system does not exist in production
anywhere today.

**2. To show the reasoning, not the product.**
A solo developer, the day after the Fable 5 / Mythos 5 shutdown, identified the two
technical causes, designed an architectural response with the right axis (mutual
verifiability, not perfect detection), and built the core that proves the completeness
mechanism is implementable. What we have is the seed — the verifiable log working
(1452 tests, ADR-053) inside an organism that can learn from every campaign the
log makes undeniable. If this way of thinking is useful to you, let us talk.

---

*Demo (~2 min available): a legitimate session whose log proves zero content
inspections, and a session with cataloged abuse detected, blocked and recorded —
both on the same immutable chain, showing the proof in both directions.
Core at `src/atlas/transparency/`, 1452 tests, mypy strict clean.*

*Sources: Anthropic's official statements and coverage from Time, CNBC, Al Jazeera,
Fortune (June 13, 2026).*
