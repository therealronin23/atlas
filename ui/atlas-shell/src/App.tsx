import { useEffect, useReducer, useRef, useState } from "react";
import { api, connectEventsWs } from "./core/api";
import { initialState, reduce } from "./core/event-reducer";
import type {
  ConnectorSpec,
  GateSpec,
  GraphNode,
  HealthInfo,
  MemorySummary,
  OsEvent,
  Preferences,
  RealityReport,
} from "./core/types";
import { DEFAULT_PREFERENCES } from "./core/types";
import { AutobuildLedger } from "./components/AutobuildLedger";
import { EventInspector } from "./components/EventInspector";
import { HarnessPanel } from "./components/HarnessPanel";
import { ExecutionPipeline } from "./components/ExecutionPipeline";
import { GraphLegend, LivingGraph } from "./components/LivingGraph";
import { MemoryVault } from "./components/MemoryVault";
import { RealityPanel } from "./components/RealityPanel";
import { Timeline } from "./components/Timeline";
import { UniversalBar } from "./components/UniversalBar";
import { IntegrationFabric } from "./components/control/IntegrationFabric";
import { PermissionsMatrix } from "./components/control/PermissionsMatrix";
import { Personalization } from "./components/control/Personalization";
import { SecurityCenter } from "./components/control/SecurityCenter";

type View =
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
  const [view, setView] = useState<View>("command");
  const [connected, setConnected] = useState(false);
  const [prefs, setPrefs] = useState<Preferences>(loadPrefs);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [reality, setReality] = useState<RealityReport | null>(null);
  const [memory, setMemory] = useState<MemorySummary | null>(null);
  const [connectors, setConnectors] = useState<ConnectorSpec[]>([]);
  const [gates, setGates] = useState<GateSpec[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<OsEvent | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
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
      connectEventsWs((event) => dispatch({ kind: "event", event }), setConnected),
    [],
  );

  // Decaimiento de actividad del grafo (solo si hay animaciones).
  useEffect(() => {
    if (!prefs.animations) return;
    const t = setInterval(() => dispatch({ kind: "decay" }), 1500);
    return () => clearInterval(t);
  }, [prefs.animations]);

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
          {view === "command" && (
            <div className="content">
              <div className="panel" style={{ flex: 2.2, display: "flex" }}>
                <header>
                  Living Knowledge Graph
                  <span className="badge sim">FIXTURE</span>
                </header>
                <LivingGraph
                  graph={state.graph}
                  onSelect={(n) => {
                    setSelectedNode(n);
                    setSelectedEvent(null);
                  }}
                />
                <div style={{ padding: "6px 14px" }}>
                  <GraphLegend />
                </div>
              </div>
              <div style={{ flex: 1.3, display: "flex", flexDirection: "column", minWidth: 300 }}>
                <div className="panel" style={{ flex: 1 }}>
                  <header>Reality / System</header>
                  <RealityPanel
                    health={health}
                    reality={reality}
                    memory={memory}
                    memoryUpdates={state.memoryUpdates}
                  />
                </div>
                <div className="panel" style={{ flex: 1 }}>
                  <header>Execution Pipeline</header>
                  <ExecutionPipeline pipelines={state.pipelines} />
                </div>
                <div className="panel" style={{ flex: 1.2 }}>
                  <header>Event / Node Inspector</header>
                  <EventInspector event={selectedEvent} node={selectedNode} />
                </div>
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
                  onSelect={(e) => {
                    setSelectedEvent(e);
                    setSelectedNode(null);
                  }}
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
