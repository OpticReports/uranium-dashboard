import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { GLOSSARY, glossaryFor, type GlossaryEntry } from "../lib/glossary";

// A small "?" badge that reveals an in-depth explanation card on hover/click.
// The card is portaled to <body> with fixed positioning so table/panel overflow
// never clips it. Long entries scroll: the card stays open while the pointer is
// over it (a short close delay bridges the badge->card gap), its height is
// capped to the viewport space on the side it opens toward, and clicking the
// badge pins it open (Escape / outside click dismisses). Pass either a glossary
// `term` key, a `metricId` (uses family fallbacks), or a full `entry`.
interface CardPos {
  x: number;
  top?: number;
  bottom?: number;
  maxH: number;
}

const CARD_W = 320;
const CARD_MAX_H = 352; // 22rem

export default function InfoTip({
  term,
  metricId,
  entry,
}: {
  term?: string;
  metricId?: string;
  entry?: GlossaryEntry;
}) {
  const [pos, setPos] = useState<CardPos | null>(null);
  const [pinned, setPinned] = useState(false);
  const closeTimer = useRef<number | null>(null);
  const btnRef = useRef<HTMLButtonElement | null>(null);
  const cardRef = useRef<HTMLDivElement | null>(null);

  const cancelClose = () => {
    if (closeTimer.current !== null) {
      window.clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  };

  // Pinned cards close on outside click or Escape.
  useEffect(() => {
    if (!pinned) return;
    const onDown = (ev: MouseEvent) => {
      const t = ev.target as Node;
      if (cardRef.current?.contains(t) || btnRef.current?.contains(t)) return;
      setPinned(false);
      setPos(null);
    };
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") {
        setPinned(false);
        setPos(null);
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [pinned]);

  useEffect(() => cancelClose, []);

  const g =
    entry ??
    (term ? GLOSSARY[term] : undefined) ??
    (metricId ? glossaryFor(metricId) : undefined);
  if (!g) return null;

  const show = () => {
    cancelClose();
    const r = btnRef.current?.getBoundingClientRect();
    if (!r) return;
    const x = Math.max(8, Math.min(r.left, window.innerWidth - CARD_W - 12));
    const spaceBelow = window.innerHeight - r.bottom - 18;
    const spaceAbove = r.top - 18;
    // Open toward the roomier side; cap height to that space so the card
    // always fits on screen and its own scrollbar handles the rest.
    if (spaceBelow >= 220 || spaceBelow >= spaceAbove) {
      setPos({ x, top: r.bottom + 6, maxH: Math.min(CARD_MAX_H, Math.max(140, spaceBelow)) });
    } else {
      setPos({
        x,
        bottom: window.innerHeight - r.top + 6,
        maxH: Math.min(CARD_MAX_H, Math.max(140, spaceAbove)),
      });
    }
  };

  const scheduleClose = () => {
    if (pinned) return;
    cancelClose();
    closeTimer.current = window.setTimeout(() => setPos(null), 250);
  };

  return (
    <span className="relative inline-block align-middle">
      <button
        ref={btnRef}
        type="button"
        onMouseEnter={show}
        onMouseLeave={scheduleClose}
        onClick={(e) => {
          e.stopPropagation();
          if (pinned) {
            setPinned(false);
            setPos(null);
          } else {
            show();
            setPinned(true);
          }
        }}
        className="ml-1 h-4 w-4 inline-flex items-center justify-center rounded-full border border-slate-600 text-[10px] leading-none text-slate-400 hover:text-sky-300 hover:border-sky-500 cursor-help"
        aria-label={`What is ${g.title}?`}
      >
        ?
      </button>
      {pos &&
        createPortal(
          <div
            ref={cardRef}
            onMouseEnter={cancelClose}
            onMouseLeave={scheduleClose}
            style={{
              position: "fixed",
              left: pos.x,
              top: pos.top,
              bottom: pos.bottom,
              width: CARD_W,
              maxHeight: pos.maxH,
            }}
            className="z-[100] rounded-lg border border-slate-700 bg-slate-900 p-3 text-left shadow-2xl text-xs font-normal normal-case tracking-normal leading-relaxed overflow-y-auto overscroll-contain"
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
            {g.read2 && (
              <div className="mt-1.5 text-slate-400">{g.read2}</div>
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
