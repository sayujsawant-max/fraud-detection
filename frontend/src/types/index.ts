/**
 * Shared frontend TypeScript types.
 *
 * Phase 0 only declares health-check responses. Prediction, drift report,
 * MLflow run, and prediction-log types are added in later phases.
 */

export type RootResponse = {
  name: string;
  version: string;
  docs: string;
};

export type HealthResponse = {
  status: string;
  version?: string;
};
