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
import type { DollarWatch, DwFiring, DwFundingRow, DwOutcomes, DwReading, DwSeries, DwStatus } from "../lib/api";
import { api } from "../lib/api";
import { errorMessage } from "../lib/format";
import { DOLLAR_ALL_NULL, DOLLAR_FIXTURE } from "../lib/dollarFixture";
import { InlineError, Loading, Panel } from "./ui";

/* Dollar watch — studies/dollar-watch.md §5. DESCRIPTIVE: what the dollar and
   the dollar-funding plumbing are doing against their own history, with the
   in-sample record beside every reading (each count with its N and base rate).
   No forecast, no odds, no colour-coded states: status chips report data
   freshness only, and every series is drawn in the same neutral palette.
   The payload is the contract; any block may be null or "error", so every
   section reads defensively and degrades to a muted "unavailable" line. */

// Fixed identities (validated with the dataviz palette checker on the panel surface).
const BLUE = "#3987e5"; // the primary series in every chart
const ORANGE = "#d95926"; // the second series where two share an axis
const VIOLET = "#9085e9"; // dated events (rule firings, swap-line announcements)
const SLATE = "#64748b";
const GRID = "#1e293b";
const TOOLTIP_STYLE = { background: "#0f172a", border: "1px solid #334155", fontSize: 11 };
const tickStyle = { fontSize: 9, fill: SLATE };

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
  return isNum(v) ? v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }) : "n/a";
}
function sgn(v: unknown, d = 1): string {
  return isNum(v) ? `${v > 0 ? "+" : ""}${fmt(v, d)}` : "n/a";
}
function pct(v: unknown, d = 1): string {
  return isNum(v) ? `${sgn(v, d)}%` : "n/a";
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
// Firing markers closer than ~3 months share one label ("1-2") so the numbers never overprint.
function mergeLabels(refs: Array<{ t: number; label?: string }>): Array<{ t: number; label?: string }> {
  const out: Array<{ t: number; label?: string }> = [];
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
function dayLabel(t: unknown): string {
  return isNum(t) ? new Date(t).toISOString().slice(0, 10) : "";
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

// ---------------------------------------------------------------------------- small pieces
function DataChip({ status }: { status: DwStatus | null | undefined }) {
  const s = status === "ok" || status === "stale" || status === "error" ? status : null;
  const title = s === "ok" ? "fetched live" : s === "stale" ? "served from cache: the source fetch did not complete" : "the source fetch failed";
  return (
    <span className="rounded border border-slate-700 px-1.5 py-0.5 font-mono text-[10px] text-slate-400" title={title}>
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

function Tile({ label, value, sub, asof, src }: { label: string; value: string; sub?: ReactNode; asof?: unknown; src?: unknown }) {
  return (
    <div className="rounded-lg border border-panelborder bg-slate-900/40 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-0.5 font-mono text-lg font-semibold tabular-nums text-slate-100">{value}</div>
      {sub && <div className="mt-0.5 text-[11px] leading-snug text-slate-400">{sub}</div>}
      <div className="mt-1 font-mono text-[10px] text-slate-500">
        as of {str(asof) ?? "n/a"} <Src href={src} />
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
  unit,
  digits = 1,
  refY = [],
  refX = [],
  height = 200,
  domain,
}: {
  rows: Array<{ t: number; v: number }>;
  unit: string;
  digits?: number;
  refY?: Array<{ y: number; label?: string }>;
  refX?: Array<{ t: number; label?: string }>;
  height?: number;
  domain?: [number | "auto", number | "auto"];
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
          <YAxis tick={tickStyle} width={44} domain={domain ?? ["auto", "auto"]} tickFormatter={(v: number) => fmt(v, digits)} />
          <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={dayLabel} formatter={(v: number) => [`${fmt(v, digits)} ${unit}`, ""]} />
          {refY.map((r) => (
            <ReferenceLine key={`y${r.y}`} y={r.y} stroke={SLATE} strokeDasharray="4 3" label={r.label ? { value: r.label, fill: SLATE, fontSize: 9, position: "insideTopLeft" } : undefined} />
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

function Outcome({ o }: { o: DwOutcomes | null | undefined }) {
  const x = o?.["12m"];
  if (!x) return <span className="text-slate-600">pending</span>;
  return (
    <span className="font-mono text-[10px] tabular-nums">
      S&amp;P {pct(x.spx_pct)} · EM FX {pct(x.emfx_pct)} · spread {sgn(x.baa10y_pp ?? x.baa_minus_10y_pp, 2)}pp
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
  const qb = q?.base_all_months?.shares ?? {};
  const mom = s.momentum;
  const g = s.safe_haven?.gold;
  const gr = s.safe_haven?.gold_record;
  const lists = ["A25", "C16", "N5"];
  return (
    <>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <Tile label="ICE DXY" value={fmt(dx?.latest, 2)} asof={dx?.asof} src={dx?.src}
          sub={<>{str(dx?.band_position) ?? "n/a"}; {pct(dx?.chg_6m_pct)} 6m, {pct(dx?.chg_12m_pct)} 12m; {ord(dx?.pct_own_history)} pct of month-ends since 1971</>} />
        <Tile label="Fed broad dollar" value={fmt(s.broad?.broad?.latest, 1)} asof={s.broad?.broad?.asof} src={s.broad?.broad?.src}
          sub={<>{pct(s.broad?.broad?.chg_6m_pct)} 6m, {pct(s.broad?.broad?.chg_12m_pct)} 12m; {ord(s.broad?.broad?.pct_10y)} pct of 10y; high since 2006 {fmt(s.broad?.high_since_2006?.value, 1)} ({str(s.broad?.high_since_2006?.date) ?? "n/a"})</>} />
        <Tile label="vs advanced / EM economies" value={`${fmt(s.broad?.afe?.latest, 1)} / ${fmt(s.broad?.eme?.latest, 1)}`} asof={s.broad?.afe?.asof} src={s.broad?.afe?.src}
          sub={<>12m {pct(s.broad?.afe?.chg_12m_pct)} / {pct(s.broad?.eme?.chg_12m_pct)}</>} />
        <Tile label="Dollar-yield quadrant" value={str(q?.label) ?? "n/a"} asof={q?.month}
          sub={<>3 months to {str(q?.month) ?? "n/a"}: DXY {pct(q?.dxy_3m_pct)}, 10y {sgn(q?.y10_3m_pp, 2)}pp</>} />
      </div>

      <div className="mt-4">
        <div className="mb-1 text-xs text-slate-400">ICE DXY, month-end close, 1971 to now. Dashed: {str(band?.label) ?? "Johnson's ad hoc 85-105 band"}</div>
        <TimeChart rows={rows} unit="" digits={0} refY={[{ y: band?.lo ?? 85, label: "85" }, { y: band?.hi ?? 105, label: "105" }]} height={230} />
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
                  <tr key={k}><Td>{k}</Td><Td right mono>{r.hits_12m ?? "n/a"} of {r.n_excursions ?? "n/a"} ({share(r.rate_12m)})</Td><Td right mono>{share(r.base_12m)}</Td>
                    <Td right mono>{r.hits_24m ?? "n/a"} ({share(r.rate_24m)})</Td><Td right mono>{share(r.base_24m)}</Td></tr>
                );
              })}
            </tbody>
          </table>
          <Note>Base = share of all months 1971-2026 with an onset in the window. No list shows the band beating its base rate.</Note>
        </div>
        <div>
          <div className="mb-1 text-xs font-semibold text-slate-300">The quadrant into crisis onsets (C16, {q?.onsets_C16?.n ?? "n/a"} onsets)</div>
          <table className="w-full text-[11px]">
            <thead><tr><Th>3-month quadrant</Th><Th right>onsets</Th><Th right>share of all months</Th></tr></thead>
            <tbody>
              {["usd_up_yld_down", "usd_up_yld_up", "usd_down_yld_up", "usd_down_yld_down"].map((k) => (
                <tr key={k} className={q?.quadrant === k ? "font-semibold" : ""}>
                  <Td>{q?.labels?.[k] ?? k}{q?.quadrant === k ? " (now)" : ""}</Td><Td right mono>{qc[k] ?? "n/a"} of {q?.onsets_C16?.n ?? "n/a"}</Td><Td right mono>{share(qb[k])}</Td>
                </tr>
              ))}
            </tbody>
          </table>
          <Note>In-sample on {q?.onsets_C16?.n ?? "n/a"} onsets: a label, not a forecast.</Note>
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <div className="mb-1 text-xs font-semibold text-slate-300">12-month momentum: {pct(mom?.dxy_12m_pct)} to {str(mom?.month) ?? "n/a"} (reading above +{fmt(mom?.threshold_pct, 0)}%: {mom?.signal ? "yes" : "no"}; last {str(mom?.last_signal_month) ?? "n/a"})</div>
          <table className="w-full text-[11px]">
            <thead><tr><Th>crisis list</Th><Th right>signal months followed in 12m</Th><Th right>episodes</Th><Th right>base</Th></tr></thead>
            <tbody>
              {lists.map((k) => {
                const r = mom?.by_list?.[k] ?? {};
                return (
                  <tr key={k}><Td>{k}</Td><Td right mono>{r.signal_months_followed_12m ?? "n/a"} of {r.signal_months ?? "n/a"} ({share(r.rate_months)})</Td>
                    <Td right mono>{r.episodes_followed_12m ?? "n/a"} of {r.episodes ?? "n/a"}</Td><Td right mono>{share(r.base_12m)}</Td></tr>
                );
              })}
            </tbody>
          </table>
          <Note>{str(mom?.caveat) ?? ""}</Note>
        </div>
        <div>
          <div className="mb-1 text-xs font-semibold text-slate-300">Safe havens and EM</div>
          <div className="grid grid-cols-2 gap-2">
            <Tile label={g?.provider === "yahoo" ? "Gold (COMEX futures)" : "Gold (spot)"} value={fmt(g?.latest, 0)} asof={g?.asof} src={g?.src}
              sub={<>{pct(g?.chg_6m_pct)} 6m; {pct(g?.off_52w_high_pct)} from its 52-week high</>} />
            <Tile label="EM FX basket" value={fmt(s.emfx?.latest, 1)} asof={s.emfx?.asof}
              sub={<>{pct(s.emfx?.chg_12m_pct)} 12m (up = EM weaker); {ord(s.emfx?.pct_10y)} pct of 10y</>} />
            <Tile label="CHF / JPY per $" value={`${fmt(s.safe_haven?.chf?.latest, 3)} / ${fmt(s.safe_haven?.jpy?.latest, 1)}`} asof={s.safe_haven?.chf?.asof}
              sub={<>6m {pct(s.safe_haven?.chf?.chg_6m_pct)} / {pct(s.safe_haven?.jpy?.chg_6m_pct)}</>} />
            <Tile label="Brent" value={`$${fmt(s.brent?.latest, 1)}`} asof={s.brent?.asof} src={s.brent?.src}
              sub={<>{pct(s.brent?.chg_12m_pct)} 12m; {ord(s.brent?.pct_own_history)} pct since {str(s.brent?.history_from)?.slice(0, 4) ?? "n/a"}</>} />
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
                <tr key={i}><Td>{String(x.episode ?? "")}</Td><Td right mono>{pct(x.intraday_pct ?? x.monthly_avg_pct)}{isNum(x.monthly_avg_pct) ? " (monthly)" : ""}</Td><Td right mono>{pct(x.close_pct)}</Td></tr>
              ))}
            </tbody>
          </table>
          <Note>Gold ended the episode above its eve level in {gr?.ended_higher ?? "n/a"} of {gr?.n_with_end ?? "n/a"} crises ({gr?.ended_higher_gt_1pct ?? "n/a"} by more than 1%): sold for dollars in the liquidation weeks, higher by the end in most.
            The dollar FELL into peak stress in {s.safe_haven?.dollar_fell_at_peak_stress?.fell ?? "n/a"} of {s.safe_haven?.dollar_fell_at_peak_stress?.n_crises ?? "n/a"}.</Note>
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
        <div className="mb-1 text-xs text-slate-400">EM FX basket (8 FRED pairs, Jan-2006 = 100; up = EM currencies weaker)</div>
        <TimeChart rows={seriesRows(s.emfx?.series)} unit="" digits={0} height={170} />
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------- layer 2
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
        <table className="w-full min-w-[640px] text-[11px]">
          <thead><tr><Th>gauge</Th><Th right>now</Th><Th>as of</Th><Th right>own-history pct</Th><Th right>10y pct</Th><Th right>1y median</Th><Th>reading</Th></tr></thead>
          <tbody>
            {arr(f.rows).map((r: DwFundingRow) => (
              <tr key={r.id} className="border-t border-slate-800/70">
                <Td>{r.label} <Src href={r.src} /></Td>
                <Td right mono>{fmt(r.latest, r.unit === "bp" ? 0 : 2)} {r.unit === "index (0 = average)" ? "" : r.unit}</Td>
                <Td mono>{str(r.asof) ?? "n/a"}</Td>
                <Td right mono>{r.id === "emb" ? `${pct(r.chg_1m_pct)} 1m` : `${ord(r.pct_own_history)}${r.history_from ? ` (since ${r.history_from.slice(0, 4)})` : ""}`}</Td>
                <Td right mono>{r.id === "emb" ? `${pct(r.off_52w_high_pct)} vs 52w high` : ord(r.pct_10y)}</Td>
                <Td right mono>{fmt(r.median_1y, r.unit === "bp" ? 0 : 2)}</Td>
                <Td><span className="text-slate-500">{str(r.direction) ?? ""}</span></Td>
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
        <div className="mb-1 text-xs font-semibold text-slate-300">Lead / lag against the broad dollar's peak (trading days; minus = before the dollar peaked)</div>
        <table className="w-full min-w-[640px] text-[11px]">
          <thead><tr><Th>series</Th>{eps.map((e) => <Th key={e}>{e} (dollar peak {ll?.dollar_peaks?.[e] ?? "n/a"})</Th>)}</tr></thead>
          <tbody>
            {arr(ll?.rows).map((r, i) => (
              <tr key={i} className="border-t border-slate-800/70"><Td>{r.series}</Td>{eps.map((e) => <Td key={e} mono>{r[e] ?? "n/a"}</Td>)}</tr>
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
  return (
    <>
      <div className="rounded border border-slate-700 bg-slate-900/40 px-3 py-2 text-[12px] text-slate-300">
        {!st ? (
          "Rule state unavailable."
        ) : sc.gate_open ? (
          <>Gate open on {st.asof}: the broad dollar's largest 20-day climb in the last 60 index days is {pct(st.roc20_max_60d_pct, 2)} ({st.roc20_max_date}) and the 10-year
            ({fmt(st.y10_now, 2)}%) is below its level before the climb ({fmt(st.y10_ref, 2)}% on {st.y10_ref_date}). The three readings below are shown separately and never added up.</>
        ) : (
          <>Gate closed on {st.asof}: the largest 20-day climb in the last 60 index days is {pct(st.roc20_max_60d_pct, 2)} ({st.roc20_max_date}); the gauge opens at +4% with the 10-year falling
            (10-year {fmt(st.y10_now, 2)}% vs {fmt(st.y10_ref, 2)}% before the climb). No dollar scramble is under way on this definition.</>
        )}
      </div>

      {sc.gate_open && ind && (
        <div className="mt-3 grid gap-2 md:grid-cols-3">
          {(
            [
              ["(a) deceleration", ind.a_deceleration, `20-day climb ${pct(ind.a_deceleration?.roc20_now_pct as number, 2)} vs max ${pct(ind.a_deceleration?.roc20_max_60d_pct as number, 2)}; dollar ${pct(ind.a_deceleration?.dollar_vs_60d_high_pct as number, 2)} vs 60-day high`],
              ["(b) funding easing", ind.b_funding_easing, `CP-bill ${fmt(ind.b_funding_easing?.cp_now as number, 2)} vs median ${fmt(ind.b_funding_easing?.cp_median_1y as number, 2)}; OFR funding ${fmt(ind.b_funding_easing?.ofr_funding_now as number, 2)} vs ${fmt(ind.b_funding_easing?.ofr_funding_median_1y as number, 2)}`],
              ["(c) gold and EM bonds turning", ind.c_risk_turn, `gold ${fmt(ind.c_risk_turn?.gold_now as number, 0)} vs 20-day high ${fmt(ind.c_risk_turn?.gold_prior_20d_high as number, 0)}; EMB ${fmt(ind.c_risk_turn?.emb_now as number, 2)} vs ${fmt(ind.c_risk_turn?.emb_prior_20d_high as number, 2)}`],
            ] as const
          ).map(([name, x, detail]) => (
            <div key={name} className="rounded border border-panelborder bg-slate-900/40 px-3 py-2">
              <div className="text-[11px] font-semibold text-slate-300">{name}: {yes(x?.met)}{name.startsWith("(a)") && x?.met ? ` (${str(sc.wording) ?? ""})` : ""}</div>
              <div className="mt-1 font-mono text-[10px] text-slate-400">{detail}</div>
              <div className="mt-1 text-[10px] text-slate-500">{str(x?.rule) ?? ""}</div>
            </div>
          ))}
          <div className="rounded border border-panelborder bg-slate-900/40 px-3 py-2 md:col-span-3 text-[11px] text-slate-400">
            Confirmations since {str(conf?.episode_start) ?? "n/a"}: dollar {pct(conf?.dollar_off_peak_pct, 2)} from its episode peak ({yes(conf?.dollar_3pct_off_peak)} at 3%);
            swap lines ${fmt(conf?.swap_now_bn, 1)}bn vs ${fmt(conf?.swap_episode_peak_bn, 1)}bn peak ({conf?.swap_below_10pct_of_peak == null ? "n/a: no material draw" : yes(conf?.swap_below_10pct_of_peak)} at 10%).
          </div>
        </div>
      )}

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <div className="mb-1 text-xs text-slate-400">Fed broad dollar, 2006 to now; dotted lines = the frozen rule's firings, numbered as in the table</div>
          <TimeChart rows={long} unit="" digits={0} refX={[...fireRefs, ...liveRefs]} height={210} />
        </div>
        <div>
          <div className="mb-1 text-xs text-slate-400">20-day change of the broad dollar, %, last ~3 years (gauge opens at +4%)</div>
          <TimeChart rows={roc} unit="%" digits={1} refY={[{ y: 4, label: "+4%" }, { y: 0 }]} height={210} />
        </div>
      </div>

      <div className="mt-4 overflow-x-auto">
        <div className="mb-1 text-xs font-semibold text-slate-300">Every firing of the frozen rule (re-arm variant), in-sample, with what followed</div>
        <table className="w-full min-w-[720px] text-[11px]">
          <thead><tr><Th>#</Th><Th>fired</Th><Th right>largest 20d climb</Th><Th right>dollar rose further</Th><Th right>S&amp;P to next low</Th><Th right>VIX 60d later</Th><Th>12 months later (EM FX up = EM weaker)</Th><Th>reading</Th></tr></thead>
          <tbody>
            {hist.map((f: DwFiring, i) => (
              <tr key={f.date} className="border-t border-slate-800/70">
                <Td mono>{i + 1}</Td><Td mono>{f.date}</Td><Td right mono>{pct(f.roc20_max_pct)} ({str(f.roc20_max_date) ?? "n/a"})</Td>
                <Td right mono>{pct(f.dollar_further_rise_pct)}</Td><Td right mono>{pct(f.spx_to_next_low_pct)}</Td><Td right mono>{sgn(f.vix_change_60d)}</Td>
                <Td><Outcome o={f.outcomes} /></Td><Td><span className="text-slate-400">{str(f.reading) ?? ""}</span></Td>
              </tr>
            ))}
          </tbody>
        </table>
        <Note>Unpatched variant (no re-arm): {arr(sc.history_unpatched).join(", ") || "n/a"}. Live re-run on today's data reproduces the frozen firings:{" "}
          {sc.live_check?.reproduces_frozen_rearm === true && sc.live_check?.reproduces_frozen_unpatched === true ? "yes" : sc.live_check ? "no (data revised; see the study)" : "n/a"}.</Note>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <div className="rounded border border-slate-700 px-3 py-2 text-[11px] text-slate-300">
          <div className="font-semibold">The null, shown permanently</div>
          On {str(mn?.window) ?? "1973-2005 monthly data"}: {mn?.firings ?? "n/a"} firings; the dollar peaked within 3 months in {mn?.dollar_peak_within_3m ?? "n/a"} (base {share(mn?.base_dollar_peak_within_3m)});
          the S&amp;P was higher 12 months later in {mn?.spx_up_12m ?? "n/a"} (base {share(mn?.base_spx_up_12m)}). No edge.
        </div>
        <div className="rounded border border-slate-700 px-3 py-2 text-[11px] text-slate-300">
          <div className="font-semibold">Order at the end of a scramble</div>
          {arr(sc.end_of_scramble?.order).map((o, i) => <span key={i}>{i + 1}. {o}{i < arr(sc.end_of_scramble?.order).length - 1 ? "; " : "."}</span>)}
          <div className="mt-1 text-slate-400">{str(sc.end_of_scramble?.case_2008) ?? ""}</div>
        </div>
        <div className="rounded border border-slate-700 px-3 py-2 text-[11px] text-slate-300">
          <div className="font-semibold">When the climb peaked</div>
          {arr(sc.vspike_timing).map((v, i) => (
            <div key={i}>{String(v.episode)}: climb {String(v.climb_peak)} ({pct(v.climb_peak_pct)}), VIX {String(v.vix_peak)}, dollar {String(v.dollar_peak)} ({pct(v.dollar_further_rise_after_climb_peak_pct)} more)</div>
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
  return (
    <>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <Tile label="USD credit outside the US" value={isNum(uc?.total_tn) ? `$${fmt(uc?.total_tn, 2)}tn` : "n/a"} asof={uc?.quarter} src={uc?.src}
          sub={<>{pct(uc?.yoy_pct)} yoy; EMEs ${fmt(uc?.eme_tn, 2)}tn ({pct(uc?.eme_yoy_pct)}, {fmt(uc?.eme_share_pct, 0)}% of the total); {str(uc?.label) ?? "n/a"}</>} />
        <Tile label="FX forwards and swaps outstanding" value={isNum(fx?.all_tn) ? `$${fmt(fx?.all_tn, 1)}tn` : "n/a"} asof={fx?.period}
          sub={<>dollar leg ${fmt(fx?.usd_leg_tn, 1)}tn; {str(fx?.prev_period) ?? "n/a"} ${fmt(fx?.prev_all_tn, 1)}tn</>} />
        <Tile label="US 2-year vs funds ceiling" value={`${fmt(s.us2y_vs_funds?.dgs2, 2)}% / ${fmt(s.us2y_vs_funds?.fed_upper, 2)}%`} asof={s.us2y_vs_funds?.dgs2_asof}
          sub={<>gap {sgn(s.us2y_vs_funds?.gap_pp, 2)}pp; {str(s.us2y_vs_funds?.reading) ?? ""}</>} />
        <Tile label="Foreign official custody" value={isNum(t?.custody?.latest) ? `$${fmt(t?.custody?.latest, 0)}bn` : "n/a"} asof={t?.custody?.asof} src={t?.custody?.src}
          sub={<>{pct(t?.custody?.chg_12m_pct)} 12m; {ord(t?.custody?.pct_10y)} pct of 10y; 10-year {fmt(t?.y10?.latest, 2)}% ({sgn(t?.y10_chg_6m_pp, 2)}pp 6m); term premium {fmt(t?.term_premium?.latest, 2)}pp</>} />
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
          <Note>{str(uc?.reading) ?? ""}. History ({String(h.quarters ?? "n/a")} quarters): credit grew {fmt(h.credit_growth_yoy_when_dollar_down_pct)}% yoy when the dollar was down vs {fmt(h.credit_growth_yoy_when_dollar_up_pct)}% when up;
            correlation {fmt(h.corr_yoy_contemporaneous, 2)} ({fmt(h.corr_yoy_dollar_leads_1q, 2)} with the dollar a quarter ahead). {str(h.corr_caveat) ?? ""}</Note>
        </div>
        <div className="overflow-x-auto">
          <div className="mb-1 text-xs font-semibold text-slate-300">Policy rates vs the Fed (BIS, end of month)</div>
          <table className="w-full text-[11px]">
            <thead><tr><Th>area</Th><Th right>rate</Th><Th right>vs Fed</Th><Th right>12m change</Th><Th>month</Th></tr></thead>
            <tbody>
              {arr(s.policy_rates?.rows).map((r) => (
                <tr key={r.area}><Td>{r.name}</Td><Td right mono>{fmt(r.rate, 2)}%</Td><Td right mono>{r.area === "US" ? "-" : `${sgn(r.vs_fed_pp, 2)}pp`}</Td><Td right mono>{sgn(r.chg_12m_pp, 2)}pp</Td><Td mono>{r.month}</Td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <Note>{str(a25?.text as string) ?? ""}: DXY {pct(a25?.dxy_2025_04_02_to_04_21_pct as number)} (2 to 21 April), 10-year {sgn(a25?.y10_2025_04_04_to_04_11_pp as number, 2)}pp (4 to 11 April). 2022: {str(t?.chain_2022?.text as string) ?? "n/a"}.</Note>
      <p className="mt-1 text-[10px] text-slate-600">Basis: {str(uc?.basis) ?? ""} {str(fx?.basis) ?? ""}</p>
    </>
  );
}

function LedgerLayer({ d }: { d: DollarWatch }) {
  const l = d.ledger;
  if (!l) return <Unavailable what="Ledger" />;
  return (
    <>
      <div className="mb-2 text-[11px] text-slate-400">Live rows since the freeze ({str(l.frozen_on) ?? "n/a"}): {arr(l.live).length === 0 ? "none yet; a firing is recorded the day the panel first sees it and is never edited." : ""}</div>
      {arr(l.live).length > 0 && (
        <table className="mb-3 w-full text-[11px]">
          <thead><tr><Th>kind</Th><Th>date</Th><Th>recorded</Th><Th>variants</Th><Th>12 months later</Th></tr></thead>
          <tbody>
            {arr(l.live).map((e) => (
              <tr key={`${e.kind}${e.date}`}><Td>{e.kind}</Td><Td mono>{e.date}</Td><Td mono>{str(e.recorded_on) ?? "n/a"}</Td><Td>{arr(e.variants).join(", ")}</Td><Td><Outcome o={e.outcomes} /></Td></tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="overflow-x-auto">
        <div className="mb-1 text-xs font-semibold text-slate-300">Momentum episodes since 1971 (12m DXY change above +10%), reconstructed in-sample</div>
        <table className="w-full min-w-[640px] text-[11px]">
          <thead><tr><Th>month</Th><Th right>DXY 12m</Th><Th right>S&amp;P 12m later</Th><Th right>EM FX 12m</Th><Th right>Baa spread 12m</Th><Th right>DXY 12m later</Th></tr></thead>
          <tbody>
            {arr(l.frozen_momentum).map((m) => {
              const o = m.outcomes?.["12m"];
              return (
                <tr key={m.month} className="border-t border-slate-800/70"><Td mono>{m.month}</Td><Td right mono>{pct(m.dxy_12m_pct)}</Td><Td right mono>{pct(o?.spx_pct)}</Td>
                  <Td right mono>{pct(o?.emfx_pct)}</Td><Td right mono>{sgn(o?.baa_minus_10y_pp, 2)}pp</Td><Td right mono>{pct(o?.dxy_pct)}</Td></tr>
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
          <span className="ml-auto font-mono text-[11px] text-slate-500">generated {str(d.generated) ?? "n/a"} · reference frozen {str(d.frozen_on) ?? "n/a"}</span>
        </div>
        <p className="mt-1 text-[12px] leading-snug text-slate-300">{str(d.headline) ?? "No live reading."}</p>
        {str(d.build_error) && <p className="mt-1 text-[11px] text-slate-500">Last build failed ({d.build_error}); showing the frozen record.</p>}
      </div>
      <Section title="1 · Dollar state" subtitle="ICE DXY, the Fed broad index, the dollar-yield quadrant, momentum, safe havens, EM FX, oil" status={b.state ?? d.state?.status} basis={d.state?.band?.basis}>
        <StateLayer d={d} />
      </Section>
      <Section title="2 · Dollar-funding nowcast" subtitle="the plumbing: CP minus bills, OFR funding, NFCI risk, SOFR tails, swap lines, EM dollar bonds" status={b.funding ?? d.funding?.status} basis={d.funding?.basis}>
        <FundingLayer d={d} />
      </Section>
      <Section title="3 · Dollar-scramble peak gauge" subtitle="Casey's deceleration rule, frozen, run live; dates the end of a dollar SCRAMBLE, not of a crisis" status={b.scramble ?? d.scramble?.status} basis={d.scramble?.basis}>
        <ScrambleLayer d={d} />
      </Section>
      <Section title="4 · Slow state" subtitle="dollar credit outside the US, the FX-swap stock, policy rates, the 2-year, the Treasury channel" status={b.slow ?? d.slow?.status}>
        <SlowLayer d={d} />
      </Section>
      <Section title="Forward ledger" subtitle="dated firings after the freeze, outcomes filled in as they mature" status={b.ledger ?? d.ledger?.status} basis={d.ledger?.basis}>
        <LedgerLayer d={d} />
      </Section>
      <Panel title="Honesty box">
        <ul className="list-disc space-y-1 pl-4 text-[11px] text-slate-400">
          {arr(d.honesty).map((h, i) => <li key={i}>{h}</li>)}
          {str(d.window_convention) && <li>Window convention: {d.window_convention}.</li>}
        </ul>
        {arr(d.pending_questions).length > 0 && (
          <div className="mt-3 text-[11px] text-slate-400">
            <div className="font-semibold text-slate-300">Pending questions</div>
            {arr(d.pending_questions).map((q, i) => (
              <div key={i}><span className="font-mono">{q.rank}</span> {q.q} <span className="text-slate-500">(moves: {q.moves ?? "n/a"}; {q.status ?? "n/a"} {q.first_asked ?? ""})</span></div>
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

// re-exported for the render smoke
export type { DwReading };
