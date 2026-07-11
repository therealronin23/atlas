// AutobuildLedger: primera vista real de "que esta construyendo Atlas y como"
// (ADR-068, Dynamic Workflow Control Surface reencuadrada). Lee
// GET /self-build/summary — datos reales del ledger de ColdUpdateManager
// (ADR-025), nunca inventados: si no hay ledger, lo dice.

import { useEffect, useState } from "react";
import { api } from "../core/api";
import type { SelfBuildSummary } from "../core/api";

const STATUS_COLOR: Record<string, string> = {
  applied: "var(--ok)",
  validated: "var(--accent)",
  proposed: "var(--warn)",
  rejected: "var(--text-dim)",
  failed: "var(--danger)",
  rolled_back: "var(--danger)",
};

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function AutobuildLedger() {
  const [summary, setSummary] = useState<SelfBuildSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        setSummary(await api.selfBuildSummary(50));
      } catch (err) {
        setError(String(err));
      }
    })();
  }, []);

  return (
    <div className="body">
      <div className="harness-banner">
        AUTOBUILD LEDGER — lo que el lazo de autoconstrucción de Atlas
        (ColdUpdateManager, ADR-025) ha propuesto de verdad, sin inventar nada
      </div>

      {error && (
        <div className="caps" style={{ color: "var(--warn)" }}>
          ⚠ error cargando ledger: {error}
        </div>
      )}

      {!summary && !error && <div className="caps">cargando…</div>}

      {summary && !summary.real && (
        <div className="caps" style={{ color: "var(--warn)" }}>
          ⚠ {summary.status}: {summary.detail}
        </div>
      )}

      {summary && summary.real && (
        <>
          <div className="harness-section">
            <h4>Resumen — {summary.total} propuestas registradas</h4>
            <div className="caps">
              por estado:{" "}
              {Object.entries(summary.by_status ?? {})
                .map(([k, v]) => `${k}=${v}`)
                .join(" · ")}
            </div>
            <div className="caps">
              por origen:{" "}
              {Object.entries(summary.by_origin ?? {})
                .map(([k, v]) => `${k}=${v}`)
                .join(" · ")}
            </div>
            <div className="caps">
              por riesgo:{" "}
              {Object.entries(summary.by_risk ?? {})
                .map(([k, v]) => `${k}=${v}`)
                .join(" · ")}
            </div>
          </div>

          <h3>Últimas {summary.recent?.length ?? 0} propuestas</h3>
          <ul className="harness-list">
            {(summary.recent ?? []).map((p) => (
              <li key={p.id}>
                <span
                  className="badge"
                  style={{
                    background: "color-mix(in srgb, " +
                      (STATUS_COLOR[p.status] ?? "var(--text-dim)") +
                      " 16%, transparent)",
                    color: STATUS_COLOR[p.status] ?? "var(--text-dim)",
                  }}
                >
                  {p.status}
                </span>{" "}
                {p.intent}
                <span className="caps">
                  {" "}
                  · origen: {p.origin} · riesgo: {p.risk} ·{" "}
                  {fmtTime(p.created_at)}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
