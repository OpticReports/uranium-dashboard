import { useEffect, useMemo, useState } from "react";
import type { NewsItem, NewsTag } from "../lib/api";
import { api } from "../lib/api";
import { Panel, InlineError, Loading } from "./ui";
import { formatDateTime, errorMessage } from "../lib/format";

const TAG_COLOR: Record<NewsTag, string> = {
  FED: "#8b5cf6",
  AUCTION: "#38bdf8",
  DATA: "#10b981",
  GEO: "#f59e0b",
  OTHER: "#6b7280",
};

function TagPill({ tag }: { tag: NewsTag }) {
  const color = TAG_COLOR[tag] ?? TAG_COLOR.OTHER;
  return (
    <span
      className="rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide"
      style={{ color, backgroundColor: `${color}18`, border: `1px solid ${color}44` }}
    >
      {tag}
    </span>
  );
}

function publishedTs(item: NewsItem): number {
  if (!item.published) return 0;
  const t = new Date(item.published).getTime();
  return Number.isNaN(t) ? 0 : t;
}

export default function NewsPanel() {
  const [items, setItems] = useState<NewsItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .news(40)
      .then((r) => {
        if (alive) setItems(r.items);
      })
      .catch((e) => {
        if (alive) setError(errorMessage(e));
      });
    return () => {
      alive = false;
    };
  }, []);

  const sorted = useMemo(
    () => [...(items ?? [])].sort((a, b) => publishedTs(b) - publishedTs(a)),
    [items],
  );

  return (
    <Panel title="Newswire" subtitle="Fed, auctions, data & geopolitics">
      {error ? (
        <InlineError message={error} />
      ) : items === null ? (
        <Loading label="Loading news…" />
      ) : sorted.length === 0 ? (
        <p className="py-4 text-center text-xs text-slate-500">
          No news items.
        </p>
      ) : (
        <ul className="flex max-h-[460px] flex-col divide-y divide-panelborder/60 overflow-y-auto scroll-thin pr-1">
          {sorted.map((item, i) => (
            <li key={`${item.link}-${i}`} className="py-2">
              <div className="flex items-center gap-2">
                <TagPill tag={item.tag} />
                <span className="text-[10px] text-slate-500">{item.source}</span>
                {item.published && (
                  <span className="ml-auto font-mono text-[10px] text-slate-600">
                    {formatDateTime(item.published)}
                  </span>
                )}
              </div>
              <a
                href={item.link}
                target="_blank"
                rel="noreferrer"
                className="mt-1 block text-sm text-slate-200 hover:text-sky-400"
              >
                {item.title}
              </a>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
