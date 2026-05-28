/**
 * Monitoring — drift detection page.
 *
 * Shows the latest drift status banner, KPI cards, the drift-score time
 * series chart, the drift_reports table, and a "Run drift check now"
 * button that fires the Phase 5 manual check.
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import { DriftReportsTable } from "@/components/DriftReportsTable";
import { DriftScoreChart } from "@/components/charts/DriftScoreChart";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { MetricCard } from "@/components/MetricCard";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/Card";
import { ApiError, api } from "@/lib/api";
import { DRIFT_THRESHOLD } from "@/lib/constants";
import {
  formatDateTime,
  formatInteger,
  formatNumber,
  timeAgo,
} from "@/lib/utils";
import type {
  DriftCheckResponse,
  DriftReportSummary,
  MonitoringStats,
} from "@/types";

type Bundle = {
  reports: DriftReportSummary[];
  stats: MonitoringStats | null;
};

const EMPTY: Bundle = { reports: [], stats: null };

export default function MonitoringPage() {
  const [data, setData] = useState<Bundle>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<DriftCheckResponse | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [reports, stats] = await Promise.allSettled([
        api.getDriftReports({ limit: 50 }),
        api.getMonitoringStats(),
      ]);
      setData({
        reports: reports.status === "fulfilled" ? reports.value.reports : [],
        stats: stats.status === "fulfilled" ? stats.value : null,
      });
      if (reports.status === "rejected" && stats.status === "rejected") {
        setError("Could not reach the monitoring API.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function runCheck() {
    setRunning(true);
    setRunError(null);
    setRunResult(null);
    try {
      const result = await api.runDriftCheck();
      setRunResult(result);
      await load();
    } catch (err) {
      if (err instanceof ApiError) {
        setRunError(err.message);
      } else if (err instanceof Error) {
        setRunError(err.message);
      } else {
        setRunError("Unknown error");
      }
    } finally {
      setRunning(false);
    }
  }

  const latestDetected =
    data.stats?.latest_drift_detected ?? data.reports[0]?.drift_detected;
  const latestScore =
    data.stats?.latest_drift_score ?? data.reports[0]?.drift_score ?? null;

  const banner =
    data.reports.length === 0
      ? { tone: "muted" as const, text: "No drift reports yet." }
      : latestDetected
        ? {
            tone: "danger" as const,
            text: "Drift detected — a challenger retrain may be warranted.",
          }
        : {
            tone: "success" as const,
            text: "All clear — recent inputs match the reference distribution.",
          };

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100">Monitoring & Drift</h1>
          <p className="mt-1 text-sm text-slate-400">
            Evidently AI compares recent predictions against the training
            reference snapshot. Threshold {DRIFT_THRESHOLD}.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={load} loading={loading}>
            Refresh
          </Button>
          <Button onClick={runCheck} loading={running} disabled={running}>
            {running ? "Running…" : "Run drift check"}
          </Button>
        </div>
      </header>

      <Badge tone={banner.tone}>{banner.text}</Badge>

      {runResult ? (
        <Card>
          <CardHeader>
            <CardTitle>Drift Check Result</CardTitle>
            <CardDescription>
              {runResult.status === "skipped"
                ? "Skipped — need at least 200 prediction logs to compute a reliable drift report."
                : runResult.status === "complete"
                  ? "Evidently completed and a new drift_reports row was inserted."
                  : runResult.reason ?? "See server logs."}
            </CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
            <Field label="Status" value={runResult.status} />
            <Field
              label="Drift detected"
              value={runResult.drift_detected ? "yes" : "no"}
            />
            <Field
              label="Drift score"
              value={
                runResult.drift_score !== null &&
                runResult.drift_score !== undefined
                  ? formatNumber(runResult.drift_score, 3)
                  : "—"
              }
            />
            <Field label="Samples" value={formatInteger(runResult.num_samples)} />
          </CardContent>
        </Card>
      ) : null}

      {runError ? <ErrorState title="Drift check failed" message={runError} /> : null}

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Latest Drift Score"
          value={
            latestScore !== null && latestScore !== undefined
              ? formatNumber(latestScore, 3)
              : "—"
          }
          accent={latestDetected ? "danger" : "success"}
          loading={loading}
        />
        <MetricCard
          label="Drift Events"
          value={formatInteger(data.stats?.drift_events)}
          accent="warning"
          loading={loading}
        />
        <MetricCard
          label="Total Reports"
          value={formatInteger(data.stats?.total_reports)}
          loading={loading}
        />
        <MetricCard
          label="Last Check"
          value={data.stats?.last_check_at ? timeAgo(data.stats.last_check_at) : "—"}
          hint={
            data.stats?.last_check_at
              ? formatDateTime(data.stats.last_check_at)
              : undefined
          }
          loading={loading}
        />
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Drift Score Over Time</CardTitle>
          <CardDescription>
            Threshold line at {DRIFT_THRESHOLD} marks the configured drift gate.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {data.reports.length > 0 ? (
            <DriftScoreChart reports={data.reports} />
          ) : (
            <div className="grid h-[260px] place-items-center text-sm text-slate-400">
              No reports yet — run a drift check above to populate this chart.
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Drift Reports</CardTitle>
          <CardDescription>
            Click &ldquo;Open HTML&rdquo; on any row to view the rendered Evidently report.
          </CardDescription>
        </CardHeader>
        <CardContent className="px-0">
          {error ? (
            <ErrorState message={error} onRetry={load} />
          ) : data.reports.length > 0 ? (
            <DriftReportsTable reports={data.reports} />
          ) : (
            <EmptyState
              title="No drift reports yet"
              description="Seed prediction logs (≥200) and run a drift check to generate one."
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
        {label}
      </span>
      <span className="text-sm text-slate-200">{value}</span>
    </div>
  );
}
