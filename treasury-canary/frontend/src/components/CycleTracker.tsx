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
  const [view, setView] = useState<"composite" | "payrolls">(
    () => (localStorage.getItem("cycleView") as any) || "composite");
  const [range, setRange] = useState<"5y" | "full">(
    () => (localStorage.getItem("cycleRange") as any) || "5y");

  useEffect(() => {
    api.cycle()                     // getJson: 4-retry cold-boot handling
      .then(setBoard)
      .catch((e) => setErr(String(e?.message ?? e)));
  }, []);
  useEffect(() => { localStorage.setItem("cycleView", view); }, [view]);
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
        {(["composite", "payrolls"] as const).map((v) => (
          <button key={v} onClick={() => setView(v)}
            className={`rounded-full border px-2.5 py-0.5 font-semibold ${
              view === v ? "border-sky-500 text-sky-300 bg-sky-500/10"
                         : "border-panelborder text-slate-500"}`}>
            {v === "composite" ? "composites" : "payrolls 12m MA"}
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
          {cur.phase.replace("_", " ")} · coin {cur.coincident >= 0 ? "+" : ""}{cur.coincident.toFixed(2)}
          {" "}· lead {cur.leading >= 0 ? "+" : ""}{cur.leading.toFixed(2)} · {cur.month}
          <InfoTip term="cycle_phase" />
        </span>
      </div>
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
    </Panel>
  );
}
