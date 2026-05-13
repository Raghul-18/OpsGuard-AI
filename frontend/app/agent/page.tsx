"use client";

import { AgentRunLog } from "@/components/AgentRunLog";
import { Bot } from "lucide-react";

export default function AgentPage() {
  return (
    <div className="px-8 py-8 max-w-4xl mx-auto space-y-6">
      <div className="opacity-0 animate-fade-up" style={{ animationFillMode: "forwards" }}>
        <h1 className="font-display text-2xl font-700 text-ink tracking-tight">
          Agent Runs
        </h1>
        <p className="text-[13px] text-ink-muted mt-1">
          Autonomous weight dispute scanner — trigger, data, decision, action.
        </p>
      </div>

      <div
        className="opacity-0 animate-fade-up"
        style={{ animationDelay: "80ms", animationFillMode: "forwards" }}
      >
        <AgentRunLog />
      </div>

      {/* How it works */}
      <div
        className="rounded-xl bg-surface-2 border border-border px-5 py-4 text-[12px] text-ink-muted space-y-1.5 opacity-0 animate-fade-up"
        style={{ animationDelay: "160ms", animationFillMode: "forwards" }}
      >
        <p className="flex items-center gap-2 text-ink font-medium text-[13px]">
          <Bot className="w-3.5 h-3.5 text-accent" />
          How the agent works
        </p>
        <p>
          The agent scans the last 30 days of shipments and flags any where{" "}
          <code className="bg-surface-3 px-1 rounded font-mono">weight_charged_kg &gt; weight_declared_kg × 1.1</code>.
        </p>
        <p>
          For each flagged shipment it calculates the overcharge, groups by courier,
          and proposes a dispute via the Shiprocket dashboard. All runs are logged
          with full reasoning to <code className="bg-surface-3 px-1 rounded font-mono">agent_runs</code> in Supabase.
        </p>
        <p>
          Runs automatically every day at 06:00 IST via APScheduler, or trigger
          manually here.
        </p>
      </div>
    </div>
  );
}
