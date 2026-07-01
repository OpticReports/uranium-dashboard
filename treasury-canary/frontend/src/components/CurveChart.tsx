import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  CartesianGrid,
} from "recharts";
import type { CurveSeriesPoint } from "../lib/api";

// Reusable minimal spread line chart. Used standalone and as a building block.
export default function CurveChart({
  series,
  height = 220,
  color = "#38bdf8",
  showGrid = true,
}: {
  series: CurveSeriesPoint[];
  height?: number;
  color?: string;
  showGrid?: boolean;
}) {
  if (series.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-xs text-slate-500">
        No series data.
      </div>
    );
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={series} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
        {showGrid && <CartesianGrid stroke="#1e293b" strokeDasharray="2 4" />}
        <XAxis
          dataKey="date"
          tick={{ fill: "#64748b", fontSize: 10 }}
          minTickGap={48}
          tickFormatter={(d: string) => (d ? d.slice(0, 4) : d)}
        />
        <YAxis
          tick={{ fill: "#64748b", fontSize: 10 }}
          width={44}
          tickFormatter={(v: number) => `${v.toFixed(1)}`}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "#0f172a",
            border: "1px solid #1e293b",
            borderRadius: 6,
            fontSize: 12,
          }}
          labelStyle={{ color: "#94a3b8" }}
          formatter={(v: number | string) => [`${Number(v).toFixed(2)} pp`, "Spread"]}
        />
        <ReferenceLine y={0} stroke="#64748b" strokeDasharray="3 3" />
        <Line
          type="monotone"
          dataKey="spread"
          stroke={color}
          dot={false}
          strokeWidth={1.5}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
