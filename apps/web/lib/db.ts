import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "@/lib/generated/prisma/client";

/**
 * One Prisma client for the whole server process.
 *
 * In development Next.js reloads modules on every change; without the globalThis cache each
 * reload would open a new connection pool until Postgres runs out of connections.
 */
const globalForPrisma = globalThis as unknown as { prisma?: PrismaClient };

function createClient(): PrismaClient {
  // WEB_DATABASE_URL: the web app's own role, ata_web (run 5, K3). DATABASE_URL is the admin
  // connection migrations use; it is the fallback until the roles exist.
  const adapter = new PrismaPg({ connectionString: process.env.WEB_DATABASE_URL || process.env.DATABASE_URL });
  return new PrismaClient({ adapter });
}

export const db = globalForPrisma.prisma ?? createClient();

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = db;
