// MissionConsole (Foundry v0, ADR-069): el centro mental del shell.
// No "vistas del sistema" sino "sistema de decisión": el radar dirige la
// atención (ask > gate > radar), la lista prioriza misiones que esperan
// decisión humana, y el inspector cuenta el Cognitive Trace de la misión
// con su receipt (qué pasó / por qué importa / qué hizo Atlas / qué falta /
// qué decisión se necesita). Datos 100% reales del ledger de ColdUpdate vía
// /missions — el bridge es READ-ONLY (ADR-058): los comandos se muestran y
// se copian, JAMÁS se ejecutan desde aquí.

import { useEffect, useMemo, useState } from "react";
import { api } from "../core/api";
import type {
  Mission,
  MissionDetailResponse,
  MissionsResponse,
  RadarFinding,
  RadarResponse,
} from "../core/api";

const STATE_LABEL: Record<string, string> = {
  plan_proposed: "PLAN PROPUESTO",
  awaiting_human_approval: "ESPERA DECISIÓN",
  approved_pending_apply: "APROBADA · SIN APLICAR",
  applied: "APLICADA",
  parked: "APARCADA",
  rejected: "RECHAZADA",
  failed: "FALLIDA",
  unknown: "DESCONOCIDO",
};

const STATE_COLOR: Record<string, string> = {
  plan_proposed: "var(--warn)",
  awaiting_human_approval: "var(--ember)",
  approved_pending_apply: "var(--accent-2)",
  applied: "var(--ok)",
  parked: "var(--text-dim)",
  rejected: "var(--text-dim)",
  failed: "var(--danger)",
  unknown: "var(--text-dim)",
};

const RISK_COLOR: Record<string, string> = {
  none: "var(--text-dim)",
  low: "var(--text-dim)",
  medium: "var(--warn)",
  high: "var(--danger)",
  critical: "var(--danger)",
};

const SEVERITY_META: Record<string, { label: string; color: string }> = {
  ask: { label: "DECISIÓN", color: "var(--ember)" },
  gate: { label: "GATE", color: "var(--danger)" },
  radar: { label: "RADAR", color: "var(--accent)" },
  silent: { label: "SILENT", color: "var(--text-dim)" },
};

const DETECTOR_LABEL: Record<string, string> = {
  repeated_proposal: "PROPUESTA REPETIDA",
  stale_proposal: "SIN MOVIMIENTO",
  validation_missing: "SIN VALIDACIÓN",
  gate_pending: "ESPERA HUMANA",
};

function stateColor(state: string): string {
  return STATE_COLOR[state] ?? "var(--text-dim)";
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function relTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const ms = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(ms)) return "";
  const h = Math.floor(ms / 3_600_000);
  if (h < 1) return `hace ${Math.max(1, Math.floor(ms / 60_000))}m`;
  if (h < 48) return `hace ${h}h`;
  return `hace ${Math.floor(h / 24)}d`;
}

function StateChip({ state }: { state: string }) {
  return (
    <span
      className="mc-chip"
      style={{
        color: stateColor(state),
        borderColor: `color-mix(in srgb, ${stateColor(state)} 45%, transparent)`,
        background: `color-mix(in srgb, ${stateColor(state)} 10%, transparent)`,
      }}
    >
      {STATE_LABEL[state] ?? state}
    </span>
  );
}

