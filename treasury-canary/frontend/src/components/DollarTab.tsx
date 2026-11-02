import { Component, useEffect, useState, type ReactNode } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DollarWatch, DwFiring, DwFundingRow, DwLedgerEntry, DwOutcomes, DwSeries, DwStatus } from "../lib/api";
import { api } from "../lib/api";
import { errorMessage } from "../lib/format";
import { DOLLAR_ALL_NULL, DOLLAR_FIXTURE } from "../lib/dollarFixture";
import { InlineError, Loading, Panel } from "./ui";

/* Dollar watch — studies/dollar-watch.md §5, §9. DESCRIPTIVE: what the dollar and
   the dollar-funding plumbing are doing against their own history, with the
   in-sample record beside every reading (each conditional count with its N and
   base rate; no rate on cells built from fewer than ~15 independent episodes).
   No forecast, no odds, no colour-coded states: status chips report data
   freshness only, and every series is drawn in the same neutral palette. The
   payload is the contract; any block may be null or "error", so every section
   reads defensively and degrades to a muted "unavailable" line. */

// Fixed identities (validated with the dataviz palette checker on the panel surface).
const BLUE = "#3987e5"; // the primary series in every chart
const ORANGE = "#d95926"; // the second series where two share an axis
const VIOLET = "#9085e9"; // dated events (rule firings, swap-line announcements)
const SLATE = "#64748b";
const GRID = "#1e293b";
const TOOLTIP_STYLE = { background: "#0f172a", border: "1px solid #334155", fontSize: 11 };
const tickStyle = { fontSize: 9, fill: SLATE };
const LIST_NAME: Record<string, string> = { A25: "A25 (25 crises)", C16: "C16 (16 dollar-stress onsets)", N5: "N5 (5 funding squeezes)" };

