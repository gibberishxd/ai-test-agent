import { readFile } from "node:fs/promises";
import { dataDir, resolveKey } from "@/lib/files";
import { canReadFile } from "@/lib/share";
import { currentWorkspaceId } from "@/lib/workspace";

/**
 * Serve a stored screenshot if its run belongs to the current workspace, or if the request
 * carries that run's share token (?share=...), which is how shared reports show their images.
 */
export async function GET(request: Request, { params }: { params: Promise<{ key: string[] }> }) {
  const { key } = await params;
  const joined = key.join("/");
  const file = resolveKey(dataDir(), joined);
  if (!file) return new Response("Not found", { status: 404 });

  const shareToken = new URL(request.url).searchParams.get("share");
  const workspaceId = await currentWorkspaceId();
  if (!(await canReadFile(joined, { workspaceId, shareToken }))) {
    return new Response("Not found", { status: 404 });
  }

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
