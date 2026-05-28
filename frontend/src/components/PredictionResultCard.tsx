/**
 * PredictionResultCard — visual presentation of one PredictionResponse.
 *
 * Renders fraud probability as a large percentage with a coloured risk
 * level + classification badge + secondary model/latency context.
 */

import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import {
  formatNumber,
  formatPercent,
  riskLevel,
  shortId,
} from "@/lib/utils";
import type { PredictionResponse } from "@/types";

type Props = {
  result: PredictionResponse;
};

export function PredictionResultCard({ result }: Props) {
  const risk = riskLevel(result.fraud_probability);
  const isFraud = result.predicted_label === 1;

  const riskTone =
    risk === "low" ? "success" : risk === "medium" ? "warning" : "danger";
  const riskAccent =
    risk === "low"
      ? "from-accent-green/30 via-accent-green/5"
      : risk === "medium"
        ? "from-accent-yellow/30 via-accent-yellow/5"
        : "from-accent-red/40 via-accent-red/5";

  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <CardTitle>Prediction Result</CardTitle>
      </CardHeader>
      <CardContent className="px-0 py-0">
        <div
          className={`relative bg-gradient-to-br ${riskAccent} to-transparent px-6 py-8`}
        >
          <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-[11px] font-medium uppercase tracking-[0.2em] text-slate-400">
                Fraud Probability
              </div>
              <div className="mt-1 flex items-baseline gap-3">
                <span className="text-5xl font-semibold text-slate-100 sm:text-6xl">
                  {formatPercent(result.fraud_probability, 1)}
                </span>
                <Badge tone={riskTone}>{risk.toUpperCase()} RISK</Badge>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {isFraud ? (
                  <Badge tone="danger">⚠ FRAUD</Badge>
                ) : (
                  <Badge tone="success">✓ LEGITIMATE</Badge>
                )}
                <span className="text-xs text-slate-400">
                  decision at threshold {formatNumber(result.threshold_used, 4)}
                </span>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs md:max-w-sm">
              <Info label="Model" value={result.model_name} />
              <Info label="Version" value={`v${result.model_version}`} />
              <Info label="Stage" value={result.model_stage} />
              <Info label="Latency" value={`${formatNumber(result.latency_ms, 1)} ms`} />
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 border-t border-surface-border/60 px-6 py-4 sm:grid-cols-3">
          <Info label="Transaction ID" value={shortId(result.transaction_id, 14)} mono />
          <Info label="Timestamp" value={new Date(result.timestamp).toISOString()} mono />
          <Info
            label="Decision"
            value={
              <span className={isFraud ? "text-accent-red" : "text-accent-green"}>
                {isFraud ? "BLOCK" : "ALLOW"}
              </span>
            }
          />
        </div>
      </CardContent>
    </Card>
  );
}

function Info({
  label,
  value,
  mono,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
        {label}
      </span>
      <span
        className={`text-sm text-slate-200 ${mono ? "font-mono text-xs" : ""}`}
      >
        {value}
      </span>
    </div>
  );
}
