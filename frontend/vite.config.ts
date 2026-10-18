/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the SPA and the API must share an origin (ADR 0003), so Vite
// proxies the backend paths. In production Caddy does the same job.
const apiTarget = process.env.VITE_API_PROXY ?? "http://127.0.0.1:8000";
const backendPaths = ["/api", "/accounts", "/healthz", "/admin", "/static"];

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: Object.fromEntries(
      backendPaths.map((p) => [p, { target: apiTarget, changeOrigin: false }]),
    ),
  },
  build: {
    sourcemap: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
