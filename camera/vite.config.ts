import { defineConfig } from "vite";

const vendor = new URL("../vendor/ground-truth", import.meta.url).pathname;

export default defineConfig({
  base: "/camera/",
  resolve: {
    alias: {
      "@mediapipe/tasks-vision": new URL("./node_modules/@mediapipe/tasks-vision", import.meta.url).pathname,
      "@ground-truth/physics": `${vendor}/physics/src`,
      "@ground-truth/capture": `${vendor}/capture/src`,
    },
  },
  server: {
    fs: { allow: [".."] },
    // `localhost` stays a secure context while the hub runs elsewhere.
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
