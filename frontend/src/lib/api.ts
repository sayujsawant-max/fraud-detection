/**
 * Typed API client for the FraudShield FastAPI backend.
 *
 * Phase 0 exposes only health checks. Prediction, monitoring, experiments,
 * and admin endpoints are added in later phases.
 */

import type { HealthResponse, RootResponse } from "@/types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${path}`);
  }
  return (await response.json()) as T;
}

export const api = {
  root: () => request<RootResponse>("/"),
  health: () => request<HealthResponse>("/health"),
  ready: () => request<HealthResponse>("/ready"),
};
