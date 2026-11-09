import { readFile } from "node:fs/promises";
import { dataDir, resolveKey, runIdOfKey } from "@/lib/files";
import { getRun } from "@/lib/runs";
import { currentWorkspaceId } from "@/lib/workspace";

/** Serve a stored screenshot, only if its run belongs to the current workspace. */
export async function GET(_request: Request, { params }: { params: Promise<{ key: string[] }> }) {
  const { key } = await params;
  const joined = key.join("/");
  const file = resolveKey(dataDir(), joined);
  if (!file) return new Response("Not found", { status: 404 });

  const run = await getRun(await currentWorkspaceId(), runIdOfKey(joined));
  if (!run) return new Response("Not found", { status: 404 });

  try {
    const data = await readFile(file);
    return new Response(new Uint8Array(data), {
      headers: {
        "Content-Type": file.endsWith(".png") ? "image/png" : "image/jpeg",
        "Cache-Control": "private, max-age=3600",
      },
    });
  } catch {
    return new Response("Not found", { status: 404 });
  }
}
