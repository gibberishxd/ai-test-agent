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

## Needs me
0. **Run 2 follow-ups (no money needed unless you choose Claude API):**
   - **Replay lost two of Sonnet's correct reports** (bugs 5 and 8, run be495c9f). Replaying
     the steps standalone works (`uv run python <scratchpad>/replay_check.py`-style: load the
     bug's steps with `replay_plans`, call `_replay_step` one by one), so look at what differs
     inside `verify_and_dedupe`: one shared browser context for all bugs (cookies, storage),
     the guard proxy, or timing. Then re-verify that run's dismissed bugs.
   - **The full claude-cli benchmark** was not run on purpose: 7 runs × ~40 Sonnet calls would
     use a large share of your Pro limit. To run it: `cd apps/worker && LLM_PROVIDER=claude-cli
     uv run worker bench` (needs `DEV_MODE=true`, and the four demo servers running).
   - **"Sign in as demo user" sometimes lands back on `/signin?callbackUrl=…`** instead of the
     dashboard (once locally on a cold dev server, twice in CI on the second e2e test). The e2e
     tests now retry the sign-in click (`signInAsDemoUser`), so other features stay tested, but
     the cause is open: check the Auth.js credentials flow (CSRF cookie timing, or a dev-server
     reload during sign-in) in the dev server's log when it happens.
   - **CI uses actions that target Node 20** (`actions/checkout@v4`, `setup-node@v4`,
     `setup-uv@v6`): GitHub forces them onto Node 24 with a deprecation warning. Bump to their
     Node 24 majors when they're out.
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
Claude API: $0.00 (no key, no Claude calls made). Ollama: $0 (local): ~12 agent runs + 2 benchmark scorings.
