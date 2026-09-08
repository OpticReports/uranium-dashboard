import React, { useEffect, useState } from "react";
import {
  ComposedChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import { api } from "../lib/api";

// "Attention Tops": Google Trends search interest vs the traded proxy, with
// the attention-top detector's flags. OBSERVE-ONLY - feeds no score, makes no
// call. The friend-with-the-silver-call intuition, made testable (H14).
const STATE_STYLE = {
  CLIMAX: "bg-red-600/20 text-red-300 border-red-600/50",
  FADING: "bg-amber-500/20 text-amber-300 border-amber-500/50",
  DIVERGENCE: "bg-sky-600/20 text-sky-300 border-sky-600/50",
  COOLED: "bg-gray-500/20 text-gray-300 border-gray-500/50",
  ELEVATED: "bg-violet-600/20 text-violet-300 border-violet-600/50",
  QUIET: "bg-emerald-600/10 text-emerald-300 border-emerald-600/40",
  NO_DATA: "bg-gray-700/30 text-gray-400 border-gray-600",
};
const FLAG_COLOR = { climax: "#ef4444", fading: "#f59e0b", divergence: "#38bdf8", cooled: "#9ca3af" };

const pct = (x) => (x == null ? "—" : `${x > 0 ? "+" : ""}${x}%`);
const flagOf = (p) => (p.climax ? "climax" : p.fading ? "fading" : p.divergence ? "divergence" : p.cooled ? "cooled" : null);

// Merge consecutive same-flag weeks into one episode chip: "CLIMAX s2 2025-12-21 → 12-28".
function episodesOf(pts) {
  const out = [];
  for (const p of pts) {
    const f = flagOf(p);
    if (!f) continue;
    const last = out[out.length - 1];
    if (last && last.flag === f && weeksBetween(last.end, p.date) <= 2) {
      last.end = p.date;
    } else {
      out.push({ flag: f, start: p.date, end: p.date, stage: p.stage });
    }
  }
  return out;
}
const weeksBetween = (a, b) => Math.round((new Date(b) - new Date(a)) / (7 * 864e5));

function FlagDot(props) {
  const { cx, cy, payload } = props;
  const f = payload && flagOf(payload);
  if (!f || cx == null || cy == null) return null;
  return <circle cx={cx} cy={cy} r={4} fill={FLAG_COLOR[f]} stroke="#0b1220" strokeWidth={1} />;
}

export default function Trends() {
  const [data, setData] = useState(null);
  const [study, setStudy] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    api.trends().then(setData).catch((e) => setErr(e.message));
    api.trendsStudy().then(setStudy).catch(() => setStudy(null));
  }, []);

  if (err) return <div className="text-red-400 text-sm">Trends unavailable: {err}</div>;
  if (!data) return <div className="text-gray-500 text-sm">Loading attention series…</div>;

  const st = data.status || {};
  return (
    <div className="space-y-4">
      <div className="bg-panel border border-edge rounded-xl p-4 text-sm text-gray-300">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-semibold text-base">🔭 Attention Tops — Google Trends vs price (observe-only)</h3>
          <span className="text-xs text-gray-400">
            DataForSEO {st.configured ? "connected" : "not configured"} · {st.used_today ?? 0}/{st.daily_cap} req today
            {st.breaker_until ? " · paused (auth/billing)" : ""}
          </span>
        </div>
        <p className="mt-2 text-xs text-gray-400">{data.note}</p>
        {study && <StudyBox study={study} />}
      </div>

      {data.items.map((it) => (
        <KeywordCard key={it.keyword} item={it} />
      ))}
      {!data.items.length && (
        <div className="text-gray-500 text-sm">No keywords configured (backend/config/trends.yaml).</div>
      )}
    </div>
  );
}

