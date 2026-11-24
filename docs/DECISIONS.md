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

## D13. SSRF guard enforced by an egress proxy, not request interception (M3)
- **Decision:** the browser's traffic goes through `GuardProxy`, a small proxy inside the
  worker. It checks host:port for every request (HTTPS via `CONNECT`) and connects to the exact
  IP it vetted. Chromium's implicit localhost bypass is turned off (`<-loopback>`).
- **Alternatives:** Playwright `context.route` interception (first attempt); Chromium host
  resolver rules; a separate proxy service such as Squid or smokescreen.
- **Why:** a test showed that `context.route` sees only the first request of a redirect chain:
  a site that redirects to `http://10.0.0.5/` got past it, and the browser really tried to
  connect. Through a proxy every redirect hop is a new request. Connecting to the vetted IP
  also prevents DNS rebinding. A separate service (smokescreen) is what I'd use in production;
  the in-process proxy is ~150 lines, testable, and has no extra infrastructure.

## D14. Findings grouped by problem, deterministic = confirmed (M3)
- **Decision:** the same console error / failing URL / axe rule / broken link on several pages
  is one bug, with every page listed in its evidence. Deterministic findings start as
  `confirmed`. Chrome's "Failed to load resource" console echo is dropped (the failed request
  is already a finding); axe runs WCAG A/AA rules only.
- **Alternatives:** one bug per page per finding (a broken header = one bug per page); including
  axe's best-practice rules.
- **Why:** a report a developer can act on. Best-practice rules are advice, and counting them
  would make false alarms on the clean shop depend on taste.

## D15. Screenshot review is part of the passive scan, findings stay "candidate" (M3)
- **Decision:** after the crawl the model reviews up to REVIEW_PAGES screenshots (default 6)
  for visual/UX problems; results are `agent` / `candidate` bugs, within the run's cost budget.
- **Alternatives:** no model in passive mode; review every page.
- **Why:** the brief asks for it, and some bugs (a "$NaN" price) are invisible to deterministic
  checks. Capping pages keeps cost predictable; replay (M5) decides whether candidates are real.

## D16. Local model: qwen3-vl:8b-instruct, not the default qwen3-vl:8b (M4)
- **Decision:** use the instruct (non-thinking) variant; removed the thinking one.
- **Alternatives:** `qwen3-vl:8b` (the default tag, a thinking model); `qwen3-vl:4b-instruct`.
- **Why:** measured on this Mac (16 GB, ~10 tokens/s): the default tag ignores `think: false`
  and wrote ~1,500 hidden reasoning tokens per step (3 minutes per step). The instruct variant
  answers the same agent observation in 36 tokens, ~14 s per step. The 4B model would be faster
  but noticeably weaker at tool use; 8B is the best fit for 16 GB.

## D17. Agent observations: numbered elements tagged in the DOM (M4)
- **Decision:** a script finds visible interactive elements, numbers them, and tags each with a
  `data-agent-id` attribute. The model sees `[7] button "Apply"`; the worker acts on
  `[data-agent-id="7"]`. Page text goes in a `<page_content>` block marked untrusted.
- **Alternatives:** raw HTML (huge and noisy); Playwright's ARIA snapshot (YAML, no stable ids
  to act on); coordinates from the screenshot (needs vision every step).
- **Why:** small observations (cheap, fast on a local model), and the model can only point at
  elements that exist. The attribute is a tiny DOM change; a site that reacts to unknown
  attributes is very unlikely.

## D18. Interactive runs start with the deterministic scan (M4)
- **Decision:** an interactive run first does the free crawl + checks (no screenshot review),
  then the agent loop with the remaining time and cost budget. Console errors and failed
  requests seen during the agent's session become deterministic findings too.
- **Alternatives:** agent loop only.
- **Why:** "deterministic checks first" (brief §8): they're free and catch the obvious bugs, so the
  model's budget goes to what only a model can find (wrong totals, validation, flows).

## D19. Interactive mode limited to the demo shop until domain verification exists (M4)
- **Decision:** interactive runs on anything other than the demo shops fail with a clear error.
  M8 adds verified domains.
- **Why:** rule: interactive mode only on verified domains. Refusing is the safe default.

## D20. Agent feedback for small models: "nothing changed", a loop warning, login guidance (M4)
- **Before (M4 run 1, qwen3-vl:8b-instruct, buggy shop):** 20 steps (11 page visits + 9 agent
  steps), 154 s, $0. The agent logged in with the generated test email instead of the demo
  account shown on the login page, reported "Login with valid credentials fails" (a false alarm),
  then clicked "Log in" until loop detection stopped the run. Bugs 5–12 found: 0 of 8.
- **Changes:** (1) the task now says to log in with an account the site offers (demo
  credentials) and that a made-up account failing is not a bug; (2) a click that leaves the page
  unchanged returns "ok, but nothing on the page changed" instead of "ok"; (3) after two
  identical actions the observation warns that a third ends the run.
