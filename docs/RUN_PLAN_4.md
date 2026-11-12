# Run 4 plan (branch `agent-v4`)

Milestone: **a real team could adopt it in their pipeline.** Goals in priority order; each is
committed and pushed when its acceptance check passes. The owner is around but not always at
the computer: questions go in chat as numbered plain text, work never waits for an answer
(see "How to work" below).

## Rules (from the owner, summarised)
- Work on `agent-v4` (from `agent-v3`). PR `agent-v3 → main` is open (#2) for the owner to
  merge. Never merge, never force-push; if the owner says #2 is merged, rebase `agent-v4` onto
  `main` and push with `--force-with-lease` (the one exception).
- No money: no paid API calls, no cloud hosting, no real third-party calls (GitHub Issues,
  Slack, outside webhooks). Integrations are tested against local fakes and receivers.
- claude-cli only from a temp folder outside the repo, file access limited to it, checked
  before every call. `SONNET_RUNS_ALLOWED = 1`, only in J7, only if the owner said yes today.
- `AI_CORE_ALLOWED = 1`: J1 may change the agent's AI core; every change explained in
  `docs/WALKTHROUGH.md`.
- Test first. New tables: Prisma migration + SQLAlchemy mirror + drift test + `docs/DATABASE.md`.
- Secrets: encrypted or hashed at rest, never logged, never sent to a model, shown once.
- `npm test` and `npm run lint` exit 0 before every commit. Old benchmark results are never
  deleted or rewritten (a mislabelled commit is corrected with a note, J0).
- Blocked ~90 min → "Needs me" + tell the owner + move on. Out of time → finish the current
  goal cleanly rather than start a new one.
- Owner's open product decisions stay untouched: bug 7's hidden code, the cart emptied by a
  reload, quantity 0 → 1.

## How to work
Questions to the owner are grouped, numbered, with options and a recommendation. A part that
depends on an answer is parked; if it is the only thing left in its goal, the recommendation
is used and recorded in `docs/DECISIONS.md` as "decided without owner, revisit".

## Goals and acceptance checks

| Goal | What | Acceptance check |
|---|---|---|
| J0 | Housekeeping and plan | Clean-build fixes pushed (`ffdb67e`), PR #2 open and unmerged; mislabelled Gemma rows `a4d5781c`/`1eccde57` say `f1bf08a` with a correction note; this plan and `docs/ROADMAP.md` committed; services up; baseline `npm test` + `npm run lint` exit 0. |
| J1 | Recognise wrong states (AI core) | Failing-first tests for: the expectation/verdict step on state-changing actions only, mismatch → candidate that must be reported or dismissed with a reason, the claude-cli native-tool-call recovery (one corrective message), the Ollama timeout retry with a trimmed observation. Gemma measured on the holdout first, then the shop: kept only if holdout AI-only recall doesn't drop and clean-build false alarms don't rise. Token cost per step recorded before/after. `MISS_ANALYSIS.md` updated. |
| J2 | Apps behind a login | Login setup per target (URL, test username, password encrypted with the existing key scheme, optional selectors) or a recorded storage state; deterministic sign-in before the agent; credentials absent from prompt, logs, steps, reports and live pane (tests grep for them); password fields masked in screenshots; logout / change password / delete account denied; automatic re-sign-in when the session drops; a signed-in-only planted bug in the shop in `bugs.json`, verify-bugs and the benchmark; "Test sign-in" button that reports success or failure without secrets. |
| J3 | Run it from CI | Workspace API keys (hash only, shown once, prefix, last used, revoke); `/api/v1` runs: start, status, JSON report, JUnit XML; rate limit per key + quota; OpenAPI spec with tests that the routes match it; signed webhooks (HMAC-SHA256 over timestamp + body), retries with backoff, a deliveries table, SSRF guard on the URL, tested against a local receiver; `examples/` CLI + GitHub Actions workflow that exits non-zero at a severity threshold (not run in this repo's CI); `docs/API.md`. |
| J4 | Bugs across releases | Fingerprint (normalised route + category + key element/message) with tricky-case tests; report shows new / still present / fixed against the previous run of the target; triage (confirmed, false positive, won't fix, comment) that follows the fingerprint; false positives suppressed later and counted per model; new tables documented. |
| J5 | Teams and tenant isolation | Roles owner/admin/member/viewer, tested per route; invitation links with expiry (no email); audit log page; Postgres RLS on tenant tables with tests that a query missing its WHERE can't read another workspace; worker and migrations still work; RLS cost measured with EXPLAIN ANALYZE; partial unique index for the default model. |
| J6 | Production readiness | Multi-stage non-root Dockerfiles; prod compose (Postgres, web, N workers, MinIO); storage interface (disk / S3) with signed expiring URLs; retention job; `/health`, `/ready`, JSON logs with run/workspace ids, metrics; CI actions pinned by SHA; `docs/DEPLOY.md` with a threat model; the prod stack brought up locally and one Gemma run through it. |
| J7 | Measure | Gemma 12B full benchmark (shop + holdout + clean, new login-only bug) next to runs 2 and 3; one Sonnet benchmark only if approved today; leaderboard and `MISS_ANALYSIS.md` updated. |
| J8 | Wrap-up | README, WALKTHROUGH, PROGRESS (Needs me with exact steps), ROADMAP, DECISIONS, DEVLOG; tests + lint green; CI green on `agent-v4`; pushed; servers and prod stack stopped, Ollama left running; short final message. |
