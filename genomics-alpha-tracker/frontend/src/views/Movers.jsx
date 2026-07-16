import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import { fmtNum, scoreColor, fmtScore10 } from "../lib/format";

// "Movers in narrative": names with the largest hype acceleration this week.
export default function Movers({ onPick }) {
  const [movers, setMovers] = useState([]);
  const [flags, setFlags] = useState([]);

  useEffect(() => {
    api.movers(15).then(setMovers);
    api.flags(7).then(setFlags);
  }, []);

  return (
    <div className="grid lg:grid-cols-2 gap-4">
      <div className="bg-panel border border-edge rounded-xl p-4">
        <h3 className="font-semibold mb-3">📈 Largest hype acceleration (7d)</h3>
        <div className="space-y-1">
          {movers.map((m) => (
            <button
              key={m.symbol}
              onClick={() => onPick?.(m.symbol)}
              className="w-full flex items-center justify-between p-2 rounded hover:bg-ink text-left"
            >
              <div>
                <span className="font-semibold text-sky-400">{m.symbol}</span>
                <span className="text-gray-400 text-sm ml-2">{m.name}</span>
              </div>
              <div className="flex items-center gap-4">
                <span className="text-sm">
                  accel <b>{fmtNum(m.mention_acceleration, 2)}</b>
                </span>
                <span className="font-bold" style={{ color: scoreColor(m.composite) }}>
                  {fmtScore10(m.composite)}
                </span>
              </div>
            </button>
          ))}
          {!movers.length && <div className="text-gray-500 text-sm">No social data yet.</div>}
        </div>
      </div>

      <div className="bg-panel border border-edge rounded-xl p-4">
        <h3 className="font-semibold mb-3">🚩 Active flags (7d)</h3>
        <div className="space-y-2 max-h-[28rem] overflow-y-auto">
          {flags.map((f) => (
            <button
              key={f.id}
              onClick={() => onPick?.(f.symbol)}
              className="w-full text-left border border-edge rounded-lg p-2 hover:bg-ink"
            >
              <div className="flex justify-between">
                <span className="font-medium text-sky-400">{f.symbol}</span>
                <span className="text-xs text-gray-400">{f.flag_type}</span>
              </div>
              <div className="text-xs text-gray-300">{f.message}</div>
            </button>
          ))}
          {!flags.length && <div className="text-gray-500 text-sm">No flags yet.</div>}
        </div>
      </div>
    </div>
  );
}
