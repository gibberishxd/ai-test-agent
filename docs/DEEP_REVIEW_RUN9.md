# Deep mode, run 9: the reports that matched no planted bug, checked by hand

**These are recommendations for the owner to decide on, not decisions.** Bug judging and
matching belong to the owner. Nothing here changes the benchmark scores or either shop.

The first deep-mode evaluation (`docs/BENCHMARKS.md`, "Deep mode, first evaluation", 2026-11-24)
left 13 reports that the scoring didn't explain:

- **Clean shop (run `e2f17518`, port 5174):** 5 reports from the agent. 4 were confirmed and
  counted as false alarms. 1 was kept apart as unverified and not counted. The 5th false alarm in
  the benchmark is the metadata finding (B3 below), which is the same on both builds.
- **Buggy shop (run `75a366f0`, port 5173):** 8 verified reports that matched no planted bug.
  Before checking them, I re-matched the run's 19 verified reports with the pinned judge
  (ollama/gemma4:12b, local, $0, nothing saved). It gave the same 11 matched and 8 unmatched that
  the benchmark recorded.

Each report was reproduced on its build with a Playwright script
([`deep-review-run9/repro.py`](deep-review-run9/repro.py)), which prints the measurements quoted
below and saves the screenshots. It was run on 2026-11-26 against `npm run dev` (5173) and
`npm run dev:clean` (5174). The cause was then looked up in `apps/demo/src`.

## Summary

| # | Build | Report | Reproduced | Recommendation |
|---|---|---|---|---|
| C1 | clean | Quantity 999999 and 1.5 accepted (input max=10) | yes | **Real bug in the shop** (not planted, in both builds) |
| C2 | clean | Shop list ignores search text still shown in the box | yes | **Real bug in the shop** (not planted, in both builds) |
| C3 | clean | Footer "Returns policy" reloads the app and empties the cart | yes | **Real bug in the shop**, a side effect of how bug 3 is planted |
| C4 | clean | Search toggle has no expanded state; Escape doesn't close it | yes | **Real bug in the shop**, minor (accessibility) |
| C5 | clean (unverified) | Order detail table is unstyled | yes | **Real bug in the shop** (cosmetic): its CSS class has no rule |
| B1 | buggy | axe: no main landmark on `/return-policy` | yes | **Duplicate of planted bug 3** (the 404 page bug 3 links to) |
| B2 | buggy | axe: content outside landmarks on `/return-policy` | yes | **Duplicate of planted bug 3** (same page) |
| B3 | buggy | Sharing and icon metadata missing | yes | **Real but not planted, the same on both builds**: decide once for both |
| B4 | buggy | Placed orders are never saved | yes | **Deliberate behaviour**: the confirmation itself says "not really: this is a demo" |
| B5 | buggy | Quantity limit not enforced (99 accepted) | yes | **Real bug in the shop**, the same as C1 |
| B6 | buggy | Cart emptied by a reload | yes | **Deliberate behaviour**, so far (your open decision since run 3) |
| B7 | buggy | Tap targets too small on mobile | yes (as measured) | **False alarm against WCAG AA**; real only against the AAA 44 px bar |
| B8 | buggy | Discount result message not announced | yes | **Real bug in the shop** (accessibility, WCAG 4.1.3), in both builds |

If you accept these recommendations:

- Of the clean run's 5 counted reports, 4 are real unplanted bugs (C1–C4) and 1 (B3's metadata)
  needs your one decision for both builds. None would be an invention by the agent.
- Of the buggy run's 8 unmatched reports, 2 are bug 3 seen again, 3 are real unplanted bugs
  (B3, B5, B8), 2 are deliberate behaviour (B4, B6), and 1 is a threshold question (B7).

## Clean shop (run e2f17518)

### C1. Add to cart ignores the quantity limits: 999999 and 1.5 accepted
- **Reproduced:** on `/products/4`, typing 999999 and clicking Add to cart gives `Cart (999999)`.
  Then 1.5 gives `Cart (1000000.5)`, and the cart total is `$18000009.00`. No message is shown.
