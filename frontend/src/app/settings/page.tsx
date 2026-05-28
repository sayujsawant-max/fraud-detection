/**
 * Settings — admin actions + external service links + dev commands.
 *
 * The admin API key lives in sessionStorage only (cleared on tab close).
 * We never log it, never send it to a third party, and the input is
 * masked by default with a "show" toggle for accessibility.
 */

"use client";

import { useEffect, useState } from "react";
import { AdminActionCard } from "@/components/AdminActionCard";
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
import { api } from "@/lib/api";
import {
  API_BASE_URL,
  EXTERNAL_LINKS,
  STORAGE_KEYS,
} from "@/lib/constants";
import { formatDateTime } from "@/lib/utils";
import type { ModelInfo, ReadyResponse, RetrainingTrigger } from "@/types";

export default function SettingsPage() {
  const [apiKey, setApiKey] = useState<string>("");
  const [showKey, setShowKey] = useState(false);
  const [trigger, setTrigger] = useState<RetrainingTrigger>("manual");
  const [ready, setReady] = useState<ReadyResponse | null>(null);
  const [model, setModel] = useState<ModelInfo | null>(null);

  // Restore the key from sessionStorage on first render (client-only).
  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.sessionStorage.getItem(STORAGE_KEYS.apiKey);
    if (stored) setApiKey(stored);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void Promise.allSettled([api.ready(), api.modelInfo()]).then(([rd, m]) => {
      if (cancelled) return;
      setReady(rd.status === "fulfilled" ? rd.value : null);
      setModel(m.status === "fulfilled" ? m.value : null);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  function saveKey() {
    if (typeof window === "undefined") return;
    if (apiKey) {
      window.sessionStorage.setItem(STORAGE_KEYS.apiKey, apiKey);
    } else {
      window.sessionStorage.removeItem(STORAGE_KEYS.apiKey);
    }
  }

  function clearKey() {
    setApiKey("");
    if (typeof window !== "undefined") {
      window.sessionStorage.removeItem(STORAGE_KEYS.apiKey);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-100">Settings & Admin</h1>
        <p className="mt-1 text-sm text-slate-400">
          Operator-facing actions. Admin endpoints require an API key — set it
          here and the buttons below will use it.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>API Configuration</CardTitle>
          <CardDescription>
            Connection details derived from <code className="text-xs">NEXT_PUBLIC_API_URL</code>.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="API Base URL" value={<span className="font-mono">{API_BASE_URL}</span>} />
          <Field
            label="API Status"
            value={
              ready ? (
                <Badge tone={ready.status === "ok" ? "success" : "warning"}>
                  {ready.status}
                </Badge>
              ) : (
                <Badge tone="muted">checking…</Badge>
              )
            }
          />
          <Field
            label="Model Loaded"
            value={
              ready ? (
                <Badge tone={ready.model_loaded ? "success" : "danger"}>
                  {ready.model_loaded ? "yes" : "no"}
                </Badge>
              ) : (
                "—"
              )
            }
          />
          <Field
            label="Current Model"
            value={
              model
                ? `${model.model_name} v${model.model_version}${
                    model.is_dummy ? " (dummy)" : ""
                  }`
                : "—"
            }
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Admin API Key</CardTitle>
          <CardDescription>
            Required for the admin actions below. Stored only in your browser{" "}
            <code className="text-xs">sessionStorage</code> (cleared on tab
            close) — never logged, never sent to a third party.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="flex-1">
              <Input
                label="X-API-Key"
                type={showKey ? "text" : "password"}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="change-me"
                hint="Defaults to ``change-me`` in local dev (.env.example)."
              />
            </div>
            <div className="flex gap-2">
              <Button variant="secondary" size="md" onClick={() => setShowKey((v) => !v)}>
                {showKey ? "Hide" : "Show"}
              </Button>
              <Button variant="primary" size="md" onClick={saveKey}>
                Save
              </Button>
              <Button variant="ghost" size="md" onClick={clearKey}>
                Clear
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <AdminActionCard
          title="Trigger Retraining"
          description="Posts to /v1/admin/retrain — runs the Prefect retraining flow in the background."
          buttonLabel="Run Retraining Flow"
          apiKey={apiKey}
          run={(key) => api.triggerRetrain(key, trigger)}
        />
        <AdminActionCard
          title="Reload Production Model"
          description="Posts to /v1/admin/reload-model — re-fetches the model from MLflow into the live predictor."
          buttonLabel="Reload Model"
          apiKey={apiKey}
          run={api.reloadModel}
        />
        <AdminActionCard
          title="Run Monitoring Flow"
          description="Posts to /v1/admin/monitoring/run — fires the Phase 6 monitoring flow once."
          buttonLabel="Run Monitoring Flow"
          apiKey={apiKey}
          run={api.runMonitoringFlow}
        />
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Retraining Trigger Reason</CardTitle>
          <CardDescription>
            Tags the retraining_runs row so the audit trail explains why this
            run happened.
          </CardDescription>
        </CardHeader>
        <CardContent className="max-w-xs">
          <Select
            label="Trigger reason"
            value={trigger}
            options={[
              { value: "manual", label: "Manual" },
              { value: "drift", label: "Drift" },
              { value: "scheduled", label: "Scheduled" },
            ]}
            onChange={(e) => setTrigger(e.target.value as RetrainingTrigger)}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>External Service Links</CardTitle>
          <CardDescription>
            Jump straight to the underlying observability + tracking surfaces.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-3">
          <ExtLink href={EXTERNAL_LINKS.apiDocs} label="FastAPI Docs" />
          <ExtLink href={EXTERNAL_LINKS.apiOpenapi} label="OpenAPI Schema" />
          <ExtLink href={EXTERNAL_LINKS.apiMetrics} label="/metrics" />
          <ExtLink href={EXTERNAL_LINKS.mlflow} label="MLflow UI" />
          <ExtLink href={EXTERNAL_LINKS.prefect} label="Prefect UI" />
          <ExtLink href={EXTERNAL_LINKS.grafana} label="Grafana" />
          <ExtLink href={EXTERNAL_LINKS.prometheusTargets} label="Prometheus" />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Developer Commands</CardTitle>
          <CardDescription>
            Run from the project root. Mirrors the Phase 6/7 Make targets.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <pre className="overflow-x-auto rounded-lg bg-surface-900 p-4 font-mono text-xs text-slate-300">
{`make docker-up                # bring up the full 7-service stack
make smoke-predict            # send one /v1/predict request
make drift-check              # run Evidently from the CLI
make run-retraining-flow      # run the Prefect retraining flow once
make trigger-retrain API_KEY=change-me
make monitoring-smoke         # generate traffic + show fraudshield_* metrics
make phase7-test              # run the Phase 7 metric tests`}
          </pre>
          <div className="mt-3 text-xs text-slate-500">
            Last checked {formatDateTime(new Date().toISOString())}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">
        {label}
      </span>
      <span className="text-sm text-slate-200">{value}</span>
    </div>
  );
}

function ExtLink({ href, label }: { href: string; label: string }) {
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
