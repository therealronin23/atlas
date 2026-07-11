// Cliente del Atlas OS Bridge (127.0.0.1:7341 vía proxy /api de vite).
// La UI nunca esconde el estado de conexión: sin bridge => banner, no fakes.

import type {
  ConnectorSpec,
  GateSpec,
  GraphData,
  HealthInfo,
  MemorySummary,
  OsEvent,
  PermissionEvaluation,
  RealityReport,
} from "./types";

const BASE = "/api";

// --- Tipos mínimos del arnés harness (endpoints de producto /connections, /business, /gates, /sectors) ---

export interface ConnectionCatalogEntry {
  connector_id: string;
  human_name: string;
  difficulty: string;
  recommended_route: string;
  default_mode: string;
}

export interface ConnectionCatalog {
  categories: Record<string, ConnectionCatalogEntry[]>;
  rejected: Record<string, unknown>;
}

export interface ConnectionPlanGate {
  capability: string;
  gate_id: string;
  risk: string;
  description: string;
}

export interface ConnectionPlanImpossible {
  capability: string;
  reason: string;
}

export interface ConnectionPlan {
  connector_id: string;
  human_name: string;
  category: string;
  route: {
    recommended: string;
    ladder_rung: string;
    route_risk: string;
    fallbacks: string[];
  };
  difficulty: string;
  default_mode: string;
  setup_steps: string[];
  granted_now: string[];
  requires_gate: ConnectionPlanGate[];
  impossible: ConnectionPlanImpossible[];
  will: string[];
  will_not: string[];
  platform_terms: string | null;
}

export interface GateTicket {
  gate_ticket_id: string;
  gate_id: string;
  action: string;
  subject_ref: string;
  risk: string;
  status: string;
}

export interface GatesOpen {
  count: number;
  tickets: GateTicket[];
}

export interface SectorInfo {
  sector_id: string;
  display_name: string;
  [key: string]: unknown;
}

export interface SectorsResponse {
  count: number;
  sectors: SectorInfo[];
  rejected: Record<string, unknown>;
}

export interface QuestionPack {
  pack_id: string;
  sector_id: string;
  display_name: string;
  questions: string[];
}

export interface QuestionPacksResponse {
  count: number;
  packs: QuestionPack[];
}

export interface SelfBuildProposal {
  id: string;
  intent: string;
  status: string;
  origin: string;
  risk: string;
  created_at: string;
  updated_at: string;
}

export interface SelfBuildSummary {
  real: boolean;
  status?: string;
  detail?: string;
  total?: number;
  by_status?: Record<string, number>;
  by_origin?: Record<string, number>;
  by_risk?: Record<string, number>;
  recent?: SelfBuildProposal[];
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return (await res.json()) as T;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return (await res.json()) as T;
}

export const api = {
  health: () => get<HealthInfo>("/health"),
  reality: () => get<{ real: boolean; report: RealityReport }>("/reality"),
  graph: () => get<GraphData>("/graph"),
  events: (limit = 200) =>
    get<{ count: number; events: OsEvent[] }>(`/events?limit=${limit}`),
  memorySummary: () => get<MemorySummary>("/memory/summary"),
  connectors: () =>
    get<{ count: number; connectors: ConnectorSpec[] }>("/connectors"),
  permissions: () => get<{ count: number; gates: GateSpec[] }>("/permissions"),
  intent: (text: string) =>
    post<{ intent_id: string; simulated: boolean; events: OsEvent[] }>("/intent", {
      text,
    }),
  simulate: (fixture: string) =>
    post<{ status: string; event_count: number }>("/simulate", { fixture }),
  testConnector: (id: string) =>
    post<{ ok: boolean; mode: string; simulated: boolean }>(
      `/connectors/${id}/test`,
    ),
  syncConnector: (id: string) =>
    post<{ ok: boolean; simulated: boolean }>(`/connectors/${id}/sync`),
  evaluate: (action: string, resource: string) =>
    post<{ simulated: boolean; evaluation: PermissionEvaluation }>(
      "/permissions/evaluate",
      { action, resource },
    ),
  connectionsCatalog: () => get<ConnectionCatalog>("/connections/catalog"),
  connectionPlan: (connectorId: string) =>
    post<ConnectionPlan>("/connections/plan", { connector_id: connectorId }),
  gatesOpen: () => get<GatesOpen>("/gates/open"),
  sectors: () => get<SectorsResponse>("/sectors"),
  questionPacks: () => get<QuestionPacksResponse>("/business/question-packs"),
  selfBuildSummary: (limit = 50) =>
    get<SelfBuildSummary>(`/self-build/summary?limit=${limit}`),
};

export function connectEventsWs(onEvent: (e: OsEvent) => void, onState: (up: boolean) => void): () => void {
  let ws: WebSocket | null = null;
  let closed = false;
  let retry = 0;

  const open = () => {
    if (closed) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/api-ws/events`);
    ws.onopen = () => {
      retry = 0;
      onState(true);
    };
    ws.onmessage = (msg) => {
      try {
        onEvent(JSON.parse(msg.data as string) as OsEvent);
      } catch {
        // línea corrupta: se ignora, el store JSONL es la verdad
      }
    };
    ws.onclose = () => {
      onState(false);
      if (!closed) {
        retry += 1;
        setTimeout(open, Math.min(1000 * 2 ** retry, 15000));
      }
    };
    ws.onerror = () => ws?.close();
  };
  open();
  return () => {
    closed = true;
    ws?.close();
  };
}
