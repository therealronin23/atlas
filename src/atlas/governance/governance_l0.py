"""
Atlas Core — Governance L0
Constitucion inmutable. Primera capa de seguridad.
Ningun agente, instruccion ni respuesta de modelo puede modificar
el estado de Governance L0 en memoria.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final


# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GovernanceViolation:
    pattern: str
    intent: str
    hard_block: str


@dataclass(frozen=True)
class GovernanceState:
    version: str
    axioms: dict[str, str]
    hard_blocks: tuple[str, ...]
    hard_block_patterns: tuple[str, ...]
    file_hash: str  # SHA-256 del governance.json original

    def describe(self) -> str:
        lines = [f"Atlas Governance L0 v{self.version}", ""]
        lines.append("Axiomas:")
        for k, v in self.axioms.items():
            lines.append(f"  [{k}] {v}")
        lines.append("\nBloqueos absolutos:")
        for b in self.hard_blocks:
            lines.append(f"  - {b}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# GovernanceL0
# ---------------------------------------------------------------------------

class GovernanceL0:
    """
    Singleton. Se carga una vez y permanece inmutable en memoria.
    Cualquier intento de modificar el archivo governance.json en disco
    durante la ejecucion se detecta y genera una alerta de emergencia.
    """

    _instance: "GovernanceL0 | None" = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self, config_path: Path) -> None:
        raw = config_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        file_hash = hashlib.sha256(raw.encode()).hexdigest()

        self._state: Final[GovernanceState] = GovernanceState(
            version=data["version"],
            axioms=dict(data["axioms"]),
            hard_blocks=tuple(data["hard_blocks"]),
            hard_block_patterns=tuple(data.get("hard_block_patterns", [])),
            file_hash=file_hash,
        )
        self._config_path: Final[Path] = config_path
        self._emergency_mode: bool = False

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls) -> "GovernanceL0":
        if cls._instance is None:
            raise RuntimeError(
                "GovernanceL0 no inicializado. "
                "Llama a GovernanceL0.initialize(config_path) primero."
            )
        return cls._instance

    @classmethod
    def initialize(cls, config_path: Path) -> "GovernanceL0":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(config_path)
        return cls._instance

    # ------------------------------------------------------------------
    # Verificacion de integridad en disco
    # ------------------------------------------------------------------

    def check_file_integrity(self) -> bool:
        """
        Verifica que governance.json en disco no ha sido modificado.
        Retorna True si es integro, False si ha sido alterado.
        Llama a enter_emergency_mode() si detecta tamper.
        """
        try:
            raw = self._config_path.read_text(encoding="utf-8")
            current_hash = hashlib.sha256(raw.encode()).hexdigest()
            if current_hash != self._state.file_hash:
                self._enter_emergency_mode(
                    f"governance.json modificado en disco. "
                    f"Hash esperado: {self._state.file_hash[:16]}... "
                    f"Hash actual: {current_hash[:16]}..."
                )
                return False
            return True
        except Exception as e:
            self._enter_emergency_mode(f"No se puede leer governance.json: {e}")
            return False

    # ------------------------------------------------------------------
    # Evaluacion de intenciones
    # ------------------------------------------------------------------

    def evaluate(self, intent: str) -> GovernanceViolation | None:
        """
        Evalua una intencion contra los patrones de bloqueo absoluto.
        Retorna None si la intencion es aceptable.
        Retorna GovernanceViolation si debe bloquearse.
        """
        if self._emergency_mode:
            return GovernanceViolation(
                pattern="emergency_mode",
                intent=intent,
                hard_block="Atlas esta en modo de emergencia. No acepta tareas.",
            )

        intent_lower = intent.lower()
        for pattern in self._state.hard_block_patterns:
            if re.search(pattern, intent_lower, re.IGNORECASE):
                # Identificar el hard_block mas relevante
                relevant = self._find_relevant_hard_block(pattern)
                return GovernanceViolation(
                    pattern=pattern,
                    intent=intent,
                    hard_block=relevant,
                )
        return None

    def is_hard_blocked(self, intent: str) -> bool:
        return self.evaluate(intent) is not None

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    @property
    def state(self) -> GovernanceState:
        return self._state

    @property
    def in_emergency_mode(self) -> bool:
        return self._emergency_mode

    # ------------------------------------------------------------------
    # Privado
    # ------------------------------------------------------------------

    def _enter_emergency_mode(self, reason: str) -> None:
        self._emergency_mode = True
        # Escribir en log de emergencia separado (fuera del Merkle Logger)
        emergency_log = self._config_path.parent.parent / "memory" / "audit" / "emergency.log"
        emergency_log.parent.mkdir(parents=True, exist_ok=True)
        with emergency_log.open("a", encoding="utf-8") as f:
            from datetime import datetime, timezone
            f.write(json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "GOVERNANCE_TAMPER_DETECTED",
                "reason": reason,
            }) + "\n")

    def _find_relevant_hard_block(self, pattern: str) -> str:
        for block in self._state.hard_blocks:
            block_lower = block.lower()
            if any(kw in block_lower for kw in pattern.lower().split("\\s+")):
                return block
        return self._state.hard_blocks[0]
