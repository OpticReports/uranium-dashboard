import React, { useEffect, useState } from "react";
import { api } from "./lib/api";
import Heatmap from "./views/Heatmap";
import Watchlist from "./views/Watchlist";
import CatalystCalendar from "./views/CatalystCalendar";
import Movers from "./views/Movers";
import DeepDive from "./views/DeepDive";
import Chat from "./views/Chat";
import CallsLog from "./views/CallsLog";
import Today from "./views/Today";
import Discovery from "./views/Discovery";

const TABS = [
  { id: "today", label: "Today" },
  { id: "heatmap", label: "Sector Heatmap" },
  { id: "watchlist", label: "Watchlist" },
  { id: "discovery", label: "Discovery" },
  { id: "catalysts", label: "Catalyst Calendar" },
  { id: "movers", label: "Movers in Narrative" },
  { id: "calls", label: "Calls Log" },
  { id: "chat", label: "Analyst Chat" },
];

export default function App() {
  const [tab, setTab] = useState("today");
  const [picked, setPicked] = useState(null);
  const [health, setHealth] = useState(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ status: "down" }));
  }, []);

  const pick = (symbol) => setPicked(symbol);

  return (
    <div className="min-h-screen">
      <header className="border-b border-edge bg-panel/60 backdrop-blur sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold">🧬 Genomics Sector Alpha Tracker</h1>
            <p className="text-xs text-gray-400">Forward-looking signal extraction for the genomics universe</p>
          </div>
          <div className="flex items-center gap-3">
            {/* Sibling research tools behind this same login gate */}
            <a href="/canary/" className="text-xs text-gray-400 hover:text-sky-300">🐤 Canary</a>
            <a href="/portfolio-optimizer/" className="text-xs text-gray-400 hover:text-sky-300">⚖️ Portfolio Optimizer</a>
            <a href="/btc/" className="text-xs text-gray-400 hover:text-sky-300">₿ Paper Engine</a>
            <HealthBadge health={health} />
          </div>
        </div>
        <nav className="max-w-7xl mx-auto px-4 flex gap-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => {
                setTab(t.id);
                setPicked(null);
              }}
              className={`px-3 py-2 text-sm border-b-2 ${
                tab === t.id && !picked
                  ? "border-sky-500 text-sky-300"
                  : "border-transparent text-gray-400 hover:text-gray-200"
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6">
        {picked ? (
          <DeepDive symbol={picked} onBack={() => setPicked(null)} />
        ) : (
          <>
            {tab === "today" && <Today onPick={pick} />}
            {tab === "heatmap" && <Heatmap onPick={pick} />}
            {tab === "watchlist" && <Watchlist onPick={pick} />}
            {tab === "discovery" && <Discovery onPick={pick} />}
            {tab === "catalysts" && <CatalystCalendar onPick={pick} />}
            {tab === "movers" && <Movers onPick={pick} />}
            {tab === "calls" && <CallsLog onPick={pick} />}
            {tab === "chat" && <Chat onPick={pick} />}
          </>
        )}
      </main>
    </div>
  );
}

function HealthBadge({ health }) {
  if (!health) return <span className="text-xs text-gray-500">connecting…</span>;
  const ok = health.status === "ok";
  const keys = health.optional_keys || {};
  const active = Object.entries(keys)
    .filter(([, v]) => v)
    .map(([k]) => k);
  return (
    <div className="text-right text-xs">
      <span className={ok ? "text-emerald-400" : "text-rose-400"}>
        ● {ok ? "API online" : "API offline"}
      </span>
      <div className="text-gray-500">
        provider: {health.market_provider || "—"}
        {active.length ? ` · keys: ${active.join(", ")}` : " · free-tier only"}
      </div>
    </div>
  );
}
