// Next.js's recommended rules (core web vitals + TypeScript), as the Next.js docs set them up.
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import { defineConfig, globalIgnores } from "eslint/config";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  globalIgnores([".next/**", "lib/generated/**", "next-env.d.ts", "playwright-report/**", "test-results/**"]),
]);
