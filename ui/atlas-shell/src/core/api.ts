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
