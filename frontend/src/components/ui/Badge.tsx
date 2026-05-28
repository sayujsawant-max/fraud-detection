/**
 * Badge — coloured pill used for labels (FRAUD/LEGIT, statuses, model stage).
 */

import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

type Tone =
  | "default"
  | "brand"
  | "success"
  | "warning"
  | "danger"
  | "info"
  | "muted";

const toneClasses: Record<Tone, string> = {
  default: "border-surface-border bg-surface-600/40 text-slate-200",
  brand: "border-brand/40 bg-brand/10 text-brand-light",
  success: "border-accent-green/40 bg-accent-green/10 text-accent-green",
  warning: "border-accent-yellow/40 bg-accent-yellow/10 text-accent-yellow",
  danger: "border-accent-red/40 bg-accent-red/10 text-accent-red",
  info: "border-sky-400/40 bg-sky-400/10 text-sky-300",
  muted: "border-slate-700/60 bg-slate-700/20 text-slate-400",
};

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  tone?: Tone;
  children: ReactNode;
};

export function Badge({
  className,
  tone = "default",
  children,
  ...props
}: BadgeProps): ReactNode {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-wider",
        toneClasses[tone],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  );
}
