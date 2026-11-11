# Walkthrough

A study guide, one section per component: what it does, how it works, why it's built this way,
weak spots, and three interview questions with good answers.

---

## Report models (`apps/worker/src/worker/report.py`)

**What:** Pydantic models for the checker's output: `Report` → `PageResult` → console errors,
failed requests, accessibility violations; plus `BrokenLink`.

**How:** each class is a typed schema. `model_dump_json()` writes JSON, `model_validate_json()`
reads it back and *validates* it: wrong types or unknown enum values raise `ValidationError`.
`schema_version` marks the format so readers can handle old files.

**Why:** the worker and the web app are different languages. One typed definition, validated
at the boundary, stops them from silently disagreeing about the data.

**Weak spots:** the TypeScript copy in the web app has to be kept in sync (M2 adds a drift
test). No migration logic yet for future schema versions.

**Interview Q&A**
1. *Why Pydantic instead of plain dicts?* Dicts accept anything; a typo in a key or a string
   where a number belongs only fails later, far from the cause. Pydantic fails at the boundary
   with a clear message, and the class doubles as documentation.
2. *Why `Field(default_factory=list)`?* Each object gets its own new list. A shared mutable
   default is a classic Python bug; Pydantic happens to copy defaults, but the factory states
   the intent explicitly.
3. *What is `schema_version` for?* When the format changes incompatibly, readers can tell old
   files from new ones and handle or reject them, instead of misreading them.

---

## URL helpers (`apps/worker/src/worker/urls.py`)

**What:** `normalize(url)` returns one canonical string per page; `is_same_origin(url, start)`
keeps the crawl on the target site.

**How:** `urlsplit` breaks a URL into parts. Normalization drops the `#fragment`, lowercases
scheme and host, drops default ports (80/443), turns an empty path into `/`. Origin = (scheme,
host, port), with the default port filled in; only http(s) qualifies.

**Why:** the crawler's visited set compares strings. Without normalization, `/cart` and
`/cart#top` look like two pages and loops become possible.

**Weak spots:** query parameter order isn't normalized yet (the brief asks for sorting: M3).
`/` and `/index.html` still count as different pages. Path case is kept on purpose.

**Interview Q&A**
1. *Why drop the fragment?* The browser never sends it to the server; it's the same document.
2. *Why not lowercase the whole URL?* Scheme and host are case-insensitive by spec, but the
   path and query may not be: `/Cart` and `/cart` can be different pages.
3. *What counts as "same origin"?* Same scheme, host and port: the browser's own security
   boundary. `http://site` and `https://site` are different origins.

---

## Crawler (`apps/worker/src/worker/crawler.py`)

**What:** visits every same-origin page reachable from the start URL, each exactly once, up to
`max_pages`.

**How:** breadth-first search. A queue of `(url, found_on)` pairs, a `seen` set of normalized
URLs (added when *queued*, not when visited), and a page budget. The page-visiting function is
passed in as a parameter.

**Why:** BFS covers the pages closest to the start first, so a cut-off crawl still covers the
most reachable pages. Passing `visit` in (dependency injection) lets the loop logic be tested
in milliseconds with a fake site, without a browser.

**Weak spots:** no `max_depth` yet (M3). Visits pages one at a time (no parallelism).
`found_on` keeps only the first page that linked to a URL.

**Interview Q&A**
1. *How do you stop a crawler from looping forever?* A visited set of normalized URLs stops
   revisits; a page budget stops infinite URL spaces like `?page=1,2,3…` that a set can't.
2. *Why add to `seen` when queuing rather than when visiting?* Otherwise two pages linking to
   the same URL would queue it twice before either visit happens.
3. *Why BFS rather than DFS?* With a page budget, DFS can spend the whole budget down one deep
   path; BFS spreads coverage across the site's top levels first.

---

## Page visits (`apps/worker/src/worker/browser.py`)

**What:** `visit_page(context, url)` loads one URL in headless Chromium and returns a
`PageResult` (status, title) plus the absolute URLs of all links on the page.

**How:** a fresh tab per URL inside a shared browser context. `page.goto` with a 15 s timeout;
then wait for `networkidle` (no requests for 500 ms), giving up quietly after 5 s; then read
every `a.href` via JavaScript. Navigation errors become `PageResult.error`, not exceptions.

**Why:** React renders links after the `load` event, so waiting for the network to go quiet
finds them. Fresh tabs keep each page's events separate; the shared context keeps cookies.
Errors-as-data means one dead page doesn't kill the whole run.

**Weak spots:** `networkidle` can be slow on chatty pages (polling) and fast-but-premature on
apps that render after a timer. `a[href]` misses navigation done by buttons or JS handlers.

**Interview Q&A**
1. *Why wait for `networkidle`?* SPAs build the DOM with JavaScript after load; reading links
   too early misses them. The timeout stops pages that never go quiet from hanging the run.
2. *Why a new page per URL?* Event listeners (console, network) attach per page, so late events
   from one page can't be blamed on the next.
3. *How are test pages served?* A pytest fixture starts Python's `http.server` on port 0 (the
   OS picks a free port) in a background thread: real HTTP, no mocks, no port clashes.

---

## Demo shop (`apps/demo`)

**What:** the benchmark target. A small React shop (product list, product page, cart,
checkout, login, profile, returns) with 12 planted bugs listed in `bugs.json`, plus a
prompt-injection review on the Linen Notebook page. Two builds from one codebase: buggy on
5173, clean on 5174.

**How:** `src/bugs.ts` exports `bug(n)`, true except in Vite's `clean` mode. Each bug is a
one-line branch, e.g. `cartTotal(cart, { ignoreQuantity: bug(5) })`. A tiny Vite plugin
returns real HTTP errors (500 for `/api/profile`, 404 for `/return-policy`).
`verify/bugs.e2e.ts` proves each bug: 13 tests × 2 projects, each expecting the bug on
`buggy` only. Run `npm run verify-bugs`.

**Why:** a benchmark needs ground truth. The buggy build measures recall (how many planted bugs
the agent finds); the clean build measures false alarms (anything reported there is wrong).
Using one codebase means the only difference between the two is the bugs.

**Weak spots:** 12 bugs is a small sample, so one found or missed bug moves recall by 8
points. The bugs are known to whoever writes the agent prompt, so there's a risk of tuning to
them; held-out bugs would be a fairer test. The cart lives in memory, so a full page load
empties it.

**Interview Q&A**
1. *How do you measure false alarms?* Run the agent against the clean build, which is the same
   code with every bug switched off. Anything it reports there is a false alarm by definition.
2. *Why verify the planted bugs with tests?* So the ground truth is itself proven: if a refactor
   accidentally removed a bug, the benchmark would quietly report a "miss" that isn't the
   agent's fault. The check also proves each bug disappears in the clean build.
3. *Why does the 404 need a server plugin?* A single-page app's dev server returns `index.html`
   with status 200 for any path; the "not found" page is drawn by JavaScript. To give the
   checker a real HTTP 404, the server has to send one.

---

## Database schema (`apps/web/prisma/schema.prisma`) and its Python mirror (`apps/worker/src/worker/db/models.py`)

**What:** six tables (workspaces, users, runs, steps, bugs, benchmark_results, audit_log) and
five enums. Prisma owns the schema and migrations; the worker describes the same tables with
SQLAlchemy.

**How:** `prisma migrate dev` turns schema changes into SQL migration files. The Python models
use `create_type=False` enums and `server_default`s, so they never try to create anything.
A test builds a fresh database from the migration SQL and compares it with the models.

