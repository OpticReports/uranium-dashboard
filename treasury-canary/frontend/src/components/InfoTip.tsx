import { useState } from "react";
import { createPortal } from "react-dom";
import { GLOSSARY, glossaryFor, type GlossaryEntry } from "../lib/glossary";

// A small "?" badge that reveals an in-depth explanation card on hover/click.
// The card is portaled to <body> with fixed positioning so table/panel overflow
// never clips it. Pass either a glossary `term` key, a `metricId` (uses family
// fallbacks), or a full `entry`.
export default function InfoTip({
  term,
  metricId,
  entry,
}: {
  term?: string;
  metricId?: string;
  entry?: GlossaryEntry;
}) {
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const g = entry ?? (term ? GLOSSARY[term] : undefined) ?? (metricId ? glossaryFor(metricId) : undefined);
  if (!g) return null;

  const CARD_W = 320;
  const show = (e: React.MouseEvent<HTMLButtonElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const x = Math.max(8, Math.min(r.left, window.innerWidth - CARD_W - 12));
    // Flip above the badge if there's no room below.
    const below = r.bottom + 6;
    const y = below + 260 > window.innerHeight ? Math.max(8, r.top - 6 - 260) : below;
    setPos({ x, y });
  };

  return (
    <span className="relative inline-block align-middle">
      <button
        type="button"
        onMouseEnter={show}
        onMouseLeave={() => setPos(null)}
        onClick={(e) => {
          e.stopPropagation();
          if (pos) setPos(null);
          else show(e);
        }}
        className="ml-1 h-4 w-4 inline-flex items-center justify-center rounded-full border border-slate-600 text-[10px] leading-none text-slate-400 hover:text-sky-300 hover:border-sky-500 cursor-help"
        aria-label={`What is ${g.title}?`}
      >
        ?
      </button>
      {pos &&
        createPortal(
          <div
            style={{ position: "fixed", left: pos.x, top: pos.y, width: CARD_W }}
            className="z-[100] rounded-lg border border-slate-700 bg-slate-900 p-3 text-left shadow-2xl text-xs font-normal normal-case tracking-normal leading-relaxed max-h-[22rem] overflow-y-auto"
          >
            <div className="mb-1 font-semibold text-slate-100">{g.title}</div>
            <div className="text-slate-300">{g.what}</div>
            {g.calc && (
              <div className="mt-1.5 text-slate-400">
                <span className="font-semibold text-slate-300">How it's calculated: </span>
                {g.calc}
              </div>
            )}
            {g.read && (
              <div className="mt-1.5 text-slate-400">
                <span className="font-semibold text-slate-300">How to read it: </span>
                {g.read}
              </div>
            )}
            {g.caveat && (
              <div className="mt-1.5 text-amber-400/90">
                <span className="font-semibold">Caveat: </span>
                {g.caveat}
              </div>
            )}
          </div>,
          document.body,
        )}
    </span>
  );
}