function RadarStrip({
  radar,
  error,
  onFocus,
}: {
  radar: RadarResponse | null;
  error: string | null;
  onFocus: (missionId: string) => void;
}) {
  if (error) {
    return <div className="caps" style={{ color: "var(--warn)" }}>⚠ radar: {error}</div>;
  }
  if (!radar) return <div className="caps">radar cargando…</div>;
  if (!radar.real) {
    return (
      <div className="caps" style={{ color: "var(--warn)" }}>
        ⚠ {radar.status}: {radar.detail}
      </div>
    );
  }
  const findings = (radar.findings ?? []).filter((f) => f.severity !== "silent");
  if (findings.length === 0) {
    return (
      <div className="mc-radar-quiet">
        <span className="mc-sweep" aria-hidden />
        RADAR EN SILENCIO — sin anomalías en el lazo de autoconstrucción
      </div>
    );
  }
  // Atención dirigida, no mar de tarjetas: decisiones (gate/ask) y bucles
  // (repeated) se muestran una a una; los detectores de mantenimiento
  // (stale/validation_missing) se agregan en UNA tarjeta-resumen cada uno.
  const order: Record<string, number> = { gate: 0, ask: 1, radar: 2, silent: 3 };
  const individual = findings.filter(
    (f) => f.severity === "gate" || f.severity === "ask"
      || f.detector === "repeated_proposal",
  );
  const aggregated: RadarFinding[] = [];
  for (const detector of ["stale_proposal", "validation_missing"]) {
    const group = findings.filter(
      (f) => f.detector === detector && !individual.includes(f),
    );
    if (group.length === 1) individual.push(group[0]);
    else if (group.length > 1) {
      aggregated.push({
        detector,
        severity: "radar",
        summary: `${group.length} propuestas — la más reciente: ${group[0].summary}`,
        mission_ids: group.flatMap((f) => f.mission_ids),
        evidence: group.flatMap((f) => f.evidence).slice(0, 12),
      });
    }
  }
  const sorted = [...individual, ...aggregated].sort(
    (a, b) => (order[a.severity] ?? 9) - (order[b.severity] ?? 9),
  );
  return (
    <div className="mc-radar-row">
      {sorted.map((f: RadarFinding, i) => {
        const meta = SEVERITY_META[f.severity] ?? SEVERITY_META.radar;
        return (
          <button
            key={`${f.detector}-${i}`}
            className={`mc-radar-card ${f.severity === "ask" ? "mc-pulse" : ""}`}
            style={{
              borderColor: `color-mix(in srgb, ${meta.color} 45%, transparent)`,
              animationDelay: `${i * 70}ms`,
            }}
            onClick={() => f.mission_ids[0] && onFocus(f.mission_ids[0])}
            title={f.evidence.join("\n")}
          >
            <span className="mc-radar-head">
              <span style={{ color: meta.color }}>{meta.label}</span>
              <span className="caps">{DETECTOR_LABEL[f.detector] ?? f.detector}</span>
              {f.mission_ids.length > 1 && (
                <span className="caps">×{f.mission_ids.length}</span>
              )}
            </span>
            <span className="mc-radar-summary">{f.summary}</span>
          </button>
        );
      })}
    </div>
  );
}

function ReceiptPanel({ detail }: { detail: MissionDetailResponse }) {
  const receipt = detail.receipt;
  if (!receipt) return null;
  const rows: Array<[string, string]> = [
    ["QUÉ PASÓ", receipt.what_happened],
    ["POR QUÉ IMPORTA", receipt.why_it_matters],
    ["QUÉ HIZO ATLAS", receipt.what_atlas_did],
    ["QUÉ FALTA", receipt.whats_missing],
    ["DECISIÓN", receipt.decision_needed],
  ];
  return (
    <div className="mc-receipt">
      <div className="mc-receipt-head">
        <span>RECIBO · {receipt.receipt_id}</span>
        <span
          className="mc-chip"
          style={{
            color: receipt.verifiable ? "var(--ok)" : "var(--warn)",
            borderColor: `color-mix(in srgb, ${
              receipt.verifiable ? "var(--ok)" : "var(--warn)"
            } 45%, transparent)`,
          }}
        >
          {receipt.verifiable ? "✓ VERIFICABLE" : "◌ SIN VALIDACIÓN"}
        </span>
      </div>
      {rows.map(([label, value]) => (
        <div className="mc-receipt-row" key={label}>
          <span className="mc-receipt-label">{label}</span>
          <span>{value}</span>
        </div>
      ))}
      <div className="mc-receipt-refs">
        {receipt.evidence_refs.map((ref) => (
          <code key={ref}>{ref}</code>
        ))}
      </div>
    </div>
  );
}

