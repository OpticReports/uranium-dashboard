import { useEffect, useState } from "react";
import type { Composite, RecessionProb } from "../lib/api";
import { api } from "../lib/api";
import { Panel, InlineError } from "./ui";
import { errorMessage } from "../lib/format";

const BAND_COLOR: Record<string, string> = {
  LOW: "#10b981",
  ELEVATED: "#f59e0b",
  HIGH: "#ef4444",
  SEVERE: "#dc2626",
  NO_DATA: "#6b7280",
};

function scoreColor(score: number): string {
  if (score < 25) return "#10b981";
  if (score < 50) return "#f59e0b";
  if (score < 75) return "#ef4444";
  return "#dc2626";
}

// Semicircular gauge (SVG). Score 0..100.
function Gauge({ score, band }: { score: number | null; band: string }) {
  const R = 90;
  const cx = 110;
  const cy = 110;
  const clamped = score === null ? 0 : Math.max(0, Math.min(100, score));
  // Semicircle from 180deg (left) to 0deg (right).
  const angle = Math.PI * (1 - clamped / 100);
  const nx = cx + R * Math.cos(angle);
  const ny = cy - R * Math.sin(angle);
  const trackPath = `M ${cx - R} ${cy} A ${R} ${R} 0 0 1 ${cx + R} ${cy}`;
  const color = score === null ? "#6b7280" : scoreColor(clamped);

  // Arc up to the score value.
  const large = clamped > 50 ? 0 : 0; // semicircle never exceeds 180
  const valuePath = `M ${cx - R} ${cy} A ${R} ${R} 0 ${large} 1 ${nx} ${ny}`;

  return (
    <svg viewBox="0 0 220 130" className="w-full max-w-[260px]">
      <path
        d={trackPath}
        fill="none"
        stroke="#1e293b"
        strokeWidth={16}
        strokeLinecap="round"
      />
      {score !== null && (
        <path
          d={valuePath}
          fill="none"
          stroke={color}
          strokeWidth={16}
          strokeLinecap="round"
        />
      )}
      <text
        x={cx}
        y={cy - 12}
        textAnchor="middle"
        className="font-mono"
        fontSize="34"
        fill={color}
        fontWeight={700}
      >
        {score === null ? "—" : Math.round(clamped)}
      </text>
      <text
        x={cx}
        y={cy + 10}
        textAnchor="middle"
        fontSize="11"
        fill="#94a3b8"
        style={{ textTransform: "uppercase", letterSpacing: "0.08em" }}
      >
        {band}
      </text>
    </svg>
  );
}

function ContributionBar({
  category,
  value,
  max,
}: {
  category: string;
  value: number;
  max: number;
}) {
  const pct = max > 0 ? (Math.abs(value) / max) * 100 : 0;
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-6 font-mono text-slate-400">{category}</span>
      <div className="h-2 flex-1 overflow-hidden rounded bg-slate-800">
        <div
          className="h-full rounded"
          style={{
            width: `${pct}%`,
            backgroundColor: scoreColor(Math.min(100, Math.abs(value) * 2)),
          }}
        />
      </div>
      <span className="w-12 text-right font-mono text-slate-300">
        {value.toFixed(1)}
      </span>
    </div>
  );
}

export default function StressGauge({
  composite,
}: {
  composite: Composite | null;
}) {
  const [recession, setRecession] = useState<RecessionProb | null>(null);
  const [recError, setRecError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .recessionProb()
      .then((r) => {
        if (alive) setRecession(r);
      })
      .catch((e) => {
        if (alive) setRecError(errorMessage(e));
      });
    return () => {
      alive = false;
    };
  }, []);

  const contributions = composite?.contributions ?? {};
  const contribEntries = Object.entries(contributions).sort(
    (a, b) => Math.abs(b[1]) - Math.abs(a[1]),
  );
  const maxContrib = contribEntries.reduce(
    (m, [, v]) => Math.max(m, Math.abs(v)),
    0,
  );

  const band = composite?.band ?? "NO_DATA";
  const coverage = composite?.coverage ?? 0;
  const coveragePct = coverage <= 1 ? coverage * 100 : coverage;

  return (
    <Panel
      title="Composite Stress"
      subtitle="Aggregate market-stress index across nine metric families"
    >
      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        {/* Gauge + band */}
        <div className="flex flex-col items-center justify-center">
          <Gauge score={composite?.score ?? null} band={band} />
          <div className="mt-2 flex items-center gap-2">
            <span
              className="rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide"
              style={{
                color: BAND_COLOR[band] ?? "#6b7280",
                backgroundColor: `${BAND_COLOR[band] ?? "#6b7280"}18`,
              }}
            >
              {band === "NO_DATA" ? "No data" : band}
            </span>
          </div>
          <p className="mt-1 text-[11px] text-slate-500">0 = calm · 100 = severe</p>
        </div>

        {/* Key readouts */}
        <div className="flex flex-col justify-center gap-3">
          <Readout label="Coverage" value={`${coveragePct.toFixed(0)}%`} />
          <Readout
            label="Recession prob. (Estrella–Mishkin)"
            value={
              recError
                ? "err"
                : recession?.probability_pct === null ||
                    recession?.probability_pct === undefined
                  ? "n/a"
                  : `${recession.probability_pct.toFixed(1)}%`
            }
            hint={recession?.model}
          />
          <div className="flex gap-3">
            <CountPill
              label="RED"
              count={composite?.n_red ?? 0}
              color="#ef4444"
            />
            <CountPill
              label="CRITICAL"
              count={composite?.n_critical ?? 0}
              color="#dc2626"
              pulse
            />
          </div>
        </div>

        {/* Contributions */}
        <div className="flex flex-col justify-center">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Component contributions
          </p>
          {contribEntries.length === 0 ? (
            <p className="text-xs text-slate-500">No contribution data.</p>
          ) : (
            <div className="flex flex-col gap-1.5">
              {contribEntries.map(([cat, val]) => (
                <ContributionBar
                  key={cat}
                  category={cat}
                  value={val}
                  max={maxContrib}
                />
              ))}
            </div>
          )}
        </div>
      </div>
      {recError && (
        <div className="mt-3">
          <InlineError message={`Recession model: ${recError}`} />
        </div>
      )}
    </Panel>
  );
}

function Readout({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <p className="font-mono text-xl text-slate-100">{value}</p>
      {hint && <p className="text-[10px] text-slate-600">{hint}</p>}
    </div>
  );
}

function CountPill({
  label,
  count,
  color,
  pulse = false,
}: {
  label: string;
  count: number;
  color: string;
  pulse?: boolean;
}) {
  return (
    <div
      className={`flex flex-col items-center rounded border px-3 py-1.5 ${
        pulse && count > 0 ? "animate-pulse" : ""
      }`}
      style={{ borderColor: `${color}55`, backgroundColor: `${color}12` }}
    >
      <span className="font-mono text-lg" style={{ color }}>
        {count}
      </span>
      <span className="text-[9px] uppercase tracking-wide" style={{ color }}>
        {label}
      </span>
    </div>
  );
}
