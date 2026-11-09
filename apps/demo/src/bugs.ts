/**
 * Planted-bug switch.
 *
 * The demo shop is the AI Test Agent's benchmark target. Every planted bug is guarded by
 * `bug(n)`, where n is its id in `bugs.json`. In the clean build (`vite --mode clean`, port 5174)
 * every `bug(n)` is false, so the same code runs with no bugs, which is how false alarms are counted.
 *
 * `grep -rn "bug(" src` lists every planted bug.
 */
export const CLEAN = import.meta.env.MODE === "clean";

export function bug(id: number): boolean {
  void id; // the id is there for grep and for readers; every bug shares the same switch
  return !CLEAN;
}
