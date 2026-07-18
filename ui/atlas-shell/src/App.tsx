import { useEffect, useReducer, useRef, useState } from "react";
import { api, connectEventsWs } from "./core/api";
import { initialState, reduce } from "./core/event-reducer";
import type {
  ConnectorSpec,
  GateSpec,
  HealthInfo,
  MemorySummary,
  OsEvent,
  Preferences,
  RealityReport,
} from "./core/types";
import { DEFAULT_PREFERENCES } from "./core/types";
import { AutobuildLedger } from "./components/AutobuildLedger";
import { MissionConsole } from "./components/MissionConsole";
import { EventInspector } from "./components/EventInspector";
import { HarnessPanel } from "./components/HarnessPanel";
import { ExecutionPipeline } from "./components/ExecutionPipeline";
import { NebulaGraph, type GraphHealth, type NebulaHandle, type NodePick } from "./components/NebulaGraph";
import { MemoryVault } from "./components/MemoryVault";
import { RealityPanel } from "./components/RealityPanel";
import { Timeline } from "./components/Timeline";
import { UniversalBar } from "./components/UniversalBar";
import { IntegrationFabric } from "./components/control/IntegrationFabric";
import { PermissionsMatrix } from "./components/control/PermissionsMatrix";
import { Personalization } from "./components/control/Personalization";
import { SecurityCenter } from "./components/control/SecurityCenter";

type View =
  | "missions"
  | "command"
  | "timeline"
  | "memory"
  | "fabric"
  | "permissions"
  | "security"
  | "personalization"
  | "harness"
  | "autobuild";

const PREFS_KEY = "atlas-os-preferences";

const VIEWS = [
  "missions", "command", "timeline", "memory", "fabric",
  "permissions", "security", "personalization", "harness", "autobuild",
] as const;

function initialView(): View {
  const q = new URLSearchParams(location.search).get("view");
  return (VIEWS as readonly string[]).includes(q ?? "") ? (q as View) : "missions";
}

