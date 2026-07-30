"""Regresión 2026-07-30: `inference_hub` dejó de cargar `.env` al importarse.

El commit 5da5f5f ("fix: close adversarial audit findings", 2026-07-16)
reestructuró el import de litellm a perezoso y, como efecto colateral no
mencionado en el commit, eliminó la llamada a `load_dotenv()`. Sin
cobertura de test, pasó desapercibido ~2 semanas: cualquier proceso que
construya `InferenceHub` sin tener ya las API keys en el entorno (systemd
sin `EnvironmentFile`, un script suelto, una sesión interactiva) cae
fail-closed en silencio para TODOS los proveedores.

Corre en un subproceso aislado a propósito -- `importlib.reload()` del
módulo real dentro del proceso de pytest compartido crea una clase
`Provider` nueva mientras otros módulos ya importados (orchestrator,
maintenance_facade...) conservan la clase vieja, rompiendo comparaciones
`is`/`isinstance` para el resto de la sesión (hallazgo real del primer
intento de este mismo test, ver historial del commit).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_importing_inference_hub_loads_dotenv() -> None:
    script = (
        "from unittest.mock import patch\n"
        "with patch('dotenv.load_dotenv') as mock_load:\n"
        "    import atlas.core.inference_hub\n"
        "    assert mock_load.call_count == 1, mock_load.call_count\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"
