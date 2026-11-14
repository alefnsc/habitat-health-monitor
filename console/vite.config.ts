import { defineConfig } from "vite";

const HUB = "http://127.0.0.1:8000";

export default defineConfig({
  base: "./",
  resolve: {
    alias: { "@data": new URL("../data", import.meta.url).pathname },
  },
  server: {
    proxy: {
      "/api": { target: HUB, changeOrigin: true },
      "/ws": { target: HUB.replace("http", "ws"), ws: true, changeOrigin: true },
    },
  },
  build: { outDir: "dist", emptyOutDir: true },
  test: { include: ["tests/**/*.test.ts"] },
});