- **Cause:** `ProductPage.tsx` sets `min={1} max={10}` on the input, but its `onChange` only
  applies `Math.max(1, Number(value) || 1)`. There's no upper bound and no integer check. This is
  not behind a `bug(n)` switch, so both builds do it.
- **Recommendation: real bug in the shop.** The input states its own limit of 10, and a
  fractional quantity makes no sense for a tote. Sonnet reported the same two cases in run 2, and
  the buggy run reported it as B5. "Quantity 0 is raised to 1" was left as intended in run 3, but
  the upper limit and fractions were never decided.
- Screenshot: [c1-quantity-cart.jpg](deep-review-run9/c1-quantity-cart.jpg)

### C2. The shop list ignores search text still shown in the search box
- **Reproduced:** open the search, type "mug" (1 product shows), go to Profile, then back to
  Shop. The box still says "mug", but all 6 products are listed.
- **Cause:** `SearchBar` lives in `Layout`, so it keeps its text across pages. `ProductList` is
  mounted again with `query = ""` and only hears the `demo-search` event when the text changes.
  Not behind a `bug(n)` switch.
- **Recommendation: real bug in the shop.** The page shows a filter it isn't applying.
- Screenshot: [c2-search-kept-list-unfiltered.jpg](deep-review-run9/c2-search-kept-list-unfiltered.jpg)

### C3. The footer "Returns policy" link reloads the app and empties the cart
- **Reproduced:** with 1 item in the cart, the header Profile link keeps `Cart (1)`. The footer
  link goes to `/returns` and shows `Cart (0)`.
- **Cause:** the footer uses a plain `<a href>` (`Layout.tsx`), so the browser loads the whole page
  again, and the cart lives only in memory (`store.tsx`). The plain anchor is there so that in the
  buggy build, bug 3's link reaches the server's real 404. The clean build kept the anchor and only
  changed the URL.
- **Recommendation: real bug in the shop**, but its fix depends on your B6 decision. If the cart is
  meant to survive reloads, B6 and C3 are the same bug. If not, the clean footer link should be a
  router `Link` (the buggy one can stay an anchor). The loop reported the same cart loss in run 8.
- Screenshot: [c3-footer-link-cart-empty.jpg](deep-review-run9/c3-footer-link-cart-empty.jpg)

### C4. The search toggle has no open/closed state, and Escape doesn't close it
- **Reproduced:** after opening, the button has no `aria-expanded`, `aria-controls` or
  `aria-pressed`. Pressing Escape in the field leaves it open.
- **Cause:** `Layout.tsx` toggles `searchOpen` without exposing it, and has no key handler.
- **Recommendation: real bug in the shop, minor.** A disclosure button that doesn't expose its
  state fails WCAG 4.1.2 (Name, Role, Value) in the usual reading. Closing on Escape is good
  practice for a non-modal disclosure but not a WCAG requirement, so the first half carries the
  report.
- Screenshot: [c4-search-open-after-escape.jpg](deep-review-run9/c4-search-open-after-escape.jpg)

### C5. The order detail table is unstyled (kept apart as unverified, not counted)
- **Reproduced:** at 768 px, the table on `/orders/1003` is 222 px wide, with 1 px cell padding,
  no row borders and centred headers. The cart table is 736 px wide, with 8 px padding, borders
  and left-aligned headers. "Canvas Tote 3" reads as one run of text.
- **Cause:** `OrdersPage.tsx` uses `className="order-lines"`, and `styles.css` has no rule for it.
  The cart uses `.table`.
- **Recommendation: real bug in the shop (cosmetic).** It was rightly kept apart as unverified: a
  purely visual difference has no replay or measurement that D116's verification could repeat.
- Screenshots: [c5-order-table.jpg](deep-review-run9/c5-order-table.jpg),
  [c5-cart-table-for-comparison.jpg](deep-review-run9/c5-cart-table-for-comparison.jpg)

