# Dev log

Two or three lines per session: what I did, what broke, what I decided and why.
Benchmark scores go here too, once Phase 2 exists.

## 2026-11-05
- Scaffolded the monorepo: Next.js web app, Vite demo shop, Python worker, Postgres via Docker, CI for both languages.
- Decided: Python for the worker (AI tooling lives there), TypeScript for the web app; a Postgres `runs` table instead of a separate queue.
