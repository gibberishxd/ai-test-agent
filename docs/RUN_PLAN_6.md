# Run 6 plan (branch `agent-v6`)

Milestone: **measure stronger Claude models.** Run 3's single Sonnet benchmark (`f6151b32`) is
still the best result, but it ran on an alias ("sonnet"), recorded $0 and dropped cache tokens,
so we don't know which model it was or what it would cost on the API. Run 6 makes claude-cli
runs measurable, then benchmarks Haiku, Sonnet and the cheap-explorer / strong-reviewer setup,
and recommends a default. The owner is around but not always at the computer: questions go in
chat as numbered plain text, and work never waits for an answer.

## Rules (from the owner, summarised)
- Work on `agent-v6` from `main`. Commit after each goal, push, never merge or force-push. At the
  end open a PR `agent-v6` → `main` and leave it open.
- No Anthropic API calls (there is no key). Every Claude call goes through claude-cli, from a
  temp folder outside the repo with file access limited to it, checked before every call, never
  able to read a bug list.
- Anything that spends the owner's Pro limit or usage credits needs an explicit yes, per
  benchmark. Without it, skip it. The one Haiku call in L1 that confirms the CLI's JSON is part
  of the owner's plan.
- A claude-cli call that reports a usage limit stops that benchmark at once: record what
  finished, no retry, tell the owner. Usage credits must never be drained by a loop.
- Test first; `npm test` and `npm run lint` exit 0 before each commit.
- Old results are never rewritten; new rows carry commit, exact model ID, settings and date.
- No e2e tests or second worker during a benchmark. Stop processes by PID only.
- The judge stays pinned to `ollama/gemma4:12b` for every benchmark.
- Product decisions stay the owner's (bug 7's hidden code, the cart emptied by a reload,
  quantity 0 → 1).

## Goals and acceptance checks (in this order)

| Goal | What | Acceptance check |
|---|---|---|
| L0 | Plan | `agent-v6` from `main`; this plan committed; the owner has the L2 matrix with time and Pro-limit estimates and a yes/no question per benchmark. |
| L1 | Make claude-cli runs measurable | `CLAUDE_CLI_MODEL` / `CLAUDE_CLI_CHEAP_MODEL` take full IDs; the model the CLI reports is recorded for every call; a benchmark refuses to start on a bare alias. All four token types recorded (input, output, cache read, cache write). An API-equivalent cost (from `llm/pricing.py`) per call, step and run, stored apart from the charged cost (still $0), labelled as an estimate wherever it is shown, and used for `MAX_RUN_COST_USD`. Benchmark output and the leaderboard show estimated cost per run and per verified planted bug. Tests first with recorded CLI JSON fixtures; one real Haiku call from the temp folder confirms the fields. |
| L2 | Measure (only the benchmarks the owner says yes to, each committed before the next) | Settings of `f6151b32`: 480 s and 40 steps per run; shop 3 buggy + 1 clean, holdout 2 buggy + 1 clean; current code (13 shop bugs, bug 13 behind the login). a) Haiku 5.5 agent; b) Sonnet 5.5 agent; c) Gemma explorer + Sonnet 5.5 reviewer; d) Gemma + Opus 5.5 reviewer, only with a separate yes after a–c. After each: AI-only and overall recall per app with counts, precision, clean-build false alarms, run time, estimated API cost per run. |
| L3 | Analysis | `MISS_ANALYSIS.md` "Run 6": per-bug table across models (found / reached but not reported / never reached / dropped by verification) and what each model's misses share. `DECISIONS.md` "Which model where": the default setup with estimated cost per run and per verified bug, backed by the numbers. Small samples and estimated costs stated plainly. |
| L4 | Wrap-up | README results (new rows only), WALKTHROUGH (L1 with interview Q&A), PROGRESS, DEVLOG; `npm test` + `npm run lint` exit 0; CI green; PR `agent-v6` → `main` opened, not merged; servers stopped by PID, Ollama left running. |
