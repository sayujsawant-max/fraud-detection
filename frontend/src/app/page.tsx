/**
 * Overview — the dashboard landing page.
 *
 * Aggregates KPIs from four backend endpoints in parallel:
 *   * /v1/logs/stats/summary
 *   * /v1/monitoring/stats
 *   * /v1/retraining/stats
 *   * /v1/model/info
 *
 * Any endpoint that 5xx's or 404s degrades gracefully into a placeholder
 * card — the page stays usable even when one half of the backend is down.
 */

"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { FraudRateChart } from "@/components/charts/FraudRateChart";
import { PredictionScoreDistribution } from "@/components/charts/PredictionScoreDistribution";
import { RetrainingStatusChart } from "@/components/charts/RetrainingStatusChart";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { MetricCard } from "@/components/MetricCard";
import { ModelInfoBadge } from "@/components/ModelInfoBadge";
import { RecentPredictionsTable } from "@/components/RecentPredictionsTable";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/Card";
import { api } from "@/lib/api";
import { DRIFT_THRESHOLD, EXTERNAL_LINKS } from "@/lib/constants";
import {
  formatInteger,
  formatNumber,
  formatPercent,
  timeAgo,
} from "@/lib/utils";
import type {
  ModelInfo,
  MonitoringStats,
  PredictionLogSummary,
  PredictionSummaryStats,
  RetrainingStats,
} from "@/types";

type Bundle = {
  stats: PredictionSummaryStats | null;
  drift: MonitoringStats | null;
  retraining: RetrainingStats | null;
  model: ModelInfo | null;
  recentLogs: PredictionLogSummary[];
};

const EMPTY: Bundle = {
  stats: null,
  drift: null,
  retraining: null,
  model: null,
  recentLogs: [],
};

