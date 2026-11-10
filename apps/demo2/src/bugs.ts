/**
 * Planted-bug switch for the holdout app. Every planted bug is guarded by `bug(n)`, n being its
 * id in bugs.json. In the clean build (`vite --mode clean`, port 5176) every `bug(n)` is false.
 */
export const CLEAN = import.meta.env.MODE === "clean";

export function bug(id: number): boolean {
  void id; // the id is there for grep and for readers
  return !CLEAN;
}
