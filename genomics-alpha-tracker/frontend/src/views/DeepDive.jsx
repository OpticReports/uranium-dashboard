import React, { useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine, BarChart, Bar, CartesianGrid,
} from "recharts";
import { api } from "../lib/api";
import { fmtNum, fmtMoney, fmtPct, scoreColor, naIfNull } from "../lib/format";
import RunwayGauge from "../components/RunwayGauge";
import Flags from "../components/Flags";
import InfoTip from "../components/InfoTip";

// Per-name deep dive: price + catalyst markers, revision/hype timelines,
// runway gauge, auditable score breakdown, flags, science/analyst feed.
export default function DeepDive({ symbol, onBack }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [days, setDays] = useState(365); // shared timeframe for price + hype charts
  const [loading, setLoading] = useState(false);

  useEffect(() => setData(null), [symbol]); // clear when switching names

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.deepDive(symbol, days)
      .then((d) => { if (alive) { setData(d); setErr(null); } })
      .catch((e) => { if (alive) setErr(e.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [symbol, days]);

  if (err) return <div className="text-rose-400">⚠ {err}</div>;
  if (!data) return <div className="text-gray-400">Loading {symbol}…</div>;

  const { security, prices, catalysts, revisions, mentions, publications, fundamentals, score, flags } = data;

  const priceData = prices.map((p) => ({ date: p.date, close: p.close }));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <button onClick={onBack} className="text-sky-400 text-sm hover:underline">
            ← back
          </button>
          <h2 className="text-2xl font-bold">
            {security.symbol} <span className="text-gray-400 text-lg font-normal">{security.name}</span>
          </h2>
          <div className="flex gap-2 mt-1">
            {(security.subsector || []).map((t) => (
              <span key={t} className="text-xs bg-sky-700/30 border border-sky-700 rounded-full px-2 py-0.5">
                {t}
              </span>
            ))}
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs text-gray-400">Alpha Signal<InfoTip term="composite" /></div>
          <div className="text-4xl font-bold" style={{ color: scoreColor(score?.composite) }}>
            {fmtNum(score?.composite, 0)}
          </div>
        </div>
      </div>

      {/* Shared timeframe control for the price + hype charts */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-400">
          Timeframe {loading && <span className="text-sky-400">· refreshing…</span>}
        </span>
        <TimeframeBar days={days} onChange={setDays} />
      </div>

      {/* Price + catalyst markers */}
      <Panel title="Price & catalyst markers">
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={priceData} margin={{ left: -10, right: 10, top: 10 }}>
            <CartesianGrid stroke="#1f2937" />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94a3b8" }} minTickGap={40} />
            <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} domain={["auto", "auto"]} />
            <Tooltip contentStyle={{ background: "#121826", border: "1px solid #1f2937" }} />
            <Line type="monotone" dataKey="close" stroke="#38bdf8" dot={false} strokeWidth={2} />
            {catalysts
              .filter((c) => priceData.some((p) => p.date <= c.date))
              .map((c) => (
                <ReferenceLine
                  key={c.id}
                  x={nearestDate(priceData, c.date)}
                  stroke="#f59e0b"
                  strokeDasharray="3 3"
                  label={{ value: c.event_type, fontSize: 9, fill: "#f59e0b", position: "top" }}
                />
              ))}
          </LineChart>
        </ResponsiveContainer>
      </Panel>

      <div className="grid lg:grid-cols-2 gap-4">
        {/* Hype timeline */}
        <HypeTimeline mentions={mentions} days={days} onChange={setDays} />

        {/* Runway + positioning */}
        <Panel title="Runway & positioning">
          <RunwayGauge quarters={fundamentals?.runway_quarters} />
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm mt-3">
            <Metric k="Market cap" v={fmtMoney(fundamentals?.market_cap)} />
            <Metric k="Cash" v={fmtMoney(fundamentals?.cash)} />
            <Metric k="Qtly burn" v={fmtMoney(fundamentals?.quarterly_burn)} />
            <Metric k="R&D" v={fmtMoney(fundamentals?.rd_spend)} />
            <Metric k="Short interest" v={fmtPct(fundamentals?.short_interest_pct)} />
            <Metric k="IV / skew" v={`${fmtNum(fundamentals?.iv, 2)} / ${fmtNum(fundamentals?.iv_skew, 2)}`} />
          </dl>
        </Panel>
      </div>

      {/* Auditable score breakdown */}
      <Panel title="Alpha Signal breakdown (auditable)">
        <ScoreBreakdown score={score} />
      </Panel>

      <div className="grid lg:grid-cols-2 gap-4">
        <Panel title="Active flags">
          <Flags flags={flags} />
        </Panel>
        <Panel title="Estimate revisions">
          {revisions.length ? (
            <div className="space-y-1 text-sm max-h-48 overflow-y-auto">
              {revisions.slice().reverse().map((r, i) => (
                <div key={i} className="flex justify-between border-b border-edge/40 py-1">
                  <span>
                    {r.direction > 0 ? "▲" : r.direction < 0 ? "▼" : "•"} {r.firm || "—"} ({r.metric})
                  </span>
                  <span className="text-gray-400">{r.date}</span>
                </div>
              ))}
            </div>
          ) : (
            <Empty>No analyst revisions recorded.</Empty>
          )}
        </Panel>
      </div>

      <Panel title="Science & news feed">
        {publications.length ? (
          <ul className="space-y-1 text-sm max-h-56 overflow-y-auto">
            {publications.map((p, i) => (
              <li key={i}>
                <span className="text-xs text-gray-500 mr-2">{p.date}</span>
                <span className="text-[10px] uppercase bg-edge rounded px-1 mr-2">{p.kind}</span>
                {p.url ? (
                  <a href={p.url} target="_blank" rel="noreferrer" className="hover:underline">
                    {p.title}
                  </a>
                ) : (
                  p.title
                )}
              </li>
            ))}
          </ul>
        ) : (
          <Empty>No publications/preprints found.</Empty>
        )}
      </Panel>
    </div>
  );
}

function ScoreBreakdown({ score }) {
  if (!score) return <Empty>No score yet — run a recompute.</Empty>;
  const comps = score.formula?.components || {};
  const rows = Object.entries(comps);
  return (
    <div>
      <table className="w-full text-sm">
        <thead className="text-gray-400">
          <tr>
            <th className="text-left py-1">Component</th>
            <th className="text-right whitespace-nowrap">Raw<InfoTip term="raw" /></th>
            <th className="text-right whitespace-nowrap">Normalized<InfoTip term="normalized" /></th>
            <th className="text-right whitespace-nowrap">Weight<InfoTip term="weight" /></th>
            <th className="text-right whitespace-nowrap">Weighted<InfoTip term="weighted" /></th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k} className="border-t border-edge/40">
              <td className="py-1">{k.replace(/_/g, " ")}<InfoTip term={k} /></td>
              <td className="text-right text-gray-400">{rawValue(k, v)}</td>
              <td className="text-right" style={{ color: scoreColor(v.normalized) }}>
                {fmtNum(v.normalized, 1)}
              </td>
              <td className="text-right text-gray-400">{naIfNull(v.weight, (x) => x)}</td>
              <td className="text-right">{fmtNum(v.weighted, 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {score.missing?.length > 0 && (
        <p className="text-xs text-amber-400 mt-2">
          Missing (excluded from weighting, not zero-filled): {score.missing.join(", ")}
        </p>
      )}
    </div>
  );
}

function rawValue(key, v) {
  if (key === "hype_divergence")
    return `div ${fmtNum(v.raw_divergence, 2)}`;
  if (key === "positioning") return `SI ${fmtPct(v.short_interest_pct)}`;
  if (key === "runway_penalty") return `${fmtNum(v.runway_quarters, 1)}q`;
  return fmtNum(v.raw, 2);
}

// Timeframe selector shared by the price + hype charts. Drives a refetch of the
// deep-dive payload with the chosen window (backend caps at 10y).
const RANGES = [
  { label: "1M", days: 30 },
  { label: "3M", days: 90 },
  { label: "6M", days: 180 },
  { label: "1Y", days: 365 },
  { label: "2Y", days: 730 },
  { label: "All", days: 3650 },
];

function TimeframeBar({ days, onChange }) {
  return (
    <div className="flex gap-1">
      {RANGES.map((r) => (
        <button
          key={r.label}
          onClick={() => onChange(r.days)}
          className={`text-xs px-2 py-0.5 rounded border ${
            days === r.days
              ? "border-sky-500 text-sky-300 bg-sky-500/10"
              : "border-edge text-gray-400 hover:text-gray-200"
          }`}
        >
          {r.label}
        </button>
      ))}
    </div>
  );
}

// Friendly label + color per source platform (stacked-bar segments + legend).
const PLATFORM_META = {
  reddit_apewisdom: { label: "Reddit", color: "#f59e0b" },
  reddit: { label: "Reddit (API)", color: "#fb923c" },
  x: { label: "X / Twitter", color: "#38bdf8" },
  twitter_fmp: { label: "Twitter (FMP)", color: "#0ea5e9" },
  stocktwits: { label: "StockTwits", color: "#a78bfa" },
  stocktwits_fmp: { label: "StockTwits (FMP)", color: "#8b5cf6" },
};
const platformMeta = (p) => PLATFORM_META[p] || { label: p, color: "#64748b" };

// Hype chart. Bars are STACKED BY SOURCE so you can see where chatter comes from.
// The window comes from the shared timeframe; bars bucket daily → weekly → monthly
// as the span grows. Mention history is sparse early on — it fills in over time.
function HypeTimeline({ mentions, days, onChange }) {
  const span = mentions.length
    ? (new Date(mentions[mentions.length - 1].date) - new Date(mentions[0].date)) / 86400000
    : 0;
  const bucket = span <= 45 ? "day" : span <= 200 ? "week" : "month";
  const { rows, platforms } = bucketMentions(mentions, bucket);
  const labelFor = { day: "daily", week: "weekly", month: "monthly" }[bucket];

  return (
    <div className="bg-panel border border-edge rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold">
          Hype timeline <span className="text-xs font-normal text-gray-400">({labelFor} mentions by source)</span>
        </h3>
        {onChange && <TimeframeBar days={days} onChange={onChange} />}
      </div>
      {rows.length ? (
        <>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={rows} margin={{ left: -10, right: 10 }}>
              <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#94a3b8" }} minTickGap={30} />
              <YAxis tick={{ fontSize: 9, fill: "#94a3b8" }} allowDecimals={false} />
              <Tooltip contentStyle={{ background: "#121826", border: "1px solid #1f2937" }} />
              {platforms.map((p) => (
                <Bar key={p} dataKey={p} stackId="m" name={platformMeta(p).label}
                     fill={platformMeta(p).color} />
              ))}
            </BarChart>
          </ResponsiveContainer>
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2 text-[10px] text-gray-400">
            {platforms.map((p) => (
              <span key={p} className="inline-flex items-center gap-1">
                <span className="w-2 h-2 rounded-sm inline-block"
                      style={{ background: platformMeta(p).color }} />
                {platformMeta(p).label}
              </span>
            ))}
          </div>
        </>
      ) : (
        <Empty>No social data in this window (mention history builds over time).</Empty>
      )}
    </div>
  );
}

// Pivot mentions into stacked rows keyed by date, one numeric field per platform.
function bucketMentions(mentions, bucket) {
  const key = (d) => {
    if (bucket === "day") return d;
    if (bucket === "month") return d.slice(0, 7); // YYYY-MM
    const dt = new Date(d + "T00:00:00"); // week → Monday's date
    const dow = (dt.getDay() + 6) % 7;
    dt.setDate(dt.getDate() - dow);
    return dt.toISOString().slice(0, 10);
  };
  const acc = {};
  const platforms = new Set();
  for (const m of mentions) {
    const k = key(m.date);
    const p = m.platform || "other";
    platforms.add(p);
    acc[k] = acc[k] || { date: k };
    acc[k][p] = (acc[k][p] || 0) + m.volume;
  }
  const rows = Object.values(acc).sort((a, b) => (a.date < b.date ? -1 : 1));
  return { rows, platforms: Array.from(platforms).sort() };
}

function nearestDate(series, target) {
  let best = series[0]?.date;
  for (const p of series) if (p.date <= target) best = p.date;
  return best;
}

const Panel = ({ title, children }) => (
  <div className="bg-panel border border-edge rounded-xl p-4">
    <h3 className="font-semibold mb-3">{title}</h3>
    {children}
  </div>
);
const Empty = ({ children }) => <div className="text-gray-500 text-sm">{children}</div>;
const Metric = ({ k, v }) => (
  <>
    <dt className="text-gray-400">{k}</dt>
    <dd className="text-right">{v}</dd>
  </>
);
