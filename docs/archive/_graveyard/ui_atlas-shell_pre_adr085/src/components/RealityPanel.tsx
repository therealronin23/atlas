// Reality/System Panel: datos REALES del core (atlas reality) + salud del bridge.

import type { HealthInfo, MemorySummary, RealityReport } from "../core/types";

interface Props {
  health: HealthInfo | null;
  reality: RealityReport | null;
  memory: MemorySummary | null;
  memoryUpdates: number;
}

export function RealityPanel({ health, reality, memory, memoryUpdates }: Props) {
  return (
    <div className="body">
      <dl className="kv">
        <dt>Bridge</dt>
        <dd>
          {health ? (
            <>
              {health.status} <span className="badge real">REAL</span>
            </>
          ) : (
            "sin conexión"
          )}
        </dd>
        {reality && (
          <>
            <dt>Repo</dt>
            <dd>
              v{reality.repo.version} · {reality.repo.branch}@{reality.repo.commit}
              {reality.repo.dirty ? ` · dirty(${reality.repo.dirty_count})` : ""}
            </dd>
            <dt>Merkle</dt>
            <dd>
              {reality.workspace.merkle.status} ·{" "}
              {reality.workspace.merkle.record_count} registros{" "}
              <span className="badge real">REAL</span>
            </dd>
          </>
        )}
        <dt>Memoria</dt>
        <dd>
          {memory?.real ? (
            <>
              {memory.records} registros <span className="badge real">REAL</span>
            </>
          ) : (
            <>
              {memory?.status ?? "…"} <span className="badge sim">N/D</span>
            </>
          )}
        </dd>
        <dt>Eventos OS</dt>
        <dd>{health?.os_events ?? "…"}</dd>
        <dt>memory.updated</dt>
        <dd>{memoryUpdates} en esta sesión</dd>
      </dl>
    </div>
  );
}
