import { config } from "dotenv";
import type { NextConfig } from "next";
import { fileURLToPath } from "node:url";

// One .env for the whole repo, at the root (Next.js would only look in apps/web).
config({ path: "../../.env", quiet: true });

const nextConfig: NextConfig = {
  // Production images (Dockerfile.web) run the self-contained server that `next build` writes
  // to .next/standalone; tracing starts at the repo root because this is an npm workspace.
  output: "standalone",
  outputFileTracingRoot: fileURLToPath(new URL("../..", import.meta.url)),
};

export default nextConfig;
