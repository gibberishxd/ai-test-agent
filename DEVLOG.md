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
