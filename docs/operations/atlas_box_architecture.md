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

### Resultado real (2026-07-23, `scripts/benchmark_workload.py --fast`)

Los 4 pasos de arriba están hechos con hardware real (este HP Omen, GTX 960M,
Ollama 0.23.2 local — cero red de pago, cero infraestructura nueva). JSON
completo en `docs/knowledge/benchmarks/workload_benchmark_2026-07-23.json`.

- **Cuello de botella real: throughput de CPU, no VRAM.** `ollama ps` confirma
  100% CPU en los dos workloads de LLM; la VRAM se mantuvo plana en ~104MiB
  antes y después (la GPU está prácticamente idle). Es deliberado, no un bug:
  `CUDA_VISIBLE_DEVICES` se dejó vacío a propósito porque esta GTX 960M
  (Maxwell) no la soporta el CUDA que trae Ollama (ver memoria
  `ollama-fix-2026-07-09`).
- **El throughput escala mal con el tamaño del modelo**: 49.9 tok/s en
  `qwen2.5:0.5b` vs 3.4 tok/s en `qwen2.5-coder:7b` (Q4_K_M) — ~14.6x más
  lento. Un modelo ≥7B es más lento que lectura humana cómoda (~15-20 tok/s);
  para respuestas largas la latencia percibida es de decenas de segundos.
- **Térmico y RAM no fueron el límite hoy** (59°C→64°C, umbral DEGRADED=70°C;
  RAM libre se mantuvo por encima del umbral DEGRADED todo el benchmark), pero
  el margen térmico medido fue de solo 6°C — no es un colchón grande para
  cargas sostenidas, a diferencia de una corrida corta como esta.
  `memory_distillation` (CPU puro, sin LLM) y `dashboard` (FastAPI TestClient,
  sin red real) corrieron limpio y rápido, sin fricción.
- **`browser_tasks` no se pudo medir**: `playwright` no está instalado en este
  venv — limitación real, documentada por el propio script (`skipped: true`,
  no un fallo silencioso). `voice` se documenta siempre como no ejecutado, por
  diseño del harness (dependencias reales no verificadas en este host).
- **Conclusión para el perfil de compra (T6, decisión N3 del operador)**: si
  el objetivo es correr modelos ≥7B con latencia razonable, el cuello real a
  resolver es cómputo (GPU con CUDA soportado o ruta de proveedor externo),
  no RAM ni VRAM total — información que faltaba antes de este benchmark.

