import React, { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { scoreColor, fmtNum } from "../lib/format";
import AddTicker from "../components/AddTicker";
import InfoTip from "../components/InfoTip";

const COMPONENT_COLS = [
  "revision_velocity",
  "catalyst_score",
  "hype_divergence",
  "positioning",
  "runway_penalty",
];

// Watchlist table: sortable by composite or any component, with inline
// add / deactivate / remove controls.
export default function Watchlist({ onPick }) {
  const [rows, setRows] = useState([]);
  const [universe, setUniverse] = useState([]);
  const [tags, setTags] = useState([]);
  const [sort, setSort] = useState({ key: "composite", dir: -1 });
  const [showInactive, setShowInactive] = useState(false);

  const load = async () => {
    const [sc, uni, tg] = await Promise.all([
      api.scores(false),
      api.listUniverse(true),
      api.subsectors(),
    ]);
    const byUni = Object.fromEntries(uni.map((u) => [u.symbol, u]));
    setRows(sc.map((s) => ({ ...s, active: byUni[s.symbol]?.active ?? true })));
    setUniverse(uni);
    setTags(tg);
  };
  useEffect(() => {
    load();
  }, []);

  const merged = useMemo(() => {
    // include universe names that may not have a score yet
    const scored = new Set(rows.map((r) => r.symbol));
    const extra = universe
      .filter((u) => !scored.has(u.symbol))
      .map((u) => ({ symbol: u.symbol, name: u.name, subsector: u.subsector, active: u.active, composite: null, components: {} }));
    return [...rows, ...extra].filter((r) => showInactive || r.active);
  }, [rows, universe, showInactive]);

  const sorted = useMemo(() => {
    const v = (r) =>
      sort.key === "composite" ? r.composite : r.components?.[sort.key];
    return [...merged].sort((a, b) => {
      const av = v(a),
        bv = v(b);
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      return (av - bv) * sort.dir;
    });
  }, [merged, sort]);

  const toggleSort = (key) =>
    setSort((s) => (s.key === key ? { key, dir: -s.dir } : { key, dir: -1 }));

  const setActive = async (symbol, active) => {
    await api.updateTicker(symbol, { active });
    load();
  };
  const remove = async (symbol) => {
    if (!confirm(`Permanently remove ${symbol}? (Deactivate keeps history.)`)) return;
    await api.deleteTicker(symbol);
    load();
  };

  return (
    <div className="space-y-4">
      <AddTicker onAdded={load} knownTags={tags} />

      <div className="flex items-center gap-3 text-sm">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
          Show inactive
        </label>
        <button onClick={() => api.recompute().then(load)} className="bg-sky-700 hover:bg-sky-600 rounded px-3 py-1">
          Recompute scores
        </button>
        <button onClick={() => api.reloadUniverse().then(load)} className="bg-edge hover:bg-gray-700 rounded px-3 py-1">
          Reload watchlist.yaml
        </button>
      </div>

      <div className="overflow-x-auto bg-panel border border-edge rounded-xl">
        <table className="w-full text-sm">
          <thead className="text-gray-400 border-b border-edge">
            <tr>
              <Th>Symbol</Th>
              <Th>Name</Th>
              <Th onClick={() => toggleSort("composite")} active={sort.key === "composite"} tip="composite">
                Alpha
              </Th>
              {COMPONENT_COLS.map((c) => (
                <Th key={c} onClick={() => toggleSort(c)} active={sort.key === c} tip={c}>
                  {c.replace(/_/g, " ")}
                </Th>
              ))}
              <Th tip="tags">Tags</Th>
              <Th>Controls</Th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.symbol} className={`border-b border-edge/50 ${r.active ? "" : "opacity-50"}`}>
                <td className="px-3 py-2">
                  <button className="font-semibold text-sky-400 hover:underline" onClick={() => onPick?.(r.symbol)}>
                    {r.symbol}
                  </button>
                </td>
                <td className="px-3 py-2 text-gray-300">{r.name}</td>
                <td className="px-3 py-2 font-bold" style={{ color: scoreColor(r.composite) }}>
                  {fmtNum(r.composite, 0)}
                </td>
                {COMPONENT_COLS.map((c) => (
                  <td key={c} className="px-3 py-2" style={{ color: scoreColor(r.components?.[c]) }}>
                    {fmtNum(r.components?.[c], 0)}
                  </td>
                ))}
                <td className="px-3 py-2 text-xs text-gray-400">{(r.subsector || []).join(", ")}</td>
                <td className="px-3 py-2 whitespace-nowrap">
                  <button
                    onClick={() => setActive(r.symbol, !r.active)}
                    className="text-xs border border-edge rounded px-2 py-0.5 mr-1 hover:bg-ink"
                  >
                    {r.active ? "Deactivate" : "Activate"}
                  </button>
                  <button
                    onClick={() => remove(r.symbol)}
                    className="text-xs border border-rose-800 text-rose-400 rounded px-2 py-0.5 hover:bg-rose-900/30"
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-gray-500">
        Cells show 0–100 normalized components. <span className="text-gray-400">n/a</span> = no data
        (not zero). Deactivating retains history; Remove deletes the universe row.
      </p>
    </div>
  );
}

function Th({ children, onClick, active, tip }) {
  return (
    <th
      className={`px-3 py-2 text-left font-medium ${active ? "text-sky-300" : ""}`}
    >
      <span onClick={onClick} className={onClick ? "cursor-pointer select-none" : ""}>
        {children} {active ? "↕" : ""}
      </span>
      {tip && <InfoTip term={tip} />}
    </th>
  );
}
