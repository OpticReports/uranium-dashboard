import type { ReactNode } from "react";
import type { MetricStatus } from "../lib/api";
import { STATUS_COLOR } from "../lib/format";

export function Panel({
  title,
  subtitle,
  right,
  children,
  className = "",
}: {
  title?: ReactNode;
  subtitle?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-lg border border-panelborder bg-panel/60 backdrop-blur ${className}`}
    >
      {(title || right) && (
        <header className="flex items-start justify-between gap-3 border-b border-panelborder px-4 py-3">
          <div>
            {title && (
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-200">
                {title}
              </h2>
            )}
            {subtitle && (
              <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>
            )}
          </div>
          {right}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function StatusPill({
  status,
  pulse = false,
}: {
  status: MetricStatus;
  pulse?: boolean;
}) {
  const color = STATUS_COLOR[status];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
      style={{ borderColor: `${color}55`, color, backgroundColor: `${color}14` }}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          pulse && (status === "CRITICAL" || status === "RED")
            ? "animate-pulse"
            : ""
        }`}
        style={{ backgroundColor: color }}
      />
      {status}
    </span>
  );
}

export function InlineError({ message }: { message: string }) {
  return (
    <div className="rounded border border-canary-red/40 bg-canary-red/10 px-3 py-2 text-xs text-red-300">
      <span className="font-semibold">Error: </span>
      {message}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-4 text-xs text-slate-500">
      <span className="h-2 w-2 animate-pulse rounded-full bg-slate-500" />
      {label}
    </div>
  );
}
