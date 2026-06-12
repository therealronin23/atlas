"""ADR-039 slice 3 — wire propuesta → adopción (reuso puro del seam).

Cierra el lazo end-to-end del agente de auto-mantenimiento: una ``McpProposal``
corroborada (slice 2) se traduce a ``McpServerConfig`` + ``Task`` y se delega en
``Orchestrator.adopt_mcp_server``, que ya consulta el decisor (ADR-040) y, si
autoriza, hace ``add_server`` en caliente + registra el undo reversible.

**El adopter NO decide.** El "botón HITL" del ADR es una implementación más del
decisor (rumbo human-ON-the-loop): bajo ``HumanDecider`` el seam devuelve
"requiere aprobación humana" y nada se adopta; bajo autónomo/híbrido con la
intención anclada al nombre del server, adopta. Aquí no vive ninguna máquina de
aprobación nueva — solo la traducción proposal→cfg+task, la invocación del seam
y la auditoría del resultado.

La intención se ancla léxicamente al nombre del server por construcción
(``...{capability}...``) para satisfacer el invariante de coherencia del decisor
autónomo (una mutación debe estar anclada en la intención sancionada).
"""

from __future__ import annotations

from collections.abc import Callable

from atlas.core.contracts import Task, TaskSource
from atlas.core.self_maintenance.candidate import McpProposal
from atlas.logging.merkle_logger import MerkleLogger
from atlas.mcp import McpServerConfig


class MaintenanceAdopter:
    """Traduce una propuesta aprobada en una adopción real vía el seam del decisor.

    Recibe el callable ``adopt`` (``Orchestrator.adopt_mcp_server``) por
    inyección — mismo estilo que el Scout — en vez del orquestador entero.
    """

    AGENT = "self_maintenance.adopter"

    # El primer arranque de un server recién descubierto descarga su paquete
    # (npx baja de npm, uvx de PyPI) antes de responder al handshake. El budget
    # por defecto (15s) lo agota; este es más holgado SOLO para la adopción
    # autónoma (primer contacto), no para los servers ya configurados.
    _FIRST_LAUNCH_TIMEOUT_S = 90.0

    def __init__(
        self,
        *,
        adopt: Callable[[McpServerConfig, Task], str],
        merkle: MerkleLogger,
    ) -> None:
        self._adopt = adopt
        self._merkle = merkle

    def adopt(self, proposal: McpProposal) -> str:
        """Intenta adoptar el server de ``proposal``. Devuelve el status textual
        del seam (``ok:`` / ``requiere aprobación humana`` / ``denegado:`` /
        ``error:``). No lanza: el veredicto del decisor es un resultado, no un
        fallo."""
        cfg = McpServerConfig(
            name=proposal.capability,
            cmd=list(proposal.cmd),
            timeout_seconds=self._FIRST_LAUNCH_TIMEOUT_S,
        )
        task = Task(
            intent=f"adopta el server MCP {proposal.capability} v{proposal.version}",
            source=TaskSource.INTERNAL,
        )
        status = self._adopt(cfg, task)
        self._audit(proposal, status)
        return status

    def _audit(self, proposal: McpProposal, status: str) -> None:
        adopted = status.startswith("ok:")
        try:
            self._merkle.log(
                action="self_maintenance.adopter_adopt",
                agent=self.AGENT,
                result="adopted" if adopted else "not_adopted",
                risk_level="high",
                payload={
                    "proposal_id": proposal.id,
                    "capability": proposal.capability,
                    "version": proposal.version,
                    "adopted": adopted,
                    "status": status,
                },
            )
        except Exception:  # noqa: BLE001 — la auditoría no rompe la adopción
            pass
