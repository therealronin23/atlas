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
| `hermes_local.sh` | Run the REST-compatible Hermes stub on the laptop (`start|stop|status|logs`) using the same HTTP contract Atlas used against the VPS. |
| `verify_twin_pairing.sh` | Read-only health check across Tailscale + Atlas + Hermes-VPS + Ollama + skill files. |
| `pipeline_smoke.py` | Gate D pipeline smoke — calls real Groq/OpenRouter, verifies fallback chain. |
| `gate_h_smoke.py` | Gate H synthesis + ResultAuditor smoke. |
| `gate_i_smoke.py` | Gate I `atlas serve` operational smoke. |
| `operational_smoke.py` | End-to-end Hermes REST + HMAC (on-host, needs HERMES_* in env). |
| `audit_complete.py` | Full local-state audit dump. |

## One-shot fixes (historical, archived)

Moved to `scripts/archive/2026-05-hermes-debugging/` — see the README in that
directory for the full index of 15 one-shot fix scripts from the Hermes-Agent
deployment debugging marathon (2026-05-27/28). Each one's changes are baked
into the consolidated `install_hermes_agent_vps.sh` and
`reconfigure_hermes_vps.sh`; do **not** re-execute the archived ones.

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
