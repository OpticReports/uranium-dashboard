import { useEffect, useState } from "react";
import {
  api,
  ApiError,
  type PinBoard as PinBoardData,
  type PinChannel,
  type PinHistory,
} from "../lib/api";
import { InlineError, Loading, Panel, StatusPill } from "./ui";
import { formatValue, STATUS_COLOR } from "../lib/format";
import InfoTip from "./InfoTip";
import {
  ChannelHistoryChart,
  CollectiveHistoryChart,
  ConfluenceReadout,
} from "./PinHistoryChart";

// Dalio pin board — the gun is the debt buildup; the pin is the trigger.
// Six measurable spark channels, each scored from live data, never a forecast.

const CHANNEL_TIP: Record<string, string> = {
  oil_shock: "pin_oil",
  policy_shock: "pin_policy",
  credit_event: "pin_credit",
  fiscal: "pin_fiscal",
  plumbing: "pin_plumbing",
  uncertainty: "pin_uncertainty",
  basis_trade: "pin_basis",
  private_credit: "pin_private_credit",
  carry_unwind: "pin_carry",
  demand_strike: "pin_demand_strike",
  concentration: "pin_concentration",
  vol_supply: "pin_vol_supply",
};

function partDotColor(status: string): string {
  return STATUS_COLOR[status as keyof typeof STATUS_COLOR] ?? "#6b7280";
}

function OverallBanner({ board }: { board: PinBoardData }) {
  const { overall, n_red, n_yellow } = board;
  if (overall === "STALE") {
    return (
      <div className="mb-4 rounded-lg border border-slate-700 bg-slate-900/60 px-4 py-2.5 text-xs text-slate-400">
        No live pin-channel data yet — most channels need a FRED API key to
        populate.
      </div>
    );
  }
  const pressure = board.pressure != null ? (
    <span className="ml-2 font-mono text-xs font-normal opacity-80">
      · board pressure {board.pressure.toFixed(0)}/100
      {board.hottest ? ` · hottest: ${board.hottest.label} (${board.hottest.score.toFixed(0)})` : ""}
    </span>
  ) : null;
  if (overall === "RED") {
    return (
      <div className="mb-4 animate-pulse rounded-lg border border-red-600 bg-red-500/10 px-4 py-2.5 text-sm font-semibold text-red-400">
        ⚠ {n_red} channel{n_red === 1 ? "" : "s"} flashing red{pressure}
      </div>
    );
  }
  if (overall === "YELLOW") {
    const n = n_yellow + n_red;
    return (
      <div className="mb-4 rounded-lg border border-amber-600 bg-amber-500/10 px-4 py-2.5 text-sm font-semibold text-amber-400">
        ⚠ {n} channel{n === 1 ? "" : "s"} warming{pressure}
      </div>
    );
  }
  return (
    <div className="mb-4 rounded-lg border border-emerald-700 bg-emerald-500/10 px-4 py-2.5 text-sm font-semibold text-emerald-400">
      No spark visible in monitored channels{pressure}
    </div>
  );
}

