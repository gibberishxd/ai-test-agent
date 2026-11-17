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

Haiku 5.5 through claude-cli, commit 447c7fc, judge ollama/gemma4:12b, 40 steps / 480 s, 2026-11-17.
A claude-cli **usage limit** stopped the measurement during IT-5 (run 2 of 3). Following the run
rules, no retry: IT-5 runs 2–3, RA-1 and RA-2 were **not measured**. Raw rows:
`apps/realworld/results.jsonl`.

| Bug | Runs | Found | Reached, not reported | Never reached |
|---|---|---|---|---|
| IT-1 Roman numerals | 3 | 0 | 3 | 0 |
| IT-2 IPv4 input read-only | 3 | 0 | 3 | 0 |
| IT-4 favorite on a tool page | 3 | 0 | 0 | 3 |
| IT-5 lower-case OTP secret | 1 (2 stopped) | 0 | 1 | 0 |
| RA-1, RA-2 | not run (usage limit) | – | – | – |
| **Total** | **10** | **0 (Wilson 95%: 0–28%)** | 7 | 3 |

The agent found none of the real reported bugs in 10 runs. It did reach the trigger area in 7
runs and filed real-looking neighbouring bugs instead: "Roman to arabic shows NaN for ABC with no
error", "Arabic to roman keeps stale output for -5 / 0", "Editing the Decimal field does not
update the IP address" (close to IT-2 but not the read-only IPv4 input), "OTP codes still shown for
an invalid base32 secret" (near IT-5, the opposite direction). It never clicked the favorite
heart (IT-4). Most other reports are axe accessibility findings. The per-run "reached" labels
come from the automatic rule; checking them by hand is under "Needs me".

## Honest limits

- 10 runs over 4 bugs in one app; react-admin wasn't measured at all. 0/10 means "probably under
  ~30%", not "zero".
- The automatic "reached" rule is coarse (typing on the right page counts); not yet hand-checked.
- Start pages are the feature's page (D102), which helps the agent; the home page would be harder.
- Several reports (NaN for invalid input, stale results) may be real unreported bugs; not yet
  checked against the app's tracker.
