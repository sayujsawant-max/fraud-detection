/**
 * AdminActionCard — single admin action button that surfaces success +
 * error inline. The API key is passed in as a prop so the parent owns
 * the (sessionStorage-only) source of truth.
 */

"use client";

import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { ApiError } from "@/lib/api";

type AdminActionCardProps = {
  title: string;
  description: string;
  buttonLabel: string;
  apiKey: string;
  run: (apiKey: string) => Promise<unknown>;
  formatSuccess?: (response: unknown) => ReactNode;
};

export function AdminActionCard({
  title,
  description,
  buttonLabel,
  apiKey,
  run,
  formatSuccess,
}: AdminActionCardProps) {
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState<ReactNode | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
    if (!apiKey) {
      setError("Enter the admin API key first.");
      return;
    }
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const response = await run(apiKey);
      setSuccess(
        formatSuccess?.(response) ?? (
          <pre className="overflow-x-auto rounded-md bg-surface-900 p-3 font-mono text-[11px] text-slate-300">
            {JSON.stringify(response, null, 2)}
          </pre>
        ),
      );
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`${err.message}`);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Unknown error");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Button onClick={handleRun} loading={busy} disabled={busy || !apiKey}>
          {busy ? "Running…" : buttonLabel}
        </Button>
        {success ? (
          <div className="rounded-md border border-accent-green/40 bg-accent-green/5 px-3 py-2 text-xs text-slate-200">
            {success}
          </div>
        ) : null}
        {error ? (
          <div className="rounded-md border border-accent-red/40 bg-accent-red/5 px-3 py-2 text-xs text-accent-red">
            {error}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
