"use client";

import { useState } from "react";
import { SyncStatus } from "@/components/SyncStatus";
import { RefreshCw } from "lucide-react";

export default function SyncPage() {
  const [syncing, setSyncing] = useState(false);

  return (
    <div className="px-8 py-8 max-w-3xl mx-auto space-y-6">
      <div className="opacity-0 animate-fade-up" style={{ animationFillMode: "forwards" }}>
        <h1 className="font-display text-2xl font-700 text-ink tracking-tight">
          Sync Status
        </h1>
        <p className="text-[13px] text-ink-muted mt-1">
          Live connector health — Shopify, Google Sheets, and Shiprocket.
        </p>
      </div>

      <div
        className="opacity-0 animate-fade-up"
        style={{ animationDelay: "80ms", animationFillMode: "forwards" }}
      >
        <SyncStatus
          onTriggerSync={() => {
            setSyncing(true);
            setTimeout(() => setSyncing(false), 3000);
          }}
          isSyncing={syncing}
        />
      </div>

      {/* Info callout */}
      <div
        className="rounded-xl bg-surface-2 border border-border px-5 py-4 text-[12px] text-ink-muted space-y-1.5 opacity-0 animate-fade-up"
        style={{ animationDelay: "160ms", animationFillMode: "forwards" }}
      >
        <p className="flex items-center gap-2 text-ink font-medium text-[13px]">
          <RefreshCw className="w-3.5 h-3.5 text-accent" />
          How syncing works
        </p>
        <p>
          Syncs are triggered manually or via the daily cron (06:00 IST). Each connector
          fetches incrementally from its last high-watermark, upserts to Supabase, and
          updates this table.
        </p>
        <p>
          If a connector shows <span className="text-danger font-mono">failed</span>, check
          that your credentials in <code className="bg-surface-3 px-1 rounded font-mono">.env</code> are valid and the source system is reachable.
        </p>
      </div>
    </div>
  );
}
