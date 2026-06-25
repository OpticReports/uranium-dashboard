import React from "react";

// Cash runway gauge. null runway => explicit "no data", not a full/empty bar.
export default function RunwayGauge({ quarters, threshold = 8, floor = 2 }) {
  if (quarters === null || quarters === undefined) {
    return (
      <div className="text-sm text-gray-400">
        Runway: <span className="text-gray-500">n/a (no burn data)</span>
      </div>
    );
  }
  const pct = Math.max(0, Math.min(1, quarters / (threshold * 1.5)));
  const danger = quarters < floor;
  const warn = quarters < threshold;
  const color = danger ? "#ef4444" : warn ? "#f59e0b" : "#10b981";
  return (
    <div>
      <div className="flex justify-between text-sm mb-1">
        <span className="text-gray-400">Cash runway</span>
        <span style={{ color }}>{quarters.toFixed(1)} quarters</span>
      </div>
      <div className="h-3 bg-ink rounded-full overflow-hidden border border-edge">
        <div className="h-full rounded-full" style={{ width: `${pct * 100}%`, background: color }} />
      </div>
      {warn && (
        <div className="text-xs mt-1" style={{ color }}>
          {danger ? "⛔ Cliff — below floor" : "⚠ Approaching cliff"}
        </div>
      )}
    </div>
  );
}
