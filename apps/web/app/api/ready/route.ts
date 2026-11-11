import { db } from "@/lib/db";
import { log } from "@/lib/log";

/** Readiness: the database answers, so this instance can take traffic. 503 otherwise. */
export async function GET() {
  try {
    await db.$queryRaw`SELECT 1`;
    return Response.json({ status: "ready", database: "ok" });
  } catch (error) {
    log("error", "not ready: the database doesn't answer", { error: String(error).slice(0, 200) });
    return Response.json({ status: "not ready", database: "unreachable" }, { status: 503 });
  }
}
