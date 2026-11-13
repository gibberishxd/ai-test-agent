# Progress: Demo v1

Milestones from `docs/PRODUCT_BRIEF.md`, in order. Status: todo / in progress / done /
done (local model) / blocked.

| # | Milestone | Status | Acceptance check result |
|---|---|---|---|
| M1 | Demo shop: 12 planted bugs, injection text, clean build on 5174, bugs.json | done | `npm run verify-bugs`: 26/26 passed (12 bugs present on 5173 and absent on 5174, injection text on both) |
| M2 | Data model + run queue, LLMClient (Fake, Claude, Ollama) | done | Inserted a queued run with SQL, `LLM_PROVIDER=fake uv run worker --once` claimed it and marked it `done` (provider=fake, claimed, finished). 52 worker tests pass. |
| M3 | Deterministic checks + passive scan, safety 6.1/6.2/6.6 | done | `uv run worker scan`: buggy shop (11 pages) → 5 bugs covering bugs 1, 2, 3, 4, each with evidence; clean shop (11 pages) → 0 bugs. SSRF guard tests pass (incl. redirect to 10.0.0.5 blocked). 115 worker tests. |
| M4 | Agent loop: safe mode, budgets, loop detection, injection, cost, caching | done (local model) | qwen3-vl:8b-instruct on the buggy shop, 3 runs: bugs 5–12 reported **0 of 8** (needs ≥ 4). Final run reached the state of bug 5 (cart shows 2 × $12, total $12) but the model didn't report it. Injection test: the agent kept testing on the injected page (didn't give up or claim no bugs) but reported no bugs → fails on the "reports bugs" half, for the same model-quality reason. Cost recorded per step and run ($0 on Ollama). All safety/budget/loop behaviour verified by 30+ unit tests. See D16, D20, D21 and Needs me #3. |
| M5 | Replay verification + dedup | done (local model) | Clean shop, local model: interactive run 0 candidates, passive run (6 screenshots reviewed) 0 candidates → false alarms 0 before and 0 after replay, so "lower than M4" can't be shown. On the buggy shop replay dismissed 2/2 false reports (run 2). Replay, verdict and dedup logic covered by unit + integration tests. Real comparison needs Claude: Needs me #3. |
| M6 | Web app core: landing, dashboard, run form, live run, report, history | done | `npm run test:e2e`: 3/3 passed. Main flow (dashboard → start run on the demo shop → live page → report with bug cards, export buttons, Download JSON) in 11.7 s with the worker on FakeClient; plus form validation and the interactive-mode guard. Pages checked at 1280 px and 375 px (no sideways scroll), light and dark, no console errors. |
| M7 | Benchmark script + benchmark page | done | `npm run bench` (ollama, qwen3-vl:8b-instruct, 3 buggy + 1 clean run): recall 33% (bugs 1–4 found 3/3, bugs 5–12 0/3), precision 100%, false alarms 0.0, cost $0.000, 335 s/run. First run showed 0% because the matcher rejected `"match": "2"` (string); fixed test-first, rescored with `bench --rescore`. Benchmark page shows tiles, charts (validated palette), per-bug table, match log. |
| M8 | B2B foundations: auth, workspaces, domain verification, quota, audit, share links | done | 11 database tests pass (`lib/b2b.db.test.ts`): workspace isolation, domain verification, quota, share links, visitor limits. Sign-in as demo user → settings → add domain → sign out checked in a real browser. |
| M9 | Polish: README, walkthrough, states, 375 px | done | README (what it is, screenshots, Mermaid architecture, how to run, safety model, cost engineering, benchmark table, how AI tools were used); WALKTHROUGH covers all 16 components; empty/loading/error states on every page; all pages checked at 375 px (no sideways scroll) and in dark mode. `npm test` exit 0 (web 64 incl. 11 DB tests, demo 7, worker 176 + 1 live-model skip), `npm run lint` exit 0, `npm run test:e2e` 3/3. Committed and pushed. |

Already done before demo v1 (branch `phase-1-checker`, merged into `demo-v1`): report models,
URL helpers, BFS crawler, Playwright page visits, local test-site fixtures. 25 worker tests.

## Local model comparison (2026-11-10, after demo v1)
`npm run bench` with `OLLAMA_MODEL` overridden, 3 buggy + 1 clean interactive runs each.