- **Alternatives:** a bigger local model (doesn't fit well in 16 GB); a scripted plan per site
  (overfits the demo shop).
- **Why:** a small model can't tell "ok" from "it worked". These are generic, honest signals
  that any site benefits from, not hints about the planted bugs.

## D21. Replay every agent action up to the report; show the model what changed (M4/M5)
- **Before (M4 run 2):** the agent walked product → cart → checkout and filed 2 vague "cart
  status" reports (the header shows "Cart (0)" after an order, which is correct). Replay
  dismissed both, but because it couldn't repeat the steps: it replayed only the step numbers
  the model listed, the model had left out "Add to cart", so "Cart (1)" never existed.
- **Changes:** (1) replay repeats every non-blocked agent action from the start of the agent
  loop up to the step where the bug was reported (stored in the bug's evidence); (2) an
  action's result says what appeared on the page ("ok; new on the page: Cart (2) | Added to
  your cart.").
- **Alternatives:** trust the model's step list (unreliable); replay from a stored browser state
  snapshot (doesn't prove the steps reproduce the bug).
- **Why:** replay must reach the same state as the original session, and the model's own list
  isn't reliable enough for that. Showing what changed gives a small model the signal a human
  tester gets by looking at the screen.

## D22. Worker Python environment rebuilt on native arm64 (Mac setup)
- **Problem:** `uv` on this Mac is the Intel build (it runs under Rosetta), so it picked the
  Intel Python 3.12 and installed Intel builds of compiled packages (pydantic-core, psycopg…).
  Under `uv run` everything stayed Intel and worked; a native arm64 shell that started
  `.venv/bin/python` directly got "incompatible architecture" errors (and `uv run` from a
  background shell failed to spawn the worker).
- **Decision:** installed uv's managed `cpython-3.12-macos-aarch64` and recreated `.venv` with
  it (`uv sync --python cpython-3.12-macos-aarch64-none`). `.python-version` stays `3.12`, so
  Windows and CI are unchanged.
- **Alternatives:** keep everything under Rosetta (slower, and fragile as shown); pin the full
  interpreter name in `.python-version` (breaks other platforms).
- **Why:** native is faster and works the same from every shell. Same lesson as Node (D2): on
  an Apple Silicon Mac with an Intel Homebrew, check the architecture of every toolchain.

## M4/M5 measurements with the local model (2026-11-09, qwen3-vl:8b-instruct, $0)

| Run | Shop | Steps | Agent reports | After replay | Planted bugs 5–12 found |
|---|---|---|---|---|---|
| M4 run 1 (before D20) | buggy | 20 | 1 (login, false) | (no replay yet) | 0/8 |
| M4 run 2 (after D20) | buggy | 30 | 2 ("cart status", false) | 0 (both dismissed) | 0/8 |
| M4 run 3 (after D21) | buggy | 25 | 0 | 0 | 0/8 |
| M5 interactive | clean | 35 | 0 | 0 | n/a |
| M5 passive + screenshot review | clean | 17 | 0 | 0 | n/a |

Conclusion: the pipeline works end to end (scan → agent → replay → dedup, steps and cost
recorded), and the deterministic part finds bugs 1–4 every time. The local 8B model explores
flows but rarely judges what it sees; it reached bug 5's state without reporting it. Claude
numbers are the real test (Needs me).

## D23. Web app stack details (M6)
- **Decision:** shadcn/ui on Radix with the "Nova" preset (Lucide icons, Geist font), one indigo
  accent, `next-themes` for light/dark (system default + toggle); the live run page polls
  `/api/runs/[id]` every 1.5 s and stops polling at a final status; database pages call
  `await connection()` so they render per request; Prisma 7 with the `pg` driver adapter.
- **Alternatives:** Server-Sent Events or WebSockets for live updates; Next's Cache Components.
- **Why:** polling is what the brief allows, works through any proxy, and is one `setInterval`
  to explain. The worker writes to Postgres, not to the web app, so a push channel would need
  `LISTEN/NOTIFY` plumbing for little gain at a 1.5 s cadence.
- **Note:** M6 work started while the last M4/M5 measurement runs (local model) were still
  running in the background; those milestones' outcomes didn't depend on M6 code.

## D24. Stale run recovery (M6)
- **Decision:** when a worker starts, runs that have been "running" for longer than the time
  budget plus 5 minutes are marked failed ("the worker stopped before the run finished").
- **Why:** the e2e test exposed it: Playwright stopped its worker mid-run and that run stayed
  "running" forever. A heartbeat column would detect it sooner; this is the simple version.

## D25. Auth.js v4 with our own small adapter and JWT sessions (M8)
- **Decision:** `next-auth` 4.24.15 (stable) with GitHub OAuth and email magic links, each
  enabled only when its env vars are set, plus a "sign in as demo user" credentials provider in
  development only. JWT sessions carry user id + workspace id. A ~100-line adapter over our
  Prisma client creates the user's personal workspace in the same transaction as the user.
- **Alternatives:** Auth.js v5 (`next-auth@5`, still beta after two years: 5.0.0-beta.32);
  the stock `@auth/prisma-adapter` (expects `@prisma/client` imports and can't create a
  workspace with the user); Clerk or another hosted auth (a paid sign-up, and less to explain).
- **Why:** stable over beta for a product. Our schema requires every user to have a workspace,
  so user creation must be ours. JWT sessions are required by the credentials provider and
  mean no session table lookups.

## D26. Visitors share a public demo workspace; limits checked in one place (M8)
- **Decision:** signed-out visitors act in the "demo" workspace and may only test the demo shop,
  5 runs per IP per hour (counted from the audit log). `startRun` is the single gate: input,
  visitor rules, monthly quota (default 50), then the audit entry.
- **Why:** the landing page's "Try it on our demo shop" must work without sign-up, but a
  visitor must not be able to point the worker at arbitrary sites.

## D27. Domain verification by DNS TXT or well-known file, SSRF-checked (M8)
- **Decision:** a per-workspace token (`workspaces.verification_token`), proven by a TXT record
  `ai-test-agent-verification=<token>` or `/.well-known/ai-test-agent.txt`. The file check
  resolves the host first and refuses private addresses, doesn't follow redirects, 5 s timeout,
  1 KB max. The worker allows interactive runs only on verified hostnames of the run's workspace.
- **Why:** interactive tests type and submit forms, which is only OK on sites you own. The
  file check is a server-side fetch of a user-chosen URL, so it gets the same SSRF care as the
  worker.

## D28. Database tests for the web app (M8)
- **Decision:** Vitest global setup creates `agent_web_test` and runs `prisma migrate deploy`;
  `*.db.test.ts` files run against it (skip locally without Postgres, fail in CI with
  `REQUIRE_DB=1`). CI's TypeScript job now has a Postgres service.
- **Why:** workspace isolation is a property of real queries; mocking the database would test
  the mock.

## D29. The agent never acts on another site (after demo v1)
- **Decision:** the agent loop checks the origin in three places: the target itself must not
  redirect to another origin (the run stops), a link to another origin is refused before the
  click, and after every action the worker checks where the page is and goes back to the last
  page on the target if it left (the step is marked blocked, so replay skips it).
- **Alternatives:** block off-origin main-frame navigations in the proxy (it can't tell a page
  load from an image or script request); allow the origin the target redirects to (a verified
  domain could then point the agent at a site its owner doesn't control).
- **Why:** before this, only the `navigate` tool was origin-checked. A click on an external
  link moved the agent to a third-party site, where interactive mode kept typing and
  submitting, which is exactly what domain verification is meant to prevent.
- **Same site:** the same origin, or the https version of an http target on the same host
  and default ports (`urls.is_same_site`), so a site that upgrades `http://shop.example` to
  `https://shop.example` still works. The crawler and the `navigate` check use the same rule.
  Subdomains, other ports and a downgrade to http are another site.

## D30. Loop detection counts repeats without effect (after demo v1)
- **Decision:** the same action 3 times in a row is a loop only when none of them changed the
  page (URL, page text or scroll position). The same action 6 times in a row
  (2 × `MAX_REPEATED_ACTIONS`) is a loop even when the page changes every time.
- **Alternatives:** keep "same action 3 times" (it ended runs that clicked "+" three times or
  scrolled a long page, which is what finding bugs 5 and 7 takes); count only no-effect
  repeats with no upper limit (a model that adds to the cart forever would run to the step
  budget).
- **Why:** repeating an action that works is testing; repeating one that does nothing is
  being stuck. The step result already knew the difference ("nothing on the page changed").

## D31. The benchmark judge is pinned separately from the agent (after demo v1)
- **Decision:** `JUDGE_PROVIDER` / `JUDGE_MODEL` choose the model that matches reports to
  planted bugs (`llm.make_judge`). The judge's name is saved with every benchmark result
  (`details.judge`) and printed. Empty settings keep the old behaviour, with a warning when a
  local model judges itself.
- **Alternatives:** keep using the agent's client (with Ollama the judge was the model under
  test, so the qwen and gemma results were graded by different judges); hard-code one judge
  model (it would break for anyone who hasn't downloaded it, and for Claude-only setups).
- **Why:** a benchmark compares agents, so everything else has to stay fixed, including who
  decides what counts as a match.

## D32. Safe mode is a table of rules, and the demo shops are fully exempt (run 2, G1.2)
- **Decision:** `DENY_RULES` in `agent/policy.py`: each rule has a category, a phrase for the
  block reason and a whole-word pattern. A click is checked against the control's text,
  aria-label, button value, link path + query and form action (URL paths are split into words,
  so `/billing/cancelSubscription` reads "cancel subscription"). Text fields are skipped: what
  a user typed isn't an action. On our own demo shops nothing is denied.
- **Alternatives:** the old flat list of nine words ("Place order", "Confirm" and "Cancel
  subscription" passed); an allow list (the agent could do almost nothing on a new site); ask
  a model whether a click is safe (a safety rule must not depend on the thing it restrains).
- **Why:** these are the actions that commit to something or can't be undone on a real site.
  A table is easy to read, extend and test row by row. Before, the demo shop was exempt only
  for "buy"; it is fake end to end, so a full exemption is simpler and lets the agent test
  checkout there.
- **Cost:** on a real site the agent can't test deleting or removing things. That is the point
  of safe mode; an opt-in "allow destructive actions on this domain" would be the next step.

## D33. The visitor rate limit uses the socket address unless a proxy is trusted (run 2, G1.3)
- **Decision:** `clientIp` ignores `X-Forwarded-For` unless `TRUST_PROXY=true`, and then takes
  the entry `TRUSTED_PROXY_HOPS` from the right (the one our proxy appended). Otherwise it
  reads `x-socket-address`, a header `instrumentation.ts` stamps on every request from the TCP
  socket, overwriting whatever the client sent. With neither, all such requests share the
  bucket "unknown".
- **Alternatives:** the left-most forwarded entry (the old code: any client can write it); a
  custom Node server to reach the socket (changes how the app starts and deploys);
  `NextRequest.ip` (removed from Next.js).
- **Why:** Next.js route handlers only see headers, and it fills `x-forwarded-for` from the
  socket only when the client didn't send one. Wrapping `http.Server.prototype.emit` is a
  small, visible hook that runs before Next.js sees the request.
- **Weak spot:** it patches a Node built-in, and in dev the hook loads with the first request,
  so that one request counts as "unknown". Runtimes without a Node HTTP server (edge) also
  get "unknown", which is stricter, never looser.

## D34. Limits and the insert run in one transaction that locks the workspace row (run 2, G1.3)
- **Decision:** `startRun` opens a transaction, runs `SELECT ... FROM workspaces WHERE id = ?
  FOR UPDATE`, counts the visitor's recent runs and the month's runs, and inserts the run.
- **Alternatives:** a counter column updated with one conditional UPDATE (needs a monthly
  reset and a second source of truth next to the runs table); SERIALIZABLE isolation (callers
  must retry on serialization failures).
- **Why:** check-then-insert let a burst of requests each see "one run left". The row lock
  makes requests for one workspace queue up; other workspaces aren't affected. A test fires
  10 at once with a quota of 3 and gets exactly 3.

## D35. A share token opens that run's screenshots, nothing else (run 2, G1.4)
- **Decision:** shared report pages request images as `/api/files/<run id>/<file>?share=<token>`.
  `canReadFile` allows a file when its run is in the caller's workspace, or when the token is
  the share token of the run named in the path.
- **Alternatives:** make screenshots public by URL (run ids would become secrets); signed,
  expiring URLs per image (more moving parts for the same guarantee).
- **Why:** shared reports showed broken images to everyone outside the workspace. Revoking
  the link clears the token, so the images stop working with it.

## D36. The domain file check connects to the address it validated (run 2, G1.5)
- **Decision:** `fetchPinned(url, ip)` uses `node:https` with a `lookup` function that always
  answers the validated address. The URL keeps the hostname, so the Host header and the TLS
  certificate check are unchanged.
- **Alternatives:** `fetch(url)` after the check (resolves the name a second time: DNS
  rebinding can answer public first and private second); fetch `https://<ip>/` with a Host
  header (TLS would check the certificate against the IP and fail).
- **Why:** it is the same rule the worker's proxy follows: check an address, then connect to
  that address.

## D37. Claude client: 16,000 max tokens, Sonnet 5.5 cache reads at $0.10 (run 2, G1.6)
- **Decision:** `MAX_TOKENS = 16000` for every Claude call; a reply cut off at the limit is
  labelled in the step. Sonnet 5.5's cache-read price is $0.10 per million tokens.
- **Why:** Sonnet 5.5 always thinks and thinking counts toward `max_tokens`; at 4,096 a reply
  could end before the tool call and waste the step. The price was listed as $0.20, which
  overstated cost. Untested against the live API (no key in this run).

## D38. Four more tester's tools: double_click, reload, set_viewport, note (run 2, G2.1)
- **Decision:** the agent gets `double_click`, `reload`, `set_viewport` ("desktop" 1280×800 or
  "mobile" 375×812) and `note` (up to 20 lines kept in every later observation). Replay repeats
  each one exactly (a double-click stays a double-click). The passive scan also stores a 375 px
  screenshot of every page, the model reviews both widths, and a phone-width finding is
  verified at phone width.
- **Alternatives:** free-form viewport sizes (more to get wrong for little gain); a scratchpad
  inside the model's reasoning (lost after each step: the loop is stateless per call).
- **Why:** these are things a manual tester does all the time: double-submit a button, refresh
  to see what survives, check a phone screen, write down a total before changing it. Without
  them some bug kinds were impossible to find, whatever the model.

## D39. The observation shows field state and where each message sits (run 2, G2.2)
- **Decision:** every field lists required/invalid and the visible text tied to it by
  `aria-describedby`/`aria-errormessage`. A new MESSAGES section lists visible error, alert and
  status messages with the field they sit next to: the only field in the same group, else the
  closest field within 60 px above or below. "What changed" keeps 600 characters and lists
  changed values first, with the old value ("Subtotal: $12.00 → $24.00").
- **Alternatives:** send the HTML (expensive, and the model would have to work out layout);
  rely on the screenshot (small models read layout poorly and screenshots aren't sent every step).
- **Why:** "the error appears under the wrong field" is invisible in plain page text, and most
  functional bugs show up as a number that didn't change the way it should.

## D40. A generic QA test charter in the system prompt (run 2, G2.3)
- **Decision:** eight techniques: boundary values, invalid input and where its error sits,
  arithmetic on totals, doing things twice, state after reload/logout, small screens, actions
  that do nothing, nonsensical values. A test fails if any name, code or address from our demo
  apps appears in the prompt or tool descriptions.
- **Alternatives:** per-site instructions (overfitting: it would score well on our shop and
  teach nothing about other sites); no guidance (the old prompt; small models clicked around
  without checking results).
- **Why:** it is what a careful human tester does on any site. The prompt stays byte-identical
  across steps so it can be cached.

## D41. Replay finds the exact element or fails loudly, starts at the last navigation, and runs after dedup (run 2, G2.4)
- **Decision:** each step records role, name, its place among same role+name elements, the
  nearby text and a CSS path. Replay uses role+name, then nearby text, then the CSS path, then
  the position only if the page has the same number of matches; otherwise it raises, and the
  bug is dismissed with "could not replay: <why>". Replay first starts at the last `navigate`
  before the report (carrying a viewport change along); if that doesn't reproduce the bug, it
  replays from the start. Dedup now runs before replay, and deterministic findings are never
  replayed.
- **Alternatives:** keep "first match" (it clicked the wrong "Add to cart" and confirmed or
  dismissed the wrong thing); replay only the steps the model listed (models forget the step
  that set up the state); record coordinates (break on any layout change).
- **Why:** a verdict on the wrong element is worse than no verdict. Starting late avoids
  repeating side effects such as a second order. Before, an agent report of a server error was
  replayed, the model couldn't see a failed request on screen, and a real bug was dismissed.

## D42. AI-only recall is the headline number for comparing models (run 2, G3.1)
- **Decision:** every benchmark result stores and shows two recalls: over all planted bugs, and
  over the bugs whose `detection` in `bugs.json` is "agent" (those the deterministic checks
  can't find). The CLI, the database (`ai_recall`), the README and the page lead with AI-only.
- **Alternatives:** keep one recall (it hid that the AI found nothing: 33% came entirely from
  free checks); drop deterministic bugs from the benchmark (the product does find them, and
  users care about the total).
- **Why:** the deterministic checks score the same for every model, so they make all models
  look alike. Only the AI-only number moves when the model gets better.

## D43. A holdout app the agent is never tuned against (run 2, G3.4)
- **Decision:** `apps/demo2`, a room-booking app on 5175 (clean build 5176) with six planted
  bugs of the same kinds as the shop (API failure, unlabelled field, wrong total, accepted
  invalid input, double submit, mobile overflow) and different specifics, its own `bugs.json`
  and `verify-bugs`. `bench` runs it 2× buggy + 1× clean by default and reports it separately.
  A unit test fails if any title, product name, code or address from either app reaches the
  prompt or tool descriptions.
- **Alternatives:** test on real public sites (no ground truth, and interactive mode needs
  ownership); a holdout made of more shop pages (same codebase and wording, not a real
  generalisation test).
- **Why:** every prompt change is made while watching the agent on the shop, so the shop score
  can drift towards "learned the shop". A separate app with unseen specifics shows whether the
  techniques generalise.

## D44. A rescore keeps the original commit (run 2, G3.3)
- **Decision:** `bench --rescore` saves a new row with the `git_commit` of the row it rescored
  and its own commit in `rescore_commit`. The page shows "abc1234 (rescored at def5678)".
- **Why:** a rescore re-matches old runs; it says nothing about the agent at the new commit.
  Before, a rescored row looked like a fresh benchmark of newer code.

## D45. The step screenshot is taken before the action, with the target's box (run 2, G4)
- **Decision:** each agent step saves the viewport screenshot the model looked at (taken in
  `_observe`, before the action) plus the chosen element's bounding box and the viewport size.
  The run page's "Live browser" pane draws the box over the screenshot in percentages, follows
  the newest step while the run is live, and has a clickable filmstrip.
- **Alternatives:** keep the after-action thumbnail (it can't show "what the agent is about to
  click": after a click the element may be gone); stream video from the browser (a media
  pipeline for a demo feature); a full-page screenshot per step (slower, and the box would
  need scroll offsets).
- **Why:** seeing the page and the outlined target is the fastest way to understand what the
  agent did and why. Reusing the existing screenshot and 1.5 s polling keeps it cheap. The
  result of an action shows in the next step's screenshot.

## D46. One OpenAI-compatible client for "any model" (run 2, G5.1)
- **Decision:** `OpenAICompatClient` speaks `POST {base_url}/chat/completions` with function
  tools and images as data URLs, and sends only parameters every major server accepts (no
  temperature, max_tokens or parallel_tool_calls). A tool call written as JSON text is still
  read. Prices come from configuration.
- **Alternatives:** one client per provider (more code, same request shape); LiteLLM or a
  similar router (a large dependency that hides the request the project should be able to
  explain).
- **Why:** OpenAI, Gemini, OpenRouter, Groq, LM Studio, vLLM and Ollama's /v1 all share this
  API, so one small, tested client reaches most models.

## D47. Workspace model keys: AES-256-GCM, workspace id as associated data (run 2, G5.3)
- **Decision:** keys are encrypted by the web app with `MODEL_KEYS_SECRET` and decrypted only
  by the worker, right before building the client. The workspace id is GCM's associated data,
  so a ciphertext copied into another workspace's row fails to decrypt. Only "•••• last4" is
  ever returned. A shared test vector proves Node and Python agree on the format.
- **Alternatives:** plain text (a database leak leaks every customer key); a hosted KMS
  (better key rotation, but a paid service and outside this repo's rules); hashing (a key
  must be usable, so it has to be decryptable).
- **Why:** it is the standard way to keep a secret usable but protected at rest, and binding
  it to the workspace turns "workspace A can't use B's key" into a property of the crypto,
  not only of the queries.
- **Weak spot:** one server key for everything, no rotation yet.

## D48. Test connection before any run, checked again by the worker (run 2, G5.2)
- **Decision:** a probe sends one tool-call request and one image request ("what colour is
  this red square?"). The model passes only if it answers, calls the tool and says "red". The
  result is stored; `startRun` refuses a model that hasn't passed, and the worker checks the
  stored result again before spending the key. The probe connects to the address it
  validated (same SSRF rule as domain verification; private addresses only in dev mode).
- **Why:** the agent cannot work without tool calls or vision. Finding that out on step 1 of a
  run wastes the user's time and money; a 2-call check up front gives a clear reason instead.

## D49. claude-cli: the owner's Claude login for local testing only (run 2, G5.4)
- **Decision:** `LLM_PROVIDER=claude-cli` runs `claude -p` (Sonnet for decisions, Haiku for
  cheap calls), asks for one strict JSON tool call, validates it against the tool schema,
  retries once with the reason, then ends the step with an error. Cost is recorded as $0. It
  refuses to start without `DEV_MODE=true` or when `NODE_ENV`/`ENV` is production, and the
  workspace UI never offers it.
- **Why:** it lets the owner see a strong model drive the agent without buying API credit.
  It shares the owner's Pro limit with their own Claude Code use, so it is used sparingly.

## D50. A model leaderboard on the benchmark page (run 2, G5.5)
- **Decision:** one row per provider and model (its newest result), ranked by AI-only recall,
  then overall recall; rows without AI-only recall go last instead of counting as 0%.
- **Why:** it is the product's promise made concrete: bring any model, and see how it scores
  here before you trust it.

## D51. ESLint with the platforms' own recommended configs, and e2e + planted bugs in CI (run 2, G7)
- **Decision:** the web app uses `eslint-config-next` (core web vitals + TypeScript); both demo
  apps use ESLint's, typescript-eslint's and the React hooks recommended rules. `npm run lint`
  runs type checks, ESLint and ruff. CI gets an `e2e` job: Postgres service, Playwright
  browsers, `verify-bugs` for both demo apps, then the web app's end-to-end tests with the
  worker on the scripted FakeClient (`FAKE_SCRIPT`), so it costs nothing.
- **Alternatives:** a custom rule set (more to maintain and explain); running e2e only locally
  (it had already caught real breakage locally; CI makes it stick).
- **Why:** recommended configs are what reviewers expect, and planted bugs that silently
  disappear would make every benchmark number meaningless; CI now notices.

## D52. Three generic fixes found by reading the G6 Gemma runs (run 2, G6)
- **What the runs showed:** with the run-2 agent, Gemma 4 12B scored 0% AI-only recall (shop
  and holdout), down from 13%. Reading the steps: it *did* find "Save changes does nothing"
  (bug 8) for the first time, but replay dismissed it because an unrelated step from an
  earlier flow (typing a discount code in the cart) couldn't be repeated; it saw the "$NaN"
  price and wrote it in a note instead of reporting it; and it once passed `element_id` as
  the string "[10]", which wasted a step.
- **Decision:** replay also tries from the agent's last return to the start page (a new flow
  usually begins there), latest start first; the prompt says a note never replaces
  report_bug; `element_number` accepts 7, 7.0, "7" and "[7]".
- **Why:** all three are about how agents behave on any site, not about the demo shop. The
  first one matters most: a correct report thrown away by the verifier is worse than a missed
  one, because nobody sees it.

## D53. Why replay threw away correct reports, and the fix (run 3, H1)
- **What was wrong (three causes, found by reproducing run be495c9f's replays offline):**
  1. *Timing on single-page apps (the main cause).* A client-side link changes the URL with
     pushState, so there is no page load and "network idle" is already true: the next step
     looked for its field (`count()` doesn't wait) before the route had drawn it → "no textbox
     Quantity on the page". A fresh browser context per replay failed in exactly the same way,
     so the run-2 first guess (the shared context) was not the cause of those failures.
  2. *Judging too early.* The router renders a navigation in a transition: after the last click
     the URL was `/cart` but the text was still the product page, so the judge said "not the
     cart page" (bug 5).
  3. *Shared context (real, but secondary).* All replays shared one browser context, so a
     second replay saw the first one's cart (`Cart (6)` instead of `Cart (3)`): wrong verdicts,
     not failures.
  Plus: steps that errored in the agent's own run (typing letters into a number field) were
  repeated and failed replay.
- **Decision:** before an element step, wait (≤ 5 s) until the browser is on the page the
  agent was on and something matching the target exists; after the last step, wait until the
  DOM has been quiet for 500 ms (≤ 3 s); one fresh context per replay plan (one browser and
  proxy for the run, `guarded_browser`); skip steps whose recorded result was an error. Every
  failure gets a kind (`element_not_found`, `ambiguous_element`, `page_differs`, `timeout`,
  `navigation_error`, `action_failed`, `no_element_recorded`), the step number and a detail,
  stored as `evidence.replay_failure`.
- **Alternatives:** a fixed sleep after each step (slow everywhere, still too short somewhere);
  Playwright's auto-waiting `locator.click()` alone (it waits for one locator, but our target
  search tries role, text, CSS and position, and must not pick "the first match"); restoring a
  storage snapshot instead of replaying the sign-in (faster, but the replay would no longer
  prove the steps lead to the bug).
- **Why:** each wait is bounded and only as long as the page needs, and none of it is specific
  to the demo shop: any React/Vue/Svelte app with client-side routing behaves this way.
- **Weak spots:** a route that shows a loading state and then waits more than 500 ms for data
  can still be judged on the loading state; a page whose URL legitimately differs between runs
  (an order id) costs up to 5 s of waiting per step before it is tried anyway.
- **Measured (offline, `uv run worker reverify be495c9f`, no Sonnet calls):** before, 1 of 6
  agent reports confirmed and 4 "could not replay"; after, 6 of 6 replay, and with the pinned
  local judge (gemma4:12b) 6 of 6 are confirmed, incl. bug 5 (cart total) and bug 8 (Save
  changes). The original verdicts came from Sonnet, so the judge differs: the stored run is not
  changed. All 16 previously confirmed agent reports of 11 older runs still replay.

## D54. The verification funnel and "correct but discarded" (run 3, H2)
- **Decision:** scoring now matches *every* report of a buggy run, not only the ones that
  survived verification, and records how each one ended (`stage`: verified, judge_said_no,
  could_not_replay, duplicate; plus the replay failure kind). Recall, AI-only recall and
  precision still count only surviving reports (what the customer sees). New numbers:
  recall / AI-only recall *before* verification, false alarms before verification (clean-run
  reports incl. dismissed ones), the funnel (reported → verified, duplicates, discarded at
  replay by reason), **correct but discarded** (discarded reports that match a planted bug)
  and bugs lost (planted bugs a run found but lost entirely). Shown in `bench` output, on the
  leaderboard and on each latest-score card.
- **Alternatives:** new columns in `benchmark_results` (a migration for numbers nothing sorts
  or filters on); judging dismissed reports in a separate script (the numbers would not be
  next to the scores they explain).
- **Why:** run 2's lost Sonnet reports were invisible in every score. If "correct but
  discarded" is high, verification is too strict; if false alarms drop a lot from before to
  after, it is earning its keep. Duplicates are not sent to the judge (the report they
  duplicate already is), so the extra judge calls are only for discarded reports.
- **False alarms for claude-cli:** they were "not measured" in run 2 because the single
  Sonnet run had no clean run. The H7 benchmark run includes a clean run, so they are measured.

## D55. The demo sign-in flake was a CSRF cookie race; no SessionProvider (run 3, H3)
- **Cause (measured):** `e2e/signin-loop.mjs` signed in 50 and 60 times in fresh browsers: 2
  and 4 failures, each one `POST /api/auth/callback/demo → 200` with a redirect to
  `/api/auth/signin` (Auth.js's "CSRF token didn't match" path), then `/signin?callbackUrl=…`.
  Auth.js v4 mints a new CSRF cookie for *every* auth request that arrives without one. On
  the sign-in page `<SessionProvider>` fired `/api/auth/session` on load (twice in dev:
  StrictMode) and on focus; when one of those answered after the button's `/api/auth/csrf`,
  it overwrote the cookie, and the token the button posted no longer matched.
- **Decision:** remove `SessionProvider` (and `components/auth-provider.tsx`). Nothing calls
  `useSession`; pages read the session on the server; `signIn`/`signOut` don't need the
  provider. The sign-in flow is then strictly sequential (providers → csrf → callback), so
  only one token is ever minted. The e2e retry helper and the CI `retries: 1` are removed.
- **Alternatives:** retry the sign-in (hides the race, which real users hit too); set the
  CSRF cookie in a proxy before the page loads (copies Auth.js internals or self-fetches);
  disable StrictMode (halves the chance, doesn't remove it).
- **Check:** `e2e/signin.e2e.ts` asserts the sign-in page makes no auth requests before the
  click (failed before the fix with two `/api/auth/session` calls) and signs in 10 times in a
  row. Loop after the fix: 0 of 50 one at a time, 0 of 50 four at once, 0 of 50 right after a
  dev-server restart.
- **Weak spot:** a future client component that adds `useSession` would bring the provider
  and the race back; the e2e test above would catch it.

## D56. Queue proof, a lease for running runs, one index from EXPLAIN (run 3, H4)
- **Queue:** `test_queue_concurrency.py` starts 8 worker threads (own connections) at the same
  instant on 300 queued runs: each run claimed exactly once, none lost. No code change was
  needed: `FOR UPDATE SKIP LOCKED` was already right.
- **Lease:** `runs.heartbeat_at` (migration `20261111010000_run_lease`), set at claim and
  renewed every 15 s by a `Heartbeat` thread; any live worker fails runs silent for 60 s, every
  30 s, in one conditional UPDATE; times from the database clock; a frozen worker that wakes up
  re-reads its run under `FOR UPDATE` and doesn't overwrite "failed".
  - Alternatives: re-queue instead of fail (would silently repeat clicks on a customer's
    site); Postgres advisory locks held for the whole run (die with the connection, but a
    worker needs a connection open for 10+ minutes and they don't show in the table);
    only the start-time check (a dead worker's run waits for some worker to restart).
  - Not tested first: the 6 lines in `main()`'s polling loop that call recovery every 30 s
    (glue around the tested `recover_expired_leases`; testing the infinite loop would need a
    clock and loop-exit hooks for no extra confidence).
- **Indexes:** `scripts/db_perf.py` (10k runs, 500k steps) showed every hot query already on an
  index except the newest benchmark results (Seq Scan + sort of every row): added
  `benchmark_results(created_at)` (0.87 → 0.09 ms for 200 rows, 0.96 → 0.01 ms for 1). Nothing
  else added. `HOT_QUERY_INDEXES` in the drift test names each index and its query.
- **Docs:** `docs/DATABASE.md` (tables, keys, indexes, queue, lease, plans, Prisma/SQLAlchemy).

## D57. CI actions on their Node 24 majors (run 3, H5)
- **Decision:** `actions/checkout@v7`, `actions/setup-node@v7`, `astral-sh/setup-uv@v10.3.3`
  (exact: from v8 on setup-uv publishes no moving major tag, so `@v10` failed to resolve) (all
  declare `runs.using: node24`; latest releases July–October 2026). GitHub was forcing the v4/v6
  versions onto Node 24 with a deprecation annotation.
- **Checked:** the breaking changes between our versions and these (setup-uv: cache defaults,
  removed `pyproject-file`/`uv-file` inputs and old manifest format; setup-node: automatic
  caching when `packageManager` is set). We pass no setup-uv inputs and set `cache: npm`
  explicitly, so none changes our behaviour; uv's cache may be off on some events (slower,
  not wrong).
- **Alternative:** pin each action to a commit SHA (stronger supply-chain protection, but the
  owner would need to update SHAs by hand; noted for later).

## D58. Two fixes found while reading run-3 traces (run 3, H6)
- **Element id as a JSON list:** gemma4:12b sometimes sends `element_id: [10]`; it was refused
  ("there is no element [[10]]"), wasting 3 of 40 steps on the shop and 3 of 25 on the holdout.
  `element_number` now accepts a one-item list. Generic: a model's way of writing an id.
- **Benchmark commit label:** `bench` read `git rev-parse HEAD` when scoring, after the runs.
  Commits made during a 2-hour benchmark relabelled it with code the runs never used (run 2's
  1200 s row; run 3's H6 benchmark, which ran on f1bf08a but will show a later commit). Now
  the commit is read before the runs start. Earlier rows are not changed; PROGRESS says which
  code each one really ran.

## D59. Remind the model of charter techniques it hasn't tried (run 3, H6)
- **Evidence (MISS_ANALYSIS):** 11 gemma4:12b runs (shop and holdout) used double_click,
  reload and the mobile viewport **0 times**; the one Sonnet run used each. Gemma typed only
  ordinary values (quantity 1, valid emails, one-night stays). The planted bugs that need those
  techniques were never triggered: not missed by judgement, just never reached.
- **Decision:** each observation's budget line lists the charter techniques this run hasn't
  used yet (unusual value in a field, double_click, reload, mobile viewport), tracked from the
  steps taken; a technique disappears once used. The system prompt is unchanged (caching).
- **Alternatives:** a longer or louder charter in the system prompt (Gemma already ignores the
  one it has); forcing techniques at fixed steps (scripted, not testing); per-form checklists
  (needs form understanding the agent doesn't have).
- **Why generic:** the four techniques are from the charter and apply to any site; the
  "unusual value" check looks only at the typed text and whether the field's name mentions
  mail. No page, product or bug of either app appears in it.
- **Rule:** kept only if the holdout results don't drop (measured below in PROGRESS).

## D60. A note's result says notes are never reported (run 3, H6)
- **Evidence:** in 5 gemma4:12b shop runs the model wrote the note "Wool Socks price is NaN"
  and reported it in only one of them. Run 2's line in the system prompt ("a note is never a
  substitute for report_bug", D52) didn't change that.
- **Decision:** the result of `note` (what the model reads on its next step) says notes are
  only for the model and are never reported, and to report a problem now with report_bug.
- **Alternatives:** detect problem words in notes ("NaN", "wrong", "broken") and file a bug
  automatically (the model's note is not a checked report: no expected/actual, no steps);
  ask the model at the end of the run to review its notes (one more call per run, and late:
  the replay steps would be far behind).
- **Why generic:** it is about how the tool works, not about any site. Measured together with
  D59 in the second Gemma benchmark; the holdout decides.

## D61. A failed model call ends the run, it doesn't fail it (run 3, H6)
- **What happened:** in the second Gemma benchmark one `decide` call took longer than the
  Ollama client's 300 s timeout. The exception went up through the agent loop and the run
  became "failed": 42 steps of work, and its reports were never verified.
- **Decision:** the loop catches a failed decision (any exception from `llm.decide`), stops
  with `stop_reason = "the model call failed: <error>"`, and the run continues as normal:
  errors seen are added as findings, reports are verified, the run ends "done".
- **Alternatives:** retry the call (a model that hangs for 300 s once often hangs again, and
  each retry costs 5 minutes); a longer timeout (hides a stuck model for longer).
- **Note:** the benchmark that hit it was already running the old code; its failed run
  (9590b85f) is scored as it is and noted in PROGRESS.

## D62. The one Sonnet benchmark: full set, holdout included (run 3, H7)
- **Decision:** the single allowed claude-cli run is a full `worker bench`: shop 3 runs + clean,
  holdout 2 runs + clean, 480 s and 40 steps (be495c9f's settings), judge pinned to
  gemma4:12b. Before it, one Haiku call started exactly as the worker starts the CLI (temp
  folder, `--restricted`, Read allowed for that folder) was asked to read
  `apps/demo/bugs.json` and was refused. A watcher checked the runs for a usage-limit or
  model-call failure, to stop the benchmark at once without a retry; none happened.
- **Alternatives:** shop only (the plan's minimum). The holdout was added because Sonnet's
  runs are short (~4 min) and the queue ran the shop first, so a usage limit would still have
  left the shop result complete; the holdout is the only evidence that gains generalise.
- **Findings recorded, not acted on:** bug 7 turned out guessable (MISS_ANALYSIS), the clean
  builds have real unplanted bugs that count as false alarms, and one run finished early after
  a native tool-call attempt in `claude -p`. All three are under "Needs me": each changes the
  benchmark or needs another Sonnet run to verify, which this run doesn't allow.

## D63. A mislabelled benchmark row is corrected in place, with a note (run 4, J0)
- **What:** result rows `a4d5781c` (R3a) and `1eccde57` (its rescore) said commit 984755e;
  their runs were made on f1bf08a (the old bench read the commit after the runs, fixed by D58).
- **Decision:** set `git_commit` to f1bf08a and add `details.correction` saying what changed,
  when and why. The rows' scores are untouched; `rescore_commit` (984755e) stays, since that
  is where the rescore ran.
- **Alternatives:** leave it and explain in PROGRESS (the leaderboard would keep showing the
  wrong commit); add a new row (a duplicate result would count twice).

## D64. Expected vs. actual is checked by the worker, not by a second model call (run 4, J1)
- **Decision:** the model states `expect` with each state-changing action; the worker compares
  it with the page's changes (expected change missing, predicted value absent). Mismatches must
  be reported or dismissed with a reason; other actions are refused once, then the candidate
  expires as ignored.
- **Alternatives:** a second "did it match?" model call per action (doubles cost and latency;
  weak models agree with themselves); a structured expectation object with fields per value
  (small models fill nested JSON badly); no enforcement (a weak model ignores the reminder,
  as it ignored its own notes in run 3).
- **Kept only if** holdout AI-only recall doesn't drop and clean-build false alarms don't rise.

## D65. A timed-out model call gets one retry with a trimmed observation (run 4, J1)
- **Decision:** clients raise `ModelTimeout`; the loop retries once with a shorter observation
  and no image, then ends the run cleanly (D61).
- **Alternatives:** a longer timeout (hides a stuck model); retrying with the same observation
  (a long prompt is the usual reason a local model is slow).

## D66. claude-cli: an answer that came with native tool-call denials is retried with a correction
- **Decision:** `permission_denials` in the CLI's JSON mean the model tried a native tool call;
  the answer is discarded and one corrective message is sent. Within the existing limit of two
  attempts per decision.
- **Why:** in run 3 such an answer was a valid `finish` ("no tools available"), so parsing alone
  couldn't catch it.

## D67. A benchmark and regular workers keep to their own runs (run 4, J1)
- **What happened:** the first J1 Gemma benchmark was ruined. The e2e tests start a worker with
  the fake model on the same database; on startup it failed a 16-minute benchmark run that was
  alive (startup recovery looked only at the start time, against its own 480 s limit), then
  claimed every queued benchmark run and ran it with the fake model. Result `6a0d7e24` is kept,
  marked `details.invalid`, and hidden by `validResults` on the benchmark and home pages.
- **Decision:** `claim_next_run(only=…)`: a benchmark processes exactly the runs it queued;
  `skip_benchmark=True`: regular workers never claim runs in the benchmark workspace. Startup
  recovery (`recover_stale_runs`) never fails a run whose heartbeat is fresh.
- **Alternatives:** a separate database for e2e (fixes this trigger only; two production
  workers with different models would still mix); a "pinned worker" column (a schema change for
  what a workspace filter already expresses).
- **Process rule:** no e2e tests while a benchmark is running.

## D68. Testing apps behind a login: the worker signs in, the agent never knows how (run 4, J2)
- **Decision:** `login_setups` per workspace and target origin: a login form (URL, username,
  password encrypted with the model-key scheme, optional selectors) or a recorded Playwright
  storage state (encrypted). `guarded_browser(login=…)` signs in every context it opens, so the
  crawl, the agent and every replay are signed in. In the loop: the password and username are
  scrubbed from observations, steps, bug reports and replay prompts; password fields are masked
  in every screenshot; logout, change/reset password and delete/close account are denied on
  every target (the demo shops too); landing on the login page without going there means the
  session ended, so the worker signs in again (at most 3 times).
- **Only on demo shops and verified domains**, for runs and for Test sign-in: a worker that
  submits credentials wherever a workspace says would be an abuse tool.
- **Test sign-in** needs a browser, so the web app sets `check_requested_at` and a worker claims
  it with `FOR UPDATE SKIP LOCKED` and stores `{ok, detail, checkedAt}`; the detail is scrubbed.
- **The username is stored in plain text** (shown in settings so you know which account it is);
  only the password and the storage state are secrets. It is still scrubbed from everything the
  model or a report sees.
- **Alternatives:** let the agent sign in with credentials in the prompt (the model and its
  provider would see them, and the agent could type them anywhere); a separate check-jobs table
  (one nullable timestamp on the setup does the same for a quick, idempotent job).
- **Untested glue:** the worker loop calls `process_login_check` before each run (one line).

## D69. Public API: hashed keys, a database rate limit, the dashboard's own rules (run 4, J3)
- **Decision:** `/api/v1` with workspace API keys (`ata_` + 32 random bytes, SHA-256 hash with a
  unique index, shown once, revocable, `last_used_at`). Starting a run calls the same `startRun`
  as the dashboard, so quota, domain verification and model checks can't drift apart. Budgets
  (`max_steps`, `max_minutes`) can only lower the worker's limits. Rate limit: 60 requests per
  key per minute, a fixed window counted with one upsert in `api_rate_windows`. Reports as JSON
  or JUnit XML (one failing test case per reported bug). `openapi.json` is the contract; tests
  check every route and method against it and validate responses with ajv.
- **Alternatives:** bcrypt for keys (slow on every request, no benefit for random 256-bit keys);
  JWTs (can't be revoked without a deny list); an in-memory rate limiter (wrong with two web
  servers); a sliding-window or token-bucket limiter (smoother, more state; a fixed window is
  enough at 60/min); generating routes from the spec (more tooling for three routes).

## D70. Webhooks: HMAC over timestamp and body, retries in the database, the egress guard (J3)
- **Decision:** `X-ATA-Signature: t=<unix>,v1=<hex HMAC-SHA256(secret, "t.body")>` (the scheme
  Stripe made common); receivers refuse timestamps older than 5 minutes (replays). Deliveries are
  rows (`webhook_deliveries`) claimed with SKIP LOCKED; backoff 30 s, 2 min, 8 min, 32 min, ~2 h,
  then failed. URLs are refused at save time for obvious internal hosts, and at send time by the
  worker's `NetworkGuard` (after DNS); the POST goes through `GuardProxy`, which connects to the
  checked address (no DNS rebinding). A blocked URL fails without retries. No redirects followed.
- **Alternatives:** signing the body only (a captured request could be replayed forever); a
  message broker for retries (one more system; the database already is the queue); sending from
  the web app (it would need the egress guard too, and runs finish in the worker).
- **Tested against a local receiver only;** the `allowed_local` exemption exists for tests and is
  never set in production.

## D71. Two incidents during run 4, and the rules that follow
- An e2e run during a benchmark let a fake-model worker take over the benchmark (fixed in code,
  D67). Rule: no e2e tests while a benchmark runs.
- `pkill -f "worker$"` to stop a test worker also killed a Docker Desktop process: Postgres went
  down and the second J1 benchmark crashed. Docker Desktop was force-restarted, the data volume was
  intact (84 runs, 11 results), and the 7 aborted runs were marked failed with the reason. Rule:
  stop processes by PID only, never by a name pattern.
- The third J1 benchmark is labelled a0af21e but also loaded the uncommitted J3 code (API,
  webhooks, run budgets): none of it changes the agent (no budgets or webhooks on benchmark runs).

## D72. Fingerprints and triage that follows them (run 4, J4)
- **Fingerprint** = SHA-256(route with ids normalised | category | key), first 16 hex. The key is
  the most stable thing that names the problem: the failing request (method, path, status), the
  console message without numbers or hashes, the axe rule, the broken link, the element an agent
  report acted on, else the title's words (sorted, no numbers or stopwords). Same message on two
  pages → two bugs; a reworded report on the same element → one bug. Set by a `before_insert`
  hook; older rows backfilled.
- **Comparison** with the target's previous finished run, computed when the page is read (new,
  still present, fixed). A run in progress shows nothing as fixed.
- **Triage** per workspace, origin and fingerprint (current state in `finding_triage`, history in
  the audit log). False positives are suppressed in later runs by the worker (`bugs.suppressed`),
  left out of the report, the API, JUnit and webhooks, and counted per model
  (`modelPrecision`, per workspace). Whether counts also go into an anonymous global number is
  the owner's open question 4.
- **Alternatives:** an embedding similarity between titles (costs a model call per finding and is
  hard to explain); storing comparisons (they change when triage changes; computing them from two
  runs is cheap); a `bug_status` enum value for suppressed (it would mix with verification's
  dismissals and the benchmark funnel).

## D73. Roles in one table, checked per route, read from the database per request (run 4, J5)
- **Decision:** owner / admin / member / viewer (the owner's question-5 default, decided without
  owner, revisit). `lib/roles.ts` holds the whole table; `authorize(action)` answers 401/403 for
  every management route; starting and stopping runs keep the visitor path (demo only). The role
  and workspace come from the database on each request, so a role change or an accepted
  invitation applies at once (one extra indexed lookup per request).
- **Invitations:** links only (no email), token hashed, 7 days, one use (conditional UPDATE),
  never "owner" (CHECK constraint); ownership moves by transfer. A removed member keeps an account
  in a new workspace of their own. Every change goes to the audit log, shown on /settings/audit.
- **One default model:** a partial unique index via Prisma's `partialIndexes` preview feature, so
  Prisma knows the index and won't propose dropping it (the alternative, raw SQL, would drift).

## D74. Row-level security with a tenant role and a per-transaction workspace (run 4, J5)
- **Decision:** `app_tenant` (NOLOGIN, NOBYPASSRLS) with a policy per tenant table; children check
  through their parent; `app_current_workspace()` fails closed. The web's `tenantDb()` extension
  sets the workspace and the role per transaction (`LOCAL`, safe with pooling). The worker and
  migrations use the owner role, unaffected.
- **Alternatives:** a separate database or schema per tenant (strong isolation, heavy operations
  and migrations ×N); RLS on the connection's own login role (needs a login per tenant or one
  shared role with session variables that leak across pooled connections); FORCE RLS on the owner
  (the worker would need tenant context everywhere, including the queue claim across tenants).
- **Not yet:** every web query through `tenantDb` (the run page, lists and the API reads are; some
  writes and settings queries still use the plain client with their WHERE). Listed under Needs me.
- **Cost:** +0.004–0.03 ms per query from the policies, +~0.1–0.3 ms from the extra statements.

## D75. The login-only demo bug and a signed-in shop benchmark (run 4, J2) — decided without owner, revisit
- **Owner's question 2 (unanswered), option a:** "My orders" (`/orders`, `/orders/:id`) only for a
  signed-in user; planted bug 13: opening an order shows the next order's number, items and total.
  Reachable by clicking, a realistic data bug, and a test of expected vs. actual. In `bugs.json`,
  a unit test, and verify-bugs on both builds (plus a check that the pages need a sign-in).
- **Owner's question 3 (unanswered), option a:** the shop benchmark (buggy and clean builds) runs
  with a saved sign-in setup for the demo account the shop itself shows; logout is denied there, so
  planted bug 11 (session survives logout) can't be triggered. Run 4's results are reported with
  and without bug 11. The holdout app has no login and is unchanged.
- **Also:** the login page's `?next=` accepts only paths in the shop (no open redirect); the
  worker's sign-in check polls for up to 5 s, because a single-page app changes view after the click
  without a page load (the real demo shop failed the first check; a fixture now covers it).

## D76. Production packaging: two images, one compose profile, S3 storage, DB-derived metrics (run 4, J6)
- **Images:** `Dockerfile.web` (multi-stage: npm ci → `next build` standalone → a runtime stage with
  only the traced server files, running as `node`; a `migrate` target runs `prisma migrate deploy`)
  and `Dockerfile.worker` (Playwright's own image for this Playwright version, so Chromium and its
  system libraries match; uv from its official image; locked dependencies without dev tools;
  runs as `pwuser`).
- **Compose:** the production services are in `docker-compose.prod.yml` (project `ata-prod`), see
  D77. Its own Postgres and volume, an S3-compatible store, migrations before web and workers
  start, `WORKERS` replicas.
- **Storage:** `Storage` gets `delete_prefix`; `S3Storage` (boto3) next to `LocalStorage`, chosen
  by `STORAGE`. The web app checks access, then redirects to a 5-minute presigned link: the bucket
  stays private and the app never streams image bytes. Tested with moto (no real S3).
- **Retention:** `workspaces.retention_days` (default 30); hourly, screenshots and steps of older
  runs are deleted and the run marked `purged_at`; findings stay for release comparison.
- **Health and metrics:** `/api/health` (liveness), `/api/ready` (database), `/api/metrics`
  (Prometheus text computed from Postgres, so every instance agrees and restarts lose nothing;
  optional bearer token). JSON logs (`LOG_FORMAT=json`) with run and workspace ids from context
  variables in the worker; secret-looking keys redacted in the web logger.
- **CI:** actions pinned by commit SHA with the version in a comment; Dependabot keeps them current.
  The customer-facing example workflow is pinned the same way.
- **Alternatives:** one image for both (the worker's browser libraries would bloat the web image);
  Kubernetes manifests (more to explain, nothing to run them on here); per-process Prometheus
  counters (lost on restart, different on each instance).

## D77. The production stack: its own compose file, and SeaweedFS instead of MinIO (run 4, J6)
- **What happened:** the first version put the production services in a `prod` profile of
  `docker-compose.yml`. Compose checks required variables (`${X:?}`) in the whole file, so plain
  `npm run db:up` failed without production secrets, and `up --profile prod` with `--env-file`
  recreated the dev database on the default port (it briefly went down; the data volume was
  untouched). And MinIO's images (`minio/minio`, `minio/mc`, also on quay.io) are no longer
  publicly pullable.
- **Decision:** `docker-compose.yml` is back to the dev database only, byte for byte;
  `docker-compose.prod.yml` (project name `ata-prod`) holds the production stack. The object store
  is SeaweedFS 4.51 (Apache-2.0, S3 API) with credentials from `S3_ACCESS_KEY`/`S3_SECRET_KEY`; the
  worker creates the bucket on first use (tested with moto), so no one-off bucket job is needed.
  The owner's plan named MinIO; what it needs is "S3-compatible", and only `S3_*` variables change
  for S3, R2, Garage or a self-run MinIO.

## D78. No Sonnet run in run 4 (J7)
- **Decision:** the owner's rule was "only if I said yes today"; question 1 (asked at the start) got
  no answer, so the one allowed claude-cli benchmark was not run. A missing answer was not taken
  as a yes for anything that spends the owner's Pro limit. The command to run it is in PROGRESS,
  "Needs me".

## D79. CI's browser jobs run in Playwright's images (run 4, J8)
- **What happened:** from about 14:00 on 2026-11-11, GitHub's runners couldn't resolve Ubuntu's
  package archive, so `playwright install --with-deps` (apt) failed in the python and e2e jobs on
  both ubuntu-latest (now 26.04) and ubuntu-24.04, for hours.
- **Decision:** those jobs run in `mcr.microsoft.com/playwright/python:v1.64.0-noble` and
  `mcr.microsoft.com/playwright:v1.64.0-noble`, which already contain Chromium's system libraries;
  only the browser binary is installed (from Playwright's CDN, no apt). The database service is
  reached by its name inside a container job. Runners stay pinned to ubuntu-24.04. CI green
  (run 43062066917).

## D80. Replay judges a change, not a screenshot (run 5, K1)
- **Problem:** "Save changes does nothing" was found 7 times (bug 8) and rejected every time.
  The judge saw one screenshot of the end state, and a page where Save did nothing looks exactly
  like a page where nobody clicked Save.
- **Decision:** replay captures a compact page state just before the last action that acts on
  the page (click, double-click, type, select, reload, back, navigate) and again once the page
  has settled after it (`page_state.py`). The state holds the URL, the visible text lines, form
  values (passwords never read), totals, local/session storage and cookies (fingerprints only,
  never values) and, for the time in between, requests (no query strings), dialogs, new tabs,
  console errors and text that appeared and vanished (a toast, caught by a MutationObserver).
  The diff sets harmless changes aside: spinner text, a line whose only change is a time or
  date, and GET requests the page was already sending (polling).
- **What counts as a response:** URL, text, fields, storage, a request, a dialog, a new tab, or
  text that appeared briefly. A console error alone does not: users don't see it (it is still
  shown to the judge as evidence of why nothing happened).
- **When the measurement decides alone:** the report says the action had no effect (a pattern
  on title + actual), the action was on a control (button, link, checkbox, select, tab, menu
  item…), and the diff is empty → confirmed with no model call. A control that does nothing at
  all is a defect a QA tester would file. Everything else (wrong-change reports, no-effect
  reports on non-controls, any diff with a change) goes to the judge with the diff summary and
  one picture: before on the left, after on the right (Pillow; one image works with every
  provider, including claude-cli and Ollama).
- **Alternatives:** asking the judge in every case (the 12B judge rejected bug 8 four times
  even with a clear description; a measured "nothing changed" is stronger evidence than its
  reading of a picture); sending two images (needs a provider change in five clients for no
  gain); the accessibility tree instead of visible text (larger, and the text plus field
  values carried every case in the tests).
- **Reverify signs in only if the run did:** `login_at_the_time` uses the workspace's login setup
  only if it existed when the run was created, so old runs replay as they ran.

## D81. The reviewer tier: a stronger model only where judgement is needed (run 5, K2)
- **Problem:** the explorer reaches bug states and then explains them away (run 4: Gemma
  dismissed 19 of 23 flagged contradictions). Running a frontier model for every step costs ~40
  decisions per run; judging is needed in a handful of them.
- **Decision:** with `REVIEWER_PROVIDER` / `REVIEWER_MODEL` set, (1) a step flagged by the
  expected-vs-actual check goes to the reviewer at once (action, expectation, what happened,
  flags, page text fenced, screenshot); it files the bug itself or dismisses the flag, and the
  explorer is only told the outcome and keeps exploring (no "resolve first" gate); (2) after the
  loop, each report the explorer filed is reviewed once as text and is kept (and rewritten more
  precisely, the old title kept as `explorer_title`) or dropped with `reviewer: <reason>`. Replay
  still verifies everything that is kept.
- **Unclear answers:** on a flagged step, "not a bug" (exploration continues; the flag is
  stored); on a final report, "keep" (replay still checks it). Losing a report on a garbled
  answer is worse than replaying one more.
- **Costs:** the reviewer's calls count against the run's cost budget the moment they happen,
  are logged as `review` steps, and are summed into `runs.reviewer_*` (provider, model, tokens,
  cost), apart from the explorer's share of `runs.cost_usd`. A benchmark records the reviewer
  in `details.reviewer`, like the judge. A report the reviewer dropped counts as
  `reviewer_said_no` in the verification funnel.
- **Scope:** server-level settings (any provider, including claude-cli locally); a
  per-workspace reviewer choice can come with K4's plans.
- **Alternatives:** the reviewer on every step (cost of a frontier model per step, no gain on
  steps that need none); the reviewer only at the end (by then the flagged state is gone, and a
  flag is exactly where Gemma failed); a vote between explorer and reviewer (the explorer's
  judgement is the weak part).

## D82. List pages: open at least one item (run 5, K2)
- **Problem:** run 4's Gemma reached the order list and never opened an order (bug 13 unreached).
- **Decision:** charter technique 9 ("Lists and details": open an item, check the detail shows
  the item you opened) plus a per-list reminder in the observation (`agent/lists.py`). A list is
  two or more same-site links whose paths share a parent and end in an id (digits, a UUID, a slug
  with a digit, optionally `.html`); the reminder names the list page and one item link and stays
  until a URL under that parent is visited. Opening a product doesn't tick off the orders list.
- **Generic:** nothing names a site, a product or a bug; tests check the charter says nothing
  site-specific.

## D83. Roles and row-level security everywhere (run 5, K3)
- **Decision:** three login roles, none superuser or BYPASSRLS: `ata_owner` (owns the schema),
  `ata_web`, `ata_worker`; the apps are members of `app_tenant`, so they see no tenant rows
  without a workspace set (fail closed). The web app goes through `tenantDb(ctx)` /
  `inTenant(ctx, fn)` for everything; the worker ties a claimed run's session to its workspace
  (`enter_tenant`). What must cross workspaces is a narrow SECURITY DEFINER function owned by
  `ata_owner`, with EXECUTE for one role (DATABASE.md, "Justified bypasses"); sign-in reads
  users through a read-only policy. Operator commands (bench, reverify, backfill, make-admin,
  set-plan) use the admin connection.
- **Env:** `DATABASE_URL` stays the admin connection (migrations, tests, operator commands);
  `WEB_DATABASE_URL` / `WORKER_DATABASE_URL` are the apps' roles and fall back to it while unset,
  so nothing breaks before `npm run db:roles` has run. Production compose gives each container
  only its own URL.
- **Alternatives:** keep the worker on the owner role (run 4; one compromised worker could read
  every workspace); a separate database per tenant (heavy to operate at this size); app-level
  checks only (one forgotten WHERE leaks data).
- **Tested** as each role (`SET LOCAL ROLE` in the worker's database tests, a real `ata_web` login
  in the web tests, a real `ata_worker` login for the worker's jobs).

## D84. Rules in Postgres: triggers, functions, views, constraints (run 5, K3)
- **Decision:** the audit log is written by triggers (actor from `app.user_id`, context from
  `app.audit_metadata`; no secret values; append-only for the apps), `updated_at` by triggers,
  triage carry-forward by a trigger on `bugs`; the queue, quota and retention are functions
  (`claim_next_run`, `consume_quota`, `apply_retention`, …) the apps call; `target_bug_history`
  (security_invoker) and `model_leaderboard` (materialized, refreshed by a statement trigger on
  every write: results are rare and the table tiny) are views; fixed sets and ranges are CHECKs.
  The app's own audit writes and the worker's `apply_triage` were removed.
- **Why:** these rules must hold for every writer. A rule in one app holds only there.
- **Kept in code:** fingerprints (Python normalisation), replay, model calls, storage deletes,
  validation messages.

## D85. Plans and usage (run 5, K4) — decided without owner, revisit
- **Plans (placeholders until the owner sets prices):** Free 30 runs/month, 40 steps, local
  models only (Ollama), 3 seats, 7 days; Team 300, 80, any model, 10, 30 days; Business 2000, 150,
  any, 50, 90 days. New workspaces start on Free; `worker set-plan` moves one.
- **Enforced by Postgres:** `consume_quota(workspace, provider)` → runs (the lower of the plan's
  and the workspace's own quota), allowed providers, and the step cap (the web app writes it to
  `runs.max_steps`); seats in `accept_invitation`; retention in `apply_retention`.
- **Usage events:** one per finished run, written by a trigger, explorer and reviewer apart;
  append-only for the apps. The run's own model counts as allowed when it is the server's
  default (the operator's choice).
- **Admin view:** `users.is_platform_admin`, set only by `worker make-admin` (owner's question d2,
  my pick), checked by the database function `platform_usage`.
- **No payment provider:** ROADMAP.md, "Billing", says what Stripe would add.

## D86. What the first tiered benchmark changed (run 5, K2)
- **Browser form validation is a response:** replay records invalid fields (with the browser's
  message) and the focused field; a submit that moves the focus to an invalid field is "the
  browser refused to submit", a change users see. It was the holdout's one false alarm.
- **Lists from the crawl seed the reminder:** the deterministic crawl already visits the site;
  its pages that share a parent and end in an id (found on one list page) are lists the agent is
  reminded about from step 1. The crawl's own visits don't tick them off: only the agent's do.
- **The reviewer model:** this Mac has 16 GB. gemma4:12b (7.7 GB) runs the explorer; the largest
  model that fits next to it and the browser in reasonable time is a ~14B model at 4-bit:
  qwen3:14b (9.3 GB, free download; the two don't fit in memory together, so Ollama swaps them
  for each review; reviews are 1–3 per run). It is text-only, so `REVIEWER_VISION=false` wraps it
  (`TextOnlyClient`): image calls become text calls, with the page text and the measured diff.
  Larger vision models (27B+) don't fit in 16 GB with the browser.
- **The e2e fake model** gets a fresh script per run (two e2e tests now run interactive runs).
- **The dev demo account** is on Business (dev-only; e2e runs it many times a month).

## D87. The reviewer tier stays optional, not the default (run 5, K2)
- **Measured:** Gemma + Gemma reviewer: shop 0%, holdout 0%, holdout false alarms 1.0. Gemma +
  qwen3:14b reviewer: shop 19%, holdout 0%, false alarms 0.0 (MISS_ANALYSIS, "Run 5, K2").
- **Rule (the owner's, set in advance):** default only if holdout judgement-only recall rises and
  clean-build false alarms don't. Holdout didn't rise with either reviewer, so `REVIEWER_*` stays
  empty by default; the tier is there for anyone who sets it (a hosted reviewer is the obvious
  next measurement, which needs an API budget).

## D88. claude-cli made measurable (run 6, L1)
- **Pinned IDs:** `CLAUDE_CLI_MODEL` / `CLAUDE_CLI_CHEAP_MODEL` (defaults `claude-sonnet-5-5` /
  `claude-haiku-5-5`); a reviewer on claude-cli takes `REVIEWER_MODEL`. `bench` refuses an alias
  ("sonnet") before queuing anything. Alternative: keep aliases and log what the CLI reports.
  Rejected: an alias silently moves to a newer model, so two results with the same label could
  be different models. The model the CLI reports (`modelUsage[...].canonicalModel`) is stored
  per step (`steps.model`) and per result (`details.reported_models`).
- **Tokens and the estimate:** all four token types from `modelUsage` (one entry per model a
  call used, each priced at its own rate). The recorded Haiku call showed the CLI writes its
  cache with a **1-hour TTL**, which costs 2x the input price, not 1.25x; `pricing.py` prices
  those writes apart. With that, our estimate equals the CLI's own `total_cost_usd` for the
  recorded call; a gap of more than 1% logs a warning (pricing.py out of date). Charged cost
  stays $0; `estimated_cost_usd` is stored per step, run and reviewer share, and is what
  `MAX_RUN_COST_USD` and the review budget spend (a provider that charges: the charge).
- **Stopping:** a usage-limit answer (`is_error` with limit text or HTTP 429, or a non-zero exit
  whose output mentions the limit) **or a call paid from usage credits** (`usage.fallback_credit`
  set) latches for the whole process: no claude-cli client calls the CLI again, the run fails, the
  benchmark stops its queued runs and saves what finished marked `invalid` (off the leaderboard).
  The credits case is treated as a limit because the owner's rule is "never drain my credits".
  The limit fixture is synthetic: recording a real one would spend the limit.
- **Benchmark cost cap:** `BENCH_MAX_COST_USD` (API-equivalent, all runs of one benchmark).
  The owner set $15 for (b) and $5 for the others.
- **Per-run cap during the claude-cli benchmarks:** `MAX_RUN_COST_USD=5` (decided without the
  owner). f6151b32 ran with an effective cap of nothing (its cost was $0); the .env's $1 would
  now cut Sonnet runs short (estimated $0.70–1.50 a run) and break comparability. $5 still stops
  a runaway run; the benchmark cap stops a runaway benchmark.
- **Time limits:** 480 s for (a) and (b) (as f6151b32), 1200 s for (c) and (d) (as run 5's Gemma
  rows): the owner's answer.
- **Opus as the agent (e):** not run. The owner asked to be asked first, to check the weekly
  limit, and was away; it is under "Needs me".

## D89. No code changes between the run 6 benchmarks (run 6, L2)
- **Decision:** benchmarks a–d all run on commit 123e23e's agent code (later commits only add
  docs), even though (a) showed a fixable weakness (a `finish` claiming the tools are
  unavailable, without a refused native call).
- **Why:** the point of L2 is to compare models; a code change between them would mix a model
  effect with a code effect, and each benchmark costs the owner's limit. The fix is noted under
  "Needs me" / next steps.

## D90. Fix the reviewer-flag crash before (d) (run 6, L2)
- **What happened:** in benchmark (c), shop run 18bce55e failed with `KeyError: 'name'` in
  `AgentRun._review_flag`: the reviewer (Sonnet) called a flagged step a bug, and the step had
  no named element, so building the report's evidence crashed. The run lost that bug and every
  step after it (a run-5 bug, reached for the first time because a strong reviewer said "bug").
- **Decision:** fix it test-first (`test_a_reviewer_bug_on_a_step_without_a_named_element_...`)
  and commit before (d). An exception to D89: it doesn't change what any model sees or decides,
  only stops a crash that would cost (d) whole runs of the owner's Opus usage.
- **Consequence:** (c) is recorded as measured, with one of its three shop runs cut short (noted
  with its result); (d) runs with the fix. Not re-running (c): no retries of a benchmark.

## D91. Which model where (run 6, L3)
Measured in run 6 (judge pinned to gemma4:12b; shop 3 runs + clean, holdout 2 runs + clean).
"Est." is the API-equivalent cost from the CLI's token counts at list price (D88), not a charge.
Per verified judgement bug = the buggy runs' estimate divided by the judgement bugs they verified
(the deterministic bugs are found for free and left out here).

| Setup | AI-only shop / holdout | False alarms (clean) | Time / run | Est. / run | Est. / verified judgement bug, shop / holdout |
|---|---|---|---|---|---|
| a) Haiku 5.5 agent | 26% (7 of 27) / 62% (5 of 8) | 0.0 / 0.0 | ~4 min | $0.06–0.09 | **$0.04 / $0.03** |
| b) Sonnet 5.5 agent | **33% (9 of 27) / 75% (6 of 8)** | 2.0 / 1.0 (real behaviour) | ~3 min | $1.44–1.68 | $0.53 / $0.56 |
| c) Gemma 12B + Sonnet reviewer | 11% (3 of 27) / 0% (0 of 8) | 0.0 / 0.0 | ~19 min | $0.01–0.05 | $0.01 / none found |
| d) Gemma 12B + Opus reviewer | 7% (2 of 27) / 0% (0 of 8) | 0.0 / 0.0 | ~19 min | $0.07–0.21 | $0.11 / none found |
| Gemma 12B alone (run 5) | 7% / 0% | 0.0 / 0.0 | ~22 min | $0 (local) | — |

- **Recommended default: Haiku 5.5 as the agent, no reviewer.** It finds most of what Sonnet
  finds (on the holdout, 5 of 8 bug-runs against Sonnet's 6 of 8, and the one technique-driven
  bug Sonnet missed), with no false alarms, in about four minutes, at roughly a fifteenth of
  Sonnet's cost per verified judgement bug. That is the product's cost story: a run costs cents,
  not dollars.
- **"Thorough" option: Sonnet 5.5 as the agent.** About +7 points on the shop and +13 on the
  holdout (1–2 more bug-runs per app in these samples) for 16–28× the cost per run. Its extra
  reports on clean builds were real behaviour, so they cost triage time rather than trust.
- **Not recommended: a cheap local explorer with a strong Claude reviewer.** The explorer limits
  it: the reviewer only sees what the explorer flags, so neither Sonnet nor Opus raised Gemma's
  holdout score above 0%, and Opus did no better than Sonnet. Cheap per run, but a run finds
  little and takes 5× longer. Keep local Gemma as the free or offline option, with the qwen3:14b
  reviewer if anything (run 5: 19% shop).
- **Not changed in code (decided without the owner):** `AGENT_MODEL` (API) and `CLAUDE_CLI_MODEL`
  stay `claude-sonnet-5-5`. The API path (`ClaudeClient`) has never made a real call; switching a
  default customers get on the strength of 5 claude-cli runs per model is the owner's product call.
  Under "Needs me".
- **Caveats, stated plainly:** samples are small (3 shop and 2 holdout runs per setup; one bug-run
  is 4–13 points); Haiku's 62% holdout rests on two runs; costs are estimates from claude-cli token
  counts, and the API client builds its own prompts and cache, so real API cost will differ; one
  Haiku run was cut short by the "tools not available" failure (D89), so Haiku's shop number is if
  anything an underestimate.

## D92. Haiku 5.5 is the default agent; the early finish is corrected (run 7, M1)
- **The owner's decision (run 7 Settings):** `AGENT_MODEL` and `CLAUDE_CLI_MODEL` default to
  `claude-haiku-5-5`; Sonnet is labelled "thorough" in `.env.example`, the README and the web
  model form (which now suggests both and fills in Haiku when Claude is picked). `PRODUCT_BRIEF.md`
  still says Sonnet: it is the original brief, kept as written; this entry supersedes it.
- **The early finish (FIX_EARLY_FINISH = yes):** run 6's Haiku run e3eb2b69 answered with a valid
  `finish` whose summary said the tools were unavailable (it had tried them natively inside
  `claude -p`, got "No such tool available", and the CLI reported no refused call, so D66 never
  fired). Now a `finish` whose summary matches that claim gets D66's corrective message once, and
  the next answer is taken whatever it is (never a loop). In the claude-cli adapter, not the loop:
  the confusion comes from the CLI's own tool layer, and other providers have real tool calling.
  Alternative: refuse any early `finish` in the loop. Rejected: it would also override real
  decisions to stop, and a provider-specific fault belongs in its adapter.

## D93. Benchmark v2: the four demo behaviours fixed (run 7, M1)
- **The owner's decision (DEMO_BEHAVIORS = fix), in both builds, with a test each** (unit tests in
  the demo apps and browser checks in `verify-bugs`):
  - **Shop, profile "Recent orders":** the profile API served a hard-coded list (#10231, #10457)
    unrelated to "My orders" (#1001–1003). Both now come from `src/orderData.ts`. The buggy build
    still can't show them, because its profile API fails on purpose (planted bug 2); bug 13 (an
    order page showing the next order) is untouched.
  - **Shop, a double-clicked "Add to cart":** the second click of a double click (within 500 ms)
    is ignored; a later click adds again. Planted bug 7 (the discount applied twice on a double
    click, in the cart) is untouched.
  - **Holdout, past dates:** a check-in before today is refused ("Check-in can't be in the past.").
  - **Holdout, dates outside the room's availability:** refused when the window is known. Decided
    without the owner, revisit: when the availability API fails (it does on purpose in the buggy
    build, planted bug 1) the booking isn't blocked. Blocking it would hide planted bugs 3–5,
    which are only reachable through a booking.
- **Labelling:** `BENCHMARK_VERSION = "v2"` in `benchmark.py`, printed in bench output, stored per
  result (`benchmark_results.benchmark_version`, `v1` for every older row), part of the
  leaderboard's key, shown on the benchmark page. A benchmark of v1 can no longer be made: the
  apps are what they are; old v1 rows stay as they were.

## D94. Specs: a team's requirements, embedded locally and retrieved per page (run 7, M3)
- **Storage:** `targets` (an app by origin, per workspace), `specs` (Markdown or text per
  target), `spec_chunks` (a spec split at its headings, each piece with a `vector(768)`), all
  under row-level security. pgvector in our own Postgres (`pgvector/pgvector:0.8.1-pg17` in dev,
  CI and the production compose file); an HNSW index with cosine distance. Alternatives: a
  separate vector database (one more service to run, back up and secure, for a few hundred rows
  per customer); IVFFlat (needs rebuilding as specs grow).
- **Embedding model: `nomic-embed-text` through Ollama** (decided without the owner). 274 MB,
  768 dimensions, an 8k-token context, ~28 ms per call warm on this 16 GB Mac (0.9 s cold); it
  wants task prefixes (`search_document:` / `search_query:`), which `OllamaEmbedder` adds.
  Considered: `mxbai-embed-large` (1024 dims, 2.5× the size, no need at this scale),
  `embeddinggemma` / `qwen3-embedding` (larger downloads, no measured gain for short English
  requirements). The model's name is stored per spec; a different model re-embeds everything.
- **Chunking:** at Markdown headings, each chunk keeps its heading path ("Booking > Dates"); a
  long section splits between lines at 800 characters. Requirements are short and their headings
  carry meaning, so no overlap and no token-based splitter.
- **When embedding happens:** in the worker, at the start of a run on the target, for specs that
  are new, edited (the web clears `chunked_at`) or embedded with another model. One place that
  embeds, one model, and no Ollama connection from the web app. If Ollama is down, the run goes
  on without specs and logs a warning.
- **Retrieval:** per page, the query is its path, title and the start of its text (400
  characters). The 8 nearest chunks are fetched; at most 3 within cosine distance 0.55 and 1,500
  characters (~400 tokens) are shown. One embedding call per distinct page, cached for the run.
- **In the prompt:** a REQUIREMENTS section in the observation, fenced as `<spec_content>`, and
  a task line saying to cite a broken requirement with its label ([S2]), only when the target has
  specs. The system prompt and the tools don't change, so a run without specs is the M2 run.
  A cited requirement is stored in `evidence.spec` and given to the replay judge.
- **Kept on by default (`USE_SPECS=true`)** only if the holdout measurement says so (D96).

## D95. Critical flows: journeys learned once, replayed without a model (run 7, M4)
- **Storage:** `flows` (name, the journey in plain language, the saved script as JSON, the last
  status) and `flow_results` (one per journey per run), under row-level security; at most 10
  flows per target (a trigger; the roadmap's 3–10).
- **A journey is an episode, not a new tool.** The agent gets the journey as its focus, at most
  15 steps, and finishes with "PASSED: <quoted text that shows it worked>" or "FAILED: ...". No
  new tool and no system prompt change, so exploration is unchanged. Alternative: begin_flow /
  end_flow tools. Rejected: a tool every run carries, for something only some targets have.
- **The script** is the episode's effective actions (clicks, typing, selects, navigation; not
  notes, blocked or failed steps) with the elements they acted on, plus the quoted texts as
  checks. Replay uses the same code as bug verification (`verify.replay`: role and name, nearby
  text, CSS path, position), then each check must be on the page.
- **Order in a run:** after the deterministic scan, before exploration; journeys spend from the
  run's step, time and cost budgets. A replayed journey costs no model call. A broken replay goes
  to the agent: repaired → the script is replaced; not → a "Critical flow failed" finding,
  verified by replay like any other.
- **Editing the wording drops the script** (the old steps may not match the new journey).

## D96. The first v2 double-click guard broke replays; fixed by click detail (run 7, M2)
- **What M2 showed:** bug 5 (cart total ignores quantity) was reported in all 3 shop runs and
  dismissed by replay all 3 times: replay saw quantity 1, not 2. The agent had clicked "Add to
  cart" twice, seconds apart; replay repeats steps back to back, under 500 ms apart, and M1's
  guard (ignore a click within 500 ms of the last) swallowed the second. My bug, not the agent's.
- **Fix:** ignore only the later clicks of a multi-click (`event.detail >= 2`): a double click
  adds once, two separate clicks add twice however fast they come. Unit test and a `verify-bugs`
  check that two separate clicks add twice, in both builds.
- **Labelling (decided without the owner, revisit):** still "benchmark v2": the intended
  behaviour is the same (a double click adds once); the M2 result `e92d2c6b` stays as measured,
  with this caveat in PROGRESS and MISS_ANALYSIS: its shop number undercounts bug 5 (3 correct
  reports lost to the guard). Holdout numbers are unaffected. Alternative: call the fixed apps
  v3. Rejected: one bad guard in my code, not a change of what the benchmark asks.

## D97. Flows after measuring; specs off by default until measured (run 7, M4 and M3)
- **Flows (measured, kept):** the second two-run measurement checked all three shop journeys in
  run 2 with no model call and re-found the profile failure for free (MISS_ANALYSIS "Run 7, M4").
  Flows are on whenever a target has them; the benchmark uses them only with `bench --flows`.
- **Specs (not measured yet, decided without the owner, revisit):** the owner's rule keeps specs
  on by default only if the holdout measurement shows judgement-only recall rising without more
  clean-build false alarms. `apps/demo2/specs.md` isn't written yet, so that measurement couldn't
  run: `USE_SPECS` now defaults to **false**, and `bench --specs` turns it on for its own runs. A
  team can still add specs; a worker with `USE_SPECS=true` uses them. Alternative: on by
  default, since specs only matter where a team adds them. Rejected: the owner's rule says
  "only if it helps", and that isn't shown yet.

## D98. Two flow fixes found by the benchmark (run 7, after M6)
- **A journey on a signed-in run is told its credentials are hidden.** The benchmark's shop
  runs sign in with a saved login, and the worker shows the saved email and password to the model
  only as "[test account]" and "[secret]" (run 4's rule: secrets never reach a model). The
  "Sign in" journey's agent read those placeholders on the login page, couldn't sign in, and filed
  a false "Critical flow failed". Now the journey's task says the run is already signed in, its
  credentials can't be typed, and a sign-in journey passes if the run is signed in. Alternative:
  skip sign-in journeys on targets with a saved login. Rejected: guessing which journey is
  "about signing in" from its wording is fragile; the agent can see that it is signed in.
- **A check must agree with the page the journey ended on.** PASSED quotes from earlier pages
  ("Go to checkout") became checks the final page can't show, so every replay "broke" and the
  journey was re-learned each run. Now a PASSED check is kept only if it is on the final page,
  and a FAILED check (what was expected) only if it is missing from it.
- **Measured?** Not separately: the Sonnet benchmark in M6 ran on the code before these fixes, so
  Haiku and Sonnet compare on the same code. The fixes have tests; their effect on a benchmark is
  the next measurement ("Needs me").

## D99. Key safety before the first API call (run 8, N0)
- **What was checked (counts only, nothing printed):** `.env` and `.env.prod` are git-ignored
  (`.gitignore` lines 16 and 46). Three tracked files contain the prefix `sk-ant-`: the redaction
  code and two tests. One has a key-shaped string (29 characters, a fake fixture in
  `test_safety.py`); the real key (106 characters) is in no tracked file and in no commit of any
  branch (`git log --all -p` compared in a script that printed only true/false).
- **The leak that existed:** `run_cli` started `claude -p` with the worker's whole environment.
  pydantic-settings reads `.env` without exporting it, so in practice the key wasn't there, but
  anything that exports `.env` (a dotenv loader, a shell `set -a`, a future process manager)
  would have made every claude-cli run bill the API key instead of the Pro plan, silently.
  Now `run_cli` passes `cli_environment()`: this process's environment without
  `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` (tests: a pure one, and a real `/usr/bin/env`
  subprocess started by `run_cli` with both set in the parent).
- **A guard test** fails if any tracked file holds `sk-ant-` followed by 40 or more key
  characters (real keys are ~100; the fixtures are short). It reports file names, never matches.
- **Proof on the real CLI** (`scripts/cli_billing_check.py`): with the key deliberately put into
  the parent process's environment, one Haiku call through `ClaudeCliClient` (stream-json, same
  stripped environment) reported `apiKeySource: "none"` (the owner's login), model
  `claude-haiku-5-5`, charged $0, API-equivalent $0.0012.
- **Alternative considered:** pass an allow-list environment (HOME, PATH, ...) to the CLI.
  Rejected: the CLI needs variables we don't control (its config dir, proxies, locale); a
  deny-list of the two credentials is exact for the risk and keeps the CLI working.
- **Not done:** a control call *with* the key, to see the CLI report `ANTHROPIC_API_KEY`: it
  would spend API credit to prove what the CLI documents.

## D100. The API path, first real calls (run 8, N1)
- **What was checked:** one short Haiku run (12 steps) with `LLM_PROVIDER=claude`, then one
  benchmark v2 (result `6dc913ac`, commit b5aaf9b). Tool use with `strict` schemas, prompt caching
  (tools + system prompt cached; reads on every step after the first model call, ~70% of input
  tokens per run) and the recorded cost (equal to the token counts at `pricing.py`'s list prices,
  which match Anthropic's table for Haiku 5.5: $0.10 / $0.50, cache read $0.01, 5-minute write
  $0.125) all worked as written in run 1. No code change was needed.
- **Left as it is (decided without the owner):** `ClaudeClient.decide` sends the server-side
  refusal fallback (`fallbacks: "default"`). Haiku 5.5 has no fallback model, so for Haiku it does
  nothing (a declined request stays declined; the docs say "default" isn't rejected, and no call
  was). It still helps a Sonnet or Opus agent. Alternative: send it only for models with a
  fallback. Not worth a model list in the client for a no-op.
- **Thinking:** Haiku 5.5 thinks adaptively by default (effort `medium`, sent explicitly);
  thinking is billed as output tokens and is included in the recorded cost.
- **Cost, real vs. estimated:** $0.013–0.019 charged per API run, against run 7's claude-cli
  estimate of ~$0.10 per run for the same model and benchmark. The CLI's estimate is the cost of
  Claude Code's own calls (its large system prompt, written to a 1-hour cache at 2× input price,
  ~9k cached tokens per call); our API client sends only our prompt and caches it for 5 minutes.
  So the claude-cli estimates overstated what a customer would pay by about 6×.

## D101. Measuring the flow fixes and the recheck with 4 shop runs (run 8, N2)
- **Decision:** `bench --holdout-first --flows --runs 4` (shop 4 + clean, holdout 2 + clean)
  instead of run 7's 3 shop runs. A failing journey goes back to the agent on its 3rd run after
  the one that saved it, i.e. the 4th shop run of a fresh benchmark: with 3 runs the recheck
  would never have run inside the measurement. Cost: one more claude-cli run (8 instead of 7).
- **Comparability:** recall is a mean per run, so 4 runs compare with run 7's 3 as well as any
  two small samples do (see the intervals in N3). The holdout part is unchanged.
- **The recheck rule (decided without the owner, the owner's goal named the behaviour):** every
  3rd run, or when the replay's result text changes. Alternatives: a time interval (runs aren't
  regular), or a random share of runs (not reproducible in a test). Counting replays keeps the
  model cost of a stuck failure to one episode per three runs.

## D102. Real-world benchmark: what was decided without the owner (run 8, N4)
- **Apps:** IT-Tools and react-admin's e-commerce demo (`docs/REAL_WORLD.md` says why, and what
  else was considered). Both run fully on this Mac from a clone at a commit.
- **Start page:** each run starts on the page of the feature with the bug, with no focus text
  and no description. Alternative: the app's home page. Rejected for IT-Tools (80 tools: 40 steps
  would mostly measure whether the right tool happens to be opened). Revisit: a home-page variant
  would measure exploration as well as recognition.
- **Third-party requests:** the apps' own requests for web fonts and a login background (Google
  Fonts, Unsplash) are allowed, as for any customer site; the agent's navigation can't leave
  the local app (the navigation guard). Alternative: block every non-local request for these
  runs. Not done: one more mode in the network guard for an asset request that changes nothing
  the agent tests.
- **Dropped bugs:** IT-3 and RA-3 don't reproduce as reported (reasons in REAL_WORLD.md). IT-3
  was replaced by the reserve IT-5; RA-3 was not replaced (time), so react-admin has 2 bugs.
- **Local apps:** `LOCAL_APP_URLS` adds the apps' URLs to "our own local apps" only when
  `DEV_MODE=true` (tested), the same rule as the demo shops.
- **Toolchain:** react-admin's demo at these commits needs Node 20 (forced to arm64); the system
  Node 20 is used rather than changing the user's Node setup.

## D103. Real-world results: the usage limit, scoring and what to fix (run 8, N4)
- **Usage limit:** a claude-cli usage-limit message arrived during IT-5's second run. As the run
  rules say, every model run stopped at once and nothing was retried; IT-5 runs 2–3, RA-1 and RA-2
  are left for the owner. The rest of run 8 (docs, hand checks, tests, PR) needed no model.
- **Reached is hand-checked:** the automatic rule said 7 runs reached the trigger; reading every
  step gave 4. The docs report the hand-checked number and keep the rule's in a side column.
  Alternative: tighten the rule now. Not done: one rule per bug tuned after seeing the runs would
  be fitted to these 10 runs.
- **Strict scoring kept:** IT-1's "ABC → NaN, no error" shares the reported bug's root cause and
  fix but not its symptom; the judge said no and the score stays 0. Changing what counts is the
  owner's call (in "Needs me").
- **No agent change tonight:** the two blind spots (a fill timeout on a read-only input treated as a
  tool error; the agent's own "should be rejected" not reported) have clear fixes, but measuring
  them needs model runs, and the usage limit had stopped those. Written up for the owner.
- **Resumed (later on 2026-11-17):** the owner said to resume the model runs; IT-5 ×2, RA-1 ×3
  and RA-2 ×3 ran on the same commit and settings with no limit message. Final: 0 of 18 found.

## D104. Real-world model comparison: Sonnet and Opus through the API (2026-11-18)
- **Transport:** Sonnet 5.5 and Opus 5.5 ran through the real Claude API (`LLM_PROVIDER=claude`),
  as the owner asked (credits, not the Pro limit); Haiku's rows are from claude-cli. Same prompt,
  tools, settings and judge; the API agent call uses effort `medium`. Alternative: rerun Haiku
  through the API too for a same-transport baseline. Not done: the owner's budget was for the
  stronger models, and Haiku's misses are already explained step by step.
- **Helper model stays Haiku** (`CHEAP_MODEL=claude-haiku-5-5`), as in the Haiku runs, so only
  the agent model changes.
- **Budget rule:** before each run, the charged cost of every API run of the session (from the
  runs table) sets the cap to min($0.80, $3.50 − spent − $0.05); a run starts only if that cap
  is at least 2× (Sonnet) or 1.5× (Opus) the model's average run so far. The per-run cap makes the
  total impossible to pass. Opus cost $0.78, twice the estimate, so it got one run.
- **Strict scoring over the judge:** the judge matched `ABC` → NaN to IT-1 for Sonnet (406ca352)
  and Opus (fe2581ce) but said no to the same report from all three Haiku runs (D103). Scored as
  not found for every model, so the columns compare; listed under "found, not in our list".
  Alternative: accept the judge. Not done: one judge rule must apply to all models, and which
  rule is the owner's matcher question.
- **IT-Tools start command:** `arch -arm64` added to IT-Tools' install and start commands in
  `bugs.json`. Started from the worker's Python, Node ran as x64 and found the arm64 esbuild
  binary wrong. react-admin already had the same prefix. Harness only, no agent change.

## D105. Layout check and axe best-practice rules (2026-11-22)
- **Decision:** every crawled page gets a layout check at the run's own screen size, before the
  phone-width screenshot: (1) the page is wider than the screen, naming up to 5 elements that
  stick out, outermost first; (2) tap targets under 44×44 CSS px, on screens under 768 px wide;
  (3) visible text under 12 px outside `code`/`pre`/`kbd`/`samp`. One finding per problem per
  page (the elements differ page by page). Overflow is `medium` (WCAG 1.4.10 Reflow is AA);
  targets and text are `low`. axe now also runs its `best-practice` rules (landmarks, skip
  links, one main heading), still one finding per rule. This reverses part of D14.
- **Where the thresholds come from:** 44 px: WCAG 2.2 SC 2.5.5 Target Size (Enhanced) and
  Apple's Human Interface Guidelines (44 pt). 768 px: the common tablet breakpoint (Bootstrap
  and Tailwind `md`), so phones and small tablets are covered. 12 px: Lighthouse's "legible font
  sizes" audit. None of them comes from a measured site.
- **Choices inside the checks:**
  - "Wider than the screen" means content past the right edge that a user can scroll to:
    `overflow-x: hidden` on the page clips instead, so it doesn't count. Elements inside their
    own scroll box or fixed to the screen don't widen the page and aren't named.
  - Tap targets keep WCAG's exceptions: a link inside a sentence (sized by the text around it)
    and disabled controls. A visually hidden checkbox counts as big as its label (the label is
    what a user taps). Elements outside the screen (a closed off-canvas menu) aren't checked.
  - Small text skips visually hidden text (screen-reader-only, 1 px boxes).
- **Alternatives:** the literal `scrollWidth > viewport` test (would flag pages that clip and
  can't scroll); 48 px (Google's Material guidance) or 24 px (WCAG 2.5.8 AA, which axe's
  `target-size` rule already checks); grouping across pages like D14 (the elements that fail
  differ per page, so a per-page finding is what a developer fixes).
- **Why reverse D14 on best-practice:** the owner asked for landmark and skip-link rules. The
  cost is the one D14 named: findings on the clean benchmark builds that are advice rather than
  failures. The benchmark's clean-build false alarms measure it, by category.

## D106. Meta/SEO check (2026-11-22)
- **Decision:** every crawled page that loaded is checked once for og:title, og:description,
  og:url, og:image, twitter:card, a canonical link, a favicon (an icon link, or else the
  browser's default `/favicon.ico`) and an apple-touch-icon. An og:image on a known placeholder
  service (placehold.co, via.placeholder.com, dummyimage.com, picsum.photos and similar) or
  one that doesn't load as an image is a problem. All `low`, category `seo`.
- **Grouping (the owner's choice):** pages with exactly the same problems share one finding
  listing the pages (a site-wide template); pages whose problems differ get their own.
- **Where the list comes from:** the Open Graph protocol (ogp.me: og:title, og:image and og:url
  are required properties, og:description recommended), X/Twitter's card markup, and the icons
  browsers and iOS show. og:type isn't checked: a missing one defaults to `website`.
- **Loading the og:image:** through the run's own browser context (`context.request`), so the
  safety proxy vets it like any page request (a test checks a private address is refused);
  once per scan, cached by URL. 5 s timeout. Not on error pages.
- **Alternatives:** one finding per page always (the owner's first wording; on a site whose
  template misses the tags, that's one identical finding per page); a HEAD request (many image
  hosts answer HEAD wrongly).

## D107. Console warnings (2026-11-22)
- **Decision:** `console.warn` messages are captured on every crawled page and during the agent's
  session, each distinct text once per page (at most 50), stored as `console_warnings` on the
  page result, and reported as one `low` finding per page listing them (category
  `console-warning`). Errors and uncaught exceptions keep their own findings and severities.
  The agent's model isn't shown warnings: they are evidence, not something to act on.
- **Not the site's:** warnings from browser extensions (an extension URL in the location or the
  text) are dropped. Our injected scripts run with the page's console muted
  (`evaluate_quietly`), since axe-core is third-party code that could log; our own scripts don't
  log. The wrapper is built as a string, not with `eval` in the page, which a site's Content
  Security Policy may forbid.
- **Alternatives:** one finding per warning text across pages, like errors (a page's warnings
  are usually one cause, a library or framework notice, so per page is less noise); telling
  harness messages apart by their source location (Chromium reports an empty URL for both
  inline page scripts and injected ones, so it can't).
- **Tradeoff:** a page message logged in the instant our script runs is muted too. Our scripts
  run for well under a second, once per page.

## D108. Keyboard probe on what the agent opens (2026-11-22)
- **Decision:** during the agent's exploration, each click is bracketed by a snapshot of the
  elements on screen and a comparison afterwards. What appeared is a **dialog** (role=dialog,
  alertdialog or an open `<dialog>`, or a fixed layer covering more than half the screen), a
  **menu** (a button showed two or more new links or buttons) or a **disclosure** (a button
  showed content that was already in the page, hidden, with the same text). After the agent
  finishes, up to 8 of those controls are opened again in a fresh browser context by
  replaying the agent's steps (the same replay plans as bug verification), then probed with
  real key presses. One finding per failing control, `confirmed` (deterministic), category
  `accessibility`, at the severity of its worst failure.
- **Checks and severities (the owner's call):** dialog: focus moves into it, Tab keeps focus
  inside it, Escape closes it (`medium`); exposed as role=dialog, aria-modal (`low`). Menu:
  Escape closes it (`medium`); the button has aria-expanded and an accessible name (`low`).
  Disclosure: aria-expanded (`low`). From the WAI-ARIA Authoring Practices (Dialog (Modal),
  Disclosure, Menu Button patterns) and WCAG 2.4.3 / 4.1.2.
- **Choices:**
  - The crawl stays look-only (rule 6.2), so only controls the agent opened are probed.
  - Probing happens in a fresh context, not in the agent's tab: Escape and Tab there would
    change what the agent is looking at.
  - A missing accessible name is `low` here: axe's `button-name` rule already reports it at
    `medium` on crawled pages, so this finding doesn't double the weight.
  - "Covers most of the screen" is more than half the viewport's area. New text in an element
    that was empty ("Saved.") is a response, not a disclosure; `<summary>` is skipped (the
    browser reports its state itself); submit buttons don't open menus or disclosures.
- **Alternatives:** clicking every toggle-looking button during the crawl (breaks look-only,
  and needs a guess at which buttons are toggles); probing in the agent's own tab (cheaper,
  but disturbs its exploration); judging with the model (the checks are mechanical).
- **Tradeoffs:** a content panel mounted fresh by a framework on click (not hidden before)
  isn't recognised as a disclosure, so those are missed rather than guessed at. Each probe
  replays the agent's steps, which adds seconds per control after the run (no model cost).

## D109. Success without a request (2026-11-22)
- **Decision:** the agent's page keeps a log of every request (method, resource type, path,
  status) and WebSocket message. When the agent clicks a form's submit button (or any button
  inside a `<form>`), the loop notes where the log stands and watches for briefly shown text.
  If a success message appears afterwards and no request in that interval sent anything, an
  expected-vs-actual candidate opens (J1): the explorer must report or dismiss it, or the
  reviewer decides when there is one. The interval's network log goes into the step's `check`
  and, if it becomes a bug, into the bug's evidence (`success_without_request`).
- **What counts:** "sent anything" is any non-GET request, or a GET of type fetch, xhr,
  document (a page load), ping (sendBeacon), eventsource or websocket. A success message is
  new text matching common completion copy (success, thanks / thank you, saved, sent,
  submitted, received, subscribed, confirmed, registered, signed up, "we'll be in touch")
  without a failure word (not, failed, error, unable, could not, invalid, try again).
- **Why a candidate and not a bug:** a client-only app (a calculator, a local draft, a
  settings page in localStorage) can rightly say "Saved" with no request. The model sees the
  page and decides; replay verification then checks any report like every other.
- **Alternatives:** a deterministic finding (would flag every client-only app); asking the
  model on every submit (a model call per form, for the rare case).
- **Tradeoffs:** success copy outside the word list (another language, an icon only) isn't
  noticed; a request sent by a service worker or another tab isn't seen. A form that posts
  to a third-party script before showing "Thanks" counts as sending, which is right: the
  data went somewhere.

## D110. Seeing CSS-only changes, and a pixel check for "nothing happens" (2026-11-22)
- **The false-alarm pattern:** content revealed with CSS (height, max-height, opacity,
  visibility, display, transform) without a change to the page's text or accessibility tree
  was reported as "clicking did nothing", and replay "confirmed" it, because both read the
  same DOM text (`innerText` keeps text hidden by a zero height, opacity or a transform).
- **(a) Perception:** the page state now includes the text a user can actually see (drawn,
  not clipped to nothing by an ancestor with overflow hidden, not transparent, not pushed off
  the side of the screen) and the elements whose shown state flipped since the previous
  capture. The replay diff lists "Text that became visible / was hidden" and "Elements shown
  or hidden", and these count as a response. The agent's click result says "now visible: …"
  instead of "nothing on the page changed". Spinners and clocks shown or hidden are set aside
  as before. Before comparing, finite CSS animations and transitions are waited for (2 s cap).
- **Vertical scrolling never counts:** "visible" ignores whether something is above or below
  the fold, otherwise a click that scrolls the page would look like a response. Being pushed
  off the left or right side (an off-canvas menu) does count.
- **(b) Independent check:** for a "nothing happens" report on a click, replay also compares
  screenshots of the region around the element, before and after (`worker/pixels.py`). If it
  changed noticeably, the report is dismissed with the measurement as the reason, without a
  model call. What is compared and why:
  - the full width, from a quarter of the screen height above the element to half below it;
  - minus the element and 8 px around it (its focus ring, hover and pressed styles), the
    element that had the focus before (its ring and caret go when the click moves the
    focus), and the text the diff set aside as harmless (a spinner, a ticking clock);
  - minus pixels that changed by themselves between two "before" screenshots 500 ms apart;
  - the pointer is moved off the content before every screenshot, and animations finish
    first; the target is scrolled into view before the "before" pictures (the click would
    scroll it anyway).
  - A pixel changed when its brightness differs by more than 10% (pixelmatch's default
    threshold) after a 1-pixel blur of both pictures. First written as "any colour channel";
    CI on Linux showed why not: Chromium there redraws unchanged text with different
    sub-pixel (coloured) anti-aliasing when the focus moves, ~1,000 changed pixels on a page
    where nothing happened (0 with blurred brightness). pixelmatch and Playwright ignore
    anti-aliasing by default for the same reason. The region changed noticeably at 100 changed
    CSS pixels (about two
    characters of body text). Chromium draws a page the same way twice (a dead button
    measured 0 changed pixels outside its mask) and Playwright's screenshot assertions count
    any differing pixel by default; the floor absorbs stray anti-aliased edges. A share of
    the screen was tried first and rejected: one revealed sentence is 0.8% of a desktop
    region and 2.6% of a phone's.
- **Alternatives:** the accessibility tree (doesn't see CSS-only changes either); a share
  threshold (depends on screen size); asking the judge with the pictures (it was shown them
  before and still confirmed these reports).
- **Tradeoffs:** a visible change that isn't the app's response (an ad rotating slower than
  500 ms near the button) can dismiss a real "does nothing" report; the regression benchmark
  checks the planted ones stay confirmed. A report whose evidence is a request that wasn't
  sent, while the screen does change, is now dismissed: from the user's side something
  happened, and the report should say what was wrong instead.

## D111. Quality first (2026-11-24, the owner's principle)
- **Decision:** the product is designed to find as many real, verified bugs as possible.
  Customers pay model costs with their own API keys, so the product doesn't trade quality for
  lower token cost. Cost optimisation comes later, and only where quality stays the same as
  measured on the benchmarks.
- **Development cost is separate:** tests run on the fake model at $0; the owner's evaluation
  runs use the owner's Claude login; API credits are never spent without asking.
- **What it reopens:** choices made earlier to keep runs cheap: text-only perception (the
  current loop mostly reads the page as text), small step budgets (40 steps, 480 s) and Haiku as
  the default agent (D91, D104). Each is to be revisited under this principle; deep mode (run 9)
  is the first step.
- **Alternatives:** keep optimising cost per run first (the approach of runs 6–8). Measured:
  Sonnet and Opus did no better than Haiku in the current loop (D104), which points at the
  harness, not at the model's price, as the limit.
- **Tradeoffs:** a deep run costs much more than a current-loop run. That is acceptable for the
  product (the customer's own key and choice), and kept off the owner's API budget for
  development.

## D112. Deep mode's data: an engine column, not a third mode (2026-11-24)
- **Decision:** a deep run is an interactive run with `engine = 'deep'` (a new `run_engine`
  enum, `loop` by default). The API's `mode: "deep"` is stored that way. New: `runs.engine_model`
  (a pinned ID, deep runs only), `runs.coverage` (JSONB), `run_status` `paused` with
  `runs.paused_reason`, `bug_status` `unverified`, and `workspaces.deep_max_steps` /
  `deep_max_seconds`.
- **Alternatives:** a third `run_mode` value `deep`. Every safety rule (look-only passive mode,
  interactive only on verified domains) reads `mode`; a third value would have to be added to
  each check, and one forgotten check would make deep runs less safe than interactive ones.
  For unverified findings: `status = candidate` plus a flag in the evidence; a separate status
  keeps them from being counted or shown with verified ones by accident.
- **Limits:** product defaults 400 steps and 60 minutes (the owner's setting). A workspace may set
  its own, higher or lower; a run may only lower its workspace's, the same rule as the current
  loop's per-run budgets (run 4, J3), so an API caller can't run past what the workspace allows.
- **No cost cap for deep runs:** steps and time bound a run, and quality comes first (D111);
  customers pay with their own key. The current loop's `MAX_RUN_COST_USD` stays as it is.


## D113. Deep mode's toolbox: general tools behind the same safety rules (2026-11-24)
- **Decision:** deep mode's model gets general browser tools (`deep/tools.py`, run by
  `deep/toolbox.py`): navigate, click, type, select, press_key, hover, scroll, any-size
  set_viewport, go_back; screenshot (JPEG), accessibility snapshot, visible text; evaluate_js,
  page_source, read_script; console and network since a mark; axe, layout, meta and the keyboard
  probe as tools. Elements are named by a `ref` from the latest snapshot (the same numbering as
  the current loop's observation), or by a CSS selector that must match exactly one element.
- **Safety, the same rules as the current loop:** passive mode's look-only rule, the deny list
  (also for Enter or Space on a destructive control, and for the keyboard probe's click), no card
  numbers off the demo shop, no navigation off the target, and a return to the site when a
  button or script leaves it. The proxy still guards every request.
- **Measuring must not act:** while an evaluate_js snippet runs, requests that send data (not
  GET, HEAD or OPTIONS) are blocked by a route on the page, and a MutationObserver tells the
  model if the snippet changed the DOM, with a warning that replay can't repeat it. page_source
  and read_script return only responses the browser already loaded: nothing new is fetched.
- **What replay repeats:** navigate, click, type, select, press_key, hover, scroll (its distance
  is recorded), set_viewport (width and height) and go_back; replay learned press_key, hover,
  any size and a scroll distance. The keyboard probe is evidence, not a replayed step: its key
  presses leave the page in a state replay can't rebuild exactly.
- **Alternatives:** Playwright MCP's own tools (a separate Node process, its own refs, none of our
  safety checks, and nothing recorded for replay); a sandboxed JavaScript (an isolated world
  can't read the page's own state, which is what measuring needs).
- **Tradeoffs:** a measuring snippet can still change the page; it is told, not prevented.
  Routing every request through Python to block data-sending ones during a snippet adds a little
  time per request.

## D114. Deep mode's process is enforced by the harness (2026-11-24)
- **Decision:** `deep/harness.py` drives the run in phases, one turn each: MAP (save_map with
  pages and flows), PLAN (save_plan, refused unless every checklist area has an item or a
  reasoned "not applicable", and layout has items at 390×844, 768×1024 and 1440×900), EXECUTE
  (plan items handed out 8 per turn, each ticked done, skipped or blocked), REVIEW (every
  candidate reported or dropped), then finish. Every tool call is a numbered step; the coverage
  (map, plan, progress, candidates, screenshots seen per viewport, budget used) is saved after
  every call.
- **Gates:** report_bug needs a flagged, open candidate and at least one browser tool call after
  the flag (the re-check), a self-review, and a verification spec: replay steps that exist and
  can be repeated; or a measurement or check the harness runs itself at that moment and stores
  (a check must report the named rule now). finish needs every item ticked, every candidate
  resolved and a screenshot seen at each viewport; when the last 10% of the steps or time is
  reached, the next prompt switches to review and finish is always allowed, with the unticked
  items recorded.
- **Stopping:** the step and time budgets, the user's Stop, three turns in a row without progress
  (phase, ticks, candidates, reports), and a usage limit, which pauses instead: everything is
  saved and the run can resume from its coverage (the browser restarts on the start page).
- **The checklist** (`deep/checklist.py`) is generic: core flows and forms (including whether a
  request is sent on submit), links and navigation, layout at three viewports, visual
  consistency, accessibility, meta and SEO, console and network, and whether the app's own text
  promises things that don't exist. A guard test keeps every benchmark app's names and bugs out
  of the prompts, checklist and tools.
- **Alternatives:** the process only in the prompt (the current loop's charter: models skip
  parts of it, MISS_ANALYSIS); one long turn with the harness only counting (no way to hand out
  the plan or to know cost at phase boundaries).
- **Tradeoffs:** a model that disagrees with a gate spends steps on refused calls; the error says
  what is missing. A resumed run loses the browser's state (a cart, a sign-in) and has to
  rebuild it.

## D115. Deep mode runs on the Claude Agent SDK, locked down to our tools (2026-11-24)
- **Decision:** the real driver (`deep/sdk_driver.py`) uses `claude-agent-sdk==0.2.180` (Python),
  the newest release at least two weeks old on 2026-11-24 (0.2.188 came out on 2026-11-23). The
  SDK runs its bundled Claude Code CLI as a subprocess; our tools are an in-process MCP server
  (`qa`). The CLI gets `tools=[]` (no built-in file, shell or web tools), `strict_mcp_config`
  (no other MCP server: not the user's, not claude.ai connectors), `setting_sources=[]` (no
  settings or CLAUDE.md), `permission_mode="dontAsk"` with only our tools allowed, our system
  prompt instead of Claude Code's, and a per-run folder in the system temp folder (checked to be
  outside the repo and the real-world apps' folder).
- **Authentication:** `DEEP_AUTH=api` passes the key to the CLI in its environment.
  `DEEP_AUTH=cli` (DEV_MODE only, never production) uses this machine's Claude login: the SDK
  always gives the CLI the worker's whole environment (read in its source: it only drops
  `CLAUDECODE`, and `options.env` can add but not remove), so the CLI is started through a
  wrapper script that unsets `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` first. The SDK's docs
  say third-party products may not offer claude.ai login; the login path is for the owner's own
  evaluation only, like claude-cli.
- **Threads:** the SDK is async; Playwright's sync API only works on its own thread. The SDK runs
  in a background thread and hands every harness call to the main thread through a queue.
- **Usage limits:** a rejected rate limit, any sign of paid overage (extra usage), a billing or
  rate-limit error, a 402/429 or a credit message, or a call paid from usage credits pauses the
  run at once; on the login path it also stops every other claude-cli call in the process.
- **Cost:** each turn's tokens from its result message, priced with `pricing.py`: charged on the
  API path, an API-equivalent estimate ($0 charged) on the login path. The SDK's own
  `total_cost_usd` is also a client-side estimate, so neither is a bill.
- **Tested without a model:** a fake CLI speaks the SDK's control protocol (initialize, MCP
  `tools/call`, interrupt) and plays scripted turns, so the driver runs end to end at $0.
- **Alternatives:** the Messages API with our own tool loop (no Claude Code harness: context
  compaction, retries and prompt caching would be ours to build); the `claude -p` subprocess the
  current claude-cli client uses (one JSON tool call per process, no real tool use, no images);
  Playwright's MCP server (no safety checks, nothing recorded for replay). ROADMAP's "Not planned:
  LangChain or LangGraph" still holds: the SDK is Anthropic's own harness, used for the model
  loop only, and the benchmark measures it against the current loop.
- **Tradeoffs:** the SDK's `Transport` and control protocol are marked internal, so the fake CLI
  can break on an SDK upgrade (the pin keeps that deliberate). Tool search is turned off with an
  environment variable so every schema is loaded up front.

## D116. Verifying deep-mode findings: replay, re-measure, or "unverified" (2026-11-24)
- **Decision:** every deep-mode finding goes through the run's verification
  (`execute.verify_and_dedupe`, after dedupe, as today), by the kind its report names:
  - **replay** (interaction bugs): the model's own recorded steps from the start page first,
    then the usual plans (every action up to the report); the existing judge, state diff and
    pixel check decide. Reproduced → confirmed; replayed but not shown → dismissed; couldn't be
    replayed at all → **unverified** (the current loop dismisses those: for deep mode a replay
    that can't run says nothing about the bug).
  - **measure / check** (`deep/measure.py`): a fresh page at the same viewport repeats the setup
    steps, then runs the stored snippet or check again. The same result (numbers rounded to one
    decimal, key order ignored) → confirmed; a different one → dismissed, with both values; a
    setup that can't be repeated or a snippet that fails now → unverified. An axe finding must
    be reported on the same element; a keyboard-probe finding opens the same control and must
    fail the same check.
  - no way given, or the run was stopped first → unverified.
- **`unverified` is its own status** (D112): never shown or counted with verified findings.
  Deep findings are always checked: the current loop's `MAX_RUN_COST_USD` doesn't apply to them
  (no cost cap for deep runs, D111/D112).
- **Alternatives:** dismiss what can't be checked (loses real bugs found in states replay can't
  rebuild, as in run be495c9f); keep them as candidates (they would read as unchecked-but-open,
  and the benchmark would count them).
- **Tradeoffs:** a measurement that depends on timing or randomness is dismissed when it
  differs; the model is told to report deterministic measurements. Rounding to one decimal can
  hide a difference smaller than that (sub-pixel sizes), which is the point.

## D117. A deep run's life: crawl, harness, verify; pause and resume (2026-11-24)
- **Decision:** `deep/run.py: run_deep` runs a deep run like an interactive one where it can: the
  same crawl and deterministic checks first (skipped on a resume), then the harness in a guarded
  context, then the run's verification. A `DbRecorder` writes every step (with its JPEG), finding,
  coverage update and turn's usage to the database as it happens; harness step n is the run's
  step `first_step + n - 1`, after the crawl's visits, and the step numbers in a finding are
  moved the same way.
- **Pause and resume:** a usage limit makes the runner set `paused` (new transitions: running →
  paused, paused → queued or stopped; a paused run is not final, so no webhook and no usage row
  yet). `worker resume RUN_ID` (and the dashboard's button) queues it again; the run continues
  from its coverage with a fresh browser, and the Agent SDK session is resumed when this machine
  still has it, else a fresh session starts. Findings so far are verified when it pauses.
- **Which driver:** `LLM_PROVIDER=fake` → the scripted driver with `DEEP_SCRIPT` ($0 tests and the
  end-to-end runs); otherwise the Agent SDK with `DEEP_AUTH`. On the API path the key is the
  run's workspace model's (an Anthropic model, Settings → Models), else the worker's own.
- **CLI:** `run-local URL --engine deep [--model claude-opus-5-5]`, `resume RUN_ID`,
  `bench --engine deep`, and `apps/realworld/measure.py --engine deep`. A paused run stops a
  benchmark the way a claude-cli usage limit does.
- **Export:** `engine`, `coverage`, a `verification` per finding (replay, measurement,
  deterministic or none), and unverified findings in their own `unverified_findings` list.
- **Alternatives:** a new worker process type for deep runs (two queues to operate); restarting a
  paused run from scratch (loses its map, plan and the tokens already spent).
- **Tradeoffs:** console errors and failed requests seen during a deep run are not turned into
  deterministic findings the way the loop's are; the model has console and network tools and a
  checklist area for them, and the crawl's deterministic findings stay (OPEN_QUESTIONS).

## D119. A usage limit during verification pauses the run too (2026-11-24, found in the evaluation)
- **What happened:** the first demo-shop deep run (`75a366f0`) paused correctly on the plan's
  five-hour limit, then verification asked claude-cli (the same login) to dedupe, hit the same
  limit, and the run was marked failed: 13 findings were left unchecked.
- **Decision:** a usage limit raised by verification is caught in `run_deep`: the run is paused
  (the first reason kept), the findings stay candidates, and verification continues on resume.
  A run whose agent had finished (`coverage.stop_reason == "finished"`) resumes with
  verification only; the agent doesn't run again.
- **Alternatives:** skip verification on every pause (a pause on the API path, where the judge
  may be another provider, could verify right away); fail the run (loses the findings).
