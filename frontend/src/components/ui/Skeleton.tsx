/**
 * Skeleton — animated shimmer placeholder used while async data loads.
 */

import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Skeleton({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>): ReactNode {
  return (
    <div
      className={cn(
        "animate-pulse rounded-md bg-surface-600/40",
        className,
      )}
      {...props}
    />
  );
}
