import { Fragment, useEffect, useMemo, useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  YAxis,
  Tooltip,
} from "recharts";
import type {
  Categories,
  Metric,
  MetricStatus,
  HistoryPoint,
} from "../lib/api";
import { api } from "../lib/api";
import { Panel, StatusPill, InlineError } from "./ui";
import {
  formatValue,
  formatDelta,
  deltaColor,
  formatPercentile,
  errorMessage,
} from "../lib/format";
import InfoTip from "./InfoTip";

const ALL_STATUSES: MetricStatus[] = [
  "CRITICAL",
  "RED",
  "YELLOW",
  "GREEN",
  "STALE",
];

const STATUS_ORDER: Record<MetricStatus, number> = {
  CRITICAL: 0,
  RED: 1,
  YELLOW: 2,
  GREEN: 3,
  STALE: 4,
};

type SortKey = "label" | "value" | "delta_1d" | "delta_20d" | "percentile" | "status";
type SortDir = "asc" | "desc";

function numOr(v: number | null, fallback: number): number {
  return v === null || Number.isNaN(v) ? fallback : v;
}

function HistorySparkline({ metricId }: { metricId: string }) {
  const [points, setPoints] = useState<HistoryPoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .metricHistory(metricId)
      .then((p) => {
        if (alive) setPoints(p);
      })
      .catch((e) => {
        if (alive) setError(errorMessage(e));
      });
    return () => {
      alive = false;
    };
  }, [metricId]);

  if (error) return <InlineError message={`History: ${error}`} />;
  if (!points) return <p className="text-xs text-slate-500">Loading history…</p>;

  const data = points
    .filter((p) => p.value !== null)
    .map((p) => ({ asof: p.asof, value: p.value as number }));

  if (data.length === 0)
    return <p className="text-xs text-slate-500">No history available.</p>;

  return (
    <ResponsiveContainer width="100%" height={90}>
      <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
        <YAxis hide domain={["auto", "auto"]} />
        <Tooltip
          contentStyle={{
            backgroundColor: "#0f172a",
            border: "1px solid #1e293b",
            borderRadius: 6,
            fontSize: 11,
          }}
          labelFormatter={(l: string | number) => String(l).slice(0, 10)}
          formatter={(v: number | string) => [Number(v).toFixed(3), "value"]}
        />
        <Line
          type="monotone"
          dataKey="value"
          stroke="#38bdf8"
          dot={false}
          strokeWidth={1.4}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

export default function MetricTable({
  categories,
  metrics,
}: {
  categories: Categories;
  metrics: Metric[];
}) {
  const [activeStatuses, setActiveStatuses] = useState<Set<MetricStatus>>(
    new Set(ALL_STATUSES),
  );
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("status");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const toggleStatus = (s: MetricStatus) => {
    setActiveStatuses((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });
  };

  const toggleCategory = (cat: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  const setSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const filtered = useMemo(
    () => metrics.filter((m) => activeStatuses.has(m.status)),
    [metrics, activeStatuses],
  );

  const sortComparator = useMemo(() => {
    const dir = sortDir === "asc" ? 1 : -1;
    return (a: Metric, b: Metric): number => {
      let cmp = 0;
      switch (sortKey) {
        case "label":
          cmp = a.label.localeCompare(b.label);
          break;
        case "status":
          cmp = STATUS_ORDER[a.status] - STATUS_ORDER[b.status];
          break;
        case "value":
          cmp = numOr(a.value, -Infinity) - numOr(b.value, -Infinity);
          break;
        case "delta_1d":
          cmp = numOr(a.delta_1d, -Infinity) - numOr(b.delta_1d, -Infinity);
          break;
        case "delta_20d":
          cmp = numOr(a.delta_20d, -Infinity) - numOr(b.delta_20d, -Infinity);
          break;
        case "percentile":
          cmp =
            numOr(a.percentile, -Infinity) - numOr(b.percentile, -Infinity);
          break;
      }
      return cmp * dir;
    };
  }, [sortKey, sortDir]);

  // Group by category, preserving category map ordering (A..I).
  const catKeys = Object.keys(categories);
  const grouped = useMemo(() => {
    const map = new Map<string, Metric[]>();
    for (const m of filtered) {
      const arr = map.get(m.category) ?? [];
      arr.push(m);
      map.set(m.category, arr);
    }
    for (const arr of map.values()) arr.sort(sortComparator);
    return map;
  }, [filtered, sortComparator]);

  // Categories present but not in the map get shown too (fallback ordering).
  const orderedCats = useMemo(() => {
    const present = new Set(metrics.map((m) => m.category));
    const inMap = catKeys.filter((c) => present.has(c));
    const extras = Array.from(present).filter((c) => !catKeys.includes(c));
    return [...inMap, ...extras];
  }, [catKeys, metrics]);

  return (
    <Panel
      title="Metric Matrix"
      subtitle="Every monitored series, by family, with traffic-light status"
      right={
        <div className="flex flex-wrap gap-1">
          {ALL_STATUSES.map((s) => (
            <button
              key={s}
              onClick={() => toggleStatus(s)}
              className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide transition-opacity ${
                activeStatuses.has(s) ? "opacity-100" : "opacity-30"
              }`}
              style={{
                borderColor: `${statusHex(s)}66`,
                color: statusHex(s),
                backgroundColor: `${statusHex(s)}14`,
              }}
            >
              {s}
            </button>
          ))}
        </div>
      }
    >
      <div className="overflow-x-auto scroll-thin">
        <table className="w-full min-w-[720px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-panelborder text-left text-[11px] uppercase tracking-wide text-slate-500">
              <Th onClick={() => setSort("label")} active={sortKey === "label"} dir={sortDir}>
                Metric
              </Th>
              <Th onClick={() => setSort("value")} active={sortKey === "value"} dir={sortDir} right>
                Value
              </Th>
              <Th onClick={() => setSort("delta_1d")} active={sortKey === "delta_1d"} dir={sortDir} right>
                1d Δ
                <InfoTip term="deltas" />
              </Th>
              <Th onClick={() => setSort("delta_20d")} active={sortKey === "delta_20d"} dir={sortDir} right>
                20d Δ
              </Th>
              <Th onClick={() => setSort("percentile")} active={sortKey === "percentile"} dir={sortDir} right>
                %ile
                <InfoTip term="percentile" />
              </Th>
              <Th onClick={() => setSort("status")} active={sortKey === "status"} dir={sortDir}>
                Status
                <InfoTip term="status_lights" />
              </Th>
              <th className="px-2 py-2 font-semibold">Signal / note</th>
            </tr>
          </thead>
          <tbody>
            {orderedCats.map((cat) => {
              const rows = grouped.get(cat) ?? [];
              if (rows.length === 0) return null;
              const isCollapsed = collapsed.has(cat);
              return (
                <GroupBody
                  key={cat}
                  cat={cat}
                  title={categories[cat] ?? cat}
                  rows={rows}
                  collapsed={isCollapsed}
                  onToggleCat={() => toggleCategory(cat)}
                  expandedRow={expandedRow}
                  onToggleRow={(id) =>
                    setExpandedRow((cur) => (cur === id ? null : id))
                  }
                />
              );
            })}
          </tbody>
        </table>
      </div>
      {filtered.length === 0 && (
        <p className="py-6 text-center text-xs text-slate-500">
          No metrics match the active status filters.
        </p>
      )}
    </Panel>
  );
}

function GroupBody({
  cat,
  title,
  rows,
  collapsed,
  onToggleCat,
  expandedRow,
  onToggleRow,
}: {
  cat: string;
  title: string;
  rows: Metric[];
  collapsed: boolean;
  onToggleCat: () => void;
  expandedRow: string | null;
  onToggleRow: (id: string) => void;
}) {
  return (
    <>
      <tr className="bg-slate-900/60">
        <td colSpan={7} className="px-2 py-1.5">
          <button
            onClick={onToggleCat}
            className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-300 hover:text-white"
          >
            <span className="inline-block w-3 text-slate-500">
              {collapsed ? "▸" : "▾"}
            </span>
            <span className="font-mono text-sky-400">{cat}</span>
            {title}
            <span className="text-slate-600">({rows.length})</span>
          </button>
        </td>
      </tr>
      {!collapsed &&
        rows.map((m) => {
          const expanded = expandedRow === m.metric_id;
          return (
            <Fragment key={m.metric_id}>
              <tr
                onClick={() => onToggleRow(m.metric_id)}
                className="cursor-pointer border-b border-panelborder/60 hover:bg-slate-800/40"
              >
                <td className="px-2 py-2">
                  <div className="flex items-center gap-1.5">
                    <span className="w-3 text-[10px] text-slate-600">
                      {expanded ? "▾" : "▸"}
                    </span>
                    <span className="text-slate-200">
                      {m.label}
                      <InfoTip metricId={m.metric_id} />
                    </span>
                  </div>
                </td>
                <td className="px-2 py-2 text-right font-mono text-slate-100">
                  {formatValue(m.value, m.unit)}
                </td>
                <td
                  className="px-2 py-2 text-right font-mono"
                  style={{ color: deltaColor(m.delta_1d) }}
                >
                  {formatDelta(m.delta_1d, m.unit)}
                </td>
                <td
                  className="px-2 py-2 text-right font-mono"
                  style={{ color: deltaColor(m.delta_20d) }}
                >
                  {formatDelta(m.delta_20d, m.unit)}
                </td>
                <td className="px-2 py-2 text-right font-mono text-slate-400">
                  {formatPercentile(m.percentile)}
                </td>
                <td className="px-2 py-2">
                  <StatusPill status={m.status} pulse={m.status === "CRITICAL"} />
                </td>
                <td className="px-2 py-2 text-xs text-slate-400">{m.note}</td>
              </tr>
              {expanded && (
                <tr className="border-b border-panelborder/60 bg-slate-900/40">
                  <td colSpan={7} className="px-4 py-3">
                    <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr,260px]">
                      <div>
                        <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">
                          History
                        </p>
                        <HistorySparkline metricId={m.metric_id} />
                      </div>
                      <div className="text-xs text-slate-400">
                        <dl className="space-y-1">
                          <Row label="Source series" value={m.source_series || "—"} mono />
                          <Row label="As of" value={m.asof ?? "—"} mono />
                          <Row label="5d Δ" value={formatDelta(m.delta_5d, m.unit)} mono />
                          <Row label="Metric ID" value={m.metric_id} mono />
                        </dl>
                      </div>
                    </div>
                  </td>
                </tr>
              )}
            </Fragment>
          );
        })}
    </>
  );
}

function Row({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-slate-500">{label}</dt>
      <dd className={mono ? "font-mono text-slate-300" : "text-slate-300"}>
        {value}
      </dd>
    </div>
  );
}

function Th({
  children,
  onClick,
  active,
  dir,
  right = false,
}: {
  children: React.ReactNode;
  onClick: () => void;
  active: boolean;
  dir: SortDir;
  right?: boolean;
}) {
  return (
    <th
      onClick={onClick}
      className={`cursor-pointer select-none px-2 py-2 font-semibold hover:text-slate-300 ${
        right ? "text-right" : "text-left"
      } ${active ? "text-sky-400" : ""}`}
    >
      {children}
      {active && <span className="ml-1">{dir === "asc" ? "↑" : "↓"}</span>}
    </th>
  );
}

function statusHex(s: MetricStatus): string {
  return {
    GREEN: "#10b981",
    YELLOW: "#f59e0b",
    RED: "#ef4444",
    CRITICAL: "#dc2626",
    STALE: "#6b7280",
  }[s];
}
