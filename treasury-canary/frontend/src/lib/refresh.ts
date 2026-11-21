import { createContext, useContext, useEffect, useRef, useState, type DependencyList } from "react";

// Panels that load once (2026-11-21): their data stayed on screen until the page was reloaded, so a
// board built during a FRED outage outlived the outage in an open tab. Every panel's load now reruns
// on a page-wide tick: every PANEL_REFRESH_MS while the tab is visible, and as soon as a hidden tab
// comes back after that long. A refresh is quiet: the panel keeps what it shows (no spinner, no
// error box when a refresh fails, the user's choices untouched) and swaps in new data on success.

export const PANEL_REFRESH_MS = 15 * 60_000;   // the backend rebuilds a degraded cache within 15 min
const CHECK_MS = 60_000;

export const RefreshTickContext = createContext(0);

/** the page-wide tick, for the App to provide: counts up once per PANEL_REFRESH_MS of visible time */
export function useRefreshTickSource(): number {
  const [tick, setTick] = useState(0);
  const last = useRef(Date.now());
  useEffect(() => {
    const due = () => {
      if (document.visibilityState !== "visible" || Date.now() - last.current < PANEL_REFRESH_MS) return;
      last.current = Date.now();
      setTick((t) => t + 1);
    };
    const id = window.setInterval(due, CHECK_MS);
    document.addEventListener("visibilitychange", due);   // a background tab's timers are throttled
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", due);
    };
  }, []);
  return tick;
}

export function useRefreshTick(): number {
  return useContext(RefreshTickContext);
}

export interface RefreshingLoad<T> {
  load: () => Promise<T>;
  /** every success: the first load, a load for new inputs, or a refresh. `first`: no success yet for these inputs */
  onData: (value: T, first: boolean) => void;
  /** a failure while nothing has loaded for these inputs; a failed refresh keeps the data on screen */
  onError?: (e: unknown) => void;
  /** before a load for new inputs (mount, a deps change), never before a refresh */
  onStart?: () => void;
}

/**
 * Loads on mount and whenever `deps` change, then again on every refresh tick. A tick never cancels a
 * load in flight; a reply older than one already applied is dropped; a deps change or unmount drops
 * every reply still out.
 */
export function useRefreshingLoad<T>(spec: RefreshingLoad<T>, deps: DependencyList = []): void {
  const tick = useRefreshTick();
  const latest = useRef(spec);
  latest.current = spec;
  const life = useRef(0);        // bumps on a deps change or unmount
  const ok = useRef(false);      // a load succeeded for the current deps
  const seq = useRef(0);
  const applied = useRef(0);
  const run = () => {
    const mine = life.current;
    const n = ++seq.current;
    latest.current.load().then(
      (value) => {
        if (mine !== life.current || n < applied.current) return;
        applied.current = n;
        const first = !ok.current;
        ok.current = true;
        latest.current.onData(value, first);
      },
      (e) => {
        if (mine !== life.current || ok.current) return;
        latest.current.onError?.(e);
      },
    );
  };
  const loadedAt = useRef<number | null>(null);
  useEffect(() => {
    life.current += 1;
    ok.current = false;
    loadedAt.current = tick;
    latest.current.onStart?.();
    run();
    return () => {
      life.current += 1;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => {
    if (loadedAt.current === null || loadedAt.current === tick) return;   // the input load covers this tick
    loadedAt.current = tick;
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick]);
}
