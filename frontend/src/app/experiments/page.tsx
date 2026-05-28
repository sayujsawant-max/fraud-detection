/**
 * Experiments — shows the retraining-runs audit trail (the closest
 * thing to MLflow runs the backend exposes directly to the frontend)
 * plus a card that links out to the MLflow UI for deeper inspection.
 *
 * If a future backend ships /v1/experiments, the page surfaces those
 * rows too; the 404/network failure paths gracefully fall back to the
 * MLflow-UI card.
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { RetrainingRunsTable } from "@/components/RetrainingRunsTable";
import { Badge } from "@/components/ui/Badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/Card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { ApiError, api } from "@/lib/api";
import { EXTERNAL_LINKS } from "@/lib/constants";
import { formatNumber, shortId } from "@/lib/utils";
import type { ExperimentRun, RetrainingRun } from "@/types";

type Bundle = {
  experiments: ExperimentRun[] | null;
  experimentsErr: string | null;
  retrainingRuns: RetrainingRun[];
};

const EMPTY: Bundle = {
  experiments: null,
  experimentsErr: null,
  retrainingRuns: [],
};

export default function ExperimentsPage() {
  const [data, setData] = useState<Bundle>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [experiments, runs] = await Promise.allSettled([
        api.getExperiments(),
        api.getRetrainingRuns({ limit: 50 }),
      ]);

      const expErr =
        experiments.status === "rejected"
          ? experiments.reason instanceof ApiError
            ? experiments.reason.status === 404
              ? null
              : experiments.reason.message
            : experiments.reason instanceof Error
              ? experiments.reason.message
              : "Could not fetch experiments."
          : null;

      setData({
        experiments:
          experiments.status === "fulfilled" ? experiments.value : null,
        experimentsErr: expErr,
        retrainingRuns: runs.status === "fulfilled" ? runs.value.runs : [],
      });

      if (
        experiments.status === "rejected" &&
        runs.status === "rejected"
      ) {
        setError("Could not reach the experiment + retraining APIs.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100">Experiments</h1>
          <p className="mt-1 text-sm text-slate-400">
            MLflow tracks every training run. The dashboard surfaces the
            retraining-run audit trail; deeper run inspection lives in MLflow.
          </p>
        </div>
      </header>

      {error ? <ErrorState message={error} onRetry={load} /> : null}

      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-3">
          <div>
            <CardTitle>MLflow Tracking Server</CardTitle>
            <CardDescription>
              Experiment metrics, artifacts, registered model versions, and
              alias history live here.
            </CardDescription>
          </div>
          <a
            href={EXTERNAL_LINKS.mlflow}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-lg border border-brand/60 bg-brand/10 px-4 py-2 text-sm text-brand-light hover:bg-brand/20"
          >
            Open MLflow ↗
          </a>
        </CardHeader>
        <CardContent className="text-sm text-slate-300">
          The CI-train command (<code className="rounded bg-surface-700/60 px-1 py-0.5 text-xs">make train-mlflow</code>)
          logs three model families (Logistic Regression, Random Forest,
          XGBoost) per run, registers the PR-AUC winner under{" "}
          <code className="rounded bg-surface-700/60 px-1 py-0.5 text-xs">fraud-detector</code>{" "}
          and aliases it{" "}
          <Badge tone="brand" className="ml-1">champion</Badge>. Manual
          promotion via{" "}
          <code className="rounded bg-surface-700/60 px-1 py-0.5 text-xs">make promote-model</code>{" "}
          flips the{" "}
          <Badge tone="success" className="ml-1">production</Badge> alias.
        </CardContent>
      </Card>

      {data.experiments ? (
        <Card>
          <CardHeader>
            <CardTitle>Recent MLflow Runs</CardTitle>
            <CardDescription>
              Read from <code className="text-xs">/v1/experiments</code> on the
              backend.
            </CardDescription>
          </CardHeader>
          <CardContent className="px-0">
            {data.experiments.length > 0 ? (
              <ExperimentsTable runs={data.experiments} />
            ) : (
              <EmptyState
                title="No experiments yet"
                description="Run `make train-mlflow` to log a training run."
              />
            )}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Retraining Runs</CardTitle>
          <CardDescription>
            Every entry from the Phase 6 retraining flow, newest first. The
            challenger PR-AUC must beat the champion by
            <code className="ml-1 rounded bg-surface-700/60 px-1 py-0.5 text-xs">MODEL_PROMOTION_MIN_DELTA</code>{" "}
            for the alias to move.
          </CardDescription>
        </CardHeader>
        <CardContent className="px-0">
          {loading ? (
            <div className="px-5 py-4 text-sm text-slate-400">Loading…</div>
          ) : data.retrainingRuns.length > 0 ? (
            <RetrainingRunsTable runs={data.retrainingRuns} />
          ) : (
            <EmptyState
              title="No retraining runs yet"
              description="Trigger one from Settings, or wait for the Prefect schedule to fire."
              cta={{ href: "/settings", label: "Open Settings →" }}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function ExperimentsTable({ runs }: { runs: ExperimentRun[] }) {
  return (
    <Table>
      <THead>
        <TR>
          <TH>Run ID</TH>
          <TH>Model</TH>
          <TH>PR-AUC</TH>
          <TH>ROC-AUC</TH>
          <TH>F1</TH>
          <TH>Status</TH>
        </TR>
      </THead>
      <TBody>
        {runs.map((r) => (
          <TR key={r.run_id}>
            <TD className="font-mono text-xs text-slate-300">
              {shortId(r.run_id, 10)}
            </TD>
            <TD className="text-sm">
              {r.model_type}
              {r.is_champion ? (
                <Badge tone="brand" className="ml-2">
                  champion
                </Badge>
              ) : null}
            </TD>
            <TD className="font-semibold text-slate-100">
              {r.pr_auc !== undefined ? formatNumber(r.pr_auc, 4) : "—"}
            </TD>
            <TD>{r.roc_auc !== undefined ? formatNumber(r.roc_auc, 4) : "—"}</TD>
            <TD>{r.f1_score !== undefined ? formatNumber(r.f1_score, 4) : "—"}</TD>
            <TD className="text-xs text-slate-400">{r.status ?? "—"}</TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}
