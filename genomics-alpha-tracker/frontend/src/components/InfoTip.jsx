import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { GLOSSARY } from "../lib/glossary";

// A small "?" badge that shows a definition card on hover/click. The card is
// portaled to <body> with fixed positioning so it never gets clipped by table
// or container overflow. Long entries scroll: the card stays open while the
// pointer is over it (a short close delay bridges the badge->card gap), its
// height is capped to the viewport space on the side it opens toward, and
// clicking the badge pins it open (Escape / outside click dismisses).
const CARD_W = 280;
const CARD_MAX_H = 352;

export default function InfoTip({ term, content }) {
  const [pos, setPos] = useState(null);
  const [pinned, setPinned] = useState(false);
  const closeTimer = useRef(null);
  const btnRef = useRef(null);
  const cardRef = useRef(null);

  const cancelClose = () => {
    if (closeTimer.current !== null) {
      window.clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  };

  useEffect(() => {
    if (!pinned) return;
    const onDown = (ev) => {
      if (cardRef.current?.contains(ev.target) || btnRef.current?.contains(ev.target)) return;
      setPinned(false);
      setPos(null);
    };
    const onKey = (ev) => {
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

  const g = content || GLOSSARY[term];
  if (!g) return null;

  const show = () => {
    cancelClose();
    const r = btnRef.current?.getBoundingClientRect();
    if (!r) return;
    const x = Math.max(8, Math.min(r.left, window.innerWidth - CARD_W - 12));
    const spaceBelow = window.innerHeight - r.bottom - 18;
    const spaceAbove = r.top - 18;
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
        className="ml-1 w-4 h-4 inline-flex items-center justify-center rounded-full border border-edge text-[10px] leading-none text-gray-400 hover:text-sky-300 hover:border-sky-500"
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
            className="z-[100] bg-panel border border-edge rounded-lg p-3 text-left shadow-2xl text-xs font-normal normal-case tracking-normal overflow-y-auto overscroll-contain"
          >
            <div className="font-semibold text-gray-100 mb-1">{g.title}</div>
            <div className="text-gray-300">{g.what}</div>
            {g.calc && (
              <div className="mt-1.5 text-gray-400">
                <b className="text-gray-300">How it's computed:</b> {g.calc}
              </div>
            )}
            {g.read && (
              <div className="mt-1.5 text-gray-400">
                <b className="text-gray-300">How to read:</b> {g.read}
              </div>
            )}
          </div>,
          document.body
        )}
    </span>
  );
}
