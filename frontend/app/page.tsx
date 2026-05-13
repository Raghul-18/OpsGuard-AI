"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import { StatCard, StatCardSkeleton } from "@/components/StatCard";
import { SyncStatus } from "@/components/SyncStatus";
import { AgentRunLog } from "@/components/AgentRunLog";
import { formatINR, formatRelativeTime } from "@/lib/utils";
import {
  AlertTriangle,
  IndianRupee,
  PackageOpen,
  Bot,
} from "lucide-react";
import { useState } from "react";

export default function DashboardPage() {
  const { data, isLoading } = useSWR("summary", () => api.getSummary(), {
    refreshInterval: 60000,
  });
  const [syncing, setSyncing] = useState(false);

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto space-y-8">
      {/* Page header */}
      <div className="opacity-0 animate-fade-up" style={{ animationFillMode: "forwards" }}>
        <h1 className="font-display text-2xl font-700 text-ink tracking-tight">
          Overview
        </h1>
        <p className="text-[13px] text-ink-muted mt-1">
          Your ops command centre — disputes, inventory, and agent activity at a glance.
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {isLoading ? (
          [1, 2, 3, 4].map((n) => <StatCardSkeleton key={n} />)
        ) : (
          <>
            <StatCard
              label="Open Disputes"
              value={data?.open_disputes ?? 0}
              sub="Weight overcharges flagged"
              icon={AlertTriangle}
              variant={data && data.open_disputes > 0 ? "warn" : "default"}
              delay={0}
            />
            <StatCard
              label="Total Disputed"
              value={data ? formatINR(data.total_disputed_inr) : "₹0"}
              sub="Recoverable amount"
              icon={IndianRupee}
              variant={data && data.total_disputed_inr > 0 ? "danger" : "default"}
              delay={60}
            />
            <StatCard
              label="Low Stock SKUs"
              value={data?.low_stock_skus ?? 0}
              sub="Below reorder level"
              icon={PackageOpen}
              variant={data && data.low_stock_skus > 0 ? "warn" : "success"}
              delay={120}
            />
            <StatCard
              label="Last Agent Run"
              value={
                data?.last_agent_run
                  ? formatRelativeTime(data.last_agent_run)
                  : "Never"
              }
              sub="Weight dispute scanner"
              icon={Bot}
              delay={180}
            />
          </>
        )}
      </div>

      {/* Sync + Agent */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <SyncStatus
          onTriggerSync={() => setSyncing(true)}
          isSyncing={syncing}
        />
        <AgentRunLog />
      </div>
    </div>
  );
}
