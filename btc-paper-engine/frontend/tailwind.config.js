/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canary: {
          green: "#10b981",
          yellow: "#f59e0b",
          red: "#ef4444",
          critical: "#dc2626",
          stale: "#6b7280",
        },
        panel: "#0f172a",
        panelborder: "#1e293b",
      },
      fontFamily: {
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
};
