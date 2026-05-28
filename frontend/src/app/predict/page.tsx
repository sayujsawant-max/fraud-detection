/**
 * Predict — the demo page. Submit a TransactionRequest, see fraud
 * probability + label + latency in the PredictionResultCard below.
 */

"use client";

import { useState } from "react";
import { ErrorState } from "@/components/ErrorState";
import { PredictionForm } from "@/components/PredictionForm";
import { PredictionResultCard } from "@/components/PredictionResultCard";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/Card";
import { ApiError, api } from "@/lib/api";
import type { PredictionResponse, TransactionRequest } from "@/types";

export default function PredictPage() {
  const [result, setResult] = useState<PredictionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(payload: TransactionRequest) {
    setSubmitting(true);
    setError(null);
    try {
      const response = await api.predict(payload);
      setResult(response);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`${err.message}`);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Unknown error");
      }
      setResult(null);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-100">
          Transaction Predictor
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Score a single transaction against the currently-loaded model.
          Switch sample payloads with the buttons below to demo legit,
          suspicious, and high-risk inputs side-by-side.
        </p>
      </header>

      {result ? <PredictionResultCard result={result} /> : null}
      {error ? <ErrorState title="Prediction failed" message={error} /> : null}

      <Card>
        <CardHeader>
          <CardTitle>Transaction Payload</CardTitle>
          <CardDescription>
            Every field maps to a column the sklearn pipeline saw at training
            time. ``log_amount`` is re-derived from amount on submit.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <PredictionForm onSubmit={handleSubmit} submitting={submitting} />
        </CardContent>
      </Card>
    </div>
  );
}
