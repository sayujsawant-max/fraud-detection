/**
 * MetricCard — single-number KPI card with optional trend indicator.
 */

import type { ReactNode } from "react";
import { Card } from "@/components/ui/Card";
import { cn } from "@/lib/utils";

type MetricCardProps = {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  trend?: "up" | "down" | "flat";
  trendLabel?: string;
  loading?: boolean;
  accent?: "default" | "brand" | "success" | "warning" | "danger";
};

const accentClasses: Record<
  NonNullable<MetricCardProps["accent"]>,
  string
> = {
  default: "text-slate-100",
  brand: "text-brand-light",
  success: "text-accent-green",
  warning: "text-accent-yellow",
  danger: "text-accent-red",
};

export function MetricCard({
  label,
  value,
  hint,
  trend,
  trendLabel,
  loading = false,
  accent = "default",
}: MetricCardProps) {
  return (
    <Card className="px-5 py-4">
      <div className="text-[11px] font-medium uppercase tracking-wider text-slate-400">
        {label}
      </div>
      <div className={cn("mt-2 text-3xl font-semibold", accentClasses[accent])}>
        {loading ? (
          <span className="inline-block h-7 w-20 animate-pulse rounded bg-surface-600/40" />
        ) : (
          value
        )}
      </div>
      {(hint || trendLabel) && !loading ? (
        <div className="mt-2 flex items-center gap-2 text-xs text-slate-400">
          {trend ? (
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px]",
                trend === "up" && "border-accent-green/40 bg-accent-green/10 text-accent-green",
                trend === "down" && "border-accent-red/40 bg-accent-red/10 text-accent-red",
                trend === "flat" && "border-slate-500/30 bg-slate-700/30 text-slate-300",
              )}
            >
              {trend === "up" ? "▲" : trend === "down" ? "▼" : "—"}
              {trendLabel}
            </span>
          ) : null}
          {hint ? <span>{hint}</span> : null}
        </div>
      ) : null}
    </Card>
  );
}
