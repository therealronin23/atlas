# Hermes-Agent deployment debugging — scripts archive

**Period:** 2026-05-27 to 2026-05-28
**Outcome:** Hermes-Agent (Nous Research) deployed to Hetzner CPX22, ADR-026
twin architecture stable. Atlas Core v0.10.0 → v0.11.0.

## Why these scripts exist

Hermes-Agent's installation surface is broader than expected (undocumented
config keys, user-level systemd, Skills Hub remote registry, context-length
minimums, separate compression model, OS deps). Each bug surfaced live
during a Telegram session and was patched with a one-shot SSH-fed script.

These scripts already ran in production; their changes are baked in. Do **not**
re-execute them — the consolidated installer
(`../install_hermes_agent_vps.sh`) and reconfigurator
(`../reconfigure_hermes_vps.sh`) supersede them.

## Index (chronological)

| Script | PR | Fix |
|---|---|---|
| `fix_hermes_paths_vps.sh` | #10 | `/home/root/` vs `/root/` HOME-dir bug when install ran as root |
| `fix_hermes_systemd_command.sh` | #12 | `hermes run` → `hermes gateway run` (former doesn't exist) |
| `finalize_hermes_vps.sh` | #13 | venv rebuild + Telegram allowlist + systemd unit |
| `fix_hermes_install_unit.sh` | #14 | `hermes gateway install` (not `gateway service install`) |
| `fix_hermes_user_unit.sh` | #15 | user-level systemd + `loginctl enable-linger root` |
| `fix_hermes_context_length.sh` | #16 | bump `context_length: 32768` → `131072` (Hermes requires ≥64K) |
| `fix_hermes_413_payload.sh` | #17 | OpenRouter primary swap (Groq free tier had request-size cap) |
| `fix_hermes_hf_primary.sh` | #18 | HF primary + SOUL.md twin identity injection |
| `fix_hermes_local_primary.sh` | #19 | Ollama qwen2.5:3b primary + q4 KV-cache so it fits 4 GB CPX22 |
| `install_hermes_deps_and_skill.sh` | #21 | apt deps (Node.js, ripgrep, ffmpeg, chromium) + first attempt at custom skill (skill format was wrong — Hermes uses Hub SKILL.md, not arbitrary Python) |
| `stabilize_hermes.sh` | #22 | stop crash loop + valid Gemini model name + Hub skill installs |
| `fix_hermes_compression_and_skills.sh` | #23 | `auxiliary.compression.context_length: 65536` explicit |
| `hermes_final_fix.sh` | #24 | HuggingFace for `auxiliary.compression` (Ollama kept reporting 32K despite OLLAMA_CONTEXT_LENGTH env) |
| `hermes_make_hf_primary.sh` | #25 | drop OpenRouter (free quota 403) + drop Ollama primary (loopback issue) |
| `hermes_groq_primary_fix_ollama.sh` | #26 | Groq primary + restore Ollama `OLLAMA_HOST=127.0.0.1:11434` (was 0.0.0.0) |

## What's now in `scripts/` (live)

| Script | Purpose |
|---|---|
| `install_hermes_agent_vps.sh` | Consolidated installer (has all the path fixes inline). Idempotent. |
| `reconfigure_hermes_vps.sh` | Reconfigure config.yaml without reinstalling. |
| `deploy_hermes_vps_oneshot.sh` | Operator wrapper: scps the installer to the VPS and triggers it. |
| `verify_twin_pairing.sh` | Read-only twin health check. |
| `install_atlas_systemd.sh` + `atlas-core.service` | Atlas Core systemd-user unit on the laptop. |
