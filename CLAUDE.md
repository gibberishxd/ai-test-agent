# AI Test Agent

A portfolio project: an AI agent that explores a web app like a manual tester and reports bugs,
measured against a demo app with planted bugs.

## Layout
- `apps/web` — Next.js (App Router, TypeScript) dashboard + API. Talks to the worker only through Postgres.
- `apps/worker` — Python (uv, Playwright, pytest, ruff). The agent: deterministic checks, LLM agent loop, replay verification.
- `apps/demo` — Vite + React demo shop: the target app. Planted bugs live here, listed in `bugs.json` (Phase 2).
- `docker-compose.yml` — local Postgres.

## Commands (from the repo root)
- `npm run setup` — install everything (Node packages, Python env, Chromium for Playwright)
- `npm run db:up` — start Postgres in Docker
- `npm run dev` — run web (3000), demo (5173) and worker together
- `npm test` / `npm run lint` — all tests / all lint + type checks

## How to work with me (the owner is learning; this matters more than speed)
- Explain the plan and any new concept BEFORE writing code. Wait for a go-ahead on anything non-trivial.
- One feature per change. Keep diffs small enough to read in a few minutes.
- Small, single-purpose functions with tests. A bug fix starts with a failing test.
- The AI core is the owner's to write: the agent loop, system prompt, bug-judging logic and benchmark matching.
  In those areas, review, suggest and explain; don't write the implementation unless explicitly asked.
- Boilerplate (config, UI components, DB schema, deployment) you can write freely.
- Never commit secrets. Config comes from `.env` (see `.env.example`).
- After each session, suggest 2–3 lines for `DEVLOG.md`.

## Current phase
Phase 0 — repo setup. Next: Phase 1, the deterministic checker in `apps/worker`.
