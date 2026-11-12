# Roadmap: from portfolio project to a product teams pay for

Honest status after run 4 (2026-11-11). "Code" means something this repo can do by itself;
the last column is what code alone can't do: it needs money, people or legal work.

| Phase | What it adds | Done already | Needs money, people or legal work |
|---|---|---|---|
| 0. Demo (done) | Paste a URL, an agent explores, a report with evidence; a benchmark with planted bugs and a holdout app | Agent loop, deterministic checks, replay verification, benchmark + leaderboard, safety (SSRF guard, deny list, domain verification), workspaces, encrypted model keys | Nothing |
| 1. Pipeline-ready (done in run 4) | Teams run it in CI on every release, on apps behind a login, and track findings across releases | Done: login setups, `/api/v1` + hashed API keys + JUnit + signed webhooks + CI example, fingerprints and triage, roles and invitations, audit log, row-level security, Docker images, S3 storage, retention, health and metrics, a production stack run locally end to end | A real CI pilot with a friendly team (people); a domain and TLS for a public API (small cost) |
| 2. Hosted beta | A public instance a team can sign up for | Ready to deploy: images, `docker-compose.prod.yml`, `docs/DEPLOY.md` (run 4). Missing: every web query through the RLS client, email for invitations | Hosting for web, workers, Postgres and object storage (money, ~$50–200/month at beta scale); model costs per run, which decide pricing; transactional email for invites and magic links (small cost); error tracking and uptime monitoring; on-call by someone |
| 3. Trust | Companies let it touch their staging apps and test accounts | Credentials encrypted, secrets never shown or logged, tenant isolation in the app and the database, threat model (run 4) | Terms of service, privacy policy and a DPA (a lawyer); an external security review or pen test (money); backups tested by restore drills; SOC 2 Type I, then Type II (money + months, usually with a compliance platform) |
| 4. Sellable | Plans, billing, support | Usage and quota per workspace | Pricing (owner's decision, from measured model cost per run); Stripe billing; a support channel and docs site; SSO/SAML for larger customers; a company or legal entity to sign contracts |
| 5. Better than a manual pass | Recall high enough that a team trusts a clean report | Benchmark proves where models stand: Sonnet 38% / Gemma 8% AI-only on the shop | More planted-bug apps (other domains), larger and more varied benchmarks, model spend to measure frontier models (money), and real customer triage data to learn precision on real sites |

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
