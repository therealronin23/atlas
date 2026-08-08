// Espejo TS del canon (schemas/*.schema.json). Si esto diverge del JSON
// Schema, el bug es aquí: la autoridad son los schemas del repo.

export type Risk = "none" | "low" | "medium" | "high" | "critical";

export type EventStatus =
  | "idle"
  | "queued"
  | "running"
  | "waiting_user"
  | "blocked"
  | "completed"
  | "failed"
  | "cancelled";

export interface OsEvent {
  id: string;
  type: string;
  timestamp: string;
  schema_version: string;
  source: string;
  workspace_id?: string | null;
  intent_id?: string | null;
  process_id?: string | null;
  actor?: string | null;
  summary: string;
  status: EventStatus;
  risk: Risk;
  confidence?: number | null;
  visible: boolean;
  simulated?: boolean | null;
  payload: Record<string, unknown>;
  causality?: { parent_event_id?: string | null; trace_id?: string | null } | null;
  audit?: {
    merkle_hash?: string | null;
    previous_hash?: string | null;
    reversible?: boolean | null;
  } | null;
  ui?: {
    priority?: number | null;
    surface?: string[] | null;
    motion?: string | null;
  } | null;
}

export interface GraphNode {
  id: string;
  type: string;
  label: string;
  state: string;
  confidence: number;
  activity: number;
  risk: Risk;
  source: string;
  metadata: Record<string, unknown>;
  actions: string[];
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  relation: string;
  weight: number;
  confidence: number;
  evidence: string[];
}

export interface GraphData {
  simulated?: boolean;
  source?: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface ConnectorSpec {
  connector_id: string;
  display_name: string;
  provider: string;
  auth_mode: string;
  credential_reference: string | null;
  read_capabilities: string[];
  write_capabilities: string[];
  risk_level: Risk;
  permission_scope: string[];
  sync_status: string;
  health: string;
  memory_policy: string;
  automation_policy: string;
  audit_policy: string;
  mode: "real" | "mock" | "sandbox";
  legal_notes?: string | null;
}

export interface GateSpec {
  gate_id: string;
  display_name: string;
  applies_to: string[];
  risk_threshold: Risk;
  approval_mode: string;
  default_decision: string;
  enabled: boolean;
  notes?: string | null;
}

export interface PermissionEvaluation {
  action: string;
  resource: string;
  actor?: string | null;
  decision: "allow" | "deny" | "require_approval";
  risk: Risk;
  reason: string;
  gate_id?: string | null;
  evaluated_at: string;
}

export interface HealthInfo {
  status: string;
  real: boolean;
  service: string;
  os_events: number;
  connectors: number;
  gates: number;
}

export interface MemorySummary {
  real: boolean;
  records?: number;
  db?: string;
  status?: string;
  detail?: string;
}

export interface RealityRepo {
  root: string;
  version: string;
  branch: string;
  commit: string;
  dirty: boolean;
  dirty_count: number;
}

export interface RealityReport {
  generated_at: string;
  repo: RealityRepo;
  workspace: {
    path: string;
    exists: boolean;
    merkle: { status: string; record_count: number; reason: string };
  };
  status?: string;
}

// Preferencias del Control Plane. TODAS tienen efecto real en la UI:
// nada de settings decorativos (regla del master prompt §10).
export interface Preferences {
  theme: "dark" | "light";
  density: "comfortable" | "compact";
  animations: boolean;
  confirmBeforeIntent: boolean;
  minRiskShown: Risk;
  showSimulated: boolean;
}

export const DEFAULT_PREFERENCES: Preferences = {
  theme: "dark",
  density: "comfortable",
  animations: true,
  confirmBeforeIntent: true,
  minRiskShown: "none",
  showSimulated: true,
};

export const RISK_ORDER: Risk[] = ["none", "low", "medium", "high", "critical"];