function StudyBox({ study }) {
  const p = study.pooled || {};
  const row = (label, s) =>
    s && (
      <tr key={label} className="border-t border-edge/60">
        <td className="py-1 pr-3 text-gray-300">{label}</td>
        <td className="py-1 pr-3 text-right">{s.episodes ?? s.r12?.n}</td>
        <td className="py-1 pr-3 text-right">{pct(s.r12?.median)}</td>
        <td className="py-1 pr-3 text-right">{pct(s.r26?.median)}</td>
        <td className="py-1 pr-3 text-right">{pct(s.dd26?.median)}</td>
        <td className="py-1 text-right">{s.dd26?.pct_dd_worse_than_20 ?? "—"}%</td>
      </tr>
    );
  return (
    <details className="mt-2">
      <summary className="cursor-pointer text-xs text-sky-300">
        Honesty box — frozen study, 11 series, {p.recall?.with_climax_within_10wk}/{p.recall?.price_peaks} price tops had a CLIMAX in the prior 10 wks
      </summary>
      <table className="mt-2 text-xs w-full max-w-xl">
        <thead>
          <tr className="text-gray-500">
            <th className="text-left font-normal">after flag</th>
            <th className="text-right font-normal">n</th>
            <th className="text-right font-normal">med 12w</th>
            <th className="text-right font-normal">med 26w</th>
            <th className="text-right font-normal">med maxDD 26w</th>
            <th className="text-right font-normal">DD ≤ −20%</th>
          </tr>
        </thead>
        <tbody>
          {row("all weeks (base)", p.base_rate && { ...p.base_rate, episodes: p.base_rate.r12?.n })}
          {row("CLIMAX (all)", p.climax)}
          {row("CLIMAX stage 1 (post hoc)", p.climax_stage1)}
          {row("CLIMAX stage 2+ (post hoc)", p.climax_stage2plus)}
          {row("FADING", p.fading)}
          {row("DIVERGENCE", p.divergence)}
        </tbody>
      </table>
      <p className="mt-1 text-[11px] text-gray-500">
        In-sample: thresholds were chosen on these same series. Weekly closes; n is tiny. Stage split was found after looking. Not a forecast.
      </p>
    </details>
  );
}

function KeywordCard({ item }) {
  const s = item.summary || {};
  const pts = item.points || [];
  const rows = pts.map((p) => ({ ...p, flagClose: flagOf(p) ? p.close : null }));
  const flagged = episodesOf(pts);
  const cls = STATE_STYLE[s.state] || STATE_STYLE.NO_DATA;
  return (
    <div className="bg-panel border border-edge rounded-xl p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-sky-400">{item.label}</span>
            <span className="text-xs text-gray-500">“{item.keyword}” · {item.price_symbol || "no price proxy"}</span>
            <span className={`text-[11px] px-2 py-0.5 rounded border ${cls}`}>{s.state || "NO_DATA"}</span>
            {s.state === "CLIMAX" && pts.length && pts[pts.length - 1].stage && (
              <span className="text-[11px] text-red-300">stage {pts[pts.length - 1].stage}</span>
            )}
          </div>
          <div className="text-xs text-gray-400 mt-1">{item.positions}</div>
          {s.notes?.length > 0 && <div className="text-xs text-gray-300 mt-1">{s.notes.join(" · ")}</div>}
        </div>
        <div className="text-xs text-gray-400 text-right">
          <div>interest {s.interest ?? "—"} (3w {s.smooth ?? "—"}) · vs prior record {s.intensity != null ? `${s.intensity}×` : "—"}</div>
          <div>last CLIMAX {s.last_climax || "—"} · FADING {s.last_fading || "—"} · DIVERGENCE {s.last_divergence || "—"}</div>
          <div>{s.weeks} wks · {item.window || ""} · fetched {item.fetched_at ? item.fetched_at.slice(0, 10) : "never"}</div>
        </div>
      </div>
      {rows.length > 0 ? (
        <div className="h-56 mt-3">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={40} tickFormatter={(d) => d.slice(0, 7)} />
              <YAxis yAxisId="i" domain={[0, 100]} tick={{ fontSize: 10 }} width={30} />
              <YAxis yAxisId="p" orientation="right" domain={["auto", "auto"]} tick={{ fontSize: 10 }} width={48} />
              <Tooltip
                contentStyle={{ background: "#0b1220", border: "1px solid #1f2937", fontSize: 11 }}
                formatter={(v, n) => [typeof v === "number" ? v.toFixed(n === "close" ? 2 : 0) : v, n]}
              />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              <Line yAxisId="i" type="monotone" dataKey="interest" stroke="#a78bfa" dot={false} strokeWidth={1.4} name="search interest" isAnimationActive={false} />
              <Line yAxisId="p" type="monotone" dataKey="close" stroke="#e5e7eb" dot={false} strokeWidth={1.2} name="close" isAnimationActive={false} connectNulls />
              <Line yAxisId="p" dataKey="flagClose" stroke="none" dot={<FlagDot />} activeDot={false} name="flag" isAnimationActive={false} legendType="none" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="text-xs text-gray-500 mt-2">No series stored yet — the daily job fills this once DataForSEO credentials are set.</div>
      )}
      {flagged.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {flagged.slice(-8).map((e) => {
            const flag = e.flag.toUpperCase();
            return (
              <span key={e.start} className={`text-[10px] px-1.5 py-0.5 rounded border ${STATE_STYLE[flag]}`}>
                {flag}{e.stage ? ` s${e.stage}` : ""} {e.start}{e.end !== e.start ? ` → ${e.end.slice(5)}` : ""}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
