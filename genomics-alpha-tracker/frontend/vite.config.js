import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API base is read from VITE_API_BASE (see .env.example). In dev we proxy
// /api -> the FastAPI backend so there are no CORS surprises.
export default defineConfig({
  plugins: [react()],
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
