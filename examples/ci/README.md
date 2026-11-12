# Run AI Test Agent from CI

- `ata-run.mjs`: a dependency-free Node 20+ script. It starts a run through the public API,
  waits for it, prints a summary, writes JUnit XML and exits non-zero when a bug at or above
  `--fail-on` (default `high`) was found. Exit codes: 0 ok, 1 bugs found, 2 the run failed or
  timed out, 3 bad usage or the API refused.
- `github-actions.yml`: the same in a GitHub Actions workflow, with the JUnit report shown as
  test results. Copy it to `.github/workflows/` in your repository.

```sh
export ATA_API_URL=https://ata.example.com ATA_API_KEY=ata_…
node examples/ci/ata-run.mjs https://staging.example.com --mode interactive --fail-on high --junit report.xml
```

The API is documented in `docs/API.md` and `apps/web/openapi.json`. This repository's own CI
never runs these files: they call a real deployment.
