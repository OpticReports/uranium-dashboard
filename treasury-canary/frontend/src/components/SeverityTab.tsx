import { useEffect, useMemo, useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  CartesianGrid,
  Legend,
} from "recharts";
import type { SeverityBlock, SeverityIndex } from "../lib/api";
import { api } from "../lib/api";
import { IMPACT_DATA } from "../lib/severityImpact";
import { Panel, InlineError, Loading } from "./ui";
import { errorMessage, formatValue } from "../lib/format";
import InfoTip from "./InfoTip";

// ---------------------------------------------------------------------------
// Loosened view of the generated `as const` impact data so we can index
// dynamically without fighting literal types.
// ---------------------------------------------------------------------------

interface PathPoint {
  m: number;
  v: number;
}

interface ImpactType {
  label: string;
  episodes: Array<Record<string, string | number | null>>;
  aggregate: Record<string, { median: number | null; values: Array<number | null> }>;
  paths: { eq_path: PathPoint[]; hpi_path: PathPoint[] };
}

interface ImpactShape {
  generated: string;
  types: Record<string, ImpactType>;
  meta: {
    equities: string;
    housing: string;
    treasury: string;
    classification: Record<string, string>;
  };
}

const IMPACT = IMPACT_DATA as unknown as ImpactShape;

// Display order for the impact map (all keys present in IMPACT_DATA.types).
const IMPACT_TYPE_ORDER = [
  "household_leverage",
  "valuation_corporate",
  "inflation_rates",
  "exogenous",
];

// Display order + labels for the composition chips (the /severity typology).
const COMPOSITION_TYPES: Array<{ key: string; label: string }> = [
  { key: "household_leverage", label: "Household / leverage" },
  { key: "valuation_corporate", label: "Valuation / corporate" },
  { key: "inflation_rates", label: "Inflation / rates" },
  { key: "fiscal_constrained", label: "Fiscal-constrained" },
];

// ---------------------------------------------------------------------------
// Formatting / color helpers
// ---------------------------------------------------------------------------

const SLATE = "#64748b";

// Score color ladder. Normal semantics: low score = mild (emerald). Block E
// (dampeners) is inverted: a HIGH dampener score means MORE cushioning = milder.
function scoreColor(score: number | null | undefined, inverted = false): string {
  if (score === null || score === undefined || Number.isNaN(score)) return SLATE;
  if (inverted) {
    if (score >= 60) return "#10b981";
    if (score >= 35) return "#f59e0b";
    return "#ef4444";
  }
  if (score < 35) return "#10b981";
  if (score < 60) return "#f59e0b";
  return "#ef4444";
}

const CLASS_COLOR: Record<string, string> = {
  MILD: "#10b981",
  MODERATE: "#f59e0b",
  SEVERE: "#ef4444",
};

function fmtNum(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "n/a";
  return v.toFixed(digits);
}

function fmtSignedPct(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "n/a";
  return `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
}

function fmtSignedAdj(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "n/a";
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}`;
}

function fmtMonths(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "n/a";
  return `${v.toFixed(0)} mo`;
}

function fmtPp(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "n/a";
  return `${v > 0 ? "+" : ""}${v.toFixed(1)} pp`;
}

// Sign color for market outcomes (positive = green, negative = red).
function signColorClass(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "text-slate-500";
  if (v > 0) return "text-emerald-400";
  if (v < 0) return "text-red-400";
  return "text-slate-300";
}

function aggMedian(t: ImpactType | undefined, key: string): number | null {
  const cell = t?.aggregate?.[String(key)];
  return cell && typeof cell.median === "number" ? cell.median : null;
}

function epNum(
  ep: Record<string, string | number | null>,
  key: string,
): number | null {
  const v = ep[String(key)];
  return typeof v === "number" && !Number.isNaN(v) ? v : null;
}

// ---------------------------------------------------------------------------
// Main tab
// ---------------------------------------------------------------------------

