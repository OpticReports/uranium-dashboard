import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API_TARGET = "http://localhost:8000";

const proxied = [
  "/metrics",
  "/composite",
  "/recession-prob",
  "/curve",
  "/events",
  "/alerts",
  "/news",
  "/health",
  "/refresh",
  "/margin",
  "/rates",
  "/shock-sim",
  "/pins",
  "/severity",
];

export default defineConfig({
  // Served under /canary on the shared domain (behind the genomics reverse proxy).
  // For a standalone root deploy, change this to "/".
  base: "/canary/",
  plugins: [react()],
  server: {
    proxy: proxied.reduce<Record<string, { target: string; changeOrigin: boolean }>>(
      (acc, path) => {
        acc[path] = { target: API_TARGET, changeOrigin: true };
        return acc;
      },
      {},
    ),
  },
});
