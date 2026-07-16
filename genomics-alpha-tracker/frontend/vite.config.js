import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API base is read from VITE_API_BASE (see .env.example). In dev we proxy
// /api -> the FastAPI backend so there are no CORS surprises.
export default defineConfig({
  plugins: [react()],
  // In production the SPA is served under /genomics/ (research.optic.capital/genomics);
  // the root Dockerfile sets VITE_BASE="/genomics/" so hashed assets resolve there.
  // Dev keeps the default "/".
  base: process.env.VITE_BASE || "/",
  server: {
    port: 5173,
    host: true,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET || "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
