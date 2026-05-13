"use client";

import { parseCitations } from "@/lib/utils";
import { CiteBadge } from "@/components/Badge";
import { Citation } from "@/lib/api";

interface CitedResponseProps {
  text: string;
  citations?: Citation[];
}

export function CitedResponse({ text, citations = [] }: CitedResponseProps) {
  const segments = parseCitations(text);
  const citationMap = new Map(citations.map((c) => [c.row_id, c]));

  return (
    <span className="leading-relaxed">
      {segments.map((seg, i) => {
        if (seg.type === "text") {
          return <span key={i}>{seg.text}</span>;
        }
        const ids = seg.rowId.split(",").map((s) => s.trim());
        return (
          <span key={i} className="inline-flex items-center flex-wrap gap-0.5">
            {ids.map((id) => {
              const meta = citationMap.get(id);
              return (
                <span key={id} className="group relative">
                  <CiteBadge rowId={id} />
                  {/* Tooltip */}
                  {meta && (
                    <span className="absolute bottom-full left-0 mb-1.5 hidden group-hover:flex flex-col gap-1 bg-surface-4 border border-border rounded-lg px-3 py-2 text-[11px] font-mono text-ink-muted whitespace-nowrap shadow-card z-50 pointer-events-none">
                      <span className="text-accent font-medium">{meta.source}</span>
                      <span>id: {meta.source_record_id}</span>
                      <span>
                        ingested:{" "}
                        {new Date(meta.ingested_at).toLocaleString("en-IN")}
                      </span>
                    </span>
                  )}
                </span>
              );
            })}
          </span>
        );
      })}
    </span>
  );
}
