// HarnessPanel: arnés de validación para /connections, /business y /gates.
// No es UX final de Atlas (D11) — solo conduce los endpoints de producto reales.

import { useEffect, useState } from "react";
import { api } from "../core/api";
import type {
  ConnectionCatalog,
  ConnectionPlan,
  GatesOpen,
  QuestionPacksResponse,
  SectorsResponse,
} from "../core/api";

export function HarnessPanel() {
  const [catalog, setCatalog] = useState<ConnectionCatalog | null>(null);
  const [sectors, setSectors] = useState<SectorsResponse | null>(null);
  const [packs, setPacks] = useState<QuestionPacksResponse | null>(null);
  const [gates, setGates] = useState<GatesOpen | null>(null);
  const [plan, setPlan] = useState<ConnectionPlan | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        setCatalog(await api.connectionsCatalog());
        setSectors(await api.sectors());
        setPacks(await api.questionPacks());
        setGates(await api.gatesOpen());
      } catch (err) {
        setLoadError(String(err));
      }
    })();
  }, []);

  const selectConnector = async (connectorId: string) => {
    setBusyId(connectorId);
    setPlanError(null);
    try {
      setPlan(await api.connectionPlan(connectorId));
    } catch (err) {
      setPlan(null);
      setPlanError(String(err));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="body">
      <div className="harness-banner">
        HARNESS — superficie de validación, no UX final de Atlas (D11)
      </div>

      {loadError && (
        <div className="caps" style={{ color: "var(--warn)" }}>
          ⚠ error cargando arnés: {loadError}
        </div>
      )}

      <h3>Catálogo de conexiones</h3>
      {!catalog && !loadError && <div className="caps">cargando…</div>}
      {catalog &&
        Object.entries(catalog.categories).map(([category, entries]) => (
          <div key={category} className="harness-section">
            <h4>{category}</h4>
            <ul className="harness-list">
              {entries.map((c) => (
                <li key={c.connector_id}>
                  <button
                    className="small"
                    disabled={busyId === c.connector_id}
                    onClick={() => void selectConnector(c.connector_id)}
                  >
                    {c.human_name}
                  </button>
                  <span className="caps">
                    {" "}
                    dificultad: {c.difficulty} · ruta: {c.recommended_route} · modo:{" "}
                    {c.default_mode}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}

      {planError && (
        <div className="caps" style={{ color: "var(--warn)" }}>
          ⚠ error de plan: {planError}
        </div>
      )}

      {plan && (
        <div className="harness-section">
          <h4>Plan: {plan.human_name}</h4>
          <div className="caps">
            categoría: {plan.category} · dificultad: {plan.difficulty} · modo:{" "}
            {plan.default_mode}
          </div>
          <div className="caps">
            ruta recomendada: {plan.route.recommended} · peldaño:{" "}
            {plan.route.ladder_rung} · riesgo de ruta: {plan.route.route_risk}
          </div>
          {plan.route.fallbacks.length > 0 && (
            <div className="caps">fallbacks: {plan.route.fallbacks.join(", ")}</div>
          )}

          <h4>Atlas hará</h4>
          <ul className="harness-list">
            {plan.will.length === 0 && <li className="caps">—</li>}
            {plan.will.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>

          <h4>Atlas NO hará</h4>
          <ul className="harness-list">
            {plan.will_not.length === 0 && <li className="caps">—</li>}
            {plan.will_not.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>

          <h4>Concedido al conectar</h4>
          <ul className="harness-list">
            {plan.granted_now.length === 0 && <li className="caps">—</li>}
            {plan.granted_now.map((g, i) => (
              <li key={i}>{g}</li>
            ))}
          </ul>

          <h4>Requiere gate</h4>
          <ul className="harness-list">
            {plan.requires_gate.length === 0 && <li className="caps">—</li>}
            {plan.requires_gate.map((g, i) => (
              <li key={i}>
                {g.capability} → <code>{g.gate_id}</code> (riesgo: {g.risk}) —{" "}
                {g.description}
              </li>
            ))}
          </ul>

          <h4>Imposible</h4>
          <ul className="harness-list">
            {plan.impossible.length === 0 && <li className="caps">—</li>}
            {plan.impossible.map((im, i) => (
              <li key={i}>
                {im.capability}: {im.reason}
              </li>
            ))}
          </ul>

          {plan.platform_terms !== null && (
            <div className="caps" style={{ color: "var(--warn)" }}>
              ⚠ términos de plataforma: {plan.platform_terms}
            </div>
          )}
        </div>
      )}

      <h3>Cola de gates</h3>
      {gates && gates.tickets.length === 0 && (
        <div className="caps">sin gates abiertos</div>
      )}
      {gates && gates.tickets.length > 0 && (
        <ul className="harness-list">
          {gates.tickets.map((t) => (
            <li key={t.gate_ticket_id}>
              <code>{t.gate_id}</code> · acción: {t.action} · sujeto:{" "}
              {t.subject_ref} · riesgo: {t.risk} · estado: {t.status}
            </li>
          ))}
        </ul>
      )}

      <h3>Sectores</h3>
      <ul className="harness-list">
        {sectors?.sectors.map((s) => (
          <li key={s.sector_id}>{s.display_name}</li>
        ))}
      </ul>

      <h3>Question packs</h3>
      <ul className="harness-list">
        {packs?.packs.map((p) => (
          <li key={p.pack_id}>
            {p.display_name} ({p.questions.length} preguntas)
          </li>
        ))}
      </ul>
    </div>
  );
}
