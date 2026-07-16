import { useEffect, useState } from "react";
import { api, ApiError, type PinBoard as PinBoardData, type PinChannel } from "../lib/api";
import { InlineError, Loading, Panel, StatusPill } from "./ui";
import { formatValue, STATUS_COLOR } from "../lib/format";
import InfoTip from "./InfoTip";

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

function ChannelCard({ channel }: { channel: PinChannel }) {
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
      </div>
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

  return (
    <Panel title={title} subtitle={subtitle}>
      <OverallBanner board={board} />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {board.channels.map((c) => (
          <ChannelCard key={c.channel_id} channel={c} />
        ))}
      </div>
      {board.framing && (
        <p className="mt-4 border-t border-panelborder/60 pt-3 text-[11px] leading-relaxed text-slate-500">
          {board.framing}
        </p>
      )}
    </Panel>
  );
}
