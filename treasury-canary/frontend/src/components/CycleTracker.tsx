import { useEffect, useMemo, useState } from "react";
import {
  ResponsiveContainer, ComposedChart, Line, XAxis, YAxis, Tooltip,
  ReferenceLine, ReferenceArea, CartesianGrid,
} from "recharts";
import { api } from "../lib/api";
import { Panel, InlineError, Loading } from "./ui";
import InfoTip from "./InfoTip";

interface CycleBoard {
  months: string[];
  coincident: (number | null)[];
  leading: (number | null)[];
  phase: (string | null)[];
  payroll_ma12_k: (number | null)[];
  rec_spans: [string, string][];
  zeberg_check: { holds: boolean; current_ma_k: number | null;
                  min_at_recession_starts_k: number | null };
  stats: { precision: number | null; recall: number | null; threshold: number };
  current: { month: string; coincident: number; leading: number; phase: string };
  basis: string;
}

const PHASE_COLOR: Record<string, string> = {
  EXPANSION: "#34d399", LATE_CYCLE: "#fbbf24", STALL: "#fb923c",
  SLOWDOWN: "#f87171", CONTRACTION: "#dc2626",
};

export default function CycleTracker() {
  const [board, setBoard] = useState<CycleBoard | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [view, setView] = useState<"composite" | "payrolls" | "analogs">(
    () => (localStorage.getItem("cycleView") as any) || "composite");
  const [analog, setAnalog] = useState<any | null>(null);
  const [analogErr, setAnalogErr] = useState<string | null>(null);
  const [range, setRange] = useState<"5y" | "full">(
    () => (localStorage.getItem("cycleRange") as any) || "5y");

  useEffect(() => {
    api.cycle()                     // getJson: 4-retry cold-boot handling
      .then(setBoard)
      .catch((e) => setErr(String(e?.message ?? e)));
  }, []);
  useEffect(() => { localStorage.setItem("cycleView", view); }, [view]);
  useEffect(() => {
    if (view === "analogs" && !analog && !analogErr)
      api.cycleAnalog().then(setAnalog)
        .catch((e) => setAnalogErr(String(e?.message ?? e)));
  }, [view, analog, analogErr]);
  useEffect(() => { localStorage.setItem("cycleRange", range); }, [range]);

  const rows = useMemo(() => {
    if (!board) return [];
    const cut = range === "5y" ? Math.max(0, board.months.length - 60) : 0;
    const out: any[] = board.months.slice(cut).map((m, i) => ({
      m,
      coin: board.coincident[cut + i],
      lead: board.leading[cut + i],
      pay: board.payroll_ma12_k[cut + i],
      phase: board.phase[cut + i],
    }));
    const nc = (board as any).nowcast;
    if (nc && out.length && view === "composite") {
      out[out.length - 1].proj = out[out.length - 1].coin;   // dashed connector
      out.push({ m: `${nc.month}*`, proj: nc.value });
    }
    return out;
  }, [board, range, view]);

  const recAreas = useMemo(() => {
    if (!board || rows.length === 0) return [];
    const lo = rows[0].m;
    return board.rec_spans.filter(([, e]) => e >= lo)
      .map(([s, e]) => [s < lo ? lo : s, e] as [string, string]);
  }, [board, rows]);

  if (err) return <Panel title="Business cycle"><InlineError message={err} /></Panel>;
  if (!board) return <Panel title="Business cycle"><Loading /></Panel>;

  const cur = board.current;
  const zc = board.zeberg_check;
  return (
    <Panel title="Business cycle — where we are, where we're heading">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-[10px]">
        {(["composite", "payrolls", "analogs"] as const).map((v) => (
          <button key={v} onClick={() => setView(v)}
            className={`rounded-full border px-2.5 py-0.5 font-semibold ${
              view === v ? "border-sky-500 text-sky-300 bg-sky-500/10"
                         : "border-panelborder text-slate-500"}`}>
            {v === "composite" ? "composites" : v === "payrolls" ? "payrolls 12m MA" : "historical analogs"}
          </button>
        ))}
        <span className="mx-1 text-slate-600">|</span>
        {(["5y", "full"] as const).map((r) => (
          <button key={r} onClick={() => setRange(r)}
            className={`rounded-full border px-2.5 py-0.5 ${
              range === r ? "border-sky-500 text-sky-300 bg-sky-500/10"
                          : "border-panelborder text-slate-500"}`}>{r}</button>
        ))}
        <span className="ml-auto font-mono text-[11px]" style={{ color: PHASE_COLOR[cur.phase] }}>
          {cur.phase.replace("_", " ")}
          {(board as any).realtime?.provisional && (
            <span className="ml-1 rounded border border-amber-500/60 px-1 text-[9px] text-amber-400"
              title={(board as any).realtime.provisional_note}>PROVISIONAL</span>
          )} · coin {cur.coincident >= 0 ? "+" : ""}{cur.coincident.toFixed(2)}
          {" "}· lead {cur.leading >= 0 ? "+" : ""}{cur.leading.toFixed(2)} · {cur.month}
          <InfoTip term="cycle_phase" />
        </span>
      </div>
      {view === "analogs" ? (
        <AnalogView analog={analog} err={analogErr} />
      ) : (
      <ResponsiveContainer width="100%" height={230}>
        <ComposedChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: -14 }}>
          <CartesianGrid stroke="#1e293b" strokeWidth={0.5} />
          <XAxis dataKey="m" tick={{ fontSize: 9, fill: "#64748b" }} minTickGap={40} />
          <YAxis tick={{ fontSize: 9, fill: "#64748b" }}
            domain={view === "composite" ? [-3, 2] : ["auto", "auto"]}
            allowDataOverflow={view === "composite"} />
          <Tooltip contentStyle={{ background: "#111a2e", border: "1px solid #26334e",
            fontSize: 11 }} labelStyle={{ color: "#93a4bd" }}
            formatter={(v: any, n: any) =>
              [typeof v === "number" ? v.toFixed(2) : v,
               n === "coin" ? "coincident (z)" : n === "lead" ? "leading (z)"
               : "payrolls 12m MA (k/mo)"]} />
          {recAreas.map(([s, e]) => (
            <ReferenceArea key={s} x1={s} x2={e} fill="#64748b" fillOpacity={0.18} />
          ))}
          {view === "composite" ? (
            <>
              <ReferenceLine y={0} stroke="#26334e" />
              <ReferenceLine y={-0.75} stroke="#f87171" strokeDasharray="4 3"
                label={{ value: "recession-consistent", fontSize: 8, fill: "#f87171",
                         position: "insideBottomLeft" }} />
              <ReferenceLine y={-0.5} stroke="#fbbf24" strokeDasharray="2 3"
                label={{ value: "leading warn", fontSize: 8, fill: "#fbbf24",
                         position: "insideTopLeft" }} />
              <Line dataKey="coin" stroke="#38bdf8" dot={false} strokeWidth={1.8} />
              <Line dataKey="lead" stroke="#c084fc" dot={false} strokeWidth={1.4} />
              <Line dataKey="proj" stroke="#fbbf24" strokeWidth={1.6}
                strokeDasharray="5 4" dot={{ r: 3, fill: "#fbbf24" }} />
            </>
          ) : (
            <>
              <ReferenceLine y={0} stroke="#f87171" strokeWidth={1} />
              <Line dataKey="pay" stroke="#38bdf8" dot={false} strokeWidth={1.8} />
            </>
          )}
        </ComposedChart>
      </ResponsiveContainer>
      )}
      {view !== "analogs" && (
      <div className="mt-1.5 text-[10px] leading-relaxed text-slate-500">
        {view === "composite" ? (
          <>Blue = coincident (NBER four: jobs·output·income·sales, 6m growth z).
          Purple = leading (curve·permits·claims·hours·credit·sentiment).
          Below −0.75: {Math.round((board.stats.precision ?? 0) * 100)}% precision /
          {" "}{Math.round((board.stats.recall ?? 0) * 100)}% recall vs NBER months (grey).
          {(board as any).nowcast && (
            <> Amber* = <b>next-month nowcast</b> {(board as any).nowcast.value.toFixed(2)} ({(board as any).nowcast.phase}) —
            payrolls/claims/rates print ~1 month before the composite; walk-forward 1972–2026
            (QA-corrected): RMSE −24% vs persistence (−7% ex-2020), ~25% of phase transitions
            called a month early [CI 18–34%], recession onsets earlier 5/7 · never missed.</>
          )}
          <InfoTip term="cycle_composite" /></>
        ) : (
          <>12-month average of monthly payroll change. Now {zc.current_ma_k?.toFixed(0)}k/mo —
          {zc.holds
            ? " below every level at which a recession STARTED since 1970 (lowest was "
              + zc.min_at_recession_starts_k?.toFixed(0) + "k): the Zeberg claim holds on our data."
            : " the \"lower than any recession entry since 1970\" claim does NOT hold on our data (min at starts: "
              + zc.min_at_recession_starts_k?.toFixed(0) + "k)."}
          <InfoTip term="cycle_payrolls" /></>
        )}
        {" "}{board.basis}
      </div>
      )}
    </Panel>
  );
}

