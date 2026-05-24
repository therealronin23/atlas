# Atlas Box Architecture Notes

**Source material:** distilled from `Gemini-Temporary Chat.md`.
**Status:** concept note, not a purchase recommendation.

The useful idea in the Gemini chat is not "buy the biggest GPU." It is to
separate Atlas into roles: user interface, sovereign policy/memory, and heavy
compute. This keeps costs down and improves security.

## Hardware Reality

For local AI, memory bandwidth and accelerator memory matter more than raw CPU
marketing numbers.

- Apple Silicon unified memory is difficult to clone with commodity PC parts.
- Cheap GPU plus lots of motherboard RAM is usually poor for LLM inference:
  offloading across PCIe can collapse throughput.
- NVIDIA remains the easiest path for CUDA-first open-source inference stacks.
- AMD APU/ROCm and SBC/NPU routes may be cheaper or more efficient, but carry
  software friction and should be validated with smoke tests before purchase.
- Small NPUs are often excellent for vision/classification workloads but are
  not automatically good LLM accelerators.

## Three-Node Pattern

The strongest architecture from the chat is a tri-tier Zero-Trust AI Gateway:

| Node | Role | Holds secrets? | Example |
|---|---|---|---|
| User terminal | UI/desktop/browser/editor | no long-term AI secrets | employee mini PC, laptop, desktop |
| Atlas Box | governance, memory, routing, audit, local SLM | yes, tightly scoped | SBC, mini PC, SFF Linux node |
| Hermes compute | heavy inference and remote continuity | no raw private data when avoidable | VPS, GPU host, API bridge |

Flow:

1. The user terminal sends requests to Atlas Box over local network/Tailscale.
2. Atlas Box applies Governance L0, PermissionProfile, PII Surrogate,
   MemoryDistiller and routing.
3. If local SLM is enough, Atlas Box answers locally.
4. If heavy reasoning is required, Atlas Box sends a minimized/redacted request
   to Hermes or an approved provider.
5. Atlas Box restores context, logs the decision and returns the answer.

## Why This Matters

This topology avoids putting everything on the user's workstation. If the
desktop is compromised, the attacker should not automatically get:

- API keys;
- full KuzuDB memory;
- Merkle audit history;
- Governance L0 authority;
- Hermes credentials.

The Atlas Box becomes a local policy gateway, not just a model runner.

## Candidate Profiles

These are architecture profiles to test, not procurement instructions.

### Profile A: Existing Workstation

- Lowest cost.
- Best for development.
- Weakest isolation if user desktop and Atlas runtime share one host.

### Profile B: Low-Power Atlas Box

- SBC or mini PC running Atlas Core, KuzuDB, MerkleLogger and small local SLM.
- Heavy tasks route to Hermes/providers.
- Good for small business deployment if setup is reproducible.

### Profile C: SFF GPU Node

- Linux mini-ITX/SFF box with dedicated GPU.
- Higher cost, easiest path for CUDA acceleration.
- Good for local inference and future Proxmox/LXC isolation experiments.

### Profile D: Distributed Local Swarm

- Uses multiple existing devices via llama.cpp RPC or similar.
- Interesting research path, but operationally complex.
- Not a Gate F dependency.

## Do Not Do

- Do not put a Raspberry Pi inside the same box and call it a VPS. Hermes needs
  public reachability or a reliable external network role.
- Do not open home-router ports to replace Tailscale/Hermes.
- Do not buy hardware before a workload benchmark defines the bottleneck.
- Do not make hardware anti-tamper destructive behavior part of Atlas without
  a dedicated security ADR and legal review.

## Next Validation

1. Define target workloads: classification, memory distillation, browser tasks,
   code generation, voice, dashboard.
2. Benchmark current HP Omen.
3. Benchmark one low-cost SLM route through Ollama.
4. Decide whether the bottleneck is latency, throughput, VRAM, RAM, thermal or
   operator setup complexity.

