"use client";

import useSWR from "swr";
import { api, ReconciliationResult } from "@/lib/api";
import { Badge } from "@/components/Badge";
import { formatINR, formatDate } from "@/lib/utils";
import { AlertTriangle, CheckCheck, X } from "lucide-react";
import { useState } from "react";

function statusVariant(status: ReconciliationResult["status"]) {
  if (status === "open") return "open";
  if (status === "actioned") return "actioned";
  return "dismissed";
}

function DisputeRow({
  item,
  onAction,
}: {
  item: ReconciliationResult;
  onAction: (id: string, status: "actioned" | "dismissed") => void;
}) {
  return (
    <div className="flex items-center gap-4 px-5 py-3.5 border-b border-border last:border-0 hover:bg-surface-3 transition-colors group">
      <Badge variant={statusVariant(item.status)}>{item.status}</Badge>
      <div className="flex-1 min-w-0">
        <p className="text-[13px] font-medium text-ink truncate font-mono">
          {item.shipment_id.slice(0, 12)}…
        </p>
        <p className="text-[11px] text-ink-muted mt-0.5">{item.discrepancy_type.replace("_", " ")}</p>
      </div>
      <div className="text-right shrink-0">
        <p className="text-[13px] font-mono text-ink-muted">
          {item.declared_value}kg → {item.charged_value}kg
        </p>
      </div>
      <p className="text-[14px] font-display font-700 text-warn w-28 text-right shrink-0">
        {formatINR(item.amount_disputed_inr)}
      </p>
      <p className="text-[11px] text-ink-muted w-28 text-right font-mono shrink-0">
        {formatDate(item.created_at)}
      </p>
      {item.status === "open" && (
        <div className="flex gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
          <button
            onClick={() => onAction(item.id, "actioned")}
            title="Mark actioned"
            className="w-7 h-7 rounded-lg bg-success-dim text-success flex items-center justify-center hover:bg-success/20 transition-colors"
          >
            <CheckCheck className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => onAction(item.id, "dismissed")}
            title="Dismiss"
            className="w-7 h-7 rounded-lg bg-surface-4 text-ink-muted flex items-center justify-center hover:bg-surface-4/80 transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
    </div>
  );
}

export default function DisputesPage() {
  const { data, isLoading, mutate } = useSWR(
    "disputes",
    () => api.getDisputes(),
    { refreshInterval: 30000 }
  );

  const [filter, setFilter] = useState<"all" | "open" | "actioned" | "dismissed">("all");

  const filtered = (data || []).filter(
    (d) => filter === "all" || d.status === filter
  );

  const totalOpen = (data || []).filter((d) => d.status === "open").reduce(
    (sum, d) => sum + d.amount_disputed_inr,
    0
  );

  const handleAction = async (id: string, status: "actioned" | "dismissed") => {
    await api.markActioned(id, status === "actioned" ? "Marked via dashboard" : "Dismissed via dashboard");
    mutate();
  };

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto space-y-6">
      <div className="flex items-start justify-between opacity-0 animate-fade-up" style={{ animationFillMode: "forwards" }}>
        <div>
          <h1 className="font-display text-2xl font-700 text-ink tracking-tight">
            Disputes
          </h1>
          <p className="text-[13px] text-ink-muted mt-1">
            Weight overcharges flagged by the autonomous agent.
          </p>
        </div>
        {totalOpen > 0 && (
          <div className="text-right">
            <p className="text-[11px] uppercase tracking-widest text-ink-muted font-medium">Recoverable</p>
            <p className="text-2xl font-display font-700 text-warn mt-0.5">
              {formatINR(totalOpen)}
            </p>
          </div>
        )}
      </div>

      {/* Filter tabs */}
      <div
        className="flex gap-1 p-1 bg-surface-2 border border-border rounded-xl w-fit opacity-0 animate-fade-up"
        style={{ animationDelay: "60ms", animationFillMode: "forwards" }}
      >
        {(["all", "open", "actioned", "dismissed"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-lg text-[12px] font-medium transition-all ${
              filter === f
                ? "bg-surface-4 text-ink"
                : "text-ink-muted hover:text-ink"
            }`}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      {/* Table */}
      <div
        className="rounded-xl bg-surface-2 border border-border shadow-card overflow-hidden opacity-0 animate-fade-up"
        style={{ animationDelay: "120ms", animationFillMode: "forwards" }}
      >
        {/* Table header */}
        <div className="flex items-center gap-4 px-5 py-3 border-b border-border bg-surface-1">
          <span className="text-[11px] uppercase tracking-widest text-ink-muted font-medium w-20">Status</span>
          <span className="text-[11px] uppercase tracking-widest text-ink-muted font-medium flex-1">Shipment</span>
          <span className="text-[11px] uppercase tracking-widest text-ink-muted font-medium">Weight</span>
          <span className="text-[11px] uppercase tracking-widest text-ink-muted font-medium w-28 text-right">Disputed</span>
          <span className="text-[11px] uppercase tracking-widest text-ink-muted font-medium w-28 text-right">Flagged</span>
          <span className="w-20" />
        </div>

        <div>
          {isLoading
            ? [1, 2, 3, 4, 5].map((n) => (
                <div key={n} className="flex items-center gap-4 px-5 py-4 border-b border-border">
                  <div className="skeleton h-5 w-16 rounded" />
                  <div className="skeleton h-3 w-32 rounded flex-1" />
                  <div className="skeleton h-3 w-20 rounded" />
                  <div className="skeleton h-5 w-20 rounded" />
                </div>
              ))
            : filtered.map((item) => (
                <DisputeRow key={item.id} item={item} onAction={handleAction} />
              ))}
          {!isLoading && filtered.length === 0 && (
            <div className="px-5 py-10 text-center">
              <AlertTriangle className="w-8 h-8 text-ink-faint mx-auto mb-3" />
              <p className="text-[13px] text-ink-muted">
                {filter === "all"
                  ? "No disputes found. Run the agent to scan for weight overcharges."
                  : `No ${filter} disputes.`}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