**Why:** two languages share one database. One owner (Prisma) avoids two competing migration
systems; the drift test catches the mirror falling behind.

**Weak spots:** the mirror is still hand-written, so every schema change touches two files.
Money is stored as `Float` (fine for cost tracking at fractions of a cent; `Decimal` would be
the choice for billing).

**Interview Q&A**
1. *Why does Prisma own the schema when Python also writes to it?* One source of truth for
   migrations. The web app needs typed queries most; the worker only mirrors the tables and a
   test proves the mirror matches.
2. *Why do ids come from Postgres (`gen_random_uuid()`)?* Prisma's `uuid()` default runs in
   JavaScript. Rows inserted from Python would have no id. A database default works for every
   client.
3. *How do you catch schema drift?* The test database is built from the real migration SQL,
   then SQLAlchemy's inspector compares tables, columns and nullability with the models.

---

## Run queue (`apps/worker/src/worker/queue.py`, `runner.py`, `main.py`)

**What:** the web app inserts a `runs` row with status `queued`; the worker claims it, does the
work, and sets `done`, `failed` or `stopped`.

**How:** `SELECT ... WHERE status='queued' ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED`,
then set `running` and commit. `transition()` only allows queued→running/stopped and
running→done/failed/stopped. `process_next` wraps the work in try/except, so any exception
becomes `failed` with the error text. `uv run worker` polls every second; `--once` does one run.

**Why:** Postgres is already there, and a row-lock queue is enough for this scale: no Redis, no
extra service to deploy. `SKIP LOCKED` lets many workers poll at once without blocking each
other or taking the same run.

**Weak spots:** if a worker dies mid-run, the run stays `running` forever (fix: a heartbeat
column plus a sweeper that re-queues or fails stale runs). Polling adds up to 1 s of latency
(fix: Postgres `LISTEN/NOTIFY`).

**Interview Q&A**
1. *What does `SKIP LOCKED` do?* Rows locked by another transaction are skipped instead of
   waited for, so concurrent workers each get a different row immediately.
2. *Why commit right after claiming?* The status change to `running` is what keeps other
   workers away; committing makes it visible and releases the lock, so a long run doesn't hold
   a database transaction open.
3. *Why a transition table?* Status is the contract with the UI. Refusing illegal moves (like
   done → running) turns silent state bugs into loud errors.

---

## LLM clients (`apps/worker/src/worker/llm/`)

**What:** one interface, `LLMClient` (`decide` = pick one tool, `review_screenshot`,
`complete`), with three implementations: `ClaudeClient` (Anthropic SDK), `OllamaClient` (local
HTTP), `FakeClient` (scripted, for tests). `make_client(settings)` picks by `LLM_PROVIDER`.
Every call returns a `Usage` with tokens and cost.

**How:** tools are described once as `ToolSpec` (name, description, JSON Schema) and converted
to each provider's format. Claude: `cache_control` on the last tool and on the system prompt
caches that prefix; `strict` tools; `tool_choice: auto`. Ollama: OpenAI-style function tools,
images as base64, and a fallback that finds a JSON tool call in plain text. Cost comes from a
price table (`pricing.py`); unknown models are charged the highest known price.

**Why:** swapping providers is a config change, so the benchmark can compare Claude and a free
local model on equal terms. FakeClient makes the agent loop testable for free and
deterministically.

**Weak spots:** prices are hard-coded and need updating by hand. The Ollama client uses one
model for both "agent" and "cheap" calls. The Claude client hasn't been run against the live
API yet (no key tonight); its unit tests use a stand-in SDK object.

**Interview Q&A**
1. *Why an interface instead of calling the SDK directly?* The agent shouldn't care which model
   answers. It also lets every unit test use a scripted fake, so tests cost nothing and never
   flake on model randomness.
2. *How does prompt caching cut cost here?* Each step sends the same tools and system prompt
   followed by a new observation. Marking the end of the stable part as cacheable makes later
   steps read it at about a tenth of the input price.
3. *What if the model doesn't call a tool?* `decide` returns `tool_call=None`; the loop counts it
   as a wasted step against the budget and asks again, instead of crashing.

---

## Deterministic checks (`apps/worker/src/worker/browser.py`, `findings.py`)

**What:** for every page: console errors and uncaught exceptions, failed requests and HTTP
4xx/5xx (page, fetch/XHR, assets), broken links (including SPA "not found" pages), axe-core
WCAG A/AA violations, slow loads (> 3 s), and a full-page screenshot. `findings.py` turns them
into bug reports.

**How:** Playwright events (`console`, `pageerror`, `requestfailed`, `response`) fill lists
while the page loads. axe-core (vendored, pinned 4.14.0) is injected with `page.evaluate`, which
a site's Content Security Policy can't block. Findings are grouped by problem (same error text,
same failing URL, same axe rule), keep every page they were seen on, and carry the raw evidence.

**Why:** these checks are free and never hallucinate, so they run first and on every page. Grouping
turns per-page noise into a report a developer can act on.

**Weak spots:** a broken link records only the first page that linked to it (the crawler's seen
set). The 3 s slow-page threshold is arbitrary, and local timings aren't representative. The
soft-404 heuristic (an h1 saying "not found") can miss custom wording.

**Interview Q&A**
1. *Why drop Chrome's "Failed to load resource" console errors?* They're Chrome's echo of a
   failed request that's already captured with better detail (URL, method, status). Keeping both
   would report the same bug twice.
2. *Why only WCAG A/AA axe rules?* They're testable requirements. Best-practice rules are
   opinions; counting them would make the false-alarm rate depend on taste.
3. *How does it find broken links in a single-page app?* A real server 404 is caught by status
   code. An SPA returns 200 for every path, so a page whose main heading says "not found" counts too.

---

## Safety guard (`apps/worker/src/worker/safety/`)

**What:** rule 6.1 (no private/internal addresses, re-checked on every redirect, stay on the
target's origin), 6.2 (passive mode = links only), 6.6 (secrets redacted from logs and stored
text).

**How:** `NetworkGuard.vet(host, port)` resolves the name and requires every IP to be global
(`ipaddress.is_global`) and not a metadata endpoint, returning the IP to use. `GuardProxy` is
an HTTP/CONNECT proxy the browser must use; it calls `vet` per request and connects to the
returned IP. In dev mode only our demo shop ports on localhost are exempt. `check_mode` refuses
type/select/submit and non-link clicks in passive mode. `redact` masks API keys, bearer tokens
and `password=`-style values; a logging filter applies it to every log line.

**Why:** the worker's browser runs inside our infrastructure, so a user-supplied URL must never
reach internal services (SSRF). Enforcing in code, not in the prompt, means a confused or
manipulated model can't get around it.

