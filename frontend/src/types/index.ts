/**
 * Shared frontend TypeScript types — mirrors the backend Pydantic schemas
 * declared in ``backend/src/api/schemas/`` and the Phase 7
 * ``fraudshield_*`` metric payloads.
 *
 * Keep field-name parity with the API responses so the typed client in
 * ``src/lib/api.ts`` can return objects without runtime translation.
 * When the backend adds a field, add it here too (or mark optional).
 */

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export type RootResponse = {
  name: string;
  version: string;
  docs: string;
};

export type HealthResponse = {
  status: string;
  version?: string;
};

export type ReadyResponse = {
  status: string;
  model_loaded: boolean;
  db_connected?: boolean;
};

// ---------------------------------------------------------------------------
// Model info
// ---------------------------------------------------------------------------

export type ModelInfo = {
  model_name: string;
  model_version: string;
  model_stage: string;
  threshold: number;
  is_dummy: boolean;
  loaded_at: string;
  feature_count?: number;
  run_id?: string | null;
};

// ---------------------------------------------------------------------------
// Predictions
// ---------------------------------------------------------------------------

export type MerchantCategory =
  | "groceries"
  | "electronics"
  | "travel"
  | "online"
  | "gas"
  | "restaurant";

export type TransactionTypeValue = "purchase" | "refund" | "cash_advance";
export type CardType = "visa" | "mastercard" | "amex" | "discover";
export type DeviceType = "mobile" | "desktop" | "pos_terminal" | "atm";
export type BrowserType = "chrome" | "safari" | "firefox" | "app" | "unknown";

/** Mirrors backend TransactionRequest exactly. */
export type TransactionRequest = {
  transaction_id?: string;
  transaction_amount: number;
  transaction_hour: number;
  transaction_day_of_week: number;
  is_weekend: 0 | 1;
  merchant_category: MerchantCategory;
  transaction_type: TransactionTypeValue;
  card_type: CardType;
  transaction_count_24h: number;
  transaction_count_7d: number;
  avg_transaction_amount_30d: number;
  amount_to_avg_ratio: number;
  unique_merchants_7d: number;
  is_first_transaction_merchant: 0 | 1;
  distance_from_home_km: number;
  is_foreign_transaction: 0 | 1;
  is_high_risk_country: 0 | 1;
  device_type: DeviceType;
  browser_type: BrowserType;
  ip_risk_score: number;
  account_age_days: number;
  user_age: number;
  credit_limit: number;
  credit_utilization: number;
  previous_fraud_flag: 0 | 1;
  log_amount: number;
  is_high_velocity: 0 | 1;
  is_new_account: 0 | 1;
  is_late_night: 0 | 1;
  amount_z_score: number;
};

export type PredictionResponse = {
  transaction_id: string;
  fraud_probability: number;
  predicted_label: 0 | 1;
  is_fraud: boolean;
  model_name: string;
  model_version: string;
  model_stage: string;
  threshold_used: number;
  latency_ms: number;
  timestamp: string;
};

export type BatchPredictionResponse = {
  predictions: PredictionResponse[];
  batch_size: number;
  batch_latency_ms: number;
  timestamp: string;
};

// ---------------------------------------------------------------------------
// Prediction logs
// ---------------------------------------------------------------------------

export type PredictionLogSummary = {
  id: string;
  transaction_id: string;
  timestamp: string;
  fraud_probability: number;
  predicted_label: 0 | 1;
  model_name: string;
  model_version: string;
  model_stage: string | null;
  optimal_threshold: number;
  latency_ms: number | null;
};

export type PredictionLogDetail = PredictionLogSummary & {
  input_features: Record<string, unknown>;
  created_at: string;
};

export type PredictionLogListResponse = {
  logs: PredictionLogSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type PredictionSummaryStats = {
  total_predictions: number;
  fraud_predictions: number;
  legitimate_predictions: number;
  fraud_rate: number;
  avg_fraud_probability: number;
  avg_latency_ms: number | null;
  latest_prediction_at: string | null;
};

// ---------------------------------------------------------------------------
// Drift / monitoring
// ---------------------------------------------------------------------------

export type DriftReportSummary = {
  id: string;
  report_id: string;
  generated_at: string;
  status: string;
  drift_detected: boolean;
  drift_score: number | null;
  num_drifted_features: number | null;
  total_features: number | null;
  num_samples: number;
  report_html_url?: string | null;
};

export type DriftReportDetail = DriftReportSummary & {
  reference_dataset_path: string | null;
  current_window_start: string | null;
  current_window_end: string | null;
  report_html_path: string | null;
  report_json_path: string | null;
  report_json: Record<string, unknown> | null;
  triggered_retrain: boolean;
  reason: string | null;
  created_at: string;
};

export type DriftReportListResponse = {
  reports: DriftReportSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type MonitoringStats = {
  latest_drift_score: number | null;
  latest_drift_detected: boolean | null;
  last_check_at: string | null;
  total_reports: number;
  drift_events: number;
  avg_drift_score: number;
};

export type DriftCheckResponse = {
  status: string;
  drift_detected: boolean;
  drift_score?: number | null;
  num_drifted_features?: number | null;
  total_features?: number | null;
  num_samples: number;
  report_id?: string | null;
  report_html_url?: string | null;
  reason?: string | null;
  generated_at: string;
};

// ---------------------------------------------------------------------------
// Retraining
// ---------------------------------------------------------------------------

export type RetrainingStatus = "running" | "promoted" | "rejected" | "failed";
export type RetrainingTrigger = "manual" | "drift" | "scheduled";

export type RetrainingRun = {
  id: string;
  trigger_reason: string;
  started_at: string;
  completed_at: string | null;
  status: RetrainingStatus;
  challenger_run_id: string | null;
  challenger_model_uri: string | null;
  challenger_model_version: string | null;
  challenger_pr_auc: number | null;
  champion_pr_auc: number | null;
  promoted: boolean;
  api_reload_status: string | null;
  outcome_notes: string | null;
  error_message: string | null;
  created_at: string;
};

export type RetrainingRunListResponse = {
  runs: RetrainingRun[];
  total: number;
  limit: number;
  offset: number;
};

export type RetrainingStats = {
  total_runs: number;
  promoted_runs: number;
  rejected_runs: number;
  failed_runs: number;
  latest_run_at: string | null;
  latest_status: RetrainingStatus | null;
};

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------

export type RetrainTriggerResponse = {
  status: string;
  trigger_reason: RetrainingTrigger;
  message: string;
};

export type ReloadModelResponse = {
  status: string;
  model_name: string;
  model_version: string;
  model_stage: string;
  is_dummy: boolean;
  loaded_at: string;
};

export type MonitoringRunResponse = {
  status: string;
  message: string;
};

// ---------------------------------------------------------------------------
// Experiments (best-effort — backend may or may not expose this)
// ---------------------------------------------------------------------------

export type ExperimentRun = {
  run_id: string;
  model_type: string;
  pr_auc?: number;
  roc_auc?: number;
  f1_score?: number;
  status?: string;
  created_at?: string;
  is_champion?: boolean;
};

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  status: number;
  body?: unknown;

  constructor(message: string, status: number, body?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}
