// Integration Fabric: conectores del bridge (mock-first, sin secretos).

import { useState } from "react";
import { api } from "../../core/api";
import type { ConnectorSpec } from "../../core/types";

export function IntegrationFabric({ connectors }: { connectors: ConnectorSpec[] }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, string>>({});

  const run = async (id: string, kind: "test" | "sync") => {
    setBusy(id);
    try {
      const res =
        kind === "test" ? await api.testConnector(id) : await api.syncConnector(id);
      setResults((r) => ({
        ...r,
        [id]: `${kind} ok (${res.simulated ? "simulado" : "real"})`,
      }));
    } catch (err) {
      setResults((r) => ({ ...r, [id]: `${kind} error: ${String(err)}` }));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="body">
      <div className="card-grid">
        {connectors.map((c) => (
          <div key={c.connector_id} className="card">
            <h3>
              {c.display_name}
              <span className="badge mode">{c.mode.toUpperCase()}</span>
              <span className={`badge risk-${c.risk_level}`}>{c.risk_level}</span>
            </h3>
            <div className="caps">
              lee: {c.read_capabilities.join(", ") || "—"}
              <br />
              escribe: {c.write_capabilities.join(", ") || "—"}
            </div>
            <div className="caps">
              credencial: <code>{c.credential_reference ?? "ninguna (mock)"}</code>
            </div>
            {c.legal_notes && (
              <div className="caps" style={{ color: "var(--warn)" }}>
                ⚠ {c.legal_notes}
              </div>
            )}
            <div className="row">
              <button
                className="small"
                disabled={busy === c.connector_id}
                onClick={() => run(c.connector_id, "test")}
              >
                Probar
              </button>
              <button
                className="small"
                disabled={busy === c.connector_id}
                onClick={() => run(c.connector_id, "sync")}
              >
                Sync
              </button>
              <span className="caps">{results[c.connector_id] ?? ""}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
