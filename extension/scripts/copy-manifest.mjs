// Copy manifest.json into dist/ after the Vite builds, and fail if a file the
// manifest names is missing from the build.
import { copyFileSync, existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const dist = resolve(root, "dist");
copyFileSync(resolve(root, "manifest.json"), resolve(dist, "manifest.json"));

const manifest = JSON.parse(readFileSync(resolve(root, "manifest.json"), "utf8"));
const required = [manifest.background.service_worker, manifest.side_panel.default_path, "content.js"];
const missing = required.filter((file) => !existsSync(resolve(dist, file)));
if (missing.length > 0) {
  console.error(`Build output is missing: ${missing.join(", ")}`);
  process.exit(1);
}
console.log("dist/ ready: load it with chrome://extensions > Load unpacked");
