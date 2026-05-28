/**
 * FraudRateChart — rolling fraud rate computed client-side from the
 * recent prediction logs. Aggregates by hour bucket.
 */

"use client";

import {
  Area,
  AreaChart,
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

function hourKey(ts: string): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "?";
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${pad(d.getHours())}:00`;
}

export function FraudRateChart({ logs }: Props) {
  // Bucket by HH:00. Keeps the chart readable even if all logs land on
  // the same day. For older spreads the X axis still shows the cycle.
  const buckets = new Map<string, { total: number; fraud: number }>();
  for (const log of logs) {
    const key = hourKey(log.timestamp);
    const cur = buckets.get(key) ?? { total: 0, fraud: 0 };
    cur.total += 1;
    if (log.predicted_label === 1) cur.fraud += 1;
    buckets.set(key, cur);
  }

  const data = Array.from(buckets.entries())
    .map(([hour, agg]) => ({
      hour,
      fraudRate: agg.total > 0 ? (agg.fraud / agg.total) * 100 : 0,
      total: agg.total,
    }))
    .sort((a, b) => a.hour.localeCompare(b.hour));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={data} margin={{ top: 5, right: 8, left: -16, bottom: 0 }}>
        <defs>
          <linearGradient id="fraudFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0ea5e9" stopOpacity={0.5} />
            <stop offset="100%" stopColor="#0ea5e9" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#1f2c4a" strokeDasharray="3 3" />
        <XAxis
          dataKey="hour"
          tick={{ fontSize: 11, fill: "#94a3b8" }}
          tickLine={false}
          axisLine={{ stroke: "#1f2c4a" }}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "#94a3b8" }}
          tickLine={false}
          axisLine={{ stroke: "#1f2c4a" }}
          unit="%"
        />
        <Tooltip
          contentStyle={{
            background: "#0f1a30",
            border: "1px solid #1f2c4a",
            borderRadius: 8,
            fontSize: 12,
          }}
          labelStyle={{ color: "#cbd5e1" }}
          formatter={(v) =>
            typeof v === "number" ? `${v.toFixed(1)}%` : String(v)
          }
        />
        <Area
          type="monotone"
          dataKey="fraudRate"
          stroke="#0ea5e9"
          strokeWidth={2}
          fill="url(#fraudFill)"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
