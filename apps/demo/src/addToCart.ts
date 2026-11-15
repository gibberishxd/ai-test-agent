/**
 * Run 7 (benchmark v2): a double click on "Add to cart" added the quantity twice. The browser
 * numbers the clicks of a multi-click in `event.detail` (1, then 2); only the later ones are
 * ignored, so a double click adds once and two separate clicks add twice, however fast they
 * come. Keyboard activation has detail 0. Not a planted bug: the same in both builds.
 */
export function acceptAdd(clickDetail: number): boolean {
  return clickDetail <= 1;
}
