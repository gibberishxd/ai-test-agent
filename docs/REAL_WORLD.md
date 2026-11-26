# Real-world benchmark (run 8, N4)

Every earlier number comes from two demo apps we wrote ourselves, with bugs we planted. This
benchmark asks a different question: **does the agent find real bugs that real users reported in
real open-source web apps?** Each bug below was reported in the app's public issue tracker and
fixed in an identifiable commit. We run the app at the commit just before the fix, on this Mac
only, and point the agent at it.

> This file holds the answer key (issue links, the reporters' words, fix commits). Like the demo
> apps' `bugs.json`, it lives in the repo, which claude-cli can never read (it runs in a temp
> folder outside the repo; `outside_repo` is checked before every call).

## How the apps were picked

Criteria (the owner's): a license that allows local use; starts locally with npm or Docker with no
paid service or external account; a UI the agent can reach without complex setup; at least three
user-visible **functional** UI bugs in the public tracker, each fixed in an identifiable commit.
No security bugs, no purely visual bugs. Small, well-known apps that start fast were preferred.

Considered and not picked: Excalidraw and tldraw (canvas apps: the agent acts on DOM elements, not
on a drawing surface); Uptime Kuma (the app itself would contact public hosts); Linkding (adding a
bookmark fetches the bookmarked public page); Memos, Gitea, Vikunja (Go builds per commit: slow,
and their Docker images are per release, not per commit); Actual Budget (large install); TiddlyWiki
(kept as a reserve: zero install, but its tracker's fixes are harder to tie to single commits).

### 1. IT-Tools (`CorentinTh/it-tools`, GPL-3.0, ~41k stars)
A collection of ~80 small developer tools (converters, generators, formatters) in Vue 3 + Vite.
Everything runs in the browser: no backend, no account, no data to seed. `pnpm install && pnpm dev`
starts it in seconds. Its tracker has many functional bugs with "fix(tool): ..." commits that close
them. The bugs need judgement (a wrong conversion, an input that can't be edited, a panel that
vanishes), the kind the agent's AI-only recall measures.

| Bug | Issue (reporter's words, shortened) | Fixed by | Start page |
|---|---|---|---|
| IT-1 | [#274](https://github.com/CorentinTh/it-tools/issues/274) Roman numeral converter: "Add 'IVX' to 'Roman to Arabic' … You will see '4'. IVX is not valid roman numerical" | [8930e139](https://github.com/CorentinTh/it-tools/commit/8930e139b28f) (PR #332, 2023-04-08) | `/roman-numeral-converter` |
| IT-2 | [#402](https://github.com/CorentinTh/it-tools/issues/402) IPv4 address converter: "Try to edit IPv4" (the input can't be changed) | [7aed9c56](https://github.com/CorentinTh/it-tools/commit/7aed9c56fd06) (PR #403, 2023-05-15) | `/ipv4-address-converter` |
| IT-3 | [#652](https://github.com/CorentinTh/it-tools/issues/652) Encrypt / decrypt text: "Select RC4 as Encryption algorithm in the Decrypt container … you can make the whole container disappear" | [02b0d0d1](https://github.com/CorentinTh/it-tools/commit/02b0d0d1a13c) (PR #711, 2023-11-01) | `/encryption` |
| IT-4 | [#1365](https://github.com/CorentinTh/it-tools/issues/1365) "When on a tool, the favorite button is not working … it is not adding to favorite (on a tool only not on home page)" | [ae136393](https://github.com/CorentinTh/it-tools/commit/ae1363937bf3) (PR #1368, 2024-10-25) | `/token-generator` |

### 2. react-admin e-commerce demo (`marmelab/react-admin`, MIT, ~27k stars)
"Posters Galore", the admin app react-admin ships as its demo (`examples/demo`): orders, customers,
products, reviews, a dashboard. Its data is generated in the browser by the repo's own data
generator and served by a fake REST server in the page, so nothing leaves the Mac; sign-in takes
any user name (the login page offers `demo` / `demo`). Vite resolves react-admin's packages from
source, so `yarn install` then `yarn dev` in `examples/demo` is enough. These bugs live in a real
framework many companies build on, two of them reported against this very demo.

| Bug | Issue (reporter's words, shortened) | Fixed by | Start page |
|---|---|---|---|
| RA-1 | [#10192](https://github.com/marmelab/react-admin/issues/10192) "Go to the Orders list … click on the 'add filter' button and select the 'clear filters' dropdown … The list empties" (expected: all records) | [5fa05d4b](https://github.com/marmelab/react-admin/commit/5fa05d4ba037454a5a1256748c48983ce3794f5c) (PR #10193, 2024-09-10) | `/#/orders` |
| RA-2 | [#10136](https://github.com/marmelab/react-admin/issues/10136) "When navigating to the show page from the second page or later in a paginated list, the `PrevNextButtons` component should display the correct index" (it doesn't) | [22dae61e](https://github.com/marmelab/react-admin/commit/22dae61e51a880e9160cb7083f64d04849c04f78) (PR #10144, 2024-08-14) | `/#/orders` (the order page has the buttons) |
| RA-3 | [#9468](https://github.com/marmelab/react-admin/issues/9468) TabbedForm: "The tabs beyond the first one are not reachable, instead the first tab keeps being visible … the url keeps adding the index of the clicked tab" | [2bed8b22](https://github.com/marmelab/react-admin/commit/2bed8b2244a9d25ecf227e58f857639b7edc5e26) (PR #9480, 2023-11-29) | `/#/products` (a product's edit page is a TabbedForm) |

**Start page (decided without the owner, revisit):** each run starts on the page of the feature
the bug is in, with no description of the bug and no focus text, like a team asking for a test
of one feature after a change. Starting at IT-Tools' home page (80 tools) would mostly measure
whether 40 steps happen to open the right tool. The agent still has to find the trigger itself
(type an invalid numeral, pick RC4 in the right panel, page through orders, ...).

**Reserve:** IT-Tools [#283](https://github.com/CorentinTh/it-tools/issues/283) (OTP generator
rejects a lower-case secret, fixed by 7c40539e) and react-admin
[#10667](https://github.com/marmelab/react-admin/issues/10667) (dashboard chart in € with $
tooltips, fixed by 9d23f078), if a bug above doesn't reproduce.

## Method

**The answer key** is `apps/realworld/bugs.json`: per bug the issue link, a short description in
the reporter's terms, the fix commit, the start page and the port, and a "reach" rule (below).
It lives in the repo, which claude-cli can't read; the apps' clones live in
`~/ai-test-agent-realworld` (their git history holds the fixes), and `outside_repo` refuses that
folder too before every claude-cli call (a test checks). A prompt guard test fails if a bug's
title or an app's name appears in the agent's prompt or tools.

**Fetch and start** (`apps/realworld/realworld.py`): a blobless clone per app (git fetches only
the files a checkout needs), then one git worktree per bug at the fix's first parent, checked by
hash; install with the app's own package manager and lockfile (pnpm 8 for IT-Tools, pnpm 7 for
the March 2023 lockfile of IT-5, yarn 3/4 for react-admin); start the dev server on the bug's
port in its own process group; stop it by that PID. No Anthropic credential reaches the apps.
react-admin's demo at these commits needs Node 20 (its Vite config uses `assert { type: 'json' }`,
which Node 22+ rejects) forced to arm64 (the native modules were installed for arm64); RA-3's
older checkout also needs `ra-core` and the data generator built first.

**Does the bug reproduce?** (`apps/realworld/checks.py`) A short Playwright script per bug does
what the reporter did and checks what they saw, before any agent run. Kept:

| Bug | Check result at the fix's parent |
|---|---|
| IT-1 | `IVX` → `4`, not flagged as invalid |
| IT-2 | the IPv4 input has `readonly`; typing changes nothing |
| IT-4 | clicking the heart on a tool page stores `[null]`; the home page lists no favorite |
| IT-5 | `abcd` rejected ("Secret should be a base32 string"), `ABCD` accepted |
| RA-1 | 13–18 rows before "Remove all filters", 0 after, while the footer still says "1-25 of 600" |
| RA-2 | the 4th order of page 2 (position 29) shows "4 / 537" |

Dropped, with the reason:
- **IT-3** (#652, RC4 in the decrypt panel): the reported symptom, the panel disappearing, does
  not happen in headless Chromium at the fix's parent. Choosing RC4 throws an uncaught
  "Malformed UTF-8 data" error, the choice doesn't apply and the dropdown stays open, but the
  panel stays. Not the bug as reported, so not measured; IT-5 (the reserve) took its place.
- **RA-3** (#9468, TabbedForm tabs): at the fix's parent the demo's own `yarn.lock` resolves
  react-router 6.2.1, and the bug came with react-router 6.19+, which users got from fresh
  installs (the fix pins react-router below 6.19). In the repo's demo the tabs work. No
  replacement (time).

**A run** (`apps/realworld/measure.py`): Haiku 5.5 through claude-cli, the benchmark's settings
(480 s, 40 steps, interactive), in a "realworld" workspace with no saved login, starting on the
bug's start page with no focus text. The app's URL is passed as `LOCAL_APP_URLS`, which only in
dev mode counts as one of our own local apps (the network guard lets the browser reach it;
navigation can't leave it). The apps' own requests for web fonts and a login background image
(react-admin's demo: Google Fonts, Unsplash) are allowed, as for any site under test (D102).

**Scoring.** Each run's reports go through the benchmark's matcher with one known bug (the
judge is the pinned `ollama/gemma4:12b`, which sees the description; the agent never does):
- **found**: a report that survived verification (replay) and that the judge matched;
- **reached, not reported**: no such report, but the run did the trigger. "Did the trigger" is a
  rule per bug (an action of the right kind, on the right page, whose arguments or reasoning
  mention the trigger: typing on the Roman numeral page, a click mentioning "favorite", a click
  on the next page of orders, ...), checked by hand on every run;
- **never reached**: neither.
Every other report is listed and read by hand: some may be real bugs nobody planted.

## Results

Haiku 5.5 through claude-cli, commit 447c7fc, judge ollama/gemma4:12b, 40 steps / 480 s, start
on the feature's page with no hint. 10 runs on 2026-11-17 morning; a claude-cli usage limit
stopped them during IT-5; the remaining 8 (IT-5 ×2, RA-1 ×3, RA-2 ×3) ran the same afternoon on
the owner's go-ahead, same commit and settings. Raw rows: `apps/realworld/results.jsonl` (6
lines; the IT-5 line from the morning holds the two runs stopped with 0 steps, not counted).
18 runs, est. ~$2.2 API-equivalent on the Pro plan, $0 charged.

| Bug | Runs | Found | Reached, not reported (hand-checked) | Never reached | Automatic rule said |
|---|---|---|---|---|---|
| IT-1 Roman numerals accept invalid numerals | 3 | 0 | 1 | 2 | 3 |
| IT-2 IPv4 input can't be edited | 3 | 0 | 2 | 1 | 3 |
| IT-4 favorite button on a tool page | 3 | 0 | 0 | 3 | 0 |
| IT-5 lower-case OTP secret rejected | 3 | 0 | 3 | 0 | 3 |
| RA-1 "Remove all filters" empties the orders list | 3 | 0 | 0 | 3 | 3 |
| RA-2 prev/next position wrong after paging | 3 | 0 | 0 | 3 | 0 |
| **Total** | **18** | **0 (Wilson 95%: 0–18%)** | **6** | **12** | 12 |

**Found: none of the six real reported bugs in 18 runs** (IT-Tools 0 of 12, interval 0–24%;
react-admin 0 of 6, 0–39%), against 40% (shop) and 62% (holdout) on our own demo apps.
**The main open problem: in 6 runs the agent reached the real bug and didn't report it.**

**What happened, run by run (read from the saved steps, no model):**
- **IT-1, run fce7cc68 saw the bug and didn't report it.** It typed `IIII` into the Roman field,
  got `4`, and its own reasoning for that step was "a non-canonical numeral (IIII) that should be
  rejected or flagged, not silently accepted". It then reported other things. Runs 1c7a377b and
  98193f67 never typed a wrong combination of Roman letters (an `IIII` attempt failed on a stale
  element id). **All three runs reported "Roman to arabic shows NaN for ABC with no error
  message"**: the same root cause as the issue (the fix, 8930e139, adds validation of the Roman
  input, which also flags `ABC`), but a different symptom from the reporter's. The judge said
  no match; we keep the strict score, and note that a person reading these reports would have
  found the missing validation.
- **IT-2: the bug showed up as a tool error.** Typing into the IPv4 field timed out (Playwright's
  fill waits for an editable element, and the field is `readonly`). Run 6e35b438 hit this six
  times, then wrote "typing into the IPv4 field keeps timing out, so I'll focus it first and
  retry"; dda4708f hit it once. Both treated it as their own tool failing, not as the app's bug.
  Run 6432d4fb never reached the real field (stale element ids). They reported nearby bugs:
  "Editing the Decimal field does not update the IP address", "invalid hex/binary accepted with
  no error".
- **IT-4: never clicked the heart.** All three runs stayed on the token options and mobile layout;
  none clicked the favorite button, so the bug (nothing gets stored) never had a chance.
- **IT-5: saw the symptom and read it the other way.** Typing `jbswy3dpehpk3pxp` showed "Secret
  should be a base32 string" (the bug: lower-case base32 is valid). The agent took the app's
  message as correct and reported "OTP codes still shown for an invalid base32 secret".

- **IT-5, runs 2f138bb1 and c9917786:** the same as run 1: both typed a lower-case secret, saw
  "Secret should be a base32 string" and reported the app showing codes for an "invalid" secret.
- **RA-1: never did the trigger.** No run opened "Add filter" and chose "Remove all filters"; the
  automatic rule matched the word "filter" in URLs and reasoning. All three typed injection-style
  text into the orders search, which left the list filtered, and then reported status tabs and
  pagination "doing nothing" on that filtered list.
- **RA-2: never opened an order from page 2.** Two runs tried to page but believed the buttons did
  nothing (the same leftover search filter); none looked at the prev/next position.
- **react-admin replay is weak:** most react-admin reports were "could not replay". The demo
  regenerates its data on every page load, so a replay sees different orders (the agent's "order
  shows a different order after reload" is that, not a bug). Verified reports there: a blocked
  external image (`ERR_BLOCKED_BY_ORB`, our network guard), console JSON errors after the injected
  search, and mobile overflow on the order page.

**Other reports (not planted, read by hand).** Besides axe accessibility findings (the same 7–8
rules in every IT-Tools run), the agent reported: Arabic-to-Roman keeps a stale result for `0`,
`-5` and silently rounds `1.5` (plausible real input-validation gaps at that commit, not
checked against the tracker); a "Copy" button that resets the input (needs a look); mobile-width
overflow on the token generator; a clipboard `NotAllowedError` (headless Chromium has no
clipboard permission: our environment, a false alarm).

**What this suggests (not measured yet):** two cheap fixes would have turned two "reached" runs
into finds: (1) a fill that times out on a visible input is evidence of a read-only field and
should come back to the agent as "this input did not accept typing", not as a tool error; (2) the
agent's own "should be rejected" reasoning after an unexpected `ok` result should make it report.
The matcher question (same root cause, different symptom) is the owner's call.

## Stronger models (2026-11-18)

**Question:** is the 0 of 18 a Haiku problem? Same six bugs, same agent code, prompt, settings and
judge; only the agent model changes. Paid from the owner's Anthropic API credits (budget $3.50,
at most $0.80 per run), so Sonnet and Opus ran through the **real Claude API**
(`LLM_PROVIDER=claude`), not claude-cli. The helper model stayed `claude-haiku-5-5`, as in the
Haiku runs. Commit 152ef1c (agent code identical to 447c7fc), 40 steps / 480 s, start on the
feature's page, judge `ollama/gemma4:12b`. All six bugs re-checked first with their scripted
checks: all still reproduce. Raw rows: `apps/realworld/results.jsonl` (13 new lines).

**Order and budget:** one Sonnet run on IT-1 to measure cost ($0.183), then Sonnet on the other
five, a second Sonnet round on all six, then Opus on Sonnet's misses, hardest first (IT-1, IT-5,
IT-4, ...). Before each run a script read the charged cost of every Claude API run of the session
from the app's own records, set the run's cap to min($0.80, $3.50 − spent − $0.05) and started
only if that cap was at least 2× (Sonnet) or 1.5× (Opus) the model's average run so far. Opus cost twice what was
planned, so it got **one run** (IT-1); after it $0.47 was left, too little for a second Opus run
($0.78 each).

### Results per bug (hand-checked)

Found / reached the trigger but didn't report it / never reached. "Found" is strict, as for Haiku:
the reporter's symptom (see "Judge" below).

| Bug | Haiku 5.5 (claude-cli) | Sonnet 5.5 (API) | Opus 5.5 (API) |
|---|---|---|---|
| IT-1 Roman numerals accept invalid numerals | 3 runs: 0 / 1 / 2 | 2 runs: 0 / 0 / 2 | 1 run: 0 / 1 / 0 |
| IT-2 IPv4 input can't be edited | 3 runs: 0 / 2 / 1 | 2 runs: 0 / 2 / 0 | not run |
| IT-4 favorite button on a tool page | 3 runs: 0 / 0 / 3 | 2 runs: 0 / 0 / 2 | not run |
| IT-5 lower-case OTP secret rejected | 3 runs: 0 / 3 / 0 | 2 runs: 0 / 0 / 2 | not run |
| RA-1 "Remove all filters" empties the list | 3 runs: 0 / 0 / 3 | 2 runs: 0 / 0 / 2 | not run |
| RA-2 prev/next position wrong after paging | 3 runs: 0 / 0 / 3 | 2 runs: 0 / 0 / 2 | not run |
| **Total found** | **0 of 18 (Wilson 95%: 0–18%)** | **0 of 12 (0–24%)** | **0 of 1 (0–79%)** |
| Reached, not reported | 6 of 18 (16–56%) | 2 of 12 (5–45%) | 1 of 1 (21–100%) |
| Automatic "reached" rule said | 12 | 8 | 1 |

All three models together: **0 of 31 runs found a listed bug (0–11%)**. Stronger models did not
change the result. Sonnet got *less* far than Haiku (it reached the trigger in 2 of 12 runs
against 6 of 18), mostly because it stops early (below).

**Judge:** the judge matched two reports to IT-1: Sonnet run 406ca352's and Opus run fe2581ce's
"Roman to arabic shows NaN for invalid input ABC". It said **no** to the same report in all three
Haiku runs. `ABC` is not a numeral made of Roman letters; it has the reported bug's root cause and
fix (8930e139 adds Roman-numeral validation), not the reporter's symptom (`IVX` → `4`). To keep
the models comparable, both are scored like Haiku's: not found. The column "found, not in our
list" below counts them. The judge being inconsistent on near-identical reports is itself a
result: gemma4:12b is a noisy judge for same-root-cause reports.

### Why each run missed (read from the saved steps, no model)

Sonnet 5.5:
- IT-1, 96fa2403: **wrong input**: typed `MCMXCIV`, `ABC`, `4000`, `-5`; never a wrong combination
  of Roman letters. Reported "4000 gives MMMM" (real, see below).
- IT-1, 406ca352: **wrong input**: same set (`ABC`, `4000`, `4001`, `-5`); reported `ABC` → NaN
  (judge yes, scored no, see above).
- IT-2, e5b817fe: **didn't see the element**: its one fill on the real field timed out (the
  read-only bug), then the field was missing from its element list and it spent 30 steps
  scrolling and reloading to find it, until the step limit.
- IT-2, 9c691637: **didn't see the element**: the same; it ended with "the input can't be
  targeted, so there's nothing more I can test", the bug described as its own limitation.
- IT-4, 30895abc and 06e06875: **wrong input**: never clicked the heart; clicked the Refresh
  button and nav links. The first was ended by the loop detector, the second finished after 23
  steps "as I judged the remaining budget better left unspent".
- IT-5, f2084e08 and 74ffdfb4: **wrong input**: typed `!!!invalid 1`, an empty secret and the
  upper-case `JBSWY3DPEHPK3PXP`; never a lower-case secret.
- RA-1, 24a5e302 and 9aaf3549: **wrong input**: never opened "Add filter"; tested tabs, a customer
  form and an order page, then finished after 16–17 steps.
- RA-2, 5d5c5414 and 7962561f: **wrong input**: never paged and then opened an order; went to
  customer pages, then finished after 14–23 steps "to conserve the budget".

Opus 5.5:
- IT-1, fe2581ce: **didn't notice**: it typed `IIII`, saw `4`, and its reasoning for that step
  was "Invalid roman numeral should be rejected with an error"; then it typed `ABC` and reported
  that instead. The same miss as Haiku's run fce7cc68. Before that it lost ~20 steps switching
  between mobile and desktop, because IT-Tools' sidebar links fill the agent's 80-element list
  and push the converter's inputs out of it (**didn't see the element**).

**What changed with a stronger model:** the plans got better: Sonnet and Opus tested boundary
values and wrote precise expectations. The failures did not change: the same blind spots as Haiku's
(a timed-out fill on a read-only input read as a tool problem; its own "should be rejected" not
turned into a report), plus one new one. **Sonnet stops early:** a median of 17 agent steps out of
40 (10–40, 70–166 s), where Haiku used 26–40 (≈340 s). Its finish reasons cite the budget
("to conserve the budget", "remaining budget better left unspent"). With half the steps unused,
none of its RA-1, RA-2 or IT-4 runs got to the trigger.

### Other reports, checked by hand

**Found, not in our list (real):**

| Real bug | How it was confirmed | Haiku | Sonnet | Opus |
|---|---|---|---|---|
| IT-Tools Roman → Arabic: `ABC` shows `NaN`, no error | the fix 8930e139 adds Roman-numeral validation | 3 runs | 1 run | 1 run |
| IT-Tools Arabic → Roman: numbers above 3999 accepted (`4000` → `MMMM`, `5000` → `MMMMM`) | the same fix adds the 1–3999 range check, with a test for 4000 | 0 | 2 runs | 1 run |
| react-admin demo: an `&` in the orders search (`Tom & Jerry`) breaks the list with "Unterminated string in JSON" | reproduced by hand at the fix's parent; `+`, `#`, quotes alone are fine | 5 runs (console errors, same message) | 1 run | 0 |
| react-admin demo: a customer's "N orders" link counts all orders but opens the list filtered to `delivered` | the source (`visitors/Aside.tsx`), unchanged upstream; may be intended | 0 | 1 run | 0 |

None of these was checked against the trackers. The two react-admin ones are in the demo app (the
`&` one in its fake REST layer), not in the framework.

**Not real or not confirmed:** a clipboard `NotAllowedError` (headless Chromium has no clipboard
permission: our environment); the blocked Unsplash image (`ERR_BLOCKED_BY_ORB`: our network
guard); axe accessibility rules (real but generic, not counted); "OTP codes still shown for an
invalid secret" (unchanged upstream: the app's design); Sonnet's "Delivered tab shows 1-25 of 27"
(did not reproduce in three tries by hand: read before the list loaded); "invalid email gives no
error" (the browser's own validation bubble, which a screenshot doesn't show); mobile overflow on
the order page and the IT-Tools sidebar covering the page at 375 px (layout, not checked).

### Cost

| | Runs | Cost per run (range) | Total | Real-bug finds (verified; run × bug) | Cost per find | Distinct real bugs | Cost per distinct real bug |
|---|---|---|---|---|---|---|---|
| Haiku 5.5 (claude-cli, API-equivalent estimate, $0 charged) | 18 | $0.13 ($0.09–0.16) | est. $2.27 | 8 | est. $0.28 | 2 | est. $1.13 |
| Sonnet 5.5 (API, charged) | 12 | $0.18 ($0.09–0.37) | **$2.199** | 5 | $0.44 | 4 | $0.55 |
| Opus 5.5 (API, charged) | 1 | $0.78 | **$0.779** | 2 | $0.39 | 2 | $0.39 |

A find is one run reporting one real bug in a verified report (a report can cover two: Sonnet's
406ca352 named `ABC` → NaN and `4001` together).

**Total API spend this session: $2.977** of $3.50 (the app's own charged-cost records; no
usage, credit or billing message appeared). The Haiku row is claude-cli's list-price estimate,
which assumes 1-hour cache writes; on the real API Haiku costs about $0.02 a benchmark run (run 8).
Opus cost 4.3× Sonnet per run, not the 2× the prices suggest: it used every step (40, ending at
221 s) and wrote about 3× the output tokens of Sonnet's IT-1 runs (10.4k against 3.5k).

## Deep mode (run 9, 2026-11-26)

One deep run per bug on the two bugs RUN_PLAN_9 names, each starting on the tool's page with no
description of the bug: Sonnet 5.5 at effort high through the Claude Agent SDK on the owner's
Claude login (`DEEP_AUTH=cli`, $0 charged), 400 steps / 60 minutes, replays and duplicates judged
by claude-cli Haiku 5.5, matching by the pinned judge gemma4:12b, classified by
`apps/realworld/measure.py --engine deep` as before (rows in `results.jsonl`).

**Recognised the bug: 2 of 2** (Wilson 95%: 34–100%; one run per bug, so this shows deep mode can
recognise these bugs, not how often it does).

| Bug | Deep mode, Sonnet 5.5 (1 run) | Loop, Haiku 5.5 (3 runs: found / reached / never) | Loop, Sonnet 5.5 (2 runs) | Loop, Opus 5.5 (1 run) |
|---|---|---|---|---|
| IT-1 Roman numerals accept invalid numerals | **found** (250 steps, 478 s, est. $1.39) | 0 / 1 / 2 | 0 / 0 / 2 | 0 / 1 / 0 |
| IT-5 lower-case OTP secret rejected | **found** (270 steps, est. $1.97; paused once on the usage limit) | 0 / 3 / 0 | 0 / 0 / 2 | not run |

- **IT-1, run `a2840e6f`:** "Roman to arabic accepts malformed numerals (VX=5, IC=99, IIII=4)",
  confirmed by replay. The same run also reported both real Roman-numeral bugs from "Other
  reports" below: numbers above 3999 (`4000` → `MMMM`) and `NaN` for unrecognised input (`xlii`,
  `ABC`), each confirmed by replay. The fix 8930e139 covers all three.
- **IT-5, run `65860fc7`:** the report the judge matched is titled "Invalid secret still produces
  OTP codes, QR code and a hex value containing '-' characters", which leads with behaviour this
  page calls the app's design (unchanged upstream). Its body names the real bug: typing the lower-case
  secret `jbswy3dpehpk3pxp` gives "Secret should be a base32 string", and the expected result
  says "lowercase and '=' padded base32 (e.g. 'MZXW6===') are valid base32 but are rejected".
  Hand-check: recognised, though bundled with a design complaint. Whether a bundled report should
  count is the matcher question above (the owner's call).
- **IT-5's pause:** the run hit the owner's five-hour usage limit after 189 steps, paused with its
  report still a candidate, and was resumed after the reset; verification then confirmed it. The
  first row for this run in `results.jsonl` (status `paused`, outcome `found`) is provisional:
  scoring counts a paused run's unverified candidates as verified (OPEN_QUESTIONS 9). The
  second row (`rescored_after_resume: true`) is the result. Its `seconds` (244) cover only the
  resumed part.
- **Not counted as real:** the clipboard `NotAllowedError`, now reported by D121 as a
  deterministic finding in both runs (our headless browser has no clipboard permission,
  OPEN_QUESTIONS 8), and generic axe and console-warning findings, as for the loop.
- **Why this differs from the loop:** the loop's runs reached both bugs (IT-5 in 3 of 3 Haiku runs)
  but didn't report them. Deep mode, with a test plan, measurement and a review of each candidate,
  reported the state it reached. Two runs can't say how much of that is the model and how much
  the harness: the loop with Sonnet found neither, so the harness matters at least.

## Honest limits

- **Small:** 18 runs over 6 bugs in 2 apps; 0 of 18 means "probably under ~18%", not "zero".
- **Stronger models, smaller samples:** Sonnet 12 runs (2 per bug), Opus 1 run (IT-1 only).
  Sonnet and Opus ran through the API, Haiku through claude-cli: same prompt and tools, different
  transport (the CLI may set its own defaults); the API agent call uses effort `medium`.
- **The start page helps:** each run starts on the feature's page (D102); from the home page it
  would be harder.
- **The automatic "reached" rule over-counts** (12 vs 6 by hand); use the hand-checked column.
- **Strict scoring:** a report of the right root cause with a different symptom (IT-1's NaN)
  counts as not found.
- **react-admin's random data** breaks our replay, so verified reports there are few.
- **Not checked against the trackers:** whether the other reports are real, known bugs.
- **Judge noise:** gemma4:12b matched `ABC → NaN` for Sonnet and Opus but not for Haiku; the
  hand-check column is the one to trust.
