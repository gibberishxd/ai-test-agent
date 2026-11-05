/** Returns true for http(s) URLs only. The agent must never be pointed at file:// or other schemes. */
export function isValidTargetUrl(input: string): boolean {
  try {
    const url = new URL(input);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}
