import { useEffect, useMemo, useState } from "react";
import type { CanaryEvent } from "../lib/api";
import { api } from "../lib/api";
import { Panel, InlineError, Loading } from "./ui";
import { SEVERITY_COLOR, formatDateTime, errorMessage } from "../lib/format";

function sortByAsofDesc(a: CanaryEvent, b: CanaryEvent): number {
  return new Date(b.asof).getTime() - new Date(a.asof).getTime();
}

function EventItem({ ev, pinned }: { ev: CanaryEvent; pinned?: boolean }) {
  const color = SEVERITY_COLOR[ev.severity] ?? "#6b7280";
  const pulse = ev.severity === "CRITICAL";
  return (
    <li
      className={`rounded border px-3 py-2 ${pinned ? "bg-slate-900/70" : "bg-slate-900/30"}`}
      style={{ borderColor: `${color}44` }}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${pulse ? "animate-pulse" : ""}`}
            style={{ backgroundColor: color }}
          />
          <span
            className="text-[10px] font-semibold uppercase tracking-wide"
            style={{ color }}
          >
            {ev.severity}
          </span>
          <span className="font-mono text-[11px] text-slate-400">{ev.type}</span>
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
    return () => {
      alive = false;
    };
  }, []);

  const pinnedAlerts = useMemo(
    () =>
      [...alerts]
        .filter((a) => a.severity === "RED" || a.severity === "CRITICAL")
        .sort(sortByAsofDesc),
    [alerts],
  );

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

  return (
    <Panel
      title="Event & Alert Feed"
      subtitle="Machine-generated signals, newest first. Active alerts = RED transitions logged since the last deploy; the metric grid above is the live source of truth"
    >
      {alertError && (
        <div className="mb-2">
          <InlineError message={`Alerts: ${alertError}`} />
        </div>
      )}

      {pinnedAlerts.length > 0 && (
        <div className="mb-3">
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-red-400">
            Active alerts
          </p>
          <ul className="flex flex-col gap-2">
            {pinnedAlerts.map((a) => (
              <EventItem key={`alert-${a.id}`} ev={a} pinned />
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
            <EventItem key={e.id} ev={e} />
          ))}
        </ul>
      )}
    </Panel>
  );
}
