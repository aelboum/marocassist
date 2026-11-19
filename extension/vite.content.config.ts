import { resolve } from "node:path";
import { defineConfig } from "vite";

// The content script as one self-contained classic script (IIFE).
export default defineConfig({
  build: {
    outDir: "dist",
    emptyOutDir: false,
    target: "chrome116",
    lib: {
      entry: resolve(import.meta.dirname, "src/content/index.ts"),
      name: "MarocAssistContent",
      formats: ["iife"],
      fileName: () => "content.js",
    },
  },
});
