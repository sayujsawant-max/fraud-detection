/**
 * Tiny utility helpers used across the dashboard.
 */

import { clsx, type ClassValue } from "clsx";

/** Tailwind-friendly classnames concatenation. */
export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}

/** Format a number to 1 decimal place, falling back to em-dash. */
export function formatNumber(
  value: number | null | undefined,
  decimals = 2,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function formatInteger(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return Math.round(value).toLocaleString();
}

/** Render a 0..1 fraction as "12.3%". */
export function formatPercent(
  value: number | null | undefined,
  decimals = 1,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(decimals)}%`;
}

/** Human-friendly time delta relative to now. */
export function timeAgo(input: string | null | undefined): string {
  if (!input) return "—";
  const then = new Date(input).getTime();
  if (Number.isNaN(then)) return "—";
  const diffMs = Date.now() - then;
  const diffSec = Math.round(diffMs / 1000);
  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  return `${diffDay}d ago`;
}

/** ISO timestamp → "2026-05-28 14:35:12" UTC-stable format. */
export function formatDateTime(input: string | null | undefined): string {
  if (!input) return "—";
  const date = new Date(input);
  if (Number.isNaN(date.getTime())) return "—";
  const pad = (n: number) => n.toString().padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  );
}

/** Truncate long IDs so tables stay readable. */
export function shortId(value: string | null | undefined, head = 8): string {
  if (!value) return "—";
  if (value.length <= head + 4) return value;
  return `${value.slice(0, head)}…`;
}

/** Map a 0..1 fraud probability to one of three labels. */
export function riskLevel(p: number): "low" | "medium" | "high" {
  if (p < 0.3) return "low";
  if (p < 0.7) return "medium";
  return "high";
}
