import { useEffect, useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ShockAsset, ShockCalibration, ShockRun } from "../lib/api";
import { api } from "../lib/api";
import { errorMessage } from "../lib/format";
import InfoTip from "./InfoTip";
import { InlineError, Loading, Panel } from "./ui";

const ASSET_COLORS: Record<ShockAsset, string> = {
  SPX: "#38bdf8",
  QQQ: "#c084fc",
  SOXX: "#f97316",
  HYG: "#34d399",
};
const ALL_ASSETS: ShockAsset[] = ["SPX", "QQQ", "SOXX", "HYG"];
// FOMC decision months on the Aug-2026..Jun-2027 grid (rate_paths.MEETINGS)
const FOMC_MONTHS = ["2026-09", "2026-10", "2026-12", "2027-01", "2027-03", "2027-04"];

// param drawer: the sensitivity surface — key params only, grouped
const DRAWER_PARAMS: Array<{ key: string; label: string }> = [
  { key: "kappa_base", label: "κ pass-through" },
  { key: "drift_spx", label: "SPX drift /yr" },
  { key: "hyg_carry", label: "HYG carry /yr" },
  { key: "implied_prob_oct", label: "Oct hike priced" },
  { key: "implied_prob_dec", label: "Dec hike priced" },
  { key: "rho_real", label: "ρ real share" },
  { key: "beta_spx", label: "β SPX" },
  { key: "beta_qqq", label: "β QQQ" },
  { key: "beta_soxx", label: "β SOXX" },
  { key: "logistic_a", label: "stress logistic a" },
  { key: "logistic_b", label: "stress logistic b" },
  { key: "oas_jump_entry", label: "OAS entry jump" },
  { key: "oas_dtheta_surprise", label: "OAS bp/surprise hike" },
  { key: "crack_soxx", label: "SOXX crack" },
  { key: "vix_haircut", label: "VIX haircut" },
  { key: "stress_exit_monthly", label: "stress exit p" },
];

