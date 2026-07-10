// Execution Pipeline: etapas del último intent, estado por evento.

import type { PipelineView } from "../core/event-reducer";

export function ExecutionPipeline({ pipelines }: { pipelines: PipelineView[] }) {
  const current = pipelines[0];
  return (
    <div className="body">
      {!current && (
        <div style={{ color: "var(--text-dim)" }}>
          Sin ejecuciones. Escribe una intención en la Universal Bar.
        </div>
      )}
      {current && (
        <>
          <div style={{ marginBottom: 8 }}>
            <strong>»&nbsp;{current.text}</strong>{" "}
            <span className={`badge ${current.simulated ? "sim" : "real"}`}>
              {current.simulated ? "SIM" : "REAL"}
            </span>
          </div>
          {current.steps.map((s) => (
            <div key={s.eventId} className="pipeline-step">
              <span className={`step-dot ${s.status}`} />
              <span className="type" style={{ fontFamily: "monospace", fontSize: 11 }}>
                {s.type}
              </span>
              <span style={{ color: "var(--text-dim)", fontSize: 11 }}>{s.status}</span>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
