# Public API (v1)

Run AI Test Agent from CI: start a run, wait for it, read the findings as JSON or as JUnit XML,
and get a signed webhook when it finishes. The contract is `apps/web/openapi.json` (served at
`/api/v1/openapi.json`); tests check the routes against it.

## Authentication
Create a key in **Settings → CI integration → API keys**. It is shown once; store it in your CI's
secrets. Send it on every request:

```
Authorization: Bearer ata_…
```

- Only a SHA-256 hash of the key is stored. A revoked key stops working at once.
- Each key may make **60 requests per minute** (HTTP 429 with `Retry-After` beyond that).
- Runs count against the workspace's monthly quota, exactly as runs started from the dashboard.
- Interactive runs need a verified domain (Settings → Domains); apps behind a login need a
  sign-in setup (Settings → Sign-in).

## Start a run
`POST /api/v1/runs`

| Field | | |
|---|---|---|
| `target_url` | required | the URL to test |
| `mode` | `passive` (default) or `interactive` | interactive clicks and types; needs a verified domain |
| `focus` | optional | what to concentrate on, e.g. `"checkout"` |
| `model_id` | optional | one of the workspace's models; default: the server's model |
| `max_steps` | 1–100 | lowers the agent's step limit |
| `max_minutes` | 1–60 | lowers the run's time limit |

```sh
curl -sS -X POST "$ATA_API_URL/api/v1/runs" \
  -H "Authorization: Bearer $ATA_API_KEY" -H "Content-Type: application/json" \
  -d '{"target_url": "https://staging.example.com", "mode": "interactive", "max_minutes": 10}'
```

`201 Created`, with a `Location` header:

```json
{
  "id": "1067b96b-3045-416e-98b6-e13291c71ce3",
  "status": "queued",
  "finished": false,
  "target_url": "https://staging.example.com/",
  "counts": { "critical": 0, "high": 0, "medium": 0, "low": 0 },
  "links": {
    "self": "https://ata.example.com/api/v1/runs/1067b96b-…",
    "report": "https://ata.example.com/api/v1/runs/1067b96b-…/report",
    "junit": "https://ata.example.com/api/v1/runs/1067b96b-…/report?format=junit",
    "dashboard": "https://ata.example.com/runs/1067b96b-…"
  }
}
```

Errors: `400` with `errors` per field (`target_url`, `mode`, `model_id`, `max_steps`, …), `401`
for a missing or revoked key, `429` for the rate limit or the monthly quota.

## Wait for it
`GET /api/v1/runs/{id}`: poll every 10 seconds until `finished` is `true`. `status` is then
`done`, `failed` or `stopped`; `counts` has the reported bugs per severity.

## Read the findings
`GET /api/v1/runs/{id}/report`: every bug the run reports (bugs that replay verification
dismissed are left out), with severity, page, expected, actual and repro steps.

`GET /api/v1/runs/{id}/report?format=junit`: JUnit XML, one failing test case per bug (its
severity as the failure type), or one passing case when nothing was found. Every CI system can
show it as test results.

```sh
curl -sS "$ATA_API_URL/api/v1/runs/$RUN_ID/report?format=junit" \
  -H "Authorization: Bearer $ATA_API_KEY" -o ata-report.xml
```

## In a pipeline
`examples/ci/ata-run.mjs` does all of the above and fails the build on a chosen severity:

```sh
node examples/ci/ata-run.mjs https://staging.example.com \
  --mode interactive --fail-on high --max-minutes 10 --junit ata-report.xml
```

Exit codes: 0 no bug at or above `--fail-on` · 1 bugs found · 2 the run failed or timed out ·
3 bad usage or the API refused. `examples/ci/github-actions.yml` is a ready-to-copy workflow.

## Webhooks
Add an endpoint in **Settings → CI integration → Webhooks**. Its signing secret (`whsec_…`) is
shown once. When a run finishes we POST:

```
POST /your/endpoint
Content-Type: application/json
X-ATA-Event: run.finished
X-ATA-Delivery: 5b0c…            (the delivery id: use it to ignore duplicates)
X-ATA-Signature: t=1762855436,v1=6f2a…

{"id":"5b0c…","event":"run.finished","created_at":"2026-11-11T10:03:56Z",
 "data":{"id":"1067b96b-…","status":"done","target_url":"https://staging.example.com/",
         "mode":"interactive","duration_s":300,"counts":{"critical":0,"high":1,"medium":0,"low":2},
         "error":null}}
```

**Verify every request** before trusting it: recompute the signature over the timestamp and the
raw body, and refuse old timestamps so a captured request can't be replayed.

```ts
import { createHmac, timingSafeEqual } from "node:crypto";

export function verify(secret: string, header: string, rawBody: string, toleranceS = 300): boolean {
  const parts = Object.fromEntries(header.split(",").map((p) => p.split("=", 2) as [string, string]));
  const timestamp = Number(parts.t);
  if (!Number.isInteger(timestamp) || Math.abs(Date.now() / 1000 - timestamp) > toleranceS) return false;
  const expected = createHmac("sha256", secret).update(`${timestamp}.${rawBody}`).digest("hex");
  const given = Buffer.from(parts.v1 ?? "", "utf8");
  return given.length === expected.length && timingSafeEqual(given, Buffer.from(expected, "utf8"));
}
```

- Answer with any 2xx within 10 seconds. Anything else (or no answer) is retried after 30 s,
  2 min, 8 min, 32 min and about 2 h; after 6 attempts the delivery is marked failed. The last
  10 deliveries per endpoint, with status code and error, are listed in Settings.
- Endpoints must be public: private, internal and cloud-metadata addresses are refused, checked
  again after DNS at send time, and the POST goes through the same egress guard as the browser.
- Redirects aren't followed. Credentials in the URL are refused: verify the signature instead.
