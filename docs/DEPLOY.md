# Running AI Test Agent in production

What's in the repo: two images (`Dockerfile.web`, `Dockerfile.worker`) and a production stack in
`docker-compose.prod.yml` (Postgres, an S3-compatible object store, a one-off migration, the web app,
N workers). It is a separate file from `docker-compose.yml` (the dev database), so dev commands
never need production secrets and production never touches the dev database. It runs on any
host with Docker; a managed platform needs the same pieces (see "On a managed platform").

```sh
cp .env.example .env.prod      # then fill in the production values below (never commit it)
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.prod ps
curl -s http://localhost:3100/api/ready      # {"status":"ready","database":"ok"}
```

Order of start-up: Postgres becomes healthy and the object store starts → `migrate` runs `prisma
migrate deploy` once → `web` and the workers start. The workers create the private `screenshots`
bucket on first use if it doesn't exist.

The object store in the compose file is SeaweedFS (Apache-2.0, S3 API): MinIO's public images are no
longer pullable. Any S3-compatible store works the same way (AWS S3, Cloudflare R2, Garage, a MinIO
you run yourself): only the `S3_*` variables change.
A release is the same command with new images: migrations run before any new code serves traffic.

## Environment

| Variable | Used by | What |
|---|---|---|
| `DATABASE_URL` | web, worker | Postgres. The compose profile builds it from `PROD_DB_USER` / `PROD_DB_PASSWORD`. |
| `NEXTAUTH_SECRET` | web | Signs sessions. 32+ random bytes. Rotating it signs everyone out. |
| `NEXTAUTH_URL`, `PUBLIC_BASE_URL` | web | The public address (links in API responses, invitations, sign-in callbacks). |
| `MODEL_KEYS_SECRET` | web, worker | 32 random bytes, base64. Encrypts workspace model keys, test-account passwords, recorded sign-ins and webhook secrets (AES-256-GCM). Losing it makes them unreadable; leaking it exposes them. Back it up separately from the database. |
| `STORAGE=s3`, `S3_*` | web, worker | Screenshots in an S3-compatible bucket. `S3_ENDPOINT` is the address the containers use, `S3_PUBLIC_ENDPOINT` the one browsers use for presigned links. |
| `LLM_PROVIDER`, `ANTHROPIC_API_KEY` / `OLLAMA_URL` / `OPENAI_COMPAT_*` | worker | The server's default model (workspaces can bring their own). |
| `METRICS_TOKEN` | web | If set, `/api/metrics` needs `Authorization: Bearer <token>`. |
| `LOG_FORMAT=json` | web, worker | One JSON object per log line, with `run_id` / `workspace_id` in the worker. |
| `DEV_MODE` | web, worker | **false in production.** True allows the local demo shops on private addresses and the local claude-cli provider. |
| `WORKERS` | compose | Number of worker containers. |
| `MAX_RUN_SECONDS`, `MAX_STEPS`, `MAX_RUN_COST_USD` | worker | Hard limits per run (API callers can only lower them). |

GitHub/email sign-in providers are configured as in the README (`AUTH_GITHUB_*`, `EMAIL_*`).

## Health, metrics, logs

- `GET /api/health`: liveness (the process answers). `GET /api/ready`: readiness (the database
  answers); route traffic only to ready instances.
- `GET /api/metrics`: Prometheus text, computed from the database so every instance reports the
  same totals: runs by status, queue depth, run durations, model tokens and cost, webhook
  deliveries by status. Alert on a growing `ata_queue_depth` (add workers) and on
  `ata_webhook_deliveries{status="failed"}`.
- Worker liveness is its run lease: a worker that stops heart-beating has its run failed by
  another worker within ~90 s (docs/DATABASE.md, "The queue").

## Scaling workers

Workers are stateless: they claim runs from Postgres with `FOR UPDATE SKIP LOCKED` (each run
exactly once, tested with 8 concurrent workers). Add workers with `WORKERS=N` (or replicas on your
platform). Each worker runs one browser; size it at ~1 CPU and ~1.5 GB RAM. With a local model,
the model server is the bottleneck, not the workers.

## Backups and retention

- **Postgres:** daily `pg_dump -Fc` (or the platform's point-in-time recovery), kept 30 days,
  restored into a scratch database once a month to prove the backup works. Back up
  `MODEL_KEYS_SECRET` separately (a password manager or a KMS), never in the same place as the
  dump.
- **Screenshots (object store):** bucket versioning or replication if you need them after a disaster;
  they are evidence, not the system of record.
- **Retention:** each workspace has `retention_days` (default 30). Once an hour a worker deletes
  the screenshots and step timelines of older runs; runs and findings stay (their fingerprints
  compare releases). Old rate-limit windows are removed too.

## On a managed platform

Any container host works: one web service (port 3000, health `/api/health`), one worker service
with N replicas (no port), a managed Postgres 17, an S3-compatible bucket (S3, R2, GCS with HMAC
keys), and a one-off job that runs the `migrate` target before each release. The database role the
app uses must own the tables and be allowed to `SET ROLE app_tenant` (the migration grants it); it
must not be a superuser, or row-level security can be switched off by whoever controls a session.

## Threat model (short)

| Threat | What could happen | What stops it |
|---|---|---|
| **SSRF** | A run, a redirect or a webhook URL reaches the internal network or a cloud metadata endpoint. | Every browser request and webhook POST goes through `GuardProxy`: the host is resolved and checked (no private, loopback, link-local or metadata addresses), and the proxy connects to the checked address, so DNS rebinding can't swap it. Redirects are checked hop by hop; webhooks don't follow redirects. Interactive runs only on verified domains. |
| **Prompt injection from tested sites** | Page text tells the model to stop testing, leak data or click something destructive. | Page text is fenced as untrusted data; the model can only choose tools, and the worker checks every choice: a deny list (payments, deletion, account changes, logout when signed in), mode rules, budgets, same-site navigation. The model never sees credentials. A test page with an injection is part of the test suite. |
| **Credential handling** | Test-account passwords, model keys, API keys or webhook secrets leak. | Passwords, model keys, recorded sign-ins and webhook secrets are encrypted at rest (AES-256-GCM, workspace id as associated data); API keys and invitation tokens are stored only as SHA-256 hashes; secrets are shown once, never returned by an API, scrubbed from prompts, steps, reports and logs, and password fields are masked in screenshots. Sign-in setups only work on verified domains. |
| **Tenant isolation** | One workspace reads or changes another's runs, keys or settings. | Every query filters by the caller's workspace; roles are checked per route (tested for every route and role); Postgres row-level security filters again for the `app_tenant` role, failing closed when no workspace is set. Share links use unguessable tokens and can be revoked. |
| **Webhook spoofing and replay** | Someone posts fake "run finished" events to a customer's endpoint, or replays a captured one. | Each delivery carries `X-ATA-Signature: t=…,v1=HMAC-SHA256(secret, "t.body")`; receivers verify it and refuse timestamps older than 5 minutes (docs/API.md). |
| **Abuse of the API** | A leaked key starts thousands of runs. | Per-key rate limit (60/min), the workspace's monthly quota, revocation that takes effect at once, `last_used_at` to spot unused keys. |
| **Supply chain** | A compromised GitHub Action or dependency. | Actions are pinned by commit SHA (Dependabot proposes updates); npm and uv installs use lock files; images are built from pinned base tags. |

What this model doesn't cover yet, and needs people or money (docs/ROADMAP.md): an external
penetration test, a security review of the deployment, SOC 2 controls, and incident response.
