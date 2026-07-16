import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PinCollectivePoint, PinHistory, PinHistoryChannel } from "../lib/api";

// Pin-channel hindcast charts. Monthly severity (same 0-100 scale and bands as
// the live board) over full source history. Red episodes cast a gray "damage
// window" band — the documented lag between that spark firing and the pain
// landing — and the collective chart counts overlapping open windows.

const SERIES = "#38bdf8"; // single data series; status colors stay reserved
const RED = "#ef4444";
const AMBER = "#f59e0b";
const GRID = "#1e293b";
const MUTED = "#64748b";

function addMonths(ym: string, n: number): string {
  const y = parseInt(ym.slice(0, 4), 10);
  const m = parseInt(ym.slice(5, 7), 10);
  const t = y * 12 + (m - 1) + n;
  const yy = Math.floor(t / 12);
  const mm = (t % 12) + 1;
  return `${String(yy).padStart(4, "0")}-${String(mm).padStart(2, "0")}`;
}

const tooltipStyle = {
  backgroundColor: "#0f172a",
  border: "1px solid #1e293b",
  borderRadius: 6,
  fontSize: 11,
};

export function ChannelHistoryChart({ hist }: { hist: PinHistoryChannel }) {
  if (hist.series.length === 0) {
    return (
      <div className="flex h-24 items-center justify-center text-[11px] text-slate-500">
        No hindcast data for this channel yet.
      </div>
    );
  }
  // Extend the axis past the data so an open damage window is fully visible.
  const data: { date: string; score: number | null }[] = [...hist.series];
  const lastData = hist.series[hist.series.length - 1].date;
  const horizon = hist.episodes.reduce(
    (h, e) => (e.window_end > h ? e.window_end : h),
    lastData,
  );
  for (let m = addMonths(lastData, 1); m <= horizon; m = addMonths(m, 1)) {
    data.push({ date: m, score: null });
  }
  const [lagLo, lagHi] = hist.lag_months;
  return (
    <div>
      <ResponsiveContainer width="100%" height={170}>
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: MUTED, fontSize: 9 }}
            minTickGap={44}
            tickFormatter={(d: string) => d.slice(0, 4)}
          />
          <YAxis domain={[0, 100]} ticks={[0, 50, 80, 100]} width={28}
                 tick={{ fill: MUTED, fontSize: 9 }} />
          {/* damage windows: gray band cast forward from each red peak */}
          {hist.episodes.map((e, i) => (
            <ReferenceArea
              key={`w-${i}`}
              x1={e.window_start}
              x2={e.window_end}
              fill={MUTED}
              fillOpacity={0.14}
              stroke="none"
            />
          ))}
          <ReferenceLine y={50} stroke={AMBER} strokeDasharray="3 4" strokeOpacity={0.5} />
          <ReferenceLine y={80} stroke={RED} strokeDasharray="3 4" strokeOpacity={0.5} />
          <Tooltip
            contentStyle={tooltipStyle}
            labelStyle={{ color: "#cbd5e1" }}
            formatter={(v: number) => [v.toFixed(0), "severity"]}
          />
          <Line
            type="monotone"
            dataKey="score"
            stroke={SERIES}
            strokeWidth={1.5}
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
            name="severity"
          />
          {hist.episodes.map((e, i) => (
            <ReferenceDot
              key={`p-${i}`}
              x={e.peak_date}
              y={e.peak_score}
              r={3.5}
              fill={RED}
              stroke="#0f172a"
              strokeWidth={1}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <p className="mt-1 text-[10px] leading-snug text-slate-500">
        Monthly max severity, full source history.{" "}
        <span className="text-red-400">●</span> red-episode peak;{" "}
        <span className="rounded-sm bg-slate-500/20 px-1">gray band</span> = damage
        window, {lagLo}–{lagHi} months after the peak ({hist.lag_basis}).
        {hist.note ? ` ${hist.note}` : ""}
      </p>
    </div>
  );
}

function CollectiveTooltip({ active, payload, label, channelLabels }: {
  active?: boolean;
  payload?: { payload: PinCollectivePoint }[];
  label?: string;
  channelLabels: Record<string, string>;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const p = payload[0].payload;
  return (
    <div style={tooltipStyle} className="px-2.5 py-1.5 text-slate-300">
      <div className="font-mono text-slate-100">
        {label}
        {p.projected ? " (projected)" : ""}
      </div>
      <div>
        damage windows open: <span className="font-mono">{p.windows_open}</span>
      </div>
      {p.window_channels.length > 0 && (
        <div className="max-w-[220px] text-slate-400">
          {p.window_channels.map((c) => channelLabels[c] ?? c).join(", ")}
        </div>
      )}
      {p.n_red != null && (
        <div>
          channels at red: <span className="font-mono">{p.n_red}</span>
        </div>
      )}
      {p.pressure != null && (
        <div>
          board pressure: <span className="font-mono">{p.pressure.toFixed(0)}/100</span>
        </div>
      )}
    </div>
  );
}

export function CollectiveHistoryChart({ history, channelLabels }: {
  history: PinHistory;
  channelLabels: Record<string, string>;
}) {
  const series = history.collective.series;
  if (series.length === 0) {
    return (
      <div className="flex h-24 items-center justify-center text-[11px] text-slate-500">
        No collective history yet.
      </div>
    );
  }
  const firstProjected = series.find((p) => p.projected)?.date;
  return (
    <div>
      <ResponsiveContainer width="100%" height={210}>
        <ComposedChart data={series} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: MUTED, fontSize: 9 }}
            minTickGap={44}
            tickFormatter={(d: string) => d.slice(0, 4)}
          />
          <YAxis allowDecimals={false} width={28} tick={{ fill: MUTED, fontSize: 9 }} />
          {firstProjected && (
            <ReferenceArea
              x1={firstProjected}
              x2={series[series.length - 1].date}
              fill={MUTED}
              fillOpacity={0.08}
              stroke="none"
              label={{ value: "projected", fill: MUTED, fontSize: 9, position: "insideTopRight" }}
            />
          )}
          <Tooltip content={<CollectiveTooltip channelLabels={channelLabels} />} />
          <Area
            type="stepAfter"
            dataKey="windows_open"
            stroke={MUTED}
            strokeWidth={1.5}
            fill={MUTED}
            fillOpacity={0.22}
            isAnimationActive={false}
            name="damage windows open"
          />
          <Line
            type="stepAfter"
            dataKey="n_red"
            stroke={RED}
            strokeWidth={1.5}
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
            name="channels at red"
          />
        </ComposedChart>
      </ResponsiveContainer>
      <div className="mt-1 flex flex-wrap items-center gap-3 text-[10px] text-slate-500">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-3 rounded-sm bg-slate-500/40" /> damage
          windows open (count)
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-0.5 w-3 rounded bg-red-500" /> channels at
          red that month
        </span>
        <span>
          Overlap is the signal: one open window is a data point — several at once is
          a regime. The shaded right edge projects windows already cast by past reds.
        </span>
      </div>
    </div>
  );
}
