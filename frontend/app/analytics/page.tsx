"use client";

import useSWR from "swr";
import { api, AnalyticsOrdersResponse } from "@/lib/api";
import { formatINR } from "@/lib/utils";
import { BarChart3 } from "lucide-react";
import { useMemo, useState } from "react";

export default function AnalyticsPage() {
  const [days, setDays] = useState(30);
  const { data, isLoading, error } = useSWR(
    ["analytics-orders", days],
    () => api.getAnalyticsOrders(days),
    { revalidateOnFocus: false }
  );

  const maxDayRev = useMemo(() => {
    if (!data?.revenue_by_day?.length) return 1;
    return Math.max(...data.revenue_by_day.map((d) => d.revenue_inr), 1);
  }, [data]);

  const codPct = useMemo(() => {
    if (!data?.summary) return 0;
    const t = data.summary.cod_lines + data.summary.prepaid_lines;
    if (!t) return 0;
    return Math.round((data.summary.cod_lines / t) * 100);
  }, [data]);

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4 opacity-0 animate-fade-up" style={{ animationFillMode: "forwards" }}>
        <div>
          <div className="flex items-center gap-2 text-ink-muted mb-1">
            <BarChart3 className="w-4 h-4" />
            <span className="text-[11px] uppercase tracking-widest font-medium">Shopify orders</span>
          </div>
          <h1 className="font-display text-2xl font-700 text-ink tracking-tight">
            Order analytics
          </h1>
          <p className="text-[13px] text-ink-muted mt-1">
            Revenue by day, COD mix, and top pincodes / SKUs from synced orders and SKU master (Sheets) costs.
          </p>
        </div>
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="text-[13px] bg-surface-2 border border-border rounded-lg px-3 py-2 text-ink"
        >
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
      </div>

      {isLoading && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-28 rounded-xl bg-surface-2 border border-border animate-pulse" />
          ))}
        </div>
      )}

      {error && (
        <p className="text-[13px] text-danger">Failed to load analytics. Sync Shopify orders first.</p>
      )}

      {data && !isLoading && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 opacity-0 animate-fade-up" style={{ animationFillMode: "forwards", animationDelay: "60ms" }}>
            <div className="p-5 rounded-xl bg-surface-2 border border-border">
              <p className="text-[11px] uppercase tracking-widest text-ink-muted font-medium">Order lines</p>
              <p className="text-2xl font-display font-700 text-ink mt-1">{data.summary.order_lines}</p>
            </div>
            <div className="p-5 rounded-xl bg-surface-2 border border-border">
              <p className="text-[11px] uppercase tracking-widest text-ink-muted font-medium">Revenue</p>
              <p className="text-2xl font-display font-700 text-accent mt-1">{formatINR(data.summary.revenue_inr)}</p>
            </div>
            <div className="p-5 rounded-xl bg-surface-2 border border-border">
              <p className="text-[11px] uppercase tracking-widest text-ink-muted font-medium">COD lines</p>
              <p className="text-2xl font-display font-700 text-warn mt-1">{data.summary.cod_lines}</p>
              <p className="text-[11px] text-ink-muted mt-1">{codPct}% of lines</p>
            </div>
            <div className="p-5 rounded-xl bg-surface-2 border border-border">
              <p className="text-[11px] uppercase tracking-widest text-ink-muted font-medium">Prepaid lines</p>
              <p className="text-2xl font-display font-700 text-ink mt-1">{data.summary.prepaid_lines}</p>
            </div>
          </div>

          <div className="rounded-xl border border-border bg-surface-2 p-5 opacity-0 animate-fade-up" style={{ animationFillMode: "forwards", animationDelay: "120ms" }}>
            <h2 className="text-[14px] font-700 text-ink mb-4">Revenue by day</h2>
            {data.revenue_by_day.length === 0 ? (
              <p className="text-[13px] text-ink-muted">No orders in this window.</p>
            ) : (
              <div className="flex items-end gap-1 h-44 px-1">
                {data.revenue_by_day.map((d) => {
                  const hPx = Math.max(6, Math.round((d.revenue_inr / maxDayRev) * 140));
                  return (
                  <div key={d.date} className="flex-1 min-w-0 flex flex-col items-center justify-end gap-1 group">
                    <div
                      className="w-full max-w-[28px] mx-auto rounded-t-md bg-accent/80 group-hover:bg-accent transition-colors"
                      style={{ height: `${hPx}px` }}
                      title={`${d.date}: ${formatINR(d.revenue_inr)}`}
                    />
                    <span className="text-[9px] text-ink-muted font-mono truncate w-full text-center">
                      {d.date.slice(5)}
                    </span>
                  </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="grid lg:grid-cols-2 gap-6 opacity-0 animate-fade-up" style={{ animationFillMode: "forwards", animationDelay: "180ms" }}>
            <div className="rounded-xl border border-border bg-surface-2 overflow-hidden">
              <div className="px-5 py-4 border-b border-border">
                <h2 className="text-[14px] font-700 text-ink">Top pincodes</h2>
                <p className="text-[12px] text-ink-muted mt-0.5">By revenue</p>
              </div>
              <div className="divide-y divide-border">
                {data.top_pincodes.map((p) => (
                  <div key={p.pincode} className="px-5 py-3 flex justify-between text-[13px]">
                    <span className="font-mono text-ink">{p.pincode}</span>
                    <span className="text-ink-muted">
                      {formatINR(p.revenue_inr)} <span className="text-ink-faint">({p.order_lines})</span>
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-xl border border-border bg-surface-2 overflow-hidden">
              <div className="px-5 py-4 border-b border-border">
                <h2 className="text-[14px] font-700 text-ink">Top SKUs</h2>
                <p className="text-[12px] text-ink-muted mt-0.5">Revenue, COGS from Sheets, margin</p>
              </div>
              <div className="max-h-80 overflow-y-auto divide-y divide-border">
                {data.top_skus.map((s) => (
                  <div key={s.sku_id} className="px-5 py-3">
                    <p className="text-[12px] font-mono text-ink truncate">{s.sku_id}</p>
                    <div className="flex justify-between mt-1 text-[12px] text-ink-muted">
                      <span>Rev {formatINR(s.revenue_inr)}</span>
                      <span>Margin {formatINR(s.margin_inr)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
