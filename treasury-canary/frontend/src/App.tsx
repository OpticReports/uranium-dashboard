import { useCallback, useEffect, useState } from "react";
import type { Composite, Health, MetricsResponse } from "./lib/api";
import { api } from "./lib/api";
import { errorMessage, formatDateTime } from "./lib/format";
import { InlineError } from "./components/ui";
import StressGauge from "./components/StressGauge";
import MetricTable from "./components/MetricTable";
import ReSteepenAlert from "./components/ReSteepenAlert";
import SahmChart from "./components/SahmChart";
import LaborPanel from "./components/LaborPanel";
import FlightToQuality from "./components/FlightToQuality";
import FlowCompass from "./components/FlowCompass";
import MarginLeverageChart from "./components/MarginLeverageChart";
import RateShockPanel from "./components/RateShockPanel";
import RateShockSimulator from "./components/RateShockSimulator";
import EventFeed from "./components/EventFeed";
import NewsPanel from "./components/NewsPanel";
import LeadingStack from "./components/LeadingStack";
import PinBoard from "./components/PinBoard";
import StatRegimeStrip from "./components/StatRegimeStrip";
import AlertBeacon from "./components/AlertBeacon";
import RateEnsemble from "./components/RateEnsemble";
import PlaybookTab from "./components/PlaybookTab";
import SeverityTab from "./components/SeverityTab";
import TrackRecordTab from "./components/TrackRecordTab";

const POLL_MS = 60_000;

type Tab = "monitor" | "playbook" | "severity" | "track";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "monitor", label: "Monitor" },
  { id: "playbook", label: "Playbook" },
  { id: "severity", label: "Severity" },
  { id: "track", label: "Track record" },
];

