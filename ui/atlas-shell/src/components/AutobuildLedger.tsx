// AutobuildLedger: primera vista real de "que esta construyendo Atlas y como"
// (ADR-068, Dynamic Workflow Control Surface reencuadrada). Lee
// GET /self-build/summary y GET /self-build/proposal/{id} — datos reales
// del ledger de ColdUpdateManager (ADR-025), nunca inventados: si no hay
// ledger, lo dice. El bridge es READ-ONLY (ADR-058): el "next_action" solo
// se MUESTRA como comando de CLI, nunca se ejecuta desde aquí.

import { useEffect, useState } from "react";
import { api } from "../core/api";
import type { SelfBuildProposalDetail, SelfBuildSummary } from "../core/api";

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

function lastLine(text: string | undefined): string {
  if (!text) return "";
  const lines = text.trim().split("\n");
  return lines[lines.length - 1] ?? "";
}

function statusColor(status: string | undefined): string {
  return STATUS_COLOR[status ?? ""] ?? "var(--text-dim)";
}

export function AutobuildLedger() {
  const [summary, setSummary] = useState<SelfBuildSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<SelfBuildProposalDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        setSummary(await api.selfBuildSummary(50));
      } catch (err) {
        setError(String(err));
      }
    })();
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setDetail(null);
    setDetailError(null);
    void (async () => {
      try {
        setDetail(await api.selfBuildProposal(selectedId));
      } catch (err) {
        setDetailError(String(err));
      }
    })();
  }, [selectedId]);

  return (
    <div className="body">
      <div className="harness-banner">
        AUTOBUILD LEDGER — lo que el lazo de autoconstrucción de Atlas
        (ColdUpdateManager, ADR-025) ha propuesto de verdad, sin inventar nada.
        Click en una propuesta para ver ficheros tocados, tests y el
        siguiente comando real (nunca se ejecuta desde aquí — el bridge es
        read-only, ADR-058).
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
              <li
                key={p.id}
                onClick={() => setSelectedId(p.id)}
                style={{
                  cursor: "pointer",
                  background:
                    selectedId === p.id
                      ? "color-mix(in srgb, var(--accent) 10%, transparent)"
                      : undefined,
                }}
              >
                <span
                  className="badge"
                  style={{
                    background: "color-mix(in srgb, " +
                      statusColor(p.status) +
                      " 16%, transparent)",
                    color: statusColor(p.status),
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

          {selectedId && (
            <div className="harness-section" style={{ borderTop: "1px solid var(--border)", paddingTop: 10 }}>
              <h4>Detalle — {selectedId}</h4>

              {detailError && (
                <div className="caps" style={{ color: "var(--warn)" }}>
                  ⚠ error cargando detalle: {detailError}
                </div>
              )}
              {!detail && !detailError && <div className="caps">cargando detalle…</div>}
              {detail && !detail.real && (
                <div className="caps" style={{ color: "var(--warn)" }}>
                  ⚠ {detail.status}: {detail.detail}
                </div>
              )}

              {detail && detail.real && (
                <>
                  <div className="kv" style={{ marginBottom: 10 }}>
                    <dt>ESTADO</dt>
                    <dd>
                      <span
                        className="badge"
                        style={{
                          background: "color-mix(in srgb, " +
                            statusColor(detail.status) +
                            " 16%, transparent)",
                          color: statusColor(detail.status),
                        }}
                      >
                        {detail.status}
                      </span>
                    </dd>
                    <dt>ORIGEN</dt>
                    <dd>{detail.origin} · riesgo {detail.risk}</dd>
                    <dt>BASE</dt>
                    <dd>{detail.base_ref}</dd>
                    <dt>CREADA</dt>
                    <dd>{detail.created_at ? fmtTime(detail.created_at) : "—"}</dd>
                    <dt>ACTUALIZADA</dt>
                    <dd>{detail.updated_at ? fmtTime(detail.updated_at) : "—"}</dd>
                  </div>

                  <h4>Ficheros tocados {detail.patch_available ? "" : "— patch no disponible en disco"}</h4>
                  {detail.files_touched && detail.files_touched.length > 0 ? (
                    <ul className="harness-list">
                      {detail.files_touched.map((f) => (
                        <li key={f} style={{ fontFamily: "var(--font-mono)" }}>{f}</li>
                      ))}
                    </ul>
                  ) : (
                    <div className="caps">sin diff legible para esta propuesta</div>
                  )}

                  <h4>Validación</h4>
                  {detail.validation ? (
                    <div className="kv">
                      <dt>RESULTADO</dt>
                      <dd style={{ color: detail.validation.passed ? "var(--ok)" : "var(--danger)" }}>
                        {detail.validation.passed ? "PASS" : "FAIL"} · {detail.validation.duration_s}s
                      </dd>
                      <dt>PYTEST</dt>
                      <dd>{lastLine(detail.validation.pytest_summary)}</dd>
                      <dt>MYPY</dt>
                      <dd>{detail.validation.mypy_summary}</dd>
                    </div>
                  ) : (
                    <div className="caps">sin validación registrada (propuesta aún no corrió tests)</div>
                  )}

                  {detail.next_action && (
                    <>
                      <h4>Siguiente paso (comando real, no se ejecuta desde aquí)</h4>
                      <pre className="inspector">{detail.next_action}</pre>
                    </>
                  )}
                </>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
