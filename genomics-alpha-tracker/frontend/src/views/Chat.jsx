import React, { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";

// Grounded analyst chat. Answers cite the dashboard's real data + live FMP.
const EXAMPLES = [
  "What are your thoughts on MU given its forward P/E? Make the bull and bear case, then a probability analysis on the trade.",
  "Which gene-editing name has the best setup right now, and why?",
  "Walk me through a smart entry on CRSP into its next catalyst.",
  "Compare NTRA and GH on valuation and Alpha Signal.",
];

// Minimal markdown: **bold**, # headings, - bullets, numbered lines.
function render(text) {
  const lines = (text || "").split("\n");
  return lines.map((line, i) => {
    const bold = (s) =>
      s.split(/(\*\*[^*]+\*\*)/g).map((part, j) =>
        part.startsWith("**") && part.endsWith("**") ? (
          <strong key={j} className="text-gray-100">{part.slice(2, -2)}</strong>
        ) : (
          <span key={j}>{part}</span>
        )
      );
    const h = line.match(/^(#{1,4})\s+(.*)/);
    if (h) return <div key={i} className="font-semibold text-sky-300 mt-3 mb-1">{bold(h[2])}</div>;
    if (/^\s*[-*]\s+/.test(line))
      return <div key={i} className="pl-4">• {bold(line.replace(/^\s*[-*]\s+/, ""))}</div>;
    if (/^\s*\d+\.\s+/.test(line))
      return <div key={i} className="pl-1 mt-1">{bold(line)}</div>;
    if (line.trim() === "") return <div key={i} className="h-2" />;
    return <div key={i}>{bold(line)}</div>;
  });
}

// Compact token-usage + prompt-cache savings line. Cache reads bill at ~0.1x, so
// every cached input token would otherwise have cost ~10x — show what that saved.
function usageLine(u) {
  if (!u) return null;
  const k = (n) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`);
  const cached = u.cache_read_input_tokens || 0;
  const fresh = (u.input_tokens || 0) + (u.cache_creation_input_tokens || 0);
  const totalIn = cached + fresh;
  const pct = totalIn ? Math.round((cached / totalIn) * 100) : 0;
  const saved = Math.round(cached * 0.9); // vs. paying full price for those tokens
  const parts = [`${k(totalIn)} in / ${k(u.output_tokens || 0)} out`];
  if (cached > 0) parts.push(`${pct}% cached → ~${k(saved)} tok saved`);
  return <> · {parts.join(" · ")}</>;
}

// Append-only decision journal: freeze this memo next to the name so "what
// did I think at entry" can be answered honestly later (entries are immutable).
function SaveToJournal({ message, question }) {
  const [state, setState] = useState("idle"); // idle | asking | saving | saved | error
  const [symbol, setSymbol] = useState("");

  const save = async (e) => {
    e.preventDefault();
    setState("saving");
    try {
      await api.addJournal({
        symbol: symbol.trim() ? symbol.trim().toUpperCase() : null,
        title: (question || "chat memo").slice(0, 180),
        content: message.content,
        source: "chat",
        model: message.model || null,
      });
      setState("saved");
    } catch (err) {
      setState("error");
    }
  };

  if (state === "saved") return <span className="text-emerald-400 shrink-0">saved to journal ✓</span>;
  if (state === "asking" || state === "saving") {
    return (
      <form onSubmit={save} className="flex items-center gap-1 shrink-0">
        <input
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          placeholder="ticker (opt.)"
          className="bg-panel border border-edge rounded px-1.5 py-0.5 w-20 text-[10px]"
          autoFocus
        />
        <button type="submit" disabled={state === "saving"} className="text-sky-300 hover:underline disabled:opacity-50">
          {state === "saving" ? "…" : "save"}
        </button>
      </form>
    );
  }
  return (
    <button onClick={() => setState("asking")} className="text-sky-400 hover:underline shrink-0">
      {state === "error" ? "retry save" : "save to journal"}
    </button>
  );
}

export default function Chat({ onPick }) {
  const [status, setStatus] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [deep, setDeep] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const endRef = useRef(null);

  useEffect(() => {
    api.chatStatus().then(setStatus).catch(() => setStatus({ enabled: false }));
  }, []);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  const send = async (text) => {
    const msg = (text ?? input).trim();
    if (!msg || busy) return;
    setError(null);
    setInput("");
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setMessages((m) => [...m, { role: "user", content: msg }]);
    setBusy(true);
    try {
      const res = await api.chat({ message: msg, history, deep });
      setMessages((m) => [...m, { role: "assistant", content: res.answer, model: res.model, tools: res.tools_used, usage: res.usage }]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  if (status && !status.enabled) {
    return (
      <div className="bg-panel border border-edge rounded-xl p-6 text-sm text-gray-300">
        <h3 className="font-semibold text-gray-100 mb-2">Analyst chat is off</h3>
        <p>Set <code className="text-sky-300">ANTHROPIC_API_KEY</code> in the backend environment
          (Render → Environment) to enable the grounded chat analyst, then redeploy.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-13rem)]">
      <div className="flex items-center justify-between mb-2 text-sm">
        <div className="text-gray-400">
          Ask about any ticker — answers are grounded in your Alpha data + live valuation.
        </div>
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={deep} onChange={(e) => setDeep(e.target.checked)} />
          <span className={deep ? "text-sky-300" : "text-gray-400"}>
            Deep analysis {status ? `(${deep ? status.model_deep : status.model_default})` : ""}
          </span>
        </label>
      </div>

      <div className="flex-1 overflow-y-auto space-y-3 bg-panel border border-edge rounded-xl p-4">
        {messages.length === 0 && (
          <div className="text-sm text-gray-400">
            <div className="mb-2">Try one of these:</div>
            <div className="space-y-1.5">
              {EXAMPLES.map((e) => (
                <button key={e} onClick={() => send(e)}
                  className="block text-left w-full border border-edge rounded-lg px-3 py-2 hover:bg-ink text-gray-300">
                  {e}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div className={`max-w-[85%] rounded-xl px-4 py-2.5 text-sm leading-relaxed ${
              m.role === "user" ? "bg-sky-700/40 border border-sky-700" : "bg-ink border border-edge"
            }`}>
              {m.role === "assistant" ? render(m.content) : m.content}
              {m.role === "assistant" && (
                <div className="mt-2 pt-2 border-t border-edge/50 text-[10px] text-gray-500 flex items-center justify-between gap-2">
                  <span>
                    {m.tools?.length > 0 && <>data pulled: {m.tools.join(" · ")} · </>}
                    {m.model}
                    {m.usage && usageLine(m.usage)}
                  </span>
                  <SaveToJournal message={m} question={messages[i - 1]?.content} />
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && <div className="text-sm text-gray-500">Analyst is thinking… (pulling data + reasoning)</div>}
        {error && <div className="text-sm text-rose-400">⚠ {error}</div>}
        <div ref={endRef} />
      </div>

      <form onSubmit={(e) => { e.preventDefault(); send(); }} className="mt-3 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about a ticker, a thesis, an entry…"
          className="flex-1 bg-ink border border-edge rounded-lg px-3 py-2.5 text-sm"
        />
        <button disabled={busy || !input.trim()}
          className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 rounded-lg px-5 font-medium">
          {busy ? "…" : "Send"}
        </button>
      </form>
      <p className="text-[11px] text-gray-600 mt-1.5">
        Research, not investment advice. Figures are pulled from your data + FMP; the model is told not to invent numbers.
      </p>
    </div>
  );
}
