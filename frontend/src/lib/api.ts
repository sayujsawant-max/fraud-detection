/**
 * Typed API client for the FraudShield FastAPI backend.
 *
 * All page-level fetches go through this client so:
 *   1. Errors are normalised to :class:`ApiError` (status + body) — pages
 *      can render an ErrorState without inspecting the raw fetch result.
 *   2. Admin endpoints are the only place the X-API-Key header is set,
 *      and the user-entered key is passed explicitly per-call. We NEVER
 *      stash it on a singleton.
 *   3. Calls default to ``cache: "no-store"`` so the dashboard always
 *      reflects the current backend state, even when SSR'd.
 */

import { API_BASE_URL } from "@/lib/constants";
import {
  ApiError,
  type BatchPredictionResponse,
  type DriftCheckResponse,
  type DriftReportDetail,
  type DriftReportListResponse,
  type ExperimentRun,
  type HealthResponse,
  type ModelInfo,
  type MonitoringRunResponse,
  type MonitoringStats,
  type PredictionLogDetail,
  type PredictionLogListResponse,
  type PredictionResponse,
  type PredictionSummaryStats,
  type ReadyResponse,
  type ReloadModelResponse,
  type RetrainTriggerResponse,
  type RetrainingRun,
  type RetrainingRunListResponse,
  type RetrainingStats,
  type RetrainingTrigger,
  type RootResponse,
  type TransactionRequest,
} from "@/types";

type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  headers?: Record<string, string>;
  /** Per-request timeout in ms. Default 15s. */
  timeoutMs?: number;
};

const DEFAULT_TIMEOUT_MS = 15_000;

function buildUrl(path: string, query?: Record<string, unknown>): string {
  const url = new URL(path, API_BASE_URL);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === "") continue;
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

async function request<T>(
  path: string,
  opts: RequestOptions = {},
  query?: Record<string, unknown>,
): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(),
    opts.timeoutMs ?? DEFAULT_TIMEOUT_MS,
  );

  const init: RequestInit = {
    method: opts.method ?? "GET",
    headers: {
      Accept: "application/json",
      ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(opts.headers ?? {}),
    },
    cache: "no-store",
    signal: controller.signal,
  };
  if (opts.body !== undefined) {
    init.body = JSON.stringify(opts.body);
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), init);
  } catch (err) {
    clearTimeout(timeout);
    const message =
      err instanceof DOMException && err.name === "AbortError"
        ? `Request timed out: ${path}`
        : `Network error reaching the API: ${path}`;
    throw new ApiError(message, 0, err);
  }
  clearTimeout(timeout);

  if (!response.ok) {
    let body: unknown = undefined;
    try {
      body = await response.json();
    } catch {
      try {
        body = await response.text();
      } catch {
        /* ignore */
      }
    }
    const detail =
      (body as { detail?: string } | null)?.detail ?? response.statusText;
    throw new ApiError(`${response.status} ${detail}`, response.status, body);
  }

  // 204 No Content + empty bodies — guard so .json() doesn't throw.
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

// ---------------------------------------------------------------------------
// Health / model
// ---------------------------------------------------------------------------

export const api = {
  root: () => request<RootResponse>("/"),
  health: () => request<HealthResponse>("/health"),
  ready: () => request<ReadyResponse>("/ready"),
  modelInfo: () => request<ModelInfo>("/v1/model/info"),

  // ------------------------------------------------------------------
  // Predictions
  // ------------------------------------------------------------------

  predict: (payload: TransactionRequest) =>
    request<PredictionResponse>("/v1/predict", {
      method: "POST",
      body: payload,
    }),

  predictBatch: (transactions: TransactionRequest[]) =>
    request<BatchPredictionResponse>("/v1/predict/batch", {
      method: "POST",
      body: { transactions },
    }),

  // ------------------------------------------------------------------
  // Logs
  // ------------------------------------------------------------------

  getLogs: (params?: {
    limit?: number;
    offset?: number;
    predicted_label?: 0 | 1;
    min_probability?: number;
    max_probability?: number;
    transaction_id?: string;
  }) =>
    request<PredictionLogListResponse>("/v1/logs", {}, params as Record<
      string,
      unknown
    >),

  getLogDetail: (logId: string) =>
    request<PredictionLogDetail>(`/v1/logs/${encodeURIComponent(logId)}`),

  getLogStats: () =>
    request<PredictionSummaryStats>("/v1/logs/stats/summary"),

  // ------------------------------------------------------------------
  // Monitoring
  // ------------------------------------------------------------------

  runDriftCheck: () =>
    request<DriftCheckResponse>("/v1/monitoring/drift/check", {
      method: "POST",
      body: {},
    }),

  getDriftReports: (params?: {
    limit?: number;
    offset?: number;
    drift_detected?: boolean;
  }) =>
    request<DriftReportListResponse>(
      "/v1/monitoring/drift-reports",
      {},
      params as Record<string, unknown>,
    ),

  getLatestDriftReport: () =>
    request<DriftReportDetail>("/v1/monitoring/drift-reports/latest"),

  getDriftReportDetail: (reportId: string) =>
    request<DriftReportDetail>(
      `/v1/monitoring/drift-reports/${encodeURIComponent(reportId)}`,
    ),

  getMonitoringStats: () =>
    request<MonitoringStats>("/v1/monitoring/stats"),

  // ------------------------------------------------------------------
  // Retraining
  // ------------------------------------------------------------------

  getRetrainingRuns: (params?: {
    limit?: number;
    offset?: number;
    status?: string;
    trigger_reason?: string;
  }) =>
    request<RetrainingRunListResponse>(
      "/v1/retraining/runs",
      {},
      params as Record<string, unknown>,
    ),

  getLatestRetrainingRun: () =>
    request<RetrainingRun>("/v1/retraining/runs/latest"),

  getRetrainingStats: () =>
    request<RetrainingStats>("/v1/retraining/stats"),

  // ------------------------------------------------------------------
  // Experiments — backend stub. Returns 404 if not implemented; pages
  // gracefully fall back to "open MLflow UI" instead.
  // ------------------------------------------------------------------

  getExperiments: () => request<ExperimentRun[]>("/v1/experiments"),

  // ------------------------------------------------------------------
  // Admin (require API key)
  // ------------------------------------------------------------------

  triggerRetrain: (apiKey: string, triggerReason: RetrainingTrigger) =>
    request<RetrainTriggerResponse>("/v1/admin/retrain", {
      method: "POST",
      headers: { "X-API-Key": apiKey },
      body: { trigger_reason: triggerReason },
    }),

  reloadModel: (apiKey: string) =>
    request<ReloadModelResponse>("/v1/admin/reload-model", {
      method: "POST",
      headers: { "X-API-Key": apiKey },
    }),

  runMonitoringFlow: (apiKey: string) =>
    request<MonitoringRunResponse>("/v1/admin/monitoring/run", {
      method: "POST",
      headers: { "X-API-Key": apiKey },
    }),
};

export { ApiError };
