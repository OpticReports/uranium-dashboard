import { useEffect, useMemo, useState } from "react";
import type { CanaryEvent, MetricStatus } from "../lib/api";
import { api } from "../lib/api";
import { Panel, InlineError, Loading } from "./ui";
import { SEVERITY_COLOR, formatDateTime, errorMessage } from "../lib/format";

function sortByAsofDesc(a: CanaryEvent, b: CanaryEvent): number {
  return new Date(b.asof).getTime() - new Date(a.asof).getTime();
}

// metric_red events carry their metric id in the type ("metric_red:<id>") and
// in detail.metric_id; other event types return null.
function metricIdOf(ev: CanaryEvent): string | null {
  if (ev.type.startsWith("metric_red:")) return ev.type.slice("metric_red:".length);
  const id = ev.detail?.metric_id;
  return typeof id === "string" ? id : null;
}

function EventItem({
  ev,
  pinned,
  recoveredStatus,
}: {
  ev: CanaryEvent;
  pinned?: boolean;
  recoveredStatus?: MetricStatus | null;
}) {
  const color = SEVERITY_COLOR[ev.severity] ?? "#6b7280";
  const pulse = ev.severity === "CRITICAL" && !recoveredStatus;
  return (
    <li
      className={`rounded border px-3 py-2 ${pinned ? "bg-slate-900/70" : "bg-slate-900/30"} ${recoveredStatus ? "opacity-45" : ""}`}
      style={{ borderColor: recoveredStatus ? "#47556944" : `${color}44` }}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${pulse ? "animate-pulse" : ""}`}
            style={{ backgroundColor: recoveredStatus ? "#64748b" : color }}
          />
          <span
            className="text-[10px] font-semibold uppercase tracking-wide"
            style={{ color: recoveredStatus ? "#94a3b8" : color }}
          >
            {ev.severity}
          </span>
          <span className="font-mono text-[11px] text-slate-400">{ev.type}</span>
          {recoveredStatus && (
            <span className="rounded bg-slate-700/60 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide text-slate-400">
              recovered — now {recoveredStatus}
            </span>
          )}
        </div>
        <span className="font-mono text-[10px] text-slate-500">
          {formatDateTime(ev.asof)}
        </span>
      </div>
      <p className="mt-1 text-xs text-slate-300">{ev.rationale}</p>
    </li>
  );
}

export default function EventFeed() {
  const [events, setEvents] = useState<CanaryEvent[] | null>(null);
  const [alerts, setAlerts] = useState<CanaryEvent[]>([]);
  const [liveStatus, setLiveStatus] = useState<Map<string, MetricStatus> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [alertError, setAlertError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .events(100)
      .then((e) => {
        if (alive) setEvents(e);
      })
      .catch((e) => {
        if (alive) setError(errorMessage(e));
      });
    api
      .alerts()
      .then((a) => {
        if (alive) setAlerts(a);
      })
      .catch((e) => {
        if (alive) setAlertError(errorMessage(e));
      });
    api
      .metrics()
      .then((m) => {
        if (alive)
          setLiveStatus(new Map(m.metrics.map((x) => [x.metric_id, x.status])));
      })
      .catch(() => {
        // No live grid -> can't tell recovered from active; show everything undimmed.
        if (alive) setLiveStatus(null);
      });
    return () => {
      alive = false;
    };
  }, []);

  // A metric_red entry is "recovered" only when the live grid confirms the
  // metric is now GREEN/YELLOW; unknown or STALE stays undimmed.
  const recoveredStatusOf = (ev: CanaryEvent): MetricStatus | null => {
    const id = metricIdOf(ev);
    if (!id || !liveStatus) return null;
    const cur = liveStatus.get(id);
    return cur === "GREEN" || cur === "YELLOW" ? cur : null;
  };

  // One row per metric: a metric that flipped RED, recovered, then flipped again
  // logged two events, and showing both made the pinned count disagree with the
  // header badge (which counts currently-RED metrics). Keep the newest
  // transition per metric; superseded ones fall through to the log below.
  const pinnedAlerts = useMemo(() => {
    const sorted = [...alerts]
      .filter((a) => a.severity === "RED" || a.severity === "CRITICAL")
      .sort(sortByAsofDesc);
    const seen = new Set<string>();
    return sorted.filter((a) => {
      const id = metricIdOf(a);
      if (!id) return true;
      if (seen.has(id)) return false;
      seen.add(id);
      return true;
    });
  }, [alerts]);

  const pinnedIds = useMemo(
    () => new Set(pinnedAlerts.map((a) => a.id)),
    [pinnedAlerts],
  );

  const feed = useMemo(
    () =>
      (events ?? [])
        .filter((e) => !pinnedIds.has(e.id))
        .sort(sortByAsofDesc),
    [events, pinnedIds],
  );

  const nRecovered = useMemo(
    () => pinnedAlerts.filter((a) => recoveredStatusOf(a) !== null).length,
    [pinnedAlerts, liveStatus],
  );

  return (
    <Panel
      title="Event & Alert Feed"
      subtitle="Machine-generated signals, newest first. This is a transition LOG, not live state — entries stay after a metric recovers (dimmed) and it resets on redeploy. The metric grid above is the live source of truth."
    >
      {alertError && (
        <div className="mb-2">
          <InlineError message={`Alerts: ${alertError}`} />
        </div>
      )}

      {pinnedAlerts.length > 0 && (
        <div className="mb-3">
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-red-400">
            Recent RED transitions
            {nRecovered > 0 && (
              <span className="ml-1.5 font-normal normal-case tracking-normal text-slate-500">
                ({pinnedAlerts.length - nRecovered} still red · {nRecovered} recovered)
              </span>
            )}
          </p>
          <ul className="flex flex-col gap-2">
            {pinnedAlerts.map((a) => (
              <EventItem
                key={`alert-${a.id}`}
                ev={a}
                pinned
                recoveredStatus={recoveredStatusOf(a)}
              />
            ))}
          </ul>
        </div>
      )}

      {error ? (
        <InlineError message={error} />
      ) : events === null ? (
        <Loading label="Loading events…" />
      ) : feed.length === 0 && pinnedAlerts.length === 0 ? (
        <p className="py-4 text-center text-xs text-slate-500">
          No events recorded.
        </p>
      ) : (
        <ul className="flex max-h-[420px] flex-col gap-2 overflow-y-auto scroll-thin pr-1">
          {feed.map((e) => (
            <EventItem key={e.id} ev={e} recoveredStatus={recoveredStatusOf(e)} />
          ))}
        </ul>
      )}
    </Panel>
  );
}
