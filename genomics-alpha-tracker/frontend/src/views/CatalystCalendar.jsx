import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import { eventLabel } from "../lib/format";

const IMPACT_COLOR = (i) =>
  i >= 0.85 ? "#ef4444" : i >= 0.6 ? "#f59e0b" : i >= 0.4 ? "#eab308" : "#64748b";

// Catalyst calendar: next 90 days, sortable/filterable by impact and subsector.
export default function CatalystCalendar({ onPick }) {
  const [cats, setCats] = useState([]);
  const [tags, setTags] = useState([]);
  const [days, setDays] = useState(90);
  const [subsector, setSubsector] = useState("");
  const [minImpact, setMinImpact] = useState(0);

  const load = async () => {
    const [c, tg] = await Promise.all([
      api.catalysts({ days, subsector: subsector || undefined, minImpact }),
      api.subsectors(),
    ]);
    setCats(c);
    setTags(tg);
  };
  useEffect(() => {
    load();
  }, [days, subsector, minImpact]);

  const daysUntil = (d) =>
    Math.round((new Date(d) - new Date()) / 86400000);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3 items-center text-sm">
        <label>
          Horizon:
          <select value={days} onChange={(e) => setDays(+e.target.value)} className="ml-2 bg-ink border border-edge rounded px-2 py-1">
            {[30, 60, 90, 180, 365].map((d) => (
              <option key={d} value={d}>
                {d}d
              </option>
            ))}
          </select>
        </label>
        <label>
          Subsector:
          <select value={subsector} onChange={(e) => setSubsector(e.target.value)} className="ml-2 bg-ink border border-edge rounded px-2 py-1">
            <option value="">all</option>
            {tags.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label>
          Min impact: {minImpact.toFixed(2)}
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={minImpact}
            onChange={(e) => setMinImpact(+e.target.value)}
            className="ml-2 align-middle"
          />
        </label>
        <span className="text-gray-500">{cats.length} catalysts</span>
      </div>

      <div className="bg-panel border border-edge rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="text-gray-400 border-b border-edge">
            <tr>
              <th className="px-3 py-2 text-left">Date</th>
              <th className="px-3 py-2 text-left">In</th>
              <th className="px-3 py-2 text-left">Symbol</th>
              <th className="px-3 py-2 text-left">Type</th>
              <th className="px-3 py-2 text-left">Title</th>
              <th className="px-3 py-2 text-left">Impact</th>
            </tr>
          </thead>
          <tbody>
            {cats.map((c) => (
              <tr key={c.id} className="border-b border-edge/50 hover:bg-ink">
                <td className="px-3 py-2 whitespace-nowrap">{c.date}</td>
                <td className="px-3 py-2 text-gray-400">{daysUntil(c.date)}d</td>
                <td className="px-3 py-2">
                  <button className="text-sky-400 hover:underline font-medium" onClick={() => onPick?.(c.symbol)}>
                    {c.symbol}
                  </button>
                </td>
                <td className="px-3 py-2">{eventLabel(c.event_type)}</td>
                <td className="px-3 py-2 text-gray-300 max-w-md truncate" title={c.title}>
                  {c.url ? (
                    <a href={c.url} target="_blank" rel="noreferrer" className="hover:underline">
                      {c.title || "—"}
                    </a>
                  ) : (
                    c.title || "—"
                  )}
                  {!c.confirmed && <span className="ml-2 text-[10px] text-amber-400">est.</span>}
                </td>
                <td className="px-3 py-2 font-semibold" style={{ color: IMPACT_COLOR(c.effective_impact) }}>
                  {c.effective_impact.toFixed(2)}
                  {c.impact_override != null && <span className="text-[10px] ml-1 text-gray-400">(override)</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!cats.length && <div className="p-4 text-gray-500 text-sm">No catalysts in range. Run a backfill / ingestion first.</div>}
      </div>
    </div>
  );
}
