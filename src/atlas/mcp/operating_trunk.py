"""
Atlas Core — OperatingTrunk: la raíz `operating` del MCP trunk portable (F2).

Capa NEUTRA, transport-agnostic: expone la disciplina operativa del repo de forma
portable. OPERATING LOOP + manías (AGENTS.md) y el estado vivo (WORK_LEDGER.md)
como texto que cualquier cliente puede extraer al arrancar; `sanitation_audit`
como tool read-only (el radar del ciclo de saneamiento, REPO_STANDARD §3).

NO sabe nada de MCP; el shell FastMCP se monta encima. Honesto: estos recursos son
ADVISORY — MCP no puede IMPONER comportamiento; el cliente decide cargarlos. La
imposición real (franken-prompt) exige un canal de system-prompt de verdad, fuera
de la primitiva MCP (ver design doc).

Diseño: docs/design/mcp_trunk_portable.md (F2).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


class OperatingTrunk:
    """Disciplina operativa del repo como recursos + tool, sobre `repo_root`."""

    def __init__(self, repo_root: Path) -> None:
        self._root = Path(repo_root)

    def _read(self, rel: str) -> str:
        path = self._root / rel
        if not path.is_file():
            raise FileNotFoundError(f"operating: no existe {rel} bajo {self._root}")
        return path.read_text(encoding="utf-8")

    def agents_md(self) -> str:
        """OPERATING LOOP + manías + pre-flight (la disciplina cross-tool)."""
        return self._read("AGENTS.md")

    def work_ledger(self) -> str:
        """Estado vivo de la matrioska (fuente única del '¿dónde estamos?')."""
        return self._read("WORK_LEDGER.md")

    def sanitation_audit(self) -> str:
        """Corre el radar read-only de saneamiento y devuelve su informe.
        No actúa (no borra ni mueve); el humano/agente decide KEEP/QUARANTINE/DELETE."""
        script = self._root / "scripts" / "sanitation_audit.py"
        if not script.is_file():
            raise FileNotFoundError(f"operating: no existe {script}")
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(self._root),
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.stdout
