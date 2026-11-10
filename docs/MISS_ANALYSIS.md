# Why the agent misses bugs (run 3, H6)

For every planted bug that needs judgement ("AI-only": the deterministic checks can't find
it), this explains from the step logs why each model found or missed it. The causes fall into
five kinds:

- **Never reached:** the agent never visited the page where the bug lives.
- **Never triggered:** it was on the page but never did the thing that makes the bug appear
  (a second unit, an invalid value, a double click, a reload, a phone-width screen).
- **Saw it, didn't report:** the bug was on screen (or in the agent's own notes) but no
  report was filed.
- **Reported, then dropped:** a report was filed but replay verification or the benchmark
  matcher threw it away.
- **Unreachable for any agent:** the bug can't be triggered without knowledge the site never
  gives (a benchmark flaw, not an agent miss).

Runs read (all on the buggy apps; step logs in the database, run ids below):

| Set | Model | Agent code | Runs | Limit |
|---|---|---|---|---|
| R2 | gemma4:12b | run 2 after D52 (commit 21e5669) | shop 804c2a85, e2ccf43f, d750ccfc; holdout d712b435, fba800a4 | 480 s |
| S | Sonnet via claude-cli | run 2 (commit 0124950) | shop be495c9f | 480 s |
| R3a | gemma4:12b | run 3 after the replay fix (f1bf08a; the result row says 984755e, see D58) | shop 6f8600fc, 88dafc6f, 906111fd; holdout e9a9fe78, 7c8f8521 | 1200 s |
| R3b | gemma4:12b | run 3 with D58–D60 | see "After the changes" below | 1200 s |

How "did it trigger the bug" was judged: by reading what the agent typed and clicked, and on
which page (for example, the dates it typed into a booking form and the nights the page then
showed). The helper that tallies this lives outside the repo on purpose: it contains the
planted bugs' details, and planted-bug details stay out of the code.

## How often each tester technique was used

| Runs | Agent steps | double_click | reload | mobile viewport | unusual typed values | notes | reports |
|---|---|---|---|---|---|---|---|
| Gemma, 11 runs (R2 + run-2 G6 + R3a, shop and holdout) | 22–40 | **0** | **0** | **0** | almost none (quantity 1, valid emails, 1-night stays) | 0–1 per run | 0–1 per run |
| Sonnet, 1 run (S) | 40 | 1 | 1 | 1 | 0, huge, 1.5, -1, letters in a number field | 0 | 7 |

This table is the main finding. Gemma follows the happy path with valid data and almost
never applies the charter's techniques. Most of its misses are "never triggered", not "saw it
and didn't recognise it".

## Demo shop (apps/demo), AI-only bugs 5–12

| Bug | Gemma R2 (3 runs) | Gemma R3a (3 runs) | Sonnet S (1 run) | Why |
|---|---|---|---|---|
| 5. Cart total ignores quantity | 0/3 | 0/3 | **reported, dropped** → found after the H1 fix (offline) | Gemma always adds one unit, so line price = total and nothing is wrong on screen (never triggered). Sonnet typed a huge quantity, saw "$8,900,000,000,000.00 vs Total $89.00", reported it, and replay dropped it ("no textbox Quantity": the replay timing bug, D53). |
| 6. Checkout accepts an invalid email | 0/3 | 0/3 | 0/1 | Gemma reaches /checkout in every run (6–12 steps there) but always types the valid test email (never triggered). Sonnet never went to checkout (it spent its steps on quantities and the profile). |
| 7. Discount applies twice on double click | 0/3 | 0/3 | 0/1 | **Unreachable for any agent.** It needs the code `SAVE10`, which the shop never shows (no banner, no hint). Gemma and Sonnet only tried made-up codes ("INVALID100", double-clicking Apply with an invalid code). Needs-me: show a code on the site, or count the bug as unfindable. |
| 8. "Save changes" does nothing | reported in 1/3, **dropped by replay** | **2/3** | **reported, dropped** → found after the H1 fix (offline) | Both models change the display name and click Save. Before H1 the report was lost in replay (an earlier step of another flow failed, or the timing bug). After H1 it is kept. |
| 9. Wool Socks price shows $NaN | 1/3 | 0/3 | 1/1 | **Saw it, didn't report.** Gemma wrote the note "Wool Socks price is NaN" in 5 runs and reported it in 1. Sonnet reported it at once. Led to D60. |
| 10. Long product name overflows on mobile | 0/3 | 0/3 | 0/1 | Gemma never changed the viewport (never triggered). Sonnet switched to mobile on /profile only, not on the long product's page. The passive scan's phone-width screenshots aren't reviewed in interactive runs (the agent decides what to look at). |
| 11. Logout doesn't clear the session after a refresh | 0/3 | 0/3 | 0/1 | Every model logged out, but no one reloaded afterwards: Gemma logged in again, Sonnet moved on (never triggered). |
| 12. Wrong-password error under the email field | 0/3 | 0/3 | 0/1 | All runs logged in with the demo credentials shown on the login page. The only invalid login tried was an unknown email (Sonnet: "No account with that email."), not a wrong password for a real account (never triggered). |

## Holdout app (apps/demo2), AI-only bugs 3–6

| Bug | Gemma R2 (2 runs) | Gemma R3a (2 runs) | Why |
|---|---|---|---|
| 3. Total charges one night whatever the stay | 0/2 | 0/2 | Every booking in all 4 runs is the same one-night stay (2024-12-01 → 2024-12-02), where one night is correct. Never triggered. |
| 4. Check-out before check-in accepted | 0/2 | 0/2 | Dates always valid and in order. Never triggered. |
| 5. Double-click "Book now" creates two bookings | 0/2 | 0/2 | Book now is always clicked once. Never triggered. |
| 6. Room name overflows on mobile | 0/2 | 0/2 | No viewport change. Never triggered. |

## Ran out of steps or time?

Not the main cause. R2's runs stopped at the 480 s limit after 22–26 steps. R3a's runs used all
40 steps in ~1100 s and found one bug more (bug 8, now kept by replay), and nothing else. The
extra steps went into more of the same happy path: a second identical checkout, a second
identical booking. Run 2 had already shown this for the shop (1200 s, 40 steps, same result).

## Reported, then dropped: before and after the replay fix

- Before H1: Sonnet's run lost 4 of its 6 agent reports in replay, including bugs 5 and 8.
  Gemma R2 lost its only bug-8 report the same way.
- After H1, R3a: 18 shop reports and 8 holdout reports, **0 discarded, 0 correct but
  discarded** (the new funnel numbers, D54). Offline, all 6 of Sonnet's reports from be495c9f
  replay and are confirmed (D53).

So the verifier is no longer what limits the score. The agent's exploration is.

## What this says to improve (generic, in order)

1. **Make weak models use the techniques** (D59): show the untried charter techniques in
   every observation. Expected to help bugs 5, 6, 10, 11, 12 and the whole holdout, since all
   are "never triggered".
2. **Notes aren't reports** (D60): the note tool's result says so. Expected to help bug 9.
3. **Wasted steps** (D58): accept `element_id: [10]` (3 of 40 steps lost in some runs).
4. Not done, for the owner: make bug 7 reachable (show the discount code somewhere on the
   shop, as real shops do), or mark it unfindable in `bugs.json`. Changing the benchmark
   mid-comparison would make run 2 and run 3 numbers incomparable.

## After the changes (R3b)

(Filled in when the second Gemma benchmark finishes.)
