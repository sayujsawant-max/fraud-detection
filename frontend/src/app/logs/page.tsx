/**
 * Logs — paginated prediction-log audit trail with filter sidebar.
 *
 * Click a row to open a detail drawer with the full input_features JSON.
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { MetricCard } from "@/components/MetricCard";
import { RecentPredictionsTable } from "@/components/RecentPredictionsTable";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { ApiError, api } from "@/lib/api";
import {
  formatDateTime,
  formatInteger,
  formatNumber,
  formatPercent,
  timeAgo,
} from "@/lib/utils";
import type {
  PredictionLogDetail,
  PredictionLogSummary,
  PredictionSummaryStats,
} from "@/types";

type Filters = {
  label: "all" | "fraud" | "legitimate";
  min_probability: string;
  max_probability: string;
  limit: number;
};

const DEFAULT_FILTERS: Filters = {
  label: "all",
  min_probability: "",
  max_probability: "",
  limit: 50,
};

export default function LogsPage() {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [logs, setLogs] = useState<PredictionLogSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<PredictionSummaryStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<PredictionLogDetail | null>(null);
  const [selectedLoading, setSelectedLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const labelFilter =
        filters.label === "fraud"
          ? (1 as const)
          : filters.label === "legitimate"
            ? (0 as const)
            : undefined;
      const params = {
        limit: filters.limit,
        offset: 0,
        predicted_label: labelFilter,
        min_probability: filters.min_probability
          ? Number(filters.min_probability)
          : undefined,
        max_probability: filters.max_probability
          ? Number(filters.max_probability)
          : undefined,
      };

      const [logsResult, statsResult] = await Promise.allSettled([
        api.getLogs(params),
        api.getLogStats(),
      ]);

      setLogs(logsResult.status === "fulfilled" ? logsResult.value.logs : []);
      setTotal(logsResult.status === "fulfilled" ? logsResult.value.total : 0);
      setStats(statsResult.status === "fulfilled" ? statsResult.value : null);

      if (
        logsResult.status === "rejected" &&
        statsResult.status === "rejected"
      ) {
        setError("Could not fetch prediction logs.");
      }
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void load();
  }, [load]);

  async function openDetail(log: PredictionLogSummary) {
    setSelected({
      ...log,
      input_features: {},
      created_at: log.timestamp,
    });
    setSelectedLoading(true);
    try {
      const detail = await api.getLogDetail(log.id);
      setSelected(detail);
    } catch (err) {
      if (err instanceof ApiError || err instanceof Error) {
        setSelected({
          ...log,
          input_features: { error: err.message },
          created_at: log.timestamp,
        });
      }
    } finally {
      setSelectedLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100">
            Prediction Logs
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Every prediction the API has served, with full input features for
            audit + drift analysis.
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={load} loading={loading}>
          Refresh
        </Button>
      </header>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Total Predictions"
          value={formatInteger(stats?.total_predictions)}
          loading={loading}
        />
        <MetricCard
          label="Fraud Rate"
          value={formatPercent(stats?.fraud_rate, 1)}
          accent="brand"
          loading={loading}
        />
        <MetricCard
          label="Avg Latency"
          value={
            stats?.avg_latency_ms !== undefined && stats?.avg_latency_ms !== null
              ? `${formatNumber(stats.avg_latency_ms, 1)} ms`
              : "—"
          }
          loading={loading}
        />
        <MetricCard
          label="Latest Prediction"
          value={stats?.latest_prediction_at ? timeAgo(stats.latest_prediction_at) : "—"}
          hint={
            stats?.latest_prediction_at
              ? formatDateTime(stats.latest_prediction_at)
              : undefined
          }
          loading={loading}
        />
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Filters</CardTitle>
          <CardDescription>
            Narrow the audit-trail by predicted label or probability window.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Select
            label="Label"
            value={filters.label}
            options={[
              { value: "all", label: "All" },
              { value: "fraud", label: "Fraud" },
              { value: "legitimate", label: "Legitimate" },
            ]}
            onChange={(e) =>
              setFilters({ ...filters, label: e.target.value as Filters["label"] })
            }
          />
          <Input
            label="Min probability (0-1)"
            type="number"
            step="0.01"
            min={0}
            max={1}
            value={filters.min_probability}
            onChange={(e) =>
              setFilters({ ...filters, min_probability: e.target.value })
            }
          />
          <Input
            label="Max probability (0-1)"
            type="number"
            step="0.01"
            min={0}
            max={1}
            value={filters.max_probability}
            onChange={(e) =>
              setFilters({ ...filters, max_probability: e.target.value })
            }
          />
          <Select
            label="Limit"
            value={String(filters.limit)}
            options={[
              { value: "20", label: "20 rows" },
              { value: "50", label: "50 rows" },
              { value: "100", label: "100 rows" },
            ]}
            onChange={(e) =>
              setFilters({ ...filters, limit: Number(e.target.value) })
            }
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            Predictions{" "}
            <Badge tone="muted" className="ml-2">
              {formatInteger(total)} total
            </Badge>
          </CardTitle>
          <CardDescription>
            Click any row to view its full input_features payload.
          </CardDescription>
        </CardHeader>
        <CardContent className="px-0">
          {error ? (
            <ErrorState message={error} onRetry={load} />
          ) : logs.length > 0 ? (
            <RecentPredictionsTable logs={logs} onRowClick={openDetail} />
          ) : (
            <EmptyState
              title="No prediction logs match these filters"
              description="Try widening the probability window or clearing the label filter."
              cta={{ href: "/predict", label: "Run a prediction →" }}
            />
          )}
        </CardContent>
      </Card>

      {selected ? (
        <LogDetailModal
          log={selected}
          loading={selectedLoading}
          onClose={() => setSelected(null)}
        />
      ) : null}
    </div>
  );
}

function LogDetailModal({
  log,
  loading,
  onClose,
}: {
  log: PredictionLogDetail;
  loading: boolean;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/60 sm:items-center">
      <div className="relative h-[80vh] w-full max-w-2xl overflow-y-auto rounded-t-2xl border border-surface-border bg-surface-800 p-6 sm:rounded-2xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-slate-400">
              Prediction Detail
            </div>
            <div className="mt-1 font-mono text-xs text-slate-300">
              {log.transaction_id}
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
          <Field label="Probability" value={formatPercent(log.fraud_probability, 1)} />
          <Field
            label="Label"
            value={log.predicted_label === 1 ? "FRAUD" : "LEGIT"}
          />
          <Field
            label="Model"
            value={`${log.model_name} v${log.model_version}`}
          />
          <Field label="Threshold" value={formatNumber(log.optimal_threshold, 4)} />
          <Field label="Timestamp" value={formatDateTime(log.timestamp)} />
          <Field
            label="Latency"
            value={
              log.latency_ms !== null ? `${formatNumber(log.latency_ms, 1)} ms` : "—"
            }
          />
        </div>

        <div className="mt-4">
          <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-slate-400">
            Input Features
          </div>
          {loading ? (
            <div className="rounded-lg bg-surface-700/40 p-3 text-xs text-slate-400">
              Loading…
            </div>
          ) : (
            <pre className="max-h-[40vh] overflow-auto rounded-lg border border-surface-border bg-surface-900 p-4 font-mono text-[11px] text-slate-300">
              {JSON.stringify(log.input_features, null, 2)}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
        {label}
      </span>
      <span className="text-sm text-slate-200">{value}</span>
    </div>
  );
}
