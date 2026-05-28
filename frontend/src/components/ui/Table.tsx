/**
 * Table — minimal data-table styling primitives. Pages compose them
 * directly rather than going through a heavy table library.
 */

import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Table({
  className,
  children,
}: HTMLAttributes<HTMLTableElement>): ReactNode {
  return (
    <div className="w-full overflow-x-auto">
      <table className={cn("w-full text-left text-sm", className)}>{children}</table>
    </div>
  );
}

export function THead({ children }: { children: ReactNode }): ReactNode {
  return (
    <thead className="bg-surface-700/40 text-[11px] font-medium uppercase tracking-wider text-slate-400">
      {children}
    </thead>
  );
}

export function TBody({ children }: { children: ReactNode }): ReactNode {
  return <tbody className="divide-y divide-surface-border/50">{children}</tbody>;
}

export function TR({
  children,
  onClick,
  className,
}: {
  children: ReactNode;
  onClick?: () => void;
  className?: string;
}): ReactNode {
  return (
    <tr
      onClick={onClick}
      className={cn(
        onClick ? "cursor-pointer hover:bg-surface-600/30" : undefined,
        className,
      )}
    >
      {children}
    </tr>
  );
}

export function TH({
  children,
  className,
}: HTMLAttributes<HTMLTableCellElement>): ReactNode {
  return (
    <th className={cn("whitespace-nowrap px-4 py-3 font-medium", className)}>
      {children}
    </th>
  );
}

export function TD({
  children,
  className,
  ...props
}: HTMLAttributes<HTMLTableCellElement>): ReactNode {
  return (
    <td
      className={cn("whitespace-nowrap px-4 py-3 text-slate-200", className)}
      {...props}
    >
      {children}
    </td>
  );
}
