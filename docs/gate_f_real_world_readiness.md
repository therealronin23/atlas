# Gate F Real-World Readiness

**Source material:** distilled from `Gemini-Temporary Chat.md`.
**Status:** planning and operator checklist.

Gate F means Atlas starts touching the real host: browser automation, editor
actions, local models, and eventually kernel-level monitoring. Passing tests is
necessary but not sufficient; the operating system must also be prepared.

## What "Gate F Works" Means

Atlas is not done just because the suite is green. The real-world bar is:

- local tooling is installed and discoverable;
- browser automation works in a controlled display context;
- L0 local inference is reachable or cleanly falls back;
- commands are routed through AtlasExecutor;
- every external-effect action is logged;
- approval boundaries still hold when the action touches the host.

## Baseline Checks

Run these manually on the host before relying on Gate F features:

```bash
cd ~/proyectos/atlas-core
source .venv/bin/activate
PYTHONPATH=src python -m pytest tests/ -q
MYPYPATH=src python -m mypy src/atlas/
```

Optional live checks:

```bash
ollama list
curl -s http://127.0.0.1:11434/api/tags | head
PYTHONPATH=src python scripts/inference_smoke.py
```

## Host Dependencies

These are not repo dependencies; they are host capabilities.

| Area | Dependency | Why |
|---|---|---|
| Browser automation | Playwright browser binaries, optional Xvfb | headless/virtual browser control |
| Local L0 inference | Ollama service and selected local model | offline or low-cost local routing |
| Kernel monitoring | Linux headers, clang/llvm, bpf tooling | future eBPF/seccomp work |
| Editor/agent terminals | stable shell profile, preferably bash in VS Code/Cline | reliable command output capture |

Suggested host commands for a Debian/Ubuntu-like system, to be reviewed before
running:

```bash
sudo apt update
sudo apt install xvfb
sudo apt install linux-headers-$(uname -r) bpfcc-tools clang llvm
```

Do not make eBPF work autonomous. It should remain a manual/operator-approved
phase until Gate F hardening is complete.

## VS Code / Agent Shell Guidance

For agent-controlled terminal sessions, prefer `bash` as the VS Code default
profile. It is the most compatible with activation scripts, pipes, pytest,
shell integration and automation tools.

Avoid using `fish` for agent automation because it is not POSIX-compatible.
`zsh` is fine for human use, but themes and prompt hooks can confuse terminal
output capture in some editor agents.

## Known Risk Areas

- Playwright can fail on captchas, unusual browser security flows or missing
  browser binaries.
- Local inference can pass tests in stub mode but fail live if Ollama is not
  running or the model is missing.
- eBPF tooling can break across kernel versions.
- Voice and browser features may need system packages outside Python.
- Editor automation must not expose raw shell execution.

## Acceptance Signal

Gate F should be considered ready for real host use only after:

1. BrowserTool and EditorTool hardening from `docs/gate_f_plan.md` is complete.
2. Full suite and mypy pass.
3. At least one real browser smoke test passes.
4. At least one local or live inference smoke test passes.
5. The operator can reproduce the setup from documented commands.

