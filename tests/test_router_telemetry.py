"""F5.1 + F5.2 (plan toasty-hatching-pillow) — telemetría de cierre de bucle y
anti-fatiga del router determinista de capacidades.

F5.1: cada bloque de sugerencias realmente mostrado se registra en
``workspace/mcp/routing_suggestions.jsonl`` como {ts, prompt_hash, hits,
top_score} — SHA-256, JAMÁS el prompt en claro. ``router_usage_report`` cruza
esas sugerencias con el ToolUsageCounter (uso real) → "% realmente usado".

F5.2: cooldown/dedupe entre turnos con estado en
``workspace/mcp/router_cooldown.json`` — la misma tool no se repite durante N
turnos; segunda invocación con el mismo prompt → bloque vacío/reducido.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from atlas.mcp.capability_router import RouteHit
from atlas.mcp.router_telemetry import (
    append_suggestion,
    apply_cooldown,
    hash_prompt,
    read_suggestions,
    usage_report,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _hit(name: str = "tool-a", score: float = 5.0) -> RouteHit:
    return RouteHit(
        name=name,
        kind="mcp",
        sector="programacion",
        status="instalado",
        purpose="demo",
        invoke_hint="trunk_invoke",
        score=score,
    )


# ---------------------------------------------------------------------------
# F5.1 — telemetría: JSONL con hash, nunca el prompt en claro
# ---------------------------------------------------------------------------


def test_hash_prompt_is_sha256_hex_and_deterministic() -> None:
    h = hash_prompt("revisar componentes react")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)
    assert h == hash_prompt("  revisar componentes react  ")  # normaliza strip
    assert h != hash_prompt("otro prompt")


def test_append_suggestion_writes_hash_never_plaintext(tmp_path: Path) -> None:
    p = tmp_path / "mcp" / "routing_suggestions.jsonl"
    prompt = "tema secretísimo: contraseñas del banco"
    append_suggestion(p, prompt=prompt, hits=[_hit(), _hit("tool-b", 3.0)], ts=123.0)

    raw = p.read_text(encoding="utf-8")
    assert "secretísimo" not in raw and "contraseñas" not in raw
    entry = json.loads(raw.strip())
    assert entry == {
        "ts": 123.0,
        "prompt_hash": hash_prompt(prompt),
        "hits": ["tool-a", "tool-b"],
        "top_score": 5.0,
    }


def test_append_suggestion_appends_lines(tmp_path: Path) -> None:
    p = tmp_path / "s.jsonl"
    append_suggestion(p, prompt="a", hits=[_hit()], ts=1.0)
    append_suggestion(p, prompt="b", hits=[_hit("tool-b")], ts=2.0)
    entries = read_suggestions(p)
    assert [e["ts"] for e in entries] == [1.0, 2.0]


def test_append_suggestion_empty_hits_writes_nothing(tmp_path: Path) -> None:
    p = tmp_path / "s.jsonl"
    append_suggestion(p, prompt="a", hits=[])
    assert not p.exists()


def test_read_suggestions_missing_file_and_corrupt_lines(tmp_path: Path) -> None:
    p = tmp_path / "s.jsonl"
    assert read_suggestions(p) == []
    p.write_text('{"ts": 1.0, "hits": ["a"]}\n{corrupta\n\n[1,2]\n', encoding="utf-8")
    entries = read_suggestions(p)
    assert len(entries) == 1 and entries[0]["ts"] == 1.0


# ---------------------------------------------------------------------------
# F5.2 — anti-fatiga: cooldown entre turnos
# ---------------------------------------------------------------------------


def test_second_invocation_same_hits_gives_empty_block(tmp_path: Path) -> None:
    state = tmp_path / "router_cooldown.json"
    hits = [_hit("a"), _hit("b")]
    first = apply_cooldown(hits, state)
    assert [h.name for h in first] == ["a", "b"]
    second = apply_cooldown(hits, state)
    assert second == []  # bloque vacío: nada que repetir


def test_cooldown_reduces_block_but_lets_new_tools_pass(tmp_path: Path) -> None:
    state = tmp_path / "router_cooldown.json"
    apply_cooldown([_hit("a")], state)
    kept = apply_cooldown([_hit("a"), _hit("b")], state)
    assert [h.name for h in kept] == ["b"]  # reducido, no vacío


def test_cooldown_expires_after_n_turns(tmp_path: Path) -> None:
    state = tmp_path / "s.json"
    assert apply_cooldown([_hit("a")], state, cooldown_turns=2)  # turno 1: sugiere
    assert apply_cooldown([_hit("a")], state, cooldown_turns=2) == []  # turno 2
    assert apply_cooldown([_hit("a")], state, cooldown_turns=2) == []  # turno 3
    kept = apply_cooldown([_hit("a")], state, cooldown_turns=2)  # turno 4: expiró
    assert [h.name for h in kept] == ["a"]


def test_cooldown_corrupt_state_fails_open(tmp_path: Path) -> None:
    state = tmp_path / "s.json"
    state.write_text("{no es json", encoding="utf-8")
    kept = apply_cooldown([_hit("a")], state)
    assert [h.name for h in kept] == ["a"]  # no revienta: resetea y sugiere


# ---------------------------------------------------------------------------
# F5.1 — informe: cruza sugerencias con ToolUsageCounter (sintético)
# ---------------------------------------------------------------------------


def test_usage_report_crosses_suggestions_with_counter() -> None:
    suggestions = [
        {"ts": 1.0, "prompt_hash": "x", "hits": ["ctx7", "vercel-skill"], "top_score": 5.0},
        {"ts": 2.0, "prompt_hash": "y", "hits": ["ctx7"], "top_score": 4.0},
    ]
    usage = {
        "mcp__ctx7__resolve_library_id": {"external": 3},
        "mcp__otro__tool": {"external": 1},
    }
    rep = usage_report(suggestions, usage)
    assert rep["suggestions_logged"] == 2
    assert rep["tools_suggested"] == 2
    assert rep["tools_used"] == 1
    assert rep["percent_used"] == 50.0
    assert rep["per_tool"]["ctx7"] == {"suggested": 2, "used": 3}
    assert rep["per_tool"]["vercel-skill"] == {"suggested": 1, "used": 0}


def test_usage_report_empty_inputs() -> None:
    rep = usage_report([], {})
    assert rep["percent_used"] == 0.0
    assert rep["tools_suggested"] == 0


def test_usage_report_script_end_to_end(tmp_path: Path) -> None:
    """El script CLI completo, con ficheros sintéticos reales."""
    from atlas.mcp.tool_usage import ToolUsageCounter

    sugg = tmp_path / "routing_suggestions.jsonl"
    append_suggestion(sugg, prompt="usar context7", hits=[_hit("ctx7")], ts=1.0)
    counter = ToolUsageCounter(tmp_path / "tool_usage.json")
    counter.record("mcp__ctx7__resolve_library_id")

    proc = subprocess.run(
        [
            sys.executable,
            str(_REPO_ROOT / "scripts" / "router_usage_report.py"),
            "--suggestions", str(sugg),
            "--usage", str(tmp_path / "tool_usage.json"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env={"PYTHONPATH": str(_REPO_ROOT / "src"), "PATH": ""},
    )
    assert proc.returncode == 0, proc.stderr
    rep = json.loads(proc.stdout)
    assert rep["percent_used"] == 100.0
    assert rep["per_tool"]["ctx7"]["used"] == 1


# ---------------------------------------------------------------------------
# Integración por el hook REAL (proceso efímero, como en producción)
# ---------------------------------------------------------------------------

_HOOK_CATALOG = """
sectors:
  programacion:
    label: Programación
    aliases: [coding]
    entries:
      - {name: react-helper, kind: skill, purpose: "revisar componentes react",
         status: instalado, tags: [react, programacion]}
