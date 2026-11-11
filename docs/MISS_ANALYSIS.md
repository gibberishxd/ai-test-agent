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
- **Needs outside knowledge:** the bug can't be triggered without something the site never
  gives (a benchmark flaw more than an agent miss; bug 7 turned out to be guessable).

Runs read (all on the buggy apps; step logs in the database, run ids below):

| Set | Model | Agent code | Runs | Limit |
|---|---|---|---|---|
| R2 | gemma4:12b | run 2 after D52 (commit 21e5669) | shop 804c2a85, e2ccf43f, d750ccfc; holdout d712b435, fba800a4 | 480 s |
| S | Sonnet via claude-cli | run 2 (commit 0124950) | shop be495c9f | 480 s |
| R3a | gemma4:12b | run 3 after the replay fix (f1bf08a; the result row says 984755e, see D58) | shop 6f8600fc, 88dafc6f, 906111fd; holdout e9a9fe78, 7c8f8521 | 1200 s |
| R3b | gemma4:12b | run 3 with D58–D60 (984755e) | shop 9590b85f (failed at step 31), a0e4c761, d52e106d; holdout 73b945f8, ab273f55 (failed at step 17) | 1200 s |

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
| 7. Discount applies twice on double click | 0/3 | 0/3 | 0/1 | Needs the code `SAVE10`, which the shop never shows. Gemma and the first Sonnet run only tried made-up codes ("INVALID100"). **Correction after H7:** Sonnet typed `SAVE10` as its first and only guess in one of three runs and found the bug, so the bug is guessable (a very common code), not unreachable. It is still unfair to agents that don't guess well. Needs-me: show a code on the site, or keep it as a "guess a common code" bug. |
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

Result row `f06138df` (commit 984755e: D58–D60, before D61). Three of the seven runs ended
early on an Ollama `ReadTimeout` (one model call took over 300 s): shop 9590b85f, holdout
ab273f55 and the clean holdout run 746e58ee. Their deterministic findings still count, and the
benchmark still counts them as buggy runs, so the AI-only numbers below are slightly
pessimistic. D61 (committed after this benchmark started) now ends such a run cleanly instead.

**Technique use** (each run, agent steps only):

| Runs | double_click | reload | mobile viewport | notes | reports |
|---|---|---|---|---|---|
| R3a, 5 buggy runs | 0 | 0 | 0 | 0–1 | 0–1 |
| R3b, 5 buggy + clean runs that got past step ~20 (5 of 7) | **1 in each** | **1 in each** | **1 in each** | 0–1 | 0–1 |

