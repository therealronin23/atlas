// Memory Vault v1: verdad honesta — resumen REAL del índice canónico +
// eventos memory.* de la sesión. La exploración profunda llega en Fase 8.

import type { MemorySummary, OsEvent } from "../core/types";

interface Props {
  memory: MemorySummary | null;
  events: OsEvent[];
}

export function MemoryVault({ memory, events }: Props) {
  const memEvents = events.filter((e) => e.type.startsWith("memory.")).slice(-30).reverse();
  return (
    <div className="body">
      <div style={{ marginBottom: 10 }}>
        {memory?.real ? (
          <>
            Índice canónico (ADR-057): <strong>{memory.records}</strong> registros en{" "}
            <code>{memory.db}</code> <span className="badge real">REAL</span>
          </>
        ) : (
          <>
            Índice canónico no disponible: {memory?.detail ?? memory?.status ?? "…"}{" "}
            <span className="badge sim">N/D</span>
          </>
        )}
      </div>
      <div style={{ color: "var(--text-dim)", fontSize: 11, marginBottom: 8 }}>
        Actividad de memoria en esta sesión:
      </div>
      {memEvents.length === 0 && (
        <div style={{ color: "var(--text-dim)" }}>Sin eventos memory.* todavía.</div>
      )}
      {memEvents.map((e) => (
        <div key={e.id} className="timeline-row">
          <span className="time">{e.timestamp.slice(11, 19)}</span>
          <span className="summary">{e.summary}</span>
          <span className={`badge ${e.simulated ? "sim" : "real"}`}>
            {e.simulated ? "SIM" : "REAL"}
          </span>
        </div>
      ))}
    </div>
  );
}
