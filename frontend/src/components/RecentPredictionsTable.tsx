/**
 * RecentPredictionsTable — compact table used on Overview + as the body
 * of the full Logs page (with optional onRowClick handler).
 */

import { Badge } from "@/components/ui/Badge";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import {
  formatNumber,
  formatPercent,
  shortId,
  timeAgo,
} from "@/lib/utils";
import type { PredictionLogSummary } from "@/types";

type Props = {
  logs: PredictionLogSummary[];
  onRowClick?: (log: PredictionLogSummary) => void;
};

export function RecentPredictionsTable({ logs, onRowClick }: Props) {
  return (
    <Table>
      <THead>
        <TR>
          <TH>Transaction</TH>
          <TH>Probability</TH>
          <TH>Label</TH>
          <TH>Model</TH>
          <TH>Latency</TH>
          <TH>When</TH>
        </TR>
      </THead>
      <TBody>
        {logs.map((log) => (
          <TR key={log.id} onClick={onRowClick ? () => onRowClick(log) : undefined}>
            <TD className="font-mono text-xs text-slate-300">
              {shortId(log.transaction_id, 12)}
            </TD>
            <TD>
              <span className="font-semibold text-slate-100">
                {formatPercent(log.fraud_probability, 1)}
              </span>
            </TD>
            <TD>
              {log.predicted_label === 1 ? (
                <Badge tone="danger">FRAUD</Badge>
              ) : (
                <Badge tone="success">LEGIT</Badge>
              )}
            </TD>
            <TD className="text-xs text-slate-400">
              {log.model_name} <span className="text-slate-500">v{log.model_version}</span>
            </TD>
            <TD className="text-xs text-slate-400">
              {log.latency_ms !== null
                ? `${formatNumber(log.latency_ms, 1)} ms`
                : "—"}
            </TD>
            <TD className="text-xs text-slate-400" title={log.timestamp}>
              {timeAgo(log.timestamp)}
            </TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}
