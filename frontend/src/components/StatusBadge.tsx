/**
 * StatusBadge — colour-coded badge for retraining / drift statuses.
 */

import { Badge } from "@/components/ui/Badge";

type Status =
  | "running"
  | "promoted"
  | "rejected"
  | "failed"
  | "complete"
  | "skipped"
  | "triggered"
  | "ok"
  | "down"
  | string;

const toneMap: Record<string, "muted" | "success" | "warning" | "danger" | "info" | "brand"> = {
  running: "info",
  promoted: "success",
  rejected: "warning",
  failed: "danger",
  complete: "success",
  skipped: "muted",
  triggered: "brand",
  ok: "success",
  down: "danger",
};

export function StatusBadge({ status }: { status: Status }) {
  const tone = toneMap[status.toLowerCase()] ?? "muted";
  return <Badge tone={tone}>{status}</Badge>;
}
