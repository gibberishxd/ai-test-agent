# Roadmap: from portfolio project to a product teams pay for

Honest status after run 5 (2026-11-12). "Code" means something this repo can do by itself;
the last column is what code alone can't do: it needs money, people or legal work.

| Phase | What it adds | Done already | Needs money, people or legal work |
|---|---|---|---|
| 0. Demo (done) | Paste a URL, an agent explores, a report with evidence; a benchmark with planted bugs and a holdout app | Agent loop, deterministic checks, replay verification, benchmark + leaderboard, safety (SSRF guard, deny list, domain verification), workspaces, encrypted model keys | Nothing |
| 1. Pipeline-ready (done in run 4) | Teams run it in CI on every release, on apps behind a login, and track findings across releases | Done: login setups, `/api/v1` + hashed API keys + JUnit + signed webhooks + CI example, fingerprints and triage, roles and invitations, audit log, row-level security, Docker images, S3 storage, retention, health and metrics, a production stack run locally end to end | A real CI pilot with a friendly team (people); a domain and TLS for a public API (small cost) |
| 2. Hosted beta | A public instance a team can sign up for | Ready to deploy: images, `docker-compose.prod.yml`, `docs/DEPLOY.md` (run 4). Missing: every web query through the RLS client, email for invitations | Hosting for web, workers, Postgres and object storage (money, ~$50–200/month at beta scale); model costs per run, which decide pricing; transactional email for invites and magic links (small cost); error tracking and uptime monitoring; on-call by someone |
| 3. Trust | Companies let it touch their staging apps and test accounts | Credentials encrypted, secrets never shown or logged, threat model (run 4); non-superuser app roles, every query under row-level security, audit log written and protected by the database (run 5) | Terms of service, privacy policy and a DPA (a lawyer); an external security review or pen test (money); backups tested by restore drills; SOC 2 Type I, then Type II (money + months, usually with a compliance platform) |
| 4. Sellable | Plans, billing, support | Plans with limits enforced by Postgres, usage events per run (explorer and reviewer cost apart), usage and admin pages (run 5); see "Billing" below for Stripe | Pricing (owner's decision, from measured model cost per run); Stripe billing; a support channel and docs site; SSO/SAML for larger customers; a company or legal entity to sign contracts |
| 5. Better than a manual pass | Recall high enough that a team trusts a clean report | Benchmark proves where models stand: Sonnet 38% (run 3); Gemma alone 7%, Gemma + local 14B reviewer 19% AI-only on the shop (run 5); verification measures changes, not screenshots | More planted-bug apps (other domains), larger and more varied benchmarks, model spend to measure frontier models (money), and real customer triage data to learn precision on real sites |

## What moves the product most, in order
1. Recall on judgement bugs (phase 5): a clean report is only worth something if it's
   trustworthy. Run 4's expected-vs-actual check finds the contradictions; a small model still
   dismisses most of them, so the next step is a stronger judge for flagged mismatches.
2. A real pilot (phase 1→2): one team running it in CI says more than any benchmark.
3. Legal and security basics (phase 3) before any customer gives it a test account.

## What moved in run 4
Phase 1 is done in code. The product can be adopted by a team's pipeline today on a self-hosted
instance. What it can't do yet is find most judgement bugs with a small local model: Gemma 4 12B
stays at ~8% AI-only recall on the shop even with an expected-vs-actual check (it explains the
mismatches away). Phase 5 (recall) is now the limit, and the cheapest next lever is a stronger
model for the agent or only for judging flagged mismatches.

## Billing: what plugging in Stripe would take (run 5, K4)
Run 5 built everything up to the payment itself: plans with limits in the database, every
workspace on a plan, limits enforced by Postgres when a run starts (`consume_quota`), seats when
an invitation is accepted, retention capped by the plan, and a usage event per finished run with
the explorer's and the reviewer's tokens and cost apart (`usage_events`). What Stripe would add:

1. **Products and prices** in Stripe for Team and Business (the prices are the owner's decision,
   from the measured cost per run), their ids stored on `plans` (a `stripe_price_id` column).
2. **Checkout and the customer portal:** an owner-only "Upgrade" button that creates a Checkout
   session for the workspace (`workspaces.stripe_customer_id`); the portal handles card changes,
   invoices and cancellations, so we never touch card data (PCI scope stays with Stripe).
3. **A webhook endpoint** (`/api/stripe/webhook`, signature verified with the endpoint secret):
   `checkout.session.completed` and `customer.subscription.updated|deleted` set `plan_id` (and a
   `subscription_status`, so a failed payment can downgrade after a grace period). Idempotent by
   event id, stored in a `stripe_events` table.
4. **Metered usage (optional):** if model cost is billed on top of the plan, a job reports each
   month's `usage_events` sums to Stripe's meter API, keyed by usage event id so a retry can't
   bill twice.
5. **Tax and invoices:** Stripe Tax and the company's legal entity (phase 4 above); a terms page
   and a refund policy.

Code-wise this is a few days: two columns, one table, three routes, tests against Stripe's test
mode and a local webhook forwarder. It is not built because it needs a Stripe account, a
company and prices.

## What moved in run 5
Phase 3 and 4 moved in code: the database now enforces isolation, the audit trail, quota and
plan limits itself, and usage is recorded the way a bill would need it. Phase 5 moved for the
first time with a local model: measured verification plus a reviewer tier took the shop's
judgement-only recall from 0% to 19% on a 16 GB laptop. The holdout didn't move, so the limit is
still model quality; the cheapest next step is a hosted reviewer (a small API budget) behind the
free local explorer, with its cost per run now recorded separately.

## Product roadmap after run 6

A plan, not built yet. It replaces "What moves the product most, in order" above as the order
of work; the phase table stays as the status of what exists.

**The rule for every item:** it must make the product find more real bugs, raise fewer false
alarms, fit how teams already work, or make it safe to buy. Nothing is added only to show a
technology.

Sizes are rough, for one person working with an AI assistant: S = days, M = 1–2 weeks,
L = 3–6 weeks.

### 1. Testing against the team's own requirements (M–L)
- **Why a customer pays:** today the agent judges a page by general sense ("a total should match
  its lines"). Most real bugs break a rule only the team knows: "free shipping above $50",
  "a manager can't approve their own expense". A run that knows the spec finds bugs no generic
  tester can.
- **What it needs:** per target, upload specs and acceptance criteria (Markdown, PDF, or pasted
  tickets); split them into chunks; embed them and store them with the `pgvector` extension in
  our own Postgres (no new database; the dev and prod images move from `postgres:17` to a
  pgvector build of it). For each page the agent visits, retrieve the few most relevant chunks
  and put them in the agent's and the reviewer's prompt as the expected behaviour. An embedding
  model must be chosen (a local one through Ollama, or a hosted one: Anthropic has no embedding
  model). The specs go under row-level security like everything else, and are treated as
  untrusted text in the prompt (prompt-injection rules as for page text).
- **How we measure it:** write specs for the holdout app (apps/demo2) the way a team would, not
  the bug list, and run the holdout benchmark with and without them. It works if judgement-only
  recall rises and clean-build false alarms don't. A guard test keeps planted-bug details out of
  the specs, as it does for the prompt today.

### 2. Critical flows (M)
- **Why a customer pays:** every team has 5–10 journeys that must never break (sign up, check
  out, reset a password). They want those covered on every release, cheaply and the same way
  each time, with exploration on top.
- **What it needs:** per target, a few journeys in plain language ("add two items, apply a
  code, pay with the test card"). The agent always covers them first. Once a journey passes, its
  steps are saved as a replayable Playwright script (replay verification already re-runs a
  report's steps, so most of the machinery exists). Later runs replay the script with no model;
  the model is called only when a replay breaks, to tell a real regression from a changed page
  and to repair the script.
- **How we measure it:** flow coverage (the share of a target's flows checked in a run), how
  often a broken replay is a real regression versus a changed page, and cost per run with flows
  replayed against the same flows explored by the model each time.

### 3. Default model setup and the real Claude API (S–M)
- **Why a customer pays:** cost and quality decide the price. Run 6 measured Haiku 5.5 as the
  agent at about $0.06–0.09 a run (estimated) with the best cost per verified bug, and Sonnet 5.5
  as the thorough option (D91). That is only an estimate until the API path has run for real.
- **What it needs:** an API key and a budget (the owner's); a smoke run through `ClaudeClient`;
  prompt caching checked (`cache_read_input_tokens` above 0 from the second step); then the
  default set from the numbers (Haiku as the agent, Sonnet as an option), which is the owner's
  call.
- **How we measure it:** a Haiku benchmark through the API compared with run 6's claude-cli
  estimate: cost per run, cost per verified bug, and recall within the run-to-run noise.

### 4. GitHub integration (M)
- **Why a customer pays:** teams review changes in pull requests. Findings that show up there,
  on the preview deploy of that change, get fixed before merge; a separate dashboard gets
  forgotten.
- **What it needs:** a GitHub App, building on the API and CI script that exist (`/api/v1`,
  `examples/ci`): start a run on a PR's preview URL (Vercel, Netlify and similar post it as a
  deployment), post one PR comment with the findings (new since the base branch, by fingerprint),
  and a pass/fail status check with a threshold the team sets. Preview domains must still be
  verified, as targets are today.
- **How we measure it:** a user check: one team uses it on real pull requests for two weeks.
  How many findings get fixed before merge, and how many comments are dismissed as noise.

### 5. Export to Jira, Linear and GitHub Issues (S–M)
- **Why a customer pays:** a bug that isn't in the team's tracker doesn't get fixed.
- **What it needs:** per workspace connections (OAuth), a "create issue" action on a finding and
  an optional automatic export of confirmed findings. The fingerprint (run 4) dedups: a finding
  already exported updates its issue instead of opening another, and an issue closed as "won't
  fix" feeds triage as a false positive.
- **How we measure it:** a user check: exported issues that are kept and fixed, against ones
  closed as duplicates or noise; zero duplicate issues for the same fingerprint across runs (a
  test).

### 6. MCP server (S)
- **Why a customer pays:** developers already work in Claude Code or Cursor. "Test my change on
  staging and tell me what broke" from the editor fits how they work, with no new tab.
- **What it needs:** a small MCP server that wraps `/api/v1` with the workspace's API key: start
  a run, poll its status, read the report and its findings. No new logic; the API's limits and
  domain checks apply.
- **How we measure it:** a user check: a developer starts a run and fixes a finding without
  leaving the editor; adoption counted by runs started through MCP.

### 7. Evaluations in CI, and tracing (M)
- **Why a customer pays:** indirectly, through trust. A change to the prompt or the agent's code
  must not quietly make it find fewer bugs. Today the benchmark is run by hand.
- **What it needs:** a small benchmark subset (a few planted bugs from each app, fixed seeds,
  one cheap model) that runs on every change to the agent's prompt or code and fails the change if
  recall drops or false alarms rise beyond the noise. It can't call the owner's subscription:
  it needs an API budget, or a local model on a self-hosted runner. Per-run tracing with
  OpenTelemetry (each step, model call, replay and its tokens and cost as spans), building on
  the JSON logs with `run_id` and the Prometheus metrics that exist.
- **How we measure it:** the check itself: it blocks a deliberately broken prompt in a test, and
  a slow or expensive run can be found from its trace in minutes.

### 8. A hosted version on AWS (L, plus money and legal work)
- **Why a customer pays:** most teams won't run Postgres, object storage and browser workers
  themselves; they buy a service.
- **What it needs:** one cloud (AWS): managed Postgres with pgvector, S3, containers for web and
  workers, browser workers isolated from each other and from our own network, with tenant
  isolation as it is today (row-level security, per-run browser contexts, the SSRF guard);
  backups tested by restore; error tracking and uptime monitoring. An external security review
  or pen test, terms of service, a privacy policy and a DPA before the first paying customer
  (phase 3 above).
- **How we measure it:** the security review passes with its findings fixed; a restore drill
  works; one pilot team uses it for a month without our help.

### Not planned, and why
- **FastAPI:** the API exists in Next.js (`/api/v1`, OpenAPI, API keys, rate limits). A second
  API service would add a deployment and a language boundary and find no more bugs.
- **LangChain or LangGraph:** our agent loop is small, tested, and measured by the benchmark. A
  framework would replace code we understand with code we don't, and the benchmark would have to
  prove it isn't worse.
- **Fine-tuning a model, and a separate bug classifier:** there isn't enough data yet. Both need
  thousands of real findings labelled by teams (confirmed, fixed, false positive), which only
  real customers produce. Triage already records those labels for later.

### Before building
Talk to 5 QA leads or engineering managers first. Run the product on their own site (with their
permission, on a staging URL they verify) and show them the report. Ask what they would pay for,
and reorder this list by their answers. Items 1 and 2 are first only on our reading of the
benchmark; customers may put 4 or 5 first.
