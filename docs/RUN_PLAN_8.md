# Run 8 plan (branch `agent-v8`)

Milestone: **real-world proof.** Every result so far comes from two demo apps we built ourselves,
and the real Claude API path has never made a call. Run 8 makes the first API calls (within a
budget), fixes the failing-journey recheck, runs enough benchmark runs to put confidence
intervals on the numbers, and measures the agent on known, fixed bugs in real open-source apps
run locally. Unattended: decisions go to `docs/DECISIONS.md`, blockers to "Needs me".

## Settings (the owner's decisions)
- `API_BUDGET_USD = 4` for all real Anthropic API calls in the run ($5 prepaid, no auto-reload);
  at most $0.50 per API run. Spend is tracked from the app's own cost records (`runs.cost_usd`
  of runs with provider `claude`); no API call once the total would pass $4.
- `LLM_PROVIDER=ollama` stays in `.env`. The provider is set per command: `LLM_PROVIDER=claude`
  for API runs, `LLM_PROVIDER=claude-cli` for Pro-plan runs.
- `HAIKU_CLI_RUNS_ALLOWED = 60` (claude-cli, the owner's Pro plan) for N2–N4; at most $2
  estimated API-equivalent per benchmark.
- No Sonnet, Opus or Fable runs.
- Real-world apps run only locally on this Mac; the agent never sees a public website.
- Any usage-limit, credit or billing message: stop all model runs, record what finished, no
  retries, continue with work that needs no model.

## Rules (summarised)
- `agent-v8` from `main` (PRs #10 and #11 are merged); commit and push after each goal; never
  merge or force-push; end with a PR `agent-v8` → `main`, not merged.
- The API key is never printed, logged or committed; the claude-cli subprocess never inherits
  `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN`.
- claude-cli only from a temp folder outside the repo, file access limited to it, checked before
  every call; it can never read a bug list, an issue text or a fix commit.
- Test first; `npm test` and `npm run lint` exit 0 before each commit; never tests, e2e or a
  second worker while a benchmark runs.
- Every new result row: commit, exact model ID, provider (api or claude-cli), benchmark name and
  version, settings, date. Old rows never rewritten. Judge pinned to `ollama/gemma4:12b`.
- Processes stopped by PID only. Blocked ~90 minutes → "Needs me", move on. Out of time → finish
  the current goal cleanly.

## Goals and acceptance checks (in this order)

| Goal | What | Acceptance check |
|---|---|---|
| N0 | Plan and key safety | This plan; `.env` and `.env.prod` git-ignored; no key-shaped string in tracked files or history (count only); `run_cli` strips both credentials (failing test first) and a guard test fails on a real-looking key in any tracked file; one claude-cli Haiku call shows `apiKeySource: none` (the Pro login) with the key in the parent's environment, charged $0. |
| N1 | Real Claude API smoke test | One short Haiku run, `LLM_PROVIDER=claude AGENT_MODEL=claude-haiku-5-5`, on the demo shop: tool calls work, cache reads appear after the first steps, the recorded cost equals the token counts at list price. Failures fixed test-first and retried once, else "Needs me". If clean: one Haiku benchmark v2 through the API within the budget; real cost per run beside run 7's claude-cli estimates, recall beside run 7's Haiku rows. |
| N2 | The open fixes | A failing journey goes back to the agent when its replay result changes, and at least every 3rd run (test first). One Haiku `bench --flows` through claude-cli measures D98's two fixes and the recheck. |
| N3 | Enough runs to trust the numbers | Haiku through claude-cli on benchmark v2: 8 buggy + 2 clean runs per app (as two identical benchmarks of 4 + 1 per app, each under the $2 cap). Wilson 95% intervals on recall over bug×run slots and a bootstrap interval over runs, in bench output, the leaderboard and the README; which earlier differences are within noise, stated plainly. |
| N4 | Real-world benchmark | `docs/REAL_WORLD.md` shortlist first (2–3 open-source apps, license, local start, ≥ 3 user-visible functional bugs each with an issue and a fix commit; no security or purely visual bugs). Per bug: a script that fetches the app by URL and commit (source outside the repo), checks out the commit before the fix, starts it with seed data; a scripted Playwright check confirms the bug reproduces (bugs that don't are dropped with the reason). The bug list stays out of claude-cli's reach. Haiku through claude-cli, 3 runs per bug version: found / reached but not reported / never reached, with intervals, plus other real-looking reports. |
| N5 | Wrap-up | README "Real-world results" near the top and the API vs claude-cli cost comparison; BENCHMARKS, MISS_ANALYSIS "Run 8", WALKTHROUGH (real-world benchmark, confidence intervals, the API path, with Q&A), PROGRESS, DECISIONS, DEVLOG, "Spend" with the real API spend; tests and lint exit 0, CI green; PR opened, not merged; servers and real-world apps stopped by PID, Ollama running. |

## Run budget (claude-cli Haiku runs, at most 60)
N2 `bench --flows` 7 · N3 2 × 10 = 20 · N4 3 per bug version (≈ 18–27) · margin for one
failed benchmark. API runs (N1) are counted in dollars, not runs.
