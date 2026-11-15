import { existsSync } from "node:fs";
import { resolve } from "node:path";
import type { NextConfig } from "next";

// The repo keeps one .env at its root (docs/structure.md, "Env keys").
// Load it for local dev and builds. Values already set (Vercel project
// settings, the shell, web/.env*) win over it.
const rootEnv = resolve(process.cwd(), "..", ".env");
if (existsSync(rootEnv)) process.loadEnvFile(rootEnv);

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
};

export default nextConfig;