**Weak spots:** the proxy forwards plain HTTP one request per connection (simple but slower).
The off-origin rule is checked on the requested URL, not after redirects. In production I'd run
a hardened egress proxy (e.g. Stripe's smokescreen) and firewall the worker's network as a second
layer.

**Interview Q&A**
1. *What is SSRF and why does a testing tool care?* Server-side request forgery: tricking a
   server into fetching URLs for you. Our worker fetches arbitrary URLs by design, so without a
   guard a user could read `169.254.169.254` (cloud credentials) or internal admin pages.
2. *Why a proxy instead of Playwright's `route`?* A test proved `route` only sees the first
   request; redirects are followed internally. A proxy sees every hop, and connecting to the
   vetted IP also defeats DNS rebinding.
3. *Why is the localhost exemption tied to specific ports?* So dev mode can test our own demo
   shops without opening Postgres, the web app or anything else on the machine.

---

## Passive scan and run execution (`scan.py`, `review.py`, `execute.py`, `storage.py`)

**What:** a passive run crawls the target through the guard proxy, runs the checks, asks the
model to review a few screenshots for visual problems, and writes steps, bugs, cost and a
summary to Postgres. `uv run worker scan URL` does the same without a database and writes
`reports/<time>/report.json`.

**How:** each visited page is saved as a `visit` step immediately (live progress) and the Stop
flag is checked after each page. Screenshots go through a `Storage` interface (local disk now)
keyed by `<run id>/page-001.png`. Model findings are `candidate` bugs; the review stops when the
run's cost budget is used up.

**Weak spots:** the screenshot review sends full-page screenshots (not downscaled yet); it
reviews the first N pages rather than choosing the most interesting ones.

**Interview Q&A**
1. *Why write each step as it happens?* The live run page polls the database; committing per
   page makes progress visible within a second and keeps partial results if the run crashes.
2. *Why separate "confirmed" and "candidate" bugs?* Deterministic findings have hard evidence.
   Model findings can be wrong; they wait for replay verification.
3. *What does the storage interface buy you?* Moving screenshots to S3 or R2 later is one new
   class; nothing that reads or writes screenshots changes.

---

## Agent loop (`apps/worker/src/worker/agent/`)

**What:** interactive mode. Each step: observe the page → the model calls exactly one tool →
the worker checks it against the safety rules → runs it → logs it. Ends on `finish`, a budget
(steps, time, cost), loop detection (same action 3× in a row without changing the page, or 6× in a row) or the Stop button.

**How:**
- `observe.py` tags visible interactive elements with `data-agent-id`, lists them as
  `[id] role "name" value/state`, adds new console/network events, the last 12 steps, bugs
  already reported, and the page text inside `<page_content>` (untrusted). A screenshot is
  attached only on a page's first visit, after the URL changes, or when the model asks.
- `tools.py`: click, type, select, navigate, go_back, scroll, take_screenshot, report_bug,
  finish. Every tool has a `reasoning` argument (shown in the timeline).
- `policy.py`: the deny list (pay, purchase, delete, unsubscribe, change password/email, send,
  transfer; buy outside the demo), card numbers only on the demo shop, and `Budget`.
- `loop.py`: `AgentRun` ties it together; callbacks save steps and bugs to the database live.
- `prompt.py`: a fixed system prompt (cacheable) with the testing approach, reporting rules,
  severity rubric and the untrusted-content rule.

**Why:** the model decides, the worker enforces. Safety and budgets live in code, so a
confused or manipulated model can't skip them. One request per step with a stable prefix
keeps cost per step flat and cacheable.

**Weak spots:** the accessible-name logic is an approximation of the browser's real algorithm.
The memory is only the last 12 steps. Navigate does a full reload, which loses in-memory state
(the prompt steers the model to click instead). A small local model often clicks around
without reporting; quality depends heavily on the model.

**Interview Q&A**
1. *How do you stop the agent from doing something destructive?* Every action is checked by
   the worker before it runs: mode rules, a deny list on the element's text, link and form
   action, card numbers only on the demo shop, and navigation only on the target's origin. A
   blocked action is logged and shown to the model, which picks something else.
2. *How do you defend against prompt injection?* The system prompt says page content is data,
   page text is fenced in a `<page_content>` block (and a fake closing tag in the page is
   neutralised), and the tools can't reach anything outside the browser. Even a fully
   "convinced" model can only click around the target site within budget.
3. *Why give the model numbered elements instead of HTML?* It's 10–50× fewer tokens, so it's
   cheaper and faster, and the model can only target elements that exist; the worker keeps the
   precise locator.

---

## Replay verification and dedup (`apps/worker/src/worker/verify.py`, `execute.py: verify_and_dedupe`)

**What:** after a run, every candidate bug (anything the model reported) is replayed in a fresh
browser context and either confirmed or dismissed with a reason. Then the cheap model merges
duplicates. Deterministic findings are confirmed without replay.

**How:** each agent step stores the role and name of the element it acted on. Replay opens the
start URL in a new context (no cookies, no state) and repeats the steps with
`get_by_role(role, name)` (falling back to exact text). The final screenshot and page text go to
the model with the bug's title, expected and actual: it must answer
`{"reproduced": true|false, "reason": ...}`, and anything unclear counts as false. If a step
can't be repeated, the bug is dismissed without a model call. Dedup sends a numbered list of
the surviving bugs to CHEAP_MODEL; each duplicate is dismissed with "duplicate of: …" and
linked by `duplicate_of_id`, always keeping the deterministic report when one is involved.

**Why:** models report things that aren't there. A second, independent look at a clean
re-creation of the steps filters many of them out, and a strict "unclear = no" rule trades a
little recall for much better precision, which is what a team acting on the report needs.

**Weak spots:** replay depends on role/name being stable; dynamic names ("Cart (2)") break it.
In-memory state reached via a full-page navigate can't be reproduced. The verifier is the same
model family as the reporter, so they can share blind spots. Bugs that need timing (double
clicks) are replayed as single clicks.

**Interview Q&A**
1. *Why replay in a fresh context instead of re-asking the model about the original screenshot?*
   A fresh context proves the bug comes from the steps, not from leftover state, and gives the
   verifier evidence it hasn't seen yet instead of asking it to agree with itself.
2. *Why does an unclear verdict count as "not reproduced"?* False alarms cost a team's trust and
   time. Requiring a clear yes makes the report something people act on; dismissed bugs stay
   visible with their reason, so nothing is silently lost.
3. *Why use the cheap model for dedup?* It's a comparison of short texts, not a judgement about
   the app, so a small model does it well at a fraction of the price.

---

## Web app (`apps/web`)

**What:** Next.js 16 (App Router) + Tailwind 4 + shadcn/ui. Pages: landing (`/`), dashboard
with the run form and recent runs (`/dashboard`), run history (`/runs`), live run + report
(`/runs/[id]`). API routes: create/list runs, run detail (polled), stop, JSON download,
screenshots (`/api/files/...`).

**How:**
- `lib/runs.ts` is the only place that reads/writes runs; every function takes a
  `workspaceId` and filters by it. `lib/workspace.ts` decides the workspace for a request.
- `lib/targets.ts` validates the form (http(s) only, interactive only on the demo shop or a
  verified domain). The worker enforces the same rules again.
- `components/run-view.tsx` is a client component: it gets the run from the server on first
  render, then polls every 1.5 s until the status is final. The timeline shows each step with its
  reasoning, thumbnail and any blocked action; the report shows bug cards sorted by severity
  with copy-as-GitHub-issue / Jira buttons (`lib/export.ts`, pure functions with tests).
- `/api/files/[...key]` serves screenshots only if the key's run belongs to the workspace, and
  refuses keys that would escape the data folder.
- `lib/contracts/types.ts` is the TypeScript copy of the worker's bug shape; a Vitest test
  compares it with `schema.json` (exported from the Pydantic models).

**Why:** server components fetch data close to the database; only interactive pieces (form,
polling, copy buttons) are client components. Validation lives in small pure functions so it's
unit-tested; the e2e test proves the whole loop through the real worker.

**Weak spots:** polling every 1.5 s per open tab is fine for a demo, wasteful at scale (SSE +
`LISTEN/NOTIFY` would fix it). A missing run renders the not-found page with HTTP 200 (Next
streams the loading state before `notFound()` runs).

**Interview Q&A**
1. *How does the browser see live progress if the worker never talks to the web app?* The
   worker commits a step row per action; the run page polls an API route that reads those rows.
   Postgres is the shared state.
2. *Why validate the URL in the web app if the worker checks it too?* Different jobs: the web
   app gives a friendly message before anything is queued; the worker is the security
   boundary and must never trust its input.
3. *How do you stop one customer seeing another's screenshots?* Screenshot keys start with the
   run id; the file route looks the run up scoped to the caller's workspace before reading the
   file, and normalises the path so `../` can't escape the folder.

---

## B2B foundations (`apps/web/lib/auth*.ts`, `workspace.ts`, `limits.ts`, `domains.ts`, `share.ts`, `settings-data.ts`)

**What:** sign-in (GitHub, email magic link, dev demo user), a personal workspace per user,
workspace-scoped data, domain verification for interactive mode, a monthly run quota with a
usage page, an audit log, revocable read-only share links, and limits for signed-out visitors.

**How:**
- `currentContext()` returns `{workspaceId, userId, signedIn}` for every request: the user's
  workspace from the JWT, or the public demo workspace for visitors. Every query filters by it.
- `startRun()` is the one gate before a run is queued: validation, visitor rules (demo shop
  only, 5/hour/IP), quota (runs since the 1st of the month), then an audit log entry.
- Domains: add → verify (TXT record or well-known file containing the workspace token) →
  `verified_at` set → `parseRunInput` (web) and `is_verified_domain` (worker) allow
  interactive mode there.
- Share links: `runs.share_token` = 24 random bytes (base64url). `/share/<token>` renders the
  report read-only; revoking sets the token to null.
- Tests: `lib/b2b.db.test.ts` runs against a real Postgres: cross-workspace reads, stops and
  shares fail; verification; quota; share links; visitor limits.

**Why:** these are what make it a product a team can use safely: their data stays theirs,
interactive testing only happens on sites they own, and usage is bounded and visible.

**Weak spots:** one workspace per user (no invitations or roles yet). The visitor rate limit
trusts `X-Forwarded-For` (fine behind a known proxy, spoofable without one). The quota counts
runs, not cost. No email is actually sent without SMTP settings.

**Interview Q&A**
1. *How do you guarantee tenant isolation?* Every data function takes the workspace id from
   the server-side session, never from the request body, and filters by it; a database test
   proves another workspace's run can't be read, stopped or shared.
2. *Why make domain verification support both DNS and a file?* DNS is the standard but needs
   DNS access; a file works for anyone who can deploy the site. Both prove control of the domain.
3. *How do share links stay safe?* 192 random bits can't be guessed or enumerated, the page is
   read-only (no stop, no re-share, no polling of private APIs), it's `noindex`, and revoking
   nulls the token so the old URL 404s immediately.

---

## Benchmark (`apps/worker/src/worker/benchmark.py`, `main.py: bench`, `apps/web/app/benchmark`)

**What:** `npm run bench` runs the agent N times (default 3) on the buggy shop and once on the
clean shop, matches every reported bug to `apps/demo/bugs.json`, and prints and stores recall,
precision, false alarms, average cost and duration, provider, model and git commit. The
benchmark page shows the latest score per provider, trend charts across versions, a per-bug
found/missed table, and every match decision.

**How:** runs go through the normal queue (same code path as a real run). For each surviving
report, the planted bugs on the same page are the candidates (all of them if none match the
page); the cheap model answers `{"match": id|null, "reason": ...}`. Recall = distinct planted
bugs found per run, averaged; precision = matched reports / all reports (a duplicate of a real
bug counts as real); false alarms = reports per clean run. `--rescore` re-matches the latest
result's runs without running the agent again.

**Why:** a testing tool without a measurement is a demo. Saving each match decision makes the
score auditable: the first real benchmark said 0% recall, and the saved decisions showed in
seconds that the model had answered `"match": "2"` (a string) while its reason said "matches
bug 2". A test now pins that.

**Weak spots:** 12 bugs is a small sample (one bug moves recall by 8 points). The matcher is a
model too, so it can be wrong; the decision log is the safeguard. The bugs are known to whoever
tunes the prompt, so there's a risk of overfitting; held-out bugs would be fairer. Cost of the
matching calls isn't included in cost per run.

**Interview Q&A**
1. *How do you measure precision for an agent like this?* Every report the user would see is
   matched to the known bug list; reports that match nothing are false positives. The clean
   build gives a second, stricter number: anything reported there is wrong by definition.
2. *Why use a model to match reports to known bugs?* Reports are free text ("total wrong for 2
   mugs" vs "cart total ignores quantity"); exact matching would undercount. The page narrows
   the candidates, and every judgement is stored so a human can audit it.
3. *What did the benchmark tell you?* With a local 8B model, recall 33% with 100% precision:
   all from the deterministic checks. The agent explores flows but rarely judges what it
   sees, which is exactly the question a Claude run answers next.

---

## Run 2: safety hardening (`agent/policy.py`, `agent/loop.py`, `config.py`, `urls.py`)

**What:** four rules the worker enforces whatever the model asks for.
- *Dev mode is opt-in.* `dev_mode` defaults to `False`; only `DEV_MODE=true` lets the browser
  reach the demo shops on localhost.
- *Safe mode is a rule table.* `DENY_RULES` lists final or destructive actions by category
  (payment, commitment, subscription, destructive, account, outbound).
- *The agent stays on the target site.* Three checks in `loop.py`: at the start (the target
  must not redirect elsewhere), before a click (a link to another site is refused) and after
  every action (`_return_to_site` goes back if the page left).
- *Loop detection counts repeats without effect.* `Budget.record(..., changed=)`.

**How:**
- `deny_reason(element, is_demo_target)` builds five fields from the element (text,
  aria-label, button value, link, form action) and tries each rule's regex on each. URLs go
  through `url_words` first: host dropped, `%20` decoded, camelCase split, punctuation turned
  into spaces, so `\bplace\s+order\b` matches `/checkout/place-order`.
- `is_same_site(url, target)` is true for the same origin (scheme + host + port) or for the
  https version of an http target on the same host and default ports.
- `_execute` returns `(result, changed)`, where changed means the URL, the page text or the
  scroll position is different. `Budget` keeps two counters: `_idle` (identical actions in a
  row that changed nothing, limit 3) and `_same` (identical actions in a row, limit 6).

**Why:** each closes a way the agent could do harm or waste a run: reaching our own network,
committing to a purchase on a customer's site, typing into a site nobody verified, or being
stopped for doing legitimate repeated testing.

**Weak spots:** the deny list is English only and keyword based, so an icon-only "trash"
button with no label passes, and "Remove filter" is blocked. Origins are compared strictly, so
a login on `auth.shop.example` can't be tested from `shop.example`. A new tab opened by a link
isn't followed. "Changed" is text based: a change that only alters colours looks like nothing.

**Interview Q&A**
1. *Why is safe mode in the worker and not in the prompt?* A prompt is a request; the model
   can ignore it, and page text can talk it out of it (prompt injection). The worker checks
   every tool call before running it, so the rule holds whatever the model decides.
2. *Why check the page's site after the action as well as before?* Before the click you can
   only read what the element says: a link has an href, a button doesn't. A button, a form
   submit or a script can go anywhere, so the only reliable check is where the page ended up.
3. *Why two loop counters?* "Same action three times" stopped runs that clicked "+" three
   times, which is exactly how you test a quantity bug. Counting only repeats that changed
   nothing fixes that, but a model adding to the cart forever changes the page every time, so
   a second, higher limit catches that case.

## Run 2: web hardening (`lib/limits.ts`, `lib/socket-address.ts`, `instrumentation.ts`, `lib/runs.ts`, `lib/share.ts`, `lib/domains.ts`)

**What:**
- *Client IP you can't fake* for the visitor rate limit.
- *Atomic quota:* a burst of requests can't exceed the monthly quota.
- *Shared reports show their screenshots,* and a share token opens only its own run's files.
- *Domain verification connects to the address it checked.*

**How:**
- `instrumentation.ts` runs once at server start and wraps `http.Server.prototype.emit`; for
  every "request" event `stampSocketAddress` writes the socket's peer address into the
  `x-socket-address` header, replacing anything the client sent. `clientIp` reads that header,
  or, with `TRUST_PROXY=true`, the entry of `X-Forwarded-For` that our own proxy appended.
- `startRun` runs in `db.$transaction`: lock the workspace row with `SELECT ... FOR UPDATE`,
  count, then insert. A second request for the same workspace waits at the lock and then
  counts the first one's run.
- `canReadFile(key, {workspaceId, shareToken})` looks for the run named in the file path
  either in the caller's workspace or with that share token. `fileUrl(key, token)` adds
  `?share=` on shared pages.
- `fetchPinned(url, ip)` passes `lookup: pinnedLookup(ip)` to `https.get`, so Node connects to
  `ip` without asking DNS again.

**Why:** all four were holes found in review: a spoofable header, a race, a broken feature,
and a time-of-check/time-of-use gap.

**Weak spots:** the socket stamp patches a Node built-in and doesn't exist on edge runtimes.
The row lock serialises all starts in one workspace, including the public demo workspace all
visitors share. Screenshots are cached by the browser for an hour, so a revoked link's images
can still show from cache. Verified domains are never re-checked.

**Interview Q&A**
1. *Why is the left-most X-Forwarded-For entry unsafe?* Each proxy appends the address it saw.
   The left side is whatever the client sent, so only the entries written by proxies you
   control can be trusted, and those are on the right.
2. *What is a check-then-act race, and how does the lock fix it?* Two requests both read
   "49 of 50 used" before either inserts, so both insert. `FOR UPDATE` makes the second
   request wait until the first transaction commits, so it reads 50.
3. *What is DNS rebinding?* You resolve a name, check the address is public, then connect by
   name; the client resolves again and the attacker's DNS now answers a private address.
   Connecting to the address you checked removes the second lookup.

## Run 2: tester's tools and a richer observation (`agent/tools.py`, `agent/observe.py`, `agent/prompt.py`, `review.py`)

**What:** new tools (`double_click`, `reload`, `set_viewport`, `note`), phone-width screenshots
in the passive scan, field states and positioned messages in the observation, changed values
first in "what changed", and a QA test charter in the system prompt.

**How:**
- `_execute` handles the new actions; `set_viewport` resizes the page and asks for a screenshot
  next step; `note` appends to `Memory.notes`, which `build_observation` prints every step.
- `COLLECT_ELEMENTS_JS` adds `required`, `invalid` and `described` per field.
  `COLLECT_MESSAGES_JS` finds visible `[role=alert|status]`, `[aria-live]` and error-looking
  classes, and assigns each the field in the same group (walking up at most 4 parents) or the
  closest overlapping field within 60 px.
- `text_changes` groups lines by "shape" (digits replaced by #), so `Subtotal: $12.00` and
  `Subtotal: $24.00` pair up and print as a change.
- `visit_page` takes a second full-page screenshot at 375×812; `review_screenshots` reviews
  both and marks phone findings `evidence.viewport = "mobile"` so `verify_bug` checks at 375 px.

**Why:** each one closes a gap between what a human tester can see or do and what the agent
could. The charter is generic on purpose; a test fails if any demo-app detail leaks into it.

**Weak spots:** "next to" is a heuristic: unusual layouts (errors in a toast at the top of the
page) won't be tied to a field. Error classes are English-ish (`error`, `invalid`, `alert`).
Phone screenshots double the review cost of a passive scan. The charter makes the prompt longer,
which small local models follow less reliably.

**Interview Q&A**
1. *Why not just give the model the HTML?* It is large and mostly noise, so it costs more and
   small models get lost in it. A short list of numbered controls with their state, plus the
   messages and where they sit, carries what a tester actually looks at.
2. *How do you keep the prompt from overfitting to your own demo?* The charter only names
   techniques, never sites or bugs, and a unit test reads `bugs.json` of both demo apps and
   fails if any title, product name, code or address appears in the prompt or tool text.
3. *Why does the note tool help?* Each model call only sees the current observation. To check
   "did the total double?", the agent needs the old total; a note keeps it in view.

## Run 2: replay that clicks the right thing (`verify.py: find_target`, `execute.py: replay_plans`)

**What:** replay finds the exact element the agent acted on or fails with a reason; it tries a
short replay from the last navigation first; dedup runs before replay.

**How:**
- `Element.target()` stores role, name, `nth`/`count` among same role+name, `context` (first
  nearby line that isn't its own label, from `CONTEXT_JS`) and `css` (from `CSS_PATH_JS`).
- `find_target` tries, each only if it yields exactly one element: role+name, then the match
  whose `CONTEXT_JS` equals the recorded context, then the CSS path if it points at one of the
  matches, then `nth` if today's count equals the recorded count. Otherwise `ReplayError`.
- `replay_plans` returns `[(last navigate URL, steps after it), (target, all steps)]`; blocked
  steps are dropped; a viewport change before the navigate is carried into the short plan.
- `verify_and_dedupe` runs `_dedupe` first (keeping deterministic findings as the original),
  then replays only agent candidates.

**Why:** "first match" made verdicts about the wrong element; full replays repeated side
effects; and agent restatements of server errors were dismissed by a replay that can't show a
failed request.

**Weak spots:** context is the first nearby line, which may be the same for two cards ("Sale!").
A CSS path breaks when the page structure changes. Starting at the last navigation can miss
state built earlier in local storage; the full replay is the fallback, at the cost of a second
model call. Dedup quality depends on the cheap model.

**Interview Q&A**
1. *Why fail instead of clicking the first match?* A wrong click produces a confident wrong
   verdict, which is worse than "could not replay": the latter is visible and honest.
2. *Why replay from the last navigation first?* A full page load resets in-memory state, so
   earlier steps matter less, and skipping them avoids repeating side effects like placing an
   order. If it doesn't reproduce, the full replay still runs.
3. *Why dedup before replay?* Deterministic findings have hard evidence. If the agent reports
   the same failed request, replaying it can only fail (the model can't see a network error in
   a screenshot) and would dismiss a real bug. Merging it first avoids that.

## Run 2: honest benchmark and the holdout app (`benchmark.py`, `main.py: bench`, `apps/demo2`, `apps/web/app/benchmark`)

**What:** the benchmark reports AI-only recall next to overall recall, scores a second app the
agent is never tuned against, records the judge, and keeps the original commit on a rescore.

**How:**
- `PlantedBug.detection` comes from `bugs.json`. `score()` computes recall over all planted
  bugs and over those with detection "agent"; `per_bug` stores the detection too.
- `run_benchmark` queues four groups of runs (shop buggy/clean, holdout buggy/clean) and
  `score_runs` scores each app against its own `bugs.json`; the holdout scores sit in
  `BenchmarkScores.holdout` and in their own columns (`holdout_ai_recall`, ...).
- `rescore_latest` passes the stored `git_commit` through and sets `rescore_commit`.
- `apps/demo2` is built like the shop: every bug behind `bug(n)`, a fake API in the Vite dev
  server, `verify/bugs.e2e.ts` checking each bug is present on 5175 and absent on 5176.
- The web page's helpers (`percentOrDash`, `judgeLabel`, `commitLabel`, `holdout`) show a dash
  or "not recorded" for older rows rather than a misleading 0%.

**Why:** a single recall number mixed what every model gets for free with what only a good model
finds, and nothing showed whether the agent was learning the shop.

**Weak spots:** the holdout is small (6 bugs, 2 runs), so one found bug moves its recall by
25 points. Both apps are written by the same person, in the same style, so they share more than
real sites would. The judge is still a model: a weak judge can mis-score both apps.

**Interview Q&A**
1. *Why report AI-only recall?* The deterministic checks find their bugs for every model, so
   overall recall makes a weak and a strong model look alike. AI-only recall isolates the part
   the model is responsible for.
2. *What does the holdout prove, and what doesn't it?* It shows the techniques work on an app
   the prompt was never adjusted for. It doesn't prove the agent works on any real site: both
   apps are small and written by us.
3. *Why keep the original commit on a rescore?* The scores describe the runs, and the runs were
   made with the old code. Labelling them with the new commit would claim the new code was
   measured when it wasn't.

## Run 2: live browser pane (`components/live-pane.tsx`, `lib/live-pane.ts`, `agent/loop.py: _observe`)

**What:** on the run page, the screenshot the agent looked at, the element it chose outlined,
the action and its reason, a step counter and a filmstrip of earlier steps.

**How:** the worker takes one viewport screenshot per step before the action and stores it
with the target's bounding box (from `getBoundingClientRect`, in viewport pixels) and the
viewport size in the step's `args`. `outlineStyle(box, viewport)` turns the box into CSS
percentages, clipping a partly off-screen box and drawing nothing for one entirely off screen.
The pane follows the newest step unless one is picked in the filmstrip.

**Why:** percentages keep the outline aligned at any display size without measuring the image.
Reusing the screenshot the model saw makes the pane honest: it shows exactly what the agent saw.

**Weak spots:** it updates every 1.5 s, so fast steps can be skipped (the filmstrip has them
all). Older runs have no boxes. A box is where the element was when the page was read; an
animation could move it before the click.

**Interview Q&A**
1. *Why percentages for the outline?* The screenshot is displayed scaled. Dividing the box by
   the viewport size gives positions that scale with the image, so no resize handling is needed.
2. *Why take the screenshot before the action?* "What is it about to click" needs the element
   on screen; after a click it may be gone or the page may have changed.
3. *How would you make it truly live?* Stream screencast frames (Chrome DevTools Protocol
   `Page.startScreencast`) over a WebSocket or SSE; the step data stays the same.

## Run 2: any model (`llm/openai_compat.py`, `llm/claude_cli.py`, `model_configs.py`, `secret_box.py`, `apps/web/lib/model-*.ts`, `secret-box.ts`)

**What:** an OpenAI-compatible client, per-workspace models with encrypted keys and a Test
connection check, a model picker on the run form, a leaderboard, and a local-only claude-cli.

**How:**
- `OpenAICompatClient` builds `messages` (system, then user content with an optional
  `image_url` data URL), `tools` as functions, `tool_choice: auto`; it reads `tool_calls` or a
  JSON call in the text. The key is a `SecretStr` and is redacted from error messages.
- Web: `createModelConfig` encrypts with `encryptSecret(key, workspaceId, MODEL_KEYS_SECRET)`;
  views only carry `keyHint`. `probeModel` checks endpoint safety, then a tool call and an
  image. `startRun` calls `usableModel` (own workspace + passed probe).
- Worker: `client_for_run` loads the run's model, checks workspace and probe, decrypts with the
  workspace id, checks the endpoint resolves to public addresses, builds the client. The runner
  records the run's provider and model and fails the run with the reason if any check fails.
- `ClaudeCliClient` runs `claude -p --output-format json`, lists the tools as JSON schemas in
  the prompt, validates the answer, retries once.

**Why:** "bring any model" is the product's main promise, so the safe parts (key storage,
isolation, SSRF) are enforced on both sides and tested, and the leaderboard shows how a model
does before anyone relies on it.

**Weak spots:** the worker checks the endpoint's address but the HTTP client resolves it again
(DNS rebinding is possible between the two). No key rotation. Prices are typed in by the user.
Models differ in tool-calling quirks that one client can't all smooth over. claude-cli spends
the owner's plan limit and is slow per step.

**Interview Q&A**
1. *How is workspace A prevented from using workspace B's key?* Every query filters by
   workspace, `startRun` and the worker both check the model's workspace, and the ciphertext
   is bound to the workspace id as AES-GCM associated data, so even a copied row won't decrypt.
2. *Why probe tool calling and vision before a run?* The agent can't act without tool calls
   or see layout without vision. A two-request check gives a clear error up front instead of
   a run that fails or wanders.
3. *Why one OpenAI-compatible client instead of SDKs per provider?* Most providers expose the
   same chat-completions shape; one small client covers them, and its request can be read and
   explained in full.

## Run 2: what the measurements taught (D52, `execute.py: replay_plans`, `agent/loop.py: element_number`, `observe.py` roles)

**What:** four small, generic fixes found by reading the steps of real runs rather than the scores:
replay also starts from the agent's last return to the start page; the prompt says a note never
replaces report_bug; element ids written as "[10]" or "10" are understood; number inputs are
recorded with their ARIA role, "spinbutton".

**Why:** each one cost a real bug or a step in a measured run. The scores alone (0% for Gemma)
said nothing about why; the step log did.

**Weak spots:** the Sonnet run shows replay is still the bottleneck: it lost two correct reports
for a reason not yet pinned down (Needs me #0 in PROGRESS).

**Interview Q&A**
1. *Your agent's score went down after you improved the prompt. What did you do?* Read the run's
   steps. The model had seen the bug but used the new note tool instead of reporting it, and the
   verifier threw away a correct report. Both were fixed in a way that helps on any site.
2. *Why does an ARIA role matter for replay?* Replay finds elements again with Playwright's
   `get_by_role`, which uses the browser's real role. Recording a different role means the
   lookup can never match.
3. *How do you make sure fixes aren't tuned to your demo shop?* Each fix is phrased as general
   tester behaviour, a test checks no demo-app detail reaches the prompt, and the holdout app,
   never tuned against, is scored next to the shop.

## Run 3: replay that waits for the page, and starts clean (`verify.py`, `execute.py: verify_and_dedupe`, `scan.py: guarded_browser`, `reverify.py`)

**What:** before each element step, replay waits (at most 5 s) until the browser is on the page
the agent was on and something matching the target exists. After the last step it waits until
the page's DOM has been quiet for 500 ms (at most 3 s) before the judge looks. Each replay plan
gets a fresh browser context (one browser and safety proxy for the whole run). Steps that
errored in the agent's own run are skipped. Each failure is stored with a kind
(`element_not_found`, `ambiguous_element`, `page_differs`, `timeout`, `navigation_error`,
`action_failed`, `no_element_recorded`), the step number and a detail, in
`bug.evidence.replay_failure`. `uv run worker reverify <run>` replays an old run's reports
read-only, and adds a judge's verdict with `--judge`.

**How it was found:** by replaying run be495c9f's stored steps offline. A fresh context per
replay failed exactly like the run, which ruled out the first guess (shared context) as the
cause of those failures. The page text showed the home page while the URL already said
`/products/6`. A client-side (pushState) link changes the URL without a page load, so "wait for
network idle" returns at once, and `locator.count()` doesn't wait at all.

**Why:** a correct report thrown away by the verifier is worse than a miss, because nobody sees
it. Result: 6 of 6 of Sonnet's reports from that run replay now (4 failed before), including
bugs 5 and 8, and all 16 earlier confirmed reports still replay.

**Weak spots:** a route that shows "Loading…" for more than 500 ms can still be judged too
early. A page whose URL differs between runs (an order id) costs up to 5 s per step before
replay tries anyway.

**Interview Q&A**
1. *Why did replay fail when the same steps worked by hand?* By hand there's always a pause.
   Replay acted within milliseconds of a client-side navigation, before the route had drawn its
   form, and nothing waited for it, because there was no page load to wait for.
2. *Why a fresh browser context per replay?* Cookies and localStorage from one replay (a cart, a
   sign-in) leaked into the next and changed what the judge saw (`Cart (6)` instead of
   `Cart (3)`). A context is cheap; a new browser per replay isn't, so there's one browser and
   many contexts.
3. *How do you know the fix didn't break what worked?* `reverify` replayed every confirmed agent
   report of 11 older runs: all 16 still replay. A new test replays two reports in a row where
   the first leaves state behind.

## Run 3: what verification throws away (`benchmark.py: score, stage_of, staged_match`, `lib/benchmark.ts: verification`)

**What:** the benchmark now sends every report to the judge, including the ones verification
dismissed, and records how each one ended: verified, judge said no, could not replay (with the
failure kind), or duplicate. The scores the customer sees (recall, precision) still count only
surviving reports. New numbers: recall and AI-only recall *before* verification, false alarms
before verification, the funnel (reported → verified, duplicates, discarded at replay by
reason), **correct but discarded**, and bugs lost. They appear in `bench` output, the
leaderboard and each latest-score card.

**Why:** run 2's lost Sonnet reports didn't show up in any number. A high "correct but
discarded" says verification is too strict. A big drop in false alarms from before to after
says it earns its keep.

**Weak spots:** the before-verification numbers depend on the judge matching reports that
weren't confirmed, which is the judge's least certain case. Duplicates aren't judged (they would
only repeat their original's match).

**Interview Q&A**
1. *What is "correct but discarded"?* A report that matches a planted bug but failed
   verification. It measures the verifier's false negatives, the cost of being strict.
2. *Why keep recall "after verification" as the headline?* It's what the customer gets. The
   before number is a diagnostic: it shows what the agent saw.
3. *Why store this in JSON details rather than columns?* Nothing sorts or filters on it. The
   page reads it from the row it already loads, so no migration was needed.

## Run 3: the sign-in flake (`app/layout.tsx`, `e2e/signin.e2e.ts`, `e2e/signin-loop.mjs`)

**What:** removed next-auth's `<SessionProvider>`. Nothing used `useSession`, and its
`/api/auth/session` requests on page load raced the sign-in button's CSRF token.

**How it was found:** a loop script signed in 50 times in fresh browsers and logged every auth
response when an attempt failed. 2 of 50 failed, each with `POST /api/auth/callback/demo` sending
the browser to Auth.js's "CSRF mismatch" redirect. Auth.js mints a new CSRF cookie for every auth
request that arrives without one, so the page's own session requests could overwrite the cookie
after the button had read its token. After the fix: 0 of 50 three times (one at a time, four in
parallel, and right after a server restart). The e2e retry helper is gone.

**Interview Q&A**
1. *How do you debug a 1-in-25 flake?* Make it happen on demand (a 50× loop), record everything
   on failure (the auth responses), and read what differs from a success.
2. *Why remove a component instead of retrying?* A retry hides a race that real users hit. The
   provider did nothing the app needed.
3. *What guards against it coming back?* An e2e test asserts the sign-in page makes no auth
   requests before the click.

## Run 3: the queue under load, and leases (`queue.py: Heartbeat, recover_expired_leases`, `runner.py`, `scripts/db_perf.py`, `docs/DATABASE.md`)

**What:** a test runs 8 workers at once against 300 queued runs and proves each run is claimed
exactly once. Runs now have a lease: `heartbeat_at` is renewed every 15 s by a background
thread. Any live worker fails runs silent for 60 s, in one conditional UPDATE, using the
database clock. A worker that was only frozen re-reads its run under a row lock before writing
the final status, so it can't undo the recovery. `scripts/db_perf.py` seeds 10k runs and 500k
steps in a throwaway database and EXPLAINs the hot queries. One index came out of it
(`benchmark_results(created_at)`). `docs/DATABASE.md` explains every table, key, index and the
queue.

**Interview Q&A:** see the end of `docs/DATABASE.md` (SKIP LOCKED, dead workers, proving an
index helps).

## Run 3: charter reminder (`agent/loop.py: untried_techniques`)

**What:** every observation lists the charter techniques the run hasn't used yet: an unusual
value in a field, double_click, reload, mobile viewport. Each one disappears once used.

**Why:** over 11 runs Gemma 12B used double_click, reload and the mobile viewport 0 times, so
bugs that need them were never triggered. A long charter in the system prompt is read once; a
short line in every observation is in front of the model at every step.

**Weak spots:** "unusual value" is a heuristic over the typed text: 0, 2+, negatives, very long
text, special characters, empty, or a malformed email in a field whose name mentions mail. A
weak model may tick a technique off once and never use it where it matters.

**Interview Q&A**
1. *Isn't that tuning to the benchmark?* The four techniques are standard exploratory testing
   heuristics, and the reminder knows nothing about any site. The holdout app, never tuned
   against, decides whether it stays.
2. *Why not put it in the system prompt?* It's already there. The system prompt stays
   byte-identical for caching, and a weak model follows what's in front of it each step.
3. *How do you know it changes behaviour?* Count technique use per run before and after
   (MISS_ANALYSIS) and compare holdout recall.

## Run 3: what the measurements taught (`docs/MISS_ANALYSIS.md`, D59–D62)

**What:** two Gemma benchmarks (before and after the charter reminder) and one Sonnet benchmark,
read per bug and per step: did the agent reach the bug's page, trigger the bug, report it, and
did verification keep it?

**What it showed:** after the replay fix (D53) verification is no longer the bottleneck: 0
correct reports discarded for Gemma, 1 for Sonnet. With the reminder (D59) Gemma reaches 7 of
12 judgement-bug states, but reports 1. Sonnet reports most of what it reaches: shop AI-only
38%, holdout 25%. For a small model the limit is recognising that a state is wrong.

**Weak spots:** 3 Gemma runs, 2 holdout runs, one Sonnet benchmark: small samples, and a
single run swings a bug from 0/3 to 2/3. The clean builds turned out to have real bugs, so
"false alarms" on them overstate Sonnet's noise. Bug 7 needs a guessed code.

**Interview Q&A**
1. *How do you know a change helped and isn't noise?* Count the behaviour it targets (technique
   use went 0 → 1 per run), not only the score, and check the holdout didn't drop.
2. *Why did Sonnet get "false alarms"?* It found real bugs in the clean build that aren't in
   the planted list. A benchmark's clean build has to be audited too.
3. *What would you do next?* Help the model compare expected with actual after each
   state-changing action, then measure on the holdout first.

## Run 4: expected vs. actual (`agent/expect.py`, `agent/loop.py: _compare, _unresolved_gate, _dismiss`, `agent/tools.py`)

**What:** before a state-changing action (click, double_click, select, reload, set_viewport) the
model writes `expect`: one line of what should happen, with concrete values ("Total: $36.00",
"'Profile saved'", "/cart"). The worker snapshots the page before the action and compares
afterwards, without another model call:
1. `Effect`: what changed: URL, lines added and removed, field values (`Quantity: 0 → 1`;
   password fields are never read), new console errors and failed requests.
2. `mismatches()`: the model expected a change and nothing changed; or a value it predicted
   (amount, number, quoted text, path) is nowhere in the page text, the fields or the URL.
   Numbers compare by value ($1,236 = 1236.00); values after "not" and dates are ignored.
3. A mismatch becomes a `Candidate`. The next observation shows it under UNRESOLVED MISMATCH;
   the model must `report_bug` (which resolves it) or `dismiss` it with a reason. Any other
   action is refused once; the second time the candidate expires as "ignored", so a stubborn
   model can't stall the run.

**Why:** run 3 showed Gemma reaching 7 of 12 bug states and reporting 1: it acted, glanced at
"ok" and moved on. Writing the expectation first makes the model do the arithmetic before it
sees the answer, and the deterministic comparison puts the contradiction in front of it. It's
the human tester's habit ("I expect $36") turned into a protocol.

**Cost:** about 20 output tokens per checked action for `expect`, and a candidate line only
when there is a mismatch. No extra model call. The comparison is a few string operations.

**Weak spots:** the check only knows what the model wrote: a vague "page updates" catches
only "nothing changed". A wrong expectation (the model miscalculates) creates a candidate it
must dismiss, costing a step. Values present anywhere on the page count as found, so "$12"
expected for a line and also shown elsewhere passes.

**Also in J1:**
- `ModelTimeout` (Ollama's read timeout): the loop retries the decision once with a
  `trimmed` observation (first line of the task, 30 elements, 4 recent steps, 800 characters of
  page text, no image). A second timeout ends the run cleanly (D61).
- claude-cli: if the CLI reports `permission_denials` (the model tried to call a tool
  natively), the answer is not taken; one corrective message says it does have the listed
  tools and must answer with the JSON object.
- `bench --holdout-first`: judge a change on the holdout before spending hours on the shop.

**Interview Q&A**
1. *Why not ask the model "was that right?" after every action?* That is a second model call
   per step (double cost and time) and a weak model says "yes". Writing the expectation first
   is cheaper and the comparison is deterministic.
2. *Isn't refusing actions until a mismatch is resolved heavy-handed?* Only once per
   candidate, then it expires. The point is that a contradiction can't scroll out of view.
3. *How do you know it helps and isn't benchmark tuning?* Nothing in it knows any site; it is
   kept only if the holdout (never tuned against) doesn't drop and clean-build false alarms
   don't rise (MISS_ANALYSIS, run 4).

## Run 4: testing apps behind a login (`login.py`, `login_checks.py`, `scan.py: guarded_browser`, `agent/loop.py`, `lib/login-setups.ts`)

**What:** a workspace saves, per site, how to sign in with a test account: a login form (URL,
username, encrypted password, optional selectors) or a recorded sign-in (Playwright storage state,
encrypted). Before a run, the worker signs in; every browser context it opens (crawl, agent,
each replay) is signed in. The agent never gets the credentials.

**How the secrets stay secret:** the password and storage state are AES-256-GCM encrypted (the
same scheme as model keys); views only say "saved". In the loop, the password and username are
scrubbed from every observation, step, bug report and replay prompt (`LoginConfig.scrub`), and
password fields are masked in every screenshot (`mask=[input[type=password]]`). Test sign-in
stores only ok/failed and a scrubbed reason.

**How the session stays alive:** logout, change/reset password and delete/close account are
denied on every target (even the demo shops, where the normal deny list is off). The crawler
skips logout links. If an action lands on the login page without the agent going there itself,
the session ended: the worker signs in again (max 3) and goes back.

**Why only on verified domains:** signing in submits credentials to a site. A worker that does
that wherever a workspace says could be used to stuff credentials into someone else's login.

**Weak spots:** "signed out" means "on the login URL"; an app that shows a login modal on the same
URL isn't detected. SSO/2FA needs a recorded storage state, which expires.

**Interview Q&A**
1. *Why not give the agent the credentials and let it log in?* The model (and its provider) would
   see them, it could type them anywhere, and a weak model fails flaky login forms. A deterministic
   sign-in is cheaper, safer and testable.
2. *How do you prove the password never leaks?* `test_signed_in_run.py` runs a whole signed-in run
   and searches every stored row and every model call for the password and username.
3. *Why scrub the username too?* It's personal data and often an email; the agent doesn't need it
   to test, and reports get shared.

## Run 4: running it from CI (`lib/api-keys.ts`, `lib/api-v1.ts`, `app/api/v1`, `openapi.json`, `webhooks.py`, `examples/ci`)

**What:** API keys per workspace; `POST /api/v1/runs`, `GET /api/v1/runs/{id}`, `GET
/api/v1/runs/{id}/report[?format=junit]`; signed webhooks when a run finishes; a CI script and a
GitHub Actions workflow that fail the build on a chosen severity.

**How:** keys are stored as SHA-256 hashes (random 256-bit keys don't need a slow hash) and looked
up by a unique index; a per-key, per-minute counter in Postgres (one atomic upsert) rate-limits
across servers. `startRun` is shared with the dashboard, so the API can't bypass quota or domain
verification. JUnit maps each reported bug to a failing test case. Webhooks: deliveries are rows
claimed with SKIP LOCKED, signed with HMAC-SHA256 over "timestamp.body", retried with backoff,
sent through the same egress guard as the browser.

**Weak spots:** a fixed window lets a burst of 2× the limit across a minute boundary; the CI
script polls (10 s) instead of waiting on the webhook; one event type only.

**Interview Q&A**
1. *Why sign the timestamp?* Without it, a captured request verifies forever (replay). With it, the
   receiver rejects anything older than 5 minutes.
2. *How does the rate limit stay correct with parallel requests?* `INSERT ... ON CONFLICT DO
   UPDATE ... RETURNING count` takes a row lock; concurrent requests queue on it and each sees its
   own count (tested with 8 parallel requests against a limit of 5).
3. *What stops a webhook from hitting your internal network?* The URL is checked after DNS by the
   same guard as the browser, and the POST goes through the guard proxy, which connects only to the
   address it checked, so DNS can't change its answer in between.

## Run 4: bugs across releases (`fingerprint.py`, `triage.py`, `lib/triage.ts`, `components/bug-card.tsx`)

**What:** every finding has a fingerprint; the run page marks each finding New or Still present
compared with the target's previous run and lists what was Fixed. Members triage a finding
(confirmed, false positive, won't fix, comment); the decision follows the fingerprint into later
runs, where false positives are hidden and counted per model.

**How:** fingerprint = hash(route with ids → `:id` | category | key). Keys are chosen to survive
run-to-run noise: numbers and bundle hashes are removed from messages, agent reports are keyed by
the element they acted on, so a reworded title stays the same bug. The worker sets it on insert
(SQLAlchemy hook) and suppresses triaged false positives at the end of a run; the web computes
new/still/fixed from two runs' fingerprints.

**Weak spots:** a page whose ids are slugs (`/products/desk-lamp`) is one route per product, so the
same bug on two products is two findings; an agent report without an element falls back to title
words, which a very different wording breaks.

**Interview Q&A**
1. *Why not use the title?* Agent titles change wording every run, deterministic titles contain ids
   and numbers. The element or message, normalised, is the stable part.
2. *Why is the same message on two pages two bugs?* A developer fixes a page, not a message; and a
   false positive on one page shouldn't hide a real error on another.
3. *What does triage teach you?* A false-positive rate per model on real customer sites, not only on
   our benchmark, which is the number a buyer cares about.
