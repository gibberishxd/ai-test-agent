# Run 7 plan (branch `agent-v7`)

Milestone: **test against what the team means.** Apply the owner's run 6 decisions (Haiku as the
default, the early-finish fix, the demo behaviours fixed as benchmark v2), then build the first
two items of "Product roadmap after run 6": spec-aware testing (pgvector, local embeddings) and
critical flows (saved journeys replayed without a model), an MCP server if time allows, and
measure. The owner may be asleep or away: questions go in chat as numbered plain text, and work
never waits for an answer.

## Settings (the owner's decisions)
- `DEFAULT_MODEL = claude-haiku-5-5` as the agent; Sonnet stays the "thorough" option.
- `FIX_EARLY_FINISH = yes` (agent loop change allowed).
- `DEMO_BEHAVIORS = fix`, in both builds: profile "Recent orders" vs "My orders"; holdout dates
  outside room availability; holdout past dates; shop double-clicked "Add to cart". From then on
  the benchmark is **benchmark v2**, labelled everywhere.
- `HAIKU_BENCHMARKS_ALLOWED = 5` (claude-cli, the owner's Pro plan), for M2, M3, M4; cap $2
  estimated API-equivalent per benchmark.
- `SONNET_BENCHMARKS_ALLOWED = 1`, only in M6, only after all Haiku work; cap $15 estimated.
- `OPUS_AGENT_RUN = no`. No Anthropic API calls (no key).

## Rules (summarised)
- `agent-v7` from `main`; commit after each goal, push, never merge or force-push; end with a PR
  `agent-v7` → `main`, not merged.
- claude-cli only from a temp folder outside the repo, file access limited to it, checked before
  every call; never able to read a bug list or a spec answer key.
- Test first; `npm test` and `npm run lint` exit 0 before each commit; never tests, e2e or a
  second worker while a benchmark runs.
- Schema changes: Prisma migration (raw SQL for extensions, functions, policies), SQLAlchemy
  mirror, drift test, row-level security on every new tenant table, `docs/DATABASE.md`.
- Old results never rewritten; new rows carry commit, exact model ID, benchmark version,
  settings and date. Judge pinned to `ollama/gemma4:12b`.
- On a usage-limit or fallback-credit message: stop all model runs, record what finished, no
  retry, continue with work that needs no model.
- Stop processes by PID only. Secrets never in git, logs or prompts.
- Blocked ~90 minutes → "Needs me" and move on. Out of time → finish the current goal cleanly.

## Goals and acceptance checks (in this order)

| Goal | What | Acceptance check |
|---|---|---|
| M0 | Plan | PRs #9 / #10 checked (not merged by us); `agent-v7` from `main`; this plan; `docs/specs/TEMPLATE.md` (holdout pages and features, names only) and the owner asked to write `apps/demo2/specs.md`. |
| M1 | Apply the decisions | Haiku 5.5 the agent default in config, the web model picker, `.env.example` and docs, Sonnet labelled "thorough"; the early finish reproduced in a failing test from the run 6 transcript, then fixed (one corrective message, then continue); the 4 demo behaviours fixed in both builds with a test each, verify-bugs green; "benchmark v2" in bench output, results and the leaderboard. |
| M2 | New baseline | One Haiku benchmark v2 (holdout first, shop, clean builds), judge gemma4:12b, cap $2. |
| M3 | Specs (roadmap item 1) | pgvector Postgres 17 image in dev, CI and prod compose; specs per target (Markdown / text) stored per workspace under RLS, chunked, embedded locally with Ollama (model chosen and recorded), pgvector column with an index; per-page retrieval (route, title, headings) of the top chunks, capped, for the agent and the verifier as untrusted reference text; Specs tab on the target page; the report names the spec a bug violates; `/api/v1` specs endpoints and OpenAPI; guard test against spec lines that match planted bugs. Measured only once the owner's `apps/demo2/specs.md` exists: Haiku holdout with specs vs M2's holdout; kept on by default only if judgement-only recall rises and clean-build false alarms don't. |
| M4 | Critical flows (roadmap item 2) | 3–10 plain-language journeys per target under RLS; the agent covers them first; a passing journey saved as a replayable Playwright script (steps, selectors, checks); later runs replay without the model, the model only when a replay breaks (repaired → script updated; not → a finding); Flows tab per target; the report shows each journey's result. Three shop journeys (sign in; add to cart and check out; change profile). Measured with Haiku: run 1 saves, run 2 replays: coverage, model calls, estimated cost, same failures found more cheaply. |
| M5 | MCP server (only if M1–M4 are done) | Wraps `/api/v1` with a workspace API key: start a run, status, report. Tests; README setup for Claude Code and Cursor. |
| M6 | Measure the final state | Haiku benchmark v2 with what M3 and M4 kept; then one Sonnet benchmark v2 if allowed and no limit was hit. Leaderboard, MISS_ANALYSIS "Run 7", README results (new rows only). |
| M7 | Wrap-up | README, WALKTHROUGH (specs, embeddings and retrieval, flows, MCP, with Q&A), DATABASE, ROADMAP, PROGRESS, DECISIONS, DEVLOG; tests and lint exit 0, CI green; PR opened, not merged; servers stopped by PID, Ollama running. |
