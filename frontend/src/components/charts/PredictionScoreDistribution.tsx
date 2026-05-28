/**
 * PredictionScoreDistribution — bucketed histogram of fraud probability.
 *
 * Bins the (client-side) recent prediction logs into 10 deciles so the
 * Overview page shows a quick "is the model committing or hedging?"
 * histogram without needing a new backend endpoint.
 */

"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PredictionLogSummary } from "@/types";

type Props = {
  logs: PredictionLogSummary[];
};

const BUCKET_EDGES = [
  0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.01,
] as const;

function bucketLabel(lo: number, hi: number): string {
  return `${Math.round(lo * 100)}-${Math.round(hi * 100)}%`;
}

export function PredictionScoreDistribution({ logs }: Props) {
  const data = BUCKET_EDGES.slice(0, -1).map((lo, idx) => {
    const hi = BUCKET_EDGES[idx + 1];
    const count = logs.filter(
      (l) => l.fraud_probability >= lo && l.fraud_probability < hi,
    ).length;
    return { bucket: bucketLabel(lo, hi), count };
  });

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 5, right: 8, left: -16, bottom: 0 }}>
        <CartesianGrid stroke="#1f2c4a" strokeDasharray="3 3" />
        <XAxis
          dataKey="bucket"
          tick={{ fontSize: 11, fill: "#94a3b8" }}
          tickLine={false}
          axisLine={{ stroke: "#1f2c4a" }}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "#94a3b8" }}
          tickLine={false}
          axisLine={{ stroke: "#1f2c4a" }}
          allowDecimals={false}
        />
        <Tooltip
          contentStyle={{
            background: "#0f1a30",
            border: "1px solid #1f2c4a",
            borderRadius: 8,
            fontSize: 12,
          }}
          labelStyle={{ color: "#cbd5e1" }}
          cursor={{ fill: "#1f2c4a55" }}
        />
        <Bar dataKey="count" fill="#0ea5e9" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