export default function OverviewPage() {
  const [data, setData] = useState<Bundle>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [stats, drift, retraining, model, logs] = await Promise.allSettled([
        api.getLogStats(),
        api.getMonitoringStats(),
        api.getRetrainingStats(),
        api.modelInfo(),
        api.getLogs({ limit: 25 }),
      ]);

      const next: Bundle = {
        stats: stats.status === "fulfilled" ? stats.value : null,
        drift: drift.status === "fulfilled" ? drift.value : null,
        retraining: retraining.status === "fulfilled" ? retraining.value : null,
        model: model.status === "fulfilled" ? model.value : null,
        recentLogs: logs.status === "fulfilled" ? logs.value.logs : [],
      };
      setData(next);

      // If *all* calls failed, surface one error card. If only some failed,
      // the page still has useful info and we keep going silently.
      const allFailed = [stats, drift, retraining, model, logs].every(
        (r) => r.status === "rejected",
      );
      if (allFailed) {
        setError("Could not reach the FastAPI backend.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const driftTone: "success" | "warning" | "danger" | "muted" =
    data.drift?.latest_drift_detected === true
      ? "danger"
      : data.drift?.latest_drift_score !== null &&
          data.drift?.latest_drift_score !== undefined
        ? "success"
        : "muted";

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100">Overview</h1>
          <p className="mt-1 text-sm text-slate-400">
            Live snapshot of predictions, drift, and retraining across the
            FraudShield stack.
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={load} loading={loading}>
          Refresh
        </Button>
      </header>

      {error ? <ErrorState message={error} onRetry={load} /> : null}

      {/* Top KPI strip */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Total Predictions"
          value={formatInteger(data.stats?.total_predictions)}
          hint={
            data.stats?.latest_prediction_at
              ? `Latest ${timeAgo(data.stats.latest_prediction_at)}`
              : "No predictions yet"
          }
          loading={loading}
        />
        <MetricCard
          label="Fraud Predictions"
          value={formatInteger(data.stats?.fraud_predictions)}
          hint={
            data.stats
              ? `${formatInteger(data.stats.legitimate_predictions)} legitimate`
              : undefined
          }
          accent="warning"
          loading={loading}
        />
        <MetricCard
          label="Fraud Rate"
          value={formatPercent(data.stats?.fraud_rate, 1)}
          hint={
            data.stats?.avg_latency_ms !== undefined && data.stats?.avg_latency_ms !== null
              ? `Avg latency ${formatNumber(data.stats.avg_latency_ms, 1)} ms`
              : undefined
          }
          accent="brand"
          loading={loading}
        />
        <MetricCard
          label="Avg Fraud Probability"
          value={formatPercent(data.stats?.avg_fraud_probability, 1)}
          loading={loading}
        />
      </section>

      {/* Model + Drift + Retraining strip */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Latest Drift Score</CardTitle>
            <CardDescription>
              Threshold {DRIFT_THRESHOLD}. Higher = more drift detected.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-baseline gap-3">
              <span className="text-4xl font-semibold text-slate-100">
                {data.drift?.latest_drift_score !== null &&
                data.drift?.latest_drift_score !== undefined
                  ? formatNumber(data.drift.latest_drift_score, 3)
                  : "—"}
              </span>
              <Badge tone={driftTone}>
                {data.drift?.latest_drift_detected === true
                  ? "Drift detected"
                  : data.drift?.latest_drift_score !== null &&
                      data.drift?.latest_drift_score !== undefined
                    ? "Within tolerance"
                    : "No reports"}
              </Badge>
            </div>
            <div className="mt-3 text-xs text-slate-400">
              {data.drift?.last_check_at
                ? `Last check ${timeAgo(data.drift.last_check_at)} · ${data.drift?.total_reports ?? 0} report(s)`
                : "Run a drift check to populate this card."}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Latest Retraining</CardTitle>
            <CardDescription>
              Result of the most recent challenger evaluation.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {data.retraining?.latest_status ? (
              <div className="flex flex-col gap-2">
                <StatusBadge status={data.retraining.latest_status} />
                <span className="text-xs text-slate-400">
                  {data.retraining.latest_run_at
                    ? `Last run ${timeAgo(data.retraining.latest_run_at)}`
                    : ""}
                </span>
                <div className="mt-2 grid grid-cols-3 gap-2 text-[11px] text-slate-300">
                  <div className="rounded-md bg-surface-700/40 px-2 py-1">
                    <div className="text-accent-green">
                      {formatInteger(data.retraining.promoted_runs)}
                    </div>
                    <div className="text-slate-500">promoted</div>
                  </div>
                  <div className="rounded-md bg-surface-700/40 px-2 py-1">
                    <div className="text-accent-yellow">
                      {formatInteger(data.retraining.rejected_runs)}
                    </div>
                    <div className="text-slate-500">rejected</div>
                  </div>
                  <div className="rounded-md bg-surface-700/40 px-2 py-1">
                    <div className="text-accent-red">
                      {formatInteger(data.retraining.failed_runs)}
                    </div>
                    <div className="text-slate-500">failed</div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-sm text-slate-400">
                No retraining runs yet. Trigger one from{" "}
                <Link
                  href="/settings"
                  className="text-brand-light hover:underline"
                >
                  Settings
                </Link>
                .
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>External Tooling</CardTitle>
            <CardDescription>
              Jump to the underlying observability stack.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-2 text-xs">
            <ExternalCard href={EXTERNAL_LINKS.apiDocs} label="FastAPI Docs" />
            <ExternalCard href={EXTERNAL_LINKS.mlflow} label="MLflow" />
            <ExternalCard href={EXTERNAL_LINKS.prefect} label="Prefect" />
            <ExternalCard href={EXTERNAL_LINKS.grafana} label="Grafana" />
            <ExternalCard
              href={EXTERNAL_LINKS.prometheusTargets}
              label="Prometheus"
            />
            <ExternalCard href={EXTERNAL_LINKS.apiMetrics} label="/metrics" />
          </CardContent>
        </Card>
      </section>

      <ModelInfoBadge model={data.model} loading={loading} />

      {/* Charts row */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Fraud Rate (recent)</CardTitle>
            <CardDescription>
              Aggregated by hour over the most recent prediction logs.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {data.recentLogs.length > 0 ? (
              <FraudRateChart logs={data.recentLogs} />
            ) : (
              <div className="grid h-[260px] place-items-center text-sm text-slate-400">
                No prediction logs to chart yet.
              </div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Prediction Score Distribution</CardTitle>
            <CardDescription>
              How confident is the model? (lower = uncertain, higher = fraud)
            </CardDescription>
          </CardHeader>
          <CardContent>
            {data.recentLogs.length > 0 ? (
              <PredictionScoreDistribution logs={data.recentLogs} />
            ) : (
              <div className="grid h-[260px] place-items-center text-sm text-slate-400">
                No prediction logs to chart yet.
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Recent Predictions</CardTitle>
            <CardDescription>
              Newest first — full history in{" "}
              <Link href="/logs" className="text-brand-light hover:underline">
                Logs
              </Link>
              .
            </CardDescription>
          </CardHeader>
          <CardContent className="px-0">
            {data.recentLogs.length > 0 ? (
              <RecentPredictionsTable logs={data.recentLogs.slice(0, 10)} />
            ) : (
              <EmptyState
                title="No predictions yet"
                description="Submit a transaction from the Predict page to populate this table."
                cta={{ href: "/predict", label: "Open Predict →" }}
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Retraining Outcomes</CardTitle>
            <CardDescription>
              Distribution of finished retraining runs.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {data.retraining ? (
              <RetrainingStatusChart stats={data.retraining} />
            ) : (
              <div className="grid h-[260px] place-items-center text-sm text-slate-400">
                Retraining endpoint unavailable.
              </div>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function ExternalCard({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center justify-between rounded-lg border border-surface-border/60 bg-surface-700/40 px-3 py-2 hover:bg-surface-600/40"
    >
      <span className="font-medium text-slate-200">{label}</span>
      <span aria-hidden className="text-slate-500">↗</span>
    </a>
  );
}
