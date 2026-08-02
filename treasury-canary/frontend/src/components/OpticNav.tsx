import { useEffect, useRef, useState } from "react";

// Universal dashboard switcher — identical copy embedded in every optic app
// (separate SPAs behind one domain; plain anchors do full navigations).
const APPS = [
  { path: "/", label: "Genomics Alpha Tracker", icon: "\u{1F9EC}" },
  { path: "/canary/", label: "Treasury Canary", icon: "\u{1F424}" },
  { path: "/portfolio-optimizer/", label: "Portfolio Optimizer", icon: "\u2696\uFE0F" },
  { path: "/btc/", label: "BTC Paper Engine", icon: "\u20BF" },
];

export default function OpticNav() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const here = window.location.pathname;
  const current = APPS.reduce(
    (best, a) =>
      here.startsWith(a.path) && a.path.length > (best?.path.length ?? 0)
        ? a
        : best,
    null as (typeof APPS)[number] | null,
  );

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="fixed left-3 top-3 z-50">
      <button
        type="button"
        aria-label="All dashboards"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex h-8 w-8 items-center justify-center rounded-md border border-slate-600/70 bg-slate-900/90 text-slate-300 shadow-lg backdrop-blur hover:border-sky-500/60 hover:text-sky-300"
        title="All dashboards"
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden>
          <path d="M1 3h12M1 7h12M1 11h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      </button>
      {open && (
        <nav className="mt-1.5 w-60 overflow-hidden rounded-lg border border-slate-700 bg-slate-900/95 shadow-2xl backdrop-blur">
          <p className="border-b border-slate-800 px-3 py-1.5 text-[9px] font-semibold uppercase tracking-widest text-slate-500">
            optic.capital dashboards
          </p>
          {APPS.map((a) => {
            const active = current?.path === a.path;
            return (
              <a
                key={a.path}
                href={a.path}
                className={`flex items-center gap-2.5 px-3 py-2 text-xs transition-colors ${
                  active
                    ? "bg-sky-500/10 font-semibold text-sky-300"
                    : "text-slate-300 hover:bg-slate-800/70 hover:text-slate-100"
                }`}
              >
                <span className="w-4 text-center">{a.icon}</span>
                {a.label}
                {active && <span className="ml-auto text-[9px] text-sky-500">here</span>}
              </a>
            );
          })}
        </nav>
      )}
    </div>
  );
}