function Inspector({
  missionId,
  detail,
  error,
}: {
  missionId: string | null;
  detail: MissionDetailResponse | null;
  error: string | null;
}) {
  const [copied, setCopied] = useState(false);
  useEffect(() => setCopied(false), [missionId]);

  if (!missionId) {
    return (
      <div className="mc-empty">
        selecciona una misión — o deja que el radar te lleve a la que espera tu
        decisión
      </div>
    );
  }
  if (error) {
    return <div className="caps" style={{ color: "var(--warn)" }}>⚠ {error}</div>;
  }
  if (!detail) return <div className="caps">cargando misión…</div>;
  if (!detail.real || !detail.mission) {
    return (
      <div className="caps" style={{ color: "var(--warn)" }}>
        ⚠ {detail.status}: {detail.detail}
      </div>
    );
  }
  const m = detail.mission;
  const validation = m.evidence_bundle.validation as
    | { passed?: boolean; pytest_exit?: number; mypy_exit?: number; duration_s?: number }
    | null;

  return (
    <div className="mc-inspector">
      <div className="mc-inspector-head">
        <span className="caps">{m.mission_id}</span>
        <StateChip state={m.state} />
      </div>
      <div className="mc-intent">{m.intent}</div>
      <div className="kv" style={{ marginBottom: 10 }}>
        <dt>ORIGEN</dt>
        <dd>
          {m.origin} · fuente {m.source.kind}
        </dd>
        <dt>RIESGO</dt>
        <dd style={{ color: RISK_COLOR[m.risk] ?? "var(--text-dim)" }}>
          {m.risk}
        </dd>
        <dt>CREADA</dt>
        <dd>{fmtTime(m.created_at)}</dd>
        <dt>ACTUALIZADA</dt>
        <dd>
          {fmtTime(m.updated_at)} <span className="caps">{relTime(m.updated_at)}</span>
        </dd>
        {validation && (
          <>
            <dt>VALIDACIÓN</dt>
            <dd style={{ color: validation.passed ? "var(--ok)" : "var(--danger)" }}>
              {validation.passed ? "PASS" : "FAIL"} · pytest_exit=
              {String(validation.pytest_exit ?? "?")} · mypy_exit=
              {String(validation.mypy_exit ?? "?")}
            </dd>
          </>
        )}
      </div>

      {m.artifacts.length > 0 && (
        <>
          <h4>Ficheros tocados ({m.artifacts.length})</h4>
          <ul className="harness-list mc-files">
            {m.artifacts.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </>
      )}

      {m.next_action && (
        <div className="mc-next">
          <div className="mc-next-label">
            SIGUIENTE ACCIÓN — comando humano real (nunca se ejecuta desde aquí)
          </div>
          <div className="mc-next-cmd">
            <code>{m.next_action.command}</code>
            <button
              className="mc-copy"
              onClick={() => {
                void navigator.clipboard
                  .writeText(m.next_action?.command ?? "")
                  .then(() => setCopied(true));
              }}
            >
              {copied ? "✓ copiado" : "copiar"}
            </button>
          </div>
        </div>
      )}

      <ReceiptPanel detail={detail} />
    </div>
  );
}

export function MissionConsole() {
  const [listing, setListing] = useState<MissionsResponse | null>(null);
  const [radar, setRadar] = useState<RadarResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [radarError, setRadarError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<MissionDetailResponse | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        setListing(await api.missions(80));
      } catch (err) {
        setError(String(err));
      }
    })();
    void (async () => {
      try {
        setRadar(await api.missionsRadar());
      } catch (err) {
        setRadarError(String(err));
      }
    })();
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setDetail(null);
    setDetailError(null);
    void (async () => {
      try {
        setDetail(await api.missionDetail(selectedId));
      } catch (err) {
        setDetailError(String(err));
      }
    })();
  }, [selectedId]);

  const { active, history } = useMemo(() => {
    const all = listing?.missions ?? [];
    return {
      active: all.filter((m) => m.human_action_required),
      history: all.filter((m) => !m.human_action_required),
    };
  }, [listing]);

  const row = (m: Mission, i: number) => (
    <li
      key={m.mission_id}
      className={`mc-row ${selectedId === m.mission_id ? "mc-row-active" : ""}`}
      style={{ animationDelay: `${Math.min(i, 12) * 40}ms` }}
      onClick={() => setSelectedId(m.mission_id)}
    >
      <StateChip state={m.state} />
      <span className="mc-row-intent">{m.intent}</span>
      <span className="mc-row-meta">
        <span style={{ color: RISK_COLOR[m.risk] ?? "var(--text-dim)" }}>
          ▲ {m.risk}
        </span>
        {" · "}
        {relTime(m.updated_at)}
      </span>
    </li>
  );

  return (
    <div className="body mc-body">
      {error && (
        <div className="caps" style={{ color: "var(--warn)" }}>
          ⚠ error cargando misiones: {error}
        </div>
      )}
      {!listing && !error && <div className="caps">cargando misiones…</div>}
      {listing && !listing.real && (
        <div className="caps" style={{ color: "var(--warn)" }}>
          ⚠ {listing.status}: {listing.detail}
        </div>
      )}

      {listing && listing.real && (
        <>
          <RadarStrip radar={radar} error={radarError} onFocus={setSelectedId} />

          <div className="mc-columns">
            <div className="mc-list">
              <h3 className="mc-section">
                ESPERAN DECISIÓN HUMANA
                <span className="mc-count" style={{ color: "var(--ember)" }}>
                  {active.length}
                </span>
              </h3>
              {active.length === 0 && (
                <div className="caps">ninguna — el lazo no espera nada de ti</div>
              )}
              <ul className="mc-rows">{active.map(row)}</ul>

              <h3 className="mc-section" style={{ marginTop: 14 }}>
                <button
                  className="mc-toggle"
                  onClick={() => setShowHistory((v) => !v)}
                >
                  {showHistory ? "▾" : "▸"} HISTORIAL
                </button>
                <span className="mc-count">{history.length}</span>
              </h3>
              {showHistory && <ul className="mc-rows">{history.map(row)}</ul>}
            </div>

            <div className="mc-detail">
              <Inspector
                missionId={selectedId}
                detail={detail}
                error={detailError}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
