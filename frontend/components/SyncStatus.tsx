"use client";

import useSWR from "swr";
import { api, SyncJob } from "@/lib/api";
import { Badge } from "@/components/Badge";
import { formatRelativeTime } from "@/lib/utils";
import { RefreshCw, ShoppingBag, FileSpreadsheet, Truck } from "lucide-react";

const CONNECTOR_META: Record<string, { label: string; icon: React.ReactNode }> = {
  shopify: {
    label: "Shopify",
    icon: <ShoppingBag className="w-4 h-4 text-[#96bf48]" />,
  },
  gsheets: {
    label: "Google Sheets",
    icon: <FileSpreadsheet className="w-4 h-4 text-[#0f9d58]" />,
  },
  shiprocket: {
    label: "Shiprocket",
    icon: <Truck className="w-4 h-4 text-[#e8692c]" />,
  },
};

function statusVariant(status: SyncJob["status"]) {
  if (status === "done") return "done";
  if (status === "running") return "running";
  if (status === "failed") return "failed";
  return "pending";
}

interface SyncStatusProps {
  merchantId?: string;
  onTriggerSync?: () => void;
  isSyncing?: boolean;
}

export function SyncStatus({ merchantId, onTriggerSync, isSyncing }: SyncStatusProps) {
  const { data, isLoading, mutate } = useSWR(
    ["sync-status", merchantId],
    () => api.getSyncStatus(merchantId),
    { refreshInterval: 30000 }
  );

  return (
    <div className="rounded-xl bg-surface-2 border border-border shadow-card overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-border">
        <div>
          <h3 className="text-[13px] font-display font-600 text-ink">Connector Sync</h3>
          <p className="text-[11px] text-ink-muted mt-0.5">Auto-refreshes every 30s</p>
        </div>
        <button
          onClick={async () => {
            onTriggerSync?.();
            await api.triggerSync(merchantId);
            mutate();
          }}
          disabled={isSyncing}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-accent-dim text-accent text-[12px] font-medium border border-accent/20 hover:bg-accent/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? "animate-spin" : ""}`} />
          Sync Now
        </button>
      </div>

      {/* Table */}
      <div className="divide-y divide-border">
        {isLoading
          ? [1, 2, 3].map((n) => (
              <div key={n} className="flex items-center gap-4 px-5 py-4">
                <div className="skeleton w-4 h-4 rounded" />
                <div className="skeleton h-3 w-24 rounded" />
                <div className="ml-auto skeleton h-5 w-16 rounded" />
                <div className="skeleton h-3 w-20 rounded" />
              </div>
            ))
          : (data || []).map((job) => {
              const meta = CONNECTOR_META[job.connector] ?? {
                label: job.connector,
                icon: null,
              };
              return (
                <div
                  key={job.id}
                  className="flex items-center gap-3 px-5 py-3.5 hover:bg-surface-3 transition-colors"
                >
                  <span className="shrink-0">{meta.icon}</span>
                  <span className="text-[13px] font-medium text-ink flex-1">
                    {meta.label}
                  </span>
                  <Badge variant={statusVariant(job.status)}>{job.status}</Badge>
                  <span className="text-[12px] text-ink-muted w-28 text-right font-mono">
                    {job.last_synced_at
                      ? formatRelativeTime(job.last_synced_at)
                      : "—"}
                  </span>
                  {job.row_count != null && (
                    <span className="text-[12px] text-ink-muted w-20 text-right font-mono">
                      {job.row_count.toLocaleString()} rows
                    </span>
                  )}
                </div>
              );
            })}
        {!isLoading && (!data || data.length === 0) && (
          <div className="px-5 py-8 text-center text-[13px] text-ink-muted">
            No sync jobs found. Trigger a sync to get started.
          </div>
        )}
      </div>
    </div>
  );
}
