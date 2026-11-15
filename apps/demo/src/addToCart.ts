/**
 * Run 7 (benchmark v2): a double click on "Add to cart" added the quantity twice. The second
 * click of a double click (within DOUBLE_CLICK_MS of the first) is ignored; a later click adds
 * again, as a shopper who wants more would expect. Not a planted bug: the same in both builds.
 */
export const DOUBLE_CLICK_MS = 500;

export function acceptAdd(lastAddAt: number | null, now: number): boolean {
  return lastAddAt === null || now - lastAddAt >= DOUBLE_CLICK_MS;
}
