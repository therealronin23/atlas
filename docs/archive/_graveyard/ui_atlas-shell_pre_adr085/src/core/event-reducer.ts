// Visual State Machine: eventos → estado derivado. Sin React aquí (ADR-059):
// este módulo es el dominio; los componentes solo renderizan lo que sale.

import type { GraphData, OsEvent } from "./types";

export interface PipelineStep {
  eventId: string;
  type: string;
  status: string;
  summary: string;
  timestamp: string;
}

export interface PipelineView {
  intentId: string;
  text: string;
  steps: PipelineStep[];
  simulated: boolean;
}

export interface AppState {
  events: OsEvent[];
  pipelines: PipelineView[];
  graph: GraphData | null;
  memoryUpdates: number;
  pendingApprovals: OsEvent[];
}

export const MAX_EVENTS = 500;
const MAX_PIPELINES = 10;

export const initialState: AppState = {
  events: [],
  pipelines: [],
  graph: null,
  memoryUpdates: 0,
  pendingApprovals: [],
};

// Mapa actor → nodo del grafo fixture: los eventos ILUMINAN el grafo.
const ACTOR_TO_NODE: Record<string, string> = {
  memory: "node_memory",
  user: "node_user",
  kernel: "node_runtime",
  governance: "node_runtime",
  connector: "node_tools",
};

function bumpGraph(graph: GraphData | null, event: OsEvent): GraphData | null {
  if (!graph || !event.actor) return graph;
  const nodeId = ACTOR_TO_NODE[event.actor];
  if (!nodeId) return graph;
  return {
    ...graph,
    nodes: graph.nodes.map((n) =>
      n.id === nodeId
        ? {
            ...n,
            activity: Math.min(1, n.activity + 0.15),
            state: event.status === "running" ? "running" : n.state,
          }
        : n,
    ),
  };
}

export function decayActivity(graph: GraphData | null): GraphData | null {
  if (!graph) return graph;
  return {
    ...graph,
    nodes: graph.nodes.map((n) => ({
      ...n,
      activity: Math.max(0.05, n.activity * 0.92),
      state: n.state === "running" ? "idle" : n.state,
    })),
  };
}

function updatePipelines(pipelines: PipelineView[], event: OsEvent): PipelineView[] {
  if (!event.intent_id) return pipelines;
  const step: PipelineStep = {
    eventId: event.id,
    type: event.type,
    status: event.status,
    summary: event.summary,
    timestamp: event.timestamp,
  };
  const idx = pipelines.findIndex((p) => p.intentId === event.intent_id);
  if (idx === -1) {
    const text =
      event.type === "intent.created" && typeof event.payload.text === "string"
        ? event.payload.text
        : event.summary;
    return [
      { intentId: event.intent_id, text, steps: [step], simulated: event.simulated === true },
      ...pipelines,
    ].slice(0, MAX_PIPELINES);
  }
  const next = [...pipelines];
  next[idx] = { ...next[idx], steps: [...next[idx].steps, step] };
  return next;
}

export type Action =
  | { kind: "event"; event: OsEvent }
  | { kind: "events"; events: OsEvent[] }
  | { kind: "graph"; graph: GraphData }
  | { kind: "decay" };

export function reduce(state: AppState, action: Action): AppState {
  switch (action.kind) {
    case "graph":
      return { ...state, graph: action.graph };
    case "decay":
      return { ...state, graph: decayActivity(state.graph) };
    case "events":
      return action.events.reduce((s, e) => reduce(s, { kind: "event", event: e }), state);
    case "event": {
      const event = action.event;
      if (state.events.some((e) => e.id === event.id)) return state;
      const events = [...state.events, event].slice(-MAX_EVENTS);
      let pendingApprovals = state.pendingApprovals;
      if (event.type === "approval.required") {
        pendingApprovals = [...pendingApprovals, event];
      } else if (
        (event.type === "approval.granted" || event.type === "approval.denied") &&
        event.process_id
      ) {
        pendingApprovals = pendingApprovals.filter(
          (p) => p.process_id !== event.process_id,
        );
      }
      return {
        events,
        pipelines: updatePipelines(state.pipelines, event),
        graph: bumpGraph(state.graph, event),
        memoryUpdates:
          state.memoryUpdates + (event.type === "memory.updated" ? 1 : 0),
        pendingApprovals,
      };
    }
  }
}
