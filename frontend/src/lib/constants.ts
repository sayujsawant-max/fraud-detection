/**
 * Project-wide constants. Centralised so external URLs and demo
 * payloads don't get hardcoded across multiple components.
 */

export const APP_NAME = "FraudShield MLOps";

/** Default base URL. Override via NEXT_PUBLIC_API_URL at build time. */
export const DEFAULT_API_BASE_URL = "http://localhost:8001";

export const API_BASE_URL: string =
  process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_BASE_URL;

/** External service links surfaced in the top-bar + Settings page. */
export const EXTERNAL_LINKS = {
  apiDocs: `${API_BASE_URL}/docs`,
  apiOpenapi: `${API_BASE_URL}/openapi.json`,
  apiMetrics: `${API_BASE_URL}/metrics`,
  mlflow: "http://localhost:5000",
  prefect: "http://localhost:4200",
  grafana: "http://localhost:3001",
  prometheusTargets: "http://localhost:9090/targets",
} as const;

/** Drift threshold mirrored from backend ``DRIFT_THRESHOLD`` setting. */
export const DRIFT_THRESHOLD = 0.3;

/** Session-storage keys. Centralised so we don't typo them. */
export const STORAGE_KEYS = {
  apiKey: "fraudshield.adminApiKey",
} as const;

/** Sidebar navigation. Source of truth for the App Shell + breadcrumbs. */
export const NAV_LINKS: ReadonlyArray<{
  href: string;
  label: string;
  description: string;
}> = [
  { href: "/", label: "Overview", description: "System KPIs" },
  { href: "/predict", label: "Predict", description: "Score a transaction" },
  { href: "/monitoring", label: "Monitoring", description: "Drift detection" },
  { href: "/experiments", label: "Experiments", description: "MLflow runs" },
  { href: "/logs", label: "Logs", description: "Prediction audit trail" },
  { href: "/settings", label: "Settings", description: "Admin actions" },
];
