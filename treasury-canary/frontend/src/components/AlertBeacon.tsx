import { useEffect, useState } from "react";
import type { CanaryEvent, Composite, PinBoard } from "../lib/api";
import { api } from "../lib/api";
import InfoTip from "./InfoTip";

// Compact header beacon summarizing the worst active warning level across the
// composite, pin board, and high-severity alert stream. Click scrolls to the
// event feed.

const POLL_MS = 60_000;

type Level = "RED" | "AMBER" | "GREEN" | "UNKNOWN";

const LEVEL_STYLE: Record<Level, { dot: string; text: string; border: string }> = {
  RED: { dot: "#dc2626", text: "text-red-400", border: "border-red-600/60" },
  AMBER: { dot: "#f59e0b", text: "text-amber-400", border: "border-amber-600/60" },
  GREEN: { dot: "#10b981", text: "text-emerald-400", border: "border-emerald-700/60" },
  UNKNOWN: { dot: "#6b7280", text: "text-slate-500", border: "border-panelborder" },
};

export default function AlertBeacon({
  composite,
}: {
  composite: Composite | null;
}) {
  const [alerts, setAlerts] = useState<CanaryEvent[] | null>(null);
  const [pins, setPins] = useState<PinBoard | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () => {
      api
        .alerts()
        .then((a) => alive && setAlerts(a))
        .catch(() => alive && setAlerts(null));
      api
        .pins()
        .then((p) => alive && setPins(p))
        .catch(() => alive && setPins(null));
    };
    load();
    const id = window.setInterval(load, POLL_MS);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  const nCritAlerts = alerts?.filter((a) => a.severity === "CRITICAL").length ?? 0;
  const nRedAlerts = alerts?.filter((a) => a.severity === "RED").length ?? 0;

  let level: Level;
  if (!composite && !pins && !alerts) {
    level = "UNKNOWN";
  } else if (
    (composite?.n_critical ?? 0) > 0 ||
    composite?.band === "SEVERE" ||
    pins?.overall === "RED" ||
    nCritAlerts > 0
  ) {
    level = "RED";
  } else if (
    (composite?.n_red ?? 0) > 0 ||
    composite?.band === "HIGH" ||
    pins?.overall === "YELLOW" ||
    nRedAlerts > 0
  ) {
    level = "AMBER";
  } else {
    level = "GREEN";
  }

  // Count ONE population, not two: the badge previously summed currently-RED
  // metric tiles PLUS logged alert events — overlapping facts counted twice
  // (user report: badge said 12, feed showed 7). The live metric grid is the
  // source of truth for "how many things are red right now"; the feed is the
  // transition LOG (resets on redeploy). Fall back to event counts only when
  // the composite hasn't loaded.
  const n = composite
    ? (composite.n_critical ?? 0) + (composite.n_red ?? 0)
    : nCritAlerts + nRedAlerts;
  const label =
    level === "UNKNOWN"
      ? "NO DATA"
      : level === "GREEN"
        ? "ALL CLEAR"
        : level === "AMBER"
          ? `${n} WARNING${n === 1 ? "" : "S"}`
          : `${n} ALERT${n === 1 ? "" : "S"}`;

  const s = LEVEL_STYLE[level];
  const pulse = level === "RED" || level === "AMBER";

  // Div, not <button>: InfoTip renders its own button and nesting is invalid.
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() =>
        document
          .getElementById("event-feed")
          ?.scrollIntoView({ behavior: "smooth" })
      }
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          document
            .getElementById("event-feed")
            ?.scrollIntoView({ behavior: "smooth" });
        }
      }}
      className={`flex cursor-pointer items-center gap-2 rounded border bg-slate-900/50 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wide transition-colors hover:bg-slate-800/60 ${s.border} ${s.text}`}
      title="Currently-RED metrics on the board (live state). The event feed below logs when each went red — it resets on redeploys, so its row count can be lower."
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${pulse ? "animate-pulse" : ""}`}
        style={{ backgroundColor: s.dot }}
      />
      {label}
      <InfoTip term="alert_beacon" />
    </div>
  );
}
