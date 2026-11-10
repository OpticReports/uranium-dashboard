import { Component, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type {
  AiDebt,
  AiDebtBlockStatus,
  AiDebtBreaking,
  AiDebtCountry,
  AiDebtCrowding,
  AiDebtDeal,
  AiDebtFiling,
  AiDebtForeignBid,
  AiDebtHolders,
  AiDebtIssuance,
  AiDebtJapan,
  AiDebtMonthRow,
  AiDebtPublicFunds,
  AiDebtReading,
  AiDebtSeries,
  AiDebtSpreadAtIssue,
} from "../lib/api";
import { api } from "../lib/api";
import { errorMessage } from "../lib/format";
import { AI_DEBT_ALL_NULL, AI_DEBT_FIXTURE } from "../lib/aiDebtFixture";
import { InlineError, Loading, Panel } from "./ui";

/* AI debt — studies/ai-debt-flows.md, spec studies/ai_debt_flows/BUILD.md.
   Context, not a signal: nothing here is pre-registered or graded and no
   alert fires from this tab; status language is "watch". The payload is the
   contract and every block may be null or carry status "stale" / "error", so
   every panel reads defensively and renders a muted "unavailable" state
   rather than throwing. Every number on screen carries its basis and as-of;
   missing data is null (shown as "n/a"), never 0. */

// ---------------------------------------------------------------------------
// Fixed colours per entity (never change with filters). Validated against the
// panel surface with the dataviz palette checker (adjacent pairs pass).
// ---------------------------------------------------------------------------

const BUCKET_COLOR: Record<string, string> = {
  hyperscaler: "#3987e5",
  "chips-memory": "#d95926",
  neocloud: "#199e70",
  "ai-lab": "#c98500",
  "data-center": "#d55181",
  power: "#008300",
  "off-balance-sheet": "#9085e9",
};
const BUCKET_ORDER = Object.keys(BUCKET_COLOR);

const RATING_COLOR: Record<string, string> = {
  AAA: "#3987e5",
  AA: "#d95926",
  A: "#199e70",
  BBB: "#c98500",
  BB: "#d55181",
  B: "#008300",
  "unrated/private": "#9085e9",
  "ABS/CMBS-tranched": "#e66767",
  unknown: "#64748b",
};
const RATING_ORDER = Object.keys(RATING_COLOR);
const RATING_LABEL: Record<string, string> = { unknown: "not captured" };

// Spread buckets charted (IG and HY aggregates sit in the tile row instead).
const SPREAD_SERIES: Array<[string, string]> = [
  ["AAA", "#3987e5"],
  ["AA", "#d95926"],
  ["A", "#199e70"],
  ["BBB", "#c98500"],
  ["BB", "#d55181"],
  ["B", "#008300"],
  ["CCC", "#e66767"],
];

const PENSION = "#c98500"; // pension / public-fund money, wherever it appears
const BLUE = "#3987e5";
const ORANGE = "#d95926";
const AQUA = "#199e70";
const VIOLET = "#9085e9";
const SLATE = "#64748b";
const GRID = "#1e293b";
const TOOLTIP_STYLE = { background: "#0f172a", border: "1px solid #334155", fontSize: 11 };
// Disjoint from every fixed colour above, so an unknown key can never be
// painted the same as a known series in the same stack.
const FALLBACK_COLORS = ["#8b5cf6", "#14b8a6", "#f472b6", "#a3e635", "#fb923c", "#22d3ee"];

// Deterministic colour for a key the fixed maps do not know (a new bucket
// name from the backend must not repaint the known ones). A null / empty key
// (a malformed deal row) gets slate rather than throwing.
function colorFor(map: Record<string, string>, key: unknown): string {
  if (typeof key !== "string" || !key) return SLATE;
  if (map[key]) return map[key];
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return FALLBACK_COLORS[h % FALLBACK_COLORS.length];
}

// The backend keys spread buckets in lower case (aaa … ccc, ig, hy); the
// display vocabulary is upper case. Normalise once on read.
function upperKeys<T>(m: Record<string, T> | null | undefined): Record<string, T> {
  return Object.fromEntries(Object.entries(m ?? {}).map(([k, v]) => [String(k).toUpperCase(), v]));
}

// ---------------------------------------------------------------------------
// Defensive helpers: the backend is built in parallel, so nothing is trusted.
// ---------------------------------------------------------------------------

function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

function fmt(v: unknown, digits = 1): string {
  if (!isNum(v)) return "n/a";
  return v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function fmtSigned(v: unknown, digits = 1): string {
  if (!isNum(v)) return "n/a";
  return `${v > 0 ? "+" : ""}${fmt(v, digits)}`;
}

function fmtBn(v: unknown, digits = 1): string {
  return isNum(v) ? `$${fmt(v, digits)}bn` : "n/a";
}

function fmtPct(v: unknown, digits = 1): string {
  return isNum(v) ? `${fmt(v, digits)}%` : "n/a";
}

function str(v: unknown): string | null {
  return typeof v === "string" && v.length > 0 ? v : null;
}

function arr<T>(v: T[] | null | undefined): T[] {
  return Array.isArray(v) ? v : [];
}

function isHttp(v: unknown): v is string {
  return typeof v === "string" && /^https?:\/\//.test(v);
}

interface Point {
  date: string;
  value: number | null;
}

// Normalise either series encoding into points, dropping malformed entries.
function points(series: AiDebtSeries | null | undefined): Point[] {
  if (!series) return [];
  if (Array.isArray(series)) {
    return series
      .filter((p) => p && typeof p.date === "string")
      .map((p) => ({ date: p.date, value: isNum(p.value) ? p.value : null }));
  }
  const dates = arr(series.dates);
  const values = arr(series.values);
  const n = Math.min(dates.length, values.length);
  const out: Point[] = [];
  for (let i = 0; i < n; i++) {
    if (typeof dates[i] === "string") out.push({ date: dates[i], value: isNum(values[i]) ? values[i] : null });
  }
  return out;
}

// Rolling 12-observation sum; null while the window is short or holed.
function rolling12(values: Array<number | null | undefined>): Array<number | null> {
  const out: Array<number | null> = [];
  for (let i = 0; i < values.length; i++) {
    if (i < 11) {
      out.push(null);
      continue;
    }
    let s = 0;
    let ok = true;
    for (let j = i - 11; j <= i; j++) {
      const v = values[j];
      if (!isNum(v)) {
        ok = false;
        break;
      }
      s += v;
    }
    out.push(ok ? Math.round(s * 1000) / 1000 : null);
  }
  return out;
}

function last<T>(xs: T[]): T | undefined {
  return xs.length ? xs[xs.length - 1] : undefined;
}

// Merge parallel arrays into recharts rows on a shared x key.
function rows(x: string[], cols: Record<string, Array<number | null | undefined> | null | undefined>): Array<Record<string, string | number | null>> {
  return x.map((k, i) => {
    const r: Record<string, string | number | null> = { x: k };
    for (const [name, vals] of Object.entries(cols)) {
      const v = vals ? vals[i] : null;
      r[name] = isNum(v) ? v : null;
    }
    return r;
  });
}

// ---------------------------------------------------------------------------
// Chrome: status pill, as-of/source line, badges, unavailable state, boundary
// ---------------------------------------------------------------------------

const STATUS_STYLE: Record<AiDebtBlockStatus, string> = { ok: "#10b981", stale: "#6b7280", error: "#f59e0b" };

function BlockPill({ status }: { status: string | null | undefined }) {
  const s: AiDebtBlockStatus = status === "ok" || status === "stale" || status === "error" ? status : "stale";
  const color = STATUS_STYLE[s];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
      style={{ borderColor: `${color}55`, color, backgroundColor: `${color}14` }}
      title={s === "ok" ? "block fetched live" : s === "stale" ? "served from cache; the source fetch did not complete" : "the source fetch failed; showing what is known"}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
      {status ?? "no status"}
    </span>
  );
}

// `src` is a URL, or a map of URLs when a reading derives from several series
// (the CCC−B gap carries {ccc, b}); every URL is linked.
function SrcLink({ href, label = "src" }: { href: unknown; label?: string }) {
  const urls: string[] = isHttp(href) ? [href] : href && typeof href === "object" ? Object.values(href as Record<string, unknown>).filter(isHttp) : [];
  if (!urls.length) return <span className="text-slate-600">{label}: n/a</span>;
  return (
    <>
      {urls.map((u, i) => (
        <a key={u} href={u} target="_blank" rel="noreferrer" className={`text-sky-400/80 hover:text-sky-300${i > 0 ? " ml-1" : ""}`} title={u}>
          {label}
          {urls.length > 1 ? ` ${i + 1}` : ""} ↗
        </a>
      ))}
    </>
  );
}

// The foreign-bid block's `src` is a URL template (…FORLT{TREAS|CORP}{NET|POS}<code>),
// not a page; prefer a concrete series URL from `src_detail` when shipped.
function concreteSrc(fb: AiDebtForeignBid | null | undefined, key: string): unknown {
  const detail = (fb as unknown as { src_detail?: unknown } | null | undefined)?.src_detail;
  const u = detail && typeof detail === "object" ? (detail as Record<string, unknown>)[key] : null;
  return isHttp(u) ? u : fb?.src;
}

function AsOf({ asof, src, basis }: { asof?: unknown; src?: unknown; basis?: unknown }) {
  return (
    <span className="font-mono text-[10px] text-slate-500">
      as of {str(asof) ?? "n/a"}
      {basis ? <span className="text-slate-600"> · {String(basis)}</span> : null} · <SrcLink href={src} />
    </span>
  );
}

const VERIF_STYLE: Record<string, { color: string; title: string }> = {
  P: { color: "#10b981", title: "P — traced to a fetched primary filing" },
  R: { color: "#38bdf8", title: "R — fetched press / issuer release" },
  S: { color: "#f59e0b", title: "S — search snippet only, pending a filing" },
};

function VerifBadge({ v }: { v: unknown }) {
  const k = typeof v === "string" ? v.toUpperCase() : "";
  const st = VERIF_STYLE[k];
  if (!st) return <span className="text-slate-600">—</span>;
  return (
    <span
      className="inline-flex h-4 w-4 items-center justify-center rounded border font-mono text-[10px] font-bold"
      style={{ color: st.color, borderColor: `${st.color}66`, backgroundColor: `${st.color}14` }}
      title={st.title}
    >
      {k}
    </span>
  );
}

const PROV_STYLE: Record<string, string> = { primary: "#10b981", press: "#38bdf8", aggregator: "#f59e0b" };

function ProvBadge({ p }: { p: unknown }) {
  const k = typeof p === "string" ? p.toLowerCase() : "unknown";
  const color = PROV_STYLE[k] ?? SLATE;
  return (
    <span
      className="whitespace-nowrap rounded border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide"
      style={{ color, borderColor: `${color}55`, backgroundColor: `${color}14` }}
    >
      {k}
    </span>
  );
}

function Unavailable({ what, why }: { what: string; why?: string | null }) {
  return (
    <div className="rounded border border-dashed border-slate-700/70 bg-slate-900/30 px-3 py-2 text-xs text-slate-500">
      {what} unavailable{why ? ` — ${why}` : ""}.
    </div>
  );
}

// A panel that throws (an unexpected payload shape) degrades to the muted
// state instead of taking the tab down.
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

function Section({
  title,
  subtitle,
  status,
  basis,
  children,
}: {
  title: string;
  subtitle?: string;
  status: string | null | undefined;
  basis?: string | null;
  children: ReactNode;
}) {
  return (
    <Panel title={title} subtitle={subtitle} right={<BlockPill status={status} />}>
      <Boundary what={title}>{children}</Boundary>
      {basis && <p className="mt-3 text-[10px] leading-snug text-slate-600">Basis: {basis}</p>}
    </Panel>
  );
}

function Tile({ label, value, sub, asof, src }: { label: string; value: string; sub?: ReactNode; asof?: unknown; src?: unknown }) {
  return (
    <div className="rounded-lg border border-panelborder bg-slate-900/40 px-4 py-3">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-0.5 font-mono text-xl font-semibold tabular-nums text-slate-100">{value}</div>
      {sub && <div className="mt-0.5 text-[11px] text-slate-400">{sub}</div>}
      <div className="mt-1">
        <AsOf asof={asof} src={src} />
      </div>
    </div>
  );
}

function Sparkline({ values, color }: { values: Array<number | null> | null | undefined; color: string }) {
  const vs = arr(values);
  const nums = vs.filter(isNum);
  if (nums.length < 2) return <span className="text-slate-700">—</span>;
  const W = 64;
  const H = 16;
  const lo = Math.min(...nums, 0);
  const hi = Math.max(...nums, 0);
  const span = hi - lo || 1;
  const pts = vs
    .map((v, i) => (isNum(v) ? `${((i / (vs.length - 1)) * W).toFixed(1)},${(H - ((v - lo) / span) * H).toFixed(1)}` : null))
    .filter((p): p is string => p !== null);
  const zero = H - ((0 - lo) / span) * H;
  return (
    <svg width={W} height={H} className="inline-block align-middle" aria-hidden>
      <line x1={0} x2={W} y1={zero} y2={zero} stroke="#334155" strokeWidth={0.5} />
      <polyline points={pts.join(" ")} fill="none" stroke={color} strokeWidth={1.2} />
    </svg>
  );
}

// Direct label on the last point of a line (recharts `label` callback).
interface LabelProps {
  x?: number;
  y?: number;
  index?: number;
  value?: number | string;
}
function lastLabel(lastIndex: number, color: string, digits = 2) {
  return (p: LabelProps): JSX.Element => {
    if (p.index !== lastIndex || !isNum(p.x) || !isNum(p.y) || !isNum(Number(p.value))) return <g />;
    return (
      <text x={p.x + 4} y={p.y + 3} fill={color} fontSize={9} fontFamily="ui-monospace, monospace">
        {fmt(Number(p.value), digits)}
      </text>
    );
  };
}

const tickStyle = { fontSize: 9, fill: SLATE };
const legendStyle = { fontSize: 10, color: SLATE };

// ---------------------------------------------------------------------------
// Tab
// ---------------------------------------------------------------------------

// Dev-only smoke hook: `?aidebt=fixture` renders the frozen sample payload,
// `?aidebt=nulls` the all-null payload. Dead code in production builds.
function devOverride(): AiDebt | null {
  if (!import.meta.env.DEV) return null;
  try {
    const q = new URLSearchParams(window.location.search).get("aidebt");
    if (q === "fixture") return AI_DEBT_FIXTURE;
    if (q === "nulls") return AI_DEBT_ALL_NULL;
  } catch {
    // no window (test renderer): fall through to the live fetch
  }
  return null;
}

export default function AiDebtTab() {
  const [data, setData] = useState<AiDebt | null>(null);
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
      .aiDebt()
      .then((d) => {
        if (alive) {
          setData(d ?? AI_DEBT_ALL_NULL);
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
      {loading && <Loading label="Loading AI-debt context…" />}
      {!loading && error && <InlineError message={`Failed to load /ai-debt: ${error}`} />}
      {!loading && !error && data && <AiDebtView data={data} />}
    </div>
  );
}

// Pure view over a payload (also what the render smoke exercises).
export function AiDebtView({ data }: { data: AiDebt }) {
  const d: AiDebt = data ?? AI_DEBT_ALL_NULL;
  const st = (block: string, own: string | null | undefined) => d.status?.[block] ?? own ?? null;
  const basis = (k: string) => str(d.basis?.[k]);
  return (
    <>
      <div className="rounded-lg border border-slate-600/60 bg-slate-500/5 px-4 py-3">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-sm font-bold tracking-wide text-slate-300">CONTEXT, NOT A SIGNAL — watch list, nothing pre-registered</span>
          <span className="text-xs text-slate-400">
            AI-trade debt issuance, who holds US corporates, the foreign and Japanese bid, pension and public-fund money, crowding and breaking gauges.
          </span>
          <span className="ml-auto font-mono text-[11px] text-slate-500">
            payload as of {str(d.asof) ?? "n/a"}
            {str(d.generated) ? ` · generated ${d.generated}` : ""}
          </span>
        </div>
      </div>

      <Boundary what="Header strip">
        <HeaderStrip d={d} />
      </Boundary>

      <Section title="AI-trade issuance" subtitle="Gross issuance at pricing by bucket; deal table with provenance; new filings not yet in the tally" status={st("issuance", d.issuance?.status)} basis={basis("issuance")}>
        {d.issuance ? <IssuancePanel iss={d.issuance} spreads30={arr(d.breaking?.spread_at_issue_30y)} /> : <Unavailable what="Issuance block" why="not in payload" />}
      </Section>

      <Section title="Who holds US corporates" subtitle="Z.1 holder sectors: levels and the last four quarters of flows; pension sectors highlighted" status={st("holders", d.holders?.status)} basis={basis("holders")}>
        {d.holders ? <HoldersPanel h={d.holders} /> : <Unavailable what="Holders block" why="not in payload" />}
      </Section>

      <Section title="Foreign bid by country" subtitle="TIC net purchases, 12 months: Treasuries vs corporates; custody centres grouped as unattributable" status={st("foreign_bid", d.foreign_bid?.status)} basis={basis("foreign")}>
        {d.foreign_bid ? <ForeignBidPanel fb={d.foreign_bid} /> : <Unavailable what="Foreign-bid block" why="not in payload" />}
      </Section>

      <Section title="Japan" subtitle="BoJ sovereign vs non-sovereign US debt; MOF flows by investor type; JGB 10y / 30y" status={st("japan", d.japan?.status)} basis={basis("japan")}>
        {d.japan ? <JapanPanel j={d.japan} /> : <Unavailable what="Japan block" why="not in payload" />}
      </Section>

      <Section title="Public funds & pensions" subtitle="The marginal buyer may be pension and public-fund money, not sovereigns: what each free series can and cannot see" status={st("public_funds", d.public_funds?.status)} basis={basis("public_funds")}>
        {d.public_funds ? <PublicFundsPanel pf={d.public_funds} /> : <Unavailable what="Public-funds block" why="not in payload" />}
      </Section>

      <Section title="Crowding" subtitle="Term premium and the 30y; net Treasury supply vs the tally; auction indirect share by tenor" status={st("crowding", d.crowding?.status)} basis={basis("crowding")}>
        {d.crowding ? <CrowdingPanel c={d.crowding} iss={d.issuance} /> : <Unavailable what="Crowding block" why="not in payload" />}
      </Section>

      <Section title="Breaking" subtitle="Spreads by rating (log), CCC−B gap, spread-at-issue drift, BDC price / NAV, dated event log" status={st("breaking", d.breaking?.status)} basis={basis("breaking")}>
        {d.breaking ? <BreakingPanel b={d.breaking} /> : <Unavailable what="Breaking block" why="not in payload" />}
      </Section>

      <HonestyBox d={d} />
    </>
  );
}

// ---------------------------------------------------------------------------
// 1. Header strip
// ---------------------------------------------------------------------------

function HeaderStrip({ d }: { d: AiDebt }) {
  const iss = d.issuance;
  const raised26 = iss?.totals_by_year?.["2026"];
  const share26 = iss?.share?.["2026"];
  const japan = arr(d.foreign_bid?.countries).find((c) => c?.name === "Japan");
  const bills = d.foreign_bid?.bills_inclusive;
  const ccc = upperKeys(d.breaking?.spreads)["CCC"];
  const dgs30 = d.crowding?.yields?.dgs30;
  const kw = d.crowding?.term_premium?.kw10;
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Tile
        label="2026 YTD raised (gross, all ccy)"
        value={fmtBn(raised26)}
        sub={
          <>
            {fmtPct(share26?.pct_hyperscaler)} hyperscaler USD legs / SIFMA US corporate issuance ({fmtBn(share26?.sifma_us_corp_bn, 0)}); all AI USD legs {fmtPct(share26?.pct_all)}
          </>
        }
        asof={iss?.asof ?? d.asof}
        src={share26?.src}
      />
      <Tile
        label="Japan 12m net: Treasuries vs corporates"
        value={`${fmtSigned(japan?.treas_net_12m)} / ${fmtSigned(japan?.corp_net_12m)}`}
        sub={
          <>
            $bn, LT only (excl. bills); Treasuries incl. bills {fmtSigned(bills?.japan_12m)} ({str(bills?.asof) ?? "n/a"})
          </>
        }
        asof={d.foreign_bid?.asof}
        src={concreteSrc(d.foreign_bid, "japan_treas_net")}
      />
      <Tile
        label="CCC OAS vs 2026 high"
        value={`${fmt(ccc?.latest, 2)} / ${fmt(ccc?.hi_2026, 2)}`}
        sub={<>% OAS (ICE BofA via FRED); end-2025 {fmt(ccc?.end_2025, 2)}; CCC−B gap {fmt(d.breaking?.ccc_b_gap?.latest, 2)} pp</>}
        asof={ccc?.asof}
        src={ccc?.src}
      />
      <Tile
        label="30y UST + 10y term premium"
        value={`${fmt(dgs30?.latest, 2)}% / ${fmt(kw?.latest, 2)}`}
        sub={<>DGS30 % and Kim-Wright TP10 pp ({str(kw?.asof) ?? "n/a"}); ACM TP10 {fmt(d.crowding?.term_premium?.acm10?.latest, 3)} ({str(d.crowding?.term_premium?.acm10?.asof) ?? "n/a"})</>}
        asof={dgs30?.asof}
        src={dgs30?.src}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// 2. Issuance
// ---------------------------------------------------------------------------

// Backend vocabulary (seed rating_buckets: AAA..B, unrated-private,
// ABS-tranched, not-captured) -> the display vocabulary of RATING_COLOR.
function normRating(r: unknown): string {
  const s = typeof r === "string" && r.trim() ? r.trim() : "unknown";
  if (RATING_COLOR[s]) return s;
  const low = s.toLowerCase();
  if (low.startsWith("unrated") || low.includes("private")) return "unrated/private";
  if (low.includes("abs") || low.includes("cmbs")) return "ABS/CMBS-tranched";
  if (/not[-_ ]?captured/.test(low) || low === "n/a" || low.startsWith("n/a")) return "unknown";
  return s;
}

// Merge month-row keys through normRating so two spellings of one rating
// never become two stacked series.
function normRatingRows(rowsIn: AiDebtMonthRow[]): AiDebtMonthRow[] {
  return rowsIn.map((r) => {
    const out: AiDebtMonthRow = { month: r.month };
    for (const [k, v] of Object.entries(r)) {
      if (k === "month" || !isNum(v)) continue;
      const nk = normRating(k);
      out[nk] = Math.round((((out[nk] as number | undefined) ?? 0) + v) * 100) / 100;
    }
    return out;
  });
}

// Monthly stacks by rating are derived from the deal rows (the payload ships
// monthly by bucket only, unless `by_month_rating` is present).
function monthlyByRating(deals: AiDebtDeal[], months: string[]): AiDebtMonthRow[] {
  const acc = new Map<string, Record<string, number>>();
  for (const m of months) acc.set(m, {});
  for (const dl of deals) {
    if (!dl?.included || !isNum(dl.size_usd_bn) || typeof dl.date !== "string") continue;
    const m = dl.date.slice(0, 7);
    const cell = acc.get(m) ?? {};
    const k = normRating(dl.rating_bucket);
    cell[k] = Math.round(((cell[k] ?? 0) + dl.size_usd_bn) * 100) / 100;
    acc.set(m, cell);
  }
  return [...acc.entries()].sort(([a], [b]) => (a < b ? -1 : 1)).map(([month, cell]) => ({ month, ...cell }));
}

function monthlyByBucket(deals: AiDebtDeal[]): AiDebtMonthRow[] {
  const acc = new Map<string, Record<string, number>>();
  for (const dl of deals) {
    if (!dl?.included || !isNum(dl.size_usd_bn) || typeof dl.date !== "string") continue;
    const m = dl.date.slice(0, 7);
    const cell = acc.get(m) ?? {};
    const b = str(dl.bucket) ?? "unknown";
    cell[b] = Math.round(((cell[b] ?? 0) + dl.size_usd_bn) * 100) / 100;
    acc.set(m, cell);
  }
  return [...acc.entries()].sort(([a], [b]) => (a < b ? -1 : 1)).map(([month, cell]) => ({ month, ...cell }));
}

// Series present in the rows: a key that is 0.0 every month (the backend ships
// a true zero for every category) gets no legend entry and no empty bar.
function seriesKeys(rowsIn: AiDebtMonthRow[], order: string[]): string[] {
  const seen = new Set<string>();
  for (const r of rowsIn) for (const k of Object.keys(r)) if (k !== "month" && isNum(r[k]) && r[k] !== 0) seen.add(k);
  const known = order.filter((k) => seen.has(k));
  const extra = [...seen].filter((k) => !order.includes(k)).sort();
  return [...known, ...extra];
}

// `{bucket: {year: v}}` or `{year: {bucket: v}}` — accept either orientation.
// `norm` merges row keys (e.g. the backend's rating vocabulary) before display.
function yearTable(t: Record<string, Record<string, number | null>> | null | undefined, norm: (k: string) => string = (k) => k): { rows: string[]; years: string[]; get: (r: string, y: string) => number | null } {
  if (!t || typeof t !== "object") return { rows: [], years: [], get: () => null };
  const outer = Object.keys(t);
  const yearLike = (k: string) => /^\d{4}$/.test(k);
  const outerIsYear = outer.length > 0 && outer.every(yearLike);
  const inner = new Set<string>();
  for (const k of outer) for (const j of Object.keys(t[k] ?? {})) inner.add(j);
  const years = (outerIsYear ? outer : [...inner]).filter(yearLike).sort();
  const rawRows = outerIsYear ? [...inner] : outer;
  const rowKeys = [...new Set(rawRows.map(norm))];
  const get = (r: string, y: string) => {
    let sum: number | null = null;
    for (const raw of rawRows) {
      if (norm(raw) !== r) continue;
      const v = outerIsYear ? t[y]?.[raw] : t[raw]?.[y];
      if (isNum(v)) sum = (sum ?? 0) + v;
    }
    return sum === null ? null : Math.round(sum * 100) / 100;
  };
  return { rows: rowKeys, years, get };
}

function IssuancePanel({ iss, spreads30 }: { iss: AiDebtIssuance; spreads30: AiDebtSpreadAtIssue[] }) {
  const [mode, setMode] = useState<"bucket" | "rating">("bucket");
  const [showAll, setShowAll] = useState(false);
  const deals = arr(iss.deals).filter((x) => x && typeof x.date === "string");

  const byBucket = useMemo(() => {
    const given = arr(iss.by_month).filter((r) => r && typeof r.month === "string");
    return given.length ? given : monthlyByBucket(deals);
  }, [iss.by_month, deals]);
  const months = byBucket.map((r) => r.month);
  const byRating = useMemo(() => {
    const given = arr(iss.by_month_rating).filter((r) => r && typeof r.month === "string");
    return given.length ? normRatingRows(given) : monthlyByRating(deals, months);
  }, [iss.by_month_rating, deals, months]);

  const chartRows = mode === "bucket" ? byBucket : byRating;
  const keys = seriesKeys(chartRows, mode === "bucket" ? BUCKET_ORDER : RATING_ORDER);
  const colorMap = mode === "bucket" ? BUCKET_COLOR : RATING_COLOR;

  const bucketT = yearTable(iss.by_bucket_year);
  const ratingT = yearTable(iss.by_rating_year, normRating);
  const years = Object.keys(iss.totals_by_year ?? {}).filter((y) => /^\d{4}$/.test(y)).sort();

  const spreadFor = (dl: AiDebtDeal): number | null => {
    const name = typeof dl.issuer === "string" ? dl.issuer.toLowerCase() : "";
    const first = name.split(" ")[0];
    if (!first) return null;
    const hit = spreads30.find((s) => {
      if (!s || s.date !== dl.date || typeof s.issuer !== "string") return false;
      const sn = s.issuer.toLowerCase();
      const sf = sn.split(" ")[0];
      return sn.startsWith(first) || (sf !== "" && name.startsWith(sf));
    });
    return hit && isNum(hit.bp) ? hit.bp : null;
  };

  const sorted = [...deals].sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
  const visible = showAll ? sorted : sorted.slice(0, 25);
  const nIncluded = deals.filter((x) => x.included).length;
  const cumulative = years.reduce<number | null>((acc, y) => {
    const v = iss.totals_by_year?.[y];
    return isNum(v) ? (acc ?? 0) + v : acc;
  }, null);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
          <span className="text-xs text-slate-300">
            Monthly issuance, $bn at pricing — stacked by {mode}
            <span className="ml-2 font-mono text-slate-500">
              seed {str(iss.seed_rev) ?? "n/a"} · {nIncluded} deals in tally · {fmtBn(cumulative)} since {years[0] ?? "start"}
            </span>
          </span>
          <span className="inline-flex overflow-hidden rounded border border-panelborder text-[10px]">
            {(["bucket", "rating"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`px-2 py-0.5 font-semibold ${mode === m ? "bg-sky-500/10 text-sky-300" : "text-slate-400 hover:text-slate-200"}`}
              >
                by {m}
              </button>
            ))}
          </span>
        </div>
        {chartRows.length === 0 || keys.length === 0 ? (
          <Unavailable what="Monthly issuance chart" why="no monthly rows in payload" />
        ) : (
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartRows} margin={{ top: 6, right: 8, left: -12, bottom: 0 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="month" tick={tickStyle} interval={2} />
                <YAxis tick={tickStyle} />
                <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number | string, name: string) => [`$${fmt(Number(v), 2)}bn`, RATING_LABEL[name] ?? name]} />
                <Legend wrapperStyle={legendStyle} iconSize={8} formatter={(name: string) => RATING_LABEL[name] ?? name} />
                {keys.map((k) => (
                  <Bar key={k} dataKey={k} stackId="m" name={k} fill={colorFor(colorMap, k)} isAnimationActive={false} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <YearTable title="By bucket × year ($bn)" t={bucketT} colors={BUCKET_COLOR} totals={iss.totals_by_year} years={years} />
        <YearTable title="By rating at issue × year ($bn)" t={ratingT} colors={RATING_COLOR} totals={iss.totals_by_year} years={years} labels={RATING_LABEL} />
        <div>
          <div className="mb-1 text-xs text-slate-300">Share of US corporate issuance and of net Treasury supply</div>
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-[10px] uppercase tracking-wide text-slate-500">
                <th className="py-1 pr-2 text-left font-normal">year</th>
                <th className="px-1 py-1 text-right font-normal">hyperscaler USD</th>
                <th className="px-1 py-1 text-right font-normal">all AI USD</th>
                <th className="px-1 py-1 text-right font-normal">SIFMA</th>
                <th className="px-1 py-1 text-right font-normal">% hyper</th>
                <th className="pl-1 py-1 text-right font-normal">% all</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(iss.share ?? {}).map(([y, s]) => (
                <tr key={y} className="border-t border-panelborder/50 font-mono tabular-nums text-slate-300">
                  <td className="py-1 pr-2 text-left">{y}</td>
                  <td className="px-1 py-1 text-right">{fmt(s?.hyperscaler_usd_bn)}</td>
                  <td className="px-1 py-1 text-right">{fmt(s?.all_ai_usd_bn)}</td>
                  <td className="px-1 py-1 text-right">{fmt(s?.sifma_us_corp_bn, 0)}</td>
                  <td className="px-1 py-1 text-right">{fmtPct(s?.pct_hyperscaler, 2)}</td>
                  <td className="pl-1 py-1 text-right">{fmtPct(s?.pct_all, 2)}</td>
                </tr>
              ))}
              {Object.keys(iss.share ?? {}).length === 0 && (
                <tr>
                  <td colSpan={6} className="py-1 text-slate-600">share: n/a</td>
                </tr>
              )}
            </tbody>
          </table>
          <p className="mt-1 text-[10px] leading-snug text-slate-500">
            USD legs over a US-only denominator (SIFMA US corporate issuance, $bn; 2026 = YTD through the latest SIFMA month). <SrcLink href={Object.values(iss.share ?? {})[0]?.src} label="SIFMA" />
          </p>
          <table className="mt-2 w-full text-[11px]">
            <thead>
              <tr className="text-[10px] uppercase tracking-wide text-slate-500">
                <th className="py-1 pr-2 text-left font-normal">window</th>
                <th className="px-1 py-1 text-right font-normal">AI tally</th>
                <th className="px-1 py-1 text-right font-normal">net mkt UST</th>
                <th className="pl-1 py-1 text-right font-normal">ratio</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(iss.vs_treasury ?? {}).map(([w, v]) => (
                <tr key={w} className="border-t border-panelborder/50 font-mono tabular-nums text-slate-300" title={str(v?.basis) ?? undefined}>
                  <td className="py-1 pr-2 text-left">{w}</td>
                  <td className="px-1 py-1 text-right">{fmt(v?.ai_bn)}</td>
                  <td className="px-1 py-1 text-right">{fmt(v?.net_marketable_ust_bn, 0)}</td>
                  <td className="pl-1 py-1 text-right">{fmtPct(v?.pct)}</td>
                </tr>
              ))}
              {Object.keys(iss.vs_treasury ?? {}).length === 0 && (
                <tr>
                  <td colSpan={4} className="py-1 text-slate-600">vs Treasury supply: n/a</td>
                </tr>
              )}
            </tbody>
          </table>
          <p className="mt-1 text-[10px] leading-snug text-slate-500">
            Gross tally (all currencies) over NET marketable Treasury issuance (MSPD, gross of Fed holdings): the numerator is gross and partly non-USD; hover a row for its window.
          </p>
        </div>
      </div>

      <div>
        <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
          <span className="text-xs text-slate-300">
            Deal table — {sorted.length} rows, newest first{showAll ? "" : ` (showing ${visible.length})`}
          </span>
          <span className="text-[10px] text-slate-500">
            provenance <VerifBadge v="P" /> primary filing · <VerifBadge v="R" /> press release · <VerifBadge v="S" /> search snippet
          </span>
        </div>
        <div className="scroll-thin max-h-[28rem] overflow-auto">
          <table className="w-full min-w-[820px] text-[11px]">
            <thead className="sticky top-0 bg-[#0f172a]">
              <tr className="text-[10px] uppercase tracking-wide text-slate-500">
                <th className="py-1 pr-2 text-left font-normal">date</th>
                <th className="px-1 py-1 text-left font-normal">issuer</th>
                <th className="px-1 py-1 text-left font-normal">bucket</th>
                <th className="px-1 py-1 text-right font-normal">size</th>
                <th className="px-1 py-1 text-right font-normal">$bn</th>
                <th className="px-1 py-1 text-left font-normal">rating</th>
                <th className="px-1 py-1 text-right font-normal">30y T+</th>
                <th className="px-1 py-1 text-left font-normal">flags</th>
                <th className="px-1 py-1 text-center font-normal">verif</th>
                <th className="pl-1 py-1 text-left font-normal">src</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((dl, i) => (
                <tr key={`${dl.date}-${dl.issuer}-${i}`} className={`border-t border-panelborder/50 ${dl.included ? "text-slate-300" : "text-slate-600"}`} title={str(dl.note) ?? undefined}>
                  <td className="py-1 pr-2 font-mono">{dl.date}</td>
                  <td className="px-1 py-1">
                    {str(dl.issuer) ?? "n/a"}
                    {!dl.included && <span className="ml-1 text-[9px] uppercase text-slate-600">excluded</span>}
                  </td>
                  <td className="px-1 py-1">
                    <span className="mr-1 inline-block h-2 w-2 rounded-sm align-middle" style={{ backgroundColor: colorFor(BUCKET_COLOR, dl.bucket) }} />
                    {str(dl.bucket) ?? "n/a"}
                  </td>
                  <td className="px-1 py-1 text-right font-mono tabular-nums">
                    {isNum(dl.size_bn) ? `${fmt(dl.size_bn, 2)} ${str(dl.ccy) ?? ""}` : "n/a"}
                  </td>
                  <td className="px-1 py-1 text-right font-mono tabular-nums">{fmt(dl.size_usd_bn, 2)}</td>
                  <td className="px-1 py-1" title={str(dl.rating_at_issue) ?? undefined}>
                    {RATING_LABEL[normRating(dl.rating_bucket)] ?? normRating(dl.rating_bucket)}
                  </td>
                  <td className="px-1 py-1 text-right font-mono tabular-nums">{isNum(spreadFor(dl)) ? spreadFor(dl) : "—"}</td>
                  <td className="px-1 py-1 text-[9px] uppercase tracking-wide text-slate-500">{arr(dl.flags).join(" ") || "—"}</td>
                  <td className="px-1 py-1 text-center">
                    <VerifBadge v={dl.verif} />
                  </td>
                  <td className="pl-1 py-1">
                    <SrcLink href={dl.src} />
                  </td>
                </tr>
              ))}
              {visible.length === 0 && (
                <tr>
                  <td colSpan={10} className="py-2 text-slate-600">no deal rows in payload</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {sorted.length > 25 && (
          <button onClick={() => setShowAll((v) => !v)} className="mt-1 text-[10px] text-sky-400/80 hover:text-sky-300">
            {showAll ? "show fewer" : `show all ${sorted.length}`}
          </button>
        )}
        <p className="mt-1 text-[10px] leading-snug text-slate-500">
          Size in the deal's currency and in USD at the FX recorded on the row; 30y T+ = spread at issue of the longest tranche where a filing prints it; flags: refi = refinancing, spv = off-balance-sheet vehicle, convert, non_usd. Excluded rows (announced, undrawn, unwound, duplicates) are kept for the record. Hover a row for its note.
        </p>
      </div>

      <div>
        <div className="mb-1 text-xs text-slate-300">New filings not yet in the tally (EDGAR poll, auto-extracted, pending review)</div>
        {arr(iss.new_filings).length === 0 ? (
          <p className="text-[11px] text-slate-500">none pending{iss.new_filings === null || iss.new_filings === undefined ? " (filings list: n/a)" : ""}</p>
        ) : (
          <ul className="flex flex-col gap-1 text-[11px]">
            {arr(iss.new_filings).map((f, i) => (
              <li key={`${f?.filed}-${i}`} className="flex flex-wrap items-baseline gap-x-2 text-slate-300">
                <span className="font-mono text-slate-400">{str(f?.filed) ?? "n/a"}</span>
                <span>{str(f?.issuer) ?? "n/a"}</span>
                <span className="rounded border border-panelborder px-1 text-[9px] uppercase text-slate-500">{str(f?.form) ?? "?"}</span>
                <span className="font-mono text-slate-400">
                  {f?.extracted && isNum(f.extracted.size_bn) ? `${f.extracted.ccy && f.extracted.ccy !== "USD" ? `${f.extracted.ccy} ` : "$"}${fmt(f.extracted.size_bn, 2)}bn${f.extracted.partial ? " (partial)" : ""}` : "size n/a"}
                  {f?.extracted && arr(f.extracted.coupons).length ? ` · ${arr(f.extracted.coupons).map((c) => (isNum(c) ? c : "FRN")).join("/")}%` : ""}
                  {f?.extracted && arr(f.extracted.maturities).length ? ` · ${arr(f.extracted.maturities).join("/")}` : ""}
                  {f?.extracted ? spreadLabel(f.extracted) : ""}
                </span>
                <span className="text-slate-500">{str(f?.status) ?? ""}</span>
                <SrcLink href={f?.url} label="filing" />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

// "T+53/68" when every spread is over the Treasury; otherwise the benchmark the
// sheet names per tranche (Bund+114.8, GoC+110, swap+109), never a hard-coded "T+".
function spreadLabel(x: NonNullable<AiDebtFiling["extracted"]>): string {
  const tr = arr(x.tranches).filter((t) => t && isNum(t.spread_bp));
  if (tr.length) {
    const bms = new Set(tr.map((t) => t.benchmark ?? "?"));
    if (bms.size === 1 && bms.has("UST")) return ` · T+${tr.map((t) => t.spread_bp).join("/")}`;
    return ` · ${tr.map((t) => `${t.benchmark === "UST" ? "T" : (t.benchmark ?? "?")}+${t.spread_bp}`).join(" ")}`;
  }
  const sp = arr(x.spreads).filter((v) => v !== null && v !== undefined);
  return sp.length ? ` · +${sp.join("/")} bp (benchmark n/a)` : "";
}

function YearTable({
  title,
  t,
  colors,
  totals,
  years,
  labels = {},
}: {
  title: string;
  t: ReturnType<typeof yearTable>;
  colors: Record<string, string>;
  totals: Record<string, number | null> | null | undefined;
  years: string[];
  labels?: Record<string, string>;
}) {
  const ys = t.years.length ? t.years : years;
  const order = Object.keys(colors);
  const rowsSorted = [...t.rows].sort((a, b) => {
    const ia = order.indexOf(a);
    const ib = order.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });
  return (
    <div>
      <div className="mb-1 text-xs text-slate-300">{title}</div>
      {rowsSorted.length === 0 ? (
        <Unavailable what={title} why="n/a" />
      ) : (
        <table className="w-full text-[11px]">
          <thead>
            <tr className="text-[10px] uppercase tracking-wide text-slate-500">
              <th className="py-1 pr-2 text-left font-normal">row</th>
              {ys.map((y) => (
                <th key={y} className="px-1 py-1 text-right font-normal">{y}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rowsSorted.map((r) => (
              <tr key={r} className="border-t border-panelborder/50 font-mono tabular-nums text-slate-300">
                <td className="py-1 pr-2 font-sans">
                  <span className="mr-1 inline-block h-2 w-2 rounded-sm align-middle" style={{ backgroundColor: colorFor(colors, r) }} />
                  {labels[r] ?? r}
                </td>
                {ys.map((y) => (
                  <td key={y} className="px-1 py-1 text-right">{fmt(t.get(r, y))}</td>
                ))}
              </tr>
            ))}
            <tr className="border-t border-panelborder font-mono tabular-nums text-slate-100">
              <td className="py-1 pr-2 font-sans font-semibold">total</td>
              {ys.map((y) => (
                <td key={y} className="px-1 py-1 text-right font-semibold">{fmt(totals?.[y])}</td>
              ))}
            </tr>
          </tbody>
        </table>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 3. Who holds US corporates (Z.1)
// ---------------------------------------------------------------------------

// Fallback labels; the backend's `z1.labels` map wins when present.
const SECTOR_LABEL: Record<string, string> = {
  rest_of_world: "Rest of world",
  rest_of_world_ex_abs: "Rest of world (ex ABS, memo line)",
  life_insurers: "Life insurers",
  pc_insurers: "P&C insurers",
  private_pensions: "Private pension funds",
  state_local_pensions: "State & local pension funds",
  federal_pensions: "Federal government retirement funds",
  mutual_funds: "Mutual funds",
  etfs: "ETFs",
  closed_end_funds: "Closed-end funds",
  hedge_funds: "Hedge funds",
  money_market_funds: "Money market funds",
  other_financial: "Other financial (GSEs, brokers, other funds)",
  banks: "Banks (private depository)",
  banks_us_chartered: "US-chartered banks",
  foreign_banking_offices: "Foreign banking offices in the US",
  other_depository: "Credit unions, affiliated-area banks",
  households: "Households (residual)",
  general_government: "Federal, state & local governments",
  all_sectors: "All sectors",
};
// Short names for the bar chart's category axis: the backend's long labels
// wrap three deep inside the 150px axis and collide. The flows table keeps
// the long ones; the tooltip shows the full label.
const CHART_LABEL: Record<string, string> = {
  rest_of_world: "Rest of world",
  rest_of_world_ex_abs: "Rest of world (ex ABS)",
  life_insurers: "Life insurers",
  pc_insurers: "P&C insurers",
  private_pensions: "Private pensions",
  state_local_pensions: "State & local pensions",
  federal_pensions: "Federal retirement funds",
  mutual_funds: "Mutual funds",
  etfs: "ETFs",
  closed_end_funds: "Closed-end funds",
  hedge_funds: "Hedge funds",
  money_market_funds: "Money market funds",
  other_financial: "Other financial",
  banks: "Banks",
  banks_us_chartered: "US-chartered banks",
  foreign_banking_offices: "Foreign bank offices",
  other_depository: "Credit unions, other",
  households: "Households (residual)",
  general_government: "Governments",
};
const PENSION_SECTORS = new Set(["private_pensions", "state_local_pensions", "federal_pensions"]);
const isPension = (k: string) => PENSION_SECTORS.has(k) || /pension/i.test(k);

function HoldersPanel({ h }: { h: AiDebtHolders }) {
  const z1 = h.z1;
  const levels = z1?.levels ?? {};
  const flows = z1?.flows_saar_last4 ?? {};
  const label = (k: string) => str(z1?.labels?.[k]) ?? SECTOR_LABEL[k] ?? k.replace(/_/g, " ");
  const chartLabel = (k: string) => CHART_LABEL[k] ?? label(k);
  // rest_of_world_ex_abs is a memo line inside rest_of_world: show one, not both
  const hasRow = "rest_of_world" in levels || "rest_of_world" in flows;
  const sectors = Object.keys({ ...levels, ...flows }).filter((k) => k !== "all_sectors" && !(hasRow && k === "rest_of_world_ex_abs"));
  const bars = sectors
    .map((k) => ({ sector: chartLabel(k), key: k, full: label(k), level: isNum(levels[k]) ? levels[k] : null }))
    .filter((r) => r.level !== null)
    .sort((a, b) => (b.level ?? 0) - (a.level ?? 0));
  const quarters = arr(z1?.flows_quarters);
  const total = levels["all_sectors"];
  if (!z1) return <Unavailable what="Z.1 holder data" why={str(h.note) ?? "n/a"} />;
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <div>
        <div className="mb-1 text-xs text-slate-300">
          Holdings of corporate & foreign bonds, $bn
          {isNum(total) && <span className="ml-2 font-mono text-slate-500">all sectors {fmt(total, 0)}</span>}
        </div>
        {bars.length === 0 ? (
          <Unavailable what="Holder levels" why="no sector levels in payload" />
        ) : (
          <div style={{ height: 26 * bars.length + 30 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={bars} layout="vertical" margin={{ top: 4, right: 40, left: 8, bottom: 0 }}>
                <CartesianGrid stroke={GRID} horizontal={false} />
                <XAxis type="number" tick={tickStyle} />
                <YAxis type="category" dataKey="sector" tick={{ ...tickStyle, fill: "#94a3b8" }} width={150} interval={0} />
                <Tooltip
                  contentStyle={TOOLTIP_STYLE}
                  formatter={(v: number | string) => [`$${fmt(Number(v), 0)}bn`, "level"]}
                  labelFormatter={(l: unknown) => bars.find((b) => b.sector === l)?.full ?? String(l)}
                />
                <Bar dataKey="level" name="level" isAnimationActive={false} radius={[0, 3, 3, 0]} label={{ position: "right", fontSize: 9, fill: "#94a3b8", formatter: (v: unknown) => fmt(v, 0) }}>
                  {bars.map((b) => (
                    <Cell key={b.key} fill={isPension(b.key) ? PENSION : BLUE} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
        <p className="mt-1 text-[10px] leading-snug text-slate-500">
          <span className="mr-1 inline-block h-2 w-2 rounded-sm align-middle" style={{ backgroundColor: PENSION }} /> pension sectors ·{" "}
          <span className="mr-1 inline-block h-2 w-2 rounded-sm align-middle" style={{ backgroundColor: BLUE }} /> other holders{hasRow ? "; the ex-ABS rest-of-world memo line is inside rest of world and not drawn separately" : ""}. <AsOf asof={h.asof} src={z1.src} />
        </p>
      </div>
      <div>
        <div className="mb-1 text-xs text-slate-300">Net purchases, last four quarters ($bn, annualised)</div>
        <table className="w-full text-[11px]">
          <thead>
            <tr className="text-[10px] uppercase tracking-wide text-slate-500">
              <th className="py-1 pr-2 text-left font-normal">sector</th>
              {(quarters.length ? quarters : ["q-3", "q-2", "q-1", "latest"]).map((q, i) => (
                <th key={`${q}-${i}`} className="px-1 py-1 text-right font-normal">{q.replace(/-\d{2}$/, "")}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...sectors, ...(flows["all_sectors"] ? ["all_sectors"] : [])].map((k) => (
              <tr key={k} className={`border-t border-panelborder/50 font-mono tabular-nums ${isPension(k) ? "text-amber-200" : "text-slate-300"}`}>
                <td className="py-1 pr-2 font-sans">{label(k)}</td>
                {(arr(flows[k]).length ? arr(flows[k]) : [null, null, null, null]).map((v, i) => (
                  <td key={i} className="px-1 py-1 text-right">{fmtSigned(v, 0)}</td>
                ))}
              </tr>
            ))}
            {sectors.length === 0 && (
              <tr>
                <td colSpan={5} className="py-1 text-slate-600">no sector flows in payload</td>
              </tr>
            )}
          </tbody>
        </table>
        {z1.pensions && (
          <p className="mt-2 text-[10px] leading-snug text-slate-400">
            Pensions: private {fmtBn(z1.pensions.private?.level, 0)} held, {fmtSigned(z1.pensions.private?.flow_saar, 0)} latest flow; state & local {fmtBn(z1.pensions.state_local?.level, 0)} held, {fmtSigned(z1.pensions.state_local?.flow_saar, 0)} latest flow.
          </p>
        )}
        {str(h.note) && <p className="mt-1 text-[10px] leading-snug text-slate-500">{h.note}</p>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 4. Foreign bid by country (TIC)
// ---------------------------------------------------------------------------

function CountryRow({ c }: { c: AiDebtCountry }) {
  return (
    <tr className="border-t border-panelborder/50 font-mono tabular-nums text-slate-300">
      <td className="py-1 pr-2 font-sans">
        {c.name}
        {str(c.code) && <span className="ml-1 text-[9px] text-slate-600">{c.code}</span>}
      </td>
      <td className="px-1 py-1 text-right">{fmtSigned(c.treas_net_12m)}</td>
      <td className="px-1 py-1 text-center">
        <Sparkline values={c.treas_spark} color={BLUE} />
      </td>
      <td className="px-1 py-1 text-right">{fmtSigned(c.corp_net_12m)}</td>
      <td className="px-1 py-1 text-center">
        <Sparkline values={c.corp_spark} color={ORANGE} />
      </td>
      <td className="px-1 py-1 text-right">{fmt(c.treas_pos, 0)}</td>
      <td className="px-1 py-1 text-right">{fmt(c.corp_pos, 0)}</td>
      <td className="pl-1 py-1 text-right">{fmtPct(c.corp_share_of_lt)}</td>
    </tr>
  );
}

function ForeignBidPanel({ fb }: { fb: AiDebtForeignBid }) {
  const countries = arr(fb.countries).filter((c) => c && typeof c.name === "string");
  const attributable = countries.filter((c) => !c.custody_centre);
  const custody = countries.filter((c) => c.custody_centre);
  const s = fb.series;
  const months = arr(s?.months);
  const flowRows = useMemo(
    () =>
      rows(months, {
        off_corp: s?.official?.corp,
        nonoff_corp: s?.non_official?.corp,
        gt_treas: s?.grand_total?.treas,
        gt_corp: s?.grand_total?.corp,
      }),
    [months, s],
  );
  const head = (
    <tr className="text-[10px] uppercase tracking-wide text-slate-500">
      <th className="py-1 pr-2 text-left font-normal">country</th>
      <th className="px-1 py-1 text-right font-normal">12m Treasuries</th>
      <th className="px-1 py-1 text-center font-normal">24m</th>
      <th className="px-1 py-1 text-right font-normal">12m corporates</th>
      <th className="px-1 py-1 text-center font-normal">24m</th>
      <th className="px-1 py-1 text-right font-normal">Tsy held</th>
      <th className="px-1 py-1 text-right font-normal">corp held</th>
      <th className="pl-1 py-1 text-right font-normal">corp % of LT</th>
    </tr>
  );
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <div className="mb-1 text-xs text-slate-300">
            Net purchases of US long-term securities, $bn, 12 months to {str(fb.asof) ?? "n/a"} (LT = excl. bills); holdings at month-end
          </div>
          {countries.length === 0 ? (
            <Unavailable what="Country table" why="no country rows in payload" />
          ) : (
            <table className="w-full text-[11px]">
              <thead>{head}</thead>
              <tbody>
                {attributable.map((c) => (
                  <CountryRow key={c.name} c={c} />
                ))}
                {custody.length > 0 && (
                  <tr>
                    <td colSpan={8} className="pt-2 pb-0.5 text-[10px] uppercase tracking-wide text-slate-500">
                      custody & fund centres — unattributable (booked to the custodian's country, not the owner's)
                    </td>
                  </tr>
                )}
                {custody.map((c) => (
                  <CountryRow key={c.name} c={c} />
                ))}
              </tbody>
            </table>
          )}
          <p className="mt-1 text-[10px] leading-snug text-slate-500">
            <span className="mr-1 inline-block h-2 w-2 rounded-sm align-middle" style={{ backgroundColor: BLUE }} /> Treasuries ·{" "}
            <span className="mr-1 inline-block h-2 w-2 rounded-sm align-middle" style={{ backgroundColor: ORANGE }} /> corporate bonds (sparklines = monthly net, zero line). TIC via FRED mirrors FORLT&#123;TREAS,CORP&#125;&#123;NET,POS&#125;; country codes shown where the mirror names them. <SrcLink href={concreteSrc(fb, "japan_treas_net")} label="src (Japan Treasuries net)" /> · <SrcLink href={concreteSrc(fb, "cslt")} label="CSLT" />
          </p>
        </div>
        <div className="lg:col-span-2">
          <div className="mb-1 text-xs text-slate-300">Treasuries incl. bills (TIC CSLT, "All Countries")</div>
          {fb.bills_inclusive ? (
            <div className="rounded border border-panelborder/60 px-3 py-2">
              <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-sm text-slate-200">
                <span>Japan {fmtSigned(fb.bills_inclusive.japan_12m)}</span>
                <span>All countries {fmtSigned(fb.bills_inclusive.all_12m)}</span>
              </div>
              <p className="mt-1 text-[10px] leading-snug text-slate-500">{str(fb.bills_inclusive.note) ?? "$bn, 12 months"}</p>
              <AsOf asof={fb.bills_inclusive.asof ?? fb.asof} src={fb.bills_inclusive.src} />
            </div>
          ) : (
            <Unavailable what="Bills-inclusive flows" why="n/a" />
          )}
          <div className="mt-3 mb-1 text-xs text-slate-300">Official vs non-official: corporate bonds, monthly $bn</div>
          {flowRows.length === 0 ? (
            <Unavailable what="Official / non-official series" why="n/a" />
          ) : (
            <div className="h-40">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={flowRows} margin={{ top: 6, right: 8, left: -14, bottom: 0 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="x" tick={tickStyle} minTickGap={40} />
                  <YAxis tick={tickStyle} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number | string) => fmtSigned(Number(v))} />
                  <Legend wrapperStyle={legendStyle} iconSize={8} />
                  <ReferenceLine y={0} stroke="#334155" />
                  <Line dataKey="off_corp" name="foreign official, corporates" stroke={VIOLET} dot={false} strokeWidth={1.5} connectNulls={false} isAnimationActive={false} />
                  <Line dataKey="nonoff_corp" name="non-official, corporates" stroke={ORANGE} dot={false} strokeWidth={1.5} connectNulls={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>
      {flowRows.length > 0 && (
        <div>
          <div className="mb-1 text-xs text-slate-300">Grand Total: LT Treasuries vs corporate bonds, monthly net $bn</div>
          <div className="h-40">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={flowRows} margin={{ top: 6, right: 8, left: -14, bottom: 0 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="x" tick={tickStyle} minTickGap={50} />
                <YAxis tick={tickStyle} />
                <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number | string) => fmtSigned(Number(v))} />
                <Legend wrapperStyle={legendStyle} iconSize={8} />
                <ReferenceLine y={0} stroke="#334155" />
                <Line dataKey="gt_treas" name="LT Treasuries" stroke={BLUE} dot={false} strokeWidth={1.5} connectNulls={false} isAnimationActive={false} />
                <Line dataKey="gt_corp" name="corporate bonds" stroke={ORANGE} dot={false} strokeWidth={1.5} connectNulls={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-1 text-[10px] leading-snug text-slate-500">
            "Grand Total" (FRED mirror, 99996) and "All Countries" (CSLT) are different aggregates; both are labelled where used. TIC cannot say whether any of this is AI paper.
          </p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 5. Japan
// ---------------------------------------------------------------------------

function JapanPanel({ j }: { j: AiDebtJapan }) {
  const boj = j.boj;
  const bojRows = useMemo(() => {
    const m = arr(boj?.months);
    if (!m.length) return [];
    return rows(m, { sovereign: rolling12(arr(boj?.sovereign)), nonsovereign: rolling12(arr(boj?.nonsovereign)), total: rolling12(arr(boj?.total)) }).filter((r) => r.total !== null || r.sovereign !== null);
  }, [boj]);
  const mof = j.mof_by_type;
  const mofRows = useMemo(() => {
    const m = arr(mof?.months);
    if (!m.length) return [];
    return rows(m, {
      banks: rolling12(arr(mof?.banks)),
      life: rolling12(arr(mof?.life)),
      trust_accounts: rolling12(arr(mof?.trust_accounts)),
      inv_trusts: rolling12(arr(mof?.inv_trusts)),
    }).filter((r) => r.banks !== null || r.trust_accounts !== null);
  }, [mof]);
  const jgb = j.jgb;
  const jgbRows = useMemo(() => rows(arr(jgb?.dates), { y10: arr(jgb?.y10), y30: arr(jgb?.y30) }), [jgb]);
  const wk = j.mof_weekly;
  const wkRows = useMemo(() => rows(arr(wk?.weeks), { net: arr(wk?.net) }), [wk]);
  const lastIdx = (xs: Array<Record<string, unknown>>) => xs.length - 1;

  return (
    <div className="flex flex-col gap-4">
      {str(j.read) && (
        <div className="rounded border-l-4 border-slate-500/70 bg-slate-500/5 px-3 py-2 text-xs leading-relaxed text-slate-300">
          <span className="font-semibold text-slate-200">Read: </span>
          {j.read}
        </div>
      )}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div>
          <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
            <span className="text-xs text-slate-300">BoJ BoP: Japanese net purchases of US long-term debt, 12m sum, JPY trn</span>
            {boj?.sum_12m && (
              <span className="font-mono text-[10px] text-slate-400">
                12m: sovereign {fmtSigned(boj.sum_12m.sovereign, 2)} · non-sovereign {fmtSigned(boj.sum_12m.nonsovereign, 2)}
              </span>
            )}
          </div>
          {bojRows.length === 0 ? (
            <Unavailable what="BoJ series" why="n/a" />
          ) : (
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={bojRows} margin={{ top: 6, right: 36, left: -14, bottom: 0 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="x" tick={tickStyle} interval={23} />
                  <YAxis tick={tickStyle} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number | string) => fmtSigned(Number(v), 2)} />
                  <Legend wrapperStyle={legendStyle} iconSize={8} />
                  <ReferenceLine y={0} stroke="#334155" />
                  <Line dataKey="sovereign" name="sovereign (govt + agency + local)" stroke={BLUE} dot={false} strokeWidth={1.6} connectNulls={false} isAnimationActive={false} label={lastLabel(lastIdx(bojRows), BLUE)} />
                  <Line dataKey="nonsovereign" name="non-sovereign residual (corporates et al.)" stroke={ORANGE} dot={false} strokeWidth={1.6} connectNulls={false} isAnimationActive={false} label={lastLabel(lastIdx(bojRows), ORANGE)} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
          <p className="mt-1 text-[10px] leading-snug text-slate-500">
            {str(boj?.unit) ?? "JPY trn"}; sovereign + residual = total by construction. <AsOf asof={boj?.asof} src={boj?.src} />
          </p>
        </div>
        <div>
          <div className="mb-1 text-xs text-slate-300">MOF: net purchases of foreign long-term debt by investor type, 12m sum, JPY trn</div>
          {mofRows.length === 0 ? (
            <Unavailable what="MOF investor-type series" why="n/a" />
          ) : (
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={mofRows} margin={{ top: 6, right: 36, left: -14, bottom: 0 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="x" tick={tickStyle} interval={23} />
                  <YAxis tick={tickStyle} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number | string) => fmtSigned(Number(v), 2)} />
                  <Legend wrapperStyle={legendStyle} iconSize={8} />
                  <ReferenceLine y={0} stroke="#334155" />
                  <Line dataKey="banks" name="banks (banking accounts)" stroke={BLUE} dot={false} strokeWidth={1.5} connectNulls={false} isAnimationActive={false} />
                  <Line dataKey="life" name="life insurers" stroke={ORANGE} dot={false} strokeWidth={1.5} connectNulls={false} isAnimationActive={false} />
                  <Line dataKey="trust_accounts" name="trust accounts (pension money)" stroke={PENSION} dot={false} strokeWidth={2} connectNulls={false} isAnimationActive={false} label={lastLabel(lastIdx(mofRows), PENSION)} />
                  <Line dataKey="inv_trusts" name="investment trusts" stroke={AQUA} dot={false} strokeWidth={1.5} connectNulls={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
          <p className="mt-1 text-[10px] leading-snug text-slate-500">
            All foreign LT debt, not US-only; the US share is not broken out by investor type. <AsOf asof={mof?.asof} src={mof?.src} />
          </p>
        </div>
        <div>
          <div className="mb-1 text-xs text-slate-300">JGB yields, %</div>
          {jgbRows.length === 0 ? (
            <Unavailable what="JGB curve" why="n/a" />
          ) : (
            <div className="h-40">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={jgbRows} margin={{ top: 6, right: 36, left: -14, bottom: 0 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="x" tick={tickStyle} minTickGap={40} />
                  <YAxis tick={tickStyle} domain={["auto", "auto"]} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number | string) => `${fmt(Number(v), 3)}%`} />
                  <Legend wrapperStyle={legendStyle} iconSize={8} />
                  <Line dataKey="y10" name="10y" stroke={BLUE} dot={false} strokeWidth={1.5} connectNulls isAnimationActive={false} label={lastLabel(lastIdx(jgbRows), BLUE, 3)} />
                  <Line dataKey="y30" name="30y" stroke={ORANGE} dot={false} strokeWidth={1.5} connectNulls isAnimationActive={false} label={lastLabel(lastIdx(jgbRows), ORANGE, 3)} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
          <p className="mt-1 text-[10px] leading-snug text-slate-500">
            <AsOf asof={jgb?.asof ?? last(arr(jgb?.dates))} src={jgb?.src} />
          </p>
        </div>
        <div>
          <div className="mb-1 text-xs text-slate-300">MOF weekly: residents' net purchases of foreign long-term debt, JPY trn</div>
          {wkRows.length === 0 ? (
            <Unavailable what="MOF weekly" why="n/a" />
          ) : (
            <div className="h-40">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={wkRows} margin={{ top: 6, right: 8, left: -14, bottom: 0 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="x" tick={tickStyle} minTickGap={40} />
                  <YAxis tick={tickStyle} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number | string) => fmtSigned(Number(v), 3)} />
                  <ReferenceLine y={0} stroke="#334155" />
                  <Bar dataKey="net" name="weekly net" fill={BLUE} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
          <p className="mt-1 text-[10px] leading-snug text-slate-500">
            <AsOf asof={wk?.asof ?? last(arr(wk?.weeks))} src={wk?.src} />
          </p>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 6. Public funds & pensions
// ---------------------------------------------------------------------------

// Which MOF investor groups were net buyers over the same 12 months, from the
// payload's 12m sums — the tile never asserts "the only buyer" as frozen text.
const MOF_GROUP_LABEL: Record<string, string> = { banks: "banks", life: "life insurers", inv_trusts: "investment trusts", trust_accounts: "trust accounts" };
function mofNetBuyers(m: AiDebtPublicFunds["mof_by_type"]): string | null {
  if (!m) return null;
  const sums = Object.keys(MOF_GROUP_LABEL).map((k) => [k, m[`${k}_12m`]] as const).filter(([, v]) => isNum(v));
  if (!sums.length) return null;
  const buyers = sums.filter(([, v]) => (v as number) > 0).map(([k]) => MOF_GROUP_LABEL[k]);
  return buyers.length ? buyers.join(", ") : "none";
}

function PublicFundsPanel({ pf }: { pf: AiDebtPublicFunds }) {
  const g = pf.gpif;
  const issuers = arr(g?.ai_issuers).filter((x) => x && typeof x.issuer === "string");
  const maxJpy = Math.max(...issuers.map((x) => (isNum(x.jpy_bn) ? x.jpy_bn : 0)), 0.001);
  const buyers = mofNetBuyers(pf.mof_by_type);
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Tile
          label="MOF trust accounts, 12m (pension money)"
          value={isNum(pf.trust_accounts_12m_jpy_trn) ? `${fmtSigned(pf.trust_accounts_12m_jpy_trn, 2)} trn` : "n/a"}
          sub={
            <>
              JPY trn, 12m net purchases of ALL foreign LT debt (MOF monthb3; trust accounts = pension and other trust money).
              {buyers !== null ? ` 12m net buyers among banks / lifers / inv. trusts / trust accounts: ${buyers}.` : " See the Japan panel's read for who else is buying."}
            </>
          }
          asof={pf.trust_accounts_asof}
          src={pf.trust_accounts_src}
        />
        <Tile
          label="Z.1 US private pensions"
          value={fmtBn(pf.z1_pensions?.private?.level, 0)}
          sub={<>held; latest flow {fmtSigned(pf.z1_pensions?.private?.flow_saar, 0)} $bn annualised</>}
          asof={pf.z1_pensions?.private?.asof}
          src={pf.z1_pensions?.src}
        />
        <Tile
          label="Z.1 US state & local pensions"
          value={fmtBn(pf.z1_pensions?.state_local?.level, 0)}
          sub={<>held; latest flow {fmtSigned(pf.z1_pensions?.state_local?.flow_saar, 0)} $bn annualised</>}
          asof={pf.z1_pensions?.state_local?.asof}
          src={pf.z1_pensions?.src}
        />
        <Tile
          label="Foreign official, US corporates"
          value={fmtSigned(pf.tic_official_corp?.net_12m)}
          sub={<>$bn net 12m; holds {fmtBn(pf.tic_official_corp?.pos, 0)} = {fmtPct(pf.tic_official_corp?.share_of_foreign_held)} of foreign-held corporates (custody basis)</>}
          asof={pf.tic_official_corp?.asof}
          src={pf.tic_official_corp?.src}
        />
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div>
          <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
            <span className="text-xs text-slate-300">GPIF: AI-issuer bonds in the foreign-bond book (ISIN level)</span>
            {g && (
              <span className="font-mono text-[10px] text-slate-400">
                AI issuers {fmtPct(g.ai_share_pct, 3)} of JPY {fmt(g.foreign_bonds_jpy_trn, 2)} trn · US Treasuries {fmt(g.ust_jpy_trn, 2)} trn{isNum(g.ust_share_pct) ? ` (${fmtPct(g.ust_share_pct)})` : ""}
              </span>
            )}
          </div>
          {issuers.length === 0 ? (
            <Unavailable what="GPIF issuer list" why={g ? "no issuer rows" : "n/a"} />
          ) : (
            <table className="w-full text-[11px]">
              <thead>
                <tr className="text-[10px] uppercase tracking-wide text-slate-500">
                  <th className="py-1 pr-2 text-left font-normal">issuer</th>
                  <th className="px-1 py-1 text-right font-normal">JPY bn</th>
                  <th className="px-1 py-1 text-right font-normal">lines</th>
                  <th className="pl-2 py-1 text-left font-normal">relative</th>
                </tr>
              </thead>
              <tbody>
                {issuers.map((x) => (
                  <tr key={x.issuer} className="border-t border-panelborder/50 font-mono tabular-nums text-slate-300">
                    <td className="py-1 pr-2 font-sans">{x.issuer}</td>
                    <td className="px-1 py-1 text-right">{fmt(x.jpy_bn, 2)}</td>
                    <td className="px-1 py-1 text-right">{isNum(x.lines) ? x.lines : "n/a"}</td>
                    <td className="pl-2 py-1">
                      <span className="block h-1.5 rounded-full" style={{ width: `${isNum(x.jpy_bn) ? Math.max(2, (100 * x.jpy_bn) / maxJpy) : 0}%`, backgroundColor: PENSION }} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="mt-1 text-[10px] leading-snug text-slate-500">
            Passive, government-bond-benchmarked: a spot check, not the marginal buyer. One fund, one date. <AsOf asof={g?.asof} src={g?.src} />
          </p>
          <ImfPipTable imf={pf.imf_pip_japan} />
        </div>
        <div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <div className="mb-1 text-xs text-emerald-300/90">What these series can see</div>
              <ul className="list-disc space-y-1 pl-4 text-[11px] leading-snug text-slate-300">
                {arr(pf.can_see).map((t, i) => (
                  <li key={i}>{t}</li>
                ))}
                {arr(pf.can_see).length === 0 && <li className="text-slate-600">n/a</li>}
              </ul>
            </div>
            <div>
              <div className="mb-1 text-xs text-amber-300/90">What they cannot see</div>
              <ul className="list-disc space-y-1 pl-4 text-[11px] leading-snug text-slate-300">
                {arr(pf.cannot_see).map((t, i) => (
                  <li key={i}>{t}</li>
                ))}
                {arr(pf.cannot_see).length === 0 && <li className="text-slate-600">n/a</li>}
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// IMF PIP: Japanese holders of US long-term debt by holder sector, semi-annual,
// $bn, private holders only (reserve assets excluded). Optional source with an
// open type, so every field is checked at runtime. S12R is a subtotal
// (insurers & pensions + other financial) and is not repeated.
const IMF_SECTOR_ORDER = ["S122", "S12QU", "S12P", "S1V", "S13", "S1"];
const IMF_SHORT: Record<string, string> = {
  S1: "All sectors (private holders)",
  S122: "Banks",
  S12QU: "Insurers & pension funds",
  S12P: "Other financial (inv. trusts, trust accounts)",
  S1V: "Nonfinancial corps & households",
  S13: "General government",
};
function ImfPipTable({ imf }: { imf: Record<string, unknown> | null | undefined }) {
  const muted = (t: string) => <p className="mt-3 text-[10px] leading-snug text-slate-500">IMF PIP Japan × US holder sectors: {t}.</p>;
  if (!imf || typeof imf !== "object") return muted("not available in this payload (optional source)");
  const periods = arr(imf.periods as string[] | null).filter((x) => typeof x === "string");
  const raw = imf.sectors && typeof imf.sectors === "object" ? (imf.sectors as Record<string, unknown>) : {};
  const known = new Set(IMF_SECTOR_ORDER);
  const keys = [...IMF_SECTOR_ORDER.filter((k) => k in raw), ...Object.keys(raw).filter((k) => !known.has(k) && k !== "S12R").sort()];
  const sectors = keys
    .map((k) => {
      const s = raw[k] as { label?: unknown; values?: unknown } | null;
      if (!s || typeof s !== "object") return null;
      return { key: k, label: str(s.label) ?? k, values: arr(s.values as Array<number | null> | null).map((v) => (isNum(v) ? v : null)) };
    })
    .filter((s): s is { key: string; label: string; values: Array<number | null> } => s !== null);
  if (!periods.length || !sectors.length) return muted("present but empty");
  return (
    <div className="mt-3">
      <div className="mb-1 text-xs text-slate-300">IMF PIP: Japanese holders of US long-term debt by sector, {str(imf.unit) ?? "$bn"}</div>
      <table className="w-full text-[11px]">
        <thead>
          <tr className="text-[10px] uppercase tracking-wide text-slate-500">
            <th className="py-1 pr-2 text-left font-normal">holder sector</th>
            {periods.map((p) => (
              <th key={p} className="px-1 py-1 text-right font-normal">{p}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sectors.map((s) => (
            <tr
              key={s.key}
              className={`border-t border-panelborder/50 font-mono tabular-nums ${s.key === "S1" ? "border-panelborder text-slate-100" : s.key === "S12QU" ? "text-amber-200" : "text-slate-300"}`}
              title={s.label}
            >
              <td className={`py-1 pr-2 font-sans${s.key === "S1" ? " font-semibold" : ""}`}>{IMF_SHORT[s.key] ?? s.label}</td>
              {periods.map((p, i) => (
                <td key={p} className="px-1 py-1 text-right">{fmt(s.values[i], 0)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1 text-[10px] leading-snug text-slate-500">
        Semi-annual, private holders only (reserve assets excluded); holdings, not purchases; no Treasuries-vs-corporates split. Hover a row for the full sector name. <AsOf asof={imf.asof} src={imf.src} />
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 7. Crowding
// ---------------------------------------------------------------------------

function tenorGroup(t: string): string | null {
  const m = /^(\d+)y/.exec(t) ?? /^(\d+)-Year/.exec(t);
  if (!m) return null;
  const n = Number(m[1]);
  if (n >= 29) return "30y";
  if (n >= 19) return "20y";
  if (n >= 9 && n <= 10) return "10y";
  return null;
}

function CrowdingPanel({ c, iss }: { c: AiDebtCrowding; iss: AiDebtIssuance | null }) {
  const kw = c.term_premium?.kw10;
  const acm = c.term_premium?.acm10;
  const tpRows = useMemo(() => {
    const k = points(kw?.series);
    const a = points(acm?.series);
    const map = new Map<string, Record<string, string | number | null>>();
    for (const p of k) map.set(p.date, { x: p.date, kw: p.value, acm: null });
    for (const p of a) {
      const r = map.get(p.date);
      if (r) r.acm = p.value;
      else map.set(p.date, { x: p.date, kw: null, acm: p.value });
    }
    return [...map.values()].filter((r) => String(r.x) >= "2023-10-01").sort((p, q) => (String(p.x) < String(q.x) ? -1 : 1));
  }, [kw, acm]);
  const dgs30 = c.yields?.dgs30;
  const y30Rows = useMemo(() => points(dgs30?.series).map((p) => ({ x: p.date, y: p.value })), [dgs30]);
  const auctions = arr(c.auctions).filter((a) => a && typeof a.date === "string");
  const aucRows = useMemo(() => {
    const map = new Map<string, Record<string, string | number | null>>();
    for (const a of auctions) {
      const g = tenorGroup(String(a.tenor));
      if (!g || !isNum(a.indirect_pct)) continue;
      const r = map.get(a.date) ?? { x: a.date };
      r[g] = a.indirect_pct;
      map.set(a.date, r);
    }
    return [...map.values()].sort((p, q) => (String(p.x) < String(q.x) ? -1 : 1));
  }, [auctions]);
  const latestByTenor = useMemo(() => {
    const out = new Map<string, (typeof auctions)[number]>();
    for (const a of [...auctions].sort((p, q) => (p.date < q.date ? -1 : 1))) {
      const g = tenorGroup(String(a.tenor)) ?? String(a.tenor);
      out.set(g, a);
    }
    return out;
  }, [auctions]);
  const tally = iss?.totals_by_year ?? {};
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div>
          <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
            <span className="text-xs text-slate-300">10y term premium, pp</span>
            <span className="font-mono text-[10px] text-slate-400">
              KW {fmt(kw?.latest, 3)} ({str(kw?.asof) ?? "n/a"}) · ACM {fmt(acm?.latest, 3)} ({str(acm?.asof) ?? "n/a"})
            </span>
          </div>
          {tpRows.length === 0 ? (
            <Unavailable what="Term-premium series" why="n/a" />
          ) : (
            <div className="h-44">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={tpRows} margin={{ top: 6, right: 36, left: -14, bottom: 0 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="x" tick={tickStyle} minTickGap={50} />
                  <YAxis tick={tickStyle} domain={["auto", "auto"]} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number | string) => fmt(Number(v), 3)} />
                  <Legend wrapperStyle={legendStyle} iconSize={8} />
                  <ReferenceLine y={0} stroke="#334155" />
                  <Line dataKey="kw" name="Kim-Wright TP10 (FRED)" stroke={BLUE} dot={false} strokeWidth={1.5} connectNulls isAnimationActive={false} />
                  <Line dataKey="acm" name="ACM TP10 (NY Fed, monthly)" stroke={ORANGE} dot={false} strokeWidth={1.5} connectNulls isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
          <p className="mt-1 text-[10px] leading-snug text-slate-500">
            <SrcLink href={kw?.src} label="KW" /> · <SrcLink href={acm?.src} label="ACM" />
          </p>
        </div>
        <div>
          <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
            <span className="text-xs text-slate-300">30y Treasury yield, %</span>
            <span className="font-mono text-[10px] text-slate-400">
              {fmt(dgs30?.latest, 2)}% ({str(dgs30?.asof) ?? "n/a"}) · 10y {fmt(c.yields?.dgs10?.latest, 2)}% · 10y breakeven {fmt(c.yields?.t10yie?.latest, 2)}%
            </span>
          </div>
          {y30Rows.length === 0 ? (
            <Unavailable what="DGS30 series" why="n/a" />
          ) : (
            <div className="h-44">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={y30Rows} margin={{ top: 6, right: 36, left: -14, bottom: 0 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="x" tick={tickStyle} minTickGap={50} />
                  <YAxis tick={tickStyle} domain={["auto", "auto"]} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number | string) => `${fmt(Number(v), 2)}%`} />
                  <Line dataKey="y" name="DGS30" stroke={BLUE} dot={false} strokeWidth={1.5} connectNulls isAnimationActive={false} label={lastLabel(y30Rows.length - 1, BLUE)} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
          <p className="mt-1 text-[10px] leading-snug text-slate-500">
            {str(dgs30?.note) ? `${dgs30?.note}. ` : ""}Fed Treasury holdings {isNum(c.fed_treast?.latest) ? `$${fmt(c.fed_treast?.latest, 0)}bn` : "n/a"}
            {str(c.fed_treast?.asof) ? ` (${c.fed_treast?.asof})` : ""} — {str(c.fed_treast?.note) ?? "a demand-side factor the crowding pieces rarely net out"}. <SrcLink href={dgs30?.src} label="DGS30" /> · <SrcLink href={c.fed_treast?.src} label="TREAST" />
          </p>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div>
          <div className="mb-1 text-xs text-slate-300">Net marketable Treasury supply vs the AI tally, $bn</div>
          {Object.keys(c.ust ?? {}).length === 0 ? (
            <Unavailable what="MSPD supply" why="n/a" />
          ) : (
            <table className="w-full text-[11px]">
              <thead>
                <tr className="text-[10px] uppercase tracking-wide text-slate-500">
                  <th className="py-1 pr-2 text-left font-normal">window</th>
                  <th className="px-1 py-1 text-right font-normal">net marketable</th>
                  <th className="px-1 py-1 text-right font-normal">coupons</th>
                  <th className="px-1 py-1 text-right font-normal">bills</th>
                  <th className="pl-1 py-1 text-right font-normal">AI tally</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(c.ust ?? {}).map(([w, v]) => {
                  const yr = /(\d{4})/.exec(w)?.[1];
                  const matched = iss?.vs_treasury?.[w]?.ai_bn;
                  const t = isNum(matched) ? matched : yr ? tally[yr] : null;
                  return (
                    <tr key={w} className="border-t border-panelborder/50 font-mono tabular-nums text-slate-300" title={str(v?.basis) ?? undefined}>
                      <td className="py-1 pr-2 font-sans">{w}</td>
                      <td className="px-1 py-1 text-right">{fmtSigned(v?.net_marketable, 0)}</td>
                      <td className="px-1 py-1 text-right">{fmtSigned(v?.coupons, 0)}</td>
                      <td className="px-1 py-1 text-right">{fmtSigned(v?.bills, 0)}</td>
                      <td className="pl-1 py-1 text-right">{isNum(t) ? fmt(t) : "n/a"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          <p className="mt-1 text-[10px] leading-snug text-slate-500">
            Change in marketable outstanding (MSPD table 1), gross of Fed holdings; hover a row for its window. AI tally = gross issuance priced inside the same window (the issuance block's vs-Treasury table; the calendar-year tally only where no matched window is shipped). Gross tally over net supply: read the ratio with that in mind.
          </p>
        </div>
        <div>
          <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
            <span className="text-xs text-slate-300">Auction indirect share by tenor, % of competitive</span>
            <span className="font-mono text-[10px] text-slate-400">
              {["10y", "20y", "30y"].map((g) => {
                const a = latestByTenor.get(g);
                return a ? `${g} ${fmt(a.indirect_pct, 1)}% (${a.date}, ${fmt(a.high_yield, 3)}%, btc ${fmt(a.btc, 2)}) ` : "";
              })}
            </span>
          </div>
          {aucRows.length === 0 ? (
            <Unavailable what="Auction series" why="n/a" />
          ) : (
            <div className="h-44">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={aucRows} margin={{ top: 6, right: 8, left: -14, bottom: 0 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="x" tick={tickStyle} minTickGap={50} />
                  <YAxis tick={tickStyle} domain={["auto", "auto"]} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number | string) => `${fmt(Number(v), 1)}%`} />
                  <Legend wrapperStyle={legendStyle} iconSize={8} />
                  <Line dataKey="10y" name="10y" stroke={BLUE} dot={{ r: 2 }} strokeWidth={1.2} connectNulls isAnimationActive={false} />
                  <Line dataKey="20y" name="20y" stroke={ORANGE} dot={{ r: 2 }} strokeWidth={1.2} connectNulls isAnimationActive={false} />
                  <Line dataKey="30y" name="30y" stroke={AQUA} dot={{ r: 2 }} strokeWidth={1.2} connectNulls isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
          <p className="mt-1 text-[10px] leading-snug text-slate-500">
            Indirect bidders are the usual foreign-demand proxy; no tail (TreasuryDirect carries no when-issued field). New issues and reopenings pooled by tenor. <SrcLink href={c.auctions_src} />
          </p>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 8. Breaking
// ---------------------------------------------------------------------------

// Side readings the backend ships next to a gauge (GZ spread and the model
// recession probability with the EBP; the credit sub-index with the OFR FSI).
// items: [payload key, label, digits, unit suffix, scale].
function sideReadings(r: AiDebtReading | null | undefined, items: Array<[string, string, number, string, number?]>): string {
  const rec = (r ?? {}) as unknown as Record<string, unknown>;
  return items
    .map(([key, label, digits, unit, scale]) => (isNum(rec[key]) ? `${label} ${fmt((rec[key] as number) * (scale ?? 1), digits)}${unit}` : null))
    .filter((x): x is string => x !== null)
    .join(" · ");
}

// `note` overrides the payload's note (used where the payload note only says
// what sits "alongside"; the side readings are rendered instead).
function ReadingCell({ label, r, digits = 2, unit, note }: { label: string; r: AiDebtReading | null | undefined; digits?: number; unit?: string; note?: string | null }) {
  const noteText = note === undefined ? str(r?.note) : str(note);
  return (
    <div className="rounded border border-panelborder/60 px-2.5 py-1.5">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className="font-mono text-sm tabular-nums text-slate-100">
        {fmt(r?.latest, digits)}
        <span className="ml-1 text-[10px] text-slate-500">{unit ?? str(r?.unit) ?? ""}</span>
      </div>
      <div className="font-mono text-[10px] text-slate-500">
        {str(r?.asof) ?? "n/a"}
        {isNum(r?.hi_2026) ? ` · 2026 hi ${fmt(r?.hi_2026, digits)}` : ""}
        {noteText ? ` · ${noteText}` : ""} · <SrcLink href={r?.src} />
      </div>
    </div>
  );
}

function BreakingPanel({ b }: { b: AiDebtBreaking }) {
  const spreads = useMemo(() => upperKeys(b.spreads), [b.spreads]);
  const spreadRows = useMemo(() => {
    const map = new Map<string, Record<string, string | number | null>>();
    for (const [k] of SPREAD_SERIES) {
      for (const p of points(spreads[k]?.series)) {
        const r = map.get(p.date) ?? { x: p.date };
        r[k] = p.value !== null && p.value > 0 ? p.value : null;
        map.set(p.date, r);
      }
    }
    return [...map.values()].sort((p, q) => (String(p.x) < String(q.x) ? -1 : 1));
  }, [spreads]);
  const gapRows = useMemo(() => points(b.ccc_b_gap?.series).map((p) => ({ x: p.date, y: p.value })), [b.ccc_b_gap]);
  const sai = arr(b.spread_at_issue_30y).filter((s) => s && typeof s.issuer === "string");
  const byIssuer = useMemo(() => {
    const m = new Map<string, typeof sai>();
    for (const s of [...sai].sort((p, q) => (p.date < q.date ? -1 : 1))) {
      const k = s.issuer.split(" ")[0];
      m.set(k, [...(m.get(k) ?? []), s]);
    }
    return m;
  }, [sai]);
  const events = [...arr(b.events).filter((e) => e && typeof e.text === "string")].sort((p, q) => (p.date < q.date ? 1 : p.date > q.date ? -1 : 0));
  const bdc = arr(b.bdc).filter((x) => x && typeof x.ticker === "string");

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <ReadingCell label="IG OAS" r={spreads["IG"]} unit="%" />
        <ReadingCell label="HY OAS" r={spreads["HY"]} unit="%" />
        <ReadingCell label="IG eff. yield" r={b.yields?.ig} unit="%" />
        <ReadingCell label="HY eff. yield" r={b.yields?.hy} unit="%" />
        <ReadingCell label="Baa − 10y" r={b.baa10y} unit="pp" />
        <ReadingCell
          label="Excess bond premium"
          r={b.ebp}
          unit="pp"
          note={["monthly", sideReadings(b.ebp, [["gz_spread_latest", "GZ spread", 2, " pp"], ["est_prob_latest", "model recession prob", 0, "%", 100]])].filter(Boolean).join(" · ")}
        />
        <ReadingCell label="OFR FSI" r={b.ofr_fsi} digits={3} unit="" note={["0 = average stress", sideReadings(b.ofr_fsi, [["credit_latest", "credit sub-index", 3, ""]])].filter(Boolean).join(" · ")} />
        <ReadingCell label="MOVE" r={b.move} digits={2} unit="" />
        <ReadingCell label="CCC − B gap" r={b.ccc_b_gap} unit="pp" />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <div className="mb-1 text-xs text-slate-300">ICE BofA OAS by rating, % (log scale; FRED serves three years; legend carries the latest print)</div>
          {spreadRows.length === 0 ? (
            <Unavailable what="Spread series" why="n/a" />
          ) : (
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={spreadRows} margin={{ top: 6, right: 40, left: -8, bottom: 0 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="x" tick={tickStyle} minTickGap={50} />
                  <YAxis tick={tickStyle} scale="log" domain={["auto", "auto"]} allowDataOverflow tickFormatter={(v: number) => fmt(v, v < 1 ? 2 : 1)} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number | string, name: string) => [`${fmt(Number(v), 2)}%`, String(name).split(" ")[0]]} />
                  <Legend wrapperStyle={legendStyle} iconSize={8} />
                  {SPREAD_SERIES.filter(([k]) => spreads[k]).map(([k, color]) => (
                    <Line key={k} dataKey={k} name={`${k} ${fmt(spreads[k]?.latest, 2)}`} stroke={color} dot={false} strokeWidth={1.4} connectNulls isAnimationActive={false} />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
          <table className="mt-2 w-full text-[11px]">
            <thead>
              <tr className="text-[10px] uppercase tracking-wide text-slate-500">
                <th className="py-1 pr-2 text-left font-normal">bucket</th>
                <th className="px-1 py-1 text-right font-normal">latest</th>
                <th className="px-1 py-1 text-right font-normal">end-2025</th>
                <th className="px-1 py-1 text-right font-normal">2026 lo</th>
                <th className="px-1 py-1 text-right font-normal">2026 hi</th>
                <th className="px-1 py-1 text-right font-normal">as of</th>
                <th className="pl-1 py-1 text-left font-normal">src</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(spreads).map(([k, r]) => (
                <tr key={k} className="border-t border-panelborder/50 font-mono tabular-nums text-slate-300">
                  <td className="py-1 pr-2 font-sans">
                    <span className="mr-1 inline-block h-2 w-2 rounded-sm align-middle" style={{ backgroundColor: SPREAD_SERIES.find(([s]) => s === k)?.[1] ?? SLATE }} />
                    {k}
                  </td>
                  <td className={`px-1 py-1 text-right ${isNum(r?.latest) && isNum(r?.hi_2026) && r.latest >= r.hi_2026 ? "text-amber-200" : ""}`}>
                    {fmt(r?.latest, 2)}
                    {isNum(r?.latest) && isNum(r?.hi_2026) && r.latest >= r.hi_2026 ? " ▲hi" : ""}
                  </td>
                  <td className="px-1 py-1 text-right">{fmt(r?.end_2025, 2)}</td>
                  <td className="px-1 py-1 text-right">{fmt(r?.lo_2026, 2)}</td>
                  <td className="px-1 py-1 text-right">{fmt(r?.hi_2026, 2)}</td>
                  <td className="px-1 py-1 text-right">{str(r?.asof) ?? "n/a"}</td>
                  <td className="pl-1 py-1 font-sans">
                    <SrcLink href={r?.src} />
                  </td>
                </tr>
              ))}
              {Object.keys(spreads).length === 0 && (
                <tr>
                  <td colSpan={7} className="py-1 text-slate-600">no spread buckets in payload</td>
                </tr>
              )}
            </tbody>
          </table>
          <p className="mt-1 text-[10px] leading-snug text-slate-500">▲hi = at or above the 2026 high (watch, not a signal).</p>
        </div>
        <div>
          <div className="mb-1 text-xs text-slate-300">CCC − B OAS gap, pp (same dates)</div>
          {gapRows.length === 0 ? (
            <Unavailable what="CCC − B gap series" why="n/a" />
          ) : (
            <div className="h-40">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={gapRows} margin={{ top: 6, right: 36, left: -14, bottom: 0 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="x" tick={tickStyle} minTickGap={50} />
                  <YAxis tick={tickStyle} domain={["auto", "auto"]} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number | string) => `${fmt(Number(v), 2)} pp`} />
                  {isNum(b.ccc_b_gap?.end_2025) && <ReferenceLine y={b.ccc_b_gap?.end_2025 ?? 0} stroke="#475569" strokeDasharray="4 3" label={{ value: "end-2025", position: "insideBottomRight", fill: "#64748b", fontSize: 9 }} />}
                  <Line dataKey="y" name="CCC − B" stroke="#e66767" dot={false} strokeWidth={1.6} connectNulls isAnimationActive={false} label={lastLabel(gapRows.length - 1, "#e66767")} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
          <p className="mt-1 text-[10px] leading-snug text-slate-500">
            The one index line that moved with neocloud stress. <AsOf asof={b.ccc_b_gap?.asof} src={b.ccc_b_gap?.src} />
          </p>

          <div className="mt-4 mb-1 text-xs text-slate-300">Spread at issue, longest tranche (bp over UST), deal by deal</div>
          {byIssuer.size === 0 ? (
            <Unavailable what="Spread-at-issue drift" why="n/a" />
          ) : (
            <table className="w-full text-[11px]">
              <tbody>
                {[...byIssuer.entries()].map(([k, xs]) => (
                  <tr key={k} className="border-t border-panelborder/50 align-top">
                    <td className="py-1 pr-2 text-slate-300">{k}</td>
                    <td className="py-1 font-mono tabular-nums text-slate-300">
                      {xs.map((s, i) => (
                        <span key={`${s.date}-${i}`} title={`${s.date}${s.maturity ? ` · due ${s.maturity}` : ""}`}>
                          {i > 0 && <span className="text-slate-600"> → </span>}
                          {isNum(s.bp) ? s.bp : "n/a"}
                          {isHttp(s.src) && (
                            <a href={s.src} target="_blank" rel="noreferrer" className="ml-0.5 text-[9px] text-sky-400/70 hover:text-sky-300">
                              ↗
                            </a>
                          )}
                        </span>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="mt-1 text-[10px] leading-snug text-slate-500">Chronological left to right; hover for the pricing date and maturity. The cleanest free gauge of primary-market concession.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <div className="lg:col-span-2">
          <div className="mb-1 text-xs text-slate-300">BDC price vs last reported NAV (private-credit lender stress)</div>
          {bdc.length === 0 ? (
            <Unavailable what="BDC table" why="n/a" />
          ) : (
            <table className="w-full text-[11px]">
              <thead>
                <tr className="text-[10px] uppercase tracking-wide text-slate-500">
                  <th className="py-1 pr-2 text-left font-normal">ticker</th>
                  <th className="px-1 py-1 text-right font-normal">price</th>
                  <th className="px-1 py-1 text-right font-normal">NAV</th>
                  <th className="px-1 py-1 text-right font-normal">P / NAV</th>
                  <th className="pl-1 py-1 text-left font-normal">NAV src</th>
                </tr>
              </thead>
              <tbody>
                {bdc.map((x) => (
                  <tr key={x.ticker} className="border-t border-panelborder/50 font-mono tabular-nums text-slate-300">
                    <td className="py-1 pr-2">{x.ticker}</td>
                    <td className="px-1 py-1 text-right">
                      {fmt(x.price, 2)}
                      <div className="text-[9px] text-slate-500">{str(x.asof) ?? "n/a"}</div>
                    </td>
                    <td className="px-1 py-1 text-right" title={str(x.nav_note) ?? undefined}>
                      {fmt(x.nav, 2)}
                      <div className="text-[9px] text-slate-500">{str(x.nav_asof) ?? (str(x.nav_note) ? "NAV not filing-sourced" : "n/a")}</div>
                    </td>
                    <td className={`px-1 py-1 text-right ${isNum(x.p_nav) && x.p_nav < 0.8 ? "text-amber-200" : ""}`}>
                      {isNum(x.p_nav) ? `${fmt(x.p_nav, 2)}×${x.p_nav < 0.8 ? " (watch)" : ""}` : "n/a"}
                    </td>
                    <td className="pl-1 py-1 font-sans">
                      <SrcLink href={x.nav_src} label="filing" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="mt-1 text-[10px] leading-snug text-slate-500">
            Prices via Yahoo chart API; NAV from the latest 8-K / 10-Q, so P/NAV mixes a daily price with a quarter-old mark. n/a where no filing-sourced NAV is on file (hover the NAV cell for the reason). "(watch)" below 0.80×.
          </p>
        </div>
        <div className="lg:col-span-3">
          <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
            <span className="text-xs text-slate-300">Event log — dated prints, newest first</span>
            <span className="text-[10px] text-slate-500">
              <ProvBadge p="primary" /> filing / official · <ProvBadge p="press" /> fetched article · <ProvBadge p="aggregator" /> second-hand
            </span>
          </div>
          {events.length === 0 ? (
            <Unavailable what="Event log" why="n/a" />
          ) : (
            <ul className="scroll-thin flex max-h-80 flex-col gap-1.5 overflow-auto pr-1">
              {events.map((e, i) => (
                <li key={`${e.date}-${i}`} className="grid grid-cols-[auto_1fr] gap-x-3 text-[11px] leading-snug text-slate-300">
                  <span className="flex flex-col items-start gap-1">
                    <span className="font-mono text-slate-400">{str(e.date) ?? "n/a"}</span>
                    <ProvBadge p={e.provenance} />
                  </span>
                  <span>
                    {e.text}
                    <span className="ml-2 font-mono text-[9px] text-slate-600">
                      retrieved {str(e.retrieved) ?? "n/a"}
                      {str(e.note) ? ` · ${e.note}` : ""} · <SrcLink href={e.src} />
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-1 text-[10px] leading-snug text-slate-500">
            CDS and single-name prices are press prints with their retrieval time, not a feed; articles get revised intraday, so the quoted text is what was read then.
          </p>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 9. Honesty box (payload text)
// ---------------------------------------------------------------------------

function HonestyBox({ d }: { d: AiDebt }) {
  const lines = arr(d.honesty).filter((x) => typeof x === "string" && x.length > 0);
  const nSrc = Object.keys(d.sources ?? {}).length;
  const statuses = Object.entries(d.status ?? {});
  return (
    <Panel title="Honesty box" subtitle="Measurement basis and what is NOT in these numbers (text from the payload)">
      {lines.length === 0 ? (
        <Unavailable what="Honesty text" why="not in payload" />
      ) : (
        <ul className="list-disc space-y-1 pl-4 text-xs leading-relaxed text-slate-300">
          {lines.map((l, i) => (
            <li key={i}>{l}</li>
          ))}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2 text-[10px] text-slate-500">
        <span>{nSrc} source URLs in payload</span>
        {statuses.map(([k, v]) => (
          <span key={k} className="inline-flex items-center gap-1">
            <span className="text-slate-600">{k}</span>
            <BlockPill status={v} />
          </span>
        ))}
        {statuses.length === 0 && <span className="text-slate-600">· block status: n/a</span>}
      </div>
    </Panel>
  );
}