// Accident composite gauge — the one measured pins->market configuration
// (studies/pin-rule-hindcast): fast-channel red on a flat/inverted curve.
// Two arming conditions shown as switches, plus a spread meter so you can
// watch the curve approach the trip line before it flips.
function AccidentGauge({ board }: { board: PinBoardData }) {
  const g = board.accident_gauge;
  if (!g || g.status === "STALE") return null;
  const thr = g.curve_threshold_pp;
  // meter scale: -1.0pp .. +2.0pp, trip zone left of the threshold
  const LO = -1.0, HI = 2.0;
  const pos = (v: number) => `${Math.min(100, Math.max(0, ((v - LO) / (HI - LO)) * 100))}%`;
  const statusText = g.status === "RED" ? "TRIGGERED" : g.status === "YELLOW" ? "ARMED — one condition" : "disarmed";
  // tri-state: true = lit, false = dark, null = UNKNOWN (data missing/stale) —
  // "no data" must never render as "condition not met"
  const Cond = ({ on, label, detail, hint }: {
    on: boolean | null; label: string; detail: string; hint?: string;
  }) => (
    <span
      title={hint}
      className={
        "rounded border px-2 py-1 text-[10px] leading-tight " +
        (on
          ? "border-red-600 bg-red-500/15 text-red-300"
          : on === null
            ? "border-slate-600 border-dashed bg-slate-800/30 text-slate-500"
            : "border-slate-700 bg-slate-800/50 text-slate-500")
      }
    >
      <span className="font-semibold uppercase tracking-wide">
        {on ? "■" : on === null ? "?" : "□"} {label}
      </span>{" "}
      <span className={on ? "text-red-200" : "text-slate-500"}>
        {on === null ? `unknown — ${detail}` : detail}
      </span>
    </span>
  );
  return (
    <div className="mb-4 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2.5">
      <div className="mb-1.5 flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-200">
          Accident composite
          <InfoTip term="accident_gauge" />
        </span>
        <StatusPill status={g.status} pulse={g.status === "RED"} />
        <span className="text-[11px] text-slate-400">{statusText}</span>
        <span className="text-[10px] text-slate-500">
          — hindcast: 44% odds of a ≥15% drawdown within 12m when both fire, vs 20% base (5 of 11 clusters — context, not calibration)
        </span>
      </div>
      <div className="mb-2 flex flex-wrap gap-1.5">
        <Cond
          on={g.fast_red}
          label="1 · fast channel red"
          detail={
            g.fast_red
              ? g.fast_red_channels.join(", ")
              : g.fast_red === null
                ? "no fast channel reporting"
                : "none of credit / plumbing / basis / carry"
          }
        />
        <Cond
          on={g.curve_flat}
          label={`2 · curve flat (<+${thr.toFixed(2)}pp in 6m)`}
          detail={
            g.spread_3m10y_now != null && g.spread_3m10y_min_6m != null
              ? `3m10y now ${g.spread_3m10y_now >= 0 ? "+" : ""}${g.spread_3m10y_now.toFixed(2)}pp · 6m low ${g.spread_3m10y_min_6m >= 0 ? "+" : ""}${g.spread_3m10y_min_6m.toFixed(2)}pp`
              : "no curve data"
          }
          hint={"Flattening = the gap between the 10-year and 3-month Treasury yields shrinking. "
            + "Steep (about +1pp or more) is normal — long rates above short rates. Near zero or "
            + "negative (inverted) means money is expensive today vs the future: levered players "
            + "earn nothing borrowing short to hold assets, so the system runs with no shock "
            + "absorber. Trips when the gap touched below +" + thr.toFixed(2) + "pp in the last 6 months."}
        />
      </div>
      {g.spread_3m10y_now != null && g.spread_3m10y_min_6m != null && (
        <div>
          <div className="relative h-3 w-full overflow-hidden rounded bg-slate-800/70">
            {/* trip zone: everything below the threshold */}
            <div className="absolute inset-y-0 left-0 bg-red-500/25" style={{ width: pos(thr) }} />
            <div className="absolute inset-y-0 w-px bg-red-400/70" style={{ left: pos(thr) }} />
            {/* 6m low (hollow) and current (solid) markers */}
            <div
              className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-sky-300 bg-transparent"
              style={{ left: pos(g.spread_3m10y_min_6m) }}
              title={`6m low ${g.spread_3m10y_min_6m.toFixed(2)}pp`}
            />
            <div
              className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-sky-400"
              style={{ left: pos(g.spread_3m10y_now) }}
              title={`now ${g.spread_3m10y_now.toFixed(2)}pp`}
            />
          </div>
          <div className="mt-0.5 flex justify-between text-[9px] text-slate-600">
            <span>-1.0pp (deep inversion)</span>
            <span className="text-red-400/80">trip &lt; +{thr.toFixed(2)}pp</span>
            <span>+2.0pp (steep)</span>
          </div>
          <p className="mt-1 text-[10px] text-slate-500">
            <span className="text-sky-400">●</span> now ·{" "}
            <span className="text-sky-300">○</span> 6-month low —{" "}
            {g.curve_flat
              ? "the curve condition is MET; a fast-channel red completes the composite."
              : `the 6m low sits ${(g.spread_3m10y_min_6m - thr).toFixed(2)}pp above the trip line — flattening toward it is the thing to watch.`}
          </p>
        </div>
      )}
      <p className="mt-1.5 text-[10px] italic leading-snug text-slate-600">{g.basis}</p>
    </div>
  );
}

