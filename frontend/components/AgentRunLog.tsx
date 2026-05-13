"use client";

import useSWR from "swr";
import { api, AgentRun } from "@/lib/api";
import { Badge } from "@/components/Badge";
import { formatINR, formatDate } from "@/lib/utils";
import { ChevronDown, ChevronRight, Bot } from "lucide-react";
import { useState } from "react";

function RunRow({ run }: { run: AgentRun }) {
  const [open, setOpen] = useState(false);
  const totalDisputed = run.proposals.reduce(
    (sum, p) => sum + p.total_disputed_inr,
    0
  );

  return (
    <div className="border-b border-border last:border-0">
      {/* Row header */}
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-5 py-3.5 hover:bg-surface-3 transition-colors text-left"
      >
        <span className="text-ink-muted">
          {open ? (
            <ChevronDown className="w-3.5 h-3.5" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5" />
          )}
        </span>
        <Badge variant={run.status === "completed" ? "done" : run.status === "running" ? "running" : "failed"}>
          {run.status}
        </Badge>
        <span className="text-[13px] text-ink flex-1 font-mono">
          {formatDate(run.run_at)}
        </span>
        <Badge variant={run.trigger === "manual" ? "manual" : "cron"}>
          {run.trigger.replace("_", " ")}
        </Badge>
        <span className="text-[12px] text-ink-muted w-24 text-right font-mono">
          {run.shipments_scanned} ships
        </span>
        {totalDisputed > 0 && (
          <span className="text-[12px] text-warn font-medium w-28 text-right font-mono">
            {formatINR(totalDisputed)}
          </span>
        )}
      </button>

      {/* Expanded detail */}
      {open && (
        <div className="px-5 pb-5 pt-1 space-y-4 bg-surface-1">
          {/* Reasoning */}
          {run.reasoning && (
            <div>
              <p className="text-[11px] uppercase tracking-widest text-ink-muted font-medium mb-2">
                Reasoning
              </p>
              <p className="text-[13px] text-ink-muted leading-relaxed bg-surface-2 rounded-lg px-4 py-3 border border-border font-mono text-[12px]">
                {run.reasoning}
              </p>
            </div>
          )}

          {/* Proposals */}
          {run.proposals.length > 0 && (
            <div>
              <p className="text-[11px] uppercase tracking-widest text-ink-muted font-medium mb-2">
                Dispute Proposals
              </p>
              <div className="space-y-2">
                {run.proposals.map((p, i) => (
                  <div
                    key={i}
                    className="bg-surface-2 border border-warn/20 rounded-lg px-4 py-3 flex items-start gap-4"
                  >
                    <div className="flex-1">
                      <p className="text-[13px] font-medium text-ink">
                        {p.courier}
                      </p>
                      <p className="text-[12px] text-ink-muted mt-0.5">
                        {p.shipment_count} shipments · {p.action}
                      </p>
                    </div>
                    <p className="text-[14px] font-display font-700 text-warn shrink-0">
                      {formatINR(p.total_disputed_inr)}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {run.error && (
            <div className="bg-danger-dim border border-danger/20 rounded-lg px-4 py-3 text-[12px] text-danger font-mono">
              {run.error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface AgentRunLogProps {
  merchantId?: string;
}

export function AgentRunLog({ merchantId }: AgentRunLogProps) {
  const { data, isLoading, mutate } = useSWR(
    ["agent-runs", merchantId],
    () => api.getAgentRuns(merchantId),
    { refreshInterval: 15000 }
  );

  const [triggering, setTriggering] = useState(false);

  const handleTrigger = async () => {
    setTriggering(true);
    try {
      await api.triggerAgent(merchantId);
      mutate();
    } finally {
      setTimeout(() => setTriggering(false), 2000);
    }
  };

  return (
    <div className="rounded-xl bg-surface-2 border border-border shadow-card overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-border">
        <div className="flex items-center gap-2.5">
          <Bot className="w-4 h-4 text-accent" />
          <div>
            <h3 className="text-[13px] font-display font-600 text-ink">
              Agent Runs
            </h3>
            <p className="text-[11px] text-ink-muted mt-0.5">
              Weight dispute scanner
            </p>
          </div>
        </div>
        <button
          onClick={handleTrigger}
          disabled={triggering}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-3 text-ink text-[12px] font-medium border border-border hover:bg-surface-4 transition-colors disabled:opacity-50"
        >
          <Bot className={`w-3.5 h-3.5 ${triggering ? "animate-pulse" : ""}`} />
          {triggering ? "Running..." : "Run Now"}
        </button>
      </div>

      <div className="divide-y divide-border">
        {isLoading
          ? [1, 2, 3].map((n) => (
              <div key={n} className="flex items-center gap-3 px-5 py-4">
                <div className="skeleton h-5 w-16 rounded" />
                <div className="skeleton h-3 w-32 rounded" />
                <div className="ml-auto skeleton h-3 w-20 rounded" />
              </div>
            ))
          : (data || []).map((run) => <RunRow key={run.id} run={run} />)}
        {!isLoading && (!data || data.length === 0) && (
          <div className="px-5 py-8 text-center text-[13px] text-ink-muted">
            No agent runs yet. Click &quot;Run Now&quot; to start.
          </div>
        )}
      </div>
    </div>
  );
}
