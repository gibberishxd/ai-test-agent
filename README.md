# AI Test Agent

An AI agent that explores a web app like a manual tester, finds bugs, and reports them with
screenshots and repro steps. Its accuracy is measured against a demo shop with planted bugs.

> Work in progress. Phase 0 (project setup) is done.

## Run it locally

Requirements: Node.js 24+, Python 3.12+ with [uv](https://docs.astral.sh/uv/), Docker Desktop, Git.

```bash
npm run setup     # install everything
npm run db:up     # start Postgres
npm run dev       # web on :3000, demo shop on :5173, worker
npm test          # all tests
```

Copy `.env.example` to `.env` before running.

## Project layout

| Folder | What it is |
| --- | --- |
| `apps/web` | Next.js dashboard and API |
| `apps/worker` | Python agent (Playwright + Claude) |
| `apps/demo` | Demo shop the agent tests, with planted bugs |

## How AI tools were used

Built with Claude Code for setup and boilerplate. The agent logic, prompts and benchmark are my own work.
