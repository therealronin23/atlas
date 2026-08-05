// Timeline persistente con filtros REALES (riesgo mínimo + simulado on/off).

import type { OsEvent, Preferences } from "../core/types";
import { RISK_ORDER } from "../core/types";

interface Props {
  events: OsEvent[];
  prefs: Preferences;
  onSelect: (e: OsEvent) => void;
}

export function Timeline({ events, prefs, onSelect }: Props) {
  const minIdx = RISK_ORDER.indexOf(prefs.minRiskShown);
  const filtered = events
    .filter((e) => e.visible)
    .filter((e) => RISK_ORDER.indexOf(e.risk) >= minIdx)
    .filter((e) => prefs.showSimulated || e.simulated !== true)
    .slice(-120)
    .reverse();

  return (
    <div className="body">
      {filtered.length === 0 && (
        <div style={{ color: "var(--text-dim)" }}>
          Sin eventos aún. Lanza una intención o reproduce un fixture.
        </div>
      )}
      {filtered.map((e) => (
        <div key={e.id} className="timeline-row" onClick={() => onSelect(e)}>
          <span className="time">{e.timestamp.slice(11, 19)}</span>
          <span className="type">{e.type}</span>
          <span className="summary">{e.summary}</span>
          <span className={`badge risk-${e.risk}`}>{e.risk}</span>
          <span className={`badge ${e.simulated ? "sim" : "real"}`}>
            {e.simulated ? "SIM" : "REAL"}
          </span>
        </div>
      ))}
    </div>
  );
}
