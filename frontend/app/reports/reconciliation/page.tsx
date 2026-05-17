"use client";

import useSWR from "swr";
import { api, ReconciliationReport } from "@/lib/api";
import { formatINR } from "@/lib/utils";
import { Download, FileText } from "lucide-react";
import { useMemo, useState } from "react";

function csvEscape(s: string | number | undefined | null): string {
  const v = s == null ? "" : String(s);
  if (/[",\n]/.test(v)) return `"${v.replace(/"/g, '""')}"`;
  return v;
}

function reportToCsv(data: ReconciliationReport): string {
  const headers = [
    "reconciliation_id",
    "shipment_id",
    "shipment_ref",
    "courier_name",
    "status",
    "amount_disputed_inr",
    "declared_kg",
    "charged_kg",
    "destination_pincode",
    "created_at",
  ];
  const lines = [headers.join(",")];
  for (const row of data.lines) {
    lines.push(
      [
        csvEscape(row.reconciliation_id),
        csvEscape(row.shipment_id),
        csvEscape(row.shipment_ref),
        csvEscape(row.courier_name),
        csvEscape(row.status),
        csvEscape(row.amount_disputed_inr),
        csvEscape(row.declared_value),
        csvEscape(row.charged_value),
        csvEscape(row.destination_pincode),
        csvEscape(row.created_at),
      ].join(",")
    );
  }
  return lines.join("\n");
}

export default function ReconciliationReportPage() {
  const [days, setDays] = useState(90);
  const { data, isLoading, error } = useSWR(
    ["reconciliation-report", days],
    () => api.getReconciliationReport(days),
    { revalidateOnFocus: false }
  );

  const maxCourier = useMemo(() => {
    if (!data?.by_courier?.length) return 1;
    return Math.max(...data.by_courier.map((c) => c.amount_inr), 1);
  }, [data]);

  const downloadCsv = () => {
    if (!data) return;
    const blob = new Blob([reportToCsv(data)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `opsguard-reconciliation-${data.merchant_id}-${days}d.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto space-y-8 print:px-4">
      <div className="flex flex-wrap items-start justify-between gap-4 opacity-0 animate-fade-up" style={{ animationFillMode: "forwards" }}>
        <div>
          <div className="flex items-center gap-2 text-ink-muted mb-1">
            <FileText className="w-4 h-4" />
            <span className="text-[11px] uppercase tracking-widest font-medium">Report</span>
          </div>
          <h1 className="font-display text-2xl font-700 text-ink tracking-tight">
            Reconciliation summary
          </h1>
          <p className="text-[13px] text-ink-muted mt-1">
            Weight and dispute lines from reconciliation_results, grouped by courier. Export includes row IDs for audit.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="text-[13px] bg-surface-2 border border-border rounded-lg px-3 py-2 text-ink"
          >
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={180}>Last 180 days</option>
          </select>
          <button
            type="button"
            onClick={downloadCsv}
            disabled={!data?.lines?.length}
            className="inline-flex items-center gap-2 text-[13px] font-medium px-4 py-2 rounded-lg bg-accent text-surface hover:opacity-95 disabled:opacity-40 transition-opacity"
          >
            <Download className="w-4 h-4" />
            Export CSV
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-24 rounded-xl bg-surface-2 border border-border animate-pulse" />
          ))}
        </div>
      )}

      {error && (
        <p className="text-[13px] text-danger">Failed to load report. Is the API running?</p>
      )}

      {data && !isLoading && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 opacity-0 animate-fade-up" style={{ animationFillMode: "forwards", animationDelay: "60ms" }}>
            <div className="p-5 rounded-xl bg-surface-2 border border-border">
              <p className="text-[11px] uppercase tracking-widest text-ink-muted font-medium">Lines</p>
              <p className="text-2xl font-display font-700 text-ink mt-1">{data.totals.lines}</p>
            </div>
            <div className="p-5 rounded-xl bg-surface-2 border border-border">
              <p className="text-[11px] uppercase tracking-widest text-ink-muted font-medium">Total disputed</p>
              <p className="text-2xl font-display font-700 text-warn mt-1">{formatINR(data.totals.amount_inr)}</p>
            </div>
            <div className="p-5 rounded-xl bg-surface-2 border border-border">
              <p className="text-[11px] uppercase tracking-widest text-ink-muted font-medium">Open recoverable</p>
              <p className="text-2xl font-display font-700 text-accent mt-1">{formatINR(data.totals.open_amount_inr)}</p>
            </div>
            <div className="p-5 rounded-xl bg-surface-2 border border-border">
              <p className="text-[11px] uppercase tracking-widest text-ink-muted font-medium">Statuses</p>
              <p className="text-[13px] text-ink mt-2 font-mono">
                {Object.entries(data.totals.by_status)
                  .map(([k, v]) => `${k}: ${v}`)
                  .join(" · ")}
              </p>
            </div>
          </div>

          <div className="rounded-xl border border-border bg-surface-2 overflow-hidden opacity-0 animate-fade-up" style={{ animationFillMode: "forwards", animationDelay: "120ms" }}>
            <div className="px-5 py-4 border-b border-border">
              <h2 className="text-[14px] font-700 text-ink">By courier</h2>
              <p className="text-[12px] text-ink-muted mt-0.5">Share of disputed INR in the selected window</p>
            </div>
            <div className="p-5 space-y-4">
              {data.by_courier.length === 0 ? (
                <p className="text-[13px] text-ink-muted">No reconciliation rows in this period.</p>
              ) : (
                data.by_courier.map((c) => (
                  <div key={c.courier}>
                    <div className="flex justify-between text-[13px] mb-1.5">
                      <span className="font-medium text-ink">{c.courier}</span>
                      <span className="font-mono text-ink-muted">
                        {formatINR(c.amount_inr)} · {c.line_count} lines · open {formatINR(c.open_amount_inr)}
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-surface-4 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-accent transition-all"
                        style={{ width: `${Math.min(100, (c.amount_inr / maxCourier) * 100)}%` }}
                      />
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="rounded-xl border border-border bg-surface-2 overflow-hidden opacity-0 animate-fade-up" style={{ animationFillMode: "forwards", animationDelay: "180ms" }}>
            <div className="px-5 py-4 border-b border-border flex justify-between items-center">
              <div>
                <h2 className="text-[14px] font-700 text-ink">Line items</h2>
                <p className="text-[12px] text-ink-muted mt-0.5">
                  {data.lines_truncated ? "Showing first 200 rows — CSV has the same cap from API." : "Up to 200 rows"}
                </p>
              </div>
            </div>
            <div className="divide-y divide-border max-h-[480px] overflow-y-auto">
              {data.lines.map((row) => (
                <div key={row.reconciliation_id} className="px-5 py-3 grid grid-cols-12 gap-2 text-[12px] items-center hover:bg-surface-3">
                  <span className="col-span-3 font-mono text-ink-muted truncate" title={row.reconciliation_id}>
                    {row.reconciliation_id.slice(0, 8)}…
                  </span>
                  <span className="col-span-2 text-ink truncate">{row.courier_name}</span>
                  <span className="col-span-2 text-ink-muted truncate">{row.shipment_ref || "—"}</span>
                  <span className="col-span-1 text-ink-muted">{row.status}</span>
                  <span className="col-span-2 text-right font-display font-700 text-warn">{formatINR(row.amount_disputed_inr)}</span>
                  <span className="col-span-2 text-right text-ink-muted font-mono">
                    {row.declared_value}→{row.charged_value} kg
                  </span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
