/**
 * A Prisma client on the test database as the admin (superuser): for fixtures across
 * workspaces and for checking what the code under test wrote. The code under test itself
 * connects as ata_web (test/global-setup.ts), so row-level security applies to it as in
 * production.
 */
import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "@/lib/generated/prisma/client";

export const adminDb = new PrismaClient({
  adapter: new PrismaPg({ connectionString: process.env.TEST_ADMIN_DATABASE_URL ?? process.env.DATABASE_URL }),
});
