# Progress: Demo v1

Milestones from `docs/PRODUCT_BRIEF.md`, in order. Status: todo / in progress / done /
done (local model) / blocked.

| # | Milestone | Status | Acceptance check result |
|---|---|---|---|
| M1 | Demo shop: 12 planted bugs, injection text, clean build on 5174, bugs.json | done | `npm run verify-bugs`: 26/26 passed (12 bugs present on 5173 and absent on 5174, injection text on both) |
| M2 | Data model + run queue, LLMClient (Fake, Claude, Ollama) | done | Inserted a queued run with SQL, `LLM_PROVIDER=fake uv run worker --once` claimed it and marked it `done` (provider=fake, claimed, finished). 52 worker tests pass. |
| M3 | Deterministic checks + passive scan, safety 6.1/6.2/6.6 | done | `uv run worker scan`: buggy shop (11 pages) → 5 bugs covering bugs 1, 2, 3, 4, each with evidence; clean shop (11 pages) → 0 bugs. SSRF guard tests pass (incl. redirect to 10.0.0.5 blocked). 115 worker tests. |
| M4 | Agent loop: safe mode, budgets, loop detection, injection, cost, caching | todo | |
| M5 | Replay verification + dedup | todo | |
| M6 | Web app core: landing, dashboard, run form, live run, report, history | todo | |
| M7 | Benchmark script + benchmark page | todo | |
| M8 | B2B foundations: auth, workspaces, domain verification, quota, audit, share links | todo | |
| M9 | Polish: README, walkthrough, states, 375 px | todo | |

Already done before demo v1 (branch `phase-1-checker`, merged into `demo-v1`): report models,
URL helpers, BFS crawler, Playwright page visits, local test-site fixtures. 25 worker tests.

## Needs me
1. **Log in to GitHub so pushes work.** Run `gh auth login` (GitHub.com → HTTPS → log in with a
   browser), make sure the `workflow` scope is included, then `gh auth setup-git`. Then, from
   the repo: `git push -u origin demo-v1`. Until then, all commits are local only.
2. **(Optional) A Claude API key** for real Claude numbers: put `ANTHROPIC_API_KEY=...` in `.env`
   and set `LLM_PROVIDER=claude`. Tonight runs on Ollama (`qwen3-vl:8b`, local, free).
3. **(Optional) The `alias: ... not found` errors in `~/.bash_profile`.** Not touched: the
   overnight rules forbid shell-config changes. Ask me to show the broken lines.
4. **(Optional) Shell setup left over from the Mac setup:** add
   `eval "$(fnm env --use-on-cd --shell zsh)"` to `~/.zshrc` (otherwise new terminals use
   Node 20), and in Docker Desktop → Settings → Advanced pick "System" so `docker` is on PATH.

## Spend tonight
Claude API: $0.00 (no key). Ollama: $0 (local).
