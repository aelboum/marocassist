import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const config = [
  ...nextCoreWebVitals,
  ...nextTypescript,
  {
    ignores: [".next/**", "node_modules/**", "next-env.d.ts"],
  },
  {
    rules: {
      // All backend calls go through lib/api.ts (one place for credentials,
      // errors and paths).
      "no-restricted-globals": ["error", { name: "localStorage", message: "No tokens or personal data in localStorage." }],
    },
  },
];

export default config;
