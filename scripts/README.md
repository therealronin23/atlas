# Atlas Core — scripts/

This directory contains:

- **Long-lived utilities** that live in production (Hermes deploy, Atlas systemd, smoke tests)
- **One-shot fix scripts** from the 2026-05-27/28 Hermes-Agent deployment debugging session, kept for reference and reproducibility

## Long-lived (use these)

| Script | What it does |
|---|---|
| `install_atlas_systemd.sh` | Install Atlas Core as a systemd-user service on the laptop. Idempotent. Survives logout via `loginctl enable-linger`. |
| `atlas-core.service` | The systemd unit template, copied to `~/.config/systemd/user/` by the installer above. |
| `install_hermes_agent_vps.sh` | One-shot installer for Hermes-Agent on the VPS (apt deps, pip venv, Ollama, systemd-user unit, ~/.hermes/config.yaml + .env). Idempotent. |
| `deploy_hermes_vps_oneshot.sh` | Operator wrapper that runs from the laptop: scps the install script to the VPS and triggers it with secrets via SSH env. |
| `reconfigure_hermes_vps.sh` | Reconfigure Hermes-Agent without reinstalling (config.yaml only). |
| `verify_twin_pairing.sh` | Read-only health check across Tailscale + Atlas + Hermes-VPS + Ollama + skill files. |
| `pipeline_smoke.py` | Gate D pipeline smoke — calls real Groq/OpenRouter, verifies fallback chain. |
| `gate_h_smoke.py` | Gate H synthesis + ResultAuditor smoke. |
| `gate_i_smoke.py` | Gate I `atlas serve` operational smoke. |
| `operational_smoke.py` | End-to-end Hermes REST + HMAC (on-host, needs HERMES_* in env). |
| `audit_complete.py` | Full local-state audit dump. |

## One-shot fixes (historical, 2026-05-27/28)

These scripts were created during the Hermes-Agent deployment debugging marathon.
Each fixed a specific issue surfaced live. They are kept for reproducibility,
not for re-execution — the changes are already in production.

Ordered by chronology of when each landed:

1. `install_hermes_agent_vps.sh` (PR #7) — initial twin architecture installer
2. `fix_hermes_paths_vps.sh` (PR #10) — `/home/root/` vs `/root/` HOME bug
3. `fix_hermes_systemd_command.sh` (PR #12) — `hermes run` → `hermes gateway run`
4. `finalize_hermes_vps.sh` (PR #13) — venv rebuild + Telegram allowlist
5. `fix_hermes_install_unit.sh` (PR #14) — `hermes gateway install` (not `service install`)
6. `fix_hermes_user_unit.sh` (PR #15) — user-level systemd + linger
7. `fix_hermes_context_length.sh` (PR #16) — model context 32K → 128K
8. `fix_hermes_413_payload.sh` (PR #17) — OpenRouter primary swap for 413s
9. `fix_hermes_hf_primary.sh` (PR #18) — HF primary + SOUL.md identity
10. `fix_hermes_local_primary.sh` (PR #19) — Ollama qwen2.5:3b primary with q4 KV cache
11. `stabilize_hermes.sh` (PR #22) — Ollama primary, valid Gemini name, Hub skills
12. `fix_hermes_compression_and_skills.sh` (PR #23) — `auxiliary.compression.context_length`
13. `install_hermes_deps_and_skill.sh` (PR #21) — Node.js, ripgrep, ffmpeg, chromium + custom Python skill (the skill format was wrong; Hermes uses SKILL.md from registries)
14. `hermes_final_fix.sh` (PR #24) — HuggingFace for `auxiliary.compression`
15. `hermes_make_hf_primary.sh` (PR #25) — drop OpenRouter (quota exhausted)
16. `hermes_groq_primary_fix_ollama.sh` (PR #26) — Groq primary + restore Ollama loopback

### Why so many?

Hermes-Agent is genuinely complex (config schema undocumented in places,
user-level systemd, Skills Hub remote registry, context-length minimum of
64K, compression model separate from primary, etc.). Each script fixed a
specific surfaced bug. They are also useful as documentation: each commit
message explains a different gotcha.

If we ever redo this from scratch, the consolidated path is:
1. `install_hermes_agent_vps.sh` (now contains all the path fixes inline)
2. `reconfigure_hermes_vps.sh` (writes the v6+ config)
3. `verify_twin_pairing.sh` (sanity check)