export default function SeverityTab() {
  const [data, setData] = useState<SeverityIndex | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .severity()
      .then((d) => {
        if (alive) {
          setData(d);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (alive) {
          setError(errorMessage(e));
          setLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="flex flex-col gap-5">
      {loading && <Loading label="Loading severity index…" />}
      {!loading && error && (
        <InlineError message={`Failed to load /severity: ${error}`} />
      )}

      {!loading && !error && data && (
        <>
          <SeverityHeader data={data} />
          {data.blocks.map((b) => (
            <BlockPanel key={b.id} block={b} />
          ))}
          <TranslationPanel data={data} />
        </>
      )}

      <ImpactMapPanel />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section 1 — the index
// ---------------------------------------------------------------------------

function SeverityHeader({ data }: { data: SeverityIndex }) {
  const cls = data.severity_class;
  const color = cls ? CLASS_COLOR[cls] ?? SLATE : SLATE;
  const { formula } = data;

  return (
    <Panel
      title={
        <>
          Severity index — how bad would it be?
          <InfoTip term="severity_index" />
        </>
      }
      subtitle="Conditional severity: if a recession starts from today's conditions, how hard does it hit?"
    >
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2">
        <span
          className="font-mono text-4xl font-bold tabular-nums"
          style={{ color }}
        >
          {data.severity_score === null ? "n/a" : data.severity_score.toFixed(0)}
        </span>
        <span
          className="text-sm font-bold uppercase tracking-wide"
          style={{ color }}
        >
          {cls ?? "no class"}
        </span>
        <span className="text-[10px] text-slate-500">/ 100</span>
      </div>

      {formula.text && (
        <p className="mt-2 font-mono text-[11px] text-slate-500">
          {formula.text}
        </p>
      )}

      <p className="mt-1.5 text-xs text-slate-400">
        base{" "}
        <span className="font-mono text-slate-300">
          {fmtNum(formula.base_amplifiers)}
        </span>{" "}
        · policy-space{" "}
        <span className="font-mono text-slate-300">
          {fmtSignedAdj(formula.policy_space_adj)}
        </span>{" "}
        · dampeners{" "}
        <span className="font-mono text-slate-300">
          {fmtSignedAdj(formula.dampener_adj)}
        </span>
      </p>

      {data.note && (
        <p className="mt-3 rounded border border-panelborder bg-slate-900/50 px-3 py-2 text-[11px] leading-relaxed text-slate-400">
          {data.note}
        </p>
      )}
    </Panel>
  );
}

function BlockPanel({ block }: { block: SeverityBlock }) {
  // Block E (dampeners) has inverted semantics: high score = MORE dampening = milder.
  const inverted = block.id.toLowerCase() === "e";
  const pillColor = scoreColor(block.score, inverted);

  return (
    <Panel
      title={
        <>
          {block.label}
          <InfoTip term={`sev_block_${block.id.toLowerCase()}`} />
          {inverted && (
            <span className="ml-2 text-[10px] font-normal normal-case tracking-normal text-slate-500">
              (high = milder)
            </span>
          )}
        </>
      }
      right={
        <span
          className="inline-flex items-center rounded-full border px-2.5 py-0.5 font-mono text-xs font-semibold tabular-nums"
          style={{
            borderColor: `${pillColor}55`,
            color: pillColor,
            backgroundColor: `${pillColor}14`,
          }}
        >
          {block.score === null ? "n/a" : block.score.toFixed(0)}
        </span>
      }
    >
      <div className="flex flex-col gap-2.5">
        {block.components.map((c) => {
          const barColor = scoreColor(c.score, inverted);
          const width =
            c.score === null ? 0 : Math.max(0, Math.min(100, c.score));
          return (
            <div key={c.id}>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="w-48 shrink-0 text-xs text-slate-300">
                  {c.label}
                </span>
                <span className="w-24 shrink-0 text-right font-mono text-xs text-slate-200">
                  {formatValue(c.value, c.unit)}
                </span>
                <span className="h-2 min-w-[80px] flex-1 overflow-hidden rounded-full bg-slate-800">
                  <span
                    className="block h-full rounded-full"
                    style={{ width: `${width}%`, backgroundColor: barColor }}
                  />
                </span>
                <span
                  className="w-8 shrink-0 text-right font-mono text-xs tabular-nums"
                  style={{ color: barColor }}
                >
                  {c.score === null ? "n/a" : c.score.toFixed(0)}
                </span>
              </div>
              {c.note && (
                <p className="mt-0.5 pl-0 text-[10px] leading-relaxed text-slate-500">
                  {c.note}
                </p>
              )}
            </div>
          );
        })}
        {block.components.length === 0 && (
          <p className="text-xs text-slate-500">No components reported.</p>
        )}
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Section 2 — Today's translation (bridges the index to the impact map)
// ---------------------------------------------------------------------------

function TranslationPanel({ data }: { data: SeverityIndex }) {
  const { type_scores, matched_type } = data.composition;
  const matched = matched_type ? IMPACT.types?.[String(matched_type)] : undefined;
  const isFiscal = matched_type === "fiscal_constrained";
  const analog = isFiscal ? IMPACT.types?.["inflation_rates"] : undefined;

  return (
    <Panel
      title={
        <>
          Today's translation
          <InfoTip term="todays_translation" />
        </>
      }
      subtitle="Which historical recession type does today's imbalance mix most resemble?"
    >
      {/* Composition chips */}
      <div className="flex flex-wrap gap-2">
        {COMPOSITION_TYPES.map((t) => {
          const score = type_scores?.[String(t.key)] ?? null;
          const isMatch = matched_type === t.key;
          return (
            <span
              key={t.key}
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs ${
                isMatch
                  ? "border-sky-500 bg-sky-500/10 text-sky-200"
                  : "border-panelborder bg-slate-900/50 text-slate-400"
              }`}
            >
              {t.label}
              <span className="font-mono font-semibold tabular-nums">
                {score === null || score === undefined || Number.isNaN(score)
                  ? "n/a"
                  : score.toFixed(0)}
              </span>
            </span>
          );
        })}
      </div>

      {/* Matched pattern summary */}
      {matched_type === null && (
        <p className="mt-3 text-xs text-slate-500">
          No matched historical pattern — composition scores unavailable or
          inconclusive.
        </p>
      )}

      {matched_type !== null && matched && (
        <div className="mt-3">
          <p className="text-xs font-semibold text-slate-200">
            Matched historical pattern:{" "}
            <span className="text-sky-300">{matched.label}</span>
          </p>
          <MedianSummaryLine t={matched} />
        </div>
      )}

      {isFiscal && analog && (
        <div className="mt-3">
          <p className="text-xs font-semibold text-slate-200">
            Nearest analog:{" "}
            <span className="text-sky-300">{analog.label}</span>{" "}
            <span className="font-normal text-slate-500">
              (fiscal-constrained has no direct U.S. sample)
            </span>
          </p>
          <MedianSummaryLine t={analog} />
          <div className="mt-2 rounded border-l-4 border-amber-500/70 bg-amber-500/5 px-3 py-2.5">
            <p className="text-xs leading-relaxed text-amber-100/90">
              Fiscal-constrained has thin U.S. precedent — nearest analogs are
              the 1970s: equity de-rating via multiple compression, housing
              holds nominally but falls in real terms, duration fails as the
              hedge. Analog-based, not sample-based.
            </p>
          </div>
        </div>
      )}

      {matched_type !== null && !matched && !isFiscal && (
        <p className="mt-3 text-xs text-slate-500">
          Matched type{" "}
          <span className="font-mono text-slate-400">{matched_type}</span> has
          no row in the historical impact study.
        </p>
      )}
    </Panel>
  );
}

function MedianSummaryLine({ t }: { t: ImpactType }) {
  return (
    <p className="mt-1 text-xs leading-relaxed text-slate-400">
      Median outcomes: equities{" "}
      <span className={`font-mono ${signColorClass(aggMedian(t, "equity_dd"))}`}>
        {fmtSignedPct(aggMedian(t, "equity_dd"))}
      </span>{" "}
      (trough {fmtMonths(aggMedian(t, "equity_tt_mo"))}, recover{" "}
      {fmtMonths(aggMedian(t, "equity_rec_mo"))}) · housing nominal{" "}
      <span
        className={`font-mono ${signColorClass(aggMedian(t, "housing_nom_dd"))}`}
      >
        {fmtSignedPct(aggMedian(t, "housing_nom_dd"))}
      </span>{" "}
      / real{" "}
      <span
        className={`font-mono ${signColorClass(aggMedian(t, "housing_real_dd"))}`}
      >
        {fmtSignedPct(aggMedian(t, "housing_real_dd"))}
      </span>{" "}
      · 10y TR{" "}
      <span className={`font-mono ${signColorClass(aggMedian(t, "tsy_12m"))}`}>
        {fmtSignedPct(aggMedian(t, "tsy_12m"))}
      </span>{" "}
      /12m,{" "}
      <span className={`font-mono ${signColorClass(aggMedian(t, "tsy_24m"))}`}>
        {fmtSignedPct(aggMedian(t, "tsy_24m"))}
      </span>{" "}
      /24m · unemployment{" "}
      <span className="font-mono text-slate-300">
        {fmtPp(aggMedian(t, "unemp_rise_pp"))}
      </span>
      .
    </p>
  );
}

// ---------------------------------------------------------------------------
// Section 3 — the Impact Map
// ---------------------------------------------------------------------------

const EPISODE_COLS: Array<{ key: string; label: string; fmt: (v: number | null) => string; sign?: boolean }> = [
  { key: "equity_dd", label: "Eq dd", fmt: fmtSignedPct, sign: true },
  { key: "equity_tt_mo", label: "Eq trough", fmt: fmtMonths },
  { key: "equity_rec_mo", label: "Eq recover", fmt: fmtMonths },
  { key: "housing_nom_dd", label: "Hsg nom dd", fmt: fmtSignedPct, sign: true },
  { key: "housing_nom_tt_mo", label: "Hsg trough", fmt: fmtMonths },
  { key: "housing_nom_rec_mo", label: "Hsg recover", fmt: fmtMonths },
  { key: "housing_real_dd", label: "Hsg real dd", fmt: fmtSignedPct, sign: true },
  { key: "housing_real_tt_mo", label: "Real trough", fmt: fmtMonths },
  { key: "tsy_12m", label: "10y 12m", fmt: fmtSignedPct, sign: true },
  { key: "tsy_24m", label: "10y 24m", fmt: fmtSignedPct, sign: true },
  { key: "unemp_rise_pp", label: "U rise", fmt: fmtPp },
];

function ImpactMapPanel() {
  return (
    <Panel
      title={
        <>
          Impact map — what each recession type did to markets
          <InfoTip term="impact_map" />
        </>
      }
      subtitle={`Event study around recession onsets · generated ${IMPACT.generated}`}
    >
      <div className="flex flex-col gap-4">
        {IMPACT_TYPE_ORDER.map((key) => {
          const t = IMPACT.types?.[String(key)];
          if (!t) return null;
          return <ImpactTypeCard key={key} typeKey={key} t={t} />;
        })}
      </div>

      <div className="mt-4 space-y-0.5 text-[10px] leading-relaxed text-slate-600">
        <p>Equities: {IMPACT.meta.equities}</p>
        <p>Housing: {IMPACT.meta.housing}</p>
        <p>Treasury: {IMPACT.meta.treasury}</p>
        <p className="pt-1 font-semibold text-slate-500">
          Medians across 1–6 episodes per type — priors, not laws.
        </p>
      </div>
    </Panel>
  );
}

function ImpactTypeCard({ typeKey, t }: { typeKey: string; t: ImpactType }) {
  const onsets = t.episodes.map((ep) => String(ep.onset ?? "?")).join(", ");

  return (
    <div className="rounded-lg border border-panelborder bg-slate-900/40 p-4">
      {/* (a) header */}
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 className="text-sm font-semibold text-slate-200">{t.label}</h3>
        <span className="font-mono text-[10px] text-slate-500">
          onsets: {onsets || "—"}
        </span>
      </div>

      {/* (b) stat grid of aggregate medians */}
      <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3 lg:grid-cols-5">
        <Stat
          label="Equities dd"
          value={fmtSignedPct(aggMedian(t, "equity_dd"))}
          colorClass={signColorClass(aggMedian(t, "equity_dd"))}
        />
        <Stat
          label="Eq trough / recover"
          value={`${fmtMonths(aggMedian(t, "equity_tt_mo"))} / ${fmtMonths(aggMedian(t, "equity_rec_mo"))}`}
        />
        <Stat
          label="Housing nominal dd"
          value={fmtSignedPct(aggMedian(t, "housing_nom_dd"))}
          colorClass={signColorClass(aggMedian(t, "housing_nom_dd"))}
          sub={`trough ${fmtMonths(aggMedian(t, "housing_nom_tt_mo"))}`}
        />
        <Stat
          label="Housing real dd"
          value={fmtSignedPct(aggMedian(t, "housing_real_dd"))}
          colorClass={signColorClass(aggMedian(t, "housing_real_dd"))}
        />
        <Stat
          label="10y TR 12m / 24m"
          value={`${fmtSignedPct(aggMedian(t, "tsy_12m"))} / ${fmtSignedPct(aggMedian(t, "tsy_24m"))}`}
          colorClass={signColorClass(aggMedian(t, "tsy_12m"))}
        />
        <Stat
          label="Unemployment"
          value={fmtPp(aggMedian(t, "unemp_rise_pp"))}
        />
      </div>

      {/* (c) episodes detail */}
      <details className="mt-3 rounded border border-panelborder bg-slate-950/40 px-3 py-2">
        <summary className="cursor-pointer text-xs font-semibold text-slate-400 hover:text-sky-300">
          Episodes ({t.episodes.length})
        </summary>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-[11px]">
            <thead>
              <tr className="border-b border-panelborder text-[10px] uppercase tracking-wide text-slate-500">
                <th className="py-1.5 pr-3 font-semibold">Onset</th>
                {EPISODE_COLS.map((c) => (
                  <th key={c.key} className="px-2 py-1.5 text-right font-semibold">
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {t.episodes.map((ep, i) => (
                <tr
                  key={`${String(ep.onset ?? i)}`}
                  className="border-b border-panelborder/50 last:border-0"
                >
                  <td className="py-1.5 pr-3 font-mono text-slate-300">
                    {String(ep.onset ?? "?")}
                  </td>
                  {EPISODE_COLS.map((c) => {
                    const v = epNum(ep, c.key);
                    return (
                      <td
                        key={c.key}
                        className={`px-2 py-1.5 text-right font-mono ${
                          c.sign ? signColorClass(v) : "text-slate-400"
                        }`}
                      >
                        {c.fmt(v)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      {/* (d) indexed path chart */}
      <PathChart typeKey={typeKey} t={t} />
    </div>
  );
}

function Stat({
  label,
  value,
  colorClass = "text-slate-200",
  sub,
}: {
  label: string;
  value: string;
  colorClass?: string;
  sub?: string;
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className={`font-mono text-xs font-semibold ${colorClass}`}>
        {value}
        {sub && (
          <span className="ml-1 font-normal text-slate-500">({sub})</span>
        )}
      </div>
    </div>
  );
}

interface PathRow {
  m: number;
  eq?: number;
  hpi?: number;
}

function PathChart({ typeKey, t }: { typeKey: string; t: ImpactType }) {
  const rows: PathRow[] = useMemo(() => {
    const byMonth = new Map<number, PathRow>();
    for (const p of t.paths?.eq_path ?? []) {
      byMonth.set(p.m, { m: p.m, eq: p.v });
    }
    for (const p of t.paths?.hpi_path ?? []) {
      const row = byMonth.get(p.m);
      if (row) row.hpi = p.v;
      else byMonth.set(p.m, { m: p.m, hpi: p.v });
    }
    return [...byMonth.values()].sort((a, b) => a.m - b.m);
  }, [t]);

  if (rows.length === 0) return null;
  const hasHousing = rows.some((r) => r.hpi !== undefined);

  return (
    <div className="mt-3">
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={rows} margin={{ top: 6, right: 16, bottom: 2, left: 0 }}>
          <CartesianGrid stroke="#1e293b" strokeDasharray="2 4" />
          <XAxis
            dataKey="m"
            type="number"
            domain={["dataMin", "dataMax"]}
            tick={{ fill: "#64748b", fontSize: 10 }}
            tickFormatter={(m: number) => `${m > 0 ? "+" : ""}${m}m`}
            minTickGap={30}
          />
          <YAxis
            tick={{ fill: "#64748b", fontSize: 10 }}
            width={40}
            domain={["auto", "auto"]}
            tickFormatter={(v: number) => v.toFixed(0)}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#0f172a",
              border: "1px solid #1e293b",
              borderRadius: 6,
              fontSize: 12,
            }}
            labelFormatter={(m: number | string) => `month ${m} from onset`}
            formatter={(value: number | string, name: string) => [
              Number(value).toFixed(1),
              name,
            ]}
          />
          <ReferenceLine
            x={0}
            stroke="#94a3b8"
            strokeDasharray="4 3"
            label={{
              value: "onset",
              position: "insideTopLeft",
              fill: "#94a3b8",
              fontSize: 10,
            }}
          />
          <ReferenceLine y={100} stroke="#334155" strokeDasharray="4 3" />
          <Legend
            wrapperStyle={{ fontSize: 10, color: "#64748b" }}
            iconSize={8}
          />
          <Line
            type="monotone"
            dataKey="eq"
            name="Equities (indexed 100 at onset)"
            stroke="#38bdf8"
            dot={false}
            strokeWidth={1.6}
            isAnimationActive={false}
            connectNulls
          />
          {hasHousing && (
            <Line
              type="monotone"
              dataKey="hpi"
              name="Housing (FHFA)"
              stroke="#f59e0b"
              dot={false}
              strokeWidth={1.6}
              isAnimationActive={false}
              connectNulls
            />
          )}
        </LineChart>
      </ResponsiveContainer>
      {!hasHousing && (
        <p className="mt-0.5 px-1 text-[10px] text-slate-600">
          No housing path for {typeKey} — episodes pre-date the FHFA series
          (1975+).
        </p>
      )}
    </div>
  );
}
