"""LogBehavioralAuditor (OSM-031) — detección de cambio conductual desde el log.

Cablea la observación de deriva conductual al log co-firmado en vez de re-ejecutar
el modelo. El log ya ancla, por `seq`, el `payload_hash` de la entrada
(InspectionRecord) y el `output_hash` de la salida (OutputInspectionRecord). Por
tanto, si un MISMO input (mismo payload_hash) produjo outputs DISTINTOS a lo largo
del tiempo, es una señal de cambio encubierto del modelo — y la evidencia está en
la cadena, es verificable, sin tocar el modelo.

Límites honestos:
  - Solo hay señal para inputs que RECURREN en el log (payload_hash visto >= 2).
  - Un output distinto puede ser legítimo (no-determinismo, actualización anunciada):
    esto FLAGGEA para investigación, NO prueba manipulación.
  - No cubre cambios sobre inputs nunca repetidos (cobertura, no garantía).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atlas.transparency.log import TransparencyLog


@dataclass(frozen=True)
class CovertChangeFinding:
    """Mismo input, outputs distintos a lo largo del log.

    Attributes
    ----------
    input_hash:     payload_hash del input recurrente.
    seqs:           seqs en los que se observó ese input (orden de aparición).
    output_hashes:  output_hashes DISTINTOS observados (orden de primera aparición).
    """

    input_hash: str
    seqs: tuple[int, ...]
    output_hashes: tuple[str, ...]


def audit_entries(entries: list[bytes]) -> list[CovertChangeFinding]:
    """Escanea leaves crudos del log y devuelve hallazgos de cambio encubierto.

    Función pura (testeable sin un log real). Empareja input↔output por `seq`.
    """
    inputs: dict[int, str] = {}        # seq → payload_hash
    outputs: dict[int, str] = {}       # seq → output_hash
    for leaf in entries:
        try:
            doc = json.loads(leaf.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        seq = doc.get("seq")
        if not isinstance(seq, int):
            continue
        if "payload_hash" in doc and "output_hash" not in doc:
            inputs[seq] = str(doc["payload_hash"])
        elif "output_hash" in doc:
            outputs[seq] = str(doc["output_hash"])

    # Agrupar output_hash por input_hash, en orden de seq.
    by_input: dict[str, list[tuple[int, str]]] = {}
    for seq in sorted(set(inputs) & set(outputs)):
        by_input.setdefault(inputs[seq], []).append((seq, outputs[seq]))

    findings: list[CovertChangeFinding] = []
    for input_hash, obs in by_input.items():
        distinct: list[str] = []
        for _seq, oh in obs:
            if oh not in distinct:
                distinct.append(oh)
        if len(distinct) >= 2:  # mismo input, >=2 outputs distintos
            findings.append(CovertChangeFinding(
                input_hash=input_hash,
                seqs=tuple(seq for seq, _ in obs),
                output_hashes=tuple(distinct),
            ))
    return findings


class LogBehavioralAuditor:
    """Audita un TransparencyLog en busca de cambio conductual encubierto."""

    def __init__(self, log: "TransparencyLog") -> None:
        self._log = log

    def audit(self) -> list[CovertChangeFinding]:
        """Devuelve los hallazgos sobre el estado actual del log."""
        return audit_entries(self._log.entries())
