import { cn } from "@/lib/utils";

type BadgeVariant = "done" | "running" | "failed" | "pending" | "open" | "actioned" | "dismissed" | "manual" | "cron";

const variantMap: Record<BadgeVariant, string> = {
  done: "bg-success-dim text-success border-success/20",
  running: "bg-accent-dim text-accent border-accent/20",
  failed: "bg-danger-dim text-danger border-danger/20",
  pending: "bg-surface-4 text-ink-muted border-border",
  open: "bg-warn-dim text-warn border-warn/20",
  actioned: "bg-success-dim text-success border-success/20",
  dismissed: "bg-surface-4 text-ink-muted border-border",
  manual: "bg-accent-dim text-accent border-accent/20",
  cron: "bg-surface-3 text-ink-muted border-border",
};

const dotMap: Record<BadgeVariant, boolean> = {
  done: false,
  running: true,
  failed: false,
  pending: false,
  open: false,
  actioned: false,
  dismissed: false,
  manual: false,
  cron: false,
};

interface BadgeProps {
  variant: BadgeVariant;
  children: React.ReactNode;
}

export function Badge({ variant, children }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-medium border font-mono",
        variantMap[variant]
      )}
    >
      {dotMap[variant] && (
        <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse-dot" />
      )}
      {children}
    </span>
  );
}

export function CiteBadge({ rowId }: { rowId: string }) {
  const short = rowId.slice(0, 8);
  return (
    <span
      title={`Source row: ${rowId}`}
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-accent-dim text-accent text-[10px] font-mono border border-accent/20 cursor-help mx-0.5 align-baseline"
    >
      ⌖ {short}
    </span>
  );
}
