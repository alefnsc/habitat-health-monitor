import { defineConfig } from "vite";

export default defineConfig({
  server: { proxy: { "/ground": "http://127.0.0.1:8100" } },
});