// Exposure map: severity says HOW STRESSED each channel is; this says HOW MUCH
// sits behind it. Bars use a sqrt scale so the $1.5T basis book stays legible
// next to the $28T Treasury market. Colors are the channel's live status.
function MassMap({ board }: { board: PinBoardData }) {
  const exp = board.exposure;
  if (!exp) return null;
  const sized = board.channels
    .filter((c) => c.mass_trillions != null)
    .sort((a, b) => (b.mass_trillions ?? 0) - (a.mass_trillions ?? 0));
  if (sized.length === 0) return null;
  const max = Math.sqrt(sized[0].mass_trillions ?? 1);
  return (
    <div className="mb-4 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2.5">
      <div className="mb-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-200">
          Systemic mass map
        </span>
        <span className="text-[11px] text-slate-400">
          stress-bearing exposure now:{" "}
          <span className="font-mono font-bold text-red-400">
            ${exp.red_trillions.toFixed(1)}T red
          </span>{" "}
          ·{" "}
          <span className="font-mono font-bold text-amber-400">
            ${exp.yellow_trillions.toFixed(1)}T yellow
          </span>{" "}
          · of ~${exp.monitored_trillions.toFixed(0)}T monitored
          {exp.unsized.length > 0 && (
            <span className="text-slate-500">
              {" "}(excl. {exp.unsized.join(", ")} — unbounded)
            </span>
          )}
        </span>
      </div>
      <ul className="space-y-1">
        {sized.map((c) => (
          <li key={c.channel_id} className="flex items-center gap-2 text-[10px]"
              title={`${c.mass} — leverage/location: ${c.leverage}`}>
            <span className="w-40 shrink-0 truncate text-slate-400">{c.label}</span>
            <span className="h-2.5 grow overflow-hidden rounded-sm bg-slate-800/70">
              <span
                className="block h-2.5 rounded-sm"
                style={{
                  width: `${(Math.sqrt(c.mass_trillions ?? 0) / max) * 100}%`,
                  backgroundColor: partDotColor(c.status),
                  opacity: c.status === "STALE" ? 0.35 : 0.85,
                }}
              />
            </span>
            <span className="w-14 shrink-0 text-right font-mono text-slate-300">
              ${(c.mass_trillions ?? 0).toFixed(1)}T
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-1.5 text-[10px] italic leading-snug text-slate-600">
        {exp.note} Bar length is √-scaled.
      </p>
    </div>
  );
}

function ChannelCard({ channel, history, recessions, drawdowns }: {
  channel: PinChannel;
  history?: PinHistory["channels"][number];
  recessions?: PinHistory["recessions"];
  drawdowns?: PinHistory["drawdowns"];
}) {
  const [showHistory, setShowHistory] = useState(false);
  return (
    <div className="flex flex-col rounded-lg border border-panelborder bg-slate-900/50 p-3">
      <div className="mb-2 flex items-start justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-200">
          {channel.label}
          {CHANNEL_TIP[channel.channel_id] && (
            <InfoTip term={CHANNEL_TIP[channel.channel_id]} />
          )}
        </span>
        <div className="flex items-center gap-1.5">
          {channel.score != null && (
            <span
              className="rounded px-1.5 py-0.5 font-mono text-[11px] font-bold"
              style={{ color: partDotColor(channel.status) }}
              title="Severity 0-100: piecewise through documented thresholds (50 = yellow line, 80 = red line, 100 = worst historical episode)"
            >
              {channel.score.toFixed(0)}
            </span>
          )}
          <StatusPill status={channel.status} pulse={channel.status === "RED"} />
        </div>
      </div>
      {channel.score != null && (
        <div className="mb-2 h-1 w-full overflow-hidden rounded bg-slate-800">
          <div
            className="h-1 rounded transition-all"
            style={{
              width: `${Math.min(channel.score, 100)}%`,
              backgroundColor: partDotColor(channel.status),
            }}
          />
        </div>
      )}
      <ul className="mb-2 space-y-1.5">
        {channel.parts.map((p, i) => (
          <li key={`${p.label}-${i}`}>
            <div className="flex items-center justify-between gap-2 text-xs">
              <span className="flex min-w-0 items-center gap-1.5 text-slate-300">
                <span
                  className="h-1.5 w-1.5 shrink-0 rounded-full"
                  style={{ backgroundColor: partDotColor(p.status) }}
                />
                <span className="truncate">{p.label}</span>
              </span>
              <span className="shrink-0 font-mono text-slate-100">
                {p.value === null ? "n/a" : formatValue(p.value, p.unit)}
              </span>
            </div>
            {p.detail && (
              <p className="ml-3 mt-0.5 text-[10px] leading-snug text-slate-500">
                {p.detail}
              </p>
            )}
          </li>
        ))}
      </ul>
      {(channel.mass || channel.speed || channel.kill_rate) && (
        <div className="mb-2 flex flex-wrap items-center gap-1.5">
          {channel.mass && <AttrBadge label="mass" value={channel.mass} />}
          {channel.speed && <AttrBadge label="speed" value={channel.speed} />}
          {channel.kill_rate && (
            <AttrBadge label="kill rate" value={channel.kill_rate} />
          )}
          <InfoTip term="pin_attributes" />
        </div>
      )}
      <div className="mt-auto border-t border-panelborder/60 pt-2">
        {channel.basis && (
          <p className="text-[10px] italic leading-snug text-slate-500">
            {channel.basis}
          </p>
        )}
        {channel.certainty && (
          <p className="mt-1 text-[10px] leading-snug text-slate-500">
            {channel.certainty}
          </p>
        )}
        {history && history.series.length > 0 && (
          <button
            type="button"
            onClick={() => setShowHistory((v) => !v)}
            className="mt-2 rounded border border-slate-700 bg-slate-800/60 px-2 py-0.5 text-[10px] text-slate-400 hover:border-slate-500 hover:text-slate-200"
          >
            {showHistory ? "▾ hide history" : "▸ history"}
            {history.episodes.length > 0 &&
              ` (${history.episodes.length} red episode${history.episodes.length === 1 ? "" : "s"})`}
          </button>
        )}
      </div>
      {showHistory && history && (
        <div className="mt-2 border-t border-panelborder/60 pt-2">
          <ChannelHistoryChart
            hist={history}
            recessions={recessions}
            drawdowns={drawdowns}
          />
        </div>
      )}
    </div>
  );
}

function AttrBadge({ label, value }: { label: string; value: string }) {
  return (
    <span
      className="rounded border border-slate-700 bg-slate-800/60 px-1.5 py-0.5 text-[9px] leading-tight text-slate-400"
      title={value}
    >
      <span className="uppercase tracking-wide text-slate-500">{label}</span>{" "}
      <span className="text-slate-300">{value}</span>
    </span>
  );
}

export default function PinBoard() {
  const [board, setBoard] = useState<PinBoardData | null>(null);
  const [history, setHistory] = useState<PinHistory | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .pins()
      .then((b) => alive && setBoard(b))
      .catch((e: unknown) =>
        alive &&
        setError(e instanceof ApiError ? e.message : "failed to load pin board"),
      );
    // hindcast loads independently — the live board never waits on it
    api
      .pinsHistory()
      .then((h) => alive && setHistory(h))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  const title = (
    <>
      Pin board — what could prick the bubble?
      <InfoTip term="pin_board" />
    </>
  );
  const subtitle =
    "The gun is the debt buildup; the pin is the trigger. Nine spark channels, measured and sized.";

  if (error) {
    return (
      <Panel title={title} subtitle={subtitle}>
        <InlineError message={error} />
      </Panel>
    );
  }
  if (!board) {
    return (
      <Panel title={title} subtitle={subtitle}>
        <Loading label="Loading pin board…" />
      </Panel>
    );
  }

  const histByChannel = new Map(
    (history?.channels ?? []).map((h) => [h.channel_id, h]),
  );
  const channelLabels = Object.fromEntries(
    board.channels.map((c) => [c.channel_id, c.label]),
  );

  return (
    <Panel title={title} subtitle={subtitle}>
      <OverallBanner board={board} />
      <AccidentGauge board={board} />
      <MassMap board={board} />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {board.channels.map((c) => (
          <ChannelCard
            key={c.channel_id}
            channel={c}
            history={histByChannel.get(c.channel_id)}
            recessions={history?.recessions}
            drawdowns={history?.drawdowns}
          />
        ))}
      </div>
      {history && history.collective.series.length > 0 && (
        <div className="mt-4 border-t border-panelborder/60 pt-3">
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-200">
            Red hits &amp; damage-window convergence
          </h3>
          <p className="mb-2 text-[11px] leading-snug text-slate-500">
            Every red episode above casts its channel&apos;s documented damage window
            forward. This counts how many are open at once — the convergence view.
          </p>
          {history.confluence && (
            <ConfluenceReadout
              conf={history.confluence}
              channelLabels={channelLabels}
            />
          )}
          <CollectiveHistoryChart history={history} channelLabels={channelLabels} />
          {history.measured_roles && (
            <p className="mt-2 text-[10px] leading-snug text-slate-500">
              {history.measured_roles}
            </p>
          )}
        </div>
      )}
      {board.framing && (
        <p className="mt-4 border-t border-panelborder/60 pt-3 text-[11px] leading-relaxed text-slate-500">
          {board.framing}
        </p>
      )}
    </Panel>
  );
}
