import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Served under /btc on the shared domain (behind the genomics reverse proxy).
// For a standalone root deploy, change base to "/".
export default defineConfig({
  base: "/btc/",
  plugins: [react()],
  server: {
    proxy: {
      "/status": "http://localhost:8000", "/books": "http://localhost:8000",
      "/signals": "http://localhost:8000", "/bars": "http://localhost:8000",
      "/events": "http://localhost:8000", "/conditions": "http://localhost:8000",
      "/health": "http://localhost:8000", "/replay": "http://localhost:8000",
    },
  },
});
