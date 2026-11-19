import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist/**", "node_modules/**", "testsite/**", "scripts/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.ts"],
    rules: {
      // Page text is untrusted: never turn it into markup or code.
      "no-restricted-properties": [
        "error",
        { property: "innerHTML", message: "Use textContent; page content is untrusted." },
        { property: "outerHTML", message: "Use textContent; page content is untrusted." },
        { object: "document", property: "cookie", message: "The extension never reads cookies." },
        { object: "document", property: "write", message: "No document.write." },
      ],
      "no-restricted-globals": [
        "error",
        { name: "fetch", message: "Phase 1: the extension makes no network requests." },
        { name: "XMLHttpRequest", message: "Phase 1: the extension makes no network requests." },
        { name: "localStorage", message: "Use chrome.storage.session; nothing persistent." },
        { name: "eval", message: "No dynamic code." },
      ],
      "no-new-func": "error",
      "no-implied-eval": "error",
    },
  },
);
