import { cn } from "@/lib/utils";
import { LucideIcon } from "lucide-react";

interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  icon: LucideIcon;
  variant?: "default" | "warn" | "danger" | "success";
  delay?: number;
}

const variantStyles = {
  default: {
    icon: "text-accent bg-accent-dim",
    value: "text-ink",
  },
  warn: {
    icon: "text-warn bg-warn-dim",
    value: "text-warn",
  },
  danger: {
    icon: "text-danger bg-danger-dim",
    value: "text-danger",
  },
  success: {
    icon: "text-success bg-success-dim",
    value: "text-success",
  },
};

export function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  variant = "default",
  delay = 0,
}: StatCardProps) {
  const styles = variantStyles[variant];

  return (
    <div
      className="rounded-xl bg-surface-2 border border-border shadow-card p-5 flex flex-col gap-4 opacity-0 animate-fade-up"
      style={{ animationDelay: `${delay}ms`, animationFillMode: "forwards" }}
    >
      <div className="flex items-center justify-between">
        <p className="text-[12px] font-medium text-ink-muted uppercase tracking-widest">
          {label}
        </p>
        <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center", styles.icon)}>
          <Icon className="w-4 h-4" />
        </div>
      </div>
      <div>
        <p className={cn("text-2xl font-display font-700 leading-none", styles.value)}>
          {value}
        </p>
        {sub && (
          <p className="text-[12px] text-ink-muted mt-1.5">{sub}</p>
        )}
      </div>
    </div>
  );
}

export function StatCardSkeleton() {
  return (
    <div className="rounded-xl bg-surface-2 border border-border shadow-card p-5 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="skeleton h-3 w-20 rounded" />
        <div className="skeleton w-8 h-8 rounded-lg" />
      </div>
      <div>
        <div className="skeleton h-7 w-24 rounded" />
        <div className="skeleton h-3 w-32 rounded mt-2" />
      </div>
    </div>
  );
}