function loadPrefs(): Preferences {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    return raw ? { ...DEFAULT_PREFERENCES, ...JSON.parse(raw) } : DEFAULT_PREFERENCES;
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

export default function App() {
  const [state, dispatch] = useReducer(reduce, initialState);
  // Mission Console es el centro mental del shell (Foundry v0, ADR-069):
  // se abre en la superficie de decisión, no en el dashboard.
  const [view, setView] = useState<View>(initialView);
  const [connected, setConnected] = useState(false);
  const [prefs, setPrefs] = useState<Preferences>(loadPrefs);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [reality, setReality] = useState<RealityReport | null>(null);
  const [memory, setMemory] = useState<MemorySummary | null>(null);
  const [connectors, setConnectors] = useState<ConnectorSpec[]>([]);
  const [gates, setGates] = useState<GateSpec[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<OsEvent | null>(null);
  const [nebulaMode, setNebulaMode] = useState<"command" | "exec" | "memory">("command");
  const [pickedHub, setPickedHub] = useState<NodePick | null>(null);
  const [graphHealth, setGraphHealth] = useState<GraphHealth | null>(null);
  const [lastActivity, setLastActivity] = useState<OsEvent | null>(null);
  const [showHealth, setShowHealth] = useState(false);
  const nebulaRef = useRef<NebulaHandle | null>(null);
  const loadedRef = useRef(false);

  // Preferencias → efecto real inmediato en el documento + persistencia.
  useEffect(() => {
    const el = document.documentElement;
    el.dataset.theme = prefs.theme;
    el.dataset.density = prefs.density;
    el.dataset.animations = prefs.animations ? "on" : "off";
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  }, [prefs]);

  // Carga inicial (una sola vez, guard contra StrictMode).
  useEffect(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;
    void (async () => {
      try {
        setHealth(await api.health());
        dispatch({ kind: "graph", graph: await api.graph() });
        const backlog = await api.events(200);
        dispatch({ kind: "events", events: backlog.events });
        setMemory(await api.memorySummary());
        setConnectors((await api.connectors()).connectors);
        setGates((await api.permissions()).gates);
        const r = await api.reality();
        setReality(r.report);
      } catch {
        // sin bridge: el banner ya lo dice; no se inventa nada
      }
    })();
  }, []);

  // WS en vivo: efecto SIN guard — el cleanup de StrictMode cierra la primera
  // conexión y este setup debe poder abrir la segunda (bug real cazado en el
  // smoke con preview: el guard dejaba la app permanentemente "sin bridge").
  useEffect(
    () =>
      connectEventsWs((event) => {
        dispatch({ kind: "event", event });
        // Cada evento REAL del bridge dispara una reacción viva en la nebulosa:
        // enciende el hub del módulo, lanza tokens por dependencias reales,
        // pulsa el reactor y suena (synapse/success/error/surface).
        if (event.visible !== false) nebulaRef.current?.react(event);
      }, setConnected),
    [],
  );

  // Decaimiento de actividad del grafo (solo si hay animaciones).
  useEffect(() => {
    if (!prefs.animations) return;
    const t = setInterval(() => dispatch({ kind: "decay" }), 1500);
    return () => clearInterval(t);
  }, [prefs.animations]);

  // El modo de la nebulosa (Command/Execution/Memory) morfea el organismo 3D.
  useEffect(() => {
    nebulaRef.current?.setMode(nebulaMode);
  }, [nebulaMode]);

  // Refresco perezoso de memoria cuando llegan memory.updated.
  useEffect(() => {
    if (state.memoryUpdates > 0) {
      void api.memorySummary().then(setMemory).catch(() => undefined);
    }
  }, [state.memoryUpdates]);

  const nav = (v: View, label: string) => (
    <button
      key={v}
      className={`navitem ${view === v ? "active" : ""}`}
      onClick={() => setView(v)}
    >
      {label}
    </button>
  );

  return (
    <>
      <div className="topbar">
        <span className="brand">
          ATLAS OS<small>shell v0.1</small>
        </span>
        <UniversalBar prefs={prefs} connected={connected} />
        <span className="conn-status">
          <span className={`dot ${connected ? "up" : ""}`} />
          {connected ? "bridge 7341" : "sin bridge"}
        </span>
      </div>
      {!connected && (
        <div className="banner">
          Bridge no conectado — arranca <code>atlas os-bridge</code>. Esta UI no
          inventa datos: sin bridge solo verás esta advertencia.
        </div>
      )}
      <div className="layout">
        <nav className="sidebar">
          <h4>Cognitive Surface</h4>
          {nav("missions", "⟁ Mission Console")}
          {nav("command", "◈ Command Center")}
          {nav("timeline", "≡ Timeline")}
          {nav("memory", "◇ Memory Vault")}
          <h4>Control Plane</h4>
          {nav("fabric", "⚡ Integration Fabric")}
          {nav("permissions", "▣ Permissions")}
          {nav("security", "⛨ Security Center")}
          {nav("personalization", "✦ Personalización")}
          {nav("harness", "⚑ Harness")}
          {nav("autobuild", "◎ Autobuild Ledger")}
        </nav>
        <main className="main">
          {view === "missions" && (
            <div className="panel" style={{ flex: 1 }}>
              <header>
                Mission Console · Atlas construyendo Atlas
                <span className="badge real">REAL — ColdUpdate ledger</span>
              </header>
              <MissionConsole />
            </div>
          )}
          {view === "command" && (
            <div className="cc-stage">
              {/* La nebulosa 3D real: 4206 ficheros reales del grafo de
                  dependencias, orbitable y con zoom. Solo se anima cuando
                  llega un evento REAL del bridge — en reposo no simula
                  actividad que no existe. */}
              <NebulaGraph
                ref={nebulaRef}
                onPick={setPickedHub}
                onHealth={setGraphHealth}
                onActivity={setLastActivity}
              />

              {/* Estado real explícito: reposo vs última actividad real —
                  arregla la confusión "veo luces pero Atlas está apagado". */}
              <div className={`cc-activity ${lastActivity ? "live" : "idle"}`}>
                <span className="dot" />
                {lastActivity
                  ? `actividad real · ${lastActivity.type} · ${lastActivity.summary}`
                  : "sin actividad real — Atlas en reposo"}
              </div>

              {/* Conmutador de modos — morfea el organismo (superficie efímera). */}
              <div className="cc-modes">
                {(
                  [
                    ["command", "◈ Command"],
                    ["exec", "⧗ Execution"],
                    ["memory", "◇ Memory"],
                  ] as const
                ).map(([m, label]) => (
                  <button
                    key={m}
                    className={`cc-mode ${nebulaMode === m ? "on" : ""}`}
                    onClick={() => setNebulaMode(m)}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {/* Botón de salud del grafo — su función PRINCIPAL: verificar
                  qué está bien conectado y qué no, con datos reales. */}
              {graphHealth && (
                <button className="cc-health-btn" onClick={() => setShowHealth((v) => !v)}>
                  ⬡ {graphHealth.total - graphHealth.orphanCount}/{graphHealth.total} conectados
                  {graphHealth.orphanCount > 0 && (
                    <span className="cc-health-warn">{graphHealth.orphanCount} huérfanos</span>
                  )}
                </button>
              )}
              {showHealth && graphHealth && (
                <div className="cc-health-panel">
                  <button className="ci-close" onClick={() => setShowHealth(false)}>
                    ✕
                  </button>
                  <h5>Salud del grafo de dependencias</h5>
                  <p className="cc-health-stat">
                    <b>{graphHealth.total}</b> ficheros reales · <b>{graphHealth.edgeCount}</b> dependencias reales
                  </p>
                  <p className="cc-health-stat">
                    <b style={{ color: graphHealth.orphanCount ? "var(--danger)" : "var(--ok)" }}>
                      {graphHealth.orphanCount}
                    </b>{" "}
                    ficheros con 0 conexiones detectadas
                  </p>
                  {graphHealth.orphanCount > 0 && (
                    <ul className="cc-orphan-list">
                      {graphHealth.orphanFiles.map((o) => (
                        <li key={o.file}>
                          <b>{o.label}</b>
                          <span>{o.file}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  <h5>Tipos de relación reales</h5>
                  <div className="cc-rel-types">
                    {Object.entries(graphHealth.relTypes).map(([rel, n]) => (
                      <span key={rel}>
                        {rel} <b>{n}</b>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Telemetría flotante en cristal — no tapa el organismo. */}
              <aside className="cc-telemetry">
                <div className="glass-card">
                  <h5>Reality · System</h5>
                  <RealityPanel
                    health={health}
                    reality={reality}
                    memory={memory}
                    memoryUpdates={state.memoryUpdates}
                  />
                </div>
                <div className="glass-card">
                  <h5>Execution Pipeline</h5>
                  <ExecutionPipeline pipelines={state.pipelines} />
                </div>
              </aside>

              {/* Inspector del nodo — superficie CONTEXTUAL: aparece al pinchar
                  un fichero real, con sus conexiones reales (relación real:
                  uses/calls/imports/inherits...). Sin datos inventados. */}
              {pickedHub && (
                <div className="cc-inspector" key={pickedHub.label + pickedHub.file}>
                  <button className="ci-close" onClick={() => setPickedHub(null)}>
                    ✕
                  </button>
                  <span className="ci-mod" style={{ color: pickedHub.color }}>
                    {pickedHub.mod.toUpperCase()}
                  </span>
                  <h4>{pickedHub.label}</h4>
                  <p className="ci-file">{pickedHub.file}</p>
                  {pickedHub.orphan ? (
                    <p className="ci-orphan">⚠ 0 conexiones reales — nodo huérfano en el grafo</p>
                  ) : (
                    <>
                      <p className="ci-deps">
                        <b>{pickedHub.deg}</b> conexiones reales
                      </p>
                      {pickedHub.connections.length > 0 && (
                        <ul className="ci-conn-list">
                          {pickedHub.connections.map((c, i) => (
                            <li key={i}>
                              <span className="ci-rel">{c.relation}</span> {c.label}
                            </li>
                          ))}
                        </ul>
                      )}
                    </>
                  )}
                </div>
              )}

              <div className="cc-hint">
                arrastra para orbitar · rueda para acercarte · pincha cualquier nodo
              </div>
            </div>
          )}
          {view === "timeline" && (
            <div className="content">
              <div className="panel" style={{ flex: 2 }}>
                <header>
                  Timeline · riesgo ≥ {prefs.minRiskShown}
                  {prefs.showSimulated ? "" : " · solo REAL"}
                </header>
                <Timeline
                  events={state.events}
                  prefs={prefs}
                  onSelect={setSelectedEvent}
                />
              </div>
              <div className="panel" style={{ flex: 1 }}>
                <header>Event Inspector</header>
                <EventInspector event={selectedEvent} node={null} />
              </div>
            </div>
          )}
          {view === "memory" && (
            <div className="panel" style={{ flex: 1 }}>
              <header>Memory Vault</header>
              <MemoryVault memory={memory} events={state.events} />
            </div>
          )}
          {view === "fabric" && (
            <div className="panel" style={{ flex: 1 }}>
              <header>
                Integration Fabric · {connectors.length} conectores
                <span className="badge sim">MOCK-FIRST</span>
              </header>
              <IntegrationFabric connectors={connectors} />
            </div>
          )}
          {view === "permissions" && (
            <div className="panel" style={{ flex: 1 }}>
              <header>Permissions Matrix · {gates.length} gates</header>
              <PermissionsMatrix gates={gates} />
            </div>
          )}
          {view === "security" && (
            <div className="panel" style={{ flex: 1 }}>
              <header>Security Center</header>
              <SecurityCenter
                pendingApprovals={state.pendingApprovals}
                events={state.events}
              />
            </div>
          )}
          {view === "personalization" && (
            <div className="panel" style={{ flex: 1 }}>
              <header>Personalización · efectos reales, no decorativos</header>
              <Personalization prefs={prefs} onChange={setPrefs} />
            </div>
          )}
          {view === "harness" && (
            <div className="panel" style={{ flex: 1 }}>
              <header>Harness · conexiones + gates</header>
              <HarnessPanel />
            </div>
          )}
          {view === "autobuild" && (
            <div className="panel" style={{ flex: 1 }}>
              <header>
                Autobuild Ledger
                <span className="badge real">REAL — ColdUpdateManager</span>
              </header>
              <AutobuildLedger />
            </div>
          )}
        </main>
      </div>
    </>
  );
}