"""


def _run_hook(repo_root: Path, prompt: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(_REPO_ROOT / "scripts" / "capability_route_hook.py"),
            "--prompt", prompt,
            "--repo-root", str(repo_root),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env={"PYTHONPATH": str(_REPO_ROOT / "src"), "PATH": ""},
    )


def test_hook_second_invocation_same_prompt_empty_block(tmp_path: Path) -> None:
    """El test del plan: segunda invocación con el mismo prompt → bloque vacío."""
    design = tmp_path / "docs" / "design"
    design.mkdir(parents=True)
    (design / "mcp_catalog.yaml").write_text(_HOOK_CATALOG, encoding="utf-8")

    first = _run_hook(tmp_path, "revisar componentes react")
    assert first.returncode == 0, first.stderr
    assert "react-helper" in first.stdout

    second = _run_hook(tmp_path, "revisar componentes react")
    assert second.returncode == 0, second.stderr
    assert second.stdout.strip() == ""  # cooldown: bloque vacío

    # Telemetría escrita bajo workspace/mcp del repo-root, sin prompt en claro.
    sugg = tmp_path / "workspace" / "mcp" / "routing_suggestions.jsonl"
    state = tmp_path / "workspace" / "mcp" / "router_cooldown.json"
    assert sugg.is_file() and state.is_file()
    raw = sugg.read_text(encoding="utf-8")
    assert "componentes" not in raw
    entries = read_suggestions(sugg)
    assert len(entries) == 1  # solo la primera invocación sugirió algo
    assert entries[0]["hits"] == ["react-helper"]


def test_hook_no_state_flag_skips_cooldown_and_telemetry(tmp_path: Path) -> None:
    design = tmp_path / "docs" / "design"
    design.mkdir(parents=True)
    (design / "mcp_catalog.yaml").write_text(_HOOK_CATALOG, encoding="utf-8")

    for _ in range(2):
        proc = subprocess.run(
            [
                sys.executable,
                str(_REPO_ROOT / "scripts" / "capability_route_hook.py"),
                "--prompt", "revisar componentes react",
                "--repo-root", str(tmp_path),
                "--no-state",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            env={"PYTHONPATH": str(_REPO_ROOT / "src"), "PATH": ""},
        )
        assert proc.returncode == 0, proc.stderr
        assert "react-helper" in proc.stdout  # sin cooldown: repite

    assert not (tmp_path / "workspace" / "mcp").exists()  # sin estado escrito
