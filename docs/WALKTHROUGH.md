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
