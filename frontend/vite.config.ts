/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Everything (Vazirmatn included) is bundled from node_modules: no CDN, no runtime requests
// to third parties. /api is proxied to the FastAPI backend in dev.
// Same-origin in production (one image serves API + SPA). In dev the backend's OriginCheck rejects
// a foreign Origin, so the proxy presents the backend's own origin (alternative: TMS_CORS_ORIGINS).
const API = process.env.VITE_API_TARGET ?? "http://localhost:8000";
const proxy = { "/api": { target: API, changeOrigin: true, headers: { origin: API } } };

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy },
  preview: { proxy },
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 900 },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
});
