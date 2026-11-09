# Decisions

One entry per decision: what, the alternatives, and why. Cost-affecting changes include
before/after numbers from the benchmark.

## D1. Postgres host port is configurable (2026-11-08)
- **Decision:** `docker-compose.yml` maps `${POSTGRES_PORT:-5432}:5432`; this Mac uses 5433.
- **Alternatives:** stop the Mac's system PostgreSQL 17 (needs sudo, may break other things);
  hardcode 5433 (breaks Windows and CI defaults).
- **Why:** a system PostgreSQL 17 already listens on 5432 on this Mac. A default of 5432 keeps
  every other machine unchanged.

## D2. Node 24 via fnm, native arm64 (2026-11-08)
- **Decision:** Node 24 installed with fnm, explicitly as arm64; `.node-version` pins 24.
- **Alternatives:** `brew install node@24` (x86_64 under Rosetta, slower), official installer.
- **Why:** version manager like the owner used on Windows; native arm64 avoids Rosetta.

## D3. Inject axe-core ourselves (2026-11-08)
- **Decision:** load a pinned `axe.min.js` into the page and call `axe.run()`.
- **Alternatives:** `axe-playwright-python` (small third-party wrapper), `@axe-core/playwright`
  (official but JavaScript-only, would need a Node sidecar).
- **Why:** about 15 lines, fully explainable, pinned version visible in the repo.

## D4. Tonight's provider: Ollama with qwen3-vl:8b (2026-11-09)
- **Decision:** installed the Ollama app (native arm64, Homebrew cask) and pulled `qwen3-vl:8b`.
  `.env` has `LLM_PROVIDER=ollama`.
- **Alternatives:** FakeClient only (then every real-model acceptance check would be "Needs
  me"); a smaller model such as `qwen3-vl:4b` (faster, weaker); a larger one (doesn't fit well
  in 16 GB next to Chromium, Postgres and Next.js).
- **Why:** there's no Anthropic API key in `.env`. The owner's standing instruction is to
  install safe dev tools without asking. The Mac has 16 GB RAM: an 8B model (~6 GB) is the
  largest that leaves room for the rest. It supports both images and tool calls, which the
  agent loop needs.

## D5. One codebase, two shops, via Vite mode (M1)
- **Decision:** every planted bug is guarded by `bug(n)` in `apps/demo/src/bugs.ts`, which is
  false when Vite runs with `--mode clean`. `vite` serves the buggy shop on 5173,
  `vite --mode clean` the clean one on 5174.
- **Alternatives:** an env variable set on the command line (`VITE_CLEAN=true vite`) — breaks
  on Windows `cmd`; two copies of the code — they'd drift apart.
- **Why:** cross-platform, and `grep "bug("` lists every planted bug in one place.

## D6. A fake backend inside the Vite dev server (M1)
- **Decision:** a small Vite plugin (`demoApi` in `vite.config.ts`) answers `/api/profile`
  (500 in the buggy build) and `/return-policy` (404).
- **Alternatives:** a separate Express server (another process and port to manage); mocking in
  the browser (then there'd be no real HTTP errors for the checker to see).
- **Why:** bugs 2 and 3 need real HTTP status codes. A Vite SPA answers 200 for every path, so
  a real 404 has to come from the server.

## D7. Bug verification with Playwright for Node (M1)
- **Decision:** `apps/demo/verify/bugs.e2e.ts` runs each bug check against both builds as two
  Playwright projects (`buggy`, `clean`); each test expects the bug only on `buggy`.
- **Alternatives:** Python Playwright in the worker (mixes target-app checks into the agent's
  code); manual checking.
- **Why:** the check belongs with the demo app, and M6 needs Node Playwright for the web
  e2e test anyway.
