import { defineConfig } from "vitest/config";

const vendor = new URL("../vendor/ground-truth", import.meta.url).pathname;

export default defineConfig({
  resolve: {
    alias: {
      "@ground-truth/physics": `${vendor}/physics/src`,
      "@ground-truth/capture": `${vendor}/capture/src`,
    },
  },
  test: {
    // One run collects the vendored upstream tests and the camera tests.
    include: [
      "tests/**/*.test.ts",
      "../vendor/ground-truth/physics/test/**/*.test.ts",
      "../vendor/ground-truth/capture/test/**/*.test.ts",
    ],
  },
  server: { fs: { allow: [".."] } },
});
