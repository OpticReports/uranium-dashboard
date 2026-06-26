import React, { useState } from "react";
import { createPortal } from "react-dom";
import { GLOSSARY } from "../lib/glossary";

// A small "?" badge that shows a definition card on hover/click. The card is
// portaled to <body> with fixed positioning so it never gets clipped by table
// or container overflow.
export default function InfoTip({ term, content }) {
  const [pos, setPos] = useState(null);
  const g = content || GLOSSARY[term];
  if (!g) return null;

  const show = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const x = Math.min(r.left, window.innerWidth - 300);
    setPos({ x: Math.max(8, x), y: r.bottom + 6 });
  };

  return (
    <span className="relative inline-block align-middle">
      <button
        type="button"
        onMouseEnter={show}
        onMouseLeave={() => setPos(null)}
        onClick={(e) => {
          e.stopPropagation();
          pos ? setPos(null) : show(e);
        }}
        className="ml-1 w-4 h-4 inline-flex items-center justify-center rounded-full border border-edge text-[10px] leading-none text-gray-400 hover:text-sky-300 hover:border-sky-500"
        aria-label={`What is ${g.title}?`}
      >
        ?
      </button>
      {pos &&
        createPortal(
          <div
            style={{ position: "fixed", left: pos.x, top: pos.y, width: 280 }}
            className="z-[100] bg-panel border border-edge rounded-lg p-3 text-left shadow-2xl text-xs font-normal normal-case tracking-normal"
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
