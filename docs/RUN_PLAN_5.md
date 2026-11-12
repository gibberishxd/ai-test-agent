# Run 5 plan (branch `agent-v5`)

Milestone: **trustworthy and accurate.** Run 4 made the product adoptable; run 5 makes its
verdicts correct, uses a stronger model only where it matters, lets the database enforce its own
rules, and meters usage that could be billed. Goals in priority order; each one is committed and
pushed when its acceptance check passes. The owner is around but not always at the computer:
questions go in chat as numbered plain text, and work never waits for an answer.

## Rules (from the owner, summarised)
- Work on `agent-v5` (from `agent-v4`, which contains `agent-v3`). Never merge, never force-push;
  when the owner says the PR is merged, rebase `agent-v5` onto `main` and push with
  `--force-with-lease` (the one exception).
- No money except `API_BUDGET_USD` (0 unless the owner sets a number). No real third-party calls;
  integrations are tested against local fakes and receivers.
- claude-cli only from a temp folder outside the repo, file access limited to it, re-checked
  before every call, never able to read a bug list. `SONNET_RUNS_ALLOWED = 1`, only with the
  owner's explicit yes this run, only in K6 after K1 and K2.
- `AI_CORE_ALLOWED = 1`: every agent change explained in `docs/WALKTHROUGH.md`.
- Test first. Schema changes: Prisma migration (raw SQL for functions, triggers, views,
  policies) + SQLAlchemy mirror + drift test + `docs/DATABASE.md`.
- Secrets never in git, logs, prompts or reports. `npm test` and `npm run lint` exit 0 before
  every commit. Old benchmark results are never deleted or rewritten.
- From run 4: no e2e tests or second worker while a benchmark runs; stop processes by PID or the
  exact command started, never a broad pkill; the production stack has its own volumes, ports and
  database.
- Blocked ~90 min → "Needs me" + tell the owner + move on. Out of time → finish the current goal.
- Owner's product decisions stay untouched: bug 7's hidden code, the cart emptied by a reload,
  quantity 0 → 1.

## Goals and acceptance checks

| Goal | What | Acceptance check |
|---|---|---|
| K0 | Branches and housekeeping | PR question asked (nothing done to PRs until answered); `agent-v5` created from `agent-v4`; this plan committed; Postgres, demos and worker start; baseline `npm test` + `npm run lint` exit 0. |
| K1 | Verify "nothing happened" bugs correctly | Replay captures a compact page state before and after the replayed action (URL, visible text / accessibility tree, form values, totals, storage, console, network) and gives the judge the diff plus both screenshots. Failing-first tests, including harmless changes (spinner, timestamp) that must not count. Offline re-check of every stored Gemma and Sonnet run with a rejected matching report (pinned judge only), before/after in `MISS_ANALYSIS.md`. **Pass:** bug 8's rejected reports verify, and no clean-build report becomes a new confirmed false alarm. |
| K2 | A stronger model where it matters | Reviewer tier: the explorer drives the browser; flagged expected-vs-actual steps and the final candidate list go to a reviewer (`REVIEWER_PROVIDER`, `REVIEWER_MODEL`, every provider); reviewer tokens and cost recorded separately per run. Generic list → detail exploration rule in the charter and the untried-technique reminder (no demo hints). Measured holdout first, then shop: Gemma+Gemma baseline, then Gemma explorer + the largest local model this Mac runs in reasonable time (chosen from free RAM, recorded). **Kept as default only if** holdout judgement-only recall rises and clean-build false alarms don't. |
| K3 | A database that enforces its own rules | Every web query through the RLS client (each remaining bypass removed or justified in `DATABASE.md`); roles: migration owner, web, worker, none superuser, app roles can't bypass RLS, used in dev, CI and the prod stack, with tests that each app role can't read other tenants' rows or change what it shouldn't. In Postgres, with direct database tests: audit triggers, `updated_at` triggers, triage carry-forward trigger; `claim_next_run`, `consume_quota`, retention procedure (worker and web call them); per-target bug history view; materialized leaderboard view with a refresh strategy; check constraints / enums for fixed sets and ranges. Table count stated; `DATABASE.md` covers every object and role, with a Mermaid ER diagram generated from the real schema. |
| K4 | Usage you could bill for | Plans table (runs per month, steps per run, models allowed, seats, retention days), each workspace on a plan; usage events per run with explorer and reviewer tokens and cost; `consume_quota` enforces plan limits; usage page per workspace (runs and cost this month, per model, against limits); admin view across workspaces; `ROADMAP.md` says what Stripe would take. |
| K5 | First-run experience | Sign-up → workspace → target → verify domain (or demo shop) → model → run → live pane → report, without help; rough edges fixed; one e2e test for the whole path; fresh Playwright screenshots in the README. |
| K6 | Measure | Gemma full benchmark (shop + holdout + clean, signed-in shop) with K1 + K2, recorded next to runs 2–4. Sonnet claude-cli benchmark only with the owner's yes (settings of `f6151b32` + bug 13). Claude API only if `API_BUDGET_USD > 0`: one smoke run first, then a reviewer benchmark only if the remaining budget covers it. Leaderboard and `MISS_ANALYSIS.md` updated. |
| K7 | Wrap-up | README, WALKTHROUGH, PROGRESS, ROADMAP, DATABASE, DECISIONS, DEVLOG updated; tests + lint green; CI green on `agent-v5`; pushed, nothing merged; dev servers, worker and prod stack stopped by PID/exact command, Ollama left running; short final message. |

## Order
K0 → K1 → K2 (code) → K3 → K4 → K5 → K2 measurements and K6 benchmarks (nothing else running
on the machine while they run) → K7. K2's measurement can run while K3 work happens only if no
e2e test or second worker runs at the same time; otherwise the benchmarks wait for the end.
