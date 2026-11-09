import path from "node:path";

/**
 * Screenshots live on the worker's disk (DATA_DIR, relative to the repo root), stored under
 * keys like "<run id>/page-001.png". This turns a key into a file path, refusing anything that
 * would escape the folder ("../../etc/passwd").
 */
export function repoRoot(): string {
  return path.resolve(process.cwd(), "..", "..");
}

export function dataDir(): string {
  const dir = process.env.DATA_DIR ?? "apps/worker/data";
  return path.isAbsolute(dir) ? dir : path.join(repoRoot(), dir);
}

export function resolveKey(root: string, key: string): string | null {
  const base = path.resolve(root);
  const file = path.resolve(base, key);
  if (!file.startsWith(base + path.sep)) return null;
  if (!/\.(png|jpe?g)$/i.test(file)) return null;
  return file;
}

/** The run a stored file belongs to: the first part of its key. */
export function runIdOfKey(key: string): string {
  return key.split("/")[0] ?? "";
}
