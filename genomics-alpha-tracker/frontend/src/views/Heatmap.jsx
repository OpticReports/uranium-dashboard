import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import { scoreColor, fmtNum } from "../lib/format";

// Sector heatmap by subsector; color = avg composite Alpha Signal. Click a tile
// to drill into its names.
export default function Heatmap({ onPick }) {
  const [tiles, setTiles] = useState([]);
  const [open, setOpen] = useState(null);
  const [scores, setScores] = useState({});

  const load = async () => {
    const [hm, sc] = await Promise.all([api.heatmap(), api.scores(true)]);
    setTiles(hm.sort((a, b) => (b.avg_composite ?? -1) - (a.avg_composite ?? -1)));
    setScores(Object.fromEntries(sc.map((s) => [s.symbol, s])));
  };
  useEffect(() => {
    load();
  }, []);

  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {tiles.map((t) => (
          <div
            key={t.subsector}
            onClick={() => setOpen(open === t.subsector ? null : t.subsector)}
            className="cursor-pointer rounded-xl p-4 border border-edge transition hover:scale-[1.02]"
            style={{ background: scoreColor(t.avg_composite) + "22", borderColor: scoreColor(t.avg_composite) }}
          >
            <div className="font-semibold">{t.subsector}</div>
            <div className="text-3xl font-bold" style={{ color: scoreColor(t.avg_composite) }}>
              {fmtNum(t.avg_composite, 0)}
            </div>
            <div className="text-xs text-gray-400">{t.count} names</div>
          </div>
        ))}
      </div>

      {open && (
        <div className="mt-4 bg-panel border border-edge rounded-xl p-4">
          <div className="font-semibold mb-2">{open} — drill-down</div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {tiles
              .find((t) => t.subsector === open)
              .symbols.map((sym) => {
                const s = scores[sym];
                return (
                  <button
                    key={sym}
                    onClick={() => onPick?.(sym)}
                    className="text-left rounded-lg border border-edge p-2 hover:bg-ink"
                  >
                    <div className="font-medium">{sym}</div>
                    <div className="text-sm" style={{ color: scoreColor(s?.composite) }}>
                      {fmtNum(s?.composite, 0)}
                    </div>
                  </button>
                );
              })}
          </div>
        </div>
      )}
    </div>
  );
}