## Buggy shop (run 75a366f0): the 8 unmatched reports

### B1, B2. axe: "one main landmark" and "content in landmarks" on `/return-policy`
- **Reproduced:** `/return-policy` answers HTTP 404 with the demo server's bare page
  (`vite.config.ts`: an `<h1>` and nothing else), which has no `<main>`. Only the buggy footer
  links there. The clean footer links to `/returns`, so these can't appear on the clean build.
- **Recommendation: duplicates of planted bug 3.** They describe the 404 page that bug 3 is about,
  not a separate defect. Two ways to stop them costing precision, both your call:
  1. the matcher accepts a deterministic finding on bug 3's target URL as bug 3;
  2. the crawl skips axe on pages answered with 4xx/5xx. A missing page's markup is rarely worth a
     finding of its own, and this rule would apply on any site.
- Screenshot: [b1-b2-return-policy-404.jpg](deep-review-run9/b1-b2-return-policy-404.jpg)

### B3. Sharing and icon metadata incomplete
- **Reproduced:** the `<head>` has only charset, viewport, title and favicon. There are no
  `og:*`, `twitter:card`, canonical or apple-touch-icon tags. The buggy and clean builds serve an
  identical `<head>`.
- **Recommendation: real, not planted, and the same on both builds.** Since D105 every run reports
  it, so it costs both precision (buggy) and a false alarm (clean) every time. Decide once: either
  add the tags to both shops (it isn't a bug you planted), or plant it as a bug in
  `bugs.json`.
- Screenshot: [b3-head-without-metadata.jpg](deep-review-run9/b3-head-without-metadata.jpg) (the
  dev server's inline styles and scripts are left out of the rendering)

### B4. Placed orders are never saved
- **Reproduced:** checkout shows "Thanks! Your order #90329 is on its way (not really: this is a
  demo).", sends no request, and My orders still lists the 3 fixed orders.
- **Recommendation: deliberate behaviour.** The shop says so on the confirmation itself. The agent
  saw the "demo" disclaimer and reported anyway. That's a reasonable call for a real site, but
  not a bug in this one.
- Screenshots: [b4-order-confirmation.jpg](deep-review-run9/b4-order-confirmation.jpg),
  [b4-my-orders-unchanged.jpg](deep-review-run9/b4-my-orders-unchanged.jpg)

### B5. Quantity limit not enforced: 99 accepted
- **Reproduced:** quantity 99 gives `Cart (99)`.
- **Recommendation: real bug in the shop, the same as C1** (same code, in both builds).
- Screenshot: [b5-quantity-99.jpg](deep-review-run9/b5-quantity-99.jpg)

### B6. The cart is emptied by a reload
- **Reproduced:** `Cart (1)` before a full load of `/cart`, `Cart (0)` after. Nothing cart-related is
  stored in `localStorage`.
- **Recommendation: deliberate behaviour, as it stands.** You left "a reload empties the cart (it
  lives only in memory)" as intended in run 3, and it's still open under "Needs me" in
  `docs/PROGRESS.md`. Deciding it also decides C3.
- Screenshot: [b6-cart-empty-after-reload.jpg](deep-review-run9/b6-cart-empty-after-reload.jpg)

### B7. Tap targets too small on mobile
- **Reproduced (measured at 390 × 844):** nav links are 24 px high (Shop 39×24, Cart 57×24,
  Profile 46×24, My orders 73×24, Log out 55×24), the search button is 32×32, and product title
  links are 18 px high.
- **Recommendation: false alarm against WCAG AA; real only against AAA.** WCAG 2.2 AA (2.5.8,
  Target Size Minimum) asks for 24×24 px. The nav meets it, and the 18 px title links are far
  enough apart for its spacing exception. The report rests on the 44 px bar of 2.5.5 (AAA), which
  the layout check uses since D105. The agent itself wrote "24px minimum" in its expected result.
  The clean run, with the same CSS, didn't report it. Your call is the threshold: keep 44 px and
  accept this as a real finding (then it should come up on both builds), or report under 24 px
  as AA does.