| Model | Recall | Precision | False alarms | Avg run | Agent steps used | Bugs found |
|---|---|---|---|---|---|---|
| qwen3-vl:8b-instruct (commit e8d3a24) | 33% | 100% | 0.0 | 335 s | not recorded (480 s limit) | 1–4 (deterministic) |
| gemma4:12b (commit e78a2ca) | 42% | 90% (100% after the matcher fix, D29 era rescore) | 0.0 | 522 s | about 24 of 40 (480 s limit ended every run) | 1–4 + **9** (agent, 3/3 runs) |
| gemma4:12b, `MAX_RUN_SECONDS=1200` (code of commit 18e1975) | 42% | 100% | 0.0 | 1101 s | 40, 40, 40 of 40 on the buggy shop; 38 on the clean shop | 1–4 + **9** (agent, 3/3 runs) |

The third row answers "was the time limit the problem?": no. With all 40 steps the agent
still found only bug 9. The result row in the database is labelled commit c6fb2e3 (HEAD when
scoring ran), but the process had loaded the code of 18e1975, before the loop-detector,
off-site and deny-list changes. The judge was the model under test (gemma4:12b).

Bug 9 ($NaN price) is the first bug found by the model rather than the deterministic checks.
The 2 unmatched reports were "Cart price and total displayed as NaN" on `/cart`, which is bug 9
seen on another page; the matcher filters candidates by page, so bug 9 (listed on `/`) wasn't
considered. Real false alarms: 0. Matcher change is open (owner's call).

## G6 measurements (run 2)

Benchmark at commit 8453aea (agent code of run 2 up to G3), gemma4:12b agent, **judge pinned to
ollama/gemma4:12b**, 480 s per run. Shop: 3 buggy + 1 clean; holdout (apps/demo2): 2 buggy + 1 clean.

| Set | AI-only recall | Recall | Precision | False alarms | Avg run |
|---|---|---|---|---|---|
| Shop | 0% | 33% | 100% | 0.0 | 490 s |
| Holdout | 0% | 33% | 100% | 0.0 | (same runs' average) |

Rerun after the D52 fixes and the spinbutton fix (commit 21e5669, same settings): shop AI-only
**4%** (bug 9 in 1 of 3 runs), recall 36%, precision 100%, 0 false alarms; holdout AI-only 0%,
recall 33%, precision 100%, 0 false alarms; 501 s per run.

Compared with the earlier Gemma rows (AI-only 13%, bug 9 in 3/3 runs): bug 9 went to 0/3. The
steps show why (D52): the agent noticed the "$NaN" price but wrote it in a `note` instead of
reporting it; it found bug 8 ("Save changes does nothing") for the first time, but replay
dismissed it because a step of an earlier flow couldn't be repeated; and one step was wasted
on `element_id: "[10]"`. Fixed generically in commit 0124950 (D52). The holdout scored the same
as the shop (only its 2 deterministic bugs), so there is no sign of shop-specific tuning, and
no sign yet that the AI part helps a 12B model.

### One run with Claude Sonnet through `claude -p` (G6.2)

`LLM_PROVIDER=claude-cli` (Sonnet for decisions, the owner's Pro plan, $0 recorded), one
interactive run on the buggy shop at commit 0124950, reports matched by the pinned local judge
(ollama/gemma4:12b). Run be495c9f: 40 agent steps, 302 s, stopped by `finish`.

- **Found (after replay):** bugs 1–4 (deterministic checks) and **9** ("Wool Socks price shows
  $NaN") → AI-only 1 of 8 (13%), overall 5 of 12 (42%), 7 reports, all matched (precision 100%).
- **Reported but dismissed by replay:** "Cart total ($89.00) doesn't match line price" (bug 5's
  kind), "Profile 'Save changes' does nothing" (bug 8), and two quantity edge cases (a huge and a
  fractional quantity accepted, which are not planted bugs). All four were dismissed with
  "could not replay: type: no textbox "Quantity" on the page".
- **What that means:** Sonnet used the charter (boundary values, double_click, reload, mobile
  viewport) and saw two more planted bugs than any local model; the verifier lost them.
  Replaying the same steps on their own afterwards succeeds step by step, so the fault is in
  the replay environment during the run, not the steps. One cause was fixed (number inputs are
  "spinbutton", commit a970ceb); the exact cause of the in-run failure isn't pinned down yet
  (see Needs me).

## Run 2 (branch `agent-v2`, plan in `docs/RUN_PLAN_2.md`)

| Goal | Status | Check |
|---|---|---|
| G0 Finish what's running | done | Benchmark finished and recorded above. Transcripts are git-ignored. The two runs queued from the dashboard were processed with `uv run worker --once` (gemma4:12b): 92cc0e45 done (35 steps, 6 bugs), 99e6cd3c done (33 steps, 7 bugs), both stopped by the 470 s time budget. |
| G1 Safety and correctness fixes (1–6) | done | Worker `uv run pytest`: 241 passed, 1 skipped. Web `npm test -w apps/web`: 79 passed. Web typecheck and worker ruff clean. Decisions D32–D37. |
| G2 Findable bugs (1–5) | done | Worker `uv run pytest`: 281 passed, 1 skipped; ruff clean. New tests: `test_observe.py`, `test_prompt.py`, `test_replay_plan.py`, `test_review.py`, new cases in `test_agent_loop.py`, `test_verify.py`, `test_passive_run.py` (incl. six identical "Add to cart" buttons). Decisions D38–D41. |
| G3 Honest benchmark (1–4) | done | Root `npm test`: web 84, demo 7, demo2 3, worker 288 passed + 1 skipped; `npm run lint` clean; new `test_benchmark_db.py` (AI-only, holdout columns, judge, rescore keeps commit) and cases in `test_benchmark.py`. Web `npm test -w apps/web`: 84 passed (page helpers). `npm run verify-bugs -w apps/demo2` (from `apps/demo2`: `npx playwright test --repeat-each 3`): 36 passed; shop `verify-bugs`: 26 passed. Migration `20261110120000_honest_benchmark` applied. Decisions D42–D44. |
| G4 Live browser pane | done | Unit: `lib/live-pane.test.ts` (box scaling, clipping, frame selection) + worker tests for the before-action screenshot and box. `npm run test:e2e`: 5 passed (28.5 s) incl. "the live browser pane shows the agent's screen and outlines what it clicks" (screenshot visible during the run, outline drawn for the click step). CI `e2e` job: success (run 42856919017). D45. |
| G5 Any model (1–5) | done | Worker `uv run pytest`: 321 passed, 1 skipped (`test_openai_compat.py` with recorded fixtures, `test_claude_cli.py`, `test_secret_box.py`, `test_run_models.py`, provider tests in `test_llm.py`). Web `npm test -w apps/web`: 120 passed (`secret-box`, `model-probe`, `model-configs`, `run-form`, leaderboard, and DB tests: key encrypted at rest, never in API views or console logs, workspace B can't list, change, delete or run with A's model, untested models refused). Typecheck clean. D46–D50. |
| G6 Measure (1–3) | done | Gemma benchmark (shop + holdout, judge pinned to gemma4:12b): shop AI-only 0%, recall 33%; holdout AI-only 0%, recall 33%; precision 100%, 0 false alarms (table above, D52 for why). Exactly one claude-cli (Sonnet) run on the buggy shop: AI-only 13%, recall 42%, 40 steps, 302 s; two more planted bugs reported but lost in replay (Needs me #0). The full claude-cli benchmark is listed under Needs me on purpose. The Gemma rerun after the fixes (21e5669): shop AI-only 4%, holdout 0% (table above). |
| G7 Project hygiene | done | ESLint: 105 web + 22 shop + 14 holdout files, 0 findings; root `npm run lint` exit 0. CI run 42856919017: typescript (now with ESLint) success, python success, new e2e job (verify-bugs for both apps + 5 e2e tests, FakeClient) success. D51. |
| G8 Wrap-up | done | README: "bring any model" positioning, live pane section with a fresh screenshot (`docs/screenshots/live-pane.png`), leaderboard, holdout explanation, updated results table, safety model. Root `npm test` exit 0 (web 120, demo 7, demo2 3, worker 330 passed + 1 skipped); root `npm run lint` exit 0; CI green on agent-v2. WALKTHROUGH covers every part touched; DEVLOG entry added. Dev servers, demo apps and worker stopped at the end; Ollama left running. |

The run stopped early because the Claude usage limit was reached. Root `npm test`,
`npm run lint` and CI on `agent-v2` were not checked.

## Run 3 (branch `agent-v3`, plan in `docs/RUN_PLAN_3.md`)

| Goal | Status | Check |
|---|---|---|
| H0 Plan | done | `docs/RUN_PLAN_3.md` committed; root `npm test` (web 120, demo 7, demo2 3, worker 330 + 1 skipped) and `npm run lint` exit 0 on `agent-v3` before any change. |
| H1 Replay fix | done | New failing-first tests: `test_replay_isolation.py` (two+ replays in one run: no leftover cart, no leftover viewport, failure reason stored; read-only re-verify), late-drawn routes and failure kinds in `test_verify.py`, errored steps in `test_replay_plan.py`. Offline re-check of run be495c9f below. D53. |
| H2 Verification funnel | done | Failing-first tests: funnel, before/after recall, correct-but-discarded, bugs lost, false alarms before/after, stage of a stored bug, printed output (`test_benchmark.py`), saved details and matching of discarded reports (`test_benchmark_db.py`), web `verification()` (`lib/benchmark.test.ts`). Shown in `bench` output, the leaderboard (reported → verified, correct but discarded) and each latest-score card. D54. |
| H3 Sign-in flake | done | `node e2e/signin-loop.mjs 50`: before 2 of 50 (and 4 of 60) landed on `/signin`; after 0 of 50, 0 of 50 with 4 in parallel, 0 of 50 after a dev-server restart. `e2e/signin.e2e.ts` failed first (two `/api/auth/session` calls before the click). Retry helper and CI `retries` removed. D55. |
| H4 Database hardening | done | `test_queue_concurrency.py`: 8 concurrent workers × 300 runs, each claimed exactly once; lease tests (starts at claim, expired → failed by another worker, long live run untouched, heartbeat renews, late worker can't undo). `scripts/db_perf.py` on 10k runs / 500k steps: one index added (`benchmark_results(created_at)`, 0.87 → 0.09 ms), all other hot queries already indexed. Migrations `20261111010000_run_lease`, `20261111020000_benchmark_results_newest` (Prisma `migrate diff` against a migrated database: no difference for them), SQLAlchemy mirror, drift test now checks hot-query indexes. `docs/DATABASE.md`. D56. |
| H5 CI cleanup | done | `actions/checkout@v7`, `actions/setup-node@v7`, `astral-sh/setup-uv@v10.3.3` (Node 24). CI run 42912487613: all three jobs green; the only annotation left is GitHub's notice about the `ubuntu-latest` label, no Node 20 deprecation. D57. |
| H6 Make the agent find more | done | `docs/MISS_ANALYSIS.md` (every AI-only bug, every Gemma run, why missed). Generic changes, failing-first tests: D58 (`element_id: [10]`, commit read before runs), D59 (untried charter techniques in each observation, `test_charter_coverage.py`), D60 (note result says notes aren't reports), D61 (failed model call ends the run cleanly). Re-measured R3a and R3b below: shop AI-only 8% both, holdout 0% both (no drop). |
| H7 One Sonnet benchmark | done | Empirical check first: a Haiku call started as the worker starts it (temp folder, `--restricted`, Read allowed) was refused when asked for `apps/demo/bugs.json`; the `outside_repo` guard runs before every call. Then exactly one `LLM_PROVIDER=claude-cli uv run worker bench` (shop 3 + clean, holdout 2 + clean, 480 s, judge gemma4:12b), no usage limit hit. Table below, D62. |
| H8 Wrap-up | done | README results table (run-3 rows), WALKTHROUGH (run-3 measurements), PROGRESS (this table, Needs me), DECISIONS D62, DEVLOG entry; root `npm test` (worker 372 passed + 1 skipped) and `npm run lint` exit 0; pushed to `agent-v3`, nothing merged; demo and web servers stopped, Ollama left running. |

### H1: run be495c9f re-checked offline (`uv run worker reverify be495c9f [--judge]`)

| Agent report (Sonnet, run be495c9f) | Recorded in run 2 | Replay now | Judge now (gemma4:12b) |
|---|---|---|---|
| Wool Socks price shows $NaN (bug 9) | confirmed | replays | confirmed |
| Quantity 0 accepted | dismissed (judge: field shows 1) | replays | confirmed |
| Huge quantity accepted | could not replay | replays | confirmed |
| Cart total doesn't match line price (**bug 5**) | could not replay | replays | confirmed |
| Profile "Save changes" does nothing (**bug 8**) | could not replay | replays | confirmed |
| Fractional quantity 1.5 accepted | could not replay | replays | confirmed |

The stored run isn't changed (its verdicts came from Sonnet; the re-check uses the pinned local
judge). No previously verified report is lost: all 16 confirmed agent reports of 11 older runs
(804c2a85, 99e6cd3c, 92cc0e45, db550019, cbc7ca2c, 28a9bd8f, 6657cffb, edf089fb, ecbd578c,
4873e406, 54b934f1) still replay.

### H6: Gemma 4 12B re-measured (same settings as run 2's 1200 s row, judge ollama/gemma4:12b)

| Run | Agent code | Shop AI-only | Shop recall | Holdout AI-only | Holdout recall | Precision | False alarms | Correct but discarded | Avg run |
|---|---|---|---|---|---|---|---|---|---|
| Run 2, G6 rerun | 21e5669 (480 s) | 4% | 36% | 0% | 33% | 100% | 0.0 / 0.0 | not measured | 501 s |
| Run 3, R3a | f1bf08a, replay fix (row corrected from 984755e in run 4, D63) | **8%** (bug 8 in 2/3) | 39% | 0% | 33% | 100% | 0.0 / 0.0 | 0 (18 + 8 reports, none discarded) | 1083 s |
| Run 3, R3b | 984755e, + D58–D60 (untried techniques, notes aren't reports) | **8%** (bug 9 in 2/3) | 39% | 0% | 33% | 100% | 0.0 / 0.0 | 0 (17 + 8 reports, none discarded) | 1075 s |

R3a's result row `a4d5781c` was scored by the old code; `1eccde57` is its `--rescore` with the
funnel (same runs, same judge). Why each bug was found or missed: `docs/MISS_ANALYSIS.md`.

R3b (result row `f06138df`): 3 of 7 runs ended early on an Ollama `ReadTimeout` (a single model
call over 300 s): shop 9590b85f, holdout ab273f55, clean holdout 746e58ee. They are still
counted as runs, so R3b's AI-only numbers are slightly pessimistic. The numbers hardly moved,
but what's behind them did: Gemma now used double click, reload and the mobile viewport in
every run that lived (0 times in 11 earlier runs) and reached 7 of the 12 AI-only bug states
(1 before), yet reported only bug 9. Holdout didn't drop, so D59/D60 stay.

### H7: one Sonnet benchmark through claude-cli, compared with be495c9f

| Run | Shop AI-only | Shop recall | Holdout AI-only | Holdout recall | Precision | False alarms (shop / holdout) | Correct but discarded | Avg run |
|---|---|---|---|---|---|---|---|---|
| be495c9f (run 2, one shop run, old replay) | 13% | 42% | not run | not run | 100% | not measured | 4 reports lost in replay (bugs 5, 8) | 302 s |
| H7, result `f6151b32` (commit a8a6d13) | **38%** | **58%** | **25%** | **50%** | 96% / 100% | 3.0 / 1.0 | 1 (bug 8, judge said no) | 222 s |

Funnel: shop 35 reported → 28 verified (5 duplicates, 2 discarded at replay), holdout 11 → 10.
Runs: shop 99bd8afb, 1b473b32, d63e628c, clean a345d91b; holdout d6ff4d1c, 55592705, clean
28db5b07. The false alarms are real behaviour of the clean builds, not hallucinations (see
Needs me). Per bug: `docs/MISS_ANALYSIS.md`.

## Run 5 (branch `agent-v5`, plan in `docs/RUN_PLAN_5.md`)

| Goal | Status | Check |
|---|---|---|
| K0 Housekeeping | done | `agent-v5` from `agent-v4`; RUN_PLAN_5.md; demos and worker start; baseline `npm test` + `npm run lint` exit 0. PR question asked; nothing done to PRs yet. |
| K1 Before/after replay | done | `page_state.py` + `verify_bug` judge the change made by the last replayed action (D80); 50+ new tests incl. clock, spinner, polling, toast, dialog. Offline re-check (MISS_ANALYSIS "Run 5, K1"): all 7 rejected bug-8 reports verify; no clean-build report was ever dismissed, so none can become a new false alarm. |
| K2 Reviewer tier + list → detail | code done, measuring | `REVIEWER_PROVIDER`/`REVIEWER_MODEL` (any provider) decide on flagged steps and the explorer's reports; reviewer tokens/cost in `runs.reviewer_*`; per-list "open one item" reminder + charter item 9 (D81, D82). Benchmarks: see K6 rows. |
| K3 Database rules | done | Roles ata_owner/web/worker (none superuser or BYPASSRLS); every web query through the tenant client, worker per-run tenant; justified bypasses as narrow functions; audit/updated_at/triage triggers, claim/quota/retention functions, two views, CHECKs; tested as each role (D83, D84; DATABASE.md). |
| K4 Plans and usage | done | `plans`, `usage_events` (trigger, explorer/reviewer apart), plan-aware `consume_quota`, seats, retention cap; /settings/usage and /admin/usage (`worker make-admin`, `set-plan`); ROADMAP "Billing" (D85, placeholders). |
| K5 First-run path | done | Dashboard "Getting started" (workspace → target → model → run → report, from the database); dev-only "create a test account" sign-up standing in for an email link; the unverified-domain error says where to verify; `e2e/first-run.e2e.ts` covers sign-up to report (9/9 e2e locally, with web and worker on their own database roles); fixed on the way: concurrent first sign-ins, the e2e fake model's script shared between runs, Free-plan limits on the dev demo account. Fresh screenshots via `e2e/screenshots.mjs`. |
| K6 Measure | done | Gemma alone (default setup) `8546919c`: shop AI-only 7%, recall 36%, 0 false alarms; holdout 0% / 33% / 0. With the qwen3:14b reviewer `dbc3482e`: shop 19% / 44% / 0, holdout 0% / 33% / 0 (bug 13 found 3/3, first time). Gemma+Gemma reviewer `14203d1f`: 0% / 0%, holdout false alarms 1.0. Sonnet not run (no yes); no API calls (`API_BUDGET_USD` 0). Leaderboard rows per reviewer (materialized view). MISS_ANALYSIS "Run 5". |
| K7 Wrap-up | done | README (run 5 section, results, screenshots), WALKTHROUGH (K1–K5 with Q&A), PROGRESS, ROADMAP, DATABASE (every object, roles, ER diagram from the schema), DECISIONS D80–D87, DEVLOG; tests and lint green; e2e 9/9 locally; pushed, nothing merged; servers stopped by PID, Ollama running. |

## Run 4 (branch `agent-v4`, plan in `docs/RUN_PLAN_4.md`)

| Goal | Status | Check |
|---|---|---|
| J0 Housekeeping | done | PR #2 (agent-v3 → main) open; R3a rows corrected to f1bf08a with a note (D63); RUN_PLAN_4.md, ROADMAP.md. |
| J1 Recognise wrong states | done (kept) | `test_expectations.py`, `test_model_resilience.py`, CLI correction test; Gemma: holdout 0% → 0%, clean false alarms 0.0 → 0.0, shop 8% → 8%; 23 mismatches flagged, 19 dismissed (MISS_ANALYSIS, D64–D66). |
| J2 Apps behind a login | done | `test_login.py`, `test_signed_in_run.py` (no credential anywhere in rows or model calls), web unit + DB tests, e2e `login-setup.e2e.ts` (D68). Demo shop: `/orders` behind the login with planted bug 13; verify-bugs both builds; the shop benchmark signs in with a saved setup (D75). |
| J3 Run it from CI | done | key, rate limit, routes, OpenAPI and webhook tests; `ata-run.mjs` against the local app exited 1 with a JUnit file (D69, D70). |
| J4 Bugs across releases | done | `test_fingerprint.py`, `test_triage.py`, `triage.db.test.ts`; run page shows New / Still present / Fixed and triage (D72). |
| J5 Teams and isolation | done | `roles.test.ts` (the whole table), `route-roles.db.test.ts` (every protected route × every role), `members.db.test.ts`, `rls.db.test.ts` (no WHERE → own rows only; cross-workspace writes fail; unset workspace sees nothing), partial unique index test; RLS cost +0.004–0.03 ms per query (D73, D74). |
| J6 Production readiness | done | Images (web 319 MB, worker 3.2 GB with Chromium); `docker-compose.prod.yml` up locally: migrations once, web ready, 2 workers. A Gemma run started via `/api/v1` with an API key: done in 494 s, 11 pages, 20 agent steps, 6 findings confirmed (incl. planted bug 8 by the agent); 42 screenshots in the object store, served through a presigned link (302 → 200 image/png; 404 without access). Health, ready, metrics answer; JSON logs carry `run_id`. Actions pinned by SHA. `docs/DEPLOY.md` with a threat model (D76, D77). |
| J7 Measure | done (Gemma only) | Gemma 12B full benchmark `bd88e166`: shop AI-only 0% (7% before verification: bug 8 reported twice, dismissed by the gemma judge), holdout 0% / 33%, 0 false alarms; signed-in runs reached `/orders` and logout was refused 3 times. The Sonnet run was not made: the owner didn't approve it today (rule: only with a yes). |
| J8 Wrap-up | done | README (pipeline section, run-4 rows), WALKTHROUGH (one section per goal with Q&A), PROGRESS (this table, Needs me with exact steps), ROADMAP (what moved), DECISIONS D63–D78, DEVLOG; `npm test` and `npm run lint` exit 0; e2e 8/8 locally; CI green (typescript, python, e2e; browser jobs in Playwright's images, D79); pushed, nothing merged; servers and the production stack stopped, Ollama left running. |

### Run 4 measurements (Gemma 4 12B, judge gemma4:12b, 1200 s)
| Run | Agent code | Shop AI-only | Shop recall | Holdout AI-only | Holdout recall | False alarms | Correct but discarded | Avg run |
|---|---|---|---|---|---|---|---|---|
| Run 4, J1 (`bea561fa`) | a0af21e, expected vs. actual | 8% (bug 8 in 2/3) | 39% | 0% | 33% | 0.0 / 0.0 | 1 | 1156 s |
| Run 4, J7 (`bd88e166`) | b114b43, everything in run 4; shop signed in, 13 bugs (bug 13 behind the login) | 0% (7% before verification) | 31% (33% without bug 11) | 0% | 33% | 0.0 / 0.0 | 2 (bug 8 twice, the judge said no) | 1277 s |

## Needs me
0. **Run 5 (branch `agent-v5`, nothing merged):**
   - **PRs (answered):** #2 and #3 (`agent-v5` → main) were merged by the owner on 2026-11-12;
     #4 holds the commits pushed after #3 (measurements, settings UI fixes, docs). Not merged.
   - **Sonnet (K6):** the owner said no for now. To run it later with the same settings as
     f6151b32 plus bug 13: `cd apps/worker && LLM_PROVIDER=claude-cli uv run worker bench
     --holdout-first` (~30 minutes of the Pro limit).
   - **API budget:** `API_BUDGET_USD` was 0, so no Claude API call was made. With a budget, the
     first step is one smoke run through `ClaudeClient` (LLM_PROVIDER=claude), then a benchmark
     with a Claude reviewer behind Gemma (`REVIEWER_PROVIDER=claude REVIEWER_MODEL=...`).
   - **Plans (D85, decided without you, revisit):** placeholder limits and prices: Free 30 runs,
     40 steps, local models, 3 seats, 7 days; Team 300/80/any/10/30; Business 2000/150/any/50/90.
     Change them in a migration (or tell me the numbers). `worker set-plan <slug> <plan>` moves a
     workspace.
   - **Platform admins:** `cd apps/worker && uv run worker make-admin you@company.com`, then
     /admin/usage.
   - **Dev database roles:** `.env` now has `WEB_DATABASE_URL` / `WORKER_DATABASE_URL` (dev-only
     passwords, set by `npm run db:roles`). A fresh clone: `npm run db:migrate && npm run
     db:roles`, then copy those lines from `.env.example`.
   - **Production stack:** `.env.prod` needs `DB_WEB_PASSWORD` and `DB_WORKER_PASSWORD` (long
     random values); the migrate job sets them on the roles.
   - **Still yours from earlier runs:** bug 7's hidden code, the cart emptied by a reload,
     quantity 0 → 1, and the matcher offering only bugs listed on a report's own page (bug 9's
     "$NaN" seen on /cart doesn't count).
0. **Run 4 (branch `agent-v4`, nothing merged):**
   - **Merge PR #2 (`agent-v3` → main)**, then tell me: I rebase `agent-v4` onto main
     (`--force-with-lease`, the one allowed exception) and open its PR.
   - **Your questions from this morning** (DECISIONS D73 and D75 record what I chose, marked
     "decided without owner, revisit"): (1) the Sonnet run: not run today without your yes; to
     run it: `cd apps/worker && LLM_PROVIDER=claude-cli uv run worker bench` (same settings as
     f6151b32; about 30 minutes, uses your Pro limit); (2) the login-only bug: order history
     shows the next order; (3) shop benchmark signed in, logout denied (bug 11 unreachable);
     (4) false-positive counts per workspace only, no global numbers yet; (5) role permissions.
   - **Every web query through the RLS client.** The run page, run lists, API reads and settings
     lists use `tenantDb`; other queries (writes, some settings and auth paths) still use the
     plain client with their WHERE. Do: replace `db.` with `tenantDb(workspaceId).` in
     `lib/*.ts` data functions one file at a time; `rls.db.test.ts` shows the pattern.
   - **Production database role:** create a non-superuser role that owns the tables and is
     granted `app_tenant` (docs/DEPLOY.md, "On a managed platform"); otherwise RLS can be bypassed.
   - **Email for invitations and magic links** (a provider, small cost): invitation links are
     copied by hand today.
   - **Pick a production object store** (S3, R2 or self-run SeaweedFS/MinIO); only `S3_*` change.
   - **Unchanged from run 3:** bug 7's hidden code, the cart emptied by a reload, quantity 0 → 1
     (your product decisions; untouched).
0. **Run 3 (branch `agent-v3`, nothing merged):**
   - **Review and merge.** `agent-v3` is based on `agent-v2`; neither is merged into `main`.
   - **Bug 7 needs the code `SAVE10`, which the shop never shows.** Sonnet guessed it once in
     three runs (H7); Gemma never does. Choose: show a code on the site (a banner, as real shops
     do) or keep it as a "guess a common code" bug. Either way, compare models on the same
     version. `docs/MISS_ANALYSIS.md`.
   - **The clean builds had real, unplanted bugs** that Sonnet found and the benchmark counted
     as false alarms (H7: 3.0 per clean shop run, 1.0 on the clean holdout). The two clear ones
     are fixed, with unit and browser tests: an empty display name is now refused, and a date
     error clears once the field is edited. Left as intended behaviour, still open for you: a
     reload empties the cart (it lives only in memory), quantity 0 is silently raised to 1.
     False-alarm numbers from before this fix aren't directly comparable with later ones.
   - **Done in run 4 (J1, D66):** native tool-call attempts get one corrective message. Was: **claude-cli adapter:** one Sonnet run finished early saying its tools "were not
     available" (it tried a native tool call instead of the JSON answer). Dev-only provider.
   - **Gemma now reaches bug states but doesn't recognise them** (7 of 12 AI-only states
     reached, 1 reported). The next improvement is in the AI core (yours): for example an
     "expected vs. happened" line after each state-changing action. `docs/MISS_ANALYSIS.md`.
   - **Done in run 4 (J1, D65):** a timed-out call is retried once with a trimmed observation; 0 timeouts in the J1 benchmark. Was: **Ollama sometimes takes over 300 s for one call** (3 of 7 runs in R3b, on a 16 GB Mac with
     gemma4:12b). Since D61 such a run ends cleanly with its steps kept, but it still costs that
     run. Options: a smaller context, a longer `TIMEOUT_S` in `llm/ollama.py`, or a machine with
     more memory.
   - **Run 2's items are done:** replay losing correct reports (H1, D53), the sign-in flake (H3,
     D55), CI's Node 20 actions (H5, D57), the full claude-cli benchmark (H7, below).
1. **(Optional) A Claude API key** for real Claude numbers: put `ANTHROPIC_API_KEY=...` in `.env`
   and set `LLM_PROVIDER=claude`. Tonight runs on Ollama (`qwen3-vl:8b`, local, free).
2. **(Optional) The `alias: ... not found` errors in `~/.bash_profile`.** Not touched: the
   overnight rules forbid shell-config changes. Ask me to show the broken lines.
3. **Re-run the model-quality checks with Claude** (tonight only had a local 8B model). With
   `ANTHROPIC_API_KEY` in `.env` and `LLM_PROVIDER=claude`, `npm run dev` running:
   - M4: `cd apps/worker && LIVE_MODEL=1 uv run pytest tests/test_live_model.py -s` (prompt
     injection), then queue an interactive run on http://localhost:5173 from the dashboard (or
     `npm run bench`, M7) and check that ≥ 4 of bugs 5–12 are reported. Expected cost: under
     $1 per run (budget-capped).
   - M5: compare false alarms on the clean shop (http://localhost:5174) before/after replay.
   - The Claude client has unit tests with a stand-in SDK but has never called the live API:
     the first real run is also the test of `ClaudeClient` (prompt caching:
     `cache_read_input_tokens` should be > 0 from the second step on).
4. **(Optional) Shell setup left over from the Mac setup:** add
   `eval "$(fnm env --use-on-cd --shell zsh)"` to `~/.zshrc` (otherwise new terminals use
   Node 20), and in Docker Desktop → Settings → Advanced pick "System" so `docker` is on PATH.

## Spend tonight
Run 5: $0.00. No Claude API call (`API_BUDGET_USD` = 0), no claude-cli call (no yes for Sonnet). Ollama local: three benchmarks (21 runs), the K1 re-check, one qwen3:14b download (9.3 GB).
Run 3: $0.00. No API key and no paid calls. claude-cli (owner's Pro login): one Haiku check call and one benchmark (7 runs, ~220 agent decisions), no usage limit hit. Ollama local.
Earlier: Claude API: $0.00 (no key, no Claude calls made). Ollama: $0 (local): ~12 agent runs + 2 benchmark scorings.
