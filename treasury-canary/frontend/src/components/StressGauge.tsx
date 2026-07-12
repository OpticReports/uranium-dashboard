import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { Composite, HorizonStat, RecessionModel } from "../lib/api";
import { api } from "../lib/api";
import { Panel, InlineError } from "./ui";
import { errorMessage } from "../lib/format";
import InfoTip from "./InfoTip";

const HORIZONS = [6, 12, 18, 24] as const;

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
  const [recModel, setRecModel] = useState<RecessionModel | null>(null);
  const [recError, setRecError] = useState<string | null>(null);
  const [horizon, setHorizon] = useState<number>(12);

  useEffect(() => {
    let alive = true;
    api
      .recessionModel()
      .then((r) => {
        if (!alive) return;
        setRecModel(r);
        if (r.default_horizon) setHorizon(r.default_horizon);
      })
      .catch((e) => {
        if (alive) setRecError(errorMessage(e));
      });
    return () => {
      alive = false;
    };
  }, []);

  const horizonStat: HorizonStat | null = useMemo(() => {
    if (!recModel) return null;
    return recModel.horizons[String(horizon)] ?? null;
  }, [recModel, horizon]);

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
      title={
        <>
          Composite Stress
          <InfoTip term="composite_score" />
        </>
      }
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
          <Readout
            label={
              <>
                Coverage
                <InfoTip term="coverage" />
              </>
            }
            value={`${coveragePct.toFixed(0)}%`}
          />
          <RecessionDial
            model={recModel}
            stat={horizonStat}
            horizon={horizon}
            onSelect={setHorizon}
            error={recError}
          />
          <div className="flex items-center gap-3">
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
            <InfoTip term="status_lights" />
          </div>
        </div>

        {/* Contributions */}
        <div className="flex flex-col justify-center">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Component contributions
            <InfoTip term="contributions" />
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

function fmtPct(v: number | null | undefined, digits = 1): string {
  return v === null || v === undefined || Number.isNaN(v)
    ? "n/a"
    : `${v.toFixed(digits)}%`;
}

function RecessionDial({
  model,
  stat,
  horizon,
  onSelect,
  error,
}: {
  model: RecessionModel | null;
  stat: HorizonStat | null;
  horizon: number;
  onSelect: (h: number) => void;
  error: string | null;
}) {
  const prob = stat?.probability_pct ?? null;
  const hasProb = prob !== null && prob !== undefined && !Number.isNaN(prob);

  // Context line: band + AUC + n.
  const band =
    stat &&
    stat.ci_low_pct !== null &&
    stat.ci_high_pct !== null &&
    !Number.isNaN(stat.ci_low_pct) &&
    !Number.isNaN(stat.ci_high_pct)
      ? `band ${Math.round(stat.ci_low_pct)}–${Math.round(stat.ci_high_pct)}%`
      : null;
  const auc =
    stat && stat.auc !== null && !Number.isNaN(stat.auc)
      ? `AUC ${stat.auc.toFixed(2)} (n=${stat.n_obs})`
      : null;
  const hasContext = band !== null || auc !== null;

  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] uppercase tracking-wide text-slate-500">
          Recession prob. · {horizon}mo
          <InfoTip term="recession_prob" />
        </p>
        <div className="flex items-center gap-1">
          {HORIZONS.map((h) => (
            <button
              key={h}
              onClick={() => onSelect(h)}
              className={`rounded border px-1.5 py-0.5 text-[10px] font-mono transition-colors ${
                h === horizon
                  ? "border-sky-500 bg-sky-500/15 text-sky-300"
                  : "border-panelborder text-slate-400 hover:text-slate-200"
              }`}
            >
              {h}
            </button>
          ))}
          <InfoTip term="horizon" />
        </div>
      </div>
      <p className="font-mono text-xl text-slate-100">
        {error ? "err" : !model ? "…" : hasProb ? fmtPct(prob) : "n/a"}
      </p>
      {hasContext ? (
        <p className="text-[10px] text-slate-500">
          {band !== null && (
            <span>
              {band}
              <InfoTip term="confidence_band" />
            </span>
          )}
          {band !== null && auc !== null && <span>{"  ·  "}</span>}
          {auc !== null && (
            <span>
              {auc}
              <InfoTip term="auc" />
            </span>
          )}
        </p>
      ) : (
        <p className="text-[10px] text-slate-600">
          {model?.method ?? "Estrella–Mishkin probit"}
        </p>
      )}
      <p className="mt-1 text-[10px] leading-snug text-slate-600">
        Model estimate with a confidence band, not a forecast. Curve predictive
        power peaks ~12–18mo.
      </p>
    </div>
  );
}

function Readout({
  label,
  value,
  hint,
}: {
  label: ReactNode;
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
