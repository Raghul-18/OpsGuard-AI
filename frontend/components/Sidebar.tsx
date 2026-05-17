"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  MessageSquare,
  RefreshCw,
  Bot,
  AlertTriangle,
  Zap,
  FileText,
  BarChart3,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { MERCHANT_ID } from "@/lib/api";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/reports/reconciliation", label: "Recon report", icon: FileText },
  { href: "/chat", label: "Ask OpsGuard", icon: MessageSquare },
  { href: "/sync", label: "Sync Status", icon: RefreshCw },
  { href: "/agent", label: "Agent Runs", icon: Bot },
  { href: "/disputes", label: "Disputes", icon: AlertTriangle },
];

export function Sidebar() {
  const path = usePathname();

  return (
    <aside className="w-56 shrink-0 flex flex-col border-r border-border bg-surface-1 h-full">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-border">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-accent flex items-center justify-center shadow-accent-glow">
            <Zap className="w-4 h-4 text-surface" strokeWidth={2.5} />
          </div>
          <div>
            <p className="font-display font-700 text-[13px] leading-none text-ink">
              OpsGuard
            </p>
            <p className="text-[10px] text-ink-muted leading-none mt-0.5 font-mono tracking-wide">
              AI
            </p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 px-2 flex flex-col gap-0.5">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = path === href || (href !== "/" && path.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded text-[13px] font-medium transition-all duration-150",
                active
                  ? "bg-accent-dim text-accent"
                  : "text-ink-muted hover:text-ink hover:bg-surface-3"
              )}
            >
              <Icon className="w-4 h-4 shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-4 py-4 border-t border-border">
        <p className="text-[11px] text-ink-faint font-mono">
          {MERCHANT_ID}
        </p>
        <p className="text-[10px] text-ink-faint mt-0.5">v1.1 · FastAPI + Next.js</p>
      </div>
    </aside>
  );
}