export default function App() {
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [composite, setComposite] = useState<Composite | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [metricsError, setMetricsError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [bannerDismissed, setBannerDismissed] = useState(false);
  const [tab, setTab] = useState<Tab>("monitor");

  const loadCore = useCallback(async () => {
    try {
      const [m, c] = await Promise.all([api.metrics(), api.composite()]);
      setMetrics(m);
      setComposite(c);
      setMetricsError(null);
      setLastRefresh(new Date().toISOString());
    } catch (e) {
      setMetricsError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    void loadCore();
    api.health().then(setHealth).catch(() => setHealth(null));
    const id = window.setInterval(() => void loadCore(), POLL_MS);
    return () => window.clearInterval(id);
  }, [loadCore]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await api.refresh();
    } catch {
      // Refresh trigger may be best-effort; still refetch below.
    }
    await loadCore();
    api.health().then(setHealth).catch(() => undefined);
    setRefreshing(false);
  }, [loadCore]);

  const showFredBanner =
    health !== null && !health.fred_key_present && !bannerDismissed;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200">
      <div className="mx-auto max-w-7xl px-4 py-6">
        {/* Header */}
        <header className="mb-5 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-slate-100 sm:text-2xl">
              🐤 Treasury Market Health Monitor — The Canary
            </h1>
            <p className="mt-0.5 text-xs text-slate-500">
              Institutional-grade fixed-income stress surveillance
            </p>
          </div>
          <div className="flex items-center gap-3">
            <AlertBeacon composite={composite} />
            <HealthBadge health={health} lastRefresh={lastRefresh} />
            <button
              onClick={() => void handleRefresh()}
              disabled={refreshing}
              className="rounded border border-sky-500/60 bg-sky-500/15 px-3 py-1.5 text-xs font-semibold text-sky-300 transition-colors hover:bg-sky-500/25 disabled:opacity-50"
            >
              {refreshing ? "Refreshing…" : "↻ Refresh"}
            </button>
          </div>
        </header>

        {/* Tab bar (segmented control) */}
        <div className="mb-4 inline-flex overflow-hidden rounded-lg border border-panelborder">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`border-r px-4 py-1.5 text-xs font-semibold transition-colors last:border-r-0 ${
                tab === t.id
                  ? "border-sky-500 bg-sky-500/10 text-sky-300"
                  : "border-panelborder text-slate-400 hover:bg-slate-800/50 hover:text-slate-200"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {showFredBanner && (
          <div className="mb-4 flex items-start justify-between gap-3 rounded-lg border border-canary-yellow/50 bg-canary-yellow/12 px-4 py-2.5">
            <p className="text-xs text-amber-200">
              <span className="font-semibold">FRED_API_KEY not set</span> — curve
              / rates / recession metrics show STALE. Keyless sources still
              populate.
            </p>
            <button
              onClick={() => setBannerDismissed(true)}
              className="text-xs text-amber-300 hover:text-amber-100"
              aria-label="Dismiss"
            >
              ✕
            </button>
          </div>
        )}

        {/* Monitor tab stays mounted (hidden) so polling/state persist across tabs. */}
        <div className={tab === "monitor" ? "" : "hidden"}>
        {metricsError && (
          <div className="mb-4">
            <InlineError message={`Failed to load metrics: ${metricsError}`} />
          </div>
        )}

        <div className="flex flex-col gap-5">
          <StressGauge composite={composite} />

          <RateEnsemble />

          <ReSteepenAlert />

          <SahmChart />

          {metrics ? (
            <LeadingStack metrics={metrics.metrics} />
          ) : (
            !metricsError && (
              <div className="rounded-lg border border-panelborder bg-panel/60 p-6 text-center text-xs text-slate-500">
                Loading leading stack…
              </div>
            )
          )}

          {metrics ? (
            <MetricTable
              categories={metrics.categories}
              metrics={metrics.metrics}
            />
          ) : (
            !metricsError && (
              <div className="rounded-lg border border-panelborder bg-panel/60 p-6 text-center text-xs text-slate-500">
                Loading metric matrix…
              </div>
            )
          )}

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            {metrics ? (
              <FlightToQuality metrics={metrics.metrics} />
            ) : (
              <div className="rounded-lg border border-panelborder bg-panel/60 p-6 text-center text-xs text-slate-500">
                Loading…
              </div>
            )}
            {metrics ? (
              <LaborPanel metrics={metrics.metrics} />
            ) : (
              <div className="rounded-lg border border-panelborder bg-panel/60 p-6 text-center text-xs text-slate-500">
                Loading…
              </div>
            )}
          </div>

          <FlowCompass />

          <RateShockPanel />

          <MarginLeverageChart />

          <PinBoard />
          <StatRegimeStrip />

          <RateShockSimulator />

          <div id="event-feed">
            <EventFeed />
          </div>

          <NewsPanel />
        </div>
        </div>

        {tab === "playbook" && <PlaybookTab />}
        {tab === "severity" && <SeverityTab />}
        {tab === "track" && <TrackRecordTab />}

        <footer className="mt-8 border-t border-panelborder pt-4 text-center text-[10px] text-slate-600">
          Association, not causation. Signals are decision inputs, not
          recommendations. Times shown in America/Puerto_Rico.
        </footer>
      </div>
    </div>
  );
}

function HealthBadge({
  health,
  lastRefresh,
}: {
  health: Health | null;
  lastRefresh: string | null;
}) {
  if (!health) {
    return (
      <div className="rounded border border-panelborder bg-slate-900/50 px-3 py-1.5 text-[10px] text-slate-500">
        health: unknown
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2 rounded border border-panelborder bg-slate-900/50 px-3 py-1.5 text-[10px]">
      <Dot ok={health.fred_key_present} label="FRED" />
      <Dot ok={health.scheduler} label="sched" />
      <span className="text-slate-500">
        last:{" "}
        <span className="font-mono text-slate-400">
          {lastRefresh ? formatDateTime(lastRefresh) : "—"}
        </span>
      </span>
    </div>
  );
}

function Dot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: ok ? "#10b981" : "#6b7280" }}
      />
      <span className="text-slate-400">{label}</span>
    </span>
  );
}
