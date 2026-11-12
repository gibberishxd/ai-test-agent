import { log } from "@/lib/log";

/** Liveness: the process answers. (Readiness, with the database, is /api/ready.) */
export function GET() {
  log("debug", "health check");
  return Response.json({ status: "ok" });
}