// ---------------------------------------------------------------------------- defensive helpers
function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}
function str(v: unknown): string | null {
  return typeof v === "string" && v.length > 0 ? v : null;
}
function arr<T>(v: T[] | null | undefined): T[] {
  return Array.isArray(v) ? v : [];
}
function fmt(v: unknown, d = 1): string {
  if (!isNum(v)) return "n/a";
  const x = Math.abs(v) < 0.5 * 10 ** -d ? 0 : v; // never "-0.0"
  return x.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
}
function sgn(v: unknown, d = 1): string {
  if (!isNum(v)) return "n/a";
  const s = fmt(v, d);
  return s !== "n/a" && v > 0 && s.replace(/[0.,]/g, "") !== "" ? `+${s}` : s;
}
function pct(v: unknown, d = 1): string {
  return isNum(v) ? `${sgn(v, d)}%` : "n/a";
}
function pp(v: unknown, d = 2): string {
  return isNum(v) ? `${sgn(v, d)}pp` : "n/a";
}
function unit(v: unknown, d: number, u: string): string {
  return isNum(v) ? `${fmt(v, d)}${u}` : "n/a";
}
function usd(v: unknown, d: number, suffix = ""): string {
  return isNum(v) ? `$${fmt(v, d)}${suffix}` : "n/a";
}
function share(v: unknown): string {
  return isNum(v) ? `${Math.round(v * 100)}%` : "n/a";
}
function ord(v: unknown): string {
  if (!isNum(v)) return "n/a";
  const n = Math.round(v);
  const s = n % 100 >= 10 && n % 100 <= 20 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${s}`;
}
function pctile(v: unknown, since?: string | null): string {
  if (!isNum(v)) return "n/a";
  return `${ord(v)} percentile${since ? ` since ${since.slice(0, 4)}` : ""}`;
}
function yes(v: unknown): string {
  return v === true ? "met" : v === false ? "not met" : "n/a";
}
function ts(d: string): number {
  const t = Date.parse(d.length === 7 ? `${d}-15` : d);
  return Number.isFinite(t) ? t : NaN;
}
function yearTick(t: number): string {
  return Number.isFinite(t) ? String(new Date(t).getUTCFullYear()) : "";
}
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function monthTick(t: number): string {
  if (!Number.isFinite(t)) return "";
  const d = new Date(t);
  return `${MON[d.getUTCMonth()]} ${String(d.getUTCFullYear()).slice(2)}`;
}
function dayLabel(t: unknown): string {
  return isNum(t) ? new Date(t).toISOString().slice(0, 10) : "";
}
// Firing markers closer than ~3 months share one label ("1-2") so the numbers never overprint.
function mergeLabels(refs: Array<{ t: number; label?: string }>): Array<{ t: number; label?: string }> {
  const out: Array<{ t: number; label?: string; first?: string }> = [];
  let head: { t: number; label?: string; first?: string } | null = null;
  for (const r of refs) {
    if (head && r.t - head.t < 90 * 864e5) {
      head.label = `${head.first ?? head.label}-${r.label ?? ""}`;
      out.push({ t: r.t });
    } else {
      head = { ...r, first: r.label };
      out.push(head);
    }
  }
  return out.map((r) => ({ t: r.t, label: r.label }));
}
function seriesRows(s: DwSeries | null | undefined): Array<{ t: number; v: number }> {
  const ds = arr(s?.dates);
  const vs = arr(s?.values);
  const out: Array<{ t: number; v: number }> = [];
  ds.forEach((d, i) => {
    const v = vs[i];
    const t = typeof d === "string" ? ts(d) : NaN;
    if (isNum(v) && Number.isFinite(t)) out.push({ t, v });
  });
  return out;
}
function srcOf(s: unknown): string | null {
  if (typeof s === "string") return s;
  if (Array.isArray(s)) return s.find((x) => typeof x === "string") ?? null;
  return null;
}
function sentences(...parts: Array<string | null | undefined>): string {
  return parts.filter((p): p is string => typeof p === "string" && p.length > 0).map((p) => (/[.!?]$/.test(p) ? p : `${p}.`)).join(" ");
}

// ---------------------------------------------------------------------------- small pieces
function DataChip({ status }: { status: DwStatus | null | undefined }) {
  const s = status === "ok" || status === "stale" || status === "error" ? status : null;
  const title = s === "ok" ? "fetched live" : s === "stale" ? "served from cache, or partly off-basis: see the notes" : "the source fetch failed";
  return (
    <span className="whitespace-nowrap rounded border border-slate-700 px-1.5 py-0.5 font-mono text-[10px] text-slate-400" title={title}>
      data: {s ?? "n/a"}
    </span>
  );
}

function Unavailable({ what, why }: { what: string; why?: string | null }) {
  return (
    <div className="rounded border border-dashed border-slate-700/70 bg-slate-900/30 px-3 py-2 text-xs text-slate-500">
      {what} unavailable{why ? ` (${why})` : ""}.
    </div>
  );
}

class Boundary extends Component<{ what: string; children: ReactNode }, { err: string | null }> {
  state = { err: null as string | null };
  static getDerivedStateFromError(e: unknown) {
    return { err: errorMessage(e) };
  }
  render() {
    if (this.state.err) return <Unavailable what={this.props.what} why={`render failed: ${this.state.err}`} />;
    return this.props.children;
  }
}

function Section({ title, subtitle, status, basis, children }: { title: string; subtitle?: string; status?: DwStatus | null; basis?: string | null; children: ReactNode }) {
  return (
    <Panel title={title} subtitle={subtitle} right={<DataChip status={status} />}>
      <Boundary what={title}>{children}</Boundary>
      {basis && <p className="mt-3 text-[10px] leading-snug text-slate-600">Basis: {basis}</p>}
    </Panel>
  );
}

function Src({ href }: { href: unknown }) {
  const u = srcOf(href);
  if (!u || !/^https?:\/\//.test(u)) return null;
  return (
    <a href={u} target="_blank" rel="noreferrer" className="text-slate-500 underline decoration-slate-700 hover:text-slate-300">
      source
    </a>
  );
}

function AsOf({ asof, intraday }: { asof: unknown; intraday?: unknown }) {
  return (
    <>
      as of {str(asof) ?? "n/a"}
      {intraday === true ? " (intraday)" : ""}
    </>
  );
}

function Tile({ label, value, sub, asof, intraday, src }: { label: string; value: string; sub?: ReactNode; asof?: unknown; intraday?: unknown; src?: unknown }) {
  return (
    <div className="rounded-lg border border-panelborder bg-slate-900/40 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-0.5 font-mono text-lg font-semibold tabular-nums text-slate-100">{value}</div>
      {sub && <div className="mt-0.5 text-[11px] leading-snug text-slate-400">{sub}</div>}
      <div className="mt-1 font-mono text-[10px] text-slate-500">
        <AsOf asof={asof} intraday={intraday} /> <Src href={src} />
      </div>
    </div>
  );
}

function Th({ children, right = false }: { children: ReactNode; right?: boolean }) {
  return <th className={`px-2 py-1 font-medium text-slate-500 ${right ? "text-right" : "text-left"}`}>{children}</th>;
}
function Td({ children, right = false, mono = false }: { children: ReactNode; right?: boolean; mono?: boolean }) {
  return <td className={`px-2 py-1 ${right ? "text-right" : ""} ${mono ? "whitespace-nowrap font-mono tabular-nums" : ""} text-slate-300`}>{children}</td>;
}

function Note({ children }: { children: ReactNode }) {
  return <p className="mt-2 text-[11px] leading-snug text-slate-400">{children}</p>;
}

function TimeChart({
  rows,
  unit: u,
  digits = 1,
  refY = [],
  refX = [],
  height = 200,
}: {
  rows: Array<{ t: number; v: number }>;
  unit: string;
  digits?: number;
  refY?: Array<{ y: number }>;
  refX?: Array<{ t: number; label?: string }>;
  height?: number;
}) {
  if (rows.length < 2) return <Unavailable what="Series" />;
  const span = rows[rows.length - 1].t - rows[0].t;
  const tickFmt = span < 6 * 365 * 864e5 ? monthTick : yearTick;
  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 12, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={tickFmt} tick={tickStyle} minTickGap={36} />
          <YAxis tick={tickStyle} width={44} domain={["auto", "auto"]} tickFormatter={(v: number) => fmt(v, digits)} />
          <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={dayLabel} formatter={(v: number) => [`${fmt(v, digits)}${u ? ` ${u}` : ""}`, ""]} />
          {refY.map((r) => (
            <ReferenceLine key={`y${r.y}`} y={r.y} stroke={SLATE} strokeDasharray="4 3" />
          ))}
          {refX.map((r, i) => (
            <ReferenceLine key={`x${i}`} x={r.t} stroke={VIOLET} strokeDasharray="2 3" label={r.label ? { value: r.label, fill: VIOLET, fontSize: 9, position: "top" } : undefined} />
          ))}
          <Line type="monotone" dataKey="v" stroke={BLUE} strokeWidth={1.5} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function OutcomeCell({ o }: { o: DwOutcomes | null | undefined }) {
  const x = o?.["12m"];
  if (!x) return <span className="text-slate-600">pending</span>;
  return (
    <span className="font-mono text-[10px] tabular-nums">
      S&amp;P {pct(x.spx_pct)} · Baa−10y {pp(x.baa10y_pp ?? x.baa_minus_10y_pp)}
    </span>
  );
}

// ---------------------------------------------------------------------------- layer 1
function StateLayer({ d }: { d: DollarWatch }) {
  const s = d.state;
  if (!s) return <Unavailable what="Dollar state" />;
  const dx = s.dxy;
  const band = s.band;
  const mon = dx?.monthly;
  const rows = arr(mon?.months)
    .map((m, i) => ({ t: ts(m), v: arr(mon?.close)[i] }))
    .filter((r): r is { t: number; v: number } => isNum(r.v) && Number.isFinite(r.t));
  const q = s.quadrant;
  const qc = q?.onsets_C16?.counts ?? {};
  const qbc = q?.base_all_months?.counts ?? {};
  const qbm = q?.base_all_months?.months;
  const mom = s.momentum;
  const g = s.safe_haven?.gold;
  const gr = s.safe_haven?.gold_record;
  const lists = ["A25", "C16", "N5"];
  return (
    <>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <Tile label="ICE DXY" value={fmt(dx?.latest, 2)} asof={dx?.asof} intraday={dx?.intraday} src={dx?.src}
          sub={<>{str(dx?.band_position) ?? "n/a"}; {pct(dx?.chg_6m_pct)} 6m, {pct(dx?.chg_12m_pct)} 12m (daily); {isNum(dx?.pct_own_history) ? `${ord(dx?.pct_own_history)} percentile of month-end closes since 1971` : "percentile n/a"}</>} />
        <Tile label="Fed broad dollar" value={fmt(s.broad?.broad?.latest, 1)} asof={s.broad?.broad?.asof} src={s.broad?.broad?.src}
          sub={<>{pct(s.broad?.broad?.chg_6m_pct)} 6m, {pct(s.broad?.broad?.chg_12m_pct)} 12m; {isNum(s.broad?.broad?.pct_10y) ? `${ord(s.broad?.broad?.pct_10y)} percentile, last 10 yrs` : "percentile n/a"}; high since 2006 {fmt(s.broad?.high_since_2006?.value, 1)} ({str(s.broad?.high_since_2006?.date) ?? "n/a"})</>} />
        <Tile label="vs advanced / EM economies" value={`${fmt(s.broad?.afe?.latest, 1)} / ${fmt(s.broad?.eme?.latest, 1)}`} asof={s.broad?.afe?.asof} src={s.broad?.afe?.src}
          sub={<>12m {pct(s.broad?.afe?.chg_12m_pct)} / {pct(s.broad?.eme?.chg_12m_pct)}</>} />
        <Tile label="Dollar-yield quadrant" value={str(q?.label) ?? "n/a"} asof={q?.month}
          sub={<>3 months to {str(q?.month) ?? "n/a"}: DXY {pct(q?.dxy_3m_pct)}, 10y {pp(q?.y10_3m_pp)}</>} />
      </div>
      {arr(s.issues).length > 0 && <Note>Data note: {arr(s.issues).join("; ")}.</Note>}

      <div className="mt-4">
        <div className="mb-1 text-xs text-slate-400">ICE DXY, month-end close, 1971 to now. Dashed lines at 85 and 105: {str(band?.label) ?? "Johnson's ad hoc band"}</div>
        <TimeChart rows={rows} unit="" digits={0} refY={[{ y: band?.lo ?? 85 }, { y: band?.hi ?? 105 }]} height={230} />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <div className="mb-1 text-xs font-semibold text-slate-300">Outside the band: what followed ({band?.by_list?.A25?.n_excursions ?? "n/a"} excursions)</div>
          <table className="w-full text-[11px]">
            <thead><tr><Th>crisis list</Th><Th right>onset within 12m</Th><Th right>base</Th><Th right>within 24m</Th><Th right>base</Th></tr></thead>
            <tbody>
              {lists.map((k) => {
                const r = band?.by_list?.[k] ?? {};
                return (
                  <tr key={k}><Td>{LIST_NAME[k]}</Td><Td right mono>{r.hits_12m ?? "n/a"} of {r.n_excursions ?? "n/a"} ({share(r.rate_12m)})</Td><Td right mono>{share(r.base_12m)}</Td>
                    <Td right mono>{r.hits_24m ?? "n/a"} of {r.n_excursions ?? "n/a"} ({share(r.rate_24m)})</Td><Td right mono>{share(r.base_24m)}</Td></tr>
                );
              })}
            </tbody>
          </table>
          <Note>{str(band?.note) ?? ""}</Note>
          <p className="mt-1 text-[10px] text-slate-600">Basis: {str(band?.basis) ?? "n/a"}</p>
          {arr(band?.excursions).length > 0 && (
            <details className="mt-1 text-[11px] text-slate-400">
              <summary className="cursor-pointer text-slate-500">The {arr(band?.excursions).length} excursions</summary>
              <table className="mt-1 w-full text-[10px]">
                <thead><tr><Th>side</Th><Th>from</Th><Th>to</Th><Th right>months</Th><Th right>extreme</Th><Th>began inside an A25 crisis</Th></tr></thead>
                <tbody>
                  {arr(band?.excursions).map((e, i) => (
                    <tr key={i}><Td>{e.side}</Td><Td mono>{e.start}</Td><Td mono>{e.end}</Td><Td right mono>{e.months}</Td><Td right mono>{fmt(e.extreme, 1)} ({e.extreme_month})</Td><Td>{e.began_inside_crisis_A25 ? "yes" : "no"}</Td></tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}
        </div>
        <div>
          <div className="mb-1 text-xs font-semibold text-slate-300">The quadrant into crisis onsets (C16, {q?.onsets_C16?.n ?? "n/a"} onsets)</div>
          <table className="w-full text-[11px]">
            <thead><tr><Th>3-month quadrant</Th><Th right>onsets</Th><Th right>all months 1971-2026</Th></tr></thead>
            <tbody>
              {["usd_up_yld_down", "usd_up_yld_up", "usd_down_yld_up", "usd_down_yld_down"].map((k) => (
                <tr key={k} className={q?.quadrant === k ? "font-semibold" : ""}>
                  <Td>{q?.labels?.[k] ?? k}{q?.quadrant === k ? " (now)" : ""}</Td><Td right mono>{qc[k] ?? "n/a"} of {q?.onsets_C16?.n ?? "n/a"}</Td>
                  <Td right mono>{isNum(qbc[k]) && isNum(qbm) ? `${qbc[k]} of ${qbm} (${Math.round((100 * qbc[k]) / qbm)}%)` : "n/a"}</Td>
                </tr>
              ))}
            </tbody>
          </table>
          <Note>In-sample on {q?.onsets_C16?.n ?? "n/a"} onsets: a label, not a forecast.</Note>
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div data-testid="momentum-table">
          <div className="mb-1 text-xs font-semibold text-slate-300">12-month DXY change (monthly averages): {pct(mom?.dxy_12m_pct)} to {str(mom?.month) ?? "n/a"}; above +{fmt(mom?.threshold_pct, 0)}%: {mom?.signal === true ? "yes" : mom?.signal === false ? "no" : "n/a"} (last {str(mom?.last_signal_month) ?? "n/a"})</div>
          <table className="w-full text-[11px]">
            <thead><tr><Th>crisis list</Th><Th right>episodes followed by an onset within 12m</Th><Th right>months above +10% followed (overlapping)</Th><Th right>base (share of all months)</Th></tr></thead>
            <tbody>
              {lists.map((k) => {
                const r = mom?.by_list?.[k] ?? {};
                return (
                  <tr key={k}><Td>{LIST_NAME[k]}</Td><Td right mono>{r.episodes_followed_12m ?? "n/a"} of {r.episodes ?? "n/a"}</Td>
                    <Td right mono>{r.signal_months_followed_12m ?? "n/a"} of {r.signal_months ?? "n/a"}</Td><Td right mono>{share(r.base_12m)}</Td></tr>
                );
              })}
            </tbody>
          </table>
          <Note>{str(mom?.caveat) ?? ""}</Note>
        </div>
        <div>
          <div className="mb-1 text-xs font-semibold text-slate-300">Safe havens and EM</div>
          <div className="grid grid-cols-2 gap-2">
            <Tile label={g?.provider === "yahoo" ? "Gold (COMEX futures)" : "Gold (spot)"} value={usd(g?.latest, 0)} asof={g?.asof} intraday={g?.intraday} src={g?.src}
              sub={sentences(`${pct(g?.chg_6m_pct)} 6m; ${pct(g?.off_52w_high_pct)} from its 52-week high${str(g?.note) ? `, ${g?.note}` : ""}`)} />
            <Tile label="EM FX basket" value={fmt(s.emfx?.latest, 1)} asof={s.emfx?.asof}
              sub={<>{pct(s.emfx?.chg_12m_pct)} 12m (up = EM weaker); {isNum(s.emfx?.pct_10y) ? `${ord(s.emfx?.pct_10y)} percentile, last 10 yrs` : "percentile n/a"}</>} />
            <Tile label="CHF / JPY per $ (up = franc / yen weaker)" value={`${fmt(s.safe_haven?.chf?.latest, 3)} / ${fmt(s.safe_haven?.jpy?.latest, 1)}`} asof={s.safe_haven?.chf?.asof}
              sub={<>6m {pct(s.safe_haven?.chf?.chg_6m_pct)} / {pct(s.safe_haven?.jpy?.chg_6m_pct)}; 12m {pct(s.safe_haven?.chf?.chg_12m_pct)} / {pct(s.safe_haven?.jpy?.chg_12m_pct)}</>} />
            <Tile label="Brent" value={usd(s.brent?.latest, 1)} asof={s.brent?.asof} src={s.brent?.src}
              sub={<>{pct(s.brent?.chg_12m_pct)} 12m; {pctile(s.brent?.pct_own_history, s.brent?.history_from)}</>} />
          </div>
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <div className="mb-1 text-xs font-semibold text-slate-300">Gold in crises</div>
          <table className="w-full text-[11px]">
            <thead><tr><Th>episode</Th><Th right>intra-crisis drawdown</Th><Th right>close-to-close</Th></tr></thead>
            <tbody>
              {arr(gr?.drawdowns).map((x, i) => (
                <tr key={i}><Td>{String(x.episode ?? "")}</Td><Td right mono>{pct(x.intraday_pct ?? x.monthly_avg_pct)}{isNum(x.monthly_avg_pct) ? " (monthly)" : ""}</Td>
                  <Td right mono>{isNum(x.close_pct) ? pct(x.close_pct) : "monthly only"}</Td></tr>
              ))}
            </tbody>
          </table>
          <Note>{str(s.safe_haven?.note) ?? ""}</Note>
        </div>
        <div>
          <div className="mb-1 text-xs font-semibold text-slate-300">When the dollar story did not hold</div>
          <ul className="space-y-1 text-[11px] text-slate-400">
            {arr(s.counter_examples).map((c, i) => (
              <li key={i}><span className="font-mono text-slate-500">{c.when}</span> {c.text}</li>
            ))}
          </ul>
        </div>
      </div>
      <div className="mt-4">
        <div className="mb-1 text-xs text-slate-400">EM FX basket (8 FRED pairs; {str(s.emfx?.unit) ?? "index"})</div>
        <TimeChart rows={seriesRows(s.emfx?.series)} unit="" digits={0} height={170} />
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------- layer 2
function fundingNow(r: DwFundingRow): string {
  if (r.unit === "$") return usd(r.latest, 2);
  if (r.unit === "$bn") return usd(r.latest, 2, "bn");
  if (r.unit === "bp") return unit(r.latest, 0, " bp");
  if (r.unit === "pp") return unit(r.latest, 2, " pp");
  return fmt(r.latest, 2);
}

function FundingLayer({ d }: { d: DollarWatch }) {
  const f = d.funding;
  if (!f) return <Unavailable what="Dollar-funding nowcast" />;
  const ll = f.leadlag;
  const eps = ["2008", "2015-16", "2018", "2020", "2022"];
  const swapRefs = arr(f.swap_events).map((e) => ({ t: ts(e.date) })).filter((x) => Number.isFinite(x.t));
  return (
    <>
      <div className="mb-2 text-[11px] text-slate-400">{str(f.label) ?? ""}</div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-[11px]">
          <thead><tr><Th>gauge</Th><Th right>now</Th><Th>as of</Th><Th right>percentile, own history</Th><Th right>percentile, last 10 yrs</Th><Th right>1y median</Th><Th>reading</Th></tr></thead>
          <tbody>
            {arr(f.rows).map((r: DwFundingRow) => (
              <tr key={r.id} className="border-t border-slate-800/70">
                <Td>{r.label} <Src href={r.src} /></Td>
                <Td right mono>{fundingNow(r)}</Td>
                <Td mono><AsOf asof={r.asof} intraday={r.intraday} /></Td>
                <Td right mono>{pctile(r.pct_own_history, r.history_from)}</Td>
                <Td right mono>{isNum(r.pct_10y) ? ord(r.pct_10y) : "n/a"}</Td>
                <Td right mono>{r.unit === "$" ? usd(r.median_1y, 2) : fmt(r.median_1y, r.unit === "bp" ? 0 : 2)}</Td>
                <Td>
                  <span className="text-slate-500">
                    {r.id === "emb" ? `${pct(r.chg_1m_pct)} 1m; ${pct(r.off_52w_high_pct)} vs 52-week high; ` : ""}
                    {str(r.direction) ?? ""}
                    {str(r.note) ? ` (${r.note})` : ""}
                  </span>
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <div>
          <div className="mb-1 text-xs text-slate-400">Financial CP minus 3-month bill, pp (weekly)</div>
          <TimeChart rows={seriesRows(f.series?.cp_fin)} unit="pp" digits={2} height={160} />
        </div>
        <div>
          <div className="mb-1 text-xs text-slate-400">OFR stress index, funding (0 = average)</div>
          <TimeChart rows={seriesRows(f.series?.ofr_funding)} unit="" digits={1} height={160} refY={[{ y: 0 }]} />
        </div>
        <div>
          <div className="mb-1 text-xs text-slate-400">Fed swap lines outstanding, $bn (dotted: Fed announcements)</div>
          <TimeChart rows={seriesRows(f.series?.swap_lines)} unit="$bn" digits={0} height={160} refX={swapRefs} />
        </div>
      </div>
      <div className="mt-4 overflow-x-auto">
        <div className="mb-1 text-xs font-semibold text-slate-300">Lead / lag against the broad dollar's peak (calendar days; minus = before the dollar peaked)</div>
        <table className="w-full min-w-[760px] text-[11px]">
          <thead><tr><Th>series</Th><Th>reading</Th>{eps.map((e) => <Th key={e}>{e} (dollar peak {ll?.dollar_peaks?.[e] ?? "n/a"})</Th>)}</tr></thead>
          <tbody>
            {arr(ll?.rows).map((r, i) => (
              <tr key={i} className="border-t border-slate-800/70"><Td>{r.series}</Td><Td><span className="text-slate-400">{r.label ?? ""}</span></Td>{eps.map((e) => <Td key={e} mono>{r[e] ?? "n/a"}</Td>)}</tr>
            ))}
          </tbody>
        </table>
        <Note>{str(ll?.basis) ?? ""}</Note>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------- layer 3
function ScrambleLayer({ d }: { d: DollarWatch }) {
  const sc = d.scramble;
  if (!sc) return <Unavailable what="Dollar-scramble gauge" />;
  const st = sc.state;
  const hist = arr(sc.history);
  const long = seriesRows(sc.series_long);
  const fireRefs = mergeLabels(hist.map((f, i) => ({ t: ts(f.date), label: String(i + 1) })).filter((x) => Number.isFinite(x.t)));
  const liveRefs = arr(sc.live_firings).map((f) => ({ t: ts(f.date), label: "live" })).filter((x) => Number.isFinite(x.t));
  const roc = arr(sc.series?.dates)
    .map((dd, i) => ({ t: ts(dd), v: arr(sc.series?.roc20_pct)[i] }))
    .filter((r): r is { t: number; v: number } => isNum(r.v) && Number.isFinite(r.t));
  const ind = sc.indicators;
  const conf = sc.confirmations;
  const mn = sc.monthly_null;
  const unpatched = arr(sc.history_unpatched);
  return (
    <>
      <div className="rounded border border-slate-700 bg-slate-900/40 px-3 py-2 text-[12px] text-slate-300">
        {!st ? (
          "Rule state unavailable."
        ) : sc.gate_open ? (
          <>Gate open on {st.asof}: the broad dollar's largest 20-day climb in the last 60 index days is {pct(st.roc20_max_60d_pct, 2)} ({st.roc20_max_date}) and the 10-year
            ({unit(st.y10_now, 2, "%")}) is below its level before the climb ({unit(st.y10_ref, 2, "%")} on {st.y10_ref_date}). The three readings below are shown separately and never added up.</>
        ) : (
          <>Gate closed on {st.asof}: the largest 20-day climb in the last 60 index days is {pct(st.roc20_max_60d_pct, 2)} ({st.roc20_max_date}); the gauge opens at +4% with the 10-year falling
            (10-year {unit(st.y10_now, 2, "%")} vs {unit(st.y10_ref, 2, "%")} before the climb). No dollar scramble is under way on this definition.</>
        )}
      </div>

      {sc.gate_open && ind && (
        <div className="mt-3 grid gap-2 md:grid-cols-3">
          {(
            [
              ["(a) deceleration", ind.a_deceleration, `20-day climb ${pct(ind.a_deceleration?.roc20_now_pct as number, 2)} vs max ${pct(ind.a_deceleration?.roc20_max_60d_pct as number, 2)}; dollar ${pct(ind.a_deceleration?.dollar_vs_60d_high_pct as number, 2)} vs 60-day high`],
              ["(b) funding easing", ind.b_funding_easing, `CP-bill ${fmt(ind.b_funding_easing?.cp_now as number, 2)} vs median ${fmt(ind.b_funding_easing?.cp_median_1y as number, 2)}; OFR funding ${fmt(ind.b_funding_easing?.ofr_funding_now as number, 2)} vs ${fmt(ind.b_funding_easing?.ofr_funding_median_1y as number, 2)}`],
              ["(c) gold and EM bonds turning", ind.c_risk_turn, `gold ${fmt(ind.c_risk_turn?.gold_now as number, 0)} vs prior 20-day high ${fmt(ind.c_risk_turn?.gold_prior_20d_high as number, 0)}; EMB ${fmt(ind.c_risk_turn?.emb_now as number, 2)} vs ${fmt(ind.c_risk_turn?.emb_prior_20d_high as number, 2)}`],
            ] as const
          ).map(([name, x, detail]) => (
            <div key={name} className="rounded border border-panelborder bg-slate-900/40 px-3 py-2">
              <div className="text-[11px] font-semibold text-slate-300">{name}: {yes(x?.met)}{name.startsWith("(a)") && x?.met ? ` (${str(sc.wording) ?? ""})` : ""}</div>
              <div className="mt-1 font-mono text-[10px] text-slate-400">{detail}</div>
              <div className="mt-1 text-[10px] text-slate-500">{str(x?.rule) ?? ""}</div>
            </div>
          ))}
          <div className="rounded border border-panelborder bg-slate-900/40 px-3 py-2 text-[11px] text-slate-400 md:col-span-3">
            Confirmations since {str(conf?.episode_start) ?? "n/a"}: dollar {pct(conf?.dollar_off_peak_pct, 2)} from its episode peak ({yes(conf?.dollar_3pct_off_peak)} at 3%);
            swap lines {usd(conf?.swap_now_bn, 1, "bn")} vs {usd(conf?.swap_episode_peak_bn, 1, "bn")} at the peak ({conf?.swap_below_10pct_of_peak == null ? "n/a: no material draw" : yes(conf?.swap_below_10pct_of_peak)} at 10%).
          </div>
        </div>
      )}

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <div className="mb-1 text-xs text-slate-400">Fed broad dollar, 2006 to now; dotted lines = the rule's in-sample firings, numbered as in the table</div>
          <TimeChart rows={long} unit="" digits={0} refX={[...fireRefs, ...liveRefs]} height={210} />
        </div>
        <div>
          <div className="mb-1 text-xs text-slate-400">20-day change of the broad dollar, %, last ~3 years (gauge opens at +4% with the 10-year falling)</div>
          <TimeChart rows={roc} unit="%" digits={1} refY={[{ y: 4 }, { y: 0 }]} height={210} />
        </div>
      </div>

      <div className="mt-4 overflow-x-auto">
        <div className="mb-1 text-xs font-semibold text-slate-300">
          Every firing of the rule, in-sample: {unpatched.length || "n/a"} under the unpatched rule (the default) plus the re-arm variant's 2008-11-06, added after the 2008-09-22 miss
        </div>
        <table className="w-full min-w-[860px] text-[11px]">
          <thead><tr><Th>#</Th><Th>fired</Th><Th>variant</Th><Th right>largest 20d climb</Th><Th right>dollar rose further</Th><Th right>S&amp;P to next low: firing day / observable</Th><Th right>VIX change over 60d (points)</Th><Th>12 months later</Th><Th>reading</Th></tr></thead>
          <tbody>
            {hist.map((f: DwFiring, i) => (
              <tr key={f.date} className="border-t border-slate-800/70">
                <Td mono>{i + 1}</Td><Td mono>{f.date}</Td><Td>{str(f.variant) ?? "n/a"}</Td><Td right mono>{pct(f.roc20_max_pct)} ({str(f.roc20_max_date) ?? "n/a"})</Td>
                <Td right mono>{pct(f.dollar_further_rise_pct)}</Td><Td right mono>{pct(f.spx_to_next_low_pct)} / {pct(f.spx_to_next_low_from_observable_pct)}</Td><Td right mono>{sgn(f.vix_change_60d)}</Td>
                <Td><OutcomeCell o={f.outcomes} /></Td><Td><span className="text-slate-400">{str(f.reading) ?? ""}</span></Td>
              </tr>
            ))}
          </tbody>
        </table>
        <Note>{sentences(str(sc.variant_live) ? `${sc.variant_live!.charAt(0).toUpperCase()}${sc.variant_live!.slice(1)}` : null,
          `Live re-run on today's data up to ${str(sc.last_index_day) ?? "the cut-off"} reproduces these firings: ${sc.live_check?.reproduces_frozen_rearm === true && sc.live_check?.reproduces_frozen_unpatched === true ? "yes" : sc.live_check ? "no (data revised; see the study)" : "n/a"}`)}</Note>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <div className="rounded border border-slate-700 px-3 py-2 text-[11px] text-slate-300">
          <div className="font-semibold">The null, shown permanently</div>
          On {str(mn?.window) ?? "1973-2005 monthly data"}: {mn?.firings ?? "n/a"} firings; the dollar peaked within 3 months in {mn?.dollar_peak_within_3m ?? "n/a"} (base {share(mn?.base_dollar_peak_within_3m)});
          the S&amp;P was higher 12 months later in {mn?.spx_up_12m ?? "n/a"} (base {share(mn?.base_spx_up_12m)}). No edge.
        </div>
        <div className="rounded border border-slate-700 px-3 py-2 text-[11px] text-slate-300">
          <div className="font-semibold">Order at the end of a scramble (as dated in 2008 and 2020; n = 2)</div>
          {arr(sc.end_of_scramble?.order).map((o, i) => <span key={i}>{i + 1}. {o}{i < arr(sc.end_of_scramble?.order).length - 1 ? "; " : "."}</span>)}
          <div className="mt-1 text-slate-400">{str(sc.end_of_scramble?.case_2008) ?? ""}</div>
        </div>
        <div className="rounded border border-slate-700 px-3 py-2 text-[11px] text-slate-300">
          <div className="font-semibold">When the climb peaked (20-day change on the rule's index)</div>
          {arr(sc.vspike_timing).map((v, i) => (
            <div key={i}>{String(v.episode)}: climb {String(v.climb_peak)} ({pct(v.climb_peak_pct)}), VIX {String(v.vix_peak)}, dollar {String(v.dollar_peak)} ({pct(v.dollar_further_rise_after_climb_peak_pct)} more){str(v.note) ? `; ${v.note}` : ""}</div>
          ))}
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------- layer 4
function SlowLayer({ d }: { d: DollarWatch }) {
  const s = d.slow;
  if (!s) return <Unavailable what="Slow state" />;
  const uc = s.usd_credit;
  const qs = arr(uc?.series?.quarters);
  const rows = qs
    .map((q, i) => ({ t: ts(`${q.slice(0, 4)}-${String(Number(q.slice(-1)) * 3).padStart(2, "0")}-28`), credit: arr(uc?.series?.credit_yoy_pct)[i], dollar: arr(uc?.series?.dollar_yoy_pct)[i] }))
    .filter((r) => Number.isFinite(r.t));
  const h = uc?.history ?? {};
  const t = s.treasury;
  const a25 = t?.april_2025;
  const fx = s.fx_swaps;
  const pr = arr(s.policy_rates?.rows);
  return (
    <>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-5">
        <Tile label="USD credit outside the US" value={usd(uc?.total_tn, 2, "tn")} asof={uc?.quarter} src={uc?.src}
          sub={sentences(`${pct(uc?.yoy_pct)} yoy; EMEs ${usd(uc?.eme_tn, 2, "tn")} (${pct(uc?.eme_yoy_pct)} yoy, ${unit(uc?.eme_share_pct, 0, "%")} of the total)`, str(uc?.label))} />
        <Tile label="FX forwards and swaps outstanding" value={usd(fx?.all_tn, 1, "tn")} asof={fx?.period}
          sub={<>dollar leg {usd(fx?.usd_leg_tn, 1, "tn")}; {str(fx?.prev_period) ?? "previous"} {usd(fx?.prev_all_tn, 1, "tn")}</>} />
        <Tile label="US 2-year vs funds ceiling" value={`${unit(s.us2y_vs_funds?.dgs2, 2, "%")} / ${unit(s.us2y_vs_funds?.fed_upper, 2, "%")}`} asof={s.us2y_vs_funds?.dgs2_asof}
          sub={sentences(`gap ${pp(s.us2y_vs_funds?.gap_pp)}`, str(s.us2y_vs_funds?.reading))} />
        <Tile label="Foreign official custody" value={usd(t?.custody?.latest, 0, "bn")} asof={t?.custody?.asof} src={t?.custody?.src}
          sub={<>{pct(t?.custody?.chg_12m_pct)} 12m; {isNum(t?.custody?.pct_10y) ? `${ord(t?.custody?.pct_10y)} percentile, last 10 yrs` : "percentile n/a"}</>} />
        <Tile label="10-year yield / term premium" value={`${unit(t?.y10?.latest, 2, "%")} / ${unit(t?.term_premium?.latest, 2, "pp")}`} asof={t?.y10?.asof} src={t?.y10?.src}
          sub={<>10-year {pp(t?.y10_chg_6m_pp)} in 6 months; term premium as of {str(t?.term_premium?.asof) ?? "n/a"}</>} />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <div className="mb-1 text-xs text-slate-400">USD credit outside the US vs the broad dollar, yoy % (quarterly)</div>
          {rows.length < 2 ? <Unavailable what="Credit series" /> : (
            <div style={{ width: "100%", height: 200 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={yearTick} tick={tickStyle} minTickGap={28} />
                  <YAxis tick={tickStyle} width={36} tickFormatter={(v: number) => fmt(v, 0)} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={dayLabel} formatter={(v: number, n: string) => [`${fmt(v, 1)}%`, n]} />
                  <Legend wrapperStyle={{ fontSize: 10, color: SLATE }} />
                  <ReferenceLine y={0} stroke={SLATE} />
                  <Line name="USD credit yoy" type="monotone" dataKey="credit" stroke={BLUE} strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls />
                  <Line name="broad dollar yoy" type="monotone" dataKey="dollar" stroke={ORANGE} strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
          <Note>{sentences(str(uc?.reading),
            isNum(h.quarters as number) ? `History (${h.quarters} quarters since 2001): credit grew ${fmt(h.credit_growth_yoy_when_dollar_down_pct as number)}% yoy when the dollar was down yoy (${h.n_down} quarters) vs ${fmt(h.credit_growth_yoy_when_dollar_up_pct as number)}% when up (${h.n_up})` : null,
            str(h.corr_caveat as string))}</Note>
        </div>
        <div className="overflow-x-auto">
          <div className="mb-1 text-xs font-semibold text-slate-300">Policy rates vs the Fed (BIS, end of month)</div>
          {pr.length === 0 ? <Unavailable what="Policy rates" /> : (
            <table className="w-full text-[11px]">
              <thead><tr><Th>area</Th><Th right>rate</Th><Th right>vs Fed (same month)</Th><Th right>12m change</Th><Th>month</Th></tr></thead>
              <tbody>
                {pr.map((r) => (
                  <tr key={r.area}><Td>{r.name}</Td><Td right mono>{unit(r.rate, 2, "%")}</Td><Td right mono>{r.area === "US" ? "-" : pp(r.vs_fed_pp)}</Td><Td right mono>{pp(r.chg_12m_pp)}</Td><Td mono>{r.month}</Td></tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="mt-1 text-[10px] text-slate-600">{str(s.policy_rates?.basis) ?? ""}</p>
        </div>
      </div>
      <Note>{sentences(str(a25?.text as string) ? `${a25?.text}: DXY ${pct(a25?.dxy_2025_04_02_to_04_21_pct as number)} (2 to 21 April), 10-year ${pp(a25?.y10_2025_04_04_to_04_11_pp as number)} (4 to 11 April)` : null,
        str(t?.chain_2022?.text as string) ? `2022: ${t?.chain_2022?.text}` : null)}</Note>
      {(str(uc?.basis) || str(fx?.basis)) && <p className="mt-1 text-[10px] text-slate-600">Basis: {sentences(str(uc?.basis), str(fx?.basis))}</p>}
    </>
  );
}

function OutcomeTriplet({ o }: { o: DwOutcomes | null | undefined }) {
  return (
    <span className="font-mono text-[10px] tabular-nums">
      {(["3m", "6m", "12m"] as const).map((h) => {
        const x = o?.[h];
        return <span key={h} className="mr-2">{h}: {x ? `S&P ${pct(x.spx_pct)} · Baa−10y ${pp(x.baa10y_pp)}` : "pending"}</span>;
      })}
    </span>
  );
}

function LedgerLayer({ d }: { d: DollarWatch }) {
  const l = d.ledger;
  if (!l) return <Unavailable what="Ledger" />;
  const live = arr(l.live) as Array<DwLedgerEntry & { h10_release?: string | null }>;
  return (
    <>
      <div className="mb-2 text-[11px] text-slate-400">
        Live rows since the reference cut-off (rule: {str(l.cutoff_rule) ?? "n/a"}; momentum: {str(l.cutoff_momentum) ?? "n/a"}):{" "}
        {live.length === 0 ? "none yet. A firing is recorded the day the panel first sees it and is never edited; at realistic edges the record needs decades to score." : `${live.length}.`}
        {str(l.problem) ? ` Ledger problem: ${l.problem}.` : ""}
      </div>
      {live.length > 0 && (
        <div className="mb-3 overflow-x-auto">
          <table className="w-full min-w-[720px] text-[11px]">
            <thead><tr><Th>kind</Th><Th>date</Th><Th>H.10 release</Th><Th>recorded</Th><Th>variants</Th><Th>outcomes from the first observable close</Th></tr></thead>
            <tbody>
              {live.map((e) => (
                <tr key={`${e.kind}${e.date}`}><Td>{e.kind}</Td><Td mono>{e.date}</Td><Td mono>{str(e.h10_release) ?? "-"}</Td><Td mono>{str(e.recorded_on) ?? "n/a"}</Td>
                  <Td>{arr(e.variants).join(", ") || "-"}</Td><Td><OutcomeTriplet o={e.outcomes} /></Td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="overflow-x-auto">
        <div className="mb-1 text-xs font-semibold text-slate-300">Momentum episodes since 1971 (12-month DXY change above +10%), reconstructed in-sample</div>
        <table className="w-full min-w-[600px] text-[11px]">
          <thead><tr><Th>month</Th><Th right>DXY 12m (trailing)</Th><Th right>S&amp;P next 12m</Th><Th right>Baa−10y next 12m</Th><Th right>DXY next 12m</Th></tr></thead>
          <tbody>
            {arr(l.frozen_momentum).map((m) => {
              const o = m.outcomes?.["12m"];
              return (
                <tr key={m.month} className="border-t border-slate-800/70"><Td mono>{m.month}</Td><Td right mono>{pct(m.dxy_12m_pct)}</Td><Td right mono>{pct(o?.spx_pct)}</Td>
                  <Td right mono>{pp(o?.baa_minus_10y_pp)}</Td><Td right mono>{pct(o?.dxy_pct)}</Td></tr>
              );
            })}
          </tbody>
        </table>
        <Note>{str(l.frozen_momentum_basis) ?? ""}</Note>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------- tab
function devOverride(): DollarWatch | null {
  if (!import.meta.env.DEV) return null;
  try {
    const q = new URLSearchParams(window.location.search).get("dollar");
    if (q === "fixture") return DOLLAR_FIXTURE;
    if (q === "nulls") return DOLLAR_ALL_NULL;
  } catch {
    // no window (server render): fall through to the live fetch
  }
  return null;
}

export default function DollarTab() {
  const [data, setData] = useState<DollarWatch | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    const dev = devOverride();
    if (dev) {
      setData(dev);
      setLoading(false);
      return;
    }
    api
      .dollarWatch()
      .then((d) => {
        if (alive) {
          setData(d ?? DOLLAR_ALL_NULL);
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
      {loading && <Loading label="Loading the dollar watch…" />}
      {!loading && error && <InlineError message={`Failed to load /dollar-watch: ${error}`} />}
      {!loading && !error && data && <DollarView data={data} />}
    </div>
  );
}

export function DollarView({ data }: { data: DollarWatch }) {
  const d: DollarWatch = data ?? DOLLAR_ALL_NULL;
  const b = d.status?.blocks ?? {};
  return (
    <>
      <div className="rounded-lg border border-slate-600/60 bg-slate-500/5 px-4 py-3">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-sm font-bold tracking-wide text-slate-300">DESCRIPTIVE: the dollar against its own history, with the record beside each reading</span>
          <span className="ml-auto font-mono text-[11px] text-slate-500">generated {str(d.generated) ?? "n/a"} · reference cut-off {str(d.frozen_on) ?? "n/a"}</span>
        </div>
        <p className="mt-1 text-[12px] leading-snug text-slate-300">{str(d.headline) ?? "No live reading."}</p>
        {str(d.build_error) && <p className="mt-1 text-[11px] text-slate-500">The last rebuild failed ({d.build_error}); showing the previous build.</p>}
      </div>
      <Section title="1 · Dollar state" subtitle="ICE DXY, the Fed broad index, the dollar-yield quadrant, momentum, safe havens, EM FX, oil" status={b.state ?? d.state?.status}>
        <StateLayer d={d} />
      </Section>
      <Section title="2 · Dollar-funding nowcast" subtitle="the plumbing: CP minus bills, OFR funding, NFCI risk, SOFR tails, swap lines, EM dollar bonds" status={b.funding ?? d.funding?.status} basis={d.funding?.basis}>
        <FundingLayer d={d} />
      </Section>
      <Section title="3 · Dollar-scramble peak gauge"
        subtitle="Casey's deceleration rule, parameters fixed, run live: an untested hypothesis about the top of a dollar SCRAMBLE (1 clean and 2 first-wave firings on the three V-spikes; no edge on 1973-2005); it says nothing about the end of a crisis"
        status={b.scramble ?? d.scramble?.status} basis={d.scramble?.basis}>
        <ScrambleLayer d={d} />
      </Section>
      <Section title="4 · Slow state" subtitle="dollar credit outside the US, the FX-swap stock, policy rates, the 2-year, the Treasury channel" status={b.slow ?? d.slow?.status}>
        <SlowLayer d={d} />
      </Section>
      <Section title="Forward ledger" subtitle="dated firings after the reference cut-off; outcomes frozen in as they mature; at realistic edges it needs decades to score" status={b.ledger ?? d.ledger?.status} basis={d.ledger?.basis}>
        <LedgerLayer d={d} />
      </Section>
      <Panel title="Honesty box">
        <ul className="list-disc space-y-1 pl-4 text-[11px] text-slate-400">
          {arr(d.honesty).map((h, i) => <li key={i}>{h}</li>)}
          {str(d.window_convention) && <li>Window convention: {d.window_convention}.</li>}
        </ul>
        {arr(d.pending_questions).length > 0 && (
          <div className="mt-3 text-[11px] text-slate-400">
            <div className="font-semibold text-slate-300">Pending questions (ranked)</div>
            {arr(d.pending_questions).map((q, i) => (
              <div key={i}><span className="font-mono">{q.rank}</span> {q.q} <span className="text-slate-500">(moves: {q.moves ?? "n/a"}; {q.status ?? "n/a"} {q.first_asked ?? ""}{q.expires ? `, expires ${q.expires}` : ""})</span></div>
            ))}
          </div>
        )}
        <p className="mt-3 text-[10px] text-slate-600">
          Crisis lists: {Object.entries(d.crisis_lists ?? {}).map(([k, v]) => `${k} = ${v?.label ?? k}`).join("; ") || "n/a"}.
        </p>
      </Panel>
    </>
  );
}
