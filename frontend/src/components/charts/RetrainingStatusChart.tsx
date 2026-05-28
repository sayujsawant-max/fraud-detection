/**
 * RetrainingStatusChart — donut showing retraining outcomes by status.
 */

"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { RetrainingStats } from "@/types";

type Props = {
  stats: RetrainingStats;
};

const COLORS: Record<string, string> = {
  promoted: "#22c55e",
  rejected: "#facc15",
  failed: "#ef4444",
  running: "#7dd3fc",
};

export function RetrainingStatusChart({ stats }: Props) {
  const data = [
    { name: "promoted", value: stats.promoted_runs },
    { name: "rejected", value: stats.rejected_runs },
    { name: "failed", value: stats.failed_runs },
  ].filter((d) => d.value > 0);

  if (data.length === 0) {
    return (
      <div className="grid h-[260px] place-items-center text-sm text-slate-400">
        No retraining runs recorded yet.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={260}>
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="name"
          innerRadius={55}
          outerRadius={85}
          paddingAngle={3}
          stroke="#0f1a30"
        >
          {data.map((entry) => (
            <Cell
              key={entry.name}
              fill={COLORS[entry.name] ?? "#64748b"}
            />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            background: "#0f1a30",
            border: "1px solid #1f2c4a",
            borderRadius: 8,
            fontSize: 12,
          }}
          labelStyle={{ color: "#cbd5e1" }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
