# Progress: Demo v1

Milestones from `docs/PRODUCT_BRIEF.md`, in order. Status: todo / in progress / done /
done (local model) / blocked.

| # | Milestone | Status | Acceptance check result |
|---|---|---|---|
| M1 | Demo shop: 12 planted bugs, injection text, clean build on 5174, bugs.json | done | `npm run verify-bugs`: 26/26 passed (12 bugs present on 5173 and absent on 5174, injection text on both) |
| M2 | Data model + run queue, LLMClient (Fake, Claude, Ollama) | done | Inserted a queued run with SQL, `LLM_PROVIDER=fake uv run worker --once` claimed it and marked it `done` (provider=fake, claimed, finished). 52 worker tests pass. |
| M3 | Deterministic checks + passive scan, safety 6.1/6.2/6.6 | done | `uv run worker scan`: buggy shop (11 pages) → 5 bugs covering bugs 1, 2, 3, 4, each with evidence; clean shop (11 pages) → 0 bugs. SSRF guard tests pass (incl. redirect to 10.0.0.5 blocked). 115 worker tests. |
| M4 | Agent loop: safe mode, budgets, loop detection, injection, cost, caching | done (local model) | qwen3-vl:8b-instruct on the buggy shop, 3 runs: bugs 5–12 reported **0 of 8** (needs ≥ 4). Final run reached the state of bug 5 (cart shows 2 × $12, total $12) but the model didn't report it. Injection test: the agent kept testing on the injected page (didn't give up or claim no bugs) but reported no bugs → fails on the "reports bugs" half, for the same model-quality reason. Cost recorded per step and run ($0 on Ollama). All safety/budget/loop behaviour verified by 30+ unit tests. See D16, D20, D21 and Needs me #3. |
| M5 | Replay verification + dedup | done (local model) | Clean shop, local model: interactive run 0 candidates, passive run (6 screenshots reviewed) 0 candidates → false alarms 0 before and 0 after replay, so "lower than M4" can't be shown. On the buggy shop replay dismissed 2/2 false reports (run 2). Replay, verdict and dedup logic covered by unit + integration tests. Real comparison needs Claude: Needs me #3. |
| M6 | Web app core: landing, dashboard, run form, live run, report, history | done | `npm run test:e2e`: 3/3 passed. Main flow (dashboard → start run on the demo shop → live page → report with bug cards, export buttons, Download JSON) in 11.7 s with the worker on FakeClient; plus form validation and the interactive-mode guard. Pages checked at 1280 px and 375 px (no sideways scroll), light and dark, no console errors. |
| M7 | Benchmark script + benchmark page | todo | |
| M8 | B2B foundations: auth, workspaces, domain verification, quota, audit, share links | todo | |
| M9 | Polish: README, walkthrough, states, 375 px | todo | |

Already done before demo v1 (branch `phase-1-checker`, merged into `demo-v1`): report models,
URL helpers, BFS crawler, Playwright page visits, local test-site fixtures. 25 worker tests.

## Needs me
1. **(Optional) A Claude API key** for real Claude numbers: put `ANTHROPIC_API_KEY=...` in `.env`
   and set `LLM_PROVIDER=claude`. Tonight runs on Ollama (`qwen3-vl:8b`, local, free).
2. **(Optional) The `alias: ... not found` errors in `~/.bash_profile`.** Not touched: the
   overnight rules forbid shell-config changes. Ask me to show the broken lines.
3. **Re-run the model-quality checks with Claude** (tonight only had a local 8B model). With
   `ANTHROPIC_API_KEY` in `.env` and `LLM_PROVIDER=claude`, `npm run dev` running:
   - M4: `cd apps/worker && LIVE_MODEL=1 uv run pytest tests/test_live_model.py -s` (prompt
     injection), then queue an interactive run on http://localhost:5173 from the dashboard (or
     `npm run bench`, M7) and check that ≥ 4 of bugs 5–12 are reported. Expected cost: under
     $1 per run (budget-capped).
   - M5: compare false alarms on the clean shop (http://localhost:5174) before/after replay.
   - The Claude client has unit tests with a stand-in SDK but has never called the live API:
     the first real run is also the test of `ClaudeClient` (prompt caching:
     `cache_read_input_tokens` should be > 0 from the second step on).
4. **(Optional) Shell setup left over from the Mac setup:** add
   `eval "$(fnm env --use-on-cd --shell zsh)"` to `~/.zshrc` (otherwise new terminals use
   Node 20), and in Docker Desktop → Settings → Advanced pick "System" so `docker` is on PATH.

## Spend tonight
Claude API: $0.00 (no key). Ollama: $0 (local).