D59 works as intended at the level it acts on: every run that lived long enough used each
technique, where 11 earlier Gemma runs never did. But it uses each one exactly once and then
moves on: it treats the list as a checklist to clear, not as ideas to apply where they fit
(the mobile viewport was set on /profile or the home page, never on the long product's page).

**Per bug: did the agent trigger it, and did it report it?** (shop: 3 runs, holdout: 2)

| Bug | R3a triggered | R3b triggered | R3b reported |
|---|---|---|---|
| Shop 5. Cart total ignores quantity | 0/3 | **2/3** | 0 |
| Shop 6. Invalid email at checkout | 0/3 | 0/3 | 0 |
| Shop 7. Discount twice on double click | 0/3 | 1/3 (with a made-up code, so the bug can't show) | 0 |
| Shop 8. Save changes does nothing | 2/3 | 3/3 | **0** (was 2/3) |
| Shop 9. Wool Socks $NaN | always on screen | always on screen | **2/3** (was 0/3) |
| Shop 10. Long name on mobile | 0/3 | 0/3 | 0 |
| Shop 11. Session survives logout + reload | 0/3 | **3/3** | 0 |
| Shop 12. Wrong-password error placement | 0/3 | 0/3 | 0 |
| Holdout 3. One night charged | 0/2 | **2/2** | 0 |
| Holdout 4. Check-out before check-in | 0/2 | **2/2** | 0 |
| Holdout 5. Double-click Book now | 0/2 | **1/2** | 0 |
| Holdout 6. Room name on mobile | 0/2 | 0/2 | 0 |

**What changed:**

- D60 (notes aren't reports) did what it was for: bug 9 went from "noted, not reported" in
  most runs to reported in 2 of 3.
- D59 moved most misses from "never triggered" to **"triggered, didn't recognise it"**: 7 of
  the 12 AI-only bugs were on screen at least once, versus 1 before. Gemma clicks Save after
  changing the name, reloads after logging out and lands logged in, books a stay with check-out
  before check-in, and then simply carries on.
- The headline numbers barely moved: shop AI-only 8% (bug 9 in 2/3, where R3a had bug 8 in
  2/3), shop recall 39%, holdout AI-only 0%, recall 33%, precision 100%, 0 false alarms,
  17 + 8 reports with none discarded. Bug 8 being missed this time is run-to-run variance in
  what Gemma chooses to report, not a regression in replay (no report was discarded).
- Holdout did not drop (0% → 0%, recall 33% → 33%), so D59 and D60 stay, per the run plan.

**So the next limit is recognition, not exploration.** The agent now reaches the bug states;
a 12B model does not compare what it sees with what it expected. Generic ideas, not tried
here (each is AI-core work for the owner): ask the model after each state-changing action for
"what did you expect, what happened" in one line before the next action (an expectation check
that a report can be built from); or let the screenshot reviewer that the passive scan
already has look at the screens right after a technique step. Sonnet already does the
comparison without help (it reported 7 things in one run), so the H7 run is the reference.

## Sonnet benchmark (H7, claude-cli, one full run)

Result row `f6151b32`, commit a8a6d13, same settings as be495c9f (480 s limit, 40 steps, judge
pinned to gemma4:12b), shop 3 runs + clean, holdout 2 runs + clean. No usage limit was hit.
The claude-cli process ran in a temp folder with `--restricted`; before the run, one Haiku call
asked to read `apps/demo/bugs.json` was refused ("outside the working directory").

| Bug | Sonnet H7 | How |
|---|---|---|
| Shop 5. Cart total ignores quantity | 1/3 | Quantity 3 → line $36.00, total $12.00. |
| Shop 6. Invalid email at checkout | 1/3 | Typed `invalid@email`, got "Order confirmed". |
| Shop 7. Discount twice | 1/3 | Guessed `SAVE10`, double-clicked Apply, saw "×2" and $72.09. |
| Shop 8. Save changes does nothing | 1/3 (+1 dropped) | Saved, reloaded, saw the old name. In another run the judge dismissed the report: "nothing happened" is hard to see on one screenshot (the 1 correct-but-discarded). |
| Shop 9. $NaN | 3/3 | |
| Shop 10. Long name on mobile | 1/3 | Switched to 375 px on the long product's page. |
| Shop 11. Session after logout + reload | 0/3 | Never logged out and reloaded in the same run. |
| Shop 12. Wrong-password error placement | 1/3 | Typed a wrong password for the demo account. |
| Holdout 3. One night charged | 1/2 | |
| Holdout 4. Check-out before check-in | 1/2 | |
| Holdout 5. Double-click Book now | 0/2 | |
| Holdout 6. Room name on mobile | 0/2 | |

**False alarms are now real:** 3 on the clean shop and 1 on the clean holdout, all confirmed by
replay. Read one by one they are real behaviour of the "clean" builds, not hallucinations:
quantity 0 silently added as 1, the cart emptied by a reload, an empty display name saved,
a stale "Check-out must be after check-in" message after the dates were fixed. The benchmark
counts them as false alarms because they aren't in the planted list. Needs-me: decide whether
to fix them in the clean builds or list them as known, unplanted bugs.

**Weak spot found:** one shop run (1b473b32) finished after 26 steps saying its tools "were not
available", although its previous step (`set_viewport`) had worked. Most likely Sonnet in
`claude -p` tried to call a tool natively instead of answering with the JSON the adapter asks
for, and then chose `finish`. Dev-only
provider; noted, not fixed (verifying a fix would need another Sonnet run).

Sonnet finds what Gemma reaches but doesn't recognise (bugs 5, 8 and holdout 3, 4 are all
states Gemma reached in R3b). That supports the R3b conclusion: the gap is recognition.
