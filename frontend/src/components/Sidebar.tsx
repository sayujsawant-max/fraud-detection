/**
 * Sidebar — the left rail of the dashboard.
 *
 * Renders the NAV_LINKS list and highlights the current route using the
 * Next.js ``usePathname`` hook. Hidden on mobile (where the AppShell
 * renders a slide-over drawer instead).
 */

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { APP_NAME, NAV_LINKS } from "@/lib/constants";
import { cn } from "@/lib/utils";

type SidebarProps = {
  onNavigate?: () => void;
};

export function Sidebar({ onNavigate }: SidebarProps) {
  const pathname = usePathname() ?? "/";

  return (
    <aside className="flex h-full w-64 flex-col gap-6 border-r border-surface-border/60 bg-surface-800/80 px-4 py-6">
      <Link
        href="/"
        onClick={onNavigate}
        className="flex items-center gap-2.5 px-2"
      >
        <span
          aria-hidden
          className="grid h-9 w-9 place-items-center rounded-lg bg-gradient-to-br from-brand to-brand-dark text-base font-bold text-white shadow-ring"
        >
          F
        </span>
        <span className="flex flex-col leading-tight">
          <span className="text-sm font-semibold text-slate-100">{APP_NAME}</span>
          <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-slate-500">
            Production MLOps
          </span>
        </span>
      </Link>

      <nav className="flex flex-col gap-1">
        {NAV_LINKS.map((link) => {
          const active =
            link.href === "/"
              ? pathname === "/"
              : pathname.startsWith(link.href);
          return (
            <Link
              key={link.href}
              href={link.href}
              onClick={onNavigate}
              className={cn(
                "group flex flex-col rounded-lg px-3 py-2 text-sm transition",
                active
                  ? "bg-brand/15 text-brand-light shadow-ring"
                  : "text-slate-300 hover:bg-surface-600/40 hover:text-slate-100",
              )}
            >
              <span className="font-medium">{link.label}</span>
              <span
                className={cn(
                  "text-[11px]",
                  active ? "text-brand-light/80" : "text-slate-500",
                )}
              >
                {link.description}
              </span>
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto rounded-lg border border-surface-border/60 bg-surface-700/40 px-3 py-3 text-[11px] text-slate-400">
        <div className="font-medium text-slate-200">FraudShield v0.8.0</div>
        <div className="mt-1">Phase 8 · Dashboard</div>
      </div>
    </aside>
  );
}
