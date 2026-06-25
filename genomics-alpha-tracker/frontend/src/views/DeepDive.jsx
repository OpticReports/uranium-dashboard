import React, { useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine, BarChart, Bar, CartesianGrid,
} from "recharts";
import { api } from "../lib/api";
import { fmtNum, fmtMoney, fmtPct, scoreColor, naIfNull } from "../lib/format";
import RunwayGauge from "../components/RunwayGauge";
import Flags from "../components/Flags";

// Per-name deep dive: price + catalyst markers, revision/hype timelines,
// runway gauge, auditable score breakdown, flags, science/analyst feed.
export default function DeepDive({ symbol, onBack }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    setData(null);
    api.deepDive(symbol).then(setData).catch((e) => setErr(e.message));
  }, [symbol]);

  if (err) return <div className="text-rose-400">⚠ {err}</div>;
  if (!data) return <div className="text-gray-400">Loading {symbol}…</div>;

  const { security, prices, catalysts, revisions, mentions, publications, fundamentals, score, flags } = data;

  const priceData = prices.map((p) => ({ date: p.date, close: p.close }));
  const hypeData = aggregateMentions(mentions);

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
          <div className="text-xs text-gray-400">Alpha Signal</div>
          <div className="text-4xl font-bold" style={{ color: scoreColor(score?.composite) }}>
            {fmtNum(score?.composite, 0)}
          </div>
        </div>
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
        <Panel title="Hype timeline (daily mentions)">
          {hypeData.length ? (
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={hypeData} margin={{ left: -10, right: 10 }}>
                <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#94a3b8" }} minTickGap={30} />
                <YAxis tick={{ fontSize: 9, fill: "#94a3b8" }} />
                <Tooltip contentStyle={{ background: "#121826", border: "1px solid #1f2937" }} />
                <Bar dataKey="volume" fill="#a78bfa" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <Empty>No social data (X/Reddit keys absent or no chatter).</Empty>
          )}
        </Panel>

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
            <th className="text-right">Raw</th>
            <th className="text-right">Normalized</th>
            <th className="text-right">Weight</th>
            <th className="text-right">Weighted</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k} className="border-t border-edge/40">
              <td className="py-1">{k.replace(/_/g, " ")}</td>
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

function aggregateMentions(mentions) {
  const byDay = {};
  for (const m of mentions) byDay[m.date] = (byDay[m.date] || 0) + m.volume;
  return Object.entries(byDay)
    .sort()
    .map(([date, volume]) => ({ date, volume }));
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
