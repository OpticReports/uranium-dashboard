import React, { useState } from "react";
import { api } from "../lib/api";

// Add a ticker: symbol + optional name (auto-fetched/validated by the backend)
// + free-form subsector tags. On success the backend kicks an immediate backfill.
export default function AddTicker({ onAdded, knownTags = [] }) {
  const [symbol, setSymbol] = useState("");
  const [name, setName] = useState("");
  const [tags, setTags] = useState([]);
  const [tagInput, setTagInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const addTag = (t) => {
    const v = t.trim().toLowerCase();
    if (v && !tags.includes(v)) setTags([...tags, v]);
    setTagInput("");
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!symbol.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.addTicker({
        symbol: symbol.trim().toUpperCase(),
        name: name.trim() || null, // null => backend validates + auto-fetches
        subsector: tags,
        active: true,
        backfill: true,
      });
      setSymbol("");
      setName("");
      setTags([]);
      onAdded?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="bg-panel border border-edge rounded-xl p-4 space-y-3">
      <div className="flex flex-wrap gap-2 items-center">
        <input
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          placeholder="Symbol (e.g. CRSP)"
          className="bg-ink border border-edge rounded px-3 py-2 w-36 uppercase"
        />
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Company (auto-fetched if blank)"
          className="bg-ink border border-edge rounded px-3 py-2 flex-1 min-w-[200px]"
        />
        <button
          disabled={busy}
          className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 rounded px-4 py-2 font-medium"
        >
          {busy ? "Validating…" : "Add + Backfill"}
        </button>
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        <input
          value={tagInput}
          onChange={(e) => setTagInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              addTag(tagInput);
            }
          }}
          placeholder="Add subsector tag, Enter…"
          className="bg-ink border border-edge rounded px-3 py-1.5 w-56 text-sm"
          list="known-tags"
        />
        <datalist id="known-tags">
          {knownTags.map((t) => (
            <option key={t} value={t} />
          ))}
        </datalist>
        {tags.map((t) => (
          <span
            key={t}
            onClick={() => setTags(tags.filter((x) => x !== t))}
            className="cursor-pointer text-xs bg-sky-700/30 border border-sky-700 rounded-full px-2 py-0.5"
            title="click to remove"
          >
            {t} ✕
          </span>
        ))}
      </div>
      {error && <div className="text-rose-400 text-sm">⚠ {error}</div>}
    </form>
  );
}