export default function RateShockSimulator() {
  const [hikes, setHikes] = useState(0);
  const [seed, setSeed] = useState(42);
  const [assets, setAssets] = useState<ShockAsset[]>(["SPX", "HYG"]);
  const [showStress, setShowStress] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [overrides, setOverrides] = useState<Record<string, number>>({});
  const [calib, setCalib] = useState<ShockCalibration | null>(null);
  const [data, setData] = useState<ShockRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.shockCalibration().then(setCalib).catch(() => {});
  }, []);

  useEffect(() => {
    let alive = true;
    setBusy(true);
    setError(null);
    api
      .shockRun({ hikes, seed, overrides: Object.keys(overrides).length ? overrides : undefined })
      .then((d) => {
        if (alive) {
          setData(d);
          setBusy(false);
        }
      })
      .catch((e) => {
        if (alive) {
          setError(errorMessage(e));
          setBusy(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [hikes, seed, overrides]);

  const rows = useMemo(() => {
    if (!data) return {} as Record<ShockAsset, Array<Record<string, number | string>>>;
    const out: Record<string, Array<Record<string, number | string>>> = {};
    for (const a of ALL_ASSETS) {
      const b = data.bands[a];
      out[a] = data.months.map((m, i) => ({
        month: m,
        p5: b["5"][i],
        d5_95: b["95"][i] - b["5"][i],
        p25: b["25"][i],
        d25_75: b["75"][i] - b["25"][i],
        p50: b["50"][i],
        stress: Math.round(data.stress_prob[i] * 100),
      }));
    }
    return out as Record<ShockAsset, Array<Record<string, number | string>>>;
  }, [data]);

  return (
    <Panel
      title={
        <>
          Rate-Shock Simulator — Scenario Fan Charts
          <InfoTip term="rate_shock_sim" />
        </>
      }
      subtitle="Given N Fed moves vs the priced path, what do equity / HY credit distributions look like out to Q2 2027? Scenario visualization, not prediction"
    >
      <div className="flex flex-wrap items-center gap-2 text-[10px]">
        <span className="uppercase tracking-wide text-slate-500">scenario</span>
        {[-2, -1, 0, 1, 2, 3, 4].map((h) => (
          <button
            key={h}
            onClick={() => setHikes(h)}
            className={`rounded-full border px-2.5 py-0.5 font-semibold ${
              hikes === h
                ? "border-sky-500 bg-sky-500/10 text-sky-300"
                : "border-panelborder text-slate-500 hover:text-slate-300"
            }`}
          >
            {h > 0 ? `+${h} hike${h > 1 ? "s" : ""}` : h < 0 ? `${h} cut${h < -1 ? "s" : ""}` : "priced path"}
          </button>
        ))}
        <span className="ml-3 uppercase tracking-wide text-slate-500">assets</span>
        {ALL_ASSETS.map((a) => (
          <button
            key={a}
            onClick={() =>
              setAssets((cur) =>
                cur.includes(a) ? cur.filter((x) => x !== a) : [...cur, a],
              )
            }
            className={`rounded-full border px-2 py-0.5 font-semibold ${
              assets.includes(a) ? "" : "border-panelborder text-slate-500"
            }`}
            style={
              assets.includes(a)
                ? {
                    color: ASSET_COLORS[a],
                    borderColor: ASSET_COLORS[a],
                    backgroundColor: `${ASSET_COLORS[a]}1a`,
                  }
                : undefined
            }
          >
            {a}
          </button>
        ))}
        <button
          onClick={() => setSeed(Math.floor(Math.random() * 1e6))}
          className="ml-3 rounded border border-panelborder px-2 py-0.5 text-slate-400 hover:text-slate-200"
          title="re-draw Monte Carlo noise"
        >
          ↻ seed {seed}
        </button>
        <button
          onClick={() => setShowStress((v) => !v)}
          className={`rounded border px-2 py-0.5 ${
            showStress
              ? "border-amber-500/60 text-amber-300"
              : "border-panelborder text-slate-500"
          }`}
        >
          stress prob
        </button>
        <button
          onClick={() => setDrawerOpen((v) => !v)}
          className="rounded border border-panelborder px-2 py-0.5 text-slate-400 hover:text-slate-200"
        >
          {drawerOpen ? "▾ params" : "▸ params"}
        </button>
        {busy && <span className="text-sky-400">running…</span>}
        {data && (
          <span className="ml-auto font-mono text-slate-500">
            κ {data.meta.kappa_used} · canary {data.meta.canary01} · OAS₀{" "}
            {Math.round(data.meta.oas0)}bp · {data.meta.n_paths.toLocaleString()} paths
          </span>
        )}
      </div>

      {drawerOpen && calib && (
        <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5 rounded border border-panelborder bg-slate-900/40 p-3 md:grid-cols-4">
          {DRAWER_PARAMS.map(({ key, label }) => {
            const meta = calib.params[key];
            if (!meta) return null;
            return (
              <label key={key} className="flex items-center gap-1.5 text-[10px] text-slate-400">
                {meta.high_sensitivity && (
                  <span
                    className="h-1.5 w-1.5 shrink-0 rounded-full bg-red-400"
                    title="HIGH-SENSITIVITY: ±50% of this param moves the terminal median by >30% (QA tornado)"
                  />
                )}
                {meta.source === "judgment" && (
                  <span
                    className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400"
                    title="judgment-tagged parameter"
                  />
                )}
                <span className="w-28 truncate" title={`${meta.note} [${meta.range}]`}>
                  {label}
                </span>
                <input
                  type="number"
                  step="any"
                  defaultValue={overrides[key] ?? meta.default}
                  onBlur={(e) => {
                    const v = parseFloat(e.target.value);
                    if (!Number.isNaN(v) && v !== meta.default)
                      setOverrides((o) => ({ ...o, [key]: v }));
                    else
                      setOverrides((o) => {
                        const { [key]: _drop, ...rest } = o;
                        return rest;
                      });
                  }}
                  className="w-20 rounded border border-panelborder bg-slate-900 px-1 py-0.5 font-mono text-[10px] text-slate-200"
                />
              </label>
            );
          })}
          <button
            onClick={() => setOverrides({})}
            className="text-left text-[10px] text-sky-400 hover:text-sky-300"
          >
            reset all
          </button>
          <a
            href="#"
            onClick={(e) => e.preventDefault()}
            className="text-[10px] text-slate-500"
            title={calib.amendments.join("\n")}
          >
            {calib.amendments.length} counter-agent amendments (hover)
          </a>
        </div>
      )}

      {error && <div className="mt-2"><InlineError message={error} /></div>}
      {!data && !error && <Loading label="Running simulator…" />}

      {data &&
        assets.map((a) => (
          <div key={a} className="mt-3">
            <div className="flex items-baseline gap-3 text-[11px]">
              <span className="font-bold" style={{ color: ASSET_COLORS[a] }}>
                {a}
              </span>
              <span className="font-mono text-slate-400">
                median {fmtPct(data.bands[a]["50"][data.months.length - 1])} · P(dd&gt;10%){" "}
                {Math.round(data.probs[a].dd_gt_10 * 100)}% · P(dd&gt;20%){" "}
                {Math.round(data.probs[a].dd_gt_20 * 100)}%
              </span>
            </div>
            <div className="h-44">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={rows[a]} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                  <XAxis dataKey="month" stroke="#475569" tick={{ fontSize: 9 }} minTickGap={20} />
                  <YAxis
                    stroke="#475569"
                    tick={{ fontSize: 9 }}
                    width={40}
                    domain={["auto", "auto"]}
                    tickFormatter={(v: number) => `${v}`}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#0f172a",
                      border: "1px solid #334155",
                      borderRadius: 6,
                      fontSize: 11,
                    }}
                    formatter={(v: number, name: string, item: { payload?: Record<string, number> }) => {
                      const p = item.payload;
                      if (name === "d5_95" && p)
                        return [`${p.p5.toFixed(1)} – ${(p.p5 + p.d5_95).toFixed(1)}`, "5–95%"];
                      if (name === "d25_75" && p)
                        return [`${p.p25.toFixed(1)} – ${(p.p25 + p.d25_75).toFixed(1)}`, "25–75%"];
                      if (name === "p50") return [Number(v).toFixed(1), "median"];
                      return null as unknown as [string, string];
                    }}
                  />
                  {FOMC_MONTHS.map((m) => (
                    <ReferenceLine key={m} x={m} stroke="#334155" strokeDasharray="2 3" />
                  ))}
                  <ReferenceLine y={100} stroke="#475569" strokeDasharray="4 4" />
                  <Area dataKey="p5" stackId="w" stroke="none" fill="transparent" isAnimationActive={false} />
                  <Area
                    dataKey="d5_95"
                    stackId="w"
                    stroke="none"
                    fill={ASSET_COLORS[a]}
                    fillOpacity={0.1}
                    isAnimationActive={false}
                  />
                  <Area dataKey="p25" stackId="n" stroke="none" fill="transparent" isAnimationActive={false} />
                  <Area
                    dataKey="d25_75"
                    stackId="n"
                    stroke="none"
                    fill={ASSET_COLORS[a]}
                    fillOpacity={0.22}
                    isAnimationActive={false}
                  />
                  <Line
                    dataKey="p50"
                    stroke={ASSET_COLORS[a]}
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>
        ))}

      {data && showStress && (
        <div className="mt-2">
          <span className="text-[10px] uppercase tracking-wide text-slate-500">
            P(stress state) by month
          </span>
          <div className="h-14">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={data.months.map((m, i) => ({
                  month: m,
                  stress: Math.round(data.stress_prob[i] * 100),
                }))}
                margin={{ top: 2, right: 8, bottom: 0, left: 0 }}
              >
                <XAxis dataKey="month" hide />
                <YAxis
                  stroke="#475569"
                  tick={{ fontSize: 8 }}
                  width={30}
                  domain={[0, 100]}
                  tickFormatter={(v: number) => `${v}%`}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#0f172a",
                    border: "1px solid #334155",
                    borderRadius: 6,
                    fontSize: 10,
                  }}
                  formatter={(v: number) => [`${v}%`, "P(stress)"]}
                />
                <Area
                  dataKey="stress"
                  stroke="#fbbf24"
                  fill="#fbbf24"
                  fillOpacity={0.15}
                  isAnimationActive={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
        Two-stage conditional engine, not a naive Monte Carlo: your scenario minus
        the market-implied path (Oct ~70% / Dec ~45% priced, editable) makes a
        surprise vector; surprises map through a term-premium-dependent κ to the
        10y, then through estimated duration betas (with a regime-switching
        credit-stress state) into asset drifts; the Monte Carlo simulates only the
        residual noise (Student-t, t-copula). Bands are 5/25/50/75/95 percentiles
        of 10,000 paths, indexed to 100 today. Dashed verticals = FOMC decisions.
        {calib && <> {calib.epistemic_note}</>}
      </p>
    </Panel>
  );
}

function fmtPct(idx: number): string {
  const pct = idx - 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
}
