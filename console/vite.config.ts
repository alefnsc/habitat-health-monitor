import { defineConfig } from "vite";

const HUB = "http://127.0.0.1:8000";

export default defineConfig(({ mode }) => ({
  base: mode === "replay" ? (process.env.CONSOLE_BASE ?? "./") : "./",
  resolve: {
    alias: { "@data": new URL("../data", import.meta.url).pathname },
  },
  server: mode === "replay" ? {} : {
    proxy: {
      "/api": { target: HUB, changeOrigin: true },
      "/ws": { target: HUB.replace("http", "ws"), ws: true, changeOrigin: true },
    },
  },
  build: { outDir: mode === "replay" ? "dist-replay" : "dist", emptyOutDir: true },
  test: { include: ["tests/**/*.test.ts"] },
}));
