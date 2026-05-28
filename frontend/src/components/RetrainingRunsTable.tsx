/**
 * RetrainingRunsTable — shows champion vs challenger PR-AUC outcomes.
 */

import { StatusBadge } from "@/components/StatusBadge";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import {
  formatDateTime,
  formatNumber,
  shortId,
} from "@/lib/utils";
import type { RetrainingRun } from "@/types";

type Props = {
  runs: RetrainingRun[];
};

export function RetrainingRunsTable({ runs }: Props) {
  return (
    <Table>
      <THead>
        <TR>
          <TH>Run ID</TH>
          <TH>Trigger</TH>
          <TH>Status</TH>
          <TH>Champion PR-AUC</TH>
          <TH>Challenger PR-AUC</TH>
          <TH>Δ</TH>
          <TH>Started</TH>
          <TH>Notes</TH>
        </TR>
      </THead>
      <TBody>
        {runs.map((r) => {
          const delta =
            r.challenger_pr_auc !== null && r.champion_pr_auc !== null
              ? r.challenger_pr_auc - r.champion_pr_auc
              : null;
          return (
            <TR key={r.id}>
              <TD className="font-mono text-xs text-slate-300">
                {shortId(r.id, 8)}
              </TD>
              <TD className="text-xs text-slate-400">{r.trigger_reason}</TD>
              <TD>
                <StatusBadge status={r.status} />
              </TD>
              <TD>
                {r.champion_pr_auc !== null
                  ? formatNumber(r.champion_pr_auc, 4)
                  : "—"}
              </TD>
              <TD className="font-semibold text-slate-100">
                {r.challenger_pr_auc !== null
                  ? formatNumber(r.challenger_pr_auc, 4)
                  : "—"}
              </TD>
              <TD
                className={
                  delta === null
                    ? "text-slate-400"
                    : delta >= 0
                      ? "text-accent-green"
                      : "text-accent-red"
                }
              >
                {delta === null
                  ? "—"
                  : `${delta >= 0 ? "+" : ""}${formatNumber(delta, 4)}`}
              </TD>
              <TD className="text-xs text-slate-400">
                {formatDateTime(r.started_at)}
              </TD>
              <TD
                className="max-w-[24ch] truncate text-xs text-slate-400"
                title={r.outcome_notes ?? r.error_message ?? ""}
              >
                {r.outcome_notes ?? r.error_message ?? "—"}
              </TD>
            </TR>
          );
        })}
      </TBody>
    </Table>
  );
}
