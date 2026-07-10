"""Atlas OS — Event Kernel (ADR-058).

Canon de eventos OS como PROYECCIÓN del EventBus existente, nunca un segundo
bus. Este paquete contiene el modelo del evento (espejo de
schemas/event.schema.json), el event store JSONL con replay y el bridge
suscriptor del bus del core.
"""

from atlas.events.schemas import GraphEdge, GraphNode, OsEvent
from atlas.events.store import OsEventStore

__all__ = ["GraphEdge", "GraphNode", "OsEvent", "OsEventStore"]
