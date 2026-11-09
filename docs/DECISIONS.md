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

## D8. Prisma pinned to 7.10.1 (M2)
- **Decision:** `prisma` and `@prisma/client` pinned to exactly 7.10.1.
- **Alternatives:** whatever `npm install` picks: on 2026-11-09 the `latest` tag pointed at
  `8.0.0-rc.33`, a release candidate, while `@prisma/client` resolved to 7.10.1 (mismatched).
- **Why:** a stable, matching pair. Revisit when Prisma 8 is released as stable.

## D9. The database generates ids and timestamps (M2)
- **Decision:** ids use `@default(dbgenerated("gen_random_uuid()"))`, timestamps `now()`;
  tables and columns are snake_case via `@map`.
- **Alternatives:** Prisma's `@default(uuid())` (generated in JavaScript only); camelCase columns.
- **Why:** Python inserts rows too. A default that lives in JavaScript would leave Python
  inserts without ids. snake_case keeps raw SQL and the SQLAlchemy mirror readable.

## D10. Python tests apply Prisma's migration SQL directly (M2)
- **Decision:** the pytest fixture creates `agent_test` and runs
  `apps/web/prisma/migrations/*/migration.sql` in order. `test_db_models.py` compares the
  SQLAlchemy mirror with the resulting tables (names, columns, nullability).
- **Alternatives:** `Base.metadata.create_all()` (tests would run against the mirror, not the
  real schema, so drift would go unnoticed); calling `npx prisma migrate deploy` from pytest
  (Python tests would need Node).
- **Why:** tests run against the real schema, with no Node dependency, and drift fails a test.
  It caught one on day one: Prisma creates `Int[]` columns as nullable.

## D11. One-shot agent requests, tool_choice "auto" (M2)
- **Decision:** each agent step is one request (system prompt + tools + current observation);
  memory of earlier steps is a short summary inside the observation, not a growing chat history.
  `tool_choice` is `auto` with `strict` tools and `disable_parallel_tool_use`.
- **Alternatives:** a growing multi-turn conversation; `tool_choice: any`.
- **Why:** constant cost per step (no ever-growing history), the system prompt and tools form a
  stable cacheable prefix, and it works the same for Claude and Ollama. `tool_choice: any` is
  rejected by Claude Sonnet 5.5 (400), so "always call exactly one tool" goes in the prompt.

## D12. Effort "medium" and refusal fallback on agent calls (M2)
- **Decision:** agent decisions use `output_config.effort = "medium"` and the server-side
  refusal fallback (`fallbacks: "default"`).
- **Alternatives:** the model default (`high`, more thinking tokens per step); `low`.
- **Why:** a step is a small decision; medium keeps thinking (billed as output) modest. To be
  re-tuned with benchmark numbers once a Claude key is available. Untested against the live
  API tonight (no key): see Needs me.