function AnalogView({ analog, err }: { analog: any; err: string | null }) {
  if (err) return <InlineError message={err} />;
  if (!analog) return <Loading />;
  const paths = analog.analogs.map((a: any, k: number) => ({ a, k }));
  const rows = Array.from({ length: 19 }, (_, h) => {
    const r: any = { h };
    paths.forEach(({ a, k }: any) => { r[`a${k}`] = a.spx_path_fwd18[h]; });
    return r;
  });
  const COLORS = ["#f87171", "#fb923c", "#fbbf24", "#c084fc", "#38bdf8"];
  const s = analog.skill;
  const ep = analog.episodes;
  const rc = analog.recent_calibration || {};
  const years = Object.keys(rc).sort();
  const calib = years.length >= 2 && years.every((y) => rc[y].recession_observed !== true)
    ? `${Math.min(...years.map((y) => rc[y].mean_p_pct))}–${Math.max(...years.map((y) => rc[y].mean_p_pct))}% across ${years[0]}–${years[years.length - 1]}`
    : null;
  const missing = (analog.current_missing_dims || []).join(", ");
  return (
    <div>
      <div className="mb-1 text-[10px] text-slate-400">
        Months since 1960 most similar to <b>{analog.asof}</b> (13-dim macro
        state; match = closer than N% of all history). S&P path next 18 months:
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <ComposedChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: -14 }}>
          <CartesianGrid stroke="#1e293b" strokeWidth={0.5} />
          <XAxis dataKey="h" tick={{ fontSize: 9, fill: "#64748b" }}
            label={{ value: "months ahead", fontSize: 9, fill: "#64748b", position: "insideBottom", offset: -2 }} />
          <YAxis tick={{ fontSize: 9, fill: "#64748b" }} unit="%" />
          <Tooltip contentStyle={{ background: "#111a2e", border: "1px solid #26334e", fontSize: 11 }}
            labelStyle={{ color: "#93a4bd" }}
            formatter={(v: any, n: any) => {
              const i = Number(String(n).slice(1));
              return [`${Number(v).toFixed(1)}%`, `${analog.analogs[i].month}`];
            }} />
          <ReferenceLine y={0} stroke="#26334e" />
          {paths.map(({ a, k }: any) => (
            <Line key={k} dataKey={`a${k}`} stroke={COLORS[k % COLORS.length]}
              dot={false} strokeWidth={a.recession_within_12m ? 1.8 : 1.2}
              strokeDasharray={a.recession_within_12m ? undefined : "4 3"} />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
      <table className="mt-2 w-full text-[10px]">
        <thead><tr className="text-slate-500">
          <th className="text-left font-normal">analog</th>
          <th className="text-left font-normal">phase then</th>
          <th className="text-right font-normal">match</th>
          <th className="text-right font-normal">fwd 6m</th>
          <th className="text-right font-normal">fwd 12m</th>
          <th className="text-right font-normal">fwd 18m</th>
          <th className="text-right font-normal">recession &le;12m</th>
        </tr></thead>
        <tbody>
          {analog.analogs.map((a: any, k: number) => (
            <tr key={a.month} className="border-t border-panelborder/40">
              <td className="py-0.5 font-mono" style={{ color: COLORS[k % COLORS.length] }}>{a.month}</td>
              <td>{(a.phase_then || "").replace("_", " ")}</td>
              <td className="text-right font-mono">{a.closer_than_pct}%</td>
              {[a.fwd_spx_6m_pct, a.fwd_spx_12m_pct, a.fwd_spx_18m_pct].map((v, j) => (
                <td key={j} className={`text-right font-mono ${v == null ? "text-slate-600" : v < 0 ? "text-rose-400" : "text-emerald-400"}`}>
                  {v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`}</td>
              ))}
              <td className="text-right">{a.recession_within_12m == null ? "—" : a.recession_within_12m ? "YES" : "no"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-1.5 text-[10px] leading-relaxed text-slate-500">
        {ep && (
          <>Top-10 analogs span <b>{ep.n} distinct episodes</b>; {ep.recession} of {ep.n}
          {ep.includes_covid ? " (one being COVID)" : ""} saw recession within 12m —
          {" "}{analog.analog_recession_within_12m_pct}% counting overlapping months,
          {" "}{ep.by_episode_pct}% counting episodes
          {ep.top10_distinct_episode_pct != null ? ` (${ep.top10_distinct_episode_pct}% over the 10 nearest distinct episodes)` : ""},
          vs {analog.climatology_recession_within_12m_pct}% unconditionally.{" "}</>
        )}
        {analog.ebp_context && (
          <>Credit check (descriptive, not a model input): Fed excess bond
          premium {analog.ebp_context.value} ({analog.ebp_context.month},
          {" "}{analog.ebp_context.percentile}th percentile) vs {analog.ebp_context.at_2007_06}
          {" "}at the matched 2007-06 month and a {analog.ebp_context.peak_2007_09} peak
          into 2008 — credit is currently <b>not confirming</b> the 2007 rhyme.{" "}</>
        )}
        {calib && (
          <>Calibration warning: analog p(recession) has read {calib} with no recession
          observed through {analog.asof} — treat the level as a regime read, not a
          calibrated probability.{" "}</>
        )}
        Walk-forward skill ({s.n_months} months): recession Brier <b>{s.brier_analog}</b> vs
        base rate {s.brier_base_rate} — {s.brier_analog < s.brier_base_rate
          ? "analogs help on this sample (edge concentrated in 2008/1979/2001; borderline under year-block resampling)"
          : "analogs do NOT beat the base rate on this sample"}; return MAE {s.ret_mae_analog_pp}pp vs
        climatology {s.ret_mae_climatology_pp}pp — {s.ret_mae_analog_pp > s.ret_mae_climatology_pp
          ? "analogs do NOT beat climatology on return magnitude"
          : "analogs edge climatology on return magnitude"}.
        {missing ? ` Current vector is missing: ${missing} (publication lag).` : ""}
        {" "}Read the paths as scenario texture, not a forecast. {analog.basis}
      </div>
    </div>
  );
}
