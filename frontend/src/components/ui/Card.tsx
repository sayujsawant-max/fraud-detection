/**
 * Card — the basic surface for every block of data on the dashboard.
 *
 * ``CardHeader`` / ``CardTitle`` / ``CardDescription`` / ``CardContent``
 * mirror the shadcn/ui shape so future migration is straightforward.
 */

import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Card({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>): ReactNode {
  return (
    <div
      className={cn(
        "card-surface rounded-xl shadow-card",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>): ReactNode {
  return (
    <div
      className={cn(
        "flex flex-col gap-1 border-b border-surface-border/60 px-5 py-4",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardTitle({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLHeadingElement>): ReactNode {
  return (
    <h3
      className={cn("text-sm font-semibold tracking-wide text-slate-100", className)}
      {...props}
    >
      {children}
    </h3>
  );
}

export function CardDescription({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLParagraphElement>): ReactNode {
  return (
    <p className={cn("text-xs text-slate-400", className)} {...props}>
      {children}
    </p>
  );
}

export function CardContent({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>): ReactNode {
  return (
    <div className={cn("px-5 py-4", className)} {...props}>
      {children}
    </div>
  );
}
