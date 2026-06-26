import React, { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { scoreColor, fmtNum, severityColor } from "../lib/format";

// Sector heatmap, rebuilt for decisions: color by momentum OR level, with a
// trend sparkline, catalyst/flag overlays, confidence shading, a quadrant
// view, and a thesis drill-down.

function momentumColor(v) {
  if (v === null || v === undefined) return "#374151";
  const t = Math.max(-15, Math.min(15, v)) / 15; // clip +/-15 pts
  if (t >= 0) return `rgb(${Math.round(60 + (1 - t) * 80)}, 190, 90)`;
  return `rgb(220, ${Math.round(120 + (1 + t) * 70)}, 70)`;
}

function Sparkline({ points, color = "#38bdf8", w = 88, h = 24 }) {
  if (!points || points.length < 2)
    return <div className="text-[10px] text-gray-600">no history</div>;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const step = w / (points.length - 1);
  const d = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${(h - ((p - min) / span) * h).toFixed(1)}`)
    .join(" ");
  return (
    <svg width={w} height={h} className="overflow-visible">
      <path d={d} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  );
}

const MomArrow = ({ v }) => {
  if (v === null || v === undefined) return <span className="text-gray-500">·</span>;
  const up = v >= 0;
  return (
    <span style={{ color: momentumColor(v) }}>
      {up ? "▲" : "▼"} {fmtNum(Math.abs(v), 1)}
    </span>
  );
};

export default function Heatmap({ onPick }) {
  const [tiles, setTiles] = useState([]);
  const [open, setOpen] = useState(null);
  const [colorBy, setColorBy] = useState("momentum"); // momentum | level
  const [view, setView] = useState("grid"); // grid | quadrant

  const load = async () => {
    const hm = await api.heatmap();
    setTiles(hm.tiles || []);
  };
  useEffect(() => {
    load();
  }, []);

  const colorFor = (t) =>
    colorBy === "momentum" ? momentumColor(t.momentum) : scoreColor(t.avg_composite);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <Toggle label="Color by" value={colorBy} setValue={setColorBy} options={[["momentum", "Momentum (Δ7d)"], ["level", "Level"]]} />
        <Toggle label="View" value={view} setValue={setView} options={[["grid", "Grid"], ["quadrant", "Quadrant"]]} />
        <span className="text-gray-500">Click a tile to drill into names + drivers.</span>
      </div>

      {view === "grid" ? (
        <Grid tiles={tiles} colorFor={colorFor} open={open} setOpen={setOpen} onPick={onPick} />
      ) : (
        <Quadrant tiles={tiles} open={open} setOpen={setOpen} />
      )}

      {open && <DrillDown tile={tiles.find((t) => t.subsector === open)} onPick={onPick} />}
    </div>
  );
}

function Grid({ tiles, colorFor, open, setOpen, onPick }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {tiles.map((t) => {
        const conf = t.data_completeness ?? 1;
        return (
          <div
            key={t.subsector}
            onClick={() => setOpen(open === t.subsector ? null : t.subsector)}
            className={`cursor-pointer rounded-xl p-4 border transition hover:scale-[1.01] ${
              open === t.subsector ? "ring-2 ring-sky-400" : ""
            }`}
            style={{
              background: colorFor(t) + "1f",
              borderColor: colorFor(t),
              opacity: 0.55 + 0.45 * conf, // desaturate low-confidence tiles
            }}
          >
            <div className="flex items-start justify-between">
              <div>
                <div className="font-semibold capitalize">{t.subsector}</div>
                <div className="text-xs text-gray-400">{t.count} names</div>
              </div>
              <Sparkline points={t.sparkline} color={colorFor(t)} />
            </div>

            <div className="flex items-end justify-between mt-2">
              <div>
                <div className="text-2xl font-bold leading-none" style={{ color: scoreColor(t.avg_composite) }}>
                  {fmtNum(t.avg_composite, 0)}
                </div>
                <div className="text-xs mt-1">
                  <MomArrow v={t.momentum} /> <span className="text-gray-500">7d</span>
                </div>
              </div>
              <div className="text-right text-[11px] space-y-0.5">
                {t.catalysts_30d > 0 && (
                  <div className="text-amber-300">🗓 {t.catalysts_30d} catalyst{t.catalysts_30d > 1 ? "s" : ""} ≤30d</div>
                )}
                {t.flag_count > 0 && (
                  <div className={t.flag_high ? "text-emerald-300" : "text-sky-300"}>
                    🚩 {t.flag_count} flag{t.flag_count > 1 ? "s" : ""}{t.flag_high ? ` (${t.flag_high} hot)` : ""}
                  </div>
                )}
                {t.breadth !== null && t.breadth !== undefined && (
                  <div className="text-gray-400">breadth {Math.round(t.breadth * 100)}%</div>
                )}
                {conf < 0.99 && <div className="text-gray-500">conf {Math.round(conf * 100)}%</div>}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Quadrant({ tiles, open, setOpen }) {
  const W = 720, H = 420, pad = 40;
  const pts = tiles.filter((t) => t.avg_composite !== null && t.momentum !== null);
  const maxMom = Math.max(10, ...pts.map((t) => Math.abs(t.momentum)));
  const x = (lvl) => pad + (lvl / 100) * (W - 2 * pad);
  const y = (mom) => H / 2 - (mom / maxMom) * (H / 2 - pad);

  return (
    <div className="bg-panel border border-edge rounded-xl p-3 overflow-x-auto">
      <svg width={W} height={H} className="min-w-[720px]">
        {/* quadrant guides */}
        <line x1={pad} y1={H / 2} x2={W - pad} y2={H / 2} stroke="#334155" strokeDasharray="4 4" />
        <line x1={(W) / 2} y1={pad} x2={W / 2} y2={H - pad} stroke="#334155" strokeDasharray="4 4" />
        <text x={W - pad} y={pad - 8} fill="#10b981" fontSize="11" textAnchor="end">Leaders (high · rising)</text>
        <text x={pad} y={pad - 8} fill="#38bdf8" fontSize="11">Improving (low · rising) ← alpha zone</text>
        <text x={W - pad} y={H - pad + 16} fill="#f59e0b" fontSize="11" textAnchor="end">Fading (high · falling)</text>
        <text x={pad} y={H - pad + 16} fill="#6b7280" fontSize="11">Laggards (low · falling)</text>
        <text x={W / 2} y={H - 6} fill="#94a3b8" fontSize="10" textAnchor="middle">Composite level →</text>

        {pts.map((t) => (
          <g key={t.subsector} className="cursor-pointer" onClick={() => setOpen(open === t.subsector ? null : t.subsector)}>
            <circle
              cx={x(t.avg_composite)} cy={y(t.momentum)}
              r={open === t.subsector ? 9 : 6}
              fill={momentumColor(t.momentum)}
              stroke={open === t.subsector ? "#fff" : "none"} strokeWidth="1.5"
            />
            <text x={x(t.avg_composite) + 9} y={y(t.momentum) + 3} fill="#cbd5e1" fontSize="10">
              {t.subsector}{t.catalysts_30d > 0 ? " 🗓" : ""}{t.flag_high > 0 ? " 🚩" : ""}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

function DrillDown({ tile, onPick }) {
  if (!tile) return null;
  return (
    <div className="bg-panel border border-edge rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="font-semibold capitalize">{tile.subsector} — names</div>
        <div className="text-xs text-gray-400">
          level {fmtNum(tile.avg_composite, 0)} · momentum <MomArrow v={tile.momentum} /> ·{" "}
          {tile.catalysts_90d} catalyst(s) ≤90d
        </div>
      </div>
      <div className="space-y-1">
        {tile.members.map((m) => (
          <div key={m.symbol} className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-edge/40 py-2">
            <button onClick={() => onPick?.(m.symbol)} className="font-semibold text-sky-400 hover:underline w-16 text-left">
              {m.symbol}
            </button>
            <span className="font-bold w-10" style={{ color: scoreColor(m.composite) }}>{fmtNum(m.composite, 0)}</span>
            <span className="w-20 text-xs"><MomArrow v={m.momentum} /></span>
            <span className="text-xs text-gray-400 flex-1 min-w-[140px]">
              {m.driver ? `↳ ${m.driver}` : "↳ —"}
            </span>
            {m.next_catalyst && (
              <span className="text-[11px] text-amber-300">
                🗓 {m.next_catalyst.event_type} in {m.next_catalyst.days_until}d
              </span>
            )}
            {m.flags.map((f) => (
              <span key={f.type} className={`text-[10px] border rounded px-1.5 py-0.5 ${severityColor[f.severity] || severityColor.info}`} title={f.message}>
                {f.type.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        ))}
      </div>
      <p className="text-xs text-gray-500 mt-2">
        Driver = the component contributing most to each name's score. Dim tiles = lower data completeness (treat scores with caution).
      </p>
    </div>
  );
}

function Toggle({ label, value, setValue, options }) {
  return (
    <div className="flex items-center gap-1">
      <span className="text-gray-400">{label}:</span>
      <div className="flex rounded-lg overflow-hidden border border-edge">
        {options.map(([val, lbl]) => (
          <button
            key={val}
            onClick={() => setValue(val)}
            className={`px-2.5 py-1 ${value === val ? "bg-sky-700 text-white" : "bg-ink text-gray-400 hover:text-gray-200"}`}
          >
            {lbl}
          </button>
        ))}
      </div>
    </div>
  );
}
