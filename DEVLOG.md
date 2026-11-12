# Dev log

Two or three lines per session: what I did, what broke, what I decided and why.
Benchmark scores go here too, once Phase 2 exists.

## 2026-11-05
- Scaffolded the monorepo: Next.js web app, Vite demo shop, Python worker, Postgres via Docker, CI for both languages.
- Decided: Python for the worker (AI tooling lives there), TypeScript for the web app; a Postgres `runs` table instead of a separate queue.
- Finished Phase 0 setup on Windows: Node 26 (scoop), Python 3.12 (uv), Docker Desktop on D: (C: was nearly full), gh. Moved `ci.yml` into `.github/workflows/`, pushed to GitHub, CI green.
- Broke: Docker's installer needs ~3.9 GB free on C: even when installing to D:; and `git push` was refused until `gh` got the `workflow` scope.

## 2026-11-09 (overnight, demo v1)
- Mac setup: Node 24 via fnm (arm64), Postgres on 5433 (a system Postgres owns 5432), worker
  venv rebuilt on arm64 Python (Intel `uv` had built an x86 venv that broke background runs).
- Built M1–M9: demo shop with 12 planted bugs + clean build; Prisma schema and Postgres queue;
  deterministic checks + passive scan; agent loop with deny list, budgets, loop detection and
  injection fencing; replay + dedup; Next.js app (live run page, reports, history); benchmark
  script + page; sign-in, workspaces, domain verification, quota, audit log, share links; README.
- Broke and fixed: the SSRF guard first used Playwright's request interception, which doesn't
  see redirect hops (a test caught a redirect to 10.0.0.5 getting through) → rewritten as an
  egress proxy that checks every hop and connects to the vetted IP. The benchmark first said
  0% because the matcher rejected `"match": "2"` (a string) → fixed, rescored.
- Benchmark (local qwen3-vl:8b, no API key): recall 33%, precision 100%, 0 false alarms, $0.
  All recall came from deterministic checks; the 8B model explores but rarely reports. Next:
  the same benchmark with Claude.

## 2026-11-10
- Benchmarked a bigger local model, gemma4:12b (Ollama, ~8 GB, fits in 16 GB): recall 42% vs
  33% for qwen3-vl:8b, 0 false alarms on the clean shop, $0, 522 s/run.
- First bug found by the model itself: bug 9 (Wool Socks "$NaN") in 3/3 runs.
- Precision showed 90% only because the matcher filters by page: the cart NaN (bug 9's symptom
  on `/cart`) counted as unmatched. Next: decide how matching handles cross-page symptoms.

## 2026-11-10 (run 2, stopped early at the usage limit)
- Gemma 4 12B with a 1200 s limit used all 40 steps and still found only bug 9: recall 42%,
  precision 100%, 0 false alarms, 1101 s/run. The time limit wasn't the bottleneck; the model is.
- Fixed from the review, test first: off-site clicks, loop detection that punished real
  testing, a pinned benchmark judge, DEV_MODE off by default, a rule-table deny list, an
  unspoofable visitor rate limit with an atomic quota, share-link screenshots, a pinned
  domain-verification fetch.
- Next: G2.1–G2.4 (viewport/double-click/reload/note tools, richer observation, QA charter,
  robust replay), then G3–G8 of docs/RUN_PLAN_2.md.

## 2026-11-10 (run 2, unattended, branch agent-v2)
- Built G1–G7 of docs/RUN_PLAN_2.md, test first: safety fixes (dev mode off by default, rule-table
  deny list, unspoofable rate limit, atomic quota, share-link screenshots, pinned verification
  fetch), tester's tools (double-click, reload, phone viewport, notes), field-aware observation,
  a generic QA charter, exact-element replay, AI-only recall, a holdout app, a live browser pane,
  "bring any model" (OpenAI-compatible client, encrypted workspace keys, Test connection,
  leaderboard), a local claude-cli provider, ESLint, and an e2e CI job. CI green.
- Measured: Gemma 4 12B 0% AI-only on shop and holdout (it noted a bug instead of reporting it;
  replay lost a correct report). One Sonnet run via claude-cli: AI-only 13%, but it reported two
  more planted bugs that replay dismissed. Verification is now the bottleneck, not the model.
- Broke and fixed: claude-cli started inside the repo could read bugs.json (now runs restricted in
  a temp folder); number inputs were recorded as "textbox" instead of "spinbutton".

## 2026-11-11 (run 3, unattended, branch agent-v3)
- H0–H8 of docs/RUN_PLAN_3.md, test first: replay waits for SPA routes and starts each bug in a
  fresh browser context (Sonnet's lost reports for bugs 5 and 8 now verify), a verification
  funnel with "correct but discarded", the sign-in flake fixed at its cause (Auth.js CSRF race),
  run leases and a queue concurrency test, an EXPLAIN-backed index, docs/DATABASE.md, Node 24 CI.
- Measured: Gemma 12B with a charter reminder now uses every technique and reaches 7/12 bug
  states but reports ~1 (shop AI-only 8%, holdout 0%). One Sonnet benchmark via claude-cli:
  shop AI-only 38% (was 13%), recall 58%, holdout 25% / 50%; its 3 "false alarms" are real
  bugs in the clean build. Next limit for small models: recognising a wrong state.

## 2026-11-11 (run 4, branch agent-v4)
- Pipeline-ready: sign-in setups for apps behind a login (encrypted, scrubbed, logout denied),
  /api/v1 with hashed keys, JUnit and signed webhooks plus a CI script, fingerprints with
  new/still/fixed and triage, roles, invitations, audit log, Postgres row-level security, Docker
  images and a production stack (Postgres, SeaweedFS, N workers) run locally end to end.
- Measured: the expected-vs-actual check flags contradictions but Gemma 12B dismisses most
  (holdout 0% → 0%, kept); final Gemma benchmark shop AI-only 0% (bug 8 found twice, dismissed by
  the replay judge). Sonnet not run without the owner's yes.
- Learned the hard way: no e2e tests during a benchmark (D67), stop processes by PID only (D71),
  and keep the dev and production compose files apart (D77).
