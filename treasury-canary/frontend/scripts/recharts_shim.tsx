// Server-render shim for the AI-debt render smoke: ResponsiveContainer
// measures the DOM, which does not exist in node, so every chart gets a fixed
// size. Everything else is the real recharts.
import { cloneElement, isValidElement, type ReactElement, type ReactNode } from "react";
// relative, so the esbuild `--alias:recharts=` that routes the component here does not remap it back
export * from "../node_modules/recharts/es6/index.js";
export function ResponsiveContainer({ children }: { children: ReactNode; width?: unknown; height?: unknown }) {
  const W = 720;
  const H = 220;
  return <div style={{ width: W, height: H }}>{isValidElement(children) ? cloneElement(children as ReactElement<{ width?: number; height?: number }>, { width: W, height: H }) : children}</div>;
}
