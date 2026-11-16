import { useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";
import { Area, CartesianGrid, ComposedChart, Customized, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { GdpCountry, GdpMeasure, GdpWatch } from "../lib/api";
import { api } from "../lib/api";
import { errorMessage } from "../lib/format";
import { GDP_FIXTURE } from "../lib/gdpFixture";
import type { GlossaryEntry } from "../lib/glossary";
import InfoTip from "./InfoTip";
import { InlineError, Loading, Panel } from "./ui";

// Categorical slots for the dark panel surface, in fixed order (dataviz validator on #0a1022: all checks pass, worst
// adjacent CVD dE 8.4, so the projection is dashed and lines are end-labelled as secondary encoding). A country keeps
// its slot while selected, so adding or removing one never repaints the others; 8 slots = 8 lines at once.
const SLOTS = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#9085e9", "#e66767"];
const MAX_SELECTED = SLOTS.length;
const BAND_MAX = 3;
const SLATE = "#64748b";
const GRID = "#1e293b";
const TOOLTIP_STYLE = { background: "#0f172a", border: "1px solid #334155", fontSize: 11, padding: "6px 8px" };
const tickStyle = { fontSize: 9, fill: SLATE };

type RangeKey = "1y" | "3y" | "5y" | "10y" | "25y" | "max" | "custom";
const RANGES: Array<{ k: RangeKey; label: string; quarters: number | null }> = [
  { k: "1y", label: "1Y", quarters: 4 }, { k: "3y", label: "3Y", quarters: 12 }, { k: "5y", label: "5Y", quarters: 20 },
  { k: "10y", label: "10Y", quarters: 40 }, { k: "25y", label: "25Y", quarters: 100 }, { k: "max", label: "Max", quarters: null },
  { k: "custom", label: "Custom", quarters: null },
];

const TIPS: Record<string, GlossaryEntry> = {
  gdp: {
    title: "Real GDP growth",
    what: "Inflation-adjusted output, % change on the same quarter a year earlier (OECD quarterly national accounts, seasonally adjusted).",
    read: "Above zero the economy is bigger than a year ago. Each economy has its own normal pace; the table shows the rule's trend for each (its 10-year median, annualised).",
  },
  per_capita: {
    title: "Real GDP growth per person",
    what: "The same growth divided by population growth over the same four quarters (IMF population, interpolated between years; IMF projections ahead).",
    read: "It strips out growth that only comes from more people. Where population is shrinking (Japan) the per-person rate runs above the headline; where it grows fast (India) it runs below.",
  },
  projection: {
    title: "The dashed projection",
    what: "A simple rule, tested on these 20 economies since 2006: each coming quarter's growth drifts back toward the economy's 10-year median at the pace it has historically, and the year-on-year rate is rolled forward from the quarters already published.",
    read: "Four quarters ahead its typical miss was about 1.6 points, against 2.3 for 'last value holds'. It cannot see shocks coming, and its 10-year trend lags slowdowns.",
    caveat: "Tested on today's revised data, not the numbers as first published, so real-time misses run larger.",
  },
  band: {
    title: "The shaded band",
    what: "Where outcomes landed around this rule's past projections: 10th-90th percentile shaded light, 25th-75th darker, by quarters ahead (pandemic quarters excluded).",
    read: "If the band sits below or above the line, the rule has run too high or too low for that economy before (China, for one: its line sits above its own band). Shown for up to three economies at a time.",
    caveat: "Since 2016 the light band held about 85-88% of outcomes outside the pandemic and about 73-76% with it, tested on 18 economies; China's and Saudi Arabia's bands are in-sample only (too short a history to test). The bands drawn use every backtest miss from 2006 on, so they are in-sample too.",
  },
  imf: {
    title: "IMF projection",
    what: "The IMF World Economic Outlook's growth projection for the year (annual GDP, so not the same measure as a quarter on a year earlier). Calendar years, except India's, which are fiscal years (April-March).",
    read: "An independent reference beside the rule; it is not backtested here.",
  },
  share: {
    title: "Share of world GDP",
    what: "GDP at market exchange rates as a share of the world's (IMF World Economic Outlook).",
    read: "A few economies set the global pace: the United States and China alone are over 40%, the six largest about 57%, and these 20 about 79%.",
  },
  record: {
    title: "The rule's record",
    what: "Four quarters ahead, how much less the rule missed by than 'last value holds' in the backtest (positive = the rule did better).",
    read: "Where it is negative (China, Indonesia) the simple rule did worse than doing nothing: read those projections with that record.",
  },
  range: {
    title: "Date range",
    what: "Presets look back from the latest quarter among the economies shown; Custom takes any two dates (quarters are matched by their start; an empty date leaves that end open).",
    read: "The projection shows whenever the range reaches that latest quarter.",
  },
};

const qi = (s: string) => Number(s.slice(0, 4)) * 4 + Number(s.slice(-1)) - 1;
const qs = (i: number) => `${Math.floor(i / 4)}-Q${(i % 4) + 1}`;
const dateToQ = (d: string) => {
  const [y, m] = d.split("-").map(Number);
  return Number.isFinite(y) && Number.isFinite(m) ? `${y}-Q${Math.floor((m - 1) / 3) + 1}` : null;
};
const qStart = (q: string) => `${q.slice(0, 4)}-${String((Number(q.slice(-1)) - 1) * 3 + 1).padStart(2, "0")}-01`;
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const pct = (v: number | null | undefined, d = 1) => (isNum(v) ? `${v > 0 ? "+" : ""}${v.toFixed(d)}%` : "n/a");

function Toggle({ on, children, onClick, title }: { on: boolean; children: ReactNode; onClick: () => void; title?: string }) {
  return (
    <button type="button" title={title} onClick={onClick} aria-pressed={on}
      className={`rounded border px-2 py-1 text-[11px] ${on ? "border-sky-600/70 bg-sky-900/30 text-sky-200" : "border-panelborder text-slate-400 hover:bg-slate-800/50 hover:text-slate-200"}`}>
      {children}
    </button>
  );
}

function statusLabel(s: string | null | undefined): { text: string; cls: string } {
  if (s === "ok") return { text: "live", cls: "border-emerald-700/60 text-emerald-300" };
  if (s === "stale") return { text: "stale copy", cls: "border-amber-600/60 text-amber-300" };
  if (s === "snapshot") return { text: "frozen snapshot", cls: "border-amber-600/60 text-amber-300" };
  if (s === "partial") return { text: "partly snapshot", cls: "border-amber-600/60 text-amber-300" };
  return { text: "data unavailable", cls: "border-slate-600 text-slate-400" };
}

interface Row { q: string; [k: string]: number | string | [number, number] | null }

function buildRows(sel: GdpCountry[], m: GdpMeasure, lo: number, hi: number, showFc: boolean, bands: boolean): Row[] {
  const latest = Math.max(...sel.map((c) => (c.last ? qi(c.last) : -1)));
  const fcOn = showFc && hi >= latest;
  const end = fcOn ? Math.max(hi, ...sel.map((c) => (c.forecast ? qi(c.forecast.quarters[c.forecast.quarters.length - 1]) : -1))) : hi;
  const rows: Row[] = [];
  const at = new Map<string, Row>();
  for (let i = lo; i <= end; i++) {
    const r: Row = { q: qs(i) };
    rows.push(r);
    at.set(r.q, r);
  }
  for (const c of sel) {
    const s = c.series;
    const vals = m === "gdp" ? s?.gdp : s?.per_capita;
    if (!s || !vals) continue;
    s.quarters.forEach((q, i) => {
      const r = at.get(q);
      if (r && qi(q) <= hi && isNum(vals[i])) r[c.code] = vals[i] as number;
    });
    const f = c.forecast;
    const fv = f ? (m === "gdp" ? f.gdp : f.per_capita) : null;
    if (fcOn && f && fv && s.quarters.length) {
      const lastVal = vals[vals.length - 1];
      const r0 = at.get(f.from);
      if (r0 && isNum(lastVal)) {
        r0[`${c.code}_f`] = lastVal;
        if (bands) { r0[`${c.code}_b80`] = [lastVal, lastVal]; r0[`${c.code}_b50`] = [lastVal, lastVal]; }
      }
      f.quarters.forEach((q, h) => {
        const r = at.get(q);
        if (!r || !isNum(fv[h])) return;
        r[`${c.code}_f`] = fv[h] as number;
        const b80 = (m === "gdp" ? f.band80.gdp : f.band80.per_capita)?.[h];
        const b50 = (m === "gdp" ? f.band50.gdp : f.band50.per_capita)?.[h];
        if (bands && b80) r[`${c.code}_b80`] = b80;
        if (bands && b50) r[`${c.code}_b50`] = b50;
      });
    }
  }
  return rows;
}

function ChartTooltip({ active, label, payload, names }: {
  active?: boolean; label?: string; payload?: Array<{ dataKey?: string | number; value?: unknown; color?: string; payload?: Row }>;
  names: Record<string, string>;
}) {
  if (!active || !payload?.length || !label) return null;
  const row = payload[0]?.payload;
  const items = Object.keys(names).map((code) => {
    const a = row?.[code];
    const f = row?.[`${code}_f`];
    const b = row?.[`${code}_b80`];
    const projected = !isNum(a) && isNum(f);
    return { code, v: isNum(a) ? a : isNum(f) ? f : null, projected, band: projected && Array.isArray(b) ? b : null };
  }).filter((x) => x.v !== null);
  if (!items.length) return null;
  return (
    <div style={TOOLTIP_STYLE} className="rounded">
      <div className="mb-1 font-mono text-[10px] text-slate-400">{label}</div>
      {items.map((x) => (
        <div key={x.code} className="flex items-center gap-2 text-[11px] text-slate-200">
          <span className="inline-block h-2 w-3 rounded-sm" style={{ background: payload.find((p) => p.dataKey === x.code || p.dataKey === `${x.code}_f`)?.color }} />
          <span className="min-w-[7rem]">{names[x.code]}</span>
          <span className="font-mono tabular-nums">{pct(x.v as number)}</span>
          {x.projected && <span className="text-slate-500">rule{x.band ? ` (80%: ${pct(x.band[0])} to ${pct(x.band[1])})` : ""}{x.band && (x.v as number) > x.band[1] ? ", above its band: the rule ran high here before" : x.band && (x.v as number) < x.band[0] ? ", below its band: the rule ran low here before" : ""}</span>}
        </div>
      ))}
    </div>
  );
}

// End labels in one layer, so they can be spread apart (dataviz step 7: no label collisions). Recharts hands a
// Customized child its state, including each line's computed points.
interface EndLabel { key: string; text: string; color: string }
interface PlotPoint { x?: number | null; y?: number | null; value?: unknown }
interface PlotItem { item?: { props?: { dataKey?: unknown } }; props?: { points?: PlotPoint[] } }

function EndLabels({ labels, formattedGraphicalItems }: { labels: EndLabel[]; formattedGraphicalItems?: PlotItem[] }) {
  const pts: Array<EndLabel & { x: number; y: number }> = [];
  for (const lab of labels) {
    const it = (formattedGraphicalItems ?? []).find((e) => e?.item?.props?.dataKey === lab.key);
    const ps = (it?.props?.points ?? []).filter((p) => isNum(p?.x) && isNum(p?.y) && p.value !== null && p.value !== undefined);
    const last = ps[ps.length - 1];
    if (last) pts.push({ ...lab, x: last.x as number, y: last.y as number });
  }
  pts.sort((a, b) => a.y - b.y);
  for (let i = 1; i < pts.length; i++) if (pts[i].y - pts[i - 1].y < 12) pts[i].y = pts[i - 1].y + 12;
  return (
    <g>
      {pts.map((p) => (
        <text key={p.key} x={p.x + 6} y={p.y} dy={3} fontSize={10} fill="#cbd5e1">
          <tspan fill={p.color}>■ </tspan>{p.text}
        </text>
      ))}
    </g>
  );
}

const fiscal = (c: GdpCountry) => !!c.imf && !!c.imf_basis && c.imf_basis !== "calendar years";
const listNames = (xs: string[]) => (xs.length > 1 ? `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}` : xs[0] ?? "");

/** the footnotes under the table (which always carries the projection columns), from the payload: a line outside
 * its own band, in-sample bands, fiscal years, and (per person) the population-series breaks */
function tableNotes(sel: GdpCountry[], m: GdpMeasure): string[] {
  const out: string[] = [];
  for (const c of sel) {
    const side = c.forecast?.line_vs_band;
    const r = c.record;
    if (side && r && isNum(r.n_h4) && isNum(r.n_over_h4) && isNum(r.median_miss_h4)) {
      const k = side === "above" ? r.n_over_h4 : r.n_h4 - r.n_over_h4;
      out.push(`* ${c.name}: the line sits ${side} its own band. The rule ${side === "above" ? "over" : "under"}-projected it in ${k} of ${r.n_h4} backtests (median miss ${pct(r.median_miss_h4).replace("%", "")} points), so outcomes have landed in the band, ${side === "above" ? "below" : "above"} the line.`);
    }
  }
  const ins = sel.filter((c) => c.forecast && c.record?.band_in_sample_only).map((c) => c.name);
  if (ins.length) out.push(`‡ ${listNames(ins)}: band in-sample only (too short a history to test it out of sample).`);
  for (const c of sel.filter(fiscal)) out.push(`† ${c.name}: IMF figures are ${c.imf_basis}.`);
  if (m === "per_capita") for (const c of sel) if (c.pop_note) out.push(c.pop_note);
  return out;
}

/** a toggled economy keeps its colour slot while shown; a new one takes the lowest free slot; none past the cap */
export function toggleSlot(s: Record<string, number>, code: string, max = MAX_SELECTED): Record<string, number> {
  if (code in s) {
    const { [code]: _drop, ...rest } = s;
    return rest;
  }
  if (Object.keys(s).length >= max) return s;
  const used = new Set(Object.values(s));
  return { ...s, [code]: SLOTS.findIndex((_, i) => !used.has(i)) };
}

/** year labels at least ~34px apart across the plot (the chart's width less the axes) */
export const yearStep = (years: number, width: number) => Math.max(1, Math.ceil((years * 34) / Math.max(200, width - 80)));

/** the chart's width, for the year-label step (none on a server render) */
function useWidth(): [RefObject<HTMLDivElement>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((es) => setW(es[0]?.contentRect.width ?? 0));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

function devOverride(): GdpWatch | null {
  if (!import.meta.env.DEV) return null;
  try {
    if (new URLSearchParams(window.location.search).get("gdp") === "fixture") return GDP_FIXTURE;
  } catch {
    // no window (server render)
  }
  return null;
}

export default function GdpTab() {
  const [data, setData] = useState<GdpWatch | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    const dev = devOverride();
    if (dev) {
      setData(dev);
      return;
    }
    api.gdpWatch().then((d) => alive && setData(d)).catch((e) => alive && setError(errorMessage(e)));
    return () => {
      alive = false;
    };
  }, []);
  if (error) return <InlineError message={`Failed to load /gdp-watch: ${error}`} />;
  if (!data) return <Loading label="Loading the GDP tab…" />;
  return <GdpView data={data} />;
}

export interface GdpInitial { measure?: GdpMeasure; range?: RangeKey; menuOpen?: boolean; selected?: string[]; from?: string; to?: string }

export function GdpView({ data, initial }: { data: GdpWatch; initial?: GdpInitial }) {
  const all = useMemo(() => [...(data.countries ?? []), ...(data.aggregates ?? [])].filter((c) => c.series), [data]);
  const byCode = useMemo(() => Object.fromEntries(all.map((c) => [c.code, c])), [all]);
  const defaults = useMemo(() => (data.countries ?? []).filter((c) => c.default).map((c) => c.code), [data]);
  const [measure, setMeasure] = useState<GdpMeasure>(initial?.measure ?? "gdp");
  const [slots, setSlots] = useState<Record<string, number>>(() =>
    Object.fromEntries((initial?.selected ?? defaults).slice(0, MAX_SELECTED).map((c, i) => [c, i])));
  const [menuOpen, setMenuOpen] = useState(initial?.menuOpen ?? false);
  const [range, setRange] = useState<RangeKey>(initial?.range ?? "10y");
  const [from, setFrom] = useState(initial?.from ?? "2016-01-01");
  const [to, setTo] = useState(initial?.to ?? `${Number((data.as_of ?? "2026").slice(0, 4)) + 1}-12-31`);
  const [showFc, setShowFc] = useState(true);

  const selected = Object.keys(slots).filter((c) => byCode[c]).sort((a, b) => slots[a] - slots[b]);
  const visible = selected.filter((c) => measure === "gdp" || byCode[c]?.series?.per_capita);
  const sel = visible.map((c) => byCode[c]);
  const toggle = (code: string) => setSlots((s) => toggleSlot(s, code));
  const setSet = (codes: string[]) => setSlots(Object.fromEntries(codes.slice(0, MAX_SELECTED).map((c, i) => [c, i])));

  const latest = sel.length ? Math.max(...sel.map((c) => (c.last ? qi(c.last) : -1))) : -1;
  const first = sel.length ? Math.min(...sel.map((c) => (c.first ? qi(c.first) : latest))) : -1;
  let lo = first;
  let hi = latest;
  const preset = RANGES.find((r) => r.k === range);
  if (preset?.quarters) lo = Math.max(first, latest - preset.quarters + 1);
  if (range === "custom") {
    const a = dateToQ(from) ? qi(dateToQ(from) as string) : first;      // empty = open at that end
    const b = dateToQ(to) ? qi(dateToQ(to) as string) : latest;
    lo = Math.max(first, Math.min(a, b));
    hi = Math.min(latest, Math.max(a, b));
  }
  const fcOn = showFc && hi >= latest;                       // the projection starts at the latest quarter
  const bands = fcOn && visible.length <= BAND_MAX;
  const rows = useMemo(() => (sel.length && lo <= hi ? buildRows(sel, measure, lo, hi, showFc, bands) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [visible.join(","), measure, lo, hi, showFc, bands]);
  const names = Object.fromEntries(visible.map((c) => [c, byCode[c].name]));
  const span = hi - lo;
  const [chartRef, width] = useWidth();
  const end = rows.length ? qi(rows[rows.length - 1].q) : hi;
  const step = yearStep((end - lo) / 4 + 1, width || 960);           // a server render has no width: assume 960px
  const yearTicks = span > 16 ? rows.map((r) => r.q).filter((q) => q.endsWith("Q1") && Number(q.slice(0, 4)) % step === 0) : undefined;
  const tickFmt = (q: string) => (span > 16 ? q.slice(0, 4) : `${q.slice(-2)} '${q.slice(2, 4)}`);
  const hasF = (code: string) => !!(measure === "gdp" ? byCode[code].forecast?.gdp : byCode[code].forecast?.per_capita);
  // every line carries its name at its end (the palette keeps neighbours apart, not all eight at once)
  const endLabels: EndLabel[] = visible.map((code) => ({ key: fcOn && hasF(code) ? `${code}_f` : code, text: code, color: SLOTS[slots[code]] }));
  const hidden = selected.length - visible.length;
  const notes = tableNotes(sel, measure);
  const st = statusLabel(data.status?.overall);
  const pooled = data.record?.pooled_ex_pandemic;
  const mName: Record<string, string> = { N: "last value holds", T: "trend only", A: "the rule (AR(1) toward trend)" };

  return (
    <div className="flex flex-col gap-5">
      <div className="rounded-lg border border-slate-600/60 bg-slate-500/5 px-4 py-3">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-sm font-bold tracking-wide text-slate-300">GDP GROWTH: the largest economies, quarter by quarter, with a tested 4-quarter projection</span>
          <span className={`ml-auto rounded border px-1.5 py-0.5 font-mono text-[10px] ${st.cls}`}>{st.text}</span>
          <span className="font-mono text-[11px] text-slate-500">latest quarter {data.as_of ?? "n/a"} · generated {data.generated ?? "n/a"}{data.status?.overall === "snapshot" && data.snapshot_as_of ? ` · snapshot of ${data.snapshot_as_of}` : ""}</span>
        </div>
        {data.build_error && <p className="mt-1 text-[11px] text-slate-500">The last rebuild failed ({data.build_error}); {data.build_fallback === "snapshot" ? `showing the frozen snapshot${data.snapshot_as_of ? ` of ${data.snapshot_as_of}` : ""}` : "showing the previous build"}.</p>}
        {!data.build_error && data.status?.overall === "snapshot" && <p className="mt-1 text-[11px] text-slate-500">The live sources did not answer; showing the frozen snapshot{data.snapshot_as_of ? ` of ${data.snapshot_as_of}` : ""}.</p>}
        {data.status?.filled && Object.keys(data.status.filled).length > 0 && <p className="mt-1 text-[11px] text-slate-500">Missing from the live reply, kept from the snapshot: {Object.entries(data.status.filled).map(([k, v]) => `${k} ${v.join(", ")}`).join("; ")}.</p>}
      </div>

      <Panel title={<>{measure === "gdp" ? "Real GDP growth" : "Real GDP growth per person"}<InfoTip entry={measure === "gdp" ? TIPS.gdp : TIPS.per_capita} /></>}
        subtitle="% on the same quarter a year earlier · solid = published · dashed = the rule's next 4 quarters">
        <div className="flex flex-wrap items-center gap-2" data-testid="gdp-controls">
          <div className="flex gap-1">
            <Toggle on={measure === "gdp"} onClick={() => setMeasure("gdp")}>GDP</Toggle>
            <Toggle on={measure === "per_capita"} onClick={() => setMeasure("per_capita")}>Per person</Toggle>
          </div>
          <span className="mx-1 h-4 w-px bg-slate-700" />
          <div className="flex flex-wrap items-center gap-1">
            {RANGES.map((r) => <Toggle key={r.k} on={range === r.k} onClick={() => setRange(r.k)}>{r.label}</Toggle>)}
            <InfoTip entry={TIPS.range} />
          </div>
          {range === "custom" && (
            <div className="flex items-center gap-1 text-[11px] text-slate-400">
              <input type="date" aria-label="From" value={from} min={sel.length ? qStart(qs(first)) : undefined} onChange={(e) => setFrom(e.target.value)}
                className="rounded border border-panelborder bg-slate-900 px-1 py-0.5 text-slate-200" />
              <span>to</span>
              <input type="date" aria-label="To" value={to} onChange={(e) => setTo(e.target.value)}
                className="rounded border border-panelborder bg-slate-900 px-1 py-0.5 text-slate-200" />
            </div>
          )}
          <label className="ml-auto flex items-center gap-1 text-[11px] text-slate-400">
            <input type="checkbox" checked={showFc} onChange={(e) => setShowFc(e.target.checked)} /> projection
            <InfoTip entry={TIPS.projection} />
          </label>
        </div>

        <div className="mt-2 rounded border border-panelborder" data-testid="gdp-menu">
          <button type="button" onClick={() => setMenuOpen((o) => !o)} aria-expanded={menuOpen}
            className="flex w-full items-center gap-2 px-2 py-1.5 text-left text-[11px] text-slate-300 hover:bg-slate-800/40">
            <span>{menuOpen ? "▾" : "▸"}</span>
            <span>Economies: {selected.length} of {all.length} selected{hidden > 0 ? `, ${hidden} with no per-person series not drawn` : ""}</span>
            <span className="truncate text-slate-500">{selected.map((c) => byCode[c].name).join(", ")}</span>
          </button>
          {menuOpen && (
            <div className="border-t border-panelborder px-2 py-2">
              <div className="mb-2 flex flex-wrap items-center gap-1 text-[11px]">
                <Toggle on={false} onClick={() => setSet(defaults)}>Largest 6</Toggle>
                <Toggle on={false} onClick={() => setSet((data.countries ?? []).slice().sort((a, b) => (b.share_world_pct ?? 0) - (a.share_world_pct ?? 0)).map((c) => c.code))}>Largest 8</Toggle>
                <Toggle on={false} onClick={() => setSlots({})}>Clear</Toggle>
                <span className="text-slate-500">up to {MAX_SELECTED} at once (the most lines the palette keeps apart)</span>
                <span className="ml-auto text-slate-500">share of world GDP, {data.share_year ?? ""}<InfoTip entry={TIPS.share} /></span>
              </div>
              <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 sm:grid-cols-3 lg:grid-cols-4">
                {all.map((c) => {
                  const on = c.code in slots;
                  const off = !on && selected.length >= MAX_SELECTED;
                  const noPc = measure === "per_capita" && !c.series?.per_capita;
                  return (
                    <label key={c.code} className={`flex items-center gap-1.5 text-[11px] ${off || noPc ? "text-slate-600" : "text-slate-300"}`}>
                      <input type="checkbox" checked={on} disabled={off} onChange={() => toggle(c.code)} />
                      {on && <span className="inline-block h-2 w-3 rounded-sm" style={{ background: SLOTS[slots[c.code]] }} />}
                      <span className="truncate">{c.name}</span>
                      <span className="ml-auto font-mono text-[10px] text-slate-500">{isNum(c.share_world_pct) ? `${c.share_world_pct.toFixed(1)}%` : c.aggregate ? "agg." : ""}</span>
                    </label>
                  );
                })}
              </div>
              {measure === "per_capita" && <p className="mt-1 text-[10px] text-slate-500">Aggregates have no per-person series.</p>}
            </div>
          )}
        </div>

        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1" data-testid="gdp-legend">
          {visible.map((code) => {
            const c = byCode[code];
            const v = measure === "gdp" ? c.series?.gdp : c.series?.per_capita;
            const f = measure === "gdp" ? c.forecast?.gdp : c.forecast?.per_capita;
            return (
              <span key={code} className="flex items-center gap-1.5 text-[11px] text-slate-300">
                <span className="inline-block h-2 w-3 rounded-sm" style={{ background: SLOTS[slots[code]] }} />
                {c.name} <span className="font-mono text-slate-400">{pct(v?.[v.length - 1])}</span>
                {fcOn && f && <span className="font-mono text-slate-500">rule: {pct(f[f.length - 1])} in {c.forecast?.quarters[3]}</span>}
                {fcOn && f && c.forecast?.line_vs_band && <span className="text-slate-500">(line {c.forecast.line_vs_band} its band*)</span>}
              </span>
            );
          })}
        </div>

        {rows.length > 1 ? (
          <div ref={chartRef} style={{ width: "100%", height: 340 }} className="mt-2" data-testid="gdp-chart" role="img"
            aria-label={`${measure === "gdp" ? "Real GDP growth" : "Real GDP growth per person"}, % on a year earlier, ${rows[0]?.q} to ${rows[rows.length - 1]?.q}: ${visible.map((c) => byCode[c].name).join(", ")}. The table below has the values.`}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={rows} margin={{ top: 8, right: 44, bottom: 0, left: 0 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="q" tick={tickStyle} tickFormatter={tickFmt} ticks={yearTicks} interval={span > 16 ? 0 : "preserveStartEnd"} minTickGap={8} />
                <YAxis tick={tickStyle} width={40} domain={["auto", "auto"]} tickFormatter={(v: number) => `${v}%`} />
                <ReferenceLine y={0} stroke={SLATE} strokeWidth={1} />
                <Tooltip content={<ChartTooltip names={names} />} cursor={{ stroke: "#475569", strokeWidth: 1 }} />
                {bands && visible.filter(hasF).map((code) => (
                  <Area key={`${code}_b80`} dataKey={`${code}_b80`} stroke="none" fill={SLOTS[slots[code]]} fillOpacity={0.12}
                    isAnimationActive={false} connectNulls={false} activeDot={false} />
                ))}
                {bands && visible.filter(hasF).map((code) => (
                  <Area key={`${code}_b50`} dataKey={`${code}_b50`} stroke="none" fill={SLOTS[slots[code]]} fillOpacity={0.2}
                    isAnimationActive={false} connectNulls={false} activeDot={false} />
                ))}
                {visible.map((code) => (
                  <Line key={code} dataKey={code} stroke={SLOTS[slots[code]]} strokeWidth={2} dot={false} activeDot={{ r: 4 }}
                    isAnimationActive={false} connectNulls={false} />
                ))}
                {fcOn && visible.filter(hasF).map((code) => (
                  <Line key={`${code}_f`} dataKey={`${code}_f`} stroke={SLOTS[slots[code]]} strokeWidth={2} strokeDasharray="6 4"
                    dot={false} activeDot={{ r: 4 }} isAnimationActive={false} connectNulls />
                ))}
                {endLabels.length > 0 && <Customized component={(p: object) => <EndLabels {...p} labels={endLabels} />} />}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="mt-3 text-[12px] text-slate-500">{selected.length && !visible.length ? "The aggregates selected have no per-person series: pick an economy, or switch to GDP." : "Pick at least one economy and a range with data."}</p>
        )}
        <p className="mt-1 text-[10px] text-slate-500">
          {fcOn && visible.length > BAND_MAX ? `Bands hidden with more than ${BAND_MAX} economies shown. ` : ""}
          {showFc && hi < latest ? "The projection shows when the range reaches the latest quarter. " : ""}
          Sources: OECD quarterly national accounts; IMF World Economic Outlook (population, shares, projections).
          {bands && <InfoTip entry={TIPS.band} />}
        </p>

        <div className="mt-3 overflow-x-auto" data-testid="gdp-table">
          <table className="w-full min-w-[720px] text-[11px]">
            <thead>
              <tr className="text-slate-500">
                <th className="px-2 py-1 text-left font-medium">economy</th>
                <th className="px-2 py-1 text-right font-medium">share<InfoTip entry={TIPS.share} /></th>
                <th className="px-2 py-1 text-left font-medium">latest</th>
                <th className="px-2 py-1 text-right font-medium">growth</th>
                <th className="px-2 py-1 text-right font-medium">per person</th>
                <th className="px-2 py-1 text-right font-medium">trend{measure === "per_capita" ? " (GDP)" : ""}<InfoTip entry={TIPS.gdp} /></th>
                <th className="px-2 py-1 text-right font-medium">rule{measure === "per_capita" ? " per person" : ""}, 4 quarters on<InfoTip entry={TIPS.projection} /></th>
                <th className="px-2 py-1 text-right font-medium">80% band{measure === "per_capita" ? " (per person)" : ""}<InfoTip entry={TIPS.band} /></th>
                <th className="px-2 py-1 text-right font-medium">IMF {Object.keys(sel.find((c) => c.imf)?.imf ?? {}).join(" / ")}{measure === "per_capita" ? " (GDP)" : ""}<InfoTip entry={TIPS.imf} /></th>
                <th className="px-2 py-1 text-right font-medium">record<InfoTip entry={TIPS.record} /></th>
              </tr>
            </thead>
            <tbody>
              {sel.map((c) => {
                const g = c.series?.gdp ?? [];
                const p = c.series?.per_capita ?? [];
                const f = c.forecast;
                const fv = measure === "gdp" ? f?.gdp : f?.per_capita;
                const b = (measure === "gdp" ? f?.band80.gdp : f?.band80.per_capita)?.[3];
                const trend = isNum(f?.trend_qoq_pct) ? 100 * ((1 + (f!.trend_qoq_pct as number) / 100) ** 4 - 1) : null;
                const rec = c.record;
                return (
                  <tr key={c.code} className="border-t border-panelborder/60">
                    <td className="px-2 py-1 text-slate-200"><span className="mr-1.5 inline-block h-2 w-3 rounded-sm" style={{ background: SLOTS[slots[c.code]] }} />{c.name}</td>
                    <td className="px-2 py-1 text-right font-mono text-slate-400">{isNum(c.share_world_pct) ? `${c.share_world_pct.toFixed(1)}%` : "agg."}</td>
                    <td className="px-2 py-1 font-mono text-slate-500">{c.last ?? "n/a"}</td>
                    <td className="px-2 py-1 text-right font-mono text-slate-200">{pct(g[g.length - 1])}</td>
                    <td className="px-2 py-1 text-right font-mono text-slate-300">{pct(p[p.length - 1])}</td>
                    <td className="px-2 py-1 text-right font-mono text-slate-400">{pct(trend)}</td>
                    <td className="px-2 py-1 text-right font-mono text-slate-200">{f && fv ? `${pct(fv[3])} (${f.quarters[3]})${f.line_vs_band ? "*" : ""}` : c.aggregate ? "not projected" : "n/a"}</td>
                    <td className="px-2 py-1 text-right font-mono text-slate-400">{b ? `${pct(b[0])} to ${pct(b[1])}${rec?.band_in_sample_only ? "‡" : ""}` : "n/a"}</td>
                    <td className="px-2 py-1 text-right font-mono text-slate-400">{c.imf ? Object.values(c.imf).map((v) => pct(v)).join(" / ") + (fiscal(c) ? "†" : "") : "n/a"}</td>
                    <td className={`px-2 py-1 text-right font-mono ${rec?.naive_better ? "text-amber-300" : "text-slate-400"}`}>
                      {isNum(rec?.skill_h4_pct) ? `${rec!.skill_h4_pct! > 0 ? "+" : ""}${rec!.skill_h4_pct}% vs naive` : "n/a"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {notes.length > 0 && (
          <ul className="mt-1 space-y-0.5 text-[10px] leading-snug text-slate-500" data-testid="gdp-notes">
            {notes.map((x) => <li key={x}>{x}</li>)}
          </ul>
        )}

        {(data.summaries ?? []).length > 0 && (
          <div className="mt-4 rounded-lg border border-sky-900/50 bg-sky-950/20 px-3 py-2" data-testid="gdp-takeaways">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-sky-300/80">What this means</div>
            <ul className="mt-1 list-disc space-y-1 pl-4 text-[12px] leading-snug text-slate-300">
              {(data.summaries ?? []).map((x, i) => <li key={i}>{x}</li>)}
            </ul>
          </div>
        )}
      </Panel>

      <Panel title="How the projection was tested" subtitle={data.method?.study ?? "studies/gdp-watch.md"}>
        {pooled && (
          <table className="w-full max-w-xl text-[11px]" data-testid="gdp-record">
            <thead>
              <tr className="text-slate-500">
                <th className="px-2 py-1 text-left font-medium">typical miss, points (pandemic quarters out)</th>
                {[1, 2, 3, 4].map((h) => <th key={h} className="px-2 py-1 text-right font-medium">{h}q ahead</th>)}
              </tr>
            </thead>
            <tbody>
              {(["N", "T", "A"] as const).map((k) => (
                <tr key={k} className={`border-t border-panelborder/60 ${k === data.record?.chosen ? "text-slate-100" : "text-slate-400"}`}>
                  <td className="px-2 py-1">{mName[k]}{k === data.record?.chosen ? " (shown)" : ""}</td>
                  {[1, 2, 3, 4].map((h) => <td key={h} className="px-2 py-1 text-right font-mono">{pooled[k]?.[String(h)]?.mae?.toFixed(2) ?? "n/a"}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="mt-2 text-[11px] text-slate-400">
          {pooled?.A?.["1"]?.n ? `${pooled.A["1"].n} projections per horizon, 20 economies, origins from ${data.record?.first_origin ?? "2006-Q1"}. ` : ""}
          {data.method?.name ?? ""}.
        </p>
        <div className="mt-3 rounded border border-slate-700 px-3 py-2" data-testid="gdp-honesty">
          <div className="text-[11px] font-semibold text-slate-300">Honesty box</div>
          <ul className="mt-1 list-disc space-y-1 pl-4 text-[11px] leading-snug text-slate-400">
            {(data.honesty ?? []).map((x, i) => <li key={i}>{x}</li>)}
          </ul>
        </div>
      </Panel>
    </div>
  );
}
