// lib/api.ts — OpsGuard FastAPI client

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const MERCHANT_ID =
  process.env.NEXT_PUBLIC_MERCHANT_ID || "merchant_demo";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface SummaryData {
  open_disputes: number;
  total_disputed_inr: number;
  low_stock_skus: number;
  last_agent_run: string | null; // ISO timestamp
}

export interface SyncJob {
  id: string;
  merchant_id: string;
  connector: "shopify" | "gsheets" | "shiprocket";
  status: "pending" | "running" | "done" | "failed";
  last_synced_at: string | null;
  completed_at: string | null;
  error: string | null;
  row_count?: number;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatResponse {
  response: string;
  citations: Citation[];
}

export interface Citation {
  row_id: string;
  source: string;
  source_record_id: string;
  ingested_at: string;
}

export interface AgentRun {
  id: string;
  merchant_id: string;
  run_at: string;
  trigger: "daily_cron" | "manual" | "webhook";
  data_window_days: number;
  shipments_scanned: number;
  findings: Finding[];
  proposals: Proposal[];
  reasoning: string;
  status: "running" | "completed" | "failed";
  error: string | null;
}

export interface Finding {
  shipment_id: string;
  courier_name: string;
  weight_declared_kg: number;
  weight_charged_kg: number;
  overcharge_inr: number;
  evidence_row_id: string;
}

export interface Proposal {
  courier: string;
  shipment_count: number;
  total_disputed_inr: number;
  shipment_ids: string[];
  action: string;
}

export interface ReconciliationResult {
  id: string;
  shipment_id: string;
  discrepancy_type: string;
  declared_value: number;
  charged_value: number;
  amount_disputed_inr: number;
  status: "open" | "actioned" | "dismissed";
  created_at: string;
  actioned_at: string | null;
  action_note: string | null;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ─── Endpoints ────────────────────────────────────────────────────────────────

export const api = {
  // Dashboard summary
  getSummary: (merchantId = MERCHANT_ID) =>
    apiFetch<SummaryData>(`/api/summary?merchant_id=${merchantId}`),

  // Sync
  getSyncStatus: (merchantId = MERCHANT_ID) =>
    apiFetch<SyncJob[]>(`/api/sync/status?merchant_id=${merchantId}`),

  triggerSync: (merchantId = MERCHANT_ID) =>
    apiFetch<{ job_id: string; status: string }>(
      `/api/sync?merchant_id=${merchantId}`,
      { method: "POST" }
    ),

  // Chat
  sendMessage: (
    message: string,
    history: ChatMessage[],
    merchantId = MERCHANT_ID
  ) =>
    apiFetch<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ merchant_id: merchantId, message, history }),
    }),

  // Agent
  getAgentRuns: (merchantId = MERCHANT_ID) =>
    apiFetch<AgentRun[]>(`/api/agent/runs?merchant_id=${merchantId}`),

  triggerAgent: (merchantId = MERCHANT_ID) =>
    apiFetch<{ run_id: string; status: string }>(
      `/api/agent/run?merchant_id=${merchantId}`,
      { method: "POST" }
    ),

  // Reconciliation / disputes
  getDisputes: (merchantId = MERCHANT_ID) =>
    apiFetch<ReconciliationResult[]>(
      `/api/disputes?merchant_id=${merchantId}`
    ),

  markActioned: (reconciliationId: string, note: string) =>
    apiFetch<{ success: boolean }>("/api/disputes/action", {
      method: "POST",
      body: JSON.stringify({ reconciliation_id: reconciliationId, note }),
    }),
};
