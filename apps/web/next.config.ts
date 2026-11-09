import { config } from "dotenv";
import type { NextConfig } from "next";

// One .env for the whole repo, at the root (Next.js would only look in apps/web).
config({ path: "../../.env", quiet: true });

const nextConfig: NextConfig = {};

export default nextConfig;
