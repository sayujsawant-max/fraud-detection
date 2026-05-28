/**
 * DriftReportsTable — list of drift_reports rows with quick links.
 */

import { Badge } from "@/components/ui/Badge";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { API_BASE_URL } from "@/lib/constants";
import { formatDateTime, formatNumber, shortId } from "@/lib/utils";
import type { DriftReportSummary } from "@/types";

type Props = {
  reports: DriftReportSummary[];
};

export function DriftReportsTable({ reports }: Props) {
  return (
    <Table>
      <THead>
        <TR>
          <TH>Report ID</TH>
          <TH>Generated</TH>
          <TH>Status</TH>
          <TH>Drift Score</TH>
          <TH>Detected</TH>
          <TH>Features Drifted</TH>
          <TH>Samples</TH>
          <TH>Artifact</TH>
        </TR>
      </THead>
      <TBody>
        {reports.map((r) => {
          const htmlPath =
            r.report_html_url ??
            `/v1/monitoring/drift-reports/${encodeURIComponent(r.report_id)}/html`;
          return (
            <TR key={r.id}>
              <TD className="font-mono text-xs text-slate-300">
                {shortId(r.report_id, 14)}
              </TD>
              <TD className="text-xs text-slate-400">
                {formatDateTime(r.generated_at)}
              </TD>
              <TD>
                <Badge
                  tone={
                    r.status === "complete"
                      ? "success"
                      : r.status === "skipped"
                        ? "muted"
                        : "danger"
                  }
                >
                  {r.status}
                </Badge>
              </TD>
              <TD className="font-semibold text-slate-100">
                {r.drift_score !== null
                  ? formatNumber(r.drift_score, 3)
                  : "—"}
              </TD>
              <TD>
                {r.drift_detected ? (
                  <Badge tone="danger">YES</Badge>
                ) : (
                  <Badge tone="success">NO</Badge>
                )}
              </TD>
              <TD className="text-xs text-slate-400">
                {r.num_drifted_features ?? "—"} /{" "}
                {r.total_features ?? "—"}
              </TD>
              <TD className="text-xs text-slate-400">{r.num_samples}</TD>
              <TD>
                <a
                  href={`${API_BASE_URL}${htmlPath}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-brand-light hover:underline"
                >
                  Open HTML ↗
                </a>
              </TD>
            </TR>
          );
        })}
      </TBody>
    </Table>
  );
}
