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
(steps, time, cost), loop detection (same action 3× in a row) or the Stop button.

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
