import type { Metric } from "../lib/api";
import { Panel, StatusPill } from "./ui";
import { formatValue } from "../lib/format";
import InfoTip from "./InfoTip";

const SAHM_ID = "labor.sahm";
const CLAIMS_ID = "labor.claims_yoy";
const UNRATE_ID = "labor.unrate";

function findMetric(metrics: Metric[], id: string): Metric | undefined {
  return metrics.find((m) => m.metric_id === id);
}

export default function LaborPanel({ metrics }: { metrics: Metric[] }) {
  const sahm = findMetric(metrics, SAHM_ID);
  const claims = findMetric(metrics, CLAIMS_ID);
  const unrate = findMetric(metrics, UNRATE_ID);

  const sahmValue = sahm?.value ?? null;
  const sahmTriggered =
    sahmValue !== null && !Number.isNaN(sahmValue) && sahmValue >= 0.5;

  const hasAny = sahm || claims || unrate;

  return (
    <Panel
      title="Labor Market"
      subtitle="Sahm Rule leads; claims and unemployment confirm"
    >
      {sahmTriggered && (
        <div className="mb-3 animate-pulse rounded-lg border border-canary-critical bg-canary-critical/15 px-4 py-2.5">
          <p className="text-sm font-bold uppercase tracking-wide text-red-300">
            ⚠ SAHM TRIGGERED — recession onset signal
          </p>
          <p className="mt-0.5 text-xs text-red-200/90">
            The Sahm Rule recession indicator has crossed its 0.50pp trigger.
          </p>
        </div>
      )}

      {!hasAny ? (
        <p className="py-6 text-center text-xs text-slate-500">
          No labor metrics available — a FRED_API_KEY may be required.
        </p>
      ) : (
        <div className="flex flex-col gap-2.5">
          <LaborRow metric={sahm} label="Sahm Rule" fallbackUnit="pp" />
          <LaborRow
            metric={claims}
            label="Initial claims YoY"
            fallbackUnit="%"
          />
          <LaborRow
            metric={unrate}
            label="Unemployment rate"
            fallbackUnit="%"
            tag="lagging · context"
          />
        </div>
      )}
    </Panel>
  );
}

function LaborRow({
  metric,
  label,
  fallbackUnit,
  tag,
}: {
  metric: Metric | undefined;
  label: string;
  fallbackUnit: string;
  tag?: string;
}) {
  // The unemployment rate carries informational: true — surface it explicitly.
  const showTag = tag ?? (metric?.informational ? "lagging · context" : undefined);
  return (
    <div className="rounded border border-panelborder bg-slate-900/40 px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-[11px] uppercase tracking-wide text-slate-400">
            {label}
            {metric && <InfoTip metricId={metric.metric_id} />}
          </p>
          {showTag && (
            <span className="rounded-full border border-slate-600/60 bg-slate-700/30 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-slate-400">
              {showTag}
            </span>
          )}
        </div>
        {metric && <StatusPill status={metric.status} />}
      </div>
      <div className="mt-1 flex items-baseline gap-2">
        <p className="font-mono text-lg text-slate-100">
          {metric
            ? formatValue(metric.value, metric.unit || fallbackUnit)
            : "n/a"}
        </p>
      </div>
      {metric?.note && (
        <p className="mt-0.5 text-[10px] leading-snug text-slate-500">
          {metric.note}
        </p>
      )}
    </div>
  );
}
