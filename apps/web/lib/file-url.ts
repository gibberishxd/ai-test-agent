/**
 * The URL of a stored screenshot. On a shared report the viewer isn't in the run's workspace,
 * so the share token goes along and the files route checks it against that one run.
 */
export function fileUrl(key: string, shareToken?: string | null): string {
  const url = `/api/files/${key}`;
  return shareToken ? `${url}?share=${encodeURIComponent(shareToken)}` : url;
}
