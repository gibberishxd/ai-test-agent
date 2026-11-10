# AI Test Agent

**Source of truth: [`docs/PRODUCT_BRIEF.md`](docs/PRODUCT_BRIEF.md).** Read it first. Progress is in
`docs/PROGRESS.md`, decisions in `docs/DECISIONS.md`, a study guide per component in
`docs/WALKTHROUGH.md`. `docs/PLAN.md` is the earlier roadmap, superseded by the brief.

A B2B web product: a team pastes their web app's URL, an AI agent explores it like a manual QA
tester and reports bugs with evidence. It measures its own accuracy against a demo shop with
planted bugs.

## Layout
- `apps/web` — Next.js (App Router, TypeScript, Tailwind, shadcn/ui) dashboard + API. Prisma owns the DB schema.
- `apps/worker` — Python (uv, Playwright, pytest, ruff, Pydantic, SQLAlchemy). Deterministic checks, agent loop, replay.
- `apps/demo` — Vite + React demo shop with planted bugs (5173) and a clean build (5174); bugs listed in `bugs.json`.
- `apps/demo2` — holdout app for the benchmark (5175, clean 5176): same kinds of bugs, never used to tune the agent.
- `docker-compose.yml` — local Postgres, the only link between web and worker.

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

## Overnight run
When the owner starts an unattended overnight run, the PART B rules in `docs/PRODUCT_BRIEF.md`
apply and override "wait for a go-ahead" and "the AI core is the owner's to write", for that run
only. In short:
- Don't ask or wait. Make the reasonable choice and record it in `docs/DECISIONS.md`
  (decision, alternatives, why).
- Work strictly in milestone order (M1–M9). After each milestone: run its acceptance check, show
  the output, update `docs/PROGRESS.md`, commit, push to `demo-v1`. Never push to main, never
  force-push, never rewrite history.
- Blocked on the owner → write it under "Needs me" in `docs/PROGRESS.md`, then continue with what
  can be done.
- Stay inside this repo: no deploys, no paid sign-ups, no shell config or global settings changes.
- Unit tests always use FakeClient. Real model calls only for acceptance checks and the benchmark.
  Keep "Spend tonight" current; at $10 of Claude spend, stop real Claude calls.
- Keep `docs/WALKTHROUGH.md` current: per component, what/how/why, weak spots, 3 interview Q&As.
- End the night with a `DEVLOG.md` entry.

## Unattended run 2 (branch `agent-v2`)
The owner's plan and ground rules for the second unattended run are in
[`docs/RUN_PLAN_2.md`](docs/RUN_PLAN_2.md). For that run only, its rules override "wait for a
go-ahead" and "the AI core is the owner's to write".

## Current phase
Demo v1 (branch `demo-v1`): milestones M1–M9 done (M4/M5 measured with a local model only).
Next: re-run M4/M5 and the benchmark with Claude (see "Needs me" in `docs/PROGRESS.md`), then
review and merge `demo-v1` into `main`.
