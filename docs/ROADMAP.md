# Roadmap: from portfolio project to a product teams pay for

Honest status as of run 4 (2026-11-11). "Code" means something this repo can do by itself;
the last column is what code alone can't do: it needs money, people or legal work.

| Phase | What it adds | Done already | Needs money, people or legal work |
|---|---|---|---|
| 0. Demo (done) | Paste a URL, an agent explores, a report with evidence; a benchmark with planted bugs and a holdout app | Agent loop, deterministic checks, replay verification, benchmark + leaderboard, safety (SSRF guard, deny list, domain verification), workspaces, encrypted model keys | Nothing |
| 1. Pipeline-ready (run 4) | Teams run it in CI on every release, on apps behind a login, and track findings across releases | Being built in run 4: login setups, `/api/v1` + API keys + JUnit + webhooks + CI example, fingerprints and triage, roles, audit log, row-level security, Docker images, S3 storage, health and metrics | A real CI pilot with a friendly team (people); a domain and TLS for a public API (small cost) |
| 2. Hosted beta | A public instance a team can sign up for | Production compose stack and `docs/DEPLOY.md` (run 4) | Hosting for web, workers, Postgres and object storage (money, ~$50–200/month at beta scale); model costs per run, which decide pricing; transactional email for invites and magic links (small cost); error tracking and uptime monitoring; on-call by someone |
| 3. Trust | Companies let it touch their staging apps and test accounts | Credentials encrypted, secrets never shown or logged, tenant isolation in the app and the database, threat model (run 4) | Terms of service, privacy policy and a DPA (a lawyer); an external security review or pen test (money); backups tested by restore drills; SOC 2 Type I, then Type II (money + months, usually with a compliance platform) |
| 4. Sellable | Plans, billing, support | Usage and quota per workspace | Pricing (owner's decision, from measured model cost per run); Stripe billing; a support channel and docs site; SSO/SAML for larger customers; a company or legal entity to sign contracts |
| 5. Better than a manual pass | Recall high enough that a team trusts a clean report | Benchmark proves where models stand: Sonnet 38% / Gemma 8% AI-only on the shop | More planted-bug apps (other domains), larger and more varied benchmarks, model spend to measure frontier models (money), and real customer triage data to learn precision on real sites |

## What moves the product most, in order
1. Recall on judgement bugs (phase 5): a clean report is only worth something if it's
   trustworthy. Run 4's expected-vs-actual check is the next step.
2. A real pilot (phase 1→2): one team running it in CI says more than any benchmark.
3. Legal and security basics (phase 3) before any customer gives it a test account.
