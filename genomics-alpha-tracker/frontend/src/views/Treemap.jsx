import React, { useEffect, useMemo, useRef, useState } from "react";
import { hierarchy, treemap, treemapSquarify } from "d3-hierarchy";
import { api } from "../lib/api";
import { scoreColor } from "../lib/format";

// Finviz-style treemap: tiles grouped by subsector, SIZE = market cap,
// COLOR = a metric you choose (Alpha Signal / momentum / 1-day price).

const METRICS = [
  ["composite", "Alpha Signal"],
  ["momentum", "Momentum (Δ7d)"],
  ["price_change", "Price (1d)"],
];

function momentumColor(v) {
  if (v === null || v === undefined) return "#374151";
  const t = Math.max(-15, Math.min(15, v)) / 15;
  return t >= 0
    ? `rgb(${Math.round(60 + (1 - t) * 80)},190,90)`
    : `rgb(220,${Math.round(120 + (1 + t) * 70)},70)`;
}
function priceColor(v) {
  if (v === null || v === undefined) return "#374151";
  const t = Math.max(-0.05, Math.min(0.05, v)) / 0.05;
  return t >= 0
    ? `rgb(${Math.round(60 + (1 - t) * 80)},190,90)`
    : `rgb(220,${Math.round(120 + (1 + t) * 70)},70)`;
}
function colorFor(metric, n) {
  if (metric === "composite") return scoreColor(n.composite);
  if (metric === "momentum") return momentumColor(n.momentum);
  return priceColor(n.price_change);
}
function labelFor(metric, n) {
  if (metric === "composite") return n.composite == null ? "n/a" : Math.round(n.composite);
  if (metric === "momentum")
    return n.momentum == null ? "·" : `${n.momentum >= 0 ? "+" : ""}${n.momentum.toFixed(0)}`;
  return n.price_change == null ? "·" : `${(n.price_change * 100).toFixed(1)}%`;
}

export default function Treemap({ onPick }) {
  const [nodes, setNodes] = useState([]);
  const [metric, setMetric] = useState("composite");
  const [width, setWidth] = useState(1000);
  const ref = useRef(null);
  const HEIGHT = 600;

  useEffect(() => {
    api.treemap().then((d) => setNodes(d.nodes || []));
  }, []);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver((e) => setWidth(e[0].contentRect.width));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);

  const root = useMemo(() => {
    if (!nodes.length) return null;
    const caps = nodes.map((n) => n.market_cap).filter((c) => c && c > 0);
    const floor = caps.length ? Math.min(...caps) * 0.4 : 1;
    const groups = {};
    for (const n of nodes) {
      (groups[n.subsector] = groups[n.subsector] || []).push({
        ...n,
        value: n.market_cap && n.market_cap > 0 ? n.market_cap : floor,
      });
    }
    const data = {
      name: "root",
      children: Object.entries(groups).map(([name, children]) => ({ name, children })),
    };
    const r = hierarchy(data).sum((d) => d.value).sort((a, b) => b.value - a.value);
    treemap().tile(treemapSquarify).size([width, HEIGHT]).paddingInner(2).paddingTop(16).round(true)(r);
    return r;
  }, [nodes, width]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <div className="flex items-center gap-1">
          <span className="text-gray-400">Color by:</span>
          <div className="flex rounded-lg overflow-hidden border border-edge">
            {METRICS.map(([val, lbl]) => (
              <button
                key={val}
                onClick={() => setMetric(val)}
                className={`px-2.5 py-1 ${metric === val ? "bg-sky-700 text-white" : "bg-ink text-gray-400 hover:text-gray-200"}`}
              >
                {lbl}
              </button>
            ))}
          </div>
        </div>
        <Legend metric={metric} />
        <span className="text-gray-500">Tile size = market cap · click a tile for the deep dive</span>
      </div>

      <div ref={ref} className="relative w-full border border-edge rounded-xl overflow-hidden bg-ink" style={{ height: HEIGHT }}>
        {root &&
          root.children.map((g) => (
            <div
              key={g.data.name}
              className="absolute text-[10px] uppercase tracking-wide text-gray-300 px-1 font-semibold pointer-events-none"
              style={{ left: g.x0, top: g.y0, width: g.x1 - g.x0 }}
            >
              {g.data.name}
            </div>
          ))}
        {root &&
          root.leaves().map((leaf) => {
            const w = leaf.x1 - leaf.x0;
            const h = leaf.y1 - leaf.y0;
            const n = leaf.data;
            return (
              <button
                key={n.symbol}
                onClick={() => onPick?.(n.symbol)}
                title={`${n.symbol} ${n.name} — Alpha ${n.composite ?? "n/a"}`}
                className="absolute flex flex-col items-center justify-center overflow-hidden text-center"
                style={{
                  left: leaf.x0, top: leaf.y0, width: w, height: h,
                  background: colorFor(metric, n),
                  border: "1px solid rgba(0,0,0,0.35)",
                }}
              >
                {w > 30 && h > 16 && (
                  <span className="font-bold leading-none text-black/85" style={{ fontSize: Math.min(16, Math.max(8, w / 5)) }}>
                    {n.symbol}
                  </span>
                )}
                {w > 40 && h > 32 && (
                  <span className="leading-none text-black/70 mt-0.5" style={{ fontSize: Math.min(12, Math.max(8, w / 7)) }}>
                    {labelFor(metric, n)}
                  </span>
                )}
              </button>
            );
          })}
      </div>
    </div>
  );
}

function Legend({ metric }) {
  const stops =
    metric === "composite"
      ? ["0", "25", "50", "75", "100"]
      : metric === "momentum"
      ? ["-15", "-7", "0", "+7", "+15"]
      : ["-5%", "-2%", "0", "+2%", "+5%"];
  const colors =
    metric === "composite"
      ? [scoreColor(0), scoreColor(25), scoreColor(50), scoreColor(75), scoreColor(100)]
      : metric === "momentum"
      ? [momentumColor(-15), momentumColor(-7), momentumColor(0), momentumColor(7), momentumColor(15)]
      : [priceColor(-0.05), priceColor(-0.02), priceColor(0), priceColor(0.02), priceColor(0.05)];
  return (
    <div className="flex items-center gap-2 text-[11px] text-gray-400">
      <span>{metric === "composite" ? "weak" : "down"}</span>
      <div className="flex">
        {colors.map((c, i) => (
          <span key={i} className="w-5 h-3" style={{ background: c }} title={stops[i]} />
        ))}
      </div>
      <span>{metric === "composite" ? "strong" : "up"}</span>
      {metric === "composite" && <span className="ml-1">(0–100, 50 = universe avg)</span>}
    </div>
  );
}
