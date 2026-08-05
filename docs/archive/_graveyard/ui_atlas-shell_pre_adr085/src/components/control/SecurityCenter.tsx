// Security Center: aprobaciones pendientes + eventos de governance/auditoría.

import type { OsEvent } from "../../core/types";

interface Props {
  pendingApprovals: OsEvent[];
  events: OsEvent[];
}

export function SecurityCenter({ pendingApprovals, events }: Props) {
  const security = events
    .filter(
      (e) =>
        e.type.startsWith("permission.") ||
        e.type.startsWith("approval.") ||
        e.type.startsWith("gate.") ||
        e.type.startsWith("security.") ||
        e.type === "audit.logged",
    )
    .slice(-40)
    .reverse();

  return (
    <div className="body">
      <h3 style={{ marginTop: 0 }}>Aprobaciones pendientes</h3>
      {pendingApprovals.length === 0 && (
        <div style={{ color: "var(--text-dim)", marginBottom: 12 }}>
          Ninguna. Todo outbound está bloqueado por defecto hasta que un humano
          apruebe (gate_outbound).
        </div>
      )}
      {pendingApprovals.map((e) => (
        <div key={e.id} className="approval">
          <strong>{e.summary}</strong>
          <div className="caps">
            {String(e.payload["action"] ?? "")} · proceso {e.process_id ?? "—"} ·{" "}
            la aprobación/denegación real ocurre en el runtime, no aquí (v1 solo
            representa).
          </div>
        </div>
      ))}
      <h3>Actividad de governance</h3>
      {security.length === 0 && (
        <div style={{ color: "var(--text-dim)" }}>Sin eventos de seguridad aún.</div>
      )}
      {security.map((e) => (
        <div key={e.id} className="timeline-row">
          <span className="time">{e.timestamp.slice(11, 19)}</span>
          <span className="type">{e.type}</span>
          <span className="summary">{e.summary}</span>
          <span className={`badge risk-${e.risk}`}>{e.risk}</span>
        </div>
      ))}
    </div>
  );
}
