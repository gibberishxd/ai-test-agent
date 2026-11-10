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