- Screenshot: [b7-header-at-390px.jpg](deep-review-run9/b7-header-at-390px.jpg)

### B8. The discount code result isn't announced to screen readers
- **Reproduced:** after Apply with an empty code, "That code isn't valid." is a plain `<p>` with no
  role or `aria-live`. There is no live region in `main`, and `#discount` has no `aria-invalid` or
  `aria-describedby`.
- **Cause:** `CartPage.tsx` renders `{codeError && <p className="error">…</p>}`, which isn't behind a
  `bug(n)` switch, so the clean build behaves the same.
- **Recommendation: real bug in the shop** (WCAG 4.1.3 Status Messages, AA). The shop's own "Added
  to your cart" message uses `role="status"`, so this one is an omission.
- Screenshot: [b8-discount-message.jpg](deep-review-run9/b8-discount-message.jpg)

## What this suggests about deep mode (for later, nothing changed)
- None of the 13 is an invention. Every report describes something the shop really does. The
  false alarms come from the benchmark's ground truth: the shops have real, unplanted bugs, and
  the clean build isn't clean.
- **Deep mode is inconsistent between the two runs.** C1 and B5 found the same quantity bug, but
  B7 and B8 came up only on the buggy run, and C2, C4 and C5 only on the clean run, though the code
  is the same in both builds. With one run per build, this is expected noise. More runs per build
  would show how stable deep mode's coverage is.

## Addendum: the re-run with D120 and D121 (2026-11-26)

One more deep run per build (buggy `b364ce85`, clean `2e31e8aa`; scores in `docs/BENCHMARKS.md`).
Its 8 unmatched buggy reports and 6 clean reports are mostly the ones above again:

| Re-run report | Build | Same as |
|---|---|---|
| axe: one main landmark / content in landmarks on `/return-policy` | buggy | B1, B2 (duplicates of bug 3) |
| Sharing and icon metadata incomplete | both | B3 |
| Quantity above 10 accepted, decimals accepted (2 reports on clean, 1 on buggy) | both | C1 / B5 |
| Order detail table unstyled | buggy | C5 (verified this time by measurement) |
| Search toggle: no `aria-expanded`, Escape doesn't close | both | C4 |
| Confirmed order never appears in My orders | clean | B4 (deliberate) |
| **Order placed with an empty cart** | both | new, see R2 |
| **Search with a trailing space finds nothing** | buggy | new, see R1 |

D121's new runtime findings added one report on the buggy build, "GET /return-policy fails with
HTTP 404", which the judge matched to bug 3. That is bug 3's broken link again under another
title, and D121's follow-up fix (commit 467366d) stops it from being reported. The run itself
used the code from before that fix. No runtime findings on the clean build.

### R1. Search with a trailing space finds nothing
- **Reproduced (clean build):** "lamp" shows 1 product, and "lamp " (with a trailing space) shows 0.
- **Cause:** `ProductList.tsx` filters with `name.toLowerCase().includes(query.toLowerCase())`
  and doesn't trim the query. Not behind a `bug(n)` switch.
- **Recommendation: real bug in the shop, minor.** A space typed by habit or by phone
  autocomplete hides every result, with only a "No products match" message.
- Screenshot: [r1-search-trailing-space.jpg](deep-review-run9/r1-search-trailing-space.jpg)

### R2. An order can be placed with an empty cart
- **Reproduced (clean build):** on `/checkout` with an empty cart the page says "Your cart is
  empty, but you can still try the form."; Place order then confirms "order #27145".
- **Recommendation: deliberate behaviour.** The page says so before the form, like B4's "not
  really: this is a demo". If you want the shop to look less like a demo to the agent, these two
  notes are what it keeps reporting around.
- Screenshot: [r2-empty-cart-order.jpg](deep-review-run9/r2-empty-cart-order.jpg)

The script for R1 and R2 is [`deep-review-run9/repro_rerun.py`](deep-review-run9/repro_rerun.py).
