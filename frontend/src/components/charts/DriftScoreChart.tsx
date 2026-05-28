/**
 * DriftScoreChart — drift score over time with the configured threshold
 * line at 0.30 so the operator can see exceedances at a glance.
 */

"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { DRIFT_THRESHOLD } from "@/lib/constants";
import type { DriftReportSummary } from "@/types";

type Props = {
  reports: DriftReportSummary[];
};

export function DriftScoreChart({ reports }: Props) {
  const data = reports
    .slice()
    .sort((a, b) => a.generated_at.localeCompare(b.generated_at))
    .map((r) => ({
      timestamp: r.generated_at.slice(5, 16).replace("T", " "),
      drift_score: r.drift_score ?? 0,
    }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 5, right: 8, left: -16, bottom: 0 }}>
        <CartesianGrid stroke="#1f2c4a" strokeDasharray="3 3" />
        <XAxis
          dataKey="timestamp"
          tick={{ fontSize: 11, fill: "#94a3b8" }}
          tickLine={false}
          axisLine={{ stroke: "#1f2c4a" }}
        />
        <YAxis
          domain={[0, 1]}
          tick={{ fontSize: 11, fill: "#94a3b8" }}
          tickLine={false}
          axisLine={{ stroke: "#1f2c4a" }}
        />
        <Tooltip
          contentStyle={{
            background: "#0f1a30",
            border: "1px solid #1f2c4a",
            borderRadius: 8,
            fontSize: 12,
          }}
          labelStyle={{ color: "#cbd5e1" }}
          formatter={(v) => (typeof v === "number" ? v.toFixed(3) : String(v))}
        />
        <ReferenceLine
          y={DRIFT_THRESHOLD}
          stroke="#facc15"
          strokeDasharray="6 4"
          label={{
            value: `threshold ${DRIFT_THRESHOLD}`,
            fill: "#facc15",
            fontSize: 11,
            position: "insideTopRight",
          }}
        />
        <Line
          type="monotone"
          dataKey="drift_score"
          stroke="#7dd3fc"
          strokeWidth={2}
          dot={{ r: 3, fill: "#0ea5e9", strokeWidth: 0 }}
          activeDot={{ r: 5 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
