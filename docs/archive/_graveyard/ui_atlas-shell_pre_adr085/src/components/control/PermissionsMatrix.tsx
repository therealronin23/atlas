// Permissions Matrix + probador del evaluador fail-closed del bridge.

import { useState } from "react";
import { api } from "../../core/api";
import type { GateSpec, PermissionEvaluation } from "../../core/types";

export function PermissionsMatrix({ gates }: { gates: GateSpec[] }) {
  const [action, setAction] = useState("mail.send");
  const [result, setResult] = useState<PermissionEvaluation | null>(null);

  const evaluate = async () => {
    const res = await api.evaluate(action, "control-plane-test");
    setResult(res.evaluation);
  };

  return (
    <div className="body">
      <div className="row" style={{ display: "flex", gap: 8, marginBottom: 14 }}>
        <input
          style={{
            flex: 1,
            background: "var(--bg-raised)",
            border: "1px solid var(--border)",
            color: "var(--text)",
            borderRadius: 8,
            padding: "7px 10px",
          }}
          value={action}
          onChange={(e) => setAction(e.target.value)}
          placeholder="acción, p.ej. mail.send"
        />
        <button className="primary" onClick={evaluate}>
          Evaluar
        </button>
      </div>
      {result && (
        <div className="approval" style={{ marginBottom: 14 }}>
          <strong>{result.action}</strong> → <strong>{result.decision}</strong>{" "}
          <span className={`badge risk-${result.risk}`}>{result.risk}</span>
          <div className="caps" style={{ marginTop: 4 }}>
            {result.reason}
            {result.gate_id ? ` · ${result.gate_id}` : ""}
          </div>
        </div>
      )}
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr style={{ color: "var(--text-dim)", textAlign: "left" }}>
            <th style={{ padding: 6 }}>Gate</th>
            <th>Cubre</th>
            <th>Modo</th>
            <th>Decisión</th>
            <th>Riesgo</th>
          </tr>
        </thead>
        <tbody>
          {gates.map((g) => (
            <tr key={g.gate_id} style={{ borderTop: "1px solid var(--border)" }}>
              <td style={{ padding: 6 }}>
                <strong>{g.display_name}</strong>
                <div className="caps">{g.gate_id}</div>
              </td>
              <td style={{ fontFamily: "monospace", fontSize: 11 }}>
                {g.applies_to.join(", ")}
              </td>
              <td>{g.approval_mode}</td>
              <td>{g.default_decision}</td>
              <td>
                <span className={`badge risk-${g.risk_threshold}`}>
                  {g.risk_threshold}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="caps" style={{ marginTop: 10 }}>
        Evaluador v1 sobre gates de fixture (fail-closed: lo no cubierto y no-lectura
        requiere aprobación). La autoridad real sigue siendo governance/ del core.
      </div>
    </div>
  );
}
