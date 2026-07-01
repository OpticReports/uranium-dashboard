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
];

export default defineConfig({
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
