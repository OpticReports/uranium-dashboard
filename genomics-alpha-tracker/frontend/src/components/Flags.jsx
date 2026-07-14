import React from "react";
import { eventLabel, FLAG_LABELS, severityColor } from "../lib/format";

// Renders evidence-linked flags. Evidence is shown inline so each flag is
// auditable (which catalysts / revisions / posts drove it).
export default function Flags({ flags = [], compact = false }) {
  if (!flags.length)
    return <div className="text-sm text-gray-500">No active flags.</div>;
  return (
    <div className="space-y-2">
      {flags.map((f, i) => (
        <div
          key={f.id ?? i}
          className={`border rounded-lg p-2 ${severityColor[f.severity] || severityColor.info}`}
        >
          <div className="flex items-center justify-between">
            <span className="font-medium text-sm">
              {FLAG_LABELS[f.flag_type] || f.flag_type}
            </span>
            {f.symbol && <span className="text-xs opacity-70">{f.symbol}</span>}
          </div>
          <div className="text-xs opacity-90">{f.message}</div>
          {!compact && f.evidence && <Evidence ev={f.evidence} />}
        </div>
      ))}
    </div>
  );
}

function Evidence({ ev }) {
  const cats = ev.catalysts || [];
  const revs = ev.revisions || [];
  return (
    <div className="mt-1 text-[11px] opacity-80 space-y-0.5">
      {cats.map((c, i) => (
        <div key={`c${i}`}>
          •{" "}
          {c.url ? (
            <a className="underline" href={c.url} target="_blank" rel="noreferrer">
              {eventLabel(c.event_type)} · {c.date}
            </a>
          ) : (
            <span>
              {eventLabel(c.event_type)} · {c.date}
            </span>
          )}{" "}
          (impact {c.impact?.toFixed?.(2)}, in {c.days_until}d)
        </div>
      ))}
      {revs.map((r, i) => (
        <div key={`r${i}`}>
          • {r.firm || "analyst"} {r.metric} {r.direction > 0 ? "▲" : r.direction < 0 ? "▼" : "•"}{" "}
          {r.date}
        </div>
      ))}
    </div>
  );
}
